# Thiết kế chuyển vùng, định tuyến và điều phối khôi phục

## 1. Disaster recovery là một quy trình kiến trúc, không phải một nút bấm

Disaster recovery (DR) là khả năng khôi phục ứng dụng, dữ liệu và hoạt động nghiệp vụ sau một sự cố nghiêm trọng. Sự cố có thể bắt đầu từ một máy chủ, availability zone (AZ), region, nhà cung cấp, lỗi cấu hình, ransomware, mất kết nối mạng hoặc thao tác vận hành làm hỏng dữ liệu. Một kế hoạch DR chỉ có giá trị khi tổ chức biết cách phát hiện đúng sự cố, quyết định có chuyển vùng hay không, ngăn hệ thống cũ tiếp tục ghi, khôi phục dữ liệu và dependency, định tuyến người dùng tới môi trường thay thế, rồi xác minh nghiệp vụ thực sự hoạt động.

**Failover không đơn giản là đổi DNS hoặc promote database replica.** Nếu traffic chuyển sang region mới nhưng secret, KMS key, queue, identity provider, object storage, network route hoặc capacity chưa sẵn sàng, ứng dụng vẫn có thể ngừng hoạt động. Nếu primary cũ chưa bị fence, hai region có thể cùng nhận ghi và tạo split-brain. Nếu replica bất đồng bộ, dữ liệu đã xác nhận ở region cũ có thể chưa có mặt ở region mới.

Trong module **CLOUD_ARCHITECTURE**, thiết kế DR phải nối yêu cầu nghiệp vụ với failure domain, replication, quyền điều phối, routing, backup, security và khả năng vận hành. Mục tiêu là phục hồi đúng thứ tự, trong RTO/RPO đã cam kết, với chi phí và mức độ phức tạp có thể duy trì theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt backup, high availability, disaster recovery, failover và failback.
- Xác định failure domain, blast radius, RTO và RPO cho từng workload.
- Thiết kế quy trình phát hiện, đánh giá, phê duyệt và kích hoạt DR.
- Điều phối thứ tự fencing, data recovery, dependency recovery và traffic cutover.
- Chọn global routing, DNS, load balancer, service discovery và endpoint strategy.
- Xử lý dữ liệu bất đồng bộ, replication lag, replay và split-brain.
- Xây dựng runbook, automation, game day và tiêu chí kết thúc DR.

## 2. Phân biệt HA, backup và DR

Các khái niệm liên quan nhưng không thay thế nhau:

| Khái niệm | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| High availability (HA) | Làm thế nào tiếp tục phục vụ khi một thành phần/miền lỗi nhỏ gặp sự cố? | Nhiều instance, multi-AZ database, load balancer health check |
| Backup/recovery | Làm thế nào khôi phục dữ liệu về trạng thái trước lỗi hoặc xóa nhầm? | Snapshot, point-in-time recovery, immutable backup |
| Disaster recovery | Làm thế nào khôi phục dịch vụ khi failure domain lớn bị mất? | Standby region, restore backup ở region khác, DR orchestration |
| Failover | Làm thế nào chuyển vai trò hoạt động sang môi trường thay thế? | Promote replica, mở writer endpoint mới, route traffic |
| Failback | Làm thế nào quay về mô hình vận hành đã chọn sau khi môi trường cũ phục hồi? | Đồng bộ lại dữ liệu, chuyển writer có kiểm soát |

Multi-AZ thường giảm thời gian phục hồi trước lỗi node hoặc AZ, nhưng không nhất thiết bảo vệ trước mất cả region, xóa dữ liệu logic hoặc compromise tài khoản quản trị. Replication cũng có thể sao chép thao tác xóa nhầm; vì vậy backup độc lập, retention và restore test vẫn cần thiết.

## 3. Xác định failure domain và blast radius

Trước khi chọn topology, hãy xác định sự cố nào kế hoạch DR phải xử lý. Một region có thể còn hoạt động nhưng một dịch vụ điều khiển, DNS, KMS hoặc network path đã lỗi. Ngược lại, một ứng dụng có thể lỗi do deployment sai trong khi hạ tầng vẫn khỏe.

### 3.1. Ma trận sự cố

| Failure domain | Biểu hiện | Phản ứng ban đầu |
| --- | --- | --- |
| Process/container/VM | Instance unhealthy, crash loop, mất node | Restart/reschedule hoặc thay instance |
| AZ | Network/storage/compute trong một AZ lỗi diện rộng | HA trong region, chuyển workload sang AZ khác |
| Region | Nhiều dịch vụ trong vùng không truy cập được hoặc suy giảm nghiêm trọng | Kích hoạt quy trình DR region |
| Provider/control plane | API quản trị, identity hoặc dịch vụ nền tảng bị ảnh hưởng | Kiểm tra khả năng điều khiển từ region/provider khác |
| Network/edge/DNS | Người dùng không tới được endpoint dù backend còn sống | Chẩn đoán đường routing, resolver và health probe |
| Data corruption/ransomware | Dữ liệu sai hoặc bị mã hóa lan rộng | Dừng ghi có nguy cơ, bảo toàn evidence và khôi phục từ nguồn sạch |
| Identity/KMS compromise | Credential/key bị lộ, bị vô hiệu hóa hoặc không thể truy cập | Thu hồi credential, khôi phục trust/key theo quy trình bảo mật |
| Human/configuration error | Route, policy, firewall hoặc database bị thay đổi sai | Rollback cấu hình, kiểm tra audit và đánh giá phạm vi tác động |

Không phải mọi lỗi ở region đều yêu cầu failover. Chuyển vùng khi chỉ một dependency cục bộ lỗi có thể mở rộng blast radius, gây mất dữ liệu hoặc làm môi trường dự phòng quá tải.

### 3.2. Phạm vi DR theo ứng dụng

Với mỗi ứng dụng, xác định các thành phần bắt buộc để hoàn thành hành trình nghiệp vụ:

- Entry point: DNS, CDN, WAF, global load balancer và API gateway.
- Compute: VM, Kubernetes, serverless, autoscaling group và image/artifact.
- Data: database, object/file storage, cache và search index.
- Messaging: queue, stream, scheduler và dead-letter queue.
- Identity/security: IAM, secret manager, KMS, certificate và federation.
- Network: VPC/VNet, subnet, route, firewall, NAT, private endpoint và DNS.
- Operations: monitoring, logging, tracing, deployment pipeline và automation.

DR của một dịch vụ chỉ hoàn thành khi các dependency cần thiết hoạt động và nghiệp vụ có thể đi hết luồng, không chỉ khi một health endpoint trả HTTP 200.

## 4. RTO, RPO và mục tiêu phục hồi

Hai chỉ số nền tảng:

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục một dịch vụ hoặc khả năng nghiệp vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường được diễn đạt bằng khoảng thời gian hoặc mốc giao dịch.

RTO/RPO phải được business owner phê duyệt theo mức độ quan trọng. Không nên đặt cùng một giá trị cho toàn bộ hệ thống.

### 4.1. Phân loại workload

| Cấp độ minh họa | Mục tiêu phục hồi | Ví dụ workload |
| --- | --- | --- |
| Tier 0 – Critical | RTO vài phút hoặc thấp hơn; RPO gần 0 theo khả năng nền tảng | Ledger, checkout lõi, identity cho hành trình mua hàng |
| Tier 1 – Essential | RTO trong khoảng một giờ; RPO ngắn đã phê duyệt | Order management, inventory projection |
| Tier 2 – Important | RTO vài giờ; có thể chấp nhận mất một cửa sổ dữ liệu giới hạn | Reporting, search index, dashboard |
| Tier 3 – Deferred | RTO dài hơn; dữ liệu có thể tạo lại hoặc khôi phục theo batch | Sandbox, cache, dữ liệu thử nghiệm |

Các mốc chỉ để minh họa cách phân tầng. RTO/RPO thực tế phụ thuộc hợp đồng, tác động kinh doanh, khả năng kỹ thuật và ngân sách.

### 4.2. RTO phải tính cả toàn bộ chuỗi

**RTO tổng = phát hiện + quyết định + fence + khôi phục/promote dữ liệu + khôi phục dependency + traffic cutover + kiểm chứng nghiệp vụ.**

Ví dụ database promote hoàn tất trong 3 phút nhưng DNS cache, secret, worker và queue cần thêm 25 phút thì RTO nghiệp vụ không phải 3 phút. Cần đo từng công đoạn và phần có thể chạy song song.

### 4.3. RPO phải gắn với semantics ghi

Với asynchronous replication, RPO phụ thuộc log chưa chuyển hoặc chưa được lưu bền vững ở region dự phòng khi lỗi xảy ra. Lag trung bình không đủ để cam kết RPO; cần theo dõi tail lag, replication backlog và thời gian link outage. Với synchronous/quorum replication, cần xác minh điều kiện ACK và failure domain của replica.

Ngoài replication, xác định RPO cho queue, object upload, file share, analytics và cấu hình. Database có RPO gần 0 nhưng queue chưa replicate có thể khiến công việc đã nhận không được xử lý sau DR.

## 5. Các chiến lược DR và chi phí

Không có một topology tối ưu cho mọi workload. Các chiến lược thường được mô tả từ mức ít chuẩn bị tới mức sẵn sàng cao:

| Chiến lược | Mô tả | RTO/RPO tương đối | Chi phí/độ phức tạp |
| --- | --- | --- | --- |
| Backup and restore | Backup được lưu ở failure domain khác; tạo hạ tầng và restore khi cần | RTO dài hơn; RPO theo lịch backup/log archive | Chi phí standby thấp hơn, restore và capacity cần chuẩn bị |
| Pilot light | Một số thành phần dữ liệu/security/core được duy trì; compute chính tạo khi DR | RTO trung bình; RPO tùy replication/backup | Chi phí trung bình; phụ thuộc automation và provisioning |
| Warm standby | Môi trường DR chạy ở capacity nhỏ hơn, dữ liệu được replicate | RTO ngắn hơn; RPO phụ thuộc replication | Tốn standby compute và vận hành song song |
| Hot standby / active-passive | Region dự phòng gần sẵn sàng đầy đủ, chỉ một bên phục vụ ghi chính | RTO thấp hơn; RPO có thể rất thấp nếu thiết kế phù hợp | Chi phí cao và cần điều phối failover/failback |
| Active-active | Nhiều region cùng phục vụ traffic; dữ liệu được phân phối/đồng bộ theo semantics | Có thể giảm chuyển traffic, nhưng conflict và recovery phức tạp | Chi phí và độ phức tạp cao nhất trong nhiều trường hợp |

Tên gọi giữa các nhà cung cấp có thể khác. Hãy đánh giá thành phần nào thực sự chạy, dữ liệu đồng bộ ra sao, capacity dự phòng bao nhiêu và thao tác nào vẫn phải làm thủ công.

### 5.1. Chọn chiến lược theo RTO/RPO

~~~mermaid
flowchart TB
    Start["Yêu cầu nghiệp vụ và RTO/RPO"] --> RTO{"RTO có thể tính bằng nhiều giờ?"}
    RTO -->|Có| Backup["Backup and restore"]
    RTO -->|Không| Warm{"Có thể chờ provision compute?"}
    Warm -->|Có| Pilot["Pilot light"]
    Warm -->|Không| Standby{"Cần capacity sẵn sàng ngay?"}
    Standby -->|Một writer| Hot["Warm / hot standby"]
    Standby -->|Phục vụ nhiều vùng| Active["Active-active"]
    Backup --> Validate["Kiểm thử restore và dependency"]
    Pilot --> Validate
    Hot --> Validate
    Active --> Validate
~~~

Sơ đồ là điểm bắt đầu thảo luận, không phải quy tắc máy móc. Active-active không tự động có RTO/RPO tốt hơn nếu conflict resolution, identity, queue hay routing chưa được thiết kế.

## 6. Phát hiện sự cố và quyết định kích hoạt DR

Phát hiện lỗi và quyết định failover là hai bước khác nhau. Health check thất bại có thể do một node hoặc một route lỗi; chưa đủ kết luận toàn region mất khả năng phục vụ. Tự động failover quá nhạy có thể tạo chuyển vùng không cần thiết hoặc split-brain.

### 6.1. Kết hợp nhiều tín hiệu

| Tín hiệu | Điều cần xác nhận |
| --- | --- |
| Synthetic transaction | Hành trình nghiệp vụ từ nhiều vantage point có thất bại không? |
| Service health | API, database, queue, identity và storage có thực sự không sẵn sàng? |
| Network reachability | Mất một route, một ISP hay toàn bộ đường tới region? |
| Provider status | Có thông báo sự cố dịch vụ/region và phạm vi ảnh hưởng không? |
| SLO/error budget | Lỗi có vượt ngưỡng kích hoạt incident/DR đã thống nhất không? |
| Data replication | Replica có theo kịp, có lỗi apply hoặc backlog bất thường không? |
| Dependency health | Dịch vụ phụ trợ còn hoạt động từ region khác không? |

Nên có probe từ nhiều region hoặc network độc lập để tránh nhầm một tuyến kết nối lỗi với sự cố backend. Tín hiệu phải có timestamp, source và correlation để người điều phối hiểu độ tin cậy.

### 6.2. Điều kiện kích hoạt

Runbook cần định nghĩa:

- Điều kiện incident được nâng lên mức disaster.
- Ai có quyền tuyên bố disaster và kích hoạt failover.
- Khi nào tự động failover được phép, khi nào cần người phê duyệt.
- Cách xác định primary đang hỏng, bị cô lập hay chỉ bị chậm.
- Ngưỡng chấp nhận mất dữ liệu và ai phê duyệt RPO vượt mục tiêu.
- Cơ chế ngăn hai nhóm vận hành đồng thời thực hiện hai lần chuyển vùng.

Với hệ thống critical, có thể tự động hóa detection và chuẩn bị môi trường nhưng yêu cầu người có trách nhiệm xác nhận destructive/irreversible data promotion. Mức tự động hóa phải dựa trên độ tin cậy của detector và tính an toàn của fencing.

### 6.3. Incident commander và vai trò

Trong disaster, phân vai rõ ràng giúp tránh nhiều người cùng thay đổi hệ thống:

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander | Điều phối quyết định, ưu tiên, timeline và cập nhật stakeholder |
| Technical lead | Đánh giá failure domain, topology và thứ tự khôi phục |
| Data lead | Kiểm tra replication, chọn recovery point, promote và xác minh dữ liệu |
| Network/edge lead | DNS, global routing, firewall, connectivity và endpoint |
| Application lead | Deploy/config, secret, readiness, queue consumer và smoke test |
| Security lead | Identity, KMS, credential, evidence và kiểm soát truy cập |
| Business owner | Chấp nhận RPO exception, xác nhận luồng nghiệp vụ và mức degraded mode |

Một người có thể kiêm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm và quyền quyết định phải được ghi rõ.

## 7. Quy trình failover theo thứ tự phụ thuộc

Failover an toàn cần một state machine hoặc runbook có các bước, điều kiện đầu vào, hành động, kiểm chứng và tiêu chí dừng. Trình tự có thể khác nhau theo kiến trúc, nhưng quyền ghi và trạng thái dữ liệu phải được giải quyết trước khi mở traffic ghi mới.

### 7.1. Chuỗi điều phối tham khảo

~~~mermaid
flowchart TD
    A["Declare disaster / incident"] --> B["Assess blast radius and current primary"]
    B --> C["Freeze risky changes and writes if needed"]
    C --> D["Fence old writer / confirm ownership"]
    D --> E["Select recovery point and promote data"]
    E --> F["Restore identity, keys, network and secrets"]
    F --> G["Start compute and dependent services"]
    G --> H["Validate health and business invariants"]
    H --> I["Shift traffic gradually"]
    I --> J["Monitor SLO, errors, data and queue"]
    J --> K["Operate in DR mode / plan failback"]
~~~

Một số bước như khôi phục network, identity và key cần được chuẩn bị hoặc chạy song song với đánh giá dữ liệu. Tuy nhiên, không cho write traffic vào database mới khi chưa xác minh quyền writer và recovery point.

### 7.2. Giai đoạn 1: Declare và freeze

1. Ghi nhận incident ID, người chỉ huy, timestamp và nguồn bằng chứng.
2. Xác định phạm vi dịch vụ, region, tenant và dữ liệu bị ảnh hưởng.
3. Dừng deployment/config changes không liên quan để giảm biến số.
4. Nếu có nguy cơ corruption/ransomware, hạn chế ghi hoặc cô lập credential/endpoint bị xâm phạm.
5. Ghi nhận các thao tác đang chạy, queue backlog và transaction chưa rõ kết quả.

### 7.3. Giai đoạn 2: Fence primary cũ

Fencing đảm bảo primary cũ không thể tiếp tục nhận ghi khi region DR trở thành writer. Cách thực hiện tùy nền tảng:

- Provider-managed promotion với leader epoch/lease.
- Thu hồi write route hoặc credential của writer cũ.
- Network isolation hoặc disable endpoint trong phạm vi có thể kiểm soát.
- Fencing token ở application/storage layer để request từ generation cũ bị từ chối.
- Quorum/witness xác nhận quyền leader mới và ngăn hai phía cùng có majority.

Chỉ cập nhật DNS không phải fencing. Client có thể cache endpoint cũ; connection pool có thể còn session đang mở; worker có thể tiếp tục retry tới primary cũ. Phải có cơ chế ở data plane hoặc quyền database ngăn writer cũ.

### 7.4. Giai đoạn 3: Chọn recovery point và promote

Data lead cần xác định:

- Replica/backup nào là nguồn có thể khôi phục tốt nhất.
- Commit/log position cuối cùng được xác nhận bền vững ở region dự phòng.
- Khoảng dữ liệu có thể thiếu hoặc có trạng thái không rõ.
- Có cần replay log/event hay đối soát transaction sau promotion không.
- Có dấu hiệu dữ liệu bị corruption hoặc bị compromise đã replicate hay không.

Không promote replica đang stale nếu đã có backup sạch/đúng hơn mà quy trình bảo mật yêu cầu. Với asynchronous replication, ghi lại RPO thực tế và xin quyết định business owner khi vượt giới hạn.

### 7.5. Giai đoạn 4: Khôi phục dependency

Khôi phục theo dependency graph, ví dụ:

1. Network routing, private endpoints, firewall, DNS nội bộ và connectivity.
2. IAM/workload identity, secret, certificate và quyền KMS.
3. Database, object/file storage, queue/stream và cache.
4. Compute, service discovery, configuration và autoscaling.
5. Background worker, scheduler, integration và observability.

Không phải mọi hệ thống cần đúng thứ tự này. Hãy lập dependency graph cụ thể và nhận diện vòng phụ thuộc, như service cần database để khởi động nhưng database restore cần credential từ secret service.

### 7.6. Giai đoạn 5: Validate trước cutover

Chạy kiểm tra theo lớp:

- **Infrastructure:** resource healthy, route/volume/endpoint/replica đúng.
- **Security:** identity, role, KMS, TLS, secret và audit hoạt động.
- **Data:** schema version, transaction invariants, row counts/checksum hoặc reconciliation phù hợp.
- **Application:** readiness, connection pool, dependency health và config.
- **Business:** tạo/đọc đơn, xác nhận payment giả lập, reservation, event publish/consume hoặc luồng đại diện.

Chỉ health check xanh không chứng minh dữ liệu đúng. Cần smoke test có dữ liệu thử an toàn, không gây side effect thật trong hệ thống thanh toán hoặc gửi thông báo tới khách hàng.

## 8. Thiết kế traffic routing khi chuyển vùng

Traffic routing quyết định client tới ứng dụng/region nào. Có thể dùng DNS failover, global load balancer, anycast, CDN origin failover, application-level routing hoặc service mesh. Mỗi phương thức có thời gian hội tụ, cache, health semantics và failure mode khác nhau.

### 8.1. DNS-based failover

DNS có thể trả địa chỉ của region dự phòng khi health check của primary thất bại. Cần xem:

- TTL và resolver/client cache thực tế; TTL thấp không đảm bảo mọi client chuyển ngay.
- Negative caching và DNS propagation behavior.
- Health check có đủ synthetic transaction hay chỉ kiểm tra TCP/HTTP endpoint?
- Có split view giữa resolver/private DNS và public DNS không?
- Client có hard-code IP hoặc giữ kết nối lâu không?
- Khi failback, cách tránh resolver chuyển về primary quá sớm là gì?

DNS phù hợp nhiều kiến trúc nhưng không phải cơ chế instant cutover. Client có thể giữ connection pool hoặc cache địa chỉ cũ lâu hơn TTL.

### 8.2. Global load balancer / traffic manager

Global routing layer có thể chọn region theo health, latency, weight, geography hoặc priority. Nó thường cho phép chuyển traffic theo tỷ lệ và health state rõ hơn DNS thuần, nhưng vẫn phụ thuộc health probe, control plane, cache và cơ chế client kết nối.

Các mode phổ biến:

| Mode | Hành vi | Dùng khi |
| --- | --- | --- |
| Priority/failover | Ưu tiên region chính, chuyển sang region phụ khi lỗi | Active-passive |
| Weighted | Chia traffic theo tỷ lệ | Canary cutover hoặc active-active |
| Latency-based | Chọn endpoint có latency quan sát thấp hơn | Ứng dụng multi-region có data routing phù hợp |
| Geo-based | Route theo vị trí hoặc policy địa lý | Data residency hoặc locality |
| Anycast/edge | Đưa client tới điểm biên gần, sau đó route vào backend | Dịch vụ edge/global |

Latency-based routing không biết dữ liệu nào mới nhất. Một region gần hơn nhưng chỉ có stale replica không nên nhận request cần read-after-write.

### 8.3. Chuyển traffic theo giai đoạn

Thay vì chuyển toàn bộ người dùng cùng lúc, có thể:

1. Chạy synthetic/internal traffic ở DR region.
2. Chuyển một tỷ lệ nhỏ traffic không gây side effect hoặc nhóm người dùng được chọn.
3. Kiểm tra latency, error, data correctness, queue và capacity.
4. Tăng tỷ lệ theo các bước đã định trước.
5. Giữ khả năng pause/rollback nếu metric vượt ngưỡng.
6. Chuyển phần còn lại khi business và technical criteria đạt.

Canary cutover giảm blast radius nhưng chỉ an toàn nếu routing và data ownership rõ. Không chia traffic ghi cho hai region chỉ để thử health nếu chỉ một region được quyền writer.

### 8.4. Session affinity và client state

Nếu session được lưu trong memory ở region A, chuyển request tiếp theo sang B có thể làm mất session. Nên dùng external session store/replication, stateless token có bảo vệ hoặc session affinity có kế hoạch DR. Cần đánh giá refresh token, CSRF state, WebSocket và long-lived connection.

## 9. Data plane: database, queue, object và file

Khôi phục compute mà không khôi phục dữ liệu và messaging tương ứng sẽ tạo một hệ thống không nhất quán.

### 9.1. Database

- Xác định writer duy nhất hoặc cơ chế multi-writer được database hỗ trợ.
- Kiểm tra replication lag, log position, promotion và endpoint.
- Xử lý transaction có kết quả không xác định từ lúc client mất kết nối.
- Dùng idempotency key, operation ID hoặc reconciliation để xử lý retry.
- Kiểm tra sequence/identity, extension, schema migration và version compatibility.
- Ngăn application pool và worker dùng endpoint cũ sau cutover.

### 9.2. Queue và event stream

Queue có thể không được replicate đồng bộ với database. Cần xác định message nào đã nhận, đã xử lý, đang in-flight và chưa chuyển vùng. Với event stream partitioned, consumer offset và retention phải được kiểm tra.

Các câu hỏi:

- Producer ở region cũ còn ghi được không?
- Queue DR có chứa đủ message và thứ tự cần thiết không?
- Có thể nhận duplicate khi replay không?
- Consumer có idempotent không?
- Visibility timeout, retry và DLQ có được khôi phục?
- Có cần pause producer/consumer trong khi chọn recovery point?

### 9.3. Object và file storage

Object replication có thể bất đồng bộ; version, delete marker, lifecycle và metadata phải được kiểm tra. Signed URL tạo ở region cũ có thể trỏ endpoint cũ hoặc hết hiệu lực. File storage cần xác minh mount, identity mapping, file lock, snapshot consistency và dữ liệu đang mở. Không giả định byte đã replicate đồng nghĩa filesystem state/ACL đã sẵn sàng.

### 9.4. Cache và search index

Cache thường có thể tái tạo từ source of truth; không nhất thiết phải replicate mọi entry. Tuy vậy cold cache sau failover có thể tạo thundering herd vào database. Cần warm-up có giới hạn, cache stampede protection và giới hạn concurrency.

Search index/materialized view thường có thể rebuild hoặc replay từ nguồn dữ liệu. Xác định freshness, checkpoint và khả năng rebuild trước khi đặt nó vào critical path của DR.

## 10. Failback: quay lại trạng thái vận hành bình thường

Failback là một thay đổi topology khác, không phải thao tác đảo ngược failover một cách máy móc. Region cũ có thể chứa dữ liệu chưa đồng bộ, config lỗi, credential cũ hoặc hạ tầng đã bị thay đổi. Trong thời gian DR, region dự phòng có thể đã trở thành nguồn dữ liệu chính.

### 10.1. Điều kiện trước failback

- Root cause của incident đã được hiểu và xử lý hoặc có biện pháp giảm thiểu.
- Region cũ đã được kiểm tra network, compute, storage, identity và security.
- Dữ liệu từ current writer đã replicate/catch-up đầy đủ tới region dự kiến trở lại.
- Không còn writer/consumer cũ có thể ghi bằng credential hoặc endpoint đã lỗi thời.
- Schema, migration, extension, encryption key và config tương thích.
- Capacity đủ để nhận traffic và có kế hoạch rollback nếu failback thất bại.
- Business owner/incident commander chấp thuận cửa sổ và rủi ro chuyển đổi.

### 10.2. Quy trình failback

1. Giữ region DR là writer trong khi kiểm tra và tái tạo region cũ.
2. Thiết lập replication theo hướng từ current writer tới region đang phục hồi.
3. Chờ replication bắt kịp; so sánh log position/lag, checksum hoặc invariant phù hợp.
4. Chọn maintenance/cutover window; thông báo và giảm thay đổi không cần thiết.
5. Fence hoặc tạm dừng ghi ở current writer theo quy trình database.
6. Xác nhận final sync và promote/đổi vai trò writer có kiểm soát.
7. Cập nhật endpoint, service discovery, routing và connection pool.
8. Chuyển traffic theo tỷ lệ; kiểm tra latency, error, dữ liệu và nghiệp vụ.
9. Giữ region DR ở chế độ replica/standby mới và xác nhận replication ngược chiều phù hợp.
10. Kết thúc incident sau khi ổn định, lưu timeline và action items.

### 10.3. Tránh failback sớm

Áp lực giảm chi phí standby có thể khiến nhóm chuyển về region cũ quá sớm. Nếu region chưa ổn định hoặc dữ liệu chưa đồng bộ, sự cố thứ hai có thể làm mất thêm dữ liệu. Failback nên dựa trên tiêu chí kiểm chứng và cửa sổ ổn định, không chỉ dựa vào việc provider thông báo dịch vụ đã phục hồi.

## 11. Điều phối giao dịch, backlog và retry trong thời gian DR

Trong failover, một số request có thể đã commit nhưng response không tới client; một số request chưa commit; message có thể đã được giao nhưng chưa ack. DR phải xử lý trạng thái không xác định này.

### 11.1. Idempotency và reconciliation

Với lệnh ghi quan trọng, lưu operation ID/idempotency key cùng trạng thái và kết quả. Khi client retry sau timeout, region mới tra cứu operation trước khi tạo side effect khác.

Đối với payment, cần đối soát với payment provider bằng transaction reference trước khi charge lại. Đối với order, cần xác định order đã tồn tại/được xác nhận hay chưa. Đối với inventory, reservation phải có unique operation key hoặc version để tránh trừ hai lần.

### 11.2. Queue backlog sau chuyển vùng

Trước khi mở consumer full scale:

- Xác định số message cũ, tuổi oldest message và loại priority.
- Kiểm tra poison message, DLQ, visibility timeout và retry attempt.
- Kiểm soát consumer concurrency theo database/API quota ở DR region.
- Ưu tiên công việc theo deadline và criticality.
- Theo dõi tốc độ backlog giảm, không chỉ desired worker count.

Scale consumer quá mạnh có thể tạo connection storm và khiến database DR chưa ổn định bị quá tải. Có thể replay theo batch nhỏ, bắt đầu với concurrency thấp rồi tăng dựa trên metric.

### 11.3. Rebuild dữ liệu dẫn xuất

Search index, cache, reporting projection hoặc feature store có thể cần rebuild. Phải xác định source of truth, watermark, event retention và quy trình replay. Không rebuild đồng thời mọi dataset nếu nó tranh capacity với giao dịch khách hàng đang phục hồi.

## 12. Network, identity và secret trong DR

Một region DR cần nhiều hơn một database endpoint.

### 12.1. Network readiness

- VPC/VNet, subnet, route table, firewall/security group và private endpoint đã được tạo hoặc có thể provision.
- CIDR không overlap với on-premises, partner network hoặc region khác.
- VPN/Direct Connect/ExpressRoute hoặc private backbone có đường dự phòng phù hợp.
- NAT, egress IP, DNS resolver và allowlist bên thứ ba được cập nhật.
- Certificate, TLS policy, service mesh và mutual TLS có thể sử dụng tại region DR.
- Capacity IP/subnet đủ cho autoscaling và node pool dự phòng.

Nếu DR region được tạo từ infrastructure-as-code lúc incident, quota và thời gian provisioning phải được thử trước. Một VPC template chưa chứng minh mọi route, firewall và private DNS đều hoạt động.

### 12.2. Identity và KMS

Ứng dụng ở DR cần xác thực được với identity provider, workload identity, secret manager và KMS. Nếu các hệ thống đó chỉ hoạt động ở region primary, DR có thể không giải mã dữ liệu hoặc lấy secret.

Chuẩn bị:

- Role/service account với trust policy phù hợp region DR.
- Secret replication/rotation và quy trình revoke credential cũ.
- Encryption key policy cho backup, replica và storage.
- Certificate lifecycle và CA trust.
- Break-glass access theo nguyên tắc least privilege, MFA và audit.

Không sao chép mọi secret sang DR một cách vô điều kiện. Chỉ replicate secret cần thiết, giới hạn quyền và giữ separation of duties.

### 12.3. Security trong disaster mode

Áp lực phục hồi không phải lý do tắt MFA, mở database public hoặc cấp admin rộng. DR cần break-glass controls có phê duyệt, thời hạn, audit và quy trình thu hồi. Nếu incident có khả năng là credential compromise hoặc ransomware, phải ưu tiên clean recovery environment, rotate key/token và bảo toàn forensic evidence trước khi mở traffic.

## 13. Runbook và tự động hóa orchestration

Một runbook tốt mô tả ai làm gì, ở đâu, điều kiện nào cho phép đi tiếp và cách quay lại khi một bước lỗi. Những thao tác có thể lặp lại, xác định rõ và idempotent nên được tự động hóa; quyết định có rủi ro mất dữ liệu hoặc thay đổi quyền writer cần guardrail rõ.

### 13.1. Cấu trúc runbook

| Thành phần | Nội dung cần có |
| --- | --- |
| Trigger | Metric, alert, provider incident và điều kiện declare |
| Owner/approver | Incident commander, data lead, security và business approver |
| Preconditions | Replica health, backup, credentials, capacity và maintenance state |
| Action | Lệnh/API/workflow có version và tham số rõ |
| Verification | Điều kiện xác nhận bước thành công |
| Timeout/retry | Thời gian chờ, số lần retry và cách xử lý trạng thái không rõ |
| Stop condition | Khi nào dừng vì nguy cơ split-brain, data loss hoặc security |
| Rollback/compensation | Cách quay về trạng thái an toàn nếu bước thất bại |
| Evidence | Timestamp, actor, request ID, output và quyết định |
| Communication | Ai cập nhật status page, customer support và stakeholder |

### 13.2. Orchestration state machine

Không nên xây một script dài chỉ chạy lần lượt nhiều lệnh mà không lưu trạng thái. Workflow orchestration nên có state bền vững:

~~~mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Assessing: Disaster signal
    Assessing --> Aborted: Region recovered / false alarm
    Assessing --> Fencing: Approved DR
    Fencing --> DataRecovery
    DataRecovery --> DependencyRecovery
    DependencyRecovery --> Validation
    Validation --> TrafficShift: Checks passed
    Validation --> RecoveryBlocked: Checks failed
    TrafficShift --> DRActive: SLO and business checks pass
    TrafficShift --> RecoveryBlocked: Error threshold exceeded
    DRActive --> FailbackPlanning: Primary region stable
    FailbackPlanning --> Failback
    Failback --> Normal: Reconciled and verified
    RecoveryBlocked --> Assessing: New plan approved
~~~

Mỗi transition cần idempotency, timeout, actor/approval và evidence. Nếu workflow bị restart, nó phải biết bước cuối đã hoàn tất hay chưa để không promote hai lần hoặc mở traffic lặp.

### 13.3. Tự động hóa theo mức rủi ro

- Tự động: thu thập trạng thái, health probe, kiểm tra lag, tạo incident context, chuẩn bị compute/network và gửi cảnh báo.
- Tự động có guardrail: shift traffic theo tỷ lệ, scale worker, warm cache và chạy smoke test không gây side effect.
- Cần phê duyệt/kiểm soát chặt: promote database, chọn recovery point có mất dữ liệu, fence writer, thay đổi identity/key hoặc xóa nguồn lỗi.

Mức phân loại cần phù hợp sản phẩm và runbook; không mặc định mọi promotion đều cần phê duyệt thủ công nếu database có failover an toàn đã kiểm chứng.

## 14. Observability và truyền thông trong DR

Khi DR đang diễn ra, nhóm cần một bức tranh duy nhất về trạng thái dịch vụ và quyết định.

### 14.1. Dashboard DR

| Nhóm | Chỉ số |
| --- | --- |
| Incident | Detection time, declare time, current phase, owner và action pending |
| Data | Replication lag, log position, last backup, restore status, data validation |
| Routing | Traffic weight, DNS/edge health, connection tới endpoint cũ/mới |
| Application | Request rate, p95/p99, error/timeout, synthetic journey |
| Dependency | Queue depth/age, DB connections, cache, third-party API và identity |
| Capacity | Ready instances/Pods, pending nodes, quota/IP, autoscaling state |
| Security | KMS/key status, secret access, IAM changes, audit gap |
| Recovery objectives | RTO elapsed/remaining, RPO measured/exception |

### 14.2. Timeline và evidence

Ghi lại timestamp thống nhất cho:

- Phát hiện đầu tiên và xác nhận incident.
- Declare disaster và người phê duyệt.
- Fence old writer và xác nhận quyền leader mới.
- Recovery point được chọn và RPO thực tế.
- Database promotion và dependency recovery.
- Traffic shift theo tỷ lệ.
- Business validation và thời điểm đạt service restoration.
- Failback, nếu có.

Timeline dùng để tính RTO thực tế, điều tra nguyên nhân và cải thiện runbook. Lưu evidence ở nơi có quyền truy cập hạn chế và retention phù hợp.

### 14.3. Stakeholder communication

Thông báo cần phân biệt:

- Đang điều tra hay đã tuyên bố disaster.
- Dịch vụ nào bị ảnh hưởng và người dùng có thể làm gì.
- Read-only/degraded mode hay giao dịch bị tạm dừng.
- Dữ liệu có thể trễ/mất trong phạm vi nào nếu đã xác nhận.
- Khi nào có bản cập nhật tiếp theo.
- Khi nào dịch vụ được xác nhận phục hồi hoàn toàn.

Không hứa thời gian khôi phục chưa được xác minh. Một endpoint trả lời được không có nghĩa toàn bộ giao dịch và dữ liệu đã ổn định.

## 15. Kiểm thử DR: prove the plan, not the document

Một DR plan chưa từng thực hiện chỉ là giả thuyết. Cần kiểm thử định kỳ để tìm sai lệch giữa kiến trúc thiết kế và cấu hình đang chạy.

### 15.1. Các cấp độ diễn tập

| Loại test | Cách thực hiện | Điều chứng minh |
| --- | --- | --- |
| Tabletop exercise | Nhóm đi qua kịch bản và quyết định trên giấy | Vai trò, quyền, communication và logic quyết định |
| Component restore | Khôi phục database/object/volume riêng trong sandbox | Backup, key, data consistency và thời gian restore |
| Partial failover | Chuyển một service hoặc nhóm traffic thử nghiệm | Routing, endpoint, application config và dependency |
| Full regional failover | Chuyển toàn bộ workload trong phạm vi DR đã chọn | RTO/RPO end-to-end, capacity và thứ tự orchestration |
| Failback exercise | Đồng bộ và chuyển lại region ban đầu | Quy trình quay lại, fencing, routing và replica topology |
| Chaos/fault injection | Mô phỏng latency, packet loss, dependency failure hoặc node loss | Hành vi khi lỗi bất ngờ và guardrail |

Không phải lần nào cũng cần full failover production. Bắt đầu từ sandbox/môi trường tương đương, sau đó tăng phạm vi theo kế hoạch, owner, blast radius và tiêu chí dừng.

### 15.2. Kịch bản kiểm thử cần có

1. Primary database mất kết nối đột ngột trong lúc có giao dịch ghi.
2. Region chính còn compute nhưng identity/KMS hoặc private network không truy cập được.
3. Replication lag lớn hơn RPO do traffic burst hoặc link chậm.
4. DNS/global routing health probe báo lỗi giả hoặc không phát hiện lỗi thật.
5. Region DR bị thiếu quota, IP hoặc capacity để nhận toàn bộ traffic.
6. Queue/stream chưa replicate đầy đủ; worker retry sau cutover.
7. Client giữ connection tới endpoint cũ sau khi DNS đổi.
8. Backup có thể truy cập nhưng key bị disable hoặc role thiếu quyền restore.
9. Dữ liệu bị xóa nhầm/đổi sai và thao tác đó đã replicate sang standby.
10. Failback bắt đầu khi primary cũ mới phục hồi một phần.

### 15.3. Đo RTO/RPO thực tế

Ghi timestamp các mốc declare, fence, data promotion, dependency ready, routing cutover và business validation. RTO nghiệp vụ kết thúc khi hành trình quan trọng hoàn tất thành công và đạt tiêu chí SLO, không phải khi API health check xanh.

RPO thực tế cần so sánh giao dịch cuối cùng đã được xác nhận với dữ liệu đã khôi phục. Có thể dùng transaction ID, commit LSN/log position, event sequence hoặc reconciliation với hệ thống upstream. Không chỉ lấy metric replication lag sau sự cố.

### 15.4. Exit criteria và action items

Một cuộc diễn tập đạt khi:

- Chuyển vùng hoàn tất trong RTO đã duyệt.
- Dữ liệu không mất vượt RPO; mọi ngoại lệ được ghi nhận.
- Chỉ có writer hợp lệ; không có split-brain.
- Identity, key, network, secrets và dependency hoạt động.
- Synthetic transaction và business journey pass.
- Queue backlog được xử lý trong SLA và không tạo duplicate side effect ngoài kiểm soát.
- Người vận hành hiểu trạng thái và có evidence đầy đủ.
- Failback hoặc duy trì DR mode có quyết định và owner rõ ràng.

Mỗi lỗi hoặc chậm trễ tạo action item có người phụ trách, deadline và kiểm tra lại trong lần diễn tập tiếp theo.

## 16. Chi phí và capacity trong DR region

DR region phải có đủ capacity vào lúc incident. Nếu chỉ chạy một phần workload, cần biết khả năng scale-up và quota thực tế. Nếu hai region cùng active bình thường, cần xác định khi một region mất thì region còn lại có chịu được toàn bộ peak không.

### 16.1. Capacity planning

- Tính peak traffic và concurrency cần phục vụ trong DR mode.
- Kiểm tra VM/instance quota, GPU quota, serverless concurrency, Kubernetes node pool và subnet IP.
- Tính database compute, connection, IOPS, storage và read/write capacity sau promotion.
- Kiểm tra queue/broker partition, consumer parallelism và rate limit.
- Kiểm tra third-party provider có cho phép egress IP/region mới không.
- Xác định workload có thể tắt hoặc degrade để ưu tiên giao dịch quan trọng.

### 16.2. Degraded mode có chủ đích

Không phải mọi tính năng đều phải hoạt động đầy đủ trong DR. Có thể:

- Tạm dừng báo cáo nặng, export và batch không khẩn cấp.
- Chuyển catalog/search sang read-only hoặc cache.
- Giới hạn upload video hoặc tác vụ có chi phí compute cao.
- Ưu tiên checkout, payment status và order lookup.
- Giảm tần suất analytics và background enrichment.

Degraded mode phải được định nghĩa từ trước, có owner và thông báo rõ cho user. Không tắt tùy tiện một dependency nếu nó ảnh hưởng invariant giao dịch.

### 16.3. TCO

Chi phí DR gồm standby compute, replica/database, backup storage, cross-region data transfer, DNS/global routing, observability, security/key management, test environment, license và nhân lực vận hành. Backup and restore rẻ hơn về standby nhưng có thể cần nhiều capacity trong thời gian khôi phục. Hot standby đắt hơn nhưng giảm provisioning delay.

So sánh chi phí theo RTO/RPO thực tế và business impact, không chỉ theo chi phí hạ tầng trung bình mỗi tháng.

## 17. Well-Architected: đánh đổi trong điều phối khôi phục

| Góc nhìn | Quyết định DR | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Runbook, orchestration state machine, role, timeline và game day | Tự động hóa giảm lỗi thao tác nhưng cần versioning, guardrail và kiểm thử |
| **Security / Bảo mật** | Fencing, break-glass, key/secret recovery, immutable backup và audit | Kiểm soát chặt có thể thêm bước; bỏ qua kiểm soát gây compromise hoặc split-brain |
| **Reliability / Độ tin cậy** | Multi-region, replication, backup, failover/failback và business validation | RTO/RPO tốt hơn thường tốn chi phí và tăng độ phức tạp |
| **Performance Efficiency / Hiệu quả hiệu năng** | Capacity dự phòng, warm cache và traffic distribution | Capacity idle và replication traffic làm tăng chi phí |
| **Cost Optimization / Tối ưu chi phí** | Chọn backup/restore, pilot light, warm/hot standby theo criticality | Tiết kiệm standby có thể làm RTO dài hơn |
| **Sustainability / Bền vững** | Right-size DR capacity, tắt workload không cần và lifecycle backup | Giảm tài nguyên nhưng phải giữ đủ headroom trong disaster |

Mọi quyết định cần gắn với yêu cầu nghiệp vụ và bằng chứng kiểm thử. Không tối ưu cost bằng cách bỏ backup cho dữ liệu quan trọng; không tối ưu availability bằng cách mở multi-writer nếu dữ liệu không có conflict semantics an toàn.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi DNS failover là toàn bộ DR | Traffic đổi nhưng data, identity và dependency chưa sẵn sàng | Orchestrate toàn bộ dependency và business validation |
| Chuyển traffic trước khi fence writer cũ | Split-brain và divergence | Fence/leader ownership trước khi mở write mới |
| Chỉ đo thời gian database promote | Báo RTO thấp hơn thực tế | Đo từ declare đến business journey pass |
| Cho rằng replica luôn đủ mới | Mất transaction đã ACK ở primary | Theo dõi log position/lag và ghi RPO thực tế |
| Không diễn tập failback | Topology lệch và hai writer khi quay lại | Kiểm thử failback như một quy trình riêng |
| DR region thiếu quota/capacity | Không chịu được tải sau chuyển vùng | Capacity reservation, quota review và full-scale test |
| Không chuẩn bị KMS/secret/identity | Dữ liệu có nhưng không giải mã hoặc ứng dụng không khởi động | DR-ready key, secret và identity path |
| Replay queue không idempotent | Charge/email/order bị trùng | Operation ID, deduplication và reconciliation |
| Dùng health check quá đơn giản | False failover hoặc không nhận ra lỗi nghiệp vụ | Synthetic transaction và multi-signal detection |
| Không có degraded mode | Tính năng phụ tranh tài nguyên với giao dịch lõi | Ưu tiên dịch vụ theo criticality |
| Backup và replica cùng quyền xóa | Ransomware/xóa nhầm phá cả hai | Immutable/offline copy và separation of duties |
| Runbook chỉ là tài liệu tĩnh | Lệnh/config lỗi thời trong incident | Version hóa, tự động hóa và game day định kỳ |

## 19. Bài thực hành: DR cho nền tảng đặt hàng đa vùng

Một nền tảng thương mại điện tử vận hành ở region A và có DR region B. Region A chứa API, PostgreSQL primary, queue, object storage, cache và workers. Region B có database replica bất đồng bộ, object replication, hạ tầng compute nhỏ hơn và global traffic manager. Checkout có yêu cầu RTO 20 phút, RPO 1 phút; dashboard analytics có thể phục hồi trong 6 giờ và RPO 1 giờ.

Một sự cố diện rộng làm API ở A timeout, replication lag dao động 40–90 giây, một phần queue không có bản sao ở B và KMS key được quản lý qua policy riêng của region A. Người dùng vẫn có thể truy cập static site qua CDN nhưng không tạo đơn mới.

**Yêu cầu bài làm:**

1. Xác định có đủ điều kiện declare disaster hay cần tiếp tục chẩn đoán; liệt kê tín hiệu cần xác minh.
2. Vẽ dependency graph và thứ tự khôi phục network, identity/KMS, database, queue, object, compute và routing.
3. Xác định cách fence primary A và chứng minh B là writer duy nhất.
4. Tính/ghi nhận RPO thực tế từ replication lag và đề xuất cách xử lý transaction có kết quả không xác định.
5. Thiết kế routing cho static content, catalog read và checkout write; giải thích DNS/global load balancer và client connection behavior.
6. Đề xuất cách xử lý queue không replicate, message in-flight, retry, DLQ và idempotency.
7. Tính capacity DR region và đề xuất degraded mode để bảo vệ checkout trong khi analytics/worker chưa phục hồi.
8. Thiết kế KMS/secret recovery và điều kiện bảo mật trước khi mở traffic.
9. Viết runbook state machine với approval, verification, stop condition và evidence cho từng bước.
10. Mô tả failback khi A phục hồi, gồm reverse replication, final sync, writer switch và traffic cutback.
11. Đề xuất kịch bản game day và dashboard đo RTO/RPO end-to-end.
12. Viết ADR so sánh pilot light, warm standby và hot standby theo chi phí, RTO/RPO và rủi ro vận hành.

### Gợi ý đánh giá

Một thiết kế tốt không chuyển checkout write sang B chỉ vì global health check báo A lỗi. Nhóm cần xác minh blast radius, fence A, chọn recovery point và ghi rõ dữ liệu có thể thiếu. KMS/identity phải sẵn sàng ở B trước khi ứng dụng đọc dữ liệu mã hóa. Queue thiếu bản sao phải có phương án replay/reconcile từ nguồn hoặc chấp nhận công việc được tạo lại theo nghiệp vụ.

RTO 20 phút phải bao gồm decision, fencing, promotion, dependencies, routing và business validation. Nếu B chỉ có compute nhỏ hơn, cần chứng minh nó phục vụ peak checkout hoặc định nghĩa degraded mode đã được business owner chấp thuận. Failback là một đợt chuyển đổi riêng với reverse replication và final sync.

## 20. Checklist trước khi đưa DR vào production

- [ ] Workload có owner, criticality tier, dependency graph và failure domain được xác định.
- [ ] RTO/RPO được business owner phê duyệt theo từng ứng dụng/dataset.
- [ ] Chiến lược backup/restore, pilot light, warm/hot standby hoặc active-active phù hợp mục tiêu.
- [ ] Replication semantics, lag, data loss window và recovery point có thể đo.
- [ ] Có multi-signal detection, declare criteria, incident commander và quyền phê duyệt.
- [ ] Fencing/leader ownership ngăn primary cũ tiếp tục ghi trước khi mở writer mới.
- [ ] Runbook có state, precondition, action, verification, timeout, stop condition và rollback.
- [ ] Dependency network, DNS, IAM, KMS, secret, certificate và private endpoint sẵn sàng ở DR.
- [ ] Database, queue, object/file, cache và search/index có recovery strategy riêng.
- [ ] Idempotency/reconciliation xử lý giao dịch không rõ kết quả và message replay.
- [ ] Traffic routing có health probe, TTL/cache consideration, gradual shift và rollback.
- [ ] Session, long-lived connection và client endpoint behavior được kiểm thử.
- [ ] DR region có quota, IP, compute, database, storage và third-party allowlist đủ capacity.
- [ ] Có degraded mode và ưu tiên workload theo criticality.
- [ ] Backup độc lập/immutable, key recovery và restore test đã được xác minh.
- [ ] Failback có reverse replication, final sync, fencing, routing và owner.
- [ ] Dashboard theo dõi incident phase, RPO/RTO, data lag, traffic, SLO, dependency và security.
- [ ] Tabletop, restore test, partial/full failover và failback game day được lên lịch.
- [ ] Action items từ diễn tập có owner, deadline và được retest.
- [ ] Chi phí standby, transfer, backup, test và vận hành nằm trong ngân sách được duyệt.

**Ghi nhớ:** Thiết kế chuyển vùng tốt điều phối dữ liệu, quyền writer, dependency và traffic theo một quy trình có trạng thái. Phải xác minh sự cố trước khi declare, fence nguồn cũ trước khi mở ghi ở nguồn mới, khôi phục identity/key/network cùng dữ liệu, rồi chuyển traffic theo tiêu chí và xác minh hành trình nghiệp vụ. Failback cần đồng bộ và cutover riêng. Hãy chứng minh RTO/RPO bằng game day và restore test định kỳ; tài liệu DR chỉ có giá trị khi người vận hành thực hiện được trong tình huống thực tế.
