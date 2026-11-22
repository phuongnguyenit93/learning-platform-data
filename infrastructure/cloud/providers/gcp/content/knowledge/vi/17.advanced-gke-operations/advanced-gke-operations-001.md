# Workload Identity Federation for GKE và quyền truy cập dịch vụ

Một dịch vụ Java `orders-api` chạy trên Google Kubernetes Engine (GKE) cần đọc cấu hình từ Secret Manager, tải tài liệu từ Cloud Storage và phát sự kiện qua Pub/Sub. Cách đơn giản nhưng nguy hiểm là tạo **service account key dạng JSON**, đóng gói vào container hoặc lưu trong Kubernetes Secret rồi đặt đường dẫn vào biến `GOOGLE_APPLICATION_CREDENTIALS`. Nếu key bị lộ, người có key có thể dùng nó bên ngoài cluster cho đến khi key bị vô hiệu hóa; đội vận hành còn phải quản lý vòng đời và luân chuyển khóa.

**Workload Identity Federation for GKE** giải quyết vấn đề bằng cách cho Pod sử dụng **danh tính Kubernetes ServiceAccount (KSA)** để nhận **credential ngắn hạn** khi gọi Google Cloud API. Không cần tạo hay phân phối private key của IAM service account cho ứng dụng. Quyền truy cập được quản lý qua **Google Cloud IAM** và có thể giới hạn tới từng bucket, secret, topic hoặc tài nguyên cần thiết.

Bài thuộc chương **GKE nâng cao và vận hành**, trong học phần **CLOUD_PROVIDERS_GCP**: khám phá Google Cloud từ project, IAM, VPC tới Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu; qua tình huống triển khai để bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Sau bài này, bạn có thể:

- Phân biệt Kubernetes ServiceAccount, Google Cloud IAM service account, node service account và IAM principal của workload.
- Giải thích dòng credential đi qua **GKE metadata server**, Kubernetes API và **Security Token Service (STS)**.
- Chọn **direct resource access** (cấp IAM trực tiếp cho KSA principal) hoặc **IAM service account impersonation**.
- Cấu hình Workload Identity Federation for GKE cho **GKE Standard** và biết vì sao **Autopilot** không cần bật thủ công.
- Triển khai một Pod Java đọc Cloud Storage bằng **Application Default Credentials (ADC)** mà không gắn JSON key.
- Thiết kế quyền truy cập cross-project, bảo vệ trước **identity sameness** giữa các cluster và quản lý IAM theo nguyên tắc quyền tối thiểu.
- Tìm nguyên nhân lỗi `403`, metadata timeout, NetworkPolicy, ImagePullBackOff và quota.
- Chuẩn bị migration từ node credentials/JSON keys, logging, rollback và checklist production.

> **Cảnh báo phạm vi thực hành:** Tên project, cluster, bucket, namespace, IAM service account và image trong ví dụ đều là placeholder. Việc sửa IAM hoặc cập nhật node pool có thể làm workload đang chạy mất quyền truy cập. Thử trong môi trường được phép, review quyền và có kế hoạch rollback trước khi thực thi.

## 1. Vấn đề: Pod nên dùng danh tính nào để gọi Google Cloud?

Giả sử ba ứng dụng chia sẻ một cluster:

| Workload | Cần truy cập | Không nên có quyền |
|---|---|---|
| `orders-api` | Đọc một secret cấu hình, đọc một bucket tài liệu | Xóa bucket, quản lý IAM, đọc dữ liệu HR |
| `payment-worker` | Publish một Pub/Sub topic | Subscribe topic nhạy cảm, tạo VM |
| `report-generator` | Ghi vào một bucket báo cáo | Xóa secret thanh toán, đổi firewall |

Nếu cả ba Pod cùng dùng **node service account** với quyền rộng, việc xâm nhập một Pod có thể mở đường tới những tài nguyên của ứng dụng khác. Nếu mỗi ứng dụng mang theo JSON key, phạm vi IAM có thể được thu hẹp nhưng xuất hiện rủi ro **phân phối/đánh cắp private key tồn tại lâu dài**.

Workload Identity Federation for GKE tạo quan hệ giữa **danh tính workload trong Kubernetes** và **IAM policy tại dịch vụ Google Cloud**. Ứng dụng nhận token ngắn hạn, chỉ có quyền mà IAM cho principal đó hoặc IAM service account được phép impersonate.

### Bốn khái niệm thường bị nhầm

| Danh tính | Được định nghĩa ở đâu? | Dùng để làm gì? |
|---|---|---|
| **Kubernetes ServiceAccount (KSA)** | Kubernetes API, thuộc một namespace | Danh tính cho process trong Pod; dùng cho Kubernetes và federation |
| **Federated IAM principal** | Workload identity pool do GKE quản lý trong IAM | Đại diện KSA để cấp role trên tài nguyên Google Cloud |
| **IAM service account (GSA)** | Google Cloud IAM, email `name@project.iam.gserviceaccount.com` | Danh tính service account có role IAM; có thể được KSA impersonate |
| **Node service account** | Gắn với VM node của GKE | Node/system agents dùng để gọi API, ví dụ kéo container image |

**KSA không tự là GSA.** Với **direct resource access**, KSA có IAM principal riêng và **không cần tạo GSA hoặc annotation liên kết**. Với **impersonation**, KSA được ủy quyền lấy token của một GSA qua IAM Credentials API; khi đó cần cả IAM binding và KSA annotation.

### Kubernetes RBAC khác Google Cloud IAM

- **RBAC** kiểm soát các thao tác với Kubernetes API: list Pods, tạo Deployments, đọc Kubernetes Secrets.
- **Google Cloud IAM** kiểm soát gọi Cloud Storage, Secret Manager, Pub/Sub, BigQuery, Cloud SQL Admin API và nhiều dịch vụ khác.
- Một KSA có IAM `roles/storage.objectViewer` **không đồng nghĩa** được quyền list Kubernetes Secrets.
- Một user có Kubernetes `cluster-admin` **không tự có mọi IAM role** tại mọi project Google Cloud. Tuy vậy, quyền tạo/sửa Pod hoặc KSA có thể cho phép lạm dụng danh tính workload đã được cấp IAM; phải bảo vệ RBAC tương ứng.

## 2. Workload Identity Federation for GKE hoạt động thế nào?

GKE quản lý **workload identity pool** cho project theo tên:

~~~text
PROJECT_ID.svc.id.goog
~~~

Khi một Pod dùng Google Cloud client library hoặc HTTP metadata endpoint để lấy credential, **GKE metadata server** trên node tiếp nhận yêu cầu. Dịch vụ này lấy token Kubernetes ServiceAccount từ Kubernetes API rồi dùng **Security Token Service (STS)** trao đổi để nhận **federated access token** ngắn hạn.

~~~mermaid
sequenceDiagram
    participant APP as Java Pod (KSA)
    participant META as GKE metadata server
    participant K8S as Kubernetes API
    participant STS as Security Token Service
    participant API as Google Cloud API
    APP->>META: ADC yêu cầu access token
    META->>K8S: Yêu cầu KSA token
    K8S-->>META: JWT có danh tính KSA
    META->>STS: Trao đổi JWT
    STS-->>META: Federated access token
    META-->>APP: Short-lived credential
    APP->>API: API request + bearer token
    API-->>APP: Kết quả theo IAM policy
~~~

**Trường hợp impersonation:** sau STS, GKE metadata server còn gọi **IAM Service Account Credentials API** để nhận access token thay mặt GSA được liên kết. Google Cloud API nhận token dưới danh tính GSA; vì vậy role trên tài nguyên phải được cấp cho **GSA**, đồng thời KSA phải có quyền `roles/iam.workloadIdentityUser` trên GSA đó.

### Lợi ích bảo mật và giới hạn

- Không cần private key JSON gắn trong Pod hoặc CI artifact.
- Credential có hạn sử dụng và thường được **Google Cloud client libraries tự làm mới**.
- IAM role có thể giới hạn rất nhỏ: một KSA chỉ đọc object trong một bucket, hoặc chỉ publish một topic.
- Khi thu hồi IAM binding, quyền truy cập mới bị chặn theo propagation/token lifetime; **thu hồi không hủy ngay lập tức mọi access token đã phát**.
- Nếu Pod bị chiếm quyền, kẻ tấn công có thể sử dụng quyền của chính KSA trong thời gian còn kiểm soát Pod. Federation **không thay** sandboxing, Pod Security, NetworkPolicy và bảo mật ứng dụng.

**Từ vựng:** GKE trước đây thường gọi tính năng này là **Workload Identity**. Tên hiện hành **Workload Identity Federation for GKE** nhấn mạnh federation và phân biệt với Workload Identity Federation dành cho Kubernetes tự quản/EKS/AKS.

## 3. Hai mô hình cấp quyền: direct và impersonation

### Mô hình A — Cấp IAM trực tiếp cho KSA principal

~~~text
Pod (KSA: apps/orders-reader)
       │ federated credential
       ▼
IAM principal://.../subject/ns/apps/sa/orders-reader
       │ roles/storage.objectViewer trên một bucket
       ▼
Cloud Storage bucket
~~~

Khi Google Cloud API hỗ trợ federated principal, cấp role **trên tài nguyên thật** cho principal của KSA. Đây là cách thường được **ưu tiên** vì giảm số danh tính và IAM binding trung gian; không cần tạo GSA.

### Mô hình B — KSA impersonate một IAM service account

~~~text
Pod (KSA: apps/orders-reader)
       │ Workload Identity User trên GSA
       ▼
IAM service account: orders-reader@security-project.iam.gserviceaccount.com
       │ roles/storage.objectViewer trên bucket
       ▼
Cloud Storage bucket
~~~

Cần **đồng thời** (1) IAM binding `roles/iam.workloadIdentityUser` trên GSA cho KSA và (2) annotation `iam.gke.io/gcp-service-account` trong KSA. Chỉ có một phía sẽ không hoạt động.

| Tiêu chí | **Direct resource access** | **GSA impersonation** |
|---|---|---|
| Principal nhận IAM role trên resource | IAM principal đại diện KSA | GSA |
| Có cần GSA riêng? | Không | Có |
| Có cần KSA annotation trỏ GSA? | Không | Có |
| Có cần role `iam.workloadIdentityUser`? | Không | Có |
| Cấu hình IAM | Ít tầng hơn | Thêm liên kết giữa KSA và GSA |
| Hỗ trợ API | Tùy Google Cloud API/method chấp nhận federated principal | Hữu ích với API/method không hỗ trợ direct |
| Audit identity | Có thể là principal KSA federated | Thường thấy GSA; cần xem delegation info để truy về KSA |
| Quản lý quyền | Role cho đúng KSA principal trên resource | Role resource cho GSA và quyền impersonate |

**Cách chọn:** bắt đầu bằng direct khi Google Cloud API và loại thao tác hỗ trợ; dùng impersonation khi có yêu cầu danh tính service account email, signed URLs, API/client legacy hoặc giới hạn khác được tài liệu dịch vụ xác nhận. Không chọn impersonation chỉ vì quen dùng `*.iam.gserviceaccount.com`.

## 4. Cú pháp IAM principal và vấn đề identity sameness

### Một KSA principal cụ thể

~~~text
principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/NAMESPACE/sa/KSA_NAME
~~~

Giải thích:

- `PROJECT_NUMBER` và `PROJECT_ID` là **project chứa GKE cluster** và workload identity pool, **không mặc định là project chứa bucket/secret đích**.
- `NAMESPACE` là Kubernetes namespace, ví dụ `apps`.
- `KSA_NAME` là Kubernetes ServiceAccount name, ví dụ `orders-reader`.
- `PROJECT_ID.svc.id.goog` là tên pool GKE tạo ra; không tự thay bằng một pool IAM mới tùy ý.
- Prefix `principal://` chỉ **một danh tính**; `principalSet://` là **một tập danh tính**.

Ví dụ với project number `123456789012` và project ID `platform-prod`:

~~~text
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/platform-prod.svc.id.goog/subject/ns/apps/sa/orders-reader
~~~

### Grant theo nhóm: vì sao phải thận trọng?

~~~text
# Mọi Pod trong cùng namespace, có thể qua nhiều cluster cùng project:
principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/namespace/NAMESPACE

# Mọi Pod trong một GKE cluster cụ thể:
principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/kubernetes.cluster/https://container.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER_NAME
~~~

Hai mẫu này phục vụ các tình huống khác nhau. Với ứng dụng chỉ cần quyền một bucket, nên **grant cho một KSA principal cụ thể** thay vì toàn namespace/cluster. Các `principalSet` dễ cấp quyền ngoài ý muốn khi team thêm workload mới.

### Identity sameness giữa các cluster cùng project

GKE tạo workload identity pool **ở cấp project**. Nếu hai cluster trong cùng project có cùng namespace `apps` và cùng KSA `orders-reader`, IAM principal dựa trên **namespace/name** có thể xem chúng là **cùng danh tính**, dù Pod chạy ở hai cluster khác nhau!

~~~text
Project: platform-prod (pool platform-prod.svc.id.goog)
    ├── Cluster A: namespace apps, KSA orders-reader ─┐
    └── Cluster B: namespace apps, KSA orders-reader ─┴──> Cùng principal theo name
                                                        │
                                                IAM bucket access
~~~

Đây là **identity sameness**. Nếu Cluster B thuộc nhóm không được tin cậy nhưng có thể tự tạo KSA trùng tên, nó có thể nhận cùng IAM role theo principal name.

Hướng xử lý:

1. **Tách cluster có ranh giới tin cậy khác nhau sang project riêng** để có workload identity pool riêng.
2. Đặt namespace/KSA name độc lập khi các cluster cần các quyền khác nhau, và kiểm soát quyền tạo namespace/KSA.
3. Với yêu cầu tinh chỉnh, dùng principal theo **ServiceAccount UID**, principalSet theo cluster hoặc IAM Conditions hỗ trợ ngữ cảnh để hạn chế phạm vi; cân nhắc vòng đời UID khi KSA bị xóa/tạo lại.
4. Không cho user/team không tin cậy có `create/edit Pod`, `ServiceAccount` hay `RoleBinding` tùy ý trong namespace chứa IAM principal mạnh.

**Lưu ý:** chỉ đổi tên GKE cluster không thay pool. Nếu IAM binding dựa trên namespace/KSA name, nó **không có cluster name** trong định danh đó. Tách tài khoản quản trị project là một phần của thiết kế bảo mật workload identity.

## 5. Điều kiện và chuẩn bị trước khi cấu hình

Để thực hành an toàn, chuẩn bị:

- Google Cloud project chứa GKE cluster, đã bật `container.googleapis.com` và billing.
- **GKE Autopilot hoặc Standard cluster** đã tồn tại, đúng version và cấu hình mạng phù hợp.
- `gcloud`/`kubectl` đã đăng nhập, đủ quyền truy cập cluster và cập nhật IAM resource đích.
- Quyền IAM quản lý cluster/ServiceAccounts khi bật tính năng, ví dụ `roles/container.admin` và `roles/iam.serviceAccountAdmin` cho người chịu trách nhiệm, cùng quyền sửa IAM trên bucket/secret/topic.
- API đích đã bật; tài liệu GKE yêu cầu **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`) trong hướng dẫn thiết lập, đặc biệt quan trọng khi impersonate GSA.
- Một bucket Cloud Storage lab hoặc một resource thử nghiệm **không có dữ liệu nhạy cảm** để thử quyền chỉ đọc.

**Chú ý:** các quyền để bật GKE và cấp IAM được sử dụng bởi platform/security team, **không** phải những quyền runtime `orders-reader` cần có. Đừng cấp `roles/container.admin` hoặc `roles/iam.serviceAccountAdmin` cho KSA chỉ để ứng dụng đọc object.

### Autopilot so với Standard

| Bước | Dedicated GKE Autopilot cluster | GKE Standard cluster |
|---|---|---|
| Workload Identity Federation for GKE ở cấp cluster | **Luôn bật** | Cần bật hoặc xác minh |
| GKE metadata server trên node | GKE tự quản | Node pools phải dùng `GKE_METADATA` |
| Có thể chọn node pool chưa bật WIF? | Không theo mô hình Autopilot thông thường | Có khi cluster còn node pool cũ dùng `GCE_METADATA` |
| Pod `nodeSelector: iam.gke.io/gke-metadata-server-enabled` | **Không dùng**; Autopilot có thể từ chối selector | Có thể dùng để ép Pod vào node có metadata server |
| IAM binding cho KSA hoặc GSA | Vẫn phải tạo đúng resource | Vẫn phải tạo đúng resource |

**Bật WIF không tự cấp quyền Google Cloud API**. Một Pod vẫn không đọc được Cloud Storage nếu thiếu IAM binding, dù metadata server trả được token.

## 6. Bật Workload Identity Federation trên Standard cluster

Giả sử Standard cluster đã có project và node pools. Dùng Bash/Cloud Shell:

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NODEPOOL="app-pool"

gcloud config set project "$CLUSTER_PROJECT"
gcloud services enable \
  container.googleapis.com \
  iamcredentials.googleapis.com

# Chỉ đọc: kiểm tra pool hiện tại.
gcloud container clusters describe "$CLUSTER" \
  --location="$LOCATION" \
  --format="value(workloadIdentityConfig.workloadPool)"

# CHỈ chạy nếu đã có kế hoạch bật WIF cho Standard cluster.
gcloud container clusters update "$CLUSTER" \
  --location="$LOCATION" \
  --workload-pool="$CLUSTER_PROJECT.svc.id.goog"

# MỚI: mọi node pool tạo sau khi cluster đã bật WIF thường dùng WIF.
# CŨ: node pools tồn tại trước đó không tự đổi metadata mode.
gcloud container node-pools describe "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --format="value(config.workloadMetadataConfig.mode)"

# CHỈ cập nhật sau khi xác minh từng workload không còn lệ thuộc node SA.
gcloud container node-pools update "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --workload-metadata=GKE_METADATA
~~~

**Điểm có thể gây outage:** cập nhật node pool sang `GKE_METADATA` khiến những Pod trên node pool đó **không còn lấy được node service account credential** theo cách cũ. Nếu workload vẫn dùng quyền node SA, API call có thể bắt đầu trả `401/403`. Thực hiện migration từng node pool sau khi đã cấp role cho KSA và kiểm tra các ứng dụng.

Khi Standard cluster có node pools dùng cả `GCE_METADATA` và `GKE_METADATA`, Pod cần WIF phải được scheduling lên đúng node pool. Có thể dùng `nodeSelector` ở **Pod spec**:

~~~yaml
spec:
  nodeSelector:
    iam.gke.io/gke-metadata-server-enabled: "true"
~~~

**Không thêm node selector này vào Autopilot**. Trên Standard, nếu dùng DaemonSet hoặc Pod có node affinity/taints khác, cần rà soát khả năng scheduling. Với một số cấu hình Windows/host networking, có giới hạn riêng; kiểm tra trước khi chuyển workloads.

## 7. Thực hành A: KSA đọc Cloud Storage trực tiếp bằng IAM

Mục tiêu: một Pod trong namespace `apps` dùng KSA `orders-reader` được phép **liệt kê và đọc object** trong **duy nhất một bucket lab**. Không tạo GSA và không dùng JSON key. Các ví dụ giả định cluster đã bật WIF và node pool (nếu Standard) có GKE metadata server.

### Bước 1 — Xác định project chứa cluster và project chứa bucket

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NAMESPACE="apps"
KSA="orders-reader"

BUCKET="my-orders-documents-lab-unique"
# Bucket có thể ở project khác; đây là BUCKET NAME, không phải project ID.

gcloud config set project "$CLUSTER_PROJECT"
gcloud container clusters get-credentials "$CLUSTER" \
  --location="$LOCATION"

gcloud projects describe "$CLUSTER_PROJECT" \
  --format="value(projectNumber)"
~~~

Ghi lại `PROJECT_NUMBER` được lệnh trên trả về. **Không tự lấy project number của bucket project** để dựng principal nếu bucket thuộc project khác. Namespace/KSA thuộc cluster có workload identity pool của `CLUSTER_PROJECT`.

### Bước 2 — Tạo namespace và KSA chuyên biệt

~~~bash
kubectl create namespace "$NAMESPACE"
kubectl create serviceaccount "$KSA" \
  --namespace="$NAMESPACE"

kubectl get serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  -o yaml
~~~

Nếu namespace/KSA đã tồn tại, `kubectl create` báo `AlreadyExists`; không xóa và tạo lại chỉ để lệnh chạy được. Trong production, khai báo Kubernetes ServiceAccount bằng GitOps/Helm/Kustomize và thống nhất owner của namespace.

Manifest tương đương:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-reader
  namespace: apps
~~~

**Không có `iam.gke.io/gcp-service-account` annotation** ở cách cấp quyền direct. KSA được nhận diện bằng namespace và tên trong federated principal.

### Bước 3 — Dựng principal và cấp role trên bucket

~~~bash
PROJECT_NUMBER="$(gcloud projects describe "$CLUSTER_PROJECT" \
  --format='value(projectNumber)')"

PRINCIPAL="principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$CLUSTER_PROJECT.svc.id.goog/subject/ns/$NAMESPACE/sa/$KSA"

# Chỉ cấp quyền Object Viewer trên bucket thực sự cần đọc.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="$PRINCIPAL" \
  --role="roles/storage.objectViewer" \
  --condition=None

# Đọc lại IAM policy để xác nhận member và scope.
gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

Lệnh này **chỉnh IAM của bucket** và cần quyền sửa bucket IAM policy. Nếu policy đã có IAM Conditions, tham số `--condition=None` thể hiện binding mới không có điều kiện; đừng xóa hoặc ghi đè các bindings khác. Người vận hành phải đối chiếu rằng bucket không chứa dữ liệu production trái mục đích bài lab.

Ở cách direct, **không cần**:

~~~text
gcloud iam service-accounts create ...
roles/iam.workloadIdentityUser
iam.gke.io/gcp-service-account
JSON service account key
~~~

### Bước 4 — Gắn KSA vào Pod

Một Pod debug dùng image Cloud SDK chỉ để thực hành kiểm tra identity. Manifest này cần thay image nếu registry của tổ chức có mirror riêng:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: wi-debug
  namespace: apps
spec:
  serviceAccountName: orders-reader
  # STANDARD ONLY: bỏ nodeSelector này trên dedicated Autopilot cluster.
  nodeSelector:
    iam.gke.io/gke-metadata-server-enabled: "true"
  containers:
    - name: debug
      image: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
      command: ["sh", "-c", "sleep 3600"]
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
          ephemeral-storage: "100Mi"
~~~

Với **Autopilot**, xóa toàn bộ trường `nodeSelector` kể cả key `iam.gke.io/gke-metadata-server-enabled`; Autopilot tự cấu hình node metadata server. Với Standard, selector chỉ có ích khi pool phù hợp và có node đủ capacity.

~~~bash
# Giả sử manifest mẫu ở trên được lưu tạm trên máy lab thành wi-debug.yaml.
kubectl apply -f wi-debug.yaml
kubectl -n apps get pod wi-debug -o wide
kubectl -n apps describe pod wi-debug
kubectl -n apps get pod wi-debug \
  -o jsonpath='{.spec.serviceAccountName}'
~~~

Trong bài thực hành, đừng copy toàn bộ YAML ra workspace dự án nếu yêu cầu của job hiện tại chỉ là tài liệu Markdown. Người học thực hiện trên môi trường lab độc lập.

### Bước 5 — Kiểm tra access từ trong Pod

~~~bash
# Kiểm tra token endpoint có phản hồi, nhưng KHÔNG in token ra log/terminal.
kubectl -n apps exec wi-debug -- sh -c \
  'curl -fsS -H "Metadata-Flavor: Google" \
    http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token \
    >/dev/null && echo "metadata token endpoint reachable"'

# Dùng gcloud trong Pod để gọi Cloud Storage bằng credential tự khám phá.
kubectl -n apps exec wi-debug -- \
  gcloud storage ls "gs://$BUCKET"
~~~

Kết quả mong đợi: endpoint metadata hoạt động và lệnh list bucket trả danh sách object hoặc kết quả thành công nếu bucket trống. Khi cấp role theo direct principal, **đúng KSA** mới có quyền; một Pod khác trong cùng namespace dùng `default` KSA không tự có quyền nếu IAM không cấp cho nó.

**Cần phân biệt:** metadata token trả thành công chỉ chứng tỏ có credential; **không chứng minh IAM role cho bucket đúng**. Bước `gcloud storage ls` hoặc HTTP API đến bucket mới thực sự xác minh authorization.

Nếu cần kiểm thử giới hạn quyền, dùng một bucket lab thứ hai không cấp role và mong đợi `403` khi truy cập. Không cần cố thử xóa object để chứng minh không có quyền write, vì dễ tạo thao tác ngoài ý muốn.

### Bước 6 — Thu hồi quyền khi kết thúc lab

~~~bash
# Chỉ gỡ đúng binding đã thêm, không sửa quyền thành viên khác.
gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" \
  --member="$PRINCIPAL" \
  --role="roles/storage.objectViewer" \
  --all

# Chỉ xóa Pod/ServiceAccount của lab nếu chắc chắn không còn ai dùng.
kubectl -n apps delete pod wi-debug
~~~

Không xóa namespace `apps` hoặc cả bucket production chỉ để dọn một bài thực hành. Kiểm tra IAM policies và các Pod đang dùng KSA trước khi gỡ.

## 8. Ứng dụng Java sử dụng Application Default Credentials

Điểm quan trọng nhất đối với developer: **Java code không cần tự phân tích KSA JWT, gọi STS hoặc tải private key**. Google Cloud Java client libraries hỗ trợ **Application Default Credentials (ADC)** và tự lấy token qua metadata server khi chạy trong GKE đã cấu hình.

### Ví dụ Java liệt kê object Cloud Storage

Giả sử project đã khai báo dependency `com.google.cloud:google-cloud-storage` theo một phiên bản hiện hành tương thích với JDK; đoạn code:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class ListOrders {
    public static void main(String[] args) {
        String bucket = System.getenv("ORDERS_BUCKET");
        if (bucket == null || bucket.isBlank()) {
            throw new IllegalArgumentException("ORDERS_BUCKET is required");
        }

        // ADC lấy credential từ GKE metadata server khi chạy trong Pod.
        // Không nạp JSON key vào image hoặc Kubernetes Secret.
        Storage storage = StorageOptions.getDefaultInstance().getService();

        Page<Blob> page = storage.list(
            bucket,
            Storage.BlobListOption.prefix("incoming/")
        );
        for (Blob blob : page.iterateAll()) {
            System.out.println(blob.getName());
        }
    }
}
~~~

Các điểm cần nhớ:

- Trong GKE, `StorageOptions.getDefaultInstance()` sử dụng ADC và credential được phát cho **KSA mà Pod đang dùng** hoặc GSA được liên kết theo impersonation.
- Ở máy phát triển, ADC có thể dùng user credential từ `gcloud auth application-default login`. Đó là **khác môi trường**, không chứng minh Pod production đã có IAM đúng.
- Không đặt biến `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới JSON key cũ trong Pod, vì ADC có thể ưu tiên key đó thay vì metadata server.
- Không in token, JWT, raw metadata JSON hay nội dung secret vào log.
- Với các client libraries cũ, cập nhật phiên bản để có hỗ trợ token refresh và federation ổn định.

### Deployment minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: apps
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
      serviceAccountName: orders-reader
      containers:
        - name: api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
          env:
            - name: ORDERS_BUCKET
              value: my-orders-documents-lab-unique
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 10
      # Standard với mixed node pools: đặt nodeSelector ở đây nếu cần.
~~~

**Manifest là ví dụ**, image Java phải có thật và triển khai endpoint `/ready` tương ứng. Nếu dùng Standard node pools trộn `GCE_METADATA` và `GKE_METADATA`, thêm `nodeSelector` ở `spec.template.spec` của Deployment; không dùng selector này với Autopilot. Nếu ứng dụng phải publish Pub/Sub hoặc đọc Secret Manager, cấp IAM trên tài nguyên đó riêng thay vì role Owner.

### Image pull khác với quyền runtime

Nếu Pod bị `ImagePullBackOff` khi kéo image riêng từ Artifact Registry, kiểm tra **node service account và quyền kéo image**, cấu hình registry/network và image tag. **Cấp `roles/artifactregistry.reader` cho KSA runtime không tự sửa lỗi image pull**, vì kubelet/node là thành phần kéo image trước khi container có thể khởi động.

## 9. Thực hành B: KSA impersonate IAM service account

Dùng khi dịch vụ API hoặc workflow thực sự cần GSA identity, ví dụ một API method không hỗ trợ direct federation, một ứng dụng legacy cần IAM service account email hoặc thao tác ký mà federated principal không đáp ứng. Nên giữ **KSA → GSA** gần với quan hệ 1-1 cho ứng dụng quan trọng, trừ khi đã đánh giá việc dùng chung.

Giả sử:

~~~text
GKE cluster project: my-gke-lab-project
Namespace/KSA: apps/orders-reader
IAM SA project: my-security-project
IAM SA name: orders-runtime
IAM SA email: orders-runtime@my-security-project.iam.gserviceaccount.com
Target bucket: my-orders-documents-lab-unique
~~~

### Bước 1 — Tạo IAM service account

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
IAM_SA_PROJECT="my-security-project"
IAM_SA_NAME="orders-runtime"
NAMESPACE="apps"
KSA="orders-reader"
BUCKET="my-orders-documents-lab-unique"

GSA_EMAIL="$IAM_SA_NAME@$IAM_SA_PROJECT.iam.gserviceaccount.com"

# Chỉ thực hiện nếu service account chưa tồn tại và đúng policy tổ chức.
gcloud iam service-accounts create "$IAM_SA_NAME" \
  --project="$IAM_SA_PROJECT" \
  --display-name="Runtime for orders API"
~~~

### Bước 2 — Cấp quyền resource cho GSA

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$GSA_EMAIL" \
  --role="roles/storage.objectViewer" \
  --condition=None
~~~

GSA được phép đọc bucket theo IAM. Nhưng **KSA chưa được phép dùng GSA** cho đến khi có binding WorkloadIdentityUser.

### Bước 3 — Cho KSA được impersonate GSA

~~~bash
gcloud iam service-accounts add-iam-policy-binding "$GSA_EMAIL" \
  --project="$IAM_SA_PROJECT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$CLUSTER_PROJECT.svc.id.goog[$NAMESPACE/$KSA]"
~~~

**Chú ý cú pháp:** ở cách GKE KSA → GSA linking được tài liệu hướng dẫn, `--member` sử dụng dạng:

~~~text
serviceAccount:CLUSTER_PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]
~~~

Đây **không phải email GSA** và không phải cú pháp `principal://` của phương án direct ở mục 7. Không thay `CLUSTER_PROJECT` bằng `IAM_SA_PROJECT` nếu hai project khác nhau.

### Bước 4 — Annotate KSA

~~~bash
kubectl annotate serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  "iam.gke.io/gcp-service-account=$GSA_EMAIL" \
  --overwrite

kubectl get serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  -o yaml
~~~

Với GitOps, đặt annotation trong manifest KSA thay vì chỉnh tay:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-reader
  namespace: apps
  annotations:
    iam.gke.io/gcp-service-account: orders-runtime@my-security-project.iam.gserviceaccount.com
~~~

Để hoạt động phải có **cả IAM binding lẫn annotation**. Nếu annotation trỏ sai email, hoặc binding cho nhầm namespace/KSA, metadata server không thể tạo GSA access token dù direct federated token vẫn có thể tồn tại.

### Bước 5 — Kiểm tra và chọn rollback

~~~bash
gcloud iam service-accounts get-iam-policy "$GSA_EMAIL" \
  --project="$IAM_SA_PROJECT"

gcloud storage buckets get-iam-policy "gs://$BUCKET"
kubectl -n apps get serviceaccount "$KSA" -o yaml

# Nếu Pod được tạo TRƯỚC khi đổi annotation, nên kiểm thử Pod mới.
kubectl -n apps rollout restart deployment/orders-api
kubectl -n apps rollout status deployment/orders-api
~~~

`rollout restart` làm Pod được thay dần; nó có thể gây gián đoạn nếu Deployment có ít replicas hoặc readiness/surge không đúng. Với production, hãy áp annotation/binding qua CI/CD có review và kiểm thử trên staging trước.

Nếu IAM SA impersonation không hoạt động, xem lỗi `iam.serviceAccounts.getAccessToken denied`, binding WorkloadIdentityUser, email annotation, IAM propagation và việc Pod có thực sự dùng KSA đã cấu hình. Không nên cấp `roles/iam.serviceAccountTokenCreator` rộng rãi hoặc tạo service account key chỉ để vượt lỗi.

**Thu hồi:** gỡ đúng KSA annotation và WorkloadIdentityUser binding sau khi ứng dụng đã chuyển sang phương án mới, sau đó gỡ IAM role trên resource khỏi GSA nếu không còn consumer; không xóa GSA dùng chung mà chưa kiểm tra phụ thuộc.

## 10. Cross-project access và nguyên tắc phân chia project

Không bắt buộc GKE cluster, IAM service account và Google Cloud resource phải trong cùng project:

~~~text
Project A: gke-prod
  ├── GKE cluster
  └── Workload Identity pool: gke-prod.svc.id.goog
       └── KSA apps/orders-reader

Project B: data-prod
  ├── Cloud Storage bucket
  └── Secret Manager secret

Project C: identities-prod (tùy chọn)
  └── GSA orders-runtime@identities-prod.iam.gserviceaccount.com
~~~

**Direct:** IAM policy của bucket/secret ở project B phải tham chiếu principal có **project number và pool của A**. **Impersonation:** GSA tại C được cấp quyền resource ở B; KSA tại A được cấp `roles/iam.workloadIdentityUser` trên GSA tại C. Quyền điều khiển IAM có thể bị Organization Policy, IAM Deny, Principal Access Boundary hoặc VPC Service Controls giới hạn thêm.

| Thành phần | Giá trị dùng để xây principal/binding |
|---|---|
| GKE pool | `A_PROJECT_ID.svc.id.goog` |
| Principal URL project number | **Số project A**, nơi GKE cluster hoạt động |
| IAM binding trên resource | Bucket/secret/topic cụ thể ở **project B** |
| GSA email khi impersonation | `name@C_PROJECT_ID.iam.gserviceaccount.com` |
| WorkloadIdentityUser member | `serviceAccount:A_PROJECT_ID.svc.id.goog[apps/orders-reader]` |

Tránh cấp IAM ở **Organization** hoặc project B nếu chỉ cần một bucket: role càng rộng, blast radius càng lớn. Cross-project access vẫn phải kiểm tra VPC networking/Private Google Access/DNS và policy perimeter; **IAM cho phép không tự tạo đường mạng** đến API.

## 11. Kết nối các dịch vụ phổ biến bằng đúng IAM role

Ví dụ một service Java có ba tác vụ: đọc file, đọc secret và publish sự kiện. Mỗi quyền nên cấp trên tài nguyên cụ thể:

| Dịch vụ | Quyền nghiệp vụ | IAM role tham khảo | Ghi chú |
|---|---|---|---|
| **Cloud Storage** | Liệt kê/đọc object | `roles/storage.objectViewer` | Cấp trên bucket, không toàn project khi không cần |
| **Secret Manager** | Đọc một secret version | `roles/secretmanager.secretAccessor` | Cấp trên **secret cụ thể**, không cho mọi secret |
| **Pub/Sub** | Publish một topic | `roles/pubsub.publisher` | Cấp trên **topic cụ thể** |
| **Pub/Sub** | Consume một subscription | `roles/pubsub.subscriber` | Cấp trên subscription cần dùng |
| **Artifact Registry** | Pull container image | `roles/artifactregistry.reader` | Thường cấp cho **node service account**, không phải runtime KSA |
| **Cloud SQL** | Kết nối instance qua connector/Cloud SQL Auth Proxy | `roles/cloudsql.client` theo resource/loại IAM hỗ trợ | Vẫn cần **DB user/auth**, mạng và cấu hình database |
| **BigQuery** | Chạy query và đọc dataset | `roles/bigquery.jobUser` cùng quyền dataset thích hợp | Hai lớp project job và dataset permissions |
| **Cloud KMS** | Sử dụng khóa để decrypt | `roles/cloudkms.cryptoKeyDecrypter` hoặc role hẹp tương ứng | Cấp trên đúng key, bảo vệ dữ liệu giải mã |

Ví dụ cấp direct IAM trên Pub/Sub topic, dùng `PRINCIPAL` đã tạo ở mục 7:

~~~bash
TOPIC="orders-events"
TOPIC_PROJECT="my-events-project"

gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --project="$TOPIC_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/pubsub.publisher"
~~~

Ví dụ cấp direct IAM trên một Secret Manager secret:

~~~bash
SECRET="orders-api-config"
SECRET_PROJECT="my-secrets-project"

gcloud secrets add-iam-policy-binding "$SECRET" \
  --project="$SECRET_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/secretmanager.secretAccessor"
~~~

Các lệnh giả định API/tài nguyên đã tồn tại và IAM của service hỗ trợ trực tiếp federated principals. Với sản phẩm/API cụ thể chưa hỗ trợ federation, cần kiểm tra **supported products and limitations** rồi dùng GSA impersonation nếu phù hợp. Đừng mặc định mọi API, mọi SDK version và mọi phương thức signed URL đều hỗ trợ principal trực tiếp.

### Cloud SQL có thêm tầng xác thực

KSA/GSA có `roles/cloudsql.client` giúp gọi Cloud SQL API/connector hoặc thiết lập kết nối theo cơ chế hỗ trợ, **không tự biến nó thành database superuser**. Ứng dụng vẫn cần DB user/IAM DB authentication theo database engine, IP/network path tới instance, connection pooling và backup/HA. Với Cloud SQL Auth Proxy hoặc Java Connector, dùng ADC lấy credential qua metadata server thay vì JSON key, rồi bảo vệ credential DB theo quy trình riêng.

### Signed URLs và các API cần email GSA

Một số cách ký URL, ký bytes hoặc API đòi hỏi **IAM service account email/private signing capability** thay vì federated principal thuần. Khi đó đánh giá khả năng **GSA impersonation và IAM Credentials API** theo hướng dẫn của dịch vụ, không xuất private key ra Pod. Phân quyền ký phải hẹp và có giám sát; **signed URL** có thể cấp khả năng đọc/ghi độc lập với danh tính người tải xuống trong thời hạn URL, nên cần giới hạn thời gian, object và HTTP method.

## 12. Metadata server, DNS và NetworkPolicy

Ứng dụng sử dụng ADC trên GKE thường gửi yêu cầu token đến:

~~~text
http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token
http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token
~~~

Để gọi metadata server, HTTP request cần header:

~~~http
Metadata-Flavor: Google
~~~

**GKE metadata server** chặn/nhận các request này và xử lý theo KSA của Pod. Không phải toàn bộ endpoint của **Compute Engine metadata server** đều có trên GKE metadata server: chỉ một tập con dành cho workload identity và một số thuộc tính cluster/node. Truy vấn một metadata field không được hỗ trợ có thể trả `404`, dù cấp IAM đúng.

### NetworkPolicy default-deny egress

Nếu namespace áp **NetworkPolicy** chặn toàn bộ egress, Pod có thể không tới được metadata server. Theo hướng dẫn GKE:

- Với mạng GKE tương ứng thông thường: cần cho phép tới `169.254.169.252/32` trên **TCP port 988**.
- Với **GKE Dataplane V2**: cần cho phép tới `169.254.169.254/32` trên **TCP port 80**.

Đây là yêu cầu về đường tới GKE metadata server, **không phải** whitelist toàn bộ Internet. Policy cụ thể phụ thuộc CNI/Dataplane đang dùng; phải xem cấu hình cluster trước khi áp dụng.

Ví dụ một NetworkPolicy **riêng** cho Pods nhãn `app=orders-api` trong môi trường dùng GKE Dataplane V2:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-gke-metadata
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 169.254.169.254/32
      ports:
        - protocol: TCP
          port: 80
~~~

**Cảnh báo:** ví dụ chỉ mở **một luồng** metadata cần thiết cho GKE Dataplane V2, không mở DNS, Cloud SQL, Google APIs hay toàn bộ traffic ứng dụng. Trong một namespace đang dùng default-deny, cần bổ sung **các policy khác** cho DNS `53`, HTTPS `443`, database và các luồng cần thiết. Policy này **không tương đương** rule cho môi trường dùng `169.254.169.252:988`.

### Node/firewall cần gọi STS

Metadata server trên node cần kết nối tới `sts.googleapis.com` qua TCP 443 để trao đổi token. Nếu VPC có default-deny egress/firewall hoặc định tuyến qua appliance chặn STS, Pod có thể gặp `504 Gateway Timeout` hoặc timeout dù vẫn kết nối được metadata endpoint nội bộ.

Khi điều tra, phân biệt:

~~~text
Pod → GKE metadata server (link-local / NetworkPolicy)
Node/metadata server → Google STS API (network/firewall/route)
Pod → Google Cloud resource API (network/firewall/DNS)
Google Cloud IAM → authorize hoặc deny (IAM roles/conditions)
~~~

Đường network tới API đích và IAM role là hai điều kiện **độc lập**. Một Pod có token đúng nhưng không đến được `storage.googleapis.com` vẫn thất bại; một Pod đến được Storage API nhưng không có Object Viewer vẫn `403`.

## 13. Các trường hợp đặc biệt: hostNetwork, service mesh, token refresh

### Pods dùng hostNetwork

Kubernetes Pod khai báo:

~~~yaml
spec:
  hostNetwork: true
~~~

Thông thường, những Pods này **không sử dụng Workload Identity Federation for GKE** theo đường mặc định: GKE có thể định tuyến metadata requests từ host-network Pod tới **Compute Engine metadata server**, làm lộ danh tính/quyền node service account thay vì danh tính KSA.

**Ngoại lệ cụ thể:** Cloud Storage FUSE CSI driver trên một số phiên bản GKE Standard mới có cơ chế xác thực KSA cho Pods `hostNetwork: true` (tài liệu nêu từ **1.33.3-gke.1226000** khi dùng driver và cấu hình tương ứng). Không suy ra ngoại lệ đó áp dụng cho mọi ứng dụng hostNetwork.

**Thực hành an toàn:** tránh hostNetwork với ứng dụng thông thường; nếu một DaemonSet/agent buộc chạy hostNetwork, kiểm tra riêng đường credential, node SA và quyền tối thiểu của node. Không mặc định các node-level system agents sử dụng KSA riêng giống application Pods.

### Cloud Service Mesh / Istio sidecar

Nếu application container bắt đầu trước khi sidecar proxy sẵn sàng, metadata request có thể bị từ chối hoặc timeout. Với Istio và Cloud Service Mesh, có thể cấu hình annotation:

~~~yaml
metadata:
  annotations:
    proxy.istio.io/config: '{ "holdApplicationUntilProxyStarts": true }'
~~~

Đặt ở **Pod template metadata** theo hướng dẫn mesh; kiểm tra version và Pod admission để chắc chắn annotation có hiệu lực. Song song, Java client nên **retry có backoff** khi chưa lấy được token, thay vì crash vĩnh viễn vì một request thất bại ngay lúc khởi động.

### Token lifetime và caching

Federated/GSA access tokens được cấp **ngắn hạn**; tài liệu GKE nêu mặc định access token có hiệu lực **1 giờ**. GKE metadata server cache token, và Google Cloud client libraries có cơ chế làm mới trước khi token hết hạn.

- **Tái sử dụng client library objects** thay vì tạo mới credential/token cho mọi dòng dữ liệu hoặc mỗi HTTP request.
- Không cache token ở cấu hình bất biến trong application rồi sử dụng vô hạn.
- Không log `Authorization: Bearer ...` hoặc lưu token vào Kubernetes ConfigMap.
- Với client tự viết gọi metadata REST, kiểm tra `expires_in` hoặc expiry và refresh có backoff.
- Khi IAM role vừa thay đổi, xác nhận propagation và token cache trước khi kết luận chính sách đã/không có hiệu lực.

Metadata server có thể cần **vài giây sau khi Pod được tạo** để bắt đầu đáp ứng. Trong tình huống request credential thất bại lúc startup, dùng **retry** hoặc init container kiểm tra metadata readiness; không vội tắt TLS validation hoặc chuyển sang static key.

## 14. Least privilege và bảo vệ Kubernetes ServiceAccount

Workload Identity Federation for GKE tạo cơ chế ủy quyền an toàn hơn **phân phối JSON keys**, nhưng an toàn tổng thể phụ thuộc quyền Kubernetes và IAM.

### Tách KSA theo chức năng

~~~text
Namespace: payments
  ├── KSA payment-api       → Secret Manager secret payment-config
  └── KSA payment-publisher → Pub/Sub topic payment-events

Namespace: reports
  └── KSA report-reader     → Cloud Storage bucket report-inputs
~~~

**Không gắn role mạnh vào KSA `default`** rồi để mọi Pod trong namespace dùng nó. Mỗi workload nên khai báo rõ `spec.serviceAccountName`; không dùng chung KSA giữa các nhóm ứng dụng nếu không có nhu cầu và đánh giá rủi ro.

### Các nguyên tắc phòng thủ

| Lớp | Kiểm soát | Lý do |
|---|---|---|
| **IAM resource** | Cấp role trên bucket/secret/topic cụ thể | Giảm dữ liệu có thể đọc/xóa nếu Pod bị xâm nhập |
| **KSA identity** | Mỗi namespace/workload có KSA riêng | Tách danh tính và audit |
| **Kubernetes RBAC** | Giới hạn quyền tạo/sửa Pod, KSA, RoleBindings | Ngăn tự chọn KSA mạnh để chạy Pod |
| **Pod Security** | Giảm quyền privileged, hostPath, hostNetwork | Hạn chế leo thang qua host/node |
| **NetworkPolicy** | Giới hạn ingress/egress nhưng vẫn cho phép metadata | Giảm nguy cơ exfiltration và lỗi auth |
| **IAM Conditions** | Giới hạn thời gian hoặc thuộc tính resource khi hỗ trợ | Thu hẹp phạm vi cấp quyền |
| **GKE project boundary** | Tách cluster không tin cậy ở project khác | Tránh identity sameness |
| **Audit/Monitoring** | Xem IAM policy changes, access failures và identity use | Phát hiện truy cập ngoài ý muốn |

Một Pod có IAM quyền đọc secret mạnh có thể tiết lộ dữ liệu thông qua HTTP endpoint bị lỗi hoặc SSRF; WIF không bảo vệ ứng dụng khỏi việc **tự gửi credential/secret** tới attacker. Vì vậy phải vá thư viện, chặn SSRF, validate URL đích và kiểm soát outbound traffic.

### Danh tính runtime và quyền deploy

Developer/pipeline chỉ cần quyền cập nhật Deployment chưa chắc đã nên có quyền:

- Tạo/sửa KSA đã được IAM cấp quyền mạnh.
- Sửa Pod `serviceAccountName` sang KSA của team khác.
- Tạo `ClusterRoleBinding` với `cluster-admin`.
- Sửa admission policies/NetworkPolicy làm mất ranh giới mạng.

Nếu namespace dùng chung nhiều team, RBAC và admission policies cần giới hạn các hành vi này. **IAM role cấp cho KSA là một khả năng bảo mật**, nên quản trị KSA như quản trị secret/role chứ không chỉ coi nó là cấu hình trang trí của Pod.

### IAM Conditions và Deny

Role `roles/storage.objectViewer` trực tiếp trên bucket có thể là đủ. Nếu bắt buộc cấp quyền ở project-level hoặc chỉ trong thời gian xử lý sự cố, dùng **IAM Conditions** (khi resource và thuộc tính hỗ trợ), ví dụ hạn hết quyền theo `request.time`. Trong tổ chức có **IAM Deny**, **Principal Access Boundary** hoặc **VPC Service Controls**, quyền Allow có thể không đủ để thao tác thành công; xem đầy đủ effective access.

## 15. Migration từ node service account hoặc JSON key

Một dự án cũ có nhiều workload dùng `GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/key.json` hoặc dựa trên node service account. **Không đổi node pool sang `GKE_METADATA` trong khi chưa biết ứng dụng nào phụ thuộc credential cũ.**

### Quy trình migration đề xuất

1. **Inventory:** liệt kê workloads, namespaces, KSA, image versions, Kubernetes Secrets/volumes, node pools và các API Google Cloud được gọi. Không xuất nội dung private keys ra log.
2. **Thiết kế quyền:** tạo KSA riêng cho từng app, chọn direct hay impersonation, thống kê IAM role/resource cần có; kiểm tra cross-project và identity sameness.
3. **Enable cluster-level WIF:** trên Standard cluster; ưu tiên **node pool mới có `GKE_METADATA`** để canary những ứng dụng đã tương thích.
4. **Gán resource IAM:** cấp quyền cho KSA principal/GSA trước, đợi IAM propagation rồi mới chuyển traffic.
5. **Cập nhật application:** dùng phiên bản Google Cloud Java client libraries hỗ trợ ADC; bỏ mount secret key và biến `GOOGLE_APPLICATION_CREDENTIALS` khi sẵn sàng.
6. **Deploy canary:** test credential, quyền đọc/ghi đúng phạm vi và hành vi khi restart/scale-out trong node pool mới hoặc Autopilot.
7. **Chuyển dần:** rollout theo namespace/workload; quan sát error rate của Google APIs, token failures và business metrics.
8. **Thu hồi khóa cũ:** sau khi xác minh không còn phụ thuộc, vô hiệu hóa/xóa service account keys theo quy trình bảo mật; không xóa GSA còn consumer hợp lệ.
9. **Giảm quyền node SA:** rà soát role thừa, giữ các quyền dành cho image pulling, logging/monitoring và node-level services cần thiết.
10. **Ghi runbook/rollback:** định nghĩa tiêu chí thành công, failure modes, ai có quyền hồi phục, và thời điểm kết thúc quá trình.

### Lưu ý khi cập nhật node pool

Chuyển node pool hiện hữu sang `GKE_METADATA` tác động **ngay** tới mọi Pod trên đó. Nếu chỉ một workload đã tương thích, nên tạo **node pool mới** rồi chuyển có kiểm soát trước khi đổi pool cũ. Trong Standard cluster có thể có tạm hai loại node pool; thêm node selector/affinity rõ ràng cho workloads đã migrate.

Không nên rollback bằng việc mở lại node metadata access rộng rãi cho production một cách vô thời hạn. Nếu ứng dụng cần rollback gấp, có thể dùng node pool cũ theo kế hoạch ứng phó đã duyệt, nhưng **phải lập lịch khắc phục để trở lại WIF**. Với **Autopilot**, WIF luôn bật và không có cách tắt tương đương Standard để né lỗi auth.

### GitOps và thứ tự triển khai

~~~text
IAM roles và resource policies
  → Workload Identity Federation cluster/node pool
  → Namespace / KSA / annotation (nếu impersonation)
  → Deployment spec.serviceAccountName
  → Canary API access
  → Production traffic rollout
  → Remove old key mounts / revoke static keys
  → Audit effective permissions
~~~

Trong GitOps, **IAM bindings thường được quản lý bằng Terraform** còn KSA/Deployment bằng Kubernetes manifests. Phải có phụ thuộc vận hành rõ: Terraform IAM xong chưa có nghĩa quyền đã propagation ngay; CI/CD cần retry test có kiểm soát thay vì deploy rồi khẳng định mọi `403` là do sai code.

## 16. Lỗi thường gặp và quy trình chẩn đoán

Khi một Pod không gọi được Google Cloud API, bắt đầu từ **thực tế Pod đang dùng danh tính nào** và **API nào báo lỗi**. Không tăng role IAM một cách mù quáng.

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| `403 PERMISSION_DENIED` khi đọc bucket | Principal sai project number, thiếu role/bucket scope hoặc IAM Conditions | KSA, member trong bucket policy, resource target |
| `iam.serviceAccounts.getAccessToken denied` | Thiếu `roles/iam.workloadIdentityUser` trên GSA, sai annotation, quyền đang propagation | IAM SA policy, KSA annotation, chờ propagation |
| `401 UNAUTHENTICATED` | Không lấy token, token hết hạn, library/ADC sai | Metadata endpoint, client auth config, logs |
| Metadata timeout `169.254...` | NetworkPolicy/Dataplane chặn, server chưa sẵn sàng, sidecar | Đường metadata, Pod startup, Istio |
| `504 Gateway Timeout` khi đổi token | STS `443` bị firewall chặn hoặc network egress lỗi | Node/network path tới `sts.googleapis.com` |
| `404` một metadata attribute | GKE metadata server không hỗ trợ field đó | Metadata endpoint documentation |
| `ImagePullBackOff` | Node SA thiếu Artifact Registry Reader hoặc image/network sai | Node identity, registry, image tag |
| Hoạt động ở Standard nhưng lỗi ở Autopilot | Node selector bị từ chối hoặc Pod security/requests không hợp lệ | Events, mode và manifest |
| Một cluster khác truy cập được cùng bucket | Namespace/KSA trùng trong cùng WIF project pool | Identity sameness và IAM principal |
| GSA access hoạt động nhưng signed URL lỗi | API/library yêu cầu email/signing khác token hiện tại | GSA impersonation, IAM Credentials và quyền ký |
| Lỗi đột ngột sau cập nhật node pool | Pod trước đó dùng node SA | Node pool `workloadMetadataConfig.mode`, migration |
| Token lỗi ngay khi Pod boot | Metadata server chưa sẵn sàng | Retry/backoff hoặc init readiness |
| Workload thiếu quyền khi cross-project | Binding đặt sai target project hoặc Organization Policy/Perimeter | Project nguồn/đích, IAM và VPC-SC |

### Bước 1 — Xác minh cluster và node pool

~~~bash
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NODEPOOL="app-pool"
NAMESPACE="apps"
POD="orders-api-EXAMPLE"

gcloud container clusters describe "$CLUSTER" \
  --location="$LOCATION" \
  --format="value(workloadIdentityConfig.workloadPool)"

gcloud container node-pools describe "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --format="value(config.workloadMetadataConfig.mode)"

kubectl -n "$NAMESPACE" get pod "$POD" -o wide
kubectl -n "$NAMESPACE" describe pod "$POD"
kubectl -n "$NAMESPACE" get pod "$POD" \
  -o jsonpath='{.spec.serviceAccountName}'
~~~

Trong **Autopilot** bỏ các thao tác node pool dành cho Standard; tập trung vào KSA, IAM, NetworkPolicy và Pod events. Nếu node mode là `GCE_METADATA` trên Standard, Pod đó chưa có đường WIF mong muốn.

### Bước 2 — Xem KSA và role trên tài nguyên

~~~bash
kubectl get serviceaccount orders-reader -n apps -o yaml
gcloud storage buckets get-iam-policy "gs://my-orders-documents-lab-unique"

# Chỉ với cách impersonation:
gcloud iam service-accounts get-iam-policy \
  orders-runtime@my-security-project.iam.gserviceaccount.com \
  --project=my-security-project
~~~

Xác minh member name dùng **đúng project chứa GKE cluster**, namespace và KSA. Với impersonation phải có cả annotation và role WorkloadIdentityUser; quyền resource phải cấp cho GSA chứ không chỉ cho KSA.

### Bước 3 — Kiểm tra đường metadata, không log token

~~~bash
# Thực thi trong một Pod lab có curl; không in access token ra terminal.
curl -sS --fail \
  -H 'Metadata-Flavor: Google' \
  'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token' \
  >/dev/null && echo "token endpoint OK"
~~~

Nếu metadata thành công nhưng Google API còn `403`, ưu tiên kiểm tra **IAM**, resource scope và API hỗ trợ federation. Nếu metadata thất bại, kiểm tra **NetworkPolicy**, STS network, node mode, Cloud Service Mesh và GKE metadata server.

### Bước 4 — Kiểm tra readiness của GKE metadata server

~~~bash
# Standard cluster: quyền xem kube-system cần được cho phép.
kubectl -n kube-system get pods -l k8s-app=gke-metadata-server

# Khi không chắc labels chính xác, dùng:
kubectl -n kube-system get pods
~~~

GKE metadata server được triển khai dạng DaemonSet trên Linux nodes (và dịch vụ Windows tương ứng). Nếu Pod metadata bị OOM/crash hoặc cần vài giây để ready, một số request auth có thể thất bại. Không xóa DaemonSet do Google quản lý để “reset” khi chưa chẩn đoán nguyên nhân.

### Bước 5 — Suy luận theo mã lỗi

~~~text
Could not find default credentials
  → Application dùng ADC? GOOGLE_APPLICATION_CREDENTIALS đang trỏ đâu?
  → metadata DNS/IP reachable? Node pool GKE_METADATA?

403 from IAMCredentials.GenerateAccessToken
  → GSA annotation đúng? WorkloadIdentityUser đúng namespace/KSA?
  → IAM propagation, IAM Deny hoặc policy context?

403 from storage.googleapis.com
  → Đúng bucket? roles/storage.objectViewer trên bucket đó?
  → Direct principal vs GSA? Bucket policy có member đúng?

ImagePullBackOff
  → Kubelet/node SA + Artifact Registry access;
     KHÔNG chỉ chỉnh IAM của KSA runtime.
~~~

Để tránh nhầm hai tầng lỗi, luôn ghi **API nào trả 403**. IAM Credentials trả 403 lúc **tạo GSA token** khác hoàn toàn Cloud Storage trả 403 lúc **đọc object**.

## 17. Độ tin cậy, quota và hiệu năng của đường lấy credential

Mọi Pod đều có thể gọi metadata để lấy access token, nhưng **GKE metadata server không phải một dịch vụ có công suất vô hạn**. Khi ứng dụng tạo nhiều clients hoặc mỗi request HTTP đều cố lấy token mới, hệ thống có thể tăng latency hoặc chạm quota.

Một số giới hạn/đặc tính đáng chú ý theo tài liệu GKE hiện hành:

| Thành phần | Giới hạn hoặc hành vi | Hướng thiết kế |
|---|---|---|
| **STS Exchange Token API** | Quota tham khảo **6.000 token exchanges/phút** theo tài liệu GKE, phụ thuộc cấu hình/quota đang có | Cache token, dùng client libraries, yêu cầu tăng quota khi có bằng chứng |
| **GKE metadata server** | Tối đa **500 concurrent connections trên một node**; vượt giới hạn có thể xếp hàng và xuất hiện `HTTP/499` khi client timeout | Không tạo credential client mới cho từng request; đo connection/latency |
| **Token lifetime** | Mặc định khoảng **3.600 giây** | Tái sử dụng và refresh có backoff |
| **Pod startup** | Metadata server có thể chưa ready trong vài giây đầu | Retry hoặc init readiness check |
| **KSA count lớn** | Trên khoảng **3.000 KSAs trong cluster**, metadata server Pod có thể gặp áp lực bộ nhớ/OOM theo tài liệu | Tách cluster/giảm KSA không dùng, theo dõi system Pods |
| **IAM binding propagation** | Role grant có thể mất vài phút để có hiệu lực | Đợi và retry thay vì cấp thêm role rộng |
| **Control plane unavailability** | Có thể ảnh hưởng đường phát token mới | Chọn kiến trúc control plane HA, chuẩn bị retry/circuit breaker |

Các ngưỡng có thể thay đổi theo version và quota của project; phải kiểm tra **Quotas & System Limits** tại thời điểm vận hành. Không dùng con số trong bài làm bảo đảm về SLA hay mức băng thông được cấp.

### Phân biệt quota của STS và IAM Credentials

- **Direct resource access** thường cần STS token exchange.
- **GSA impersonation** còn cần các thao tác như `GenerateAccessToken` hoặc `GenerateIdToken` từ **IAM Service Account Credentials API**.
- GKE có hỗ trợ đặt **quota project** khác cho một số thao tác IAM Credentials; feature này có điều kiện về phiên bản và permission, không tự tăng quota toàn bộ các dịch vụ đích.

Ví dụ khi cần chuyển quota của IAM Credentials sang một project chuyên biệt:

~~~bash
QUOTA_PROJECT="my-identity-quota-project"

# PROJECT_NUMBER và PRINCIPAL là của GKE cluster project.
gcloud projects add-iam-policy-binding "$QUOTA_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/serviceusage.serviceUsageConsumer" \
  --condition=None

kubectl annotate serviceaccount orders-reader -n apps \
  "iam.gke.io/credential-quota-project=$QUOTA_PROJECT" \
  --overwrite
~~~

Đây là tùy chọn dành cho tình huống **quota IAM Service Account Credentials API**, không phải bước bắt buộc của mọi workload. Người vận hành cần kiểm tra quyền `serviceusage.services.use`, project bị tính quota và kết quả thực tế trên Quotas dashboard.

### Hướng tối ưu cho ứng dụng Java

1. Khởi tạo Google Cloud Storage/Pub/Sub/Secret Manager client một số lần hợp lý, dùng lại qua connection pool hoặc singleton được quản lý.
2. Dùng ADC có refresh tự động; không gọi metadata endpoint thủ công cho mỗi business request.
3. Cài đặt retry có backoff và jitter cho lỗi transient nhưng không retry vô hạn `PERMISSION_DENIED` do policy thiếu.
4. Đặt timeout tách biệt cho metadata/token, API đích và downstream database.
5. Theo dõi `request latency` và token errors sau Pod scale-out, node drain hoặc GKE upgrades.
6. Không log access token; log identity label, operation name và error code đã được biên tập.

## 18. Cloud Audit Logs và quan sát quyền thực tế

**IAM permission được khai báo** và **quyền đang được sử dụng** không hoàn toàn giống nhau. Để thu hẹp quyền theo thực tế, cần kiểm tra Cloud Audit Logs và chỉ số lỗi ứng dụng.

### Các điểm kiểm toán

| Nguồn | Cần quan sát |
|---|---|
| **Cloud Audit Logs của IAM** | Ai sửa role binding trên resource/GSA, policy có điều kiện nào thay đổi |
| **Data Access logs của dịch vụ đích** | Read secret, đọc object, publish message theo cấu hình logging của dịch vụ |
| **IAM Credentials API logs** | Hoạt động `GenerateAccessToken`/impersonation khi thông tin được ghi |
| **GKE metadata server logs** | Token exchange failures, connectivity/availability của metadata path |
| **GKE Kubernetes Audit Logs / events** | Ai tạo/sửa KSA, Deployment, ServiceAccount annotation, RBAC |
| **Application logs và Monitoring** | `401/403/429/5xx`, latency, retry, initialization failures |

Ở mô hình **direct**, Cloud Audit Logs có thể hiển thị federated identity trong `authenticationInfo.principalSubject` hoặc những trường tương ứng tùy dịch vụ. Ở mô hình **impersonation**, một số logs biểu diễn GSA là principal thực thi và có thông tin delegation bổ sung. **Không mặc định mọi dịch vụ đều ghi cùng field**; cần xem log entry thật của API đang dùng.

Một bộ lọc Logs Explorer **minh họa để điều tra thất bại authorization**:

~~~text
protoPayload.status.code=7
~~~

Mã gRPC `7` thường biểu thị `PERMISSION_DENIED`; filter này không tự bao phủ mọi lỗi HTTP của mọi ứng dụng. Có thể kết hợp:

~~~text
protoPayload.serviceName="storage.googleapis.com"
protoPayload.status.code=7
~~~

Nếu không thấy log, kiểm tra **project chứa tài nguyên đích**, quyền xem Logging, loại log và việc **Data Access Audit Logs** đã được bật với phương thức đó chưa. Không nên bật toàn bộ Data Access logging vô hạn mà không cân nhắc khối lượng dữ liệu nhạy cảm và chi phí.

### Dashboard và alert đề xuất

| Metric/tín hiệu | Phát hiện |
|---|---|
| Số lỗi `UNAUTHENTICATED`/`PERMISSION_DENIED` theo workload | Sai binding hoặc migration làm mất quyền |
| STS/IAM Credentials API quota errors | Token refresh bị quá tải hoặc quota thấp |
| Metadata latency/timeout, gke-metadata-server unhealthy | Đường credential bị nghẽn |
| GKE Pod restarts và readiness failures | Ứng dụng không boot được vì thiếu credential |
| Số KSA/GSA bindings và vai trò rộng | Privilege creep, danh tính không còn sử dụng |
| Cloud Storage/Secret Manager access theo KSA/GSA | Thao tác không đúng mô hình quyền kỳ vọng |
| IAM policy changes ngoài CI/CD | Thay đổi khẩn cấp, drift hoặc truy cập trái phép |

Để dễ truy vết, ứng dụng nên log `namespace`, tên workload, mục đích API call và correlation ID **không chứa secret**. Khi review IAM, so sánh “role đã cấp” với “permission thực sự dùng”, rồi gỡ quyền thừa theo một quy trình có thể rollback.

## 19. Chi phí và quản trị vòng đời

Lợi ích lớn của Workload Identity Federation for GKE là giảm rủi ro và chi phí vận hành private keys. Tuy nhiên, **không mặc nhiên làm GKE/Pub/Sub/Storage API miễn phí** và cũng không loại bỏ mọi chi phí:

- **GKE:** cluster, nodes hoặc Pods theo Standard/Autopilot, logging, networking.
- **Google Cloud API đích:** số thao tác đọc object/secret, Pub/Sub publish, Cloud SQL connections và dữ liệu truyền.
- **IAM/STS/IAM Credentials:** quản lý quota/token exchanges, client caching và các giới hạn hiện hành; kiểm tra biểu phí riêng nếu có tính phí cho chức năng đang dùng.
- **Cloud Logging/Monitoring:** chi phí ingest, lưu giữ và metric khi thu thập nhiều event.
- **CI/CD/GitOps:** quản trị Terraform IAM bindings, Kubernetes KSA manifests và audit.

Một service Java tạo client mới mỗi request có thể gây gánh nặng token exchange không cần thiết, thậm chí làm tăng lỗi/latency. Dùng client libraries/caching hợp lý giúp hệ thống ổn định và giảm tải.

**FinOps/ownership:** đặt nhãn ứng dụng và namespace để phân bổ GKE cost, quản lý service accounts bằng owner/team, định kỳ xóa bindings không còn dùng. Không để một GSA “shared-runtime-admin” tồn tại nhiều năm với `Editor` trong nhiều project chỉ vì tiện triển khai.

Cloud Billing budget alerts giúp phát hiện chi phí bất thường nhưng **không tự thu hồi IAM permission**. IAM review, access monitoring và process thay đổi vẫn cần chạy độc lập.

## 20. Tình huống: ba dịch vụ Java trong hệ thống đơn hàng

Một doanh nghiệp chạy GKE regional cluster trong project `gke-prod`, dữ liệu nằm ở các project riêng:

~~~text
                         Google Kubernetes Engine
                         Project: gke-prod
                 Workload pool: gke-prod.svc.id.goog
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
         namespace orders   namespace payments  namespace reports
         KSA orders-api     KSA payment-worker   KSA report-reader
                 │                │                │
                 ▼                ▼                ▼
         Secret Manager       Pub/Sub topic    Cloud Storage bucket
         orders-config        payment-events     report-inputs
         Project secrets-prod Project events-prod Project data-prod
~~~

### Phân quyền ban đầu

| KSA | Cấp trực tiếp | Không cấp |
|---|---|---|
| `orders/orders-api` | `roles/secretmanager.secretAccessor` trên một secret | Quyền đọc toàn bộ Secret Manager project |
| `payments/payment-worker` | `roles/pubsub.publisher` trên topic payment-events | `roles/pubsub.admin`, quyền xóa topic |
| `reports/report-reader` | `roles/storage.objectViewer` trên một bucket | `roles/storage.admin` |

Nhóm platform bật WIF; nhóm IAM/security cấp role trên resource; các team ứng dụng gắn đúng `serviceAccountName` trong Deployment. Java code sử dụng ADC; GitOps quản lý KSA/Deployment, Terraform quản lý IAM role bindings.

### Thay đổi nghiệp vụ: payment-worker cần signed URL

Nếu một API hoặc SDK cần IAM service account để ký, nhóm Payments tạo **GSA riêng** `payment-signer@identities-prod.iam.gserviceaccount.com`, cấp đúng quyền cần thiết trên tài nguyên ký, rồi cho KSA `payments/payment-worker` được `roles/iam.workloadIdentityUser` trên GSA và thêm annotation. Các dịch vụ khác vẫn dùng direct federation.

Không chuyển cả ba service sang GSA impersonation chỉ vì một service gặp hạn chế về signed URL. Cách làm lai giữ IAM đơn giản cho phần lớn ứng dụng mà vẫn tương thích yêu cầu đặc biệt.

### Thay đổi hạ tầng: tạo cluster staging cùng project

Một team khác tạo `orders` namespace và `orders-api` KSA trùng tên trong cluster staging thuộc **cùng project `gke-prod`**. Với direct principal theo namespace/KSA, staging có thể được xem là cùng identity với production.

**Rủi ro:** staging Pod có thể đọc secret production nếu cluster mới không nằm trong ranh giới tin cậy tương đương. Hướng ưu tiên là đặt staging ở **project khác** (ví dụ `gke-staging`), tạo pool khác và chỉ cấp quyền tới tài nguyên staging. Chỉ đổi KSA name cũng có thể giảm trùng, nhưng không thay ranh giới tin cậy project-level.

### Khi phát sinh 403 hàng loạt sau node pool update

Trong một lần nâng cấp Standard node pool, ứng dụng cũ dùng node SA bị lỗi. Runbook:

1. Xác minh node pool đang `GKE_METADATA` và Pod đã gắn KSA có IAM role.
2. Xem lỗi từ metadata server hay Google Cloud API đích.
3. Nếu thiếu binding, cấp đúng role trên resource, đợi propagation và thử lại canary.
4. Nếu ứng dụng vẫn dùng JSON key/ADC sai, sửa cấu hình hoặc chuyển tạm sang pool cũ theo kế hoạch được phê duyệt.
5. Giữ metrics về lỗi người dùng, SLO, số request `401/403` và thời gian khắc phục.
6. Hoàn tất migration rồi mới thu hồi quyền rộng của node service account.

**Bài học từ tình huống:** IAM đúng người và đúng tài nguyên quan trọng hơn việc cố “khiến token tạo thành công”. WIF là cơ chế cấp credential, còn quyền hiệu lực, đường mạng, quản lý Pod và bảo mật ứng dụng quyết định hệ thống có an toàn hay không.

## 21. Checklist triển khai production

### Thiết kế danh tính và IAM

- [ ] Mỗi workload cần quyền khác nhau có namespace/KSA phù hợp, không mặc định dùng `default` KSA.
- [ ] Đã chọn direct principal khi API hỗ trợ; chỉ dùng GSA impersonation nếu có nhu cầu cụ thể.
- [ ] Với direct, principal URL sử dụng **project number/pool của GKE cluster project**.
- [ ] Với impersonation, đã có cả **WorkloadIdentityUser IAM binding** và **KSA annotation** chính xác.
- [ ] IAM roles giới hạn trên bucket/secret/topic/key/resource cụ thể, không gán `Owner/Editor` bừa bãi.
- [ ] Các cluster cùng project đã được kiểm tra **identity sameness**, ranh giới tin cậy và quyền tạo KSA.
- [ ] Có người chịu trách nhiệm thu hồi quyền và xử lý khi một KSA/GSA không còn dùng.

### GKE và ứng dụng

- [ ] Autopilot luôn có WIF; Standard cluster/node pool được bật `GKE_METADATA` đúng kế hoạch.
- [ ] Mọi Pod cần WIF khai báo đúng `serviceAccountName`.
- [ ] Standard mixed pools có selector/affinity phù hợp; Autopilot **không dùng nodeSelector metadata server**.
- [ ] Java SDK sử dụng ADC, không mount static JSON key qua Kubernetes Secret.
- [ ] Host-network Pods, service mesh và system agents được đánh giá đường credential riêng.
- [ ] Image pull identity của **node** vẫn có quyền Artifact Registry phù hợp.
- [ ] Metadata endpoint, DNS, STS `443`, Google Cloud API egress được cho phép theo NetworkPolicy/VPC.
- [ ] Ứng dụng retry token metadata startup errors có backoff và tự refresh credential.

### Vận hành và sự cố

- [ ] Đã thử truy cập resource được phép và resource không được phép từ đúng Pod/KSA.
- [ ] Có dashboard `401/403`, token failures, quota, latency và application SLO.
- [ ] Cloud Audit Logs/IAM change logs và access logs được bật ở phạm vi cần thiết.
- [ ] Migration không đổi node pool hàng loạt khi còn Pod dùng node service account.
- [ ] Có canary/rollback và quy trình xóa static keys sau chuyển đổi thành công.
- [ ] Đã xem quota STS/IAM Credentials, vùng triển khai, IAM propagation và concurrency.
- [ ] Đã rà soát chi phí API, logging và node/Pod; không giữ danh tính không còn owner.

## 22. Bài tập thực hành và câu hỏi tình huống

### Bài tập A — KSA đọc đúng một bucket

Một nhóm chạy `report-service` trong namespace `analytics` trên GKE Standard cluster thuộc project `gke-learning`; bucket `reports-private-lab` nằm ở project khác.

1. Viết lệnh kiểm tra cluster workload pool và node pool metadata mode.
2. Tạo KSA `report-reader` và Deployment gắn `serviceAccountName` này.
3. Tạo principal URL direct với project number của **gke-learning**, không dùng project number của bucket.
4. Cấp `roles/storage.objectViewer` trên **duy nhất bucket** cần đọc.
5. Test metadata token endpoint và đọc object; giải thích vì sao hai phép test khác nhau.
6. Nêu cách thu hồi quyền khi nhóm chuyển sang bucket mới mà không xóa bucket dữ liệu.

### Bài tập B — Chọn impersonation khi cần service account

Ứng dụng `invoice-api` cần tạo signed URL, còn SDK hiện tại yêu cầu IAM service account email:

1. Giải thích vì sao có thể cần GSA impersonation thay vì direct principal.
2. Viết lệnh tạo GSA ở project `identity-prod`; cấp quyền resource thật ở project `billing-prod`.
3. Viết binding `roles/iam.workloadIdentityUser` cho KSA `invoices/invoice-api`.
4. Thêm annotation `iam.gke.io/gcp-service-account` và giải thích điều gì xảy ra nếu thiếu annotation.
5. Cho hai loại 403: lỗi `GenerateAccessToken` và lỗi khi truy cập Cloud Storage; nêu bước kiểm tra riêng.

### Bài tập C — Identity sameness và ranh giới tin cậy

Hai cluster `gke-prod-a` và `gke-test-b` cùng project `team-platform` đều có namespace `orders` và KSA `orders-api`.

1. Giải thích vì sao hai workload có thể là **cùng principal** với IAM binding dựa trên namespace/name.
2. Chỉ ra nguy cơ khi admin cluster test có quyền tạo Pod mới.
3. Đề xuất ba cách giảm rủi ro; giải thích vì sao **project separation** thường mạnh nhất.
4. Phân biệt `principal://.../subject/ns/.../sa/...` và `principalSet://.../namespace/...`.
5. Nếu KSA bị xóa/tạo lại với cùng tên, principal dựa trên name và UID khác nhau ra sao?

### Bài tập D — Sự cố sau migration

Một dịch vụ Java đọc Pub/Sub bị lỗi trong vài phút sau khi node pool chuyển sang `GKE_METADATA`. Pods có `serviceAccountName` đúng nhưng application logs có cả `403` và metadata timeout:

1. Dùng lệnh nào để kiểm tra node pool, KSA và Pod scheduling?
2. Nếu lỗi đến từ `iamcredentials.googleapis.com`, IAM binding nào có thể đang thiếu?
3. Nếu metadata không phản hồi, NetworkPolicy cần mở IP/port nào trên GKE Dataplane V2?
4. Vì sao STS network egress `443` vẫn cần mở mặc dù metadata endpoint là IP nội bộ?
5. Nếu vừa cấp IAM binding mà vẫn 403, phải xét IAM propagation/token cache thế nào?
6. Nêu tiêu chí rollback có kiểm soát và biện pháp tránh phải quay lại JSON keys.

### Bài tập E — Java và hiệu năng xác thực

Một Java worker tạo mới Cloud Storage client cho **mỗi message** Pub/Sub và log toàn bộ access token khi lỗi.

1. Nêu các nguy cơ bảo mật và hiệu năng.
2. Viết cách khởi tạo client một lần theo ADC.
3. Giải thích giới hạn metadata server concurrent connections và token refresh.
4. Đề xuất metric theo dõi `403`, `429`, metadata latency và Cloud Storage operations.
5. Đề xuất cách redaction logs, IAM role review và quản lý quota project khi cần.

**Câu hỏi tổng kết:** Nếu một Pod đã lấy được federated token nhưng không đọc được `gs://orders-prod`, hãy phân biệt ít nhất bốn khả năng: (1) principal/binding sai; (2) IAM Deny/Conditions; (3) Google Cloud API không hỗ trợ direct federation cho operation đang gọi; (4) network/API path không hoạt động. Trình bày cách kiểm chứng từng khả năng trước khi quyết định đổi từ direct sang impersonation.

## Tài liệu tham khảo chính thức

- [About Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — kiến trúc, token flow, principal identifiers và identity sameness.
- [Authenticate to Google Cloud APIs from GKE workloads](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) — bật WIF trên Standard, cấp direct IAM, KSA-GSA linking và kiểm thử.
- [Troubleshoot GKE authentication issues](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/authentication) — IAM 403, NetworkPolicy, metadata timeouts, quota và node pools.
- [Best practices for hardening GKE security](https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster) — KSA isolation, IAM least privilege và guardrails.
- [IAM principal identifiers for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity#principal-identifiers) — `principal://` và `principalSet://`.
- [IAM Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) — nguyên lý federation và short-lived credentials.
- [Google Cloud Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) — thứ tự chọn credential của client libraries.
- [Cloud Storage IAM roles](https://cloud.google.com/storage/docs/access-control/iam-roles) — Object Viewer và cấp IAM tại bucket.
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control) — quyền đọc secret phiên bản.
- [Pub/Sub access control with IAM](https://cloud.google.com/pubsub/docs/access-control) — role Publisher/Subscriber theo topic/subscription.
- [IAM service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation) — impersonation và kiểm soát ủy quyền.
- [Cloud SQL connector authentication](https://cloud.google.com/sql/docs/mysql/connect-connectors) — IAM/ADC, network và database authentication.
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit) — truy vết truy cập và thay đổi IAM.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — chi phí cluster, nodes, Pods và tài nguyên phụ thuộc.
