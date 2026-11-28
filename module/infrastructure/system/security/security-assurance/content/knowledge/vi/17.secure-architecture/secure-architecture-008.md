# Resilience boundary: thiết kế ranh giới cô lập sự cố và giới hạn phạm vi ảnh hưởng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **resilience boundary** và phân biệt nó với trust boundary, network boundary, service boundary và failure domain.
2. Xác định các miền lỗi trong kiến trúc: process, host, zone, region, tenant, service, control plane, data plane và nhà cung cấp phụ thuộc.
3. Thiết kế ranh giới cô lập để hạn chế **blast radius**, tránh một lỗi hoặc cuộc tấn công lan qua toàn hệ thống.
4. Áp dụng bulkhead, timeout, retry có giới hạn, circuit breaker, rate limit, backpressure, load shedding và graceful degradation đúng ngữ cảnh.
5. Đánh giá các quyết định **fail-open/fail-closed**, fallback và cache theo mục tiêu bảo mật, tính toàn vẹn nghiệp vụ và khả năng sẵn sàng.
6. Thiết kế khôi phục, failover, backup, RTO/RPO, SLO và khả năng vận hành khi một dependency quan trọng không hoạt động.
7. Chuyển threat model và kiến trúc thành **security requirements, controls, fault-injection tests, audit evidence và remediation**.

Trong module **SECURITY_SECURITY_ASSURANCE**, kiến trúc an toàn cần được chứng minh bằng hành vi của hệ thống khi có sự cố. Một dịch vụ có thể hoạt động đúng khi mọi dependency khỏe mạnh nhưng trở nên nguy hiểm khi IdP, KMS, database, audit pipeline hoặc mạng gặp lỗi. **Resilience boundary** xác định nơi hệ thống có thể cô lập lỗi, giới hạn quyền và tài nguyên bị ảnh hưởng, duy trì những chức năng cần thiết và phục hồi có kiểm soát.

## 1. Resilience boundary là gì?

**Resilience boundary** là ranh giới kiến trúc được thiết kế để một lỗi, quá tải, sự cố bảo mật hoặc mất dependency **không lan rộng ngoài phạm vi đã dự kiến**. Bên trong ranh giới, hệ thống có cơ chế phát hiện, cô lập, suy giảm chức năng an toàn và phục hồi. Giữa các ranh giới, giao tiếp được kiểm soát để tránh tạo đường lan truyền không giới hạn.

Ví dụ, một dịch vụ xử lý thanh toán dùng một pool kết nối riêng và quota riêng cho mỗi nhóm workload. Khi một tenant gửi quá nhiều yêu cầu, hệ thống có thể giới hạn tenant đó mà không làm cạn connection pool của mọi tenant. Đây là một resilience boundary ở cấp tài nguyên/tenant.

Resilience boundary không phải một đường kẻ trên sơ đồ. Nó cần được thể hiện bằng **cơ chế kỹ thuật, giới hạn tài nguyên, quyền truy cập, chính sách lỗi, quy trình vận hành và kết quả kiểm thử**.

### 1.1. Phân biệt các loại boundary

| Loại boundary | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Trust boundary** | Tại đâu giả định tin cậy thay đổi và cần xác thực/kiểm tra? | Internet → API gateway; service → vendor |
| **Resilience boundary** | Tại đâu lỗi được phát hiện và ngăn lan sang phần khác? | Bulkhead riêng cho payment worker |
| **Failure domain** | Một sự cố chung có thể làm hỏng những thành phần nào? | Một availability zone, cluster, region hoặc cloud account |
| **Network boundary** | Lưu lượng nào được phép đi qua ranh giới mạng? | Subnet, firewall, security group, service mesh |
| **Service boundary** | Thành phần nào sở hữu API, dữ liệu và trách nhiệm nghiệp vụ? | Payment service và notification service |
| **Tenant boundary** | Tài nguyên và dữ liệu của khách hàng được tách ra sao? | Tenant-scoped storage, quota và authorization |
| **Administrative boundary** | Ai có thể thay đổi cấu hình/quyền của hệ thống? | Production account tách khỏi development account |

Các boundary có thể trùng nhau nhưng không đồng nghĩa. Một subnet riêng có thể là network boundary nhưng không tạo resilience boundary nếu các service vẫn dùng chung database, queue và thread pool. Một service có API riêng có thể có service boundary nhưng vẫn chịu chung failure domain với mọi service khác nếu tất cả chạy trên một node hoặc phụ thuộc một control plane duy nhất.

### 1.2. Resilience không chỉ là availability

Resilience bao gồm khả năng **chịu lỗi, giới hạn tác động, duy trì chức năng quan trọng, phục hồi và thích nghi**. Tính sẵn sàng là một phần, nhưng một hệ thống vẫn có thể “available” trong khi:

- Trả dữ liệu sai hoặc dữ liệu cũ không phù hợp.
- Bỏ qua authorization vì policy service không phản hồi.
- Ghi nhận giao dịch trùng do retry.
- Mất audit evidence trong lúc failover.
- Cho phép một tenant tiêu thụ tài nguyên của tenant khác.
- Tắt kiểm tra chứng thư để “khắc phục nhanh” lỗi kết nối.

Vì vậy, resilience assurance phải đánh giá **availability, confidentiality, integrity, accountability và safety của nghiệp vụ** cùng lúc.

### 1.3. Một resilience boundary tốt cần chứng minh điều gì?

- Có **failure domain** và phạm vi ảnh hưởng được mô tả rõ.
- Có giới hạn tài nguyên và quyền giữa các workload/tenant.
- Có phát hiện dependency lỗi, quá tải hoặc hành vi bất thường.
- Có timeout, retry, queue và fallback với điều kiện xác định.
- Có quyết định rõ chức năng nào tiếp tục, chức năng nào bị hạn chế.
- Có bảo vệ authorization, integrity và audit trong trạng thái suy giảm.
- Có phương án phục hồi và đối soát sau khi dependency hoạt động trở lại.
- Có test chứng minh lỗi không vượt ranh giới và không tạo side effect sai.

## 2. Xác định failure domain và blast radius

**Failure domain** là phạm vi thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân lỗi. **Blast radius** là phạm vi tác động thực tế hoặc tiềm năng của sự cố. Thiết kế resilience boundary nhằm giảm khả năng một lỗi cục bộ biến thành sự cố toàn hệ thống.

### 2.1. Các lớp failure domain

| Lớp | Ví dụ lỗi | Câu hỏi cô lập |
|---|---|---|
| **Process** | Memory leak, deadlock, crash | Process có thể restart mà không làm mất toàn bộ service? |
| **Container/VM/host** | Node hỏng, disk full, kernel issue | Replica có nằm trên host khác? |
| **Cluster** | Scheduler, control plane hoặc shared storage lỗi | Cluster có thể cô lập workload hoặc chuyển sang cluster khác? |
| **Availability zone** | Mất nguồn, mạng hoặc dịch vụ trong một zone | Có capacity và data replication ở zone khác? |
| **Region** | Region outage, control-plane dependency | Có disaster recovery ở region khác và dữ liệu nhất quán? |
| **Service/dependency** | IdP, KMS, DNS, database, queue không phản hồi | Consumer có timeout, isolation và safe fallback? |
| **Tenant** | Noisy neighbor, tenant abuse, dữ liệu bị lẫn | Quota, partition và authorization có giới hạn tenant? |
| **Identity/privilege** | Service account hoặc admin bị compromise | Quyền có giới hạn theo workload và môi trường? |
| **Control plane** | Policy/config/deployment service lỗi | Data plane có tiếp tục an toàn theo trạng thái đã xác minh? |
| **Vendor/provider** | SaaS, cloud hoặc payment provider gián đoạn | Có dependency map, contract, fallback và exit/recovery plan? |

Một hệ thống có nhiều replica vẫn có thể có failure domain chung nếu tất cả replica:

- Dùng cùng một KMS key hoặc identity provider.
- Được deploy bởi cùng một pipeline lỗi.
- Chia sẻ một database hoặc DNS resolver.
- Dùng chung quota, connection pool hoặc network gateway.
- Phụ thuộc cùng một tài khoản quản trị có thể thay policy của tất cả.

**Số lượng replica không tự nói lên mức độc lập.** Cần tìm common-mode failures: một nguyên nhân duy nhất có thể làm hỏng nhiều bản sao cùng lúc.

### 2.2. Ví dụ blast radius

Một ứng dụng có 100 tenant. Mỗi tenant gửi yêu cầu báo cáo. Nếu tất cả request dùng một thread pool và một connection pool:

1. Tenant A tạo hàng nghìn báo cáo nặng.
2. Các request giữ connection lâu.
3. Pool cạn; request của tenant B, C và cả admin cũng bị chặn.
4. Notification worker và payment API có thể dùng chung tài nguyên, gây ảnh hưởng tiếp.

Nếu có **per-tenant quota, worker pool riêng, giới hạn concurrency và load shedding**, tenant A có thể bị giới hạn trong phạm vi nhỏ hơn. Tuy nhiên, nếu mọi tenant vẫn dùng chung database không có query/resource controls, blast radius vẫn có thể lan tới database.

### 2.3. Common-mode failure

Các nguyên nhân cần tìm trong threat modeling:

- Một cấu hình sai được rollout đồng thời tới tất cả replicas.
- Một chứng thư hoặc khóa chung hết hạn.
- Một policy IAM bị sửa làm mất quyền hoặc mở rộng quyền trên toàn account.
- Một DNS zone/resolver lỗi ảnh hưởng nhiều service.
- Một pipeline deploy phát hành cùng artifact lỗi tới mọi region.
- Một schema migration không tương thích làm mọi consumer ngừng xử lý.
- Một vendor outage ảnh hưởng tất cả chức năng phụ thuộc.
- Một account admin hoặc secret chung bị compromise.

**Đa vùng (multi-region) không đồng nghĩa độc lập hoàn toàn** nếu các vùng vẫn chia sẻ control plane, danh tính, khóa, cấu hình hoặc dữ liệu phụ thuộc không có phương án thay thế.

## 3. Vẽ ranh giới resilience trong kiến trúc

### 3.1. Bản đồ dependency và failure propagation

Sơ đồ dưới đây mô tả một nền tảng giao dịch. Các mũi tên thể hiện phụ thuộc cần đánh giá; một dependency lỗi có thể tác động nhiều service nếu không có boundary.

~~~mermaid
flowchart TD
    U["Customer / Operator"] --> G["API Gateway"]
    G --> I["Identity Provider"]
    G --> P["Payment API"]
    P --> D[("Payment DB")]
    P --> K["KMS"]
    P --> Q["Payment Queue"]
    Q --> W["Payment Worker"]
    W --> V["Payment Provider"]
    P --> A["Audit Pipeline"]
    W --> A
    G --> N["Notification Service"]
    N --> M["Messaging Provider"]
    C["Deployment / Config Control Plane"] --> G
    C --> P
    C --> W
    C --> N
~~~

Các câu hỏi:

- IdP lỗi có làm **mọi request** dừng hay chỉ request cần xác thực mới?
- KMS lỗi có ảnh hưởng đọc dữ liệu đã giải mã trong memory, tạo dữ liệu mới, hay tất cả?
- Queue lỗi có làm payment API chờ vô hạn?
- Notification provider lỗi có ngăn hoàn tất thanh toán?
- Audit pipeline lỗi có làm mất evidence hoặc buộc dừng hành động nhạy cảm?
- Config control plane lỗi có làm data plane không thể phục vụ request hiện tại?
- Một admin có thể thay cấu hình đồng thời ở tất cả region không?

### 3.2. Resilience boundary nên có owner và hợp đồng

Với mỗi boundary, ghi:

1. **Boundary ID và mục đích:** giới hạn lỗi hoặc quyền gì?
2. **Phạm vi:** service, process, tenant, queue, node, zone, region hay account?
3. **Failure assumptions:** lỗi nào được dự kiến, lỗi nào ngoài khả năng bảo vệ?
4. **Allowed dependencies:** thành phần nào được gọi qua boundary và với quyền nào?
5. **Resource limits:** timeout, concurrency, queue size, memory/CPU quota, rate limit.
6. **Degraded behavior:** chức năng nào tiếp tục, chức năng nào bị từ chối hoặc trì hoãn?
7. **Recovery:** điều kiện phục hồi, retry/replay, reconciliation và owner.
8. **Security invariants:** authorization, tenant isolation, audit và integrity phải còn đúng.
9. **Evidence:** test, telemetry, configuration snapshot và incident record.

### 3.3. Trust boundary và resilience boundary phối hợp

Một request đi qua service boundary cần **xác thực và authorization**; đồng thời phải chịu **timeout, quota và circuit breaker** để lỗi ở service đích không làm cạn tài nguyên nguồn.

~~~mermaid
flowchart LR
    subgraph A["Trust domain A"]
      C["Client / Workload"]
      X["AuthN + AuthZ"]
      C --> X
    end
    subgraph B["Resilience domain B"]
      R["Rate limit / quota"]
      T["Timeout + bulkhead"]
      S["Service"]
      R --> T --> S
    end
    X -->|"Authenticated, authorized request"| R
    S --> O["Bounded response / error"]
~~~

**Xác thực thành công không có nghĩa request được phép tiêu thụ tài nguyên vô hạn.** Ngược lại, một circuit breaker mở không được dẫn tới việc bỏ qua authorization hoặc trả dữ liệu nhạy cảm từ cache không còn hợp lệ.

## 4. Các mẫu thiết kế cô lập lỗi

### 4.1. Bulkhead — phân khoang tài nguyên

**Bulkhead** tách tài nguyên để sự cố của một workload không làm cạn tài nguyên của workload khác.

Ví dụ:

- Connection pool riêng cho payment và reporting.
- Thread/executor pool riêng cho tác vụ tương tác và batch.
- Quota CPU/memory theo tenant hoặc service.
- Queue riêng cho các loại công việc có mức quan trọng khác nhau.
- Giới hạn concurrency theo downstream provider.

| Không có bulkhead | Có bulkhead |
|---|---|
| Batch report giữ hết thread | Report có pool và concurrency riêng |
| Một tenant làm cạn connection | Per-tenant quota và giới hạn connection |
| Một provider chậm giữ request thread | Pool riêng, timeout và circuit breaker |
| Admin action bị ảnh hưởng bởi background job | Tài nguyên cho control/administrative path được bảo vệ |

Bulkhead cần thiết kế cẩn thận: chia quá nhỏ có thể làm lãng phí capacity; chia quá lớn vẫn để lại shared bottleneck. Phải đo tải và kiểm thử ở mức thực tế.

### 4.2. Timeout — giới hạn thời gian chờ

Mỗi lời gọi dependency cần có **timeout hữu hạn** phù hợp với ngân sách thời gian của request.

Ví dụ một API có tổng latency budget 2 giây. Nếu API gọi lần lượt IdP, database và vendor, không thể cấp timeout 2 giây cho từng dependency mà vẫn kỳ vọng tổng request hoàn thành trong 2 giây.

Nguyên tắc:

- Truyền **deadline/budget** qua các service, tránh mỗi lớp chờ tối đa riêng biệt.
- Chọn timeout theo latency distribution, mục tiêu SLO và loại thao tác.
- Phân biệt timeout kết nối, timeout đọc và timeout xử lý.
- Khi timeout, không giả định thao tác ở phía server chắc chắn chưa xảy ra.
- Với write operation, dùng idempotency key và kiểm tra trạng thái trước khi retry.

### 4.3. Retry có giới hạn

Retry có thể xử lý lỗi tạm thời nhưng cũng có thể tạo **retry storm**:

1. Dependency chậm.
2. Consumer timeout và retry.
3. Số request tăng khi dependency đang quá tải.
4. Dependency càng chậm, nhiều consumer tiếp tục retry.
5. Lỗi lan rộng thành outage.

Một chính sách retry nên xác định:

- Chỉ retry lỗi tạm thời đã phân loại.
- Giới hạn số lần và tổng thời gian.
- **Exponential backoff + jitter** để phân tán thời điểm retry.
- Không retry vô hạn hoặc ở mọi lớp cùng lúc.
- Chỉ retry write khi có idempotency hoặc cơ chế bảo vệ duplicate.
- Tôn trọng retry-after/rate limit của dependency khi phù hợp.
- Có metric để phát hiện retry amplification.

### 4.4. Circuit breaker — ngắt mạch dependency

Circuit breaker theo dõi lỗi/timeout và tạm ngừng gọi dependency khi ngưỡng được cấu hình đạt. Mô hình phổ biến:

- **Closed:** cho request đi qua, theo dõi kết quả.
- **Open:** từ chối nhanh hoặc chuyển sang degraded behavior.
- **Half-open:** cho một số probe có giới hạn để kiểm tra phục hồi.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Error/timeout threshold reached
    OPEN --> HALF_OPEN: Cooldown elapsed
    HALF_OPEN --> CLOSED: Probe succeeds
    HALF_OPEN --> OPEN: Probe fails
~~~

Circuit breaker **không phải cơ chế authorization** và không tự xác định fallback an toàn. Khi mở circuit:

- Không được trả dữ liệu từ tenant khác hoặc cache vượt thời hạn.
- Không được biến lỗi policy check thành mặc định allow.
- Không được coi một write request bị timeout là chắc chắn thất bại.
- Cần log trạng thái circuit và theo dõi khi circuit mở quá lâu.

### 4.5. Backpressure và bounded queue

**Backpressure** giúp nguồn gửi điều chỉnh tốc độ khi consumer không xử lý kịp. Queue phải có giới hạn:

- Giới hạn số message, byte, tuổi message và concurrency.
- Định nghĩa hành vi khi queue đầy: reject, defer, shed low-priority work hoặc route sang DLQ.
- Kiểm soát quyền publish/consume và bảo vệ payload.
- Định nghĩa retention và replay để message cũ không tạo side effect ngoài ý muốn.
- Giám sát queue age, consumer lag và DLQ growth.

Queue không phải kho vô hạn. Một queue không có quota có thể biến một dependency outage ngắn thành **sự cố storage hoặc chi phí kéo dài**.

### 4.6. Rate limiting và load shedding

Rate limiting bảo vệ tài nguyên trước lưu lượng vượt ngưỡng; load shedding chủ động bỏ hoặc từ chối công việc ít quan trọng khi hệ thống quá tải.

Có thể áp theo:

- Principal/user, tenant, API key hoặc workload identity.
- Endpoint, operation, resource hoặc downstream dependency.
- Tổng lưu lượng, concurrency, cost units hoặc request weight.
- Mức ưu tiên nghiệp vụ và ngân sách tài nguyên.

**Rate limit phải có ranh giới tenant và identity đáng tin.** Không dùng một header do client tự khai làm định danh duy nhất nếu attacker có thể đổi header để né quota. Admin bypass cũng cần policy, audit và giới hạn, không phải miễn trừ vô hạn.

### 4.7. Isolation theo tenant và cell-based architecture

**Cell-based architecture** chia hệ thống thành các cell tương đối độc lập; mỗi cell phục vụ một nhóm tenant hoặc workload và có tài nguyên/data plane riêng. Mục tiêu là giới hạn sự cố ở một cell.

~~~mermaid
flowchart TD
    E["Edge / routing layer"] --> R{"Tenant-to-cell routing"}
    R --> C1["Cell A"]
    R --> C2["Cell B"]
    R --> C3["Cell C"]
    subgraph A["Cell A - isolated resources"]
      C1 --> A1["API + queue + data partition"]
    end
    subgraph B["Cell B - isolated resources"]
      C2 --> B1["API + queue + data partition"]
    end
    subgraph C["Cell C - isolated resources"]
      C3 --> C1X["API + queue + data partition"]
    end
~~~

Cell isolation có thể bao gồm:

- Data partition hoặc database riêng.
- Queue, worker pool, quota và cache riêng.
- Key/policy scope phù hợp với tenant group.
- Giới hạn quyền admin và deployment.
- Health/routing riêng, có khả năng cô lập cell lỗi.

Nhưng cell vẫn có thể có common-mode dependency: **global IdP, shared KMS, global DNS, shared config plane hoặc central routing**. Cần ghi rõ dependency chung và cách xử lý khi chúng lỗi.

## 5. Graceful degradation và quyết định fail-open/fail-closed

### 5.1. Graceful degradation là gì?

**Graceful degradation** là khả năng duy trì chức năng cốt lõi khi một phần hệ thống không hoạt động, bằng cách **giảm chức năng có kiểm soát** thay vì sụp đổ toàn bộ hoặc bỏ qua yêu cầu bảo mật.

Ví dụ:

- Payment vẫn xử lý trạng thái đã xác minh nhưng tạm dừng xuất báo cáo.
- User có thể xem dữ liệu công khai đã cache, nhưng không thực hiện thay đổi nhạy cảm khi authorization không xác minh được.
- Notification bị trì hoãn trong queue, không làm giao dịch chính thất bại nếu nghiệp vụ cho phép.
- Dashboard analytics hiển thị dữ liệu cũ kèm timestamp, không giả vờ là dữ liệu real-time.

### 5.2. Fail-open và fail-closed

- **Fail-closed:** Khi không thể kiểm tra một điều kiện quan trọng, từ chối hoặc dừng hành động liên quan.
- **Fail-open:** Khi dependency lỗi, tiếp tục một số hoạt động theo chính sách fallback.

Không có lựa chọn nào đúng cho mọi dependency. Quyết định phải dựa trên **tác động bảo mật, toàn vẹn, khả dụng và khả năng phục hồi**.

| Dependency/operation | Hướng xử lý thường cần cân nhắc | Lý do và giới hạn |
|---|---|---|
| Authorization cho thay người nhận thanh toán | Fail-closed cho thao tác nhạy cảm | Không thể xác minh quyền thì không thay đổi trạng thái tài chính |
| Public content đã cache | Có thể tiếp tục đọc theo cache policy | Không được dùng cache để trả nội dung riêng tư vượt quyền |
| MFA/IdP cho admin action | Thường fail-closed hoặc dùng emergency workflow có kiểm soát | Không tự hạ mức xác thực khi IdP lỗi |
| KMS decrypt cho dữ liệu mới | Có thể từ chối/queue theo nghiệp vụ | Không lưu plaintext hoặc bỏ mã hóa để tiếp tục |
| Notification provider | Có thể queue và retry có giới hạn | Thông báo chậm có thể chấp nhận nếu không làm sai giao dịch |
| Fraud/risk scoring | Phụ thuộc mức rủi ro; có thể hold/review hoặc áp policy hạn chế | Không mặc định approve mọi giao dịch khi scorer down |
| Audit pipeline | Ghi vào durable local buffer hoặc dừng thao tác trọng yếu nếu không thể đảm bảo accountability | Không âm thầm bỏ audit evidence |
| DNS/service discovery | Dùng cache/secondary resolver theo policy | Phải kiểm tra TTL, authenticity và stale endpoint risk |

### 5.3. Quyết định fallback theo ma trận

Với mỗi chức năng, ghi:

1. **Business criticality:** Nếu không hoạt động thì tác động gì?
2. **Security impact:** Fallback có làm giảm authentication, authorization, confidentiality hoặc audit không?
3. **Integrity impact:** Có thể tạo giao dịch trùng, sai trạng thái hoặc mất dữ liệu không?
4. **Freshness:** Dữ liệu cache hoặc policy cũ được phép dùng tới khi nào?
5. **Scope:** Fallback ảnh hưởng một tenant hay toàn hệ thống?
6. **Approval:** Ai có quyền kích hoạt và trong điều kiện nào?
7. **Expiry:** Fallback kết thúc khi nào, tự động hay thủ công?
8. **Evidence:** Có log, alert, review và hậu kiểm không?

### 5.4. Không để fallback trở thành đường bypass

Các mẫu fallback nguy hiểm:

- IdP timeout → bỏ qua authentication.
- Policy engine timeout → mặc định allow.
- KMS lỗi → ghi plaintext vào database hoặc file tạm không bảo vệ.
- Certificate validation lỗi → tắt kiểm tra TLS.
- Audit service down → bỏ ghi log vô thời hạn.
- Fraud scorer down → tự động approve giao dịch rủi ro cao.
- Tenant routing lỗi → gửi request vào partition mặc định.

Nếu cần emergency path, hãy thiết kế **break-glass identity, quyền tối thiểu, điều kiện kích hoạt, thời hạn, independent approval, audit độc lập và hậu kiểm**. Emergency path cần được test như một control riêng.

## 6. Resilience của identity, authorization và policy

### 6.1. Identity provider outage

Khi IdP không truy cập được, hệ thống cần phân biệt:

- Session đã được xác thực và còn hiệu lực theo policy.
- Session hết hạn hoặc cần reauthentication.
- Đăng nhập mới.
- Thay đổi quyền hoặc thao tác privileged.
- Tài khoản emergency đã được phê duyệt.

Một số ứng dụng có thể tiếp tục phục vụ **session đã được xác minh** trong giới hạn thời gian/chính sách, trong khi chặn login mới hoặc thao tác nhạy cảm cần reauth. Điều này phải được thiết kế theo risk, không dùng một cache token không giới hạn.

### 6.2. Authorization policy engine unavailable

Nếu policy engine lỗi:

- Xác định quyết định nào có thể dùng **policy snapshot đã xác minh** và trong thời hạn nào.
- Xác định thao tác nào phải dừng vì cần policy mới hoặc kiểm tra quyền động.
- Không lấy một kết quả allow cũ để cấp quyền mới ngoài scope.
- Ghi nhận policy version, cache age và lý do fallback.
- Khi policy engine trở lại, đối chiếu quyết định trong thời gian degraded và kiểm tra quyền đã bị thu hồi.

**Stale authorization** là rủi ro thực tế: quyền có thể đã bị thu hồi trong lúc hệ thống dùng cache. Với privileged actions, data export hoặc thay đổi tài chính, freshness cần nghiêm ngặt hơn.

### 6.3. Session, token và revocation

Resilience design phải xét:

- Token expiry, refresh và key rotation.
- Session revocation khi tài khoản bị khóa hoặc credential compromise.
- Cache introspection/authorization và thời hạn chấp nhận.
- Hành vi khi identity provider hoặc signing-key metadata endpoint không truy cập được.
- Không chấp nhận token không xác minh được chữ ký hoặc issuer chỉ để tăng availability.

Có thể cần một chiến lược **degraded access** cho chức năng ít rủi ro, nhưng phải ghi rõ phạm vi, freshness, người duyệt và cách thu hồi khi hệ thống phục hồi.

## 7. Resilience của KMS, secrets và cryptographic operations

### 7.1. KMS unavailable

KMS lỗi có thể ảnh hưởng:

- Encrypt/decrypt dữ liệu mới hoặc dữ liệu đang đọc.
- Unwrap DEK trong envelope encryption.
- Ký token/artifact hoặc xác minh trust chain tùy kiến trúc.
- Khởi động workload cần lấy secret/credential.
- Restore backup cần key version cũ.

Thiết kế cần xác định **operation nào thực sự phụ thuộc KMS đồng bộ**, operation nào có thể dùng state đã được kiểm chứng và operation nào phải chờ. Không nên tự động cache raw key lâu dài để che outage nếu chưa đánh giá boundary, memory exposure và revocation.

### 7.2. Tách control plane và data plane

Một dịch vụ quản lý khóa có thể có các đường quản trị và sử dụng khác nhau. Cần kiểm tra:

- KMS management API lỗi có ảnh hưởng cryptographic operation hiện tại không?
- Key đã được cấp phát có thể tiếp tục dùng theo policy/cache nào?
- Policy change hoặc key rotation có bị trì hoãn không?
- Audit events có được buffer và gửi lại đầy đủ không?
- Failover sang region khác có cùng key version và trust policy không?

Không giả định mọi provider có cùng behavior. Phải dựa vào **tài liệu dịch vụ, cấu hình đang dùng, SLA và test thực tế**.

### 7.3. Khi key unavailable

- Không chuyển sang plaintext hoặc key mặc định yếu hơn.
- Giữ request có thể retry trong queue có giới hạn nếu nghiệp vụ cho phép.
- Chặn thao tác nhạy cảm khi không thể đáp ứng yêu cầu bảo vệ.
- Có runbook khôi phục KMS/key access và kiểm tra quyền.
- Sau phục hồi, đối chiếu request chưa xử lý, tránh duplicate và xác minh integrity.

## 8. Resilience của dữ liệu và giao dịch phân tán

### 8.1. Timeout không có nghĩa write thất bại

Ví dụ Payment API gửi yêu cầu sang provider. Request timeout có thể xảy ra **sau khi provider đã thực hiện giao dịch** nhưng trước khi response quay lại. Nếu API retry không có idempotency, có thể tạo thanh toán trùng.

Các control:

- Idempotency key gắn với một ý định nghiệp vụ ổn định.
- Lưu request state và provider reference.
- Retry có giới hạn, phân biệt lỗi chắc chắn thất bại với trạng thái chưa rõ.
- Reconciliation với provider sau timeout.
- Không báo thành công/thất bại khi trạng thái thực tế chưa được xác minh.

### 8.2. Outbox/inbox và event processing

Với giao dịch cần phát event:

- **Transactional outbox** giúp ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction logic.
- Consumer dùng **inbox/deduplication** hoặc idempotent handler để xử lý event lặp.
- Event có ID, version, timestamp và schema version.
- Dead-letter queue có owner, retention, access control và quy trình replay.
- Replay không được bỏ qua authorization hoặc làm hồi sinh trạng thái đã bị hủy/xóa theo policy.

### 8.3. Saga và compensation

Trong workflow nhiều service, không phải lúc nào cũng có một transaction phân tán duy nhất. **Saga** chia quy trình thành các bước và có compensation khi bước sau thất bại.

Ví dụ đặt hàng:

1. Tạo order ở trạng thái pending.
2. Reserve inventory.
3. Authorize payment.
4. Confirm order.
5. Nếu payment thất bại, release inventory theo quy tắc.

Compensation không phải lúc nào cũng đảo ngược hoàn toàn một hành động đã xảy ra. Với giao dịch tài chính, cần **reversal/refund workflow**, audit và approval; không xóa lịch sử để giả vờ hành động chưa từng xảy ra.

### 8.4. Consistency và degraded mode

Nếu một replica chậm hoặc region bị partition:

- Không dùng dữ liệu stale để cho phép hành động cần trạng thái mới nhất.
- Hiển thị thời điểm dữ liệu được cập nhật nếu chỉ có thể cung cấp snapshot.
- Giới hạn thao tác ghi khi không thể bảo đảm consistency cần thiết.
- Định nghĩa conflict resolution và reconciliation.
- Test split-brain, duplicate events và out-of-order messages.

## 9. Resilience của network, DNS, TLS và service discovery

### 9.1. Network partition

Network partition có thể khiến hai thành phần không biết trạng thái của nhau. Hệ thống cần:

- Timeout và retry có giới hạn.
- Health check không nhầm **process alive** với **service ready**.
- Routing loại bỏ endpoint không khỏe theo tiêu chí đã định.
- Giữ authorization và service identity khi failover.
- Tránh fallback tới endpoint không xác minh được danh tính.
- Có phương án phục hồi dữ liệu/event sau khi kết nối trở lại.

### 9.2. DNS và service discovery

DNS lỗi có thể làm service không tìm thấy dependency; DNS bị giả mạo hoặc cấu hình sai có thể định tuyến tới endpoint không tin cậy.

Kiểm tra:

- Resolver dự phòng và cache TTL có phù hợp không?
- DNSSEC hoặc cơ chế xác minh tương ứng có áp dụng khi cần?
- Service identity/TLS certificate vẫn được kiểm tra sau khi đổi endpoint?
- Endpoint cache cũ có thể trỏ tới IP đã được tái sử dụng?
- Admin có thể sửa record ảnh hưởng nhiều service mà không có review?

Không dùng IP fallback cố định nếu không có quy trình cập nhật, xác minh identity và quản lý certificate.

### 9.3. TLS/certificate expiry

Certificate hết hạn có thể gây outage; tắt certificate validation để khôi phục kết nối có thể tạo MITM vulnerability.

Resilience controls:

- Theo dõi certificate inventory, expiry và renewal status.
- Tự động gia hạn với monitoring và cảnh báo lỗi.
- Kiểm thử renewal trên staging và xác minh endpoint thực sự dùng cert mới.
- Có overlap window/rollout theo thiết kế để tránh downtime.
- Giữ certificate validation; nếu trust chain lỗi, xử lý nguyên nhân và dùng quy trình khẩn cấp có kiểm soát.

## 10. Multi-zone, multi-region và disaster recovery

### 10.1. High availability khác disaster recovery

| Khái niệm | Mục tiêu | Ví dụ |
|---|---|---|
| **High availability (HA)** | Duy trì dịch vụ khi một thành phần/zone lỗi | Nhiều replica qua các zone |
| **Disaster recovery (DR)** | Khôi phục sau sự cố lớn làm mất môi trường chính | Backup/replication sang region khác |
| **Backup** | Có bản dữ liệu có thể dùng để khôi phục | Snapshot, point-in-time backup |
| **Failover** | Chuyển hoạt động sang thành phần/vùng thay thế | Route sang standby region |
| **Failback** | Chuyển lại môi trường chính sau khắc phục | Đồng bộ và chuyển traffic có kiểm soát |

HA không thay backup; replication có thể sao chép cả lỗi hoặc thao tác xóa nhầm. Backup không tự chứng minh restore thành công.

### 10.2. RTO và RPO

- **RTO (Recovery Time Objective):** mục tiêu thời gian khôi phục dịch vụ sau gián đoạn.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa theo thời gian mà tổ chức chấp nhận trong kịch bản đã định.

Các mục tiêu này cần xuất phát từ **business impact analysis và risk appetite**, không chọn tùy tiện vì nền tảng có một con số mặc định.

Ví dụ giả định:

| Workload | RTO minh họa | RPO minh họa | Ghi chú |
|---|---:|---:|---|
| Payment authorization | 30 phút | 1 phút | Mức ưu tiên cao; cần kiểm tra provider state và duplicate |
| Customer reporting | 8 giờ | 4 giờ | Có thể chấp nhận dữ liệu chậm hơn |
| Internal analytics | 24 giờ | 12 giờ | Có thể tái tạo một phần từ nguồn |

Đây chỉ là ví dụ học tập. Giá trị thật cần được business owner phê duyệt và kiểm chứng bằng recovery exercise.

### 10.3. Active-active và active-passive

| Mô hình | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|
| **Active-passive** | Mô hình chính/phụ rõ, có thể đơn giản hóa write ownership | Standby có thể lỗi thời, failover chậm hoặc chưa từng được thử |
| **Active-active** | Nhiều vùng cùng phục vụ, có thể giảm thời gian chuyển đổi | Conflict, split-brain, consistency, duplicate và global dependency phức tạp |

Không chọn active-active chỉ vì nghe có vẻ resilient. Phải xác định **data consistency, write ownership, idempotency, routing, key availability, identity và audit** trên cả hai vùng.

### 10.4. Failover có kiểm soát

Một quy trình failover nên:

1. Xác minh sự cố và phạm vi, không kích hoạt chỉ vì một health check đơn lẻ.
2. Kiểm tra trạng thái dữ liệu, replication lag, key availability và dependency health.
3. Đánh giá quyền, routing, certificates, secrets và policy của vùng thay thế.
4. Ngăn hai vùng cùng nhận write trái thiết kế.
5. Chuyển traffic theo kế hoạch, theo dõi error rate và business invariants.
6. Đối soát giao dịch/event, xử lý duplicate hoặc incomplete states.
7. Lưu approval, timestamps, metrics, test results và quyết định failback.

### 10.5. Recovery không được bỏ qua security controls

Sau restore/failover, kiểm tra:

- IAM/authorization policies và tenant boundaries.
- KMS keys, key versions, certificate trust và secrets.
- Audit log integrity, retention và pipeline.
- Security agents, monitoring, alert routing.
- Data classification, deletion/restriction state và legal holds.
- Patch/config version, artifact integrity và deployment provenance.
- Backup access, emergency identities và quyền tạm thời.

Một region đã phục hồi nhưng **chưa có audit, policy hoặc access controls** không được coi là môi trường production an toàn.

## 11. Resilience boundary trong cloud và container platforms

### 11.1. Kubernetes/container orchestration

Những cơ chế như pod replicas, readiness/liveness probes, resource requests/limits, node affinity, topology spread và disruption budgets có thể hỗ trợ resilience. Nhưng cấu hình phải được kiểm tra theo failure domain thực:

- Replica có thực sự phân bố qua node/zone khác nhau?
- Một workload có thể tiêu thụ hết CPU/memory hoặc ephemeral storage?
- Readiness probe có loại instance lỗi khỏi traffic đúng cách?
- Liveness probe có restart hàng loạt khi dependency ngoài cluster chậm?
- Pod disruption budget có làm cản trở maintenance hoặc tạo false confidence?
- Secret mount, service account và network policy có nhất quán khi reschedule?

**Liveness probe không nên phụ thuộc mọi downstream service** nếu một dependency outage sẽ khiến toàn bộ pod restart liên tục. Phân biệt process liveness với readiness của chức năng cụ thể.

### 11.2. Resource isolation

| Tài nguyên | Boundary/guardrail | Failure cần tránh |
|---|---|---|
| CPU/memory | Requests/limits, quota, autoscaling | Noisy neighbor và OOM cascade |
| Disk/ephemeral storage | Quota, retention, log rotation | Disk full làm chết node/service |
| Network | Egress rules, connection limits | Một workload mở quá nhiều kết nối |
| Threads/connections | Pool riêng, concurrency limit | Pool exhaustion lan sang service khác |
| Queue | Max depth/age, DLQ policy | Message backlog vô hạn |
| API calls | Per-tenant/per-principal rate limit | Abuse và resource exhaustion |
| Secrets/KMS operations | Operation quota và principal scope | Một workload gọi KMS quá mức hoặc quá rộng |

### 11.3. Cloud account/project boundary

Tách account/project cho production, staging và development có thể giảm blast radius của:

- IAM policy mistakes.
- Resource deletion hoặc quota exhaustion.
- Secret/key exposure.
- Deployment automation compromise.
- Logging/configuration changes.

Nhưng shared organization-level admin, identity provider, billing/quota hoặc central network vẫn có thể là common-mode dependency. Inventory phải ghi rõ **shared control plane** và quyền ảnh hưởng nhiều account.

## 12. Kiến trúc tham chiếu và policy mẫu

### 12.1. Ví dụ phân vùng hệ thống thanh toán

Một thiết kế tham chiếu có thể tách:

- **Edge/API boundary:** xác thực, rate limit, request size limit và routing.
- **Payment critical cell:** payment API, queue/worker, database và key policy theo scope.
- **Reporting cell:** worker/DB/cache riêng, không chiếm tài nguyên payment.
- **Notification cell:** retry/queue riêng; lỗi nhà cung cấp thông báo không làm giao dịch thất bại nếu nghiệp vụ cho phép.
- **Control plane:** deployment, config và administrative access được tách quyền.
- **Audit plane:** log được gửi tới nơi có quyền sửa/xóa độc lập với workload cần giám sát.

~~~mermaid
flowchart TD
    U["Users / partners"] --> E["Edge: AuthN, AuthZ,<br/>rate limits"]
    E --> P["Payment critical cell"]
    E --> R["Reporting cell"]
    E --> N["Notification cell"]
    P --> PD[("Payment data")]
    P --> PK["Payment KMS policy"]
    P --> PQ["Payment queue"]
    PQ --> PW["Payment workers"]
    R --> RD[("Reporting data/cache")]
    N --> NQ["Notification queue"]
    NQ --> NP["Messaging provider"]
    CP["Restricted control plane"] --> P
    CP --> R
    CP --> N
    P --> AL["Protected audit plane"]
    R --> AL
    N --> AL
~~~

Điểm quan trọng không phải số lượng cell, mà là **tài nguyên, quyền, data path, failure handling và audit** có được cô lập đủ theo mục tiêu không.

### 12.2. YAML minh họa resilience policy

Đây là **mẫu giáo dục**, không phải schema cấu hình chuẩn của cloud provider hay service mesh:

~~~yaml
resiliencePolicy:
  id: RES-PAYMENTS-PROD-01
  version: "1.0"
  status: illustrative
  system: payments-platform
  ownerRole: Payments Platform Owner
  riskOwnerRole: Payments Risk Owner

  boundaries:
    - id: BOUNDARY-PAYMENT-CELL
      type: tenant-workload-cell
      scope:
        environment: production
        workload: payment-critical
      isolation:
        databasePartition: payments-prod
        queue: payment-critical-queue
        workerPool: payment-workers
        resourceQuotaReference: QUOTA-PAYMENT-CRITICAL
      sharedDependencies:
        - identity-provider
        - kms-service
        - protected-audit-platform

  dependencyPolicies:
    - dependency: payment-provider
      timeoutReference: PAYMENT-PROVIDER-TIMEOUT
      retryPolicyReference: PAYMENT-IDEMPOTENT-RETRY
      circuitBreakerReference: PAYMENT-PROVIDER-CIRCUIT
      fallback: hold-and-reconcile
    - dependency: notification-provider
      timeoutReference: NOTIFICATION-TIMEOUT
      retryPolicyReference: NOTIFICATION-BOUNDED-RETRY
      fallback: bounded-queue
    - dependency: authorization-service
      fallback: deny-sensitive-actions
      cachePolicyReference: AUTHZ-CACHE-FRESHNESS
    - dependency: kms-service
      fallback: no-plaintext-degraded-mode
      recoveryReference: KMS-RECOVERY-RUNBOOK

  securityInvariants:
    - tenant-isolation-preserved
    - authorization-required-for-state-change
    - payment-idempotency-enforced
    - audit-events-retained
    - no-unapproved-plaintext-fallback

  recovery:
    rtoReference: PAYMENT-RTO-APPROVED
    rpoReference: PAYMENT-RPO-APPROVED
    failoverRunbook: PAYMENT-REGION-FAILOVER
    restoreReconciliation: PAYMENT-DATA-RECONCILIATION

  assurance:
    tests:
      - TEST-TENANT-RESOURCE-ISOLATION
      - TEST-PAYMENT-DEPENDENCY-TIMEOUT
      - TEST-PROVIDER-RETRY-IDEMPOTENCY
      - TEST-AUTHORIZATION-DEPENDENCY-OUTAGE
      - TEST-KMS-UNAVAILABLE
      - TEST-AUDIT-PIPELINE-DEGRADED
      - TEST-REGION-FAILOVER
    evidenceReferences:
      - EV-RESILIENCE-ARCHITECTURE-REVIEW
      - EV-FAILOVER-EXERCISE
    knownGaps:
      - vendor-region-recovery-not-yet-verified
~~~

Các giá trị tham chiếu như TEST-PAYMENT-DEPENDENCY-TIMEOUT là **đầu mối evidence**, chưa chứng minh bài test đã chạy. Cần kết quả thực tế, môi trường, release, expected/actual, người kiểm tra và giới hạn.

### 12.3. Hợp đồng dependency

Mỗi dependency nên có một contract vận hành:

| Thuộc tính | Nội dung |
|---|---|
| Owner | Team chịu trách nhiệm dependency và consumer |
| Criticality | Mức quan trọng với chức năng nghiệp vụ |
| Timeout/deadline | Giới hạn thời gian và ngân sách tổng |
| Retry | Loại lỗi, số lần, backoff, idempotency |
| Circuit breaker | Điều kiện mở/đóng và half-open probes |
| Capacity | Quota, concurrency, queue limit |
| Fallback | Chức năng tiếp tục/dừng và security invariants |
| Observability | Metrics, logs, traces, alerts |
| Recovery | Runbook, RTO/RPO, reconciliation |
| Security | AuthN/AuthZ, TLS, data classification, audit |

## 13. Threat modeling: attacker có thể khai thác trạng thái lỗi

### 13.1. Kịch bản tấn công

| Attack path | Ý đồ | Resilience control cần có |
|---|---|---|
| **Resource exhaustion** | Làm cạn thread, CPU, memory, DB pool | Quota, rate limit, bulkhead, load shedding |
| **Retry amplification** | Khuếch đại request vào dependency yếu | Retry budget, backoff/jitter, circuit breaker |
| **Tenant noisy neighbor** | Làm tenant khác không truy cập được | Tenant isolation, fair scheduling, per-tenant limits |
| **Dependency outage → fail-open** | Tận dụng fallback để vượt authorization | Explicit fallback policy, deny sensitive actions |
| **Stale policy/session** | Dùng quyền cũ sau khi bị thu hồi | Freshness limits, revocation handling, step-up |
| **Queue poisoning/replay** | Đưa message sai hoặc lặp để gây side effects | Authenticated producers, schema validation, idempotency |
| **Failover abuse** | Ép chuyển vùng hoặc chiếm endpoint fallback | Approved routing, endpoint identity, failover audit |
| **Control-plane compromise** | Thay cấu hình nhiều cell/region | Admin isolation, SoD, signed deployment, independent logs |
| **Audit pipeline disruption** | Làm hành động trái phép không để lại dấu vết | Durable buffer, health alert, protected audit plane |
| **Certificate expiry/validation bypass** | Tạo outage rồi dụ operator tắt TLS validation | Renewal monitoring, safe runbook, negative tests |

### 13.2. Security invariants khi degraded

Trong mọi trạng thái degraded, phải xác định những thuộc tính **không được vi phạm**:

- Không truy cập chéo tenant.
- Không cấp quyền khi không thể xác minh điều kiện cần thiết.
- Không ghi dữ liệu nhạy cảm plaintext vào nơi fallback không được bảo vệ.
- Không tạo giao dịch trùng hoặc mất dấu trạng thái chưa xác định.
- Không bỏ qua audit đối với hành động nhạy cảm.
- Không dùng certificate/endpoint không xác minh được danh tính.
- Không cho quyền emergency tồn tại vô thời hạn.

Một chức năng có thể tạm dừng nhưng vẫn giữ các invariants này. **Degraded mode không phải vùng miễn trừ security policy.**

## 14. Kiểm thử resilience và fault injection

### 14.1. Từ giả định tới testable requirement

Không viết chung chung “hệ thống phải resilient”. Hãy chuyển thành yêu cầu:

| Requirement ID | Yêu cầu mẫu | Tiêu chí đo/kiểm tra |
|---|---|---|
| RES-01 | Lỗi reporting không làm cạn tài nguyên payment | Khi report pool đầy, payment workload vẫn đạt giới hạn đã duyệt |
| RES-02 | Dependency timeout không tạo request chờ vô hạn | Request kết thúc theo deadline và có trạng thái kiểm tra được |
| RES-03 | Retry không tạo duplicate payment | Cùng idempotency key chỉ tạo một hiệu ứng nghiệp vụ |
| RES-04 | Authorization outage không cho phép state change nhạy cảm | Sensitive action bị từ chối hoặc giữ theo policy |
| RES-05 | Notification outage không làm mất payment result | Event được lưu/queue có giới hạn và xử lý lại an toàn |
| RES-06 | Một tenant không tiêu thụ tài nguyên vô hạn | Quota/rate limit được enforce và tenant khác vẫn có capacity |
| RES-07 | Audit outage được phát hiện và xử lý theo policy | Buffer/alert hoặc controlled stop, không silent drop |
| RES-08 | Region failover bảo toàn tenant/authz/integrity | Post-failover tests và reconciliation đạt |
| RES-09 | KMS outage không dẫn đến plaintext fallback | Không có path ghi plaintext trái policy |
| RES-10 | Recovery không khôi phục trạng thái bị thu hồi/xóa trái quy định | Restore reconciliation áp dụng các quyết định còn hiệu lực |

### 14.2. Fault injection và chaos engineering

**Fault injection** chủ động tạo lỗi có kiểm soát để kiểm tra phản ứng. **Chaos engineering** xây dựng giả thuyết, thử nghiệm trong phạm vi được quản lý và học từ kết quả để tăng độ tin cậy.

Các loại thử nghiệm:

- Tăng latency hoặc trả timeout từ một dependency.
- Dừng một replica, node hoặc zone trong môi trường kiểm thử phù hợp.
- Giới hạn CPU/memory/connection để xem bulkhead hoạt động.
- Làm queue consumer chậm hoặc queue đầy.
- Mô phỏng KMS, IdP, DNS hoặc audit pipeline unavailable.
- Thử certificate gần hết hạn/rotation failure trong môi trường an toàn.
- Mô phỏng region failover và failback.
- Gửi event lặp, out-of-order hoặc retry sau timeout.
- Thử tenant vượt quota và kiểm tra tác động tới tenant khác.

Không chạy chaos experiment vượt quá phạm vi được phép hoặc có thể gây mất dữ liệu/gián đoạn nghiêm trọng. Với production, cần **scope, approval, blast-radius guardrails, stop conditions, rollback và người giám sát**. Một bài test có phép phải có giả thuyết và tiêu chí dừng rõ ràng.

### 14.3. Gherkin minh họa

~~~gherkin
Feature: Resilience boundary assurance for payments

  Scenario: Reporting saturation does not exhaust payment resources
    Given reporting and payment workloads have separate resource pools
    And the reporting pool reaches its approved concurrency limit
    When additional reporting requests arrive
    Then excess reporting work must be rejected or deferred safely
    And payment requests must retain their reserved capacity

  Scenario: Authorization outage does not permit a sensitive state change
    Given a payment beneficiary change requires a fresh authorization decision
    And the authorization service is unavailable
    When a user requests the beneficiary change
    Then the change must not be committed
    And the degraded decision must be recorded

  Scenario: Provider timeout does not duplicate a payment
    Given payment request P1 has a stable idempotency key
    And the provider may complete the operation before a timeout is returned
    When the client retries P1 within the approved policy
    Then the system must reconcile the provider result
    And no duplicate payment effect may be created

  Scenario: Notification outage does not lose a committed payment event
    Given a payment has been committed
    And the notification provider is unavailable
    When the notification delivery is attempted
    Then the event must enter the approved bounded retry path
    And payment state must remain correct

  Scenario: KMS outage never falls back to plaintext storage
    Given payment data must be encrypted using the approved key policy
    And KMS cryptographic operations are unavailable
    When the application attempts to persist new sensitive data
    Then the application must follow the approved safe failure behavior
    And plaintext must not be written as a fallback

  Scenario: One tenant cannot exhaust shared capacity
    Given tenant A and tenant B use the same platform
    And tenant A exceeds its approved workload quota
    When tenant A submits additional requests
    Then tenant A must be limited within its isolation boundary
    And tenant B must retain its reserved service capacity

  Scenario: Region failover preserves security controls
    Given the primary region is declared unavailable
    And the approved recovery region is ready
    When the controlled failover procedure completes
    Then authentication and tenant authorization must remain enforced
    And audit collection and data reconciliation must be verified
~~~

### 14.4. Bằng chứng của một fault-injection test

Một báo cáo test cần:

1. **Hypothesis:** điều gì được kỳ vọng khi dependency/zone/tenant gặp lỗi?
2. **Scope:** service, tenant, environment, version, data và failure domain.
3. **Preconditions:** health baseline, traffic, monitoring và rollback.
4. **Fault:** lỗi nào được tạo, thời điểm, mức độ và thời gian kéo dài.
5. **Expected behavior:** chức năng tiếp tục/dừng, security invariants, RTO/RPO/SLO.
6. **Actual behavior:** metrics, logs, traces, business state, error rate và user impact.
7. **Safety controls:** stop condition, người giám sát, rollback và kết quả.
8. **Findings:** propagation ngoài dự kiến, control failure, owner và remediation.
9. **Retest:** bằng chứng lỗi đã được khắc phục và boundary giữ đúng phạm vi.

Không kết luận “pass” chỉ vì pod tự restart. Cần xác minh **người dùng có bị lộ dữ liệu, giao dịch có bị trùng, tenant khác có bị ảnh hưởng và audit có còn đủ không**.

## 15. Observability, SLO và recovery evidence

### 15.1. Metrics theo dõi resilience

| Metric | Điều cần quan sát | Ý nghĩa assurance |
|---|---|---|
| **Dependency latency/error rate** | p95/p99, timeout, error class | Phát hiện degradation trước khi lan rộng |
| **Retry amplification** | Số request retry so với request gốc | Nhận biết retry storm |
| **Circuit breaker state** | Open/half-open duration và số lần chuyển trạng thái | Kiểm tra dependency isolation |
| **Pool saturation** | Thread, connection, CPU, memory, disk | Chứng minh bulkhead/quota |
| **Queue depth/age/lag** | Message tồn, tuổi, DLQ | Phát hiện backlog và replay risk |
| **Tenant fairness** | Tỷ lệ resource/request theo tenant | Kiểm tra noisy-neighbor containment |
| **Fail-open events** | Số lần fallback giảm kiểm tra | Theo dõi security exposure |
| **Authorization stale-cache age** | Tuổi policy/session cache | Đánh giá quyền cũ |
| **Audit event completeness** | Expected vs received events | Phát hiện mất accountability |
| **Failover/recovery duration** | Thời gian phát hiện, quyết định, chuyển vùng, xác minh | So với RTO |
| **Data loss/reconciliation gaps** | Số giao dịch/event cần đối soát | So với RPO và integrity objective |
| **Isolation violations** | Sự cố vượt tenant/cell/resource boundary | Chỉ báo trực tiếp của containment failure |

### 15.2. SLO và error budget

**Service Level Indicator (SLI)** là chỉ số đo một thuộc tính dịch vụ; **Service Level Objective (SLO)** là mục tiêu được chọn cho SLI trong một khoảng thời gian. Error budget mô tả mức lỗi/gián đoạn có thể chấp nhận theo SLO.

Ví dụ:

- Tỷ lệ request payment thành công trong điều kiện hợp lệ.
- Latency của API dưới ngưỡng đã duyệt.
- Tỷ lệ notification được giao trong thời gian mục tiêu.
- Tỷ lệ audit events được ghi nhận đầy đủ.
- Tỷ lệ recovery drill đạt RTO/RPO.

Không nên dùng một SLO availability duy nhất để đại diện resilience. Có thể có API vẫn trả 200 nhưng **authorization bị bỏ qua hoặc dữ liệu sai**; cần các SLI về correctness, security control và evidence completeness.

### 15.3. Incident và post-incident review

Sau sự cố, cần đánh giá:

- Boundary nào giữ được lỗi và boundary nào bị vượt?
- Dependency chung nào tạo common-mode failure?
- Có fallback nào làm suy giảm security control?
- Retry, queue hoặc failover có tạo duplicate/loss?
- Tenant hoặc dữ liệu nào bị ảnh hưởng?
- Audit, identity, key và monitoring có hoạt động trong suốt sự cố?
- RTO/RPO thực tế so với mục tiêu?
- Runbook, ownership và communication có phù hợp?
- Finding nào cần remediation, deadline và retest?

Post-incident review nên tập trung vào **nguyên nhân hệ thống và thay đổi kiểm soát**, không chỉ xác định một thao tác cá nhân.

## 16. Governance, RACI và quyết định kiến trúc

### 16.1. Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| **System/architecture owner** | Xác định boundary, dependency, failure domains và kiến trúc mục tiêu |
| **Service owner** | Vận hành timeout, retry, bulkhead, circuit breaker và fallback |
| **Platform/SRE** | Hạ tầng, capacity, observability, failover và recovery drills |
| **Security architect** | Threat model, trust boundaries, access policy và security invariants |
| **Data owner** | Integrity, retention, RPO/RTO và reconciliation dữ liệu |
| **Identity/KMS owner** | Resilience của IdP, policy, key access và recovery |
| **Incident commander** | Điều phối response, containment, escalation và quyết định khẩn cấp |
| **Risk owner** | Đánh giá residual risk và chấp nhận rủi ro theo thẩm quyền |
| **Security assurance/QA** | Kiểm tra thiết kế, test, evidence, findings và retest |
| **Internal audit** | Đánh giá độc lập trong phạm vi được giao |

### 16.2. RACI minh họa

RACI: **R** thực hiện; **A** chịu trách nhiệm cuối cùng; **C** tham vấn; **I** được thông báo.

| Hoạt động | Architecture owner | Service/SRE | Security | Data owner | Assurance |
|---|---|---|---|---|---|
| Phân tích failure domains và boundary | **A/R** | R | C | C | C |
| Định nghĩa degraded behavior | A | **R** | **C** | C | C |
| Phê duyệt security invariants | C | C | **A/R** | C | C |
| Đặt RTO/RPO | C | R | C | **A** | C |
| Chạy fault-injection/recovery test | A | **R** | R | C | C |
| Đánh giá evidence và finding | C | C | C | C | **A/R** |
| Chấp nhận residual risk | I | C | C | C | I |

Người có quyền chấp nhận rủi ro phải theo **risk governance thực tế**. Người vận hành không mặc nhiên có quyền chấp nhận việc bỏ authorization, mất audit hoặc fail-open cho thao tác nhạy cảm.

### 16.3. Architecture Decision Record (ADR)

Mỗi quyết định quan trọng về resilience nên ghi:

- Context và business requirement.
- Failure scenarios và threat assumptions.
- Boundary options đã cân nhắc.
- Phương án chọn và lý do.
- Security invariants và degraded behavior.
- Dependency, common-mode risk và residual risk.
- RTO/RPO/SLO và capacity assumptions.
- Test/monitoring/evidence cần có.
- Owner, approval, version và trigger xem xét lại.

ADR giúp reviewer hiểu **vì sao hệ thống fail-closed ở thao tác này nhưng vẫn queue thao tác khác**, hoặc vì sao một shared dependency được chấp nhận cùng biện pháp giảm thiểu.

## 17. Case study: Notification outage làm gián đoạn thanh toán

Một nền tảng thanh toán gồm Payment API, Payment DB, Notification Service và một nhà cung cấp SMS/email. Sau một đợt tăng lưu lượng, nhà cung cấp notification phản hồi rất chậm.

Kiến trúc ban đầu có:

1. Payment API gọi Notification Service đồng bộ trong cùng request thread.
2. Hai service dùng chung connection pool và worker executor.
3. Retry không giới hạn khi timeout.
4. Notification Service giữ connection chờ provider.
5. Payment API chỉ commit trạng thái thanh toán sau khi gửi notification thành công.
6. Dashboard chỉ đo HTTP availability, không theo dõi duplicate, queue age hay payment state.

Kết quả: provider chậm khiến pool cạn, payment API timeout, client retry và một số request tạo trạng thái không nhất quán. Một số thông báo đã được gửi nhưng client nhận lỗi; nhân viên vận hành không biết giao dịch nào đã thực hiện.

### 17.1. Phân tích failure propagation

| Thành phần | Lỗi trực tiếp | Tác động lan |
|---|---|---|
| Messaging provider | Latency/timeout | Notification workers giữ tài nguyên |
| Notification Service | Retry không giới hạn | Connection/thread pool bị chiếm |
| Payment API | Dùng chung pool và chờ đồng bộ | Payment request timeout |
| Client | Retry request không idempotent | Nguy cơ duplicate |
| Payment DB | State transition phụ thuộc notification | Trạng thái nghiệp vụ không rõ |
| Audit/monitoring | Không có correlation/queue metrics | Khó xác định actual outcome |

### 17.2. Thiết kế lại resilience boundary

**Tách luồng nghiệp vụ:** Payment API ghi nhận giao dịch và notification event theo transaction/outbox; notification được xử lý bất đồng bộ khi nghiệp vụ cho phép.

**Tách tài nguyên:** Notification có worker pool, connection pool, queue và quota riêng. Provider chậm không làm cạn tài nguyên payment.

**Giới hạn retry:** Retry bounded với exponential backoff/jitter; circuit breaker mở khi provider lỗi; message quá hạn chuyển DLQ theo policy.

**Bảo vệ integrity:** Payment request dùng idempotency key; trạng thái giao dịch có thể đối soát; notification không được tạo lại payment.

**Degraded behavior:** Payment có thể hoàn tất nếu điều kiện nghiệp vụ không phụ thuộc notification; thông báo được queue và hiển thị trạng thái chờ. Nếu notification là điều kiện pháp lý/nghiệp vụ bắt buộc trước một bước cụ thể, workflow phải giữ đúng điều kiện đó thay vì mặc định bỏ qua.

**Observability:** Theo dõi provider latency, retry amplification, queue age, DLQ, payment state và notification delivery correlation.

**Recovery:** Khi provider trở lại, drain queue theo rate limit, chống duplicate, đối soát event và ghi nhận lỗi không thể giao.

### 17.3. Kết luận assurance

> **Claim:** Sự cố của nhà cung cấp notification không làm cạn tài nguyên payment hoặc tạo giao dịch trùng trong phạm vi hệ thống và kịch bản đã kiểm thử.
>
> **Argument:** Notification được tách resource pool và queue; payment state được commit độc lập theo business rule; retry có giới hạn; idempotency và reconciliation bảo vệ integrity.
>
> **Evidence:** Architecture/ADR, resource configuration, fault-injection test, payment state assertions, duplicate checks, queue/DLQ metrics và recovery exercise.
>
> **Limitations:** Chưa bao phủ outage đồng thời của database và KMS; vùng DR của notification provider chưa có test độc lập. Những dependency này cần ghi trong risk register và kế hoạch test tiếp theo.

### 17.4. Bài học

- Dependency phụ trợ không nên chiếm tài nguyên của luồng cốt lõi nếu nghiệp vụ cho phép tách.
- Timeout và retry cần được thiết kế cùng idempotency và state reconciliation.
- Graceful degradation phải tuân theo business rule; không phải mọi notification đều có thể trì hoãn.
- Dashboard availability không đủ; phải đo correctness và evidence.
- Resilience boundary chỉ được chứng minh khi test thực tế cho thấy lỗi được giới hạn.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao chưa đủ? | Cách cải thiện |
|---|---|---|
| Coi nhiều replica là resilience | Replica có thể cùng failure domain/dependency | Đối chiếu zone, account, control plane và common-mode failures |
| Chỉ dùng network segmentation | Không giới hạn thread, queue, DB pool hoặc tenant resource | Kết hợp network, resource và service isolation |
| Retry mọi lỗi | Tạo retry storm và duplicate writes | Retry classification, budget, jitter và idempotency |
| Timeout giống nhau cho mọi dependency | Không phản ánh latency budget và criticality | Deadline propagation và per-operation policy |
| Circuit breaker tự động giải quyết fallback | Có thể trả stale data hoặc bỏ authorization | Định nghĩa degraded behavior và security invariants |
| Fail-open khi IdP/policy lỗi | Có thể cấp quyền không được xác minh | Fail-closed cho hành động nhạy cảm hoặc emergency path có kiểm soát |
| Fail-closed cho mọi chức năng | Có thể làm gián đoạn chức năng ít rủi ro không cần thiết | Phân loại theo business/security impact |
| Queue không giới hạn | Backlog làm đầy storage và tăng thời gian phục hồi | Bounded queue, backpressure, DLQ và retention |
| Multi-region được coi là độc lập | Shared IdP/KMS/DNS/config có thể lỗi chung | Dependency mapping và common-mode test |
| Backup job thành công được coi là DR đạt | Không chứng minh restore, key và integrity | Recovery drills với actual workloads |
| RTO/RPO đặt theo mong muốn kỹ thuật | Không phản ánh business impact | BIA, risk owner và phê duyệt |
| Bỏ audit khi hệ thống quá tải | Mất accountability trong sự cố | Durable buffer/controlled stop/alert theo policy |
| Tắt TLS validation để khôi phục kết nối | Tạo MITM exposure | Sửa trust/certificate, dùng runbook an toàn |
| Dùng stale authorization vô thời hạn | Quyền đã thu hồi vẫn có thể được dùng | Cache freshness, revocation và step-up |
| Test pod restart rồi kết luận pass | Không kiểm tra data, tenant, payment hoặc audit | Test end-to-end business/security invariants |
| Chaos test không có stop condition | Có thể biến thử nghiệm thành outage thật | Scope, approval, guardrails và rollback |
| Chỉ đo availability | Không thấy data corruption, bypass hoặc lost audit | SLI cho correctness, security và evidence |
| Không kiểm thử failback | Có thể gây split-brain hoặc mất dữ liệu khi quay lại | Failback exercise và reconciliation |

## 19. Bài tập thực hành

### Bài tập 1 — Vẽ failure domains

Một hệ thống gồm API Gateway, Identity Provider, Order Service, Payment Service, Redis, PostgreSQL, Kafka, KMS và Notification Provider. Các service chạy trên ba availability zones nhưng dùng một KMS và một DNS resolver chung.

**Yêu cầu:** Vẽ dependency map; đánh dấu trust boundary, resilience boundary và common-mode failure. Xác định tối thiểu **năm blast-radius risks** và đề xuất boundary có thể kiểm chứng.

### Bài tập 2 — Thiết kế bulkhead cho noisy tenant

Tenant A chạy báo cáo nặng làm cạn connection pool và khiến tenant B không truy cập được API.

**Yêu cầu:** Đề xuất per-tenant quota, pool, concurrency, queue và load shedding. Viết acceptance criteria chứng minh tenant A bị giới hạn mà tenant B vẫn có capacity. Nêu giới hạn nếu database vẫn là shared bottleneck.

### Bài tập 3 — Retry, timeout và idempotency

Payment Provider có thể hoàn tất giao dịch nhưng response bị timeout. Client gửi lại cùng request; worker cũng retry ở tầng dưới.

**Yêu cầu:** Thiết kế deadline budget, retry policy, idempotency key, provider reconciliation và trạng thái giao dịch chưa xác định. Viết ba test âm/dương để chứng minh không tạo duplicate.

### Bài tập 4 — Quyết định fail-open/fail-closed

Các dependency gồm IdP, authorization engine, KMS, fraud scorer, notification provider và audit pipeline.

**Yêu cầu:** Lập ma trận fallback theo operation (read, export, beneficiary change, payment commit, notification). Giải thích security invariants, freshness, approval, expiry và evidence cho mỗi quyết định. Không dùng một quy tắc chung cho mọi dependency.

### Bài tập 5 — KMS và audit outage

KMS unavailable trong 20 phút, đồng thời audit pipeline không nhận event. Ứng dụng cần ghi một giao dịch mới.

**Yêu cầu:** Phân biệt thao tác nào cần KMS đồng bộ; xác định safe behavior, durable audit buffering hoặc controlled stop theo policy; thiết kế recovery/reconciliation và test chứng minh không ghi plaintext, không mất audit và không tạo giao dịch sai.

### Bài tập 6 — Multi-region failover

Primary region bị mất kết nối. Secondary region có database replica lag, key version khác và chưa nhận policy mới nhất.

**Yêu cầu:** Viết runbook decision gates: data consistency, key availability, IAM/authz, tenant routing, audit, RTO/RPO, split-brain prevention và failback. Đề xuất evidence trước khi tuyên bố recovery hoàn tất.

### Bài tập 7 — Fault injection và assurance report

Nhóm SRE muốn làm thử nghiệm gây latency cho Payment Provider và dừng một notification worker.

**Yêu cầu:** Xây dựng hypothesis, scope, preconditions, stop conditions, expected/actual metrics, business invariants, evidence và remediation. Viết một Claim–Argument–Evidence–Limitations sau khi giả định thử nghiệm đạt.

### Bài tập 8 — Tìm common-mode dependencies

Một nền tảng có 12 cells nhưng tất cả dùng chung global IdP, KMS, DNS, deployment pipeline và central audit service.

**Yêu cầu:** Xác định các shared failure domains, đánh giá blast radius và đề xuất cách phân vùng/quorum/failover/telemetry phù hợp. Giải thích những dependency nào nên dùng chung và điều kiện nào phải có để giảm rủi ro.

## 20. Checklist đánh giá Resilience boundary

- **Scope:** Có xác định service, tenant, environment, zone, region, account và business-critical flows không?
- **Boundaries:** Trust boundary, service boundary, failure domain và resilience boundary có được phân biệt rõ?
- **Dependencies:** Có inventory IdP, KMS, DNS, database, queue, audit, config plane và vendor không?
- **Common-mode failure:** Có thành phần hoặc quyền quản trị chung ảnh hưởng nhiều cell/region không?
- **Isolation:** Có bulkhead, quota, pool, queue, tenant partition và resource limits phù hợp không?
- **Timeout:** Có deadline budget và timeout hữu hạn theo dependency/operation không?
- **Retry:** Có phân loại lỗi, bounded retries, backoff/jitter và idempotency không?
- **Circuit breaker:** Có điều kiện open/half-open/close, fallback và telemetry rõ không?
- **Backpressure:** Queue có giới hạn depth/age, DLQ, retention và replay control không?
- **Graceful degradation:** Chức năng nào tiếp tục/dừng; security invariants có được giữ?
- **Fail-open/closed:** Quyết định có căn cứ theo operation, risk, freshness, approval và expiry?
- **Identity/authorization:** Khi IdP/policy lỗi, có ngăn quyền stale hoặc bypass không?
- **Cryptography:** KMS/key unavailable không dẫn tới plaintext fallback hoặc bỏ xác minh?
- **Data integrity:** Có idempotency, reconciliation, duplicate protection và xử lý out-of-order?
- **HA/DR:** Có RTO/RPO, backup, restore, failover/failback và test thực tế?
- **Recovery security:** IAM, keys, audit, monitoring, tenant isolation và retention có được kiểm tra sau restore?
- **Testing:** Có fault injection, dependency outage, tenant saturation, region failover và failure-path tests?
- **Observability:** Có metrics cho latency, retry, circuit, queue, fail-open, audit completeness và isolation violation?
- **Evidence:** Có architecture/ADR, config, release, expected/actual, logs, test reports và limitations?
- **Governance:** Owner, risk owner, incident commander và assurance reviewer có trách nhiệm rõ?
- **Continuous assurance:** Thay đổi dependency, cell, policy, vendor hoặc incident có kích hoạt review/retest?

**Điều cần ghi nhớ:** Resilience boundary là cách kiến trúc **giới hạn nơi một lỗi có thể lan tới và bảo vệ các thuộc tính quan trọng khi hệ thống suy giảm**. Nó chỉ có giá trị khi được triển khai bằng resource isolation, dependency policies, safe fallback, data integrity và recovery có kiểm soát. Trong **security assurance**, hãy chứng minh ranh giới bằng **threat model, dependency inventory, fault-injection tests, telemetry, recovery drills và evidence về những security invariants vẫn được giữ**, đồng thời nêu rõ common-mode risks và phần chưa được kiểm chứng.
