# GitOps cho AKS với Flux

Khi một nhóm vận hành cụm **Azure Kubernetes Service (AKS)**, số lượng thành phần cần triển khai có thể tăng nhanh: API, worker xử lý hàng đợi, namespace, ConfigMap, Service, Ingress, Horizontal Pod Autoscaler, policy và tài nguyên giám sát. Nếu mỗi lần thay đổi đều dùng lệnh `kubectl apply` từ laptop hoặc một pipeline có quyền quản trị cụm, trạng thái thực tế dễ lệch khỏi cấu hình đã được duyệt. Khi có sự cố, đội vận hành còn phải trả lời: ai đổi tài nguyên, thay đổi nào đang chạy trên production, và làm sao trở lại phiên bản an toàn?

**GitOps** giải quyết vấn đề bằng cách dùng một nguồn khai báo được kiểm soát phiên bản (thường là Git) làm **nguồn trạng thái mong muốn**, và sử dụng bộ điều khiển trong cụm để liên tục **reconcile** trạng thái Kubernetes về trạng thái đó. **Flux** là bộ công cụ/controller GitOps cho Kubernetes; trên Azure, có thể tích hợp Flux v2 với AKS thông qua khả năng **GitOps (Flux v2)** và các tài nguyên Azure Kubernetes Configuration tương ứng.

Bài học nằm trong chương **Vận hành AKS** thuộc module **CLOUD_PROVIDERS_AZURE**. Ngoài YAML Kubernetes, chúng ta đặt GitOps trong hệ sinh thái Azure gồm subscription và resource group, Microsoft Entra ID và Azure RBAC, Azure Container Registry (ACR), virtual network, các dịch vụ lưu trữ/dữ liệu, Azure Monitor, bảo mật và chi phí. Mục tiêu là biết xây một quy trình **review → merge → reconcile → verify → rollback**, chứ không chỉ biết cài Flux.

Sau bài học, bạn có thể:

- Diễn giải các nguyên lý GitOps, sự khác nhau giữa **GitOps pull-based** và pipeline deploy push-based.
- Giải thích nhiệm vụ của Flux source-controller, kustomize-controller, helm-controller và các bộ điều khiển tự động hóa image khi được cài.
- Tổ chức Git repository cho nhiều môi trường/cluster bằng Kustomize hoặc Helm và phân biệt nguồn Git, Kustomization, HelmRelease.
- Thiết lập GitOps cho AKS bằng Azure CLI ở mức lab có quyền phù hợp, biết cách đọc trạng thái reconciliation.
- Thiết kế xác thực tới repository và ACR, quản lý secret an toàn, phân quyền tối thiểu và ranh giới giữa Git, Azure, Kubernetes.
- Điều tra drift, manifest lỗi, source không truy cập được, image pull lỗi, health check không đạt và sự cố xóa tài nguyên do prune.
- Rollback bằng một commit Git có kiểm soát, theo dõi ứng dụng sau rollout, và quyết định khi nào cần tạm dừng reconciliation.

## 1. GitOps là gì và giải quyết sự cố nào?

**GitOps** là một cách thực hành vận hành hệ thống khai báo: cấu hình mong muốn được lưu ở nguồn version-controlled, được kiểm tra/phê duyệt như code, và một controller tự đồng bộ tài nguyên đang chạy với cấu hình đã phê duyệt. Hình thức phổ biến là Git chứa Kubernetes manifests hoặc tham chiếu Helm chart/version, controller Flux quan sát source rồi áp dụng thay đổi vào cụm.

Giả sử production đang chạy Deployment `orders-api` với ba replicas. Một người dùng lệnh:

~~~bash
kubectl -n orders scale deployment/orders-api --replicas=1
~~~

Nếu Git đang khai báo `replicas: 3` và Flux chịu trách nhiệm trường đó, lần reconciliation tiếp theo có thể đưa `replicas` trở lại 3. Đây là **drift correction**: thay đổi thủ công ngoài nguồn trạng thái mong muốn không còn là sự thật cuối cùng.

Tuy nhiên, GitOps **không tự động phân biệt thay đổi nguy hiểm và an toàn**. Nếu người có quyền merge thay giá trị `replicas: 0`, Flux vẫn có thể áp dụng cấu hình đó nếu chính sách và quyền cho phép. Vì vậy GitOps phải đi cùng code review, RBAC, kiểm thử, policy, image scanning và giám sát.

### Những nguyên tắc thực hành

1. **Khai báo:** trạng thái tài nguyên được mô tả bằng YAML/Kustomize/Helm values, hạn chế các bước tùy biến khó tái lập.
2. **Version control:** mọi thay đổi quan trọng có commit, lịch sử, người review và liên kết change ticket.
3. **Tự động pull/reconcile:** controller lấy trạng thái mong muốn và cập nhật Kubernetes qua API, không cần pipeline CI lưu kubeconfig production.
4. **Quan sát và sửa lệch:** có trạng thái Ready/Reconciling, events, logs, alert và cơ chế xử lý lỗi.
5. **Phân quyền:** ai được merge, ai được deploy controller, ai được sửa namespace/cluster-scope phải được tách rõ.

Một hệ thống chỉ sao chép file YAML vào Git nhưng deploy bằng `kubectl apply` thủ công **chưa đạt đầy đủ vòng điều khiển GitOps**. Ngược lại, Flux reconcile liên tục nhưng repository không được bảo vệ thì vẫn thiếu nền tảng quản trị.

### Sơ đồ vòng lặp

~~~mermaid
flowchart LR
    DEV[Developer / Platform engineer] --> PR[Pull request]
    PR --> CHECK[Test, scan, policy, review]
    CHECK -->|Merge| GIT[(Git desired state)]
    GIT -->|Poll hoặc webhook| FLUX[Flux controllers trong AKS]
    FLUX -->|Kubernetes API| API[Kubernetes API server]
    API --> WORK[Deployments, Services, ConfigMaps...]
    WORK -. Status / events .-> OBS[Monitor + alert]
    API -. Trạng thái quan sát .-> FLUX
    FLUX -. Reconcile về desired state .-> API
~~~

Flux là **reconciler**, không phải nơi lưu source code hay image. Git repository, chart repository hoặc OCI artifact là nguồn cấu hình; ACR/registry là nơi lưu container images. **Image build và Kubernetes deployment là hai công đoạn khác nhau.**

## 2. Phân biệt CI, CD, GitOps và IaC

| Hoạt động | Đầu vào | Đầu ra | Ai thường thực hiện? |
|---|---|---|---|
| **CI** (Continuous Integration) | Source code, Dockerfile | Build/test, image digest, scan/SBOM | GitHub Actions, Azure Pipelines hoặc CI runner |
| **GitOps CD** | YAML/Kustomize/Helm values đã merge | Kubernetes workload theo cấu hình được duyệt | Flux controllers chạy trong AKS |
| **Infrastructure as Code** | Định nghĩa Azure resources | AKS, VNet, ACR, identities, monitoring, role assignments | Bicep/ARM/Terraform và pipeline hạ tầng |
| **Kubernetes manifests** | Mô tả đối tượng Kubernetes | Deployment, Service, ConfigMap, policy... | Flux áp dụng qua Kubernetes API |
| **Runtime monitoring** | Metrics, logs, traces, events | Cảnh báo, quyết định giữ hay rollback | Azure Monitor, Prometheus, App Insights, đội vận hành |

Ví dụ một phiên bản API mới:

1. CI build và kiểm thử image, push vào ACR với tag không bị ghi đè hoặc ghi nhận digest.
2. Một pull request ở **configuration repository** đổi image tham chiếu từ `orders-api:1.4.0` sang `orders-api:1.4.1`.
3. PR đi qua review, kiểm tra YAML/Kustomize và kiểm tra policy.
4. Sau khi merge, Flux lấy commit mới và áp dụng manifest.
5. Kubernetes tạo Pods mới theo Deployment rollout strategy.
6. Monitoring xác nhận readiness, error rate, latency và nghiệp vụ; nếu lỗi, revert commit thay vì để thay đổi thủ công lâu dài.

**Không nên cấp quyền kube-admin production cho CI chỉ để deploy image.** Với GitOps, CI cần quyền push image và đề xuất/cập nhật cấu hình trong Git theo cơ chế phê duyệt; Flux thực hiện cập nhật Kubernetes bằng quyền trong cụm. Cơ chế nào giữ bí mật Git credential và quyền của Flux cũng phải được bảo vệ.

### GitOps không thay cho Bicep/Terraform

Flux quản lý tài nguyên **Kubernetes API** và các CRD hiện có. Nó không tự tạo VNet, subnet, AKS cluster, Azure SQL hay ACR chỉ vì bạn thêm một Deployment vào Git. Có thể dùng các Kubernetes controllers/operator để quản lý thêm hạ tầng khi đã được hỗ trợ, nhưng đó là một kiến trúc mở rộng với rủi ro/phân quyền riêng, không phải mặc định.

Thông thường:

- **Azure IaC:** AKS cluster, node pools, identity, ACR, VNet, firewall, workload identity, Azure Monitor.
- **GitOps:** namespace được ủy quyền, application Deployment, Service, ConfigMap, Ingress, HelmRelease, một số policy/controller theo mức cho phép.
- **CI/CD và security:** build image, scan, PR validation, approve và promote.

## 3. Flux v2 có những thành phần nào?

Flux là một tập hợp controller Kubernetes. Sự hiện diện của các controller/phần mở rộng phụ thuộc cách Flux được cài, tính năng và phiên bản đang sử dụng; không mặc định mọi cluster đều có đầy đủ image automation.

| Thành phần | Chức năng | Resource API thường thấy |
|---|---|---|
| **source-controller** | Lấy Git/OCI/Helm nguồn, tạo artifacts cho các controller khác | `GitRepository`, `OCIRepository`, `HelmRepository` |
| **kustomize-controller** | Reconcile Kubernetes manifests dựa trên Kustomize | `Kustomization` (Flux CRD) |
| **helm-controller** | Reconcile Helm releases khai báo trong Git | `HelmRelease` |
| **notification-controller** | Gửi sự kiện/cảnh báo và nhận webhook theo cấu hình | `Alert`, `Provider`, `Receiver` |
| **image-reflector-controller** | Quan sát các image tags từ registry | `ImageRepository`, `ImagePolicy` |
| **image-automation-controller** | Cập nhật Git theo chính sách image automation nếu được cấp quyền | `ImageUpdateAutomation` |

**Kustomization của Flux** và **file Kustomize `kustomization.yaml`** là hai thứ khác nhau:

- `kind: Kustomization`, API group `kustomize.toolkit.fluxcd.io`: một đối tượng Kubernetes dùng để chỉ cho Flux **đọc source nào, path nào, reconcile/prune/health như thế nào**.
- File `kustomization.yaml` trong Git: hướng dẫn **Kustomize ghép tài nguyên**, base/overlay, images, namespace và patches.

Flux kustomize-controller thường dựng manifest từ path và thực hiện server-side apply qua Kubernetes API. Bộ điều khiển có thể theo dõi resource inventory để prune các đối tượng không còn trong desired state theo chính sách đã chọn.

### Dòng dữ liệu giữa controller

~~~mermaid
flowchart TD
    GIT[(Git configuration repository)]
    GIT --> SRC[source-controller / GitRepository]
    SRC --> ART[Source artifact]
    ART --> KUST[kustomize-controller / Flux Kustomization]
    ART --> HELM[helm-controller / HelmRelease]
    KUST --> KAPI[Kubernetes API]
    HELM --> KAPI
    KAPI --> PODS[Deployments, Services, Jobs, ConfigMaps]
    REG[(ACR images)] -->|Kubelet/container runtime pull| PODS
    IMGR[Image automation controllers nếu được bật] -. Tạo commit thay image .-> GIT
~~~

**ACR image pull thuộc đường chạy Pod**, không phải đường source-controller đọc Git. AKS nodes/kubelet cần được cấp quyền kéo image, chẳng hạn cơ chế **attach ACR**/role assignment hoặc identity phù hợp. Khi image `ImagePullBackOff`, source-controller vẫn có thể `Ready=True` vì nó đã đọc được YAML; kiểm tra Pod events và registry permission riêng.

## 4. GitOps trên AKS: cách tích hợp Flux với Azure

Có thể triển khai Flux như dự án upstream trên Kubernetes hoặc dùng khả năng **GitOps (Flux v2)** được tích hợp qua **Azure Kubernetes Configuration** cho AKS. Hai hướng có các bước cài đặt/quản trị khác nhau, nhưng đều dựa trên mô hình Kubernetes controllers reconcile desired state.

Với tích hợp Azure, các thành phần thường gặp:

1. **AKS cluster** và quyền truy cập control plane đúng phạm vi.
2. **Flux extension** (extension type `microsoft.flux`) hoạt động trên cluster.
3. **Flux configuration** ở Azure (`Microsoft.KubernetesConfiguration/fluxConfigurations`) tham chiếu Git/OCI source và một hoặc nhiều kustomizations.
4. Các **Flux Kubernetes custom resources** được tạo/điều phối trong cluster theo cấu hình tích hợp.
5. **Azure RBAC + Kubernetes RBAC** cho ai được tạo configuration/extension và ai được Flux phép sửa resource.
6. **Source credentials** nếu repository là private và đường mạng tới Git/OCI source.

### Kiến trúc quản trị

~~~mermaid
flowchart TB
    SUB[Azure Subscription / Resource Group] --> AKS[AKS cluster]
    SUB --> GCFG[Azure Flux configuration]
    GCFG --> EXT[Flux extension]
    EXT --> CONTROLLERS[Flux controllers trong AKS]
    REPO[(Git desired-state repository)] --> CONTROLLERS
    CONTROLLERS --> API[Kubernetes API]
    API --> NS1[Namespace orders]
    API --> NS2[Namespace payments]
    ACR[(Azure Container Registry)] -->|Image pull| NS1
    ACR -->|Image pull| NS2
    MON[Azure Monitor + Git history] -. Evidence .-> CONTROLLERS
~~~

Một nguồn Git đã kết nối **không tự cấp toàn quyền** cho controller ở mọi namespace. Quyền thực thi phụ thuộc cách Flux được cài/cấu hình, service account và Kubernetes RBAC. Trong cấu hình Azure, lựa chọn scope `cluster` hoặc `namespace` có ảnh hưởng tới phạm vi quản lý của cấu hình; kiểm tra contract của extension và namespace permissions trước khi gán môi trường production.

### “Azure resource Ready” và “workload healthy” khác nhau

Ví dụ Azure Resource Manager báo extension provisioned và GitOps configuration đã tạo, nhưng Deployment không lên vì image tag không tồn tại. Điều này không đồng nghĩa GitOps end-to-end thành công. Cần đối chiếu **ít nhất bốn lớp**: Azure extension/configuration, Flux GitRepository/Kustomization, Kubernetes Deployment/Pod, rồi health ứng dụng qua request thật.

## 5. Cấu trúc repository cho AKS nhiều môi trường

Không có một layout repository duy nhất được Flux bắt buộc. Mẫu dễ quản trị dùng **base** chung và **overlays** cho dev/staging/prod, cộng với thư mục cluster để chỉ định workload nào thuộc cluster nào.

~~~text
gitops-config/
├── apps/
│   └── orders-api/
│       ├── base/
│       │   ├── deployment.yaml
│       │   ├── service.yaml
│       │   └── kustomization.yaml
│       └── overlays/
│           ├── dev/
│           │   └── kustomization.yaml
│           └── prod/
│               └── kustomization.yaml
├── clusters/
│   ├── aks-dev/
│   │   ├── orders-api.yaml
│   │   └── kustomization.yaml
│   └── aks-prod/
│       ├── orders-api.yaml
│       └── kustomization.yaml
└── README.md
~~~

Đây là **cấu trúc minh họa trong repository Git của người học**, không phải lời đề nghị đọc/ghi các tệp ngoài hai file bài học được giao cho worker. Trong lab thực tế, người học có thể tạo repository riêng theo mẫu đã được review.

Hai mức cần hiểu:

- `apps/orders-api/base` chứa cấu hình Kubernetes được tái dùng.
- `apps/orders-api/overlays/prod` tùy biến image tag, replica count, tài nguyên và cấu hình production.
- `clusters/aks-prod` là entrypoint cho Flux: khai báo những ứng dụng hoặc Kustomization nào được áp dụng lên cluster production.

### Một repo hay nhiều repo?

| Phương án | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| **Monorepo GitOps** cho nhiều app/cluster | Dễ thấy thay đổi liên quan, một nơi đặt policy và review | Scope quyền merge quá rộng nếu không có CODEOWNERS/branch protection |
| **Repo theo team/app** | Quyền sở hữu rõ, pipeline độc lập | Cần cơ chế bootstrap/aggregation và nhất quán chuẩn |
| **Repo theo môi trường** | Hàng rào giữa staging/production rõ | Có thể tạo duplication và khó promote bản đã test |
| **Tách source code và config repo** | CI và quyền đổi deployment tách biệt | Cần liên kết commit/image digest giữa hai repo |

Với production, nên dùng **protected branch, PR review, CODEOWNERS, status checks và audit**. Nếu dùng cùng một Git branch cho dev và production, phải có folder/scope rõ và quyền merge đủ chặt; không để một PR thử nghiệm vô tình sửa overlay production.

## 6. Desired state: Kubernetes manifests và Kustomize

Ví dụ workload `orders-api` chạy trong namespace `orders`. Container image được lấy từ ACR; Deployment có request/limit, readiness/liveness probe để rollout có bằng chứng.

### 6.1. Deployment base

~~~yaml
# apps/orders-api/base/deployment.yaml (ví dụ minh họa)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 2
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
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
          image: myregistry.azurecr.io/orders-api:1.4.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
~~~

Đây là **manifest mẫu**, cần được điều chỉnh theo CPU/RAM, thời gian startup, số replicas, availability zones và SLO thực tế. Với ứng dụng khởi động lâu, nên cân nhắc `startupProbe` thay vì chỉ tăng ngẫu nhiên `initialDelaySeconds`. Nếu readiness phụ thuộc database chung quá chặt, một lỗi DB có thể khiến toàn bộ Pods bị loại khỏi Service.

### 6.2. Service

~~~yaml
# apps/orders-api/base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

`ClusterIP` giúp ứng dụng truy cập nội bộ trong cluster; nó **không tự công bố Internet endpoint**. Nếu cần ingress công khai, phải thiết kế controller/gateway, domain, TLS/WAF và chính sách mạng riêng. Hãy tránh đưa database credentials vào manifests.

### 6.3. Base Kustomize

~~~yaml
# apps/orders-api/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
~~~

### 6.4. Overlay production

~~~yaml
# apps/orders-api/overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: orders
resources:
  - ../../base
images:
  - name: myregistry.azurecr.io/orders-api
    newTag: 1.4.1
replicas:
  - name: orders-api
    count: 3
~~~

Nếu namespace `orders` chưa tồn tại, phải tạo bằng một manifest hoặc quy trình bootstrap được quản lý trước khi áp dụng tài nguyên namespaced. Thêm `namespace: orders` vào Kustomize **không tự chứng minh** namespace đã tồn tại. Với GitOps nhiều app, có thể có Kustomization chuyên quản namespace, RBAC, quota và network policy rồi để app phụ thuộc vào lớp này.

Ví dụ resource cho **lớp platform bootstrap**, triển khai trước workload:

~~~yaml
# platform/namespaces/orders.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders
  labels:
    application: orders
    environment: production
~~~

Namespace này nên được quản lý ở Kustomization nền tảng riêng, có review cho RBAC, quota và NetworkPolicy. Không để nhiều Kustomization cùng quản Namespace `orders` bằng các desired states khác nhau; resource dùng chung phải có một owner rõ ràng.

**Khuyến nghị artifact:** Kustomize images field dùng tag `1.4.1` chỉ để minh họa. Production nên dùng tag immutable được quản lý và ghi lại digest, hoặc khai báo image bằng digest theo quy trình công cụ hỗ trợ, nhằm tránh repository tag bị thay nội dung ngoài dự kiến.

## 7. Flux custom resources: GitRepository và Kustomization

Để hiểu điều gì xảy ra bên trong, hãy xem cách Flux dùng CRD. Đây là **cách cấu hình Flux thuần Kubernetes**, tách với cách tạo GitOps configuration thông qua tài nguyên Azure ở phần tiếp theo; không nhất thiết phải áp dụng đồng thời hai phương pháp tạo cùng resource.

### 7.1. GitRepository: chỉ định nguồn cấu hình

~~~yaml
# flux-system/git-source.yaml (mẫu cho Flux upstream)
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: platform-config
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/example-org/gitops-config
  ref:
    branch: main
~~~

`url` là repository **minh họa**, không phải URL thật. Đối với private Git, cần cấu hình xác thực qua secret/identity được hỗ trợ; không thêm token trực tiếp vào URL hoặc YAML đã commit. Source-controller định kỳ lấy trạng thái Git và công bố artifact ở commit được nhận diện, giúp các Kustomization đọc cùng một nguồn phiên bản.

Nếu nguồn không truy cập được vì DNS, proxy, credentials hoặc branch sai, `GitRepository` có thể không Ready, và việc cập nhật manifests sẽ bị dừng cho đến khi nguồn phục hồi. Khi mạng tạm mất, những tài nguyên Kubernetes đã triển khai **không tự biến mất chỉ vì không fetch được Git**; tác động cụ thể phụ thuộc trạng thái/last applied configuration và khả năng hoạt động của controller.

### 7.2. Flux Kustomization: áp dụng một path

~~~yaml
# flux-system/orders-prod.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: orders-prod
  namespace: flux-system
spec:
  interval: 5m
  retryInterval: 1m
  timeout: 3m
  path: ./apps/orders-api/overlays/prod
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform-config
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: orders-api
      namespace: orders
~~~

Các trường quan trọng:

| Trường | Vai trò | Điểm cần chú ý |
|---|---|---|
| `interval` | Chu kỳ reconcile bình thường | Không đảm bảo đúng từng giây; controller có lịch/giới hạn xử lý |
| `retryInterval` | Chu kỳ thử lại sau lỗi theo cấu hình được hỗ trợ | Không thay timeout của API hay app |
| `path` | Thư mục trong artifact Git mà Flux dựng manifests | Sai path làm Kustomization failed hoặc không có desired resources |
| `sourceRef` | Nguồn Flux sử dụng | Tên và namespace phải phù hợp |
| `prune: true` | Dọn những resource Flux từng quản lý nhưng không còn trong desired set theo semantics dịch vụ | **Có thể xóa nhầm tài nguyên nếu sửa/xóa manifest sai** |
| `healthChecks` | Kiểm tra tài nguyên sau apply | Deployment readiness khác kiểm tra nghiệp vụ end-to-end |
| `suspend` (nếu đặt) | Tạm dừng reconciliation của đối tượng | Chỉ dùng theo runbook, tránh drift kéo dài |

Ví dụ `healthChecks` chờ Deployment đạt trạng thái được hỗ trợ theo Flux, nhưng **không** biết API có tạo đơn hàng chính xác hay không. Pipeline production nên có synthetic/business tests ngoài condition Ready của Kubernetes.

### 7.3. Flux Kustomization và Kustomize kustomization.yaml

Hai YAML này phối hợp:

~~~text
Flux Kustomization (CRD trong cluster)
  spec.sourceRef: platform-config
  spec.path: ./apps/orders-api/overlays/prod
          |
          v
Kustomize kustomization.yaml (file trong Git)
  resources: ../../base
  images: newTag 1.4.1
  replicas: count 3
          |
          v
Deployment + Service theo cấu hình cuối cùng
~~~

Nếu thiết kế **bootstrap nhiều Kustomization**, có thể đặt Flux CRDs ở `clusters/aks-prod` rồi cấu hình một root Kustomization để áp dụng các CRDs đó. Điều quan trọng là dùng **một nguồn sở hữu rõ ràng**: không nên vừa tạo `orders-prod` bằng Azure Flux configuration vừa tạo một đối tượng `orders-prod` khác bằng manifests, rồi để hai nơi cùng sửa nó.

### 7.4. DependsOn và thứ tự triển khai

Một ứng dụng có thể cần namespace, quota, policy hoặc custom resource definition trước. Flux Kustomization hỗ trợ phụ thuộc giữa các Kustomization phù hợp:

~~~yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: orders-prod
  namespace: flux-system
spec:
  interval: 5m
  path: ./apps/orders-api/overlays/prod
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform-config
  dependsOn:
    - name: platform-namespaces
~~~

Đoạn trên là ví dụ **thay thế/biến thể** của Kustomization trước, không phải một đối tượng thứ hai cùng tên cần apply song song. `platform-namespaces` phải thực sự tồn tại và Ready ở phạm vi Flux cho phép. Không tạo vòng phụ thuộc A → B → A. Thứ tự phụ thuộc giúp tránh lỗi resource chưa tồn tại nhưng không thay thế migration database hay dependency readiness của ứng dụng.

## 8. Thiết lập GitOps trên AKS bằng Azure CLI

Các bước bên dưới mô tả **một lab tham chiếu**, không phải thao tác được thực thi trong lúc viết bài. Cần có Azure subscription thử nghiệm, AKS cluster đã tạo sẵn, Git repository có manifests an toàn và ACR image hợp lệ. Người thực hiện có quyền quản lý AKS/Flux extension/configuration và quyền Kubernetes cần thiết.

**Giới hạn phạm vi lab:** dùng đúng cụm thử nghiệm. Lệnh tạo extension và Flux configuration thay đổi cách cluster reconcile tài nguyên; tuyệt đối không chạy vào production chỉ để kiểm tra cú pháp.

### 8.1. Chuẩn bị công cụ

~~~bash
az login

SUBSCRIPTION_ID="<subscription-id-lab>"
RG="rg-aks-gitops-lab"
AKS="aks-gitops-lab"
CONFIG_NAME="aks-prod-config"
REPO_URL="https://github.com/example-org/gitops-config"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name,tenant:tenantId}" -o table

# Kiểm tra phiên bản Azure CLI và khả năng hỗ trợ extensions.
az version
az extension show --name k8s-configuration --output json
az extension show --name k8s-extension --output json
~~~

Nếu chưa có extension hỗ trợ, có thể cài trong môi trường được phép:

~~~bash
az extension add --name k8s-configuration --upgrade
az extension add --name k8s-extension --upgrade
~~~

Tên tham số, extension version và các tính năng có thể thay đổi. Hãy kiểm tra `az k8s-configuration flux --help` và `az k8s-extension create --help` với bản CLI thực tế. Không cài/cập nhật extension trong runner production mà không kiểm soát version và kiểm thử.

### 8.2. Kiểm tra cluster mục tiêu

~~~bash
az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{id:id,location:location,provisioningState:provisioningState}" \
  --output json
~~~

Ở môi trường thử nghiệm có quyền, có thể lấy kubeconfig:

~~~bash
az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl cluster-info
kubectl get nodes
~~~

**Không coi quyền `get-credentials` là quyền vô hạn:** truy cập Kubernetes API còn phụ thuộc Microsoft Entra integration, Kubernetes RBAC/Azure RBAC for Kubernetes authorization và network private cluster. Không yêu cầu `--admin` nếu không thực sự cần và chưa được phê duyệt.

### 8.3. Cài hoặc xác minh Flux extension

Trong kịch bản tích hợp Azure được hỗ trợ, tham khảo cú pháp minh họa:

~~~bash
az k8s-extension create \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name flux \
  --extension-type microsoft.flux \
  --scope cluster \
  --release-train stable
~~~

Nếu extension đã tồn tại, **không tạo trùng**. Xem trạng thái:

~~~bash
az k8s-extension show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name flux \
  --output json
~~~

Đừng mặc định extension `ProvisioningState=Succeeded` nghĩa là mọi Kustomization đều Ready; kiểm tra objects trong cluster và trạng thái source riêng. Một số workflow Azure Flux configuration có thể yêu cầu/thiết lập extension theo thứ tự khác: kiểm tra phiên bản tài liệu Azure/CLI tương ứng trước khi tự động hóa.

### 8.4. Tạo Flux configuration trỏ vào repository

Ví dụ cấu hình root hoặc app path trên AKS. Để giữ lab đơn giản, **chỉ trỏ vào overlay ứng dụng** đã chứa các manifest Kubernetes:

~~~bash
az k8s-configuration flux create \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  --scope cluster \
  --namespace flux-system \
  --url "$REPO_URL" \
  --branch main \
  --kustomization name=orders-prod path=./apps/orders-api/overlays/prod prune=true
~~~

Đây là **một cách tạo configuration tích hợp Azure**, thay cho việc apply thủ công các CRDs `GitRepository`/`Kustomization` có cùng mục đích ở phần 7. Những trường cụ thể như `--kustomization`, `--namespace` hoặc cơ chế xác thực repo cần kiểm tra bằng `az k8s-configuration flux create --help` theo CLI version.

**Private Git:** URL public trong ví dụ nhằm không làm lộ credential. Với repo private, dùng SSH deploy key/HTTPS credential hoặc cơ chế tích hợp được hỗ trợ và có quản lý secret; không ghi PAT hay private key vào command history, pipeline log hoặc file YAML theo cách công khai.

**Dữ liệu đầu vào:** repo phải có thật, path phải tồn tại, image được ACR pull, namespace cần thiết đã được tạo và cluster có đủ quyền tạo resource. Lệnh tạo configuration thành công nhưng path rỗng/sai sẽ không tạo workload như mong đợi.

### 8.5. Xem trạng thái Flux configuration và cluster

~~~bash
az k8s-configuration flux show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  --output json

kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl get deployments -n orders
kubectl get pods -n orders
~~~

Nếu cluster không có Flux CRDs, kiểm tra extension và trạng thái cài đặt trước khi kết luận Git repo sai. Nếu CRDs tồn tại nhưng không Ready, kiểm tra controller logs, conditions và source artifact. Nếu Flux Ready mà Pod không chạy, xem Deployment status, image pull và runtime readiness.

### 8.6. Reconcile theo yêu cầu

Ở cụm có **Flux CLI** tương thích và đủ Kubernetes permissions:

~~~bash
# Flux CLI thao tác vào cluster đã chọn ở kubectl context.
flux get sources git -A
flux get kustomizations -A

# Ví dụ tên/source phải được xác nhận từ lệnh flux get.
flux reconcile kustomization orders-prod \
  --namespace flux-system \
  --with-source
~~~

`flux reconcile` yêu cầu reconciliation ngay, **không thay đổi commit Git** và không làm lệnh apply “bỏ qua” dữ liệu không hợp lệ. Nếu source là private và auth lỗi, reconcile lại liên tục không giải quyết nguyên nhân. Cần kiểm tra GitRepository credential/network; nếu YAML thiếu CRD hoặc sai schema, phải sửa PR trong Git.

**Chú ý tên nguồn:** Azure Flux configuration có thể đặt tên đối tượng trong cluster theo quy tắc tích hợp. Đừng dùng tên placeholder trong ví dụ để đoán `GitRepository.metadata.name`; hãy đọc các objects thực tế. Trong khi đó `orders-prod` là tên kustomization minh họa đã đặt khi tạo configuration.

## 9. Chiến lược promotion: dev → staging → production

GitOps không buộc mọi môi trường luôn chạy cùng phiên bản. Một thiết kế thường gặp giữ **image digest bất biến** và chuyển đúng artifact đã qua kiểm thử từ môi trường thấp lên cao.

~~~mermaid
flowchart LR
    CODE[Source commit] --> CI[Build + unit/integration + scan]
    CI --> ACR[ACR: image digest D]
    ACR --> PRDEV[PR cấu hình dev dùng D]
    PRDEV --> FLUXDEV[Flux dev reconcile]
    FLUXDEV --> TEST[Smoke + contract + load tests]
    TEST --> PRPROD[PR production overlay dùng đúng D]
    PRPROD --> APPROVE[CODEOWNERS / change approval]
    APPROVE --> FLUXPROD[Flux prod reconcile]
    FLUXPROD --> MON[Health, SLO, business checks]
~~~

### Một cách quản lý overlay

~~~yaml
# apps/orders-api/overlays/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: orders
resources:
  - ../../base
images:
  - name: myregistry.azurecr.io/orders-api
    newTag: 1.4.2-rc.1
replicas:
  - name: orders-api
    count: 1
~~~

Production dùng `1.4.1` cho tới khi phiên bản mới được phê duyệt. **Không chỉ đẩy tag mới vào ACR rồi mong Flux tự đổi deployment**: nếu Git không thay, Flux vẫn reconcile cùng desired image reference, trừ khi bạn đã chủ động cấu hình **image automation** hoặc công cụ quản lý tag phù hợp.

### Thiết kế branch và quyền merge

| Môi trường | Cách bảo vệ |
|---|---|
| Dev | PR/CI cơ bản, chỉ team liên quan được sửa overlay dev |
| Staging | Integration tests, contract tests và giới hạn quyền truy cập dữ liệu |
| Production | Protected branch, CODEOWNERS, approval có trách nhiệm, policy scan, audit và rollback plan |

Không để CI tự sửa thẳng production branch bằng credential có quyền admin mà không có cơ chế review tương ứng, kể cả khi image scan đã pass. **Lỗi business logic vẫn có thể lọt qua scan bảo mật**.

## 10. Reconciliation, drift detection và điều khiển tài nguyên

Flux hoạt động theo chu kỳ: fetch artifact, build manifests, so sánh với trạng thái hiện có, rồi apply sửa đổi theo thiết kế. Khi người dùng sửa Kubernetes resource trực tiếp ngoài Git, Flux có thể đưa phần resource mà nó quản lý trở về desired state. Đây là điểm mạnh nhưng cũng là nguyên nhân khiến cách “sửa tạm bằng kubectl” không bền.

### 10.1. Ví dụ drift do sửa trực tiếp

Desired state trong Git:

~~~yaml
spec:
  replicas: 3
~~~

Một người vận hành dùng lệnh:

~~~bash
kubectl -n orders scale deployment/orders-api --replicas=1
~~~

Nếu trường `replicas` thuộc phạm vi Flux đang quản lý và không có cơ chế điều khiển khác được cấu hình để tránh xung đột, controller có thể đưa giá trị về 3 ở lần reconcile phù hợp.

**Ngoại lệ quan trọng: HPA và field ownership.** Khi Horizontal Pod Autoscaler quản lý `replicas`, nếu YAML/Kustomize và HPA cùng ghi liên tục vào cùng trường có thể gây va chạm hoặc hành vi khó đoán. Thiết kế GitOps phải biết **trường nào thuộc quyền điều khiển của Flux, HPA hay operator**. Không áp dụng nhận định đơn giản “replicas luôn về Git” cho một Deployment có HPA mà chưa kiểm tra cách sở hữu trường.

### 10.2. Reconciliation interval

Các giá trị `interval: 1m` hoặc `5m` là chu kỳ dự kiến, **không phải SLA yêu cầu commit được áp dụng đúng sau 60 hoặc 300 giây**. Thời gian thực tế còn chịu ảnh hưởng:

- Chu kỳ fetch Git/artifact và trạng thái controller.
- Hàng đợi reconciliation, backoff/retry khi lỗi.
- Số lượng object và thời gian API server xử lý.
- Thời gian rollout Deployment/HelmRelease.
- Health check của Kustomization và readiness Pods.
- Webhook receiver nếu cấu hình giúp giảm độ trễ phát hiện thay đổi.

Đừng giảm interval của hàng nghìn source xuống vài giây để “deploy ngay”; nó có thể tăng tải lên Git provider, Kubernetes API và controller mà chưa giải quyết chất lượng phát hành.

### 10.3. Phân biệt ba loại drift

| Loại drift | Ví dụ | Tác động/giải pháp |
|---|---|---|
| **Kubernetes runtime drift** | `kubectl edit` đổi image/replica ở resource do Flux quản lý | Flux có thể reconcile về desired state |
| **Git/config drift** | Overlay prod dùng tag khác bản đã phê duyệt trong release record | Review PR, audit commit, bảo vệ branch/policy |
| **Azure infrastructure drift** | NSG/VNet/ACR role bị đổi ngoài Terraform/Bicep | Flux không tự sửa nếu không có controller khai báo quản lý Azure resource tương ứng |

Không nên gán mọi loại drift cho Flux. Để quản trị toàn diện, kết hợp Azure Policy, IaC drift detection và Kubernetes policy/controller phù hợp.

## 11. Prune: tính năng mạnh nhất cũng là rủi ro lớn

Trong Flux Kustomization, `prune: true` cho phép controller xóa những resource **trước đây được quản lý trong inventory của Kustomization** nhưng không còn thuộc desired set theo logic của nó. Điều này giúp Git thật sự là nguồn trạng thái mong muốn: xóa manifest thì hệ thống dọn resource tương ứng. Nhưng với sai sót trong PR, hậu quả cũng có thể nghiêm trọng.

### 11.1. Ví dụ tai nạn

Giả sử repo có:

~~~text
apps/orders-api/overlays/prod/
  deployment.yaml
  service.yaml
  kustomization.yaml
~~~

Một commit vô tình xóa `service.yaml` khỏi Kustomize resources. Nếu Flux đang prune tài nguyên Service này, Service có thể bị xóa khỏi cluster và traffic tới API bị gián đoạn. Nếu resource chứa dữ liệu như PersistentVolumeClaim hoặc CustomResource có finalizer, tác động phụ thuộc cơ chế bảo vệ và retention của tài nguyên; **không được coi prune là thao tác vô hại**.

### 11.2. Bảo vệ trước khi bật prune

- Bắt buộc review các PR có xóa hoặc đổi tên tài nguyên, đặc biệt ở namespace prod.
- Dùng `kustomize build`/`kubectl diff` hoặc công cụ validate theo phạm vi và quyền phù hợp để thấy đối tượng thay đổi.
- Phân tách Kustomization quản lý **resource dùng chung/stateful** khỏi Kustomization của workload stateless.
- Với tài nguyên cần bảo vệ, đánh giá annotation/chính sách prune của Flux hoặc deletion policy được hỗ trợ; xác minh semantics theo phiên bản đang chạy.
- Dùng Git history, branch protection và code owners để hạn chế lệnh xóa vô ý.
- Lập backup và phương án restore độc lập cho dữ liệu có giá trị.

**Không tự đặt `prune: false` cho mọi thứ rồi cho rằng đã an toàn.** Khi resource bị xóa khỏi Git nhưng không được prune, object cũ có thể tồn tại vô thời hạn, khiến hệ thống drift và khó quản lý. Chọn policy theo **lifecycle từng tài nguyên**.

### 11.3. Chuyển quyền sở hữu resource

Nếu muốn tách một Deployment ra khỏi Kustomization A để Kustomization B quản lý, cần lập kế hoạch handoff để tránh hai controller cùng apply hoặc A prune object trước khi B kịp tiếp quản. Chuyển owner trong một PR không đủ nếu các thay đổi không đồng bộ và không có thứ tự.

Hãy xác định rõ:

1. Resource ID gồm group/version/kind/namespace/name.
2. Kustomization nào đang giữ inventory/field ownership.
3. Policy prune/deletion hiện tại.
4. B sẽ áp dụng lúc nào, dependencies và rollback.
5. Cách chứng minh không có thời gian resource bị orphan hoặc bị xóa.

## 12. Helm với Flux: HelmRepository và HelmRelease

Nhiều tổ chức triển khai các hệ thống như ingress controller, monitoring, cert-manager hoặc ứng dụng từ **Helm chart**. Flux có thể quản lý những release này bằng controller và CRDs phù hợp. Với GitOps, không nên dùng `helm upgrade` tay như kênh triển khai chính trên resource do HelmRelease quản lý: reconcile có thể đưa trạng thái về bản khai báo.

### 12.1. HelmRepository

~~~yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: demo-charts
  namespace: orders
spec:
  interval: 10m
  url: https://charts.example.org
~~~

`https://charts.example.org` là **địa chỉ ví dụ không dùng làm nguồn production**. Với OCI Helm chart hoặc private chart registry, dùng loại source/protocol được hỗ trợ và cấu hình xác thực đúng; không mặc định chart HTTP index và OCI là một giao thức.

### 12.2. HelmRelease

~~~yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: sample-api
  namespace: orders
spec:
  interval: 5m
  chart:
    spec:
      chart: example-api
      version: "1.2.3"
      sourceRef:
        kind: HelmRepository
        name: demo-charts
        namespace: orders
  values:
    replicaCount: 3
    image:
      repository: myregistry.azurecr.io/orders-api
      tag: "1.4.1"
    service:
      type: ClusterIP
~~~

Đây là manifest **minh họa cú pháp/ý tưởng**: chart `example-api`, `values` và endpoint ví dụ không được giả định tồn tại. Khi đưa vào repository thật, phải kiểm tra schema chart, hỗ trợ version HelmRelease API, namespace/permissions và các giá trị bắt buộc của chart.

### 12.3. Nên dùng Kustomize hay Helm?

| Tiêu chí | Kustomize | Helm qua Flux |
|---|---|---|
| Cấu hình chủ đạo | YAML Kubernetes + base/overlay/patch | Chart templates + values + release lifecycle |
| Phù hợp | Workload nội bộ ít template, tách môi trường | Ứng dụng đóng gói thành chart hoặc nền tảng có chart được duy trì |
| Xác định phiên bản | Git commit + manifests/image | Git commit + chart version + values/image |
| Rollback GitOps | Revert/PR sửa overlay, Flux apply lại | Revert chart version/values, Flux reconcile HelmRelease |
| Rủi ro | Prune và thay đổi field/resource | Helm hooks, CRDs, dependencies, upgrade/remediation policy |

**Helm rollback thủ công chưa chắc bền** khi HelmRelease vẫn khai báo bản mới. Với Flux, quy trình chuẩn là **revert desired state trong Git**, rồi quan sát helm-controller reconcile. Helm controller có chiến lược remediation theo cấu hình được hỗ trợ; vẫn cần kiểm thử ứng dụng và xử lý migration dữ liệu riêng.

## 13. Image automation với Flux: dùng được nhưng cần kiểm soát

Flux có các controller mở rộng giúp:

1. Quan sát tags/digest mới của image từ ACR hoặc registry (`ImageRepository`).
2. Chọn tag theo policy (`ImagePolicy`).
3. Đề xuất hoặc commit thay đổi trong Git (`ImageUpdateAutomation`) theo cấu hình đã được phép.
4. Source/Kustomization reconcile commit được cập nhật và triển khai.

~~~mermaid
flowchart LR
    CI[CI build/scan] --> ACR[ACR repository]
    ACR --> REFLECT[Image reflector + ImagePolicy]
    REFLECT --> AUTO[ImageUpdateAutomation]
    AUTO -->|Git commit khi được phép| GIT[Git configuration repository]
    GIT --> FLUX[Flux source/kustomize controller]
    FLUX --> AKS[AKS deployment]
~~~

Image automation **không nhất thiết được cài/bật mặc định** trong mọi mô hình Flux extension. Nó cũng không thay thế phê duyệt production: nếu controller có quyền ghi thẳng branch mà không có PR gate, một image chưa kiểm thử đầy đủ có thể trở thành desired state production.

### Chính sách khuyến nghị

- Với **dev**, có thể tự động chọn image từ nhánh build thử nghiệm theo policy và kiểm tra.
- Với **staging**, giới hạn nguồn image đã scan và qua integration tests.
- Với **production**, ưu tiên commit/pull request do pipeline đề xuất với **human approval hoặc gate tự động có bằng chứng đủ mạnh**, thay vì auto-update trực tiếp.
- Dùng tag immutable, metadata build và lưu digest. Tránh policy mơ hồ chỉ chọn `latest`.
- Giới hạn Git write credentials của controller automation, tách quyền branch dev/prod và bảo vệ deploy keys.
- Khi dùng ACR có private endpoint, image reflector cần network/DNS và quyền đọc registry; đường này có thể khác với kubelet pull image.

### Có cần image automation cho GitOps?

**Không bắt buộc.** Mô hình ổn định nhất cho nhiều đội là CI chỉ build/push image, rồi một PR được review thay image reference trong Git. Flux reconcile PR đã merge. Image automation hữu ích khi có nhiều image/tần suất release cao và đã có kiểm soát phù hợp, nhưng làm tăng bề mặt quyền và độ phức tạp quan sát.

## 14. Bảo mật GitOps: identity, secrets và phạm vi quyền

GitOps thay đổi điểm thực thi từ pipeline/laptop sang các controller **luôn chạy trong cluster**. Do đó, quyền của controller và độ tin cậy của source Git trở thành tài sản quan trọng. Một commit độc hại được merge vào branch production có thể trở thành thao tác thay đổi Kubernetes tự động.

### 14.1. Bốn lớp quyền khác nhau

| Lớp | Ví dụ quyền | Sai lầm cần tránh |
|---|---|---|
| **Git** | Ai có thể xem/merge repo, tạo tag/release, cập nhật pipeline? | Token ghi toàn bộ repo hoặc bỏ branch protection |
| **Azure control plane** | Ai tạo Flux extension/configuration, quản lý AKS/ACR/identities? | Cấp Owner toàn subscription cho developer cần xem deployment |
| **Kubernetes API** | Service account Flux có thể tạo/xóa đối tượng nào? | Controller của team ứng dụng có cluster-admin trên mọi namespace |
| **Data plane** | Pod runtime có quyền đọc Blob/SQL/Key Vault không? | Coi Flux/Kubernetes admin permission là quyền truy cập dữ liệu ứng dụng |

**Microsoft Entra ID/Azure RBAC** quản lý Azure resources và có thể tích hợp Kubernetes authorization; **Kubernetes RBAC** quản lý thao tác trên Kubernetes API theo cấu hình cluster. Đây là hai hệ phân quyền cần thiết kế phối hợp, không mặc định một vai trò Azure `Contributor` đủ mọi hành động bên trong Kubernetes.

### 14.2. Giới hạn phạm vi controller

Một mô hình production:

- Team nền tảng sở hữu namespace `flux-system`, controllers, cluster-scoped CRDs, network policies chung và policy admission.
- Team `orders` chỉ được đề xuất sửa manifest thuộc app/namespace của mình qua PR; Flux Kustomization ứng dụng nên chạy với **service account có quyền tối thiểu** nếu kiến trúc Flux hỗ trợ.
- Team bảo mật xét duyệt những thay đổi ảnh hưởng RBAC, ClusterRole, admission policies, Gateway/Ingress công khai và network policies.
- Pipeline CI có quyền build/push vào ACR và tạo PR; không nhận kubeconfig production có quyền admin.

Flux Kustomization có trường `spec.serviceAccountName` theo cơ chế được hỗ trợ để reconcile với identity Kubernetes giới hạn quyền. Khi dùng service account khác, phải cấp đủ permissions đối với resource cần quản lý, bao gồm read/list/watch/patch và delete nếu bật prune, nhưng **không cấp thêm cluster-wide rights vô lý**. Kiểm tra namespace của service account và RoleBinding/ClusterRoleBinding theo model cụm, đặc biệt khi Flux CRDs thuộc namespace `flux-system` nhưng tài nguyên đích ở `orders`.

**Đừng tự nhầm `scope=namespace` khi tạo Azure Flux configuration với việc Flux controllers tự động không thể sửa bất kỳ cluster-scoped resource nào.** Phạm vi hiệu lực phụ thuộc extension, cấu hình service account, Kubernetes RBAC và tài nguyên CRD được quản lý; hãy xác minh quyền thực tế, không chỉ tên flag.

### 14.3. Nguồn Git private và credential

Với repository private, phương án truy cập có thể gồm SSH deploy key, HTTPS token hoặc identity/workload federation được tích hợp trong môi trường hỗ trợ. Quy tắc:

1. Ưu tiên credential **read-only** cho source-controller; chỉ image automation controller thực sự cần quyền write khi được bật.
2. Hạn chế scope token theo repo/branch, thời gian hiệu lực và khả năng rotate.
3. Không dán PAT/private key vào manifest Git, Docker image, command history hoặc ticket công khai.
4. Kiểm tra SSH known_hosts/TLS certificate validation theo khả năng tích hợp.
5. Theo dõi authentication failures và sự kiện thay đổi credential.
6. Đảm bảo đường mạng tới Git provider và registries được bảo vệ bởi DNS, proxy/firewall/Private Endpoint phù hợp.

Nếu source nằm ở một dịch vụ Git ngoài Azure, mạng AKS cần truy cập endpoint đó theo cơ chế cluster; việc AKS có private endpoint tới ACR **không** đồng nghĩa source-controller truy cập được Git provider.

### 14.4. Không commit plaintext secrets

Ví dụ manifest sau **không được commit** vào repo production:

~~~yaml
# Ví dụ KHÔNG AN TOÀN: không áp dụng và không commit vào Git
apiVersion: v1
kind: Secret
metadata:
  name: payment-key
  namespace: orders
type: Opaque
stringData:
  API_KEY: "plaintext-sensitive-token"
~~~

`Secret.data` dạng Base64 cũng **không phải mã hóa bảo mật**. Thay vào đó, chọn một chiến lược được doanh nghiệp phê duyệt:

- **Azure Key Vault + External Secrets Operator hoặc Secrets Store CSI Driver** khi được triển khai hỗ trợ: quản lý secret trong Key Vault, cấp identity AKS/workload phù hợp, đồng bộ/mount vào Pod theo cơ chế riêng.
- **SOPS với khóa KMS/Key Vault được hỗ trợ**: chỉ commit tệp đã mã hóa, cấp quyền giải mã cho Flux controller đúng scope. Không commit private key giải mã vào cùng repo.
- **Managed identity / Microsoft Entra Workload ID**: khi ứng dụng có thể truy cập Azure data services không dùng password, cấp quyền data-plane tối thiểu và bỏ qua static secret.

Không có lựa chọn nào tự miễn trừ việc kiểm soát quyền đọc Key Vault, rotation, logging, threat modeling và cách ứng dụng reload secret. Nếu dùng External Secrets, Flux có thể quản lý **ExternalSecret CRD**, nhưng operator phải được cài/Ready trước; cần có dependency order.

### 14.5. Phân biệt ba danh tính quan trọng

| Danh tính | Dùng cho | Không tự cung cấp |
|---|---|---|
| **Flux Git source credential** | Đọc repo chứa desired state | Kubelet quyền pull image từ ACR |
| **AKS kubelet/registry identity** | Pull container image vào node | Quyền đọc Azure SQL/Key Vault của ứng dụng |
| **Pod/workload identity** | API runtime truy cập Azure services theo Entra RBAC | Quyền sửa Git hoặc AKS cluster |

Một GitRepository Ready có thể đi kèm Pod `ImagePullBackOff` vì kubelet identity thiếu quyền ACR. Ngược lại, image pull thành công nhưng Pod gọi Key Vault trả 403 có thể là lỗi workload identity hoặc Key Vault data-plane RBAC. Điều tra **đúng danh tính của luồng bị lỗi**.

### 14.6. Network policy và supply chain

- Tránh để controller GitOps và workload có quyền egress tự do nếu tổ chức cần phân tách; allowlist domain/endpoint thực sự cần dùng.
- Với private AKS, kiểm tra DNS/proxy cho Git provider, ACR và Azure management endpoints theo kiến trúc.
- Quét và khóa version của Flux extension/controllers cũng như các CRDs trước khi nâng cấp; không chỉ quét images ứng dụng.
- Dùng signed commits/tags, image provenance/attestation và admission policies khi phù hợp yêu cầu.
- Không trao cho mọi team quyền tạo ClusterRoleBinding hoặc áp dụng CRDs mới chỉ bằng một PR vào repo ứng dụng.

## 15. Quan sát reconciliation: biết được commit nào đã chạy

Một dashboard chỉ hiển thị `kubectl get pods` xanh là chưa đủ. Cần liên kết Git commit, artifact digest, Flux reconciliation status, Kubernetes rollout và chỉ số kinh doanh.

### 15.1. Chuỗi bằng chứng cần lưu

~~~text
Git commit SHA / PR / reviewer
         ↓
GitRepository artifact revision (commit)
         ↓
Flux Kustomization observed revision + Ready condition
         ↓
Kubernetes Deployment image digest / rollout condition
         ↓
Pods Ready + app synthetic tests + SLO metrics
~~~

Một `GitRepository Ready=True` chỉ nghĩa source đã được lấy hợp lệ theo contract. Một `Kustomization Ready=True` cho thấy reconcile/health được báo thành công theo cấu hình của Flux, không nhất thiết bảo đảm thanh toán, báo cáo, dữ liệu hoặc API ngoài đều đúng.

### 15.2. Các lệnh điều tra chỉ đọc

~~~bash
# Kiểm tra Flux objects bằng Kubernetes API.
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A

# Thay namespace/name bằng đối tượng thực tế trong cluster.
kubectl -n flux-system describe gitrepository platform-config
kubectl -n flux-system describe kustomization orders-prod

# Xem trạng thái workload.
kubectl -n orders rollout status deployment/orders-api --timeout=180s
kubectl -n orders get deploy,svc,pods -o wide
kubectl -n orders get events --sort-by=.metadata.creationTimestamp
~~~

Tên `platform-config` là mẫu của phương án Flux upstream trong phần 7; ở configuration được Azure tạo, tên thực tế có thể khác. Hãy liệt kê object trước khi chạy `describe`. Trước khi chạy lệnh, kiểm tra `kubectl config current-context` để không truy vấn nhầm production cluster.

Với Flux CLI:

~~~bash
flux get sources git -A
flux get kustomizations -A
flux get helmreleases -A

# Đọc lỗi theo controller/resource.
flux logs --all-namespaces --level=error
~~~

Ở một số phiên bản CLI/controller, cú pháp hoặc option có khác; kiểm tra `flux --help`. Khi chưa có Flux CLI, vẫn có thể dùng `kubectl`/Azure Portal và controller logs để điều tra.

### 15.3. Phân loại condition và sự kiện

| Condition/sự kiện | Ý nghĩa phổ biến | Nên kiểm tra |
|---|---|---|
| Source `Ready=False` | Không lấy được Git/OCI/Helm artifact | URL, branch, auth, DNS, TLS, rate limit |
| Kustomization `Ready=False` | Build/apply/health lỗi hoặc dependency chưa sẵn sàng | `path`, schema, namespace, RBAC, healthChecks |
| HelmRelease `Ready=False` | Chart fetch, install/upgrade hoặc health lỗi | Chart version, values, hooks, CRDs, helm-controller logs |
| Deployment không Ready | Replica chưa đủ, readiness thất bại hoặc scheduling lỗi | Pod events, probes, resources, node status |
| `ImagePullBackOff` | Không kéo được container image | Registry, tag/digest, kubelet identity, network |
| Pod `CrashLoopBackOff` | App/entrypoint crash liên tục | Container logs, env, dependencies, startup |
| 5xx tăng dù Flux Ready | Lỗi ứng dụng/kinh doanh hoặc dependency | App Insights/traces, synthetic transactions |

### 15.4. Azure Monitor và Log Analytics

Có thể tập hợp:

- Flux controller console logs và Kubernetes events.
- Azure Resource Manager Activity Log cho thay đổi extension/configuration/permissions.
- AKS Container Insights/managed Prometheus theo khả năng/tính năng đã cấu hình.
- Application Insights/OpenTelemetry cho request, error, dependency latency.
- ACR logs để phân tích image push/pull theo các tính năng được bật.
- Git hosting audit log cho PR merge, branch protection và token changes.

**Không mặc định mọi source log tự động đổ vào một bảng Log Analytics**. Cần triển khai diagnostic settings, agent/exporter và telemetry instrumentation phù hợp rồi kiểm tra schema, thời gian lưu và quyền xem dữ liệu. Cảnh báo nên phân biệt lỗi Flux controller, lỗi Kubernetes workload và lỗi nghiệp vụ.

### 15.5. KPI vận hành GitOps

| KPI | Diễn giải |
|---|---|
| **Reconciliation freshness** | Thời gian từ commit được phê duyệt đến observed revision phù hợp |
| **Ready coverage** | Phần trăm Kustomization/HelmRelease quan trọng đang Ready |
| **Drift recovery** | Thời gian sửa lệch có chủ đích/ngoài ý muốn |
| **Deployment lead time** | Từ commit đến workload thực sự khỏe, không chỉ apply thành công |
| **Rollback time** | Thời gian khôi phục chất lượng sau release lỗi |
| **Prune incidents** | Số lần resource bị xóa ngoài dự kiến do cấu hình/lifecycle |
| **Source failures** | Tần suất Git auth/DNS/provider outage ảnh hưởng reconciliation |
| **Policy violations** | PR/manifests bị phát hiện vượt quyền, image không hợp lệ hoặc secret lộ |

KPI phải có **mốc thời gian và mẫu số rõ ràng**. Nếu source-controller không kéo được Git trong 30 phút nhưng Pod đang chạy khỏe, đó là lỗi kiểm soát cấu hình cần xử lý; không nhất thiết là sự cố HTTP hiện tại, nhưng có thể làm giảm khả năng triển khai bản vá khẩn cấp.

## 16. Rollback theo Git và xử lý tình huống khẩn cấp

### 16.1. Rollback bền vững bằng Git revert

Giả sử commit `abc1234` ở config repo đã đổi image từ `1.4.0` sang `1.4.1`; sau khi Flux reconcile, API trả lỗi tăng. Cách khôi phục bền vững là **sửa lại desired state trong Git** theo quy trình:

1. Dừng pipeline promotion để tránh commit mới tiếp tục đẩy bản lỗi.
2. Xác định **commit/PR gây lỗi**, tag/digest đã chạy và phạm vi resource bị ảnh hưởng.
3. Tạo **revert commit** hoặc PR chỉnh image/config về bản ổn định; kiểm tra tác động nếu commit cũ thay nhiều tài nguyên.
4. Review, test và merge theo cơ chế break-glass được phê duyệt (nếu khẩn cấp).
5. Quan sát GitRepository/Kustomization observed revision và Kubernetes Deployment rollout.
6. Thực hiện smoke/synthetic/business tests và đo lỗi/latency để xác nhận phục hồi.
7. Ghi change/incident, nguyên nhân, phạm vi ảnh hưởng và các phòng ngừa tiếp theo.

Ví dụ Bash thực hiện trong **bản sao config repository do người học sở hữu**, không chạy trên repo production khi chưa được phê duyệt:

~~~bash
# Chỉ minh họa: thay SHA bằng commit thực sự cần hoàn tác.
git log --oneline -n 10
git show --stat abc1234

# Tạo commit revert sau khi xác định thay đổi cần đảo.
git revert abc1234

# Kiểm tra diff, tests, mở PR và merge theo quy trình.
git show --stat --oneline HEAD
~~~

Lệnh `git revert` không bắt buộc được chạy thẳng trên branch protected. Trong nhiều tổ chức, tạo branch mới rồi mở PR là cách đúng. Nếu commit `abc1234` chứa cả thay đổi database schema không tương thích, đảo manifest đơn thuần có thể chưa khôi phục ứng dụng.

### 16.2. Vì sao `kubectl rollout undo` chưa phải rollback GitOps?

Một người vận hành có thể dùng:

~~~bash
# Ví dụ break-glass: không chạy trên production khi chưa có phép.
# kubectl -n orders rollout undo deployment/orders-api
~~~

Thao tác này có thể thay đổi trạng thái runtime tạm thời. Nhưng nếu Git vẫn khai báo image mới, **Flux có thể reconcile lại** và đưa Deployment về desired state lỗi. Vì vậy đây không phải phương án rollback bền vững khi Flux vẫn hoạt động.

Nếu buộc phải can thiệp trực tiếp trong sự cố nghiêm trọng, phải:

- Xác nhận Flux Kustomization nào sở hữu Deployment.
- Quyết định **suspend reconciliation** phù hợp trước khi áp dụng sửa chữa thủ công khi được phép, hoặc cập nhật Git ngay lập tức.
- Ghi lại thời gian/owner và mọi thay đổi ngoài Git.
- Đồng bộ trạng thái cuối trở lại Git rồi mới resume reconciliation có kiểm soát.

### 16.3. Suspend/resume có điều kiện

Trong môi trường có Flux CLI và đủ quyền:

~~~bash
# DỪNG reconciliation tạm thời của Kustomization; có thể tạo drift.
flux suspend kustomization orders-prod \
  --namespace flux-system

# Sau khi Git đã chứa cấu hình đúng và change được phê duyệt:
flux resume kustomization orders-prod \
  --namespace flux-system

flux get kustomizations -A
~~~

Không coi `suspend` là nút pause chung của mọi controller/resource. Các Flux source, HelmRelease hoặc Kustomization khác có thể vẫn chạy tùy phạm vi và dependencies. Một lần suspend kéo dài có thể khiến lỗ hổng bảo mật không được vá, desired state không được thực thi và vận hành không còn tự động. Ghi incident, người chịu trách nhiệm, thời điểm resume và kiểm tra mọi thay đổi sau khi bật lại.

### 16.4. Những thứ rollback Git không thể khôi phục tự động

| Thay đổi | Vì sao revert Git chưa đủ? |
|---|---|
| Database migration phá schema | Git manifest không phục hồi cấu trúc/dữ liệu đã bị xóa |
| Message/event schema không tương thích | Consumer cũ không đọc được sự kiện đã phát |
| Secret rotation | Secret cũ có thể đã hết hạn hoặc bị thu hồi |
| Xóa PVC/PV do prune | Dữ liệu có thể mất theo reclaim/backup policy; tạo YAML mới không phục hồi bytes |
| External API side effects | Thanh toán/email đã gửi không tự đảo ngược |
| CRD upgrade | Dữ liệu custom resource có thể bị chuyển đổi hoặc mất tương thích |
| Azure resource drift | Flux không tự hoàn tác các thay đổi Azure ngoài phạm vi nó quản lý |

Vì vậy, một kế hoạch release an toàn cần **expand–migrate–contract**, backup/restore, idempotency, versioned messages và phương án DR theo RPO/RTO, không chỉ một nút revert.

## 17. Troubleshooting GitOps theo từng lớp

Khi một deployment không cập nhật như mong đợi, phải xác định lỗi ở bước **Git fetch → artifact → Kustomize/Helm → Kubernetes API → scheduling/runtime → ứng dụng**. Thay đổi tất cả thông số cùng lúc khiến việc điều tra khó tái hiện và có thể gây thêm drift.

### 17.1. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Bằng chứng/hành động |
|---|---|---|
| `GitRepository Ready=False` | Repo URL/branch sai, SSH key/PAT hết hạn, TLS/proxy/DNS chặn | Describe source, source-controller logs, xác minh credential/network |
| Git commit mới không được quan sát | Interval, Git source stuck, webhook thất bại hoặc branch sai | `GitRepository.status.artifact.revision`, reconcile source đúng tên |
| `Kustomization Ready=False: path not found` | `spec.path` sai hoặc thư mục chưa có `kustomization.yaml`/manifest phù hợp | Xem Git artifact, path và build bằng Kustomize |
| `Kustomization Ready=False: build failed` | Kustomize resources/patches không hợp lệ, file thiếu | Build overlay trong CI/lab và đọc controller condition |
| `Kustomization apply failed: forbidden` | Service account không đủ Kubernetes RBAC | Role/RoleBinding/ClusterRole, namespace và API permission |
| `Health check timeout` | Deployment chưa Ready, probe fail hoặc API server chậm | Describe Deployment/Pods, Pod logs/events, timeout thực tế |
| `HelmRelease failed` | Chart source/values/hook/CRD lỗi | Describe HelmRelease, Helm repository status, helm-controller logs |
| `ImagePullBackOff` | ACR chưa cho kubelet pull, tag không tồn tại, DNS/firewall | Pod events, registry/image digest, kubelet identity |
| `CrashLoopBackOff` | Ứng dụng crash, config/secret sai, OOM | Pod logs/previous, env, resource limits, dependency |
| `Pending` kéo dài | Không đủ node capacity, taint/toleration/affinity/PVC | Pod describe, node/pool, scheduler events |
| `Flux Ready=True` nhưng HTTP 500 | Lỗi business logic hoặc database/API dependency | Application Insights/traces/synthetic test, không chỉ Flux status |
| Resource bị tạo rồi biến mất | Prune, controller khác sở hữu cùng object, admission/policy | Git diff, Flux inventory, events, audit logs |
| `kubectl edit` bị “hoàn tác” | Flux reconciliation áp desired state | Kiểm tra Git và field ownership; tạo PR thay đổi chính thức |
| Revert Git nhưng ứng dụng vẫn lỗi | Kustomization chưa sync hoặc schema/secret/queue không tương thích | Observed revision, rollout, data compatibility |
| Controller pods không chạy | Extension/cluster resource/network hoặc version không tương thích | Flux extension status, controller events, node capacity |

**Đừng xóa namespace `flux-system` hoặc cài lại toàn bộ extension như biện pháp đầu tiên.** Điều này có thể xóa controllers/configurations, làm mất khả năng sửa đổi và gây gián đoạn trên nhiều workload. Đầu tiên cần đọc lỗi chính xác và xác định phạm vi.

### 17.2. Runbook từng bước

**Bước 1 — Xác nhận đúng đích:** Azure subscription, AKS cluster, context kubectl, tên Flux configuration, namespace, Kustomization/HelmRelease.

~~~bash
az account show --query "{id:id,name:name}" -o table
kubectl config current-context
kubectl cluster-info
kubectl get nodes
~~~

**Bước 2 — Azure integration:** kiểm tra extension/configuration qua `az k8s-extension show` và `az k8s-configuration flux show` nếu dùng tích hợp Azure. Nếu extension lỗi, phân biệt lỗi provision với lỗi source Git.

**Bước 3 — Flux sources:**

~~~bash
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
flux get sources git -A
~~~

Xem `status.conditions`, artifact revision và error message. Nếu Git source không Ready, chưa cần đi vào Deployment để đoán lỗi.

**Bước 4 — Kustomizations/Helm:**

~~~bash
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
flux get kustomizations -A
flux get helmreleases -A
~~~

Xác nhận `sourceRef`, `path`, `prune`, dependencies, serviceAccount và observed revision. Nếu manifest bị từ chối, kiểm tra lỗi API/admission và quyền ở cluster.

**Bước 5 — Kubernetes workloads:**

~~~bash
kubectl -n orders get deploy,svc,pods
kubectl -n orders describe deployment orders-api
kubectl -n orders get events --sort-by=.metadata.creationTimestamp
kubectl -n orders rollout status deployment/orders-api --timeout=180s
~~~

Nếu Pod không Ready, xem container log, readiness/liveness probe, registry pull, resource quota, node/pool và network. Kustomization có thể chờ health nếu đã khai báo checks; nếu không có checks tương ứng, trạng thái Ready của Flux có thể được thiết lập trước khi app thật sự ổn.

**Bước 6 — Ứng dụng:** gọi synthetic endpoint, kiểm tra HTTP status, p95/p99, SQL/Storage/Key Vault, ingress, API bên ngoài và giao dịch nghiệp vụ.

**Bước 7 — Khắc phục bền vững:** sửa Git PR/IaC config đúng nguồn sở hữu; hạn chế thao tác live `kubectl` trừ break-glass. Quan sát cùng commit/hash được controller apply và đóng incident khi SLO hồi phục.

### 17.3. Phân biệt Git status và Kubernetes condition

Một commit đã merge thành công chỉ khẳng định Git lưu desired state. Một Kustomization đã ghi `lastAppliedRevision` đúng commit chỉ cho thấy controller đã áp dụng phiên bản theo logic của nó; lỗi Pod sau khi scheduling, lỗi dependency ở tầng ứng dụng hoặc thao tác side effects còn cần kiểm chứng riêng.

Không sử dụng một cột `Ready=True` làm căn cứ tự động promote vào production nếu thiếu smoke/business tests. Flux là cơ chế đồng bộ cấu hình, **không phải hệ thống kiểm thử nghiệp vụ toàn diện**.

## 18. GitOps và rollout có kiểm soát trên AKS

Một Deployment khai báo `strategy: RollingUpdate` và có readiness probe có thể giúp thay Pod dần dần. Nhưng Flux **không tự hiểu “canary 5%, 25%, 50%”** chỉ vì đang reconcile Deployment. Nếu cần weighted canary/blue-green ở tầng request, phải thiết kế thêm controller/ingress hoặc service mesh hỗ trợ, cùng monitoring và rollback policy.

### 18.1. Ba cấp triển khai

| Cấp độ | Cách thực hiện | Ưu tiên |
|---|---|---|
| **Rolling update** | Kubernetes Deployment rolling strategy, readiness, PodDisruptionBudget nếu phù hợp | Mặc định tốt cho nhiều web API stateless |
| **Canary/blue-green có phân bổ traffic** | Hai versions + controller/ingress hỗ trợ weighted routing, ví dụ Flagger tích hợp stack tương thích | Khi cần tăng traffic theo SLO và rủi ro |
| **Feature flag theo người dùng** | Cấu hình application/feature management, phân đoạn cohort | Khi rollout một chức năng mà không cần thay infrastructure traffic |

Sự hiện diện của Flux **không đồng nghĩa** đã có Flagger, Argo Rollouts hoặc service mesh. Nếu dùng một công cụ rollout bổ sung, Flux có thể khai báo CRDs/config của công cụ đó trong Git, còn rollout controller chịu trách nhiệm thay traffic. Cần kiểm tra tương thích với ingress/gateway đã chọn và nguồn metrics.

### 18.2. Rollout theo môi trường và readiness

Một quy trình đáng tin:

1. CI build artifact mới, quét bảo mật và thực hiện unit/integration tests.
2. PR đưa artifact vào dev overlay, Flux dev reconcile.
3. Chạy smoke/contract tests, đối chiếu database schema và kiểm thử dependency.
4. PR promote cùng artifact sang staging, đo hiệu năng/synthetic traffic.
5. PR production theo approval, Flux prod reconcile.
6. Nếu dùng canary controller, controller kiểm tra metrics để tăng/giảm traffic theo policy; nếu không, Deployment rolling update với rollback Git khi SLO lỗi.
7. Theo dõi application logs, request error rate, latency, replica/Pod restarts, chi phí và incidents.

**Traffic draining:** Pod readiness chuyển về false không tự đảm bảo mọi kết nối TCP/gRPC đang chạy đã kết thúc. Thiết kế `terminationGracePeriodSeconds`, `preStop`, keep-alive và logic graceful shutdown theo workload thực tế.

### 18.3. Stateful workloads cần runbook riêng

Với StatefulSet, database hoặc message broker, rolling update không đủ để bảo đảm integrity. Cần:

- Backup và restore đã được thử nghiệm.
- Kiểm tra quorum/leader election, replica lag và storage class/PVC retention.
- Phân tích version compatibility giữa các Pods và dữ liệu.
- Quy tắc schema/event versioning khi các phiên bản cùng hoạt động.
- Lệnh failover/rollback theo tài liệu sản phẩm, không chỉ revert Git.

Không dùng `prune: true` mà không xem xét lifecycle của StatefulSet/PVC và reclaim policy. Kubernetes object được tạo lại **không đồng nghĩa dữ liệu trên volume được phục hồi**.

## 19. GitOps cho nhiều cluster, nhiều subscription và khôi phục

Trong doanh nghiệp, AKS thường được chia theo môi trường, khu vực, mức độ nhạy cảm hoặc ownership của team. GitOps giúp duy trì chuẩn chung nhưng không nên tạo một identity/branch có thể thay mọi cluster production mà không có kiểm soát.

### 19.1. Mô hình quản trị nhiều cluster

~~~mermaid
flowchart TB
    POLICY[Platform governance / Git CODEOWNERS]
    POLICY --> REPO[(GitOps config repo)]
    REPO --> DEV[Flux: AKS-dev]
    REPO --> STAGE[Flux: AKS-staging]
    REPO --> PROD1[Flux: AKS-prod-region-A]
    REPO --> PROD2[Flux: AKS-prod-region-B]
    DEV --> W1[Dev workloads]
    STAGE --> W2[Staging workloads]
    PROD1 --> W3[Prod workloads A]
    PROD2 --> W4[Prod workloads B]
    MON[Azure Monitor / SLO dashboards] -. Observe .-> PROD1
    MON -. Observe .-> PROD2
~~~

Các cluster có thể nằm ở các **subscription/resource group khác nhau**, nhưng dùng cùng base manifests, overlay và policy. Mỗi cluster chọn **đúng path/ref** của mình; không nên trỏ mọi production cluster vào một nhánh/path thay đổi tự do mà thiếu gate. Tách **cluster identity** và resource permissions theo phạm vi; tránh dùng chung một tài khoản admin để bootstrap mọi thứ rồi không rotate.

### 19.2. Bootstrap từ trạng thái trống

Giả sử AKS cluster production phải được tạo lại sau sự cố. Để GitOps có thể khôi phục workload, cần:

1. IaC có khả năng tái tạo AKS/VNet/subnet/identities/ACR connectivity và monitoring.
2. Repo Git còn truy cập được, credential bootstrap có phương án khôi phục an toàn.
3. Flux extension/controllers được cài phiên bản tương thích.
4. Kustomizations được dựng **đúng thứ tự**: namespaces/RBAC/CRDs/operators → workloads.
5. Image digests trong ACR hoặc registry còn tồn tại và có pull permissions.
6. External secrets/dữ liệu/database/volumes được phục hồi qua kế hoạch DR riêng.
7. Smoke/contract tests xác nhận hệ thống sau dựng lại phục vụ được.

GitOps giúp **tái tạo Kubernetes objects**, nhưng **không tự khôi phục database, blob, persistent volumes hoặc trạng thái ngoài cluster**. Backup/restore và DR phải có runbook riêng, cùng RPO/RTO và quyết định failover.

### 19.3. Tính sẵn sàng khi Git provider bị lỗi

Khi Git provider không truy cập được, workload đang chạy có thể vẫn phục vụ nếu cluster và dependencies khỏe. Nhưng bạn có thể **không triển khai được thay đổi/rollback qua GitOps** cho đến khi nguồn phục hồi. Có thể thiết kế:

- Repository mirror/backup và runbook chuyển nguồn được phê duyệt.
- Local artifact/cache của controller theo khả năng dịch vụ, không coi cache là bản backup bảo đảm.
- Pipeline break-glass có quyền giới hạn, được audit và có thể đồng bộ ngược về Git.
- Snapshot/config backup và registry artifact retention cho image quan trọng.

Đừng để một GitHub/ADO PAT duy nhất không có kế hoạch rotate là điểm hỏng chung của tất cả production clusters.

## 20. Chi phí, hiệu năng và giới hạn vận hành GitOps

GitOps giúp giảm thao tác thủ công, nhưng **không có nghĩa không phát sinh chi phí**. Azure tính phí cho những tài nguyên theo mô hình giá hiện hành, gồm AKS/nodes, registry, mạng, lưu trữ và quan sát. Một số khả năng extension/GitOps cũng có thể có điều kiện tính phí hoặc quyền sử dụng khác nhau theo loại cluster/gói Azure; cần kiểm tra pricing/entitlement của môi trường thực tế, đặc biệt khi quản lý **Azure Arc-enabled Kubernetes** thay vì AKS.

### 20.1. Những nguồn chi phí cần xem xét

| Nguồn | Tác động | Cách kiểm soát |
|---|---|---|
| **AKS nodes/compute** | Node pool phục vụ ứng dụng và Flux controllers, số máy dự phòng | Requests/limits, node sizing, autoscaler, workload placement |
| **Azure Container Registry** | Dung lượng image, tier, network/transactions | Image retention theo chính sách, giữ artifact phục vụ rollback |
| **Networking** | NAT Gateway, Azure Firewall, Private Endpoint, lưu lượng outbound hoặc liên vùng | Route đúng, tối ưu image pull và egress |
| **Monitoring** | Log Analytics/Container Insights/Prometheus/alerts | Sampling, retention, lọc dữ liệu không cần thiết |
| **Storage** | PVC/PV, snapshots, backup và data replication | Backup lifecycle và phân loại dữ liệu |
| **CI/CD** | Build runners, scan tools, artifact signing, Git hosting | Tối ưu pipeline và caching có kiểm soát |
| **Kubernetes operations** | Tải API server, Flux reconcile quá dày, số lượng CRDs | Điều chỉnh interval, chia Kustomization và controller resources |

Giá từng thành phần có thể thay đổi theo vùng, SKU, thời điểm và điều khoản của subscription. Hãy xem **Azure Cost Management**, tagging `owner`/`application`/`environment`/`costCenter`, ngân sách và xu hướng thực tế. **Budget alert không tự ngăn chi phí phát sinh**.

### 20.2. Tối ưu reconciliation

Thay vì tạo một Kustomization khổng lồ quản mọi namespace và hàng nghìn resources:

- Tách theo team/app hoặc lớp platform với boundaries rõ.
- Dùng `dependsOn` cho những phụ thuộc cần thứ tự, tránh mọi app bị chặn bởi một resource không liên quan.
- Chọn interval hợp lý theo tần suất thay đổi, độ nhạy vận hành và giới hạn Git/API.
- Định nghĩa health checks có ích, không gọi endpoint chẩn đoán nặng ở tốc độ quá dày.
- Theo dõi controller CPU/memory, queue, error rate và khả năng Git provider.
- Giữ manifest/config dễ đọc và có tests để giảm số lần build/apply thất bại.

Không nên đặt `interval: 10s` cho mọi repository chỉ vì muốn giảm deployment lead time vài chục giây. Có thể dùng webhook/notification và cơ chế reconcile theo nhu cầu khi cần, song vẫn phải đánh giá tải và bảo mật.

### 20.3. Nâng cấp Flux extension và CRDs

Flux controllers là phần mềm vận hành, có phiên bản và phụ thuộc compatibility. Khi nâng version:

1. Kiểm tra AKS/Kubernetes version, GitOps extension version và CRD API versions đang sử dụng.
2. Đọc breaking changes và kế hoạch deprecation/migration của các custom resources.
3. Dựng môi trường thử nghiệm có cấu hình GitOps tương tự, chạy reconcile/HelmRelease tests.
4. Sao lưu manifests/config, ghi thông tin extension và controller versions trước thay đổi.
5. Nâng cấp theo change window, theo dõi controller health, reconciliation failures và app SLO.
6. Có kế hoạch quay về phiên bản tương thích, nhưng không mặc định hạ cấp controller/CRD luôn an toàn.

Đừng nhầm **nâng cấp AKS control plane/node pools** với **Flux reconcile workload manifests**. AKS upgrade, node image upgrade, K8s API deprecations và GitOps extension upgrades là các thay đổi có quan hệ nhưng cần lịch và kiểm chứng riêng. Nếu YAML dùng K8s API version đã bị loại, Flux có thể bắt đầu lỗi sau khi upgrade cluster ngay cả khi Git không đổi.

## 21. Tình huống thực tế: vận hành nền tảng đơn hàng AKS

**Bối cảnh:** Doanh nghiệp có hai subscription (`app-dev` và `app-production`), hai cụm AKS theo môi trường và một ACR private. Hệ thống đơn hàng gồm web API, worker nhận Azure Service Bus messages, Azure SQL qua Private Endpoint và Azure Key Vault. Nhóm vận hành muốn chuyển từ deploy bằng laptop sang GitOps, với yêu cầu production:

- Mọi thay đổi có PR, reviewer và record của image digest.
- Không cất database password hay token trong Git.
- Khi deploy bản lỗi, có thể quay về image đã kiểm chứng mà không ghi đè dữ liệu.
- Không để một team được xóa resource của team khác.
- Có trạng thái drift/reconcile và alert với owner rõ ràng.
- Vẫn có kế hoạch DR nếu Git provider hoặc một Azure region không sẵn sàng.

### 21.1. Bản thiết kế tham chiếu

~~~mermaid
flowchart LR
    DEV[Source PR] --> CI[CI build + test + scan]
    CI --> ACR[Private ACR: image digest]
    CI --> PR[Config PR - overlay]
    PR --> REVIEW[CODEOWNERS + policy checks]
    REVIEW -->|Merge| REPO[(Protected Git config repo)]
    REPO --> FLUXDEV[Flux controllers AKS dev]
    REPO --> FLUXPROD[Flux controllers AKS prod]
    FLUXDEV --> DEVAPP[Dev namespaces]
    FLUXPROD --> PRODAPP[Prod namespaces]
    PRODAPP --> SQL[Azure SQL private endpoint]
    PRODAPP --> BUS[Azure Service Bus]
    PRODAPP --> KV[Azure Key Vault]
    ACR -. Kubelet image pull .-> PRODAPP
    MON[Azure Monitor + App Insights] -. Observe .-> PRODAPP
~~~

### 21.2. Phân chia trách nhiệm

| Vai trò | Trách nhiệm | Quyền hạn mục tiêu |
|---|---|---|
| **Platform team** | AKS/IaC, Flux extension, CRDs, RBAC, namespaces, monitoring | Quản lý nền tảng; audit và change approval |
| **Application team** | Code, Dockerfile, app manifests, tests và đề xuất image | Commit/PR repo ứng dụng; không có cluster-admin prod |
| **Security team** | Policy, scan, secrets, RBAC review và CVE SLO | Phê duyệt quy tắc/ngoại lệ theo quy trình |
| **Release owner** | Kiểm tra PR config, approve promotion/rollback | Quyền merge có bảo vệ, theo dõi SLO |
| **On-call/SRE** | Theo dõi health, incident, break-glass khi cần | Quyền khẩn cấp có thời hạn và audit |

### 21.3. Đợt phát hành phiên bản 1.4.2

1. Developer thay code API, CI build image `orders-api:1.4.2`, scan và ghi digest `D2`.
2. Team mở PR đổi `apps/orders-api/overlays/dev` sang digest `D2`.
3. Flux trên dev reconcile; smoke tests, contract tests và integration với SQL/Service Bus chạy thành công.
4. Release owner mở PR đổi overlay production sang đúng `D2`, không rebuild một image production khác không có kiểm chứng.
5. Review xác nhận không có plaintext secret, scope đúng namespace, `prune` không vô tình xóa Service/PVC, schema vẫn tương thích.
6. Merge PR; Flux prod fetch commit, Kustomization apply, Kubernetes Deployment rolling update.
7. SRE theo dõi observed revision, Pod readiness, HTTP 5xx, p95 latency, SQL/Service Bus dependency failures và business metrics.
8. Nếu lỗi vượt SLO, tạo revert PR có phê duyệt, đưa image về digest `D1`; kiểm tra dữ liệu, queue và tác vụ đang xử lý.
9. Ghi release/incident evidence, bổ sung test, cập nhật baseline cho vòng tiếp theo.

### 21.4. Khi `prune` xóa Service sai

Giả sử PR vô tình xóa Service khỏi resources base và Flux prune nó. Một số Pod vẫn Running nhưng người dùng không gọi được API vì Service không còn. Khắc phục theo runbook:

1. Dừng promotion và xác định commit gây mất resource.
2. Xem Kustomization inventory/conditions, Git diff và Kubernetes events; kiểm tra xem có những resource khác bị prune không.
3. Revert manifest Service về desired state qua PR khẩn cấp/được phê duyệt.
4. Quan sát Flux tạo lại Service và endpoints; kiểm tra ingress, HTTP health và giao dịch.
5. Đánh giá tác động dữ liệu, network, thời gian gián đoạn và policy phòng ngừa; xem xét test cho resource deletion diff.

Nếu resource bị prune là PVC hoặc tài nguyên stateful, việc khôi phục YAML **không chứng minh dữ liệu còn nguyên**. Phải thực hiện backup/restore theo chiến lược storage.

### 21.5. Khi Azure SQL migration phá phiên bản cũ

Phiên bản mới tạo cột/đổi dữ liệu theo cách bản cũ không đọc được. Revert image về `D1` có thể khiến API tiếp tục lỗi. Giải pháp phòng ngừa:

- **Expand:** thêm schema mới tương thích với code cũ.
- **Migrate:** backfill dữ liệu theo job được điều phối, có checkpoint và kiểm tra.
- **Dual-read/write hoặc adapter:** trong thời gian nhiều phiên bản tồn tại, theo chính sách ứng dụng.
- **Contract:** chỉ bỏ schema cũ sau khi hết cửa sổ rollback và có kế hoạch DR.

Không tự chạy migration phá hủy trong init container của mọi Pod: Pod mới có thể chạy migration nhiều lần khi Kubernetes reschedule và Flux reconcile.

## 22. Bài thực hành: xây GitOps cho một API trên AKS

**Đề bài:** Bạn có cụm AKS lab, ACR private và repo Git thuộc quyền quản lý. Ứng dụng `inventory-api` chạy ở namespace `inventory`, có endpoint `/health/ready`; phiên bản ổn định là `1.0.0`, bản mới `1.1.0`. Cần triển khai bằng Flux và bảo đảm có thể rollback sau khi thấy lỗi business.

Hãy hoàn thành:

1. **Sơ đồ:** vẽ luồng CI build → ACR → Git PR → Flux controllers → Kubernetes API → Deployment/Pods.
2. **Phân biệt:** GitOps GitRepository, Flux Kustomization, file `kustomization.yaml`, HelmRelease, Deployment và replica có vai trò gì?
3. **Repository:** tạo cấu trúc base/overlay dev/prod có namespace, Deployment, Service, image tag/digest và resource requests/limits.
4. **Bảo mật source:** mô tả cách Flux đọc private Git mà không commit PAT/SSH private key vào repo.
5. **Azure:** liệt kê điều kiện cần trước khi tạo extension/configuration cho AKS và các Azure RBAC permissions liên quan.
6. **CLI:** viết lệnh tạo/kiểm tra Flux extension, tạo configuration trỏ đúng overlay test và đọc trạng thái nguồn/Kustomization.
7. **Kubernetes:** chứng minh Pod dùng image đúng, Service đúng port, readiness probe đạt và client gọi được API.
8. **Promotion:** mô tả quy trình đưa đúng image digest từ dev lên production qua PR/approval.
9. **Drift:** dùng ví dụ thay replica thủ công rồi giải thích Flux/HPA/field ownership ảnh hưởng cách sửa lệch thế nào.
10. **Prune:** minh họa một manifest bị xóa từ overlay; giải thích lúc nào `prune=true` gây nguy cơ và cần thiết kế bảo vệ gì.
11. **Helm:** nếu muốn cài ingress controller từ chart, chọn HelmRelease và nguồn Helm chart, liệt kê điều kiện CRD/permission.
12. **Secret:** thiết kế dùng Key Vault + Workload Identity hoặc SOPS an toàn; không dùng Secret plaintext/Base64 như mã hóa.
13. **Image pull:** khi GitRepository Ready nhưng Pod `ImagePullBackOff`, cho biết identity/đường mạng nào cần kiểm tra.
14. **Observability:** nêu tối thiểu sáu metric/log cần có; liên kết Git SHA tới image digest và health ứng dụng.
15. **Rollback:** giải thích tại sao `kubectl rollout undo` không đủ; viết thứ tự Git revert và xác minh sau đó.
16. **DR:** mô tả cách phục hồi workload khi Git provider không truy cập và khi AKS cluster phải tạo lại.
17. **Chi phí:** dự toán compute AKS/Flux, ACR, network, Log Analytics, backup và cách đặt budget.
18. **Bằng chứng:** lưu commit, PR reviewer, observed revision, Deployment image, kết quả synthetic test và incident/runbook.

### Mẫu lệnh kiểm tra sau khi merge

~~~bash
# Chỉ chạy tại cluster lab có kubeconfig context đúng.
kubectl config current-context
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl -n inventory get deploy,pods,svc

# Theo dõi Deployment thật thay vì chỉ coi Git commit là thành công.
kubectl -n inventory rollout status \
  deployment/inventory-api --timeout=180s
~~~

### Khung trả lời kiểm chứng

| Đối tượng | Bằng chứng cần có |
|---|---|
| Git repository | Branch/commit và PR đã được review |
| Flux source | GitRepository Ready, artifact revision trùng commit mong muốn |
| Flux Kustomization | Ready, correct sourceRef/path, prune/health policy rõ |
| Kubernetes Deployment | Image digest, replicas/rollout conditions và đúng namespace |
| Pods | Running/Ready, không có image pull/crash/restart bất thường |
| Application | Health endpoint và giao dịch API thực sự thành công |
| Security | Quyền Git/ACR/Kubernetes/Key Vault tách rõ, không secret lộ |
| Rollback | Commit revert đã apply, image cũ hoạt động và dữ liệu tương thích |
| FinOps | Có owner, tags, budget và log retention hợp lý |

Bài thực hành đạt yêu cầu khi người học chứng minh được **commit nào đã được Flux quan sát, object nào đã được áp dụng, app có khỏe thật không và cách khôi phục khi release lỗi**. Không chỉ chụp ảnh “Flux extension provisioning succeeded”.

## 23. Checklist vận hành GitOps production

### 23.1. Trước khi cài Flux hoặc cấu hình một cluster mới

- [ ] Xác nhận subscription, resource group, AKS cluster, region và kubeconfig context.
- [ ] Xác định một phương án cài/quản lý Flux chính, tránh hai hệ thống cùng sở hữu CRDs/extension.
- [ ] Xác minh AKS/Kubernetes version và Flux extension/controller/CRD compatibility.
- [ ] Thiết kế repository layout theo cluster/environment/team và quy định ai sở hữu path nào.
- [ ] Bật Git branch protection, PR review, CODEOWNERS và kiểm tra IaC/Kubernetes manifests.
- [ ] Xác định network/DNS đến Git repository, ACR, Azure services và private endpoints.
- [ ] Thiết kế Git source credentials read-only, rotation và lưu trữ secret an toàn.
- [ ] Cấp Azure RBAC và Kubernetes RBAC đúng scope; xem xét service account cho Flux Kustomization.
- [ ] Quy định prune/deletion policy, tài nguyên stateful cần bảo vệ và quy trình chuyển owner.
- [ ] Chuẩn bị giám sát Flux, AKS, app telemetry và alert owner.
- [ ] Có backup/DR plan độc lập với Git repository, bao gồm dữ liệu và image registry.

### 23.2. Trước khi merge một PR production

- [ ] Đã kiểm tra Git diff, YAML schema và `kustomize build`/Helm chart values.
- [ ] Đã kiểm tra Kubernetes API versions tương thích với AKS version.
- [ ] Image đến từ registry tin cậy, đã scan, gắn tag/digest có thể tái hiện.
- [ ] Không có plaintext Secret, PAT, private key hoặc credential bị commit.
- [ ] PR không thêm quyền RBAC/public ingress/quy tắc network vượt phạm vi.
- [ ] Không xóa/đổi tên tài nguyên ngoài dự kiến khi `prune=true`.
- [ ] Database migration, message schema và image rollback tương thích.
- [ ] Có đủ Pod capacity, readiness/startup/liveness hợp lý và rollout strategy.
- [ ] Có change approval/owner và test thành công ở môi trường thấp.
- [ ] Có rollback commit/image và đường khôi phục khi repository/registry không truy cập.

### 23.3. Sau khi merge

- [ ] Xác minh GitRepository đã quan sát đúng commit.
- [ ] Xác minh Kustomization/HelmRelease đã reconcile đúng source/path/values.
- [ ] Kiểm tra Kubernetes resource inventory và không có prune/delete bất thường.
- [ ] Deployment rollout thành công, Pods Ready, không Pending/CrashLoop/ImagePullBackOff.
- [ ] Test HTTP/API, database, queue, secret, identity và kết nối mạng đúng.
- [ ] Theo dõi p95/p99 latency, error rate và resource metrics sau release.
- [ ] Nếu gặp lỗi, tạm dừng promotion, thực hiện rollback theo Git và đánh giá dữ liệu.
- [ ] Lưu commit SHA, PR, image digest, observed revision, kết quả test và incident trong hệ thống quản trị.

## 24. Các hiểu lầm phổ biến và cách sửa

| Hiểu lầm | Sự thật cần nhớ |
|---|---|
| “Có Git repository là đã GitOps.” | Cần controller reconciliation, quyền, kiểm soát review và observability |
| “Flux thay thế CI.” | Flux chủ yếu reconcile desired state; build/test/scan image vẫn là trách nhiệm CI |
| “Cài Flux extension thành công nghĩa là ứng dụng khỏe.” | Extension/config/source/Deployment/app là các lớp kiểm chứng độc lập |
| “GitRepository Ready thì image pull chắc chắn được.” | Git auth khác ACR kubelet identity và Pod runtime pull |
| “Kustomization.yaml là cùng một thứ với Flux Kustomization.” | File Kustomize build manifests; Flux CRD chỉ định source/path/prune/health |
| “Kubernetes replicas luôn về đúng Git, kể cả có HPA.” | HPA và Flux có thể quản lý trường khác nhau; thiết kế field ownership |
| “Prune chỉ làm sạch file không dùng.” | Có thể xóa Service/CRD/PVC hoặc resource quan trọng theo phạm vi owner |
| “Git revert khôi phục toàn bộ hệ thống.” | Không tự hoàn tác database schema, dữ liệu bị xóa, queue hay side effects |
| “kubectl rollout undo là rollback bền vững.” | Flux có thể reconcile lại image lỗi nếu Git vẫn khai báo nó |
| “GitOps tự làm canary 5% traffic.” | Cần thêm rollout controller/ingress với weighted routing; Flux tự nó không chia traffic HTTP |
| “Kubernetes Secret Base64 là an toàn để commit.” | Base64 là encoding, cần SOPS/Key Vault/secret management thích hợp |
| “Mọi Azure resource do Flux tự tạo.” | VNet, AKS, ACR và data services thường được IaC khác quản lý |
| “Một cluster-admin service account cho mọi team là đơn giản nhất.” | Tăng phạm vi ảnh hưởng của một repo/credential bị xâm phạm |
| “Có ba replicas thì an toàn sau mọi lần deploy.” | Phụ thuộc zone, readiness, capacity, DB và rollout behavior |
| “Source controller offline sẽ ngay lập tức làm app ngừng chạy.” | Workload hiện hữu có thể vẫn chạy; vấn đề là thiếu khả năng sync/change |

## 25. Dọn dẹp lab và bảo vệ quyền sở hữu tài nguyên

Sau khi học, nếu đã tự tạo Flux configuration/extension trên một cluster thử nghiệm, phải kiểm tra **ai sở hữu** từng tài nguyên trước khi xóa. Không được xóa một Flux extension dùng chung để dọn một ứng dụng, vì điều đó có thể ngừng reconciliation của nhiều team.

### 25.1. Kiểm kê trước khi thao tác

~~~bash
az account show --query "{id:id,name:name}" -o table

az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{id:id,provisioningState:provisioningState}" \
  -o json

az k8s-configuration flux show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  -o json

kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl get namespaces
~~~

Chỉ **đọc** các tài nguyên hiện có trong bước này. Nếu cluster có nhiều Flux configurations, cần xem tất cả ownership và controller tương ứng trước khi cân nhắc xóa extension.

### 25.2. Những quyết định dọn dẹp

1. **Không xóa config production** chỉ vì kết thúc lab: phân biệt resource lab và platform shared.
2. Xác minh trạng thái `prune` và resource inventory trước khi xóa hoặc đổi ownership của Flux Kustomization.
3. Nếu có Kubernetes resource stateful, kiểm tra PersistentVolume/PVC, reclaim policy, backup và ảnh hưởng khi xóa manifest.
4. Với ACR, giữ image digests phục vụ rollback/DR; chỉ dọn theo policy và owner được phê duyệt.
5. Khi không còn ứng dụng cần Flux trên cluster lab, mới cân nhắc dọn configuration/extension đúng thứ tự được dịch vụ hỗ trợ và theo SOP.
6. Nếu resource group hoàn toàn do lab sở hữu, vẫn cần kiểm kê tất cả VM/AKS/ACR/Storage/logs trước khi xóa; không xóa group chứa tài nguyên dùng chung.
7. Kiểm tra tài nguyên còn phát sinh phí: AKS nodes, load balancers/public IP, NAT/Firewall, ACR, backup và Log Analytics.

**Không có lệnh xóa hàng loạt trong ví dụ này**, vì tác động có thể vượt phạm vi một bài thực hành. Nếu muốn thử cleanup, thực hiện trên cluster/resource group disposable đã được xác nhận bằng tài liệu vận hành, không phải từ một command copy-paste.

## 26. Ghi nhớ

**GitOps cho AKS với Flux** là mô hình đưa **trạng thái mong muốn của Kubernetes vào Git và liên tục reconcile trạng thái thực tế bằng controller**. Từ đó, đội vận hành có lịch sử thay đổi rõ ràng, cơ chế sửa drift, khả năng tách quyền deployment khỏi CI và quy trình rollback có thể kiểm toán.

Các điểm cốt lõi:

1. **CI tạo artifact, Flux triển khai desired state:** image được build/scan và lưu ở ACR; Git khai báo image/version/config; Flux reconcile qua Kubernetes API.
2. **Flux có nhiều controller:** source-controller lấy nguồn, kustomize-controller và helm-controller triển khai; image automation là phần mở rộng cần được cấp quyền riêng.
3. **Phân biệt Kustomization:** CRD Flux quản source/path/prune/health; file Kustomize `kustomization.yaml` ghép base/overlay Kubernetes manifests.
4. **Kiểm chứng theo nhiều lớp:** Azure Flux configuration/extension, Git source, Kustomization/HelmRelease, Pods và **health ứng dụng thực tế**.
5. **Bảo vệ Git và quyền:** branch protection, review, Azure RBAC, Kubernetes RBAC, credentials tối thiểu, Key Vault/SOPS/Workload Identity và artifact provenance.
6. **Chú ý prune và drift:** resource bị xóa khỏi Git có thể bị prune; sửa trực tiếp Kubernetes có thể bị Flux ghi đè, nên thay desired state qua Git.
7. **Rollback bền vững bằng Git revert/PR:** không chỉ `kubectl rollout undo`; giữ image digest cũ, schema tương thích và kế hoạch dữ liệu/DR.
8. **GitOps không tự thực hiện tất cả:** AKS upgrades, build CI, canary traffic splitting, database restore, CVE remediation và giám sát nghiệp vụ cần các quy trình/công cụ bổ trợ.
9. **Vận hành và FinOps:** chọn reconciliation interval hợp lý, chia ownership, theo dõi source failures/reconciliation lag, chi phí compute, registry, logs và networking.

Một hệ thống GitOps tốt không chỉ có trạng thái `Ready=True`. Nó phải trả lời được **commit nào được phê duyệt, Flux đã áp dụng gì, workload có thực sự khỏe không, ai chịu trách nhiệm khi lệch trạng thái và có thể phục hồi như thế nào khi xảy ra lỗi**.
