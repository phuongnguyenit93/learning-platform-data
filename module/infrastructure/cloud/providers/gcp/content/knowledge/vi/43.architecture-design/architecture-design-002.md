# So sánh Compute Engine, GKE, Cloud Run và App Engine

Khi đưa một ứng dụng Java/Spring lên Google Cloud, câu hỏi đầu tiên không nhất thiết là “dùng lệnh deploy nào?”. Câu hỏi quan trọng hơn là **ứng dụng cần bao nhiêu quyền kiểm soát hạ tầng, cần kiểu mở rộng nào, đội ngũ sẵn sàng vận hành đến đâu và yêu cầu về độ tin cậy, bảo mật, chi phí là gì?** Một REST API đơn giản có thể phù hợp với Cloud Run, hệ thống nhiều workload cần Kubernetes có thể phù hợp với Google Kubernetes Engine (GKE), phần mềm legacy phụ thuộc hệ điều hành có thể cần Compute Engine, còn ứng dụng web đã gắn chặt với mô hình App Engine có thể tiếp tục phát huy lợi thế của dịch vụ đó.

Bài học nằm trong chương **Thiết kế kiến trúc GCP** của module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong bài này, chúng ta so sánh bốn nền tảng chạy ứng dụng từ góc nhìn kiến trúc, không coi một nền tảng là tốt nhất trong mọi trường hợp.

> **Phạm vi:** So sánh chủ yếu xoay quanh ứng dụng web/API, dịch vụ Java/Spring Boot, worker và một số workload nền. Tính năng, giới hạn và giá có thể thay đổi theo thời gian, region và cấu hình; luôn kiểm tra tài liệu cùng bảng giá chính thức trước khi chốt phương án production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mô hình máy ảo, Kubernetes, serverless container và nền tảng ứng dụng được quản lý.
- Đánh giá Compute Engine, GKE, Cloud Run và App Engine theo quyền kiểm soát, vận hành, scaling, triển khai, network, chi phí và tính di động.
- Hiểu khác biệt giữa GKE Autopilot và Standard, cũng như App Engine Standard và Flexible.
- Chọn nền tảng dựa trên yêu cầu Java/Spring Boot, background jobs, dịch vụ trạng thái và phụ thuộc hạ tầng.
- Ước lượng các thành phần của tổng chi phí sở hữu thay vì chỉ so giá CPU hoặc memory.
- Thiết kế deployment mẫu và xác định ranh giới IAM, storage, logging và rollback.
- Đề xuất kiến trúc một nền tảng hoặc kết hợp nhiều nền tảng với lập luận và giả định có thể kiểm tra.

## 1. Bốn lựa chọn trên phổ quyền kiểm soát

Google Cloud cung cấp nhiều mức trừu tượng:

1. **Compute Engine:** cấp máy ảo (VM). Nhóm có quyền kiểm soát guest OS, runtime, process và phần lớn cấu hình host ở mức VM.
2. **GKE:** cung cấp Kubernetes được quản lý. Nhóm định nghĩa Pod, Deployment, Service, networking và chính sách Kubernetes; mức quản lý node khác nhau giữa Standard và Autopilot.
3. **Cloud Run:** triển khai container hoặc source thành workload serverless mà không phải vận hành cluster. Cloud Run có nhiều loại tài nguyên, trong đó services phù hợp request-driven API, jobs phù hợp task hữu hạn và worker pools phù hợp xử lý nền dạng pull/always-on.
4. **App Engine:** nền tảng triển khai ứng dụng theo service/version, với môi trường **Standard** và **Flexible** có đặc tính vận hành khác nhau.

~~~mermaid
flowchart LR
    A["Compute Engine<br/>VM và guest OS"]
    B["GKE<br/>Kubernetes"]
    C["Cloud Run<br/>serverless workloads"]
    D["App Engine<br/>app-centric platform"]
    A --- B --- C --- D
~~~

Sơ đồ giúp hình dung các mô hình triển khai, **không** phải một thứ tự tuyệt đối về chi phí, hiệu năng hoặc mức phù hợp. GKE Autopilot giảm đáng kể công việc node so với GKE Standard; App Engine Flexible vẫn chạy trên VM được quản lý; Cloud Run hiện không chỉ phục vụ HTTP requests. Khi ra quyết định, hãy so sánh theo loại workload cụ thể.

### Shared responsibility: Google quản lý gì và nhóm quản lý gì?

| Lớp trách nhiệm | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Phần cứng, hạ tầng Google | Google | Google | Google | Google |
| Guest OS của workload | Nhóm vận hành chịu trách nhiệm cấu hình/vá guest OS | Node OS do GKE quản lý ở mức phụ thuộc mode; nhóm vẫn quản lý workload | Google quản lý hạ tầng, ứng dụng quản lý dependencies trong image/source | Google quản lý môi trường theo Standard/Flexible |
| Orchestration | Nhóm tự làm hoặc dùng MIG | Kubernetes/GKE | Cloud Run | App Engine |
| Runtime/ứng dụng | Nhóm | Nhóm | Nhóm | Nhóm, trong ranh giới runtime |
| IAM, dữ liệu, secret, network policy | Nhóm cấu hình | Nhóm cấu hình; một phần mặc định do GKE hỗ trợ | Nhóm cấu hình ingress/egress/identity | Nhóm cấu hình service IAM, identity và quyền |
| Scaling policy, SLO, observability | Nhóm | Nhóm | Nhóm, dù nền tảng lo provisioning | Nhóm, dù nền tảng lo provisioning |

**Managed không có nghĩa là không còn việc vận hành.** Với mọi nền tảng, đội ngũ vẫn chịu trách nhiệm thiết kế phân quyền, bảo vệ dữ liệu, quản lý dependency, xử lý lỗi ứng dụng, đặt SLO và quan sát tác động người dùng.

## 2. So sánh nhanh trong một bảng

| Tiêu chí | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Đơn vị triển khai | VM image, startup script, package, container trên VM | Container trong Pod/Deployment/Job | Container, source build; service/job/worker pool | App service và version; source/runtime hoặc container tùy môi trường |
| Quyền kiểm soát OS | Cao, gồm guest OS và kernel | Cao hơn trong Standard; giới hạn hơn ở Autopilot | Không sửa host OS/kernel | Standard hạn chế, Flexible tùy biến qua container/Dockerfile |
| Tự quản lý node | Có | Standard: có; Autopilot: GKE quản lý | Không | Không theo mô hình quản trị node thông thường |
| Kiểu mở rộng | Tự thiết kế hoặc MIG autoscaling | HPA/VPA, node autoscaling, theo mode | Theo loại workload: request, task, CPU/backlog hoặc cấu hình | Automatic/basic/manual tùy Standard/Flexible |
| Scale to zero | VM không mặc định scale-to-zero | Workload có thể về 0 replica, nhưng còn chi phí cluster/node theo mode | Service thường có thể về 0; jobs chạy khi được gọi; worker pool có quy tắc riêng | Standard automatic có thể về 0; Flexible thường cần ít nhất 1 instance |
| Mức độ vận hành | Cao | Trung bình đến cao; Autopilot giảm việc node | Thấp hơn cho workload phù hợp | Tương đối thấp, nhưng chịu ràng buộc platform |
| Workload stateful | Có thể chạy với disk và HA tự thiết kế | StatefulSet + persistent volumes | Nên tách state bền vững ra dịch vụ khác | Nên tách state bền vững ra dịch vụ khác |
| Phù hợp điển hình | Legacy, custom OS, agent/driver đặc biệt | Nhiều microservice, Kubernetes-native, cần networking/operator | API, webhook, event processing, batch task phù hợp | App web đã theo App Engine hoặc cần mô hình service/version |
| Giá phải xét | VM, disk, IP, network, OS/license, HA | Cluster, node hoặc workload resources, network, storage | CPU/memory/resources theo chế độ billing, requests, min instances và network | Instance/resources theo Standard/Flexible, storage/network và dịch vụ phụ trợ |
| Tính di động | VM image/script, cần quản lý OS | Kubernetes manifests, vẫn có cấu hình riêng GCP | OCI image di động ở mức code, nhưng API/deploy riêng Cloud Run | App.yaml và runtime/model triển khai có mức gắn nền tảng |

Đây là bảng định hướng. Ví dụ GKE Autopilot có tính tự động hóa cao hơn GKE Standard, Cloud Run có loại workload nền ngoài service HTTP, và Compute Engine Managed Instance Groups (MIG) hỗ trợ autoscaling/autohealing. Vì thế, không nên quyết định chỉ bằng một ô “Có/Không”.

## 3. Compute Engine: quyền kiểm soát VM và sự linh hoạt

Compute Engine là dịch vụ Infrastructure as a Service (IaaS): tạo VM với machine type, hệ điều hành, disk, network interface, firewall và service account phù hợp. Nhóm có thể cài JDK, Nginx, agent giám sát, thư viện native hoặc phần mềm cần quyền quản trị guest OS.

### Khi Compute Engine là lựa chọn tốt

- Ứng dụng legacy cần cấu hình hệ điều hành, cổng TCP tùy biến, daemon hoặc thư viện native.
- Có yêu cầu kiểm soát kernel/guest OS, driver, process manager hoặc lịch vá cụ thể.
- Workload cần gắn disk, dùng GPU/hardware profile, hoặc có yêu cầu phần mềm không phù hợp giới hạn của PaaS.
- Tổ chức đã vận hành hiệu quả VM và có công cụ image baking, patching, backup, monitoring.
- Cần lộ trình lift-and-shift nhanh từ VM/on-premises trước khi hiện đại hóa ứng dụng.

### Những gì nhóm phải vận hành

- Cấu hình OS, update/patch bảo mật, hardening và xử lý CVE.
- Triển khai code, cấu hình systemd/service, tự động restart và health checks.
- Load balancing, autoscaling, capacity planning và HA giữa nhiều zone.
- Monitoring agent, log shipping, backup, recovery, disk lifecycle.
- Firewall, service account, network ingress/egress và bảo vệ SSH.

Một VM duy nhất chạy Spring Boot có thể đủ cho bài demo nhưng là single point of failure. Với ứng dụng production cần availability, nên xem xét nhiều VM ở các zone khác nhau, load balancer và mô hình update/rollback có kiểm soát.

### Managed Instance Groups

Compute Engine **Managed Instance Groups (MIG)** cho phép quản lý nhiều VM tương tự qua instance template, hỗ trợ autoscaling, autohealing, rolling updates và triển khai theo nhiều zone với regional MIG. Điều này giảm một phần công việc so với quản lý từng VM thủ công, nhưng nhóm vẫn phải quản lý image, OS, cấu hình ứng dụng và chiến lược release.

Không nhầm lẫn MIG autoscaling với khả năng serverless hoàn toàn: các VM trong group vẫn có lifecycle, thời gian boot và chi phí theo tài nguyên được cấp.

### Ví dụ triển khai Spring Boot trên VM

Một kiến trúc đơn giản:

~~~text
HTTPS Load Balancer
      |
Managed Instance Group
  +--- VM A (Spring Boot, systemd, Ops Agent)
  +--- VM B (Spring Boot, systemd, Ops Agent)
      |
Cloud SQL / Memorystore / Cloud Storage
~~~

Các VM dùng service account hạn chế quyền và tải artifact đã được kiểm thử từ một repository tin cậy. Tài nguyên trạng thái bền vững tách khỏi filesystem của từng VM nếu cần triển khai có khả năng thay thế instance.

**Hạn chế cốt lõi:** độ tự do lớn đi kèm chi phí vận hành lớn. Nếu chỉ cần chạy một API HTTP stateless, Compute Engine có thể tạo thêm công việc không đem lại lợi ích tương ứng.

## 4. GKE: Kubernetes cho hệ thống nhiều workload

Google Kubernetes Engine cung cấp Kubernetes được quản lý. Bạn khai báo desired state của ứng dụng bằng Deployment, StatefulSet, DaemonSet, Job, Service, ConfigMap, Secret, Ingress hoặc Gateway. Kubernetes điều phối Pod, thực hiện rolling updates, đưa Pod mới vào phục vụ sau readiness probe và thay thế Pod lỗi theo controller.

### Khi chọn GKE

- Đội ngũ đã có kinh nghiệm Kubernetes hoặc cần một nền tảng chung cho nhiều team/microservices.
- Workload cần custom Kubernetes controller, operator, sidecar, service mesh, advanced networking hoặc policy.
- Cần orchestration cho nhiều loại workload: web/API, worker, Job, cron, StatefulSet.
- Cần kiểm soát cấu hình deployment, placement, affinity, taints/tolerations, quota và namespaces.
- Muốn hợp nhất quy trình GitOps/Helm/Kustomize và triển khai đa-cluster.

GKE không tự loại bỏ nhu cầu hiểu Kubernetes. Nhóm vẫn thiết kế manifest, requests/limits, probes, security context, RBAC, rollout và khôi phục sự cố ứng dụng.

### GKE Standard so với Autopilot

| Câu hỏi | GKE Standard | GKE Autopilot |
|---|---|---|
 Ai quản lý node pool? | Nhóm chọn/kiểm soát, với công cụ autoscaler hỗ trợ | Google quản lý node infrastructure cho workload Autopilot |
| Quyền tùy chỉnh node | Nhiều lựa chọn, phù hợp driver/agent đặc thù | Bị giới hạn bởi chính sách và cấu hình Autopilot |
| Autoscaling | Kết hợp HPA và cluster/node autoscaler, cấu hình do nhóm quyết định | GKE tự cấp node capacity theo nhu cầu Pod; nhóm vẫn thiết kế workload scaling |
| Bảo mật mặc định | Nhóm cần cấu hình và duy trì policy tương ứng | Tích hợp nhiều mặc định và giới hạn bảo mật |
| Định giá | Thường xem chi phí cluster + node resources và dịch vụ liên quan | Thường xem chi phí cluster + resources workload theo mô hình được áp dụng |
| Phù hợp | Cần kiểm soát hạ tầng hoặc tính năng bị Autopilot hạn chế | Phần lớn workload Kubernetes chuẩn, muốn giảm vận hành node |

**Lưu ý hiện hành:** GKE có thể chạy workload Autopilot trong một Standard cluster bằng ComputeClass khi cấu hình phù hợp. Vì vậy không nên hiểu mô hình này chỉ gồm hai lựa chọn loại trừ hoàn toàn. Với tổ chức mới, Autopilot thường là phương án cần đánh giá trước nếu không có yêu cầu node đặc biệt.

### Ví dụ Kubernetes Deployment cho Java API

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/example-project/apps/orders-api:release-12
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
~~~

Manifest giả định Spring Boot có endpoint readiness và liveness được bật và được bảo vệ phù hợp. Để triển khai hoàn chỉnh còn cần namespace, Kubernetes Service/Gateway hoặc Ingress, Workload Identity Federation for GKE, Artifact Registry access, cấu hình network và các policy cần thiết.

### Giá phải trả của sự linh hoạt

Mọi thứ từ Pod scheduling đến resource quotas, autoscaling và upgrade windows cần có owner. Khi chỉ vận hành hai API nhỏ, một cluster riêng có thể tạo operational overhead không đáng có. Tuy nhiên, khi có nhiều team và workload cùng chia sẻ cluster, năng lực orchestration và khả năng tiêu chuẩn hóa có thể mang lại lợi ích lớn.

## 5. Cloud Run: workload serverless không cần quản lý cluster

Cloud Run chạy ứng dụng container hóa hoặc source được build thành container trên hạ tầng do Google quản lý. Với ứng dụng web/API, **Cloud Run services** thường là điểm bắt đầu hợp lý vì nhóm chủ yếu cung cấp image, cấu hình CPU/memory, concurrency, min/max instances, ingress, identity và các kết nối cần thiết.

Cloud Run hiện có nhiều kiểu tài nguyên:

| Loại tài nguyên | Mục tiêu chính | Mẫu sử dụng |
|---|---|---|
| Services | Nhận request HTTP/gRPC hoặc sự kiện được chuyển thành request | REST API, webhook, frontend/backend web |
| Jobs | Chạy tác vụ có điểm bắt đầu/kết thúc, có thể chia nhiều task | ETL, migration, batch report, xử lý theo lịch qua Scheduler/Workflows |
| Worker pools | Xử lý nền liên tục/pull-based thay vì chờ HTTP request | Consumer hàng đợi hoặc event stream lâu dài |
| Instances | Trường hợp cần một instance được quản lý độc lập | Workload đặc biệt, không phải lựa chọn API phổ thông |

### Những lợi thế chính

- Không cần tạo hoặc quản lý Kubernetes cluster hay VM.
- Deployment từ container image, revision để kiểm tra/rollback và chia traffic.
- Có thể scale theo lưu lượng với request-driven services; service có thể về 0 khi không cần instance giữ ấm.
- Dễ gắn runtime service account, Secret Manager, Cloud Logging/Monitoring/Trace.
- Phù hợp API Java/Spring Boot stateless, webhook và event-driven integration.

### Cần hiểu giới hạn vận hành

- Không được tùy chỉnh host OS/kernel theo cách của VM.
- Thiết kế container để khởi động và phục vụ theo hợp đồng runtime của Cloud Run.
- Filesystem cục bộ của instance không nên được xem là nơi lưu state bền vững; dùng Cloud Storage, Cloud SQL, Spanner, Firestore hoặc dịch vụ phù hợp.
- Với Cloud Run services, request có deadline; timeout mặc định 5 phút và có thể tăng đến tối đa 60 phút theo cấu hình hiện hành. Không dùng một request HTTP làm tác vụ vô hạn.
- Nếu workload cần liên tục lắng nghe hoặc poll nguồn ngoài khi không có request, cần đánh giá worker pools, min instances, instance-based billing hoặc kiến trúc queue/event thay vì giả định service scale từ 0 sẽ tự chạy lại không có request.
- Scale-to-zero giúp tiết kiệm trong nhiều mô hình, nhưng có thể gây cold start. Cấu hình minimum instances có thể giảm độ trễ đổi lại chi phí.

**Không nên kết luận Cloud Run không có GPU hoặc không chạy được background task.** Khả năng GPU và loại workload đã mở rộng; quyết định cụ thể vẫn phụ thuộc loại tài nguyên, quota, region, yêu cầu phần cứng và giới hạn được công bố.

### Ví dụ deploy Java container lên Cloud Run

Sau khi build image Spring Boot và push Artifact Registry:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/example-project/apps/orders-api:release-12" \
  --region="asia-southeast1" \
  --project="example-project" \
  --service-account="orders-runtime@example-project.iam.gserviceaccount.com" \
  --memory="1Gi" \
  --cpu="1" \
  --concurrency="40" \
  --min="0" \
  --max="20"
~~~

Đây là ví dụ minh họa, không phải cấu hình tối ưu cho mọi API. Tùy phiên bản CLI và mô hình autoscaling, hãy kiểm tra các cờ min/max tương ứng. Service chỉ nên nhận public traffic khi được cấp quyền invoker/ingress phù hợp; **không** mở public chỉ để kiểm thử.

Sau deploy, kiểm tra revision Ready, smoke test có authentication nếu cần, error rate, P95 latency và số connection database. Với database có giới hạn kết nối, cân nhắc tác động của số instance tối đa nhân với số connection mỗi instance.

### Billing không chỉ là số request

Cloud Run có lựa chọn billing theo request hoặc instance tùy loại/cấu hình workload. Chi phí còn phụ thuộc CPU, memory, thời gian hoạt động, minimum instances, GPU khi sử dụng, network và các dịch vụ phụ trợ. Không xem “scale to zero” đồng nghĩa “miễn phí”; số request nhiều, memory cao hoặc min instances có thể dẫn đến tổng chi phí đáng kể.

## 6. App Engine: nền tảng triển khai ứng dụng theo version

App Engine là nền tảng ứng dụng được quản lý với khái niệm service, version và traffic splitting. Hai môi trường của App Engine có hành vi khác nhau rõ rệt:

- **Standard environment:** dùng runtime do Google cung cấp, cấu hình theo app.yaml; tự động mở rộng theo chế độ scaling được chọn, hỗ trợ scale-to-zero trong trường hợp automatic scaling phù hợp.
- **Flexible environment:** chạy ứng dụng trong container trên VM được quản lý; hỗ trợ runtime tùy biến hơn, background process và SSH debugging; phiên bản đang hoạt động cần tối thiểu một instance, thường có thời gian startup/deploy lâu hơn Standard.

### So sánh Standard và Flexible

| Tiêu chí | App Engine Standard | App Engine Flexible |
|---|---|---|
| Runtime | Runtime được hỗ trợ theo lịch lifecycle | Runtime tích hợp hoặc custom runtime/container |
| Tùy chỉnh môi trường | Hạn chế hơn | Tùy chỉnh qua Dockerfile |
| Tác vụ background | Có giới hạn tùy runtime | Linh hoạt hơn với background process |
| Local filesystem | Không xem là durable storage; /tmp có phạm vi riêng | Có filesystem trên VM nhưng vẫn cần tách state bền vững |
| Startup | Thường nhanh hơn | Có thể cần thời gian khởi tạo VM/container |
| Scale to zero | Có thể với automatic scaling | Không, tối thiểu 1 instance của version đang phục vụ |
| Debug trực tiếp qua SSH | Không | Có |
| Đơn vị triển khai | Service/version theo app.yaml | Service/version theo app.yaml |

### App Engine có phù hợp cho Java/Spring không?

Có. App Engine Standard thế hệ runtime mới hỗ trợ Java hiện đại (ví dụ Java 21 hoặc Java 25 trong phạm vi runtime được hỗ trợ) và các framework tạo executable JAR như Spring Boot. Khả năng hỗ trợ cụ thể phải được xác nhận theo lịch lifecycle của runtime và phiên bản ứng dụng.

Ví dụ **app.yaml** tối giản cho Java 21 trên Standard:

~~~yaml
runtime: java21
instance_class: F2
automatic_scaling:
  min_instances: 0
  max_instances: 10
~~~

Ứng dụng phải tuân thủ hợp đồng runtime được chọn, bao gồm cách khởi động, lắng nghe cổng và quản lý trạng thái. Không sao chép trực tiếp file app.yaml này vào Flexible vì cấu hình machine resources/runtime và scaling khác nhau.

Triển khai một version:

~~~bash
gcloud app deploy app.yaml \
  --project=example-project \
  --quiet
~~~

App Engine có khả năng chia traffic giữa các version, hỗ trợ rollback bằng chuyển traffic, nhưng vẫn cần đánh giá migration database và các side effect khi quay về version trước.

### Khi giữ hoặc chọn App Engine

- Dự án đã chạy ổn định trên App Engine, dùng hệ thống service/version và các tích hợp sẵn.
- Ứng dụng web phù hợp với runtime và giới hạn của Standard.
- Đội ngũ muốn mô hình platform-centric ít thao tác cluster/VM.
- Flexible có thể phù hợp khi ứng dụng cần custom runtime nhưng vẫn muốn dùng workflow App Engine.

Đối với **ứng dụng mới**, nên so sánh Cloud Run trước vì container workflow thường linh hoạt cho CI/CD và có nhiều kiểu workload. Tuy vậy, không có quy tắc rằng mọi App Engine app cần chuyển ngay. Chi phí migration, tích hợp legacy, SLO và rủi ro vận hành có thể làm việc tiếp tục dùng App Engine trở thành lựa chọn hợp lý.

## 7. Quy trình ra quyết định thay vì chọn theo tên dịch vụ

Trước khi chọn nền tảng, nhóm kiến trúc cần ghi lại các ràng buộc thực tế:

1. Ứng dụng phục vụ HTTP/gRPC, chạy task theo lịch, tiêu thụ message liên tục hay cần process dài hạn?
2. Có cần quyền quản trị guest OS, kernel module, driver hoặc agent đặc thù không?
3. Ứng dụng có container hóa được không? Có cần Kubernetes operator, StatefulSet, DaemonSet hoặc service mesh không?
4. Lưu lượng ổn định hay thay đổi mạnh? Có yêu cầu khởi động nhanh hoặc duy trì instance nóng?
5. Trạng thái bền vững nằm ở đâu? Có thể dùng managed database/storage hay bắt buộc gắn disk trực tiếp?
6. Đội ngũ có khả năng quản trị VM/Kubernetes 24/7 không? Đang có platform team dùng chung không?
7. Yêu cầu bảo mật/tuân thủ có buộc kiểm soát OS, network, image hoặc data residency theo cách cụ thể không?
8. SLO về latency, availability, RTO, RPO và thời gian khôi phục khi deploy hỏng là gì?
9. Chi phí tính trên cả năm, cả nhân lực vận hành và các dịch vụ phụ trợ, có thể chấp nhận không?
10. Có cần di chuyển đa cloud, giữ lại cấu hình Kubernetes hoặc tương thích với runtime legacy không?

Một quy trình định hướng:

~~~mermaid
flowchart TD
    A["Xác định loại workload và SLO"]
    B{"Cần guest OS, kernel, driver đặc thù?"}
    C["Ưu tiên Compute Engine"]
    D{"Cần Kubernetes API, operator,<br/>sidecar hoặc scheduling phức tạp?"}
    E["Đánh giá GKE Autopilot/Standard"]
    F{"Ứng dụng web/API hoặc job<br/>chạy bằng container?"}
    G["Đánh giá Cloud Run"]
    H{"Đã phụ thuộc mô hình<br/>App Engine / app.yaml?"}
    I["Đánh giá App Engine Standard/Flexible"]
    J["So sánh chi phí, bảo mật, SLO,<br/>độ phức tạp và khả năng migration"]
    A --> B
    B -->|"Có"| C
    B -->|"Không"| D
    D -->|"Có"| E
    D -->|"Không"| F
    F -->|"Có"| G
    F -->|"Không"| H
    H -->|"Có"| I
    H -->|"Không"| C
    C --> J
    E --> J
    G --> J
    I --> J
~~~

Đây là **heuristic**, không phải sơ đồ ràng buộc tuyệt đối. Một job dài có thể chạy bằng Cloud Run Jobs, GKE Job, VM hoặc App Engine task architecture tùy giới hạn và mục tiêu. Một workload container cũng có thể chạy trên VM. Sau khi có phương án sơ bộ, phải xác minh quota/feature/region, làm proof-of-concept và đo dữ liệu thực tế trước khi quyết định.

### Ma trận đánh giá có trọng số

Một nhóm có thể chấm mỗi lựa chọn theo thang điểm 1–5 (5 là phù hợp nhất) với ràng buộc của mình. Ví dụ cho API Spring Boot **stateless**, lưu lượng tăng giảm, không cần Kubernetes:

| Tiêu chí | Trọng số gợi ý | Compute Engine | GKE | Cloud Run | App Engine |
|---|---:|---:|---:|---:|---:|
| Ít công sức vận hành | 30% | 2 | 3 | 5 | 4 |
| Co giãn theo tải | 20% | 3 | 4 | 5 | 4 |
| Phù hợp container hiện có | 20% | 4 | 5 | 5 | 3 |
| Ít cấu hình triển khai | 15% | 2 | 3 | 5 | 4 |
| Kiểm soát hạ tầng | 10% | 5 | 4 | 2 | 2 |
| Tận dụng kỹ năng đội ngũ | 5% | 3 | 2 | 4 | 3 |

**Các điểm số chỉ là minh họa**, không phải benchmark khách quan và không nên dùng nguyên xi cho dự án khác. Nhóm phải chấm lại dựa trên kỹ năng thực tế, ràng buộc network, trạng thái ứng dụng, SLO và báo giá. Trước tiên loại những phương án không đáp ứng ràng buộc bắt buộc, sau đó mới so sánh tổng điểm có trọng số.

## 8. So sánh scaling và khả năng sẵn sàng cao

Mở rộng không chỉ là “thêm instance”. Cần xem tín hiệu autoscaling, thời gian warm-up, giới hạn kết nối downstream, khả năng cân bằng tải và phương án phục hồi khi một zone/region lỗi.

| Chủ đề | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Đơn vị scale phổ biến | VM/MIG instance | Pod và node | Service instance, task hoặc worker theo loại tài nguyên | Instance/version |
| Tín hiệu scale | CPU, load balancing, Monitoring metric, lịch... với MIG | HPA, custom metrics, node autoscaler và các controller | Request/concurrency/CPU/backlog tùy loại workload và cấu hình | Chế độ automatic/basic/manual cùng tín hiệu phù hợp |
| Trách nhiệm warm-up | Startup script/process, health check | Image pull, startup/readiness probes | Image startup, concurrency và min instances | Runtime/version startup, min instances theo environment |
| Rolling update | MIG updater hoặc pipeline do nhóm tổ chức | Deployment controller, GitOps, progressive delivery | Revision và traffic split với services | Version và traffic split |
| HA | Regional MIG + LB, multi-zone và thiết kế state | Regional cluster/node/Pod topology, probes/PDB | Nền tảng quản lý provisioning, nhóm vẫn thiết kế availability của dependencies | Nền tảng quản lý instance, nhóm vẫn thiết kế dependencies |

### Cold start và request latency

Cloud Run services và App Engine Standard automatic có thể giảm tài nguyên khi không có traffic. Một request mới có thể cần khởi tạo instance; với Spring Boot, thời gian khởi động JVM, class loading, kết nối database và khởi tạo bean đều có ảnh hưởng. Có thể:

- Tối ưu startup, không tải dữ liệu lớn khi khởi động.
- Chọn concurrency phù hợp và tránh giữ nhiều connection không cần thiết.
- Sử dụng minimum instances khi SLO latency yêu cầu và cân nhắc chi phí.
- Dùng readiness/health và đo latency thực tế dưới tải.

GKE hoặc Compute Engine thường giữ một lượng capacity đang chạy để đáp ứng nhanh; tuy nhiên chúng cũng có thời gian scale-out khi cần thêm Pod/node/VM, không có nghĩa mọi đột biến đều được phục vụ ngay.

### Downstream bottlenecks

Một API với autoscaling rất mạnh có thể làm quá tải Cloud SQL hoặc dịch vụ thanh toán. Hãy ước lượng số connection tối đa:

~~~text
Total possible DB connections ≈ max instances/pods × max connections per instance
~~~

Ví dụ 20 Cloud Run instances, mỗi instance có HikariCP maximumPoolSize 10, có thể tạo đến khoảng 200 database connections nếu tất cả pool đều dùng tối đa. Tương tự, 40 Pod trên GKE với pool 10 có thể tạo đến 400 connections. Đây là **giới hạn lý thuyết theo cấu hình**, không phải số connection hiện tại; cần đo metrics và tính cả các client khác.

Không chọn platform chỉ dựa trên khả năng autoscale frontend. Phải kiểm tra database connection limits, queue, API quotas và rate limiting cho toàn bộ kiến trúc.

### Multi-zone và multi-region

- Compute Engine cần thiết kế regional MIG, load balancer, database HA và backup phù hợp.
- GKE cần chọn regional/zonal topology, Pod disruption, topology spread, volume location và cách failover.
- Cloud Run giảm công việc quản lý instance, nhưng tính sẵn sàng tổng thể vẫn phụ thuộc region/service configuration và dependencies; multi-region cần kiến trúc routing/failover riêng.
- App Engine quản lý version và instance trong phạm vi region của application, nhưng ứng dụng vẫn phải có chiến lược database, external API và disaster recovery.

**Availability của nền tảng không thay thế RTO/RPO của dữ liệu.** Dịch vụ có thể tiếp tục nhận request nhưng vẫn không hoàn tất tác vụ nếu database bị lỗi.

## 9. State, storage và background processing

Một ứng dụng được thiết kế như stateless API thường có nhiều lựa chọn runtime hơn ứng dụng ghi dữ liệu lâu dài vào local disk.

### State nên nằm ở đâu?

| Nhu cầu | Lựa chọn kiến trúc thường phù hợp |
|---|---|
| Quan hệ SQL | Cloud SQL hoặc dịch vụ database quản lý khác |
| Key-value/document | Firestore, Redis/Memorystore hoặc dịch vụ phù hợp |
| Object/file bền vững | Cloud Storage |
| Event/message | Pub/Sub hoặc queue phù hợp |
| Session web | External session store hoặc cookie/session token được bảo vệ |
| Local cache | Cache chỉ tăng hiệu năng, chịu được mất dữ liệu |
| File thao tác tạm | Filesystem tạm với giới hạn và cleanup rõ ràng |

Compute Engine và GKE có khả năng gắn persistent disk và chạy stateful application. Tuy nhiên, **có thể** chạy database trên VM/Pod không đồng nghĩa **nên** tự vận hành database nếu dịch vụ managed đáp ứng yêu cầu. Cần tính backup, replication, failover, patching, observability và kỹ năng DBA.

### Background jobs và consumers

| Nhu cầu | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Batch có điểm kết thúc | Process/VM/job scheduler | Kubernetes Job/CronJob | Cloud Run Jobs | Task architecture theo môi trường |
| HTTP API | VM+LB | Deployment+Service/Gateway | Cloud Run Service | App Engine Service |
| Consumer chạy liên tục | Daemon/process có supervisor | Deployment/StatefulSet | Worker pool hoặc service cấu hình phù hợp | Flexible hỗ trợ background process; Standard có hạn chế |
| Scheduler | OS/systemd timer/cron | CronJob | Cloud Scheduler kích hoạt Jobs/Workflows | Cloud Scheduler/cron service theo mô hình ứng dụng |
| Cần custom kernel/driver | Có thể | Standard với node phù hợp | Không kiểm soát host kernel | Không phải lựa chọn chính |

**Đừng giữ HTTP request mở hàng giờ để chạy công việc nền** nếu có thể tách thành queue + task worker. Mô hình producer → Pub/Sub → worker giúp cô lập timeout, retry, dead-letter, idempotency và scale độc lập với frontend. Trên Cloud Run, hãy xem xét Jobs hoặc worker pools tùy công việc có thời điểm kết thúc hay là consumer liên tục.

### Ví dụ kiến trúc thương mại điện tử kết hợp

~~~mermaid
flowchart LR
    U["Web / mobile clients"] --> LB["HTTPS entry"]
    LB --> API["Cloud Run<br/>Orders API"]
    API --> DB["Cloud SQL"]
    API --> PS["Pub/Sub"]
    PS --> W["GKE hoặc Cloud Run<br/>worker"]
    W --> ST["Cloud Storage"]
    W --> DB
    API --> SM["Secret Manager"]
    W --> SM
~~~

API HTTP có thể dùng Cloud Run vì stateless và lưu lượng biến động. Worker có thể dùng Cloud Run worker pool hoặc GKE, tùy yêu cầu xử lý liên tục, Kubernetes, sidecar và chi phí. Database và storage lưu state bền vững tách khỏi lifecycle instance.

Không sử dụng hai nền tảng chỉ vì hệ thống có hai thành phần. Nếu cả API và worker đều đáp ứng yêu cầu Cloud Run thì một nền tảng có thể giảm nhiều công việc quản trị. Ngược lại, nếu toàn bộ tổ chức có platform GKE chuẩn hóa, đặt cả hai thành phần trên GKE cũng có thể hợp lý.

## 10. Network, IAM và bảo mật

Khả năng truy cập API hoặc database riêng tư phụ thuộc cấu hình VPC, ingress/egress, identity, firewall và dịch vụ đích. Không thể kết luận “dịch vụ serverless luôn public” hoặc “GKE/VM luôn an toàn hơn”.

### Compute Engine

- Dùng firewall rules, network tags, service account và nguyên tắc không cấp external IP nếu không cần.
- Giới hạn SSH bằng IAM/OS Login/IAP khi phù hợp; không mở SSH toàn Internet.
- Cập nhật image/OS, cài monitoring agent và quản lý vulnerability.
- Hạn chế service account scopes/permissions theo chính sách, bảo vệ metadata credentials.

### GKE

- Cấu hình Kubernetes RBAC, namespace, NetworkPolicy và workload security.
- Dùng Workload Identity Federation for GKE thay khóa JSON service account trong Pod.
- Quét container image, kiểm soát admission/policy và quyền service account.
- Tách trách nhiệm cluster-admin khỏi quyền deploy ứng dụng trong namespace.
- Thiết kế private cluster/endpoints/egress khi cần.

### Cloud Run

- Gắn runtime service account với quyền tối thiểu.
- Quyết định ingress public/internal, yêu cầu IAM invoker và identity token cho service-to-service.
- Chọn Direct VPC egress hoặc phương án kết nối VPC phù hợp, kiểm tra firewall/network route.
- Dùng Secret Manager và tránh đưa secret vào image hoặc source.
- Giới hạn max instances để không gây quá tải dependency.

### App Engine

- Sử dụng service account đúng scope của ứng dụng/version.
- Bảo vệ endpoint, cấu hình quyền truy cập và kiểm tra integration với VPC.
- Kiểm tra hạn chế của runtime Standard hoặc quyền/config của Flexible.
- Quản lý secret, dependency và việc hiển thị lỗi/log tương tự mọi platform khác.

### Mẫu phân quyền chung

| Principal | Quyền cần thiết | Không nên cấp mặc định |
|---|---|---|
| CI build identity | Đọc source, push Artifact Registry, deploy đến target | Quyền sửa dữ liệu nghiệp vụ production |
| Runtime identity | Đọc secret và gọi database/API cần thiết | Owner/Editor hoặc quyền deploy |
| Người vận hành | Đọc logs/metrics, thực hiện runbook theo vai trò | Toàn quyền trên mọi project |
| Security auditor | Đọc audit logs/cấu hình được cho phép | Quyền sửa runtime nếu không cần |

Mọi nền tảng cần kế hoạch xoay vòng secret, kiểm soát software supply chain, theo dõi hoạt động quản trị và kiểm chứng backup/recovery. Sự khác biệt lớn là nhóm phải tự áp dụng các kiểm soát này ở lớp VM, Kubernetes hay service configuration.

## 11. CI/CD, rollout và rollback

Một kiến trúc vận hành tốt không chỉ “deploy được” mà còn **biết phiên bản nào đang chạy, đo tác động sau deploy và quay lại phiên bản trước khi cần**.

| Platform | Artifact chính | Triển khai | Cơ chế rollback thường dùng |
|---|---|---|---|
| Compute Engine | VM image, package hoặc container image | Startup script, automation, MIG rolling update | MIG rollback về instance template đã kiểm thử hoặc cập nhật image |
| GKE | Container image digest + manifest | kubectl, Helm, GitOps, Cloud Deploy | Rollout undo hoặc khôi phục Git/manifest/image, kiểm tra Pod Ready |
| Cloud Run | Container image digest + revision config | gcloud run deploy/Cloud Deploy | Chuyển traffic về revision ổn định |
| App Engine | Source/runtime version hoặc container theo môi trường | gcloud app deploy | Chuyển traffic về version trước |

### Build once, promote many

Nên xây artifact một lần trong CI, quét và kiểm thử rồi promote cùng image digest qua staging và production. Không build lại trên mỗi môi trường nếu không cần, vì image có thể khác nhau do dependency/base image thay đổi.

Ví dụ một container image Java:

~~~text
asia-southeast1-docker.pkg.dev/example-project/apps/orders-api@sha256:IMAGE_DIGEST
~~~

Đây là đường dẫn minh họa; IMAGE_DIGEST cần thay bằng digest thực tế. Artifact Registry hỗ trợ tham chiếu theo digest để xác định đúng nội dung triển khai. Khi rollout, lưu mapping giữa commit SHA, Cloud Build ID, artifact digest và revision/Deployment.

### Health checks và rollout gates

- **Compute Engine:** health check của load balancer/MIG và smoke test ứng dụng.
- **GKE:** startup/readiness/liveness probes, rollout status và SLI của từng release.
- **Cloud Run:** revision Ready, smoke test với authentication, gradual traffic split.
- **App Engine:** health/traffic metrics, chuyển tỷ lệ traffic giữa các version khi phù hợp.

Một deployment trả exit code 0 không đủ để coi release thành công. Phải quan sát request latency, error rate, luồng nghiệp vụ, database metrics và saturation trong cửa sổ thời gian đủ đại diện.

### Database migrations

Rollback runtime **không** đồng nghĩa rollback data/schema. Áp dụng chiến lược **expand-and-contract**: thêm cấu trúc mới theo cách tương thích, deploy code đọc được cả schema cũ/mới, chuyển dữ liệu, rồi chỉ xóa trường cũ sau khi không còn instance/consumer phụ thuộc. Điều này quan trọng với mọi platform, nhất là Cloud Run traffic split hoặc GKE rolling update khi hai phiên bản có thể chạy đồng thời.

## 12. Chi phí: đừng so sánh chỉ bằng đơn giá máy

Một thiết kế rẻ về CPU có thể đắt về vận hành hoặc mạng; một thiết kế có chi phí resource cao hơn có thể giảm đáng kể công sức quản trị. Đánh giá **Total Cost of Ownership (TCO)** thay vì chỉ tính “1 vCPU/1 GB RAM”.

Các thành phần cần ước tính:

~~~text
TCO =
  compute / runtime charges
  + storage / persistent disks
  + network egress / load balancing / NAT
  + logs / metrics / tracing
  + databases / cache / messaging / secrets
  + CI/CD, artifact và bảo mật
  + nhân lực vận hành / sự cố / nâng cấp
~~~

| Platform | Các điểm dễ bị bỏ sót khi tính |
|---|---|
| Compute Engine | VM luôn chạy dù ít request, boot disks, snapshots, OS license, LB và thời gian patching |
| GKE Standard | Cluster và node capacity chưa sử dụng hết, overprovision requests, network/ingress/storage, người vận hành |
| GKE Autopilot | Resources workload yêu cầu, cluster charges, tính năng và giới hạn theo loại Pod, network/storage |
| Cloud Run | Min instances, cấu hình CPU/memory, concurrency, request count, instance-based billing, network/VPC và downstream |
| App Engine Standard | Instance class và scaling, các version giữ traffic, dịch vụ phụ trợ và network |
| App Engine Flexible | VM resources/instance tối thiểu, startup, storage/network và quản lý version |

### Ví dụ so sánh định tính

**Workload A:** 10 request/phút vào ban đêm, 1.000 request/phút trong 15 phút giữa ngày, stateless Spring API, không cần OS tùy chỉnh. Cloud Run có thể tận dụng autoscaling, kể cả scale-down khi ít tải; VM hoặc cluster luôn giữ capacity có thể kém hiệu quả nếu chưa được dùng chung cho workload khác.

**Workload B:** 100 microservices chạy liên tục với traffic ổn định, nhiều team đã có platform engineering và Kubernetes chung. GKE Standard hoặc Autopilot có thể có lợi thế từ chia sẻ nền tảng, orchestration và khả năng tối ưu resource; Cloud Run vẫn cần được đánh giá theo toàn bộ workload, không thể mặc định đắt hơn.

**Workload C:** Java legacy có dịch vụ TCP tùy chỉnh, hệ thống agent native và yêu cầu kernel cụ thể. Compute Engine có thể giảm chi phí refactor ban đầu dù vận hành VM lớn hơn. Chọn Cloud Run chỉ vì bill thấp mà sau đó phải viết lại ứng dụng nhiều tháng có thể không tối ưu TCO.

Không đưa con số tiền giả định vào dự toán chính thức. Hãy dùng bảng giá cập nhật, Google Cloud Pricing Calculator hoặc báo giá tổ chức, với dự đoán request, runtime, memory/CPU, egress, tần suất deploy và SLO cụ thể.

### Phép đo giúp quyết định

1. Đo requests/second theo giờ, percentile latency, CPU/memory và tần suất idle.
2. Ước lượng số replica/instance cần cho peak.
3. Kiểm tra cold-start, database connection và autoscaling under load.
4. Tính chi phí storage/network/LB/NAT/observability, không chỉ runtime.
5. Tính thời gian thao tác định kỳ: security patches, cluster upgrades, troubleshooting.
6. Chạy pilot trong môi trường thử nghiệm để đo số liệu trước khi cam kết kiến trúc lâu dài.

## 13. Tính di động và rủi ro phụ thuộc nền tảng

**Di động ứng dụng** có nhiều cấp độ:

- **Mã nguồn Java/Spring Boot** có thể chạy trên nhiều nền tảng nếu tránh gắn logic nghiệp vụ với API runtime.
- **Container image OCI** thường có thể tái sử dụng trên Cloud Run, GKE hoặc VM chạy container, nhưng service configuration khác nhau.
- **Kubernetes manifests** có tính chuẩn hóa, nhưng StorageClass, LoadBalancer, ingress, Workload Identity hoặc custom controller có thể phụ thuộc provider.
- **VM images** cho phép di chuyển một phần workload, nhưng kernel, network, disk, bootstrap và vận hành khác nhau.
- **App Engine app.yaml** và service/version workflow có mức gắn với platform; di chuyển sang Cloud Run/GKE có thể cần chuyển cấu hình.

Tính di động không đồng nghĩa chi phí migration bằng 0. Cơ sở dữ liệu, service account, Cloud Logging/Monitoring, event contracts và network thường là các điểm cần tái thiết kế khi di chuyển.

### Tách phần nghiệp vụ khỏi hạ tầng

Ví dụ Spring Boot nên gọi các interface như OrderRepository, PaymentGateway và EventPublisher; implementation bên dưới sử dụng Cloud SQL, Pub/Sub hoặc một backend khác. Cấu hình lấy từ environment hoặc Secret Manager thay vì đặt cứng project ID/service URL.

Khi cần chuyển Cloud Run sang GKE:

1. Giữ nguyên image đã được kiểm thử nếu hợp đồng container phù hợp.
2. Chuyển service/secret configuration sang ConfigMap, Secret hoặc tích hợp Secret Manager phù hợp.
3. Chọn KSA và Workload Identity Federation cho GKE.
4. Khai báo Kubernetes Deployment/Service/Gateway, probes và requests/limits.
5. Thiết kế autoscaling và network.
6. Kiểm tra logs, trace, metrics và hành vi graceful shutdown.
7. Chuyển traffic theo giai đoạn và chuẩn bị rollback.

Ngược lại, từ GKE sang Cloud Run, cần loại bỏ những phần phụ thuộc cluster, node hoặc sidecar đặc biệt nếu Cloud Run không đáp ứng; dữ liệu trạng thái phải được đưa ra dịch vụ bền vững.

## 14. Sáu tình huống lựa chọn nền tảng

### Tình huống 1 — API mới bằng Spring Boot, tải thay đổi mạnh

Ứng dụng phục vụ HTTPS, stateless, database nằm ở Cloud SQL, team nhỏ và không có platform engineering.

**Ứng viên ưu tiên:** Cloud Run Service. Lý do: không quản lý VM/cluster, triển khai image, tự mở rộng theo request và có revision/traffic split. Cần kiểm tra cold start, concurrency, timeout và database connections.

**Khi đổi lựa chọn:** dùng GKE nếu công ty đã có cluster/platform chuẩn với chính sách và chi phí vận hành tốt, hoặc khi cần service mesh/operator đặc thù.

### Tình huống 2 — Hệ thống 30 microservices có GitOps và sidecar riêng

Đội ngũ cần nhiều namespace, custom resources, shared ingress, network policy, sidecar và GitOps.

**Ứng viên ưu tiên:** GKE. Đánh giá Autopilot trước nếu workload đáp ứng ràng buộc; chọn Standard khi cần quyền kiểm soát node hoặc tính năng Autopilot không cho phép. Cần xây platform ownership, cluster upgrades, quotas và ứng phó sự cố.

**Khi đổi lựa chọn:** nếu phần lớn service thực sự đơn giản và team không muốn duy trì Kubernetes, cân nhắc Cloud Run cho các service phù hợp.

### Tình huống 3 — Hệ thống kế toán legacy phụ thuộc OS

Ứng dụng Java đời cũ cần cài gói hệ thống, truy cập TCP đặc biệt, agent vendor và lịch maintenance cố định.

**Ứng viên ưu tiên:** Compute Engine, có thể kết hợp MIG hoặc các VM HA tùy trạng thái. Bắt đầu bằng lift-and-shift có kiểm soát, sau đó từng bước tách state và nâng cấp runtime.

**Khi đổi lựa chọn:** sau khi loại được phụ thuộc OS và container hóa ổn định, đánh giá GKE hoặc Cloud Run để giảm vận hành.

### Tình huống 4 — Web app đang chạy App Engine Standard

Ứng dụng có version/traffic split ổn định, tuân thủ runtime hỗ trợ, các nhóm vận hành đã quen với app.yaml và hệ thống chưa có yêu cầu mới ngoài platform.

**Ứng viên ưu tiên:** tiếp tục App Engine nếu SLO, security, lifecycle và chi phí còn phù hợp. Đặt kế hoạch nâng runtime đúng lịch hỗ trợ, đồng thời thử một prototype Cloud Run để hiểu chi phí migration.

**Khi đổi lựa chọn:** yêu cầu runtime/container linh hoạt hơn, chiến lược thống nhất artifact hoặc hạn chế của App Engine gây trở ngại cho phát triển.

### Tình huống 5 — Batch tạo báo cáo cuối ngày

Tác vụ bắt đầu theo lịch, chia lô dữ liệu, hoàn thành sau khoảng thời gian hữu hạn, không cần phục vụ HTTP.

**Ứng viên ưu tiên:** Cloud Run Jobs kết hợp Scheduler/Workflows nếu giới hạn runtime, quota và kết nối phù hợp; hoặc Kubernetes Job nếu tổ chức đã có GKE và cần scheduling/policy đặc thù.

**Khi đổi lựa chọn:** dùng Compute Engine/Batch hoặc workload GKE tương ứng nếu cần hardware, job duration, dependency hoặc orchestration không đáp ứng bằng Cloud Run Jobs.

### Tình huống 6 — Consumer thông điệp chạy liên tục

Một worker liên tục poll nguồn dữ liệu, có thể không nhận HTTP requests trong thời gian dài.

**Ứng viên ưu tiên:** Cloud Run worker pool hoặc GKE Deployment tùy cơ chế scaling, reliability và yêu cầu nền tảng. Nếu xử lý theo event có thể chuyển thành push request đến Cloud Run Service, cân nhắc mô hình đó để giảm công việc nền.

**Khi đổi lựa chọn:** Compute Engine có thể phù hợp với agent/driver đặc biệt, còn App Engine Flexible cần được kiểm tra nếu hệ thống legacy đã theo mô hình App Engine.

### Tình huống 7 — Một dịch vụ có yêu cầu xử lý dữ liệu nhạy cảm

Ứng dụng cần private connectivity, định danh workload, lưu dữ liệu trong region cụ thể và kiểm soát đường ra Internet.

**Ứng viên:** cả bốn nền tảng có thể đáp ứng một phần hoặc toàn bộ tùy yêu cầu cụ thể. Trước khi chọn, lập ma trận đáp ứng: ingress, egress, VPC, DNS, secret access, encryption, organization policies, logging và audit. Nếu bắt buộc host OS control, Compute Engine hoặc GKE Standard có lợi thế; nếu chỉ cần IAM và network bảo vệ đúng, Cloud Run/App Engine vẫn có thể phù hợp.

**Bài học:** không suy ra yêu cầu compliance chỉ từ tên nền tảng. Cần đối chiếu kiểm soát thực tế với quy định và cấu hình được cấp phép.

## 15. Các lỗi tư duy kiến trúc thường gặp

| Nhận định vội vàng | Vì sao dễ sai? | Cách đánh giá đúng hơn |
|---|---|---|
| Serverless luôn rẻ nhất | Min instances, request density, network và downstream có thể tạo chi phí đáng kể | Tính TCO với workload và chế độ billing thực tế |
| Kubernetes luôn chuyên nghiệp hơn | Vận hành cluster, YAML, RBAC, debugging có chi phí | Chọn GKE khi thật sự cần orchestration, policy hoặc ecosystem |
| VM luôn chậm đổi mới | MIG, image baking, IaC và automation hỗ trợ CI/CD mạnh | Đánh giá mức tự động hóa và ràng buộc của tổ chức |
| Cloud Run chỉ chạy HTTP API | Có Jobs, worker pools và các kiểu tài nguyên khác | Phân loại workload rồi kiểm tra tính năng hiện hành |
| GKE Autopilot giống Cloud Run | Autopilot vẫn dùng Kubernetes API/semantics và chịu ràng buộc Kubernetes | So sánh nhu cầu orchestration, Pod policy, node control |
| App Engine đã quá cũ nên phải xóa | Ứng dụng đang ổn định có thể có chi phí migration lớn | Đo SLO, runtime lifecycle, security và opportunity cost |
| Deploy thành công là ứng dụng đã khỏe | DB, queue, API ngoài và user journey có thể vẫn lỗi | Smoke test, SLI/alert và canary sau deploy |
| VM/container có disk thì dữ liệu đã bền vững | Local disk và instance lifecycle không bảo đảm business continuity | Thiết kế backup, replication, RPO/RTO và managed storage |
| Có autoscaling thì không cần capacity planning | Downstream quota hoặc connection pool vẫn có giới hạn | Load test hệ thống end-to-end và giới hạn tốc độ |
| Chạy một container ở hai nơi là hoàn toàn di động | IAM, ingress, storage, secret và logging khác nhau | Dùng adapter/config layer và thử nghiệm migration |

### Quy tắc ưu tiên ít vận hành nhưng không hy sinh yêu cầu

Một chiến lược hữu ích là **chọn mức trừu tượng cao nhất vẫn đáp ứng ràng buộc bắt buộc**. Nếu Cloud Run đủ khả năng chạy ứng dụng, không cần mặc định dựng Kubernetes. Nếu cần Kubernetes, xem xét Autopilot trước khi tự quản node. Nếu cần cấu hình OS/kernel, Compute Engine hoặc GKE Standard có thể hợp lý hơn. Với App Engine app đã ổn định, quyết định đổi platform nên dựa trên lợi ích rõ ràng chứ không dựa vào xu hướng.

Tuy nhiên, tính sẵn có của platform team và chuẩn tổ chức cũng là một ràng buộc. Một công ty đã có GKE platform dùng chung với dashboard, security policies, GitOps và SRE trực ca có thể triển khai service mới trên GKE rất nhanh mà không tăng nhiều chi phí biên. Ngược lại, một startup nhỏ sẽ không có cùng lợi thế đó.

## 16. Ghi lại quyết định bằng Architecture Decision Record

Trước khi triển khai production, nên tạo một **Architecture Decision Record (ADR)** ngắn, có thể kiểm tra lại sau khi giả định thay đổi.

Mẫu:

~~~markdown
# ADR: Chọn nền tảng chạy Orders API

## Bối cảnh
- Workload: Spring Boot REST API, stateless
- Traffic: trung bình / peak / idle
- SLO latency và availability:
- Data: Cloud SQL, Pub/Sub, Cloud Storage
- Đội vận hành, kỹ năng và on-call:
- Ràng buộc IAM / network / compliance:

## Phương án
1. Cloud Run
2. GKE Autopilot
3. GKE Standard
4. Compute Engine MIG
5. App Engine Standard/Flexible

## Ràng buộc bắt buộc
- ...

## Đánh giá
| Tiêu chí | Trọng số | Cloud Run | GKE | VM | App Engine |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

## Quyết định
- Nền tảng được chọn:
- Vì sao:
- Phương án bị loại và lý do:

## Rủi ro và biện pháp
- Cold start:
- Database connection:
- Security / IAM:
- Cost uncertainty:
- Rollback / DR:

## Cách xác minh
- Load test:
- Smoke test:
- Chi phí đo được:
- SLI/SLO trong giai đoạn thử nghiệm:

## Thời điểm đánh giá lại
- Sau 3 tháng hoặc khi nhu cầu kỹ thuật thay đổi đáng kể
~~~

ADR nên ghi **giả định và điều kiện đảo quyết định**. Ví dụ: “Chọn Cloud Run nếu P95 latency dưới 300 ms với min instances nhỏ hơn hoặc bằng 2 và chi phí tháng đạt ngân sách”. Khi lưu lượng tăng hoặc requirement đổi, nhóm có cơ sở để đánh giá lại mà không phải tranh luận theo cảm tính.

## 17. Bài tập thực hành: chọn platform cho ba ứng dụng

Giả sử tổ chức có ba dịch vụ:

| Ứng dụng | Đặc điểm | Ràng buộc |
|---|---|---|
| Orders API | Spring Boot, HTTP, stateless, tải dao động | Cần deploy nhiều lần/tuần, SLO latency |
| Billing worker | Xử lý message bất đồng bộ, thời gian chạy biến động | Retry, DLQ, có thể cần chạy liên tục |
| Legacy reporting | Java app cũ, cài native library và process OS riêng | Chưa thể refactor ngay, yêu cầu quyền trên guest OS |

Hãy thực hiện:

1. Ghi mục tiêu nghiệp vụ và SLI/SLO cho từng ứng dụng.
2. Phân loại workload (request-driven, task-driven, continuously running, stateful/legacy).
3. Liệt kê dependency: Cloud SQL, Pub/Sub, external API, filesystem, secret, network.
4. Xác định ràng buộc bắt buộc như custom kernel/driver hoặc Kubernetes-specific operator.
5. Lập shortlist giữa Compute Engine, GKE Autopilot/Standard, Cloud Run và App Engine.
6. Lập ma trận tối thiểu sáu tiêu chí, có trọng số và điểm được giải thích.
7. Với Orders API, thử deploy một container Spring Boot lên Cloud Run staging; ghi revision, image digest, startup time và request latency.
8. Với một workload phù hợp, dựng Deployment/Job mẫu trên GKE thử nghiệm (nếu có quyền), so sánh YAML, startup/rollout và công việc vận hành.
9. Với Legacy reporting, viết kế hoạch VM/MIG cùng OS patch, health check, backup và deployment automation.
10. Dùng Pricing Calculator hoặc báo giá cập nhật để ước tính chi phí theo traffic/CPU/memory/network của từng phương án.
11. Thiết kế security boundary: build identity, runtime identity, IAM, VPC, secret và database access.
12. Viết ADR nêu lựa chọn ban đầu, rủi ro, dữ liệu chưa biết và thời điểm xem lại.

### Kết quả mong đợi

- **Orders API:** Cloud Run thường là ứng viên đầu tiên nếu không có ràng buộc đặc biệt; cần xác minh cold start, concurrency và database connections.
- **Billing worker:** Cloud Run Jobs, worker pool hoặc GKE Job/Deployment tùy kiểu xử lý, thời gian và yêu cầu scaling.
- **Legacy reporting:** Compute Engine có thể là bước đầu ít refactor nhất, nhưng cần lộ trình tối ưu vận hành và nâng phiên bản.

Đây là định hướng từ đề bài, không phải đáp án duy nhất. Một bài làm tốt cần nêu vì sao lựa chọn còn phù hợp khi traffic, chi phí hoặc kỹ năng tổ chức thay đổi.

### Tiêu chí đánh giá

- Phân biệt đúng các môi trường App Engine và mode GKE.
- Không chọn dựa trên giá CPU đơn lẻ.
- Có SLO, chi phí, IAM, networking, data state và chiến lược rollback.
- Không nhầm các loại Cloud Run resource.
- Có kế hoạch kiểm chứng bằng thử nghiệm thay vì khẳng định không có dữ liệu.
- Ghi rõ ràng buộc bắt buộc, giả định và trade-off.

## 18. Checklist kiến trúc trước khi chốt nền tảng

- [ ] Đã mô tả loại workload: HTTP, event, batch, continuous worker hay legacy.
- [ ] Đã ghi SLI, SLO, RTO, RPO và yêu cầu peak traffic.
- [ ] Đã phân loại state bền vững và state tạm.
- [ ] Đã xác nhận nhu cầu kernel/OS/native driver hoặc Kubernetes API.
- [ ] Đã so sánh GKE Autopilot và Standard khi chọn GKE.
- [ ] Đã phân biệt App Engine Standard với Flexible.
- [ ] Đã kiểm tra Cloud Run services/jobs/worker pools theo nhu cầu.
- [ ] Đã kiểm tra region, quota, runtime support và giới hạn của platform.
- [ ] Đã xem xét service account, ingress/egress, VPC, IAM, secret và audit.
- [ ] Đã ước lượng cold start, concurrency và giới hạn database connections.
- [ ] Đã thiết kế deployment, health check, gradual rollout và rollback.
- [ ] Đã chuẩn bị observability: log, metric, trace, dashboard và alert.
- [ ] Đã tính network, storage, load balancer và dịch vụ phụ trợ trong chi phí.
- [ ] Đã tính công sức vận hành của OS/cluster/patching/on-call.
- [ ] Đã kiểm tra mức di động của image, manifests và cấu hình.
- [ ] Đã làm thử nghiệm tải/khả dụng với dữ liệu gần thực tế.
- [ ] Đã ghi ADR và điều kiện cần đánh giá lại quyết định.

## Câu hỏi tự kiểm tra

**1. Khác biệt chính giữa Compute Engine và Cloud Run là gì?**

Compute Engine cung cấp VM để nhóm quản lý guest OS và quá trình chạy; Cloud Run nhận workload container/source và quản lý provisioning hạ tầng. Đổi lại, Cloud Run hạn chế quyền can thiệp host OS/kernel nhưng giảm công việc vận hành VM.

**2. GKE Autopilot có khiến Kubernetes biến mất khỏi trách nhiệm đội ứng dụng không?**

Không. Autopilot quản lý phần lớn node infrastructure; nhóm vẫn dùng Kubernetes API, khai báo Pod/Deployment, probes, scaling policy, security và quyền truy cập của workload.

**3. Vì sao không nói mọi App Engine đều scale-to-zero?**

Vì App Engine có Standard và Flexible khác nhau. Standard automatic có thể về 0 trong các điều kiện phù hợp; Flexible cần ít nhất một instance cho version hoạt động.

**4. Cloud Run Service có phải lựa chọn duy nhất cho mọi background job không?**

Không. Cloud Run có Jobs cho task hữu hạn và worker pools cho consumer/pull workload. Ngoài ra có GKE Job/CronJob và các mô hình khác tùy yêu cầu.

**5. Tại sao một HTTP API có autoscaling mạnh vẫn có thể lỗi?**

Database, queue hoặc downstream API có quota và connection limit. Khi scale nhanh, tổng lưu lượng/connection từ tất cả instance có thể vượt capacity phụ thuộc.

**6. Khi nào Compute Engine phù hợp hơn GKE/Cloud Run?**

Khi ứng dụng cần kiểm soát OS/kernel, thư viện native, driver hoặc topology VM mà platform cao hơn không hỗ trợ; hoặc khi chi phí refactor vượt lợi ích trong giai đoạn đầu.

**7. Điều gì khiến hai container image giống hệt nhau trên Cloud Run và GKE có hành vi khác nhau?**

Các yếu tố như IAM, ingress/egress, timeouts, concurrency, CPU allocation, storage, probes, autoscaling và service configuration khác nhau giữa hai nền tảng.

**8. TCO khác giá runtime như thế nào?**

TCO bao gồm không chỉ compute mà cả storage, network, observability, CI/CD, security, backup, nhân lực vận hành và chi phí xử lý sự cố.

**9. Vì sao không nên tự động chuyển mọi App Engine app cũ sang nền tảng mới?**

Vì cần đánh giá runtime support, hiện trạng SLO, migration effort, dependency, chi phí và rủi ro. Một ứng dụng đang đáp ứng yêu cầu có thể tiếp tục chạy hiệu quả trên App Engine.

**10. Khi nào kiến trúc đa nền tảng hợp lý?**

Khi các workload có nhu cầu khác nhau rõ ràng và lợi ích của việc dùng nền tảng thích hợp vượt chi phí tích hợp, vận hành, bảo mật và observability giữa chúng.

## Tài liệu tham khảo

- [Google Cloud – Choose compute options](https://docs.cloud.google.com/docs/compute-area/choose-compute-options)
- [Compute Engine – Instance groups and Managed Instance Groups](https://docs.cloud.google.com/compute/docs/instance-groups)
- [GKE – GKE and Cloud Run](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run)
- [GKE – About modes of operation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode)
- [GKE – Autopilot and Standard feature comparison](https://docs.cloud.google.com/kubernetes-engine/docs/resources/autopilot-standard-feature-comparison)
- [GKE – Autopilot mode workloads in Standard clusters](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-autopilot-mode-standard-clusters)
- [Cloud Run – Deployment options and resource model](https://docs.cloud.google.com/run/docs/resource-model)
- [Cloud Run – Instance autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud Run – Request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Cloud Run – Minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [App Engine – Choose an environment](https://docs.cloud.google.com/appengine/docs/the-appengine-environments)
- [App Engine – Flexible versus Standard](https://docs.cloud.google.com/appengine/docs/flexible/flexible-for-standard-users)
- [App Engine Standard – Java runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime)
- [App Engine Standard – Runtime support schedule](https://docs.cloud.google.com/appengine/docs/standard/lifecycle/support-schedule)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
- [Google Cloud Architecture Framework](https://docs.cloud.google.com/architecture/framework)

## Kết luận

**Compute Engine, GKE, Cloud Run và App Engine không phải bốn mức nâng cấp tuyến tính**, mà là bốn mô hình vận hành với các trade-off khác nhau. Compute Engine cho quyền kiểm soát VM và OS; GKE cung cấp orchestration Kubernetes với lựa chọn Autopilot hoặc Standard; Cloud Run giúp chạy API, jobs và worker workloads mà không phải quản lý cluster; App Engine cung cấp mô hình ứng dụng service/version với Standard và Flexible.

Với ứng dụng Java/Spring Boot mới, stateless và không có yêu cầu đặc thù, Cloud Run thường đáng được đánh giá trước. Với hệ thống Kubernetes-native hoặc nhiều workload cần chính sách/chức năng orchestration, GKE là lựa chọn tự nhiên. Với ứng dụng legacy cần tùy chỉnh OS, Compute Engine có thể giảm chi phí chuyển đổi; với ứng dụng App Engine ổn định, giữ nguyên nền tảng đôi khi hợp lý hơn một cuộc migration vội vàng. Kết luận cuối cùng phải dựa trên **SLO, vận hành, IAM, dữ liệu, chi phí thực đo và khả năng khôi phục**, rồi được ghi lại bằng ADR để xem xét lại khi yêu cầu thay đổi.
