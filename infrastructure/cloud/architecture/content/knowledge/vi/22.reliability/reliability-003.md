# Triển khai đa vùng sẵn sàng và tránh phụ thuộc dùng chung

Một ứng dụng có nhiều replica vẫn có thể ngừng hoạt động nếu tất cả replica nằm trong cùng một vùng cloud và vùng đó gặp sự cố. Tương tự, triển khai ứng dụng ở hai region chưa chắc tạo ra khả năng phục hồi thực sự nếu cả hai cùng phụ thuộc vào một database primary, một DNS provider, một hệ thống identity, một KMS key path hoặc một pipeline điều khiển duy nhất. Kiến trúc đa vùng chỉ có giá trị khi hệ thống có thể tiếp tục cung cấp chức năng quan trọng trong tình huống một failure domain bị cô lập hoặc mất hoàn toàn.

**Triển khai đa vùng (multi-region deployment)** là bố trí các thành phần ứng dụng và dữ liệu trên nhiều region địa lý để giảm ảnh hưởng của sự cố có phạm vi lớn, hỗ trợ yêu cầu độ trễ hoặc tuân thủ dữ liệu. **High availability (HA)** là khả năng duy trì dịch vụ trong mức gián đoạn cho phép khi một hay nhiều thành phần lỗi. **Disaster recovery (DR)** là năng lực khôi phục dịch vụ và dữ liệu sau một sự cố nghiêm trọng theo mục tiêu thời gian và mất dữ liệu đã thống nhất.

Một thiết kế có thể đạt HA trong một region bằng nhiều availability zone, nhưng vẫn không chống chịu được sự cố ở cấp region. Ngược lại, triển khai hai region không tự động bảo đảm HA nếu failover, dữ liệu, identity hoặc dependency dùng chung không sẵn sàng. Bài học này tập trung vào kiến trúc đa vùng và cách nhận diện, giảm thiểu các dependency dùng chung có thể làm mất tác dụng của dự phòng.

Trong module **CLOUD_ARCHITECTURE**, chủ đề này liên kết trực tiếp với độ tin cậy, bảo mật, network, compute, data architecture, vận hành và chi phí. Mục tiêu là đánh giá failure domain, chọn topology phù hợp, định nghĩa RTO/RPO, thiết kế replication và traffic failover, tránh split-brain, kiểm tra shared dependencies và chứng minh khả năng phục hồi bằng diễn tập.

## 1. Availability zone, region và failure domain

Một cloud provider thường tổ chức hạ tầng thành các khu vực địa lý (region), trong mỗi region có thể có nhiều availability zone (AZ) hoặc vùng hạ tầng độc lập tương ứng. Các AZ thường được thiết kế để giảm tương quan lỗi về nguồn điện, làm mát và mạng trong phạm vi region, nhưng chi tiết cách ly phụ thuộc provider.

**Failure domain** là phạm vi tài nguyên có thể cùng bị ảnh hưởng bởi một nguyên nhân lỗi. Nó có thể là:
- Một process hoặc container.
- Một VM hoặc node.
- Một rack hoặc cụm phần cứng.
- Một availability zone.
- Một region.
- Một provider hoặc control plane.
- Một dependency dùng chung như DNS, identity, certificate authority hoặc KMS.

~~~mermaid
flowchart TB
    P["Cloud provider"] --> R1["Region A"]
    P --> R2["Region B"]
    R1 --> A1["AZ A1"]
    R1 --> A2["AZ A2"]
    R2 --> B1["AZ B1"]
    R2 --> B2["AZ B2"]
    A1 --> N1["Compute / Data"]
    A2 --> N2["Compute / Data"]
    B1 --> N3["Compute / Data"]
    B2 --> N4["Compute / Data"]
~~~

Việc có hai AZ trong cùng region giúp xử lý một số lỗi cục bộ, nhưng nhiều dịch vụ quản lý, endpoint, quota, control plane và dữ liệu vẫn có phạm vi region. Mất region có thể ảnh hưởng tất cả AZ trong region đó.

### 1.1. HA nhiều AZ và DR nhiều region

| Phạm vi | Mục tiêu chính | Ví dụ sự cố được giảm thiểu | Giới hạn |
|---|---|---|---|
| Nhiều process/container | Tiếp tục khi một tiến trình lỗi | Crash, memory leak cục bộ | Không chịu được node/zone failure nếu đặt cùng host |
| Nhiều node | Chịu lỗi máy chủ | VM/node hỏng | Có thể cùng AZ hoặc cùng storage/network dependency |
| Nhiều AZ | Chịu một số lỗi cấp zone | Mất điện, mạng hoặc hạ tầng một AZ | Không chống được region-wide outage |
| Nhiều region | Phục hồi sau sự cố cấp region | Mất region, gián đoạn diện rộng | Phức tạp về dữ liệu, routing, consistency và chi phí |
| Đa provider | Giảm một số rủi ro phụ thuộc provider | Provider-wide hoặc control-plane outage | Tăng đáng kể phức tạp, dữ liệu và vận hành |

Không phải mọi ứng dụng cần multi-region active-active. Trước tiên cần xác định hậu quả downtime và mất dữ liệu, rồi chọn failure domain phù hợp với yêu cầu kinh doanh.

## 2. Xác định mục tiêu RTO và RPO

Hai mục tiêu nền tảng của DR là:

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa chấp nhận bị mất, thường biểu diễn bằng khoảng thời gian dữ liệu.

Ví dụ:
- Một trang nội dung công khai có thể chấp nhận RTO 4 giờ và RPO 1 giờ.
- Một API đặt chỗ trọng yếu có thể cần RTO 15 phút và RPO gần bằng 0, nhưng phải xem xét khả năng kỹ thuật, chi phí và định nghĩa chính xác của giao dịch đã commit.
- Một dashboard phân tích có thể chấp nhận RTO dài hơn và chạy lại từ dữ liệu nguồn.

RTO/RPO là **mục tiêu nghiệp vụ**, không phải lời hứa mặc định của dịch vụ cloud. Cần kiểm chứng bằng replication lag, thời gian phát hiện, thời gian quyết định failover, thời gian cấp tài nguyên, DNS/traffic propagation, startup, recovery database và kiểm tra nghiệp vụ.

### 2.1. Phân biệt availability với recovery

Availability thường đo tỷ lệ thời gian hệ thống phục vụ đúng SLO trong một khoảng quan sát. DR tập trung vào cách phục hồi sau một sự cố lớn và kiểm soát mất dữ liệu. Một hệ thống có nhiều region nhưng failover mất 6 giờ vẫn có thể không đáp ứng mục tiêu RTO 30 phút.

### 2.2. Ví dụ RTO/RPO theo tier

| Tier dịch vụ | RTO minh họa | RPO minh họa | Kiểu giải pháp thường cân nhắc |
|---|---:|---:|---|
| Tier 0: giao dịch cốt lõi | Phút | Gần 0 hoặc vài giây | Multi-zone, replication chặt, standby nóng hoặc multi-region được thiết kế kỹ |
| Tier 1: API nghiệp vụ quan trọng | 15–60 phút | Vài phút | Warm standby, database replication, tự động/điều phối failover |
| Tier 2: báo cáo/vận hành | Vài giờ | 1 giờ hoặc hơn | Pilot light, backup/restore, batch rebuild |
| Tier 3: nội dung có thể tái tạo | Hàng giờ/ngày | Có thể tái tạo | Backup, object versioning, redeploy từ artifact |

Các giá trị chỉ minh họa. Phải thống nhất RTO/RPO cho từng capability và loại dữ liệu, không gán một con số cho toàn hệ thống rồi giả định mọi thành phần có cùng mức quan trọng.

## 3. Chọn topology đa vùng

Có nhiều topology. Không có topology nào tốt nhất trong mọi hoàn cảnh.

### 3.1. Active-passive

Một region phục vụ production; region còn lại duy trì bản sao dữ liệu và compute dự phòng. Khi region chính không hoạt động, hệ thống promote database hoặc bật compute ở region dự phòng rồi chuyển traffic.

~~~mermaid
flowchart TB
    U["Users"] --> G["Global routing"]
    G --> A["Region A - Active"]
    G -. "Standby" .-> B["Region B - Passive"]
    A --> DA[("Primary data")]
    DA ==>|"Replication"| DB[("Standby replica")]
    B -.-> DB
~~~

Ưu điểm:
- Một nơi ghi dữ liệu chính giúp đơn giản hóa consistency.
- Standby có thể ít tài nguyên hơn nên giảm chi phí so với active-active.
- Dễ giải thích về ownership và luồng ghi.

Đánh đổi:
- Standby có thể không đủ capacity nếu chỉ được giữ ở mức tối thiểu.
- Khi failover cần promote dữ liệu, scale compute, kiểm tra dependency và chuyển traffic.
- Replication lag có thể làm mất các giao dịch gần nhất.
- Nếu failover không diễn tập, quy trình thủ công dễ vượt RTO.

Active-passive phù hợp khi cần DR rõ ràng, traffic có thể chuyển vùng và nghiệp vụ chấp nhận một khoảng failover.

### 3.2. Warm standby

Region dự phòng đã chạy một phiên bản tối thiểu hoặc thu nhỏ của ứng dụng, database replica và dependency cần thiết. Khi region chính lỗi, tăng capacity và chuyển traffic.

Ưu điểm là RTO thường tốt hơn pilot light vì nhiều thành phần đã sẵn sàng. Đổi lại, vẫn phải đảm bảo warm capacity, scale-up time, model/artifact/cache warm-up và quota. Replica standby cần được kiểm tra liên tục để không trở thành một hệ thống cũ hoặc cấu hình lệch.

### 3.3. Pilot light

Region dự phòng có những thành phần tối thiểu để phục hồi, như network, identity integration, database replication, artifact và cấu hình. Compute ứng dụng có thể chưa chạy hoặc chỉ chạy ở mức rất nhỏ.

Chi phí thấp hơn warm standby nhưng RTO dài hơn do phải cấp compute, triển khai ứng dụng, nạp artifact và xác minh. Phải chắc chắn automation, image registry và secret access đều hoạt động trong region dự phòng.

### 3.4. Backup and restore

Không duy trì ứng dụng chạy ở region thứ hai. Khi cần DR, khôi phục backup, triển khai hạ tầng và dữ liệu ở nơi khác.

Đây là cách có thể phù hợp hệ thống ít quan trọng hoặc dữ liệu có thể tái tạo, nhưng thường RTO dài hơn. Backup chỉ hữu ích khi restore được, key vẫn truy cập được, schema tương thích và thời gian khôi phục đã được đo.

### 3.5. Active-active

Nhiều region cùng nhận traffic production. Có thể mỗi region phục vụ người dùng gần đó hoặc mọi region cùng phục vụ toàn bộ người dùng.

~~~mermaid
flowchart TB
    U["Users worldwide"] --> G["Global traffic manager"]
    G --> A["Region A - Active"]
    G --> B["Region B - Active"]
    A --> DA[("Regional data A")]
    B --> DB[("Regional data B")]
    DA <-->|"Replication / conflict policy"| DB
~~~

Ưu điểm:
- Có thể giảm latency cho người dùng ở nhiều khu vực.
- Compute của nhiều region đều đang được sử dụng.
- Một region lỗi có thể chuyển traffic sang region khác mà không cần khởi động toàn bộ stack.

Đánh đổi:
- Dữ liệu ghi đồng thời ở nhiều nơi cần conflict resolution hoặc partition ownership.
- Có thể phát sinh duplicate, lost update hoặc write conflict.
- Traffic có thể chuyển sang region còn lại làm overload khi capacity chỉ được tính cho phân bổ bình thường.
- Cần consistency model, routing policy và dữ liệu locality rõ ràng.
- Kiểm thử và vận hành phức tạp hơn đáng kể.

Active-active chỉ hợp lý khi workload và data model thực sự hỗ trợ phân tán ghi hoặc có cách điều phối nhất quán, đồng thời lợi ích latency/availability xứng đáng với chi phí.

### 3.6. So sánh topology

| Kiểu | Compute ở region DR | Độ phức tạp dữ liệu | Chi phí thường gặp | RTO tương đối |
|---|---|---|---|---|
| Backup/restore | Không hoặc rất ít | Khôi phục backup | Thấp hơn khi bình thường | Dài |
| Pilot light | Tối thiểu | Replication/restore | Thấp–trung bình | Trung bình–dài |
| Warm standby | Thu nhỏ nhưng chạy | Replication và promote | Trung bình | Ngắn hơn pilot light |
| Active-passive nóng | Đủ capacity dự phòng | Một writer chính, standby | Cao hơn | Ngắn |
| Active-active | Nhiều region đều phục vụ | Multi-writer/partition/conflict | Thường cao và phức tạp | Có thể ngắn, nếu không có data bottleneck |

RTO thực tế còn phụ thuộc vào failure detection, quyết định failover, promotion, routing propagation, dependencies và validation. Không suy ra RTO chỉ từ tên topology.

## 4. Traffic routing và failover

Traffic đa vùng có thể được điều phối qua DNS-based routing, global load balancer, anycast network, CDN hoặc service-specific traffic manager.

Các chiến lược:
- **Priority/failover:** ưu tiên region chính; chuyển sang region dự phòng khi health check thất bại.
- **Weighted routing:** phân bổ tỷ lệ traffic giữa nhiều region.
- **Latency-based routing:** đưa user tới region có độ trễ phù hợp.
- **Geographic routing:** định tuyến theo vị trí hoặc data residency.
- **Anycast/global edge:** định tuyến tới điểm vào mạng gần hoặc khỏe theo cơ chế provider.

### 4.1. Health check phải phản ánh khả năng phục vụ

Một endpoint health chỉ kiểm tra process đang sống có thể trả healthy dù database đã mất kết nối. Mặt khác, nếu health check phụ thuộc mọi dịch vụ tùy chọn, một dependency phụ lỗi có thể loại cả region khỏi routing.

Cần phân biệt:
- **Liveness:** process có cần restart không?
- **Readiness:** instance có thể nhận traffic mới không?
- **Regional health:** region có đủ các capability tối thiểu để phục vụ loại request cụ thể không?
- **Dependency health:** dependency nào lỗi và có thể degrade chức năng nào?

Health check nên kiểm tra các dependency trọng yếu ở mức phù hợp nhưng không gây thundering herd hoặc biến outage của một tính năng phụ thành failover toàn region.

### 4.2. DNS failover có độ trễ và cache

DNS-based failover không phải lúc nào cũng tức thời:
- Resolver và client có thể cache record theo TTL.
- Một số client không tuân thủ TTL như mong đợi.
- Health check có interval và threshold trước khi thay đổi routing.
- Connection đang mở có thể tiếp tục dùng endpoint cũ.
- DNS control plane hoặc authoritative DNS chính là dependency cần được đánh giá.

Global load balancer có thể chuyển traffic nhanh hơn trong một số mô hình, nhưng bản thân nó cũng có phạm vi failure và dependency riêng. Cần đo thời gian chuyển traffic thực tế từ nhiều mạng và region.

### 4.3. Quy trình failover

1. Phát hiện lỗi bằng telemetry độc lập với region bị ảnh hưởng.
2. Xác minh phạm vi và loại sự cố: zone, region, dữ liệu, network hay dependency.
3. Quyết định failover tự động hay cần approval.
4. Ngăn ghi mới ở primary nếu cần để tránh split-brain.
5. Kiểm tra replication lag và chọn điểm dữ liệu có thể promote.
6. Promote database/partition hoặc chuyển writer theo quy trình.
7. Bảo đảm secret, identity, KMS, DNS, certificate và endpoint ở region đích hoạt động.
8. Scale compute và worker tới capacity cần thiết.
9. Chuyển traffic theo từng bước hoặc policy đã kiểm thử.
10. Chạy smoke test và xác minh nghiệp vụ, không chỉ HTTP 200.
11. Giám sát lỗi, latency, queue backlog, duplicate và data consistency.
12. Ghi nhận thời gian phục hồi và đối soát dữ liệu.

Không failover ghi hai chiều chỉ vì endpoint primary không phản hồi. Nếu chưa biết primary có còn ghi được hay không, chuyển writer có thể tạo split-brain.

## 5. Replication và tính nhất quán dữ liệu

Một region thứ hai chỉ hữu ích khi có dữ liệu đủ mới để phục vụ nghiệp vụ.

### 5.1. Synchronous replication

Giao dịch được xác nhận sau khi dữ liệu đã được ghi theo cơ chế đồng bộ tới một hoặc nhiều bản sao cần thiết. Có thể giảm RPO nhưng tăng latency và phụ thuộc network giữa các failure domain. Nếu replica không phản hồi, write availability có thể giảm.

### 5.2. Asynchronous replication

Primary xác nhận write trước khi bản sao nhận đầy đủ dữ liệu. Giảm latency và giúp primary ít phụ thuộc đường truyền liên region, nhưng replica có lag. Khi primary mất đột ngột, các giao dịch chưa replicate có thể mất.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary DB
    participant R as Remote replica
    A->>P: Commit transaction
    P-->>A: Commit acknowledged
    P-->>R: Replicate asynchronously
    Note over P,R: Replica may lag behind primary
~~~

### 5.3. Semi-synchronous và quorum

Một số hệ thống xác nhận write sau khi một tập replica/quorum nhận log hoặc dữ liệu theo semantics cụ thể. Quorum không có nghĩa “đa số region luôn có dữ liệu đầy đủ” theo mọi sản phẩm; phải hiểu điều kiện commit, failure tolerance, election và consistency guarantee.

### 5.4. Các loại replication cần phân biệt

- **Storage/block replication:** sao chép block hoặc volume; có thể crash-consistent nhưng không nhất thiết application-consistent.
- **Database replication:** sao chép transaction/log hoặc row-level change theo cơ chế DB.
- **Object replication:** sao chép object/version/metadata; có thể bất đồng bộ và không bảo đảm thứ tự nghiệp vụ giữa nhiều object.
- **Event replication:** chuyển event qua broker/stream; cần xử lý duplicate, ordering và replay.
- **Application-level replication:** application ghi tới nhiều nơi hoặc đồng bộ theo workflow riêng.

Không coi backup, replication và consistency là từ đồng nghĩa. Replication có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu mã hóa bởi key đã mất; backup có thể giữ điểm khôi phục lịch sử riêng biệt.

## 6. Split-brain, quorum và single-writer ownership

**Split-brain** xảy ra khi hai node/region cùng tin rằng mình là primary hoặc có quyền ghi, trong khi hệ thống mong muốn chỉ một writer. Khi network partition, hai phía có thể nhận write và tạo dữ liệu mâu thuẫn.

Cách giảm rủi ro:
- Có cơ chế leader election/quorum với semantics được hiểu rõ.
- Dùng lease có thời hạn và fencing token để ngăn writer cũ tiếp tục ghi sau khi mất quyền.
- Chặn hoặc fence primary cũ trước khi promote writer mới.
- Dùng single-writer per dataset/partition nếu workload không hỗ trợ multi-writer.
- Thiết kế idempotency và conflict resolution cho trường hợp duplicate.
- Không quyết định promote chỉ từ health check của app.

Trong multi-region, quorum giữa các region có thể chịu ảnh hưởng bởi latency liên vùng và mất mạng. Thiết kế ba failure domain hoặc witness có thể giúp một số hệ thống xác định majority, nhưng witness không thay thế bản sao dữ liệu đủ để phục vụ write. Cần xem thuật toán và yêu cầu cụ thể của database/broker.

### 6.1. Fencing token

Một fencing token là số thứ tự/epoch tăng đơn điệu cấp cho chủ thể giữ quyền. Storage hoặc resource kiểm tra token để từ chối writer cũ có token thấp hơn. Đây là cách bảo vệ trước trường hợp lease hết hạn nhưng process cũ vẫn chạy do pause hoặc network delay.

Không phải mọi database/cloud service có API fencing trực tiếp; đôi khi cần đặt logic trong tầng dữ liệu hoặc dùng cơ chế consensus/provider hỗ trợ.

## 7. Tránh shared dependencies làm mất dự phòng

Đây là phần thường bị bỏ quên nhất trong thiết kế multi-region. Hai region có thể chạy application và database độc lập nhưng cùng cần một dịch vụ dùng chung để khởi động, xác thực, giải mã secret, phân giải tên hoặc deploy. Nếu dependency đó lỗi, cả hai region cùng không hoạt động.

Một shared dependency có thể là:
- Identity provider, federation hoặc control plane xác thực.
- DNS authoritative, registrar hoặc DNS management account.
- KMS, HSM, certificate authority và dịch vụ cấp chứng chỉ.
- Secret manager hoặc cấu hình tập trung.
- Container/image registry, package repository, model registry.
- CI/CD, source control, deployment orchestrator.
- Global load balancer, WAF, CDN control plane.
- Centralized logging, monitoring, tracing hoặc alerting.
- Network hub, transit gateway, firewall hoặc egress proxy.
- Database control plane, replication coordinator hoặc shared metadata store.
- SaaS bên thứ ba, payment provider, email/SMS provider.

~~~mermaid
flowchart TB
    A["Region A"] --> APPA["Application A"]
    B["Region B"] --> APPB["Application B"]
    APPA --> SHARED["Shared identity / KMS / DNS / registry"]
    APPB --> SHARED
    SHARED --> X["Shared dependency failure"]
    X --> DOWN["Both regions affected"]
~~~

### 7.1. Lập dependency inventory

Với mỗi dependency, ghi:
- Owner và team vận hành.
- Failure domain/phạm vi region.
- Endpoint và network path.
- Có cần trong runtime hay chỉ lúc deploy/startup?
- Có cache/local credential/fallback không?
- Có thể truy cập từ region DR không?
- RTO/RPO và SLA của nhà cung cấp.
- Cách thay thế khi dependency unavailable.
- Quy trình kiểm thử và người có quyền thực hiện.

Không chỉ hỏi “dịch vụ có multi-region không?” mà phải hỏi **control plane, data plane, identity, key access và quota của nó được dự phòng như thế nào**.

## 8. Thiết kế identity và quyền truy cập đa vùng

Một ứng dụng dự phòng có thể không khởi động nếu workload identity hoặc federation chỉ cấu hình cho region chính.

Cần đánh giá:
- Workload identity có được tạo/ủy quyền cho region, account/subscription/project đích không?
- Token issuer, audience, federation trust và endpoint có thể truy cập khi region chính mất không?
- Credential có phụ thuộc identity control plane theo thời điểm lấy token không?
- Runtime có thể tiếp tục dùng token ngắn hạn đang có trong bao lâu?
- Role/policy ở region DR đã được provision và kiểm tra quyền chưa?
- Admin break-glass có hoạt động nếu SSO/IdP chính gián đoạn không?

Ưu tiên identity riêng cho workload và quyền tối thiểu. Tránh chỉ tạo role khi failover xảy ra vì quá trình provisioning có thể nằm trên critical path RTO.

### 8.1. Control plane và data plane

Control plane quản lý cấu hình/tài nguyên; data plane xử lý traffic hoặc thao tác runtime. Một số dịch vụ có thể tiếp tục data-plane operation khi control plane bị gián đoạn, nhưng không thể tạo tài nguyên mới, đổi policy hoặc cấp credential. Cần biết chính xác behavior dịch vụ được dùng.

Thiết kế DR không nên giả định rằng vì container đang chạy ở region B nên mọi thao tác identity, secret retrieval, policy refresh và scaling cũng sẽ hoạt động.

## 9. KMS, encryption key và certificate

Một database replica hoặc object đã replicate có thể không đọc được ở region dự phòng nếu key hoặc quyền giải mã không sẵn sàng.

Cần:
- Key có thể được sử dụng tại region đích theo policy/provider không?
- Có multi-region key hay key replica và semantics rotation phù hợp không?
- Backup encryption key được escrow/quản lý ở đâu?
- Identity của workload DR có quyền decrypt đúng scope không?
- Hệ thống certificate có thể phát hành/renew khi CA hoặc account chính lỗi không?
- Trust bundle và certificate có expiry phù hợp với thời gian DR không?
- Có lưu private key trong một dependency tập trung duy nhất không?

Không sao chép private key thô tùy tiện sang region khác. Dùng cơ chế KMS/HSM và key replication được provider hỗ trợ; kiểm tra policy, audit và residency. DR drill cần thử giải mã backup hoặc đọc dữ liệu đã replicate bằng identity của region dự phòng, không chỉ xác minh object tồn tại.

## 10. DNS, network và kết nối giữa region

DNS và network là hạ tầng thiết yếu của cả application lẫn quy trình failover.

Cần đánh giá:
- DNS authoritative và account quản lý có độc lập với region application không?
- TTL, resolver cache và propagation được đo ra sao?
- Có địa chỉ/endpoint dự phòng và certificate phù hợp không?
- Transit network, firewall, NAT, egress proxy có shared failure point không?
- Routing table, peering, private endpoint và security group ở region DR đã sẵn sàng chưa?
- Kết nối tới data store, object storage, identity và third-party có được kiểm thử không?
- Có tránh phụ thuộc duy nhất vào một VPN appliance hoặc một network hub không?

Một region có compute healthy nhưng không truy cập được database hoặc identity endpoint vẫn không thể phục vụ. Có thể cần network path riêng hoặc thiết kế hub redundancy; tuy nhiên, thêm đường mạng cần kiểm soát routing loop, security boundary và chi phí cross-region.

### 10.1. Egress và data transfer

Replication, backup, log shipping và traffic failover đều có thể tạo cross-region egress. Khi thiết kế, tính:
- Dung lượng dữ liệu replicate mỗi giây/ngày.
- Burst khi backlog được catch up.
- Lưu lượng app giữa region.
- Chi phí backup/restore và object replication.
- Phí global load balancer/CDN và cross-zone transfer.

Một kiến trúc active-active có thể tạo lượng replication hai chiều đáng kể; chi phí và latency cần được benchmark trước.

## 11. Registry, artifact và pipeline trong DR

Region dự phòng có thể không triển khai được nếu container registry, package repository hoặc model artifact store chỉ tồn tại ở region chính.

Cần chuẩn bị:
- Image và artifact đã được promote được replicate tới region DR.
- Digest/signature và provenance được giữ nguyên.
- Runtime dependency có thể cài đặt mà không gọi registry chính.
- IaC/module/provider/version cần thiết có bản mirror hoặc cache.
- Secret/config cho deployment đã được chuẩn bị an toàn.
- Deployment pipeline có thể chạy từ một failure domain độc lập.
- Quyền phê duyệt và break-glass được duy trì ngoài SSO/control plane duy nhất nếu yêu cầu.

Không để runbook DR yêu cầu “build lại image từ source” khi source control, package registry hoặc CI/CD chính đang lỗi. Nên chuẩn bị artifact production-ready đã kiểm duyệt, cùng manifest triển khai có version.

## 12. Observability và quản trị khi mất một region

Centralized observability giúp có cái nhìn toàn hệ thống nhưng chính nó cũng có thể trở thành shared dependency. Nếu mọi metric/log/alert chỉ gửi về một region và region đó mất, đội vận hành có thể mất tầm nhìn vào sự cố còn lại.

Cân nhắc:
- Agent có local buffer khi central collector unavailable.
- Có monitor/alert ngoài region và ngoài account/subscription chính.
- Có kênh liên lạc incident độc lập với hệ thống ứng dụng.
- Dashboard cho từng region và dashboard global.
- Clock/time synchronization đủ tin cậy để đối chiếu log.
- Correlation ID và trace context được truyền xuyên region.
- Log chứa dữ liệu nhạy cảm được redaction trước khi replicate.
- Quyền truy cập observability hoạt động khi SSO chính lỗi.

Cần phân biệt telemetry của control plane và data plane. Một dashboard xanh không chứng minh user journey thành công; phải kiểm tra synthetic transaction từ bên ngoài từng region.

## 13. Active-active data design và phân vùng quyền ghi

Để active-active an toàn, cần lựa chọn mô hình dữ liệu phù hợp.

### 13.1. Single-writer per record/partition

Mỗi aggregate/tenant/partition có một region chịu trách nhiệm ghi tại một thời điểm. Các region khác có thể đọc replica hoặc xử lý workload khác. Khi failover, cần chuyển ownership có epoch/fencing và đối soát replication.

Ưu điểm là giảm write conflict. Đánh đổi là một partition có thể phải chuyển region khi owner lỗi và có thể tăng latency cho user ở xa writer.

### 13.2. Multi-writer với conflict resolution

Nhiều region có thể ghi cùng một dữ liệu. Cần định nghĩa cách giải quyết xung đột:
- Last-write-wins theo timestamp/clock đã quản lý.
- Version vector/causal metadata.
- CRDT cho loại dữ liệu phù hợp.
- Application-level merge hoặc workflow compensation.

Last-write-wins đơn giản nhưng có thể ghi đè update có ý nghĩa; clock lệch có thể gây kết quả sai. CRDT chỉ áp dụng được với cấu trúc và phép toán có tính chất phù hợp, không phải giải pháp chung cho giao dịch booking hoặc payment.

### 13.3. Phân vùng theo địa lý/tenant

Một tenant hoặc nhóm dữ liệu được gán home region. User có thể truy cập qua global endpoint nhưng thao tác ghi định tuyến tới region sở hữu. Cách này giảm conflict nhưng cần:
- Mapping tenant-to-region có độ sẵn sàng cao.
- Quy trình chuyển tenant khi region lỗi.
- Cách đọc dữ liệu chéo region.
- Quy định data residency.
- Xử lý transaction liên tenant hoặc báo cáo toàn cục.

Đây là lựa chọn thường dễ kiểm soát hơn multi-writer tùy ý cho dữ liệu giao dịch.

## 14. Failback: quay về region ban đầu

Sau khi failover sang region B, không nên tự động chuyển traffic về region A ngay khi A báo healthy. A có thể vẫn chứa dữ liệu cũ, version schema lệch hoặc cấu hình khác.

Quy trình failback:
1. Xác nhận region A đã phục hồi và nguyên nhân gốc được xử lý.
2. Giữ A ở trạng thái không nhận write.
3. Đồng bộ dữ liệu từ writer hiện tại B về A.
4. Đối soát replication lag, schema, key access và object versions.
5. Kiểm tra app/runtime/image/config cùng model/secret version.
6. Thực hiện test nghiệp vụ và capacity test ở A.
7. Chọn maintenance window và kế hoạch chuyển quyền ghi.
8. Fence writer B hoặc chuyển ownership theo protocol.
9. Chuyển traffic từng bước và quan sát.
10. Giữ khả năng quay lại B cho tới khi xác nhận ổn định.
11. Ghi nhận thời gian failback và dữ liệu được reconciliation.

Failback là một quy trình thay đổi dữ liệu và traffic có rủi ro; không đồng nghĩa với đảo ngược DNS record.

## 15. Security trong kiến trúc đa vùng

Mở rộng region làm tăng số bản sao dữ liệu, endpoint, key, policy và principal. Bảo mật phải nhất quán mà vẫn đáp ứng data residency.

- Áp dụng least privilege cho runtime, replication agent và operator.
- Tách quyền failover, promote writer, redrive và purge.
- Mã hóa data in transit và at rest; quản lý key ở region đích.
- Có audit log độc lập hoặc được replicate an toàn.
- Bảo vệ control plane, break-glass và emergency credential.
- Xác định dữ liệu nào không được rời khỏi region/quốc gia.
- Không mở network rộng giữa hai region chỉ để dễ replication.
- Kiểm soát secret/config drift và image provenance.
- Kiểm tra security policy ở region DR, không chỉ ở region chính.
- Giữ nguyên quy trình incident response khi một region/IdP bị xâm nhập.

Một DR site là production site trong tình huống khẩn cấp. Không được giảm security posture tới mức dữ liệu quan trọng trở thành dễ truy cập hơn chỉ vì cần khôi phục nhanh.

## 16. Kiểm thử và diễn tập đa vùng

Tài liệu DR chưa được diễn tập chỉ là giả định. Cần kiểm thử theo nhiều cấp:

| Loại test | Phạm vi | Mục tiêu |
|---|---|---|
| Component failover | Process/node/AZ | Kiểm tra health, reschedule và load balancing |
| Region simulation | Chặn một số dependency hoặc route của region | Kiểm tra detection và fallback |
| Planned regional failover | Chuyển traffic có kế hoạch | Xác nhận runbook, data promotion và DNS/routing |
| Unplanned DR exercise | Mô phỏng mất region không báo trước trong môi trường kiểm soát | Đo RTO/RPO thực tế |
| Dependency outage | IdP, KMS, DNS, registry, observability | Phát hiện shared dependency |
| Restore test | Khôi phục backup vào môi trường riêng | Xác nhận backup và key dùng được |
| Failback rehearsal | Đồng bộ về region ban đầu | Kiểm tra reverse replication và ownership |
| Capacity failover test | Chuyển toàn bộ tải sang region còn lại | Xác nhận headroom và quota |

### 16.1. Game day có kiểm soát

Một game day nên có:
- Scope, owner và người chỉ huy.
- Kịch bản, điều kiện dừng và rollback.
- Mục tiêu RTO/RPO và tiêu chí thành công.
- Các user journey cần xác minh.
- Kiểm soát tác động tới khách hàng và dữ liệu thật.
- Ghi lại timeline và quyết định.
- Review sau diễn tập và theo dõi action item.

Không cần bắt đầu bằng việc tắt toàn bộ region production. Có thể mô phỏng chặn dependency, failover staging hoặc chuyển một cohort nhỏ trước khi tiến hành diễn tập lớn.

## 17. Bảng kiểm tra shared dependency

Dùng bảng sau trong architecture review:

| Dependency | Region A | Region B | Có shared failure domain? | Phương án kiểm soát |
|---|---|---|---|---|
| Identity/token issuer | Local/federated | Local/federated | Cần xác minh | Token strategy, alternate admin access |
| DNS/traffic management | Global service | Global service | Có thể | Redundant authoritative DNS, tested routing |
| KMS/HSM | Regional key | Regional replica/key | Có thể | Cross-region key policy, decrypt test |
| Secret/config store | Runtime endpoint | Runtime endpoint | Có thể | Replica/cache, local bootstrap config |
| Container/artifact registry | Local mirror | Local mirror | Có thể | Replicated immutable artifacts |
| CI/CD and source control | Pipeline primary | Independent deployment path | Có thể | DR deploy pipeline and runbook |
| Network hub/firewall | Path A | Path B | Có thể | Redundant path and routing test |
| Observability/alerting | Local buffer | Local buffer | Có thể | Independent monitors and incident channel |
| Certificate authority | Issuer access | Issuer access | Có thể | Pre-issued cert, renew/rotation exercise |
| Third-party provider | Same endpoint | Same endpoint | Thường có | Alternative provider or graceful degradation |
| Quota/control plane | Account/service quota | Account/service quota | Tùy provider | Pre-approved quota and warm capacity |

Bảng này là điểm bắt đầu. Với từng dependency, phải ghi rõ endpoint, account, control plane, data plane, identity và failure scope thực tế. Hai endpoint khác nhau không nhất thiết là hai failure domain độc lập nếu chúng cùng dùng backend hoặc control plane.

## 18. Đánh đổi theo Well-Architected

| Khía cạnh | Lợi ích của multi-region | Rủi ro/chi phí cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Phục hồi khi mất zone/region, giảm downtime | Replication lag, split-brain, failover không diễn tập, capacity DR thiếu | DR drill, measured RTO/RPO, failover test |
| **Bảo mật** | Có thể cô lập failure domain và duy trì dịch vụ | Tăng bản sao PII, key/policy drift, break-glass yếu | IAM review, encryption test, audit và residency |
| **Hiệu quả hiệu năng** | Phục vụ gần user, latency thấp hơn, phân tải | Cross-region write/replication latency, routing sai, cache cold | p95/p99 theo region, replication lag |
| **Tối ưu chi phí** | Tránh outage lớn; có thể dùng pilot light/standby | Compute nhàn rỗi, replication, network egress, DR exercise | Cost per tier, standby utilization, transfer cost |
| **Vận hành xuất sắc** | Có recovery process và ownership rõ | Nhiều topology, runbook và control plane hơn | Game day, runbook, dependency inventory |
| **Bền vững** | Duy trì dịch vụ và phục hồi dữ liệu quan trọng | Replicate mọi dữ liệu không cần thiết làm tăng storage/network/compute | Data classification, lifecycle và replication scope |

Các đánh đổi thường gặp:
- Active-active có thể giảm latency nhưng làm consistency và conflict resolution phức tạp.
- Active-passive dễ giữ single-writer hơn nhưng cần capacity standby và failover.
- Replication đồng bộ giảm RPO nhưng tăng latency và phụ thuộc network.
- Replication bất đồng bộ giảm độ trễ write nhưng có thể mất dữ liệu gần nhất.
- Shared global services giảm trùng lặp vận hành nhưng tạo failure domain chung.
- Tách dịch vụ theo region tăng isolation nhưng yêu cầu provisioning, policy và automation nhất quán.

## 19. Quy trình thiết kế đa vùng

1. **Phân loại capability:** xác định dịch vụ nào thật sự cần multi-zone hoặc multi-region.
2. **Xác định business impact:** downtime, mất dữ liệu, data residency và SLA.
3. **Đặt RTO/RPO:** theo từng capability, database và loại dữ liệu.
4. **Vẽ failure domain:** compute, AZ, region, provider và shared service.
5. **Chọn topology:** active-passive, pilot light, warm standby, active-active hoặc backup/restore.
6. **Thiết kế traffic routing:** health, DNS/global load balancing, propagation và capacity.
7. **Thiết kế data replication:** sync/async, writer ownership, lag, conflict và consistency.
8. **Loại bỏ shared dependency đơn điểm:** identity, KMS, DNS, registry, secrets, network, CI/CD và observability.
9. **Chuẩn bị capacity/quotas:** compute, storage, GPU nếu cần, IP, endpoint và provider quota ở region đích.
10. **Thiết kế security:** identity, key, encryption, audit, residency và break-glass.
11. **Viết failover/failback runbook:** trigger, authority, fencing, promotion, traffic và validation.
12. **Kiểm thử và diễn tập:** đo RTO/RPO, user journey, dependency outage và capacity.
13. **Theo dõi drift:** config, image, schema, policy và artifact giữa các region.
14. **Rà soát chi phí:** standby, replication, egress, license và vận hành định kỳ.

### ADR minh họa — Booking API chạy active-passive

> **Bối cảnh:** Booking API phục vụ giao dịch quan trọng. Mục tiêu kinh doanh là khôi phục trong 30 phút và không mất các giao dịch đã được xác nhận theo semantics commit của hệ thống. Traffic tập trung chủ yếu ở một khu vực địa lý.
>
> **Phương án A:** Multi-region active-active cho cả application và database. Có thể giữ traffic ở nhiều region nhưng cần thiết kế multi-writer hoặc phân vùng dữ liệu, giải quyết conflict và đối soát.
>
> **Phương án B:** Active region phục vụ ghi; region thứ hai chạy warm standby với database replication và application capacity thu nhỏ. Khi failover, fence writer cũ, promote standby rồi chuyển traffic.
>
> **Quyết định minh họa:** Chọn B nếu measured RTO/RPO đáp ứng cam kết và business không yêu cầu write locality ở nhiều region. Giữ single-writer để đơn giản hóa transaction booking.
>
> **Shared dependency:** Chuẩn bị identity, KMS key access, secret/config, DNS routing, container image và deployment pipeline ở region standby. Có monitor độc lập với region active.
>
> **Recovery:** Xác minh replication lag, fence primary, promote standby, scale capacity, chuyển traffic, smoke test booking/payment và đối soát transaction gần thời điểm lỗi.
>
> **Kiểm chứng:** Planned/unplanned failover, mất một AZ, mất region, IdP/KMS/DNS failure, quota thiếu, backup decrypt và failback.
>
> **Điều kiện xem xét lại:** Người dùng/traffic phân bố nhiều khu vực, latency liên region không đạt SLO hoặc cần write locality; khi đó đánh giá partition ownership hoặc active-active có kiểm soát.

## 20. Bài tập thực hành: tìm shared dependency trong kiến trúc DR

Một nền tảng đặt chỗ triển khai:
- Booking API và Notification Worker ở Region A.
- Một bản sao application và database replica ở Region B.
- Global DNS routing chuyển traffic khi A lỗi.
- Cả hai region dùng cùng identity provider, KMS account, secret manager endpoint, container registry, CI/CD pipeline và central logging ở Region A.
- Database replication bất đồng bộ với lag thường 20 giây.
- Region B chỉ chạy 30% capacity của A.

Nhóm tuyên bố RTO 10 phút và RPO 0.

**Yêu cầu:**
1. Xác định những shared dependency có thể làm Region B không khởi động hoặc không phục vụ được.
2. Đánh giá liệu RPO 0 có phù hợp với asynchronous replication lag 20 giây không.
3. Xác định thiếu hụt capacity khi chuyển 100% traffic sang B.
4. Thiết kế failover writer an toàn để tránh split-brain.
5. Đề xuất cách dự phòng identity, KMS, secrets, registry, pipeline, DNS và observability.
6. Xác định RTO thực tế cần đo qua những bước nào.
7. Thiết kế failback và đối soát các booking gần thời điểm region A mất.
8. Đề xuất game day kiểm thử cả region outage và shared dependency outage.

### Hướng giải quyết

- Region B còn phụ thuộc identity, KMS, secret manager, registry, CI/CD và logging của Region A. Khi A mất, B có thể không lấy token/secret, giải mã dữ liệu, nạp image, scale hoặc quan sát được sự cố.
- Replication bất đồng bộ lag 20 giây không chứng minh RPO 0. Cần đo lag, xác định giao dịch commit nào đã tới replica và thay đổi replication/consistency hoặc điều chỉnh RPO.
- Capacity 30% không thể phục vụ 100% peak nếu không có scale nhanh, admission control hoặc graceful degradation. Kiểm tra quota và startup/warm-up trước.
- Trước khi promote B, fence writer A bằng cơ chế database/epoch/lease phù hợp; xác minh primary cũ không thể nhận write; chỉ một writer được hoạt động.
- Chuẩn bị identity federation/credential, quyền decrypt key, secret/config local hoặc replica, mirror artifact, pipeline DR độc lập, DNS authority ngoài failure domain và telemetry local/independent.
- RTO tính từ detection tới service đạt user journey và SLO, gồm decision, fencing, promotion, scale, traffic propagation và validation.
- Failback phải đồng bộ dữ liệu B→A, dừng write A trước, đối soát booking/payment, kiểm tra version/config rồi mới chuyển ownership và traffic.
- Game day lần lượt cô lập region A, IdP, KMS, registry và observability; đặt điều kiện dừng, test data protection và đo RTO/RPO.

### Câu hỏi tự kiểm tra

1. Multi-AZ và multi-region bảo vệ trước những failure domain nào?
2. RTO và RPO khác nhau ra sao? Vì sao phải đo thay vì suy từ topology?
3. Active-passive, warm standby, pilot light và active-active khác nhau thế nào?
4. Vì sao DNS failover có thể chậm hơn health check?
5. Replication bất đồng bộ có thể làm mất giao dịch nào khi failover?
6. Split-brain xảy ra khi nào và fencing token giúp gì?
7. Vì sao KMS, identity hoặc registry có thể làm hai region cùng ngừng hoạt động?
8. Control plane outage khác data plane outage như thế nào?
9. Khi nào single-writer per tenant/partition phù hợp hơn multi-writer?
10. Vì sao failback cần quy trình riêng?
11. Centralized observability có thể trở thành shared dependency ra sao?
12. Bằng chứng nào chứng minh DR site thực sự đạt RTO/RPO?

Một kiến trúc đa vùng đáng tin cậy không chỉ có thêm một bản sao ứng dụng và database. Nó phải **cô lập được failure domain, có dữ liệu đủ mới, chuyển quyền ghi an toàn, duy trì identity/key/network/artifact và quan sát được hệ thống khi region chính mất**. Topology phù hợp cần bắt đầu từ RTO/RPO và data semantics, rồi được chứng minh bằng failover, failback và dependency outage drills có đo lường.
