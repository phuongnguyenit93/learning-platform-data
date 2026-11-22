# Mẫu cell-based và deployment stamp để giới hạn quy mô mỗi đơn vị

> **Chương:** Mở rộng hệ thống  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một hệ thống có thể cần chia thành nhiều **cell** thay vì mở rộng vô hạn một cụm dùng chung.
2. Mô tả cách **deployment stamp** đóng gói một đơn vị triển khai hoàn chỉnh có thể lặp lại, nhân bản và quản lý theo phiên bản.
3. Xác định ranh giới cell theo tenant, workload, khu vực hoặc miền nghiệp vụ; chọn khóa định tuyến và cơ chế gán khách hàng.
4. Thiết kế cách cô lập dữ liệu, compute, network, quota, lỗi và quyền truy cập giữa các cell.
5. Tính giới hạn quy mô mỗi cell từ capacity, concurrency, dependency và blast radius; đặt ngưỡng cảnh báo và hành động mở cell mới.
6. Tổ chức control plane, data plane, inventory, placement service, routing và vòng đời stamp.
7. Lập kế hoạch di chuyển tenant/workload giữa cell, xử lý dữ liệu và nhất quán, rollback và cân bằng tải.
8. Đánh giá đánh đổi về độ phức tạp, chi phí, vận hành, độ tin cậy và bảo mật theo tư duy Well-Architected.

## 1. Khi một cụm dùng chung không còn là ranh giới phù hợp

Ở giai đoạn đầu, một hệ thống thường được triển khai thành một ứng dụng hoặc một cụm dịch vụ dùng chung cho mọi khách hàng. Cách này đơn giản: một bộ API, một database, một hàng đợi, một bộ dashboard và một pipeline phát hành. Tăng tải thường bắt đầu bằng cách tăng kích thước database, thêm instance API, thêm worker và tối ưu truy vấn.

Nhưng một hệ thống SaaS tăng trưởng có thể gặp giới hạn không chỉ ở CPU hoặc RAM:

- Database chung có giới hạn connection, IOPS, transaction, storage, lock và tốc độ phục hồi.
- Một tenant có traffic bất thường có thể chiếm connection pool, queue, cache hoặc worker của tenant khác.
- Lỗi schema, migration hoặc cấu hình có thể ảnh hưởng toàn bộ khách hàng.
- Một sự cố ở một vùng, dịch vụ phụ thuộc hoặc tài khoản cloud tạo blast radius lớn.
- Release mới cùng lúc tác động tất cả tenant; rollback hoặc triển khai dần khó giới hạn phạm vi.
- Quota của cloud service, giới hạn partition hoặc giới hạn API có thể đạt trước khi compute ứng dụng hết năng lực.
- Quy mô một cụm lớn khiến backup, restore, failover, maintenance và điều tra sự cố kéo dài.

**Cell-based architecture** chia hệ thống thành nhiều đơn vị phục vụ độc lập tương đối, mỗi đơn vị được giới hạn về quy mô và blast radius. Một cell có đủ thành phần cần thiết để phục vụ một nhóm tenant hoặc một workload: ingress/routing nội bộ, compute, database hoặc data partition, queue, cache, telemetry và chính sách vận hành.

Khi một cell gặp lỗi, mục tiêu là giới hạn tác động chủ yếu trong nhóm tenant/workload được gán vào cell đó. Khi một cell gần giới hạn, hệ thống có thể tạo cell mới và gán khách hàng mới hoặc di chuyển một phần khách hàng sang cell khác.

Cell không tự loại bỏ mọi shared dependency. DNS, identity provider, billing, control plane, container registry, observability, KMS hoặc dịch vụ mạng vẫn có thể được chia sẻ. Kiến trúc phải xác định những thành phần dùng chung nào có thể trở thành single point of failure hoặc làm tái mở rộng blast radius.

## 2. Cell, deployment stamp và các khái niệm liên quan

### 2.1. Cell là gì?

Một **cell** là một miền triển khai và vận hành có giới hạn, được thiết kế để phục vụ một tập tenant/workload xác định với năng lực và chính sách độc lập trong phạm vi kiến trúc cho phép.

Một cell có thể bao gồm:

- Điểm vào hoặc route nội bộ của cell.
- Một hay nhiều API/service instance.
- Database, schema, partition hoặc cụm dữ liệu thuộc phạm vi cell.
- Queue, worker, cache và storage riêng hoặc phân vùng có kiểm soát.
- Identity/workload role và network policy.
- Metric, log, trace, alert, runbook và cấu hình capacity.
- Version ứng dụng, cấu hình runtime và metadata nhận diện cell.

Cell có thể là một deployment trong cùng region, một tài khoản/subscription/project riêng, một nhóm cluster, một database shard hoặc một tổ hợp. **Ranh giới logic và ranh giới hạ tầng không bắt buộc trùng nhau**, nhưng càng dùng chung tài nguyên cốt lõi thì khả năng cô lập lỗi càng phụ thuộc vào cấu hình và quota của tài nguyên đó.

### 2.2. Deployment stamp là gì?

**Deployment stamp** là một gói triển khai có thể lặp lại, đại diện cho một bản sao có cấu hình của workload. Một stamp thường được tạo từ IaC modules, cấu hình, version ứng dụng, policy, network và các dịch vụ dữ liệu cần thiết.

Stamp là cách đóng gói để tạo cell một cách nhất quán:

- Có định danh và phiên bản template.
- Có tham số vùng, capacity, tier, loại dịch vụ và chính sách.
- Có tập resource ID được inventory ghi nhận.
- Có health/readiness, telemetry và tiêu chí nghiệm thu.
- Có lifecycle: provision, activate, scale, upgrade, drain, retire.

Trong nhiều kiến trúc, một deployment stamp triển khai ra một cell. Tuy vậy, một stamp cũng có thể tạo nhiều cell instance hoặc một cell có thể gồm nhiều stamp con theo tầng. Điều quan trọng là **đơn vị lặp lại có ranh giới và hợp đồng rõ**, không phải tên gọi.

### 2.3. Phân biệt cell với shard, replica và availability zone

| Khái niệm | Mục đích chính | Điểm khác với cell |
|---|---|---|
| **Shard/partition dữ liệu** | Chia dữ liệu và tải đọc/ghi | Có thể chỉ chia database; ứng dụng, queue và lỗi vẫn dùng chung |
| **Replica** | Tăng khả năng đọc hoặc dự phòng | Bản sao thường thuộc cùng một logical service/data set, không nhất thiết độc lập tenant |
| **Availability zone** | Cô lập một số lỗi hạ tầng trong region | Một cell có thể trải trên nhiều zone; nhiều cell cũng có thể cùng zone |
| **Microservice** | Tách trách nhiệm và ranh giới code/deploy | Service tách nhỏ nhưng vẫn có thể dùng chung database và blast radius |
| **Deployment stamp** | Nhân bản một cấu hình triển khai hoàn chỉnh | Là mẫu triển khai; cell là đơn vị cô lập/vận hành được tạo từ mẫu đó |
| **Tenant isolation** | Ngăn khách hàng truy cập hoặc tác động dữ liệu của nhau | Cell tăng lớp cách ly, nhưng vẫn cần authz và kiểm soát dữ liệu trong cell |

Một hệ thống sharded chưa chắc cell-based. Nếu mọi shard dùng chung queue, control plane có quyền xóa tất cả và release pipeline cùng lúc tác động toàn bộ shard, blast radius vẫn có thể rộng. Ngược lại, một cell có database riêng nhưng nhiều API replica bên trong không phải hệ thống microservice chỉ vì có nhiều instance.

## 3. Kiến trúc logic: control plane và data plane

### 3.1. Hai miền trách nhiệm

Một kiến trúc nhiều cell thường tách:

- **Control plane:** quản lý inventory cell, placement, tenant assignment, provisioning, policy, version, capacity, lifecycle và routing metadata.
- **Data plane:** xử lý request nghiệp vụ trong cell, truy cập dữ liệu của nhóm tenant được gán và phục vụ workload.

Control plane không nên nằm trên đường xử lý bắt buộc của mọi request. Nếu placement service tạm thời lỗi, request của tenant đã được gán cell vẫn nên được định tuyến theo assignment đã lưu/cached trong phạm vi an toàn. Các thao tác quản trị như tạo tenant, đổi cell hoặc provision cell mới có thể tạm chờ control plane.

### 3.2. Sơ đồ nhiều cell

~~~mermaid
flowchart TB
    U[Clients / Tenants] --> EDGE[Global Ingress / Gateway]
    EDGE --> ROUTER[Cell Router]
    ROUTER --> C1
    ROUTER --> C2
    ROUTER --> C3
    subgraph Control[Control Plane]
        REG[Cell Inventory]
        PLACE[Placement Service]
        PROV[Stamp Provisioner]
        POLICY[Policy / Capacity Controller]
        REG <--> PLACE
        PLACE --> ROUTER
        POLICY --> PROV
        PROV --> REG
    end
    subgraph C1[Cell A]
        AAPI[API + Workers]
        ADB[(Cell A Database)]
        AQ[Queue / Cache]
        AAPI --> ADB
        AAPI --> AQ
    end
    subgraph C2[Cell B]
        BAPI[API + Workers]
        BDB[(Cell B Database)]
        BQ[Queue / Cache]
        BAPI --> BDB
        BAPI --> BQ
    end
    subgraph C3[Cell C]
        CAPI[API + Workers]
        CDB[(Cell C Database)]
        CQ[Queue / Cache]
        CAPI --> CDB
        CAPI --> CQ
    end
    OBS[Central Observability] -.-> AAPI
    OBS -.-> BAPI
    OBS -.-> CAPI
~~~

Sơ đồ logic không có nghĩa central observability hoặc router nhất thiết là một máy chủ duy nhất. Các dịch vụ dùng chung cần triển khai HA, giới hạn quyền, cache và kế hoạch fallback. Router cần biết cell assignment nhưng không cần biết dữ liệu nghiệp vụ bên trong.

### 3.3. Control plane không trở thành điểm nghẽn

Các thao tác control plane thường ít hơn request nghiệp vụ nhưng có tác động lớn:

- Tạo cell mới hoặc cập nhật stamp version.
- Gán tenant mới, di chuyển tenant hoặc khóa tenant.
- Đánh dấu cell degraded/full/maintenance.
- Cập nhật routing metadata.
- Xem capacity và quyết định scale-out.
- Thu hồi cell sau khi tenant đã di chuyển.

Các biện pháp bảo vệ:

1. Dùng API quản trị có authentication, authorization và audit.
2. Tách quyền provision/destroy khỏi quyền xử lý request thường.
3. Lưu trạng thái workflow bền vững; thao tác provision có thể retry idempotently.
4. Cache assignment ở router/data plane; định nghĩa thời hạn và cách xử lý metadata lỗi thời.
5. Có quota và rate limit cho việc tạo cell để tránh automation tạo tài nguyên vô hạn.
6. Yêu cầu review riêng cho hành động phá hủy, migration dữ liệu và thay đổi routing diện rộng.
7. Đảm bảo control plane có thể hoạt động khi một cell lỗi, và không phụ thuộc chính cell đang được sửa.

Nếu router phải gọi placement database trên từng request, placement service trở thành dependency latency và availability của toàn bộ hệ thống. Assignment nên được cache hoặc phân phối qua cơ chế có độ tin cậy phù hợp.

## 4. Chọn ranh giới cell

Không có một cách chia cell phù hợp cho mọi sản phẩm. Ranh giới cần cân nhắc blast radius, dữ liệu, tải, địa lý, quyền và chi phí.

### 4.1. Một số chiến lược placement

| Chiến lược | Cách gán | Ưu điểm | Hạn chế |
|---|---|---|---|
| Theo tenant | Mỗi tenant thuộc một cell cố định | Cách ly và định tuyến rõ | Tenant lớn có thể vượt capacity một cell |
| Theo nhóm tenant | Nhiều tenant nhỏ chung cell | Hiệu quả chi phí, vận hành đơn giản hơn | Một tenant noisy neighbor ảnh hưởng nhóm |
| Theo khu vực địa lý | Tenant vào cell gần region được phép | Latency và data residency | Phải quản lý nhiều region và capacity không đều |
| Theo tier/service plan | Premium, standard hoặc workload khác vào cell khác | Phân bổ tài nguyên theo giá trị/SLO | Phức tạp billing/placement và tránh ưu tiên sai |
| Theo miền nghiệp vụ/workload | Workload khác nhau dùng cell riêng | Cô lập đặc tính tải và release | Có thể cần tích hợp chéo cell |
| Hybrid | Kết hợp tenant, geography, tier và capacity | Linh hoạt | Policy và routing khó hơn, phải có quy tắc nhất quán |

### 4.2. Nguyên tắc chọn ranh giới

- **Blast radius:** lỗi một cell ảnh hưởng bao nhiêu tenant, bao nhiêu phần doanh thu hoặc nghiệp vụ?
- **Data ownership:** dữ liệu của ai được lưu cùng nhau; yêu cầu xóa/export có thể cô lập không?
- **Workload profile:** đọc/ghi, burst, batch, background job và dung lượng của nhóm tenant có tương đồng không?
- **Quota/capacity:** các tenant chia sẻ cùng quota database, queue hoặc network ra sao?
- **Geography/compliance:** dữ liệu phải ở region nào, có được replication xuyên vùng không?
- **Release cadence:** tenant có cần phiên bản khác nhau hay mọi cell cần đồng nhất phiên bản?
- **Support model:** nhóm trực sự cố có thể xác định cell, owner và runbook dễ dàng không?
- **Cost efficiency:** số cell có tạo ra quá nhiều tài nguyên idle, bản sao control plane và công việc vận hành không?

Không nên chọn cell chỉ theo số tenant. Mười tenant nhỏ có thể tiêu thụ ít hơn một tenant xử lý dữ liệu nặng. Cần dùng metric theo tài nguyên và workload.

### 4.3. Tenant lớn và noisy neighbor

Một tenant có thể lớn dần và chiếm phần đáng kể capacity của cell. Các lựa chọn:

- Đưa tenant lớn vào cell riêng (silo/dedicated cell).
- Định tuyến workload nặng sang pool riêng nhưng giữ metadata và identity chung.
- Dùng quota/rate limit/priority để giới hạn mức tiêu thụ.
- Tách các tác vụ batch/analytics khỏi request tương tác.
- Chuyển tenant sang cell mới có capacity lớn hơn.

Dedicated cell giúp cô lập và tùy chỉnh SLO, nhưng tăng chi phí tối thiểu do phải duy trì database/compute/monitoring riêng. Cần tiering dựa trên nhu cầu và giá trị rõ ràng, tránh mở cell riêng theo quyết định thủ công khó kiểm soát.

## 5. Thiết kế deployment stamp có thể lặp lại

### 5.1. Stamp phải khai báo đầy đủ

Một stamp nên được mô tả bằng template có phiên bản và tham số:

| Nhóm | Nội dung cần khai báo |
|---|---|
| Identity | stamp ID, cell ID, environment, owner/team, tenant capacity |
| Location | cloud account/project, region, zone policy, network boundary |
| Compute | API/worker profile, autoscaling min/max, resource limits |
| Data | database engine/tier, storage limit, backup, retention, encryption |
| Messaging/cache | queue/topic, partition, retry, DLQ, cache capacity |
| Security | workload identity, IAM roles, KMS key, ingress/egress |
| Routing | cell endpoint, router metadata, health status, traffic weight |
| Observability | logs, metrics, traces, dashboards, alerts, tags |
| Version | stamp template version, application release, schema version |
| Lifecycle | provision, acceptance, active, degraded, draining, retired |

Thông số mặc định cần an toàn. Ví dụ database không public, secret không nằm trong repository, ingress chỉ mở qua gateway, log che dữ liệu nhạy cảm, backup bật theo loại dữ liệu và quota có giới hạn.

### 5.2. IaC và pipeline tạo cell

Một pipeline tham chiếu:

~~~mermaid
flowchart TD
    REQ[Cell request] --> VALID[Validate owner / region / capacity / budget]
    VALID --> PLAN[Render stamp + IaC plan]
    PLAN --> REVIEW[Policy checks and approval]
    REVIEW --> APPLY[Provision network / IAM / data / compute]
    APPLY --> BOOT[Bootstrap app and register endpoints]
    BOOT --> TEST[Health, security, connectivity, smoke tests]
    TEST --> ACCEPT{Acceptance passed?}
    ACCEPT -- No --> FIX[Remediate or rollback provisioning]
    FIX --> PLAN
    ACCEPT -- Yes --> INV[Register inventory and placement capacity]
    INV --> ACTIVE[Cell available for assignment]
~~~

Pipeline cần:

- Tách state IaC theo cell hoặc scope có thể quản lý độc lập.
- Idempotent để retry không tạo trùng resource.
- Giới hạn parallel provisioning để không vượt quota hoặc tạo spike control plane.
- Review diff/plan và phát hiện thao tác xóa/thay thế tài nguyên quan trọng.
- Kiểm tra policy tự động trước và sau apply.
- Ghi resource ID, endpoint, version, owner và output vào inventory.
- Chỉ cho phép placement service chọn cell khi acceptance đã thành công.
- Có rollback/cleanup cho provisioning dở dang và cơ chế reconcile state.

### 5.3. Không trôi cấu hình giữa các cell

Khi số cell tăng, chỉnh tay một cell tạo ra drift và hành vi không đồng nhất. Cần quản lý:

1. Stamp template version và ứng dụng version.
2. Cấu hình có nguồn chuẩn (Git/config service) và schema kiểm tra.
3. Quét drift định kỳ, tạo cảnh báo và quy trình reconcile.
4. Phát hành mẫu mới theo canary hoặc theo wave.
5. Giữ inventory thể hiện cell nào chưa cập nhật và lý do.
6. Có ngoại lệ được duyệt, thời hạn và owner rõ ràng.

Không bắt buộc tất cả cell ở cùng một release ngay lập tức. Có thể dùng wave theo region/tier/tenant cohort, nhưng số phiên bản và thời gian hỗ trợ phải được giới hạn để giảm chi phí tương thích.

## 6. Định tuyến và gán tenant vào cell

### 6.1. Assignment registry

Router cần xác định tenant/workload thuộc cell nào. Một registry tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| tenant_id | Định danh tenant |
| cell_id | Cell được gán |
| region | Vị trí triển khai |
| state | pending, active, moving, suspended, retired |
| routing_version | Phiên bản assignment dùng để phát hiện metadata cũ |
| assigned_at | Thời điểm gán |
| placement_reason | Quy tắc/tier/capacity đã dùng |
| data_location | Nơi dữ liệu chuẩn đang tồn tại |

Registry là metadata điều khiển, cần backup, audit, kiểm soát quyền sửa và tính nhất quán. Tránh lưu dữ liệu nghiệp vụ lớn trong registry hoặc cho phép caller tự chọn cell qua header không được kiểm chứng.

### 6.2. Luồng request

~~~mermaid
sequenceDiagram
    actor Client
    participant Edge as Global Gateway
    participant Auth as Identity / AuthN
    participant Router as Cell Router
    participant Reg as Assignment Cache / Registry
    participant Cell as Assigned Cell
    Client->>Edge: Request + access token
    Edge->>Auth: Validate identity and tenant claims
    Auth-->>Edge: Authenticated tenant context
    Edge->>Router: Route by verified tenant_id
    Router->>Reg: Resolve tenant assignment
    Reg-->>Router: cell_id + routing_version
    Router->>Cell: Forward to assigned endpoint
    Cell->>Cell: Authorize tenant and process request
    Cell-->>Client: Response
~~~

Đây là luồng logic; router có thể dùng cached mapping và không gọi registry đồng bộ ở từng request. **Xác thực danh tính và phân quyền tenant vẫn phải diễn ra trong cell**: biết tenant_id không đồng nghĩa được phép truy cập mọi dữ liệu của tenant đó.

### 6.3. Chọn khóa định tuyến

Tenant ID thường là khóa định tuyến dễ hiểu khi mỗi tenant thuộc một cell. Không dùng email, tên khách hàng hoặc thuộc tính người dùng có thể đổi làm khóa placement. Đối với workload không tenant như ingest telemetry hoặc job nội bộ, có thể cần workload ID/domain key riêng.

Một registry cần tránh:

- **Hot key:** một tenant rất lớn làm mapping cache hoặc router tập trung tải.
- **Stale assignment:** cache cũ chuyển request về cell cũ sau migration.
- **Split assignment:** hai router đồng thời hiểu tenant ở hai cell.
- **Missing assignment:** tenant vừa tạo chưa có cell active.
- **Unauthorized override:** client tự gửi cell ID để truy cập cell khác.

Dùng routing version/generation, cache TTL, invalidation, audit và cơ chế transition state để xử lý. Với tenant đang di chuyển, router có thể từ chối hoặc forward theo policy có kiểm soát, không đồng thời ghi cả hai nơi nếu chưa có cơ chế đồng bộ được thiết kế.

## 7. Giới hạn quy mô mỗi cell

Cell chỉ hữu ích nếu có giới hạn rõ. Nếu cell được phép tăng vô hạn, vấn đề của single cluster chỉ chuyển sang từng cell.

### 7.1. Xác định giới hạn theo thành phần

Giới hạn cell cần xét tối thiểu:

| Thành phần | Giới hạn cần đo |
|---|---|
| API/compute | Request/s, concurrency, CPU, memory, thread/connection pool, p95/p99 |
| Database | TPS, active connection, IOPS, storage, lock wait, replication lag, maintenance window |
| Queue/broker | Publish/consume throughput, partition, message size, backlog, oldest age |
| Cache | Memory, eviction, hot key, network throughput |
| Network | NAT/egress, connection tracking, bandwidth, private endpoint/service quota |
| Control plane | Provisioning rate, API quota, number cell/tenant mapping, registry throughput |
| Observability | Log/metric volume, cardinality, retention, ingestion limit |
| Backup/restore | Backup window, restore throughput, RTO/RPO và capacity phục hồi |

Giới hạn hữu ích nhất thường là **giới hạn sớm nhất trong các dependency quan trọng**, không phải CPU API. Ví dụ API còn 40% CPU nhưng database đã đạt giới hạn connection, việc tăng thêm API instance có thể làm tình hình tệ hơn.

### 7.2. Tính capacity theo SLO

Ví dụ giả định đo tải đại diện cho một cell:

- Database chịu được 1.000 transaction/giây trước khi p95 vượt mục tiêu.
- Đội muốn giữ utilization mục tiêu không quá 70% để còn headroom.
- Một tenant trung bình tạo 5 transaction/giây tại peak.
- Dự phòng cho tác vụ nền và biến động chung là 100 transaction/giây.

Capacity dành cho tenant:

~~~text
Target transaction rate = 1.000 × 70% = 700 txn/s
Headroom cho nền tảng = 100 txn/s
Capacity còn lại cho tenant = 700 - 100 = 600 txn/s
Số tenant lý thuyết = 600 / 5 = 120
~~~

Kết quả 120 là ước tính sơ bộ, không phải quota được chốt. Tenant không phân bố đều; một tenant có thể tăng đột biến; transaction mix và độ lớn dữ liệu khác nhau. Nếu cell có tenant lớn nhất gấp 10 lần trung bình, phải đưa skew vào kiểm thử hoặc tách dedicated cell.

Không cộng capacity giữa các thành phần nếu chúng không cùng đơn vị hoặc dependency có tỷ lệ sử dụng khác. Xây capacity model theo bottleneck của luồng nghiệp vụ: một request có thể tạo nhiều query, message và external call.

### 7.3. Quy tắc mở cell mới

Có thể đặt các ngưỡng theo nhiều tín hiệu:

- Dự báo database utilization hoặc connection pool vượt ngưỡng trong cửa sổ ổn định.
- p95/p99 tăng theo tải dù đã tối ưu query và scale trong cell.
- Storage/backup/restore tiến gần giới hạn vận hành.
- Một tenant làm usage skew vượt mức cho phép.
- Cell không còn đủ capacity dự phòng khi mất một zone.
- Quota cloud không còn headroom cho autoscaling.
- Mức blast radius hoặc số tenant vượt mục tiêu quản trị.

Ví dụ policy minh họa:

~~~text
if projected_peak_db_utilization > 70%
   for 3 consecutive review windows:
       mark cell = NEAR_CAPACITY
       stop assigning new tenants
       evaluate scale-up or create next cell

if critical_dependency_saturation > 85%
   or error_budget_burn exceeds alert policy:
       trigger immediate capacity / reliability review
~~~

Ngưỡng cần lấy từ load test, SLO và khả năng chịu lỗi; không áp 70%/85% như chuẩn cho mọi database. Cần thêm giới hạn tuyệt đối, tốc độ tăng trưởng và thời gian provision cell mới để tạo trước khi hết headroom.

### 7.4. Scale-up trong cell hay scale-out bằng cell mới?

| Hành động | Phù hợp khi | Hạn chế |
|---|---|---|
| Scale-up database/compute trong cell | Còn headroom quota và lợi ích rõ, chưa cần tăng blast radius | Có trần phần cứng/dịch vụ và có thể cần downtime |
| Scale-out API/worker trong cell | Bottleneck ở stateless compute/worker | Có thể tăng tải dependency dùng chung |
| Tách tenant lớn sang cell riêng | Noisy neighbor hoặc tenant vượt profile | Cần migration và vận hành dedicated capacity |
| Mở cell mới cho tenant mới | Cell hiện tại gần capacity, cần giới hạn blast radius | Tăng footprint, routing và chi phí nền |
| Chia workload theo cell riêng | Batch/analytics ảnh hưởng request tương tác | Tăng tích hợp và quản lý data product |

Mở cell mới không tự giải quyết bottleneck toàn cục như một database analytics dùng chung, identity provider, NAT gateway hoặc broker central. Shared dependency cần capacity model và kế hoạch phân vùng riêng.

## 8. Cô lập dữ liệu và giao dịch giữa cell

### 8.1. Data isolation

Có nhiều mức cô lập:

| Mức | Ví dụ | Đặc điểm |
|---|---|---|
| Logical tenant partition | Mọi tenant ở cùng DB, có tenant_id và row-level policy | Chi phí thấp, cần kiểm soát query/authz cực kỳ chặt |
| Schema/database per cell | Mỗi cell dùng schema hoặc DB riêng | Giới hạn nhiều lỗi dữ liệu hơn nhưng vẫn có shared instance/cluster quota |
| Cluster/account per cell | Database và hạ tầng dữ liệu riêng | Blast radius và quyền tốt hơn; chi phí và vận hành cao |
| Dedicated cell per tenant | Một tenant lớn có database/compute riêng | Cô lập mạnh, footprint lớn |

Chọn mức phù hợp với threat model, dữ liệu nhạy cảm, compliance, SLO, chi phí và mức độ độc lập cần đạt. Database riêng không thay thế authorization; một token của tenant A vẫn không được truy cập tenant B qua API hoặc export.

### 8.2. Invariant khi dữ liệu nằm trong một cell

- Cell là nơi có quyền ghi nguồn sự thật của tenant được gán.
- Mọi request truy cập dữ liệu phải xác minh tenant context và resource ownership.
- Primary/unique key nên có tenant scope hoặc bảo đảm ID global unique đúng yêu cầu.
- Background worker nhận message phải biết tenant/cell và xác thực payload nguồn.
- Backup/restore phải xác định rõ phạm vi cell và tenant; restore một cell không được ghi đè dữ liệu cell khác.
- Audit và retention theo tenant phải hoạt động xuyên storage, backup, event và analytics.

### 8.3. Giao dịch xuyên cell

Nếu một nghiệp vụ yêu cầu cập nhật dữ liệu ở hai cell khác nhau, không nên giả định có một transaction ACID đơn giản giữa chúng. Các lựa chọn:

- Đặt dữ liệu có quan hệ giao dịch chặt chẽ trong cùng cell nếu nghiệp vụ cho phép.
- Dùng saga/process manager với bước, trạng thái, timeout và compensation rõ.
- Dùng event/outbox để giao tiếp bất đồng bộ, chấp nhận eventual consistency.
- Tạo một service sở hữu dữ liệu tổng thể hoặc ledger nếu nghiệp vụ yêu cầu nơi ghi chuẩn duy nhất.

Không dùng cell boundary theo tenant nếu nghiệp vụ xuyên tenant cần ghi đồng bộ thường xuyên và không thể chấp nhận eventual consistency; khi đó cần xem lại ranh giới hoặc mô hình dữ liệu.

### 8.4. Backup và khôi phục theo cell

Mỗi cell nên có:

- Chính sách backup, snapshot/PITR và encryption key được định danh.
- Mục tiêu RTO/RPO phù hợp loại tenant/tier.
- Runbook restore vào cùng cell hoặc cell thay thế.
- Kiểm tra consistency giữa database, object storage, queue/outbox và metadata.
- Diễn tập restore độc lập từng cell, và diễn tập control plane/registry.
- Quy trình update routing sau restore/failover có fencing và version.

Backup riêng từng cell giúp khoanh vùng phục hồi, nhưng cũng làm tăng số lịch, key, policy và kết quả cần giám sát. Automation phải chứng minh tất cả cell được backup và restore test theo chính sách.

## 9. Cô lập lỗi và điều phối sự cố

### 9.1. Blast radius có giới hạn

Một cell degraded không nhất thiết làm toàn platform unavailable. Router có thể ngừng gán tenant mới vào cell đó; các tenant hiện hữu tiếp tục theo chính sách phục hồi. Control plane tạo cell mới cho tenant mới hoặc sau khi cell cũ được retire.

~~~mermaid
flowchart TB
    U[Requests] --> R[Cell Router]
    R -->|Healthy assignments| A[Cell A: Healthy]
    R -->|Healthy assignments| B[Cell B: Healthy]
    R -.->|Block new placement| C[Cell C: Degraded]
    C --> ALERT[Incident + Recovery workflow]
    ALERT --> REPAIR[Repair / restore / drain]
    REPAIR --> HEALTH{Acceptance and health restored?}
    HEALTH -->|Yes| C
    HEALTH -->|No| MIGRATE[Controlled tenant migration]
    MIGRATE --> N[Cell D: Replacement]
~~~

Không tự động chuyển mọi tenant ra khỏi cell degraded khi chưa hiểu lỗi. Nếu lỗi là database corruption hoặc dữ liệu chưa đồng bộ, chuyển traffic sang cell khác không có dữ liệu đúng có thể làm tình hình nghiêm trọng hơn.

### 9.2. Phân loại health theo cell

Một cell có thể có các trạng thái:

- **Provisioning:** tài nguyên đang được tạo; chưa nhận tenant.
- **Ready:** đạt kiểm tra nghiệm thu và có thể nhận assignment.
- **Active:** đang phục vụ tenant.
- **Near-capacity:** vẫn phục vụ nhưng không nên nhận thêm tải/tenant theo policy.
- **Degraded:** một hoặc nhiều thành phần quan trọng suy giảm.
- **Draining:** không nhận tenant mới, đang chuyển hoặc kết thúc workload.
- **Recovering:** đang restore/reconcile, chưa được mở lại.
- **Retired:** đã ngừng và đối soát tài nguyên/dữ liệu/quyền.

Cell status không nên là một cờ xanh/đỏ duy nhất. Lưu cả reason code, dependency status, thời gian đổi trạng thái, owner, action được phép và routing policy.

### 9.3. Shared dependency và correlated failure

Cell-based architecture giảm lỗi lan truyền giữa cell nhưng shared service vẫn có thể gây lỗi đồng thời:

| Shared dependency | Rủi ro | Biện pháp |
|---|---|---|
| Identity provider | Không xác thực được request trên mọi cell | HA, cache/session policy an toàn, fallback không bỏ xác thực |
| Global router/DNS | Không định tuyến được mọi cell | Dự phòng, cache assignment, health và failover control |
| Message broker dùng chung | Backlog hoặc quota tác động nhiều cell | Quota/namespace/partition isolation, capacity và backpressure |
| Central KMS | Không giải mã hoặc không khởi động workload | Thiết kế key availability, quyền và break-glass phù hợp |
| Observability pipeline | Mất telemetry toàn fleet | Buffer cục bộ, nhiều vùng tiếp nhận, alert độc lập |
| CI/CD/artifact registry | Không phát hành hoặc sửa lỗi cell | Cache artifact, version pinning và kế hoạch vận hành khi control plane lỗi |
| Control plane database | Không cập nhật placement/lifecycle | Replication/backup, cache và quy trình vận hành dự phòng |

Mục tiêu không nhất thiết loại bỏ mọi shared dependency, mà là **biết phạm vi ảnh hưởng, có cơ chế giảm tác động và không giả định cell độc lập tuyệt đối**.

## 10. Vòng đời tenant và cell

### 10.1. Đăng ký tenant mới

Một luồng assignment:

1. Xác thực tenant/business owner, region/data residency và service tier.
2. Tính nhu cầu tài nguyên ban đầu, tìm cell Ready/Active còn headroom.
3. Kiểm tra quota, tenant mix, locality và policy.
4. Tạo tenant metadata và cấu hình namespace/partition hoặc database scope.
5. Kiểm tra truy cập, dữ liệu khởi tạo và route.
6. Ghi assignment state active kèm routing version.
7. Bắt đầu traffic theo policy, theo dõi lỗi và capacity.

Tenant không được active chỉ vì đã có cell_id. Cần xác nhận dữ liệu khởi tạo, quyền, encryption, quota và route hoạt động.

### 10.2. Cell full hoặc gần capacity

Khi cell near-capacity:

- Ngừng placement tenant mới nếu dự báo vượt headroom.
- Giảm tải hoặc giới hạn workload không thiết yếu nếu cần.
- Scale-up trong cell nếu dependency và quota còn cho phép.
- Provision stamp mới, thực hiện acceptance.
- Gán tenant mới vào cell mới.
- Chọn tenant cần di chuyển nếu cell hiện hữu vượt ngưỡng hoặc cần cô lập noisy neighbor.

Tạo cell mới trước khi thật sự hết capacity; provisioning, database initialization, catalog và test có thể mất thời gian. Capacity controller cần dự báo dựa trên growth rate và lead time tạo cell.

### 10.3. Retire cell

Không xóa cell khi vẫn còn tenant assignment hoặc dữ liệu cần lưu. Quy trình retire:

1. Đánh dấu draining, không nhận assignment mới.
2. Liệt kê tenant, job, queue, secret, API client và dependency còn hoạt động.
3. Di chuyển tenant hoặc hoàn tất offboarding theo yêu cầu.
4. Đối soát dữ liệu, event chưa xử lý, backup và retention.
5. Thu hồi routing, credential và workload identity phù hợp thứ tự.
6. Thực hiện destroy plan đã review; giữ bản lưu trữ được duyệt.
7. Đối soát inventory, cloud resources, quota và billing.
8. Lưu audit record và đánh dấu retired.

## 11. Di chuyển tenant giữa cell

Tenant migration là thao tác phức tạp vì cần giữ dữ liệu, ghi mới, event và routing nhất quán trong suốt quá trình.

### 11.1. Các phương án di chuyển

| Phương án | Cách làm | Khi phù hợp | Rủi ro/đánh đổi |
|---|---|---|---|
| Offline migration | Tạm ngừng ghi, copy dữ liệu, kiểm tra, đổi route | Dữ liệu nhỏ, maintenance window chấp nhận được | Downtime theo thời gian copy/verify |
| Snapshot + delta sync | Snapshot ban đầu, đồng bộ thay đổi, rồi cutover | Dataset lớn và cần giảm downtime | Phải xử lý log/CDC và thứ tự commit |
| Dual-write có kiểm soát | Ghi hai nơi trong giai đoạn chuyển | Một số trường hợp cần transition ngắn | Dễ lệch và khó rollback; cần idempotency/reconciliation |
| Proxy/forwarding tạm thời | Cell cũ forward request hoặc ghi tới cell mới | Giảm đổi client/routing trong một thời gian | Thêm hop, coupling và điểm lỗi chuyển tiếp |

Không bật dual-write chỉ để “an toàn”. Nếu hai nơi không có transaction chung, một write có thể thành công ở cell A nhưng thất bại ở B. Phải có outbox, retry, reconciliation và nguồn sự thật được chỉ định.

### 11.2. Quy trình cutover tham chiếu

~~~mermaid
sequenceDiagram
    participant CP as Control Plane
    participant Old as Source Cell
    participant New as Destination Cell
    participant Router
    CP->>New: Provision and validate tenant scope
    CP->>Old: Start snapshot / CDC export
    Old-->>New: Initial snapshot
    Old-->>New: Delta changes / CDC
    New->>New: Validate counts, checksums, invariants
    CP->>Old: Freeze writes or enter controlled cutover
    Old-->>New: Final delta and checkpoint
    New-->>CP: Consistency gate passed
    CP->>Router: Update assignment + routing version
    Router-->>New: Route new requests
    New-->>CP: Observe successful traffic
    CP->>Old: Retain read-only rollback window
    Note over Old,New: Retire source only after acceptance and retention checks
~~~

Các bước quan trọng:

1. Provision destination cell và tạo schema/config đúng phiên bản.
2. Copy snapshot có version/checkpoint.
3. Đồng bộ delta bằng CDC/event log hoặc phương án phù hợp.
4. Đối soát số dòng, checksum theo partition, invariant nghiệp vụ và quyền.
5. Tạm ngừng ghi hoặc dùng cơ chế fencing để chặn writer cũ trong cửa sổ cutover.
6. Áp delta cuối, xác nhận checkpoint và đánh dấu nguồn dữ liệu chuẩn.
7. Cập nhật assignment/routing version theo cơ chế atomic hoặc có trạng thái transition an toàn.
8. Theo dõi request, event, latency, error và dữ liệu sau chuyển.
9. Giữ source ở read-only/retention theo thời hạn rollback được phê duyệt.
10. Chỉ retire source khi đủ điều kiện dữ liệu và vận hành.

### 11.3. Rollback migration

Rollback không phải luôn đảo route về cell cũ. Sau cutover có thể đã phát sinh giao dịch mới ở cell đích. Nếu quay lại nguồn mà không đồng bộ delta ngược, có thể mất dữ liệu.

Kế hoạch rollback cần nêu:

- Mốc cuối cùng cell cũ còn là writer.
- Cell mới trở thành writer từ thời điểm nào.
- Cách ghi nhận mọi mutation sau cutover.
- Có thể reverse-sync về cell cũ hay phải forward-fix trong cell mới?
- Ai quyết định rollback và giới hạn thời gian?
- Nếu không thể rollback dữ liệu, cách khôi phục là roll-forward/fix-forward nào?

Giữ source read-only có thể hỗ trợ tra cứu/đối soát nhưng không tự làm cho rollback write an toàn.

## 12. Release và nâng cấp fleet cell

### 12.1. Rollout theo wave

Khi có hàng chục hoặc hàng trăm cell, deploy cùng lúc làm tăng blast radius. Có thể phát hành theo wave:

1. Test integration/staging stamp.
2. Canary trên một cell nội bộ hoặc nhóm tenant thử nghiệm.
3. Wave nhỏ theo region/tier, theo dõi SLI và data correctness.
4. Tăng dần số cell sau mỗi quality gate.
5. Tạm dừng nếu error budget, lỗi schema, latency hoặc dependency vượt ngưỡng.
6. Hoàn tất rollout và xác nhận cell còn lại theo deadline.

Phải quản lý compatibility giữa các version ứng dụng, schema và event. Cell A có thể đã nâng cấp trong khi Cell B còn phiên bản cũ. Shared service hoặc event format phải hỗ trợ giai đoạn đồng tồn tại.

### 12.2. Version skew

Một fleet có version skew có thể gây:

- Contract API/event khác nhau giữa cell.
- Tool quản trị không tương thích.
- Migration schema chỉ chạy ở một phần cell.
- Dashboard tổng hợp không hiểu metric cũ/mới.
- Lỗ hổng bảo mật ở cell không được nâng cấp kịp.

Cần inventory theo stamp version, application version, schema version và ngày phát hành; định nghĩa support window, minimum supported version và deadline nâng cấp. Có thể tự động đánh dấu cell out-of-policy và ngừng nhận tenant mới.

### 12.3. Cell canary phải đại diện

Không chọn cell canary chỉ vì ít tenant. Cần cân nhắc:

- Workload profile và traffic có giống fleet hay không.
- Có tenant nội bộ/đối tác có thể phản hồi nhanh không.
- Region/cloud dependency có đại diện không.
- Data volume và schema có thể bộc lộ migration issue không.
- Có thể rollback/fix-forward mà không tạo ảnh hưởng rộng không.

Một cell nhỏ chỉ test được startup, không chắc phơi bày bottleneck database hoặc streaming ở tải cao.

## 13. Quan sát và quản trị fleet

### 13.1. Metric cấp cell và cấp fleet

| Nhóm | Cell-level metric | Fleet-level metric |
|---|---|---|
| Traffic | RPS, request success, p95/p99 theo endpoint | Tổng traffic, phân bố tải, tenant skew |
| Compute | CPU/memory/concurrency/API saturation | Cell utilization distribution, số cell near-capacity |
| Database | TPS, connection, IOPS, lock, storage, replica lag | Top cell bottleneck, capacity forecast |
| Queue | Depth, oldest age, retry, DLQ, consume rate | Backlog tổng, cell có consumer lag |
| Reliability | Availability/SLO, incident, restart, failover | Error budget theo cell/fleet, correlated failure |
| Capacity | Headroom, tenant count, growth rate | Lead time tạo cell, tỷ lệ sử dụng, reserved capacity |
| Security | IAM drift, policy violation, access anomaly | Cell out-of-policy, credential rotation status |
| Release | Version, deployment outcome, rollback | Version skew, rollout percentage |
| Cost | Cost per tenant/cell, idle resources | Cost per active tenant, cost per unit workload |

Không chỉ lấy average toàn fleet. Một vài cell gần bão hòa có thể bị che khuất bởi nhiều cell nhàn rỗi. Theo dõi percentile/distribution và top-N cell/tenant theo tài nguyên.

### 13.2. Dashboard và runbook

Dashboard nên trả lời nhanh:

- Cell nào active, near-capacity, degraded, draining hoặc out-of-policy?
- Tenant nào thuộc cell nào và thay đổi assignment gần nhất khi nào?
- Bottleneck của cell là API, DB, queue, network hay shared dependency?
- Cell còn đủ capacity nếu mất một zone không?
- Phiên bản và schema nào đang chạy ở từng cell?
- Backup/restore gần nhất và lần diễn tập cuối?
- Chi phí tăng ở cell nào và do workload/retention/query nào?

Runbook cần có bước khoanh vùng, owner, lệnh/automation được phép, điều kiện dừng và cách xác nhận phục hồi. Tránh yêu cầu người trực chạy truy vấn thủ công trên mọi cell mà không có inventory và automation.

### 13.3. Fleet compliance

Một controller có thể quét cell định kỳ:

~~~text
for each cell in inventory:
    verify stamp_version is supported
    verify required security policies
    verify backups and restore evidence
    verify telemetry and alert ownership
    verify capacity and dependency health
    verify tenant assignments are consistent
    if violation:
        create remediation work
        block new placement when risk is critical
~~~

Đây là mã giả quy trình, không phải script chạy trực tiếp. Policy enforcement cần có chế độ kiểm tra, cảnh báo, chặn placement và ngoại lệ với owner/thời hạn; tránh auto-destroy cell chỉ vì một tag bị thiếu.

## 14. Bảo mật trong kiến trúc cell-based

### 14.1. Ranh giới cell không thay thế ranh giới danh tính

Ngay cả khi tenant được tách cell, API vẫn phải:

- Xác minh token và audience/issuer.
- Lấy tenant context từ claim đáng tin cậy sau authentication.
- Kiểm tra tenant assignment và resource ownership.
- Áp dụng authorization ở từng thao tác dữ liệu.
- Chặn caller tự thay tenant/cell ID trong path/header/body để truy cập tenant khác.
- Ghi audit cho thao tác nhạy cảm, export, quản trị và migration.

Cell riêng là lớp giảm blast radius, không phải lý do bỏ kiểm thử IDOR/BOLA hoặc tenant isolation.

### 14.2. Quyền quản trị và break-glass

Control plane thường có quyền lớn: tạo/destroy network, database, IAM và routing. Cần:

- Tách identity cho provisioner, router, data migration, operator và workload.
- Least privilege theo cell scope; hạn chế quyền wildcard toàn fleet.
- Approval/audit cho destroy, reassign, change region và rotation key có ảnh hưởng lớn.
- Break-glass có thời hạn, MFA, log và review sau sử dụng.
- Quản lý KMS key/secret theo cell hoặc theo domain; không để một credential bị lộ mở toàn fleet.
- Policy cho cross-cell data access và support access có kiểm soát.

### 14.3. Mã hóa và dữ liệu nhạy cảm

Tenant có thể yêu cầu key riêng, region riêng hoặc retention riêng. Mẫu stamp nên cho phép policy tier tương ứng nhưng không nên tạo biến thể không kiểm soát. Mọi exception phải được inventory và review.

Khi xóa một tenant, phải xem cả database cell, queue, cache, object storage, snapshot, backup, analytics extract và data science dataset. Cell boundary giúp cô lập tập dữ liệu nhưng không tự bảo đảm xóa hết mọi bản sao.

## 15. Chi phí và hiệu quả sử dụng

### 15.1. Lợi ích và chi phí của việc nhân bản

Cell tăng số lần lặp lại các thành phần như database, queue, cache, gateway và monitoring. Điều này có thể tăng tổng chi phí nền ngay cả khi mỗi cell chưa được dùng hết.

Các lựa chọn:

- Cell nhỏ giảm blast radius nhưng có thể làm tăng chi phí idle và số database/cluster.
- Cell lớn cải thiện utilization nhưng tăng blast radius và thời gian phục hồi.
- Dedicated cell tăng cách ly nhưng giảm economies of scale.
- Shared control plane tiết kiệm chi phí nhưng cần HA, quota và kiểm soát tương quan lỗi.
- Shared broker/storage tiết kiệm footprint nhưng có thể tái tạo noisy neighbor.

### 15.2. Ví dụ tính chi phí sơ bộ

Giả sử một stamp có chi phí nền 500 USD/tháng cho database tier tối thiểu, compute baseline 200 USD/tháng, queue/cache/monitoring 100 USD/tháng. Tổng baseline là 800 USD/tháng/cell trước chi phí biến đổi.

~~~text
10 cell × 800 USD = 8.000 USD/tháng baseline

Nếu mỗi cell chỉ dùng trung bình 35% compute baseline,
nhưng database và một số dịch vụ vẫn phải duy trì:
chi phí không giảm theo đúng 35%.
~~~

Ví dụ chỉ nhằm minh họa cách tư duy, không đại diện giá dịch vụ cloud. Dự toán thực cần dùng calculator/billing của provider, region, reservation/discount, network egress, backup, log, data transfer và mức HA.

### 15.3. Theo dõi utilization và hiệu quả

Metric gợi ý:

- Cost per active tenant và cost per transaction.
- Tỷ lệ utilization compute/database theo cell.
- Số cell near-capacity và số cell idle.
- Tenant count và workload skew theo cell.
- Chi phí dự phòng HA/DR và backup.
- Provisioning cost/time và chi phí migration.

Không tối ưu chỉ số cost per tenant nếu nó làm tăng tail latency hoặc blast radius vượt mục tiêu. Đánh giá tổng thể theo SLO, risk và cost.

## 16. Đánh đổi và khi nào không nên dùng cell-based

Cell-based architecture có lợi khi quy mô, độ độc lập hoặc yêu cầu cách ly đủ lớn. Nhưng nó tạo thêm một tầng phân phối và điều phối.

### 16.1. Chi phí phức tạp

- Cần control plane và inventory chính xác.
- Routing phải hiểu assignment, transition và cache invalidation.
- Migration giữa cell cần giải quyết consistency và rollback.
- Fleet có version skew và policy drift.
- Debug request cần trace qua gateway/router tới đúng cell.
- Backup/restore, security review và capacity planning phải nhân rộng.
- Shared dependency vẫn có thể tạo correlated failure.

### 16.2. Khi nào nên giữ kiến trúc đơn giản hơn?

Không cần cell-based nếu:

- Tải và dữ liệu còn nhỏ, một cụm đáp ứng SLO với headroom đủ.
- Không có yêu cầu blast radius/tenant isolation cao.
- Đội chưa có khả năng vận hành nhiều đơn vị độc lập.
- Chi phí nền của mỗi cell cao hơn lợi ích scale/isolation.
- Workload cần transaction xuyên tenant liên tục khiến chia cell làm tăng phức tạp.

Có thể bắt đầu bằng modular architecture, tenant-aware schema, quota, rate limit, queue isolation và observability. Chuẩn bị access pattern, tenant registry và IaC để tiến hóa sau mà không phải chia cell quá sớm.

### 16.3. Các bước tiến hóa

1. Một cụm dùng chung, có tenant ID, authz và quota đúng.
2. Tách workload nặng, read replica hoặc partition dữ liệu theo nhu cầu.
3. Chuẩn hóa deployment bằng stamp/IaC nhưng vẫn chạy một hoặc vài cell.
4. Tách nhóm tenant và control plane/placement.
5. Mở thêm cell theo capacity và blast radius.
6. Bổ sung migration automation, fleet release và compliance.

Không phải mọi hệ thống phải đi qua tất cả bước; hãy dùng trigger cụ thể thay vì coi cell-based là đích bắt buộc.

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi với cell và deployment stamp | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Cell có thể provision, test, release, migrate và retire lặp lại? | IaC, pipeline, inventory, runbook, fleet dashboard |
| **Security** | Tenant, workload, cell và control plane có least privilege và cách ly dữ liệu? | Tenant isolation tests, IAM review, audit, KMS policy |
| **Reliability** | Cell lỗi có khoanh vùng; shared dependency có kế hoạch; restore/migration đạt yêu cầu? | Fault injection, cell outage drill, restore, routing test |
| **Performance Efficiency** | Capacity mỗi cell, quota, noisy neighbor và scale-out có được đo? | Load test, skew, saturation, capacity forecast |
| **Cost Optimization** | Footprint cell, idle baseline, dedicated tier và migration có hiệu quả? | Cost per tenant, utilization, showback |
| **Sustainability** | Có giảm tài nguyên nhàn rỗi, lifecycle stamp và storage/backup hợp lý? | Idle cell reports, scale-down, retention compliance |

Cell-based không tự động tăng mọi trụ cột. Nhiều cell có thể tăng độ tin cậy nhờ cô lập nhưng làm operational excellence khó hơn nếu thiếu automation. Chọn ranh giới phù hợp với khả năng thực thi của tổ chức.

## 18. Bài thực hành: chia nền tảng đặt lịch thành các cell

**Tình huống:** Một SaaS đặt lịch có 2.000 tenant. Phần lớn tenant nhỏ, nhưng 20 tenant lớn tạo 45% lưu lượng. Một cụm hiện tại có API, relational database, queue và cache dùng chung. Giờ cao điểm xuất hiện noisy neighbor; release mới ảnh hưởng tất cả khách hàng. Nhóm có thể triển khai một cell bằng IaC nhưng chưa có placement service hoặc tenant migration automation.

Hãy thiết kế kế hoạch tiến hóa:

1. **Access/workload profile:** phân tích traffic, DB TPS, connection, queue depth, storage, tenant skew và peak profile.
2. **Cell boundary:** chọn nhóm tenant, dedicated cell cho tenant lớn hoặc cách hybrid; giải thích blast radius và chi phí.
3. **Stamp:** mô tả network, compute, DB, queue, cache, IAM, monitoring, backup và version tham số hóa.
4. **Control plane:** định nghĩa inventory, placement, assignment state, router, cache TTL và quyền thay đổi.
5. **Capacity:** dùng load test để xác định giới hạn database/compute/queue; tính số tenant theo profile và headroom sau lỗi zone.
6. **Isolation:** xác định database per cell hay shared cluster/schema; nêu cách đảm bảo tenant authorization và backup/restore.
7. **Migration:** chọn offline hay snapshot+delta sync; mô tả fencing, cutover, routing version, rollback và đối soát.
8. **Release fleet:** thiết kế cell canary và wave rollout, policy version skew và hỗ trợ schema đồng tồn tại.
9. **Operations:** dashboard cell/fleet, cảnh báo near-capacity, degraded cell, drift và restore.
10. **FinOps/Well-Architected:** ước tính baseline cost, cost per tenant, các shared dependency và rủi ro còn lại.

Bảng thiết kế tối thiểu:

| Quyết định | Lựa chọn | Lý do | Cách kiểm chứng |
|---|---|---|---|
| Cell placement | Theo tier + workload, có dedicated cell cho tenant lớn | Giảm noisy neighbor và giới hạn blast radius | Load test theo skew |
| Tenant registry | Tenant ID → cell ID + routing version | Route ổn định và migration có trạng thái | Stale cache/split assignment test |
| Data isolation | Database riêng theo cell | Giới hạn connection/IO và backup scope | Tenant isolation + restore drill |
| Capacity trigger | Theo DB TPS, p95, connection, queue age | Phát hiện bottleneck thực | Capacity test và forecast |
| Migration | Snapshot + delta sync + fencing | Giảm downtime với dữ liệu lớn | Reconciliation và rollback drill |
| Fleet release | Canary rồi rollout theo wave | Giới hạn tác động version mới | SLI gate và version inventory |

**Tiêu chí hoàn thành:** Người review hiểu cell chứa những gì, tenant được gán ra sao, giới hạn nào khiến cần cell mới, lỗi cell ảnh hưởng ai, dữ liệu di chuyển thế nào và ai chịu trách nhiệm cho từng thao tác. Các con số chưa có dữ liệu phải ghi là giả định cần đo.

## 19. Khung ghi nhớ

- **Cell** là đơn vị phục vụ và cô lập có giới hạn; mục tiêu là giảm blast radius và cung cấp capacity có thể dự đoán.
- **Deployment stamp** là mẫu triển khai có phiên bản, tham số và lifecycle để tạo các cell nhất quán.
- **Control plane** quản lý placement, inventory và lifecycle; **data plane** xử lý request và dữ liệu nghiệp vụ.
- **Cell boundary** nên dựa trên workload, tenant, dữ liệu, region, SLO và chi phí; không chỉ đếm khách hàng.
- **Capacity limit** phải tính bottleneck và headroom sau lỗi; mở cell mới trước khi hết năng lực.
- **Tenant routing** cần assignment có version, cache và kiểm tra quyền trong cell.
- **Migration** cần nguồn sự thật, snapshot/delta, fencing, cutover, đối soát và kế hoạch rollback.
- **Shared dependency** vẫn có thể tạo correlated failure; phải được thiết kế và kiểm thử như một phần của fleet.
- **Automation và governance** giúp stamp, release, backup, security và compliance đồng nhất khi số cell tăng.

Mẫu cell-based và deployment stamp biến mở rộng thành việc nhân bản có kiểm soát các đơn vị nhỏ hơn, mỗi đơn vị có giới hạn, owner và hành vi phục hồi rõ ràng. Giá trị chính là giới hạn tác động và dự báo năng lực; đổi lại, tổ chức phải đầu tư vào placement, routing, migration và quản trị fleet. Chỉ nên mở rộng sang mô hình này khi lợi ích về độ tin cậy, cách ly hoặc khả năng tăng trưởng lớn hơn chi phí vận hành mà nó tạo ra.
