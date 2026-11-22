# Mục tiêu RPO, RTO và kiến trúc nhiều vùng lỗi trong PostgreSQL

Một hệ thống PostgreSQL có tính sẵn sàng cao cần trả lời hai câu hỏi trước khi chọn topology: **chấp nhận mất tối đa bao nhiêu dữ liệu khi có sự cố, và dịch vụ phải hoạt động trở lại trong bao lâu?** Hai câu trả lời đó được biểu diễn bằng RPO (Recovery Point Objective) và RTO (Recovery Time Objective).

RPO/RTO là mục tiêu kinh doanh và vận hành. Chúng quyết định số bản sao, cách đồng bộ WAL, vị trí standby, chiến lược backup, cơ chế failover, dung lượng dự phòng, quy trình kiểm thử và ngân sách. Một sơ đồ có nhiều PostgreSQL nodes chưa chắc đạt HA nếu các nodes cùng phụ thuộc một storage, một vùng mạng, một hệ thống định danh hoặc một người vận hành có thể xóa tất cả.

Trong bài học này, **vùng lỗi (failure domain)** là một phạm vi mà một sự cố chung có thể làm mất khả năng phục vụ của nhiều thành phần cùng lúc. Kiến trúc nhiều vùng lỗi phải phân tách đủ độc lập để một sự cố trong một vùng không kéo toàn bộ hệ thống xuống, đồng thời vẫn có cách điều phối failover an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa RPO, RTO, RLO, availability và SLO/SLA.
2. Chuyển yêu cầu kinh doanh thành mục tiêu phục hồi có thể đo lường.
3. Phân biệt HA, disaster recovery, backup và business continuity.
4. Nhận diện failure domains từ process, host, rack, availability zone, region tới cloud account/provider.
5. Thiết kế primary/standby PostgreSQL theo synchronous hoặc asynchronous replication.
6. Giải thích trade-off giữa data loss, commit latency và availability.
7. Hiểu quorum, fencing, leader election, split brain và failover safety.
8. Thiết kế topology multi-AZ và multi-region.
9. Kết hợp streaming replication với WAL archive, base backup và PITR.
10. Tính capacity headroom, replication lag và recovery throughput.
11. Xây dựng runbook, monitoring, alerting và restore/failover drills.
12. Đánh giá chi phí, giới hạn và các failure modes của kiến trúc HA.

## 2. RPO là gì?

### 2.1. Định nghĩa

**Recovery Point Objective (RPO)** là lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường đo bằng thời gian từ thời điểm xảy ra sự cố đến recovery point cuối cùng có thể khôi phục.

Ví dụ:

- RPO 0: với các transaction đã được xác nhận commit trong phạm vi failure assumptions, không chấp nhận mất transaction nào.
- RPO 5 phút: chấp nhận khôi phục tới điểm dữ liệu gần nhất cách thời điểm sự cố tối đa 5 phút.
- RPO 1 giờ: tổ chức có thể chấp nhận mất tối đa khoảng một giờ giao dịch.

RPO không có nghĩa “backup chạy mỗi 5 phút”. Backup cadence chỉ là một yếu tố; streaming replication, WAL archive, replication lag, archive latency và failure mode quyết định recovery point thực tế.

### 2.2. Ví dụ tính RPO

Một primary ghi WAL liên tục. Standby asynchronous đã replay WAL tới 10:24:30. Primary gặp sự cố lúc 10:25:00 và không thể lấy WAL chưa được gửi/flush từ primary.

Recovery point gần nhất trên standby có thể tương ứng 10:24:30. RPO xấp xỉ 30 giây, nếu transaction time và LSN mapping được hiểu đúng.

Đây chỉ là ví dụ đơn giản. Trong vận hành, cần dùng LSN/commit metadata và đo lag; `pg_last_xact_replay_timestamp()` có thể cũ dù standby đã replay hết WAL hiện có nếu primary không phát sinh transaction gần đây.

### 2.3. RPO là mục tiêu, không phải số đo

Phân biệt:

- **Target RPO:** mức mất dữ liệu tối đa được business chấp nhận;
- **Observed RPO:** lượng dữ liệu thực tế mất trong một incident/drill;
- **Potential RPO:** lượng dữ liệu có thể mất theo trạng thái replication/archive tại thời điểm hiện tại.

Nếu target RPO là 30 giây nhưng standby thường lag 3 phút, kiến trúc chưa đáp ứng mục tiêu dù chưa có incident.

### 2.4. RPO theo loại sự cố

RPO phải được gắn với failure scenario:

| Sự cố | Cơ chế phục hồi | RPO có thể đạt |
| --- | --- | --- |
| PostgreSQL process crash | Crash recovery từ local WAL | Thường không mất commit đã được flush theo durability settings |
| Primary host mất | Promote standby | Phụ thuộc synchronous/asynchronous replication và WAL đã nhận |
| Một AZ mất | Promote standby ở AZ khác | Phụ thuộc vị trí standby và replication mode |
| Region mất | Promote replica/restore ở region khác | Phụ thuộc cross-region replication và archive lag |
| Logical corruption/DELETE nhầm | PITR từ base backup + WAL | Tới thời điểm trước thao tác lỗi, nếu WAL chain đầy đủ |
| Ransomware/xóa backup | Restore từ immutable/offline copy | Phụ thuộc bản sao sạch gần nhất |
| Mất cả cloud account/provider | Restore ở provider/account độc lập | Phụ thuộc offsite copies và dữ liệu đã replicate |

Một RPO được công bố mà không nêu failure scenario có thể gây hiểu nhầm. RPO 0 cho lỗi host không đồng nghĩa RPO 0 khi cả region bị phá hủy hoặc người dùng xóa dữ liệu hợp lệ.

### 2.5. RPO và asynchronous replication

Asynchronous standby nhận WAL sau khi primary đã xác nhận commit. Khi primary hỏng đột ngột, một phần WAL vừa commit có thể chưa tới standby. RPO phụ thuộc:

- WAL generation rate;
- Network bandwidth/latency;
- Standby write/flush/replay throughput;
- Network outage duration;
- Queueing và disk capacity;
- Cách failover chọn node.

Không thể suy ra RPO chỉ từ giá trị `replay_lag` ở một thời điểm. Cần theo dõi LSN và thời gian nhận/flush/replay.

### 2.6. RPO và synchronous replication

Với synchronous replication được cấu hình đúng, primary có thể chỉ xác nhận commit sau khi một hoặc nhiều synchronous standbys đã flush WAL (hoặc đạt mức `synchronous_commit` được chọn). Điều này giảm hoặc loại bỏ mất các commits đã acknowledge trong failure scenario được bảo đảm.

Tuy nhiên, RPO 0 có điều kiện:

- Synchronous standby thực sự được chọn và đang hoạt động;
- Commit acknowledgment chờ đúng mức durability;
- Standby và primary không cùng failure domain bị mất;
- Storage trên cả hai nodes thực hiện flush đúng;
- Failover chọn đúng node có WAL đã được xác nhận;
- Không có lỗi cấu hình, thao tác thủ công hoặc corruption lan truyền.

Synchronous replication không bảo vệ khỏi DELETE nhầm, application bug, malicious SQL hay mất đồng thời cả các bản sao.

## 3. RTO là gì?

### 3.1. Định nghĩa

**Recovery Time Objective (RTO)** là thời gian tối đa tổ chức chấp nhận để khôi phục dịch vụ sau sự cố. RTO phải được đo từ một mốc đã thống nhất, ví dụ thời điểm dịch vụ ngừng đáp ứng request hoặc thời điểm incident được phát hiện, tới khi dịch vụ đạt điều kiện hoạt động trở lại.

RTO không chỉ là thời gian PostgreSQL process start. Nó có thể bao gồm phát hiện sự cố, quyết định failover, fencing, promotion, chuyển endpoint, warm-up, validation và mở traffic.

### 3.2. Phân rã RTO

Một mô hình hữu ích:

| Giai đoạn | Nội dung |
| --- | --- |
| Detection | Monitoring phát hiện và xác nhận sự cố |
| Decision | Phân loại incident, quyết định failover/restore |
| Fencing | Ngăn primary cũ tiếp tục nhận writes |
| Recovery | Promote standby hoặc restore base backup và replay WAL |
| Cutover | Chuyển DNS/VIP/load balancer/connection routing |
| Validation | Kiểm tra database, dữ liệu và ứng dụng |
| Stabilization | Theo dõi tải, replication, backup và error rate |

Tổng thời gian của các giai đoạn tạo nên observed RTO. Nếu RTO tính tới lúc request đầu tiên thành công, cần ghi riêng thời gian stabilization sau đó.

### 3.3. Ví dụ RTO

Một hệ thống đặt RTO 15 phút cho lỗi primary host:

- Detection: 1 phút;
- Decision và fencing: 2 phút;
- Promote standby: 1 phút;
- Chuyển endpoint: 2 phút;
- Application validation: 4 phút;
- Stabilization: 5 phút.

Tổng 15 phút. Nếu drill thực tế mất 27 phút, kiến trúc/runbook chưa đáp ứng RTO, dù promotion chỉ mất 30 giây.

### 3.4. RTO khác downtime

Downtime là thời gian dịch vụ thực tế không đáp ứng yêu cầu. RTO là giới hạn mục tiêu được đặt ra trước. Một hệ thống có thể đạt RTO trong một lần drill nhưng vẫn có downtime dài hơn trong incident khác nếu failure domain lớn hơn.

### 3.5. RTO và kích thước database

Restore từ backup thường tốn thời gian theo:

- Tổng bytes phải đọc/ghi;
- Storage throughput và IOPS;
- Số tablespaces/volumes;
- WAL volume cần replay;
- Số incremental backups cần combine;
- CPU và compression;
- Extension startup;
- Index/collation rebuild;
- Validation và application warm-up.

Với cluster nhiều TB, copy backup từ object storage có thể mất hàng giờ. Nếu RTO chỉ vài phút, thường cần standby đã được dựng sẵn thay vì bắt đầu restore sau incident.

### 3.6. RTO và RPO có thể xung đột

Synchronous replication có thể giảm RPO nhưng tăng commit latency và khiến writes bị block khi synchronous standby không khả dụng, tùy cấu hình. Asynchronous replication có thể tăng write availability nhưng có khả năng mất một phần WAL khi failover.

Restore từ backup có thể đạt recovery point cũ hơn nhưng mất nhiều thời gian hơn promote standby. Vì vậy thiết kế phải tối ưu đồng thời RPO, RTO và failure scenario.

## 4. Các mục tiêu liên quan: availability, SLO và RLO

### 4.1. Availability

Availability thường biểu diễn tỷ lệ thời gian dịch vụ sẵn sàng trong một khoảng đo:

\[
\text{Availability} =
\frac{\text{Thời gian sẵn sàng}}{\text{Tổng thời gian quan sát}}
\times 100\%
\]

Ví dụ 99.9% availability tương ứng khoảng 0.1% thời gian không sẵn sàng trong kỳ đo. Số phút downtime quy đổi phụ thuộc kỳ đo là tháng, quý hay năm.

### 4.2. SLO và SLA

- **SLO (Service Level Objective):** mục tiêu chất lượng dịch vụ nội bộ/được công bố, ví dụ availability 99.95%, RPO 1 phút, RTO 15 phút.
- **SLA (Service Level Agreement):** cam kết hợp đồng với khách hàng, có thể kèm điều khoản/credit khi không đạt.
- **SLI (Service Level Indicator):** chỉ số đo như request success rate, latency, error rate hoặc availability.

Một SLO phải có cách đo, cửa sổ thời gian, nguồn dữ liệu và tiêu chí loại trừ rõ ràng.

### 4.3. RLO và business recovery

Recovery Level Objective (RLO) mô tả mức độ chức năng/dữ liệu cần được khôi phục, ví dụ chỉ read-only trước, sau đó mới cho phép giao dịch. RLO hữu ích khi một hệ thống có thể phục vụ ở chế độ suy giảm trong lúc khôi phục đầy đủ.

### 4.4. MTPD/MAO

Maximum Tolerable Period of Disruption (MTPD), đôi khi gọi Maximum Acceptable Outage (MAO), là khoảng gián đoạn tối đa business có thể chịu trước khi hậu quả trở nên không thể chấp nhận. RTO phải thấp hơn MTPD để còn thời gian xác minh và phục hồi hoạt động.

### 4.5. Ví dụ mục tiêu cho một dịch vụ

| Mục tiêu | Giá trị ví dụ |
| --- | --- |
| Availability SLO | 99.95% mỗi tháng |
| RPO khi mất host/AZ | 0–30 giây theo replication mode |
| RPO khi mất region | 5 phút |
| RTO khi mất host | 5 phút |
| RTO khi mất AZ | 10 phút |
| RTO khi mất region | 2 giờ |
| RTO khi logical corruption | 4 giờ |
| RLO ban đầu | Read-only, sau đó mở writes |

Đây là ví dụ để minh họa cách tách mục tiêu theo scenario, không phải default phù hợp cho mọi hệ thống.

## 5. Failure domain là gì?

### 5.1. Định nghĩa

Failure domain là tập hợp thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân chung. Phân tán nodes theo hostname không đủ nếu chúng vẫn dùng cùng nguồn điện, switch, storage array hoặc control plane.

Mục tiêu của kiến trúc nhiều vùng lỗi là:

1. Giảm khả năng một sự cố đơn lẻ làm mất tất cả replicas;
2. Giữ đủ dữ liệu và năng lực để tiếp tục phục vụ;
3. Ngăn các replicas độc lập ghi dữ liệu xung đột;
4. Có đường phục hồi khi lỗi lan rộng hơn phạm vi HA thông thường.

### 5.2. Các lớp failure domain

| Lớp | Ví dụ sự cố | Biện pháp phân tách |
| --- | --- | --- |
| Process | PostgreSQL backend/postmaster crash | Supervisor, restart, standby |
| VM/host | Kernel panic, host power loss | Replicas trên host khác |
| Rack | PDU, top-of-rack switch, cooling | Phân tán rack |
| Availability zone (AZ) | Mất điện, network hoặc storage của AZ | Replica ở AZ khác |
| Region | Region-wide network/control-plane outage | DR region khác |
| Cloud account/project | IAM lockout, accidental deletion, billing/suspension | Account/project độc lập |
| Cloud provider | Provider outage hoặc policy event | Off-provider backup/DR |
| Identity/control plane | DNS, IAM, KMS, secrets, orchestration outage | Break-glass access và dependency redundancy |
| Human/operational | Xóa nhầm, deploy lỗi, credential bị lộ | RBAC, approval, immutable backups, audit |
| Software/data | Bug, corrupt migration, ransomware | PITR, logical copies, immutable/offline backups |

### 5.3. Vùng lỗi tương quan

Hai VMs khác nhau vẫn có thể cùng failure domain nếu:

- Chúng chạy trong cùng host hoặc cùng rack;
- Dùng chung một storage volume/array;
- Cùng phụ thuộc một AZ network gateway;
- Cùng dùng một KMS key hoặc identity provider;
- Backup và primary ở cùng account với quyền delete giống nhau;
- Cùng nhận một deployment/configuration bug.

Phân tách phải xét cả hạ tầng vật lý lẫn dependency vận hành.

### 5.4. AZ và region

Availability zone thường là một vùng hạ tầng độc lập trong một region, với nguồn điện/network riêng theo định nghĩa nhà cung cấp. Region là phạm vi địa lý lớn hơn và thường có failure domains độc lập hơn.

Multi-AZ thường bảo vệ lỗi một AZ với latency thấp hơn multi-region. Multi-region bảo vệ thảm họa region nhưng replication latency, data transfer cost và failover complexity cao hơn.

### 5.5. Failure domain của storage

Nếu primary và standby nằm ở hai AZ nhưng dùng một shared storage system chỉ có một failure domain, mất storage có thể làm cả hai nodes mất dữ liệu. Shared storage có thể có redundancy nội bộ, nhưng phải hiểu failure boundaries và SLA thực tế của nó.

Với PostgreSQL streaming replication, mỗi node thường có data files riêng trên storage độc lập. Điều này tránh một số lỗi shared-disk, nhưng cần đồng bộ WAL và quản lý failover.

### 5.6. Failure domain của backup

Backup cùng region/account với primary có thể mất cùng primary khi:

- Credential bị chiếm quyền và attacker xóa cả hai;
- IAM policy/configuration sai;
- Region/provider gặp sự cố;
- Ransomware mã hóa mounted backup repository.

Giữ bản sao immutable/offline/cross-account/cross-region theo threat model. Đảm bảo tài khoản DR vẫn có thể truy cập bản backup khi identity system chính gặp sự cố.

### 5.7. Failure domain của control plane

Một database có thể khỏe nhưng ứng dụng vẫn không kết nối nếu DNS, secrets manager, KMS, load balancer, service discovery hoặc orchestration control plane mất. Thiết kế DR phải bao gồm những dependency này, không chỉ PostgreSQL.

### 5.8. Failure domain của con người

Một thao tác có thể lan qua nhiều regions nếu cùng một automation role có quyền xóa mọi backups/replicas. Giảm blast radius bằng:

- Least privilege;
- Tách quyền vận hành và quyền xóa backup;
- Multi-person approval cho thao tác destructive;
- Immutable retention/object lock;
- Audit logs tách biệt;
- Break-glass accounts được bảo vệ và kiểm thử.

## 6. HA, disaster recovery và backup khác nhau

### 6.1. High Availability (HA)

HA tập trung duy trì hoặc nhanh chóng khôi phục dịch vụ khi lỗi thành phần thường gặp. Một topology HA có thể dùng primary + standby, health checks, fencing và automated failover.

Mục tiêu HA thường đo bằng RTO ngắn và RPO thấp cho lỗi host/AZ. HA không tự đảm bảo bảo vệ trước logical corruption hoặc xóa nhầm.

### 6.2. Disaster Recovery (DR)

DR chuẩn bị phục hồi khi một failure domain lớn bị mất: region, provider, account, storage hoặc toàn bộ site. DR thường dùng cross-region replicas, base backups, WAL archive, immutable copies và quy trình khởi động lại ở nơi khác.

DR có thể có RTO/RPO dài hơn HA vì cần chuyển hạ tầng, khôi phục dependencies, xác minh dữ liệu và chuyển traffic.

### 6.3. Backup

Backup là bản sao có thể khôi phục dữ liệu. Nó là một phần của DR và chống lỗi logic, nhưng backup không tự làm dịch vụ HA. Cần backup độc lập với replication vì replication sẽ sao chép cả thay đổi sai hợp lệ.

### 6.4. Business continuity

Business continuity bao gồm cả người, quy trình, ứng dụng, mạng, đối tác, hỗ trợ khách hàng và hoạt động nghiệp vụ. Database recovery chỉ là một phần của kế hoạch liên tục kinh doanh.

### 6.5. So sánh nhanh

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Restart/recovery | Phục hồi lỗi process | PostgreSQL crash recovery |
| HA | Tiếp tục phục vụ sau lỗi host/AZ | Promote standby |
| DR | Phục hồi sau thảm họa lớn | Restore/promote ở region khác |
| Backup/PITR | Quay về trạng thái dữ liệu cũ | Restore base backup + WAL |
| Business continuity | Duy trì hoạt động nghiệp vụ | Read-only/degraded mode, quy trình thủ công |

## 7. Kiến trúc HA cơ bản cho PostgreSQL

### 7.1. Primary và standby

PostgreSQL physical streaming replication dùng WAL để đồng bộ changes từ primary tới standby. Primary nhận writes; standby nhận WAL, flush và replay để cập nhật data files.

~~~text
              Application
                   |
              Write endpoint
                   |
              PostgreSQL
                Primary
                   |
              WAL streaming
                   |
              PostgreSQL
                Standby
~~~

Standby có thể phục vụ read-only queries khi hot standby được bật. Promotion chuyển standby thành primary mới sau khi quyết định failover.

### 7.2. Streaming replication không tự failover

PostgreSQL cung cấp replication protocol và recovery primitives. Việc phát hiện primary mất, chọn standby, fencing primary cũ, promote và chuyển endpoint cần orchestration bên ngoài hoặc managed service.

Các công cụ HA phổ biến trong hệ sinh thái gồm Patroni, repmgr, pg_auto_failover và giải pháp managed database của cloud. Chọn công cụ theo consensus store, fencing mechanism, supported PostgreSQL versions, operational skill và recovery behavior.

### 7.3. Hai node không đủ để quyết định an toàn trong mọi partition

Nếu chỉ có hai nodes và mất kết nối giữa chúng, mỗi node không thể tự biết node kia đã chết hay chỉ bị cô lập mạng. Nếu cả hai cùng promote/accept writes, split brain xảy ra.

Một hệ thống HA cần quorum/witness hoặc fencing/out-of-band control để xác định quyền sở hữu primary. Số lượng nodes không tự tạo ra quorum logic.

### 7.4. Tách data plane và control plane

- **Data plane:** PostgreSQL, WAL, data files, network replication.
- **Control plane:** health checks, leader election, DCS/consensus, fencing, service discovery, VIP/DNS, automation.

Control plane phải có failure model riêng. Nếu DCS đặt cùng một AZ duy nhất, topology data multi-AZ có thể vẫn không failover khi AZ đó mất.

### 7.5. Client routing

Ứng dụng không nên hard-code IP primary. Dùng endpoint ổn định qua proxy, VIP, DNS/service discovery hoặc managed endpoint. Kiểm tra DNS caching, connection pool retry, TCP keepalive và transaction retry semantics.

### 7.6. Failover không làm transaction retry an toàn tự động

Nếu kết nối bị đứt trong lúc COMMIT, client có thể không biết transaction đã commit hay chưa. Retry request mù có thể tạo duplicate business action. Dùng idempotency keys, unique constraints, transaction status lookup và application retry policy.

## 8. Synchronous và asynchronous replication

### 8.1. Asynchronous replication

Primary không chờ standby xác nhận WAL trước khi trả commit success. Điều này giảm commit latency và giúp primary tiếp tục writes khi standby/network bị chậm, nhưng có thể mất WAL chưa tới standby nếu primary mất.

### 8.2. Synchronous replication

Primary chờ một hoặc nhiều synchronous standbys đạt acknowledgment level trước khi xác nhận commit. Điều này tăng durability của acknowledged commits theo failure assumptions nhưng có thể làm writes chờ khi synchronous standby không sẵn sàng.

### 8.3. synchronous_commit levels

Các mức thường gặp:

| Setting | Điều kiện chờ ở standby |
| --- | --- |
| `off` | Không chờ local WAL flush theo cơ chế thông thường của commit; có thể mất transaction vừa được báo thành công khi crash |
| `local` | Chờ local WAL flush, không chờ synchronous standby |
| `remote_write` | Chờ synchronous standby ghi WAL tới OS, chưa nhất thiết durable trên storage |
| `on` | Chờ synchronous standby flush WAL xuống durable storage |
| `remote_apply` | Chờ synchronous standby replay WAL, ngoài việc flush |

Tên setting và semantics cần kiểm tra theo major version. `synchronous_commit=on` chỉ chờ remote nếu synchronous standby được cấu hình/chọn; nếu không có synchronous standby thì setting này không tự biến asynchronous replication thành synchronous.

### 8.4. synchronous_standby_names

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Chọn một synchronous standby theo priority order. Có thể cấu hình quorum:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Ví dụ quorum yêu cầu ít nhất hai standbys trong danh sách xác nhận. Cú pháp/behavior phải đối chiếu tài liệu đúng version. `FIRST` và `ANY` có semantics khác nhau khi chọn synchronous standbys.

### 8.5. Commit latency

Synchronous commit latency ít nhất chịu ảnh hưởng bởi network round-trip tới standby, WAL flush latency và scheduling. Cross-region synchronous replication có thể làm tăng đáng kể latency do khoảng cách địa lý.

### 8.6. Availability trade-off

Nếu tất cả synchronous standbys mất kết nối, commit có thể bị block trong khi primary vẫn chạy. Điều này có thể là hành vi mong muốn để bảo vệ RPO, nhưng cần một quy trình xử lý có chủ đích:

- Chờ standby phục hồi;
- Chuyển synchronous target sang node còn hoạt động;
- Tạm thời cho phép async mode theo approval/risk policy;
- Chuyển traffic sang node khác nếu đủ điều kiện.

Không tự động hạ durability mà không cảnh báo và không ghi lại RPO mới.

### 8.7. Quorum replication

Với `ANY N`, transaction chờ đủ N standbys trong danh sách xác nhận. Quorum giúp chịu lỗi một số standbys nhưng phải thiết kế số lượng nodes, failure domains và promotion candidates cẩn thận.

Một node nhận acknowledgment nhưng không được chọn để promote vẫn có thể là vấn đề nếu node sẽ được promote không có cùng WAL. Failover controller cần chọn một node có recovery point ít nhất tương ứng với commits đã acknowledge.

### 8.8. Không nhầm remote_write với durable flush

`remote_write` xác nhận WAL đã được ghi tới OS của standby, nhưng không tương đương flush durable xuống media. Nếu cần bảo vệ trước mất điện/storage crash trên standby, hiểu rõ mức acknowledgment và storage flush semantics.

### 8.9. Không nhầm remote_apply với business consistency

`remote_apply` bảo đảm standby đã replay WAL tới commit, hữu ích cho read-after-write trên standby. Nó không bảo đảm mọi downstream cache, search index, message queue hoặc external service đã cập nhật.

### 8.10. Replication lag

Theo dõi riêng:

- Send lag: WAL primary chưa gửi tới standby;
- Write lag: WAL đã nhận nhưng chưa ghi xuống OS;
- Flush lag: WAL đã ghi nhưng chưa flush durable;
- Replay lag: WAL đã flush nhưng chưa apply vào data pages.

Các metrics có thể là NULL tùy trạng thái/hoạt động; dùng LSN distance và WAL generation rate cùng thời gian quan sát.

## 9. Multi-AZ architecture

### 9.1. Mô hình primary/standby qua hai AZ

~~~text
                    Region A
       +----------------+   +----------------+
       | AZ-a           |   | AZ-b           |
       |                |   |                |
App -->| Primary        |-->| Standby        |
       | local storage  |WAL| local storage  |
       +----------------+   +----------------+
                \               /
                 \-- HA control-/
                    plane
~~~

Primary và standby nằm trên các AZ khác nhau, có storage độc lập và đường network riêng. Nếu AZ-a mất, controller có thể promote standby ở AZ-b sau khi xác minh primary cũ không thể tiếp tục ghi.

### 9.2. Số lượng standby

Một standby có thể đủ cho lỗi đơn lẻ nhưng không còn redundancy sau khi promote. Với yêu cầu cao hơn, có thể có:

- Một synchronous standby ở AZ khác để giảm RPO;
- Một asynchronous standby thứ hai ở AZ thứ ba hoặc region khác;
- WAL archive độc lập để PITR/DR.

Không cần replica ở mọi AZ nếu chi phí vượt lợi ích; lựa chọn dựa trên failure scenarios và RTO/RPO.

### 9.3. Primary và standby trên cùng AZ

Hai nodes khác host trong cùng AZ bảo vệ host/process failure nhưng không bảo vệ AZ outage. Ghi rõ mức bảo vệ trong architecture document.

### 9.4. Synchronous standby cùng region

Đặt synchronous standby ở AZ khác trong cùng region có thể cân bằng latency và RPO. Tuy nhiên, nếu cả region bị partition hoặc outage, synchronous commits có thể block và primary không thể đảm bảo write availability.

### 9.5. Ba AZ và quorum

Với ba AZ, có thể bố trí primary và hai standbys, hoặc DCS/consensus voters ở ba AZ. Cần phân biệt quorum của control plane với số synchronous standbys của PostgreSQL:

- DCS quorum quyết định node nào được phép giữ leadership;
- PostgreSQL synchronous quorum quyết định commit cần bao nhiêu WAL acknowledgments.

Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

### 9.6. Compute, storage và network

Multi-AZ chỉ hiệu quả khi các lớp cùng được phân tách:

- Compute instances ở AZ khác;
- Data volumes riêng và replicated qua WAL;
- Network routes/firewalls/security groups sẵn sàng;
- DNS/load balancer có endpoint failover;
- Backup repository không phụ thuộc một AZ;
- Control plane có quorum ngoài AZ đơn lẻ.

### 9.7. AZ outage và failover

Khi một AZ mất:

1. Xác minh outage không phải network partition cục bộ;
2. Xác định primary có thể vẫn nhận writes qua đường khác hay không;
3. Fencing primary cũ;
4. Chọn standby có WAL mới nhất và phù hợp RPO;
5. Promote;
6. Chuyển endpoint;
7. Kiểm tra application và tạo lại redundancy.

### 9.8. Availability zone không phải region độc lập hoàn toàn

Các AZ trong một region có thể cùng phụ thuộc một số control plane, DNS services, identity services hoặc backbone network. Multi-AZ giảm nhiều rủi ro nhưng không thay thế DR cross-region.

## 10. Multi-region architecture

### 10.1. Vì sao cần region thứ hai?

Multi-region bảo vệ trước sự cố vượt khỏi một AZ hoặc toàn bộ region: lỗi hạ tầng rộng, network backbone, control plane, sự cố vật lý hoặc một quyết định vận hành làm mất region chính.

### 10.2. Active-passive

Một region phục vụ writes; region còn lại duy trì standby/read-only và sẵn sàng nhận vai trò primary khi DR được kích hoạt.

~~~text
               Application
                    |
              Global endpoint
                    |
             Region A (active)
             PostgreSQL primary
                    |
             Async WAL stream
                    |
             Region B (passive)
             PostgreSQL standby
                    |
             WAL archive + backups
~~~

Active-passive thường đơn giản hơn cho một PostgreSQL cluster vì chỉ có một write primary tại một thời điểm.

### 10.3. Active-active không phải hai primary cùng ghi một cluster

PostgreSQL physical streaming replication là primary-to-standby. Nó không cung cấp multi-writer conflict resolution giữa hai primary độc lập.

Active-active ở tầng ứng dụng hoặc logical replication cần thiết kế conflict handling, key allocation, transaction semantics và consistency. Không được hiểu active-active là hai physical primaries cùng ghi một PGDATA/replication stream.

### 10.4. Cross-region asynchronous replication

Đây là mô hình phổ biến vì giảm commit latency trên primary. RPO phụ thuộc WAN latency/bandwidth và standby lag. Region DR cần đủ capacity và đủ WAL để replay.

### 10.5. Cross-region synchronous replication

Có thể giảm RPO cho commits đã acknowledge nhưng làm commit latency tăng theo WAN round-trip. Nếu link giữa regions mất, primary có thể block writes theo synchronous policy. Đây là lựa chọn chỉ phù hợp khi business chấp nhận latency/availability trade-off.

### 10.6. Regional independence

Region DR cần độc lập đủ về:

- Compute capacity/quota;
- Storage volumes/object storage;
- Network ingress/egress;
- DNS/global traffic manager;
- IAM roles và KMS access;
- Secrets/certificates;
- Monitoring/alerting;
- Backup catalog và restore tooling.

Nếu DR region chỉ có database replica nhưng không có ứng dụng, network route, credentials hoặc capacity để chạy workload, RTO thực tế sẽ dài.

### 10.7. Failover sang region B

Kịch bản:

1. Xác nhận region A mất hoặc không thể khôi phục trong RTO;
2. Kiểm tra standby B đã nhận/replay WAL tới LSN nào;
3. Xác định potential data loss so với target RPO;
4. Fencing region A bằng network/IAM/compute control nếu còn khả năng hoạt động;
5. Promote standby B;
6. Chuyển global endpoint và ứng dụng;
7. Kiểm tra writes và business invariants;
8. Bắt đầu backup/WAL archive trên timeline mới;
9. Dựng lại region A thành standby sau khi an toàn.

### 10.8. Failback không tự động đảo ngược failover

Sau khi B nhận writes, A đã cũ và divergent. Để quay lại A, phải rebuild/rewind A từ B, chờ catch up, lên lịch switchover và fence B tại thời điểm chuyển. Không bật lại A như primary cũ.

### 10.9. DNS TTL và endpoint switching

Global DNS/traffic manager có thể có TTL, cache và health-check delay. Một số clients giữ connection pool lâu hơn TTL. RTO phải tính cả thời gian clients nhận endpoint mới và reconnect.

### 10.10. Data sovereignty và compliance

Cross-region replication có thể chuyển dữ liệu qua biên giới. Kiểm tra data residency, encryption, key locality, retention, privacy requirements và hợp đồng nhà cung cấp trước khi chọn region DR.

### 10.11. Network partition giữa regions

Nếu primary region và DR region mất kết nối nhưng cả hai vẫn hoạt động, không tự promote DR region chỉ vì không thấy primary. Phải có fencing/quorum hoặc một quy trình quyết định được kiểm soát để tránh hai primary cùng nhận writes.

## 11. Quorum, leader election và fencing

### 11.1. Quorum

Quorum là số phiếu tối thiểu cần có để một quyết định trong hệ thống phân tán được xem là hợp lệ. Với consensus group gồm N voters, majority quorum thường là floor(N/2)+1.

Ví dụ:

| Voters | Majority quorum |
| ---: | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |

Quorum ngăn hai phía của một network partition cùng đạt majority nếu voters và protocol được triển khai đúng.

### 11.2. Witness

Witness là một voter/arbiter không nhất thiết chạy PostgreSQL data. Nó có thể giúp xác định phía nào có quyền leadership khi hai data nodes mất kết nối.

Witness không thay thế standby chứa WAL/data. Nếu chỉ có witness mà không có một replica dữ liệu khỏe, quorum không tạo ra database để phục vụ.

### 11.3. Leader election

HA controller chọn một node được phép làm primary. Leadership cần lease/term/epoch hoặc consensus state để node cũ không tiếp tục ghi khi đã mất quyền.

### 11.4. Fencing

Fencing là hành động ngăn node cũ tiếp tục truy cập hoặc ghi vào tài nguyên production trước khi promote node mới. Có thể thực hiện qua:

- Tắt/stop instance hoặc host;
- Power fencing qua out-of-band management;
- Thu hồi storage/network access;
- Chặn write traffic ở network/load balancer;
- Cloud API/IAM/compute fencing;
- Cluster manager bảo đảm lease/leader token.

Chỉ bỏ IP khỏi DNS không phải fencing chắc chắn nếu ứng dụng vẫn có thể kết nối trực tiếp tới primary cũ.

### 11.5. Split brain

Split brain xảy ra khi hai nodes cùng tin mình là primary và nhận writes độc lập. Hai histories sẽ diverge; PostgreSQL physical replication không tự merge hai nhánh đó.

Hậu quả:

- Mất hoặc trùng business transactions;
- Divergent WAL timelines;
- Inconsistent IDs/unique keys;
- Khó xác định source of truth;
- Phục hồi phức tạp bằng logical reconciliation.

### 11.6. Failover safety

Trước khi promote, controller cần:

1. Đảm bảo primary cũ đã bị fencing hoặc có bằng chứng chắc chắn không thể ghi;
2. Xác định candidate standby và WAL position;
3. Kiểm tra candidate có đủ điều kiện promotion;
4. Ghi lại quyết định/epoch;
5. Promote đúng một node;
6. Chỉ sau đó chuyển writes tới endpoint mới.

### 11.7. Quorum của DCS không đảm bảo dữ liệu mới nhất

Một DCS có quorum có thể chọn leader an toàn về control plane, nhưng candidate PostgreSQL vẫn có thể lag WAL. Cần thêm policy chọn candidate theo WAL LSN, synchronous replication guarantees và business RPO.

### 11.8. Synchronous quorum và failover quorum

Synchronous quorum trả lời câu hỏi “commit cần bao nhiêu standby acknowledgments?”. DCS quorum trả lời “node nào được phép làm leader?”. Không được đánh đồng hai quorum.

### 11.9. Manual failover

Manual failover vẫn cần checklist fencing, candidate selection, promotion, endpoint change và validation. Việc một DBA chạy `pg_ctl promote` không tự bảo đảm primary cũ đã dừng.

### 11.10. Failover automation

Automation phải xử lý timeout, transient network errors, false positives, DCS unavailability, lagging replicas và stale endpoints. Cần test cả tình huống controller chết giữa chừng, không chỉ happy path.

## 12. Replication, backup và PITR bổ trợ nhau

### 12.1. Replication không phải backup

Streaming replication sao chép WAL changes gần như liên tục. Nếu một user chạy DROP TABLE hoặc ứng dụng ghi dữ liệu sai, standby cũng replay thay đổi đó.

### 12.2. Backup không phải HA

Base backup và WAL archive có thể phục hồi cluster nhưng restore lớn có thể mất hàng giờ. Nếu RTO vài phút, cần standby hoặc managed failover.

### 12.3. PITR bảo vệ logical errors

PITR dùng base backup + WAL archive để dừng ở trước transaction/operation gây lỗi. Restore sang cluster tạm giúp trích xuất dữ liệu bị xóa nhầm mà không nhất thiết phải rollback toàn production.

### 12.4. Kiến trúc nhiều lớp

~~~text
                 Primary
                    |
          +---------+----------+
          |                    |
     Sync standby        Async DR standby
       Multi-AZ             Other region
          |                    |
          +---------+----------+
                    |
              WAL archive
                    |
              Base backups
                    |
          Immutable/offsite copy
~~~

Sơ đồ minh họa các lớp bảo vệ. Topology thực tế phải chọn số replicas, sync policy, archive path và failure domains theo RPO/RTO.

### 12.5. Archive WAL độc lập

Archive WAL nên nằm ở storage/account/failure domain khác primary. Theo dõi archive success, failed segments, retention và timeline history. Streaming standby không thay thế WAL archive.

### 12.6. Backup encryption và immutability

Mã hóa backup khi lưu/truyền, bảo vệ keys độc lập, dùng immutable retention/object lock và tách quyền delete. Kiểm thử khả năng khôi phục key ở DR site.

### 12.7. Backup cadence và WAL

Base backup càng thường xuyên có thể giảm lượng WAL phải replay và rút ngắn RTO, nhưng tăng storage/network cost. Incremental backup có thể giảm transfer size nhưng thêm chain complexity. Đo restore time thực tế trước khi chọn cadence.

### 12.8. Logical backup

Logical dump hữu ích cho selective recovery, migration và trích xuất bảng. Nó bổ sung cho physical backup, đặc biệt khi cần khôi phục một object sau thao tác sai.

## 13. Thiết kế capacity cho standby và DR

### 13.1. Standby cần đủ năng lực để chạy production

Một standby có CPU/RAM/storage thấp hơn primary có thể theo kịp khi workload bình thường nhưng không chịu được peak load sau promotion. Khi primary mất, toàn bộ application workload chuyển sang node còn lại.

Capacity planning phải kiểm tra:

- CPU cores và clock/NUMA;
- RAM và `shared_buffers`;
- Storage IOPS/throughput/latency;
- Network bandwidth;
- WAL receiver/replay throughput;
- Connection limits;
- Temporary files và sort/hash memory;
- Extension/background worker capacity.

### 13.2. N+1 capacity

Thiết kế N+1 nghĩa là sau khi mất một node, phần capacity còn lại vẫn đáp ứng workload mục tiêu. Nếu primary và standby mỗi node chỉ đủ 50% workload, failover có thể làm hệ thống quá tải ngay khi vừa phục hồi.

### 13.3. Headroom

Giữ headroom cho:

- Peak traffic;
- WAL replay;
- Autovacuum;
- Backup/restore;
- Index maintenance;
- Connection storms sau failover;
- Monitoring/management agents.

Không lấy average CPU thấp làm bằng chứng standby đủ capacity.

### 13.4. WAL replay throughput

Nếu standby replay WAL chậm hơn tốc độ primary tạo WAL trong thời gian dài, lag sẽ tăng không giới hạn. Khi primary mất, recovery point trên standby càng cũ.

Đo WAL generation rate và replay throughput trong peak workload. Nếu replay throughput thấp, kiểm tra storage random I/O, CPU, checkpoint behavior, query conflicts trên hot standby và network.

### 13.5. Catch-up time

Một standby lag 100 GB cần thời gian catch up phụ thuộc throughput thực tế. Nếu net replay throughput là 200 MB/s, lý thuyết mất khoảng 500 giây, nhưng còn cạnh tranh I/O, WAL arrival và checkpoint. Đo bằng drill, không chỉ chia dung lượng cho tốc độ quảng cáo.

### 13.6. Storage capacity

Dự phòng dung lượng cho:

- Data growth;
- WAL retention do replication slots;
- Archive staging;
- Temporary restore files;
- Incremental combine output;
- Index rebuild;
- Backup retention;
- Emergency headroom.

Một slot inactive có thể giữ WAL lâu và làm `pg_wal` đầy. Cảnh báo trước khi disk pressure ảnh hưởng primary.

### 13.7. Connection capacity

Sau failover, clients có thể reconnect đồng loạt. `max_connections`, connection pool size, PgBouncer/proxy capacity và application retry jitter cần được tính cho peak reconnection storm.

### 13.8. Region DR capacity

Nếu DR region chỉ chạy standby nhỏ, cần biết thời gian scale up, quota, instance availability và storage resize. Một node không đủ capacity có thể đạt database recovery nhưng không đạt service RTO.

## 14. Monitoring để chứng minh RPO/RTO

### 14.1. Monitoring replication

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

Tên/cột view có thể khác theo major version. Kiểm tra catalog trên version đang chạy.

### 14.2. Theo dõi LSN distance

Primary có thể cung cấp current WAL LSN:

~~~sql
SELECT pg_current_wal_lsn();
~~~

Standby có thể đọc:

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

So sánh LSN cần tính khoảng bytes bằng hàm phù hợp và đảm bảo hai giá trị thuộc cùng timeline/cluster history. Không so sánh LSN từ các timeline không liên quan như một số đo lag trực tiếp.

### 14.3. Replication lag time

Các cột lag trong `pg_stat_replication` hữu ích nhưng không phải đồng hồ RPO tuyệt đối. Khi không có WAL mới, lag có thể NULL hoặc cũ; khi có burst WAL, lag tăng nhanh. Kết hợp LSN gap, WAL rate và timestamps.

### 14.4. Archive monitoring

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Alert khi archive failures tăng, last archived time quá cũ so với WAL activity hoặc repository không nhận segment. Theo dõi continuity chứ không chỉ command success.

### 14.5. Health check primary

Health check nên kiểm tra nhiều lớp:

- PostgreSQL process/connection;
- Query khả dụng;
- Disk/memory pressure;
- WAL/archive progress;
- Replication state;
- Application-level write/read path;
- Control plane leader/fencing state.

Một TCP port mở không chứng minh primary sẵn sàng nhận transaction.

### 14.6. Health check standby

Kiểm tra:

- WAL receiver connected;
- Receive/flush/replay LSN tiến triển;
- Lag trong target;
- Storage đủ dung lượng;
- Standby có thể promote;
- Extension/config tương thích;
- Không có recovery conflicts bất thường.

### 14.7. Potential RPO alert

Định nghĩa ngưỡng cảnh báo theo mục tiêu:

- Warning khi estimated potential RPO đạt 50% budget;
- Critical khi vượt target RPO;
- Page on-call nếu standby/archive không thể bắt kịp.

Các ngưỡng ví dụ phải điều chỉnh theo workload và business objective. Không đợi incident mới phát hiện replica lag.

### 14.8. RTO telemetry

Ghi timestamps tự động cho:

- First failure signal;
- Incident declaration;
- Failover decision;
- Fencing completed;
- Promotion completed;
- Endpoint switched;
- First successful application request;
- Business validation completed.

Từ đó tính từng thành phần RTO và xác định bottleneck.

### 14.9. Alert fatigue

Alert phải có severity, owner, runbook link và action rõ. Đừng page khi một metric đơn lẻ transient nếu không có user impact; đồng thời không gộp mọi lỗi vào một health check chung khó chẩn đoán.

### 14.10. Dashboard HA/DR

Một dashboard nên thể hiện:

- Primary/standby role và node health;
- Timeline/system identifier;
- Synchronous standby state;
- Send/write/flush/replay LSN gaps;
- WAL generation/replay rates;
- Archive status/last segment;
- Slot retained WAL;
- Disk/CPU/network headroom;
- Potential RPO;
- Restore drill RTO history.

## 15. Failure scenarios và response matrix

| Scenario | Detection | Response chính | Mục tiêu cần đo |
| --- | --- | --- | --- |
| Process crash | Process/SQL health check | Restart, crash recovery | RTO process recovery |
| Primary host lost | Host/DB unreachable | Fence host, promote standby | RPO/RTO host |
| AZ network partition | Cross-AZ health/consensus | Xác định quorum, fence phía cũ | Split-brain prevention |
| AZ outage | Cloud/AZ signals | Promote standby AZ khác | RPO/RTO AZ |
| Region outage | Multi-signal regional failure | DR decision, promote region B | RPO/RTO region |
| Standby lag | LSN gap/lag alert | Tăng capacity, fix network/I/O | Potential RPO |
| WAL archive failure | `pg_stat_archiver`/repository | Sửa pipeline, bảo vệ WAL | PITR recoverability |
| Logical corruption | Data/business validation | Isolate, PITR restore | RPO/RTO logical |
| Ransomware | Security/backup integrity | Isolate, restore immutable copy | Clean recovery point |
| Operator error | Audit/change event | Stop change, PITR/logical restore | Data loss window |
| KMS/IAM outage | Auth/key errors | Break-glass access, DR identity path | Dependency RTO |
| Control-plane outage | DCS/leader election alarms | Safe manual procedure | Failover safety |

## 16. Failure mode analysis

### 16.1. Primary chết nhưng standby lag

Standby có thể promote nhanh nhưng mất các commits chưa replicate. So sánh potential RPO và chọn node có LSN mới nhất. Nếu primary còn truy cập được storage/WAL, có thể lấy WAL tail theo quy trình an toàn trước khi promote.

### 16.2. Network partition nhưng primary vẫn sống

Standby có thể nghĩ primary chết. Nếu promotion xảy ra mà primary không bị fence, split brain. Health check nên dùng nhiều tín hiệu và fencing có thể thực thi ngoài network partition.

### 16.3. Synchronous standby mất

Primary có thể tiếp tục nhận kết nối nhưng commits bị chờ. Cần chính sách fail-open/fail-closed rõ ràng. Hạ sync policy có thể tăng availability nhưng làm tăng RPO; phải được giám sát và audit.

### 16.4. Standby mất storage

Primary có thể vẫn hoạt động. Cần khôi phục standby từ backup hoặc base backup mới; không coi việc primary đang khỏe là đã khôi phục redundancy.

### 16.5. Primary và standby cùng lỗi do shared dependency

Ví dụ một KMS key bị disable khiến cả hai nodes không mount được encrypted volumes. Tách compute nhưng không tách key management vẫn còn common failure domain.

### 16.6. Bug/migration được replicate

Standby sẽ nhận WAL của thay đổi hợp lệ nhưng sai nghiệp vụ. PITR cần base backup và WAL archive có thể dừng trước thay đổi; backup immutable bảo vệ khi primary và replicas cùng bị ảnh hưởng.

### 16.7. Backup repository bị xóa

Replication không cứu được backup bị xóa. Tách account, IAM, retention lock và audit để attacker/operator không thể xóa đồng thời mọi bản sao.

### 16.8. Region DR hết quota

Một replica không thể scale hoặc restore khi region B không còn instance/storage quota. Reserve capacity hoặc kiểm thử quota request/scale path định kỳ.

### 16.9. DNS/global routing không cập nhật

Database mới đã promote nhưng ứng dụng vẫn gọi endpoint cũ. Kiểm tra DNS TTL, resolver cache, connection pools, proxy config và direct hostnames.

### 16.10. Restore keys/dependencies không có

Database files tồn tại nhưng extension/KMS/SSL secrets không thể lấy từ DR. Giữ encrypted copies, key recovery process và dependency inventory ngoài failure domain chính.

## 17. Chuyển yêu cầu kinh doanh thành topology

### 17.1. Bắt đầu từ workload và business impact

Trước khi chọn số nodes, thu thập:

- Loại dữ liệu và mức độ quan trọng;
- Giao dịch nào không thể mất;
- Thời gian gián đoạn tối đa;
- Giờ cao điểm và seasonality;
- Quy mô dữ liệu/WAL;
- Phụ thuộc ứng dụng và bên thứ ba;
- Yêu cầu compliance/data residency;
- Ngân sách hạ tầng và nhân sự on-call.

Không đặt RPO/RTO chỉ dựa trên topology mà đội kỹ thuật đang có.

### 17.2. Phân loại workload

Ví dụ:

| Workload | Mức độ quan trọng | Hướng thiết kế |
| --- | --- | --- |
| Ledger/payment | Rất cao | Synchronous HA, immutable backup, DR region |
| Order processing | Cao | Multi-AZ standby, WAL archive, PITR |
| Reporting | Trung bình | Async/read replica, có thể chấp nhận lag |
| Analytics staging | Thấp hơn | Backup định kỳ, restore theo nhu cầu |
| Audit/legal records | Rất cao về retention | Immutable/offsite backup và kiểm soát truy cập |

Một cluster có thể chứa nhiều workload với mục tiêu khác nhau; nếu yêu cầu xung đột, cân nhắc tách cluster hoặc tách luồng dữ liệu.

### 17.3. Failure scenario matrix

Tạo bảng cho từng failure:

| Scenario | RPO target | RTO target | Recovery method | Owner |
| --- | --- | --- | --- | --- |
| Process crash | Gần 0 | 1 phút | Restart/crash recovery | DBA/on-call |
| Host failure | 0–30 giây | 5 phút | Promote local standby | DBA/SRE |
| AZ outage | 0–1 phút | 10 phút | Cross-AZ promotion | SRE |
| Region outage | 5 phút | 2 giờ | Cross-region DR | DR lead |
| Logical corruption | Trước transaction lỗi | 4 giờ | PITR + selective export | DBA/application |
| Ransomware | Bản sạch gần nhất | 8 giờ | Immutable restore | Security/DR |

Giá trị phải được business owner phê duyệt và kiểm chứng qua drills.

### 17.4. Chọn topology theo mục tiêu

| Yêu cầu | Topology gợi ý | Hạn chế cần chấp nhận |
| --- | --- | --- |
| RPO vài phút, RTO vài phút cho host | Primary + async standby cùng region | Có thể mất WAL tail |
| RPO rất thấp cho host/AZ | Primary + synchronous standby ở AZ khác | Commit latency và write blocking khi sync node mất |
| DR region RPO vài phút | Async cross-region standby + WAL archive | Có data loss nếu region mất trước khi WAL tới DR |
| DR region RPO gần 0 | Sync cross-region hoặc thiết kế commit/quorum phù hợp | WAN latency cao, partition có thể dừng writes |
| Bảo vệ logical errors | Base backup + WAL archive + PITR | Restore test và thời gian replay |
| Bảo vệ ransomware | Immutable/offline/cross-account backups | Cost, key management, restore time |

### 17.5. Không tối ưu một con số duy nhất

Tối ưu RPO mà bỏ qua availability có thể khiến writes block khi WAN/synchronous standby lỗi. Tối ưu RTO bằng nhiều replicas mà bỏ qua backup có thể khiến lỗi logic lan tới tất cả nodes. Tối ưu availability mà bỏ qua fencing có thể tạo split brain.

### 17.6. Business impact tiers

Có thể phân tầng:

- Tier 0: ledger/payment/core identity; cần RPO/RTO thấp nhất và DR được kiểm thử thường xuyên;
- Tier 1: customer-facing transactional workloads;
- Tier 2: reporting và internal tools;
- Tier 3: batch, cache, rebuildable datasets.

Mỗi tier có backup cadence, standby placement, alert response và budget khác nhau.

## 18. Ví dụ kiến trúc tham khảo

### 18.1. Lab/dev

Yêu cầu ví dụ: RPO 24 giờ, RTO 1 ngày.

Kiến trúc:

- Một PostgreSQL primary;
- Daily base backup;
- WAL archive nếu cần PITR;
- Backup lưu ở object storage;
- Restore test theo lịch.

Không cần automated multi-AZ failover nếu downtime có thể chấp nhận.

### 18.2. Internal application

Yêu cầu ví dụ: RPO 5 phút, RTO 30 phút.

Kiến trúc:

- Primary + async standby ở host/AZ khác;
- WAL archive liên tục;
- Base backup định kỳ;
- Health checks và manual/controlled failover;
- Application connection endpoint ổn định.

RPO thực tế cần monitor lag; RTO drill bao gồm promotion và application reconnect.

### 18.3. Customer-facing transactional service

Yêu cầu ví dụ: RPO 0–30 giây cho host/AZ, RTO dưới 5 phút.

Kiến trúc:

- Primary ở AZ-a;
- Synchronous standby ở AZ-b;
- Async standby ở AZ-c hoặc DR region;
- HA controller có quorum/fencing;
- WAL archive độc lập;
- Immutable backups;
- Global endpoint/connection proxy;
- Automated drills và alerting.

Nếu synchronous standby không sẵn sàng, policy phải nêu rõ có block writes hay hạ sync mode với approval.

### 18.4. Regional disaster recovery

Yêu cầu ví dụ: RPO 5 phút, RTO 2 giờ.

Kiến trúc:

- Multi-AZ HA trong primary region;
- Async physical standby ở DR region;
- WAL archive cross-region;
- Base backups được copy cross-account;
- DR application infrastructure và secrets sẵn sàng;
- Global DNS/traffic management;
- DR runbook và annual/quarterly full-region drills.

### 18.5. Compliance/archive workload

Yêu cầu: retention dài, auditability và khả năng phục hồi clean copies.

Kiến trúc:

- Primary/standby cho availability;
- Base backup + WAL archive;
- Immutable object retention;
- Account tách quyền delete;
- Key recovery process;
- Periodic restore verification;
- Retention policy được phê duyệt.

### 18.6. Một cluster hay nhiều clusters?

Nếu payment và reporting cùng cluster, reporting queries có thể ảnh hưởng latency của giao dịch; một failure/config change có thể tác động cả hai. Cân nhắc tách cluster hoặc dùng read replicas/resource governance khi business objectives khác nhau.

## 19. Cost và trade-offs

### 19.1. Compute cost

Standby chạy liên tục tiêu thụ compute. Một standby đủ capacity để nhận toàn bộ workload có thể gần bằng chi phí primary. DR region có thể chạy nhỏ hơn nhưng phải tính scale-up time.

### 19.2. Storage cost

Mỗi physical standby có data copy riêng. Base backups, incremental chains, WAL archives và immutable copies làm tăng storage cost. Retention dài giúp bảo vệ nhưng cần lifecycle rules có hiểu biết về backup chain.

### 19.3. Network cost

Cross-AZ/cross-region WAL streaming và backup transfer có thể phát sinh egress charges. Synchronous cross-region còn tăng commit latency do RTT.

### 19.4. Operational cost

Multi-region đòi hỏi:

- On-call coverage;
- DR exercises;
- Version/config synchronization;
- Secrets/key management;
- Failover/failback runbooks;
- Monitoring nhiều regions;
- Quota/capacity management;
- Incident coordination.

### 19.5. Complexity budget

Mỗi replica, controller, proxy, DCS, region và backup tool tăng thêm một tập failure modes. Thêm thành phần chỉ khi nó giảm rủi ro/đạt mục tiêu có giá trị rõ ràng.

### 19.6. Managed PostgreSQL

Managed services có thể cung cấp Multi-AZ, automated backups, cross-region replicas và failover orchestration. Tuy nhiên, cần kiểm tra:

- RPO/RTO theo từng failure scenario;
- Replication mode và acknowledgment semantics;
- Failover detection/fencing;
- Backup retention/restore time;
- Cross-region failover support;
- Limits/quota và service maintenance behavior;
- Khả năng export/restore ngoài provider.

Không suy ra RPO 0 hoặc RTO vài phút chỉ từ nhãn “Multi-AZ”.

### 19.7. Self-managed PostgreSQL

Self-managed cho phép kiểm soát sâu nhưng team phải chịu trách nhiệm cho controller, DCS, fencing, backups, patching, monitoring, restore tests và incident response.

### 19.8. Quyết định theo total cost of ownership

Tính cả chi phí outage dự kiến, dữ liệu mất, nhân sự vận hành, storage/network và độ phức tạp. Một topology rẻ hơn có thể có expected loss cao hơn khi sự cố xảy ra.

## 20. Kiểm thử HA và DR

### 20.1. Vì sao phải drill?

Runbook chưa được thực hành thường có giả định sai: credentials hết hạn, DNS cache lâu, extension thiếu, WAL archive gap, quota không đủ hoặc controller không thể fence primary.

### 20.2. Các cấp kiểm thử

1. Unit test scripts: kiểm tra command, config và permissions;
2. Component test: dừng một standby, kiểm tra monitoring/reattach;
3. Failover drill: mô phỏng primary host loss;
4. AZ drill: cô lập một AZ/network path;
5. Region DR drill: restore/promote ở region khác;
6. PITR drill: khôi phục trước một transaction gây lỗi;
7. Ransomware/backup drill: phục hồi từ immutable copy;
8. Full business continuity drill: kiểm tra application, DNS, identity và operations.

### 20.3. Không bắt đầu bằng phá production

Thực hiện drills trong staging hoặc môi trường có blast radius được kiểm soát. Nếu production game day được phê duyệt, phải có scope, rollback, on-call, customer impact controls và stop conditions rõ ràng.

### 20.4. Test process restart

Xác minh PostgreSQL tự crash-recover, monitoring báo đúng và application reconnect. Đo downtime và đảm bảo transaction retry không tạo duplicate.

### 20.5. Test standby promotion

Mô phỏng primary không thể phục vụ. Kiểm tra fencing, candidate selection, promotion, endpoint switching, application smoke tests và rebuild redundancy.

### 20.6. Test network partition

Tạo partition có kiểm soát giữa primary/standby/control plane. Xác nhận chỉ một node có quyền writes và system không promote nhầm khi primary vẫn sống.

### 20.7. Test WAL archive recovery

Restore một base backup riêng, cấu hình restore command và replay WAL tới target. Xác nhận archive đủ segments/history và đo recovery time.

### 20.8. Test logical error recovery

Trong lab, tạo restore point, thực hiện một thao tác xóa nhầm, PITR sang cluster mới và xác minh dữ liệu trước/sau. Đo thời gian export/import nếu chỉ phục hồi một table.

### 20.9. Test failback

Sau failover drill, dựng lại node cũ thành standby bằng rewind hoặc base backup. Chờ catch up, switchover có kiểm soát và kiểm tra không có split brain.

### 20.10. Ghi nhận kết quả

Mỗi drill lưu:

- Scenario và failure domain;
- Target/observed RPO;
- Target/observed RTO;
- Timeline/LSN của candidate;
- Detection/decision/fencing/promotion/cutover durations;
- Data/application validation results;
- Manual steps và blockers;
- Follow-up owner/deadline.

### 20.11. Game day sau thay đổi lớn

Chạy lại các tests liên quan sau major upgrade, OS/extension update, network redesign, IAM/KMS change, backup tool change, topology change hoặc chuyển storage.

## 21. Runbook failover khi primary host mất

### 21.1. Điều kiện bắt đầu

Runbook chỉ được kích hoạt khi incident commander/HA controller xác nhận primary không còn phục vụ được và failure scope đã được xác định. Một health check timeout đơn lẻ chưa đủ để promote.

### 21.2. Xác định trạng thái

Thu thập:

- Primary process/host/network health;
- DCS/consensus leader state;
- Standby receive/flush/replay LSN;
- Synchronous standby status;
- WAL archive progress;
- Khả năng truy cập out-of-band để fence host;
- Application error rate và request queue.

### 21.3. Fencing

Fencing primary cũ trước promotion theo cơ chế đã test. Nếu không thể xác minh primary cũ bị cô lập, dừng và dùng quy trình escalation. Không mở writes đồng thời ở hai nodes.

### 21.4. Chọn candidate

Chọn standby:

- Cùng system identifier/cluster history;
- Có timeline/WAL hợp lệ;
- Có receive/flush/replay LSN mới nhất;
- Đáp ứng RPO đã thống nhất;
- Đủ capacity để nhận workload.

Ghi lại ước tính data loss nếu asynchronous WAL chưa được nhận.

### 21.5. Promote

Khi fencing và candidate đã xác nhận:

~~~sql
SELECT pg_promote(wait => true);
~~~

Hoặc dùng HA manager. Xác nhận node thoát recovery và nhận writes đúng vai trò.

### 21.6. Chuyển endpoint

Chuyển proxy/VIP/DNS/managed endpoint. Theo dõi connection pools, client retries, TLS và application health. Nếu client vẫn gọi IP cũ, sửa service discovery theo runbook.

### 21.7. Validation

Chạy smoke tests:

- Read critical records;
- Commit một transaction kiểm thử có kiểm soát;
- Xác nhận unique/foreign key constraints;
- Kiểm tra sequences;
- Kiểm tra replication/archive;
- Xác nhận application error rate.

### 21.8. Khôi phục redundancy

Tạo lại standby từ primary mới bằng rewind nếu đủ điều kiện hoặc base backup mới. Không coi incident đã xong khi chỉ một primary chạy; redundancy phải được phục hồi và kiểm chứng.

## 22. Runbook disaster recovery khi mất region

### 22.1. Xác nhận DR trigger

Kích hoạt DR khi region chính không thể phục hồi trong RTO hoặc đã được xác định là mất. Ghi rõ người ra quyết định, timestamp và phạm vi outage.

### 22.2. Chọn nguồn dữ liệu

Ưu tiên candidate theo thứ tự đã định trước:

- Cross-region standby còn khỏe và có WAL mới nhất;
- Base backup + WAL archive ở DR region;
- Immutable backup/offsite copy nếu replicas/archive bị ảnh hưởng.

So sánh recovery point với target RPO. Nếu không thể đạt target, incident commander phải quyết định business acceptance trước cutover.

### 22.3. Fencing region cũ

Nếu region cũ có thể hoạt động lại, cô lập write access bằng network/IAM/compute controls. Không dựa vào DNS TTL như biện pháp duy nhất.

### 22.4. Khôi phục dependencies

Kiểm tra:

- Compute/storage quota;
- Network routes/firewall;
- IAM roles/KMS keys/secrets;
- TLS certificates/DNS;
- Application deployment/config;
- Monitoring/alerting;
- Backup/WAL archive access.

### 22.5. Promote và mở traffic

Promote node DR sau khi fencing. Chuyển global endpoint, reconnect clients và chạy business validation. Bật WAL archive/backup cho timeline mới ngay sau cutover.

### 22.6. Rebuild region cũ

Khi region cũ trở lại, không bật primary cũ vào mạng writes. Dùng rewind hoặc base backup từ primary mới để tái lập standby. Thực hiện failback sau khi có plan và maintenance window.

## 23. Runbook phục hồi khi replication lag vượt RPO

### 23.1. Cảnh báo sớm

Nếu estimated lag chạm warning threshold:

1. Xác định lag ở send/write/flush/replay stage;
2. Kiểm tra network bandwidth/packet loss;
3. Kiểm tra standby CPU/I/O;
4. Kiểm tra WAL generation burst;
5. Kiểm tra recovery conflicts và disk pressure;
6. Dự báo catch-up time.

### 23.2. Giảm workload có chủ đích

Nếu cần, giảm batch/bulk jobs hoặc read workload trên standby để replay WAL bắt kịp. Không tắt replication hoặc xóa slot mà chưa hiểu tác động.

### 23.3. Kiểm tra slot và WAL retention

Kiểm tra replication slots, retained WAL và disk. Nếu slot giữ WAL quá nhiều, giải quyết consumer/standby trước khi thay đổi slot policy. Một slot bị drop có thể khiến standby cần base backup mới.

### 23.4. Escalation

Nếu lag vượt RPO:

- Thông báo business/on-call;
- Ghi nhận potential data loss;
- Cân nhắc thêm replica hoặc tăng capacity;
- Không promote standby lagging chỉ vì nó là node duy nhất còn online nếu còn khả năng phục hồi WAL mới hơn;
- Cập nhật RPO status trong incident channel.

### 23.5. Sau khi bắt kịp

Xác nhận lag giảm ổn định, archive hoạt động, slot retention hợp lý và nguyên nhân gốc được xử lý. Điều chỉnh capacity/alert thresholds nếu cần.

## 24. Checklist thiết kế kiến trúc nhiều vùng lỗi

### 24.1. Business objectives

- [ ] RPO được định nghĩa riêng cho host, AZ, region và logical corruption.
- [ ] RTO có mốc bắt đầu/kết thúc và các giai đoạn đo.
- [ ] SLO/SLI/availability window được thống nhất.
- [ ] MTPD lớn hơn RTO với thời gian dự phòng validation.
- [ ] RLO/degraded mode được xác định.
- [ ] Business owner chấp nhận trade-off latency/data loss.

### 24.2. Failure domains

- [ ] Primary/standby không cùng host/rack/AZ.
- [ ] Storage replicas độc lập theo failure model.
- [ ] Control plane/DCS có quorum phù hợp.
- [ ] Backup nằm ngoài primary failure domain.
- [ ] Account/IAM/KMS có đường truy cập DR.
- [ ] DNS/network/load balancer có phương án dự phòng.
- [ ] Có kế hoạch chống common-mode software/human errors.

### 24.3. Replication and failover

- [ ] Sync/async mode phù hợp RPO.
- [ ] `synchronous_commit` và `synchronous_standby_names` được hiểu rõ.
- [ ] Quorum commit và quorum control plane được phân biệt.
- [ ] Failover candidate selection dựa trên WAL position.
- [ ] Fencing đã được test.
- [ ] Split brain scenarios đã được drill.
- [ ] Client retry/idempotency được thiết kế.
- [ ] Failback/rebuild standby có runbook.

### 24.4. Backup and DR

- [ ] Base backup và WAL archive liên tục.
- [ ] Immutable/offsite copy theo threat model.
- [ ] Backup retention bảo vệ PITR window.
- [ ] Timeline history được giữ.
- [ ] Keys/secrets có quy trình recovery độc lập.
- [ ] Restore test chứng minh RPO/RTO.
- [ ] Logical backup có cho selective recovery khi cần.

### 24.5. Capacity and monitoring

- [ ] Standby đủ capacity cho peak workload.
- [ ] WAL replay throughput lớn hơn hoặc theo kịp generation rate.
- [ ] Storage headroom đủ cho WAL/backup/recovery.
- [ ] Connection storm được kiểm soát.
- [ ] Potential RPO được giám sát.
- [ ] RTO phase timestamps được ghi.
- [ ] Archive/slot/disk/replication alerts có owner/runbook.
- [ ] DR region quota/capacity đã được kiểm tra.

### 24.6. Operations

- [ ] Runbook có người chịu trách nhiệm và quyền truy cập.
- [ ] On-call có thể fencing/promote an toàn.
- [ ] Manual failover được thực hành.
- [ ] AZ/region drills có lịch.
- [ ] Mỗi drill ghi observed RPO/RTO và follow-ups.
- [ ] Thay đổi OS/DB/network/IAM đều trigger review HA/DR.

## 25. Bài tập thực hành: RPO, RTO và multi-failure-domain

Các bài tập dùng lab hoặc tình huống giả lập. Không thực hiện fencing, partition, failover hay destructive operation trên production chỉ để làm bài. Với cấu hình phụ thuộc version/provider, đọc tài liệu đúng phiên bản.

### Bài 1 — Định nghĩa RPO

Giải thích RPO bằng ngôn ngữ business. Phân biệt target RPO với observed RPO.

### Bài 2 — Định nghĩa RTO

Một hệ thống báo PostgreSQL start lại sau 20 giây nhưng ứng dụng kết nối lại sau 8 phút. RTO nên đo tới mốc nào? Vì sao?

### Bài 3 — Tính RPO từ lag

Primary gặp sự cố lúc 10:00:00, standby đã replay dữ liệu tới 09:59:42. Ước lượng RPO và nêu các giả định còn thiếu.

### Bài 4 — RPO không phải backup interval

Backup chạy mỗi 5 phút nhưng WAL archive bị lỗi 20 phút. Vì sao không thể khẳng định RPO là 5 phút?

### Bài 5 — RTO decomposition

Một failover mất 12 phút. Hãy chia thành detection, decision, fencing, promotion, endpoint switching và validation; đề xuất metric cho mỗi bước.

### Bài 6 — Availability calculation

Tính downtime tối đa trong 30 ngày cho availability 99.9% và 99.99%. Nêu giả định tháng có 30 ngày.

### Bài 7 — MTPD

Business chỉ chịu gián đoạn 60 phút. Vì sao RTO 60 phút không an toàn? Đề xuất khoảng dự phòng.

### Bài 8 — RPO theo failure scenario

Một hệ thống có sync standby cùng AZ và async standby ở region khác. Đặt RPO riêng cho host, AZ và region; giải thích trade-offs.

### Bài 9 — Failure domain

Hai PostgreSQL VMs ở hai host khác nhau nhưng cùng dùng một storage array. Những failure nào vẫn có thể làm mất cả hai?

### Bài 10 — Multi-AZ

Vẽ topology primary ở AZ-a và standby ở AZ-b. Bổ sung control plane, client endpoint, backup và WAL archive.

### Bài 11 — Multi-region

Thiết kế active-passive giữa Region A và B. Liệt kê các dependencies ngoài database cần có ở region B.

### Bài 12 — HA vs DR

Phân biệt HA và DR bằng hai ví dụ sự cố. Vì sao backup không tự tạo HA?

### Bài 13 — Sync replication

Giải thích sự khác nhau giữa asynchronous và synchronous replication về commit acknowledgment, latency và potential data loss.

### Bài 14 — synchronous_commit

So sánh `remote_write`, `on` và `remote_apply`. Setting nào chờ standby replay WAL?

### Bài 15 — synchronous_standby_names

Giải thích `FIRST 1` và `ANY 2`. Nêu tình huống một standby không còn đủ để satisfy quorum.

### Bài 16 — Sync standby outage

Primary vẫn khỏe nhưng synchronous standby mất kết nối. Điều gì xảy ra với commit? Đề xuất policy fail-closed và fail-open.

### Bài 17 — Cross-region sync

Vì sao synchronous replication qua region có thể làm commit latency tăng? Network partition ảnh hưởng availability thế nào?

### Bài 18 — Replication lag

Phân biệt send, write, flush và replay lag. Chỉ số nào gần với WAL đã durable trên standby?

### Bài 19 — RPO monitoring

Viết query lấy LSN primary và standby. Giải thích vì sao phải xét timeline khi so sánh.

### Bài 20 — Quorum

Một consensus group có 5 voters. Majority quorum cần bao nhiêu phiếu? Có thể mất tối đa bao nhiêu voters mà vẫn có quorum?

### Bài 21 — Witness

Witness có lưu PostgreSQL data không? Nó giúp gì khi chỉ có hai data nodes?

### Bài 22 — Fencing

Nêu ba cách fencing primary cũ. Vì sao chỉ đổi DNS record không đủ?

### Bài 23 — Split brain

Hai primaries cùng nhận writes. Nêu hậu quả và giải thích vì sao PostgreSQL physical replication không tự merge histories.

### Bài 24 — DCS quorum vs sync quorum

Phân biệt quorum của DCS/leader election và quorum của synchronous replication.

### Bài 25 — Candidate selection

Hai standbys có replay LSN khác nhau. Làm sao chọn node promotion để giảm data loss? Cần kiểm tra gì ngoài LSN?

### Bài 26 — Multi-AZ failure

AZ-a mất nhưng primary có thể vẫn sống qua một network path khác. Quy trình nào ngăn promote standby gây split brain?

### Bài 27 — Region partition

Region A và B mất kết nối nhưng đều hoạt động. Vì sao không nên tự động promote B chỉ vì B không thấy A?

### Bài 28 — Failback

Sau khi promote Region B, vì sao không bật lại Region A thành primary? Mô tả rebuild/rewind và switchover.

### Bài 29 — Backup vs replication

Một DROP TABLE được replicate sang standby. Cơ chế nào giúp lấy lại table? Vì sao standby không đủ?

### Bài 30 — PITR

Mô tả quy trình restore base backup + WAL archive tới trước transaction gây lỗi. Vì sao nên restore sang cluster tạm trước?

### Bài 31 — Capacity N+1

Primary dùng 70% CPU ở peak, standby chỉ có 4 vCPU so với primary 16 vCPU. Những rủi ro gì khi promote?

### Bài 32 — WAL replay

Primary tạo WAL 300 MB/s, standby replay 250 MB/s liên tục. Lag sẽ thay đổi thế nào theo thời gian? Đề xuất giải pháp.

### Bài 33 — Catch-up time

Standby lag 60 GB, net replay throughput 120 MB/s. Tính thời gian lý thuyết và nêu các yếu tố làm thời gian thực tế dài hơn.

### Bài 34 — Disk capacity

Replication slot giữ 500 GB WAL khi standby offline. Những cảnh báo/giới hạn nào cần có để bảo vệ primary disk?

### Bài 35 — Connection storm

Sau failover 3.000 application connections reconnect đồng thời. Thiết kế pool/retry/jitter và capacity controls.

### Bài 36 — Control plane failure

DCS đặt trong một AZ duy nhất và AZ đó mất. Vì sao database multi-AZ vẫn có thể không tự failover?

### Bài 37 — DNS TTL

Database mới đã promote nhưng clients vẫn kết nối primary cũ. Liệt kê nguyên nhân DNS/client cache và giải pháp endpoint.

### Bài 38 — IAM/KMS dependency

Primary và standby ở hai AZ nhưng cùng dùng một KMS key bị disable. Vì sao đây vẫn là common failure domain?

### Bài 39 — RPO 0

Một hệ thống tuyên bố RPO 0. Hãy liệt kê failure assumptions cần nêu để tuyên bố này có ý nghĩa.

### Bài 40 — RTO vài phút

Một cluster 6 TB cần restore từ object storage trong 90 phút. Muốn RTO 5 phút, topology cần thay đổi thế nào?

### Bài 41 — Multi-region active-active

Vì sao hai PostgreSQL physical primaries không thể cùng ghi một replication history? Nêu các vấn đề conflict/key allocation nếu dùng logical active-active.

### Bài 42 — Managed database

Nhà cung cấp quảng cáo Multi-AZ. Viết 8 câu hỏi cần hỏi để xác minh RPO/RTO, fencing, backup và cross-region DR.

### Bài 43 — Cost trade-off

So sánh chi phí compute/storage/network/operations của một primary + một standby với multi-AZ + multi-region + immutable backup.

### Bài 44 — Failure matrix

Tạo bảng process/host/AZ/region/logical corruption/ransomware và điền RPO, RTO, recovery method, owner.

### Bài 45 — Failover drill

Thiết kế drill mô phỏng primary host loss, gồm fencing, promotion, endpoint switching, application validation và rebuild standby.

### Bài 46 — Network partition drill

Trong lab, mô phỏng mất kết nối primary/standby/control plane. Tiêu chí pass là gì để chứng minh không split brain?

### Bài 47 — DR drill

Thiết kế một bài kiểm tra region failover và failback. Đo thời gian từng bước và observed RPO.

### Bài 48 — Logical corruption drill

Tạo một transaction xóa nhầm trong lab, restore PITR tới trước transaction và export lại dữ liệu. Ghi RTO.

### Bài 49 — Monitoring design

Thiết kế dashboard hiển thị role, LSN gaps, sync state, WAL archive, potential RPO, disk headroom và RTO history.

### Bài 50 — Capstone: kiến trúc PostgreSQL nhiều vùng lỗi

Một hệ thống xử lý thanh toán có 2 TB dữ liệu, 5.000 transactions/second vào peak, RPO dưới 30 giây khi mất AZ, RTO 5 phút khi mất host, RPO 5 phút/RTO 2 giờ khi mất region. Ứng dụng chạy ở ba AZ, có một dịch vụ KMS và object storage backup.

**Yêu cầu:**

1. Chọn primary/standby topology và đặt sync/async mode.
2. Đề xuất vị trí các nodes và DCS voters để chịu lỗi AZ.
3. Xác định fencing mechanism và candidate promotion policy.
4. Thiết kế async cross-region DR và WAL archive.
5. Tính capacity headroom cho peak workload và failover.
6. Xác định backup retention, immutable copy và key recovery.
7. Thiết kế endpoint routing, connection pooling và idempotent retries.
8. Lập failure matrix cho host/AZ/region/logical/ransomware.
9. Thiết kế monitoring potential RPO và các phase của RTO.
10. Viết failover, failback, PITR và full-region DR runbooks.
11. Xây dựng drill schedule và acceptance criteria.
12. Phân tích chi phí/latency/availability và xin business sign-off cho trade-offs.

**Tiêu chí đạt:** mỗi failure scenario có RPO/RTO rõ, topology có đủ failure isolation, promotion không tạo split brain, backup/PITR bảo vệ logical errors và kết quả được chứng minh bằng drills.

## 26. Câu hỏi thường gặp

### 26.1. RPO 0 có nghĩa là không bao giờ mất dữ liệu không?

Không. RPO 0 chỉ có ý nghĩa trong failure assumptions đã nêu, thường cho commits được xác nhận bởi synchronous replication. Nó không bảo vệ trước logical deletion, corruption được replicate, mất tất cả failure domains hoặc lỗi storage/flush không tuân thủ.

### 26.2. RTO có phải thời gian PostgreSQL start không?

Không. RTO thường tính tới khi dịch vụ/application đáp ứng yêu cầu. Cần bao gồm detection, decision, fencing, promotion/restore, endpoint switching và validation.

### 26.3. Synchronous replication có làm primary luôn sẵn sàng không?

Không. Nó tăng durability của acknowledged commits nhưng có thể block writes khi synchronous standby không khả dụng. Availability và commit latency phải được cân bằng theo policy.

### 26.4. Asynchronous replication có luôn mất dữ liệu khi failover không?

Không. Nếu standby đã nhận/flush mọi WAL cần thiết trước khi primary mất, data loss có thể bằng 0. Nhưng cơ chế này không bảo đảm điều đó trong mọi failure timing.

### 26.5. Multi-AZ có bảo vệ mất region không?

Không đầy đủ. Multi-AZ bảo vệ một số lỗi trong region. Cần cross-region DR và backup độc lập để xử lý region-wide failures.

### 26.6. Multi-region có tự động đồng nghĩa HA?

Không. Cần replication, fencing, leader election, endpoint switching, dependencies và runbooks. Chỉ có một replica ở region khác chưa tạo thành failover an toàn.

### 26.7. Hai PostgreSQL nodes có đủ để tránh split brain không?

Không tự động. Khi network partition, mỗi node có thể nghĩ node kia chết. Cần quorum/witness hoặc fencing mechanism đáng tin cậy.

### 26.8. Witness có thay standby được không?

Không. Witness giúp quyết định leadership nhưng không chứa database data/WAL để phục vụ ứng dụng.

### 26.9. Quorum 3 voters chịu được bao nhiêu lỗi?

Majority quorum là 2/3, nên có thể tiếp tục quyết định khi mất một voter nếu protocol/placement đúng. Mất hai voters thì không còn quorum.

### 26.10. Quorum của DCS có bảo đảm standby mới nhất không?

Không. Nó quyết định leadership. Cần thêm candidate selection theo WAL position và synchronous replication guarantees.

### 26.11. Có nên synchronous replicate qua region?

Chỉ khi business cần RPO rất thấp và chấp nhận WAN commit latency cũng như write blocking khi partition. Nhiều hệ thống dùng sync trong region và async cross-region.

### 26.12. `remote_write` có durable như `on` không?

Không. `remote_write` chờ WAL được ghi tới OS trên standby; `on` chờ flush durable theo semantics PostgreSQL. Hiểu rõ storage flush behavior của platform.

### 26.13. `remote_apply` có cần cho mọi ứng dụng?

Không. Nó hữu ích khi cần read-after-write trên standby. Nó tăng latency và không bảo đảm external systems/cache đã cập nhật.

### 26.14. Standby có thể phục vụ writes không?

Physical standby trong recovery mode là read-only. Sau promotion, node trở thành primary và có thể nhận writes.

### 26.15. Streaming replication có thay WAL archive không?

Không. Streaming phục vụ standby đang hoạt động; WAL archive hỗ trợ PITR, phục hồi sau mất standby và các recovery scenarios dài hạn.

### 26.16. Backup có thay standby không?

Không. Restore backup thường chậm hơn promotion standby. Backup bảo vệ dữ liệu lâu dài và logical errors; standby phục vụ HA.

### 26.17. Replication có bảo vệ khỏi DROP TABLE không?

Không. WAL của thao tác DROP được replicate. Dùng PITR hoặc logical backup/restore để lấy lại dữ liệu.

### 26.18. Nếu standby lag vượt RPO thì phải promote không?

Không tự động. Đánh giá primary/WAL tail còn có thể lấy được không, chọn node có LSN mới nhất và báo business về potential data loss.

### 26.19. Failover có thể tự động hoàn toàn không?

Có thể tự động trong một số topology, nhưng phải có fencing, quorum, candidate selection và test cho network partitions. Các tình huống không rõ ràng cần manual escalation.

### 26.20. Chuyển DNS có phải fencing không?

Không. DNS không ngăn clients kết nối trực tiếp tới primary cũ. Fencing phải làm node cũ không thể nhận writes.

### 26.21. Vì sao client cần idempotency?

Nếu connection đứt trong COMMIT, client không biết transaction đã commit hay chưa. Idempotency key/unique constraint giúp retry mà không tạo duplicate business action.

### 26.22. Standby nhỏ hơn primary có được không?

Có thể cho workloads thấp, nhưng sau promotion có thể không chịu được peak. Đo replay và production throughput rồi giữ headroom phù hợp.

### 26.23. Một standby có đủ cho DR không?

Nó có thể bảo vệ một số failures nhưng không bảo vệ logical corruption, ransomware hoặc mất toàn bộ region/account. Cần backup và WAL archive độc lập.

### 26.24. RPO được đo bằng timestamp hay LSN?

Business thường diễn đạt bằng thời gian; kỹ thuật nên theo dõi LSN/commit state và timestamps. Timestamp replay có thể cũ khi workload idle nên không đủ một mình.

### 26.25. RTO nên tính tới khi nào?

Tới mốc business/service đã định nghĩa, thường là first successful application request hoặc full service restored. Ghi riêng stabilization/cleanup nếu không nằm trong RTO.

### 26.26. Multi-AZ có tăng availability 100% không?

Không. Có thể vẫn gặp common-mode failure, control-plane outage, bugs, operator errors, dependency outages và failover mistakes.

### 26.27. Cross-region standby có cần đủ compute không?

Cần đủ capacity hoặc một kế hoạch scale-up đã được kiểm thử. Nếu phải chờ quota/instance provisioning quá lâu, RTO sẽ không đạt.

### 26.28. Làm sao chứng minh RPO/RTO?

Đo replication/archive lag và chạy drills có timestamp. Ghi observed recovery point, từng phase duration, application validation và các blockers.

### 26.29. Bao lâu nên chạy DR drill?

Theo criticality và policy; hệ thống quan trọng thường cần component/failover drills thường xuyên và full-region drills định kỳ. Chạy lại sau thay đổi lớn.

### 26.30. Kiến trúc nào tốt nhất?

Kiến trúc phù hợp là kiến trúc đáp ứng RPO/RTO theo từng failure scenario, có failure isolation và có thể vận hành/kiểm thử trong ngân sách. Không có topology tối ưu cho mọi workload.

## 27. Tài liệu PostgreSQL chính thức

Các liên kết sau trỏ tới tài liệu PostgreSQL hiện hành. Chọn đúng major version và kiểm tra semantics của synchronous replication, recovery và views trước khi triển khai:

- [High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/current/high-availability.html): tổng quan HA, replication và failover.
- [Warm Standby Servers](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication và standby operation.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous standby và acknowledgment behavior.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): `synchronous_standby_names`, `synchronous_commit`, slots và WAL senders.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): durability và WAL settings.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và PITR.
- [Recovery Configuration](https://www.postgresql.org/docs/current/recovery-config.html): restore command, recovery signals và targets.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): replication, archiver và statistics views.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo physical base backup và standby.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): kiểm tra backup manifest.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): tái đồng bộ node sau failover.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): kiểm tra data page checksums offline.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): nâng cấp major version.

## 28. Tổng kết

RPO và RTO phải bắt đầu từ business impact, được xác định riêng cho từng failure scenario và được kiểm chứng bằng monitoring/drills. Multi-AZ và multi-region chỉ hữu ích khi các nodes, storage, network, control plane, identity, backup và vận hành được phân tách theo failure domains phù hợp.

| Thành phần | Vai trò |
| --- | --- |
| RPO | Giới hạn lượng dữ liệu chấp nhận mất |
| RTO | Giới hạn thời gian khôi phục dịch vụ |
| Synchronous replication | Giảm data loss cho acknowledged commits theo failure assumptions |
| Asynchronous replication | Giảm commit latency, có thể có WAL tail chưa replicate |
| Quorum/fencing | Chọn đúng primary và ngăn split brain |
| Multi-AZ | Chịu lỗi một vùng hạ tầng trong region |
| Multi-region DR | Phục hồi khi region chính gặp thảm họa |
| Base backup + WAL archive | PITR và phục hồi khi replicas không đủ |
| Immutable/offsite backup | Chống logical errors, ransomware và xóa bản sao |
| Restore/failover drills | Chứng minh RPO/RTO thực tế |

Một kiến trúc tốt không chỉ có nhiều bản sao. Nó phải biết bản sao nào được phép ghi, bản sao nào có dữ liệu mới nhất, làm sao ngăn primary cũ tiếp tục hoạt động, và cách khôi phục khi cả replication lẫn hạ tầng chính bị ảnh hưởng.

**Hãy thiết kế theo failure scenario, đo bằng RPO/RTO thực tế và kiểm thử cả failover lẫn failback.** HA duy trì dịch vụ qua lỗi thành phần; DR khôi phục sau thảm họa lớn; backup/PITR bảo vệ dữ liệu trước lỗi logic và các sự cố lan qua mọi replicas.
