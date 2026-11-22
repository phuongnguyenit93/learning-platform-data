# Lựa chọn GKE Standard và GKE Autopilot

Một nhóm phát triển Java muốn chuyển dịch vụ đơn hàng từ Compute Engine sang Kubernetes để triển khai nhiều bản sao, cập nhật không gián đoạn và tự động mở rộng khi traffic tăng. Người quản trị đặt câu hỏi: **nên chọn GKE Standard hay GKE Autopilot?** Hai lựa chọn đều chạy Kubernetes trên Google Cloud, nhưng khác nhau về mức kiểm soát node, trách nhiệm vận hành, chính sách bảo mật mặc định, cách quản lý tài nguyên và cơ chế tính phí.

**Google Kubernetes Engine (GKE)** cung cấp Kubernetes được quản lý, với control plane do Google Cloud vận hành. **Standard** phù hợp khi tổ chức cần tự quản cấu hình và công suất node pool. **Autopilot** để Google Cloud quản lý phần lớn hạ tầng node, phân bổ tài nguyên theo yêu cầu workload và áp các kiểm soát được cấu hình sẵn. Tài liệu GKE hiện hành còn cho phép dùng **Autopilot ComputeClasses bên trong Standard cluster**, nên sự lựa chọn không nhất thiết là “toàn cluster chỉ một kiểu workload”.

Bài thuộc chương **GKE cơ bản** của học phần **CLOUD_PROVIDERS_GCP**. Qua những tình huống triển khai, người học sẽ kết nối GKE với tổ chức project, IAM, VPC, Compute Engine, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, theo dõi độ tin cậy và tối ưu chi phí.

Sau bài này, bạn có thể:

- Phân biệt **control plane**, **node**, **node pool**, **Pod**, **Deployment**, **Service** và mức Google Cloud quản lý ở mỗi mode.
- Chọn Standard hoặc Autopilot dựa trên nhu cầu quyền đặc biệt, phần cứng, vận hành, bảo mật, hiệu năng và ngân sách.
- Hiểu **cluster mode** và **workload mode** khác nhau thế nào; biết vai trò của **GKE ComputeClasses**.
- Tạo cluster lab bằng `gcloud`, kết nối bằng `kubectl` và triển khai một ứng dụng Java containerized.
- Lập kế hoạch `resources.requests`/`limits`, HPA, node autoscaling, vị trí chạy Pod và cập nhật phiên bản.
- Giải thích chi phí **node-based** so với **Pod-based**, kể cả trường hợp Autopilot dùng phần cứng đặc thù.
- Chuẩn bị phương án di chuyển workload, kiểm tra bảo mật/monitoring và xử lý Pod bị `Pending` hoặc `Rejected`.

> **Phạm vi:** các tên cluster, project và image bên dưới là ví dụ. Không chạy lệnh tạo cluster, Service loại LoadBalancer hoặc tài nguyên lưu trữ trên project production nếu chưa được phê duyệt. GKE, VM, IP, PersistentVolume, network egress và các dịch vụ khác có thể phát sinh chi phí.

## 1. GKE quản lý những thành phần Kubernetes nào?

Một cluster Kubernetes có **control plane** và tập **worker nodes**. Control plane nhận yêu cầu API, lưu trạng thái mong muốn, lập lịch và điều phối. Worker node chạy Pod; Pod chứa một hoặc nhiều container cùng mạng và không gian lưu trữ đã khai báo.

~~~mermaid
flowchart TD
  A["Developer / GitOps / kubectl"] --> B["GKE Kubernetes API"]
  B --> C["Control plane do Google quản lý"]
  C --> D{"Chọn mode vận hành"}
  D --> E["Standard: node pools do bạn cấu hình"]
  D --> F["Autopilot: GKE cấp và quản lý node"]
  E --> G["Kubernetes Pods"]
  F --> G
  G --> H["Service / Gateway / Ingress"]
  H --> I["Load Balancer / người dùng"]
  G --> J["Cloud SQL / Cloud Storage / Pub/Sub"]
~~~

Sơ đồ là khái niệm; cluster không nhất thiết có Internet-facing load balancer và Standard cluster có thể chạy cả Autopilot workloads thông qua ComputeClasses khi đáp ứng điều kiện hỗ trợ.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Cluster** | Đơn vị quản trị Kubernetes API, cấu hình mạng/bảo mật và tài nguyên | `orders-prod` |
| **Control plane** | API server, scheduler, controllers và trạng thái Kubernetes | GKE quản lý cả ở Standard lẫn Autopilot |
| **Node** | VM/hạ tầng chạy kubelet và Pods | Node của Compute Engine hoặc node do Autopilot quản lý |
| **Node pool** | Nhóm node chung cấu hình, machine type, autoscaling | `general-pool` trong Standard |
| **Pod** | Đơn vị workload nhỏ nhất được scheduling | Một container API Java |
| **Deployment** | Quản lý số replica và rollout Pods | `orders-api`, 3 replicas |
| **Service** | Cấp địa chỉ ổn định và phân phối lưu lượng tới Pods | `ClusterIP` hoặc `LoadBalancer` |
| **Ingress/Gateway** | Điều phối HTTP(S) tới service theo host/path | API với TLS qua load balancer |
| **HPA** | Thay đổi số Pod replicas theo metric | Từ 2 lên 10 Pods |

**Điểm quan trọng:** GKE không vận hành code Java, tối ưu SQL hoặc tạo backup cơ sở dữ liệu thay bạn. Bạn vẫn chịu trách nhiệm image, cấu hình container, access control, workloads, release, SLO và phụ thuộc dữ liệu cho cả hai mode.

## 2. GKE Standard: kiểm soát node pools và hạ tầng

Với **Standard cluster**, người quản trị chủ động chọn và cấu hình node pools: machine family, loại VM, kích thước, disk, GPU, vùng đặt node, chiến lược autoscaling và nhiều thiết lập Kubernetes/node-level khác. GKE vẫn quản lý control plane, có thể tự động repair/upgrade node theo các cấu hình đã bật, nhưng **bạn quản lý cấu hình và hiệu quả sử dụng công suất node**.

~~~text
GKE Standard cluster
  ├── Control plane (Google quản lý)
  ├── Node pool: web-pool
  │     ├── VM e2-standard-4
  │     └── VM e2-standard-4
  ├── Node pool: batch-pool
  │     └── VM spot / machine family phù hợp
  └── Deployments, Services, HPA, Policies
~~~

Standard phù hợp khi:

- Cần quản lý **machine type, image, node labels/taints, boot disk, custom node settings** rất chi tiết.
- Có **DaemonSet** hoặc workload đòi hỏi đặc quyền/host access không tương thích ràng buộc Autopilot.
- Cần tối ưu chi phí ở mức **node pool, reservation, committed use discount**, packing và baseline VM.
- Có ứng dụng legacy, networking hoặc storage phụ thuộc cấu hình node đặc thù.
- Đội platform/SRE có quy trình vận hành cluster/node và chấp nhận trách nhiệm capacity planning.

**Đánh đổi:** VM được cấp cho Standard node pool vẫn có thể bị tính phí khi đang chạy **dù Pod sử dụng ít tài nguyên**. Thiết kế node pool quá lớn, min-nodes cao hoặc Pod requests quá thấp dễ gây lãng phí; ngược lại thiếu node hoặc quota khiến Pods Pending.

### Standard không đồng nghĩa “mọi việc đều thủ công”

GKE Standard vẫn hỗ trợ **node auto-upgrade, node auto-repair, cluster autoscaler, HPA, release channels, managed control plane** và nhiều tính năng tự động khác. Sự khác biệt cốt lõi là **khả năng và trách nhiệm cấu hình nhiều thành phần hơn** chứ không phải GKE từ chối quản lý hạ tầng.

## 3. GKE Autopilot: tập trung khai báo workload

Với một **dedicated Autopilot cluster**, Google Cloud quản lý node infrastructure, node provisioning/scaling, bin packing và áp nhiều cấu hình về bảo mật, độ tin cậy và cập nhật theo khuyến nghị. Bạn khai báo **Pods, CPU/memory requests, volumes, policies, networking và ứng dụng**; GKE quyết định cấp node phù hợp.

~~~text
GKE Autopilot cluster
  ├── Control plane (Google quản lý)
  ├── Managed node infrastructure (GKE điều phối)
  │     └── Nodes được tạo theo Pods và ComputeClasses
  ├── Deployment: orders-api replicas=3
  ├── requests: CPU / memory / ephemeral storage
  └── Services, HPA, Policies, Observability
~~~

Autopilot thường phù hợp khi:

- Web APIs, microservices, background workers, batch jobs chạy trong **container không đòi hỏi host privilege**.
- Muốn giảm thời gian quản trị node pool, upgrade, scaling và bin packing.
- Đội phát triển muốn tập trung Kubernetes manifests, CI/CD, GitOps và SLO.
- Ưu tiên một tập **bảo mật mặc định** được kiểm soát chặt chẽ.
- Khối lượng workload thay đổi và mong muốn chi phí gắn với tài nguyên workload thực sự yêu cầu.

**Autopilot không phải Cloud Run.** Bạn vẫn quản lý Kubernetes resources, namespace, Service, HPA, deployment và network policies. Cloud Run có mô hình triển khai ứng dụng trừu tượng hơn; nếu chỉ một HTTP service đơn giản không cần đặc điểm Kubernetes, nên so sánh cả Cloud Run trước khi tạo GKE cluster.

### Giới hạn của Autopilot không phải “không dùng được GPU”

Autopilot hỗ trợ một số GPU, TPU, Arm, machine series và ComputeClasses theo tài liệu/region/version. Khi cần **phần cứng cụ thể**, GKE có thể tạo node tương ứng và áp **node-based billing** với premium quản lý Autopilot; không phải mọi Autopilot workload đều được tính theo Pod requests. Cần kiểm tra tính năng và quota cho loại phần cứng được chọn.

## 4. So sánh Standard và Autopilot theo tiêu chí kỹ thuật

| Tiêu chí | **Standard** | **Autopilot** |
|---|---|---|
| Control plane | Google Cloud quản lý | Google Cloud quản lý |
| Worker nodes | Bạn định nghĩa node pools và policy; GKE hỗ trợ repair/upgrade/scaling | Google Cloud cấp và quản lý node tương ứng workload |
| Machine type / disk | Điều khiển trực tiếp, linh hoạt | Khai báo qua workload/ComputeClass và khả năng hỗ trợ |
| Node count | Node pool size và cluster autoscaler | GKE điều chỉnh node infrastructure theo Pod demand |
| Kubernetes Pods / Services | Developer/platform quản lý | Developer/platform quản lý |
| Bảo mật mặc định | Nhiều cài đặt linh hoạt, cần hardening chủ động | Nhiều guardrails và ràng buộc tự động |
| Privileged containers / host access | Có thể dùng theo chính sách và quyền của cluster | Thường bị giới hạn; có ngoại lệ được hỗ trợ cho partner/system |
| Tối ưu chi phí | Quản lý node utilization, packing, CUD/Spot | General-purpose Pod-based; phần cứng đặc thù node-based |
| Thay đổi hệ điều hành/node | Chủ động hơn | Không có toàn quyền SSH/quản trị node như Standard |
| Autoscaling Pods | Tự cấu hình HPA/VPA hoặc controller tương ứng | Vẫn phải thiết kế HPA/VPA để điều chỉnh số Pod |
| Regional/HA | Có thể chọn kiến trúc zonal hoặc regional | Autopilot cluster được thiết kế theo mô hình regional được quản lý |
| Quota và giới hạn | Node/CPU, IP/Pod, API quotas, storage, LB | Pod requests, resource bounds, quota và giới hạn scheduling |
| Vận hành | Kiểm soát cao, công sức platform lớn hơn | Kiểm soát node ít hơn, công sức platform giảm |

**Không có mode luôn rẻ hơn hoặc nhanh hơn trong mọi trường hợp.** Một Standard cluster có các VM được sử dụng hiệu quả và chiết khấu mạnh có thể cạnh tranh về chi phí. Một Autopilot cluster có requests cao, nhiều replica luôn chạy hoặc yêu cầu GPU chuyên dụng có thể đắt hơn dự tính.

## 5. Phân biệt cluster mode và workload mode trong GKE mới

Nhiều tài liệu cũ trình bày GKE theo hai hộp tách biệt: **Standard cluster** và **Autopilot cluster**. Trong tài liệu GKE hiện hành, có thêm khái niệm **Autopilot mode cho workload trong Standard cluster** thông qua **ComputeClasses**.

| Cấu hình | Workloads nào chạy? | Ai quản lý nodes? |
|---|---|---|
| **Dedicated Autopilot cluster** | Chỉ Autopilot workloads | GKE quản lý các nodes |
| **Standard cluster thông thường** | Standard workloads theo node pools bạn tạo | Platform quản lý thiết lập node pools |
| **Standard cluster có Autopilot ComputeClass** | Standard workload + những Pods chọn Autopilot class | GKE quản lý node của Autopilot workloads; platform quản node pools còn lại |
| **Standard cluster cấu hình Autopilot mặc định** | Phần lớn workloads dùng Autopilot theo cấu hình default, có khả năng override | Tùy ComputeClasses và cấu hình cluster |

**Điều kiện phiên bản:** chạy workload Autopilot trong Standard cluster cần một phiên bản GKE hỗ trợ và các điều kiện mạng/bảo mật tương ứng; tài liệu nêu mức tối thiểu cho Autopilot ComputeClasses là **GKE 1.34.1-gke.1829001**, còn một số tính năng mới như đặt Autopilot class mặc định/toàn cluster cần phiên bản mới hơn. Không giả định mọi cluster Standard đã tạo từ lâu hỗ trợ ngay khi gán một label.

**Cluster mode có tính lâu dài:** khi tạo dedicated Autopilot cluster, các cài đặt Autopilot bắt buộc là **bất biến**; bạn không thể đơn giản chuyển cluster đó sang dedicated Standard bằng cách tắt một flag. Muốn thay mode hoặc các đặc tính bất biến thường phải tạo cluster mới, triển khai/migrate workload và chuyển traffic có kiểm soát.

### ComputeClass là gì?

**GKE ComputeClass** là custom Kubernetes resource khai báo các phương án tính toán (ví dụ machine series, Spot, fallback, accelerator hoặc Autopilot container-optimized compute platform), giúp workload chọn profile thay vì hardcode chi tiết node.

Một số **built-in Autopilot ComputeClasses** như `autopilot` và `autopilot-spot` được GKE cung cấp theo phiên bản phù hợp. Autopilot cluster dùng cơ chế này cho general-purpose workloads mặc định; Standard cluster có thể cho những Pod tương thích chọn ComputeClass để GKE quản node riêng cho chúng.

**Không phải chỉ gắn `cloud.google.com/compute-class: autopilot` là đủ**: cluster cần đáp ứng version, VPC-native networking, Shielded GKE Nodes và các điều kiện hệ thống liên quan. Có thể cần ít nhất một Standard node pool không có taints cho system Pods không chạy trên Autopilot-managed nodes. Kiểm tra tài liệu trước khi áp vào Standard production.

## 6. Phân chia trách nhiệm vận hành

| Việc vận hành | Standard | Autopilot |
|---|---|---|
| Kubernetes API/control plane availability | Google Cloud | Google Cloud |
| Quy hoạch node pool và machine type | Platform | Chủ yếu GKE; platform chọn ComputeClass/hardware khi cần |
| Patching/upgrade node OS | Platform cấu hình auto-upgrade và chịu trách nhiệm chính sách | GKE tự quản nhiều bước hơn |
| Autoscaler cho node | Platform bật/đặt giới hạn và theo dõi | GKE điều chỉnh theo Pod demand |
| App image, Java runtime, dependencies | Application team | Application team |
| K8s Deployment/Service/HPA | Application/platform | Application/platform |
| IAM, Workload Identity, secrets | Application/platform | Application/platform |
| VPC, ingress/egress, DNS, LB, firewall | Platform/network | Platform/network, trừ phần tự động do GKE cấp |
| Backups, persistent data, migration | Application/data platform | Application/data platform |
| SLO, release, runbook, security incidents | Application/SRE | Application/SRE |
| Quota, cost allocation, budgets | FinOps/platform | FinOps/platform |

Autopilot giảm phần việc liên quan **node**, không loại bỏ trách nhiệm thiết kế backend của ứng dụng. Nếu Cloud SQL chỉ có một instance không HA hoặc API không có readiness probe, chạy trên Autopilot cũng không tự làm ứng dụng chịu lỗi.

## 7. Lựa chọn dựa trên 5 câu hỏi thực tế

1. **Workload có cần quyền đặc biệt trên host không?** Nếu bắt buộc dùng privileged containers, host namespaces, unsafe sysctls, tùy biến kernel hoặc agent bảo mật không được Autopilot hỗ trợ, ưu tiên Standard hoặc giải pháp thay thế. Xác minh chính sách đối với các partner DaemonSets được Autopilot cho phép.
2. **Có cần chọn máy cụ thể, reservation hoặc GPU/TPU?** Standard cho phép kiểm soát node pool trực tiếp; Autopilot cũng có phần cứng chuyên dụng qua các khả năng được hỗ trợ nhưng cơ chế chi phí có thể khác.
3. **Có đội platform vận hành Kubernetes đủ năng lực?** Nếu nguồn lực ít và workloads phù hợp, Autopilot giảm khối lượng vận hành đáng kể.
4. **Khối lượng tài nguyên dự đoán được không?** Baseline node cao nhưng utilization tốt, có CUD: Standard đáng tính toán. Nhiều Pod nhỏ, tải biến động: so sánh Autopilot Pod-based billing.
5. **Chính sách tổ chức yêu cầu gì?** Hãy kiểm tra IAM, network, compliance, version/channel, private access, quota và data residency trước khi chốt mode.

### Ma trận chọn nhanh

| Tình huống | Lựa chọn ban đầu | Vì sao |
|---|---|---|
| API Java stateless, triển khai nhanh, ít người vận hành nodes | **Autopilot** | Tập trung app và giảm node operations |
| Đội platform cần privileged DaemonSet/host access đặc thù | **Standard** | Cần cấu hình node và Pod sâu hơn |
| Nhiều web services nhỏ, autoscale theo giờ | **Autopilot** | Tính phí theo Pod requests cho general-purpose workload |
| Cluster chạy hệ thống legacy gắn chặt loại kernel/node | **Standard** | Tương thích hạ tầng, kiểm soát node |
| Standard cluster hiện hữu có vài service không cần node đặc thù | **Autopilot ComputeClass trong Standard**, khi đủ điều kiện | Dùng kết hợp hai mode theo workload |
| GPU training/batch | **Đánh giá cả hai** | Kiểm tra availability, loại accelerator, quota và node-based billing |
| Dev lab ngắn hạn | **Tùy mô hình chi phí và lab** | Cluster fee và node/Pod usage vẫn phát sinh |
| Yêu cầu zero node khi không có workload | **Đánh giá cluster/version và Autopilot** | Không đồng nghĩa toàn bộ chi phí bằng 0 |

**Tránh kết luận máy móc:** “production luôn cần Standard” là sai; GKE khuyến nghị Autopilot cho đa số workloads production tương thích. “Autopilot không dùng được GPU/DaemonSet” cũng không chính xác nếu nói tuyệt đối; phải xem phần cứng và các hạn chế/ngoại lệ hiện hành.

## 8. Chuẩn bị project và cấu hình cluster lab

Một cluster lab cần:

- Google Cloud project đã gắn billing, bật **Kubernetes Engine API** (`container.googleapis.com`).
- IAM thích hợp cho người tạo cluster, ví dụ `roles/container.clusterAdmin` theo phạm vi; quyền mạng/service account nếu cấu hình riêng.
- Region/zone có sẵn GKE và quota; chọn ví dụ `asia-southeast1` với zone `asia-southeast1-a`, nhưng kiểm tra máy/region thực tế.
- VPC/subnet, Secondary IP ranges cho Pods/Services nếu dùng mạng cấu hình riêng; cân nhắc **VPC-native cluster**.
- Cloud SDK có `gcloud`, `kubectl`, **gke-gcloud-auth-plugin** và quyền kết nối control plane.
- Dự toán chi phí: cluster management fee, Standard nodes hoặc Autopilot Pods/nodes, disk, load balancer, IP, egress và logging.

### Tạo Autopilot cluster mẫu

~~~bash
PROJECT_ID="my-gke-lab-project"
REGION="asia-southeast1"
AUTO_CLUSTER="orders-autopilot-lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com

# Tạo dedicated Autopilot cluster.
gcloud container clusters create-auto "$AUTO_CLUSTER" \
  --location="$REGION" \
  --release-channel=regular

gcloud container clusters describe "$AUTO_CLUSTER" \
  --location="$REGION" \
  --format="yaml(name,location,autopilot,releaseChannel,status)"

gcloud container clusters get-credentials "$AUTO_CLUSTER" \
  --location="$REGION"
kubectl get nodes
kubectl get namespaces
~~~

Autopilot cluster khi chưa có user workloads có thể không có worker nodes cần phục vụ ứng dụng; sau khi tạo Deployment, GKE tự tạo capacity cần thiết. **Đừng xem việc không thấy nhiều node trước khi deploy là dấu hiệu cluster lỗi**. Ngoài ra, `create-auto` và các cài đặt mặc định có thể thay đổi theo release channel; hãy đối chiếu cluster config trước khi dùng production.

### Tạo Standard cluster mẫu

~~~bash
PROJECT_ID="my-gke-lab-project"
ZONE="asia-southeast1-a"
STD_CLUSTER="orders-standard-lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com

# Một zonal Standard cluster, với node pool ban đầu do bạn chọn.
gcloud container clusters create "$STD_CLUSTER" \
  --location="$ZONE" \
  --num-nodes=2 \
  --machine-type=e2-standard-2 \
  --release-channel=regular

gcloud container clusters describe "$STD_CLUSTER" \
  --location="$ZONE" \
  --format="yaml(name,location,nodePools,releaseChannel,status)"

gcloud container clusters get-credentials "$STD_CLUSTER" \
  --location="$ZONE"
kubectl get nodes -o wide
~~~

Zonal cluster trong ví dụ dùng **một zone**, vì vậy không phải thiết kế chịu lỗi zone cho production. Standard **cũng có thể tạo regional cluster** nếu yêu cầu HA tương ứng. Đừng so sánh “Standard zonal” với “Autopilot regional” rồi cho rằng mọi khác biệt HA đến từ mode.

**Hai đoạn CLI độc lập**: tạo cả hai cluster sẽ phát sinh chi phí cho cả hai. Trong lab, thực hiện một cluster tại một thời điểm hoặc dùng hai project riêng khi cần phân tích so sánh, rồi dọn tài nguyên an toàn.

## 9. Triển khai cùng một Java API trên hai mode

Mode là lựa chọn ở hạ tầng; Kubernetes Deployment của ứng dụng thường có thể dùng cùng manifest khi nó tuân thủ các yêu cầu của Autopilot và cluster Standard.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
              ephemeral-storage: "1Gi"
            limits:
              cpu: "1000m"
              memory: "2Gi"
              ephemeral-storage: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
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

Đây là **manifest tham khảo**, không tạo thành ứng dụng Java hoàn chỉnh: phải có image thật trong Artifact Registry, cho runtime image-pull identity quyền đọc, triển khai endpoint `/ready` và `/health`. `ClusterIP` chỉ cung cấp service nội bộ; muốn Internet truy cập cần Ingress/Gateway hoặc Service LoadBalancer phù hợp.

**Một khác biệt quan trọng:** Autopilot có thể **điều chỉnh requests** dựa trên minimum, maximum và tỷ lệ CPU:memory của ComputeClass, cũng có thể áp defaults khi thiếu trường. Giá trị 500m CPU, 1Gi memory trong ví dụ có thể được chấp nhận trên cấu hình phù hợp nhưng phải xem Pod đã được admission sửa thế nào; không giả định nó luôn giữ nguyên cho mọi kiến trúc/version.

### Apply và quan sát

~~~bash
# Giả định file orders-api.yaml đã được chuẩn bị bên ngoài bài học.
kubectl apply -f orders-api.yaml

kubectl get deployments,pods,services -l app=orders-api
kubectl rollout status deployment/orders-api
kubectl describe deployment orders-api
kubectl get pods -l app=orders-api -o wide
kubectl get events --sort-by=.lastTimestamp
~~~

Khi thử trên Standard cluster, Pod được scheduler đặt lên nodes có đủ CPU/memory còn trống. Khi thử trên Autopilot, GKE có thể cấp node mới và mất thêm thời gian trước khi Pod `Running`, đặc biệt lần đầu. **Pod Pending vài phút không nhất thiết là lỗi**, nhưng cần xem event để phân biệt provisioning hợp lệ với quota, constraint hoặc image pull failure.

## 10. Requests, limits và Pod scaling

Trong Kubernetes:

- **`requests.cpu` / `requests.memory`** ảnh hưởng placement và là cơ sở sizing/cost ở mô hình Pod-based Autopilot.
- **`limits.cpu` / `limits.memory`** xác định ngưỡng CPU throttling và giới hạn bộ nhớ; vượt memory limit có thể gây `OOMKilled`.
- **`ephemeral-storage`** là dung lượng tạm của container (writable layer, logs...), không thay PersistentVolume/Cloud Storage.
- **HPA** thay số replicas của workload theo CPU/memory hoặc metric đã tích hợp.
- **Node autoscaling** tăng/giảm công suất node để Pods có chỗ chạy; trong Standard bạn quản lý node pool autoscaling, trong Autopilot GKE quản lý node provisioning.

| Tình huống | Standard | Autopilot |
|---|---|---|
| Deployment tăng 3 → 8 Pods | HPA tạo Pod; cluster autoscaler cấp thêm VM nếu node pool cần và có cấu hình | HPA tạo Pod; GKE chủ động cấp thêm node capacity |
| CPU request quá nhỏ | Có thể làm scheduling dễ hơn nhưng tăng contention/OOM risk nếu memory sai | Có thể bị nâng request về minimum/ratio hợp lệ, ảnh hưởng bill |
| Chưa cấu hình HPA | Replicas giữ theo Deployment spec | Replicas cũng giữ theo Deployment spec |
| Chỉ bật node autoscaler | Không tự tăng Pod replicas nếu HPA không hoạt động | Google tăng node theo Pod demand, không tự tăng replicas khi traffic lớn |

### HPA ví dụ

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

HPA CPU utilization 65% được hiểu tương đối so với **CPU requests**, không phải 65% số core của toàn cluster. Ví dụ một Pod yêu cầu `500m`, mục tiêu CPU khoảng `325m` theo quy tắc metric được thu thập; HPA tính toán tổng thể trên các Pods hợp lệ và có thuật toán ổn định riêng. Đây **không phải bảo đảm tự động đạt 65% ngay lập tức**.

~~~bash
kubectl apply -f orders-api-hpa.yaml
kubectl get hpa orders-api-hpa
kubectl describe hpa orders-api-hpa
kubectl top pods
~~~

Nếu HPA hiển thị `unknown` cho CPU metric, kiểm tra metrics server/pipeline, requests của container, quyền truy cập và thời gian Pod đã hoạt động. Không tăng `maxReplicas` vô hạn để khắc phục database bottleneck.

## 11. Tính phí: Pod-based và node-based không giống nhau

Một sai lầm khi so sánh hai mode là nói **“Autopilot chỉ trả tiền theo Pods”** mà không xét phần cứng, hoặc **“Standard luôn rẻ hơn vì tự quản node”** mà không tính tài nguyên bỏ trống và công sức vận hành.

### Standard: chủ yếu tính theo node

Trong node pools Standard, chi phí compute dựa trên **Compute Engine VM**, boot disk, network và các thành phần hạ tầng liên quan. Node chạy 24 giờ nhưng Pod chỉ dùng 20% CPU vẫn bị tính phí theo công suất VM đã cấp; có thể có committed use discount hoặc Spot VMs theo chính sách tương ứng.

~~~text
Tổng chi phí Standard, mô hình gần đúng
  = cluster management fee
  + tổng node VM-hours × giá VM
  + boot disks / PersistentVolumes / network / LB
  + logging / monitoring / các dịch vụ phụ thuộc
~~~

**Node autoscaler** có thể giảm số VM trong phạm vi node pool; nhưng node pool min size, các system Pods, PodDisruptionBudgets, Pod requests và ràng buộc zone có thể giữ một mức công suất nhất định. Với Standard, chi phí cần theo dõi **node utilization** và phần CPU/memory bị cấp nhưng không sử dụng.

### Autopilot general-purpose: Pod-based

Với workloads **general-purpose** trên Autopilot container-optimized compute platform hoặc những built-in ComputeClasses tương ứng như Balanced/Scale-Out trong Autopilot cluster, GKE dùng mô hình **Pod-based billing**: phí chủ yếu theo CPU, memory và ephemeral storage **được request** của Pods đã được đặt lên node.

~~~text
Tổng chi phí Autopilot general-purpose, mô hình gần đúng
  = cluster management fee
  + tổng (Pod requested CPU/memory/ephemeral-storage × thời gian billable)
  + PersistentVolumes / network / LB
  + logging / monitoring / dịch vụ phụ thuộc
~~~

Trong mô hình này, node size và phần node chưa cấp cho Pod không phải đơn vị chính để tính phí workload; một số system Pods và node overhead không được tính theo cách của user Pod. Tuy nhiên, **Pod đã được schedule nhưng đang CrashLoopBackOff hoặc ImagePullBackOff vẫn có thể bị tính phí**, trong khi Pod chưa được schedule không được tính theo mô hình này.

**Chú ý minimum/default requests:** nếu thiếu `resources.requests`, Autopilot tự bổ sung; nếu CPU/memory nằm ngoài giới hạn hoặc tỷ lệ của ComputeClass, GKE có thể nâng yêu cầu lên mức hợp lệ. Giá tính theo **requests sau admission**, không theo con số lập trình viên tưởng tượng ban đầu. Ví dụ ứng dụng chỉ cần 200m CPU nhưng Pod không khai báo gì có thể chịu requests mặc định cao hơn. Không tối ưu bằng cách cố khai báo `0` rồi kỳ vọng miễn phí.

### Autopilot phần cứng chuyên dụng: node-based

Khi workloads chọn **GPU, TPU hoặc machine series/accelerator cụ thể** qua selectors hay ComputeClasses, Autopilot có thể cấp VM chuyên dụng và tính theo **toàn bộ node Compute Engine resources + Autopilot management premium**. Nếu một workload chỉ dùng một phần nhỏ GPU node, vẫn có thể trả tiền cho cả node; cần tính packing, quota, scheduling và thời gian node tồn tại.

| Workload | Mode/tài nguyên | Hướng lập dự toán |
|---|---|---|
| Standard web API trên e2 node pool | Node-based | VM-hours × node count; Pod utilization ảnh hưởng lãng phí |
| Autopilot API không cần hardware riêng | Pod-based | Pod requests × thời gian Pod được schedule |
| Autopilot batch chọn GPU/machine series cụ thể | Node-based + premium | VM/accelerator hours, khả năng packing lên node |
| Autopilot ComputeClass trong Standard cluster | Theo loại Autopilot workload | General-purpose Pod-based; hardware-specific node-based |
| Standard GPU pool | Compute Engine nodes + GPU | Số node, loại GPU, disk và discounts có thể áp dụng |

### Cluster management fee và các khoản dễ quên

Cả Standard và Autopilot đều có thể chịu **phí quản lý cluster** theo biểu phí GKE; một số điều kiện miễn phí/tín dụng hàng tháng áp dụng cho loại cluster đủ điều kiện và Billing account. Không coi “GKE free tier” là miễn phí VM, Pods, load balancer, network hoặc Cloud SQL.

Ngoài compute cần tính:

- Persistent Disk, Filestore, Cloud Storage FUSE và operations.
- External/Internal Load Balancer, public IP, Cloud NAT và network egress.
- Artifact Registry, Secret Manager, Cloud Logging/Monitoring, security products.
- Quota/capacity dự phòng cho rolling updates, HPA tăng tải và Pod disruption.
- Thời gian đội vận hành SRE/platform: không phải dòng hóa đơn Google Cloud nhưng là chi phí doanh nghiệp thực.

Tham khảo [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) và [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator) trước khi quyết định. **Không so sánh bằng giá vCPU đơn lẻ** nếu hai phương án khác nhau về tính sẵn sàng, hiệu năng và trách nhiệm vận hành.

### Bài toán so sánh có điều kiện

Giả sử 10 API, mỗi API dùng 3 Pods thường xuyên, mỗi Pod khai báo `500m` CPU và `1Gi` memory. Tổng requests ứng dụng là:

~~~text
Số Pod = 10 × 3 = 30
CPU requests = 30 × 0.5 = 15 vCPU
Memory requests = 30 × 1 GiB = 30 GiB
~~~

Với **Autopilot general-purpose**, 30 Pods đóng góp vào phần billable requests theo thời gian schedule và những adjustment có thể xảy ra; thêm phí cluster, storage, network. Với **Standard**, phải chọn đủ nodes để chứa 15 vCPU và 30 GiB **cộng system overhead**, cần dự trù khả năng chịu lỗi zone và surge. Nếu chọn nhiều VM lớn nhưng chỉ chạy một vài Pods, Standard dễ bị lãng phí; nếu node pool được packing tốt và có discounts, tính toán có thể khác.

Đây không phải bảng so sánh tiền chính xác vì chưa có region price, availability tier, load profiles, CUD, CPU architecture và giờ hoạt động. Hãy đo requests thực, SLO và chi phí trên môi trường thử nghiệm trước khi tối ưu.

## 12. Bảo mật: guardrails của Autopilot và quyền kiểm soát Standard

Trong Autopilot cluster, GKE áp các chính sách được cấu hình sẵn nhằm hạn chế những cấu hình Pod có thể làm tăng nguy cơ truy cập host:

- **Privileged containers** bị chặn theo mặc định, trừ một số trường hợp hệ thống/đối tác được xác minh và hỗ trợ.
- **Host namespaces, HostProcess, unsafe sysctls** và nhiều dạng truy cập host bị giới hạn.
- **hostPath volumes** bị giới hạn; có một số trường hợp chỉ đọc đối với log theo tài liệu.
- Linux capabilities được kiểm soát; một số capability hoặc networking mode có cơ chế opt-in theo phiên bản/tính năng.
- Một số Pod settings được **admission controller** tự điều chỉnh hoặc từ chối khi trái guardrails.

Standard linh hoạt hơn: người quản trị có thể cho phép privileged Pod hoặc host-level agent khi cần. **Linh hoạt không có nghĩa an toàn hơn theo mặc định**; tổ chức phải chủ động áp Pod Security Standards, policy engine, container image scanning, hạn chế quyền, audit và cập nhật node.

### IAM và Kubernetes RBAC

Có hai lớp cấp quyền:

1. **Google Cloud IAM:** ai được tạo/sửa cluster, quản lý mạng và gọi Google APIs.
2. **Kubernetes RBAC:** ai được đọc, tạo, sửa hoặc xóa namespace, Deployment, Secret và các tài nguyên K8s khi đã kết nối control plane.

| Actor | Hành động | Hướng giới hạn |
|---|---|---|
| Platform cluster admin | Tạo/sửa cluster, node pools và cluster policies | `roles/container.clusterAdmin` trên project cần thiết |
| Developer | Deploy vào namespace ứng dụng | IAM phù hợp + Kubernetes Role/RoleBinding đúng namespace |
| CI/CD release identity | Áp manifests được phê duyệt | Quyền Kubernetes tối thiểu; tách prod và dev |
| Java runtime Pod | Truy cập Cloud SQL/Storage/Pub/Sub | Workload Identity Federation for GKE và IAM roles trên resource |
| Auditor/SRE | Đọc logs, metrics, trạng thái cluster | Quyền đọc, không phải `cluster-admin` mặc định |

**Workload Identity Federation for GKE** cho phép workload trong Pod dùng Kubernetes ServiceAccount kết nối với IAM principal của Google Cloud theo mô hình hỗ trợ, tránh lưu JSON service account key dài hạn vào container image hoặc Secret. Cấu hình cụ thể tùy cluster và workload, nhưng nguyên tắc **quyền tối thiểu** như nhau ở Standard và Autopilot.

### Kiểm tra manifest trước khi chọn mode

Nếu một ứng dụng yêu cầu:

~~~yaml
securityContext:
  privileged: true
  runAsUser: 0
volumes:
  - name: host
    hostPath:
      path: /var/lib
~~~

**Không triển khai nguyên xi manifest này lên Autopilot và kỳ vọng được chấp nhận.** `privileged` và `hostPath` có thể vi phạm guardrails. `runAsUser: 0` **không phải lúc nào cũng bị chặn** trong Autopilot, vì policy có thể cho container chạy root trong một số điều kiện. Vì vậy cần nhìn đúng trường bị policy từ chối, thay vì nói chung chung “Autopilot cấm mọi container chạy root”.

Đội bảo mật có thể thay agent host-level bằng phương án quan sát/scan không yêu cầu privileged DaemonSet, hoặc chạy thành phần đặc thù trên Standard node pool/cluster.

## 13. Mạng, địa chỉ IP và truy cập ứng dụng

GKE dùng VPC để Pods/Nodes kết nối dịch vụ khác. Một thiết kế production phải xét:

- **VPC-native IP addressing:** subnet và secondary ranges cho Pods/Services, tránh hết IP khi HPA tăng replicas.
- **Private nodes / control plane access:** giới hạn external IP và quyền truy cập Kubernetes API, cấu hình Cloud NAT/Private Google Access khi cần.
- **Ingress:** Service type LoadBalancer, GKE Ingress hoặc Gateway API để nhận request; Cloud DNS/TLS/Cloud Armor cho endpoint công khai khi phù hợp.
- **Egress:** VPC firewall, routing, Cloud NAT, Secure Web Proxy hoặc chính sách tổ chức để kiểm soát request ra Internet.
- **NetworkPolicy và GKE Dataplane V2:** giảm truy cập pod-to-pod ngoài nhu cầu.
- **Service-to-service authentication:** không coi “ở cùng cluster” là được phép gọi mọi API.

### Sơ đồ minh họa cho Java API

~~~mermaid
flowchart TD
  A["Internet client"] --> B["Cloud DNS"]
  B --> C["External Application Load Balancer + TLS"]
  C --> D["GKE Service / Gateway"]
  D --> E["Java API Pods: Standard hoặc Autopilot"]
  E --> F["Cloud SQL private IP"]
  E --> G["Cloud Storage API"]
  E --> H["Pub/Sub"]
  I["IAM / Workload Identity"] --> E
  J["NetworkPolicy / VPC firewall"] --> E
~~~

**Chọn mode không tự tạo an toàn mạng:** nếu bạn khai báo Kubernetes Service kiểu `LoadBalancer`, Google Cloud có thể cấp tài nguyên LB và IP theo thiết lập. Nếu muốn chỉ người trong VPC truy cập, cần chọn đúng loại internal LB hoặc chính sách networking, không chỉ đổi Standard sang Autopilot.

### GKE và Cloud Run trong cùng kiến trúc

Một tổ chức có thể chạy batch hoặc các dịch vụ yêu cầu Kubernetes trên GKE, còn API đơn giản ít cần cluster-level controls trên Cloud Run. Điều quan trọng là quyền mạng, identity, CI/CD, logs và chi phí **ở từng service** chứ không buộc mọi ứng dụng dùng một nền tảng.

## 14. Lưu trữ bền vững và khả năng sẵn sàng

Pods là các instance **có thể bị tạo lại**; file ghi trên container writable layer không phải nơi lưu trữ bền vững cho dữ liệu nghiệp vụ. Dù Standard hay Autopilot, phải lựa chọn storage theo access pattern:

| Yêu cầu | Giải pháp tham khảo | Lưu ý |
|---|---|---|
| Một Pod cần block filesystem bền vững | PersistentVolume/PVC qua Persistent Disk CSI driver | Phụ thuộc zone, access mode, attach/detach |
| Nhiều Pods/VMs cần chia sẻ file POSIX | Filestore CSI driver | NFS networking, permissions, tier và chi phí |
| Ảnh và object artifacts | Cloud Storage API hoặc Cloud Storage FUSE CSI driver | Object semantics không hoàn toàn như POSIX disk |
| Database giao dịch | Cloud SQL/AlloyDB hoặc dịch vụ DB phù hợp | HA, backup, connection pool và quota độc lập với GKE |
| Cache tạm | Ephemeral storage hoặc Redis/Memorystore | Không coi dữ liệu tạm là bản sao duy nhất |

**Một PVC ReadWriteOnce gắn Persistent Disk không tự hỗ trợ nhiều Pods ở nhiều node cùng ghi**. Khi cần RWX/shared-filesystem, xem Filestore hoặc giải pháp khác có ngữ nghĩa đúng. Autopilot cũng hỗ trợ nhiều CSI/storage integrations, nhưng có khác biệt về access mode, node privileges, file system và driver support theo phiên bản.

### High availability không phụ thuộc mode một cách đơn giản

Autopilot clusters dùng kiến trúc **regional**; Standard có thể là **zonal** hoặc **regional**. Nhưng **regional cluster chưa đủ để ứng dụng HA**:

1. Chạy nhiều replicas ở các zone theo scheduling/ComputeClass hỗ trợ.
2. Dùng readiness/liveness/startup probes phù hợp với thời gian khởi động JVM.
3. Đặt PodDisruptionBudget và topology spread constraints khi thích hợp, hiểu giới hạn scheduling.
4. Đảm bảo storage/database không đặt toàn bộ dữ liệu ở một single point of failure.
5. Tính capacity cho thời gian một zone bị lỗi, rolling updates hoặc cluster maintenance.
6. Thiết kế graceful termination, timeout, retry có kiểm soát và tránh retry storm.

Ví dụ Deployment `replicas: 3` **không bảo đảm mỗi Pod nằm một zone**. Nếu yêu cầu phân tán, dùng topology spread constraints hoặc affinity phù hợp, sau đó xác minh phân bố thật qua `kubectl get pods -o wide`.

## 15. Triển khai, cập nhật và GitOps

Cả hai mode đều dùng Kubernetes manifests, `kubectl`, Helm, Kustomize, Argo CD/Flux hoặc các pipeline tương thích.

Luồng phát hành đề xuất:

~~~text
Git commit
  → CI tests + image scanning
  → Build Java container image
  → Push vào Artifact Registry
  → Review manifests (CPU/memory, probes, policy)
  → Apply bằng GitOps/CD identity
  → Deployment rolling update
  → Readiness / SLO checks / canary nếu có
  → Monitor và rollback khi cần
~~~

**Versioned images:** tránh chạy `:latest` không kiểm soát; dùng digest hoặc image tag bất biến để biết chính xác phiên bản đang phục vụ. Tách application deployment khỏi node management; việc nâng version GKE không đồng nghĩa tự build lại image Java.

### Rolling update và rollback

~~~bash
# Dùng image thật do CI đã push, PROJECT_ID phải được thay.
kubectl set image deployment/orders-api \
  api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v2

kubectl rollout status deployment/orders-api
kubectl rollout history deployment/orders-api

# Nếu phiên bản mới không đáp ứng điều kiện đã đặt.
kubectl rollout undo deployment/orders-api
~~~

Pod rollout có thể bị kẹt nếu `maxUnavailable`, `maxSurge`, quota, readiness hoặc tài nguyên node không phù hợp. Trong Standard, kiểm tra cả node pool capacity/autoscaler; trong Autopilot, xem admission, scheduling và resource provisioning. Rollback Deployment thay image đã triển khai **không tự rollback schema database** hoặc dữ liệu đã ghi.

### Maintenance và upgrades

GKE có **release channels** và cơ chế upgrade/maintenance. Autopilot áp quản lý node theo cấu hình được Google định trước; Standard cho đội platform kiểm soát nhiều thiết lập node pool, auto-upgrade window và rollout hơn. Với cả hai:

- Test image/client compatibility với Kubernetes version dự kiến.
- Theo dõi deprecation APIs trước khi nâng version.
- Chọn maintenance windows/exclusions khi đáp ứng tiêu chí hỗ trợ.
- Dùng readiness và PodDisruptionBudgets để giảm tác động tới SLO.
- Không coi việc Google quản node là cam kết zero downtime đối với một ứng dụng chỉ có một replica.

## 16. Quota, scheduling và độ trễ khởi động

Một Pod có thể nằm ở `Pending` dù manifest hợp lệ. Những nguyên nhân chính:

| Vấn đề | Biểu hiện | Standard | Autopilot |
|---|---|---|---|
| CPU/memory không đủ | `Insufficient cpu/memory` | Resize hoặc autoscale node pool, kiểm tra requests | GKE cấp node; kiểm tra quota/compute bounds |
| Resource requests không hợp lệ | Admission/rejection hoặc request bị điều chỉnh | Kiểm tra LimitRange/ResourceQuota | Kiểm tra Autopilot min/max và CPU:memory ratio |
| Node affinity quá chặt | Không node thỏa selector/taints | Điều chỉnh node pools/taints | Điều chỉnh ComputeClass/constraints |
| Quota hoặc capacity thiếu | Node provisioning thất bại hoặc kéo dài | Kiểm tra CPU/GPU quota và zone | Kiểm tra quotas, vùng/accelerator availability |
| Private registry không truy cập | `ImagePullBackOff` | Image pull identity, network | Tương tự; node do Google quản lý |
| Pod security không phù hợp | Admission rejection | Kiểm tra policies của cluster | Kiểm tra guardrails Autopilot |
| Storage zone mismatch | PVC Pending, mount thất bại | Kiểm tra node/volume zones | Kiểm tra topology/driver/support |
| Rollout quá nhanh | 5xx hoặc readiness errors | Cân nhắc surge/capacity | Cân nhắc node provisioning và resource requests |

**Autopilot provisioning cũng có thời gian trễ:** khi có đợt scale-out đột ngột, GKE cần tạo node/capacity mới, tải image và đợi ứng dụng sẵn sàng. Một API có JVM warmup 90 giây không đạt năng lực xử lý ngay khi HPA tăng replicas. Thiết kế HPA metric, pre-warming/replica floor và load shedding phù hợp với SLO.

### Câu lệnh điều tra nhanh

~~~bash
kubectl get pods -A -o wide
kubectl describe pod POD_NAME -n NAMESPACE
kubectl get events -A --sort-by=.lastTimestamp
kubectl get nodes -o wide
kubectl get deployments,hpa -A
kubectl get pvc -A

# Khi Pod đã chạy nhưng ứng dụng lỗi.
kubectl logs deployment/orders-api --tail=100
kubectl describe deployment/orders-api
~~~

Nếu `kubectl get nodes` cho thấy vài nodes của Autopilot, điều đó không cho phép SSH/tùy chỉnh hệ điều hành như Standard. Khi Pod bị Admission webhook từ chối, đọc **chính xác reason/message** trong events thay vì tăng CPU hoặc vô hiệu hóa guardrail một cách mù quáng.

## 17. Di chuyển workload và chọn kiến trúc lai

Một tổ chức có Standard cluster với nhiều ứng dụng; một số Pod có thể chạy tốt trên Autopilot, số khác cần privileged agent. Có ít nhất hai hướng:

**Hướng A — Tạo dedicated Autopilot cluster mới.** Dùng khi phần lớn workloads phù hợp và muốn giảm trách nhiệm node-level lâu dài.

1. Kiểm kê Deployment, StatefulSet, DaemonSet, PVC, NetworkPolicy, Ingress, HPA, CRDs và các cluster add-ons.
2. Kiểm tra privileged containers, `hostPath`, machine type/GPU, CSI drivers, CPU/memory/ephemeral requests và CPU:memory ratio.
3. Tạo Autopilot cluster trong VPC/region được phê duyệt; thiết lập IAM, Workload Identity, Artifact Registry, Secret Manager, logging và network.
4. Triển khai namespace, CRDs và workload phiên bản tương thích từ GitOps.
5. Di chuyển dữ liệu bền vững bằng snapshot/backup/replication phù hợp, không copy tạm một PVC đang ghi rồi giả định nhất quán.
6. Chạy kiểm thử chức năng, performance và security; đo requests thực và chi phí.
7. Chuyển traffic bằng load balancing/DNS theo kế hoạch canary, giữ endpoint cũ để rollback khi cần.
8. Sau khi ổn định, rà soát chi phí và xóa tài nguyên Standard cũ đúng quy trình.

**Hướng B — Giữ Standard cluster, chọn Autopilot ComputeClasses cho một số workloads.** Dùng khi cần hybrid controls trong cùng cluster, và cluster đạt version/network/security prerequisites. Phải hiểu Autopilot workloads có guardrails/đơn giá riêng ngay cả khi chúng ở trong Standard cluster.

### Minh họa workload chọn Autopilot ComputeClass trong Standard cluster

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      nodeSelector:
        cloud.google.com/compute-class: autopilot
      containers:
        - name: worker
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-worker:v1
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
~~~

Đây là **minh họa** trên Standard cluster có hỗ trợ built-in `autopilot` ComputeClass. Nếu cluster không đạt version/prerequisites, Pod có thể Pending. Cần xác minh ComputeClass đang tồn tại và cách scheduler chọn node; không dùng manifest này như hướng dẫn bất chấp phiên bản. Trên dedicated Autopilot cluster, GKE đã chọn Autopilot cho workloads và thường **không cần** gắn selector này.

**Không phải migration in-place:** bạn không thể đặt vài node pools mới rồi biến toàn bộ một dedicated Autopilot cluster thành Standard cluster có quyền node không giới hạn. Xây kiến trúc lai phải đi qua tính năng **Standard + Autopilot ComputeClasses** được hỗ trợ hoặc triển khai ở hai cluster.

## 18. Tình huống doanh nghiệp: chọn mode cho từng hệ thống

Giả sử một doanh nghiệp thương mại điện tử có bốn hệ thống trên Google Cloud:

1. **Orders API Java:** 8 microservices stateless dùng Cloud SQL và Pub/Sub, có đỉnh traffic theo giờ.
2. **Search indexing:** worker chạy job xử lý dữ liệu, có GPU theo từng giai đoạn.
3. **Fraud engine legacy:** một số agent cần quyền host-level, DaemonSets và cấu hình kernel chuyên biệt.
4. **Web frontend:** container HTTP đơn giản, chỉ có vài service, không phụ thuộc Kubernetes-specific APIs.

### Đánh giá theo workload, không theo khẩu hiệu

| Hệ thống | Nhu cầu nổi bật | Hướng lựa chọn ban đầu |
|---|---|---|
| Orders API Java | Ít node-level customization, nhiều replicas, HPA và rollout | **GKE Autopilot** nếu yêu cầu network/storage tương thích |
| Search indexing có GPU | Phần cứng chuyên dụng, batch theo thời điểm | **So sánh Autopilot hardware-specific và Standard GPU pools** |
| Fraud engine legacy | Privileged agent/host access bắt buộc | **GKE Standard** hoặc thay đổi agent để tương thích |
| Web frontend tối giản | Không cần cluster, muốn ít Kubernetes operations | **So sánh Cloud Run** trước khi quyết định dùng GKE |

### Phương án kiến trúc A: tách theo trách nhiệm

~~~text
                     Google Cloud Organization
                       ├── ecommerce-prod project
                       │    ├── GKE Autopilot: Orders APIs
                       │    ├── Cloud SQL: dữ liệu giao dịch
                       │    ├── Pub/Sub: event bus
                       │    └── External Application Load Balancer
                       ├── fraud-prod project
                       │    └── GKE Standard: privileged agents
                       └── web-prod project
                            └── Cloud Run: frontend HTTP
~~~

Ưu điểm: tách IAM, security posture, release process và chi phí theo nhóm. Đánh đổi: nhiều project/cluster hơn, cần quản trị network, observability, service-to-service authentication và CI/CD xuyên project.

### Phương án kiến trúc B: Standard cluster lai

Nếu tổ chức đã có Standard cluster regional đáp ứng điều kiện ComputeClasses mới, có thể giữ một Standard node pool cho Fraud engine và cho Orders worker hợp lệ dùng Autopilot ComputeClass. Ưu điểm là ít thay đổi network/API hơn; đổi lại nhóm platform **vẫn phải vận hành Standard cluster** và quản các policy khi cả hai loại workload cùng tồn tại.

### Quy trình lựa chọn có bằng chứng

Trước khi chốt, hãy thực hiện một pilot:

1. **Inventory yêu cầu:** tập Pod manifests, DaemonSets, CRDs, storage, host privileges, data residency và release windows.
2. **Chạy admission test:** cùng deployment được apply trong môi trường Standard và Autopilot; lưu sự kiện bị từ chối hoặc requests được điều chỉnh.
3. **Load test:** đo startup latency, P95/P99 HTTP latency, database connections, HPA lag, Pod scale-out, quota failures.
4. **So sánh chi phí:** cùng throughput/SLO, tính cluster fee, vCPU/memory requests, VM/node-hours, network, LB, disk, logging, nhân lực vận hành.
5. **Đánh giá outage:** simulate Pod crashes, node drain và zone-level failure trong môi trường được phép.
6. **Review bảo mật:** IAM, Workload Identity, RBAC, network policies, privileged workloads, image supply chain.
7. **Chốt mô hình vận hành:** người chịu trách nhiệm node, app, scaling, patching, sự cố và rollback.

**Kết luận của tình huống:** Orders APIs nhiều khả năng phù hợp Autopilot; Fraud cần Standard nếu không thể bỏ đặc quyền; Search phải benchmark phần cứng/giá thật; Web frontend có thể không cần GKE. Chọn nền tảng theo mục tiêu nghiệp vụ và kiến trúc ứng dụng, không ép mọi workload lên một mode.

## 19. Các sai lầm thường gặp khi chọn GKE mode

| Nhận định sai | Điều đúng cần kiểm tra |
|---|---|
| “Autopilot không có VM/node.” | Có hạ tầng node, nhưng GKE quản lý chúng và cấp theo workload |
| “Standard tự quản cả control plane.” | GKE quản lý Kubernetes control plane ở cả hai mode |
| “Autopilot nghĩa là không cần HPA.” | HPA vẫn cần nếu muốn thay đổi số replicas dựa trên traffic/metrics |
| “Autopilot luôn tính tiền theo Pod.” | General-purpose Pod-based; phần cứng chuyên dụng có thể node-based + premium |
| “Không khai báo requests thì Pod chỉ trả tiền đúng CPU đã sử dụng.” | Autopilot thêm default requests và có thể điều chỉnh theo giới hạn |
| “Standard luôn rẻ hơn.” | Phải tính VM utilization, discounts, node overhead và chi phí vận hành |
| “Autopilot không hỗ trợ GPU.” | Có khả năng hỗ trợ GPU/accelerators theo class, region, version và quota |
| “Autopilot cấm mọi container chạy root.” | Một số quyền host/privileged bị chặn; root user không phải luôn bị cấm |
| “Standard và Autopilot không thể cùng tồn tại.” | Standard cluster có thể chạy Autopilot workloads qua ComputeClasses khi đủ điều kiện |
| “Regional GKE là đủ cho HA.” | Cần nhiều Pod, topology spread, storage/database HA và đủ capacity |
| “Pod Pending tức là cluster lỗi.” | Có thể đang cấp node hoặc bị ràng buộc quota, policies, PVC hoặc resources |
| “Tắt hoặc xóa Deployment là hết chi phí.” | Cluster, Standard nodes, PV, LB, IP và các tài nguyên phụ thuộc có thể vẫn tồn tại |

## 20. Checklist lựa chọn và triển khai

### Trước khi chọn Standard hay Autopilot

- [ ] Đã liệt kê tất cả workload, DaemonSets, CRDs, CSI drivers, agents và các quyền host.
- [ ] Xác định Pod security requirements, privileged mode, hostPath và sysctls.
- [ ] Kiểm tra GPU/TPU, Arm, memory, disk, network và ComputeClass support theo region/version.
- [ ] Phân biệt cluster mode với workload mode trong Standard cluster có Autopilot ComputeClasses.
- [ ] Đã xác nhận yêu cầu HA ở mức VM/zone/region và phụ thuộc database/storage.
- [ ] Đã chọn VPC-native networking, dải IP Pod/Service và đường ingress/egress.
- [ ] Quyết định ai quản lý node pools, patch/upgrade, capacity, Pod security và incident response.
- [ ] So sánh chi phí theo throughput/SLO, node utilization, Pod requests, GPU premium, network/LB/PV/Logging.

### Trước khi triển khai ứng dụng

- [ ] Container image phiên bản rõ ràng, nằm trong registry được cấp quyền.
- [ ] Deployment có CPU/memory/ephemeral-storage requests và limits hợp lệ.
- [ ] Readiness, liveness và startup probes phản ánh vòng đời ứng dụng.
- [ ] HPA có min/max replicas và metrics đáng tin; đánh giá thời gian cấp node và boot JVM.
- [ ] Workload Identity Federation và IAM theo nguyên tắc quyền tối thiểu.
- [ ] Kubernetes RBAC, namespaces và network policies đã được review.
- [ ] PVC/Filestore/Cloud Storage phù hợp với ngữ nghĩa dữ liệu; có backup và restore plan.
- [ ] Application Load Balancer/TLS/Cloud Armor, DNS và firewall được kiểm tra nếu công khai.
- [ ] CI/CD, release channel, maintenance windows và rollback đã có owner.
- [ ] Alerts theo error rate, latency, saturation, Pod pending, OOM, HPA và chi phí đã được cấu hình.

### Khi kết thúc lab hoặc migration

- [ ] Đã sao lưu/di chuyển dữ liệu trước khi xóa cluster hoặc PVC.
- [ ] Xem lại LoadBalancer IP, PersistentVolumes, Filestore, Cloud NAT, Artifact Registry và logging resources còn tồn tại.
- [ ] Chỉ xóa tài nguyên đúng project/cluster sau khi kiểm tra owner và retention.
- [ ] Ghi quyết định kiến trúc, lý do, giả định chi phí và tiêu chí xem xét lại.

## 21. Bài tập vận dụng

**Bài tập A — Lựa chọn mode cho API Java.** Một nhóm có 5 microservices stateless. Mỗi service có 3 replicas, mỗi Pod trung bình yêu cầu `500m` CPU và `1Gi` memory. Nhóm chưa có SRE chuyên Kubernetes, cần HPA khi traffic tăng, dùng Cloud SQL private IP và Pub/Sub.

1. Chọn Standard hay Autopilot cho phương án ban đầu; giải thích bằng ít nhất bốn tiêu chí.
2. Tính tổng CPU/memory **requested** ở mức baseline và phân biệt với CPU thực dùng.
3. Liệt kê các nhóm chi phí: cluster fee, Pod/node compute, LB, Cloud SQL, network, logging và storage.
4. Viết Deployment manifest với probes, `resources.requests`/`limits` và HPA tối thiểu 3, tối đa 12 replicas.
5. Giải thích tại sao HPA tăng replicas nhưng Pod mới vẫn có thể Pending trong một khoảng thời gian.
6. Đề xuất cách cấp quyền cho Pods truy cập Pub/Sub và Cloud SQL mà không đặt service account key trong image.

**Bài tập B — Khả năng tương thích với Autopilot.** Cluster hiện có một security agent DaemonSet chạy `privileged: true`, mount hostPath `/var/lib`, một dịch vụ có GPU và một batch worker chỉ cần CPU.

1. Đánh dấu thành phần nào phải được kiểm thử/thiết kế lại trước khi chuyển sang dedicated Autopilot.
2. Đề xuất kiến trúc Standard node pool kết hợp Autopilot ComputeClass khi version hỗ trợ.
3. Giải thích vì sao workload GPU trong Autopilot có thể được tính theo **node-based** chứ không theo Pod requests.
4. Nêu dữ liệu nào cần benchmark trước khi quyết định giữ Standard GPU pool.

**Bài tập C — So sánh chi phí và SLO.** Một Standard node pool đang dùng 4 VM, mỗi VM 4 vCPU và 16 GiB RAM. Hầu hết thời gian tổng Pods chỉ request 6 vCPU và 12 GiB RAM; mỗi ngày có 2 giờ request tăng gấp đôi.

1. Tính công suất VM đã cấp và tỷ lệ CPU/memory requests so với công suất danh nghĩa (chưa trừ system overhead).
2. Đề xuất một lịch HPA + node autoscaler phù hợp cho Standard, kèm min/max và kiểm tra quota.
3. Ước lượng Autopilot general-purpose từ tổng Pod requests theo giờ (không cần giá thực nếu chưa có bảng giá), rồi so sánh tương đối.
4. Giải thích vì sao không thể kết luận mode nào rẻ hơn chỉ từ tổng `kubectl top` CPU.
5. Mô tả cách đo P95 latency, 5xx, startup time và rollout behavior trước khi thay đổi production.

**Bài tập D — Sự cố production.** Sau khi deploy một ứng dụng Java lên Autopilot cluster, các Pod ở trạng thái `Pending`, một số log cho biết `resource request` ngoài giới hạn; deployment trên Standard cluster trước đó chạy được.

1. Chỉ ra ít nhất ba lệnh `kubectl` để điều tra.
2. Giải thích cách Autopilot áp default/min/max và ratio cho CPU:memory.
3. Nêu khi nào nên sửa requests, khi nào cần ComputeClass khác, khi nào phải chọn Standard vì đặc quyền host.
4. Đề xuất cách rollout lại không ảnh hưởng những service đã chạy.
5. Liệt kê guardrails/metrics để sự cố tương tự được phát hiện trong CI trước production.

**Câu hỏi tổng kết:** Nếu yêu cầu là “chỉ một REST API Java với HTTP request và vài tác vụ nền”, hãy giải thích vì sao **Cloud Run** cũng phải có trong danh sách phương án, thay vì mặc định chọn một GKE mode.

## Tài liệu tham khảo chính thức

- [About GKE modes of operation](https://cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode) — khác biệt giữa Standard và Autopilot ở cấp workload và cluster.
- [GKE Autopilot overview](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview) — cơ chế quản lý node, vận hành và ComputeClasses.
- [Autopilot workloads in GKE Standard clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/about-autopilot-mode-standard-clusters) — chạy workload Autopilot trong Standard cluster.
- [Run Autopilot workloads in Standard clusters](https://cloud.google.com/kubernetes-engine/docs/how-to/autopilot-classes-standard-clusters) — điều kiện version, networking, node pools và ComputeClass.
- [Configure Standard clusters to use Autopilot by default](https://cloud.google.com/kubernetes-engine/docs/how-to/standard-clusters-autopilot-mode) — cấu hình Autopilot-like settings cho Standard cluster.
- [Create an Autopilot cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster) — Console, CLI và Terraform.
- [Create a zonal Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-zonal-cluster) — CLI, zones và node pools.
- [Create a regional Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-regional-cluster) — regional control plane, multi-zone node pools và HA.
- [Autopilot resource requests](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests) — requests defaults, minimums, ratios và bursting.
- [Autopilot security measures](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-security) — privileged, capabilities, host access và chính sách mặc định.
- [GKE ComputeClasses](https://cloud.google.com/kubernetes-engine/docs/concepts/about-custom-compute-classes) — khai báo cấu hình tính toán theo workload.
- [Built-in GKE ComputeClasses](https://cloud.google.com/kubernetes-engine/docs/concepts/about-built-in-compute-classes) — autopilot, autopilot-spot và các classes khác.
- [GKE cluster autoscaling](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler) — quản trị node capacity và cách autoscaler hoạt động.
- [GKE storage overview](https://cloud.google.com/kubernetes-engine/docs/concepts/storage-overview) — Persistent Disk, Filestore và Cloud Storage FUSE.
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — danh tính Pods và Google Cloud IAM.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — cluster fee, Pod-based/node-based billing và giới hạn.
- [GKE and Cloud Run](https://cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run) — chọn nền tảng phù hợp với ứng dụng container.
