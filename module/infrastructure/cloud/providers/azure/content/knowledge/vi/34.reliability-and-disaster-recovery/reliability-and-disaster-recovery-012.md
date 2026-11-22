# Diễn tập DR và đánh giá sau sự cố

## 1. Mục tiêu của bài học

**Disaster Recovery (DR, khôi phục thảm họa)** là khả năng khôi phục dịch vụ và dữ liệu về mức chấp nhận được sau sự cố nghiêm trọng. Một bản thiết kế DR chỉ đáng tin khi đội vận hành đã **diễn tập**, đo lường được kết quả, phát hiện lỗ hổng và sửa chúng. Có backup, replica hoặc một region dự phòng chưa chứng minh hệ thống khôi phục được trong giới hạn mà nghiệp vụ yêu cầu.

Trong chương **Độ tin cậy và khôi phục thảm họa** của module `CLOUD_PROVIDERS_AZURE`, bài này đưa các thành phần Azure — subscription, resource group, Microsoft Entra ID, mạng ảo, máy ảo hoặc dịch vụ ứng dụng, lưu trữ, cơ sở dữ liệu, giám sát, bảo mật và kiểm soát chi phí — vào một quy trình thực hành: **chuẩn bị → diễn tập DR → thu thập bằng chứng → đánh giá sau sự cố → cải tiến → diễn tập lại**.

Sau bài học, người học có thể:

1. Phân biệt bài kiểm thử DR với bài kiểm thử HA, backup và xử lý sự cố thực tế.
2. Lập kế hoạch diễn tập với mục tiêu RTO/RPO, phạm vi, điều kiện an toàn, người chịu trách nhiệm và tiêu chí dừng.
3. Chọn kịch bản mất zone, mất region, mất dữ liệu hoặc mất dependency; diễn tập failover/failback phù hợp với dịch vụ Azure.
4. Ghi timestamp, đo downtime, mức mất dữ liệu, độ toàn vẹn dữ liệu và năng lực phục vụ sau chuyển đổi.
5. Viết post-incident review không quy lỗi cá nhân, phân tích nguyên nhân và theo dõi hành động phòng ngừa bằng kết quả đo được.

**Kết quả cuối cùng của một lần diễn tập không chỉ là “đã chuyển sang dự phòng” mà phải là bằng chứng rằng người dùng vẫn thực hiện được các giao dịch quan trọng, dữ liệu đáp ứng RPO, thời gian khôi phục đáp ứng RTO và đội vận hành có thể lặp lại quy trình.**

## 2. Phân biệt HA, DR, backup và các loại kiểm thử

| Khái niệm | Vấn đề giải quyết | Cách đánh giá |
| --- | --- | --- |
| **High Availability (HA)** | Giảm gián đoạn khi một instance, node hoặc Availability Zone bị lỗi | Rút một replica/zone khỏi đường phục vụ; xác minh khả năng tự chuyển tải |
| **Disaster Recovery (DR)** | Khôi phục dịch vụ khi mất một môi trường, region hoặc nhóm dependency quan trọng | Thực hiện chuyển sang môi trường dự phòng, kiểm tra dữ liệu và luồng nghiệp vụ |
| **Backup & restore** | Lấy lại trạng thái dữ liệu từ một thời điểm hoặc phiên bản phù hợp | Khôi phục bản sao đến môi trường cách ly, kiểm tra tính nhất quán và khả năng sử dụng |
| **Business Continuity (BC)** | Duy trì quy trình kinh doanh và hoạt động con người trong khủng hoảng | Diễn tập liên lạc, vận hành thủ công, ưu tiên dịch vụ và điều phối quyết định |
| **Incident response** | Phát hiện, khoanh vùng, ứng phó sự cố đang diễn ra | Kiểm tra cảnh báo, phân vai, truyền thông và quy trình ra quyết định |
| **Post-incident review** | Học từ những gì đã xảy ra để giảm xác suất/tác động của lỗi kế tiếp | Phân tích timeline, nguyên nhân hệ thống, hành động khắc phục và kiểm thử lại |

Một hệ thống có thể **chạy đa Availability Zone trong một region** nhưng chưa có DR nếu toàn bộ region ngừng hoạt động. Ngược lại, một bản backup đặt ở nơi khác có thể giúp khôi phục dữ liệu nhưng không bảo đảm API, DNS, danh tính, quyền truy cập và mạng được dựng lại kịp mục tiêu.

Bài diễn tập cần mô tả rõ đang kiểm tra **lớp nào**, bởi nếu chỉ tắt một VM rồi thấy load balancer chuyển lưu lượng, kết quả đó chưa chứng minh năng lực DR cấp region.

### 2.1. Các mức trưởng thành của diễn tập

| Mức | Hoạt động | Điều chứng minh được | Giới hạn |
| --- | --- | --- | --- |
| **Tabletop** | Nhóm đi theo kịch bản trên giấy, thảo luận quyết định và runbook | Vai trò, sơ đồ phụ thuộc, bước thực hiện và điểm chưa rõ | Chưa chứng minh hệ thống kỹ thuật phục hồi được |
| **Component restore** | Khôi phục database, VM hoặc tệp từ backup sang môi trường thử | Bản sao lưu có thể dùng và quy trình restore hoạt động | Chưa chứng minh toàn bộ luồng nghiệp vụ |
| **Isolated test failover** | Dựng bản DR trên mạng cô lập, kiểm thử ứng dụng và dữ liệu | Có thể khởi chạy workload ở môi trường dự phòng | Chưa chứng minh đổi tuyến lưu lượng thực tế |
| **Controlled switchover** | Chuyển lưu lượng thử nghiệm hoặc có kiểm soát tới DR | Đường vào, danh tính, phụ thuộc và vận hành end-to-end | Cần quản trị thay đổi, rollback và kiểm soát dữ liệu ghi |
| **Full exercise** | Thử quy trình từ phát hiện đến phục hồi và trở về ổn định | RTO/RPO thực tế, tính sẵn sàng của tổ chức và năng lực vận hành | Chi phí/rủi ro cao hơn; phải giới hạn phạm vi phù hợp |

Có thể tăng dần mức diễn tập qua từng kỳ. Không nên dùng kết quả tabletop thay cho phép đo RTO của một lần failover hoàn chỉnh.

## 3. Chuyển yêu cầu nghiệp vụ thành mục tiêu đo được

Trước khi viết runbook, hãy chọn các **giao dịch nghiệp vụ ưu tiên** và thỏa thuận điều gì được xem là phục hồi thành công. Ví dụ hệ thống `orders` có hai luồng: khách hàng đặt đơn và quản trị viên xem đơn đã tạo.

### 3.1. SLI/SLO, RTO, RPO, MTTD và MTTR

| Chỉ số | Ý nghĩa | Cách đo trong diễn tập |
| --- | --- | --- |
| **SLI** | Chỉ báo mức dịch vụ, như tỷ lệ đặt đơn thành công, p95 latency | Probe từ ngoài hệ thống cùng telemetry giao dịch thực |
| **SLO** | Mục tiêu của SLI trong một cửa sổ thời gian | So kết quả quan sát với ngưỡng đã thỏa thuận |
| **RTO** (*Recovery Time Objective*) | Thời gian tối đa cho phép từ khi dịch vụ gián đoạn đến lúc khôi phục mức chấp nhận được | `T_recovered - T_impact`, dựa trên tiêu chí khôi phục đã định nghĩa |
| **RPO** (*Recovery Point Objective*) | Mức mất dữ liệu tối đa chấp nhận được khi khôi phục | So trạng thái dữ liệu đã xác nhận trước lỗi với dữ liệu còn sau failover/restore |
| **MTTD** (*Mean Time To Detect*) | Trung bình thời gian từ khi lỗi gây tác động đến lúc phát hiện | Đo qua nhiều sự cố/bài diễn tập, không suy từ một lần |
| **MTTR** (*Mean Time To Recover/Repair*) | Trung bình thời gian phục hồi/sửa chữa theo định nghĩa tổ chức | Đo qua nhiều sự cố với mốc bắt đầu và kết thúc thống nhất |

**Ví dụ giả định do doanh nghiệp lựa chọn**, không phải SLA hay cam kết của Azure:

- Mục tiêu RTO cho đặt đơn: **30 phút**.
- Mục tiêu RPO cho các đơn đã được xác nhận: **5 phút**.
- Sau khi phục hồi, tỷ lệ giao dịch đặt đơn thành công phải đạt tối thiểu **99%** trong cửa sổ quan sát 10 phút; p95 latency dưới **2 giây**.
- Mục tiêu thông báo lần đầu cho người điều phối và nhóm liên quan: **trong 5 phút** sau phát hiện.

Với đơn hàng có giao dịch tài chính, RPO 5 phút có thể **không chấp nhận được**. Cần nghiệp vụ xác định chính xác dữ liệu nào phải bảo toàn và liệu có cơ chế đối soát, bù trừ, replay hoặc idempotency hay không.

### 3.2. Cách đo RTO/RPO tránh kết luận sai

Định nghĩa mốc:

~~~text
T_impact     = 10:00:00   Người dùng bắt đầu không thể đặt đơn
T_detected   = 10:02:10   Cảnh báo/nhân sự phát hiện
T_declared   = 10:04:00   Incident Commander quyết định thực thi DR
T_failover   = 10:17:00   Chuyển tuyến/drain traffic xong
T_recovered  = 10:22:30   Giao dịch đạt SLI/SLO định nghĩa trước
~~~

**RTO thực đo** = 22 phút 30 giây, tính từ `T_impact` đến `T_recovered`. Nếu tính từ `T_declared` sẽ bỏ qua thời gian phát hiện và ra quyết định, khiến báo cáo lạc quan hơn thực tế.

**RPO không đo bằng độ dài downtime.** Cần dùng dữ liệu chứng minh:

- `last_acknowledged_write`: sự kiện ghi cuối đã thông báo thành công cho người dùng trước sự cố.
- `last_recoverable_write`: sự kiện mới nhất có mặt và hợp lệ trong môi trường sau khôi phục.
- Tập các sự kiện có ID duy nhất để đối chiếu **mất, trùng, sai thứ tự và dữ liệu mồ côi**.

Nếu tại 10:00:00 phát sinh lỗi, bản ghi đã xác nhận cuối có ở 09:59:50 nhưng bản sao phục hồi chỉ có đến 09:57:00, khoảng dữ liệu có nguy cơ mất là khoảng **2 phút 50 giây** tính đến điểm phục hồi, đồng thời phải đối soát các bản ghi cụ thể để biết mất thực tế. Đo theo timestamp chỉ là xấp xỉ khi đồng hồ lệch, ghi bất đồng bộ hoặc dữ liệu đến không đúng thứ tự. Luôn bổ sung đối soát bằng transaction ID và trạng thái commit.

### 3.3. Tiêu chí thành công đa chiều

Một bài diễn tập không đạt nếu API có HTTP 200 nhưng không thể đọc đơn, gửi thông báo hoặc xử lý queue. Quy định tiêu chí bao gồm:

1. **Availability:** những hành trình người dùng nào hoạt động, đạt SLI nào?
2. **Data integrity:** bản ghi đã xác nhận còn đủ, không có duplicate, khóa chính và quan hệ hợp lệ?
3. **Security:** quyền RBAC, Managed Identity, Key Vault, kết nối TLS, audit log còn đúng khi ở DR?
4. **Operations:** dashboards, alerts, logs, người trực và quy trình hỗ trợ có theo dõi được môi trường DR?
5. **Performance/capacity:** môi trường dự phòng chịu được tải dự kiến và backlog sau failover?
6. **Cost:** chi phí phục hồi, nhân bản, truyền dữ liệu và tài nguyên DR tạm thời có trong ngân sách?

## 4. Kiểm kê hệ thống và dựng sơ đồ dependency

Trong Azure, service DR thực tế liên quan nhiều subscription/resource group và dịch vụ phụ trợ. Ví dụ một kiến trúc:

~~~mermaid
flowchart TB
    C["Client / mobile / web"] --> DNS["DNS / Front Door / ingress"]
    DNS --> API["API vùng chính"]
    API --> DB["Cơ sở dữ liệu chính"]
    API --> Q["Queue / broker"]
    Q --> W["Worker"]
    W --> ST["Blob Storage"]
    API --> ID["Entra ID / Managed Identity"]
    API --> KV["Key Vault"]
    API --> NET["VNet / Private DNS / Private Endpoint"]
    M["Azure Monitor / Log Analytics"] -.-> API
    M -.-> DB
    M -.-> Q
    DAPI["API vùng dự phòng"] --> DDB["Dữ liệu vùng dự phòng"]
    DNS -. "Điều hướng khi failover" .-> DAPI
    DB -. "Nhân bản / backup theo cấu hình" .-> DDB
~~~

Mũi tên nét đứt là **khả năng thiết kế** cần được cấu hình và xác minh, không hàm ý Azure tự động nhân bản mọi dịch vụ. Chẳng hạn ứng dụng có thể chạy ở region dự phòng nhưng không truy cập được Key Vault, DNS, hoặc Private Endpoint của database.

Tạo một bản kiểm kê có thể điền:

| Thành phần | Chủ sở hữu | Primary / DR | Phương thức phục hồi | Bằng chứng cần thu |
| --- | --- | --- | --- | --- |
| Frontend/ingress | Nhóm platform | Cấu hình địa chỉ, route, DNS ở cả hai môi trường | Đổi tuyến/ưu tiên vùng khỏe | Route đã cập nhật, probe từ bên ngoài |
| Compute/API | Nhóm ứng dụng | Replica hoặc bản triển khai được dựng sẵn ở DR | Scale/khởi động từ IaC và image đã kiểm soát | Deployment hash, readiness, SLI |
| Database | Nhóm dữ liệu | Replica/failover group hoặc backup phù hợp | Promote/failover hoặc restore | Transaction IDs, point-in-time, RPO |
| Blob/storage | Nhóm dữ liệu | Redundancy phù hợp nhu cầu | Đọc replica/khôi phục bản sao | Object checksum, khả năng truy cập |
| Queue/worker | Nhóm ứng dụng | DR broker hoặc kế hoạch drain/replay | Chuyển consumer, xử lý lại | Message ID, duplicate, backlog |
| VNet/DNS/Private Endpoint | Nhóm mạng | Cấu hình tại cả hai nơi | Chuyển route/endpoint có kiểm soát | DNS resolve, kết nối TLS |
| Identity/Key Vault | Nhóm an ninh | Danh tính, vai trò, secrets và keys có kế hoạch DR | Khôi phục truy cập và quyền tối thiểu | RBAC, truy cập secret, audit |
| Monitoring | Nhóm SRE | Dashboard/cảnh báo cho cả primary và DR | Phát hiện và xác nhận trạng thái | Timeline, alerts, synthetic probes |

**Dependency phải được kiểm tra ở chiều đi và chiều về:** sau failover, worker ở DR có thể gửi message về một broker chỉ tồn tại ở primary; điều này tạo đường phụ thuộc ngầm vào vùng vừa hỏng. Cũng cần xác nhận quota, SKU, khả năng cấp phát VM và giới hạn dịch vụ trong vùng dự phòng.

## 5. Chọn kịch bản diễn tập có ý nghĩa

Không phải lỗi nào cũng cần failover toàn region. Hãy phân loại **phạm vi và hậu quả** trước khi chọn hành động.

| Kịch bản | Injection / giả lập an toàn | Hành động mong đợi | Điều cần đo |
| --- | --- | --- | --- |
| **Lỗi một instance** | Rút một backend thử nghiệm | Load balancer chuyển request sang backend khác | Tỷ lệ lỗi, thời gian loại backend |
| **Lỗi một AZ** | Cô lập tập backend tại zone trong môi trường thử | Các zone còn lại chịu tải, stateful tier vẫn hoạt động | N-1 capacity, độ trễ, quorum |
| **Mất primary region** | Bài tập tabletop hoặc failover có kiểm soát sang DR | Khôi phục đường vào, API, dữ liệu và dependencies ở DR | RTO/RPO, DNS, tình trạng queue, transaction |
| **Mất database/ghi nhầm** | Dùng tập dữ liệu kiểm thử và điểm backup đã biết | Khôi phục đúng point-in-time, đối soát dữ liệu | RPO, restore duration, integrity |
| **Lỗi mạng/private DNS** | Điều chỉnh policy/network trong môi trường cô lập | Phát hiện nguyên nhân, mở tuyến đúng không làm lộ dịch vụ | Reachability, TLS, cảnh báo |
| **Lỗi chứng thực/quyền** | Giả lập thiếu quyền bằng identity thử nghiệm | Quy trình xử lý giữ nguyên least privilege | Thời gian phát hiện, audit, khả năng phục hồi |
| **Lỗi release/config đồng loạt** | Deploy phiên bản lỗi có thể rollback ở staging | Dừng triển khai, rollback hoặc khôi phục cấu hình | Phát hiện lỗi, thời gian phục hồi, ngăn tái diễn |

Phân biệt **fault injection** (tạo tình huống lỗi kiểm soát), **test failover** (khởi tạo môi trường kiểm thử từ bản replication) và **real failover** (chuyển dịch vụ sản xuất). Không làm như thể ba thao tác luôn tương đương về mức rủi ro.

Chọn ít nhất một **happy path** và một **negative path**: chẳng hạn failover diễn ra nhưng một secret không có ở DR; hoặc môi trường DR chạy nhưng backlog queue tăng nhanh. Negative path giúp phát hiện các điểm chưa được mô hình hóa.

## 6. Kế hoạch diễn tập: điều kiện bắt đầu, phân vai và cơ chế dừng

Trước ngày diễn tập, lập kế hoạch thành một tài liệu có thể kiểm tra thay vì chỉ ghi “thử failover vào cuối tuần”.

### 6.1. Mẫu thẻ diễn tập (exercise charter)

~~~yaml
exercise_id: dr-orders-2026-11
system: orders
environment: staging-isolated
scenario: primary-region-unavailable
objectives:
  rto_minutes: 30
  rpo_minutes: 5
  essential_journeys:
    - create-order
    - read-order
    - process-order-event
scope:
  includes:
    - application
    - database
    - private-network
    - ingress
    - monitoring
  excludes:
    - production-payment-provider
roles:
  incident_commander: "Vị trí: SRE lead"
  exercise_controller: "Vị trí: người điều phối kiểm thử"
  application_owner: "Vị trí: lead ứng dụng"
  data_owner: "Vị trí: DBA / data engineer"
  observer: "Vị trí: người ghi timeline"
controls:
  data: synthetic-only
  outbound_notifications: disabled
  test_network: isolated
  stop_if: "Có traffic thật hoặc ảnh hưởng production ngoài phạm vi"
evidence:
  - timeline-utc
  - synthetic-transactions
  - monitoring-query-results
  - database-reconciliation
  - failover-operation-logs
~~~

Đây là **mẫu kế hoạch**, không phải cấu hình mà Azure tự thi hành. Thay các giá trị minh họa bằng môi trường, người phụ trách, tiêu chí và mốc thời gian thực tế.

### 6.2. Các vai trò cần phân biệt

- **Incident Commander (IC):** quyết định ưu tiên, chuyển trạng thái, phân công và truyền thông trong khuôn khổ đã được phê duyệt.
- **Exercise Controller:** điều phối kịch bản và injection, kiểm soát giới hạn thử nghiệm; có quyền dừng bài diễn tập.
- **Technical Leads:** ứng dụng, dữ liệu, network, platform; thực hiện và xác minh bước thuộc phạm vi phụ trách.
- **Observer/Scribe:** ghi thời điểm, kết quả, bằng chứng, giả định và mọi thao tác; hạn chế tham gia sửa lỗi nếu không được phân công.
- **Business representative:** xác nhận hành trình quan trọng đã phục hồi và quyết định mức suy giảm chấp nhận được.
- **Communications owner:** cập nhật trạng thái cho các bên liên quan; nội dung thử nghiệm phải được đánh dấu rõ.

Ở nhóm nhỏ có thể một người đảm nhiệm nhiều vai trò, nhưng **quyền quyết định** và **người ghi bằng chứng** vẫn cần được chỉ rõ.

### 6.3. Điều kiện Go / No-Go

Chỉ bắt đầu khi đã xác minh: môi trường test cô lập; backup/replica hiện diện và đủ mới; người có thẩm quyền đã chấp thuận phạm vi; các dịch vụ trả phí hoặc tài nguyên tạm có hạn mức; cơ chế quay lại/cleanup rõ ràng; dashboard và synthetic transaction hoạt động; dữ liệu kiểm thử không kích hoạt thanh toán, email hoặc webhooks thật.

**Stop condition** ví dụ: xuất hiện request từ khách hàng production vào môi trường thử, mất khả năng quan sát, replication có biểu hiện bất thường, hoặc thao tác vượt ra ngoài scope cho phép. Khi đó controller dừng injection, đóng băng thay đổi và đánh giá lại trạng thái; không cố đạt mục tiêu RTO bằng mọi giá.

## 7. Quy trình diễn tập DR theo thời gian

Một vòng diễn tập đầy đủ có các giai đoạn sau:

~~~mermaid
flowchart LR
    P["Chuẩn bị & baseline"] --> F["Tạo tình huống lỗi"]
    F --> D["Phát hiện & xác nhận"]
    D --> A["Quyết định chuyển sang DR"]
    A --> O["Failover / Restore"]
    O --> V["Kiểm thử end-to-end & dữ liệu"]
    V --> S["Ổn định và theo dõi"]
    S --> B["Failback / cleanup có kiểm soát"]
    B --> R["Post-incident review"]
    R --> X["Hành động khắc phục & diễn tập lại"]
~~~

### Giai đoạn A — Baseline trước khi gây lỗi

Trước injection, quan sát hệ thống khỏe:

1. Chụp sơ đồ kiến trúc và phiên bản triển khai (commit/image tag hoặc artifact ID).
2. Xác nhận resource group, subscription, region, SKU/tier, quota, identity và mục tiêu DNS/ingress.
3. Ghi chỉ số ban đầu: RPS, success rate, p95 latency, queue depth, replication health/lag và last successful backup.
4. Sinh tập **synthetic transactions** với ID duy nhất, có thể đối soát từ primary và DR.
5. Xác nhận dashboard, alert, người trực và kênh liên lạc; đồng bộ timezone/UTC trong nhật ký.

### Giai đoạn B — Kích hoạt sự cố có kiểm soát

Exercise Controller kích hoạt kịch bản đã duyệt, chẳng hạn tạm **không sử dụng** endpoint primary của môi trường thử để giả lập mất region. Ghi chính xác `T_impact`. Với test failover của giải pháp replication, tạo vùng thử cách ly thay vì cắt lưu lượng production.

Đánh giá xem cảnh báo phát hiện lỗi có đi qua đúng chuỗi **alert → on-call → nhận trách nhiệm → quyết định** hay không; observer chỉ ghi nhận, tránh tự sửa thay operator trừ khi vượt stop condition.

### Giai đoạn C — Quyết định và thực hiện phục hồi

IC xác nhận phạm vi lỗi, nêu chiến lược và rủi ro dữ liệu: “dùng bản sao DR có RPO dự kiến trong ngưỡng” hoặc “restore điểm backup gần nhất và đối soát các giao dịch chưa có”. Nhóm kỹ thuật thực hiện runbook **đúng dịch vụ**; không chọn bất kỳ lệnh failover chung nào cho toàn bộ Azure.

Các hành động có thể bao gồm: khởi chạy workload DR; kích hoạt vai trò database theo cách dịch vụ hỗ trợ; cấu hình ingress; bảo đảm DNS/Private DNS, certificates, Managed Identity, network rules và outbound access đúng. Nếu dữ liệu primary có thể đang nhận ghi, phải xử lý rủi ro **split-brain** và “hai nơi cùng được ghi” trước khi cho DR nhận giao dịch.

### Giai đoạn D — Xác minh từ góc nhìn người dùng

Không kết thúc tại thông báo “failover succeeded” của control plane. Chạy lại các giao dịch tổng hợp:

- Đặt đơn có idempotency key và nhận cùng một transaction ID khi thử lại.
- Đọc được đơn vừa tạo từ endpoint công khai/đường kết nối dự kiến.
- Xác minh message tạo ra được worker tiêu thụ đúng một lần về mặt nghiệp vụ dù broker có thể giao lại.
- Truy xuất các object/blob bắt buộc, kiểm tra checksum hoặc mã phiên bản.
- Xác minh đăng nhập, lấy secret, DNS resolve, TLS và audit.
- Tải thử ở mức thiết kế và theo dõi capacity của DR.

Ghi `T_recovered` **khi tiêu chí chấp nhận được đáp ứng liên tục** trong cửa sổ đã quy định, không phải khi bước kỹ thuật cuối vừa chạy xong.

### Giai đoạn E — Ổn định, failback và cleanup

Tùy kịch bản, môi trường DR có thể tiếp tục phục vụ hoặc quay về primary sau khi primary khỏe. **Failback là một thay đổi rủi ro riêng**: cần tái đồng bộ dữ liệu, chọn authoritative source, chặn ghi đồng thời trái phép, kiểm tra đường mạng và dữ liệu, thực hiện chuyển tuyến có kiểm soát rồi mới đưa primary vào phục vụ.

Nếu chỉ là test failover cách ly, hãy **cleanup** các VM/network/tài nguyên test theo quy trình dịch vụ, xác nhận replication của hệ thống gốc không bị ảnh hưởng. Không bỏ lại tài nguyên tính phí hoặc endpoint có thể bị truy cập ngoài ý muốn.

## 8. Áp dụng công cụ Azure theo từng mẫu DR

Mỗi dịch vụ có giới hạn và quy trình riêng. Những hướng dẫn dưới đây dùng để **chọn cách diễn tập**, không phải lệnh thao tác áp dụng cho mọi tài khoản.

### 8.1. Azure Site Recovery (ASR) cho workload được hỗ trợ

**Azure Site Recovery** hỗ trợ sao chép và điều phối khôi phục cho các loại VM/workload được hỗ trợ. Với **test failover**, ASR có thể khởi tạo bản VM phục hồi để kiểm thử, thường dùng một **mạng thử nghiệm riêng**.

Quy trình ở mức vận hành:

1. Xác nhận replication health, policy và recovery point, sự tương thích của workload, quyền và mạng thử.
2. Chọn đúng protected item hoặc recovery plan trong Recovery Services vault, khởi chạy **Test failover** bằng recovery point được chọn.
3. Truy cập VM phục hồi qua mạng test đã chuẩn bị; kiểm tra OS, dịch vụ, ứng dụng, DNS, kết nối đến dữ liệu test và giao dịch synthetic.
4. Ghi thời gian, kết quả, lỗi khởi động, khác biệt cấu hình và các thao tác thủ công.
5. Chạy **Cleanup test failover** theo quy trình ASR, xác nhận tài nguyên thử đã được xử lý và replication ban đầu vẫn khỏe.

**Test failover không đồng nghĩa failover production.** Khi failover thật, các bước commit, reprotect và failback khác nhau theo loại nguồn/đích; phải theo runbook cập nhật của chính workload. Không thực hiện unplanned failover chỉ để làm một bài kiểm thử khi test failover đáp ứng mục đích.

Nếu ứng dụng gồm nhiều VM có dependency, cần xem xét recovery plan, thứ tự khởi động, scripts và thời điểm database/queue thực sự sẵn sàng; VM ở trạng thái Running không có nghĩa ứng dụng đã phục hồi.

### 8.2. Azure Backup và phục hồi dữ liệu

Bài diễn tập **restore** phải chứng minh backup đọc được, khóa/quyền cho phép khôi phục, dữ liệu hợp lệ và thời gian restore phù hợp RTO. Ví dụ:

- Chọn recovery point với timestamp và retention đã kiểm tra.
- Restore vào **resource group hoặc đích kiểm thử** riêng nếu loại workload hỗ trợ.
- Giữ cách ly quyền/mạng và dùng dữ liệu không gây tác động tới production.
- Chạy kiểm tra schema, số bản ghi, khóa ngoại hoặc checksum, giao dịch ứng dụng.
- Ghi phần chênh lệch giữa recovery point và các write đã xác nhận, rồi áp dụng đối soát/replay nếu thiết kế hỗ trợ.

Không đánh dấu “RPO đạt” chỉ vì backup job có trạng thái Success: cần xem **điểm phục hồi thực sự có thể sử dụng** và nội dung dữ liệu sau restore. Backup có thể phục vụ khôi phục lỗi xóa nhầm hoặc corruption ngay cả khi replica DR cũng đã sao chép thay đổi sai.

### 8.3. Azure SQL và các dịch vụ dữ liệu có failover

Nếu dùng **Azure SQL Database failover groups** hoặc khả năng geo-replication/HA tương ứng, cần kiểm tra:

- Chính xác role primary/secondary, lag và tình trạng replication trước test.
- Ứng dụng dùng đúng listener/endpoint theo mô hình đã triển khai; DNS caching và connection pooling có thể ảnh hưởng thời gian chuyển.
- Tác động của **forced/unplanned failover** đến mất dữ liệu khi nhân bản bất đồng bộ; không cam kết RPO bằng 0 cho cross-region asynchronous replication.
- Thời gian ứng dụng reconnect, idempotency và các transaction có trạng thái không rõ ràng.
- Cơ chế failback, dữ liệu ghi trong thời gian ở DR và thứ tự tái đồng bộ.

Thực hiện chuyển vai trò trong **môi trường test** theo quy trình dịch vụ và quyền được cấp. Failover control plane thành công chưa đủ nếu ứng dụng vẫn trỏ tới endpoint cũ.

### 8.4. Azure Storage và lựa chọn redundancy

Azure Storage có các tùy chọn như **LRS, ZRS, GRS, GZRS** và những biến thể có khả năng đọc secondary tùy loại tài khoản/vùng được hỗ trợ. Khả năng nhân bản địa lý, đọc secondary và **account failover** là các khái niệm khác nhau.

Trước bất kỳ bài diễn tập storage failover, xác minh:

- SKU hiện tại có hỗ trợ thao tác dự kiến không.
- Dữ liệu được nhân bản **bất đồng bộ** ra region phụ có thể tồn tại độ trễ; ghi đã xác nhận tại primary có thể chưa xuất hiện tại secondary.
- Account failover có thể làm thay đổi trạng thái replication, chi phí hoặc cấu hình; không xem là thao tác test vô hại và dễ đảo ngược.
- Ứng dụng có phụ thuộc queue, table, file hoặc blob API nào bị giới hạn riêng không.

Đối với mục tiêu kiểm tra phục hồi, ưu tiên **đọc bản sao được hỗ trợ hoặc restore vào tài nguyên test** trước khi cân nhắc thao tác làm thay đổi tài khoản sản xuất.

### 8.5. Mạng, điều hướng lưu lượng và identity

Các lớp định tuyến như **Azure Front Door**, DNS, load balancer, Application Gateway và các cấu hình VNet/Private Endpoint có vai trò khác nhau. Chọn thành phần đúng kiến trúc, xác minh health probes, origin priorities và chính sách định tuyến. DNS TTL không bảo đảm mọi client chuyển đúng lúc vì có cache, kết nối tồn tại và resolver khác nhau.

Với DR cross-region, kiểm tra network security groups, routes, NAT/outbound dependencies, Private DNS Zone links, certificates, service endpoints và các giới hạn kết nối. Kiểm tra Managed Identity, RBAC, Azure Key Vault và quyền truy cập dữ liệu ở region/scope dự phòng; không sao chép bí mật thủ công qua log hoặc trang báo cáo.

### 8.6. Xác nhận phạm vi Azure trước khi diễn tập

Một số lệnh Azure CLI chỉ **đọc trạng thái**, thích hợp để thu bằng chứng trước và sau diễn tập:

~~~bash
# Xác minh subscription/tenant của phiên CLI đang dùng.
az account show \
  --query "{subscription:id, tenant:tenantId}" \
  -o json

# Kiểm kê resource trong resource group thử nghiệm.
az resource list \
  --resource-group rg-orders-dr-test \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# Xem cấu hình một tài nguyên đã biết ID.
az resource show \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-orders-dr-test/providers/<provider>/<type>/<resource-name>" \
  -o json
~~~

Ký hiệu `<...>` trong ví dụ là placeholder và phải được thay bằng resource ID thực. Các lệnh trên không kích hoạt failover. Quy trình failover có thể yêu cầu thao tác riêng tại Azure Portal, API hoặc CLI extension của dịch vụ đang dùng; người vận hành phải kiểm chứng cú pháp phù hợp và quyền trước khi chạy.

## 9. Thu bằng chứng: metric, log, timeline và dữ liệu

Để có thể đánh giá sau sự cố, hãy **định nghĩa bộ bằng chứng trước diễn tập**. Khi bắt đầu, observer ghi UTC timestamp, người thực hiện, hành động, kết quả và đường dẫn tới log/traces. Cần lưu thông tin đủ để tái hiện kết luận nhưng tránh đưa secret, token, PII hoặc dữ liệu nhạy cảm vào bản báo cáo.

### 9.1. Ví dụ truy vấn Application Insights qua Log Analytics

Với ứng dụng gửi request telemetry vào workspace có bảng `AppRequests`, có thể phân tích tỷ lệ request không thành công theo phút:

~~~kusto
AppRequests
| where TimeGenerated between (datetime(2026-11-20T09:55:00Z) .. datetime(2026-11-20T10:45:00Z))
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
    by bin(TimeGenerated, 1m), AppRoleName
| extend FailureRatePercent = iff(Requests == 0, real(null), 100.0 * Failures / Requests)
| order by TimeGenerated asc
~~~

Đây là truy vấn mẫu cho schema `AppRequests`; tùy cách tích hợp Application Insights và workspace, tên bảng/cột, sampling và dữ liệu thực tế có thể khác. `ItemCount` giúp ước lượng số request khi có sampling, nhưng kết quả vẫn phải được đối chiếu với synthetic test và business events.

Để kiểm tra p95 latency:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = count(),
    P95LatencyMs = percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

Truy vấn latency dùng các sự kiện telemetry có sẵn; nếu sampling, cần ghi chú giới hạn đại diện của dữ liệu. Không thể chỉ dựa trên CPU thấp hoặc một probe 200 để khẳng định hệ thống phục hồi đúng nghiệp vụ.

### 9.2. Tệp timeline nên có những gì?

| UTC | Nguồn bằng chứng | Sự kiện | Tác động | Người ghi / người thực hiện |
| --- | --- | --- | --- | --- |
| 10:00:00 | Synthetic order probe | Bắt đầu timeout | Tỷ lệ đặt đơn giảm | Observer |
| 10:02:10 | Azure Monitor alert | Alert fired | On-call nhận cảnh báo | SRE |
| 10:04:00 | Bridge log | IC kích hoạt runbook DR | Bắt đầu quá trình khôi phục | IC |
| 10:11:00 | Database event | DR database nhận role ghi | Có thể bắt đầu kiểm tra state | DBA |
| 10:17:00 | Ingress metrics | Lưu lượng chuyển qua DR | Đường vào đã chuyển | Platform |
| 10:22:30 | Synthetic + SLI | Đạt tiêu chí trong cửa sổ chấp nhận | Dịch vụ được công nhận phục hồi | Business owner |

Các mốc là **số liệu minh họa**. Nếu chưa có telemetry hoặc đồng hồ không đồng bộ, ghi rõ khoảng bất định thay vì tạo timestamp chính xác giả.

### 9.3. Mẫu đối soát dữ liệu đơn hàng

Trước diễn tập, tạo các đơn tổng hợp với `exercise_id` và `order_id` duy nhất, ghi lại trạng thái commit và timestamp ở một nguồn bằng chứng độc lập. Sau failover:

~~~text
Expected:
  order-A: ACKNOWLEDGED, amount=100, checksum=X1
  order-B: ACKNOWLEDGED, amount=200, checksum=X2
  order-C: PENDING,      amount=300, checksum=X3

Recovered:
  order-A: PRESENT, amount=100, checksum=X1
  order-B: PRESENT, amount=200, checksum=X2
  order-C: MISSING
~~~

Nếu `order-C` chưa được xác nhận cho người dùng, kết quả nghiệp vụ có thể xử lý bằng retry/cancel theo thiết kế. Nếu `order-B` đã báo thành công nhưng bị thiếu, đó là **mất dữ liệu đã xác nhận**, phải báo cáo và đối soát dù phép đo RPO theo timestamp trông vẫn trong ngưỡng.

Cần thêm kiểm tra duplicate order, outbox/inbox message, sequence, idempotency key, audit log và trạng thái phụ thuộc downstream. **Data integrity là tiêu chí độc lập**, không thể suy ra chỉ từ độ trễ sao chép.

## 10. Tính và báo cáo kết quả diễn tập

Giả sử bài diễn tập môi trường thử có các kết quả sau:

| Phép đo | Mục tiêu | Kết quả thực đo | Đánh giá |
| --- | --- | --- | --- |
| **RTO** | ≤ 30 phút | 22 phút 30 giây | Đạt theo tiêu chí thời gian |
| **RPO** | ≤ 5 phút | Điểm phục hồi trễ 2 phút 50 giây; đã đối soát bản ghi | Đạt giới hạn thời gian; vẫn phải xét dữ liệu |
| **Đặt đơn thành công** | ≥ 99% trong cửa sổ phục hồi | 99,5% trong 10 phút | Đạt |
| **p95 latency** | < 2 giây | 1,8 giây | Đạt |
| **Đơn đã xác nhận bị mất** | 0 theo mục tiêu nghiệp vụ | 1 đơn chưa tìm thấy sau đối soát | **Không đạt** |
| **Thông báo cho nhóm liên quan** | ≤ 5 phút sau phát hiện | 7 phút | **Không đạt** |
| **Cleanup** | Không còn tài nguyên test ngoài phạm vi | Còn một NIC/VM test | **Không đạt** |

**Không được đánh dấu cả bài “PASS” chỉ vì RTO/RPO nằm trong mục tiêu.** Ví dụ trên có vi phạm dữ liệu đã xác nhận, truyền thông chậm và cleanup chưa hoàn tất. Báo cáo tổng thể nên đánh dấu **PARTIAL/FAILED theo acceptance criteria đã chốt trước**, đồng thời phân biệt từng mục đạt hoặc không đạt.

Những điểm đặc biệt cần nêu trong kết luận:

- **Dự phòng hoạt động:** DR phục vụ được bao nhiêu phần trăm hành trình, trong bao lâu?
- **Khả năng lặp lại:** Có bước nào cần người nhớ thao tác, quyền tạm hoặc cấu hình thủ công không?
- **Giới hạn đo:** Metrics sampling, missing traces, clock skew, test workload thấp hơn peak thực tế?
- **Ảnh hưởng gián tiếp:** queue backlog, duplicate messages, mất phân quyền, lag, throughput, cost?
- **Khả năng quay lại:** Sau failback/cleanup, primary và secondary có về trạng thái quản lý mong muốn không?

## 11. Post-incident review: đánh giá để hệ thống tốt hơn

**Post-incident review** (còn gọi là postmortem) là một phần của vòng học tập sau cả **sự cố thật** và **bài diễn tập**. Mục tiêu là hiểu hệ thống đã hành xử như thế nào, những điều kiện nào khiến tác động nghiêm trọng hơn, cơ chế phát hiện/ứng phó đã hiệu quả đến đâu và cần thay đổi gì.

Nên dùng cách tiếp cận **blameless**: tập trung vào điều kiện kỹ thuật, quy trình và thông tin có sẵn tại thời điểm quyết định. Điều này không loại bỏ trách nhiệm chủ sở hữu hành động; nó giúp tìm nguyên nhân có thể khắc phục mà không che giấu dữ liệu.

### 11.1. Cấu trúc một báo cáo có thể hành động

~~~markdown
# DR Exercise / Incident Review: <mã sự cố>

**Ngày/giờ (UTC):** ...
**Môi trường, subscription, region:** ...
**Mức ảnh hưởng và loại sự cố:** ...
**Incident Commander / Exercise Controller:** ...
**Dịch vụ và hành trình bị tác động:** ...

## Tổng quan
- Người dùng gặp tác động gì, trong thời gian nào?
- Hệ thống khôi phục bằng cơ chế nào?
- Kết quả so với RTO, RPO và các SLO đã đặt?

## Timeline
| UTC | Sự kiện | Bằng chứng | Quyết định / thao tác |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Những gì hoạt động
- ...

## Những gì không hoạt động hoặc chưa biết
- ...

## Phân tích nguyên nhân và yếu tố đóng góp
- Trigger: ...
- Điều kiện tồn tại trước đó: ...
- Dependency thất bại: ...
- Tại sao alert/runbook không phát hiện hoặc xử lý sớm hơn: ...

## Tác động dữ liệu và bảo mật
- Giao dịch đã ACK, giao dịch chưa xác định, dữ liệu cần đối soát: ...
- Quyền truy cập, audit, log và các ngoại lệ: ...

## Hành động tiếp theo
| ID | Hành động | Owner | Deadline | Bằng chứng nghiệm thu |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

## Điều kiện kiểm thử lại
- ...
~~~

Ví dụ nội dung trên là **mẫu tài liệu**, không cần tạo file riêng cho mỗi bài học. Trong quy trình làm việc, báo cáo được lưu tại nơi tổ chức quản lý sự cố, liên kết đến truy vấn, dashboard, log và thay đổi mã có liên quan.

### 11.2. Tìm nguyên nhân gốc và yếu tố đóng góp

Tránh kết luận mơ hồ như “database lỗi” hoặc “kỹ sư thao tác chậm”. Hỏi cụ thể theo chuỗi nguyên nhân:

**Dấu hiệu:** Sau chuyển tuyến, API DR trả 5xx trong 7 phút.

**Tại sao?** API không mở được kết nối database qua private DNS.

**Tại sao?** VNet DR thiếu liên kết với Private DNS Zone phục vụ endpoint DR.

**Tại sao?** IaC cho môi trường DR không khai báo liên kết này; việc kiểm tra chỉ xác nhận VM và database đã chạy.

**Vì sao không phát hiện sớm?** Readiness probe chỉ kiểm tra tiến trình, không có synthetic transaction từ môi trường DR; runbook cũng chưa yêu cầu thử DNS từ workload.

Từ đó xác định nhiều hành động:

1. Bổ sung khai báo Private DNS Zone link đúng VNet DR vào IaC, có review và deployment kiểm soát.
2. Tạo synthetic test xác minh DNS → TLS → database → giao dịch đơn hàng từ DR.
3. Bổ sung gate “kiểm tra kết nối và quyền” trước khi chuyển ingress.
4. Diễn tập lại tình huống với một dependency bị cố ý cấu hình sai để kiểm tra cảnh báo và hướng dẫn xử lý.

**Không phải tất cả vấn đề đều có một “root cause” duy nhất.** Có thể có nhiều điều kiện cùng dẫn đến sự cố; review nên ghi mức chắc chắn của kết luận, giả thuyết cần kiểm chứng và dữ liệu còn thiếu.

## 12. Hành động khắc phục: chuyển phát hiện thành thay đổi kiểm chứng được

Một action item hiệu quả phải có **owner, thời hạn, phạm vi thay đổi và điều kiện hoàn thành**. Hãy tránh các hành động chung chung kiểu “tăng giám sát” hoặc “đào tạo nhân sự” nếu không chỉ ra sẽ giảm rủi ro như thế nào.

| Phát hiện | Hành động cụ thể | Bằng chứng đóng |
| --- | --- | --- |
| DR VNet thiếu private DNS link | Thêm resource IaC, có validation trước phát hành | Pipeline kiểm tra link; synthetic test qua DR thành công |
| RTO bị kéo dài vì cấp VM tại DR | Giữ warm capacity hoặc có kế hoạch reservation/quota phù hợp | Diễn tập N-1 hoặc region failover tại tải đã thống nhất đạt RTO |
| Backup job xanh nhưng restore fail | Định kỳ restore vào môi trường cách ly và kiểm tra dữ liệu | Báo cáo restore tự động và đối soát checksum |
| RPO chưa đo được | Ghi synthetic write ID và ack timestamp vào nguồn độc lập | Có báo cáo last-ack/last-recoverable và kết quả đối soát |
| Alert chỉ phát hiện sau 10 phút | Thêm SLI end-to-end + routing đến người trực | Diễn tập tiếp theo đo MTTD trong mục tiêu |
| Failback tạo duplicate processing | Áp dụng idempotency/outbox và fence writer trước chuyển | Test replay/duplicate không tạo đơn hoặc charge trùng |
| Test resource bị bỏ lại | Thêm checklist cleanup và kiểm tra tài nguyên theo tag `exercise_id` | Inventory sau test rỗng đối với phần phải hủy; chi phí được đối chiếu |

Phân loại action item theo rủi ro (ví dụ **P0: có thể gây mất dữ liệu đã xác nhận; P1: tăng RTO; P2: thiếu minh bạch vận hành**). Mức độ và deadline do tổ chức xác định, nhưng mọi phát hiện nghiêm trọng phải có người nhận trách nhiệm đến khi kiểm chứng hoàn tất.

### 12.1. Đóng action item có nghĩa gì?

Một Pull Request được merge hoặc ticket được đánh dấu Done **chưa đủ**. Cần bằng chứng rằng hành vi đã thay đổi trong điều kiện liên quan: kiểm thử IaC/deployment, health probe mới, restore thành công, synthetic test hoặc kết quả diễn tập lại. Nếu còn rủi ro tồn đọng do giới hạn dịch vụ hoặc chi phí, phải có **risk acceptance** rõ người phê duyệt và ngày xem lại.

## 13. Sai lầm phổ biến trong diễn tập và đánh giá

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ kiểm tra tài nguyên “Running” | Người dùng vẫn có thể lỗi DNS, auth, database | Kiểm thử hành trình nghiệp vụ từ ngoài vào trong |
| Bắt đầu đo RTO khi IC quyết định failover | Che giấu thời gian phát hiện và ra quyết định | Bắt đầu từ thời điểm dịch vụ mất khả năng đáp ứng |
| Lấy backup success làm bằng chứng RPO | Backup có thể không khôi phục được hoặc quá cũ | Restore, đọc dữ liệu và đối soát giao dịch |
| Test failover và production failover bị coi là một | Đánh giá sai rủi ro và khả năng đáp ứng thực tế | Ghi rõ mức thử và giới hạn bằng chứng |
| Khôi phục chỉ một VM của ứng dụng nhiều thành phần | Queue, DNS, identity hoặc dữ liệu bị bỏ sót | Kiểm kê dependency và kiểm thử end-to-end |
| Dùng forced failover với replica bất đồng bộ mà không chấp nhận rủi ro dữ liệu | Có thể mất ghi chưa nhân bản | Chọn recovery point, ghi nhận lag, đối soát và quyết định theo RPO |
| Không có điều kiện dừng | Sự cố kiểm thử lan sang production hoặc dữ liệu thật | Mạng cách ly, synthetic data, quyền giới hạn và stop conditions |
| Dừng đánh giá ngay khi ingress chuyển xong | Không biết giao dịch, backlog hoặc dữ liệu còn đúng không | Chờ cửa sổ SLO, kiểm tra data integrity và monitoring |
| Viết postmortem để xác định người có lỗi | Che khuất điều kiện hệ thống và ngăn chia sẻ sự thật | Phân tích theo timeline, dependency và yếu tố đóng góp |
| Ticket hoàn thành mà không diễn tập lại | Không biết biện pháp có hiệu quả hay không | Gắn điều kiện nghiệm thu và kiểm thử lại |

Một thay đổi có thể đồng thời cải thiện RTO và tăng chi phí, hoặc cải thiện RPO nhưng thêm độ trễ ghi. Các lựa chọn cần dựa vào **mục tiêu nghiệp vụ và kiểm thử** chứ không chỉ tối đa hóa redundancy.

## 14. Thực hành tổng hợp: game day cho ứng dụng đặt hàng

**Bối cảnh giả định:** Hệ thống `orders` triển khai ở Azure region chính, có API, worker, database, blob storage, Key Vault và mạng riêng. Có một cấu hình DR ở region thứ hai; định tuyến traffic qua lớp ingress. Mục tiêu: **RTO ≤ 30 phút**, **RPO ≤ 5 phút** cho dữ liệu được phép mất tối đa trong kịch bản thử; **không mất các giao dịch đã xác nhận** thuộc nhóm nghiệp vụ yêu cầu đối soát tuyệt đối.

### Nhiệm vụ A — Lập charter và baseline

Điền bảng kiểm kê dependencies tại mục 4 và mẫu charter tại mục 6. Chỉ rõ owner ứng dụng/dữ liệu/mạng; loại service/tier, region, replication lag, backup recovery point và SLI bình thường. Tạo 30 đơn synthetic có mã duy nhất; lưu danh sách ack ở nơi độc lập để đối chiếu về sau.

### Nhiệm vụ B — Thực hiện test failover cách ly

Dùng cơ chế **test failover hoặc restore test** phù hợp dịch vụ đang triển khai. Không chạy thao tác thay đổi primary production. Theo dõi từng sự kiện từ injection đến lúc DR phục vụ giao dịch; ghi UTC timestamp và link bằng chứng. Khi có lỗi, giữ lại log/traces, tiếp tục theo điều kiện dừng đã duyệt.

### Nhiệm vụ C — Đo kết quả

Tính `T_recovered - T_impact`, đối chiếu transaction ID và trạng thái dữ liệu trước/sau. Đo tỷ lệ thành công và p95 latency trong cửa sổ phục hồi. Kiểm tra cả truy cập Key Vault, Private DNS, nhận message, worker backlog và mức tải phù hợp. Tính tổng chi phí tài nguyên test được tạo.

### Nhiệm vụ D — Failback/cleanup và review

Hoàn nguyên hoặc cleanup theo đúng loại bài thử, kiểm tra replication tiếp tục khỏe. Viết review với timeline, mục tiêu so kết quả, ít nhất ba yếu tố đóng góp và các action item có owner/deadline/bằng chứng kiểm thử lại. Một lỗi chưa tái hiện được phải được ghi là **unknown**, không tự suy ra nguyên nhân.

### Mẫu bảng nộp kết quả

| Mục | Kết quả cần cung cấp |
| --- | --- |
| Scope và điều kiện an toàn | Primary/DR, dữ liệu thử, cách ly, stop conditions |
| Bằng chứng kiểm thử | Timeline UTC, logs, dashboards, phiên bản triển khai |
| Chỉ số | Tác động thực tế, MTTD, RTO, RPO, SLI, throughput |
| Tính toàn vẹn | ID bản ghi có/thiếu/trùng, checksum, hành động đối soát |
| Vận hành | Quyết định, role, liên lạc, thao tác thủ công và lỗi phát hiện |
| Failback/cleanup | Xác minh hệ thống gốc, replication, tài nguyên tạm và chi phí |
| Bài học | Nguyên nhân/yếu tố đóng góp, owner, deadline và lịch diễn tập lại |

**Tiêu chí đạt:** Người học giải thích được điều gì đã được kiểm thử, có đủ bằng chứng để xác nhận hoặc bác bỏ RTO/RPO, chứng minh giao dịch quan trọng còn đúng, nêu rõ rủi ro tồn tại và chuyển phát hiện thành hành động được kiểm thử lại.

## 15. Tích hợp diễn tập DR vào hoạt động dài hạn

DR hiệu quả cần là một **quy trình lặp lại**, gắn với thay đổi kiến trúc, không phải sự kiện làm một lần rồi cất tài liệu. Các tín hiệu cần kích hoạt rà soát và diễn tập lại gồm: đổi database tier/SKU, chuyển vùng, thay ingress hoặc DNS, thêm queue/worker, thay xác thực, thay IaC, chuyển subscription, đổi cách backup/replication và sửa runbook.

Đặt **nhịp kiểm thử theo mức độ quan trọng** của hệ thống và yêu cầu tổ chức; mỗi kỳ có thể chọn một lớp lỗi khác nhau. Theo dõi xu hướng RTO/RPO, tỷ lệ bước thủ công, lỗi cleanup và action item quá hạn. Với mọi quyết định chi phí, so sánh chi phí warm standby, backup retention, lưu lượng nhân bản, DR drills với thiệt hại kinh doanh khi ngừng dịch vụ.

Điều phối thay đổi bằng IaC và pipeline giúp môi trường primary/DR nhất quán, nhưng chỉ diễn tập mới chỉ ra khác biệt còn sót lại trong permissions, network, quota và state. Kết quả đo từ diễn tập phải cập nhật runbook, monitoring, kế hoạch capacity và danh sách rủi ro.

## 16. Tổng kết kiến thức

Một buổi diễn tập DR tốt trả lời được bốn câu hỏi có bằng chứng:

1. **Lỗi nào đã xảy ra?** Phạm vi, mức tác động và dependency bị ảnh hưởng.
2. **Dịch vụ phục hồi thế nào?** Quy trình, người quyết định, các mốc thời gian và điều kiện nghiệp vụ đã hoạt động trở lại.
3. **Dữ liệu và bảo mật còn đúng không?** Recovery point, transaction reconciliation, quyền truy cập và kiểm tra sau failover.
4. **Hệ thống sẽ tốt hơn thế nào?** Những thay đổi có owner, thời hạn, điều kiện hoàn thành và bài diễn tập xác minh tiếp theo.

Trong Azure, hãy đo từ góc nhìn người dùng, đối chiếu dữ liệu thực tế, kiểm tra dịch vụ và cấu hình đúng SKU/region, rồi dùng **post-incident review** để biến lỗi thành cải tiến bền vững. Khôi phục thảm họa chỉ có giá trị khi được kiểm chứng bằng một hệ thống có thể sử dụng và một quy trình đủ rõ để thực hiện lại trong điều kiện áp lực.
