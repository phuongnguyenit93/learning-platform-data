# Giới hạn phạm vi ảnh hưởng bằng phân vùng hoặc mô hình cell trong Microservices

Một hệ thống Microservices có thể chạy hàng trăm instance và nhiều bản sao database nhưng vẫn gặp sự cố toàn cục khi một tenant tạo quá nhiều truy vấn, một shared dependency bị nghẽn hoặc một bản phát hành lỗi được triển khai đồng thời. Vì vậy, mục tiêu vận hành không chỉ là **phục hồi nhanh sau lỗi** mà còn là **giới hạn số khách hàng, request và nghiệp vụ bị ảnh hưởng** khi lỗi xuất hiện.

Hai nhóm kỹ thuật thường được dùng là **phân vùng (partitioning/sharding)** và **mô hình cell (cell-based architecture)**. Phân vùng chia dữ liệu hoặc công việc theo một khóa xác định. Mô hình cell tổ chức một nhóm dịch vụ và tài nguyên thành đơn vị có khả năng phục vụ tương đối độc lập. Chúng không đồng nghĩa với nhau và cũng không tự động đem lại khả năng chịu lỗi: ranh giới chỉ thực sự có hiệu lực khi các nguồn tài nguyên, đường gọi và quy trình vận hành phù hợp.

Bài viết thuộc chủ đề **Vận hành và SLO** trong kiến trúc hệ thống Microservices, tập trung vào thiết kế blast radius, cô lập lỗi, lựa chọn khóa phân vùng, định tuyến theo cell, chỉ số SLO và các phép thử xác nhận tính độc lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích blast radius, failure domain, fault isolation và sự liên hệ với SLO/error budget.
- Phân biệt logical partition, physical shard, tenant isolation, availability zone và cell.
- Đọc dependency graph để nhận ra các điểm chung có nguy cơ làm lỗi lan rộng.
- Chọn partition key, thiết kế routing và phát hiện hot partition/noisy neighbor.
- Tổ chức dịch vụ, database, cache, worker, queue và quota thành những cell có ranh giới rõ ràng.
- Đề xuất phương án triển khai, failover, resharding và di chuyển tenant có kiểm soát.
- Kết hợp bulkhead, rate limit, timeout, circuit breaker và backpressure.
- Thiết lập global SLO và per-cell SLO, đánh giá ảnh hưởng thật của một cell outage.
- Kiểm thử blast radius thông qua fault injection, canary và diễn tập sự cố.
- Cân bằng chi phí, độ phức tạp và mức độc lập cần thiết.

## 2. Blast radius và failure domain

**Blast radius** là phạm vi chịu hậu quả khi một thành phần, một thay đổi phần mềm hoặc một luồng tải gặp lỗi. Có thể đo bằng số request thất bại, tenant, giao dịch, service hoặc vùng địa lý bị ảnh hưởng.

Giả sử nền tảng SaaS có 100 tenant. Nếu tất cả chung một cụm ứng dụng và database writer, lỗi của database có thể làm toàn bộ 100 tenant ngừng tạo đơn hàng. Nếu tenant được chia thành bốn cell có database và worker độc lập, một lỗi khu trú ở cell chứa 25 tenant có thể chỉ ảnh hưởng 25 tenant. Con số là minh họa khi phân bố đều; nếu cell đó chứa 70% traffic thì tác động theo request có thể vẫn rất lớn.

**Failure domain** là nhóm thành phần có thể thất bại do cùng một nguyên nhân. Các ví dụ:

- Một process/Pod cùng mất khi container lỗi.
- Nhiều Pod trên cùng node cùng mất khi node lỗi.
- Các node trong một availability zone có thể cùng bị ảnh hưởng bởi sự cố zone.
- Các service sử dụng chung database primary có thể cùng nghẽn khi primary quá tải.
- Nhiều cell dùng một control plane/configuration service có thể cùng lỗi vì cấu hình sai.
- Các tenant chia chung pool connection có thể bị ảnh hưởng bởi một truy vấn giữ kết nối lâu.

**Fault isolation** cố gắng giữ hậu quả ở trong miền đã định. **Fault containment** là những cơ chế cụ thể như giới hạn concurrency, queue có dung lượng hữu hạn, quota, timeouts, partition ownership hoặc tài nguyên độc lập.

Một kiến trúc đặt tên nhiều nhóm là "cell" chưa chắc đã giới hạn blast radius. Cần xác định thành phần nào thực sự dùng chung và chứng minh các nhóm không kéo nhau vào tình trạng lỗi.

## 3. Partition, shard và cell khác nhau thế nào?

### 3.1. Logical partition

**Partition** chia tập dữ liệu hoặc việc xử lý theo một khóa hoặc quy tắc:

- Orders chia theo tenantId.
- Dữ liệu lịch sử chia theo tháng.
- Kafka events chia theo orderId.
- Queue worker phân theo khu vực.
- Cache keys có namespace theo tenant.

Một logical partition có thể vẫn nằm trên cùng database host hoặc cùng broker cluster với partition khác. Vì thế, logical partition không tự cô lập lỗi CPU, disk hoặc mạng của tài nguyên chung.

### 3.2. Physical sharding

**Sharding** thường chỉ việc phân phối tập dữ liệu qua nhiều shard hoặc database instance/cluster. Mỗi shard giữ một phần dữ liệu và có thể được vận hành riêng.

~~~text
Tenant 001, 004, 007 ---> Shard A ---> Database Cluster A
Tenant 002, 005, 008 ---> Shard B ---> Database Cluster B
Tenant 003, 006, 009 ---> Shard C ---> Database Cluster C
~~~

Nếu database cluster A quá tải, shard B và C có cơ hội tiếp tục hoạt động. Tuy nhiên, khả năng đó phụ thuộc việc chúng không cùng bị nghẽn bởi router, hệ thống backup, network hoặc connection pool chung.

### 3.3. Cell-based architecture

**Cell** là một đơn vị phục vụ một nhóm tenant/workload đã được phân quyền sở hữu, thường có application instances, workers, cache và persistence tương ứng.

~~~text
                    +-----------------------+
Client ------------>| Global routing/gateway|
                    +-----------+-----------+
                                |
           +--------------------+------------------+
           |                    |                  |
           v                    v                  v
    +-------------+      +-------------+    +-------------+
    |   Cell A    |      |   Cell B    |    |   Cell C    |
    | API + Worker|      | API + Worker|    | API + Worker|
    | DB + Cache  |      | DB + Cache  |    | DB + Cache  |
    +-------------+      +-------------+    +-------------+
       Tenant 1-30          Tenant 31-60       Tenant 61-90
~~~

Một cell có thể chứa nhiều partition. Một shard có thể chỉ là phần dữ liệu thuộc một cell. Cell tập trung vào **ranh giới vận hành và ranh giới lỗi**, trong khi partition chủ yếu mô tả **cách chia khối lượng dữ liệu hoặc công việc**.

| Tiêu chí | Partition/Sharding | Cell |
|---|---|---|
| Đơn vị chia | Dữ liệu hoặc công việc | Tập dịch vụ và tài nguyên phục vụ |
| Mục tiêu | Phân bố lưu trữ, workload, tăng song song | Cô lập lỗi, triển khai và công suất theo miền |
| Routing | Key → partition/shard | Tenant/request → cell |
| Ranh giới lỗi | Chỉ rõ khi hạ tầng đủ độc lập | Là mục tiêu thiết kế |
| Dịch vụ | Có thể dùng một deployment chung | Có thể triển khai riêng mỗi cell |
| Dữ liệu | Partition trong một DB hoặc shard nhiều DB | Cell có dữ liệu thuộc phạm vi sở hữu |
| Đánh đổi | Query xuyên shard, hot key, reshard | Directory, vận hành nhiều bản, chi phí nền |

Phân vùng và cell có thể kết hợp. Không nên chọn một chiến lược chỉ vì tên gọi, mà cần dựa trên phạm vi lỗi muốn giới hạn.

## 4. Vẽ dependency graph và xác định điểm chung

Trước khi quyết định chia cell, xem một request đi qua những đâu:

~~~text
User
 |
 v
DNS / Gateway / Authentication
 |
 v
Order Service
 |----> Order Database
 |----> Inventory Service
 |----> Payment provider
 |----> Redis
 |----> Message broker ---> Notification worker
~~~

Với mỗi cạnh, đặt câu hỏi:

1. Thành phần này lỗi thì bao nhiêu tenant bị ảnh hưởng?
2. Khi dependency chậm, thread, connection, queue hoặc retry của caller có bị giữ đến cạn không?
3. Có ranh giới timeout và concurrency limit không?
4. Có secret, DNS, auth, config hoặc control plane chung cho toàn bộ hệ thống không?
5. Tải của tenant A có thể làm tenant B không còn tài nguyên không?
6. Khi ứng dụng đang rolling deploy, một bản lỗi có thể tác động đến tất cả cell cùng lúc không?
7. Nếu cần failover, dữ liệu có hiện diện và nhất quán ở đích mới không?

Một bản đồ rõ ràng sẽ chỉ ra một số điểm chung phải làm HA, một số điểm nên đặt quota và một số thành phần nên được tách hoàn toàn.

### 4.1. Ví dụ về cô lập giả

Hệ thống có 12 Pod Order Service chia thành ba namespace Kubernetes, mỗi namespace bốn Pod, nhưng tất cả ghi vào một PostgreSQL primary. Nếu một query chạy chậm làm DB cạn connection, cả ba namespace đều bị ảnh hưởng. Số namespace cao không làm database biến thành ba failure domain.

Ngược lại, có ba database cluster độc lập nhưng mọi request phải gọi một directory service duy nhất mà không có cache hoặc fallback: mất directory vẫn làm ba cell không nhận request mới. Cả data plane và control plane cần được phân tích.

## 5. Các cấp độ cô lập có thể áp dụng

### 5.1. Logical isolation

Một database có tenant_id trên các bảng, API luôn truy vấn đúng tenant và cache dùng key prefix. Rẻ và dễ vận hành nhưng tài nguyên vật lý còn dùng chung. Cần authorization, data scoping và quota để hạn chế ảnh hưởng logic.

### 5.2. Resource isolation

Các tenant/workload có connection pool, worker queue, cache namespace hoặc database shard riêng. Giúp ngăn noisy neighbor lấy hết tài nguyên, nhưng vẫn còn các shared dependencies.

### 5.3. Cell isolation

Mỗi nhóm tenant có application, worker, persistence và khả năng deploy riêng, kèm routing rõ ràng. Mức cô lập cao hơn, đổi lại phải quản lý nhiều cell, backup, migration, monitoring và capacity.

Mức nào phù hợp tùy SLO, quy mô và chi phí. Một nền tảng nhỏ có thể bắt đầu từ bulkhead/quota và logical partition; hệ thống lớn với yêu cầu độ tin cậy cao có thể tiến tới cell.

## 6. Chọn partition key

Khóa phân vùng quyết định nơi dữ liệu/công việc thuộc về. Một khóa tốt cần ổn định, có thể định tuyến trước khi xử lý, phân bố tải hợp lý và tôn trọng ranh giới nghiệp vụ.

| Partition key | Phù hợp với | Rủi ro |
|---|---|---|
| tenantId | SaaS đa tenant | Tenant lớn thành hot partition |
| customerId | Dữ liệu theo khách hàng | Khó xử lý truy vấn xuyên nhiều customer |
| orderId | Workflow theo từng đơn | Truy vấn tổng hợp theo tenant có thể fan-out |
| region | Độ trễ và data residency | Vùng không cân bằng; migration xuyên vùng |
| time range | Lưu trữ lịch sử, log/analytics | Partition gần nhất luôn nóng |
| hash của khóa | Phân tán key tương đối đều | Mất locality nghiệp vụ, chuyển key khó |
| workload type | Checkout, reporting, background batch | Cần cơ chế phối hợp và quyền dữ liệu |

### 6.1. Hot partition và tải lệch

Giả sử bốn partition có số tenant bằng nhau, nhưng tenant X tạo 55% RPS toàn hệ thống. Nếu X thuộc partition A, A bão hòa trong khi B/C/D còn rảnh. Chia **đều số tenant** không đồng nghĩa chia đều CPU, IOPS hay request.

Có thể giải quyết bằng cách:

- Chuyển tenant lớn sang shard/cell riêng.
- Sử dụng weighted placement theo peak traffic, dữ liệu và CPU.
- Tách các tác vụ batch/reporting khỏi đường giao dịch.
- Giới hạn concurrency, rate hoặc resource budget theo tenant.
- Dùng cache và tối ưu truy vấn phù hợp.
- Chia thêm theo secondary key khi nghiệp vụ thực sự hỗ trợ.

Không tùy tiện chia nhỏ dữ liệu cần transaction mạnh giữa nhiều shard, vì chi phí nhất quán và giao dịch xuyên shard có thể cao.

## 7. Định tuyến tenant tới cell

Một thiết kế thường có **Cell Directory** lưu mapping bền vững:

~~~text
tenant-101 -> cell-a
tenant-102 -> cell-b
tenant-103 -> cell-a
tenant-900 -> dedicated-cell-1
~~~

Request đi theo đường:

~~~text
Client
  |
  v
Authenticate + authorize tenant membership
  |
  v
Trusted tenantId
  |
  v
Cell directory / cached placement
  |
  v
Cell gateway / service discovery
  |
  v
Application + persistence của cell
~~~

Nguyên tắc:

- TenantId cần lấy từ ngữ cảnh đã xác thực/ủy quyền; không tin một header do client tùy ý gửi.
- Cell URI/endpoint lấy từ cấu hình tin cậy, không tạo URL trực tiếp từ dữ liệu người dùng.
- Directory cần version, owner, quy tắc cache và invalidation.
- Không có mapping thì trả lỗi có kiểm soát; **không route ngẫu nhiên sang cell khác**.
- Những request của cùng workflow phải dùng routing nhất quán trong thời gian xử lý.
- Tracing/log gắn cellId, placementVersion và correlationId.
- Mapping phải tuân thủ quy tắc data residency và tenant placement policy.

### 7.1. Hash modulo và giới hạn

~~~text
cellIndex = hash(tenantId) mod N
~~~

Đây là phép chia đơn giản nhưng nguy hiểm nếu dữ liệu đã được lưu bền vững theo cell. Đổi N từ 4 thành 5 có thể làm nhiều tenant đổi đích. Nếu router đổi tính toán trước khi dữ liệu được chuyển, client có thể đọc sai chỗ.

Consistent hashing có thể giảm lượng key cần chuyển khi thêm/bớt node, nhưng **không tự chuyển dữ liệu, không xử lý split-brain và không bảo đảm transaction**. Với storage stateful, nên có placement được quản lý và workflow di chuyển an toàn.

### 7.2. Java router minh họa

~~~java
record CellTarget(String cellId, URI baseUri, long placementVersion) {}

interface CellDirectory {
    Optional<CellTarget> findActiveCell(String authorizedTenantId);
}

final class TenantCellRouter {
    private final CellDirectory directory;

    TenantCellRouter(CellDirectory directory) {
        this.directory = directory;
    }

    CellTarget resolve(String authorizedTenantId) {
        return directory.findActiveCell(authorizedTenantId)
            .orElseThrow(() ->
                new IllegalStateException("No active tenant placement"));
    }
}
~~~

Mã chỉ minh họa việc ánh xạ. Lớp gateway phải kiểm tra quyền của tenant và có cơ chế xử lý lỗi. Base URI phải đến từ directory/config đáng tin cậy để tránh SSRF. Khi migration đang diễn ra, trạng thái mapping cần được điều phối bởi state machine để không có hai writer độc lập cùng nhận quyền.

## 8. Kiến trúc của một cell

Một cell có thể chứa:

~~~text
+------------------ CELL A -------------------+
|                                              |
| Ingress A --> Order API A --> Order DB A     |
|                  |                           |
|                  +--> Inventory Worker A     |
|                  |       |                   |
|                  |       +--> Queue A        |
|                  +--> Redis Cache A          |
|                                              |
| Quotas / Alerts / Rollout Policy A           |
+----------------------------------------------+

+------------------ CELL B -------------------+
| Ingress B --> Order API B --> Order DB B     |
|                  +--> Worker B / Queue B     |
|                  +--> Redis Cache B          |
| Quotas / Alerts / Rollout Policy B           |
+----------------------------------------------+
~~~

Đây là một cấu trúc gợi ý, không phải yêu cầu mọi hệ thống phải nhân bản mọi service. Nếu một dịch vụ chung đủ HA và lỗi của nó không kéo theo đường phục vụ chính, có thể cân nhắc dùng chung. Phải phân tích mức phụ thuộc thay vì mặc định.

### 8.1. Những tài nguyên thường cần tách hoặc đặt quota

- API/worker instances, autoscaling và rollout theo cell.
- Database/shard hoặc ít nhất workload quota và isolation rõ ràng.
- Cache, connection pools, queue capacity và message consumers.
- CPU/RAM, số Pod/node, IOPS và băng thông khi chia sẻ hạ tầng.
- Quyền truy cập, secret và lưu trữ trong từng failure domain.
- Telemetry cellId, alert và runbook để khôi phục đúng phạm vi.

### 8.2. Thành phần dùng chung có thể phá isolation

Các thành phần thường còn chung gồm DNS, gateway, auth, feature flags, KMS, broker cluster, CI/CD, config service, schema registry, control plane và third-party API. Lỗi một trong những thành phần đó có thể tạo correlated outage.

Cần kiểm tra:

1. Thành phần chung có HA và đủ capacity không?
2. Client có timeout và bounded retry khi gọi nó không?
3. Có cache an toàn để tiếp tục hoạt động khi nó mất tạm thời không?
4. Có local quota/bulkhead ngăn một cell chiếm hết nó không?
5. Có canary cho thay đổi cấu hình ở tầng chung không?
6. Nếu nó mất, cell vẫn có thể xử lý traffic đã biết mapping trong thời gian giới hạn không?

Một control plane có HA vẫn có thể phát cấu hình sai đến toàn bộ cell. Vì vậy phải có kiểm soát chất lượng, rollout theo wave và đường rollback config.

## 9. Bulkhead: cách ly tài nguyên bên trong service

**Bulkhead pattern** giới hạn tài nguyên theo nhóm công việc để khi một luồng chậm hoặc lỗi, luồng khác còn capacity.

Ví dụ:

~~~text
               Order Service
                     |
             +-------+-------+
             |               |
        Checkout Pool     Report Pool
        max active: 80    max active: 10
        queue bounded     queue bounded
             |               |
             +-------+-------+
                     |
                Database
~~~

Nếu report query chạy lâu và Report Pool đầy, request report có thể bị từ chối hoặc xếp hàng hữu hạn; checkout vẫn còn thread/connection riêng. Các con số chỉ để minh họa và phải được đo trên workload thật.

| Cơ chế | Phạm vi giới hạn | Tác dụng |
|---|---|---|
| Concurrency semaphore | Số việc đang chạy | Giữ thread/connection không bị chiếm hết |
| Bounded queue | Số việc chờ | Ngăn memory growth |
| Rate limiter | Request/cost units theo thời gian | Cô lập noisy neighbor |
| Connection pool riêng | Số kết nối xuống DB/API | Giảm tranh chấp |
| Circuit breaker | Lời gọi đến dependency lỗi | Chặn thác lỗi và retry storm |
| Timeout/deadline | Thời gian giữ tài nguyên | Tránh chờ vô hạn |
| CPU/memory quota | Tài nguyên được cấp | Giảm chiếm dụng chéo |
| Tenant quota | Ngân sách per tenant | Hạn chế một khách hàng làm quá tải nhóm |

### 9.1. Noisy neighbor

Một tenant gọi 50 request/giây có thể tốn nhiều CPU hơn tenant gọi 500 request/giây nếu mỗi request chạy query rất lớn. Vì thế quota theo RPS không đủ. Cần đo request cost, DB time, CPU, message bytes, storage I/O và số job đang chạy; rồi áp giới hạn tương ứng.

## 10. Cô lập dữ liệu

### 10.1. Logical isolation trong database

Một schema phổ biến là có tenant_id:

~~~sql
CREATE TABLE orders (
    tenant_id text NOT NULL,
    order_id text NOT NULL,
    status text NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Mọi thao tác phải dùng tenant đã xác thực và điều kiện dữ liệu tương ứng. Có thể bổ sung Row-Level Security khi phù hợp để giảm rủi ro truy cập chéo. Tuy vậy, tất cả tenant vẫn chia CPU, WAL, storage I/O và connection limit của database server.

### 10.2. Database riêng theo cell

~~~text
Cell A --> DB cluster A
Cell B --> DB cluster B
Cell C --> DB cluster C
~~~

Cô lập vật lý tăng cơ hội giảm blast radius nhưng làm tăng số backup, migration, credential, monitoring và quy trình DR. Nếu mọi DB cluster vẫn dùng chung một dịch vụ điều khiển bị lỗi, phần chung đó còn là failure domain.

### 10.3. Truy vấn xuyên cell

Dashboard tổng hợp tất cả tenant có thể phải fan-out đến từng cell. Nếu một cell chậm, toàn bộ request có thể chờ. Phương án:

- Đồng bộ dữ liệu tổng hợp qua pipeline bất đồng bộ để đọc ở hệ thống analytics.
- Cho phép kết quả một phần có ghi rõ độ mới và phạm vi nếu nghiệp vụ chấp nhận.
- Giới hạn deadline, fan-out concurrency và retry.
- Cache số liệu toàn cục, tránh query nóng bắn hàng trăm yêu cầu xuyên cell.
- Đặt quyền truy cập và data residency rõ ràng cho dữ liệu tổng hợp.

Cell architecture hiệu quả khi critical path của một tenant ít phải gọi đồng bộ đến các cell khác.

## 11. Message broker và partition

Kafka partition phân phối sự kiện theo key và xác định phạm vi thứ tự trong từng partition. Nhưng nhiều partition có thể cùng nằm trên một broker cluster, dùng chung disk, network và quota. **Một Kafka partition không tương đương một failure-isolated cell.**

Các rủi ro:

- Broker cluster mất làm nhiều partition ngừng hoạt động.
- Một consumer process xử lý nhiều partition và bị OOM có thể làm group rebalance.
- Poison message làm lag tăng; retry vô hạn có thể chiếm tài nguyên toàn worker.
- Một producer phát quá nhiều message lớn, tăng broker network/storage load.
- Consumer đọc message sai tenant/cell gây ghi nhầm dữ liệu.

Các biện pháp:

1. Chọn message key theo ordering/ownership, ví dụ orderId hoặc tenantId.
2. Đặt producer/consumer quota khi broker hỗ trợ.
3. Giới hạn message size, batch size và retry; dùng DLQ và backoff có chủ đích.
4. Cân nhắc topic hoặc broker cluster riêng theo cell nếu SLO yêu cầu isolation mạnh.
5. Đo consumer lag, oldest message age, throughput và error theo partition/cell.
6. Xác minh consumer chỉ cập nhật dữ liệu mà nó thực sự sở hữu.

Nếu một event tạo side effect, cơ chế idempotency phải chịu được duplicate delivery và retry trong cùng hoặc khác worker.

## 12. Kubernetes namespace và availability zone

Namespace giúp tổ chức object và áp policy/quota. Nó **không tự động tách node, network, CNI, control plane hoặc storage**.

Ví dụ ResourceQuota:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: cell-a-compute
  namespace: cell-a
spec:
  hard:
    requests.cpu: "16"
    requests.memory: "32Gi"
    limits.cpu: "24"
    limits.memory: "48Gi"
    pods: "80"
~~~

Quota hạn chế lượng tài nguyên một namespace được khai báo sử dụng, không bảo đảm sẽ có sẵn CPU/RAM thực tế khi tất cả node đã đầy. Cần kết hợp scheduling, node capacity, anti-affinity/topology spread, NetworkPolicy, quyền truy cập và observability.

### 12.1. Multi-node và multi-AZ

- Nhiều Pod trên một node vẫn có cùng failure domain của node.
- Nhiều Pod trên nhiều node cùng AZ chịu lỗi node nhưng chưa chịu được zone outage.
- Pod trên nhiều AZ tăng khả năng chịu lỗi AZ nếu database/network/dependencies cũng phù hợp.
- Một cell có thể trải nhiều AZ; cell không bắt buộc bằng một AZ.
- Các cell ở cùng cluster có thể cùng bị tác động bởi cluster control plane hoặc một cấu hình sai.

Mức tách biệt phải phù hợp mục tiêu rủi ro và chi phí, không chỉ dựa vào số replica.

## 13. Các mô hình cell theo ranh giới nghiệp vụ

### 13.1. Tenant cell

Gán nhóm tenant vào cell. Phù hợp SaaS, dễ tính tác động theo khách hàng và di chuyển tenant lớn ra riêng. Phải quản lý weighted placement và tenant migration.

### 13.2. Geographic cell

Gán request/dữ liệu theo region để giảm latency và đáp ứng data residency. Failover xuyên vùng cần kiểm chứng replication, quyền lưu trữ dữ liệu và chiến lược khôi phục.

### 13.3. Workload cell

Tách realtime checkout, reporting, batch import hoặc inference để các đặc tính tải không ảnh hưởng nhau. Có thể dùng shared DB nhưng phải áp giới hạn theo workload; isolation vật lý phụ thuộc topology.

### 13.4. Dedicated customer cell

Khách hàng lớn hoặc cần cam kết vận hành đặc biệt có cell riêng. Giúp quản lý quota và ảnh hưởng, nhưng tốn tài nguyên và automation.

Một kiến trúc có thể kết hợp các chiều:

~~~text
Region 1:
  Cell A1: small tenants
  Cell A2: medium tenants
  Cell A3: dedicated large tenant

Region 2:
  Cell B1: small tenants
  Cell B2: regulated tenants
~~~

## 14. Quy mô cell và capacity planning

Giả sử load test cho thấy mỗi cell xử lý ổn định 600 request/giây khi đạt SLO. Nhóm dùng mục tiêu 75% công suất để có headroom:

~~~text
Planning capacity per cell
= 600 × 0.75
= 450 request/second
~~~

Nếu peak traffic dự kiến là 1.600 RPS:

~~~text
Estimated cell count = ceil(1600 / 450) = 4
~~~

Đây là ước lượng sơ bộ, chưa chứng minh bốn cell đủ. Phải xét traffic skew, các request có chi phí khác nhau, database throughput, hot tenant, lỗi một Pod hoặc AZ, và capacity của shared gateway/identity.

**Điểm quan trọng:** mục tiêu tránh vượt capacity không chỉ phụ thuộc số tenant. Một cell chứa ít tenant nhưng một khách hàng rất lớn có thể nóng hơn cell chứa hàng trăm tenant nhỏ.

### 14.1. Dự phòng khi một cell lỗi

Có hai chiến lược khác nhau:

- **Cô lập và khôi phục tại chỗ:** chỉ tenant thuộc cell lỗi bị ảnh hưởng, cell khác tiếp tục hoạt động.
- **Failover sang cell khác:** cần dữ liệu/replication, quyền ghi và capacity dự phòng ở đích.

Không được mặc định failover workload có trạng thái sang cell rỗng. Nếu Cell B không có dữ liệu của tenant ở Cell A, đổi route có thể làm hệ thống đọc ra dữ liệu trống hoặc tạo hai nguồn dữ liệu không nhất quán.

## 15. Resharding và di chuyển tenant an toàn

Khi cell nóng hoặc cần mở rộng, việc chuyển tenant là một bài toán dữ liệu và routing, không chỉ đổi config.

Một quy trình minh họa:

~~~text
ACTIVE_ON_A
    |
    v
PREPARE_B
    |
    v
SNAPSHOT / BACKFILL A -> B
    |
    v
CATCH_UP NEW CHANGES
    |
    v
QUIESCE OR COORDINATE WRITES
    |
    v
CUTOVER PLACEMENT VERSION
    |
    v
VERIFY DATA AND TRAFFIC ON B
    |
    v
RETIRE OLD COPY WHEN SAFE
~~~

Điểm cần làm rõ:

- Quyền ghi chính thức nằm ở đâu trong từng giai đoạn?
- Request đang chạy trước cutover có tiếp tục ghi vào A không?
- Event tới muộn có được xử lý ở đúng cell owner không?
- Backfill và write mới có thể làm dữ liệu hai phía lệch không?
- Nếu cutover thất bại, rollback mapping có làm mất các bản ghi mới ở B không?
- Khi nào được xóa bản sao A theo chính sách dữ liệu?
- Có trace/audit để tái hiện một tenant đã di chuyển như thế nào không?

Nên có placementVersion và cơ chế fencing để ngăn writer cũ tiếp tục nhận ghi sau khi quyền sở hữu đã chuyển. Việc copy dữ liệu một lần rồi đổi hash không xử lý đầy đủ race condition.

## 16. Cell-based architecture và SLO

**SLO** là mục tiêu định lượng cho trải nghiệm người dùng, ví dụ tỷ lệ request thành công, latency hoặc độ mới dữ liệu. Cell giúp giảm số người dùng bị lỗi khi sự cố khu trú, nhưng không làm SLO tự động đạt.

### 16.1. Ví dụ tính ảnh hưởng của một cell outage

Giả sử traffic được chia đều vào bốn cell. Một cell phục vụ 25% tổng request và bị ngừng hoàn toàn trong 10 phút của một ngày 1.440 phút. Giả định traffic ổn định, không có lỗi khác:

~~~text
Global request error fraction
= 25% × (10 / 1440)
≈ 0.1736%

Global request success fraction
≈ 99.8264%
~~~

Nếu một shared dependency khiến **cả bốn cell** cùng thất bại 10 phút:

~~~text
Global request error fraction
= 100% × (10 / 1440)
≈ 0.6944%

Global request success fraction
≈ 99.3056%
~~~

Cô lập giúp giảm ảnh hưởng tổng khoảng bốn lần trong ví dụ. Nhưng 99.8264% vẫn chưa đạt SLO 99.9% nếu SLO được đánh giá theo cửa sổ đó. Nếu tải không đều hoặc cell có traffic khác nhau, phải tính trọng số request thực tế chứ không tính trung bình số cell.

### 16.2. Global SLO và per-cell SLO

Theo dõi đồng thời:

- **Global SLO:** trải nghiệm chung của sản phẩm.
- **Per-cell SLO:** tránh lỗi của một nhóm khách hàng bị che bởi trung bình toàn cầu.
- **Per-tenant/per-tier SLO:** nếu sản phẩm có cam kết riêng.
- **Dependency SLI:** database latency, queue lag, auth error, routing error theo cell.
- **Control-plane SLI:** availability/latency của directory, config, gateway và shared services.

Ví dụ Cell A có success 99%, B/C/D có 100%. Nếu A chỉ nhận 1% traffic, chỉ số global có thể vẫn gần 99.99% nhưng khách hàng trong A chịu trải nghiệm rất xấu. Cần alert theo cell/cohort có ngưỡng phù hợp.

### 16.3. Error budget và release policy

Với request-based SLO 99.9%, error budget là 0.1% request đủ điều kiện trong cửa sổ đo. Không nên quy đổi máy móc thành số phút cố định nếu lưu lượng thay đổi theo giờ. Một phút peak có thể ảnh hưởng nhiều request hơn một phút ban đêm.

Khi một cell đốt error budget nhanh:

1. Dừng rollout trên cell đó và các wave chưa triển khai.
2. Xác định lỗi cục bộ hay lỗi của shared dependency.
3. Ngăn retry storm sang các cell/dependency khác.
4. Ưu tiên khôi phục trải nghiệm người dùng và tính đúng đắn dữ liệu.
5. Cập nhật risk/release policy dựa trên nguyên nhân và bằng chứng kiểm thử.

## 17. Observability theo cell

Nếu dashboard chỉ có service_name=order-service, một cell lỗi có thể bị che khi tổng trung bình tốt. Nên thêm những dimension hữu hạn như cell_id, region, deployment_version, workload_class và contract_version.

~~~text
service_name = order-service
cell_id = cell-a
region = region-1
deployment_version = 2.7.3
workload_class = checkout
~~~

Không đưa tenantId hoặc orderId của hàng triệu đối tượng vào mọi label Prometheus vì cardinality có thể tăng cực lớn. Những ID cụ thể thường phù hợp với log/trace hoặc hệ truy vấn riêng có kiểm soát hơn.

| Nhóm metric | Gợi ý đo theo cell |
|---|---|
| Traffic | RPS, request bytes, concurrent requests |
| User experience | Success rate, p50/p95/p99 latency |
| App | Timeouts, retries, circuit breaker state |
| Database | Query latency, connection pool wait, locks, IOPS |
| Messaging | Queue depth, oldest message age, consumer lag, DLQ |
| Capacity | CPU, memory, throttling, quota usage, pending Pods |
| Routing | Missing placement, stale mapping, misrouted requests |
| Release | Image digest, config version, rollout wave |
| Cross-cell | Fan-out requests, partial failures, shared dependency errors |

Distributed tracing nên có cellId/correlationId để biết request đi qua cell nào và tại sao. Nếu một request liên tục gọi các cell khác, đó có thể là dấu hiệu ranh giới dữ liệu chưa được thiết kế đúng. Dữ liệu nhạy cảm phải được lọc khỏi log/trace theo chính sách.

## 18. Progressive delivery theo cell

Một ưu điểm của cell là triển khai theo wave:

~~~text
Build candidate image
        |
        v
Deploy Cell A canary
        |
        v
Observe SLO + logs + data integrity
        |
        +--> FAIL: stop rollout / rollback A
        |
        v
Deploy Cell B
        |
        v
Deploy Cell C, D
~~~

Cách này giới hạn phạm vi nếu bản mới có lỗi. Tuy nhiên, cần tránh các lỗi đồng bộ:

- Migration phá hủy schema trong database chung có thể ảnh hưởng mọi cell.
- Config global được bật toàn hệ thống trước khi canary.
- Producer mới phát event không tương thích tới consumer cũ ở nhiều cell.
- Shared library, TLS hoặc secret rotation làm tất cả cell lỗi.
- Cell canary có workload khác phần còn lại, không phát hiện đường nghiệp vụ hiếm.

Các wave cần có điều kiện dừng dựa trên metric per-cell và global. Không chỉ dựa vào kết quả CI của một phiên bản rồi rollout đồng thời tất cả cell.

## 19. Failover: cần thiết kế dữ liệu và ownership

Khi Cell A không khả dụng, có thể giữ tenant A tạm thời lỗi và phục hồi tại chỗ, hoặc chuyển tenant sang Cell B đã được chuẩn bị. Mỗi lựa chọn có mức rủi ro riêng.

Để failover stateful cần:

- **RTO:** thời gian khôi phục mục tiêu.
- **RPO:** lượng dữ liệu tối đa có thể mất.
- **Replication:** dữ liệu đã có ở đích mới hay chưa.
- **Consistency:** đích có trạng thái đủ mới để xử lý nghiệp vụ không.
- **Fencing:** nguồn cũ có bị ngăn ghi sau khi chuyển quyền không.
- **Capacity:** đích mới có chịu thêm tải mà không kéo tenant của nó vào lỗi không.
- **Residency:** chuyển vùng có hợp lệ về dữ liệu không.
- **Rollback/roll-forward:** nếu failover thất bại, trạng thái được đồng bộ/khôi phục ra sao.

Với worker stateless, failover có thể đơn giản hơn nếu job nằm trong queue bền vững và worker khác có quyền xử lý. Với database có trạng thái, chuyển route mà không có replication không phải failover an toàn.

## 20. Shared dependencies và nguy cơ correlated outage

Ngay cả khi tách app/database theo cell, một số thành phần có thể còn chung:

1. DNS, CDN hoặc global gateway.
2. Identity provider, token verification, shared secrets/KMS.
3. Cell directory, service discovery và configuration service.
4. CI/CD pipeline, schema migrations và release automation.
5. Kafka/broker cluster, object storage hoặc payment provider.
6. Hệ thống logs/metrics/traces nếu đường gửi telemetry chặn xử lý chính.
7. Rate limits hoặc license quotas ở dịch vụ bên ngoài.

Một lỗi toàn cục có thể bắt nguồn từ tài nguyên chung. Các giải pháp gồm HA, cấu hình có version, cache theo chính sách, bounded retries, quota theo cell, circuit breaker, không đồng bộ logging và kiểm soát rollout. Không nên giả định tất cả shared dependencies đều có thể nhân bản độc lập; cần xác định cái nào là điểm lỗi đáng giảm thiểu theo SLO.

### 20.1. Control plane và data plane

Control plane quản lý placement, cấu hình và tạo cell. Data plane xử lý request/ghi dữ liệu của tenant. Trong một thiết kế chịu lỗi tốt, data plane có thể tiếp tục phục vụ những request đã biết routing trong một khoảng giới hạn ngay cả khi control plane tạm mất, nếu điều đó không tạo rủi ro dữ liệu stale/split-brain.

Câu hỏi thực hành: khi directory ngừng 10 phút, gateway có cache placement không, TTL là bao lâu, và nếu tenant đang được migrate thì request có thể tiếp tục tới cell cũ một cách an toàn không? Cần kiểm thử, không chỉ đưa ra giả định.

## 21. Runbook xử lý sự cố một cell

Giả sử p99 của Cell B tăng từ 150 ms lên 2 giây; Cell A/C bình thường.

1. Xác định thời điểm bắt đầu, loại request, nhóm tenant và SLI bị ảnh hưởng ở B.
2. Kiểm tra rollout/config/migration mới nhất của B.
3. Xem saturation CPU, thread, DB pool, queue lag, lock và third-party errors.
4. So sánh với cell khác để phân biệt lỗi cục bộ và shared dependency.
5. Tạm dừng rollout chưa hoàn tất, cô lập batch workload hoặc noisy tenant nếu phù hợp.
6. Áp timeout, circuit breaker và bounded retries để ngăn lỗi lan.
7. Rollback deployment hoặc repair đúng thành phần; tránh chuyển dữ liệu/tenant tùy ý.
8. Theo dõi lại p99, error rate, backlog và tính đúng đắn dữ liệu.
9. Ghi số tenant/request chịu ảnh hưởng, error budget burn và nguyên nhân.
10. Cập nhật capacity plan, quota, test hoặc chính sách canary.

Nếu nhiều cell lỗi đồng thời và có stack trace giống nhau, ưu tiên xem shared config, library hoặc dependency. Đừng tự kết luận lỗi từng cell độc lập.

## 22. Kiểm thử blast radius và failure isolation

Một sơ đồ có nhiều cell chưa đủ để khẳng định chịu lỗi; cần thử nghiệm có kiểm soát.

### 22.1. Fault injection theo cell

Trên môi trường test hoặc môi trường được phép diễn tập:

- Ngừng một Pod của Cell A và kiểm tra readiness/draining.
- Làm database A chậm hoặc mất kết nối có giới hạn thời gian.
- Đưa queue A vào tình trạng backlog hoặc poison message.
- Tạo tải bất thường từ một tenant thuộc A.
- Tạm ngắt cache A hoặc tăng latency.
- Canary một phiên bản ứng dụng lỗi có chủ đích ở A, rồi rollback.
- Mô phỏng directory tạm mất trong khi gateway có cached placement.

**Kỳ vọng:** A suy giảm đúng phạm vi đã thử, B/C giữ SLO; không có retry storm xuống dependency dùng chung; dữ liệu không bị route sang cell khác.

### 22.2. Kiểm chứng theo điều kiện

Ghi lại:

- Tỷ lệ request lỗi và p95/p99 của từng cell.
- Số tenant và nghiệp vụ bị ảnh hưởng.
- Saturation của shared gateway, broker, auth và database nếu có.
- Số misrouted requests hoặc cross-cell writes.
- Thời gian phát hiện, thời gian khôi phục và error budget tiêu thụ.
- Hành vi khi phục hồi backlog, reconnect và retry.
- Khả năng dừng rollout đúng tại cell lỗi.

Nếu chỉ một cell bị lỗi nhưng global p95 gần như không đổi, phép thử vẫn phải báo rằng **cell đó đã bị ảnh hưởng**, không chỉ nhìn chỉ số toàn hệ thống.

### 22.3. Thử shared dependency

Ngoài lỗi cục bộ, cần thử một số failure domain chung như directory, auth, gateway hoặc broker. Đây là cách nhận ra những đường lan truyền còn sót. Không inject lỗi vào hệ thống đang có khách hàng thực nếu chưa được phép và chưa có biện pháp giới hạn ảnh hưởng.

## 23. Automation khi có nhiều cell

Khi số cell tăng, vận hành thủ công dễ tạo drift:

- Cell A chạy version khác mà không ai biết.
- Database migration bị bỏ sót ở một cell.
- Quota/rate limit không nhất quán.
- Secret rotation thành công ở đa số cell nhưng còn lỗi ở một nhóm.
- Pipeline rollout thiếu điều kiện dừng.
- Monitoring không có cell_id và không xác định được owner.

Nên dùng IaC và cấu hình mẫu theo cell, nhưng phát hành theo wave có điều kiện dừng. Cần inventory các thuộc tính: cellId, region, owner, tenant placement, app version/digest, DB schema, rollout status, quota và health. Automation tạo consistency nhưng có thể nhân bản lỗi cấu hình rất nhanh nếu không có canary.

## 24. Đánh đổi về chi phí và độ phức tạp

Cell nhỏ thường giới hạn phạm vi lỗi tốt hơn nhưng tăng baseline cost vì mỗi cell cần replica, cache, database, observability và headroom. Cell lớn tiết kiệm overhead nhưng một sự cố ảnh hưởng nhiều tenant hơn.

| Tiêu chí | Ít cell, kích thước lớn | Nhiều cell, kích thước nhỏ |
|---|---|---|
| Baseline cost | Có thể thấp hơn | Có thể cao hơn |
| Blast radius mỗi cell | Rộng | Hẹp |
| Sử dụng tài nguyên | Dễ tận dụng pool lớn | Có thể thừa capacity ở cell ít tải |
| Tenant placement | Ít nơi cần quản lý | Dễ tách tenant đặc biệt nhưng quản lý phức tạp |
| Rollout | Ít đơn vị triển khai | Có thể canary theo nhiều wave |
| Migration | Ít shard/DB | Nhiều luồng migrate và schema |
| Monitoring | Đơn giản hơn | Nhiều dimension, alert và runbook |
| Khôi phục | Ít thao tác nhưng tác động rộng | Có thể tập trung vào một cell |

Mục tiêu tối ưu không chỉ là chi phí hạ tầng nhỏ nhất. Cần so sánh tổn thất do outage, SLO cam kết, công sức vận hành, khả năng di chuyển tenant và sự phân bố tải thực tế.

## 25. Tình huống thực hành: SaaS có tenant lớn

**Bối cảnh:** nền tảng có 240 tenant. Hai mươi tenant lớn tạo 60% traffic; 220 tenant nhỏ tạo 40%. Tất cả dùng chung app và DB primary. Một tenant lớn chạy batch import làm checkout chậm cho toàn bộ người dùng.

**Hướng giải quyết:**

1. Đo CPU, DB query time, IOPS, pool wait và peak theo tenant.
2. Tối ưu các truy vấn/transaction gây lock, phân trang batch.
3. Dùng worker pool và database connection budget riêng cho batch import.
4. Đặt quota per tenant dựa trên chi phí thực tế, không chỉ số request.
5. Chọn tenantId làm placement key và tạo cell directory versioned.
6. Chia các tenant nhỏ vào cell theo weighted load, cấp cell riêng cho tenant lớn khi cần.
7. Giữ app, cache, worker và DB/shard của cell theo ranh giới cô lập đã chọn.
8. Viết quy trình migrate tenant và kiểm thử ownership/fencing.
9. Triển khai cell lần lượt, chạy fault injection tại một cell.
10. Theo dõi per-cell SLO, global SLO và shared dependency usage.

**Câu hỏi suy luận:**

- Nếu các cell có DB riêng nhưng cùng gọi payment provider hạn mức 1000 RPS, sự cố noisy neighbor còn lan ở đâu?
- Nếu directory mất nhưng cache mapping còn, điều kiện nào cho phép tiếp tục phục vụ an toàn?
- Vì sao không tự route tenant từ Cell A lỗi sang Cell B khi B không có dữ liệu?
- Tại sao 60 tenant mỗi cell chưa chắc cân bằng hơn 40 tenant mỗi cell?
- Nếu rollout một cấu hình sai đồng loạt đến tất cả cell, cell architecture đã bảo vệ release failure chưa?
- Khi cutover tenant sang B, làm sao ngăn job cũ tiếp tục ghi vào A?

## 26. Checklist trước khi vận hành

### Ranh giới và routing

- [ ] Có dependency graph và danh sách failure domain dùng chung.
- [ ] Đã xác định blast radius mong muốn theo tenant, request và nghiệp vụ.
- [ ] Partition key phù hợp locality, phân bố tải và data ownership.
- [ ] Có biện pháp cho hot partition và tenant lớn.
- [ ] Directory/placement có version, owner, kiểm soát update và cache policy.
- [ ] Tenant identity được xác thực trước routing; không đọc/ghi nhầm cell.
- [ ] Có state machine và fencing cho tenant migration.
- [ ] Query/fan-out xuyên cell bị giới hạn, không phụ thuộc đồng bộ không cần thiết.

### Tài nguyên và khả năng chịu lỗi

- [ ] Mỗi cell có capacity đo được, headroom và quota.
- [ ] Worker, queue, DB pool, cache có mức isolation phù hợp SLO.
- [ ] Có timeout, circuit breaker, bounded retry và backpressure.
- [ ] Pod/node/zone placement phù hợp mục tiêu HA.
- [ ] Đã phân tích shared gateway, DNS, auth, KMS, broker và control plane.
- [ ] Failover stateful có replication, RTO/RPO, fencing và đủ capacity ở đích.
- [ ] Có quy trình backup, restore và migration theo cell.

### SLO, kiểm thử, triển khai

- [ ] Có global SLO và per-cell/per-cohort SLO cho phần cần giám sát.
- [ ] Metric theo cellId gồm throughput, error, p95/p99 và saturation.
- [ ] Có alert và runbook cho local/correlated outage.
- [ ] Canary và rollout có wave, điều kiện dừng và rollback.
- [ ] Có thử lỗi Pod, DB, broker, directory và một số shared dependency.
- [ ] Bài thử xác nhận các cell không bị inject vẫn giữ mức phục vụ yêu cầu.
- [ ] Có inventory app version/digest, schema và tenant placement.
- [ ] Chi phí thêm cell đã được so với lợi ích về blast radius và SLO.
- [ ] Kết quả diễn tập và postmortem được dùng để cải thiện ranh giới.

## 27. Kết luận

**Phân vùng** xác định dữ liệu hoặc công việc được chia và định tuyến thế nào. **Cell-based architecture** tổ chức các tài nguyên cần thiết thành đơn vị phục vụ tương đối độc lập, giúp giới hạn số khách hàng chịu tác động nếu một nhóm lỗi. Trong Microservices, hiệu quả của hai cách này phụ thuộc vào ranh giới **thực tế** của database, broker, cache, routing, shared dependencies và quy trình vận hành.

Một hệ thống có nhiều cell vẫn có thể sập toàn cục nếu dùng chung một gateway lỗi, config sai được đẩy đồng loạt hoặc failover dữ liệu không an toàn. Do vậy, cần đo blast radius, chọn khóa phân vùng có cơ sở, quản lý placement, áp bulkhead/quota, triển khai theo wave và kiểm chứng qua fault injection.

Hướng làm bền vững là **vẽ ranh giới lỗi → đo tải và SLO → chia partition/cell hợp lý → kiểm soát nguồn tài nguyên chung → thử sự cố và khả năng khôi phục → cải tiến theo bằng chứng vận hành**. Khi đó, cell và partition mới trở thành cơ chế giúp hệ thống chịu lỗi cục bộ mà không kéo theo toàn bộ nền tảng.