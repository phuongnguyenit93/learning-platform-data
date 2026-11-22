# Config Sync và Policy Controller

> **Chương:** GKE nâng cao và vận hành  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Khi một doanh nghiệp chạy nhiều cụm **Google Kubernetes Engine (GKE)**, việc dùng `kubectl apply` thủ công dễ tạo ra khác biệt giữa các cụm: namespace thiếu nhãn sở hữu, quyền RBAC bị chỉnh ngoài quy trình, hoặc ứng dụng được triển khai trái chính sách bảo mật. Hai công cụ tích hợp với GKE giải quyết **hai vấn đề bổ sung nhau**:

- **Config Sync** đồng bộ cấu hình Kubernetes từ **source of truth** (Git, OCI artifact hoặc Helm chart), phát hiện và hòa giải cấu hình bị lệch (*configuration drift*).
- **Policy Controller** kiểm tra tài nguyên Kubernetes bằng **constraints**: ghi nhận vi phạm hoặc từ chối thao tác khi chính sách bắt buộc không được đáp ứng.

Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, bao quát project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và giám sát độ tin cậy/chi phí. Trong chương **GKE nâng cao và vận hành**, ta thiết kế một quy trình GitOps cho namespace `orders-lab`, rồi dùng Policy Controller yêu cầu namespace có nhãn `owner`. Trọng tâm là **phân biệt vai trò, triển khai an toàn và kiểm chứng thực tế**, không chỉ bật hai tính năng.

**Sau bài học, bạn có thể:**

1. Giải thích luồng Git → Config Sync → Kubernetes API và Policy Controller audit/admission.
2. Phân biệt `RootSync`, `RepoSync`, ConstraintTemplate, Constraint và policy bundles.
3. Thiết kế GitOps source of truth, phân quyền platform/application teams và tránh tranh chấp ownership.
4. Cấu hình Config Sync bằng fleet/Console và một `RootSync` dùng Git.
5. Tạo constraint `K8sRequiredLabels`, thử ở chế độ `dryrun` rồi mới cân nhắc `deny`.
6. Giám sát trạng thái đồng bộ, lỗi `KNV...`, violations, admission failures và drift.
7. Xây runbook rollback, kiểm thử và đánh giá ảnh hưởng đến SLO, bảo mật, chi phí.

## 1. Bài toán: cấu hình đúng và chính sách đúng không giống nhau

Giả sử ba cụm GKE thuộc cùng doanh nghiệp:

| Cụm | Mục đích | Rủi ro nếu quản lý thủ công |
| --- | --- | --- |
| `gke-dev` | Phát triển | Namespace và RBAC được tạo tùy tiện |
| `gke-staging` | Thử nghiệm | Không khớp cấu hình production |
| `gke-prod` | Khách hàng thật | Người vận hành sửa trực tiếp, khó truy vết |

Mục tiêu: mọi namespace ứng dụng đều có nhãn `owner` để xác định người chịu trách nhiệm; cấu hình `Namespace`, `ResourceQuota`, `NetworkPolicy` và `RoleBinding` được duyệt trong Git rồi triển khai nhất quán.

~~~mermaid
flowchart LR
  DEV["Pull request + code review"] --> GIT["Git / OCI / Helm\nNguồn cấu hình được duyệt"]
  GIT --> SYNC["Config Sync\nFetch · Render · Reconcile"]
  SYNC --> API["Kubernetes API\nCụm GKE"]
  POL["Policy Controller\nConstraints + Audit"] -. "Admission kiểm tra tạo/sửa" .-> API
  POL -. "Audit các tài nguyên hiện có" .-> REPORT["Violations / Logs / Metrics"]
  API --> STATE["Namespace · RBAC · Quota · Workloads"]
  STATE -. "Drift từ sửa thủ công" .-> SYNC
~~~

**Config Sync hỏi:** “Trạng thái hiện tại có khớp cấu hình được quản lý trong nguồn không?” **Policy Controller hỏi:** “Thao tác hoặc tài nguyên này có đáp ứng chính sách không?” Hai công cụ có thể dùng độc lập; kết hợp sẽ giúp **phân phối cấu hình được duyệt** và **kiểm tra quy tắc**. <https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/overview> ; <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/overview>

### 1.1. Trách nhiệm cụ thể

| Khía cạnh | Config Sync | Policy Controller |
| --- | --- | --- |
| Đầu vào | Git repository, OCI image, Helm chart | ConstraintTemplate, Constraint, policy bundles |
| Hoạt động chính | Liên tục đối chiếu và áp dụng desired state | Audit tài nguyên; admission kiểm tra create/update |
| Khi tài nguyên bị sửa tay | Có thể hòa giải về giá trị mong muốn | Chỉ can thiệp nếu vi phạm một constraint tương ứng |
| Khi manifest trong Git sai | Có thể không sync được hoặc áp dụng cấu hình sai | Có thể ngăn thay đổi vi phạm, nếu policy và admission phù hợp |
| Khi object cũ vi phạm | Config Sync không tự biết quy tắc nghiệp vụ nếu chưa được mã hóa | Audit báo vi phạm; không tự sửa mọi object |
| Quyền quan trọng | Đọc nguồn, reconcile tài nguyên trong cluster | Webhook/controller có quyền đặc thù; quyền quản trị policy |
| Bằng chứng | Git revision, sync status, resource inventory | Constraint status, violations, audit/admission logs |

**Không thay thế các lớp khác:** Policy Controller không tự cấp IAM tối thiểu cho Google Cloud project, không thay Binary Authorization, network policies, workload identity, secret management hoặc vulnerability scanning. Config Sync cũng không phải hệ thống backup của Git/etcd hay công cụ rollback cơ sở dữ liệu.

## 2. Config Sync: đồng bộ theo GitOps

**GitOps** dùng repository/version control làm nơi lưu **cấu hình mong muốn**. Với Config Sync, bộ điều khiển (*reconciler*) theo dõi nguồn, chuẩn hóa manifests và dùng Kubernetes API để tạo/sửa/xóa tài nguyên thuộc phạm vi quản lý.

~~~text
Git commit R1:
  namespace orders-lab có owner=orders-team
       ↓
Config Sync áp dụng R1 lên cluster
       ↓
Ai đó sửa owner=unknown trực tiếp bằng kubectl
       ↓
Config Sync phát hiện drift và đưa về owner=orders-team
~~~

Điều này **không** có nghĩa Config Sync luôn khôi phục tức thì. Đồng bộ có chu kỳ, có thể gặp lỗi Git auth, network, API server, RBAC, admission webhook hoặc xung đột với controller khác. Theo dõi *đã áp dụng revision nào* quan trọng hơn chỉ xem một Pod trong namespace.

### 2.1. Các loại nguồn

| Source of truth | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| **Git** | PR review, lịch sử, branch và rollout thông thường | Config Sync cần read-only access; kiểm soát credentials/branch |
| **OCI image** | Đóng gói manifests thành artifact có thể pin digest | Quy trình publish, quyền Artifact Registry và identity |
| **Helm chart** | Cấu hình dựa chart và values khi được hỗ trợ | Cách cấu hình nguồn Helm có giới hạn theo Console/gcloud; có thể dùng `RootSync`/`RepoSync` qua Kubernetes API |

**Không đặt Git credentials hoặc plaintext secrets trực tiếp trong repository.** Config Sync cần quyền đọc nguồn; Kubernetes resources được đồng bộ vẫn cần quy trình secret management phù hợp.

### 2.2. `RootSync` và `RepoSync`

| Resource | Phạm vi | Ví dụ sử dụng |
| --- | --- | --- |
| **RootSync** | Reconciler cấp cluster, có thể quản lý cluster-scoped và namespaced resources | Platform team quản lý Namespace, RBAC, ResourceQuota, Policy Controller constraints |
| **RepoSync** | Reconciler theo một namespace, giới hạn ở namespaced resources của namespace đó | Application team quản lý ConfigMap, Deployment, Service của chính namespace |

- `RootSync` được tạo trong namespace hệ thống `config-management-system`; mặc định cài Config Sync có thể tạo đối tượng `root-sync`.
- `RepoSync` nằm trong namespace mà nó quản lý. Cần ràng buộc RBAC và người sở hữu nguồn phù hợp.
- Một cluster có thể dùng nhiều nguồn, nhưng **không để hai reconcilers cùng sở hữu một object**. Xung đột cùng `group/kind/namespace/name` có thể tạo lỗi `KNV1060`.
- Không yêu cầu ứng dụng tự tạo cluster-scoped `Namespace` thông qua một `RepoSync` chỉ có quyền namespace.

**Nguyên tắc ownership:** Platform repo tạo namespace và guardrails; app repo quản lý workload trong namespace đó. Phân quyền Git, Kubernetes RBAC và Config Sync reconciler phải khớp.

## 3. Policy Controller: audit và admission

**Policy Controller** xây trên Open Policy Agent Gatekeeper và cung cấp thư viện các **ConstraintTemplates**, constraints, policy bundles và công cụ quan sát tuân thủ. Một template định nghĩa loại quy tắc và parameters; một **Constraint** cụ thể chọn scope tài nguyên và giá trị cần kiểm tra.

Ví dụ:

~~~text
ConstraintTemplate: K8sRequiredLabels
    |
    +-- Constraint "namespaces-must-have-owner"
            match: kind Namespace
            parameters.labels: owner
            enforcementAction: dryrun | warn | deny
~~~

### 3.1. Ba enforcement actions

| Mode | Khi có vi phạm trong thao tác admission | Dùng khi nào |
| --- | --- | --- |
| `dryrun` | Không chặn; vi phạm được ghi nhận để đánh giá | Mặc định khi thử quy tắc mới |
| `warn` | Không chặn; trả warning tại admission khi có vi phạm | Giai đoạn migration/nhắc nhóm triển khai |
| `deny` | Từ chối request vi phạm | Khi đã có baseline, ngoại lệ và rollout được duyệt |

**Nếu thiếu `spec.enforcementAction`, mặc định là `deny`.** Vì vậy luôn khai báo `dryrun` rõ ràng khi đưa constraint mới vào cluster có workload thực. <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/auditing-constraints>

### 3.2. Admission khác audit

- **Admission:** webhook kiểm tra những thao tác mà Kubernetes API gửi tới nó, thường create/update. `deny` có thể ngăn object mới hoặc bản sửa vi phạm; **không tự xóa các object cũ đang vi phạm**.
- **Audit:** quét các tài nguyên đang tồn tại và ghi nhận violations theo chu kỳ; hữu ích phát hiện cấu hình cũ bị lệch policy.
- **Độ tin cậy:** theo tài liệu hiện hành, webhook của Policy Controller **fail-open** khi controller không hoạt động để tránh làm tê liệt cụm. Đây không phải một cơ chế bảo đảm mọi thao tác đều bị chặn trong mọi thời điểm.
- **Referential constraints:** quy tắc cần thông tin từ object khác có thể phụ thuộc cache và **eventual consistency**; không giả định chúng cung cấp giao dịch phân tán tuyệt đối.

Đối với kiểm soát quan trọng, cần bổ sung **CI policy validation**, Kubernetes RBAC, audit, admission monitoring và các guardrails khác của GKE/Google Cloud.

## 4. Chuẩn bị lab và nguyên tắc an toàn

Bài thực hành giả định **cụm GKE thử nghiệm đã tồn tại** và đã đăng ký với **fleet**. Không tạo hoặc sửa cụm production để làm ví dụ.

| Đầu vào | Giá trị minh họa |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| GKE cluster | `gke-policy-lab` |
| Fleet membership | `gke-policy-lab` |
| Namespace | `orders-lab` |
| Git repository | `https://github.com/ORG/gke-config-lab.git` |
| Thư mục Git | `clusters/lab` |
| Nhãn bắt buộc | `owner` |
| Constraint | `namespaces-must-have-owner` |

**Điều kiện:**

1. Người thực hành có quyền phù hợp để bật fleet features, cấu hình sync và tạo constraints; kiểm tra IAM thay vì cấp Owner toàn project.
2. `gcloud`, `kubectl`, `nomos` có sẵn; kubecontext trỏ đúng cluster lab.
3. Các APIs cần thiết được bật theo hướng dẫn và hạn mức/quota/chi phí được duyệt.
4. Git repo dành cho lab có nhánh/revision và manifests đúng; `auth: none` **chỉ dùng cho Git public**. Với Git private, dùng SSH/token/GitHub App hoặc Workload Identity theo nguồn được hỗ trợ.
5. Cụm không cài một Gatekeeper open source khác chồng lên Policy Controller nếu không được hỗ trợ; xác nhận khả năng Autopilot/Standard của từng tính năng trước khi bật mutation hoặc exemption.
6. Các tài nguyên hệ thống như `kube-system`, `gatekeeper-system`, `config-management-system` không được thử chặn bừa bãi. Giới hạn policy lab vào đối tượng/namespace định trước.
7. Ghi lại cấu hình cũ và người sở hữu; bật policy ở **dryrun trước**.

**Cảnh báo thao tác:** Các lệnh `enable`, `apply`, `delete` bên dưới thay đổi cluster/fleet. Ví dụ lab mang mục đích học, không chạy trong môi trường sản xuất nếu chưa có change approval và rollback.

## 5. Cài Config Sync và kết nối source of truth

### 5.1. Kiểm tra trạng thái trước khi bật

~~~bash
gcloud config get-value project
gcloud container fleet memberships list --project=LAB_PROJECT_ID
gcloud container clusters list --project=LAB_PROJECT_ID

# Tài nguyên Kubernetes hiện có (đọc, đúng kubecontext)
kubectl config current-context
kubectl get ns orders-lab --ignore-not-found
kubectl get rootsync -n config-management-system
~~~

Nếu CRD `RootSync` chưa cài, lệnh cuối có thể báo resource type không tồn tại; đây là tín hiệu cần kiểm tra feature installation, không phải lý do để cố cài CRD bằng manifest không rõ nguồn.

### 5.2. Cách cài qua Console

Trong Google Cloud Console, vào **GKE → Config** hoặc mục **Config Sync** theo giao diện hiện hành, chọn **Install Config Sync** cho fleet hoặc cụm lab đã đăng ký, rồi triển khai package từ source of truth. Theo dõi trạng thái cài đặt và nguồn Git. Console có thể tự đăng ký membership khi chọn cluster.

Cách này thuận tiện cho fleet; nếu cần tùy chỉnh `RootSync` và multi-repo, sử dụng hướng dẫn cấu hình theo Kubernetes API của Google Cloud.

### 5.3. Ví dụ cài bằng gcloud fleet

Để giữ nội dung lab nhất quán, ta chọn **bật feature trước, cấu hình nguồn sau**. Theo tài liệu gcloud hiện hành, tệp `apply-spec.yaml`:

~~~yaml
applySpecVersion: 1
spec:
  configSync:
    enabled: true
~~~

Sau khi cluster đã thuộc fleet, quản trị viên được phép chạy:

~~~bash
# Thay đổi fleet/cluster: chỉ làm trên lab
gcloud beta container fleet config-management enable \
  --project=LAB_PROJECT_ID

gcloud beta container fleet config-management apply \
  --membership=gke-policy-lab \
  --config=apply-spec.yaml \
  --project=LAB_PROJECT_ID
~~~

Kiểm tra:

~~~bash
gcloud beta container fleet config-management status \
  --project=LAB_PROJECT_ID

kubectl get rootsync -n config-management-system
~~~

Nếu bản CLI hoặc chế độ quản lý fleet của tổ chức khác ví dụ, kiểm tra `gcloud beta container fleet config-management --help` và tài liệu cài đặt hiện hành, **không** suy rằng mọi phiên bản đều có cùng subcommands/flags. <https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-config-sync>

### 5.4. Cấu hình RootSync theo Git

Tạo hoặc sửa đối tượng `RootSync` **trong môi trường lab** bằng file `root-sync.yaml`:

~~~yaml
apiVersion: configsync.gke.io/v1beta1
kind: RootSync
metadata:
  name: root-sync
  namespace: config-management-system
spec:
  sourceType: git
  sourceFormat: unstructured
  git:
    repo: https://github.com/ORG/gke-config-lab.git
    revision: main
    dir: clusters/lab
    auth: none
    period: 60s
~~~

Đây là cấu hình minh họa **chỉ chạy khi** repository Git public thật và chứa manifests ở đúng thư mục. Với nguồn private, thay `auth: none` bằng kiểu xác thực được hỗ trợ và cấu hình credentials/identity theo hướng dẫn (không ghi secret vào Git). Với source OCI hoặc Helm phải dùng trường tương ứng, không dùng `git.repo` để trỏ tới chart.

~~~bash
# Có tác động: trỏ Config Sync tới Git source của lab
kubectl apply -f root-sync.yaml

# Đọc trạng thái
kubectl get rootsync root-sync -n config-management-system -o yaml
nomos status
~~~

Nếu cài qua Console/fleet defaults và đội vận hành quản lý cấu hình tập trung, phải thống nhất **một ownership path** cho cài đặt; tránh để automation khác liên tục ghi đè `RootSync`.

### 5.5. Tổ chức repo ngắn gọn

~~~text
gke-config-lab/
  clusters/
    lab/
      namespace-orders.yaml
      quota-orders.yaml
      constraint-owner.yaml        # thêm sau khi Policy Controller sẵn sàng
~~~

`namespace-orders.yaml`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-lab
  labels:
    owner: orders-team
    environment: lab
~~~

`quota-orders.yaml`:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-lab
spec:
  hard:
    pods: "10"
    requests.cpu: "4"
    requests.memory: 8Gi
~~~

Commit và push manifests vào Git **đã được review**; Config Sync sẽ đọc, parse và áp dụng. Phải xem `ResourceQuota` có phù hợp các Pods trong namespace không; một quota quá thấp có thể khiến workloads mới không chạy.

## 6. Xác minh đồng bộ và drift

Dùng `nomos status` để kiểm tra package/reconciler đã lấy revision và apply thành công, không chỉ xem trạng thái feature đã cài:

~~~bash
nomos status

kubectl get ns orders-lab --show-labels
kubectl get resourcequota orders-quota -n orders-lab

kubectl get rootsync root-sync -n config-management-system \
  -o yaml
~~~

Khi thay `owner` trong Git và commit, Config Sync sẽ cập nhật namespace sau khi lấy được revision mới. Để minh họa drift, **chỉ trên namespace lab do chính bạn quản lý**, có thể sửa label trực tiếp rồi theo dõi nó được đưa về desired state:

~~~bash
# Thay đổi tài nguyên; KHÔNG dùng trên namespace production
kubectl label namespace orders-lab owner=manual-change --overwrite

# Chỉ đọc để quan sát reconciliation
kubectl get ns orders-lab --show-labels
nomos status
~~~

**Không cam kết drift được sửa ngay lập tức**; thời gian phụ thuộc fetch interval, API/server reconciliation, quyền và lỗi nguồn. Một thay đổi thủ công trên tài nguyên **không thuộc phạm vi Config Sync** sẽ không được tính năng này tự quản lý.

Nếu cần **undo** một thay đổi mong muốn đã được push nhầm, ưu tiên **revert Git commit** rồi để reconciler áp dụng. Chỉnh trực tiếp bằng `kubectl` có thể bị ghi đè. Trước khi xóa một manifest khỏi source, kiểm tra cơ chế **pruning/deletion** và hậu quả; xóa tên namespace khỏi Git có thể tác động tới toàn bộ workloads.

## 7. Cài Policy Controller và kiểm tra template library

### 7.1. Bật API và controller qua fleet

Sau khi xác nhận cluster thuộc fleet, quản trị viên có thể dùng:

~~~bash
# Thao tác thay đổi project và fleet, chỉ dùng trong lab
gcloud services enable anthospolicycontroller.googleapis.com \
  --project=LAB_PROJECT_ID

gcloud container fleet policycontroller enable \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID
~~~

Kiểm tra trạng thái:

~~~bash
gcloud container fleet policycontroller describe \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID

kubectl get constrainttemplates
kubectl get pods -n gatekeeper-system
~~~

Cài đặt thành công có thể hiển thị state `ACTIVE` trong metadata fleet; controller/template library cần thời gian khởi động. Policy Controller được cấu hình theo fleet và có thể có **fleet defaults**. Không bật hàng loạt mọi cluster khi chỉ thực hành trên một membership.

Theo tài liệu, thư viện templates được cài theo cấu hình mặc định; có thể kiểm tra `kubectl get constrainttemplates`. Nếu `K8sRequiredLabels` chưa có, **không áp dụng constraint dựa trên template đó** cho đến khi template đã sẵn sàng. <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/installing-policy-controller>

### 7.2. Cẩn trọng với cấu hình nâng cao

- **Mutating webhook** và một số lựa chọn exemption có giới hạn trên GKE Autopilot; kiểm tra hướng dẫn chính thức trước khi bật.
- **Referential constraints** cần đồng bộ object cache và có thể có độ trễ; không mặc nhiên mạnh như policy chỉ dựa object đang admission.
- Policy Controller cài đặt có thể ảnh hưởng API admission throughput và latency; cần theo dõi trước khi mở rộng.
- Không cài OPA Gatekeeper standalone chồng lên Policy Controller trong cùng cluster khi hướng dẫn không hỗ trợ.

## 8. Viết constraint bắt buộc nhãn `owner`

Sau khi Policy Controller và template library sẵn sàng, tạo constraint `K8sRequiredLabels`. Để tránh tác động tới namespace hệ thống, ví dụ **chỉ khớp namespace thử nghiệm** `orders-policy-test`.

Tệp `constraint-owner.yaml`:

~~~yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: lab-namespace-require-owner
spec:
  enforcementAction: dryrun
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Namespace"]
    namespaces: ["orders-policy-test"]
  parameters:
    labels:
      - key: owner
~~~

**Giải thích các trường quan trọng:**

- `kind: K8sRequiredLabels`: sử dụng template có sẵn; phải chờ CRD/template sẵn sàng.
- `match.kinds`: kiểm tra **Namespace** (core API group).
- `match.namespaces`: với resource loại Namespace, Gatekeeper coi namespace đó thuộc về chính nó; ví dụ chỉ nhắm `orders-policy-test`.
- `parameters.labels`: yêu cầu có label key `owner`; muốn giới hạn giá trị có thể bổ sung `allowedRegex` theo schema template.
- `enforcementAction: dryrun`: quan sát vi phạm trước, **không chặn**.

**Phân biệt kiểm tra ở đâu:** Chỉ kiểm tra metadata labels của object **Namespace**; không tự kiểm tra từng Pod/Deployment trong namespace đó. Muốn kiểm tra workloads phải có constraint/scope riêng.

### 8.1. Quản lý constraint bằng Config Sync

Nếu platform team dùng `RootSync` trỏ `clusters/lab`, hãy **commit constraint vào thư mục Git này sau khi Policy Controller đã cài**. Config Sync sẽ reconcile resource đó.

~~~text
clusters/lab/
  namespace-orders.yaml
  quota-orders.yaml
  constraint-owner.yaml
~~~

Khi constraint **thuộc sở hữu Config Sync**, không chỉnh trực tiếp `kubectl patch` để chuyển `dryrun → deny`: lần đồng bộ sau sẽ đưa về giá trị Git. Thay đổi Git qua pull request là cách đúng để giữ audit.

Chỉ dùng `kubectl apply -f constraint-owner.yaml` nếu bạn đang thử trên một cluster không đồng bộ đối tượng constraint đó qua Config Sync. Đừng quản lý **cùng một constraint** qua cả lệnh thủ công và source of truth.

### 8.2. Kiểm tra ở chế độ dryrun

Tạo tệp `bad-namespace.yaml` trên **máy thực hành**:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-policy-test
  # Cố tình thiếu nhãn owner
~~~

Sau khi constraint đã được đồng bộ:

~~~bash
# Tài nguyên lab có tác động thật: tạo namespace thiếu owner
kubectl apply -f bad-namespace.yaml

# Đọc Constraint và kết quả audit
kubectl get k8srequiredlabels lab-namespace-require-owner -o yaml
kubectl get ns orders-policy-test --show-labels
~~~

Khi action là `dryrun`, Kubernetes có thể **chấp nhận** namespace chưa đạt policy; sau audit cycle, Constraint sẽ ghi nhận các trường trong `status` như `totalViolations` hoặc `violations`. Kết quả audit không nhất thiết xuất hiện ngay sau `kubectl apply`.

### 8.3. Chuyển sang deny sau khi đánh giá

Sau khi đã chứng minh rule đúng scope, review các trường hợp ngoại lệ và có approval, đổi **trong Git**:

~~~yaml
spec:
  enforcementAction: deny
~~~

Đây là **đoạn thay đổi minh họa**, không phải full manifest; phần còn lại giữ nguyên. Sau khi Config Sync đồng bộ, kiểm tra `kubectl get k8srequiredlabels ... -o yaml` để xác nhận mode thật.

Bây giờ, namespace `orders-policy-test` **đang tồn tại** và thiếu `owner` **không bị tự xóa**. Nhưng một thao tác **update** khiến webhook admission đánh giá object vẫn thiếu nhãn có thể bị từ chối. Chỉ thử trong lab:

~~~bash
# Kiểm tra ở server, không lưu thay đổi nếu --dry-run=server được hỗ trợ
kubectl label namespace orders-policy-test stage=deny-test \
  --overwrite --dry-run=server
~~~

Kỳ vọng: request không được chấp nhận bởi constraint vì object vẫn không có `owner`. Thử một thay đổi có bổ sung owner, sau đó xác minh hành vi:

~~~bash
# Chỉ khi test dry-run lành tính, thêm label thật cho namespace LAB
kubectl label namespace orders-policy-test owner=orders-team

kubectl get ns orders-policy-test --show-labels
~~~

**Cảnh báo:** Bật deny trên mọi `Namespace` trong cụm có thể ảnh hưởng add-ons và công cụ hệ thống. Lab dùng scope một namespace có chủ đích, không phải chính sách production hoàn chỉnh. Với production, thiết kế exemptions, label policy, quy trình admission, audit và migration theo đội bảo mật.

### 8.4. Test đúng điều kiện và tránh false positives

- Một constraint mới không bao giờ nên tự động chuyển sang `deny` chỉ vì YAML “hợp lệ”.
- Không dùng `enforcementAction: deny` trên cluster thật khi chưa kiểm chứng scope/exception.
- Phân biệt một **admission denial** mới với audit violation trên resource **đang tồn tại**.
- Nếu dùng `warn` trong giai đoạn chuyển tiếp, warning không chặn deployment; phải đo số vi phạm còn lại.
- Với constraint nhiều parameters/phụ thuộc object khác, kiểm tra schema ConstraintTemplate và eventual consistency.

## 9. Triển khai nhiều cụm an toàn

Một pipeline tối thiểu:

~~~mermaid
flowchart TD
    PR["PR sửa cấu hình/constraint"] --> CHECK["Schema + Policy review + security checks"]
    CHECK --> DEV["Git source cho cluster lab"]
    DEV --> DRY["Policy Controller dryrun/warn\nConfig Sync xác nhận Synced"]
    DRY --> RISK{"Có vi phạm/lỗi sync?"}
    RISK -- "Có" --> FIX["Sửa manifest/constraint trong Git"]
    FIX --> PR
    RISK -- "Không" --> STAGE["Staging: kiểm thử admission và readiness"]
    STAGE --> APPROVE["Change approval"]
    APPROVE --> PROD["Rollout từng nhóm clusters"]
    PROD --> OBS["Monitor drift, violations, API errors"]
~~~

### 9.1. Quyền sở hữu GitOps

| Nhóm | Sở hữu | Không nên có |
| --- | --- | --- |
| Platform | RootSync, namespace, RBAC baseline, constraints/bundles | Quyền merge tùy ý không review |
| Application | RepoSync cho namespace được giao, app manifests | Cluster-admin hoặc sửa guardrail toàn fleet |
| Security | Policy library, exceptions, approval `deny` | Phải thao tác trực tiếp mỗi cluster |
| SRE | Health, audit, rollback, monitoring | Chữa cháy bằng thay Git ngoài quy trình |

Nguồn Git cần branch protection, review, secret scanning và kiểm tra YAML. **Người có quyền merge vào root repo có thể tác động rộng tới cluster**; dù Git dễ audit, quyền này phải được quản trị như một đặc quyền hạ tầng.

### 9.2. Tránh hai controller “đánh nhau”

Ví dụ một operator khác cũng sửa `spec` của cùng Deployment do Config Sync quản lý. Khi hai controller liên tục thay cùng field, có thể phát sinh conflict hoặc loop. Giải pháp:

1. Xác nhận **owner của từng field/resource** và đường quản trị chính.
2. Không đồng bộ những trường mà HPA/operator cần tự chỉnh theo hướng dẫn sản phẩm.
3. Dùng cấu hình ignore fields/ownership phù hợp khi được hỗ trợ, hoặc không đưa tài nguyên đó vào GitOps scope.
4. Với `RootSync` và `RepoSync` cùng quản lý resource, xử lý nguồn ownership; mã lỗi `KNV1060` báo conflict thường gặp.
5. **Không tắt Config Sync để hợp thức hóa drift** khi chưa hiểu hệ quả xóa/pruning.

### 9.3. Rollback an toàn

| Sự cố | Cách khôi phục ưu tiên |
| --- | --- |
| Config Sync áp cấu hình sai | Revert Git commit, quan sát sync status và runtime readiness |
| Constraint deny chặn release | Chuyển về `dryrun`/`warn` qua Git có approval, theo dõi hòa giải |
| Git credentials mất hiệu lực | Sửa authentication hoặc quyền read-only, không mở repository private thành public |
| Policy controller không sẵn sàng | Kiểm tra controller, admission/audit health; không coi fail-open là an toàn |
| Xóa manifest khỏi Git ngoài ý muốn | Đánh giá pruning tác động; restore manifest từ lịch sử Git, xác minh dữ liệu |
| RepoSync xung đột RootSync | Gỡ ownership trùng từ một nguồn, không patch thủ công vòng lặp |

Việc revert manifest **không tự khôi phục dữ liệu** nếu một StatefulSet/PVC/Namespace đã bị xóa và storage không có cơ chế bảo vệ. Cần backup và DR riêng.

## 10. Quan sát, xử lý lỗi và quyền tối thiểu

### 10.1. Các lệnh quan sát chỉ đọc

~~~bash
# Config Sync
nomos status
kubectl get rootsync -n config-management-system
kubectl get reposync -A

# Policy Controller
gcloud container fleet policycontroller describe \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID
kubectl get constrainttemplates
kubectl get k8srequiredlabels lab-namespace-require-owner -o yaml

# Kiểm tra namespace trong lab
kubectl get ns orders-lab orders-policy-test --show-labels
~~~

Một lệnh `kubectl get constrainttemplates` cho biết templates tồn tại, nhưng **không chứng minh constraint đang audit/enforce đúng**. Cần xem action và violations; tương tự `RootSync` tồn tại chưa chứng minh revision mới nhất đã Synced.

### 10.2. Ma trận sự cố ngắn

| Hiện tượng | Nguyên nhân hay gặp | Bước kiểm tra |
| --- | --- | --- |
| Config Sync không lấy được Git | URL/branch/path sai, auth hết hạn, egress DNS/network | `nomos status`; logs `git-sync`; RootSync status |
| Git được lấy nhưng apply lỗi | Manifest/CRD/RBAC/admission không tương thích | Mã lỗi `KNV...`, resource events, API response |
| `KNV1060` | Nhiều nguồn cùng quản lý resource | Tìm RootSync/RepoSync trùng group/kind/name/namespace |
| `KNV2009` | Apply Kubernetes API thất bại | Đọc lỗi chi tiết, RBAC/CRD/namespace/constraint |
| Có drift kéo dài | Sync lỗi hoặc field do controller khác sửa | Đối chiếu source revision, ownership và controller |
| Constraint báo CRD không tồn tại | Template library chưa cài/sẵn sàng | `kubectl get constrainttemplates` và controller status |
| Namespace thiếu owner vẫn tạo được | Constraint `dryrun/warn`, scope không khớp hoặc webhook không hoạt động | Kiểm tra `enforcementAction`, match, admission health |
| Namespace đã có vi phạm vẫn tồn tại sau deny | Deny không tự xóa tài nguyên cũ | Audit, cập nhật resource theo policy |
| Add-on bị chặn khi bật deny | Policy quá rộng/thiếu ngoại lệ | Tạm quay về dryrun có phê duyệt, chỉnh match |
| Audit báo violation nhưng không thấy ngay | Audit chạy theo chu kỳ | Chờ chu kỳ, kiểm tra logs và Constraint status |
| CI báo hợp lệ nhưng Config Sync fail | Khác cluster API versions, CRDs, permissions | Test server-side validation ở cluster lab cùng version |

### 10.3. Metric và cảnh báo nên có

| Nhóm | Tín hiệu |
| --- | --- |
| Config Sync | Sync success/error, source revision applied, thời gian drift |
| Policy Controller | Violations theo constraint/cluster, denies/warnings, webhook/audit health |
| Kubernetes API | Admission latency/error rate, API server load |
| Workload | Pod readiness, deployment rollout, HTTP 5xx/p95 |
| Security | Thay đổi RootSync, constraints, roles, secrets, source credentials |
| Chi phí | GKE cluster/node, controller resources, Cloud Logging/Monitoring, Git/OCI transfer |

Nhiều `RootSync`/`RepoSync` có thể làm tăng API requests do các reconcilers hoạt động song song; không thêm nguồn tùy tiện. Config Sync dùng server-side apply; các API PATCH trong audit logs không nhất thiết nghĩa là source vừa thay đổi.

### 10.4. Tác động của IAM và bảo mật

- **Google Cloud IAM/fleet permissions** quản lý ai được bật feature và cấu hình GKE ở tầng Google Cloud.
- **Kubernetes RBAC** quản lý ai tạo/sửa `RootSync`, `RepoSync`, Constraint, Namespace và RoleBinding.
- **Git permissions** quản lý ai đưa desired state vào nguồn.
- **Service identity** của Config Sync cần quyền **đọc nguồn** Git/OCI/Helm, không nhất thiết quyền write lên source.
- **Secret Manager/Workload Identity** và cách xác thực nguồn cần được triển khai theo môi trường; không commit token/SSH private key vào Git.
- Config Sync/Policy Controller là **controllers có quyền mạnh trong cluster**, nên cập nhật phiên bản, giám sát và tách trách nhiệm quản trị.

## 11. Case study: chuẩn hóa GKE cho hệ thống đặt hàng

**Bối cảnh:** Đội nền tảng sở hữu ba clusters dev/staging/prod, đội orders chịu trách nhiệm namespace riêng; security yêu cầu mọi namespace ứng dụng có owner và workloads phải giới hạn tài nguyên.

Giải pháp:

1. **RootSync:** phát hành baseline về Namespace, RBAC, ResourceQuota và constraints từ platform Git.
2. **RepoSync:** cho đội orders tự quản lý Deployments, Services, ConfigMaps trong namespace mà họ được giao.
3. **Policy Controller:** thử `K8sRequiredLabels` ở `dryrun`; sau kiểm toán, chuyển `deny` theo từng cluster hoặc nhóm resource có kiểm soát.
4. **CI:** validate manifests, security checks, pull request approvals; không coi Config Sync tự kiểm mọi lỗi.
5. **SRE:** theo dõi sync status, policy violations, rollout success và HTTP SLO.
6. **Rollback:** revert Git/đổi `deny → dryrun` nếu chính sách chặn việc sửa khẩn cấp, có audit lý do.

**Câu hỏi thiết kế:** Nếu một Namespace trong Git thiếu owner, Config Sync sẽ phải áp dụng object vi phạm. Khi Policy Controller ở `deny`, reconcile có thể bị chặn; vì vậy **kiểm tra policy trong CI và dryrun trước khi mở rộng** giúp tránh tạo sự cố tự gây ra.

**Đánh đổi chi phí:** Mỗi cluster cần controller resources/observability và đội ngũ duy trì policy; đổi lại giảm sai lệch cấu hình, công sửa tay và thời gian kiểm toán. Không hứa tỉ lệ tiết kiệm hoặc mức SLA khi chưa có số đo thực tế.

## 12. Bài thực hành có hướng dẫn

**Mục tiêu:** Hoàn tất hai kiểm chứng độc lập trên cluster lab.

| Bước | Thao tác | Bằng chứng cần nộp |
| --- | --- | --- |
| 1 | Xem fleet membership, kubecontext, APIs và quyền | Đúng project/cluster lab |
| 2 | Bật Config Sync, cấu hình RootSync tới Git thử nghiệm | `nomos status` và source revision |
| 3 | Commit Namespace có `owner` và ResourceQuota | Hai tài nguyên xuất hiện trong cluster |
| 4 | Sửa nhãn namespace lab trực tiếp, quan sát drift | Label quay lại trạng thái Git |
| 5 | Cài Policy Controller/template library | Feature ACTIVE, `K8sRequiredLabels` có sẵn |
| 6 | Commit constraint ở `dryrun`, tạo `orders-policy-test` thiếu owner | Có violation, thao tác không bị deny |
| 7 | Sau review, đổi `deny` trong Git; thử server-side dry-run update không hợp lệ | Admission từ chối đúng scope |
| 8 | Thêm `owner` hợp lệ và quan sát audit | Vi phạm được khắc phục theo chu kỳ |
| 9 | Thu thập logs, ghi runbook và rollback | Không ảnh hưởng namespace ngoài lab |

**Dọn lab:** Nếu `orders-policy-test` được tạo thủ công, chỉ xóa namespace đó sau khi xác nhận không có workload/dữ liệu khác. Việc xóa namespace hoặc gỡ `RootSync` có thể kéo theo tài nguyên do Config Sync quản lý; không tắt fleet features hoặc xóa source Git chung chỉ để kết thúc bài. Đối chiếu ownership, retention và chi phí trước khi xóa tài nguyên lab.

## 13. Câu hỏi ôn tập

1. **Config Sync khác Policy Controller ở điểm nào?** Một công cụ hòa giải desired state; một công cụ kiểm toán/thực thi constraints.
2. **RootSync và RepoSync khác nhau?** RootSync quản lý tài nguyên cấp cluster và namespace; RepoSync giới hạn namespace theo cấu hình/quyền.
3. **Có thể dùng OCI/Helm làm nguồn không?** Có theo khả năng hỗ trợ; cách cài source Helm không giống Git trong Console/CLI.
4. **ConstraintTemplate và Constraint có giống nhau?** Không; template định nghĩa loại quy tắc, constraint cấu hình phạm vi/tham số.
5. **Nếu bỏ enforcementAction?** Mặc định là `deny`, có thể gây gián đoạn.
6. **Dryrun có tự sửa violation không?** Không; chỉ đánh giá, không chặn hay tự chỉnh resource.
7. **Deny có xóa Namespace cũ thiếu owner không?** Không, nó chặn request phù hợp khi admission diễn ra.
8. **Tại sao không mở deny toàn cluster ngay?** Dễ chặn add-ons và thay đổi vận hành hợp lệ; phải scope, dryrun và quản trị ngoại lệ.
9. **Tại sao sửa constraint bằng kubectl rồi bị trở lại bản cũ?** Nó đang thuộc sở hữu Git/Config Sync.
10. **KNV1060 thường chỉ điều gì?** Trùng ownership resource giữa nhiều sources of truth.
11. **Git được fetch nhưng apply fail có thể do đâu?** API/CRD/RBAC, admission constraint, manifest lỗi hoặc xung đột controllers.
12. **Policy Controller offline có luôn chặn API không?** Không; tài liệu nêu admission webhook fail-open khi không chạy.
13. **GitOps có thay thế backup ứng dụng không?** Không, Git giữ manifests nhưng không khôi phục dữ liệu đã xóa.
14. **Đâu là ba nguồn permission phải xét?** Google Cloud IAM, Kubernetes RBAC và Git/source access.
15. **Thước đo rollout thành công là gì?** Source revision Synced, không có policy violations ngoài dự kiến, workload/SLO không xấu đi.

## 14. Checklist đưa vào vận hành

- [ ] Đã phân định RootSync/RepoSync ownership và quyền Git review.
- [ ] Source of truth có versioning, branch protection và không chứa secrets.
- [ ] Config Sync đã Sync đúng revision trên từng cluster; không chỉ “installed”.
- [ ] Có CI validation theo Kubernetes API/CRDs và policies mục tiêu.
- [ ] Policy Controller templates/bundles đã đúng phiên bản và health.
- [ ] Constraints có scope, exceptions, parameters và `enforcementAction` tường minh.
- [ ] Đã quan sát `dryrun`/`warn` trước khi bật `deny`.
- [ ] Đã xử lý vi phạm sẵn có, cả namespace/add-ons liên quan.
- [ ] Có metrics/cảnh báo sync errors, drift, admission failures, API latency.
- [ ] IAM, Kubernetes RBAC, nguồn Git/OCI và controller identities tuân thủ least privilege.
- [ ] Có runbook khôi phục Git, policy và tình huống controller lỗi.
- [ ] Đã kiểm tra tác động tới workload, SLO, controller resource và chi phí.
- [ ] Không có hai reconcilers tranh quyền sở hữu cùng một object.

## 15. Tài liệu chính thức Google Cloud

- [Config Sync overview](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/overview) — GitOps và reconciliation.
- [Sources of truth](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/concepts/sources-of-truth) — Git, OCI, Helm; `RootSync`.
- [Install Config Sync](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-config-sync) — Console, fleet và CLI.
- [RootSync and RepoSync fields](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/reference/rootsync-reposync-fields) — cấu trúc CRDs và auth.
- [Multiple sources of truth](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/multiple-repositories) — multi-repo/ownership.
- [Use nomos](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/nomos-command) — trạng thái đồng bộ.
- [Config Sync troubleshooting](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/troubleshooting-config-sync) — điều tra errors.
- [Config Sync error reference](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/reference/errors) — `KNV1060`, `KNV2009`.
- [Install Policy Controller](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/installing-policy-controller) — fleet, APIs và prerequisites.
- [Constraint template library](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/latest/reference/constraint-template-library) — `K8sRequiredLabels` và nhiều templates khác.
- [Create constraints](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/creating-policy-controller-constraints) — YAML, match và parameters.
- [Audit constraints](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/auditing-constraints) — `dryrun`, `warn`, `deny`.
- [Policy Controller constraint match](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/reference/match) — scope và namespace/label selectors.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — chi phí sử dụng tính năng và cluster.

**Kết luận:** **Config Sync quản lý trạng thái mong muốn; Policy Controller kiểm tra và áp quy tắc tuân thủ.** Hai công cụ hiệu quả nhất khi có ownership Git rõ ràng, manifests được review, constraints triển khai từ `dryrun` đến `deny` theo bằng chứng, và quan sát được cả trạng thái đồng bộ lẫn tác động lên workloads.
