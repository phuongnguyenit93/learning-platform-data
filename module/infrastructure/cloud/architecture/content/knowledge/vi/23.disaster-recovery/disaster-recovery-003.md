# Chiến lược backup–restore, pilot light, warm standby và active–active

> **Chương:** Phục hồi thảm họa  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt backup/restore, pilot light, warm standby và active–active; nhận biết chúng là các chiến lược có mức sẵn sàng, chi phí và độ phức tạp khác nhau.
2. Chuyển yêu cầu nghiệp vụ thành mục tiêu **RTO** và **RPO**, xác định thứ tự phục hồi và mức dịch vụ tối thiểu cần đạt.
3. Thiết kế bảo vệ và khôi phục dữ liệu, cấu hình, danh tính, khóa mã hóa, ứng dụng và các dependency cần thiết.
4. Phân tích replica lag, consistency, split-brain, fencing, failover và failback trong môi trường một vùng hoặc nhiều vùng.
5. Lựa chọn topology active-passive/active-active, quy trình DNS/global routing và cơ chế xác nhận khả năng phục hồi.
6. Tổ chức runbook, quyền quyết định, diễn tập DR, đo thời gian khôi phục và xử lý khoảng cách giữa kế hoạch với năng lực thực tế.
7. Đánh giá trade-off về độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành và tính bền vững theo Well-Architected.

## 1. Disaster recovery giải quyết vấn đề gì?

Một hệ thống cloud có thể chạy nhiều instance, dùng database managed, load balancer và nhiều availability zone nhưng vẫn có thể gặp sự cố vượt ra ngoài miền lỗi đơn lẻ. Ví dụ:

- Một region không khả dụng do sự cố diện rộng hoặc mất kết nối tới các dịch vụ nền.
- Lỗi cấu hình hoặc release xấu lan tới mọi instance.
- Tài khoản cloud bị xâm nhập, dữ liệu bị mã hóa/xóa hoặc quyền quản trị bị lạm dụng.
- Database corruption, thao tác xóa nhầm, ransomware hoặc dữ liệu logic sai được replication sang bản sao.
- Nhà cung cấp hoặc hệ thống định danh bên ngoài gặp gián đoạn kéo dài.
- Sự cố vật lý, thiên tai hoặc vấn đề vận hành khiến đội ngũ không thể truy cập vùng chính.

**Disaster recovery (DR)** là tập chiến lược, kiến trúc, dữ liệu, quy trình và năng lực tổ chức để khôi phục dịch vụ sau sự cố nghiêm trọng. Mục tiêu không chỉ là khởi động lại máy chủ. Một hệ thống chỉ thật sự được phục hồi khi người dùng có thể thực hiện lại nghiệp vụ quan trọng, dữ liệu đạt mức nhất quán chấp nhận được, quyền truy cập hoạt động, tích hợp cần thiết sẵn sàng và đội vận hành có thể giám sát trạng thái mới.

### 1.1. Phân biệt high availability, backup và disaster recovery

| Khái niệm | Mục tiêu | Ví dụ | Giới hạn |
|---|---|---|---|
| **High availability (HA)** | Giảm gián đoạn trong miền lỗi dự kiến | Nhiều instance/zone, managed DB failover | Không tự giải quyết lỗi toàn region hoặc dữ liệu bị xóa logic |
| **Backup** | Có bản sao dữ liệu/cấu hình để khôi phục | Snapshot, point-in-time recovery, object versioning | Có backup không chứng minh restore được hoặc restore đủ nhanh |
| **Disaster recovery** | Khôi phục dịch vụ và dữ liệu sau thảm họa | Restore sang region khác, warm standby, active-active | Cần quy trình, quyết định, quyền, dữ liệu và kiểm thử đầu cuối |
| **Business continuity** | Duy trì hoạt động kinh doanh trong và sau sự cố | Quy trình thủ công tạm thời, kênh liên lạc dự phòng | Rộng hơn công nghệ; gồm con người, nhà cung cấp và nghiệp vụ |

HA và DR bổ trợ nhau. Multi-AZ có thể xử lý một số lỗi hạ tầng cục bộ nhưng không nhất thiết bảo vệ trước lỗi cấu hình được triển khai đồng thời tới mọi zone. Backup bảo vệ khả năng khôi phục dữ liệu ở một mốc, nhưng không nhất thiết cung cấp endpoint đang sẵn sàng nhận traffic. Kế hoạch DR cần nói rõ phạm vi của từng cơ chế.

### 1.2. Phạm vi “phục hồi hệ thống”

Một workload gồm nhiều thành phần và dependency:

- Compute, container image, VM template, serverless function và cấu hình runtime.
- Database, object storage, file system, cache và search index.
- Queue, broker, event subscription, scheduler và background worker.
- Network, DNS, certificate, firewall, private endpoint và routing.
- IAM, workload identity, KMS key, secret, policy và audit log.
- CI/CD, source repository, artifact registry, IaC state và configuration registry.
- Monitoring, logging, alerting, tracing, on-call và incident communication.
- Hệ thống bên ngoài như thanh toán, email/SMS, identity provider và đối tác.

Chỉ phục hồi database mà thiếu encryption key hoặc danh tính có quyền đọc dữ liệu thì dịch vụ chưa thể hoạt động. Chỉ dựng compute mà thiếu queue offsets hoặc schema tương thích có thể tạo giao dịch trùng hoặc mất event. Phải có dependency map và thứ tự phục hồi.

## 2. RTO và RPO: bắt đầu từ yêu cầu kinh doanh

### 2.1. Recovery Time Objective (RTO)

**RTO** là mục tiêu thời gian tối đa mà tổ chức đặt ra để khôi phục một dịch vụ hoặc năng lực nghiệp vụ sau gián đoạn, theo định nghĩa và điểm đo đã thống nhất.

Ví dụ: Booking API phải phục hồi khả năng nhận và xác nhận booking trong vòng 2 giờ kể từ lúc incident commander tuyên bố DR. Muốn RTO có ý nghĩa, cần định nghĩa:

- Đồng hồ bắt đầu khi phát hiện lỗi, khi xác nhận incident hay khi chính thức kích hoạt DR?
- Điểm kết thúc là endpoint trả 200, traffic đã chuyển, giao dịch nghiệp vụ đã được xác nhận hay toàn bộ backlog đã xử lý?
- Phạm vi là API cốt lõi, hệ thống đầy đủ hay mọi tenant/tính năng?
- RTO áp dụng ở tải nào và trong region/điều kiện nào?

RTO không chỉ là thời gian chạy lệnh failover. Nó có thể gồm phát hiện, quyết định, cấp quyền, provision, restore dữ liệu, kiểm tra consistency, chuyển routing, warm-up và xác nhận nghiệp vụ.

### 2.2. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa được chấp nhận, thường được diễn đạt dưới dạng khoảng thời gian dữ liệu phát sinh có thể không còn trong bản phục hồi sau sự cố.

Ví dụ RPO 15 phút nghĩa là tổ chức chấp nhận khả năng mất tối đa 15 phút dữ liệu theo mốc được định nghĩa. Điều đó không có nghĩa mọi bản backup phải chạy đúng mỗi 15 phút: còn phụ thuộc replication lag, log retention, thời điểm sự cố, tính nhất quán và cách restore.

Đối với replication bất đồng bộ, RPO thực tế có thể lớn hơn 0 do dữ liệu đã commit ở primary nhưng chưa đến replica khi mất vùng. Với replication đồng bộ, RPO có thể gần 0 cho một số lỗi và điều kiện cụ thể, nhưng có thể đổi lấy latency và availability khi liên vùng bị phân đoạn mạng. Không có cam kết “RPO bằng 0” chỉ vì dịch vụ có replica.

### 2.3. Ví dụ phân loại dịch vụ

| Năng lực nghiệp vụ | RTO mục tiêu (giả định) | RPO mục tiêu (giả định) | Lý do |
|---|---:|---:|---|
| Tạo và xác nhận booking | 1 giờ | 1 phút | Giao dịch ảnh hưởng trực tiếp khách hàng |
| Tra cứu lịch đã đặt | 2 giờ | 15 phút | Có thể tạm giảm cấp, nhưng dữ liệu cần đúng |
| Báo cáo phân tích | 24 giờ | 24 giờ | Có thể tái tạo từ dữ liệu nguồn |
| Email thông báo | 4 giờ | 1 giờ | Có thể xử lý backlog sau khi phục hồi |
| Cổng quản trị nội bộ | 8 giờ | 4 giờ | Có quy trình hỗ trợ tạm thời khác |

Các con số trên chỉ là ví dụ để luyện phân tích. RTO/RPO thật phải được owner nghiệp vụ, risk/compliance, kiến trúc và vận hành phê duyệt theo BIA (Business Impact Analysis), chi phí và nghĩa vụ hợp đồng.

### 2.4. RTO/RPO phải có cách đo

~~~text
RTO_measured =
  time(service meets agreed recovery criteria)
  - time(disaster declaration / agreed start event)

RPO_measured =
  time(last recoverable consistent business state)
  - time(disaster event / agreed reference point)
~~~

Trong diễn tập, lưu các mốc: phát hiện, tuyên bố DR, quyền được cấp, tài nguyên sẵn sàng, restore/replication hoàn tất, data validation, traffic cutover và giao dịch smoke test thành công. Với RPO, so sánh checkpoint cuối cùng phục hồi được với log nghiệp vụ/commit marker tại nguồn. Nếu không ghi mốc và dữ liệu đối chiếu, tổ chức không thể biết mục tiêu có đạt hay không.

## 3. Bốn chiến lược DR thường gặp

### 3.1. Backup–restore

Ở mô hình **backup–restore**, region hoặc môi trường dự phòng không giữ sẵn toàn bộ workload chạy. Khi có thảm họa, đội vận hành khởi tạo hạ tầng cần thiết, khôi phục dữ liệu từ backup, cấu hình các dependency và chuyển traffic.

~~~mermaid
flowchart TB
    U[Users] --> DNS[DNS / Global Router]
    DNS --> P[Primary Region]
    P --> APP[Application + Database]
    P --> BK[Backup / Replication to DR Storage]
    BK -.-> DR[(Protected backup in recovery region)]
    DR -. restore on disaster .-> R[Recovery Region]
    R --> RAPP[Provisioned Application]
    RAPP --> RDB[(Restored Database)]
    DNS -. cutover after validation .-> RAPP
~~~

**Ưu điểm:**

- Chi phí nền thấp hơn vì compute/database dự phòng không phải luôn chạy ở quy mô production.
- Dễ bắt đầu khi RTO cho phép vài giờ hoặc lâu hơn.
- Có thể tạo bản phục hồi trong tài khoản/region tách biệt; backup bất biến giúp phòng thao tác xóa hoặc ransomware.
- Phù hợp dữ liệu có thể khôi phục từ backup hoặc tái tạo từ hệ thống nguồn.

**Đánh đổi:**

- RTO gồm thời gian provision, restore và kiểm thử, thường cao hơn các chiến lược có workload sẵn.
- Cần bảo đảm quota, artifact, IaC, secret, KMS key và quyền ở vùng phục hồi.
- Backup có thể bị hỏng, không nhất quán hoặc quá cũ; cần restore test.
- Dữ liệu tạo sau mốc backup có thể mất theo RPO, trừ khi có log/PITR/replication bổ sung.

Backup–restore không đồng nghĩa “copy snapshot rồi bật app”. Cần kế hoạch khôi phục thứ tự dependency, migration schema, endpoint, chứng chỉ, queue, worker và các tích hợp bên ngoài.

### 3.2. Pilot light

**Pilot light** duy trì một phần tối thiểu của hệ thống ở vùng phục hồi, thường là các thành phần dữ liệu/metadata hoặc hạ tầng thiết yếu được replication/cấu hình sẵn. Compute ứng dụng chính được provision hoặc scale lên khi kích hoạt DR.

~~~mermaid
flowchart TB
    U[Users] --> G[Global Router]
    G --> P[Primary Region: Full Stack]
    subgraph DR[Recovery Region: Pilot Light]
        DATA[(Replicated / standby data)]
        BASE[Network / IAM / Keys / Minimal Services]
        TEMPLATE[Versioned IaC + Artifacts]
        DATA --- BASE
        BASE --- TEMPLATE
    end
    P -. asynchronous replication .-> DATA
    G -. after compute scale-up and validation .-> APP[Recovery Application Fleet]
    DATA --> APP
    BASE --> APP
~~~

**Ưu điểm:** giảm thời gian chuẩn bị vì network, identity, key, dữ liệu hoặc một số dịch vụ cốt lõi đã tồn tại; chi phí thường thấp hơn warm standby/active-active.

**Đánh đổi:** cần tự động hóa scale/provision và phụ thuộc vào tốc độ khởi tạo, quota, image, cấu hình và kiểm thử. Nếu chỉ có database replica mà chưa có pipeline, DNS, secret hay quyền, RTO vẫn có thể dài.

Pilot light phù hợp khi muốn giảm RTO so với backup–restore nhưng không cần compute toàn bộ chạy liên tục. Cần định nghĩa rõ “pilot” gồm thành phần nào; một replica dữ liệu không tự động biến kiến trúc thành pilot light có thể phục hồi.

### 3.3. Warm standby

**Warm standby** duy trì một phiên bản nhỏ hơn nhưng hoạt động của workload tại vùng phục hồi. Dữ liệu được replication hoặc đồng bộ theo chiến lược; khi primary lỗi, standby được scale lên, kiểm tra và nhận traffic.

~~~mermaid
flowchart TB
    U[Users] --> G[Global Router]
    G --> P[Primary Region: Full Capacity]
    G -. failover .-> S
    subgraph Primary[Primary]
        P --> PA[Application Fleet]
        PA --> PD[(Primary Database)]
    end
    subgraph Standby[Warm Standby]
        S[Standby Endpoint] --> SA[Small Application Fleet]
        SA --> SD[(Replicated Standby Database)]
    end
    PD -. replication .-> SD
~~~

**Ưu điểm:** ứng dụng đã chạy và dependency được kiểm chứng thường xuyên; RTO thấp hơn backup–restore/pilot light nếu dữ liệu và routing sẵn sàng; có thể phục vụ một phần traffic thử nghiệm hoặc đọc theo policy.

**Đánh đổi:** chi phí compute và database standby liên tục; cần duy trì version parity, replication, capacity scale-up và tránh standby bị bỏ quên. Nếu standby nhỏ hơn nhiều, scale-up có thể mất thời gian hoặc không đạt tải production ngay.

Warm standby là lựa chọn thực tế cho workload có RTO từ vài phút đến dưới một giờ tùy hệ thống, nhưng không có thời gian chuẩn chung. Chỉ phép diễn tập mới xác nhận được RTO thật.

### 3.4. Active–active

Trong mô hình **active–active**, nhiều region/site cùng nhận và xử lý traffic bình thường. Khi một vùng lỗi, vùng còn lại tiếp tục phục vụ hoặc tăng capacity. Dữ liệu phải được thiết kế để xử lý ghi đồng thời hoặc phân vùng ownership rõ.

~~~mermaid
flowchart TB
    U[Global Users] --> G[Global Traffic Manager]
    G --> A[Region A: Active]
    G --> B[Region B: Active]
    subgraph RA[Region A]
        A --> AA[App + Workers]
        AA --> AD[(Region A Data)]
    end
    subgraph RB[Region B]
        B --> BA[App + Workers]
        BA --> BD[(Region B Data)]
    end
    AD <-->|Replication / conflict policy| BD
~~~

**Ưu điểm:**

- Có nhiều vùng đang phục vụ, giảm thời gian chuyển đổi compute/routing khi một vùng lỗi.
- Có thể giảm latency địa lý và tăng tổng throughput.
- Tận dụng capacity dự phòng ngay cả khi không có sự cố.

**Đánh đổi:**

- Chi phí cao vì nhiều vùng chạy workload và thường cần dữ liệu được đồng bộ liên tục.
- Xử lý xung đột ghi, consistency, ordering, duplicate và retry khó hơn.
- Một region mất có thể làm tăng gấp đôi tải ở region còn lại; cần headroom.
- Release, schema và policy phải tương thích giữa các phiên bản đang hoạt động.
- Correlated failure do shared identity, control plane, DNS, broker hoặc lỗi logic vẫn có thể tác động tất cả region.

Active–active không bảo đảm RPO=0. Nếu replication bất đồng bộ, một vùng có thể mất dữ liệu đã commit ở vùng khác nhưng chưa nhận được. Nếu replication đồng bộ xuyên vùng, latency ghi và hành vi khi network partition cần được đánh giá cẩn thận. Cần biết rõ nơi quyết định dữ liệu đúng và cách giải quyết conflict.

## 4. So sánh chiến lược và chọn theo mục tiêu

### 4.1. Bảng so sánh định tính

| Tiêu chí | Backup–restore | Pilot light | Warm standby | Active–active |
|---|---|---|---|---|
| Compute tại vùng DR | Chưa chạy hoặc rất ít | Tối thiểu | Chạy ở quy mô nhỏ | Chạy production ở nhiều vùng |
| Dữ liệu | Backup/PITR; có thể thêm log replication | Thường replication cho dữ liệu thiết yếu | Replication/standby thường xuyên | Đồng bộ/replication liên tục theo mô hình |
| RTO tương đối | Cao nhất | Trung bình-cao | Thấp hơn | Có thể thấp nhất về routing/compute |
| RPO tương đối | Phụ thuộc lịch backup/PITR | Phụ thuộc replication/log | Phụ thuộc replication | Phụ thuộc semantics đồng bộ dữ liệu |
| Chi phí nền | Thấp | Thấp–trung bình | Trung bình–cao | Cao |
| Độ phức tạp vận hành | Restore/runbook | Automation scale và bootstrap | Parity, replication, scale-up | Data conflict, routing, multi-region operation |
| Rủi ro bỏ quên | Backup không restore được | Hạ tầng pilot không đủ để mở rộng | Standby lệch version/không đủ capacity | Split-brain và correlated failure |

Các nhãn RTO/RPO là tương đối, không phải SLA đảm bảo. Một backup–restore có automation rất tốt có thể nhanh hơn pilot light được cấu hình sơ sài; một warm standby bị replica lag lớn có thể phục hồi dữ liệu kém hơn backup/PITR đúng mốc.

### 4.2. Ma trận quyết định tham khảo

| Ràng buộc | Chiến lược có thể phù hợp | Câu hỏi cần xác minh |
|---|---|---|
| RTO nhiều giờ, RPO vài giờ, nhạy chi phí | Backup–restore | Restore volume lớn mất bao lâu? |
| RTO khoảng một đến vài giờ, muốn giảm bootstrap | Pilot light | Provision compute và validate mất bao lâu? |
| RTO vài phút đến dưới một giờ, cần môi trường chạy sẵn | Warm standby | Standby scale lên tải production trong bao lâu? |
| RTO rất thấp, phục vụ đa địa lý liên tục | Active–active | Data conflict, consistency, failover tải và chi phí? |
| Dữ liệu có thể tái tạo, compute stateless | Backup artifact/config + recreate | Nguồn dữ liệu chuẩn có thực sự độc lập? |
| Workload có giao dịch ghi toàn cầu, không chấp nhận conflict | Có thể chọn active-passive với writer duy nhất | Promotion, fencing và failover có đạt RTO/RPO? |

### 4.3. Không bắt buộc một chiến lược cho cả hệ thống

Một sản phẩm có thể dùng:

- Booking database: warm standby hoặc database cross-region recovery với mục tiêu RPO/RTO chặt.
- Analytics warehouse: backup–restore hoặc tái tạo dữ liệu từ raw lake.
- Image/file storage: replication hoặc backup theo retention.
- API compute: pilot light hoặc scale-from-zero nếu container/image/config sẵn.
- Notification worker: queue replication hoặc replay từ event log/outbox, với deduplication.
- Admin console: backup–restore nếu nghiệp vụ chấp nhận thời gian dài hơn.

Chiến lược nên phân theo **business capability và data criticality**. Nếu toàn hệ thống dùng cùng chiến lược đắt nhất, chi phí có thể lãng phí; nếu mọi thành phần dùng chiến lược rẻ nhất, nghiệp vụ cốt lõi có thể không đạt RTO/RPO.

## 5. Backup: thiết kế khả năng khôi phục, không chỉ tạo bản sao

### 5.1. Các dạng backup

| Dạng | Mô tả | Phù hợp |
|---|---|---|
| Full backup/snapshot | Ảnh chụp đầy đủ theo cơ chế dịch vụ | Mốc phục hồi, clone/restore |
| Incremental backup | Chỉ lưu phần thay đổi kể từ mốc trước | Giảm thời gian và dung lượng so với full lặp lại |
| Point-in-time recovery (PITR) | Khôi phục tới thời điểm trong cửa sổ log còn giữ | Khôi phục sau thao tác xóa/sửa nhầm |
| Transaction log/WAL backup | Lưu log thay đổi để phục hồi tới mốc | Database cần RPO thấp hơn lịch full backup |
| Object versioning | Giữ nhiều phiên bản object | Khôi phục tệp bị ghi đè/xóa theo khả năng dịch vụ |
| Immutable/offline backup | Bản sao có khóa xóa/retention hoặc tách khỏi môi trường nguồn | Phòng xóa nhầm, chiếm quyền và ransomware |

Không phải mọi loại database hoặc object storage hỗ trợ cùng cơ chế; tên tính năng và giới hạn phụ thuộc provider, tier, engine và region. Phải xác nhận backup được lưu ở failure domain/credential boundary phù hợp, có encryption key khôi phục được và không bị xóa cùng tài khoản nguồn.

### 5.2. Quy tắc bảo vệ bản backup

- **Tách quyền:** tài khoản vận hành ứng dụng không mặc nhiên có quyền xóa mọi bản backup.
- **Tách miền lỗi:** lưu bản sao ở region/account/project hoặc vault riêng theo threat model.
- **Immutable/retention lock:** dùng khi cần bảo vệ trước thao tác xóa có chủ đích; hiểu thời hạn khóa và quy trình ngoại lệ.
- **Mã hóa và key recovery:** bảo vệ backup bằng key nhưng phải có quy trình khôi phục key, quyền decrypt và kiểm soát break-glass.
- **Catalog và inventory:** biết backup thuộc database/dataset nào, thời điểm, loại, key, retention và trạng thái kiểm tra.
- **Giám sát:** cảnh báo backup thất bại, thiếu coverage, bất thường về dung lượng hoặc xóa policy.
- **Kiểm tra restore:** định kỳ khôi phục vào môi trường cô lập và xác nhận dữ liệu/ứng dụng.

Một bản backup mã hóa bằng KMS key đã mất hoặc bị vô hiệu hóa vĩnh viễn có thể không dùng được. Backup copy riêng nhưng không giữ metadata, schema, log hoặc tài liệu để đọc cũng có thể không đáp ứng mục tiêu phục hồi.

### 5.3. Backup consistency

Backup phải đại diện cho trạng thái dữ liệu có thể sử dụng. Snapshot của một database có thể nhất quán theo cơ chế database, nhưng backup đồng thời database, object storage và queue không tự thành một transaction phân tán.

Ví dụ booking ghi vào database rồi phát event và lưu tệp đính kèm:

- Database snapshot có booking mới.
- Object storage backup chưa có tệp đính kèm đó.
- Event backup có thể chứa hoặc thiếu message liên quan.

Khi restore, ứng dụng có thể thấy tham chiếu tới tệp không tồn tại hoặc gửi notification trùng. Cần xác định consistency boundary: transaction/outbox, checkpoint, manifest, event version, object version và quy trình reconciliation.

### 5.4. Retention và lịch backup

Thiết kế retention theo:

- RPO và loại dữ liệu.
- Nghĩa vụ pháp lý/hợp đồng và legal hold.
- Khả năng phát hiện corruption muộn; cần giữ mốc lịch sử đủ lâu.
- Dung lượng/chi phí và lớp lưu trữ.
- Khả năng phục hồi trong cửa sổ backup chain/log.
- Chính sách xóa dữ liệu cá nhân và bản sao dẫn xuất.

Lưu backup 35 ngày không có nghĩa dữ liệu chỉ có thể mất tối đa 35 ngày; RPO phụ thuộc tần suất/log replication. Ngược lại, backup mỗi giờ nhưng chỉ giữ 2 giờ có thể không đủ phục hồi khi phát hiện corruption sau nhiều ngày. Phải chọn lịch và retention cùng nhau.

## 6. Restore và kiểm chứng dữ liệu

### 6.1. Quy trình restore tham chiếu

1. Xác định incident, phạm vi ảnh hưởng, mốc dữ liệu sạch cuối cùng và business owner.
2. Chọn chiến lược phục hồi và nơi restore; cô lập khỏi hệ thống hỏng.
3. Xác minh backup ID, thời gian, checksum/manifest, encryption key, schema và quyền.
4. Provision network, storage, compute và identity cần thiết.
5. Restore database/object/table theo thứ tự dependency; áp log/PITR nếu cần.
6. Chạy integrity check, count/sum reconciliation, kiểm tra quan hệ và dữ liệu nghiệp vụ.
7. Khởi động consumer/job có kiểm soát; deduplicate hoặc replay message theo policy.
8. Smoke test các luồng nghiệp vụ và bảo mật; xác nhận không gọi nhầm endpoint production cũ.
9. Cập nhật routing sau phê duyệt; quan sát SLI và backlog.
10. Lưu kết quả, thời gian, RPO/RTO thực tế và các sai lệch.

### 6.2. Không nhầm “restore thành công” với “dịch vụ phục hồi”

| Lớp kiểm tra | Ví dụ bằng chứng |
|---|---|
| Backup artifact | ID, timestamp, checksum, encryption/key metadata |
| Database | Instance online, schema đúng, integrity/constraints hợp lệ |
| Dữ liệu | Record count, key range, reconciliation, last committed marker |
| Ứng dụng | Health/readiness, startup, connection và secret hoạt động |
| Nghiệp vụ | Tạo/tra cứu/hủy booking thử theo policy, không tạo dữ liệu thật ngoài ý muốn |
| Tích hợp | Queue, event, payment sandbox/provider policy, callback |
| Bảo mật | IAM/tenant access, audit, network boundary và encryption |
| Vận hành | Dashboard, alert, runbook và on-call route hoạt động |

Restore test nên dùng dữ liệu và quy mô gần production; một database 1 GB phục hồi nhanh không chứng minh database 20 TB đạt RTO.

### 6.3. Clean-room recovery

Nếu thảm họa là tài khoản bị chiếm quyền hoặc ransomware, restore trong cùng môi trường có thể khôi phục luôn malware, credential bị lộ hoặc cấu hình độc hại. **Clean-room recovery** dựng môi trường phục hồi được cô lập, dùng artifact/baseline đã xác minh, credential mới và backup bất biến đã kiểm tra.

Các bước cần xét:

- Tạo account/project và network từ nguồn IaC tin cậy.
- Xác minh image/container artifact, dependency và pipeline.
- Xoay secret/key/token có nguy cơ bị lộ; thu hồi credential cũ.
- Khôi phục dữ liệu từ mốc sạch trước sự cố, quét malware/corruption theo quy trình.
- Chỉ cho phép kết nối tới dependency cần thiết; giới hạn egress.
- Kiểm thử và xác nhận bảo mật trước khi mở traffic.

Clean-room recovery có thể tăng RTO nhưng giảm nguy cơ tái nhiễm hoặc tái sử dụng cấu hình bị xâm nhập. Đây là yêu cầu cần cân nhắc riêng cho threat model, không phải bước thay thế cho mọi loại mất zone.

## 7. Replication, consistency và thứ tự ghi

### 7.1. Đồng bộ và bất đồng bộ

| Cơ chế | Hành vi | Lợi ích | Đánh đổi |
|---|---|---|---|
| Synchronous replication | Commit chờ điều kiện xác nhận từ replica theo semantics hệ quản trị | Có thể giảm mất dữ liệu với một số failure model | Tăng latency, phụ thuộc network; có thể ảnh hưởng availability |
| Asynchronous replication | Primary commit trước, replica nhận sau | Giảm latency commit và chịu network delay tốt hơn | Replica lag, RPO lớn hơn 0 |
| Semi-synchronous/quorum | Chờ một tập xác nhận hoặc điều kiện trung gian | Cân bằng tùy engine/triển khai | Semantics phức tạp; phải đọc chính xác cam kết của dịch vụ |
| Log shipping | Chuyển transaction log để apply ở nơi khác | Có thể đạt RPO nhỏ và giữ mốc log | Lag/apply rate và quy trình promotion |
| Snapshot replication | Sao chép theo mốc dữ liệu | Đơn giản cho một số dataset | Độ trễ và lượng thay đổi mất kể từ snapshot |

Không suy ra mức RPO chỉ từ từ “synchronous” hoặc “cross-region”. Cần đọc failure model: primary có xác nhận commit khi nào, bao nhiêu replica phải ack, xử lý network partition ra sao, transaction nào được bảo vệ và cách failover chọn node.

### 7.2. Replica lag

**Replica lag** là độ trễ giữa thay đổi ở nguồn và thời điểm replica có thể phục vụ thay đổi đó. Có thể đo theo thời gian, log position, byte/transaction backlog hoặc chỉ số do database cung cấp.

Lag tăng có thể do network, throughput, workload, apply conflict, storage chậm hoặc replica không đủ tài nguyên. Trong DR, lag trực tiếp ảnh hưởng RPO và tính đúng đắn khi promotion.

Ví dụ:

~~~text
Primary last committed marker: 12:00:00
Standby last applied marker:   11:59:42
Observed lag:                  18 seconds
~~~

Nếu primary mất ngay lúc 12:00, standby có thể thiếu giao dịch trong khoảng lag, tùy cơ chế và commit semantics. Không dùng giá trị lag từ một thời điểm trước sự cố làm bằng chứng tuyệt đối; cần theo dõi liên tục và đối chiếu marker cuối cùng khi promotion.

### 7.3. Split-brain và fencing

**Split-brain** xảy ra khi hai vùng cùng tin mình là primary/leader và cùng nhận ghi. Khi kết nối bị chia cắt, việc mỗi bên tự promote có thể tạo hai lịch sử dữ liệu khác nhau.

Biện pháp:

- Có một cơ chế quyết định quyền writer/leader rõ ràng.
- Dùng quorum/lease/epoch hoặc fencing token theo khả năng nền tảng để chặn writer cũ.
- Không chỉ dựa vào DNS đổi hướng; kết nối cũ có thể còn hoạt động.
- Chỉ promote standby khi primary đã được xác định không còn quyền ghi hoặc có biện pháp cô lập.
- Ghi lại generation/epoch để request/worker cũ không tiếp tục ghi sau chuyển vai trò.
- Có runbook cho tình huống không xác định được primary; ưu tiên an toàn dữ liệu hơn tự động tạo hai writer.

Fencing là điều kiện quan trọng trong nhiều mô hình active-passive và failover database. Việc thực hiện cụ thể khác nhau theo database/cloud service; DNS, load balancer hay trạng thái health không tự cung cấp fencing.

### 7.4. Active–active và giải quyết conflict

Nếu hai region cùng ghi dữ liệu, cần chọn một chiến lược:

- **Partitioned ownership:** một tenant/entity chỉ có một region làm writer tại một thời điểm.
- **Single-writer, multi-reader:** nhiều vùng đọc nhưng chỉ một nơi ghi chuẩn.
- **Conflict-free/CRDT hoặc merge logic:** chỉ dùng khi mô hình dữ liệu và nghiệp vụ hỗ trợ phép hợp nhất có ý nghĩa.
- **Optimistic conflict detection:** lưu version/ETag và yêu cầu client giải quyết conflict.
- **Application-level reconciliation:** phát hiện hai cập nhật cạnh tranh và xử lý theo quy tắc nghiệp vụ.

Không giải quyết conflict bằng timestamp “cái mới hơn thắng” một cách mặc định. Đồng hồ các vùng có thể lệch; cập nhật sau về thời gian không nhất thiết đúng hơn về nghiệp vụ. Với booking độc quyền, hai region xác nhận cùng slot rồi merge bằng last-write-wins có thể vi phạm invariant.

## 8. Thiết kế failover và failback

### 8.1. Failover là một quy trình có cổng kiểm tra

Failover chuyển khả năng phục vụ từ môi trường primary sang recovery site/region. Một quy trình an toàn cần:

1. Phát hiện và xác nhận sự cố vượt phạm vi HA.
2. Xác định mức độ ảnh hưởng, dữ liệu và dependency liên quan.
3. Người có quyền tuyên bố DR/incident commander kích hoạt runbook.
4. Fence hoặc cô lập writer/traffic ở nguồn theo thiết kế.
5. Xác định mốc dữ liệu cuối và quyết định RPO thực tế có được chấp nhận không.
6. Promote/restore database và dependency.
7. Khởi động/scale ứng dụng, worker và integration.
8. Chạy integrity, security và business smoke tests.
9. Chuyển global routing/DNS/traffic theo policy.
10. Thông báo trạng thái và theo dõi SLI/capacity ở vùng mới.

Không tự động failover toàn region chỉ vì một health probe lỗi. Probe có thể false positive hoặc chỉ kiểm tra endpoint ứng dụng mà không phản ánh dữ liệu. Cần nhiều tín hiệu và quyết định tương xứng với tác động.

### 8.2. Sơ đồ failover active-passive

~~~mermaid
sequenceDiagram
    participant Mon as Monitoring
    participant IC as Incident Commander
    participant Prim as Primary Region
    participant DR as Recovery Region
    participant GTM as Global Traffic Manager
    Mon->>IC: Region outage / SLI breach
    IC->>IC: Confirm DR criteria and declare
    IC->>Prim: Fence old writer / isolate if reachable
    IC->>DR: Verify replica or restore point
    DR-->>IC: Data point, lag and readiness evidence
    IC->>DR: Promote writer / start workloads
    DR-->>IC: Integrity + business smoke tests pass
    IC->>GTM: Approve traffic cutover
    GTM-->>DR: Route new traffic
    IC->>Mon: Observe SLI, errors and capacity
~~~

Nếu primary không thể truy cập để fence, cần cơ chế quorum/lease hoặc bằng chứng authoritative khác. Tuyên bố primary đã chết chỉ dựa vào timeout từ một client không đủ để bảo đảm primary không còn nhận ghi từ client khác.

### 8.3. DNS và global routing

Global traffic manager có thể dùng health check, weighted/priority routing, latency/geography hoặc failover policy. DNS-based failover cần lưu ý:

- Resolver/client cache DNS theo TTL hoặc chính sách riêng.
- Kết nối dài/connection pool có thể tiếp tục dùng endpoint cũ.
- DNS update không bảo đảm mọi client chuyển ngay.
- Health check cần kiểm tra endpoint và readiness phù hợp; routing layer không xác thực consistency dữ liệu.
- Khi cutover, chứng chỉ, CORS, callback URL, allowlist và external webhook có thể cần cập nhật.

Kế hoạch nên đo thời gian hội tụ của resolver/client thực tế và có cơ chế retry/reconnect. Không cam kết failover “tức thì” chỉ vì đặt TTL rất thấp.

### 8.4. Failback

Failback là chuyển dịch vụ về site/region ban đầu hoặc một primary mới sau khi sự cố đã được khắc phục. Đây là một thay đổi dữ liệu và routing có rủi ro tương tự migration:

1. Điều tra nguyên nhân primary cũ; xác nhận không còn lỗi gốc.
2. Giữ một writer duy nhất ở vùng hiện đang hoạt động.
3. Đồng bộ/đối soát dữ liệu về nơi dự kiến trở lại.
4. Xác minh replica lag, schema và key/version tương thích.
5. Fence vai trò writer cũ; xác định thời điểm promotion mới.
6. Test ở traffic thấp hoặc môi trường staging; kiểm tra routing và tích hợp.
7. Chuyển traffic có kiểm soát, quan sát SLI và rollback criteria.
8. Chỉ scale down vùng đang phục vụ sau khi xác nhận hệ thống ổn định.

Không failback chỉ vì primary cũ đã xanh. Nếu dữ liệu phát sinh ở DR region, đổi route về mà không sync có thể làm mất toàn bộ giao dịch trong thời gian thảm họa.

## 9. Recovery dependency và thứ tự khôi phục

### 9.1. Dependency map

Với mỗi thành phần, ghi:

| Thành phần | Phụ thuộc cần phục hồi | Câu hỏi |
|---|---|---|
| Network/VPC/subnet | CIDR, route, private endpoint, firewall, DNS | Có xung đột CIDR hoặc route tới vùng cũ không? |
| Identity/IAM | Workload role, federated identity, admin access | Ai có thể cấp quyền khi IdP chính lỗi? |
| KMS/secrets | Key replica, decrypt permission, secret version | Có thể giải mã backup và khởi động app? |
| Database | Backup/log/replica, schema, endpoint | Mốc dữ liệu nào được chọn và ai promote? |
| Object storage | Object version, replication, lifecycle | Có đủ object, metadata và quyền? |
| Queue/event | Topic, subscription, offset, retention, DLQ | Có message thiếu/lặp và cách replay nào? |
| Compute | Image, artifact, config, quota | Version có tái tạo được và quota đủ? |
| DNS/certificate | Domain, record, TLS cert, external allowlist | Client/đối tác có kết nối được? |
| Observability | Dashboard, alert, logs, tracing, on-call | Có thể giám sát site DR từ bên ngoài? |
| External providers | Payment, email, identity, webhook | Endpoint/credential/allowlist có tương ứng vùng mới? |

### 9.2. Recovery order

Một thứ tự thường dùng:

~~~mermaid
flowchart TD
    A[Declare DR / isolate incident] --> B[Recover access, account and keys]
    B --> C[Network, DNS prerequisites and security boundary]
    C --> D[Restore / promote data services]
    D --> E[Validate consistency and data integrity]
    E --> F[Start compute and application dependencies]
    F --> G[Start workers, schedules and integrations carefully]
    G --> H[Business smoke tests and security checks]
    H --> I[Traffic cutover]
    I --> J[Monitor, reconcile and stabilize]
~~~

Đây là thứ tự logic, không phải runbook chung áp dụng nguyên xi. Có thể cần khởi động một số control service trước database; queue worker thường nên giữ dừng cho đến khi xác định offset/dedup và trạng thái dữ liệu. DNS chuẩn bị sớm nhưng chỉ cutover sau validation.

### 9.3. Ưu tiên phục hồi theo nghiệp vụ

Không nhất thiết phục hồi mọi tính năng cùng lúc. Xác định:

- **Minimum viable service:** các luồng tối thiểu cần có để doanh nghiệp tiếp tục hoạt động.
- **Tier 0 dependencies:** identity, network, keys, DNS hoặc control plane cần có trước.
- **Tier 1 workload:** giao dịch cốt lõi và dữ liệu chuẩn.
- **Tier 2 workload:** tra cứu, thông báo, hỗ trợ vận hành.
- **Tier 3 workload:** báo cáo, phân tích, tác vụ nền có thể trì hoãn.

Thứ tự phải tránh làm sai dữ liệu. Ví dụ booking API có thể mở trước khi email worker phục hồi nếu outbox/event lưu bền và backlog được kiểm soát. Tuy nhiên, không mở write nếu dữ liệu booking chưa được promote đúng.

## 10. Bảo mật trong disaster recovery

### 10.1. DR không được làm yếu bảo mật

Áp lực khôi phục nhanh dễ dẫn tới các ngoại lệ nguy hiểm: mở database public, dùng tài khoản admin chung, tắt MFA, bỏ qua tenant authorization hoặc sao chép secret lâu năm. Kế hoạch DR phải định nghĩa quyền khẩn cấp trước sự cố.

Các nguyên tắc:

- Dùng least privilege; tách DR operator, data restore operator và security approver.
- Break-glass có MFA, thời hạn, audit, phê duyệt và quy trình thu hồi sau sự cố.
- Không lưu secret trong backup script, runbook hoặc output log.
- KMS key và quyền decrypt phải có cách phục hồi/replicate được kiểm soát.
- Khóa/certificate/credential được đánh giá có thể đã bị lộ trong incident; cần xoay mới.
- Môi trường restore phải có network segmentation, private access và egress allowlist.
- Audit log và bản backup quan trọng cần chống xóa/chỉnh sửa ngoài quyền kiểm soát ứng dụng.

### 10.2. Ransomware và backup bất biến

Nếu attacker có quyền quản trị production, họ có thể thử xóa snapshot, key, backup vault hoặc bản sao cùng tài khoản. Biện pháp giảm rủi ro:

- Tách backup account/security boundary và giới hạn quyền cross-account.
- Dùng immutable retention hoặc vault lock khi phù hợp.
- Bảo vệ control plane và credential quản trị bằng MFA/approval.
- Theo dõi hành vi xóa hàng loạt, thay đổi retention, disable backup và key policy.
- Diễn tập clean-room restore từ backup đã kiểm chứng, không tin artifact vừa bị incident tác động.

Immutability có thể làm việc xóa hợp pháp hoặc sửa nhầm khó hơn trong thời hạn khóa; phải thiết kế retention/legal hold và quy trình vận hành phù hợp.

### 10.3. Quyền riêng tư và data residency

Khi copy dữ liệu sang region DR, vẫn phải tuân thủ quy định vị trí dữ liệu, hợp đồng và quyền truy cập. Replication sang region khác không tự được phép vì mục đích DR. Xác định dữ liệu nào được replication, dữ liệu nào phải mã hóa/ẩn danh, ai được truy cập và backup giữ bao lâu.

## 11. Diễn tập và kiểm chứng kế hoạch DR

### 11.1. Tại sao phải diễn tập?

Runbook có thể đúng về mặt tài liệu nhưng thất bại vì:

- Credential hết hạn hoặc người trực không có quyền.
- Quota DR region không đủ hoặc dịch vụ chưa được bật.
- Backup thiếu object, key hoặc log.
- IaC drift hoặc image không còn truy cập.
- DNS/provider webhook vẫn trỏ về endpoint cũ.
- Replica lag cao hơn RPO.
- Restore database chạy lâu hơn dự kiến.
- Dashboard/alert phụ thuộc chính region bị lỗi.

Chỉ **restore test, failover drill và diễn tập có đo** mới xác nhận được năng lực. “Backup job success” không phải tiêu chí đạt DR.

### 11.2. Các cấp độ diễn tập

| Cấp độ | Cách làm | Mục tiêu | Rủi ro |
|---|---|---|---|
| Tabletop | Thảo luận kịch bản, vai trò, quyết định và liên lạc | Phát hiện khoảng trống runbook/quyền | Ít bằng chứng kỹ thuật |
| Backup restore test | Restore bản sao vào môi trường cô lập | Kiểm tra tính sử dụng của backup và thời gian | Tốn compute/storage, có thể ảnh hưởng nguồn nếu làm sai |
| Component failover | Mô phỏng mất database/zone/queue trong test | Kiểm tra từng cơ chế | Có thể ảnh hưởng dependency dùng chung |
| Regional DR drill | Chuyển workload thử sang region dự phòng | Đo RTO/RPO end-to-end | Phức tạp, phải có phạm vi/điều kiện dừng |
| Game day / chaos | Tiêm lỗi có kiểm soát theo giả thuyết | Kiểm tra phản ứng và khả năng tự phục hồi | Chỉ thực hiện khi có guardrail và blast radius rõ |

### 11.3. Kịch bản diễn tập mẫu

**Bối cảnh:** Booking API ở Region A không thể phục vụ; database primary ngừng hoạt động. Region B đang giữ warm standby với replication bất đồng bộ. Mục tiêu giả định RTO 60 phút, RPO 5 phút.

| Bước | Hoạt động | Bằng chứng cần ghi |
|---|---|---|
| 1 | Xác nhận sự cố và declare DR | Timestamp, người quyết định, phạm vi |
| 2 | Kiểm tra standby, replica lag và data marker | Last applied transaction/marker |
| 3 | Fence primary hoặc xác minh cơ chế ngăn ghi kép | Evidence writer cũ không còn nhận ghi |
| 4 | Promote standby | Timestamp, role/generation mới |
| 5 | Kiểm tra schema, số booking, invariant và outbox | Reconciliation report |
| 6 | Khởi động API/worker và secret | Health, IAM, dependency test |
| 7 | Chuyển traffic tới Region B | DNS/GTM convergence, request success |
| 8 | Tạo/tra cứu booking thử trong tenant test | Business smoke test, audit |
| 9 | Theo dõi error, p95, backlog và capacity | Dashboard, alert, queue age |
| 10 | Tính RTO/RPO và ghi lessons learned | Timeline và action owner |

Nếu RTO đo được 78 phút hoặc RPO 9 phút, không sửa báo cáo để “đạt mục tiêu”. Ghi khoảng cách và quyết định: tăng replication, provision sẵn compute, cải thiện automation, đổi mục tiêu đã được business chấp nhận hay đầu tư chiến lược khác.

### 11.4. Tiêu chí thành công

- Người có quyền kích hoạt DR và quyền truy cập thực tế đều sẵn sàng.
- Recovery site có thể được khởi động trong quota và policy đã phê duyệt.
- Dữ liệu đạt RPO và integrity check.
- Writer/leader duy nhất, không có split-brain.
- Luồng nghiệp vụ tối thiểu hoạt động và security control được giữ.
- Traffic đã chuyển và client có thể truy cập trong RTO.
- Monitoring/alert và on-call hoạt động tại recovery site.
- Failback hoặc trạng thái hoạt động lâu dài sau DR có kế hoạch cụ thể.
- Các vấn đề phát hiện có owner, deadline và bằng chứng đóng.

## 12. Ước tính chi phí và tổng chi phí sở hữu

### 12.1. Thành phần chi phí

| Thành phần | Backup–restore | Pilot light | Warm standby | Active–active |
|---|---|---|---|---|
| Compute idle | Thấp | Thấp | Trung bình | Cao |
| Database/replica | Backup/storage, có thể log | Data replica/standby | Standby chạy liên tục | Nhiều node/region active |
| Storage/backup | Trung bình, theo retention | Backup + replication | Backup + replication | Replication và backup đa vùng |
| Network/egress | Khi backup/restore | Liên tục hoặc định kỳ | Replication liên tục | Inter-region traffic liên tục |
| Test/automation | Cần restore drill | Provision/scale drill | Failover/scale-up drill | Conflict/failover/load drills |
| Operations | Ít thành phần chạy, restore phức tạp | Điều phối provision | Giữ parity/lag/capacity | Cao, multi-region và consistency |

### 12.2. Ví dụ định tính

Giả sử database production và ứng dụng có chi phí 10.000 USD/tháng trong một region. Phương án DR không thể tính đơn giản là:

- Backup–restore: “0 USD” vì vẫn có backup storage, transfer, vault, test và nhân lực.
- Pilot light: “10%” vì một số database/replication/key/network và dịch vụ tối thiểu luôn chạy.
- Warm standby: “50%” nếu compute nhỏ nhưng database/replica có thể chiếm phần lớn chi phí.
- Active–active: “100% thêm” chỉ là ước lượng thô; tải chia vùng, data transfer, license, backup và capacity surge làm chi phí thực khác.

Để dự toán thật, dùng provider pricing theo region/discount, storage class, IO, backup retention, inter-region transfer, request, license, monitoring và support. Cộng thêm chi phí diễn tập và năng lực nhân sự duy trì.

### 12.3. Tối ưu chi phí mà không làm mất khả năng phục hồi

- Chọn chiến lược theo tier dữ liệu/workload.
- Dùng compute co giãn trong pilot light/warm standby, nhưng giữ quota và thời gian scale đã đo.
- Dùng lifecycle chuyển backup ít truy cập sang storage phù hợp, sau khi kiểm tra thời gian restore.
- Tránh replication mọi loại dữ liệu nếu dữ liệu có thể tái tạo; nhưng giữ nguồn và bằng chứng đầy đủ.
- Lập lịch restore/drill, có budget và dọn tài nguyên test sau diễn tập.
- Theo dõi chi phí backup/replica/egress theo service owner.
- Không giảm retention hoặc tắt backup tự động chỉ vì tháng hiện tại vượt budget nếu chưa có risk approval.

## 13. Những sai lầm DR thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Có backup nhưng chưa restore thử | Bản sao có thể thiếu, hỏng hoặc không đọc được | Restore drill và integrity check |
| Lấy RPO từ chu kỳ backup mà bỏ qua lag/log | Mất dữ liệu lớn hơn dự kiến | Đo recoverable commit marker/replica lag |
| Chỉ khôi phục DB | API thiếu key, secret, queue, DNS hoặc quyền | Dependency map và end-to-end smoke test |
| Active-passive nhưng cả hai cùng nhận ghi | Split-brain, dữ liệu phân nhánh | Fencing, quorum/lease và một writer |
| DNS TTL thấp được coi là failover tức thì | Client vẫn dùng cache/kết nối cũ | Đo resolver/client convergence |
| Warm standby không được cập nhật | Version/schema/config lệch primary | Drift scan và parity check |
| Standby không đủ capacity | Chuyển traffic xong nhưng hệ thống sập vì quá tải | Load test và headroom sau sự cố |
| Replicate mọi thứ kể cả lỗi logic | Corruption/xóa nhầm lan sang DR | Immutable backup, PITR và clean-room |
| Failback không đồng bộ delta | Mất giao dịch đã tạo tại DR | Reconcile, reverse sync/fix-forward, fencing |
| DR operator thiếu quyền khi incident | Chậm cấp quyền và không thể phục hồi | Break-glass drill, quyền có thời hạn |
| Kế hoạch chỉ do đội hạ tầng sở hữu | Nghiệp vụ không biết mức gián đoạn/mất dữ liệu | Business owner phê duyệt BIA/RTO/RPO |
| Chỉ diễn tập tabletop | Không phát hiện giới hạn quota, tốc độ restore và DNS | Restore/failover test kỹ thuật định kỳ |

## 14. Bài thực hành: chọn và diễn tập DR cho nền tảng đặt lịch

**Tình huống:** Một nền tảng SaaS đặt lịch chạy tại Region A. Thành phần gồm Booking API, relational database, notification queue, object storage chứa tệp, dashboard và analytics warehouse. Có 2 availability zone trong region chính. Tổ chức có thể triển khai tại Region B nhưng cần cân đối chi phí.

Yêu cầu nghiệp vụ giả định:

- Tạo/đọc booking cốt lõi: RTO không quá 60 phút, RPO không quá 5 phút.
- Thông báo email: RTO 4 giờ; có thể gửi chậm nhưng không gửi trùng.
- Analytics: RTO 24 giờ; chấp nhận xây lại từ dữ liệu nguồn.
- Dữ liệu khách hàng cần mã hóa và tuân thủ chính sách region/retention.
- Failover không được để hai region cùng xác nhận một slot.

Hãy hoàn thành các đầu ra:

1. **BIA và dependency map:** phân loại nghiệp vụ, owner, tác động, dependency Tier 0/1/2 và điểm đo RTO/RPO.
2. **So sánh bốn chiến lược:** backup–restore, pilot light, warm standby, active–active; chọn phương án cho từng lớp Booking DB, API, queue, object storage và analytics.
3. **Backup design:** lịch full/incremental/PITR, log retention, immutable vault, region/account, KMS, retention và restore test.
4. **Replication/data consistency:** đo replica lag, xác định writer, fencing, event/outbox, queue replay và deduplication.
5. **Runbook failover:** ai declare, quyền nào, thứ tự restore/promote, data check, smoke test, routing và tiêu chí mở traffic.
6. **Failback:** cách đồng bộ delta, giữ writer duy nhất, cutover và rollback/fix-forward.
7. **Security/clean-room:** cách bảo vệ backup, xoay credential, network isolation và phục hồi khi tài khoản bị xâm nhập.
8. **DR drill:** tạo timeline giả lập, ghi timestamp, tính RTO/RPO thực đo, xác định gap và action owner.
9. **TCO:** dự toán compute, database standby, storage, replication, egress, backup, test và vận hành.
10. **Well-Architected review:** nêu rủi ro và bằng chứng tương ứng cho từng trụ cột.

### Bảng quyết định mẫu

| Thành phần | Chiến lược đề xuất | Mục tiêu | Kiểm chứng |
|---|---|---|---|
| Booking DB | Warm standby hoặc phương án managed DR tương đương | RPO ≤ 5 phút (giả định) | Replica lag, promotion và consistency |
| Booking API | Pilot light/warm standby tùy RTO | RTO ≤ 60 phút | Provision/scale và business smoke test |
| Notification | Backup queue/outbox + replay có dedup | RTO 4 giờ | Duplicate/replay test |
| Object storage | Cross-region replication + version/immutable backup theo dữ liệu | Theo retention và nghiệp vụ | Object inventory, checksum, restore |
| Analytics | Backup–restore hoặc rebuild từ raw | RTO 24 giờ | Rebuild completeness và report validation |

### Bảng timeline diễn tập

| Mốc | Timestamp | Người chịu trách nhiệm | Bằng chứng |
|---|---|---|---|
| Incident phát hiện | Điền khi diễn tập | Operations | Alert/event |
| Declare DR | Điền khi diễn tập | Incident commander | Decision log |
| Xác nhận RPO/replica | Điền khi diễn tập | DBA/Data owner | Commit marker/lag |
| Writer fencing | Điền khi diễn tập | Database/Platform | Role/epoch evidence |
| Data restore/promotion | Điền khi diễn tập | Data recovery owner | Restore log |
| Business test đạt | Điền khi diễn tập | Product/QA | Kết quả booking test |
| Traffic cutover | Điền khi diễn tập | Network/Platform | DNS/GTM observation |
| Dịch vụ đạt tiêu chí | Điền khi diễn tập | Service owner | SLI và dashboard |

**Tiêu chí hoàn thành:** Một người trực khác có thể dùng tài liệu để quyết định đúng chiến lược, phục hồi đúng thứ tự, chứng minh dữ liệu đạt RPO, đưa nghiệp vụ trở lại trong RTO và thực hiện failback mà không tạo writer kép hoặc mất giao dịch.

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi về DR | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Runbook, quyền, owner, contact và diễn tập có được duy trì? | Tabletop, drill timeline, action tracking, automation |
| **Security** | Backup bất biến, IAM/KMS, clean-room và break-glass có an toàn? | Restore test, access review, audit, key recovery drill |
| **Reliability** | RTO/RPO có đạt, dependency và failover/failback có được kiểm chứng? | Restore/failover/failback exercise, integrity check |
| **Performance Efficiency** | Standby có đủ capacity và scale-up kịp? | Load test, scale time, latency, queue/backlog |
| **Cost Optimization** | Chi phí replication/standby/backup có tương xứng tier nghiệp vụ? | DR TCO, cost allocation, utilization |
| **Sustainability** | Có tránh compute standby dư thừa và retention không cần thiết? | Utilization, lifecycle, backup policy review |

Mô hình DR tốt là lựa chọn có chủ đích giữa mức gián đoạn/mất dữ liệu chấp nhận được và chi phí để giảm hai rủi ro đó. Không phải mọi thành phần đều cần active–active; cũng không thể dùng backup–restore cho một luồng nghiệp vụ có RTO vài phút mà không chứng minh được tốc độ restore và bootstrap.

## 16. Khung ghi nhớ

- **RTO** nói về thời gian phục hồi dịch vụ; **RPO** nói về mức mất dữ liệu có thể chấp nhận. Cả hai phải có điểm bắt đầu/kết thúc và cách đo rõ.
- **Backup–restore** có chi phí nền thấp nhưng RTO thường dài; **pilot light** chuẩn bị sẵn một phần; **warm standby** chạy workload nhỏ; **active–active** phục vụ đồng thời nhưng phức tạp về dữ liệu và vận hành.
- **Backup chưa đủ nếu chưa restore thử.** Cần bảo vệ bản sao, key, metadata, quyền và kiểm chứng dữ liệu/nghiệp vụ.
- **Replication không tự bảo đảm consistency.** Phải hiểu lag, commit semantics, writer, fencing và conflict.
- **Failover gồm dữ liệu, dependency, ứng dụng, routing và người vận hành.** DNS chỉ là một phần của quá trình.
- **Failback là một migration dữ liệu/routing có kiểm soát**, không đơn giản đổi traffic về primary cũ.
- **Diễn tập và đo lường là bằng chứng năng lực DR.** Ghi RTO/RPO thực tế, gap, owner và hạn xử lý.
- **Chọn chiến lược theo từng capability và tier dữ liệu**, không áp một mẫu đắt nhất hoặc rẻ nhất cho toàn hệ thống.

Thiết kế disaster recovery bắt đầu từ mức gián đoạn và mất dữ liệu mà nghiệp vụ có thể chấp nhận, rồi mới chọn backup, replication, pilot light, warm standby hay active–active. Kiến trúc chỉ đáng tin khi vùng phục hồi có đủ dữ liệu, quyền, khóa, compute, network và dependency; quy trình failover/failback đã được diễn tập; và kết quả đo chứng minh hệ thống đạt mục tiêu đã cam kết.
