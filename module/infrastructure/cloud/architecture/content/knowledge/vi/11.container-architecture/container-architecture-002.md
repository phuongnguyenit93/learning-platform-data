# Lựa chọn nền tảng container được quản lý và Kubernetes

> **Chương:** Kiến trúc container  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ tới lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt nền tảng container được quản lý ở cấp ứng dụng, Kubernetes được quản lý và Kubernetes tự vận hành.
2. Phân tích workload để xác định mức kiểm soát compute, network, storage, scheduling và runtime cần thiết.
3. So sánh các lựa chọn theo trách nhiệm vận hành, khả năng tùy biến, độ tin cậy, bảo mật, mở rộng và TCO.
4. Thiết kế workload container có cấu hình tài nguyên, health probes, autoscaling, network policy, secrets, observability và chiến lược rollout phù hợp.
5. Xây dựng ma trận quyết định có điều kiện bắt buộc, trọng số và bằng chứng kiểm thử.
6. Lập kế hoạch triển khai, di trú và xem xét lại lựa chọn khi yêu cầu hoặc năng lực đội thay đổi.

## 1. Bắt đầu từ workload, không bắt đầu từ tên nền tảng

Container đóng gói ứng dụng cùng các dependency cần thiết để chạy, giúp giảm khác biệt giữa môi trường phát triển, kiểm thử và production. Nhưng việc chạy container ở đâu vẫn là quyết định kiến trúc quan trọng.

Một ứng dụng đặt chỗ trên cloud có thể gồm ba nhóm workload:

- API HTTP phục vụ người dùng, cần autoscaling theo lưu lượng và phát hành phiên bản thường xuyên.
- Worker xử lý hàng đợi, chạy liên tục, cần kiểm soát concurrency và shutdown có trật tự.
- Job định kỳ tạo báo cáo, đồng bộ dữ liệu hoặc dọn dẹp tài nguyên.

Cùng một image có thể chạy trên nhiều nền tảng. Trước khi chọn, hãy trả lời:

- Đội cần kiểm soát những phần nào: node, network, scheduling, ingress, storage, service discovery hay runtime policy?
- Có workload cần GPU, kernel capability, daemon, sidecar hoặc volume đặc biệt không?
- Số lượng service, mức biến động tải, concurrency và thời gian chạy là bao nhiêu?
- Ai chịu trách nhiệm patch node, nâng cấp control plane, cluster networking, capacity và sự cố production?
- Yêu cầu bảo mật, vùng dữ liệu, audit, SLO, RTO/RPO và ngân sách nào là điều kiện bắt buộc?

Một nền tảng tốt giúp tổ chức đáp ứng yêu cầu với mức độ kiểm soát và trách nhiệm vận hành phù hợp.

## 2. Các loại nền tảng container thường gặp

### 2.1. Managed container platform cấp ứng dụng

Người dùng thường cung cấp image, cấu hình CPU/RAM, biến môi trường, cổng, health check và quy tắc mở rộng. Nền tảng đảm nhiệm phần lớn việc bố trí compute và quản lý môi trường chạy.

Đặc điểm thường gặp:

- Triển khai container mà không phải trực tiếp quản lý cluster Kubernetes.
- Mức trừu tượng cao, tích hợp sẵn với load balancer, logging, identity và autoscaling theo cách của nhà cung cấp.
- Phù hợp với web service, API, worker và tác vụ container có yêu cầu runtime tiêu chuẩn.
- Ít quyền tùy biến scheduler, node OS, CNI/CSI, admission policy hoặc service mesh so với Kubernetes.
- Có thể giới hạn thời gian chạy, loại workload, concurrency, network mode hoặc cách mount volume.

Ví dụ gồm AWS App Runner, Google Cloud Run, Azure Container Apps và các dịch vụ tương tự. Tên gọi và tính năng thay đổi theo sản phẩm, phiên bản và khu vực triển khai; cần kiểm tra tài liệu hiện hành trước khi quyết định.

### 2.2. Managed Kubernetes

Nhà cung cấp quản lý một phần hoặc phần lớn control plane; khách hàng vẫn khai báo workload qua API Kubernetes và chịu trách nhiệm với nhiều cấu hình cluster, node pool, networking, security policy và ứng dụng.

Ví dụ phổ biến gồm Amazon EKS, Google Kubernetes Engine (GKE) và Azure Kubernetes Service (AKS). Phạm vi quản lý khác nhau theo chế độ vận hành, node model, phiên bản và tính năng được bật.

Managed Kubernetes không có nghĩa nhà cung cấp chịu toàn bộ trách nhiệm cho cấu hình cluster hoặc ứng dụng.

### 2.3. Self-managed Kubernetes

Tổ chức tự cài đặt và quản lý control plane, node, nâng cấp, network, storage, backup/restore, security và observability. Cách này cho mức kiểm soát lớn nhưng cũng tạo nhiều trách nhiệm hạ tầng hơn.

Chỉ nên chọn khi có lý do rõ ràng như môi trường đặc thù, yêu cầu kiểm soát không thể đáp ứng bằng dịch vụ managed hoặc năng lực nền tảng đủ mạnh. Tự vận hành chỉ để có toàn quyền có thể khiến đội dành phần lớn thời gian duy trì nền tảng thay vì phát triển sản phẩm.

### 2.4. Các khái niệm không nên nhầm

| Khái niệm | Vai trò |
| --- | --- |
| Container runtime | Chạy container image và quản lý vòng đời process/container |
| Orchestrator | Lập lịch, duy trì trạng thái mong muốn, mở rộng và quản lý nhiều workload |
| Kubernetes control plane | API, scheduler, controller và các thành phần điều khiển cluster |
| Worker node | Máy/compute chạy workload container trong mô hình Kubernetes node-based |
| Managed platform | Dịch vụ trừu tượng hóa một phần trách nhiệm hạ tầng và vận hành |
| Container registry | Lưu và phân phối image/artifact |
| Service mesh | Lớp hỗ trợ giao tiếp service-to-service, telemetry và traffic policy |

Kubernetes là nền tảng điều phối container, không phải container runtime đơn lẻ. Nó cung cấp API và cơ chế điều khiển linh hoạt, nhưng không tự động giải quyết thiết kế nghiệp vụ, dữ liệu, bảo mật ứng dụng hoặc chi phí.

## 3. Hai hướng lựa chọn: managed platform và Kubernetes

~~~mermaid
flowchart TB
    W["Yêu cầu workload và tổ chức"] --> Q{"Cần mức kiểm soát orchestration đến đâu?"}
    Q -->|"Runtime tiêu chuẩn, ít vận hành nền tảng"| M["Managed container platform"]
    Q -->|"Cần API Kubernetes, policy và ecosystem"| K["Managed Kubernetes"]
    Q -->|"Cần kiểm soát sâu control plane/hạ tầng"| S["Self-managed Kubernetes"]
    M --> MV["Tập trung app config, image, IAM, network tích hợp"]
    K --> KV["Quản lý cluster/node, namespace, policy, workload"]
    S --> SV["Quản lý control plane, node, upgrades, network, storage"]
~~~

Managed platform thường giảm số quyết định hạ tầng mà nhóm ứng dụng phải vận hành. Kubernetes tạo một mô hình điều khiển chung và ecosystem phong phú, nhưng người vận hành phải hiểu thêm các abstraction, dependency và cơ chế lỗi.

Không có lựa chọn tối ưu cho mọi tổ chức. Có hệ thống nên dùng hai loại: API tiêu chuẩn chạy trên managed platform, còn workload yêu cầu scheduling/policy đặc biệt chạy trên Kubernetes. Kết hợp chỉ có lợi khi sự khác biệt đủ lớn để bù chi phí vận hành hai nền tảng.

### 3.1. Bảng so sánh tổng quan

| Tiêu chí | Managed platform | Managed Kubernetes | Self-managed Kubernetes |
| --- | --- | --- | --- |
| Mức trừu tượng | Cao | Trung bình | Thấp hơn |
| Control plane | Nền tảng quản lý | Nhà cung cấp quản lý theo phạm vi dịch vụ | Tổ chức chịu trách nhiệm |
| Node/compute | Có thể ẩn hoặc cấu hình theo profile | Thường chọn node pool/compute model | Tổ chức quản lý node và OS |
| Linh hoạt orchestration | Theo tính năng nền tảng | Cao theo API Kubernetes | Cao nhưng tự chịu vận hành |
| Networking | Theo mô hình nhà cung cấp | CNI, Service, Ingress/Gateway, network policy | Tự triển khai phần lớn lớp mạng |
| Storage | Giới hạn theo tích hợp | CSI, PV/PVC, StorageClass | Tự quản lý tích hợp storage |
| Autoscaling | Theo request, CPU, concurrency hoặc metric hỗ trợ | HPA, KEDA, node autoscaling tùy hệ thống | Tự vận hành các thành phần mở rộng |
| Portability | Phụ thuộc API và dịch vụ tích hợp | API tương đối chuẩn, nhưng storage/network/identity vẫn khác | Kiểm soát cao hơn nhưng không loại bỏ mọi phụ thuộc |
| Gánh nặng vận hành | Thường thấp hơn | Trung bình đến cao | Cao |
| Phù hợp | App tiêu chuẩn, đội tập trung sản phẩm | Nhiều workload, cần điều phối linh hoạt | Môi trường đặc thù và đội platform chuyên sâu |

Bảng phản ánh xu hướng, không phải cam kết cho mọi nhà cung cấp. Cần so sánh đúng service mode, region, quota, giới hạn runtime và mô hình thanh toán.

## 4. Xây bộ tiêu chí lựa chọn có thể đo được

### 4.1. Điều kiện bắt buộc trước khi chấm điểm

Một số yêu cầu loại trừ phương án ngay từ đầu:

- Region/zone phải được phép xử lý và lưu dữ liệu.
- Runtime phải hỗ trợ ngôn ngữ, CPU architecture, kernel/capability, filesystem hoặc GPU cần thiết.
- Có thể đáp ứng network connectivity, private endpoint, egress control và IAM policy bắt buộc.
- Có khả năng backup/restore và đạt yêu cầu RTO/RPO.
- Hỗ trợ log, audit, vulnerability scanning và cơ chế patch theo chính sách.
- Nằm trong quota, budget và hợp đồng được phê duyệt.

Nếu một managed platform không hỗ trợ volume với semantics ứng dụng bắt buộc, đó là điều kiện chưa đáp ứng. Cần đổi cách thiết kế ứng dụng hoặc chọn nền tảng khác; không nên chỉ cho điểm thấp rồi bỏ qua.

### 4.2. Ma trận yêu cầu

| Nhóm | Câu hỏi | Bằng chứng nên có |
| --- | --- | --- |
| Workload | HTTP, background worker, batch, streaming, stateful hay GPU? | Workload profile, prototype |
| Scale | Tải đỉnh, tốc độ tăng, scale-to-zero có phù hợp không? | Load test, concurrency test |
| Availability | SLO, deployment zone, failover, node drain? | Diễn tập lỗi và báo cáo |
| Security | IAM, image provenance, secrets, egress, runtime isolation? | Threat model, policy test |
| Operations | Team có on-call và kỹ năng xử lý nền tảng không? | Skills/capacity assessment |
| Deployment | Rolling update, canary, rollback, blue/green? | Release test |
| Observability | Metrics, logs, traces, audit và retention? | Dashboard và alert test |
| Cost | Compute, request, storage, network, license, vận hành? | TCO theo tải thường/đỉnh |
| Portability | Có cần di chuyển cloud hoặc hybrid? | Dependency inventory, migration exercise |

### 4.3. Chấm điểm sau khi qua điều kiện bắt buộc

Có thể thống nhất thang 1–5 và trọng số để đánh giá tương đối:

\[
Score=\sum_{i=1}^{n}w_i s_i,\qquad \sum_{i=1}^{n}w_i=1
\]

Trong đó \(w_i\) là trọng số tiêu chí do các bên thống nhất, \(s_i\) là điểm phương án ở tiêu chí đó. Điểm số là công cụ thảo luận, không phải phép đo khách quan nếu dữ liệu đầu vào chỉ là phỏng đoán.

Ví dụ giả định cho API HTTP và worker nền tiêu chuẩn:

| Tiêu chí | Trọng số | Managed platform | Managed Kubernetes |
| --- | ---: | ---: | ---: |
| Đơn giản vận hành | 25% | 5 | 3 |
| Linh hoạt orchestration | 20% | 2 | 5 |
| Scale workload tiêu chuẩn | 15% | 4 | 4 |
| Kiểm soát network/policy | 15% | 3 | 5 |
| Tốc độ onboarding | 10% | 5 | 3 |
| TCO theo quy mô giả định | 15% | 4 | 3 |
| **Tổng có trọng số** | **100%** | **3,85** | **3,80** |

Điểm số chỉ minh họa cách làm. Hệ thống có hàng trăm workload, custom controller hoặc policy phức tạp có thể cho kết quả khác; hệ thống có hai API tiêu chuẩn với đội nhỏ có thể nghiêng rõ về managed platform.

Không nên chấm security chỉ vì một nền tảng có nhiều tính năng. An toàn phụ thuộc cả cấu hình, identity, network, pipeline, runtime và năng lực vận hành.

## 5. Khi nào managed container platform phù hợp?

Cân nhắc managed platform khi:

- Workload chủ yếu là HTTP API, web service, worker và scheduled job theo runtime tiêu chuẩn.
- Đội muốn tập trung vào business logic, delivery và vận hành ứng dụng.
- Không cần custom scheduler, daemon trên node, CRD/operator hoặc network plugin đặc biệt.
- Tải biến động, cần scale theo request/concurrency hoặc scale-to-zero.
- Muốn giảm trách nhiệm patch, nâng cấp control plane/node và capacity planning.
- Muốn tiếp cận container bằng lộ trình triển khai đơn giản, dễ đào tạo.

### Các giới hạn cần kiểm tra

- Execution model: request-triggered service hay workload chạy nền lâu dài?
- Concurrency: request tối đa mỗi instance, queue semantics và giới hạn xử lý song song.
- Startup/shutdown: startup timeout, graceful termination, scale-to-zero và cold start.
- Storage: filesystem ephemeral hay persistent; access mode và behavior khi instance thay đổi.
- Networking: private ingress, outbound static IP, VPC integration, service identity, private DNS.
- Runtime: quyền root, kernel capability, host access, sidecar, init process, CPU architecture.
- Job/scheduler: chạy định kỳ, retry, timeout và kiểm soát job trùng.
- Quota: max instances, request size, execution time, image size và regional capacity.

Nền tảng serverless container có thể thuận tiện nhưng vẫn có giới hạn cho workload stateful, daemon hoặc xử lý dài. Không nên suy ra rằng không có cold start, quota hay trách nhiệm vận hành chỉ từ tên serverless.

## 6. Khi nào Kubernetes đem lại lợi ích?

Kubernetes phù hợp hơn khi yêu cầu cần một lớp orchestration giàu khả năng:

- Hàng chục/hàng trăm workload với nhiều loại Deployment, StatefulSet, DaemonSet, Job và CronJob.
- Scheduling, affinity/anti-affinity, topology spread, resource quota và priority.
- Service discovery và traffic routing nhất quán giữa nhiều team.
- Custom resource/controller hoặc ecosystem phục vụ vận hành nền tảng.
- Network policy, admission policy và kiểm soát workload theo namespace/cluster.
- Nhiều workload có đặc điểm tài nguyên khác nhau, cần node pool riêng.
- Có đội platform đủ năng lực chuẩn hóa cluster, policy, upgrade, observability và hỗ trợ developer.

Phân biệt cần Kubernetes với thích Kubernetes. Nếu workload chỉ cần chạy một image HTTP tiêu chuẩn, chưa chắc việc quản lý cluster, node pool, ingress, policy và operator đem lại giá trị tương xứng.

### 6.1. Thành phần cần hiểu

| Thành phần | Chức năng | Câu hỏi thiết kế |
| --- | --- | --- |
| Cluster | Phạm vi điều khiển và tài nguyên | Một hay nhiều cluster? Tách theo môi trường, vùng, trust boundary? |
| Control plane | API server, scheduler, controller | Provider quản lý phần nào? Upgrade policy? |
| Node pool | Nhóm node có cấu hình compute tương tự | Workload cần CPU, memory, GPU hoặc architecture khác nhau? |
| Namespace | Phân vùng logic | Quota, RBAC và network policy đã đủ cô lập chưa? |
| Deployment | Quản lý replica ứng dụng stateless | Rolling update, readiness, rollout strategy? |
| StatefulSet | Workload stateful cần identity/volume ổn định | Có nên chạy DB trong cluster? Backup/restore ra sao? |
| Service | Địa chỉ ổn định để truy cập workload | Internal/external access? |
| Ingress/Gateway | Điểm vào HTTP(S) | TLS, routing, WAF và ownership? |
| ConfigMap/Secret | Cấu hình và tham chiếu secret | Encryption at rest, secret store, rotation? |
| HPA | Mở rộng replica workload | Metric, min/max và stabilization? |
| PodDisruptionBudget | Giới hạn voluntary disruption | Có đủ replica và topology không? |
| Network Policy | Kiểm soát luồng mạng Pod/namespace | CNI có enforcement không? |
| Operator/CRD | Mở rộng API/automation | Ai sở hữu lifecycle, upgrade và sự cố? |

### 6.2. Ví dụ Deployment cho API stateless

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api:1.8.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            failureThreshold: 30
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
~~~

Ví dụ cần điều chỉnh theo ứng dụng và cluster:

- Requests giúp scheduler tính tài nguyên; khai báo thấp hơn nhu cầu có thể làm node quá tải.
- Limits giới hạn mức sử dụng theo semantics runtime. CPU limit có thể gây throttling; memory vượt limit thường dẫn đến container bị OOMKilled.
- Startup probe dành thời gian cho ứng dụng khởi động; readiness quyết định có nhận traffic; liveness xác định process có cần restart.
- Không dùng một endpoint kiểm tra mọi dependency cho cả ba loại probe.
- Read-only filesystem cần đường ghi hợp lệ cho thư mục tạm qua volume phù hợp.
- Không nên dùng tag latest cho production; cần artifact versioned hoặc image digest có thể truy vết và rollback.

## 7. Tài nguyên, autoscaling và capacity planning

### 7.1. CPU/memory requests và limits

Trong Kubernetes:

- Request là lượng tài nguyên scheduler dùng để bố trí Pod.
- Limit là giới hạn áp dụng ở runtime theo loại tài nguyên.
- Overcommit có thể tăng hiệu quả sử dụng node nhưng giảm margin cho workload quan trọng.
- QoS class chịu ảnh hưởng từ requests/limits và có thể tác động lựa chọn Pod khi node pressure xảy ra.

Không lấy cấu hình máy local áp nguyên lên production. Hãy đo profile ở tải thực tế hoặc benchmark có dataset, concurrency và điều kiện gần production.

### 7.2. Mở rộng workload

Horizontal Pod Autoscaler (HPA) thay đổi số replica dựa trên metric như CPU, memory hoặc custom/external metrics nếu hệ thống hỗ trợ. HPA không tự tạo thêm năng lực node nếu cluster không có compute trống; node autoscaler hoặc compute provider phải bổ sung capacity.

~~~mermaid
flowchart TD
    MET["Metrics: CPU / request rate / queue age"] --> HPA["HPA / autoscaling policy"]
    HPA --> REPL["Số replica Pod"]
    REPL --> SCHED["Scheduler"]
    SCHED -->|"Node còn capacity"| NODES["Worker nodes"]
    SCHED -->|"Thiếu capacity"| CA["Cluster/node autoscaler"]
    CA --> NODES
    NODES --> APP["Workload chạy"]
    APP --> MET
~~~

Cần xác định:

- Metric nào phản ánh nhu cầu thật? CPU cao không phải lúc nào cũng tương quan với số request.
- Min/max replicas, scale-up speed, scale-down stabilization và resource headroom.
- Node startup delay, quota vùng và giới hạn API cloud.
- Pod startup time, image pull, readiness và thời gian warm-up.
- Database/broker phía sau có chịu được concurrency mới không?

### 7.3. Scale-to-zero và cold start

Scale-to-zero giảm chi phí khi không có request, nhưng request đầu tiên sau idle có thể chậm vì khởi tạo container, load image, runtime và kết nối dependency. Với checkout hoặc API có SLO p95 nghiêm ngặt, cần thử tải sau giai đoạn idle.

Worker dùng queue cần chiến lược rõ: scale-to-zero có thể phù hợp với tác vụ thưa, nhưng phải đo thời gian nhận message đầu tiên, visibility timeout, duplicate delivery và khả năng drain khi scale-down.

## 8. Networking, ingress và service-to-service

Nền tảng container quyết định cách workload nhận request và gọi dependency:

- Ingress traffic có thể đi qua load balancer, API gateway, WAF hoặc ingress controller.
- Pod/service giao tiếp qua DNS nội bộ, virtual network và policy.
- Outbound traffic cần được kiểm soát qua NAT, egress gateway, private endpoint hoặc firewall.
- TLS/mTLS, service identity và authorization là lớp bảo vệ quan trọng; network reachability không đồng nghĩa được phép truy cập nghiệp vụ.
- Service discovery cần ổn định qua rollout, scale và node failure.
- Observability phải ghi được request/trace xuyên qua gateway, service và worker.

Đừng xem cluster như một mạng phẳng. Nếu mọi Pod được phép gọi mọi Pod và mọi database đều mở cho mọi namespace, một container bị xâm nhập có thể di chuyển ngang. Cần xác định trust boundary, default-deny policy khi phù hợp, RBAC và service account tối thiểu quyền, cùng kiểm thử network reachability.

Managed container platform cấp ứng dụng có thể cung cấp private networking hoặc service identity theo abstraction riêng. Hãy đánh giá hành vi thực tế thay vì ép mô hình cấu hình Kubernetes lên một dịch vụ không công khai các khái niệm đó.

## 9. Bảo mật chuỗi cung ứng và runtime

Container image mang theo code, thư viện, OS package và cấu hình khởi động. Rủi ro xuất hiện từ source, dependency, build pipeline, registry đến production runtime.

Các kiểm soát cần cân nhắc:

1. **Base image:** dùng image tối thiểu, nguồn tin cậy và lịch cập nhật rõ.
2. **Build reproducibility:** khóa version dependency, tạo SBOM và provenance khi khả thi.
3. **Image scanning:** quét CVE, áp severity policy và ngoại lệ có owner/thời hạn.
4. **Registry access:** private registry, IAM least privilege và audit pull/push.
5. **Image signing/verification:** xác minh artifact đến production từ pipeline tin cậy nếu hệ thống hỗ trợ.
6. **Runtime security:** non-root, read-only filesystem, drop capability, seccomp/AppArmor hoặc cơ chế tương đương, hạn chế host access và privilege.
7. **Secrets:** lấy từ secret manager hoặc cơ chế an toàn, không bake vào image hay log.
8. **Patch lifecycle:** rebuild và redeploy image khi base image hoặc dependency cần cập nhật; container không tự cập nhật thư viện bên trong khi đang chạy.

### 9.1. Ví dụ Dockerfile nhiều giai đoạn

~~~dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine AS runtime
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
~~~

Ví dụ chỉ minh họa multi-stage build. Trước production cần xác minh version base image đã được pin theo policy, user 101 có quyền đọc/ghi phù hợp, cấu hình nginx hỗ trợ non-root/cổng unprivileged, health check và logging được thiết lập. Không copy file môi trường, private key hoặc local cache vào final image.

## 10. Deployment strategy và availability

Một nền tảng container tốt vẫn có thể gây downtime nếu rollout, probe và shutdown không phù hợp.

### 10.1. Rolling update

Thay dần Pod cũ bằng Pod mới theo giới hạn maxSurge/maxUnavailable. Phù hợp khi ứng dụng và schema tương thích giữa các phiên bản. Cần readiness chính xác, termination grace period và capacity đủ cho giai đoạn hai phiên bản cùng chạy.

### 10.2. Blue/green và canary

- **Blue/green:** duy trì hai môi trường, chuyển traffic sau kiểm thử. Dễ rollback traffic nhưng có thể tăng chi phí và cần xử lý schema/data migration.
- **Canary:** chuyển một phần traffic tới phiên bản mới, theo dõi error rate/latency rồi tăng dần. Cần traffic splitting và số liệu đáng tin cậy.

### 10.3. Readiness và graceful shutdown

Khi Pod nhận SIGTERM, ứng dụng cần ngừng nhận request mới, hoàn tất hoặc từ chối công việc đang chạy theo semantics, đóng connection và thoát trong thời hạn. Nếu terminate process ngay lập tức, request hoặc message đang xử lý có thể mất hoặc bị gửi lại.

Với worker queue, thiết kế ack/nack, visibility timeout, idempotency và drain phải phối hợp với lifecycle của container. PreStop hook có thể hỗ trợ nhưng không thay thế logic shutdown an toàn trong ứng dụng.

### 10.4. Availability zone và disruption

Nhiều replica không có nghĩa là HA nếu tất cả Pod nằm cùng node hoặc zone. Có thể dùng topology spread, anti-affinity, PodDisruptionBudget và node pool phù hợp. PDB giới hạn một số voluntary disruptions; không bảo vệ khỏi mọi sự cố node/zone hoặc mọi kiểu force deletion.

Managed platform có thể ẩn node placement; cần kiểm tra cam kết multi-zone, cách phân bổ instance và khả năng failover theo đúng mode.

## 11. Stateful workloads và lưu trữ

Container có filesystem ghi tạm không đồng nghĩa dữ liệu bền vững. Nếu container bị thay thế, local data có thể mất.

Đối với stateful workload, cần làm rõ:

- **Ephemeral storage:** cache/tệp tạm có thể tái tạo; cần quản lý dung lượng và cleanup.
- **Persistent volume:** volume có vòng đời, access mode, zone affinity, snapshot và backup riêng.
- **Managed database/object storage:** nên cân nhắc dịch vụ dữ liệu được quản lý thay vì tự chạy database trong cluster, trừ khi có lý do cụ thể.
- **StatefulSet:** cung cấp identity/ordinal và volume claim template; không tự động giải quyết replication, backup hoặc database consistency.
- **Restore:** diễn tập phục hồi dữ liệu, không chỉ kiểm tra snapshot tồn tại.

Với managed application platform, volume có thể không hỗ trợ hoặc chỉ hỗ trợ một số dạng persistence. Nếu workload cần filesystem dùng chung hoặc storage semantics đặc biệt, phải xác minh trước khi chọn.

### Khi nào nên chạy database trong Kubernetes?

Có thể hợp lý khi đội có kinh nghiệm vận hành database operator, replication, backup, restore, upgrade, storage class và sự cố dữ liệu; hoặc môi trường có ràng buộc khiến triển khai này hữu ích.

Không nên đưa database vào cluster chỉ vì muốn mọi thứ đều container. Managed database có thể cung cấp backup, patch, failover và tích hợp cloud IAM tốt hơn với chi phí vận hành thấp hơn. So sánh TCO và khả năng đạt RPO/RTO trong điều kiện thực tế.

## 12. Observability và trách nhiệm vận hành

Managed platform giảm một phần công việc infrastructure nhưng vẫn cần quan sát ứng dụng. Kubernetes làm tăng thêm lớp cần giám sát: control plane theo phạm vi truy cập, node, scheduler, CNI, CSI, ingress, operator, quota và cluster autoscaler.

| Lớp | Chỉ số / log cần theo dõi |
| --- | --- |
| Application | Request rate, p95/p99, error rate, business success |
| Container | CPU, memory, throttling, restart, OOMKilled, startup time |
| Kubernetes workload | Desired vs available replicas, rollout, pending Pod, probe failures |
| Node/cluster | Capacity, pressure, node readiness, scheduling, upgrade status |
| Networking | Connection errors, DNS, ingress latency, policy drops |
| Storage | Volume capacity, latency, attach/mount failures, snapshot/restore |
| Autoscaling | Replica changes, scale lag, quota, pending workloads |
| Cost | vCPU/RAM idle, request pricing, node utilization, egress, log ingestion |

Không chỉ theo dõi Pod Running. Một API có ba replica Running nhưng toàn bộ request chậm vì database vẫn là một hệ thống không đạt yêu cầu. SLI/SLO nên phản ánh hành vi người dùng: tỷ lệ tìm kiếm thành công, p95 checkout, tỷ lệ job hoàn tất đúng hạn và khả năng phục hồi.

SRE cần runbook cho Pod crash loop/OOM, node/zone mất khả dụng, HPA thiếu metric/quota, image pull thất bại, secret/config lỗi sau deploy, network policy chặn nhầm, storage mount/restore lỗi và control plane/API quota gặp sự cố.

## 13. Chi phí: tính TCO thay vì chỉ giá compute

Managed platform thường tính tiền theo instance/resource đang chạy, request, thời gian compute hoặc kết hợp tùy sản phẩm. Kubernetes có chi phí control plane/management tùy provider/mode, node/compute, storage, load balancer, network, logs, registry, license và nhân sự vận hành.

\[
TCO = C_{\text{compute}} + C_{\text{control}} + C_{\text{network}}
+ C_{\text{storage}} + C_{\text{observability}}
+ C_{\text{security}} + C_{\text{operations}}
\]

Trong đó chi phí vận hành gồm công platform engineering, trực sự cố, nâng cấp, xử lý lỗ hổng, kiểm thử DR và duy trì automation.

### Ví dụ so sánh giả định

Giả sử một dịch vụ API và hai worker có tải vừa phải:

| Khoản mục/tháng | Managed platform | Managed Kubernetes |
| --- | ---: | ---: |
| Compute workload | 700 USD | 500 USD |
| Platform/control/cluster | Gộp vào dịch vụ hoặc theo mức dùng | 150 USD |
| Load balancer/network | 80 USD | 120 USD |
| Logging/metrics/security | 100 USD | 120 USD |
| Công vận hành phân bổ | 100 USD | 450 USD |
| **Tổng minh họa** | **980 USD** | **1.340 USD** |

Số liệu hoàn toàn minh họa, không phải báo giá nhà cung cấp. Với nhiều workload, node sharing có thể giúp Kubernetes hiệu quả hơn; với số lượng ít, managed platform có thể tránh chi phí nền và công vận hành cluster.

Tính ít nhất sáu kịch bản: steady state, peak, idle, failure/DR, growth và engineering cost. Không chọn Kubernetes chỉ với kỳ vọng tiết kiệm compute; cũng không chọn managed platform chỉ vì nghĩ rằng không còn chi phí vận hành.

## 14. Tình huống thực tế: nền tảng đặt chỗ đang tăng trưởng

### 14.1. Bối cảnh

Một doanh nghiệp có ba API stateless cần autoscaling, hai worker tiêu thụ message từ queue, một job báo cáo theo lịch và một thành phần xử lý ảnh cần thư viện native đặc biệt. Đội Platform có hai kỹ sư; đội phát triển muốn phát hành thường xuyên. Dự kiến mở rộng từ 10.000 lên 100.000 người dùng hoạt động trong một năm.

Đây là bối cảnh giả định. Chưa đủ thông tin để chốt nền tảng; phải đo throughput, thời gian job, dependency, security và chi phí trước.

### 14.2. Hai phương án

**Phương án A — Managed container platform cho toàn bộ workload**

Ưu điểm: ít gánh nặng cluster, onboarding API nhanh, tích hợp dịch vụ cloud, có thể autoscale theo mức sử dụng nếu nền tảng hỗ trợ.

Cần xác minh: worker chạy liên tục/queue semantics, job schedule, thư viện native, storage, concurrency, outbound network và khả năng giữ instance nóng theo SLO.

**Phương án B — Managed Kubernetes**

Ưu điểm: quản lý nhiều loại workload qua API và ecosystem chung; tùy biến scheduler, node pool, policy, sidecar/operator và network theo nhu cầu.

Đánh đổi: đội Platform phải phụ trách cluster upgrade, node capacity, CNI/CSI, ingress, policy, observability và hỗ trợ developer. Hai kỹ sư cần xác định khả năng trực và mức tự động hóa trước khi mở rộng.

### 14.3. Phương án kết hợp có thể xem xét

| Workload | Hướng đề xuất ban đầu | Điều kiện |
| --- | --- | --- |
| API tiêu chuẩn | Managed platform | p95, concurrency, private networking và autoscaling đạt |
| Worker queue | Managed platform hoặc Kubernetes | Graceful shutdown, queue metric, retry và long-running process |
| Scheduled report | Managed job/scheduler hoặc Kubernetes CronJob | Retry, timeout, tránh job trùng và kiểm soát quyền |
| Image processing native | Prototype trên cả hai nếu cần | CPU/GPU, library, memory và throughput |
| Workload cần policy/scheduling đặc biệt | Managed Kubernetes nếu đã chứng minh nhu cầu | Platform team đủ năng lực và cung cấp guardrails |

Kết hợp tạo thêm cách triển khai, logging, IAM, deployment và support. Chỉ dùng khi khác biệt workload đáng kể; nếu API, worker và job đều chạy tốt trên cùng managed platform thì một nền tảng có thể đơn giản hơn.

### 14.4. Kế hoạch kiểm chứng

1. Đóng gói cùng một image cho API và worker.
2. Deploy prototype lên managed platform và managed Kubernetes trong môi trường tương đương.
3. Chạy load test với tải thường/đỉnh; đo p95/p99, cold start, concurrency và error rate.
4. Thử worker xử lý message trùng, shutdown, scale-down, retry và dead-letter queue.
5. Thử rollout/rollback, secret rotation, network restriction và image vulnerability scanning.
6. Mô phỏng instance/node failure và khôi phục dữ liệu liên quan.
7. Tính TCO gồm compute, cluster/platform, network, logging, security và công vận hành.
8. Review kết quả với Product, SRE, Security, Finance và owner kỹ thuật; ghi ADR và trigger xem xét lại.

## 15. Lộ trình triển khai và di trú

### Bước 1 — Chuẩn hóa image

Build reproducible, pin dependency và base image; chạy non-root khi khả thi; externalize config/secrets; log stdout/stderr; có health endpoint và graceful shutdown. Không lưu state quan trọng trong writable filesystem của container.

### Bước 2 — Đo workload

Tạo workload profile về CPU, memory, startup, duration, concurrency, network và I/O. Xác định SLO, capacity, surge, dependency và biến động tải.

### Bước 3 — Xây nền tảng triển khai chuẩn

Dùng Infrastructure as Code, registry, CI/CD, image scan, identity, network, logs, metrics, secrets và runbook. Nếu chọn Kubernetes, chuẩn hóa namespace, quotas, RBAC, network policies, node pools, ingress, HPA và upgrade policy.

### Bước 4 — Di chuyển một workload đại diện

Chọn API không quá nhạy cảm hoặc worker có thể đối soát; triển khai song song, chuyển một phần lưu lượng, theo dõi SLI và rollback. Không di chuyển mọi service cùng lúc.

### Bước 5 — Mở rộng theo bằng chứng

Chỉ bổ sung workload hoặc cluster khi có lý do rõ. Tối ưu node/request, quota, autoscaling và cost allocation; đánh giá lại sau sự cố và thay đổi traffic.

### Bước 6 — Kiểm soát nợ nền tảng

Nợ platform có thể gồm cluster không được nâng cấp, operator không còn hỗ trợ, policy drift, dashboard thiếu, module IaC trùng lặp và deploy thủ công. Ghi owner, mức ảnh hưởng và trigger trả nợ.

## 16. Architecture Decision Record mẫu

~~~markdown
# ADR-041: Chọn nền tảng chạy container cho API và worker đặt chỗ

Trạng thái: Chấp thuận có điều kiện
Decision owner: Architecture lead + SRE + Product
Ngày: YYYY-MM-DD

Bối cảnh:
- 3 API stateless, 2 worker queue, 1 scheduled report.
- Đội Platform có 2 kỹ sư.
- Cần autoscaling, rollout an toàn và quan sát theo SLO.
- Image native của image processor cần kiểm chứng riêng.

Ràng buộc:
- Region và network phải đạt chính sách dữ liệu.
- RTO/RPO, IAM và audit theo yêu cầu đã phê duyệt.
- TCO trong ngân sách.

Phương án:
A. Managed container platform.
B. Managed Kubernetes.
C. Kết hợp theo loại workload.

Quyết định:
- Thử nghiệm A cho API và worker tiêu chuẩn.
- Chỉ chọn B cho workload có yêu cầu orchestration/policy
  mà A không đáp ứng, sau khi review năng lực Platform.

Đánh đổi:
- A giảm công quản lý cluster nhưng bị giới hạn abstraction.
- B linh hoạt hơn, tăng trách nhiệm node/network/upgrade.
- C tăng số nền tảng cần quan sát và support.

Bằng chứng nghiệm thu:
- Load, cold-start, graceful shutdown, queue retry.
- Security, network, image scanning và rollback.
- Diễn tập lỗi và TCO theo steady/peak/DR.

Điều kiện xem xét lại:
- Workload mới cần GPU/daemon/operator;
  số workload tăng mạnh; SLO/region/chi phí thay đổi;
  hoặc Platform team đạt năng lực vận hành cluster mới.
~~~

ADR cần đính kèm workload profile, báo cáo thử nghiệm, cost model, rủi ro còn lại và owner. Không phê duyệt chỉ từ một bản demo chạy thành công.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chọn Kubernetes vì microservices | Tăng vận hành mà chưa có nhu cầu orchestration | Đánh giá workload và năng lực đội |
| Nghĩ managed nghĩa là provider chịu mọi trách nhiệm | Bỏ qua security, app, quota và cấu hình | Làm rõ shared responsibility và RACI |
| So sánh chỉ giá CPU/RAM | Bỏ control plane, egress, logging, backup, nhân sự | Tính TCO và kịch bản lỗi/tăng trưởng |
| Không đo cold start/scale lag | Vi phạm p95 trong giờ cao điểm | Load test từ idle và surge |
| Đặt request/limit tùy tiện | Throttling, OOM, pending Pod | Profile tài nguyên và điều chỉnh |
| Dùng liveness kiểm tra toàn bộ dependency | Dependency lỗi gây restart dây chuyền | Tách startup/readiness/liveness |
| Quên graceful shutdown | Mất hoặc trùng job/message | Drain, idempotency và termination test |
| Nhiều replica nhưng chung một zone | Mất zone vẫn làm toàn bộ workload gián đoạn | Topology spread và diễn tập failure |
| Đưa DB vào cluster chỉ để đồng nhất | Tăng rủi ro storage/backup/upgrade | So sánh managed DB và operator |
| Bật HPA nhưng thiếu node capacity | Pod pending khi tải tăng | Kết hợp workload và node autoscaling |
| Không chuẩn hóa image/registry | Deploy lỗi, lỗ hổng, khó truy vết | Pin artifact, scan, sign/verify và audit |
| Dùng nhiều nền tảng tùy tiện | Phân mảnh IAM, logging và kỹ năng | Chỉ dùng hybrid khi workload có yêu cầu khác biệt |

## 18. Bài tập thực hành

Một hệ thống logistics gồm 12 microservice, 4 worker queue, 2 batch job chạy mỗi đêm và một dịch vụ xử lý hình ảnh. Đội có 4 kỹ sư backend, 1 kỹ sư Platform; hiện có CI/CD nhưng chưa có kinh nghiệm vận hành cluster. Doanh nghiệp cần mở rộng gấp bốn lần trong mùa cao điểm, p95 API theo ngưỡng Product phê duyệt và DR phù hợp hợp đồng.

Hãy thực hiện:

1. Lập workload profile cho API, worker, batch và image processor; xác định CPU/RAM, concurrency, startup, storage, network và thời gian chạy.
2. Xác định điều kiện bắt buộc: region, network, IAM, audit, RTO/RPO, SLO và quota.
3. So sánh managed platform và managed Kubernetes; nêu tính năng cụ thể cần kiểm tra.
4. Xây ma trận quyết định có trọng số; giải thích trọng số với Product, Security, SRE và Finance.
5. Đề xuất nền tảng cho từng workload; nếu chọn kết hợp, giải thích chi phí hỗ trợ nhiều nền tảng.
6. Thiết kế rollout API/worker, probes, graceful shutdown, autoscaling, queue backpressure và rollback.
7. Viết kịch bản kiểm thử cold start, peak load, node/instance failure, secret rotation, restore và cost spike.
8. Tạo ADR có giả định, phương án thay thế, rủi ro còn lại, owner và điều kiện đánh giá lại.

**Tiêu chí tự đánh giá:** giải pháp tốt phải chứng minh nền tảng đáp ứng workload và trách nhiệm vận hành, có số liệu SLO/chi phí, có thể triển khai/khôi phục an toàn và không dựa vào giả định rằng nhiều công nghệ hơn sẽ tự động tốt hơn.

## 19. Checklist trước khi đưa workload vào production

- [ ] Workload profile và yêu cầu chất lượng đã được xác nhận.
- [ ] Chọn nền tảng dựa vào điều kiện bắt buộc và ma trận so sánh có bằng chứng.
- [ ] Image có nguồn tin cậy, pin version/digest, được quét và quản lý lifecycle.
- [ ] Container chạy quyền tối thiểu; không chứa secrets; filesystem được thiết kế đúng.
- [ ] CPU/RAM requests/limits dựa trên đo đạc.
- [ ] Startup/readiness/liveness probes phản ánh đúng trạng thái ứng dụng.
- [ ] Autoscaling có metric, min/max, headroom, quota và dependency capacity.
- [ ] Networking, ingress, egress, service identity và policy được kiểm tra.
- [ ] Deployment hỗ trợ rolling/canary/blue-green phù hợp, rollback đã thử.
- [ ] Graceful shutdown, job drain, idempotency và queue retry đã xác minh.
- [ ] Volume, backup, restore, RTO/RPO và dữ liệu stateful có owner.
- [ ] Metrics/logs/traces/dashboard/alert/runbook đã sẵn sàng.
- [ ] Node/cluster/platform được patch và nâng cấp theo policy.
- [ ] TCO gồm compute, platform, storage, network, observability, security và công vận hành.
- [ ] ADR ghi phương án, đánh đổi, giả định, rủi ro và trigger xem xét lại.

## Ghi nhớ

**Managed container platform** giúp đội tập trung vào ứng dụng bằng cách trừu tượng hóa nhiều phần triển khai và vận hành; đổi lại, mức tùy biến phụ thuộc giới hạn sản phẩm. **Kubernetes** cung cấp API orchestration phong phú, phù hợp khi nhu cầu về workload, scheduling, policy và ecosystem đủ lớn; đổi lại tổ chức phải đầu tư năng lực platform, networking, storage, security và lifecycle.

Hãy lựa chọn theo chuỗi **yêu cầu workload → điều kiện bắt buộc → mức kiểm soát cần thiết → năng lực vận hành → thử nghiệm SLO/TCO → ADR có điều kiện xem xét lại**. Một nền tảng phù hợp giúp hệ thống đáp ứng yêu cầu nghiệp vụ an toàn, đáng tin cậy, có khả năng mở rộng và chi phí vận hành chấp nhận được.
