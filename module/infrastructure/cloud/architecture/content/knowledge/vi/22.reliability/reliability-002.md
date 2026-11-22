# Thiết kế miền lỗi và giới hạn bán kính ảnh hưởng

Một hệ thống cloud có thể trải rộng trên nhiều máy chủ, vùng sẵn sàng và dịch vụ được quản lý nhưng vẫn gặp sự cố diện rộng nếu các thành phần dùng chung quá nhiều tài nguyên hoặc phụ thuộc lẫn nhau. Một lỗi nhỏ trong database connection pool, hàng đợi, cấu hình định tuyến hoặc dịch vụ xác thực có thể làm nhiều chức năng cùng ngừng hoạt động. Vì vậy, thiết kế độ tin cậy không chỉ là thêm bản sao hay triển khai nhiều availability zone. Cần xác định **miền lỗi (failure domain)** và chủ động giới hạn **bán kính ảnh hưởng (blast radius)** của mỗi sự cố.

Miền lỗi là phạm vi hạ tầng hoặc thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân lỗi. Blast radius mô tả phạm vi người dùng, dữ liệu, dịch vụ hoặc chức năng bị tác động khi một lỗi xảy ra. Kiến trúc tốt tạo ra các ranh giới độc lập hợp lý, giới hạn tài nguyên dùng chung, kiểm soát đường lan truyền của lỗi và giữ những chức năng quan trọng tiếp tục hoạt động trong chế độ suy giảm có chủ đích.

Bài học thuộc chương **Độ tin cậy** của lộ trình **Cloud Architecture**. Chương trình học cách thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Nội dung tập trung vào cách biến các mục tiêu đó thành ranh giới failure domain, chính sách cô lập và quy trình phục hồi có thể kiểm chứng.

Sau bài học, bạn có thể:

- Phân biệt failure domain, fault containment boundary, blast radius, availability zone và region.
- Lập bản đồ dependency, shared resources và các đường lan truyền lỗi.
- Thiết kế isolation theo zone, region, service, tenant, cell và workload.
- Áp dụng bulkhead, timeout, circuit breaker, load shedding và graceful degradation.
- Giới hạn concurrency, connection, queue và quota để ngăn một workload làm cạn tài nguyên chung.
- Thiết kế data replication, failover và recovery với nhận thức về consistency.
- Định nghĩa SLO, error budget và tiêu chí phục hồi theo cấp độ ảnh hưởng.
- Kiểm thử các tình huống lỗi và đo phạm vi tác động thực tế.

## 1. Failure domain và blast radius

**Failure domain** là tập hợp tài nguyên có thể cùng mất khả năng phục vụ do một nguyên nhân chung. Ví dụ các máy ảo cùng nằm trên một rack điện, các workload cùng dùng một availability zone, hoặc nhiều service phụ thuộc một database cluster duy nhất.

**Blast radius** là mức độ tác động mà một sự cố tạo ra. Có thể đo bằng số tenant/người dùng, tỷ lệ request, số chức năng, số bản ghi hoặc thời gian dịch vụ bị suy giảm.

Hai khái niệm liên quan nhưng không giống nhau: failure domain mô tả nơi lỗi có thể xảy ra cùng nhau; blast radius mô tả hậu quả lỗi lan tới đâu. Một failure domain lớn có thể tạo blast radius nhỏ nếu có lớp cách ly tốt. Ngược lại, một lỗi ở thành phần nhỏ có thể có blast radius lớn nếu nó nằm trên mọi đường xử lý.

### 1.1. Ví dụ đơn giản

Giả sử một ứng dụng gồm API, booking service, payment service và notification worker. Nếu tất cả cùng dùng một connection pool chung tới database, một truy vấn bị treo có thể chiếm hết connection và làm cả bốn chức năng ngừng hoạt động. Lỗi bắt đầu từ một workload nhưng lan tới nhiều chức năng vì chia sẻ tài nguyên mà không có giới hạn.

Nếu mỗi workload có pool riêng với quota, timeout và giới hạn concurrency, truy vấn lỗi vẫn có thể ảnh hưởng booking service nhưng ít có khả năng làm cạn connection của payment hoặc notification. Đây là cách thu hẹp blast radius bằng fault containment.

### 1.2. Mô hình tư duy

~~~mermaid
flowchart TB
    subgraph SHARED["Không có ranh giới cô lập"]
        S["Shared database / connection pool"]
        A["Booking"]
        B["Payment"]
        C["Notification"]
        A --> S
        B --> S
        C --> S
        S --> X["Sự cố tài nguyên chung"]
    end
~~~

~~~mermaid
flowchart TB
    subgraph ISOLATED["Có ranh giới tài nguyên"]
        A["Booking"] --> PA["Pool / quota A"]
        B["Payment"] --> PB["Pool / quota B"]
        C["Notification"] --> PC["Pool / quota C"]
        PA --> DB[("Database có giới hạn tổng")]
        PB --> DB
        PC --> DB
    end
    X["Lỗi ở workload A"] -. "Bị giới hạn trong quota" .-> PA
~~~

Cô lập ở ứng dụng không tự tạo ra database độc lập; tổng quota vẫn phải nằm trong năng lực thật của database. Mục tiêu là phân bổ và ngăn một caller sử dụng hết tài nguyên của các chức năng khác.

## 2. Các lớp miền lỗi trong cloud

Miền lỗi tồn tại ở nhiều lớp, từ phần cứng tới ứng dụng và dữ liệu.

| Lớp | Ví dụ miền lỗi | Hậu quả có thể gặp |
| --- | --- | --- |
| Phần cứng | Disk, host, rack, nguồn điện | Máy chủ hoặc nhóm máy dừng |
| Mạng | Switch, router, link, DNS, NAT gateway | Mất kết nối hoặc tăng latency |
| Availability zone | Trung tâm dữ liệu/zone độc lập theo mô hình nhà cung cấp | Mất một phần compute, network hoặc storage trong zone |
| Region | Khu vực cloud | Mất dịch vụ hoặc kết nối ở quy mô địa lý |
| Control plane | API quản lý/provisioning của nhà cung cấp | Không tạo/sửa tài nguyên được dù data plane có thể còn chạy |
| Dịch vụ dùng chung | Identity, DNS, secrets, database, message broker | Nhiều workload cùng phụ thuộc một điểm |
| Ứng dụng | Một process, service, deployment hoặc cell | Một phiên bản lỗi ảnh hưởng request được route tới nó |
| Tenant/workload | Một tenant hoặc job nặng | Noisy neighbor hoặc lỗi dữ liệu riêng |
| Con người/quy trình | Cấu hình sai, deploy lỗi, credential bị lộ | Thay đổi đồng thời tác động nhiều môi trường |

Một availability zone có thể được thiết kế để độc lập về một số thành phần vật lý nhưng không đồng nghĩa hoàn toàn không có dependency chung. Region cũng có thể dùng một số control plane hoặc dịch vụ toàn cục. Cần xác minh đặc tính thực tế của nhà cung cấp và dịch vụ được sử dụng.

## 3. Fault containment boundary

**Fault containment boundary** là ranh giới kiến trúc được thiết kế để ngăn lỗi vượt ra ngoài một phạm vi. Nó có thể là tiến trình riêng, queue riêng, account/project cloud, network boundary, database cluster, cell hoặc region.

Một boundary hữu ích cần:

- Có tài nguyên và quota được giới hạn.
- Có dependency được xác định rõ.
- Có cơ chế phát hiện và xử lý lỗi.
- Có quyền truy cập và credential phù hợp.
- Có thể deploy, rollback hoặc phục hồi mà không tác động toàn hệ thống.
- Có metric cho biết lỗi đang bị giữ trong boundary hay đã lan ra ngoài.

Không phải boundary nào cũng cần hạ tầng hoàn toàn riêng. Có thể bắt đầu bằng giới hạn concurrency và pool, sau đó tăng mức cô lập khi yêu cầu availability hoặc tenant isolation cao hơn.

## 4. Availability zone và region isolation

### 4.1. Multi-zone

Triển khai trên nhiều availability zone có thể giảm phụ thuộc vào một khu vực hạ tầng đơn lẻ trong region. Ứng dụng thường cần load balancer, compute phân bố nhiều zone và database/storage có topology phù hợp.

Tuy vậy, multi-zone chỉ có ích khi đường xử lý thực sự có thể tiếp tục nếu một zone mất:

- Load balancer và network route vẫn phục vụ được.
- Application instance còn ở zone khác.
- Database có replica/quorum hoặc khả năng failover thích hợp.
- Storage và queue không bị giới hạn trong zone lỗi.
- Subnet/IP capacity ở zone còn lại đủ tải.
- Dependency nội bộ và outbound connectivity vẫn hoạt động.

Nếu tất cả app instance nằm ở zone A, việc tạo database replica ở zone B không giúp ứng dụng tiếp tục phục vụ khi zone A mất.

### 4.2. Multi-region

Multi-region có thể giảm blast radius của sự cố region, hỗ trợ disaster recovery hoặc phục vụ người dùng ở nhiều khu vực địa lý. Đổi lại, nó làm phức tạp consistency, replication, routing, data residency, identity và vận hành.

Cần xác định mô hình dữ liệu:

- **Active-passive:** một region phục vụ chính, region còn lại standby hoặc phục vụ giới hạn.
- **Active-active:** nhiều region cùng phục vụ traffic; cần phân vùng quyền ghi, conflict resolution hoặc replication semantics rõ.
- **Read-local/write-home:** người dùng đọc gần region nhưng ghi về region sở hữu dữ liệu.
- **Sharded-by-region:** mỗi nhóm dữ liệu có home region, hạn chế ghi chéo vùng.

Không được coi active-active là lựa chọn tự nhiên chỉ vì có nhiều region. Với dữ liệu có invariant mạnh, một vùng ghi có thẩm quyền hoặc sharding rõ ràng có thể an toàn và dễ vận hành hơn.

## 5. Shared dependency là nguồn blast radius lớn

Một service được dùng chung bởi nhiều ứng dụng có thể trở thành điểm lan truyền lỗi. Ví dụ:

- Identity provider lỗi khiến mọi request cần đăng nhập thất bại.
- DNS lỗi khiến service không tìm được dependency.
- Secrets manager lỗi làm workload mới khởi động không lấy được credential.
- Database cluster chung khiến một tenant/job gây cạn connection.
- Message broker chung bị đầy queue hoặc quota.
- NAT gateway hoặc outbound proxy dùng chung bị quá tải.

Lập danh sách dependency chung và xác định vai trò của chúng trong từng hành trình nghiệp vụ.

### 5.1. Dependency critical và optional

| Dependency | Critical khi nào? | Cách giảm ảnh hưởng |
| --- | --- | --- |
| Identity/authentication | Mọi request cần xác thực mới | Token validation cục bộ theo chính sách, cache JWK có TTL, nhiều đường kết nối được hỗ trợ |
| Profile service | Hiển thị thông tin bổ sung | Cache hoặc fallback cho phần không nhạy cảm |
| Payment provider | Tạo giao dịch thanh toán | Timeout, idempotency, trạng thái pending và reconciliation |
| Notification provider | Gửi thông báo | Queue bền vững, retry có giới hạn, xử lý sau |
| Analytics warehouse | Dashboard/report | Tách khỏi đường giao dịch |
| Feature/config service | Quyết định tính năng hoặc policy | Cache versioned có TTL; không fallback cũ với policy nhạy cảm nếu không an toàn |

Không có một fallback chung cho mọi dependency. Với auth, fallback cũ có thể mở quyền sai; với thumbnail, fallback placeholder thường đủ. Mỗi use case cần quy định mức stale/fallback chấp nhận được.

## 6. Dependency graph và đường lan truyền lỗi

Một dịch vụ có thể ổn định riêng nhưng thất bại khi một dependency chậm. Ví dụ API chờ booking service; booking service chờ inventory; inventory lại chờ database. Nếu timeout không được phân bổ, mỗi tầng có thể giữ request và connection lâu hơn mức cần thiết.

Hãy vẽ dependency graph theo từng hành trình, không chỉ sơ đồ deployment. Bao gồm cả synchronous call, queue, database, DNS, secret, external provider và control plane cần thiết khi vận hành.

~~~mermaid
flowchart LR
    U["Client"] --> API["API"]
    API --> B["Booking"]
    B --> I["Inventory"]
    B --> P["Payment"]
    I --> DB[("Database")]
    P --> PSP["Payment provider"]
    B --> ID["Identity/config"]
    B --> Q["Event queue"]
    Q --> N["Notification"]
~~~

Với mỗi cạnh, ghi timeout, retry, concurrency, criticality, ownership và hành vi khi dependency lỗi. Các cạnh synchronous tạo chuỗi latency và có nguy cơ lan lỗi trực tiếp; queue có thể tách thời điểm xử lý nhưng tạo backlog và yêu cầu durability.

### 6.1. Tính critical path

Một request đồng bộ chỉ hoàn tất khi các dependency bắt buộc hoàn tất. Nếu API cần booking và inventory đồng thời, latency có thể xấp xỉ thời gian chậm nhất cộng overhead; nếu gọi tuần tự, thời gian có thể cộng dồn. Nhiều dependency song song cũng làm xác suất ít nhất một dependency lỗi tăng lên.

Do đó, giảm số dependency trên critical path thường giúp giảm blast radius và latency. Những công việc có thể làm sau nên được đưa vào queue/workflow phù hợp, với trạng thái rõ ràng.

## 7. Bulkhead: ngăn một workload chiếm hết tài nguyên

**Bulkhead pattern** chia tài nguyên thành các vùng giới hạn độc lập, giống các khoang kín trên tàu. Một nhóm request gặp lỗi hoặc tăng tải không thể tiêu thụ hết mọi thread, connection hay worker của hệ thống.

Các loại bulkhead:

- Thread pool riêng theo dependency hoặc workload.
- Connection pool riêng cho nhóm chức năng.
- Queue riêng cho tác vụ có mức ưu tiên khác nhau.
- Concurrency limit theo tenant hoặc operation.
- CPU/memory quota theo container/process.
- Account, project hoặc cluster riêng cho workload cần isolation mạnh.

Ví dụ, luồng thanh toán không nên dùng chung một executor không giới hạn với công việc tạo thumbnail. Nếu thumbnail worker bị treo, payment request vẫn cần có thread, connection và quota được bảo vệ.

### 7.1. Đánh đổi

Bulkhead làm tăng cấu hình và có thể để tài nguyên nhàn rỗi trong một partition trong khi partition khác quá tải. Chia quá nhiều pool nhỏ gây fragmentation. Kích thước pool và tỷ lệ tài nguyên cần dựa trên workload, SLO và giới hạn downstream.

## 8. Timeout và deadline propagation

Timeout ngăn request giữ tài nguyên vô hạn khi dependency không phản hồi. Nhưng timeout mỗi tầng độc lập có thể gây ra tình huống caller đã hết hạn trong khi downstream vẫn tiếp tục xử lý.

Nên dùng **deadline** xuyên request: caller có thời hạn tổng; mỗi dependency nhận budget còn lại trừ overhead an toàn.

Ví dụ một API có deadline 800 ms:

| Thành phần | Budget ví dụ |
| --- | ---: |
| Gateway/auth | 80 ms |
| Booking logic | 120 ms |
| Inventory query | 180 ms |
| Payment status read | 180 ms |
| Serialize/response | 60 ms |
| Dự phòng network/variance | 180 ms |
| Tổng | 800 ms |

Các số chỉ minh họa. Nếu inventory timeout ở 180 ms, API không nên tiếp tục thử lại nhiều lần nếu deadline tổng không còn đủ. Cần hủy công việc downstream khi có thể và giải phóng connection/permit.

Timeout không chứng minh thao tác thất bại. Với command có side effect, client có thể không biết commit đã xảy ra. Cần idempotency key, trạng thái operation và reconciliation thay vì gửi lại mù quáng.

## 9. Circuit breaker: dừng gọi dependency đang lỗi

Circuit breaker theo dõi lỗi hoặc timeout và tạm ngăn các call mới tới dependency khi vượt ngưỡng.

Ba trạng thái phổ biến:

- **Closed:** cho phép request đi qua và theo dõi kết quả.
- **Open:** từ chối nhanh hoặc dùng fallback trong khoảng cool-down.
- **Half-open:** cho một số ít probe để kiểm tra dependency đã phục hồi chưa.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error/timeout threshold exceeded
    Open --> HalfOpen: Cooldown elapsed
    HalfOpen --> Closed: Probe succeeds
    HalfOpen --> Open: Probe fails
~~~

Circuit breaker giúp tránh giữ thread và connection chờ một dependency đã hỏng. Tuy nhiên, cần chọn threshold và window phù hợp. Nếu threshold quá nhạy, một đợt lỗi ngắn tạo false open; nếu quá lỏng, hệ thống tiếp tục khuếch đại tải.

Circuit breaker không thay retry policy, timeout hoặc bulkhead. Các cơ chế này phối hợp để bảo vệ các lớp khác nhau.

## 10. Load shedding và graceful degradation

Khi hệ thống gần hết capacity, tiếp tục nhận mọi request có thể khiến tất cả chức năng cùng sụp. **Load shedding** chủ động từ chối hoặc loại bỏ một phần tải để bảo vệ phần còn lại. **Graceful degradation** cho phép hệ thống cung cấp một tập chức năng giảm nhưng vẫn hữu ích.

Ví dụ nền tảng đặt thuê thiết bị:

| Chức năng | Khi quá tải | Chính sách suy giảm |
| --- | --- | --- |
| Xác nhận thanh toán | Ưu tiên cao | Giữ capacity dành riêng; trả trạng thái pending khi cần |
| Tạo booking | Ưu tiên cao | Rate limit có kiểm soát; không xác nhận nếu chưa commit |
| Xem lịch sử đơn | Ưu tiên vừa | Đọc cache/replica có freshness được công bố |
| Gợi ý sản phẩm | Có thể trì hoãn | Tắt hoặc trả nội dung mặc định |
| Gửi email | Bất đồng bộ | Giữ queue và gửi sau |
| Báo cáo lớn | Ưu tiên thấp | Tạm hoãn hoặc giảm concurrency |

Một cơ chế degradation cần định nghĩa dữ liệu nào được phép cũ, thao tác nào bị tắt và trạng thái nào được trả cho người dùng. Không được giả vờ thành công hoặc hiển thị kết quả mặc định sai cho một giao dịch quan trọng.

## 11. Admission control và giới hạn tài nguyên

Admission control quyết định có nhận thêm công việc dựa trên năng lực hiện tại và policy. Nó hữu ích trước khi queue, executor hoặc database đã đầy.

Các giới hạn nên xem xét:

- Maximum request rate theo tenant/API key.
- Maximum concurrent requests trên service.
- Connection pool và query concurrency cho database.
- Maximum inflight messages và queue depth.
- CPU/memory limit cho workload.
- External API quota.
- Maximum job duration và payload size.
- Priority quota và reserved capacity cho tác vụ quan trọng.

Khi từ chối, trả lỗi và hướng dẫn thử lại phù hợp như 429/503 cùng Retry-After nếu có thể. Với message producer, broker/consumer cần semantics retry và dead-letter rõ. Không trả accepted trước khi công việc được lưu bền vững theo cam kết.

### 11.1. Tránh cạn kiệt tài nguyên theo dây chuyền

Một API có thể tạo 10 downstream calls cho mỗi request. Nếu nhận 1.000 request đồng thời, hệ thống có thể tạo 10.000 call tới dependency. Cần giới hạn fan-out, batch, concurrency và số lần retry trên toàn đường đi; chỉ giới hạn request ở gateway là chưa đủ.

## 12. Cô lập tenant và noisy neighbor

Trong SaaS multi-tenant, một tenant lớn hoặc lỗi cấu hình có thể tiêu thụ tài nguyên của tenant khác. Đây là dạng blast radius ở cấp workload.

Các biện pháp:

- Quota request, storage, compute và job theo tenant.
- Concurrency limit và fairness policy.
- Queue partition hoặc queue riêng theo mức isolation cần thiết.
- Rate limit cho export, report và bulk operation.
- Cache key và database query luôn gắn tenant context.
- Giới hạn số kết nối và query chạy dài theo tenant.
- Cảnh báo usage bất thường và tự động throttle.
- Tier isolation cho tenant có yêu cầu compliance hoặc SLO cao.

Không nhất thiết tạo hạ tầng riêng cho mọi tenant. Shared infrastructure với quota có thể hiệu quả hơn, nhưng tenant có workload cực lớn hoặc yêu cầu cách ly mạnh có thể cần dedicated cell/database/cluster.

## 13. Cell-based architecture

**Cell architecture** chia một hệ thống lớn thành nhiều đơn vị triển khai tương đối độc lập. Mỗi cell phục vụ một nhóm tenant hoặc partition dữ liệu và có compute, queue, database cùng quota riêng trong phạm vi cell.

~~~mermaid
flowchart TB
    G["Global routing / tenant directory"] --> C1["Cell A"]
    G --> C2["Cell B"]
    G --> C3["Cell C"]
    subgraph CELL_A["Failure boundary A"]
        C1 --> A1[("App + DB + Queue A")]
    end
    subgraph CELL_B["Failure boundary B"]
        C2 --> B1[("App + DB + Queue B")]
    end
    subgraph CELL_C["Failure boundary C"]
        C3 --> C1DB[("App + DB + Queue C")]
    end
~~~

Nếu cell B gặp lỗi, tenant trong cell B có thể bị ảnh hưởng trong khi cell A và C tiếp tục hoạt động. Global routing và tenant directory vẫn là dependency chung cần được thiết kế HA/cached fallback; nếu chúng hỏng, cell độc lập vẫn có thể bị ảnh hưởng ở bước tìm vị trí tenant.

### 13.1. Tiêu chí chia cell

Có thể chia theo:

- Số lượng tenant mục tiêu mỗi cell.
- Tổng workload và quota.
- Region/data residency.
- Tier/SLO của tenant.
- Data partition hoặc tenant hash.
- Blast radius tối đa mà tổ chức chấp nhận.

Cell quá lớn làm blast radius lớn; cell quá nhỏ làm tăng chi phí, vận hành và mất hiệu quả tài nguyên. Số tenant không phải tiêu chí duy nhất: mười tenant lớn có thể tạo tải cao hơn hàng nghìn tenant nhỏ.

### 13.2. Cell independence

Một cell chỉ độc lập khi có đủ khả năng phục vụ những chức năng được cam kết khi dependency global bị suy giảm. Cần xem xét auth/token validation, config cache, tenant mapping, secrets, observability ingestion, deployment control và data replication. Không nhất thiết nhân bản mọi control plane; nhưng phải phân biệt chức năng cần khi runtime với chức năng chỉ cần khi quản trị.

## 14. Data boundary và replication failure

Database và storage có thể tạo blast radius nếu nhiều service hoặc tenant cùng dùng chung bảng, schema hay cluster mà không có resource guardrail.

Cần xác định:

- Data ownership theo domain/tenant.
- Transaction boundary và invariant.
- Connection/query quota.
- Partition/shard hoặc database-per-tenant khi phù hợp.
- Replication topology và lag tolerance.
- Backup/restore boundary.
- Failover/fencing và quyền promotion.
- Hành vi khi storage hoặc data plane bị lỗi.

Replication không thay thế backup. Nếu một thao tác xóa nhầm được replicate, các bản sao cũng có thể bị xóa. Nếu một replica lag, failover sang nó có thể làm mất phần dữ liệu chưa nhận. Kiến trúc cần RPO/RTO và recovery test tương ứng.

### 14.1. Không mở rộng blast radius bằng transaction xuyên miền

Một transaction đồng bộ trải qua nhiều database hoặc service tạo coupling cao. Khi một dependency chậm, tất cả participant có thể giữ tài nguyên. Với quy trình dài, cân nhắc saga/workflow, trạng thái trung gian và compensation. Tuy nhiên, compensation là hành động nghiệp vụ mới chứ không phải rollback ACID hoàn hảo.

## 15. Shared control plane và data plane

Cloud và SaaS thường có **control plane** để provision, cấu hình, phân quyền, deploy; và **data plane** để xử lý request nghiệp vụ. Một sự cố control plane không nhất thiết phải làm data plane ngừng xử lý.

Ví dụ, nếu control plane dùng để quản lý feature/config không khả dụng, runtime có thể tiếp tục dùng config version đã validate gần nhất trong một thời gian. Nhưng nếu policy liên quan tới thu hồi quyền truy cập, giữ config cũ có thể không an toàn.

Cần xác định cho từng loại config:

- Có thể dùng last-known-good trong bao lâu?
- Cần fail-open hay fail-closed?
- Thay đổi nào phải có hiệu lực ngay?
- Có cần cache local và chữ ký/version?
- Cách phục hồi khi config store hoạt động lại?
- Làm sao tránh hàng loạt instance refresh đồng thời gây load spike?

Không dùng một fallback policy chung cho branding, entitlement và security policy.

## 16. Deploy, config change và lỗi do con người

Blast radius thường đến từ thay đổi phần mềm/cấu hình nhiều hơn lỗi phần cứng. Một release lỗi được triển khai toàn bộ tenant cùng lúc có thể gây outage diện rộng dù hạ tầng nhiều zone vẫn khỏe.

Các cơ chế giảm tác động:

- Canary deployment và progressive rollout.
- Feature flag có owner, expiry và kill switch.
- Deployment theo cell/cohort.
- Automated health gate và stop condition.
- Expand–migrate–contract cho schema.
- Config validation và staged publication.
- Rollback/forward-fix đã diễn tập.
- Separation of duties cho thay đổi nhạy cảm.
- Immutable artifact và release metadata.
- Giới hạn tốc độ rollout để tránh đồng loạt.

Rollback application không luôn đảo ngược được database migration hoặc dữ liệu đã ghi. Cần backward compatibility và kế hoạch forward fix.

## 17. Recovery strategy: khôi phục trong boundary nào?

Khi lỗi xảy ra, cần biết phục hồi tại chỗ, chuyển traffic, promote replica hay khôi phục toàn region. Chọn chiến lược theo nguyên nhân và phạm vi lỗi.

| Phạm vi lỗi | Chiến lược thường xem xét | Điều cần xác minh |
| --- | --- | --- |
| Một process/container | Restart/replace instance | Startup, readiness và idempotent job |
| Một service version | Rollback/canary stop | Schema và data compatibility |
| Một host/zone | Reschedule hoặc failover sang zone khác | Capacity, subnet, data quorum |
| Một database node | Failover/promote theo engine | Replication lag, fencing, unknown commit |
| Một cell | Reroute tenant hoặc restore cell | Tenant directory, data ownership và RTO |
| Một region | DR failover hoặc failover theo sharding | RPO, DNS/routing, data residency |
| Một external dependency | Degrade, queue hoặc manual process | Business state và reconciliation |

Không nên chuyển traffic sang nơi khác nếu nơi đó không có dữ liệu mới nhất, credential cần thiết hoặc capacity đủ. Failover có thể làm hệ thống tệ hơn nếu diễn ra tự động mà thiếu điều kiện.

## 18. Đo blast radius và độ tin cậy

Chỉ số tổng availability có thể che giấu việc một nhóm tenant hoặc một chức năng bị ảnh hưởng nặng. Nên đo ở nhiều chiều.

| Metric | Câu hỏi |
| --- | --- |
| Affected request percentage | Bao nhiêu request bị lỗi/timeout trong sự cố? |
| Affected tenant count | Bao nhiêu tenant bị ảnh hưởng và theo tier nào? |
| Affected cell/zone/region | Sự cố có lan qua boundary không? |
| Dependency fan-out | Một request tạo bao nhiêu downstream call? |
| Error rate by dependency | Dependency nào tạo lỗi lan truyền? |
| Queue age/backlog | Công việc trì hoãn tích tụ ở đâu? |
| Resource saturation | Connection, CPU, memory, thread, disk đã cạn ở boundary nào? |
| Recovery time | Bao lâu để khôi phục chức năng quan trọng? |
| Data loss/duplication | Có giao dịch mất, trùng hoặc cần reconciliation? |
| Error budget burn | SLO bị tiêu thụ nhanh tới mức nào? |

Theo dõi theo tenant, cell, region và operation giúp phát hiện noisy neighbor và lỗi chỉ ảnh hưởng một phân vùng. Tránh log payload nhạy cảm chỉ để đo blast radius; metadata và định danh đã kiểm soát thường đủ.

## 19. SLO, error budget và degradation policy

SLO nên gắn với hành trình người dùng, không chỉ CPU hoặc health check. Ví dụ:

- 99,9% request tạo booking được xử lý đúng trong cửa sổ mục tiêu.
- 99% thanh toán có kết quả xác định hoặc trạng thái pending có thể tra cứu.
- 99,5% tenant không bị ảnh hưởng bởi sự cố của một cell khác.
- Sau khi mất một zone, chức năng cốt lõi phục hồi trong thời gian mục tiêu.
- Job thông báo có thể chậm nhưng không mất sau khi được xác nhận durable.

Error budget giúp quyết định tốc độ phát hành và ưu tiên reliability work. Khi budget bị tiêu thụ nhanh, tổ chức có thể tạm dừng rollout rủi ro, giảm thay đổi hoặc tập trung loại bỏ nguồn sự cố.

Cần ghi rõ chức năng nào được degrade và dữ liệu nào được phép stale. Ví dụ có thể tắt recommendation để bảo vệ booking; không thể tự đổi trạng thái payment từ unknown sang failed chỉ để UI có câu trả lời nhanh.

## 20. Chaos engineering và failure injection

Chaos engineering là cách kiểm tra giả thuyết về độ tin cậy bằng cách tạo lỗi có kiểm soát trong điều kiện quan sát được. Mục tiêu là phát hiện đường lan truyền và xác nhận cơ chế containment.

Ví dụ thử nghiệm:

- Dừng một application instance.
- Tăng latency hoặc trả lỗi từ một dependency.
- Ngắt kết nối tới một replica hoặc zone test.
- Làm đầy queue trong môi trường thử nghiệm.
- Giới hạn connection database.
- Thu hồi credential giả lập.
- Triển khai config sai vào một cohort thử nghiệm.
- Tắt một worker giữa batch để kiểm tra ack/checkpoint.
- Mô phỏng DNS/network degradation.

Trước khi thử nghiệm cần xác định hypothesis, phạm vi, blast radius cho phép, guardrail, cách dừng và tiêu chí thành công. Không bắt đầu bằng cách gây lỗi diện rộng trên production nếu chưa có kiểm soát và phê duyệt phù hợp.

### 20.1. Game day

Game day là buổi diễn tập có kịch bản và người tham gia rõ: người điều phối, operator, observer và business representative. Đo thời gian phát hiện, quyết định, phục hồi và chất lượng truyền thông nội bộ; ghi lại gap trong runbook và automation.

Không coi chaos experiment thành công chỉ vì hệ thống không sập. Có thể ứng dụng vẫn trả response nhưng latency, error budget hoặc data correctness đã vi phạm.

## 21. Ví dụ thiết kế: nền tảng đặt thuê đa tenant

Giả sử nền tảng có 3.000 tenant, các chức năng booking, payment, inventory, notification và analytics. Một tenant lớn chạy báo cáo và export dữ liệu vào giờ cao điểm. Một lỗi ở notification provider không được phép ngăn khách đặt thuê.

### 21.1. Ranh giới đề xuất

- Chia tenant vào các cell theo region và capacity; tenant lớn có quota hoặc cell riêng theo SLO/hợp đồng.
- Booking và payment có reserved capacity, pool và timeout riêng.
- Inventory kiểm soát concurrency trên dữ liệu có thẩm quyền.
- Notification đi qua queue bền vững và worker group có rate limit.
- Analytics/export chạy ở data platform riêng, với per-tenant quota.
- Global routing/tenant directory có HA, local cache versioned và quy trình phục hồi.
- Observability phân chiều tenant, cell, dependency và operation.

~~~mermaid
flowchart TB
    U["Clients"] --> G["Global routing / tenant directory"]
    G --> CA["Cell A"]
    G --> CB["Cell B"]
    G --> CC["Cell C"]
    subgraph CELL_A["Cell A"]
        CA --> BA["Booking + Payment"]
        CA --> QA["Notification queue"]
        BA --> DBA[("Cell A data")]
        QA --> WA["Notification workers"]
    end
    subgraph CELL_B["Cell B"]
        CB --> BB["Booking + Payment"]
        CB --> QB["Notification queue"]
        BB --> DBB[("Cell B data")]
        QB --> WB["Notification workers"]
    end
    subgraph CELL_C["Cell C"]
        CC --> BC["Booking + Payment"]
        CC --> QC["Notification queue"]
        BC --> DBC[("Cell C data")]
        QC --> WC["Notification workers"]
    end
    X["Analytics platform"] -. "CDC / controlled export" .-> DBA
    X -. "CDC / controlled export" .-> DBB
    X -. "CDC / controlled export" .-> DBC
~~~

Sơ đồ là một topology minh họa. Việc chia database, queue hoặc cell thực tế phụ thuộc tính năng cloud provider, tenant placement và chi phí. Điểm quan trọng là công việc export/notification không chia sẻ không giới hạn tài nguyên với critical path booking/payment.

### 21.2. Kịch bản lỗi

| Sự cố | Phạm vi có thể giới hạn | Hành vi mong muốn |
| --- | --- | --- |
| Tenant C export quá lớn | Quota/worker của tenant hoặc cell C | Throttle export; booking của tenant khác tiếp tục |
| Notification provider lỗi | Notification worker/queue | Booking vẫn commit; thông báo chờ gửi |
| Một cell database mất kết nối | Cell tương ứng | Tenant ở cell khác tiếp tục; cell lỗi phục hồi theo runbook |
| Config service chậm | Config lookup path | Dùng last-known-good config phù hợp policy |
| Global routing lỗi | Đường resolve tenant | Cached mapping và fallback an toàn; không route nhầm tenant |
| Payment provider timeout | Payment operation | Trạng thái pending/unknown, idempotency và reconciliation |

### 21.3. Tiêu chí nghiệm thu

1. Làm quá tải export tenant C; xác nhận pool/queue của booking và payment không bị chiếm hết.
2. Dừng notification worker; xác nhận booking được commit và queue giữ message durable.
3. Giả lập một cell mất database; xác nhận cell khác không chịu cùng lỗi.
4. Làm config service unavailable; xác nhận policy nào dùng cache được và policy nào fail closed.
5. Làm global routing chậm; xác nhận tenant context không bị ánh xạ nhầm.
6. Ngắt kết nối payment tại thời điểm commit; xác nhận idempotency và reconciliation.
7. Đo số tenant/request bị ảnh hưởng, queue age, latency, error rate và thời gian phục hồi.

## 22. Quy trình thiết kế fault containment

1. **Xác định hành trình quan trọng:** booking, payment, login, search, notification và reporting.
2. **Vẽ dependency graph:** synchronous, asynchronous, shared resource, external service và control plane.
3. **Lập danh sách failure domain:** host, zone, region, DB, queue, tenant, cell và con người.
4. **Xác định blast radius chấp nhận:** số tenant/request/dữ liệu và thời gian suy giảm tối đa.
5. **Chọn boundary:** process, pool, queue, cell, account/project, database hoặc region theo giá trị isolation.
6. **Đặt quota và admission control:** connection, concurrency, request rate, memory, storage, queue và tenant.
7. **Thiết kế lỗi:** timeout/deadline, circuit breaker, retry, load shedding và graceful degradation.
8. **Thiết kế data recovery:** replication, backup, RPO/RTO, fencing và reconciliation.
9. **Thiết kế rollout:** canary, deployment theo cell, config validation và rollback.
10. **Thiết lập quan sát:** metric theo tenant/cell/zone/dependency và error budget.
11. **Diễn tập:** dependency outage, zone loss, noisy neighbor, queue full, config error và restore.
12. **Cập nhật runbook:** owner, trigger, escalation, stop condition và bằng chứng phục hồi.

## 23. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ triển khai multi-zone mà không kiểm tra dependency | Database, DNS hoặc identity vẫn là điểm lỗi chung | Vẽ và kiểm thử dependency graph |
| Dùng chung pool không giới hạn | Một workload cạn connection của toàn hệ thống | Bulkhead và quota theo workload |
| Retry mọi lỗi ngay lập tức | Retry storm và khuếch đại outage | Timeout, backoff, jitter và retry budget |
| Không có deadline end-to-end | Request giữ tài nguyên lâu qua nhiều tầng | Propagate deadline và hủy công việc |
| Fallback mọi dependency bằng cache cũ | Quyết định nhạy cảm dựa trên policy/state stale | Phân loại fail-open/fail-closed theo nghiệp vụ |
| Scale vô hạn khi queue tăng | Làm downstream quá tải | Admission control và scale theo capacity |
| Không có per-tenant quota | Noisy neighbor ảnh hưởng tenant khác | Fairness và usage limits |
| Cell dùng chung quá nhiều control dependency | Sự cố global vẫn tác động tất cả cell | Thiết kế cached/local capability và recovery |
| Promote replica không kiểm tra freshness/fencing | Mất dữ liệu hoặc split brain | Failover runbook và candidate criteria |
| Rollout toàn bộ tenant cùng lúc | Một release lỗi tạo blast radius toàn platform | Canary/cohort và stop condition |
| Degrade mà không rõ semantics | UI hiển thị sai hoặc xác nhận nghiệp vụ giả | Contract cho stale/partial/unavailable |
| Không diễn tập | Runbook, automation và RTO chỉ tồn tại trên giấy | Game day và failure injection có guardrail |
| Chỉ đo availability tổng thể | Lỗi một cell/tenant bị che giấu | Metric theo tenant, cell, region và operation |

## 24. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Failure domain đã rõ? Lỗi một zone/tenant/dependency có bị giới hạn? Có bulkhead, failover, backup và recovery test? |
| **Bảo mật** | Tenant, secret, network và admin boundary có isolation? Sự cố một credential có thể lan tới bao nhiêu workload? |
| **Hiệu quả hiệu năng** | Timeout, concurrency, connection và queue được giới hạn? Dependency chậm có làm tăng latency dây chuyền? |
| **Tối ưu chi phí** | Mức isolation có tương xứng với SLO? Dedicated cell/replica có utilization hợp lý? Có tránh overprovisioning và retry waste? |
| **Khả năng vận hành** | Có dependency map, metric theo blast radius, runbook, canary, game day và owner cho từng boundary? |

### Checklist nghiệm thu

- [ ] Failure domain và fault containment boundary được lập bản đồ theo hạ tầng và hành trình nghiệp vụ.
- [ ] Blast radius được định lượng theo tenant, request, chức năng, dữ liệu và thời gian.
- [ ] Shared dependencies và shared resources có owner, quota, health signal và fallback.
- [ ] Workload critical có pool, concurrency và capacity được bảo vệ.
- [ ] Timeout/deadline được truyền xuyên call chain; retry có giới hạn và idempotency.
- [ ] Circuit breaker, load shedding và graceful degradation có semantics rõ.
- [ ] Tenant/cell isolation ngăn noisy neighbor và cross-tenant impact.
- [ ] Multi-zone/region topology có đủ compute, data, network và dependency để failover.
- [ ] Failover có candidate criteria, fencing, RPO/RTO và reconciliation.
- [ ] Deployment/config change có canary, stop condition và rollback/forward-fix.
- [ ] Config/identity fallback được phân loại fail-open/fail-closed theo mức rủi ro.
- [ ] Dashboard đo error rate, latency, saturation, queue age và affected tenants theo boundary.
- [ ] Có failure injection/game day cho các kịch bản quan trọng.
- [ ] Runbook nêu rõ owner, escalation, stop condition và bằng chứng phục hồi.

## 25. Bài tập áp dụng

Một nền tảng SaaS phục vụ 1.200 doanh nghiệp trong ba region. Mỗi tenant có booking, payment, notification và reporting. Database được dùng chung theo region; một nhóm tenant lớn thường chạy export hàng loạt. Dịch vụ gửi thông báo là nhà cung cấp bên ngoài. Đội vận hành muốn khi một tenant hoặc một zone gặp sự cố, các tenant khác vẫn tiếp tục tạo và quản lý booking.

Hãy thiết kế:

1. Các failure domain ở host, zone, region, database, queue, tenant và service là gì?
2. Thành phần shared nào có thể tạo blast radius toàn region?
3. Cần bulkhead/quotas nào cho booking, payment, notification và export?
4. Khi nào nên chọn shared database có quota, database shard hoặc dedicated cell?
5. Thiết kế fallback khi identity/config service không khả dụng; policy nào fail open và policy nào fail closed?
6. Notification provider lỗi thì trạng thái booking và notification queue hoạt động ra sao?
7. Zone mất thì compute, database, network và tenant routing phục hồi như thế nào?
8. Đặt RPO/RTO và SLO cho booking/payment, notification và reporting ra sao?
9. Làm thế nào kiểm thử noisy neighbor và xác định blast radius thực tế?
10. Các metric nào chứng minh lỗi ở một tenant/cell không lan sang tenant khác?

Một phương án có cơ sở có thể bắt đầu bằng quota theo tenant, pool/queue riêng cho critical workload, notification bất đồng bộ và export được điều tiết. Khi một nhóm tenant tạo tải hoặc có yêu cầu isolation cao, chuyển họ sang cell/database riêng theo cohort. Thiết kế multi-zone phải bao gồm data và network failover, còn multi-region chỉ được chọn khi RPO/RTO và data residency biện minh cho chi phí và độ phức tạp.

**Điểm cốt lõi:** độ tin cậy không chỉ đến từ việc có bản sao ở nhiều nơi; nó còn đến từ khả năng giữ lỗi trong một miền nhỏ. Hãy xác định failure domain, giới hạn tài nguyên dùng chung, cô lập tenant và workload, thiết kế graceful degradation và kiểm chứng bằng diễn tập. Blast radius càng được đo và giới hạn rõ, hệ thống càng có khả năng tiếp tục phục vụ phần lớn người dùng khi một thành phần gặp sự cố.
