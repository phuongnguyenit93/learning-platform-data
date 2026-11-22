# Đối chiếu dịch vụ tương đương giữa AWS, Azure và Google Cloud

## 1. Mục tiêu và cách đọc bản đối chiếu

Trong kiến trúc ứng dụng đám mây, câu hỏi “Dịch vụ X của AWS tương đương với dịch vụ nào ở Azure hoặc Google Cloud?” thường xuất hiện khi thiết kế hệ thống mới, đánh giá phương án đa đám mây hoặc lập kế hoạch di chuyển. Một bảng tra tên sản phẩm có thể giúp định hướng nhanh, nhưng **tên dịch vụ giống chức năng không đồng nghĩa chúng có cùng hợp đồng vận hành, khả năng mở rộng, mức nhất quán hay chi phí**.

Bài học thuộc chương **Mẫu kiến trúc tham chiếu** của module **CLOUD_ARCHITECTURE**. Mục tiêu là học cách chọn và đối chiếu các thành phần từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai; đồng thời nhìn rõ đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài này, người học có thể:

- Ánh xạ năng lực kiến trúc giữa **Amazon Web Services (AWS)**, **Microsoft Azure** và **Google Cloud** mà không nhầm lẫn giữa sản phẩm và chức năng.
- Nhận ra những nhóm có tương đương khá sát (như object storage) và những nhóm phải thiết kế lại (như NoSQL, hàng đợi, serverless).
- Chuyển một **kiến trúc tham chiếu trung lập nhà cung cấp** thành ba phương án triển khai có thể so sánh.
- Tạo tiêu chí chọn dịch vụ dựa trên SLO, mô hình dữ liệu, mức nhất quán, yêu cầu mạng và bảo mật, khả năng vận hành cùng tổng chi phí sở hữu (TCO).
- Lập kế hoạch kiểm chứng và di chuyển có thể đo lường, thay vì chỉ thay tên sản phẩm trên sơ đồ.

> **Phạm vi:** Tên dịch vụ và nhóm năng lực bên dưới là định hướng kỹ thuật; tính năng, SKU, quota, giá, SLA, khu vực cung cấp và cách tích hợp có thể thay đổi. Trước quyết định triển khai cần kiểm tra tài liệu và điều khoản hiện hành tại **region** dự kiến.

## 2. Đối chiếu theo năng lực, không đối chiếu theo tên

Cùng một chức năng “chạy container” có thể được giải quyết bằng Kubernetes, dịch vụ container được quản lý hoặc nền tảng serverless. Vì thế, khi đối chiếu cần đi theo bốn lớp:

| Lớp đối chiếu | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Hợp đồng chức năng** | Dịch vụ tiếp nhận loại workload/giao thức/dữ liệu nào? | HTTP request, tác vụ nền, queue, SQL, key–value, object. |
| **Tính chất phi chức năng** | Giới hạn mở rộng, độ trễ, nhất quán, HA, DR, SLO ra sao? | RPO/RTO, thông lượng, thời gian cold start, thứ tự sự kiện. |
| **Vận hành và bảo mật** | Ai quản lý OS, bản vá, backup, IAM, mạng riêng, log, khóa mã hóa? | VM tự quản khác dịch vụ database được quản lý. |
| **Chi phí và ràng buộc** | Trả theo thời gian, yêu cầu, dung lượng hay lưu lượng? Có egress/license/lock-in? | Trả tiền cho giờ chạy VM khác trả tiền cho request. |

Có thể đánh giá độ tương đương theo ba mức:

1. **Gần tương đương:** cùng loại tài nguyên và mô hình tiêu thụ chính, nhưng vẫn phải kiểm tra SLA, quota, cấu hình và giá.
2. **Tương đương về mục đích:** cùng giải quyết một nhu cầu, song API, hành vi, khả năng vận hành hoặc mô hình lập trình khác nhau.
3. **Không có tương đương một-một:** cần kết hợp nhiều dịch vụ hoặc thiết kế lại một phần ứng dụng và dữ liệu.

Ví dụ, **Amazon S3 ↔ Azure Blob Storage ↔ Google Cloud Storage** đều là object storage, tương đồng khá sát về mục đích. Ngược lại, **Amazon SQS ↔ Azure Service Bus ↔ Google Cloud Pub/Sub** chỉ là bản so sánh điểm xuất phát: SQS là hàng đợi công việc, Service Bus có queue/topic và broker features, còn Pub/Sub lấy topic–subscription làm trung tâm. Muốn giao một tác vụ HTTP cụ thể trên Google Cloud có thể cần **Cloud Tasks**.

## 3. Tài khoản, tổ chức, mạng và phân phối lưu lượng

Bảng dưới đây tập trung vào vai trò kiến trúc. Một ô có nhiều tên cho biết **nhiều dịch vụ phối hợp** để tạo thành năng lực tương ứng.

| Năng lực | AWS | Azure | Google Cloud | Lưu ý kiến trúc |
| --- | --- | --- | --- | --- |
| Phân cấp tổ chức và quản trị | AWS Organizations, Control Tower | Management groups, subscriptions, Azure Policy, landing zones | Organization, folders, projects, Organization Policy | Ranh giới tính phí, tài nguyên, quyền và quota không giống nhau. |
| Quản lý định danh, quyền | IAM, IAM Identity Center | Microsoft Entra ID, Azure RBAC | Cloud IAM, Cloud Identity | Phân biệt người dùng, workload identity, role, policy và federation. |
| Mạng ảo riêng | Amazon VPC | Azure Virtual Network (VNet) | Virtual Private Cloud (VPC) | AWS VPC và Azure VNet có phạm vi vùng; Google Cloud VPC là mạng toàn cục với subnet theo vùng. |
| Mạng con | VPC subnets | VNet subnets | VPC subnets | Ranh giới subnet/zone khác nhau, không sao chép CIDR và cấu trúc máy móc. |
| Lọc lưu lượng | Security Groups, Network ACLs | Network Security Groups, Azure Firewall | VPC firewall rules, Cloud NGFW | Stateful/stateless, ưu tiên rule và chỗ gắn chính sách khác nhau. |
| Truy cập riêng đến dịch vụ | VPC endpoints, AWS PrivateLink | Private Endpoint, Azure Private Link | Private Service Connect | Kiểm tra DNS riêng, hướng kết nối, loại endpoint và dịch vụ được hỗ trợ. |
| NAT cho outbound | NAT Gateway | Azure NAT Gateway | Cloud NAT | Kiểm tra giới hạn IP/port, logging và chi phí egress. |
| VPN và đường truyền riêng | Site-to-Site VPN, Direct Connect | VPN Gateway, ExpressRoute | Cloud VPN, Cloud Interconnect | Khác về định tuyến BGP, độ sẵn sàng, băng thông và vị trí kết nối. |
| Phân giải DNS | Route 53 | Azure DNS, Azure Private DNS | Cloud DNS | DNS công khai và DNS riêng cần thiết kế riêng. |
| Phân phối nội dung | CloudFront | Azure Front Door/CDN | Cloud CDN | Khác về điểm tích hợp WAF, cache, origin, tính năng global. |
| Load balancer HTTP(S) | Application Load Balancer | Application Gateway, Azure Front Door | Application Load Balancer | Chọn phạm vi regional/global và cách tích hợp với backend. |
| Load balancer L4 | Network Load Balancer | Azure Load Balancer | Network Load Balancer | Giao thức, passthrough/proxy và health check khác nhau. |
| WAF / bảo vệ ứng dụng | AWS WAF | Web Application Firewall (Application Gateway/Front Door) | Cloud Armor | Điểm áp policy, phạm vi bảo vệ, giới hạn rule và giá cần xem riêng. |

### Khác biệt mạng rất dễ bị bỏ qua

**AWS**: VPC nằm trong một region; subnet gắn với một Availability Zone (AZ). **Azure**: VNet ở phạm vi region, subnet có thể chứa tài nguyên của các zone khác nhau tùy loại dịch vụ. **Google Cloud**: VPC mang tính toàn cục, còn subnet là tài nguyên theo region. Điều đó tác động trực tiếp đến sơ đồ route, cấp phát IP, phân vùng lỗi và tự động hóa bằng IaC.

Khi chuyển kiến trúc từ AWS sang Google Cloud, việc gộp hoặc tách VPC cần được quyết định từ yêu cầu cô lập, tổ chức, kết nối, firewall và quota, chứ không nên máy móc tạo “mỗi region một VPC” vì cách AWS thường làm. Khi chuyển sang Azure, phải chú ý cách áp dụng NSG, private endpoint và DNS riêng. Mọi phương án đều cần định nghĩa rõ đường **north–south** (người dùng vào ứng dụng) và **east–west** (lưu lượng giữa các thành phần nội bộ).

## 4. Compute, container, serverless và lớp ứng dụng

| Nhu cầu | AWS | Azure | Google Cloud | Mức tương đương và rủi ro |
| --- | --- | --- | --- | --- |
| Máy ảo | EC2 | Azure Virtual Machines | Compute Engine | Gần tương đương ở mức VM; khác loại máy, ổ đĩa, image, quota và mô hình giá. |
| Tự động mở rộng VM | EC2 Auto Scaling groups | Virtual Machine Scale Sets | Managed Instance Groups | Kiểm tra health check, autoscaling signal và chiến lược cập nhật. |
| Kubernetes được quản lý | EKS | AKS | GKE | Đều vận hành Kubernetes nhưng khác phiên bản, quyền, mạng, node/pod, tính năng quản lý. |
| Điều phối container không cần tự quản Kubernetes | ECS | Azure Container Apps | Cloud Run | Cùng nhóm nhu cầu nhưng mô hình tác vụ, request, network, scaling khác đáng kể. |
| Compute serverless cho container | Fargate (với ECS/EKS) | Azure Container Apps, Azure Container Instances | Cloud Run | Không có ánh xạ một-một: Fargate cung cấp năng lực chạy task/pod, Cloud Run là nền tảng chạy service/job. |
| Function theo sự kiện | Lambda | Azure Functions | Cloud Run functions (trước đây là Cloud Functions) | Khác giới hạn runtime, trigger, concurrency, cold start, timeout. |
| Web app PaaS | Elastic Beanstalk, App Runner | Azure App Service | App Engine, Cloud Run | Mức kiểm soát runtime, khả năng triển khai và mạng riêng khác nhau. |
| API management | API Gateway | API Management | API Gateway, Apigee | API gateway cơ bản và nền tảng API management doanh nghiệp là hai mức khác nhau. |
| Workflow orchestration | Step Functions | Durable Functions, Logic Apps | Workflows | Cần đối chiếu state, retry, timeout, integration và giới hạn chi phí. |
| Build và triển khai | CodeBuild/CodePipeline, CodeDeploy | Azure DevOps Pipelines, GitHub Actions | Cloud Build, Cloud Deploy | Có thể dùng công cụ CI/CD chung; khác cách cấp quyền và phát hành. |
| Registry image | Elastic Container Registry (ECR) | Azure Container Registry (ACR) | Artifact Registry | Kiểm tra replication, vulnerability scanning, quyền đọc và retention. |

### Khi nào chọn VM, Kubernetes, PaaS hay serverless?

- **VM** phù hợp khi cần kiểm soát hệ điều hành, phần mềm phụ thuộc hoặc cách đóng gói khó thay đổi. Đánh đổi là trách nhiệm vá lỗi, scaling, hardening và vận hành.
- **Kubernetes được quản lý** hữu ích khi có nhiều service cần cùng mô hình orchestration, chính sách phân phối workload và hệ sinh thái Kubernetes. Vẫn phải quản trị cấu hình, cluster lifecycle, mạng, quyền, năng lực và chi phí.
- **PaaS/container serverless** phù hợp API/web hoặc job có giao diện phù hợp, muốn giảm công vận hành máy chủ. Phải kiểm tra startup time, giới hạn request, session, concurrency, kết nối tới database và hành vi scale-to-zero.
- **Functions** thuận tiện cho xử lý sự kiện nhỏ, ngắn và độc lập. Không nên chuyển một tiến trình dài hoặc cần trạng thái cục bộ thành function chỉ vì cả ba cloud đều có tên dịch vụ “functions”.

**Ví dụ:** Một API Java phục vụ đơn hàng có phiên kéo dài và truy cập PostgreSQL. Nó có thể chạy trên ECS/EKS, Azure App Service/AKS hoặc Cloud Run/GKE. Tuy nhiên, lựa chọn đúng phụ thuộc vào mức xử lý đồng thời, kết nối database tối đa, cách triển khai private connectivity, yêu cầu session và kiểm thử tải; không thể chỉ dựa vào ngôn ngữ Java hay container image.

## 5. Lưu trữ, cơ sở dữ liệu và phân tích dữ liệu

| Năng lực dữ liệu | AWS | Azure | Google Cloud | Cần kiểm tra trước khi chọn |
| --- | --- | --- | --- | --- |
| Object storage | S3 | Blob Storage | Cloud Storage | API, tier, lifecycle, versioning, event, IAM, egress và metadata khác nhau. |
| Block storage cho VM | EBS | Managed Disks | Persistent Disk, Hyperdisk | IOPS/throughput, snapshot, gắn đĩa và cơ chế chia sẻ. |
| File share được quản lý | EFS, FSx (theo giao thức) | Azure Files, Azure NetApp Files | Filestore, Google Cloud NetApp Volumes | NFS/SMB, ACL, hiệu năng, HA và vùng cung cấp. |
| PostgreSQL được quản lý | RDS for PostgreSQL | Azure Database for PostgreSQL – Flexible Server | Cloud SQL for PostgreSQL | Xác nhận extension, version, HA, replicas, backup, networking và limit. |
| MySQL được quản lý | RDS for MySQL | Azure Database for MySQL – Flexible Server | Cloud SQL for MySQL | Không mặc định giống nhau về replication, PITR và failover. |
| SQL Server được quản lý | RDS for SQL Server | Azure SQL Managed Instance/SQL Database (tùy tính năng) | Cloud SQL for SQL Server | Cần đánh giá khả năng tương thích engine, tính năng SQL Server và license. |
| Quan hệ tối ưu hiệu năng cloud | Aurora | Không có bản sao đồng nhất; chọn Azure SQL/PostgreSQL theo workload | AlloyDB for PostgreSQL (với nhu cầu tương ứng) | Aurora, Azure SQL, AlloyDB khác engine/tầng lưu trữ và tính năng. |
| NoSQL document/key–value | DynamoDB | Azure Cosmos DB for NoSQL | Firestore; Bigtable cho một số mẫu truy cập khác | **Không một-một** về partition key, query, transaction, consistency, API và billing. |
| Cache phân tán | ElastiCache | Azure Managed Redis | Memorystore | Kiểm tra engine/version, Redis compatibility, topology, failover và giá. |
| Data warehouse | Redshift | Azure Synapse Analytics, Microsoft Fabric Warehouse | BigQuery | Khác mô hình compute/storage, SQL dialect, concurrency và chi phí truy vấn. |
| Xử lý luồng/sự kiện dữ liệu | Kinesis Data Streams, Managed Service for Apache Flink | Event Hubs, Stream Analytics | Pub/Sub, Dataflow | Ghép đúng ingestion, stream processing và retention. |
| ETL / điều phối dữ liệu | Glue | Azure Data Factory | Dataflow, Cloud Data Fusion, Workflows (tùy bài toán) | Dịch vụ quản lý pipeline khác engine xử lý phân tán. |
| Sao lưu tập trung / DR | AWS Backup, Elastic Disaster Recovery | Azure Backup, Site Recovery | Backup and DR Service | Mức hỗ trợ từng workload, vùng phục hồi và khả năng test restore khác nhau. |
| Di chuyển database | AWS Database Migration Service | Azure Database Migration Service | Database Migration Service | Loại engine, CDC, DDL, mục tiêu và hạn chế chuyển đổi phải kiểm tra cụ thể. |

### Ba phép đối chiếu cần đi sâu

**1. Quan hệ (RDBMS):** Khi dùng PostgreSQL, việc so RDS for PostgreSQL ↔ Azure Database for PostgreSQL ↔ Cloud SQL for PostgreSQL là hợp lý ở mức engine. Nhưng RPO, HA, bản sao đọc, giới hạn kết nối, phiên bản extension, log replication, quyền superuser, backup và khôi phục theo thời điểm có thể khác. **Amazon Aurora PostgreSQL-compatible** không phải bản sao tương đương tuyệt đối của PostgreSQL managed trên hai nền tảng còn lại.

**2. NoSQL:** DynamoDB nổi bật với mô hình truy cập bằng khóa phân vùng, khóa sắp xếp và secondary index; Cosmos DB for NoSQL có partitioning, query/index và lựa chọn nhất quán riêng; Firestore là document database với cấu trúc query, transaction, index và giới hạn khác. Bigtable là wide-column store phù hợp workload có key range và thông lượng lớn hơn một số trường hợp của DynamoDB, nhưng cũng không tương thích trực tiếp. Cần xem **access pattern thực tế**, không chọn theo từ “NoSQL”.

**3. Cache:** Redis/Valkey được dùng làm cache, session, rate limiting hoặc cấu trúc dữ liệu nhanh. Khi đổi dịch vụ, phải kiểm tra tính tương thích lệnh, clustering, eviction, TTL, persistence, failover, subnet, auth và chi phí. Cache không mặc nhiên là nguồn dữ liệu có thẩm quyền; chọn chính sách tái tạo dữ liệu khi bị mất.

## 6. Messaging, event và tác vụ bất đồng bộ

| Nhu cầu | AWS | Azure | Google Cloud | Nhận xét |
| --- | --- | --- | --- | --- |
| Work queue cho consumer | SQS | Service Bus queues | Cloud Tasks (đặc biệt HTTP task), Pub/Sub cho xử lý subscription | Cách nhận task, ack, retry và điều phối consumer khác nhau. |
| Pub/sub sự kiện | SNS, EventBridge | Service Bus topics, Event Grid | Pub/Sub, Eventarc | Phân biệt thông điệp bền vững, event routing và tích hợp SaaS/cloud. |
| Event bus / routing | EventBridge | Event Grid | Eventarc | Source/target, filter, schema, delivery khác nhau. |
| Streaming log lớn | Kinesis Data Streams, MSK | Event Hubs | Pub/Sub hoặc Managed Service for Apache Kafka (theo nhu cầu) | Khác retention, partition, ordering, consumer và protocol. |
| Job orchestration | Step Functions | Durable Functions, Logic Apps | Workflows | Retry, compensation, callback và timeout là đặc điểm quan trọng. |

### Vì sao queue không tự động tương đương?

Giả sử một hệ thống tạo đơn hàng, phát sự kiện rồi cập nhật tồn kho:

~~~text
Đơn hàng được tạo
    ↓
Outbox trong cùng giao dịch ghi đơn
    ↓
Publisher đọc outbox → Broker
    ↓
Consumer cập nhật tồn kho
    ↓
Xác nhận / retry / dead-letter
~~~

Bất kể dùng SQS, Service Bus hay Pub/Sub, kiến trúc cần trả lời:

- **Bảo đảm chuyển phát:** thông thường phải thiết kế cho khả năng nhận lặp; consumer cần **idempotency key** hoặc cơ chế chống xử lý trùng. Không mặc định có exactly-once cho tác dụng phụ bên ngoài.
- **Thứ tự:** có cần đúng thứ tự cho từng đơn hàng hay chỉ cần xử lý cuối cùng đúng? FIFO, sessions, ordering keys có giới hạn và hành vi riêng.
- **Retry và poison messages:** giới hạn số lần retry, dead-letter queue/subscription, công cụ replay và cảnh báo backlog.
- **Lưu giữ:** thời hạn retention, TTL, visibility lock/ack deadline và cách xử lý consumer chậm.
- **Luồng dữ liệu:** một lệnh phải giao cho một worker hay một sự kiện cần nhiều subscriber? Đây là lựa chọn giữa work queue và pub/sub, không phải chỉ đổi SDK.
- **Truy cập riêng và bảo mật:** service identity, khóa, mã hóa, quyền topic/queue, networking và audit.

Ví dụ: Một dịch vụ xử lý ảnh nhận lệnh HTTP có retry theo lịch có thể phù hợp SQS + worker trên AWS, Service Bus queue + worker trên Azure, hoặc Cloud Tasks + Cloud Run trên Google Cloud. Nếu cùng một sự kiện “ảnh đã tải lên” cần được ba dịch vụ độc lập tiêu thụ, SNS/EventBridge, Event Grid/Service Bus topics, hoặc Pub/Sub/Eventarc đáng xem xét hơn.

## 7. Quan sát, bảo mật và hạ tầng dưới dạng mã

| Năng lực | AWS | Azure | Google Cloud | Nguyên tắc so sánh |
| --- | --- | --- | --- | --- |
| Metrics/logs/alerts | CloudWatch | Azure Monitor, Log Analytics | Cloud Monitoring, Cloud Logging | Xem giới hạn thu thập, cardinality, retention và giá dữ liệu quan sát. |
| Tracing hiệu năng ứng dụng | X-Ray / tích hợp OpenTelemetry | Application Insights | Cloud Trace | Dùng trace context chung để dễ di chuyển và đối chiếu. |
| Nhật ký thao tác quản trị | CloudTrail | Azure Activity Log | Cloud Audit Logs | Phân biệt audit control plane với access/data plane. |
| Quản lý secrets | Secrets Manager, Systems Manager Parameter Store | Key Vault | Secret Manager | Vòng đời secret, rotation, identity và ranh giới truy cập. |
| Quản lý khóa mã hóa | KMS, CloudHSM | Key Vault Keys, Managed HSM | Cloud KMS, Cloud HSM | BYOK/HYOK, key residency và quyền cấp phát khác nhau. |
| Security posture | Security Hub, GuardDuty | Microsoft Defender for Cloud | Security Command Center | Phạm vi nguồn tín hiệu và cách bật/tính phí khác nhau. |
| Governance policy | AWS Config, Organizations policies | Azure Policy | Organization Policy, policy tooling | Cơ chế ngăn chặn, phát hiện và khắc phục vi phạm khác nhau. |
| IaC và khai báo cấu hình | CloudFormation, CDK | ARM templates, Bicep | Infrastructure Manager (Terraform), Config Connector | Terraform là lựa chọn đa cloud, nhưng module/provider khác nhau. |

**OpenTelemetry, Kubernetes và Terraform** có thể giảm công chuyển đổi ở các lớp nhất định, nhưng không xóa hết khác biệt nền tảng. Một deployment Kubernetes có thể tương tự về YAML song vẫn cần triển khai lại ingress, load balancer, CSI storage, workload identity, network policy và autoscaler. Module Terraform dùng cho AWS VPC không thể thay chuỗi “aws” bằng “azurerm” để tạo một VNet tương đương.

Mô hình **shared responsibility** cũng cần được lập lại khi đổi dịch vụ: nhà cung cấp vận hành một phần lớp cơ sở hạ tầng, còn tổ chức vẫn chịu trách nhiệm phân quyền, cấu hình, dữ liệu, bảo mật ứng dụng, tuân thủ và kế hoạch khôi phục theo phạm vi dịch vụ.

## 8. Mẫu kiến trúc tham chiếu: web/API và xử lý đơn hàng

### Yêu cầu giả định

Một nền tảng thương mại điện tử cần:

- Public API qua HTTPS, WAF và giới hạn tốc độ; backend không nhận trực tiếp lưu lượng không qua ingress được duyệt.
- Ứng dụng stateless có thể mở rộng tự động; yêu cầu **99,9% khả dụng hàng tháng** như một mục tiêu minh họa, không phải lời hứa SLA.
- PostgreSQL lưu đơn hàng; object storage chứa tệp; cache hỗ trợ truy vấn thường xuyên.
- Khi đơn được ghi thành công, sự kiện được phát để gửi email và cập nhật hệ thống kho; consumer chịu được xử lý trùng.
- Truy cập dữ liệu qua kết nối riêng, secret có quyền tối thiểu, metrics/logs/traces tập trung, có backup và thử restore.
- Môi trường đầu tiên đặt trong **một region, tận dụng nhiều zone khi dịch vụ hỗ trợ**. Sự cố mất nguyên region cần thiết kế DR bổ sung, không được suy ra từ việc có nhiều zone.

### Sơ đồ logic trung lập nền tảng

~~~mermaid
flowchart TD
    U[Người dùng / ứng dụng đối tác] --> D[DNS + CDN + WAF]
    D --> G[HTTPS ingress / API gateway]
    G --> A[Ứng dụng stateless / autoscaling]
    A --> DB[(Managed PostgreSQL / HA)]
    A --> C[(Managed cache)]
    A --> O[(Object storage)]
    A --> OB[(Transactional outbox)]
    OB --> P[Publisher]
    P --> Q[(Queue / event broker)]
    Q --> W[Background workers]
    W --> X[Email / kho / đối tác]
    A -. telemetry .-> M[Metrics / logs / traces]
    W -. telemetry .-> M
    DB -. backup/restore .-> R[Backup và kế hoạch DR]
~~~

Sơ đồ thể hiện **vai trò**, chưa ấn định hãng. Trong triển khai thực tế, outbox thường là **bảng nằm trong cùng database/giao dịch với đơn hàng** (ở đây tách hình để dễ đọc), từ đó một publisher chuyển sự kiện ra broker. Cách này giảm nguy cơ “đã ghi đơn nhưng không phát được event”, dù vẫn cần deduplication khi publisher gửi lặp.

### Cấu hình tham chiếu theo từng cloud

| Thành phần logic | Phương án AWS | Phương án Azure | Phương án Google Cloud |
| --- | --- | --- | --- |
| DNS, edge, WAF | Route 53 + CloudFront + AWS WAF | Azure DNS + Front Door + WAF | Cloud DNS + External Application Load Balancer/Cloud CDN + Cloud Armor |
| HTTPS ingress | ALB hoặc API Gateway tùy yêu cầu | Application Gateway hoặc API Management tùy yêu cầu | External Application Load Balancer hoặc API Gateway tùy yêu cầu |
| Backend container | ECS/Fargate, hoặc EKS | Container Apps, hoặc AKS | Cloud Run, hoặc GKE |
| PostgreSQL HA | RDS for PostgreSQL Multi-AZ | Azure Database for PostgreSQL Flexible Server với HA phù hợp | Cloud SQL for PostgreSQL với cấu hình HA phù hợp |
| Cache | ElastiCache | Azure Managed Redis | Memorystore |
| Object storage | S3 | Blob Storage | Cloud Storage |
| Công việc nền | SQS + worker | Service Bus queue + worker | Cloud Tasks hoặc Pub/Sub + worker tùy semantics |
| Secrets & workload identity | Secrets Manager + IAM role | Key Vault + Managed Identity/RBAC | Secret Manager + service account/IAM |
| Telemetry | CloudWatch và tracing | Azure Monitor + Application Insights | Cloud Monitoring + Logging + Trace |
| Backup & khôi phục | Backup/snapshot và RDS recovery | Backup/PITR theo dịch vụ | Backup/PITR theo dịch vụ |

**Cần phân biệt các lựa chọn trong cùng một ô:** ALB và API Gateway không thay thế hoàn toàn nhau; App Gateway và API Management giải quyết những lớp trách nhiệm khác nhau. Cloud Tasks phù hợp tác vụ định hướng đích, còn Pub/Sub phù hợp publish–subscribe. Chọn một stack cụ thể sau khi xác định ranh giới và giao thức của ứng dụng.

### Điểm thiết kế không thể bỏ qua

**Độ tin cậy:** Nhiều zone giảm rủi ro lỗi zone, nhưng không bảo đảm chống lỗi region. Cần thiết kế health check, failover, chính sách timeout/retry, độ bền event, backup, restore và đánh giá RTO/RPO thật. Đặt cache là thành phần tùy chọn hay bắt buộc sẽ ảnh hưởng cách fallback.

**Bảo mật:** Đặt database trên mạng riêng, tách quyền đọc/ghi, dùng workload identity thay khóa lưu lâu dài khi có thể, bật mã hóa lưu trữ và truyền tải. Phải kiểm tra ingress, egress, private connectivity và secret rotation ở từng hãng.

**Hiệu năng:** Autoscaling backend có thể làm số kết nối PostgreSQL tăng đột biến; cần giới hạn concurrency, pooling và thử tải. Scaling của worker phải tôn trọng sức chịu tải của dịch vụ downstream và giới hạn API đối tác.

**Chi phí:** So sánh request, giờ vCPU/RAM, DB instance/storage/IO, load balancer, NAT, network egress, logging, backup và môi trường dự phòng. Không suy ra “serverless luôn rẻ hơn”; với tải ổn định cao và cấu hình có mức tối thiểu, kết quả có thể khác.

**Vận hành:** Xác định owner, dashboard SLI/SLO, cảnh báo đủ khả năng hành động, runbook, lịch diễn tập restore và thời hạn giữ log. Việc đổi provider không có nghĩa công việc vận hành biến mất.

## 9. Mẫu đối chiếu khi di chuyển một ứng dụng

Giả sử hệ thống hiện có **EKS + RDS for PostgreSQL + SQS + S3**. Hai phương án đang được xem xét:

| Thành phần hiện tại | Sang Azure | Sang Google Cloud | Việc cần xác minh / thiết kế lại |
| --- | --- | --- | --- |
| EKS | AKS | GKE | Phiên bản Kubernetes, CNI/IP planning, ingress, autoscaler, service account/workload identity, storage class. |
| RDS for PostgreSQL | Azure Database for PostgreSQL Flexible Server | Cloud SQL for PostgreSQL | Extension, PITR, HA, CDC, connection limit, phiên bản, quyền, schema và thời gian cutover. |
| SQS Standard queue | Service Bus queue | Pub/Sub subscription hoặc Cloud Tasks tùy kiểu xử lý | Visibility timeout/lock, ack, retry, delivery semantics, DLQ, idempotency và ordering. |
| S3 | Blob Storage | Cloud Storage | SDK/API, URL ký, metadata, lifecycle, checksum, sự kiện, encryption, transfer và egress. |
| IAM roles cho workload | Managed Identity/Workload Identity | Workload Identity Federation/service accounts | Quy tắc trust, quyền tối thiểu, cấp token, luân chuyển và thu hồi quyền. |
| CloudWatch/CloudTrail | Azure Monitor/Activity Log | Cloud Monitoring/Cloud Audit Logs | Chuẩn hóa log, trace ID, metric label, retention, cảnh báo và chi phí. |

Có thể chia công việc thành năm bước:

1. **Inventory:** Ghi toàn bộ dịch vụ, phiên bản runtime, dependency, lưu lượng vào/ra, số kết nối, dữ liệu, yêu cầu pháp lý, cấu hình network và identity.
2. **Contract mapping:** Đối chiếu yêu cầu chức năng và phi chức năng cho từng thành phần; chỉ định ô nào gần tương đương, ô nào buộc đổi SDK, mô hình lưu trữ hoặc hành vi xử lý sự kiện.
3. **Proof of concept:** Dựng một lát cắt đầu-cuối có ingress, API, DB, queue, IAM và telemetry; thử fault injection đơn giản, load test và kiểm tra dữ liệu.
4. **Data/cutover planning:** Chọn snapshot/CDC hoặc phương án sao chép phù hợp, xác định mốc nhất quán, chỉ một bên có quyền ghi, đối soát, rollback/roll-forward và mức RPO/RTO.
5. **Triển khai và xác minh:** Theo dõi SLO, tính đúng đắn nghiệp vụ, sai lệch chi phí, năng lực vận hành; chỉ ngừng tài nguyên cũ sau khi qua mốc chấp thuận.

Đặc biệt, **giữ nguyên RDBMS engine không đồng nghĩa quá trình migration là lift-and-shift thuần túy**. Những thứ gắn với provider như IAM, network, metrics, backup, secrets, object storage event và message broker vẫn cần thay đổi hoặc cấu hình lại.

## 10. Ma trận quyết định có thể kiểm chứng

Một nhóm kiến trúc nên chấm **phương án triển khai cụ thể**, không chấm thương hiệu cloud chung. Đề xuất tiêu chí minh họa:

| Tiêu chí | Trọng số ví dụ | Chứng cứ |
| --- | ---: | --- |
| Đáp ứng chức năng và tương thích dữ liệu | 25% | Test hợp đồng API, truy vấn, hành vi queue, kết quả nghiệp vụ. |
| Độ tin cậy và khả năng phục hồi | 20% | SLO, fault test, backup restore, RPO/RTO diễn tập. |
| Bảo mật và tuân thủ | 20% | Threat model, IAM, data residency, audit, private connectivity. |
| Hiệu năng và mở rộng | 15% | Load test p95/p99, concurrency, backlog, quota. |
| Tổng chi phí sở hữu | 10% | Ước lượng compute, data, egress, log, license, nhân lực vận hành. |
| Năng lực đội ngũ và khả năng vận hành | 10% | Quy trình CI/CD, runbook, kỹ năng, hỗ trợ, thời gian khắc phục sự cố. |

Chấm mỗi tiêu chí từ **0 đến 5** với tiêu chuẩn công khai, sau đó tính:

~~~text
Điểm phương án = Σ (điểm tiêu chí / 5 × trọng số tiêu chí)
~~~

Điểm tối đa là 100%. **Đừng để điểm tổng cao che khuất điều kiện bắt buộc.** Nếu ứng dụng không đáp ứng yêu cầu chủ quyền dữ liệu hoặc mất giao dịch trái với RPO cho phép, phương án đó **không đạt**, dù rẻ hay dễ vận hành.

Ví dụ: Hai phương án Cloud Run và AKS đều chạy được container; POC cho thấy Cloud Run có thời gian triển khai thấp hơn nhưng mô hình kết nối và concurrency hiện tại vượt giới hạn kết nối cơ sở dữ liệu nếu không thêm pooling. Trong trường hợp đó phải thay đổi kiến trúc kết nối và thử tải lại, thay vì chỉ cộng điểm cho lợi thế vận hành.

## 11. Danh sách kiểm chứng trước khi phê duyệt ánh xạ

Mỗi dòng ánh xạ nên có bằng chứng rõ ràng cho các câu hỏi sau:

1. **API/protocol:** Có tương thích HTTP, TCP, SQL, event schema và client SDK không?
2. **Vùng triển khai:** Dịch vụ/SKU có tại region cần dùng không; dữ liệu lưu ở đâu, backup ở đâu?
3. **Topology HA/DR:** Tự khôi phục khi mất instance, zone và region đến mức nào? RPO/RTO có thể chứng minh không?
4. **Consistency:** Khi ghi xong, dữ liệu được đọc thấy ở đâu, sau bao lâu, thứ tự ra sao?
5. **Giới hạn:** Quota theo tài khoản/project/subscription, số kết nối, kích thước payload, timeout, backlog và throughput?
6. **Network:** Public/private endpoint, DNS, NAT, firewall, egress, kết nối hybrid và private route?
7. **Identity:** Workload xác thực bằng gì, audit ra sao, có secret tĩnh hay không?
8. **Khôi phục:** Có backup, PITR, export, restore, test restore và kế hoạch rollback dữ liệu?
9. **Quan sát:** Có thể theo dõi request, trace, log, metric và đối soát kết quả nghiệp vụ không?
10. **Giá:** Đủ lưu lượng thực tế và đỉnh tải, phí khu vực, mạng, dữ liệu đọc/ghi, vận hành, log và môi trường dự phòng?
11. **Vận hành:** Ai trực, ai nâng cấp, ai cấp quyền, quy trình thay đổi và xử lý sự cố?
12. **Khóa nhà cung cấp:** Dịch vụ có dùng API/tính năng độc quyền không, chi phí và rủi ro khi chuyển lần sau là gì?

Ghi kết quả dưới dạng **Decision Record (ADR)**: bối cảnh, yêu cầu bắt buộc, các phương án, bằng chứng POC, quyết định, rủi ro được chấp nhận và thời điểm đánh giá lại. Điều này giúp nhóm không phải đoán lý do tại sao một dịch vụ được chọn khi hệ thống đã đi vào vận hành.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách tiếp cận đúng |
| --- | --- | --- |
| “Dịch vụ A có ở ba cloud nên tính năng giống nhau.” | Thiếu tính năng về mạng, IAM, retry, backup hoặc quota khi triển khai. | So theo workload contract và kiểm thử từng khả năng quan trọng. |
| “SQS có tên tương tự Pub/Sub nên thay thẳng SDK.” | Xử lý lặp, sai thứ tự, sai mô hình tiêu thụ task/sự kiện. | Thiết kế lại publish, ack, retry, DLQ và idempotency. |
| “DynamoDB chuyển sang Cosmos DB/Firestore chỉ cần copy bảng.” | Sai partitioning, index, query hoặc consistency, làm tăng chi phí và giảm hiệu năng. | Bắt đầu từ mẫu truy cập và mô hình dữ liệu rồi mới chọn sản phẩm. |
| “Managed Kubernetes có nghĩa không phải vận hành cluster.” | Tích lũy lỗi security/network/upgrade và nợ vận hành. | Lập bảng trách nhiệm của nền tảng và đội ứng dụng. |
| “Có hai availability zone là chống được mọi sự cố.” | Không phục hồi được khi cả region gặp sự cố. | Thiết kế DR theo failure domain và đo RTO/RPO thực tế. |
| “Cloud serverless tính phí theo request nên chắc chắn tiết kiệm.” | Bỏ sót traffic thường trực, minimum instances, database, NAT, log, egress. | Mô hình hóa tải thật và so TCO toàn hệ thống. |
| “Terraform giúp mọi cloud trở nên giống nhau.” | Khác biệt network, IAM, LB, DB và event vẫn tồn tại. | Dùng IaC cho khả năng tái tạo, nhưng thiết kế module và policy theo provider. |
| “Chỉ thay VPC bằng VNet là hoàn tất lớp mạng.” | Sai subnet/zone, route, DNS, firewall và private endpoint. | Vẽ lại tuyến kết nối end-to-end và xác thực cô lập. |

## 13. Thực hành: đối chiếu một kiến trúc trên ba nhà cung cấp

Một nền tảng quản lý học tập có API Java, PostgreSQL, kho lưu tệp bài tập, background worker kiểm tra bài, 40.000 người dùng hoạt động hằng ngày và lưu lượng tăng 8 lần vào giờ thi. Yêu cầu nghiệp vụ: dữ liệu chỉ được xử lý tại vùng được phê duyệt, không thất lạc bài đã nộp, API đạt p95 dưới 400 ms ở tải mục tiêu và cần kiểm tra khả năng phục hồi trong 60 phút. Các thông số là **giả định cho bài tập**, không mặc nhiên là SLA.

Hãy tạo ba bản thiết kế AWS, Azure và Google Cloud, mỗi bản có:

1. Sơ đồ gồm DNS/edge, ingress, compute, database, object storage, queue/worker, identity, observability và backup.
2. Bảng dịch vụ đã chọn, mức tương đương (gần/tương đương mục đích/không một-một) và lý do.
3. Mô tả một luồng “nộp bài”: lưu metadata, lưu tệp, ghi outbox, xuất sự kiện, worker chấm bài, retry và chống xử lý trùng.
4. Kế hoạch kiểm thử tải tăng 8 lần; kiểm tra connection pool, backlog queue, I/O database, p95 và giới hạn autoscaling.
5. Kịch bản mất một zone và kịch bản mất region; nêu rõ khi nào cần bổ sung cấu hình DR và tác động của replication tới RPO.
6. Ước lượng TCO theo các nhóm chi phí chính, đồng thời ghi giả định về region, lưu lượng, log retention, egress và nhân sự vận hành.
7. ADR lựa chọn một phương án phù hợp nhất với điều kiện bắt buộc, kết quả POC và rủi ro còn lại.

**Tiêu chí hoàn thành:** không có ánh xạ dịch vụ nào chỉ dựa vào tên; mỗi thành phần phải chứng minh được hợp đồng chức năng, bảo mật, HA/DR, giới hạn kỹ thuật và cách vận hành. Phương án có vẻ “gần tương đương” nhưng không đáp ứng điều kiện bắt buộc phải được thay đổi hoặc loại bỏ.

## 14. Gợi ý đọc tài liệu chính thức

Để kiểm chứng tính năng hiện hành khi triển khai, tra cứu trực tiếp trang tài liệu sản phẩm và tài liệu kiến trúc tham chiếu của nhà cung cấp:

- **AWS:** AWS Architecture Center và AWS Well-Architected Framework trên trang tài liệu chính thức của AWS.
- **Azure:** Azure Architecture Center và Azure Well-Architected Framework trên Microsoft Learn.
- **Google Cloud:** Cloud Architecture Center và Google Cloud Well-Architected Framework trong tài liệu Google Cloud.

Khi tham khảo, luôn ghi ngày kiểm tra, region, SKU/version và liên kết trang mô tả **tính năng cụ thể** vào ADR. Bảng đối chiếu chỉ là điểm bắt đầu của một quyết định kiến trúc có thể kiểm chứng.
