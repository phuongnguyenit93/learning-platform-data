# Lựa chọn nền tảng Azure để chạy ứng dụng Spring Boot

Một ứng dụng **Spring Boot** có thể chạy được trên máy tính cá nhân chỉ bằng lệnh **java -jar**. Nhưng khi triển khai lên Microsoft Azure, đội phát triển cần trả lời nhiều câu hỏi: nên dùng **Azure App Service**, **Azure Container Apps**, **Azure Kubernetes Service (AKS)**, **Azure Functions**, hay **Azure Virtual Machines**? Ứng dụng cần mở rộng tới bao nhiêu bản sao, có thể ngừng khi không có truy cập không, cần truy cập database qua mạng riêng không, và ai chịu trách nhiệm vá lỗi hệ điều hành, cấu hình autoscaling, backup, quan sát và xử lý sự cố?

Lựa chọn nền tảng không đơn giản là tìm dịch vụ hỗ trợ Java. **Cùng một Spring Boot JAR** có thể phù hợp với App Service cho ứng dụng web doanh nghiệp, Container Apps cho microservice chạy bằng container, AKS cho một hệ thống Kubernetes có yêu cầu vận hành phức tạp, hoặc VM khi phải kiểm soát hệ điều hành. Mỗi phương án phân chia trách nhiệm, chi phí và mức tự động hóa khác nhau.

Bài thuộc chương **Spring Boot trên Azure** của module **CLOUD_PROVIDERS_AZURE**. Trong bối cảnh học Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, tính toán, lưu trữ, dữ liệu, giám sát, bảo vệ và chi phí, chúng ta sẽ xây dựng **phương pháp chọn nền tảng Spring Boot dựa trên yêu cầu thực**, thay vì chọn dịch vụ chỉ vì quen tên. Nội dung gồm so sánh, sơ đồ quyết định, mẫu cấu hình, chiến lược triển khai, các tình huống và bài thực hành.

**Phạm vi:** đây là bài lựa chọn và thiết kế kiến trúc, không phải hướng dẫn tự ý tạo tài nguyên production. Tính năng, tên SKU, JDK runtime, giới hạn scale, pricing và lifecycle của các dịch vụ Azure thay đổi theo thời điểm/region/subscription. Kiểm tra tài liệu chính thức và tính sẵn có trước khi chốt phương án. Các số liệu trong ví dụ được ghi rõ là **giả định**, không phải cam kết SLA/giá hay benchmark thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt mô hình vận hành **PaaS, container PaaS, Kubernetes managed, serverless functions và IaaS** khi host Spring Boot.
- Đánh giá năm lựa chọn chính: **App Service, Container Apps, AKS, Functions và Virtual Machines**.
- Giải thích vì sao **Azure Spring Apps** cần được đánh giá theo thông báo vòng đời/retirement trước khi chọn cho hệ thống mới.
- Chọn nền tảng theo **kiểu workload**, yêu cầu HTTP/background jobs, scale, cold start, hệ điều hành và mức tự chủ hạ tầng.
- So sánh **artifact JAR/WAR** và **OCI container image**, cùng hậu quả với CI/CD.
- Phân tích mạng ingress/egress, VNet, private endpoints, managed identity, TLS và secrets.
- Thiết kế health checks, graceful shutdown, resource limits, scaling và connection pooling cho Java.
- Xây dựng quy trình triển khai, rolling/blue-green/canary và rollback phù hợp từng nền tảng.
- Tính sơ bộ **tổng chi phí sở hữu (TCO)** thay vì chỉ so sánh giá compute niêm yết.
- Dùng một **decision matrix có trọng số** để biện luận lựa chọn cho các trường hợp thực tế.
- Viết các kiểm thử và runbook giúp giảm rủi ro khi đưa Spring Boot lên Azure.

## 2. Bắt đầu từ ứng dụng, không bắt đầu từ tên dịch vụ

Trước khi tìm một nút **Create** trên Portal, hãy lập hồ sơ ứng dụng:

| Câu hỏi | Ví dụ câu trả lời | Ảnh hưởng tới lựa chọn |
|---|---|---|
| Ứng dụng phục vụ gì? | REST API nhận 100 req/s | PaaS/container PaaS dễ phù hợp |
| Traffic ổn định không? | Ban ngày cao, đêm gần như 0 | Autoscale/scale-to-zero có giá trị |
| Có request lâu không? | Upload, báo cáo tới vài phút | Timeout, async processing |
| Có state trong process không? | HTTP session trong RAM | Cần externalize session hoặc sticky session có giới hạn |
| Cần native libs/OS control không? | ffmpeg, thư viện đặc thù | Container hoặc VM tùy mức kiểm soát |
| Cần bao nhiêu microservices? | 2, 10 hay 100 services | Complexity/Kubernetes trade-off |
| Đã có đội vận hành K8s? | Không | AKS có thể tạo chi phí tổ chức lớn |
| Data private? | SQL/Redis qua Private Endpoint | VNet ingress/egress và DNS |
| Yêu cầu latency? | P95 dưới 300 ms | Cold start, CPU/RAM, region, DB |
| Có giới hạn chi phí? | Ngân sách cố định cho môi trường lab | Phải tính chi phí cố định và biến đổi |
| SLO/DR? | 99,9% với RTO/RPO cụ thể | Multi-zone/region, runbook, backup |
| Hạn release? | Đội Java nhỏ, deploy mỗi ngày | Managed platform và CI/CD đơn giản |

**Độ phức tạp nghiệp vụ không tự đồng nghĩa phải dùng Kubernetes.** Một monolith lớn vẫn có thể vận hành tốt trên App Service. Ngược lại, một microservice nhỏ có tính chất batch/trigger có thể phù hợp Azure Functions hơn cả App Service và AKS.

## 3. Các mô hình compute Azure cho Spring Boot

~~~mermaid
flowchart TD
    A[Ứng dụng Spring Boot] --> B{Mẫu workload?}
    B -->|HTTP API/web, ít ops| C[Azure App Service]
    B -->|Container services, event-driven autoscale| D[Azure Container Apps]
    B -->|Nền tảng K8s, kiểm soát sâu| E[Azure Kubernetes Service]
    B -->|Tác vụ ngắn theo event| F[Azure Functions Java]
    B -->|OS/kernel/native dependencies đặc thù| G[Azure Virtual Machines]
    C --> H[Azure SQL/PostgreSQL/Cosmos, Key Vault, Monitor]
    D --> H
    E --> H
    F --> H
    G --> H
~~~

### Phân tầng trách nhiệm

| Mô hình | Azure quản lý nhiều hơn | Đội ứng dụng còn phải làm |
|---|---|---|
| **App Service (PaaS)** | Hạ tầng web hosting, nền tảng runtime theo cấu hình, mở rộng plan | Mã Java, dependencies, config, health, scale policy, bảo mật app |
| **Container Apps (managed container app)** | Hạ tầng container, ingress, revisions, nhiều khả năng autoscaling | Docker image, CPU/RAM, secrets/identity, scaling rules, service communication |
| **AKS (managed Kubernetes)** | Kubernetes control plane và các tính năng managed theo cấu hình | Worker nodes/node pools, manifests, ingress, cluster security, upgrades, observability |
| **Functions (FaaS)** | Runtime function triggers/hosting theo plan | Function contract, bindings, dependency/cold start, retries, state |
| **VMs (IaaS)** | Compute host/hypervisor nền tảng Azure | OS patches, Java runtime, load balancer, deployment, HA, security và autoscale |

Managed không có nghĩa **không vận hành**. Đội phát triển vẫn sở hữu độ đúng của ứng dụng, quản lý dữ liệu, ứng xử trước lỗi phụ thuộc, endpoint exposure và chi phí.

## 4. Bảng so sánh nhanh năm lựa chọn

| Tiêu chí | App Service | Container Apps | AKS | Functions | VMs |
|---|---|---|---|---|---|
| Artifact điển hình | JAR/WAR hoặc container | Container image | Container image | Function package/container khi hỗ trợ | JAR/container tùy ý |
| Mức tự quản hạ tầng | Thấp | Thấp–vừa | Vừa–cao | Thấp cho function workload | Cao |
| HTTP API lâu dài | Rất phù hợp | Rất phù hợp | Rất phù hợp | Phù hợp endpoint/function theo giới hạn hosting | Có thể |
| Event/background workers | Có thể, cần cân nhắc hosting/lifecycle | Tốt với jobs/queue scaling | Tốt nếu đã có orchestration | Rất hợp triggers | Có thể |
| Scale-to-zero | Không phải mặc định của dedicated plan | Có theo cấu hình/kiểu scale và plan | Phụ thuộc kiến trúc, không tương đương app-level zero | Có trên plan phù hợp | Không tự có |
| Kubernetes-level control | Không | Trừu tượng hóa | Có | Không | Tự triển khai nếu muốn |
| Blue-green/canary | Slots/traffic routing theo plan/tính năng | Revisions/traffic weights | Deployments/Ingress/service mesh | Slots/versions tùy hosting | Tự xây |
| Mạng riêng/identity | Hỗ trợ theo plan/config | Hỗ trợ theo environment/network config | Hỗ trợ VNet/workload identity | Hỗ trợ theo hosting plan | Toàn quyền cấu hình |
| Gánh nặng vận hành | Thấp | Thấp–vừa | Cao hơn | Thấp–vừa | Cao nhất |
| Phù hợp đội Java ít DevOps | Cao | Cao nếu biết Docker | Cần cân nhắc | Cao cho event code | Thường thấp |

Các ô mô tả **xu hướng**; không thay bảng hỗ trợ theo SKU/region. Ví dụ tính năng deployment slots, private endpoints, loại autoscale hay workload profiles có thể cần plan trả phí hoặc cấu hình cụ thể.

## 5. Azure App Service: điểm bắt đầu cho Spring Boot HTTP API

**Azure App Service** là một nền tảng web PaaS có thể chạy ứng dụng Java theo runtime được hỗ trợ, bao gồm Spring Boot executable JAR trên **Java SE** và các kiểu hosting Java/web application được dịch vụ cung cấp.

~~~text
Client HTTPS
      |
      v
Azure App Service frontend / managed hosting
      |
      v
Spring Boot Java process
      |
      +-- Azure SQL / PostgreSQL
      +-- Key Vault / managed identity
      +-- Application Insights / Azure Monitor
~~~

### Khi nên chọn

- Đội có **một vài REST APIs** hoặc monolith Spring Boot.
- Muốn deploy **JAR trực tiếp**, không bắt buộc tự đóng container.
- Không muốn quản lý Kubernetes cluster và node upgrades.
- Cần CI/CD, app settings, custom domains, TLS, health/diagnostics.
- Traffic tương đối dự đoán được; có khả năng scale plan khi cần.

### Cần nhớ về App Service Plan

App Service app được host trên **App Service Plan** với SKU, compute và các giới hạn tài nguyên liên quan. **Scale up** tăng tài nguyên mỗi instance, **scale out** tăng số instances; nhiều apps dùng chung một plan có thể chia sẻ compute và ảnh hưởng lẫn nhau.

~~~text
App Service Plan: plan-enterprise
    |
    +-- app-support-api
    +-- app-admin-web
    +-- app-reporting

Shared plan compute:
  apps có thể tranh CPU/RAM với nhau
~~~

**Tạo ba Web Apps trên cùng plan không tương đương ba máy chủ độc lập**. Khi sizing, xem tổng tải và isolation cần thiết.

### Những giới hạn cần đánh giá

- App Service Plan có **chi phí nền tảng** tùy SKU ngay cả khi ứng dụng ít requests.
- Không tự biến mọi endpoint xử lý dài thành background job đáng tin.
- Nếu cần native libraries đặc biệt, kiểm tra runtime support hoặc dùng **custom container**.
- Network, deployment slots, autoscale và SLA phụ thuộc plan/feature.
- Cấu hình JVM heap, connection pool, file storage và health checks vẫn do ứng dụng quản lý.

## 6. App Service: JAR, WAR hay custom container?

| Dạng đóng gói | Dùng khi | Điểm cần lưu ý |
|---|---|---|
| **Executable Spring Boot JAR** | Spring Boot khởi chạy embedded server | Chọn Java SE runtime và JDK tương thích |
| **WAR deployment** | Ứng dụng cần servlet container hosting | Xác minh Tomcat/runtime/version |
| **Custom container** | Cần custom native dependencies hoặc runtime được đóng gói | Quản lý Dockerfile, base image patches, registry |

### Executable JAR

~~~bash
# Chạy minh họa trên máy phát triển
./mvnw -B clean verify
java -jar target/support-api.jar
~~~

Lệnh giả định Maven project đã có **finalName=support-api** hoặc build tạo đúng tên JAR. Với Gradle, tên artifact và lệnh khác; không thể đổi đường dẫn khi chưa kiểm tra dự án thật.

### Custom container

Không phải cứ dùng App Service thì không được container hóa. Nếu đội đã có OCI image pipeline, **App Service for Containers** có thể là lựa chọn trung gian giữa trải nghiệm PaaS và yêu cầu image riêng. Tuy nhiên, điều này không tự đem lại revisions/scale-to-zero giống Container Apps.

### Cấu hình JVM

Ứng dụng cần lựa chọn JDK được Azure hosting plan hỗ trợ, đặt resource settings và cung cấp **secrets qua cấu hình/identity**, không hard-code trong JAR. Khi app bị OOM, nguyên nhân có thể ở cả heap, metaspace, direct memory, threads, libraries hoặc tải dữ liệu; đừng chỉ tăng **-Xmx** vượt RAM của plan.

## 7. App Service: triển khai, health checks và deployment slots

Quy trình điển hình:

1. Build và kiểm thử artifact trên CI.
2. Tạo App Service Plan/Web App với Java runtime hoặc custom image phù hợp.
3. Bật managed identity, cấu hình app settings và kết nối database.
4. Deploy vào staging/slot khi plan hỗ trợ.
5. Smoke test **health/readiness, auth, database connectivity**.
6. Swap/route traffic sang production theo chiến lược khả dụng.
7. Quan sát lỗi, p95 latency, memory và log.
8. Rollback code/config an toàn nếu có lỗi.

**Deployment slots** giúp thử và hoán đổi phiên bản khi được hỗ trợ. Tuy nhiên, **slot setting stickiness, connection strings và identities** phải được xác minh; swap sai cấu hình có thể khiến staging chạm database production hoặc ngược lại.

### File system và app instances

Không lưu **session, upload đang xử lý, job state hoặc transactional data** độc quyền trong file hệ thống cục bộ của một instance nếu ứng dụng sẽ scale out/restart. Dùng Azure Blob Storage/database/cache phù hợp và thiết kế idempotency.

### Bài toán long-running job

HTTP request thực hiện báo cáo 30 phút có thể gặp timeout/proxy lifecycle. Một lựa chọn tốt hơn:

~~~text
POST /reports
     |
     v
Spring Boot API
     |
     +-- Create job record
     +-- Enqueue Service Bus message
     |
     v
202 Accepted + jobId
     |
     v
Background worker / Functions / Container Apps Job
     |
     v
Blob report + status API
~~~

**Dùng App Service cho HTTP API không buộc bạn chạy mọi tác vụ ở trong cùng web process.** Tách worker thường tăng khả năng khôi phục và kiểm soát tải.

## 8. Azure Container Apps: container PaaS cho Spring Boot

**Azure Container Apps (ACA)** là nền tảng chạy ứng dụng container có managed environment, ingress/service networking và nhiều khả năng autoscaling theo HTTP và sự kiện thông qua cơ chế được hỗ trợ.

~~~text
Client / Queue
       |
       v
Azure Container Apps environment
       |
       +-- Container app: orders-api
       |       revision v1 / revision v2
       |
       +-- Container app: notifications-worker
       |
       +-- Container Apps Job: nightly-import
       |
       v
Azure SQL / Service Bus / Key Vault
~~~

### Khi nên chọn

- Đội quen Docker/OCI images nhưng **không muốn quản Kubernetes cluster**.
- Ứng dụng có nhiều microservices nhỏ hoặc background workers.
- Lưu lượng biến động, cần **autoscale theo HTTP/queue/event**.
- Muốn **revision-based releases**, chia traffic hoặc revision rollback.
- Có job chạy theo lịch/sự kiện (dùng **Container Apps Jobs** khi phù hợp).
- Cần network/identity/secret management theo môi trường.

### Những thành phần phải hiểu

| Thành phần | Mục đích |
|---|---|
| **Container Apps environment** | Ranh giới quản lý hosting/network của các container apps |
| **Container app** | Định nghĩa ứng dụng: image, ingress, env, scale |
| **Revision** | Phiên bản immutable cấu hình phù hợp với revision semantics |
| **Replica** | Một instance container app chạy ở thời điểm nhất định |
| **Scale rule** | Điều kiện tăng/giảm replicas; HTTP và external triggers tùy support |
| **Job** | Tác vụ hữu hạn/chạy lịch hoặc sự kiện, khác long-running API |
| **Workload profiles / consumption** | Các tùy chọn tài nguyên/cost theo environment/plan |

**Container Apps là managed platform nhưng vẫn dùng container image do bạn duy trì.** Bạn chịu trách nhiệm base image CVEs, build provenance, resource requests, application security, liveness/readiness và service-to-service auth.

## 9. Container Apps: scale-to-zero, cold start và revisions

**Scale-to-zero** có thể giảm số replicas của một app về 0 khi không có nhu cầu và cấu hình hỗ trợ. Đây là lợi thế với workload thưa, nhưng khởi động lại một Spring Boot JVM từ 0 cần thời gian.

~~~text
Không có request/queue events
       |
       v
Replicas: 0
       |
       | Request hoặc event trigger
       v
Provision container + start JVM
       |
       v
Spring context / DB connection pool ready
       |
       v
Phục vụ requests
~~~

### Khi không nên scale-to-zero

- API yêu cầu p95 latency thấp ngay cả sau khoảng thời gian im lặng.
- Cold start của ứng dụng Spring lớn, migration/cache warm-up lâu.
- Có kết nối liên tục/WebSocket hoặc các assumptions về process luôn chạy.
- Traffic/trigger không tương thích hoặc queue consumer đã có chính sách khác.

Giải pháp là **minReplicas lớn hơn 0** hoặc nền tảng/cấu hình capacity phù hợp. Cần tính chi phí trả cho replicas luôn ấm và hạ tầng environment/network đi kèm, không giả định scale-to-zero đồng nghĩa hóa đơn bằng 0.

### Revision releases

Container Apps hỗ trợ revision lifecycle và **traffic splitting** theo chế độ phù hợp. Khi release một image mới:

1. Tạo revision candidate.
2. Smoke test readiness và các external dependencies.
3. Phân bổ một tỷ lệ traffic nếu được hỗ trợ.
4. Theo dõi lỗi và latency.
5. Chuyển traffic hoặc quay về revision cũ.

**Traffic split không đảm bảo database schema tương thích**. Nếu release mới có destructive migration, rollback image sẽ không khôi phục cột đã xóa.

## 10. Container Apps: ingress, target port và giao tiếp nội bộ

Spring Boot thường lắng nghe HTTP trên port **8080** khi tự cấu hình. Trong Container Apps, ingress cần biết **targetPort** tương ứng, còn ứng dụng phải bind trên địa chỉ phù hợp trong container.

~~~text
Container Apps HTTPS endpoint
           |
           | Managed ingress
           v
Container targetPort=8080
           |
           v
Spring Boot process (0.0.0.0:8080)
~~~

Ví dụ cấu hình ứng dụng:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0

spring:
  application:
    name: orders-api

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

**Tên property thực phải phù hợp Spring Boot version** và cách đóng gói. Khi chạy trên App Service, không nên sao chép cứng port 8080 từ Container Apps mà bỏ qua conventions của Java hosting runtime.

### Internal vs external ingress

Một service dành riêng cho API nội bộ nên dùng **internal ingress/private networking** khi môi trường cho phép. Một app public cần TLS/domain, authentication, rate limits và các network protections liên quan. **Chỉ chọn internal ingress không thay thế OAuth/JWT hoặc kiểm tra quyền business.**

### Dapr, KEDA và các thành phần bổ sung

Container Apps có tích hợp/tính năng hỗ trợ **Dapr** và scaling theo event. Đừng bật mọi thành phần chỉ vì có sẵn; mỗi sidecar/trigger thêm learning curve, latency, resource consumption và cấu hình.

## 11. Azure Kubernetes Service: khi cần nền tảng Kubernetes

**AKS** phù hợp khi nhu cầu yêu cầu các khái niệm và ecosystem Kubernetes: Deployments, Services, Ingress/Gateway, Horizontal Pod Autoscaler, node pools, storage classes, network policies, operators và nhiều công cụ platform engineering.

~~~mermaid
flowchart LR
    U[Client] --> I[Ingress / Gateway]
    I --> S[Kubernetes Service]
    S --> P1[Spring Boot Pod A]
    S --> P2[Spring Boot Pod B]
    P1 --> D[(Azure SQL / PostgreSQL)]
    P2 --> D
    K[HPA / KEDA] --> P1
    K --> P2
~~~

### Khi AKS có lợi

- Tổ chức **đã có đội platform/Kubernetes vận hành tốt**.
- Có hàng chục/hàng trăm workloads và cần policy/platform chuẩn hóa.
- Cần **network controls, scheduling, node pools, sidecars, operators** hoặc workloads phức tạp.
- Có yêu cầu GPU/specialized compute khi phù hợp với node/tier.
- Muốn khả năng dùng manifests/Helm/GitOps và ecosystem K8s sâu.
- Có hệ thống vận hành multi-service với SRE/cluster upgrade runbooks.

### Khi AKS là gánh nặng

Với **một REST API đơn giản, hai người phát triển**, AKS có thể đòi quá nhiều công việc:

- Nâng cấp cluster/node images và xử lý compatibility.
- Quản lý ingress controller, certificate, cluster DNS, network policy.
- Vận hành HPA/cluster autoscaler/KEDA, storage và secrets.
- Theo dõi nodes, pods, scheduling, resource pressure và logging.
- RBAC/Kubernetes service accounts/workload identity và supply-chain security.

**Managed control plane không có nghĩa toàn bộ worker nodes/cluster operations được Azure tự quản tới mức ứng dụng không cần SRE.**

## 12. AKS: Pod, resource limits và scaling của Spring Boot

Một Spring Boot pod có:

- **requests/limits** CPU và memory.
- **readiness/liveness/startup probes** tùy khởi động.
- **graceful shutdown** và termination grace period.
- **HPA** scale pods, **cluster autoscaler** scale node pool nếu cần.
- **Pod disruption budgets**, spread/affinity khi HA cần.
- **workload identity** khi truy cập Azure services.

~~~text
Spring Boot Deployment
  replicas: 3
    |
    +-- Pod 1: CPU request 250m, memory request 512Mi
    +-- Pod 2: CPU request 250m, memory request 512Mi
    +-- Pod 3: CPU request 250m, memory request 512Mi
    |
    v
Service -> Ingress -> Clients
~~~

Các requests/limits trên là **giả định minh họa**, không phải kích thước chuẩn cho mọi Spring Boot application. Cần đo JVM **heap, non-heap, thread stacks, native allocations** và application peak trước khi giới hạn.

### JVM và memory limits

Đừng đặt **-Xmx=1GiB** rồi giới hạn container đúng **1GiB**, vì JVM còn dùng metaspace, JIT/code cache, direct buffers, GC, threads và OS overhead. Với container-aware JVM, có thể dùng **-XX:MaxRAMPercentage** phù hợp và chừa headroom; chọn giá trị bằng load tests.

### HPA không tự giải quyết dependency bottleneck

Nếu 10 pods đồng thời mở **50 DB connections mỗi pod**, database có thể nhận 500 connections. Scale từ 10 lên 50 pods có thể làm cạn connection limit. Thiết kế **connection pool, backpressure và caching** trước khi tăng replicas.

## 13. AKS: ví dụ Deployment và Service cho Spring Boot

Một ứng dụng container hóa có thể được triển khai trên AKS bằng **Deployment** và **Service**. Ví dụ YAML minh họa cho một image đã được build và đẩy lên registry được phép truy cập:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: myregistry.azurecr.io/orders-api:1.0.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1024Mi"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - port: 80
      targetPort: 8080
~~~

**Đây là ví dụ khái niệm**, không phải manifest production hoàn chỉnh. Phải thay registry/image bằng image thật, cấu hình image pull/workload identity, securityContext, topology spread, startup probe, ingress, HPA, budgets và database secrets phù hợp.

### Tại sao có readiness và liveness khác nhau?

- **Readiness** nói pod có thể nhận request ngay bây giờ không; nếu chưa kết nối được dependency quan trọng hoặc vẫn đang khởi động, tránh đưa traffic vào pod.
- **Liveness** chỉ nên phát hiện trạng thái process không thể tự phục hồi, không nên liên tục restart mọi pod khi database bên ngoài bị outage.
- **Startup probe** có ích với Spring Boot khởi động lâu, giúp tránh liveness killing quá sớm.

Đường dẫn **/actuator/health/liveness** và **/actuator/health/readiness** cần Spring Boot Actuator và health probes đã bật đúng phiên bản. Đừng chỉ sao chép YAML mà không bật endpoints hoặc xác minh HTTP response.

### Manifest chưa tạo public endpoint

Service **ClusterIP** chỉ mở đường nội bộ cluster. Muốn public HTTPS cần ingress/gateway/controller, domain, certificate, network controls và authentication. Một lỗi thường gặp là đổi Service type sang LoadBalancer rồi vô tình công khai API quản trị.

## 14. AKS: Helm, GitOps và platform engineering

AKS phát huy lợi thế khi tổ chức có quy trình chuẩn hóa:

~~~text
Git: Spring Boot source + Dockerfile
        |
        v
CI build, scan, test, sign image
        |
        v
Azure Container Registry (ACR)
        |
        v
GitOps/Helm manifests with image digest
        |
        v
AKS cluster, multiple namespaces
        |
        v
Monitoring, policy, rollout controller
~~~

### Câu hỏi tổ chức trước khi chọn AKS

- Ai quản lý version/upgrade Kubernetes và node images?
- Có cluster/team isolation, resource quota và namespace policy chưa?
- Ai quản lý ingress controller, private DNS và TLS certificates?
- Có GitOps, image scanning, secret management và observability chung?
- Có SRE trực cảnh báo, xử lý scheduling/eviction/cluster outage?
- Một cluster dành riêng cho ứng dụng hay chia sẻ nhiều workloads?

Nếu tổ chức đã vận hành AKS làm nền tảng dùng chung, chi phí **cận biên** để thêm một Spring Boot service có thể thấp hơn mở một nền tảng mới. Ngược lại, tạo một cluster riêng cho API nhỏ có thể làm tăng TCO, thời gian khắc phục và gánh nặng bảo trì.

## 15. Azure Functions: cho những chức năng Java theo sự kiện

**Azure Functions** là một lựa chọn phù hợp nếu Spring Boot application có phần xử lý **event-driven**, ví dụ khi tệp mới xuất hiện, queue nhận message, timer tới lịch hoặc một HTTP endpoint gọn cần gọi code Java.

~~~text
Azure Service Bus queue
          |
          v
Azure Functions Java
          |
          +-- Validate message
          +-- Execute application function
          +-- Write result to database
          |
          v
Complete/retry/dead-letter according to binding/host settings
~~~

### Không nhầm Spring Boot web app và Java Function

Một ứng dụng Spring Boot với embedded Tomcat và hàng chục REST controllers **không tự biến thành Function App chỉ bằng việc deploy JAR**. Azure Functions có **programming model, triggers/bindings, host lifecycle** và những integration libraries riêng. Có các cách tích hợp Java/Spring Cloud Function vào Azure Functions theo phiên bản được hỗ trợ, nhưng thường cần **adapter/refactor**.

### Khi chọn Functions

- Workload chạy theo **event** với thời lượng/đặc tính phù hợp hosting plan.
- Xử lý Service Bus, Event Hubs, timer hoặc một số HTTP endpoints.
- Muốn tách background processing khỏi Spring Boot API.
- Có thể chấp nhận cold start trên plan tương ứng hoặc chọn hosting plan có khả năng luôn ấm.
- Không cần duy trì một JVM web server liên tục cho toàn bộ ứng dụng.

### Khi không nên mặc định chọn

- Ứng dụng monolith Spring MVC lớn, stateful và yêu cầu web-server lifecycle dài.
- HTTP requests xử lý hàng chục phút mà không muốn chuyển async.
- Có long-lived connections hoặc unmanaged background threads.
- Ràng buộc timeout/cold start/hosting plan trái với SLO.

**Functions không đồng nghĩa luôn miễn phí hoặc tự động scale vô hạn.** Chi phí và tính năng khác nhau giữa consumption-based plans, Flex Consumption/Premium và dedicated hosting theo khả năng hiện hành.

## 16. Azure Functions: ví dụ Java event handler

Một function Java đọc Service Bus message có thể biểu diễn bằng:

~~~java
package com.example.orders;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger;

public class OrderEventsFunction {

    @FunctionName("processOrderEvent")
    public void handle(
        @ServiceBusQueueTrigger(
            name = "message",
            queueName = "order-events",
            connection = "SERVICE_BUS_CONNECTION"
        ) String message,
        ExecutionContext context) {

        // Parse, validate, authorize where required, process idempotently.
        // Do not log sensitive message contents.
        context.getLogger().info("Order event received");
    }
}
~~~

Đây là **skeleton** dựa trên Java Azure Functions SDK/annotations. Cần project/plugin, Maven dependency **azure-functions-java-library**, binding extension tương thích, host settings và credential/identity phù hợp. Tên **SERVICE_BUS_CONNECTION** là tên cấu hình binding, không phải giá trị connection string trong source. Production phải xử lý duplicate, retries, dead-letter, error mapping và tài nguyên dùng chung.

### Kết hợp với App Service hoặc Container Apps

Thường không cần chọn **một nền tảng duy nhất**:

~~~text
Spring Boot API trên App Service
         |
         v
Service Bus queue
         |
         v
Azure Functions Java
         |
         v
Database / external business integration
~~~

Lựa chọn linh hoạt này có thể đơn giản hơn chạy toàn bộ hệ thống trên AKS khi chỉ một vài chức năng thật sự cần event triggers.

## 17. Azure Virtual Machines: kiểm soát hệ điều hành

**Azure Virtual Machines** phù hợp nếu ứng dụng phải kiểm soát hệ điều hành, agent, thư viện native, network stack, môi trường Java đặc thù hoặc có yêu cầu lift-and-shift chưa thể container hóa.

~~~text
Azure Load Balancer / Application Gateway
                 |
                 v
         Virtual Machine Scale Set
                 |
            +----+----+
            |         |
          VM A      VM B
       Java/Spring Java/Spring
            |         |
            +----+----+
                 |
                 v
         Database / storage
~~~

### Ai quản lý gì?

Đội vận hành chịu trách nhiệm đáng kể:

- OS images, patching, security baselines và endpoint protection.
- Cài đặt/cập nhật JDK, process supervisor, startup scripts.
- Load balancer, certificates, network security groups, routing.
- Scale sets, availability zones, backup và disaster recovery.
- Log shipping, disk capacity, monitoring agent và incident response.

### Khi VM hợp lý

- Có phần mềm legacy/agent native chưa chạy được trên PaaS/container.
- Cần kernel/OS/custom driver hoặc filesystem model đặc thù.
- Có ràng buộc cấp phép/hạ tầng cụ thể cần IaaS.
- Đội có automation/patch management tốt và biết rõ TCO.

**VM là lựa chọn có chủ đích, không phải mặc định "đảm bảo chạy"**. Nếu chỉ cần chạy JAR thông thường, thường có các phương án ít vận hành hơn.

### Một VM đơn không phải HA

Nếu tất cả nằm trên **một VM** và VM/zone lỗi, ứng dụng ngừng. Muốn availability, phải thiết kế nhiều instances, load balancing, health checks và data-layer HA; không chỉ chụp snapshot OS disk rồi gọi đó là kiến trúc chịu lỗi.

## 18. Azure Spring Apps: lưu ý vòng đời dịch vụ

**Azure Spring Apps** (trước đây Azure Spring Cloud) từng cung cấp trải nghiệm PaaS chuyên cho ứng dụng Spring. Tuy nhiên, dịch vụ đã được Microsoft công bố **lộ trình nghỉ hưu/retirement**. Với kiến trúc mới, cần **kiểm tra thông báo retirement, thời hạn hỗ trợ, điều kiện tạo mới và hướng dẫn migration hiện hành** trước khi cân nhắc.

### Cách ra quyết định

| Tình huống | Hướng xử lý |
|---|---|
| Xây Spring Boot service **mới** | Ưu tiên đánh giá App Service, Container Apps hoặc AKS theo yêu cầu |
| Đang chạy Spring Apps | Lập inventory, dependency, network, config, service binding và kế hoạch migration |
| Muốn dùng built-in Spring conveniences | Xem khả năng thay thế bằng cấu hình app/platform, config services và observability |
| Hợp đồng yêu cầu nền tảng được hỗ trợ lâu dài | Rà soát lifecycle official và roadmap, không chọn dựa trên bài viết cũ |

### Không chuyển "nguyên xi" mà bỏ qua chức năng

Một hệ thống cũ có thể phụ thuộc vào **config management, service discovery, JVM metrics, managed certificates, build/deploy conventions và autoscale** của Spring Apps. Di chuyển sang App Service/Container Apps/AKS đòi ánh xạ từng tính năng, chạy regression tests và chọn mô hình vận hành mới.

Không ghi một ngày retirement cụ thể vào kế hoạch migration nếu chưa đối chiếu thông báo chính thức mới nhất của Microsoft và hợp đồng tổ chức.

## 19. Các dịch vụ bổ sung: cái gì chạy Spring Boot, cái gì không?

Không phải dịch vụ Azure có thể nhận Java code đều là một nền tảng web hosting trực tiếp:

| Dịch vụ | Có phải host chính cho Spring Boot API? | Vai trò |
|---|---|---|
| **Azure Container Registry** | Không | Lưu OCI images, truy xuất build artifact |
| **Azure API Management** | Không | Gateway, auth policies, quotas và API exposure |
| **Azure Front Door** | Không | Global entry, routing, CDN/WAF theo cấu hình |
| **Azure Application Gateway** | Không | Layer-7 routing/WAF trong kiến trúc mạng |
| **Azure Service Bus** | Không | Queue/topic giữa microservices |
| **Azure Cache for Redis** | Không | Caching/session/dữ liệu tạm theo model phù hợp |
| **Azure SQL/PostgreSQL/Cosmos DB** | Không | Data stores |
| **Azure Key Vault** | Không | Quản lý secrets/certificates/keys |
| **Azure Monitor/Application Insights** | Không | Metrics, logs, traces |
| **Azure Static Web Apps** | Không phải mặc định cho full Spring Boot web server | Hosting frontend và API integration theo giới hạn |
| **Azure Container Instances** | Có thể chạy container nhưng không phải mặc định cho API production phức tạp | One-off jobs, isolated runs, simple containers |

**Đừng chọn API Management hoặc Azure Front Door thay cho compute**: chúng đứng phía trước backend, không chạy tiến trình Spring Boot.

## 20. Workload HTTP đồng bộ và background jobs

Nhiều hệ thống Spring Boot vừa có HTTP controllers vừa có **@Scheduled**, Kafka/Service Bus listeners hoặc batch jobs. Chạy mọi thứ trong cùng process khiến việc scale dễ gây hiệu ứng ngoài ý muốn.

### Tình huống

~~~text
Spring Boot orders-api
  +-- GET /orders
  +-- POST /orders
  +-- @Scheduled sendDailyInvoice()
~~~

Nếu scale từ 1 lên 5 replicas, **@Scheduled** có thể chạy 5 lần trừ khi có distributed lock/leader election hoặc scheduler bảo đảm exclusivity. Ngay cả khi có lock, chia chung CPU/RAM với API cũng có thể tạo latency spikes.

### Thiết kế tách workload

~~~text
Orders API:
  App Service hoặc Container App
  HTTP ingress + auth + database
          |
          v
  Service Bus / durable job record
          |
          v
Worker:
  Azure Function hoặc Container Apps Job / service
          |
          v
Database / Blob Storage / email
~~~

**Scale HTTP theo requests không đồng nghĩa scale workers theo backlog.** Chọn trigger và scale metric của từng workload.

### Khi chọn Functions hay Container Apps Job?

- **Functions:** tính năng trigger/binding phong phú, các handlers tương đối ngắn và phù hợp hosting model.
- **Container Apps Jobs:** cần chạy một container hữu hạn theo lịch/sự kiện/manual, thuận tiện khi job đã có Docker image và lifecycle rõ.
- **AKS CronJob/Job:** hợp lý nếu toàn bộ platform đã vận hành trên AKS và có chính sách scheduling/quota/monitoring.

Không mặc định jobs kéo dài hàng giờ có thể chạy trong mọi plan của Functions; kiểm tra **timeout, hosting plan, checkpoint** và idempotency.

## 21. Chọn artifact: JAR, OCI image và build supply chain

Lựa chọn nền tảng kéo theo cách đóng gói:

~~~mermaid
flowchart LR
    S[Git repository] --> B[Build Maven/Gradle + tests]
    B --> J[Spring Boot executable JAR]
    J --> A[App Service Java SE]
    J --> I[OCI image build]
    I --> R[Azure Container Registry]
    R --> C[Container Apps]
    R --> K[AKS]
    R --> P[App Service custom container]
~~~

### JAR deployment có lợi gì?

- Không bắt buộc đội biết Docker nếu chọn App Service Java SE.
- Managed runtime image/Java hosting theo support matrix của dịch vụ.
- Pipeline đơn giản cho ứng dụng web thông thường.

### OCI image có lợi gì?

- Đóng gói JDK/runtime, native libraries và startup behavior theo bản build.
- Dùng cùng image đã kiểm thử trên Container Apps, AKS hoặc container-enabled hosting.
- Thuận lợi cho image scanning, signing, digest pinning và reproducibility.

### OCI image có thêm trách nhiệm

- Theo dõi CVEs của base image và dependencies.
- Không nhúng secrets, SSH keys hoặc dữ liệu tenant vào image layers.
- Chạy non-root khi phù hợp; dùng minimal runtime image.
- Ghi image digest, SBOM và provenance khi có yêu cầu.
- Chọn đúng CPU architecture/OS và JDK compatibility.

**Container hóa không tự làm ứng dụng cloud-native**. Một Spring Boot container vẫn có thể lưu state cục bộ, tạo session không thể scale, giữ static secret hoặc crash khi database tạm lỗi.

## 22. Dockerfile mẫu cho Spring Boot

Giả sử dự án Maven tạo **target/support-api.jar** sau kiểm thử:

~~~dockerfile
# Ví dụ dùng JDK 21; thay bằng bản được ứng dụng và platform hỗ trợ.
FROM eclipse-temurin:21-jre
WORKDIR /app

# Giả định artifact đã được CI build và test trước khi tạo image.
COPY target/support-api.jar /app/application.jar

# Dùng non-root UID; quyền file/volume phải tương thích.
USER 10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

### Build và thử local

~~~bash
./mvnw -B clean verify
docker build -t support-api:lab .
docker run --rm -p 8080:8080 support-api:lab
curl --fail http://localhost:8080/actuator/health
~~~

**Đây là ví dụ thực hành**, không phải khẳng định một project hiện hữu có Maven wrapper, JAR tên support-api.jar, Actuator dependency hay health endpoint. Phải cấu hình **finalName**, build plugins, Actuator và environment cho đúng dự án.

### Điểm vận hành phải kiểm tra

1. Dùng base image đã được cập nhật và pin phiên bản/digest theo chính sách.
2. Build JAR ở CI, chạy unit/integration tests và scan trước khi push image.
3. Không đặt database passwords, connection strings hay secrets qua **ENV** cứng trong Dockerfile.
4. Kiểm tra **UID 10001** có quyền đọc JAR và ghi vào thư mục tạm nếu thư viện cần.
5. Tính RAM cho heap + non-heap; **65% là số minh họa**, không phải giá trị tối ưu phổ quát.
6. Expose 8080 không tự mở Internet: còn cần Container Apps ingress/AKS Service/Ingress tương ứng.
7. Thêm graceful shutdown và readiness probe trước khi đưa traffic.

Nếu dùng distroless image hoặc JDK major version khác, cần kiểm tra tính tương thích thư viện/native và cách debug production.

## 23. Runtime versions và compatibility matrix

Spring Boot chạy trên JVM, nhưng không phải mọi kết hợp **JDK + Spring Boot + Azure runtime + SDK** đều được hỗ trợ. Trước khi chọn nền tảng:

| Hạng mục | Cần xác nhận |
|---|---|
| **Java major version** | Dự án cần Java 17, 21 hoặc bản được hỗ trợ |
| **Spring Boot version** | Tương thích JDK, Spring Framework và dependencies |
| **Container base image** | Hỗ trợ architecture, CA certificates, tzdata, native libs |
| **Azure hosting runtime** | JDK/runtime stack thực có ở App Service/Functions |
| **Azure SDK BOM** | Các thư viện identity, storage, Service Bus có phiên bản nhất quán |
| **Startup commands** | JAR path, JVM flags, port và graceful shutdown |
| **Build pipeline** | Maven/Gradle toolchain, reproducible builds, tests |
| **Security** | CVEs/runtime patches, SBOM, container scan, EOL policy |

### Rủi ro khi nâng phiên bản

Một app build Java 21 bytecode không chạy được trên runtime Java 17. Spring Boot major upgrade có thể đổi package **javax → jakarta**, config keys, security behavior hoặc Actuator paths. Chọn platform phải cho phép nâng cấp có kiểm thử thay vì giữ một JDK đã hết hỗ trợ quá lâu.

### Khuyến nghị

Với ứng dụng mới, chọn phiên bản **LTS JDK và Spring Boot đang được hỗ trợ tại thời điểm triển khai**, kiểm tra Azure support matrix và yêu cầu dependencies. Không khóa hard-code phiên bản runtime trong tài liệu kiến trúc mà không có lịch xem lại.

## 24. Decision tree thực dụng

~~~text
Bạn có Spring Boot application
  |
  +-- Chủ yếu là event handlers/jobs ngắn?
  |      |
  |      +-- Có: xét Azure Functions Java
  |             hoặc Container Apps Jobs nếu job đóng container
  |
  +-- HTTP API/web server liên tục?
         |
         +-- Muốn deploy JAR nhanh, ít vận hành?
         |      -> App Service
         |
         +-- Đã container hóa, cần revisions/event autoscale?
         |      -> Container Apps
         |
         +-- Cần Kubernetes-level APIs, operators, node pools?
         |      -> AKS, nếu có năng lực platform operations
         |
         +-- Phải toàn quyền OS/native kernel/legacy runtime?
                -> VM/VM Scale Sets
~~~

**Đây không phải thuật toán tự động thay người thiết kế.** Ví dụ tổ chức có AKS shared cluster chuẩn hóa có thể chọn AKS cho API nhỏ; một app containerized vẫn có thể chạy tốt trên App Service for Containers. Cần đối chiếu tất cả ràng buộc bắt buộc trước khi dùng thứ tự ưu tiên.

### Nếu có hai đáp án ngang nhau?

Ưu tiên phương án **ít gánh nặng vận hành hơn mà vẫn đáp ứng SLO/security/network**, hoặc phương án phù hợp với nền tảng đội ngũ đã vận hành thành thạo. Tránh tạo một platform mới chỉ vì một tính năng hấp dẫn chưa có use case.

## 25. Ma trận chấm điểm có trọng số

Decision tree hữu ích để loại bớt phương án, nhưng **không thay thế các ràng buộc bắt buộc**. Trước khi chấm điểm, loại ngay nền tảng không đáp ứng yêu cầu pháp lý, data residency, bảo mật mạng, native dependency hoặc mức hỗ trợ sản phẩm.

Với các phương án còn lại, chấm **1 = rất không phù hợp, 5 = rất phù hợp** theo các tiêu chí có trọng số.

### Ví dụ: đội 4 người, một Spring Boot REST API, traffic ổn định

| Tiêu chí | Trọng số | App Service | Container Apps | AKS | Functions | VM |
|---|---:|---:|---:|---:|---:|---:|
| Ít gánh nặng vận hành | 30% | 5 | 4 | 2 | 3 | 1 |
| Phù hợp HTTP API liên tục | 25% | 4 | 5 | 5 | 2 | 4 |
| Phù hợp ngân sách dự kiến | 20% | 4 | 4 | 2 | 5 | 2 |
| Hỗ trợ mạng/bảo mật cần thiết | 15% | 4 | 4 | 5 | 3 | 5 |
| Đội ngũ đã có kỹ năng | 10% | 5 | 4 | 2 | 4 | 2 |
| **Tổng điểm minh họa / 5** | **100%** | **4,40** | **4,25** | **3,20** | **3,25** | **2,65** |

Cách tính cho App Service:

~~~text
0,30 × 5 + 0,25 × 4 + 0,20 × 4 + 0,15 × 4 + 0,10 × 5
= 1,50 + 1,00 + 0,80 + 0,60 + 0,50
= 4,40 / 5,00
~~~

**Tất cả điểm số là giả định do nhóm giả lập tự chấm**, không phải xếp hạng khách quan của Azure. Nếu tổ chức đã có AKS platform dùng chung hoặc yêu cầu native network policies, trọng số/kỹ năng và chi phí thay đổi; AKS có thể thắng.

### Quy trình dùng bảng đúng

1. Ghi các **must-have**: compliance, private access, latency SLO, loại workload.
2. Loại phương án không đáp ứng được must-have.
3. Thống nhất trọng số với nhóm bảo mật, vận hành, sản phẩm và tài chính.
4. Chấm từng điểm với bằng chứng/PoC, không chấm theo cảm tính.
5. Chạy **sensitivity analysis**: tăng trọng số cost hoặc ops thì kết quả đổi không?
6. Chọn hai phương án tốt nhất để thử benchmark và cost estimation.
7. Ghi **Architecture Decision Record (ADR)**, điều kiện xem xét lại.

**Điểm cao không khắc phục vi phạm bắt buộc.** Một nền tảng đạt 4,8/5 nhưng không đáp ứng data residency vẫn không được chọn.

## 26. Networking: phân biệt inbound và outbound

Spring Boot có ít nhất ba luồng mạng:

~~~text
Client -> HTTPS -> Java application
                         |
                         +-- Azure SQL / PostgreSQL
                         +-- Azure Service Bus
                         +-- Key Vault
                         +-- Azure Storage
                         +-- External payment API
~~~

### Inbound

Ai có thể gọi ứng dụng?

- Public Internet qua HTTPS và gateway/WAF khi cần.
- Chỉ mạng nội bộ/VNet/Private Endpoint.
- Một frontend khác trong cùng platform.
- Một Azure service callback cần endpoint được xác thực.

### Outbound

Ứng dụng cần đi tới những đích nào?

- Database private IP/Private Endpoint với đúng DNS.
- Managed services bằng data-plane identity.
- External API qua NAT/firewall/proxy nếu có allowlist.
- Identity provider để lấy token khi cần.

| Nền tảng | Cần phân biệt |
|---|---|
| **App Service** | **VNet Integration** phục vụ outbound tới VNet; **Private Endpoint** phục vụ private inbound theo tính năng |
| **Container Apps** | Environment networking, internal/external ingress, VNet và outbound controls |
| **AKS** | Cluster/node/pod network, ingress controller, Network Policy và egress |
| **Functions** | VNet/private access tùy hosting plan và mô hình trigger |
| **VM** | VNet subnet, NSG, load balancer, firewall/NAT và DNS |

**App Service VNet Integration không tự biến public web app thành private app.** Nếu cần chặn inbound Internet, phải cấu hình inbound access restrictions/private endpoint theo topology đã phê duyệt.

### DNS là phần quan trọng của Private Link

Một ứng dụng có thể resolve **mydb.postgres.database.azure.com** hoặc hostname database khác thành địa chỉ public dù đã tạo Private Endpoint. Cần kiểm tra:

- Private DNS zone/link/forwarder.
- Kết quả DNS từ **đúng app instance/pod**.
- Route/firewall/port tới dịch vụ.
- TLS hostname verification và certificate.
- Data-plane permissions.

**Không hard-code private IP trong Java** để bỏ qua lỗi DNS. Nó làm TLS và khả năng thay đổi dịch vụ kém an toàn.

## 27. Secrets và managed identity

Không đặt database password, Azure Storage connection string, Service Bus key hoặc token bí mật trong **application.properties** đã commit hoặc Docker image.

### Một mẫu kiến trúc

~~~text
Spring Boot workload
       |
       | Managed identity / Workload identity
       v
Microsoft Entra ID
       |
       +-- Access to Key Vault (nếu cần secret)
       +-- Access to Storage/Service Bus data plane
       +-- Access to Azure SQL/PostgreSQL theo capability
       |
       v
Authorized Azure resources
~~~

| Platform | Cơ chế danh tính thường xem xét |
|---|---|
| **App Service** | System-assigned hoặc user-assigned managed identity |
| **Container Apps** | Managed identity gắn với container app theo tính năng |
| **AKS** | Microsoft Entra Workload ID cho pod/service account; cluster identity khác workload identity |
| **Functions** | Managed identity của Function App theo hosting |
| **VM** | Managed identity của VM/VMSS |

### Hai sai lầm phổ biến

1. **Bật managed identity nhưng chưa gán data-plane role:** request vẫn 403.
2. **Cấp Azure Contributor trên resource group rồi cho rằng app có quyền query dữ liệu:** control-plane RBAC khác data-plane authorization.

Hãy cấp đúng scope và **least privilege**, kiểm thử với workload identity thực, không lấy credential của developer Owner để che vấn đề.

### Khi vẫn cần secret

Một số third-party APIs, database providers hoặc hệ thống legacy vẫn dùng password/API key. Dùng **Azure Key Vault**, secret references/app settings và rotation plan; hạn chế quyền đọc trong Key Vault. Không đưa raw secrets vào error logs, application telemetry hoặc support tickets.

### Spring Cloud Azure

Các thư viện **Spring Cloud Azure** có thể giúp tích hợp Azure identity, Service Bus, Storage, Key Vault theo versions phù hợp với Spring Boot. Cần pin **Spring Boot–Spring Cloud Azure compatibility matrix**, không tự giả định mọi version mới nhất kết hợp được.

## 28. Configuration: môi trường và feature flags

Tách cấu hình khỏi artifact để deploy cùng JAR/image vào dev/staging/prod:

~~~yaml
# Cấu hình minh họa, không chứa credentials thật.
spring:
  application:
    name: orders-api
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các giá trị khác được inject qua app settings/environment variables hoặc secret references:

~~~text
SPRING_PROFILES_ACTIVE=staging
DATABASE_HOST=<STAGING_DATABASE_HOST>
SERVICE_BUS_NAMESPACE=<STAGING_NAMESPACE>
SPRING_DATASOURCE_PASSWORD=<INJECTED_SECRET_IF_REQUIRED>
APP_FEATURE_NEW_CHECKOUT=false
~~~

**Environment variables không tự có mã hóa end-to-end hay quyền truy cập hoàn hảo**. Ai có quyền xem cấu hình container/pod/process có thể thấy một số giá trị; ưu tiên identity thay static secrets và phân quyền platform.

### Không nhầm environment với Spring profile

**dev/staging/prod** là các môi trường hạ tầng có thể khác subscription, resource group, network và database. **Spring profile** chỉ là một cách chọn cấu hình trong ứng dụng. Đặt profile=prod không tự khiến identity, database hoặc storage trỏ production đúng; phải kiểm tra deployment config và policy.

### Feature flags

Sử dụng feature flags cho release theo từng tenant hoặc canary có thể giúp giảm rollback toàn bộ JAR. Tuy nhiên phải thiết kế mặc định an toàn và không để những tính năng có rủi ro dữ liệu chỉ được bảo vệ bằng một flag client-side.

## 29. Database: không để tầng compute quyết định cấu trúc dữ liệu

Ứng dụng Spring Boot có thể sử dụng:

- **Azure SQL Database** khi cần relational model/T-SQL theo ứng dụng.
- **Azure Database for PostgreSQL – Flexible Server** cho PostgreSQL/JPA/JDBC.
- **Azure Cosmos DB** cho NoSQL document workloads có partitioning và RU model.
- **Azure Blob Storage** cho tệp lớn, ảnh, exports.
- **Azure Cache for Redis/Redis service phù hợp** cho cache/session/lock theo support lifecycle.

Chọn database theo **data model, consistency, transactions, HA, cost**, không vì AKS/App Service bắt buộc một DB nhất định.

### Pooling và autoscale

Giả sử:

~~~text
Một instance Spring Boot:
  HikariCP maximumPoolSize = 20

10 replicas:
  Tối đa 200 DB connections trong mô hình đơn giản

40 replicas:
  Tối đa 800 DB connections
~~~

Đây là **phép nhân giả định**, chưa tính admin connections, retries, maintenance và pool behavior. Hãy kiểm tra database connection limits, saturation và transaction time. Một scale rule theo CPU/request có thể làm tăng connection demand, khiến database quá tải trước khi ứng dụng hết CPU.

### Session state và cache

Tránh dựa vào **HTTP session chỉ trong RAM** nếu có nhiều instances hoặc rolling updates. Dùng stateless tokens khi hợp lý, hoặc distributed session store được thiết kế đúng. Cache không thay database nguồn; cần TTL, invalidation, stampede protection và tenant isolation.

## 30. Health checks, probes và JVM startup

Spring Boot Actuator cung cấp health endpoints khi thêm dependency và cấu hình:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

### Các tầng kiểm tra

| Check | Mục đích | Tránh |
|---|---|---|
| **Startup** | Ứng dụng đã khởi động đủ để đánh giá liveness | Restart JVM trong lúc warm-up hợp lệ |
| **Liveness** | Process có bị kẹt không thể tự phục hồi? | Restart khi database tạm ngừng |
| **Readiness** | Instance có sẵn sàng nhận traffic? | Gửi request vào pod đang migrate/initialize |
| **Business synthetic check** | Giao dịch thật có hoạt động? | Coi HTTP 200 của /health là đủ cho mọi chức năng |

### Startup có thể dài vì sao?

- Spring context và dependency injection lớn.
- JIT warm-up hoặc cache init.
- Database migration/schema validation.
- DNS/network/Key Vault fetch chậm.
- Large classpath hoặc native library loading.

Chọn **startupProbe/readiness thresholds** phù hợp thời gian khởi động đã đo. Đừng dùng liveness probe gọi tất cả downstream services; outage của SQL có thể khiến mọi pod restart liên tục và kéo dài sự cố.

### Graceful shutdown

Khi rolling deploy:

1. Ngừng nhận request mới.
2. Hoàn tất những requests đang xử lý trong thời hạn.
3. Dừng listeners/threads và đóng connections.
4. Đảm bảo background jobs có checkpoint/retry state.

Spring Boot có **server.shutdown=graceful** và phase timeout theo phiên bản; platform cũng cần termination grace period phù hợp. Không hứa mọi request được hoàn tất nếu VM/pod bị force-kill, node mất điện hoặc thời hạn hết.

## 31. Autoscaling: đúng metric cho đúng workload

Không phải mọi service scale theo cùng cách:

| Workload | Metric cần cân nhắc |
|---|---|
| REST API | Request rate/concurrency, CPU, latency, memory |
| Service Bus worker | Queue depth, oldest message age, execution duration |
| Event Hubs processor | Consumer lag, partition utilization, time-to-process |
| Batch scheduler | Job queue/backlog và deadline |
| Memory-heavy analytics | Memory, GC pause, heap pressure |
| WebSocket/streaming | Connections/concurrency và network I/O |

### Ví dụ scale sai

Một worker Service Bus ít CPU vì đang đợi database chậm. Autoscale dựa trên CPU sẽ không tăng replicas, hoặc tăng replicas cũng có thể làm DB tệ hơn. Metric tốt hơn có thể là backlog/age, nhưng vẫn phải có **max concurrency** để không gây sập dependency.

### Scale-out không tự có HA dữ liệu

Thêm 10 Spring Boot instances trên AKS/App Service không làm một PostgreSQL single-instance trở nên multi-zone. Compute scale và data-tier HA/DR là hai nhiệm vụ độc lập.

### Cold start và min instances

Với Container Apps/Functions, scale-to-zero hoặc môi trường serverless có thể xuất hiện cold start. Với App Service/AKS, process vẫn có startup time khi deploy/replace. Đo **time-to-readiness** và dùng pre-warming/min replicas khi SLO cần phản hồi nhanh.

## 32. Observability và phân tích hiệu năng

Các lớp cần quan sát:

~~~text
User request / traceId
        |
        v
Gateway / WAF / API Management
        |
        v
Spring Boot HTTP controller
        |
        +-- DB query / connection pool
        +-- Service Bus publish
        +-- Redis cache
        +-- External API
        |
        v
HTTP response / business result
~~~

### Gợi ý telemetry

| Tầng | Dữ liệu có ích |
|---|---|
| **Platform** | CPU, memory, restarts, replicas, cold starts/scale events |
| **JVM** | Heap, GC duration, threads, class loading, OOM |
| **HTTP** | Request rate, p50/p95 latency, 4xx/5xx, timeouts |
| **Database** | Pool utilization, query latency, retry/deadlocks |
| **Queue** | Publish/consume latency, backlog, DLQ |
| **Security** | Unauthorized attempts, denied identities, configuration changes |
| **Business** | Orders created, payment failures, processing lag |
| **Cost** | Spend per environment/service, log ingestion, egress |

Spring Boot thường dùng **Micrometer + Actuator** cho metrics. **Application Insights/Azure Monitor/OpenTelemetry** có thể giúp tập trung traces, logs và số liệu JVM, tùy cách instrumentation/agent/version được cấu hình.

### Correlation

Lưu một **traceId/requestId** từ ingress qua Spring Boot, Azure SDK và database/queue nơi được hỗ trợ. Không log full authorization header, cookies, database passwords, raw PII hoặc file uploads. Set sampling/retention theo độ nhạy dữ liệu và chi phí.

### Đừng chỉ theo dõi CPU

Một app có CPU 30% nhưng p95 latency tăng có thể do DNS, connection pool cạn, SQL locks, GC, network hoặc downstream throttling. SRE cần nhìn **dependency traces** trước khi quyết định scale.

## 33. High availability và disaster recovery

### Các mục tiêu khác nhau

- **Availability:** app tiếp tục phục vụ khi một instance lỗi.
- **RTO:** thời gian tối đa chấp nhận để khôi phục sau sự cố.
- **RPO:** mức mất dữ liệu tối đa chấp nhận khi khôi phục.
- **SLO/SLA:** mục tiêu vận hành so với cam kết dịch vụ theo điều kiện.

### Ví dụ một kiến trúc có khả năng chịu lỗi

~~~text
Users
  |
  v
Azure Front Door / Application Gateway theo yêu cầu
  |
  +--> Region A: >=2 healthy Spring Boot instances
  |         |
  |         +--> Database HA configuration
  |
  +--> Region B: standby/active theo DR plan
            |
            +--> Replication / recovery mechanism
~~~

### Điều cần kiểm tra theo nền tảng

| Nền tảng | Điểm HA |
|---|---|
| **App Service** | Số instances, zone redundancy support của plan, health/routing và regional DR |
| **Container Apps** | Multiple replicas, zones theo environment/plan, revision availability |
| **AKS** | Multi-node pools/zones, topology spread, PDB, resilient ingress |
| **Functions** | Hosting-plan availability và retry/durable processing |
| **VMs** | Availability zones/sets, VMSS, load balancer và patch orchestration |

**Một deployment có replicas=2 không tự bảo đảm multi-zone**; xem placement, platform support, DB HA, shared dependencies và single points of failure.

### Backup không phải HA

Backup giúp phục hồi dữ liệu, còn HA giúp tiếp tục xử lý khi một instance/thành phần lỗi. Đừng tính RPO/RTO cho Spring Boot chỉ từ số replicas compute. Thực hành **failover** và kiểm tra restore/secret/network/DNS.

## 34. Bảo mật và supply chain ở từng nền tảng

Những trách nhiệm chung:

- Quản lý dependencies/CVEs, JDK và Spring Boot versions.
- Không đặt secrets trong Git, image, shell history hoặc log.
- Authentication/authorization bằng **Microsoft Entra ID/OIDC/JWT** hoặc phương thức phù hợp.
- HTTPS/TLS, HSTS và policy public endpoint theo yêu cầu.
- Validate request, CORS/CSRF, input size, upload security.
- Least privilege data-plane, NSG/network segmentation và egress control.
- Configurations/role assignments được quản trị bằng IaC và audit.

### Trọng tâm khác nhau

| Nền tảng | Vấn đề cần chú ý thêm |
|---|---|
| **App Service** | App settings/slot settings, access restrictions, runtime upgrades |
| **Container Apps** | Image signing/scanning, secrets/ingress, revision exposure |
| **AKS** | Kubernetes RBAC, service accounts, network policies, admission, node security |
| **Functions** | Function keys vs end-user auth, trigger identity, exposed HTTP functions |
| **VMs** | OS hardening, patch management, SSH/RDP, host firewall, agents |

**Function key không tương đương user authentication** và **Kubernetes namespace không phải ranh giới bảo mật tuyệt đối**. Thiết kế permissions từ user identity tới resource, không chỉ tầng transport.

### Secret scanning và rollout

Khi secret vô tình bị commit vào image/repository, xóa commit không đủ; phải **rotate** secret, audit access và kiểm tra logs. Với ACR image, pin digest và scan để phát hiện thư viện dễ bị tấn công trước rollout.

## 35. Chi phí: so sánh TCO thay vì chỉ giá compute

Một dự toán "VM 2 vCPU rẻ hơn App Service 2 vCPU" chưa đủ. **Tổng chi phí sở hữu** gồm compute, các dịch vụ phụ thuộc và công vận hành.

~~~text
TCO = Compute/hosting
    + Network ingress/egress/Private Link
    + Database/Storage/Cache
    + Monitoring/log retention
    + Registry/build/security
    + Backup/DR/capacity headroom
    + Vận hành con người & rủi ro sự cố
~~~

### Nhóm chi phí cần liệt kê

| Hạng mục | App Service | Container Apps | AKS | Functions | VMs |
|---|---|---|---|---|---|
| Compute chính | App Service Plan | Consumption/dedicated workload profiles theo plan | Node VMs/node pools và cluster-tier features | Executions/resources/hosting plan | VM hours/disk |
| Tải nhàn rỗi | Plan vẫn có thể tính phí | Scale-to-zero tùy app/plan, có thể có environment cost | Nodes/platform vẫn chạy tùy setup | Tùy plan, min instances/capacity | VM vẫn chạy |
| Scale burst | Plan scale-out | Replica autoscaling | HPA + cluster autoscaler | Trigger-based scale | VMSS/autoscale |
| Network | VNet/Private Endpoint/NAT theo yêu cầu | Environment VNet/ingress/egress | Load balancer, ingress, NAT/VNet | VNet theo plan/tính năng | Load balancer, NSG, Public IP/NAT |
| Security tooling | App/identity policy | Image scanning/secrets | Cluster policy/node/image security | Trigger/identity security | OS patching/hardening |
| Observability | App Insights/logs | Container/platform logs | K8s/container insights | Function telemetry | VM agents/logs |
| Ops/TCO | Thường thấp | Thường thấp–vừa | Cao nếu thiếu platform team | Tùy code/trigger model | Cao |

Các dòng thể hiện **nguồn chi phí**, không phải so sánh giá trực tiếp. Giá/plan/regions đổi theo thời gian và cấu hình; để định lượng, dùng **Azure Pricing Calculator + benchmark thực + Cost Management**.

### Ví dụ đơn giản về instance-hours

Một API cần duy trì **hai instances liên tục** trong tháng giả định 730 giờ:

~~~text
2 instances × 730 giờ = 1.460 instance-hours/tháng
~~~

Một worker chỉ chạy **20 giờ CPU/billing-eligible time mỗi tháng** có thể phù hợp kiểu execution-based hơn nếu runtime và workflow đáp ứng. Tuy nhiên **không thể lấy 20 giờ so thẳng 1.460 giờ rồi kết luận Functions rẻ hơn**: compute units, memory, billing grain, startup, idle charges, downstream traffic và platform capacity khác nhau.

### Chi phí nhân sự và khả năng vận hành

Giả sử dùng AKS cho một API tiết kiệm được một khoản compute mỗi tháng, nhưng đội phải dành thêm 15 giờ/tháng xử lý patching, policies và sự cố cluster. Khi tính TCO, phần công sức này có thể vượt tiết kiệm compute. Ngược lại, nếu đã có AKS platform team dùng chung, chi phí cận biên có thể hợp lý.

## 36. Công thức sizing sơ bộ Spring Boot

Trước khi chọn SKU, đo một ứng dụng đại diện dưới tải kỳ vọng:

| Thước đo | Ý nghĩa |
|---|---|
| Peak concurrent HTTP requests | Số request đang xử lý cùng lúc |
| RPS/QPS | Thông lượng ứng dụng |
| P50/P95/P99 latency | Độ trễ thực tế, không chỉ trung bình |
| CPU per instance | Mức tiêu thụ compute |
| Heap và non-heap RSS | RAM thực cần cho JVM |
| GC pause/time | Dấu hiệu áp lực bộ nhớ |
| DB pool utilization | Giới hạn connections thực |
| Startup/readiness time | Ảnh hưởng autoscale/deployment |
| Downstream latency | Bottleneck SQL/queue/external API |

### Ước lượng concurrency theo Little's Law

Trong điều kiện trạng thái ổn định và giả định phù hợp:

~~~text
Concurrent requests xấp xỉ = throughput (requests/giây)
                               × average latency (giây)

Ví dụ:
  120 requests/giây × 0,20 giây = 24 concurrent requests trung bình
~~~

**Đây không phải quota CPU hay công thức số pods chính xác**. Một request có thể chờ I/O, request latency có phân bố lệch, WebSockets có thời lượng dài và peak khác average. Dùng kết quả load test để chọn số instances, headroom và autoscale thresholds.

### Sizing memory

Giả định một instance thực đo có:

~~~text
Heap maximum:         700 MiB
Non-heap/native/stack: 200 MiB
OS/process overhead:  100 MiB
Headroom mong muốn:   300 MiB
----------------------------
Capacity cần xem xét: 1.300 MiB
~~~

Con số chỉ minh họa cách cộng, chưa tính ảnh hưởng CPU limits, classloading, file buffers, TLS, code paths và traffic. Đừng luôn chọn replica 1GiB chỉ vì -Xmx thấp hơn 1GiB.

### Sizing database connections khi scale-out

~~~text
maxDBConnectionsNeeded ≈ maxReplicas × maxPoolSizePerReplica
                         + worker/admin overhead

Ví dụ:
  12 replicas × 15 connections = 180
  + 30 dành cho services/ops   = 210 connections tham khảo
~~~

Đây là **mức trần lý thuyết** theo cấu hình; connection use thực phụ thuộc pool/lifecycle. Database phải được sizing theo burst và các kết nối khác; app cũng cần timeout/backpressure khi pool cạn.

## 37. Deployment strategy và rollback theo nền tảng

| Nền tảng | Chiến lược thường dùng | Điểm cần kiểm tra |
|---|---|---|
| **App Service** | Deployment slots, swap, traffic routing theo plan/tính năng | Sticky settings, health, warm-up |
| **Container Apps** | Revision rollout/traffic weights, quay về revision trước | Revision modes, secrets/ingress, readiness |
| **AKS** | RollingUpdate/blue-green/canary với Deployment/Ingress/mesh/GitOps | Probe, PDB, capacity, HPA, image digest |
| **Functions** | Slot/version deployments theo hosting support hoặc staged release | Trigger activation, retry, old event bindings |
| **VM/VMSS** | Image rollout/blue-green scale set, rolling upgrades | OS/image compatibility, load balancer health |

### Không chỉ rollback image

Một release thường thay:

~~~text
Java app version
Database schema migration
Event JSON schema
Feature flags
Authorization roles
Container/host settings
Endpoint/network configuration
~~~

**Rollback code có thể thất bại nếu database đã đổi theo cách không tương thích.** Dùng mô hình **expand-and-contract schema migrations**, backward-compatible events, feature flags và testing khi nhiều app versions cùng chạy.

### Một quy trình deploy có kiểm soát

1. Build cùng artifact/JAR/image một lần từ commit được kiểm thử.
2. Security scan, SBOM và dependency checks.
3. Deploy môi trường staging với data/network/config tương đương ở mức cần thiết.
4. Chạy smoke/integration tests và kiểm tra readiness.
5. Canary/blue-green hoặc rolling release theo khả năng platform.
6. Theo dõi p95/5xx, DB metrics, queue lag và business KPI.
7. Promote hoặc rollback route/artifact theo runbook.
8. Chỉ cleanup revision/slot cũ sau thời gian quan sát hợp lý.

Không dùng **latest** image tag không cố định làm chứng cứ đã deploy đúng phiên bản. Ghi image digest/commit SHA và configuration revision.

## 38. Azure CLI: kiểm kê nền tảng hiện có

Trước khi tạo thêm compute service, kiểm kê subscription đã có:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"

# App Service Web Apps
az webapp list --resource-group "$RG" \
  --query "[].{name:name,location:location,kind:kind}" \
  --output table

# Azure Container Apps (cần đúng CLI extension/version)
az containerapp list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# AKS clusters
az aks list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# Azure Functions
az functionapp list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# Azure VMs
az vm list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table
~~~

Các lệnh **chỉ đọc metadata** theo quyền hiện có. Để chạy **az containerapp**, có thể cần cài/cập nhật CLI extension; các output properties và command flags thay đổi theo version. Một resource không xuất hiện trong resource group này không đồng nghĩa subscription không có dịch vụ tương tự ở resource group khác.

### Không dùng subscription production để thử create ngẫu nhiên

Mỗi lệnh tạo App Service Plan, Container Apps environment, AKS cluster hoặc VM có thể tạo **chi phí, public endpoint và chính sách network** khác nhau. Với bài lựa chọn nền tảng, có thể hoàn tất ma trận quyết định và mock deployment **không tạo resource thật**.

## 39. Architecture Decision Record (ADR): quyết định có thể kiểm chứng

Một ADR ngắn giúp tránh chọn theo sở thích cá nhân:

~~~text
ADR-007: Platform for Spring Boot orders-api

Context:
  1 Spring Boot REST API, 5 developers
  HTTP traffic daytime, staging/prod environments
  Azure SQL private access, Entra auth, p95 SLO

Must-have:
  Private database egress, managed identity,
  deployment rollback, JVM 21 support, regional availability

Considered:
  App Service, Container Apps, AKS, Functions, VM

Decision:
  <SELECTED_PLATFORM_AFTER_TEST>

Why:
  <EVIDENCE_FROM_COST_AND_LOAD_TEST>

Trade-offs:
  <OPERATIONS, IDLE COST, SCALE, DEPLOYMENT LIMITS>

Revisit if:
  >10 microservices, need Kubernetes operators,
  traffic shape or compliance changes
~~~

### ADR phải ghi lý do loại phương án

Ví dụ:

- **AKS bị loại** vì không có đội vận hành cluster, và không cần K8s-specific features.
- **Functions bị loại** vì ứng dụng là long-running Spring MVC web app, chưa có kế hoạch refactor handlers.
- **VM bị loại** vì không có native OS constraints.
- **App Service và Container Apps vào vòng PoC** vì đều đáp ứng các điều kiện bắt buộc.

Nếu kết luận chỉ là "chọn AKS vì đang là xu hướng", ADR chưa có bằng chứng kiến trúc.

## 40. Tình huống A: đội nhỏ vận hành một REST API

**Bối cảnh:** Một đội có bốn Java developers xây cổng quản lý đơn hàng, dùng Spring Boot/Java 21, Azure Database for PostgreSQL, khoảng 50–150 requests/s vào giờ cao điểm. Không dùng K8s operators, không có platform team.

### Đánh giá

1. Có thể deploy **executable JAR** với cấu hình App Service phù hợp.
2. Nếu đã có Docker pipeline hoặc cần revision-based releases, cân nhắc Container Apps.
3. Cần database private networking và managed identity theo support matrix.
4. Phải đo RAM, JVM startup, p95 latency và connection pool.
5. Nếu traffic ổn định cả ngày, **scale-to-zero không phải ưu tiên số một**.

### Kết luận cho kịch bản

**App Service** là lựa chọn mặc định hợp lý để PoC đầu tiên; **Container Apps** là ứng viên tương đương nếu đội ưu tiên OCI image/scale/event-driven. **AKS/VM không tự mang lại lợi ích** trong mô hình này trừ khi có constraint mới.

### Sai lầm thường gặp

Chọn AKS ngay vì muốn có "khả năng mở rộng trong tương lai", nhưng chưa có nhu cầu Kubernetes và phải mất nhiều tuần xây networking, ingress, patching pipeline. Khả năng mở rộng cần được chứng minh bằng workload data, không phải số tên dịch vụ.

## 41. Tình huống B: microservices cần scale theo queue

**Bối cảnh:** Một hệ thống thương mại điện tử gồm API orders, inventory, payment integration và notification worker. Orders API phục vụ HTTP, còn worker xử lý Service Bus queue có lưu lượng gấp 20 lần vào buổi tối.

~~~text
HTTP Orders API
     |
     +--> Database
     |
     v
Service Bus queue
     |
     v
Notification worker
     |
     v
Email / external system
~~~

### Phương án

- **Container Apps** cho APIs/workers containerized, scale rule theo HTTP/queue khi được hỗ trợ.
- Hoặc **App Service cho REST API + Azure Functions/Container Apps Job** cho worker.
- **AKS** nếu tổ chức cần Kubernetes, có platform team và các dịch vụ đã dùng K8s.

### Vì sao không đặt worker vào cùng web app?

Khi tăng API replicas, worker listener có thể nhân bản không mong muốn; khi worker backlog tăng, scale HTTP không nhất thiết giúp. Tách service cho phép **độc lập resource limits, autoscale, deployment, credentials và SLO**.

### Điểm cần kiểm tra

- Queue retry/dead-letter và idempotency.
- Không gửi email/charge hai lần khi worker restart.
- HPA/KEDA or external scaling có giới hạn theo database/external API.
- Monitoring oldest message age và backlog thay vì chỉ CPU.

## 42. Tình huống C: batch 20 phút, mỗi đêm một lần

**Bối cảnh:** Một ứng dụng Java đọc tệp CSV từ Blob Storage vào lúc 02:00, xử lý 20 phút rồi dừng. Không có HTTP API, không cần JVM luôn chạy.

### Các ứng viên

| Phương án | Đánh giá |
|---|---|
| **Container Apps Job** | Hợp lý nếu công việc đã đóng container, cần lịch chạy và giới hạn tài nguyên |
| **Azure Functions** | Hợp lý khi function programming model, trigger và hosting plan phù hợp thời gian xử lý |
| **AKS CronJob** | Hợp lý nếu đã có AKS cluster và operational policy |
| **VM cron** | Có thể nhưng chi phí/vận hành cao nếu chỉ vì một job |
| **App Service scheduled logic** | Cần cân nhắc web lifecycle, scale-out, duplicate scheduling |

### Quyết định gợi ý

Nếu đội đã có Dockerfile và chưa có AKS, **Container Apps Job** đáng PoC. Nếu logic tương thích Azure Functions trigger và giới hạn hosting, **Functions** cũng đáng thử.

### Phần dễ bị bỏ sót

- Job chạy lại sau failure có tạo dữ liệu trùng không?
- Có input blob version/event ID ổn định không?
- Có phải chia 20 phút thành các chunk với checkpoint không?
- File đầu vào và kết quả output có được lưu bền ngoài container không?
- Có timeout, retry và max parallel jobs rõ không?

**Một job không có HTTP traffic không cần hosting web server liên tục** chỉ để có nơi chạy Java main method.

## 43. Tình huống D: hệ thống ngân hàng yêu cầu mạng riêng và kiểm toán

**Bối cảnh:** Một Spring Boot API xử lý dữ liệu nhạy cảm. Yêu cầu:

- Inbound chỉ từ private network hoặc gateway đã được kiểm soát.
- Database qua Private Endpoint/Private DNS.
- Managed identity và RBAC tối thiểu.
- WAF, audit logs, log retention có chính sách.
- RTO/RPO và khả năng multi-zone rõ ràng.
- Không cho phép deploy thủ công từ laptop developer.

### Cách lựa chọn

Không thể kết luận **chỉ AKS** mới đáp ứng các yêu cầu này. **App Service, Container Apps và AKS** đều có thể có những cơ chế đáp ứng tùy **SKU/region/topology/tính năng thực tế**. Cần kiểm tra từng tiêu chí bắt buộc:

1. Private inbound/egress và network inspection.
2. Managed identity/data-plane RBAC.
3. Chính sách data residency và zone availability.
4. Secrets, container/JDK patching, audit logging.
5. CI/CD approval và image/artifact provenance.
6. Khả năng DR và thử failover.

### Khi AKS thật sự có lợi

Nếu tổ chức cần **Kubernetes Network Policies**, policy admission, operators, cấu hình scheduling chuyên biệt và đã có platform team, AKS có thể cung cấp bộ công cụ phù hợp. Nếu API đơn giản và PaaS hỗ trợ đầy đủ network/identity/compliance, chọn AKS chỉ vì nhãn "enterprise" chưa đủ lý do.

### Sai lầm cần tránh

Đặt App Service VNet Integration rồi tuyên bố API đã private. VNet Integration chủ yếu giải quyết **outbound**; cần kiểm tra **inbound restrictions/private endpoint** và gateway path độc lập. Tương tự, AKS nằm trong VNet không tự bảo vệ mọi service được mở kiểu public LoadBalancer.

## 44. Tình huống E: ứng dụng legacy phụ thuộc native OS agent

**Bối cảnh:** Spring Boot 2.x trên JDK cũ, dùng thư viện native được cài bằng script hệ điều hành, yêu cầu agent bảo mật độc quyền chạy dưới quyền root và ghi vào filesystem cục bộ.

### Đánh giá

- Kiểm tra thư viện có thể đóng vào **custom container** với quyền non-root không.
- Xác minh JDK/Spring Boot hiện tại còn được hỗ trợ/bảo mật không.
- Kiểm tra yêu cầu agent có thể chuyển sang managed telemetry/sidecar không.
- Nếu bắt buộc OS/kernel control không có trên PaaS, **VM/VMSS** có thể là phương án chuyển tiếp.
- Nếu dùng VM, thiết kế HA, OS patching, managed disks, backup và monitoring.

### Kế hoạch theo hai giai đoạn

~~~text
Giai đoạn 1: bảo đảm ứng dụng chạy an toàn và có HA
  VM/VMSS hoặc container nếu khả thi
          |
          v
Giai đoạn 2: loại native dependencies / nâng JDK
          |
          v
  Đánh giá migration sang App Service/ACA/AKS
~~~

**Không ép đưa legacy vào AKS chỉ để "hiện đại hóa"** nếu container vẫn cần privileged root và host filesystem quá mức. Việc chọn nền tảng phải đi kèm thay đổi kiến trúc/mô hình quyền thật sự.

## 45. Tình huống F: Container Apps cold start làm p95 latency tăng

**Bối cảnh:** Một API ít truy cập ban đêm được đặt Container Apps với **minReplicas=0**. Sau 20 phút yên tĩnh, request đầu tiên mất nhiều giây; SLO API yêu cầu response nhanh cả khi idle.

### Chẩn đoán

1. Đo thời gian từ request đến replica provisioning.
2. Đo JVM startup và Spring context initialization.
3. Đo thời gian database connection, Key Vault access và cache warm-up.
4. Kiểm tra request đã thực sự tới container hay bị mạng/gateway delay.
5. Xem scaling rule và minReplicas/maxReplicas.

### Các lựa chọn

- Đặt **minReplicas=1** hoặc cao hơn để giảm cold start theo khả năng plan.
- Tối ưu startup, tránh blocking initialization không cần thiết.
- Cân nhắc **App Service** với công suất warm nếu traffic/SLO thích hợp.
- Nếu ứng dụng chỉ xử lý async jobs, cho phép queue chờ thay vì đòi HTTP response ngay.

**Scale-to-zero là một lựa chọn kinh tế và kỹ thuật**, không phải tính năng phải bật cho mọi app. Chuyển min replicas sẽ thay đổi cost; phải tính dựa trên tải thực tế.

## 46. Tình huống G: AKS scale nhiều pods nhưng PostgreSQL chậm hơn

**Bối cảnh:** API nhận 429/5xx khi traffic tăng. Nhóm tăng HPA từ 5 lên 30 pods. CPU mỗi pod giảm, nhưng database trả "too many connections" và p95 latency tăng.

### Phân tích

~~~text
Before:
   5 pods × poolSize 20 = tối đa 100 DB connections

After:
  30 pods × poolSize 20 = tối đa 600 DB connections

Database connection budget giả định: 250
~~~

HPA đã nhân số pool vượt khả năng database. Đây là **vấn đề thiết kế phụ thuộc**, không nhất thiết do Kubernetes lỗi.

### Cách khắc phục

1. Giảm per-pod pool max theo tổng connection budget.
2. Giới hạn max replicas và API concurrency trong lúc ổn định dịch vụ.
3. Tối ưu query, transaction duration và cache.
4. Xem khả năng **connection pooler/proxy** tương thích với database và workload.
5. Nếu cần, scale database theo đo đạc và chính sách HA.
6. Đặt metrics/alerts cho HikariCP active/pending, DB connections và latency.

Không chỉ tăng database max_connections vô hạn nếu memory/CPU/lock contention vẫn là giới hạn thực sự.

## 47. Tình huống H: App Service slot swap gửi traffic sang database sai

**Bối cảnh:** staging App Service dùng database test, production dùng database thật. Sau slot swap, ứng dụng production khởi động với một vài biến môi trường lấy từ staging và thao tác trên dữ liệu thử.

### Nguyên nhân

- Slot settings và swap behavior chưa được hiểu đầy đủ.
- App dùng một biến môi trường tên sai hoặc secret reference trỏ chung.
- Không có smoke test xác nhận environment/data source identity.
- Một số resource được chia sẻ giữa staging/prod nhưng ứng dụng không phân biệt.

### Runbook

1. Dừng các write operations gây ảnh hưởng nếu phát hiện sai target.
2. Xác minh **effective configuration** nhưng không in password/secret.
3. Xem slot-specific settings, identity và Key Vault references.
4. Khôi phục traffic/config theo runbook có kiểm soát.
5. Kiểm tra dữ liệu phát sinh sai và đánh giá remediation.
6. Bổ sung startup guard hoặc post-deploy test xác minh resource/environment ID.

### Prevention

Gắn nhãn tài nguyên, tách identities/RBAC theo môi trường và kiểm soát quyền database để **staging identity không thể ghi production data**. Nếu deployment config sai, least privilege vẫn có thể chặn tác hại.

## 48. Bài thực hành: chọn nền tảng cho dự án Spring Boot

### Bối cảnh

Một doanh nghiệp muốn đưa hệ thống **Commerce API** lên Azure. Hệ thống có:

- Một Spring Boot REST API chạy **Java 21**, dùng Maven và PostgreSQL.
- Một worker xử lý Service Bus messages để gửi email.
- Kho lưu trữ file hóa đơn là Azure Blob Storage.
- Giai đoạn đầu **4 Java developers**, chưa có Kubernetes platform team.
- Môi trường **development, staging, production** cần tách quyền.
- Peak giả định **120 requests/giây**, latency mục tiêu p95 dưới **500 ms**.
- Dev có thể tắt ngoài giờ; production cần 2 instances hoặc phương án HA phù hợp.
- Database yêu cầu network private, secrets quản lý tập trung, có alerting.

**Dữ liệu và giá trị trên là giả định học tập.** Không dùng production resources thật để thử nghiệm; nếu chưa có subscription/quyền tạo, hoàn thành bài bằng ADR, manifests và kiểm thử local/mock.

### Phần A: lập bảng yêu cầu

| Yêu cầu | Bắt buộc hay mong muốn? | Bằng chứng cần có |
|---|---|---|
| Chạy JDK 21 và Spring Boot version tương thích | Bắt buộc | Runtime/support matrix |
| HTTPS REST API | Bắt buộc | Ingress test |
| Private database access | Bắt buộc | DNS/network path proof |
| Identity không dùng static Azure keys | Ưu tiên cao | Managed identity + RBAC test |
| p95 dưới 500 ms | Bắt buộc theo SLO giả | Load test |
| Release/rollback có kiểm thử | Bắt buộc | Staging/canary evidence |
| Scale theo HTTP | Mong muốn | Load/scale metrics |
| Worker scale theo Service Bus queue | Mong muốn | Queue backlog metrics |
| Scale-to-zero dev | Mong muốn | Cost vs cold start test |
| Không cần vận hành K8s | Mong muốn cao | Ops effort estimate |

Học viên phải giải thích **tính năng nào là hard constraint**. Nếu một phương án không thể đảm bảo mạng riêng trong region/SKU đang dùng, không cho điểm cao chỉ vì giá tốt.

### Phần B: chọn tối đa hai kiến trúc thử nghiệm

**Kiến trúc 1 — App Service + Functions**

~~~text
Browser / frontend
       |
       v
App Service: Spring Boot Commerce API
       |
       +-- PostgreSQL Flexible Server qua private networking
       +-- Azure Blob Storage
       +-- Azure Service Bus queue
                       |
                       v
               Azure Functions Java worker
~~~

**Kiến trúc 2 — Azure Container Apps**

~~~text
Browser / frontend
       |
       v
Container App: commerce-api
       |
       +-- PostgreSQL Flexible Server qua private networking
       +-- Blob Storage
       +-- Service Bus queue
                       |
                       v
               Container App: mail-worker
               (scale theo queue khi được hỗ trợ)
~~~

**Kiến trúc 3 — AKS** là lựa chọn bổ sung để so sánh nếu tổ chức đã có cluster/shared platform. Không bắt buộc triển khai cả ba vì có thể phát sinh chi phí cao.

### Phần C: chuẩn bị Spring Boot app local

Tạo một REST controller đơn giản:

~~~java
package com.example.commerce;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@RestController
public class DemoController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of(
            "service", "commerce-api",
            "timeUtc", Instant.now().toString()
        );
    }
}
~~~

Đây là **một class** trong project Spring Boot đã được khởi tạo, không phải project Java hoàn chỉnh. Cần main application class, Maven/Gradle, Spring Web dependency và Actuator. Không dùng endpoint ping làm bằng chứng toàn hệ thống đã kết nối database hoặc đáp ứng security.

Tạo health endpoint theo Spring Boot Actuator:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true

server:
  port: 8080
  shutdown: graceful
~~~

**Đặt port 8080 cho bản local/container**; khi deploy App Service Java SE, kiểm tra runtime port convention của hosting. Nếu database chưa cấu hình, health check chỉ xác nhận phần ứng dụng đã chạy, không phải chức năng business hoàn chỉnh.

### Phần D: kiểm thử local

~~~bash
# Lệnh yêu cầu project Maven hợp lệ
./mvnw -B clean verify
./mvnw spring-boot:run

# Thực hiện từ terminal khác
curl --fail http://localhost:8080/api/ping
curl --fail http://localhost:8080/actuator/health
~~~

Không chạy một bộ kiểm thử tích hợp database thật nếu chưa có test configuration, vì ứng dụng có thể kết nối production nhầm. Dùng local container/test database hoặc mock đã được cho phép.

### Phần E: đóng gói hai cách

**JAR cho App Service:**

~~~text
Git -> Maven verify -> executable JAR
                     |
                     v
              App Service Java SE
~~~

**OCI image cho Container Apps:**

~~~text
Git -> Maven verify -> Dockerfile -> ACR
                                  |
                                  v
                           Container Apps
~~~

Nếu dùng Dockerfile ở mục 22, bảo đảm artifact có tên **target/support-api.jar** hoặc sửa lệnh COPY theo output thực của dự án. Kiểm tra container chạy non-root, có health endpoint và port 8080.

### Phần F: thử deployment sandbox (nếu được phê duyệt)

1. Chọn subscription và resource group lab, gắn tags **environment, owner, costCenter, deleteAfter**.
2. Dùng IaC hoặc hướng dẫn Portal được tổ chức cho phép để tạo đúng một nền tảng thử.
3. Thiết lập staging data source, managed identity và secret references.
4. Xác minh private DNS/network path từ chính app instance.
5. Deploy artifact đã test; ghi commit SHA/image digest.
6. Smoke test **/api/ping** và **/actuator/health**, xác thực thực tế của API.
7. Thử 2 instances/replicas, thực hiện rolling/revision deployment.
8. Kiểm tra graceful shutdown, logs/traces và rollback.
9. Thử tải có giới hạn, đo CPU/RAM, p95, DB connections.
10. Thu thập thông tin cost/limits và dọn tài nguyên lab khi xong.

**Không cần tạo AKS cluster chỉ để hoàn thành bài này** nếu người học chưa có quyền/budget. Một ADR kèm kế hoạch benchmark và kiến trúc minh chứng vẫn đạt mục tiêu học tập.

### Phần G: ma trận benchmark để điền

| Chỉ số | App Service + Functions | Container Apps | Kết luận |
|---|---|---|---|
| Time-to-first-response khi warm | Đo thực tế | Đo thực tế | Theo SLO |
| Cold-start sau idle | Nếu có theo mô hình | Đo nếu minReplicas=0 | UX trade-off |
| P95 latency ở 120 req/s | Đo thực tế | Đo thực tế | Chọn đạt target |
| JVM resident memory | Đo thực tế | Đo thực tế | Sizing |
| Database peak connections | Đo thực tế | Đo thực tế | Phải dưới capacity |
| Max scale được kiểm chứng | Theo plan/test | Theo plan/test | Không tự suy quota |
| CI/CD rollback | Slot/process test | Revision test | Time to recovery |
| Private network + identity | PASS/FAIL | PASS/FAIL | Must-have |
| Worker queue backlog | Theo trigger/worker | Theo scale rule | Theo SLO |
| Monthly total cost estimate | Dựa SKU/usage | Dựa SKU/usage | Bao gồm downstream |
| Operational effort | Ước lượng giờ/tháng | Ước lượng giờ/tháng | TCO |

Không điền số latency/cost tự tưởng tượng rồi gọi đó là kết quả benchmark. Nếu không chạy lab thực, ghi **not measured**, cùng giả định và kế hoạch đo.

### Phần H: viết ADR một trang

Kết quả thực hành cần nêu:

1. **Bối cảnh/requirements**: loại app, SLO, team, workload, compliance.
2. **Phương án được xét**: ít nhất App Service và Container Apps; giải thích việc loại Functions/AKS/VM nếu không phù hợp.
3. **Must-have evaluation**: network, JDK, identity, DR, release.
4. **Ma trận có trọng số**, kèm giả định/tính nhạy.
5. **Bằng chứng PoC/ước lượng chi phí**, ghi rõ chỗ chưa đo.
6. **Quyết định và trade-offs**, owner phê duyệt.
7. **Kế hoạch triển khai/rollback**, điều kiện xem xét lại trong tương lai.

### Phần I: cleanup

- Xóa hoặc dừng đúng tài nguyên **lab do mình tạo/sở hữu** theo chính sách, không xóa resource group dùng chung.
- Xóa test images/secrets theo retention; không xóa registry/Key Vault production.
- Xác minh không còn chi phí plan, environment, node, log ingestion, disk hoặc NAT ngoài dự tính.
- Không commit keys/connection strings; nếu đã lộ thì rotate.

## 49. Checklist trước khi chốt nền tảng

- [ ] Đã xác định HTTP API, worker, scheduler và các workload riêng.
- [ ] Có mục tiêu SLO, peak load, idle time và RTO/RPO.
- [ ] Biết dependency về JDK/Spring Boot/native libraries/OS.
- [ ] Đã kiểm tra runtime/JDK support và lifecycle dịch vụ Azure.
- [ ] Không mặc định chọn Azure Spring Apps cho kiến trúc mới khi chưa kiểm tra retirement notices.
- [ ] Đã so sánh App Service, Container Apps, AKS, Functions và VM theo use case.
- [ ] Có must-have security/compliance/region/identity trước khi chấm điểm.
- [ ] Đã tính gánh nặng vận hành và năng lực đội ngũ.
- [ ] Biết artifact sẽ là JAR/WAR hay OCI image và cách scan/sign.
- [ ] Đã tách HTTP API và background jobs nếu scaling/lifecycle khác nhau.
- [ ] Đã thử health checks, readiness/liveness/startup và graceful shutdown.
- [ ] Biết memory/CPU sizing và JVM non-heap headroom.
- [ ] Biết app port/ingress configuration theo platform.
- [ ] Đã kiểm tra inbound vs outbound private network và DNS từ workload.
- [ ] Dùng managed identity/data-plane RBAC và Key Vault khi thích hợp.
- [ ] Không lưu secrets trong Git, JAR, container image hoặc log.
- [ ] Không dùng ephemeral local disk làm source-of-truth hay session store.
- [ ] Đã tính database connection pool theo max replicas.
- [ ] Có autoscale metric đúng cho HTTP/queue/stream và concurrency cap.
- [ ] Đã xác định cold-start budget và min instances nếu SLO cần.
- [ ] Đã chọn deployment/rollback strategy và khả năng schema compatibility.
- [ ] Có telemetry JVM/HTTP/downstream/traces, alerts và runbooks.
- [ ] Đã đánh giá zone/region HA, backup/restore và DR.
- [ ] Đã tính TCO gồm compute, network, database, logs, CI/CD và nhân sự.
- [ ] Có ADR và điều kiện đánh giá lại quyết định.
- [ ] Chỉ tạo tài nguyên thực khi có quyền/budget; dọn lab sau thử nghiệm.

## 50. Câu hỏi tự kiểm tra

1. Vì sao không thể chọn nền tảng Azure chỉ dựa vào việc hỗ trợ Java?
2. App Service, Container Apps, AKS, Functions và VM khác nhau ở mức tự quản nào?
3. Khi nào App Service Java SE là lựa chọn đơn giản hơn containerization?
4. Một App Service Plan chia sẻ giữa nhiều Web Apps ảnh hưởng sizing ra sao?
5. Có thể deploy custom container lên App Service không?
6. Container Apps environment, app, revision và replica khác nhau thế nào?
7. Khi nào scale-to-zero tốt và khi nào làm hỏng latency SLO?
8. KEDA/event-based scaling khác HTTP/CPU autoscaling ở mục tiêu nào?
9. Tại sao chạy một Spring Boot monolith web bằng Azure Functions không phải chỉ upload JAR?
10. Khi nào Functions là lựa chọn tốt cho Java event handler?
11. Những yêu cầu nào thực sự biện minh cho AKS?
12. Managed Kubernetes control plane có loại bỏ trách nhiệm patching/nodes của đội vận hành không?
13. Kubernetes Deployment, Service và Ingress có vai trò gì?
14. Readiness, liveness và startup probes khác nhau ra sao?
15. Vì sao liveness probe không nên phụ thuộc SQL availability quá chặt?
16. Tại sao cấu hình container memory limit bằng đúng JVM heap max dễ gây OOM?
17. Khi nào VM/VMSS vẫn là lựa chọn đúng?
18. Azure Spring Apps có yếu tố vòng đời nào cần kiểm tra trước quyết định mới?
19. Azure Front Door và API Management có thay compute Spring Boot được không?
20. Tại sao @Scheduled có thể chạy nhiều lần khi scale replicas?
21. JAR và OCI image khác nhau ở chuỗi cung ứng và patching?
22. Spring Boot container đã chạy trong Docker có tự là stateless app không?
23. App Service VNet Integration khác inbound Private Endpoint thế nào?
24. Managed identity đã bật có tự cấp data-plane permission không?
25. Secret references/Key Vault giải quyết vấn đề gì, và vẫn còn rủi ro nào?
26. Vì sao database connection pool phải tính theo số replicas tối đa?
27. Tại sao tăng pods có thể làm PostgreSQL chậm đi?
28. RTO, RPO, SLO và SLA khác nhau thế nào?
29. Hai replicas có tự bảo đảm multi-zone HA không?
30. Blue-green/canary/rollback có thể thất bại do schema migration ra sao?
31. Vì sao phí log ingestion/egress/network cần có trong TCO?
32. Decision matrix có trọng số có thể dùng trước bước compliance screening không?
33. Một REST API nhỏ có thể hưởng lợi từ AKS nếu đã có platform team như thế nào?
34. Nếu workload chỉ chạy một lần/đêm, vì sao không cần máy ảo chạy liên tục?
35. Hệ thống yêu cầu private network có bắt buộc phải dùng AKS không?
36. Container Apps minReplicas=0 cần kiểm thử những gì?
37. Vì sao một slot swap có thể gây sự cố dù code hoàn toàn đúng?
38. Những số liệu nào cần đo để so sánh App Service và Container Apps?
39. Khi một deployment return HTTP 200, điều đó chứng minh chức năng nghiệp vụ đã đúng chưa?
40. Trường hợp nào khiến bạn cần xem xét lại ADR sau sáu tháng?

## 51. Tài liệu tham khảo

- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview) — dịch vụ web PaaS.
- [Configure a Java app for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java) — Java runtime, hosting và cấu hình.
- [App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — staging, swap và rollback.
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview) — container apps, environments, scaling.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — versioning và traffic management.
- [Azure Container Apps scale](https://learn.microsoft.com/azure/container-apps/scale-app) — HTTP/event-driven scaling.
- [Azure Container Apps jobs](https://learn.microsoft.com/azure/container-apps/jobs) — jobs theo lịch/sự kiện.
- [Azure Kubernetes Service overview](https://learn.microsoft.com/azure/aks/intro-kubernetes) — AKS và kiến trúc managed Kubernetes.
- [Kubernetes workload identity on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — service account và Entra identity.
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview) — FaaS triggers/hosting models.
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java programming model.
- [Azure Virtual Machines overview](https://learn.microsoft.com/azure/virtual-machines/overview) — IaaS và VM operations.
- [Azure Spring Apps documentation and lifecycle information](https://learn.microsoft.com/azure/azure-spring-apps/) — xem thông báo retirement/migration hiện hành.
- [Azure Container Registry documentation](https://learn.microsoft.com/azure/container-registry/) — OCI images và artifact security.
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — workload authentication.
- [Azure Private Link documentation](https://learn.microsoft.com/azure/private-link/private-link-overview) — private connectivity và DNS.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html) — health/metrics/production-ready features.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, distributed traces và alerts.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — tính chi phí theo region/SKU.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, security, operational excellence, performance và cost.

**Kết luận:** Đối với Spring Boot trên Azure, hãy chọn nền tảng theo **workload và trách nhiệm vận hành**, không theo nhãn "mạnh nhất". **App Service** thường hợp lý cho REST API/JAR cần ít hạ tầng; **Container Apps** phù hợp containerized microservices, background jobs và scaling linh hoạt; **AKS** dành cho nơi cần Kubernetes và có năng lực platform engineering; **Functions** hợp với xử lý sự kiện; **VMs** dành cho yêu cầu OS/legacy đặc thù. Dù chọn phương án nào, chất lượng production vẫn phụ thuộc **identity, private networking, dữ liệu, JVM resource sizing, health probes, deployment/rollback, observability và TCO**. Hãy dùng must-have criteria, ma trận đánh giá có trọng số, PoC và ADR để quyết định bằng chứng cứ, đồng thời kiểm tra lifecycle/tính năng Azure tại thời điểm triển khai.
