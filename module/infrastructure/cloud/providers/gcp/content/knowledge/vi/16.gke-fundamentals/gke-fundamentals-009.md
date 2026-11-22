# Quản lý Secrets và danh tính workload trên GKE

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Kubernetes ServiceAccount (KSA)**, **Google Cloud IAM service account (IAM SA)**, **node service account**, IAM policy và Kubernetes RBAC; tránh nhầm quyền truy cập Kubernetes API với quyền gọi Google Cloud APIs.
2. Giải thích cách **Workload Identity Federation for GKE** (WIF for GKE) cấp danh tính ngắn hạn cho Pod mà không cần lưu khóa JSON service account trong container.
3. Tạo IAM binding trực tiếp cho KSA principal, hoặc liên kết KSA với IAM service account bằng impersonation khi API/ứng dụng có yêu cầu tương thích.
4. So sánh **Kubernetes Secret**, **Google Cloud Secret Manager**, **Secret Manager add-on/CSI volume** và cơ chế **SecretSync**; chọn giải pháp theo tính nhạy cảm, khả năng xoay vòng, giao diện ứng dụng và yêu cầu vận hành.
5. Triển khai ví dụ **gcloud + kubectl + YAML + Java** để Pod đọc một secret được cấp phép, kiểm tra mount và xử lý xoay vòng mà không để lộ giá trị.
6. Chẩn đoán các lỗi **403, ImagePullBackOff, FailedMount, lỗi ADC/token, secret không refresh**, đồng thời thiết kế IAM/RBAC tối thiểu, logging, kiểm toán, HA và chi phí.

## 1. Bài toán thực tế: một Pod cần bí mật và quyền truy cập cloud

Giả sử công ty triển khai hệ thống bán hàng trên **Google Kubernetes Engine (GKE)**:

- Deployment **orders-api** viết bằng Java/Spring Boot cần mật khẩu của một dịch vụ legacy, lưu trong **Secret Manager**.
- Cùng Pod cần quyền **đọc một Cloud Storage bucket**, nhưng không được xóa hay ghi đè object.
- Worker **image-processor** cần quyền đọc ảnh và ghi ảnh tối ưu vào bucket khác.
- Pipeline **Cloud Build** đẩy image vào **Artifact Registry** và triển khai một phiên bản mới lên GKE.
- Một nhóm vận hành có quyền xem Pod logs, nhưng **không được phép đọc secret values**.

Một cách làm thiếu an toàn là nhúng JSON private key hoặc DB password vào image, file deployment.yaml, ConfigMap, biến môi trường của pipeline hoặc Git. Khi đó, chỉ cần truy cập source, registry hoặc một log bị rò rỉ là bí mật có thể lộ.

Thay vào đó:

1. **Workload Identity Federation for GKE** xác nhận *Pod là workload nào* và cấp danh tính/credential ngắn hạn cho Google Cloud APIs.
2. **IAM** quyết định workload được đọc secret hoặc bucket cụ thể nào.
3. **Secret Manager** lưu giá trị nhạy cảm, quản lý phiên bản, quyền truy cập, audit và quy trình rotation.
4. **Kubernetes RBAC**, namespace, Pod security và network policies giảm nguy cơ workload khác trong cluster lấy trộm quyền hoặc secrets.
5. **Ứng dụng** vẫn phải bảo vệ giá trị đã đọc trong bộ nhớ, file, log và kết nối đến dịch vụ đích.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, đây là kiến thức nối project/IAM/VPC với Compute Engine, GKE, Cloud Run, lưu trữ và database, đồng thời phục vụ tự động hóa phát hành, bảo mật tài nguyên, theo dõi độ tin cậy và chi phí.

> **Nguyên tắc chính:** danh tính và secret là hai bài toán khác nhau. WIF trả lời “workload nào đang yêu cầu?”, IAM trả lời “workload được phép làm gì?”, còn Secret Manager giữ “giá trị bí mật”. Không cấp quyền IAM rộng chỉ để tránh lỗi secret mounting.

## 2. Những loại danh tính thường bị nhầm lẫn

### 2.1. Bảng phân biệt

| Khái niệm | Nơi tồn tại | Dùng để làm gì? | Ví dụ |
|---|---|---|---|
| **Người dùng Google Cloud** | Google Cloud IAM/Identity | Quản trị GKE và các tài nguyên cloud theo quyền IAM | developer@example.com |
| **Kubernetes ServiceAccount (KSA)** | Kubernetes API, thuộc **một namespace** | Danh tính của Pod đối với Kubernetes và WIF | namespace=shop, name=orders-ksa |
| **Kubernetes RBAC Role/RoleBinding** | Kubernetes cluster | Cho KSA/user làm thao tác với Kubernetes API | get/list Pods, không được get Secrets |
| **Google Cloud IAM service account (IAM SA)** | Google Cloud project | Danh tính workload cho Google APIs; có thể impersonate | orders-gsa@shop-dev-001.iam.gserviceaccount.com |
| **Node service account** | Compute Engine node/managed node pool | Quyền phục vụ node agent, image pull và chức năng node | gke-nodes@... |
| **WIF principal identifier** | Google Cloud IAM policy | Biểu diễn KSA/namespace/cluster trong IAM | principal://.../subject/ns/shop/sa/orders-ksa |
| **Secret Manager secret** | Google Cloud Secret Manager | Lưu bí mật và các versions | orders-db-password |
| **Kubernetes Secret** | Kubernetes API namespace | Lưu cấu hình nhạy cảm cho Pods theo cơ chế Kubernetes | db-credentials |

**KSA không phải IAM SA.** Cùng có chữ “service account”, nhưng một đối tượng thuộc cluster/namespace, đối tượng kia thuộc Google Cloud IAM. Trong các bước sau, luôn phân biệt hai loại.

### 2.2. Hai lớp phân quyền khác nhau

~~~mermaid
flowchart LR
    P["Pod orders-api<br/>serviceAccountName: orders-ksa"] --> K["Kubernetes ServiceAccount"]
    K --> R["Kubernetes RBAC<br/>Kubernetes API"]
    K --> W["Workload Identity Federation<br/>GKE metadata server"]
    W --> I["Google Cloud IAM policy"]
    I --> SM["Secret Manager"]
    I --> GCS["Cloud Storage"]
    I --> OTHER["Các Google APIs được hỗ trợ"]
~~~

Một KSA **có Kubernetes Role được phép list Pods** không tự có quyền đọc Secret Manager. Ngược lại, một KSA principal có **roles/secretmanager.secretAccessor** không tự được phép liệt kê Kubernetes Secrets trong cluster.

### 2.3. Tránh dùng KSA mặc định cho mọi Pod

Mỗi namespace có một KSA tên **default**. Nếu tất cả ứng dụng đều dùng default KSA rồi IAM grant cho principal đó, chúng có thể **chia sẻ quyền** ngoài mong muốn.

Thiết kế tốt:

~~~text
Namespace shop
  ServiceAccount orders-ksa        → chỉ đọc orders-db-password
  ServiceAccount image-worker-ksa  → đọc input bucket, ghi output bucket

Namespace analytics
  ServiceAccount reports-ksa       → chỉ đọc bucket reports
~~~

Trong Kubernetes workload manifest, luôn ghi rõ **serviceAccountName** cho những ứng dụng cần truy cập API/secret. Không gắn một GSA giàu quyền lên KSA dùng chung.

## 3. Workload Identity Federation for GKE hoạt động ra sao?

### 3.1. Truy cập Google APIs mà không lưu service account key

Khi bật WIF for GKE, Google Cloud quản lý **workload identity pool** của project có dạng:

~~~text
PROJECT_ID.svc.id.goog
~~~

Mỗi project có workload identity pool được quản lý cho GKE. GKE đăng ký cluster làm identity provider và sử dụng **GKE metadata server** trên nodes để trao đổi thông tin nhận dạng của workload lấy credential phù hợp khi gọi Google APIs.

~~~mermaid
sequenceDiagram
    participant APP as Java app trong Pod
    participant META as GKE metadata server
    participant STS as Google Cloud token services
    participant IAM as IAM policy
    participant SM as Secret Manager
    APP->>META: ADC yêu cầu credential
    META->>STS: Trao đổi xác thực workload
    STS-->>META: Credential ngắn hạn
    META-->>APP: Credential
    APP->>SM: accessSecretVersion qua TLS
    SM->>IAM: Kiểm tra principal / permission
    alt Có quyền
        IAM-->>SM: Allow
        SM-->>APP: Secret payload
    else Không có quyền
        IAM-->>SM: Deny
        SM-->>APP: PERMISSION_DENIED
    end
~~~

Sơ đồ thể hiện logic, không khẳng định từng dịch vụ nội bộ luôn gọi đồng bộ theo thứ tự minh họa. **ADC (Application Default Credentials)** và Google Cloud client libraries xử lý credential ngắn hạn; ứng dụng không cần đóng gói khóa JSON riêng.

### 3.2. Autopilot và Standard khác nhau ở đâu?

| Cụm | Trạng thái WIF | Điều kiện vận hành |
|---|---|---|
| **GKE Autopilot** | **Luôn được bật** | Không cần bật WIF thủ công, các node sử dụng cơ chế GKE quản lý |
| **GKE Standard mới** | Có thể bật khi tạo cluster | Đảm bảo cluster có workload pool và node pool dùng GKE metadata server |
| **GKE Standard hiện có** | Phải bật cluster, sau đó kiểm tra/cập nhật node pools cũ | Bật cluster **không tự đổi node pool đã tồn tại** |

Trên Standard, khi node pool sử dụng **GKE_METADATA**, ứng dụng trong Pods gọi metadata endpoint được GKE metadata server xử lý thay cho node's Compute Engine metadata server, ngoại trừ các giới hạn như **hostNetwork Pods**.

### 3.3. Principal identity của KSA có dạng nào?

Giả sử:

~~~text
Project ID       = shop-dev-001
Project number   = 123456789012
Namespace        = shop
KSA              = orders-ksa
~~~

Principal của KSA này:

~~~text
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/subject/ns/shop/sa/orders-ksa
~~~

**123456789012** là **project number**, không phải project ID. Các trường namespace/KSA phải khớp chính xác tên trong Kubernetes.

Các selectors mở rộng:

| Loại IAM principal | Phạm vi |
|---|---|
| **principal://.../subject/ns/shop/sa/orders-ksa** | Mọi Pod chạy dưới KSA có namespace/name đó trong workload pool |
| **principal://.../kubernetes.serviceaccount.uid/UID** | Một Kubernetes ServiceAccount cụ thể theo UID |
| **principalSet://.../namespace/shop** | Toàn bộ Pod trong namespace shop của pool |
| **principalSet://.../kubernetes.cluster/...** | Các Pods thuộc một cluster cụ thể khi dùng selector hỗ trợ |

Với nguyên tắc least privilege, ưu tiên **principal của KSA cụ thể**, không cấp **principalSet toàn namespace hoặc toàn cluster** trừ khi đã có yêu cầu rõ ràng.

### 3.4. Rủi ro “identity sameness” giữa clusters cùng project

Trong một project, hai GKE clusters có thể sử dụng **cùng workload identity pool**. Nếu chúng đều chứa **namespace shop và KSA orders-ksa**, IAM identifier theo tên namespace/KSA có thể được nhìn như **cùng một principal**, bất kể cluster.

Điều này đặc biệt nguy hiểm khi một cluster dev do nhiều người quản lý chung project với cluster production. Có các cách giảm rủi ro:

1. **Tách clusters có mức tin cậy khác nhau sang các projects khác nhau**.
2. Sử dụng namespace/KSA names tách biệt được quản trị nghiêm ngặt.
3. Cân nhắc identity theo **KSA UID** hoặc selectors ràng buộc cluster khi phù hợp.
4. Dùng policy kiểm soát ai được tạo namespace/KSA và ai được deploy workload chạy dưới KSA được cấp quyền.

Không mặc định **cluster name** là một phần của KSA principal string theo namespace/name. Đây là điểm kiểm tra bắt buộc với kiến trúc đa cluster.

## 4. Hai cách cho Pod gọi Google Cloud APIs

### 4.1. Cách A — Grant IAM trực tiếp cho Kubernetes ServiceAccount principal

Đây là cách được khuyến nghị khi API hỗ trợ federated principal IAM binding.

~~~text
Pod → orders-ksa → WIF principal
                 → IAM binding trên Secret Manager secret
                 → Secret Manager API
~~~

Ưu điểm:

- Không cần tạo GSA chỉ để đọc Secret Manager.
- IAM trực tiếp ràng buộc một KSA với một secret/bucket.
- Không cần quản lý long-lived service account key.
- Thuận tiện kiểm toán theo workload identity.

Hạn chế: một số APIs/client libraries hoặc use cases chưa hỗ trợ trực tiếp WIF principal; có thể cần cách B.

### 4.2. Cách B — KSA impersonate một IAM service account

~~~text
Pod → KSA → Workload Identity Federation
          → roles/iam.workloadIdentityUser trên IAM SA
          → Credential impersonation IAM SA
          → Google Cloud API
~~~

Cần **cả hai cấu hình**:

1. Trên IAM SA, grant **roles/iam.workloadIdentityUser** cho KSA theo syntax hỗ trợ.
2. Annotate KSA bằng **iam.gke.io/gcp-service-account=GSA_EMAIL**.

Đồng thời, IAM SA phải được cấp chính xác các roles trên Google resources mà workload cần. Nếu chỉ annotate KSA nhưng không grant quyền impersonation, Pod vẫn có thể nhận lỗi **403**.

**Không cần và không nên** tải JSON private key của GSA xuống Pod. Impersonation phát hành credential ngắn hạn và bảo toàn mô hình phân quyền IAM.

### 4.3. Khi nào chọn cách nào?

| Tình huống | Hướng ưu tiên |
|---|---|
| Pod đọc một secret trong Secret Manager | **IAM direct KSA principal** |
| Pod truy cập bucket Cloud Storage có IAM support | IAM direct khi use case được hỗ trợ |
| Client/Google API không hỗ trợ trực tiếp federated identity | KSA → **IAM SA impersonation** |
| Ứng dụng cũ kiểm tra identity qua GSA email | Impersonation, thử tính tương thích |
| Chỉ cần quyền truy cập Kubernetes Pods/ConfigMaps | Kubernetes RBAC, **không nhất thiết cần Google IAM** |

Hai cách không phải hai bước bắt buộc phải triển khai cùng nhau. Chọn đúng một mô hình cho từng workload và document chủ sở hữu IAM bindings.

## 5. Bí mật được lưu ở đâu? Kubernetes Secret hay Secret Manager?

### 5.1. Kubernetes Secret

Kubernetes **Secret** là API object trong một namespace, chứa dữ liệu nhạy cảm giới hạn kích thước **1 MiB mỗi Secret**.

Ví dụ:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: legacy-db
  namespace: shop
type: Opaque
stringData:
  username: training-user
  password: REPLACE_WITH_NON_REAL_VALUE
~~~

**Không commit file chứa secret thật vào Git**, dù dùng **stringData** hay **data**. Cấu trúc **data** yêu cầu base64, nhưng **base64 chỉ là encoding, không phải encryption**; ai lấy được giá trị có thể giải mã.

GKE quản lý encryption at rest mặc định cho nội dung customer, gồm Kubernetes Secrets. Nếu cần kiểm soát thêm bằng khóa do doanh nghiệp quản lý, có thể bật **application-layer secrets encryption với Cloud KMS** theo tính năng GKE. Điều này **không thay thế Kubernetes RBAC**: người có quyền đọc Secret qua Kubernetes API vẫn có thể nhận plaintext theo cơ chế API.

### 5.2. Secret Manager

**Google Cloud Secret Manager** lưu **secret** cùng nhiều **secret versions** (ví dụ 1, 2, latest), có IAM control theo secret, audit logs, lifecycle, rotation scheduling/notifications và lựa chọn location/CMEK.

| Tiêu chí | Kubernetes Secret | Secret Manager |
|---|---|---|
| Control plane | Kubernetes API | Google Cloud API |
| Định danh | namespace/name | project/locations/secret/version |
| Quyền chính | Kubernetes RBAC, admission, namespace | Google Cloud IAM và guardrails |
| Giá trị tồn tại trong cluster state | **Có** | **Không**, nếu dùng API trực tiếp/CSI mount không đồng bộ |
| Sử dụng trực tiếp | env var, secret volume, imagePullSecrets | SDK/API, CSI volume; SecretSync nếu cần K8s Secret |
| Versioning | Update Secret object, không có Secret Manager-style versions | Có version và alias/latest |
| Rotation | Cập nhật Secret; Pod/app phải nhận thay đổi | Thêm version, có thể tích hợp CSI refresh/sync/app reload |
| Phù hợp | Ứng dụng legacy, controller cần Kubernetes Secret, pull secrets | Credentials nhạy cảm, kiểm soát IAM, audit và quản lý đa dịch vụ |

Secret Manager được khuyến nghị làm nguồn quản lý bí mật tập trung cho các workload cần IAM governance. Kubernetes Secrets vẫn là phần hợp lệ của Kubernetes; điều quan trọng là **kiểm soát nơi bí mật được sao chép**.

### 5.3. Đừng nhầm ba thuật ngữ “secret”

- **Kubernetes Secret**: Kubernetes API object.
- **Secret Manager secret**: tài nguyên Google Cloud, chứa các versions.
- **SecretProviderClass**: cấu hình CSI chỉ định **Secret Manager versions nào được mount**; nó không tự chứa plaintext secret.

Trong bài thực hành, dùng **Secret Manager add-on** để mount secret trực tiếp vào Pod dưới dạng file. Không tạo Kubernetes Secret trung gian nếu ứng dụng đọc file được.

## 6. Các phương thức cung cấp secret cho Pod

| Phương thức | Ưu điểm | Giới hạn/rủi ro | Khi nên dùng |
|---|---|---|---|
| **Kubernetes Secret → env** | Ứng dụng nhận biến môi trường dễ dàng | Secret nằm trong cluster API; env **không tự cập nhật** trong container đang chạy | Legacy ứng dụng chỉ hiểu env |
| **Kubernetes Secret → volume** | File được cập nhật sau propagation delay | Vẫn là K8s Secret; **subPath không tự cập nhật** | Controller/ứng dụng cần file semantics |
| **Secret Manager SDK/API trực tiếp** | Không sao chép vào K8s; IAM rõ; app kiểm soát cache/retry | Cần code và xử lý API latency/quota | Ứng dụng Java có thể dùng SDK |
| **GKE Secret Manager add-on (CSI)** | File được mount trực tiếp trong Pod, không tạo K8s Secret; rotation tùy chọn | Phụ thuộc CSI, node/version hỗ trợ; app phải reload | Ứng dụng đọc file, muốn vận hành managed |
| **GKE SecretSync** | Đồng bộ từ Secret Manager sang K8s Secret, dùng env/volume chuẩn | Bí mật **được sao chép vào cluster state** | Legacy apps/controllers bắt buộc dùng K8s Secret |

**Định hướng chọn:** dùng **SDK hoặc CSI add-on** khi có thể. Chỉ đồng bộ thành Kubernetes Secret khi ứng dụng thực sự cần API object đó. Đây cũng là khuyến nghị của tài liệu GKE Secret Manager integration.

## 7. Kiểm soát Kubernetes Secrets và RBAC

### 7.1. Base64 và encryption

Trong Kubernetes manifest, **data** chứa chuỗi base64; **stringData** cho plaintext rồi API server chuyển đổi thành data. Cả hai đều có thể làm lộ secret trong manifest, command history, Git hoặc CI logs.

~~~bash
# Chỉ xem metadata, không in secret payload ra terminal/log
kubectl get secrets -n shop
kubectl describe secret legacy-db -n shop
~~~

Không đưa lệnh **kubectl get secret ... -o yaml** hoặc base64 decode vào runbook logging chung, vì sẽ tiết lộ nội dung cho người đọc terminal/session history. **kubectl describe secret** thường chỉ hiện key names và sizes; vẫn cần kiểm tra log tooling đang thu thập.

### 7.2. Quyền truy cập Kubernetes Secrets

Một **Role** ví dụ cấp quyền **get toàn bộ Kubernetes Secret**, bao gồm cả giá trị nhạy cảm, qua Kubernetes API (không phải chỉ metadata). Chỉ cấp quyền này khi ứng dụng thật sự phải gọi Kubernetes API đọc Secret:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: legacy-secret-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["legacy-db"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: legacy-secret-reader-binding
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: legacy-reader-ksa
    namespace: shop
roleRef:
  kind: Role
  name: legacy-secret-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Role này chỉ ảnh hưởng **Kubernetes API**. Nó không cấp quyền Secret Manager. Đồng thời, RoleBinding riêng không phải biện pháp cách ly hoàn chỉnh nếu một user có quyền **tạo Pod trong namespace**, bởi họ có thể khiến Pod đọc Secrets được mount theo quyền Pod đã được cấp.

### 7.3. Rủi ro privilege escalation qua Pod creation

Ngay cả khi một developer không có verb **get** trên Secrets, quyền **create Pods/Deployments** trong namespace có thể cho phép họ tạo một Pod mount Secret cùng namespace, từ đó lấy được giá trị gián tiếp.

Vì vậy:

1. Tách namespace theo mức tin cậy; không để người không đáng tin có quyền deploy vào namespace chứa secret production.
2. Giới hạn ai được tạo/chỉnh **Pod, Deployment, Job, DaemonSet**, nhất là serviceAccountName.
3. Áp dụng **Pod Security Admission**, policy/admission controls, network policies theo kiến trúc.
4. Không chia sẻ node/cluster giữa các tenant không tin nhau nếu isolation requirements vượt khả năng mô hình.
5. Kiểm soát quyền **exec vào container**, vì có thể đọc filesystem hoặc memory/env của tiến trình.

### 7.4. Secret volume và env cập nhật khác nhau

Ví dụ Pod dùng Kubernetes Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: legacy-web
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels: {app: legacy-web}
  template:
    metadata:
      labels: {app: legacy-web}
    spec:
      containers:
        - name: web
          image: REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
          env:
            - name: LEGACY_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: legacy-db
                  key: password
          volumeMounts:
            - name: db-files
              mountPath: /etc/legacy-db
              readOnly: true
      volumes:
        - name: db-files
          secret:
            secretName: legacy-db
~~~

Ở đây:

- **LEGACY_PASSWORD** lấy giá trị một lần khi container khởi động; cập nhật Secret **không tự cập nhật env** trong container đang chạy.
- **Secret volume** thường được kubelet cập nhật sau khoảng trễ đồng bộ/cache, **trừ khi mount qua subPath**.
- Ứng dụng có thể vẫn giữ mật khẩu cũ trong memory/connection pool dù file đã đổi. Cần reload logic hoặc rolling restart khi phù hợp.

Với production, không nên đồng thời đưa cùng bí mật vào cả env và volume nếu chỉ một kênh là đủ. Ví dụ minh họa cả hai để so sánh hành vi, không phải yêu cầu kiến trúc.

## 8. Thực hành A — Chuẩn bị GKE Workload Identity Federation

### 8.1. Các giả định của bài thực hành

| Thuộc tính | Giá trị minh họa |
|---|---|
| GKE/Secret Manager project | **shop-dev-001** |
| Project number giả định | **123456789012** |
| Cluster Standard hoặc Autopilot | **shop-gke** |
| Region | **asia-southeast1** |
| Kubernetes namespace | **shop** |
| Kubernetes ServiceAccount | **orders-ksa** |
| Secret Manager secret | **orders-db-password** |
| Workload image thử nghiệm | **busybox:1.36** (thay bằng image đã duyệt nếu môi trường yêu cầu) |

**Đây là lab chưa được triển khai**. Project number, domain, IP, tên cluster/secret chỉ để giải thích. Việc tạo cluster, bật add-on, secret, log và chạy Pods có thể phát sinh chi phí. Chỉ thực hiện trên project được ủy quyền.

### 8.2. Kiểm tra project, cluster và IAM

~~~bash
gcloud config get-value project
gcloud auth list
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"

gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(name,location,workloadIdentityConfig,nodePools)"
~~~

Thay **123456789012** trong các lệnh IAM bên dưới bằng **projectNumber thật**. Trên Autopilot, WIF for GKE đã bật; trên Standard cần đảm bảo cả cluster và node pools liên quan dùng GKE metadata server.

### 8.3. Bật WIF trên cluster Standard đã tồn tại nếu chưa bật

~~~bash
# Có tác động tới cluster; cần quyền quản trị và kế hoạch thay đổi.
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --workload-pool=shop-dev-001.svc.id.goog
~~~

Lệnh chỉ minh họa **Standard**. Bật ở cluster không tự cập nhật mọi node pool cũ.

### 8.4. Kiểm tra node pool Standard

~~~bash
gcloud container node-pools list \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1

gcloud container node-pools describe NODE_POOL \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(config.workloadMetadataConfig)"
~~~

Nếu một node pool cũ chưa dùng GKE metadata server, có thể cần update theo quy trình được phê duyệt:

~~~bash
gcloud container node-pools update NODE_POOL \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --workload-metadata=GKE_METADATA
~~~

Cập nhật node pool có thể khiến Pods được thay thế hoặc chuyển nơi chạy; hãy chọn cách rollout phù hợp với SLO. Autopilot không cần bước này và không nhận nodeSelector dùng để chọn node pool WIF như Standard.

### 8.5. Lấy kubeconfig và tạo namespace/KSA

~~~bash
gcloud container clusters get-credentials shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1

kubectl config current-context
kubectl create namespace shop
kubectl create serviceaccount orders-ksa -n shop
kubectl get serviceaccount orders-ksa -n shop -o yaml
~~~

Trước khi chạy, kiểm tra namespace/KSA chưa tồn tại hoặc áp dụng idempotent manifest tương đương. **get-credentials** đổi kubeconfig context đang dùng; vì vậy phải xác nhận **đúng cluster/namespace** trước khi deploy.

### 8.6. KSA tự nó chưa có quyền gì ở Google Cloud

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-ksa
  namespace: shop
~~~

Tạo KSA thành công không tạo quyền Secret Manager, Cloud Storage hay Cloud SQL. Bước tiếp theo là **IAM binding ở chính tài nguyên đích**.

## 9. Thực hành B — IAM trực tiếp: KSA chỉ được đọc một Secret Manager secret

### 9.1. Chuẩn bị secret

Trước tiên tạo một secret phục vụ lab. **Không đưa giá trị thật vào câu lệnh hoặc Git**. Tùy quy trình, hãy sử dụng công cụ nhập bí mật bảo mật được phê duyệt; dòng dưới chỉ tạo container secret rỗng, không tạo version chứa password:

~~~bash
gcloud services enable secretmanager.googleapis.com \
  --project=shop-dev-001

gcloud secrets create orders-db-password \
  --project=shop-dev-001 \
  --replication-policy=automatic
~~~

Tạo một secret version với **nội dung lab không nhạy cảm** để thực hành (một file đã chuẩn bị an toàn tên **lab-secret.txt**):

~~~bash
gcloud secrets versions add orders-db-password \
  --project=shop-dev-001 \
  --data-file=./lab-secret.txt

gcloud secrets versions list orders-db-password \
  --project=shop-dev-001
~~~

Trong production, file đầu vào phải được tạo bằng quy trình an toàn, hạn chế quyền đọc, không đưa vào VCS; sau khi xác nhận secret được lưu, xử lý/xóa bản sao plaintext theo quy định. Không đọc secret ra terminal để chứng minh thành công.

### 9.2. Grant secretAccessor cho đúng KSA principal

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/subject/ns/shop/sa/orders-ksa" \
  --role="roles/secretmanager.secretAccessor"
~~~

Điểm quan trọng:

- IAM binding cấp quyền trên **một secret**, không phải toàn project.
- **roles/secretmanager.secretAccessor** cho phép truy cập payload secret versions trong phạm vi secret được cấp, không cấp quyền tạo/xóa secret hoặc đổi IAM.
- Nếu cluster nằm ở project khác với secret, principal string phải dùng **project number/ID của cluster identity pool**, còn **--project** chỉ project chứa secret.
- Nếu có **IAM Deny, VPC Service Controls, organization policy hoặc network policy** khác, role này chưa bảo đảm request thành công.

### 9.3. Readback IAM mà không đọc secret value

~~~bash
gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001

kubectl get serviceaccount orders-ksa -n shop
~~~

Xác nhận policy chứa chính xác một **principal://.../subject/ns/shop/sa/orders-ksa**, không có wildcard principalSet ngoài ý muốn. Không cấp **roles/owner** hoặc **roles/secretmanager.admin** cho một application chỉ đọc bí mật.

### 9.4. Test âm tính

Tạo KSA thứ hai **unprivileged-ksa** trong cùng namespace nhưng **không grant IAM**. Một Pod dùng KSA này phải bị **PERMISSION_DENIED** khi gọi Secret Manager. Nếu vẫn thành công, hãy kiểm tra:

- KSA có được IAM grant qua role cấp project/ancestor không?
- Ứng dụng có dùng JSON service account key hoặc ADC file khác thay vì WIF?
- Có GSA impersonation hoặc principalSet rộng không?
- Các cluster dev/prod có trùng namespace/KSA identifier trong cùng identity pool không?

**Một phép thử chỉ kiểm tra đường thành công chưa đủ** để chứng minh chính sách least privilege.

## 10. Thực hành C — Dùng Secret Manager managed add-on (CSI volume)

### 10.1. Điều kiện phiên bản và giới hạn

**GKE Secret Manager add-on** là thành phần được Google Cloud quản lý, dựa trên cơ chế **Secrets Store CSI Driver** nhưng dùng provider **gke** và CSI driver:

~~~text
secrets-store-gke.csi.k8s.io
~~~

Các điều kiện từ tài liệu chính thức:

| Điều kiện | Giá trị tối thiểu / yêu cầu |
|---|---|
| GKE version dùng add-on | **1.27.14-gke.1042001** hoặc mới hơn |
| GKE version dùng automatic rotation của add-on | **1.32.2-gke.1059000** hoặc mới hơn |
| OS node | **Container-Optimized OS / Ubuntu Linux** |
| GKE modes | **Autopilot và Standard** |
| Authentication | **Workload Identity Federation for GKE** |
| Windows Server nodes | **Không được hỗ trợ** với add-on này |
| CSI driver name | **secrets-store-gke.csi.k8s.io** |
| SecretProviderClass provider | **gke** |
| Rotation default nếu bật | **120 giây**, tối thiểu **60 giây** |

**Đừng nhầm driver managed** với open-source driver **secrets-store.csi.k8s.io** và provider **gcp**. Hai phiên bản có thể cùng tồn tại khi migration nhưng dùng manifests khác nhau.

### 10.2. Bật add-on và rotation trên cluster đủ điều kiện

~~~bash
# Thao tác thay đổi cấu hình cluster (lab được phép).
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-manager \
  --enable-secret-manager-rotation
~~~

Với phiên bản GKE đủ điều kiện, có thể chỉ định interval:

~~~bash
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-manager \
  --enable-secret-manager-rotation \
  --secret-manager-rotation-interval=300s
~~~

Các flags rotation không hoạt động trên phiên bản quá cũ. **Không bật/tắt cluster feature ở production chỉ để thử**, vì thay đổi có thể ảnh hưởng workload mount secret đang chạy.

Kiểm tra cấu hình:

~~~bash
gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(addonsConfig.secretManagerConfig,workloadIdentityConfig)"
~~~

### 10.3. SecretProviderClass chỉ định phiên bản cần mount

Lưu thành **orders-secret-provider.yaml** (chỉ là tên file minh họa; trong công việc worker này không tạo file thực hành đó):

~~~yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: orders-secret-provider
  namespace: shop
spec:
  provider: gke
  parameters:
    secrets: |
      - resourceName: "projects/shop-dev-001/secrets/orders-db-password/versions/latest"
        path: "db-password"
~~~

Giải thích:

- **SecretProviderClass** chứa **tên tài nguyên**, không chứa plaintext password.
- **versions/latest** giúp chọn phiên bản mới nhất khi mount/refresh theo cơ chế của add-on; nếu pin **versions/1**, đổi version 2 sẽ **không tự** làm config chuyển sang version 2.
- **path** là tên file được tạo trong volume, ở ví dụ là **db-password**.
- Với **regional Secret Manager secret**, resource path phải có **/locations/REGION/** theo định dạng region-specific; đừng dùng cú pháp global nếu secret là regional.

~~~bash
kubectl apply -f orders-secret-provider.yaml
kubectl get secretproviderclass -n shop
~~~

### 10.4. Pod dùng KSA và CSI volume

Manifest **orders-secret-test.yaml**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-secret-test
  namespace: shop
spec:
  serviceAccountName: orders-ksa
  containers:
    - name: test
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          if test -s /var/secrets/db-password; then
            echo "Secret mounted successfully (value hidden)"
          else
            echo "Secret file missing or empty" >&2
            exit 1
          fi
          sleep 3600
      volumeMounts:
        - name: orders-password
          mountPath: /var/secrets
          readOnly: true
  volumes:
    - name: orders-password
      csi:
        driver: secrets-store-gke.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: orders-secret-provider
~~~

Trên **GKE Standard**, nếu cluster có hỗn hợp node pools, thêm vào **spec** của Pod:

~~~yaml
nodeSelector:
  iam.gke.io/gke-metadata-server-enabled: "true"
~~~

**Không thêm nodeSelector này trong Autopilot**: hệ thống quản lý nodes đã bật WIF và có thể từ chối selector đó.

Chạy:

~~~bash
kubectl apply -f orders-secret-test.yaml
kubectl get pod orders-secret-test -n shop
kubectl describe pod orders-secret-test -n shop
kubectl logs orders-secret-test -n shop
~~~

Lệnh log chỉ in thông báo thành công/thất bại, **không in password**. Đây là điểm cố ý để tránh lộ secret qua terminal, CI logs hoặc hệ thống giám sát.

### 10.5. Vì sao cần đúng namespace?

**Pod, KSA và SecretProviderClass** trong ví dụ đều ở namespace **shop**. IAM principal xác định **shop/orders-ksa**. Nếu deploy Pod vào **default** namespace hoặc chuyển serviceAccountName sang KSA khác, mount có thể thất bại do quyền WIF không còn khớp.

### 10.6. Kiểm thử phiên bản mới và rotation

1. Tạo secret version mới qua quy trình bảo mật, không đưa nội dung vào log.
2. Giữ SecretProviderClass dùng **versions/latest**.
3. Với rotation enabled và GKE đủ version, add-on kiểm tra định kỳ (default 120 giây) và cập nhật **file đã mount** mà không cần restart Pod.
4. Ứng dụng phải **đọc lại file hoặc reload credentials/connection pool**; một Java app đọc mật khẩu đúng một lần lúc startup vẫn có thể giữ giá trị cũ.
5. Kiểm tra thay đổi bằng **version ID, checksum test an toàn hoặc hành vi kết nối**, không in plaintext secret.

**Quan trọng:** cập nhật mounted file **không đồng nghĩa** kết nối database hiện hữu tự xác thực lại hoặc Spring properties tự được refresh. Cần thiết kế vòng đời credentials trong ứng dụng.

## 11. Thực hành D — Dùng Google Cloud Java client để đọc Secret Manager trực tiếp

Ứng dụng Java cũng có thể dùng API Secret Manager trực tiếp, không cần CSI. Ưu điểm là app kiểm soát lúc fetch, retry, cache, version pinning và telemetry.

### 11.1. Quy trình

1. Pod chạy bằng **orders-ksa** và WIF đã hoạt động.
2. KSA principal có quyền **secretmanager.versions.access** qua **roles/secretmanager.secretAccessor** trên secret.
3. Java client dùng **Application Default Credentials**, không cần file JSON service account key.
4. Ứng dụng lấy version được cấu hình, dùng giá trị trong memory, tránh log và xóa/ghi đè buffer khi có thể.

### 11.2. Ví dụ Java

Thêm dependency chính thức **google-cloud-secretmanager** vào Maven/Gradle BOM theo version do tổ chức kiểm duyệt. Code minh họa:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DbSecretLoader {
    private DbSecretLoader() {}

    public static String readPassword(String projectId, String secretId)
            throws Exception {
        SecretVersionName name =
            SecretVersionName.of(projectId, secretId, "latest");

        // Client library tự tìm Application Default Credentials.
        try (SecretManagerServiceClient client =
                SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                client.accessSecretVersion(name);
            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

Ví dụ này trả **String** vì dễ minh họa; Java String là immutable và không thể chắc chắn xóa dữ liệu khỏi heap ngay. Với thông tin cực kỳ nhạy cảm, cân nhắc API dữ liệu dạng bytes và quản lý vòng đời bộ nhớ, giảm thời gian giữ bí mật, không lưu trong singleton hoặc cache quá dài.

**Không dùng trong production theo cách gọi API mỗi request HTTP**: sẽ tăng latency, quota, chi phí và tạo dependency trực tiếp với Secret Manager khi upstream có sự cố. Thiết kế cache/reload có thời hạn, retry/backoff và xử lý lỗi có kiểm soát.

### 11.3. Secret Manager và Spring Boot

Nếu ứng dụng cần cấu hình database:

- Với **CSI volume**, đọc **/var/secrets/db-password** từ file bằng thư viện/config loader tương thích; nếu muốn rotation, cập nhật HikariCP pool/credentials theo một quy trình reload có kiểm soát.
- Với **API trực tiếp**, lấy secret khi startup hoặc một service credential provider; định kỳ reload nếu dùng **latest**, có circuit breaker và xử lý lỗi.
- Không log **spring.datasource.password**, **JDBC URL chứa password** hoặc env dump.
- Có thể ưu tiên **Cloud SQL IAM database authentication**, Cloud SQL connectors/proxy hoặc sản phẩm quản lý danh tính thay mật khẩu tĩnh khi hỗ trợ; WIF và DB authentication là hai lớp khác nhau.

**Không giả định:** chỉ cần WIF thì Java tự có quyền đăng nhập PostgreSQL. IAM cấp quyền gọi Google Cloud APIs; database có thể vẫn yêu cầu phương thức xác thực riêng.

## 12. Phương án thay thế — KSA impersonate IAM service account

Nếu API client không hỗ trợ direct KSA principal hoặc yêu cầu danh tính GSA, dùng cách liên kết.

### 12.1. Tạo IAM SA chỉ dành cho orders-api

~~~bash
gcloud iam service-accounts create orders-gsa \
  --project=shop-dev-001 \
  --display-name="GKE orders application"
~~~

GSA email sẽ là:

~~~text
orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

### 12.2. Cấp quyền cho GSA trên secret

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-gsa@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
~~~

### 12.3. Cho KSA impersonate GSA

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-gsa@shop-dev-001.iam.gserviceaccount.com \
  --project=shop-dev-001 \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:shop-dev-001.svc.id.goog[shop/orders-ksa]"
~~~

### 12.4. Annotate KSA

~~~bash
kubectl annotate serviceaccount orders-ksa \
  --namespace=shop \
  iam.gke.io/gcp-service-account=orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

**Cần cả IAM binding và annotation.** Nếu là lab đang thử **direct principal mode**, tránh giữ đồng thời nhiều grants không cần thiết; tài liệu rõ workload đang dùng mode nào, đánh giá và thu hồi role dư.

### 12.5. Những lỗi thường thấy

- Sai format member; đây là syntax **serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA]** dành cho impersonation, **khác** full **principal://** syntax dùng direct IAM.
- GSA ở project khác với cluster, dùng sai GSA email/project trong binding.
- KSA không có annotation hoặc Pod dùng KSA khác.
- GSA được phép impersonate nhưng chưa có role trên Secret Manager secret.
- Pod ở node pool Standard chưa bật GKE metadata server.
- Client đặt biến **GOOGLE_APPLICATION_CREDENTIALS** trỏ tới file key cũ không tồn tại; ADC bỏ qua WIF path dự kiến.

**Đối với apps cần identity email format**, có thể dùng annotation **iam.gke.io/return-principal-id-as-email: "true"** theo tài liệu, nhưng cần hiểu endpoint tương thích và không dùng nó để thay thế IAM grants.

## 13. SecretSync — Khi ứng dụng chỉ biết Kubernetes Secret API

### 13.1. Tại sao không phải ứng dụng nào cũng dùng CSI file?

Một số chart Helm, controllers và ứng dụng legacy bắt buộc đọc **Kubernetes Secret** theo tên, qua:

- **env.valueFrom.secretKeyRef**.
- **volume.secret.secretName**.
- Custom resources tham chiếu **secretName**.

Nếu ứng dụng không hỗ trợ đọc file CSI hoặc SDK, **Secret Manager integrated secret synchronization** trên GKE có thể tạo/cập nhật Kubernetes Secret từ nguồn Secret Manager.

**Cần hiểu đánh đổi:** bí mật được **sao chép vào Kubernetes API/cluster state**, nên các quyền RBAC, encryption, namespace isolation và rủi ro Pod creation đã nêu lại trở nên quan trọng. Với ứng dụng đọc file được, tài liệu Google Cloud ưu tiên **Secret Manager add-on** hơn SecretSync.

### 13.2. Điều kiện và flags

Tính năng SecretSync tích hợp trong GKE yêu cầu:

| Yêu cầu | Chi tiết |
|---|---|
| GKE version | **1.33 hoặc mới hơn** theo tài liệu hiện hành |
| Cluster mode | Autopilot và Standard |
| WIF for GKE | **Bắt buộc** |
| Cluster flag | **--enable-secret-sync** |
| Rotation flag | **--enable-secret-sync-rotation**; mặc định 120 giây, tối thiểu 60 giây |
| K8s resources | **SecretProviderClass** và **SecretSync**, cùng KSA được cấp IAM |

Ví dụ trên cluster đủ điều kiện:

~~~bash
# Có tác động đến cluster; chỉ chạy sau khi kiểm tra version và quyền.
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-sync \
  --enable-secret-sync-rotation
~~~

**SecretSync khác CSI add-on**: bật **--enable-secret-manager** cho CSI mount không đồng nghĩa tự bật secret synchronization. Cả hai có thể dùng SecretProviderClass nhưng khác cách tiêu thụ và nơi bí mật được lưu.

### 13.3. Ví dụ SecretSync resource

Giả sử SecretProviderClass **orders-secret-provider** ở phần 10 đã tồn tại trong namespace **shop**. Một resource **SecretSync** có thể tạo một Kubernetes Secret **orders-legacy**:

~~~yaml
apiVersion: secret-sync.gke.io/v1
kind: SecretSync
metadata:
  name: orders-legacy
  namespace: shop
spec:
  serviceAccountName: orders-ksa
  secretProviderClassName: orders-secret-provider
  secretObject:
    type: Opaque
    data:
      - sourcePath: db-password
        targetKey: password
~~~

Ứng dụng legacy sau đó dùng:

~~~yaml
env:
  - name: LEGACY_DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-legacy
        key: password
~~~

**Khi SecretSync rotation cập nhật Kubernetes Secret, env của container hiện tại vẫn không tự đổi.** Phải có quy trình restart/reload. Mount Kubernetes Secret dưới dạng volume có thể nhận cập nhật sau propagation delay nếu không dùng subPath, nhưng ứng dụng vẫn phải đọc lại file.

### 13.4. Dừng đồng bộ không xóa secret đã được sao chép

Nếu disable SecretSync ở cluster, các Kubernetes Secrets đã tạo **không tự bị xóa**. Cần có quy trình cleanup riêng khi kết thúc migration để tránh bản sao secret tồn tại không còn được quản lý. Đừng xóa SecretSync hoặc Kubernetes Secret đang được workload dùng mà chưa có thay thế và xác nhận readiness.

## 14. Rotation: xoay vòng bí mật không chỉ là tạo một version mới

### 14.1. Thế nào là rotation thành công?

Một hệ thống xác thực bằng mật khẩu có ít nhất ba state:

1. **Secret Manager** lưu secret version mới.
2. **Pod/ứng dụng** đọc version mới.
3. **Dịch vụ đích** (database, API bên thứ ba) chấp nhận credential mới và không còn phụ thuộc credential cũ.

Nếu chỉ làm bước (1), ứng dụng có thể vẫn đang giữ password cũ trong env, memory hoặc connection pool. Nếu đổi password ở database trước khi Pod cập nhật, traffic có thể bị lỗi ngay.

### 14.2. Khuyến nghị dùng two-credential overlap khi dịch vụ hỗ trợ

~~~mermaid
flowchart LR
    A["Credential cũ hoạt động"] --> B["Tạo/cho phép credential mới tại đích"]
    B --> C["Tạo Secret Manager version mới"]
    C --> D["Canary/rollout hoặc CSI refresh"]
    D --> E["Kiểm thử app dùng credential mới"]
    E --> F["Thu hồi credential cũ"]
    F --> G["Audit + cleanup version cũ theo policy"]
~~~

Với dịch vụ hỗ trợ **hai khóa hoặc hai tài khoản cùng hiệu lực**, cách overlap giúp giảm gián đoạn. Nếu database chỉ có một password cho account, cần chiến lược change window, retry, drain, rollout đồng bộ và rollback.

### 14.3. Pin version hay dùng latest?

| Chọn version | Ưu điểm | Nhược điểm |
|---|---|---|
| **versions/5** (pin) | Triển khai tái lập, dễ rollback version cụ thể | Phải cập nhật manifest/config khi rotate |
| **versions/latest** | Có thể tự nhận version mới qua CSI rotation/SDK refresh | Rủi ro thay đổi bất ngờ; cần app reload và test |
| **Version alias được quản lý** nếu API hỗ trợ | Có thể chuyển alias sang version được duyệt theo quy trình | Thêm trách nhiệm quản lý alias, không phải mọi integration nhận alias như nhau |

Với production, tổ chức nên lựa chọn theo quy trình release; không phải mọi secret đều phù hợp với **latest**. Ví dụ credential database cần cả ứng dụng và đích sẵn sàng, trong khi certificate/CA có thể cần một giai đoạn tin cậy song song.

### 14.4. Rotation không phải quyền đọc plaintext của người vận hành

Người triển khai rotation pipeline có thể cần quyền tạo Secret Manager version, còn runtime chỉ cần **secretAccessor**. Tách hai principal và có xét duyệt:

- **Runtime KSA**: đọc secret đã phát hành.
- **Rotation service account**: thêm version mới, có quyền update credential tại hệ thống đích theo phạm vi.
- **Security/platform admin**: quản trị IAM, policy, audit, lifecycle.

Không cấp toàn bộ quyền **Secret Manager Admin** cho ứng dụng Java chỉ vì nó phải đọc secret khi chạy.

### 14.5. Thu hồi và tiêu hủy versions

Khi nghi ngờ lộ secret:

1. Thu hồi ở **dịch vụ đích** (đổi database password, revoke API key).
2. Ngăn tiếp tục cấp credential cũ qua IAM hoặc remove references.
3. Phát hành version mới và rollout/reload.
4. Kiểm tra workload còn dùng version cũ không, qua telemetry/an toàn.
5. Cân nhắc **disable** version cũ để thử tác động trước khi **destroy** vĩnh viễn theo quy trình.

Theo best practices của Secret Manager, nên **disable trước khi destroy** để có cơ hội phát hiện dependency còn dùng. Việc disable/destroy secret version không thu hồi ngay một session/token đã được hệ thống đích cấp từ trước; cần thu hồi ở hệ thống đích.

## 15. Security hardening cho danh tính workload và Secrets

### 15.1. Ranh giới bảo mật nhiều lớp

~~~mermaid
flowchart TD
    U["Developer / CI / Admin"] --> AUTH["IAM + cluster authentication"]
    AUTH --> RBAC["Kubernetes RBAC / admission policies"]
    RBAC --> POD["Pod với KSA cụ thể"]
    POD --> WIF["WIF for GKE / GKE metadata server"]
    WIF --> IAM["Google Cloud IAM trên secret/bucket"]
    IAM --> SM["Secret Manager / Google API"]
    POD --> NET["NetworkPolicies, Pod security, TLS"]
    SM --> AUD["Audit/monitoring"]
    NET --> AUD
~~~

### 15.2. Checklist hardening

| Lớp | Việc nên làm | Rủi ro nếu bỏ qua |
|---|---|---|
| **Cluster/project isolation** | Tách project/cluster giữa prod và môi trường không tin cậy | Trùng KSA principal identity giữa clusters |
| **KSA** | KSA riêng theo workload và namespace | Một quyền IAM vô tình dùng chung cho nhiều apps |
| **Google IAM** | Grant ở tài nguyên cụ thể, ví dụ một secret | Lộ một Pod có thể đọc nhiều secrets |
| **Kubernetes RBAC** | Hạn chế get/list/watch Secrets, create Pod, exec | Exfiltration từ Kubernetes API/Pod |
| **Admission/Pod Security** | Chặn privileged/hostPath nguy hiểm, giới hạn hostNetwork | Truy cập node metadata hoặc secrets ngoài phạm vi |
| **Container runtime** | Không chạy root khi không cần, read-only root FS khi phù hợp | Attacker ghi hoặc trích xuất dữ liệu dễ hơn |
| **Secret delivery** | Ưu tiên SDK/CSI; ít bản sao plaintext | Secret trong manifest, backup, env dumps |
| **Encryption** | GKE default encryption, ứng dụng cần thì Cloud KMS encryption | Thiếu kiểm soát key/đánh giá dữ liệu |
| **Network** | NetworkPolicy, egress/TLS và private endpoints theo kiến trúc | Pod gọi upstream tùy ý hoặc lộ secret qua network |
| **Logging** | Audit quyền và lỗi, **không log giá trị** | Secret lộ qua log aggregator |
| **Supply chain** | Image pin digest, scan, policy deployment | Image độc hại truy cập token/secret mount |

### 15.3. Rủi ro privileged, hostNetwork và node identity

Workload chạy **hostNetwork: true** có giới hạn riêng: các Pods đó **không dùng WIF for GKE theo cách thông thường**, có thể đi đến metadata path khác. Quyền node service account và chính sách node network vì thế vẫn là một phần của security threat model.

Container được chạy **privileged**, mount host filesystem hoặc có quyền rộng trên node cũng có thể vượt qua kỳ vọng isolation giữa Pods. WIF là cơ chế danh tính, **không phải sandbox bảo vệ tuyệt đối khi node bị chiếm quyền**.

### 15.4. Không đưa secret vào places khó thu hồi

Tránh:

- Container image layer, Dockerfile **ENV/ARG** chứa plaintext.
- Kubernetes ConfigMap, GitOps plain YAML, Helm values không được bảo vệ.
- Lệnh CLI có password thật trong process args/history.
- Kubernetes Secret **data base64** được coi là mã hóa.
- Java exception/stack trace, HTTP response debug, Spring actuator environment endpoints.
- Logs của CI/CD, GitHub Actions, hệ thống chat/ticket.
- Crash dumps, heap dumps, debug shells không giới hạn.

Nếu cần GitOps, dùng phương án **external secret reference** hoặc hệ thống secret encryption được quản lý phù hợp. Không đặt ciphertext tự làm là đủ nếu key giải mã vẫn được commit cùng repository.

### 15.5. Bảo vệ đường image pull khác với quyền của Pod

**ImagePullBackOff** có thể xảy ra vì identity thực hiện pull image không có quyền Artifact Registry Reader; đây **không nhất thiết** là thiếu role của **orders-ksa**.

Trên GKE, phải kiểm tra node service account/managed service agent hoặc identity có trách nhiệm pull theo phiên bản/mô hình triển khai. Không tự grant **roles/artifactregistry.admin** cho orders-ksa chỉ vì Pod không khởi động được.

### 15.6. Chính sách service account token trong Pod

Kubernetes có **projected service account tokens** để xác thực với Kubernetes API, có thời hạn và audience phù hợp. Với Pods **không cần Kubernetes API**, có thể xem xét **automountServiceAccountToken: false** để giảm bề mặt rủi ro.

Nhưng với Pods dùng **Workload Identity Federation**, việc credential projection/metadata server phải được kiểm tra theo GKE. **Không tắt mount token một cách máy móc** rồi kết luận WIF sẽ tiếp tục hoạt động. Test workload identity thực sau mọi thay đổi.

## 16. Audit logging, bảo mật và hiệu năng vận hành

### 16.1. Quan sát ba nguồn riêng

| Nguồn | Dùng để biết | Gợi ý kiểm tra |
|---|---|---|
| **Kubernetes Events** | CSI mount lỗi, scheduling, SecretSync/Pod lỗi | kubectl describe pod, kubectl get events |
| **Kubernetes API audit logs** | Ai tạo/chỉnh KSA, Secret, RoleBinding, Pod | Cloud Logging audit của GKE theo cấu hình |
| **Secret Manager audit logs** | Access versions, IAM modifications và lỗi quyền | Cloud Audit Logs, Data Access logging theo policy |
| **IAM policy / Policy Troubleshooter** | Vì sao principal được cấp hoặc bị chặn | IAM inheritance, deny, principal string |
| **Workload application logs** | ADC/SDK error, reconnect, startup | Không in payload hoặc access token |
| **Cloud Monitoring** | Restart count, 5xx, mount delays, quota/latency | SLO dashboard và alert theo môi trường |

**Cloud Audit Logs Data Access** có thể cần được bật theo loại dịch vụ và chính sách, phát sinh dung lượng/chi phí. Không mặc định tất cả request secret đều đã được log đầy đủ nếu hệ thống chưa được cấu hình.

### 16.2. Những alert hữu ích

- **PERMISSION_DENIED** tăng đột biến sau thay đổi IAM.
- Mount/CSI event **FailedMount**, Pods trong **ContainerCreating** quá lâu.
- GKE metadata server timeout hoặc ADC credential errors.
- Secret Manager API errors, quota/rate-limit và latency tăng.
- Rotation đã phát hành version mới nhưng app vẫn dùng credential cũ.
- IAM policy mới cấp **secretAccessor** cho principalSet quá rộng.
- Thay đổi KSA, RoleBinding hoặc IAM SA impersonation bất thường.
- ImagePullBackOff kéo dài sau deploy.

Alert phải kèm **cluster, project, namespace, KSA, secret resource, version và error code**, tránh đính kèm plaintext secret, token hoặc toàn bộ payload.

### 16.3. Hiệu năng và chi phí

| Giải pháp | Chi phí/thành phần liên quan | Tối ưu |
|---|---|---|
| **Kubernetes Secret** | Cluster/control-plane, operational/security burden | Không dùng số lượng lớn làm kho dữ liệu thông thường |
| **Secret Manager** | Active secret versions, access operations, replication/CMEK tùy chọn | Không fetch mỗi HTTP request; cache hợp lý |
| **CSI add-on** | Pod mounts, API calls khi mount/rotation, GKE resources | Rotation interval theo nhu cầu, tránh refresh không cần |
| **SecretSync** | Đồng bộ và Kubernetes Secret objects | Chỉ bật khi legacy app cần; dọn copies cũ |
| **WIF for GKE** | Credential exchanges và các APIs liên quan theo quota/pricing hiện hành | Reuse client, tránh tạo client mỗi request |
| **Logging/Monitoring** | Log storage/query, monitoring metrics và notifications | Chọn log volume và retention theo bảo mật/SLO |

Không tự giả định mỗi lần CSI refresh tính phí như một Secret Manager API request trong mọi trường hợp; đối chiếu **metrics, operation counts và bảng giá hiện hành** để ước lượng TCO.

## 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ưu tiên |
|---|---|---|
| **403 PERMISSION_DENIED** khi gọi Secret Manager | Sai WIF principal, thiếu secretAccessor, IAM deny hoặc policy khác | Project number, namespace/KSA, secret IAM policy |
| **403** khi impersonate GSA | Thiếu roles/iam.workloadIdentityUser hoặc annotation sai | KSA annotation, GSA IAM policy |
| App báo **DefaultCredentialsError** | ADC không đến GKE metadata server, env key file lỗi | GOOGLE_APPLICATION_CREDENTIALS, node pool, metadata server |
| **FailedMount** trên CSI | Add-on chưa bật, SecretProviderClass sai, thiếu IAM hoặc version không tồn tại | kubectl describe pod, cluster add-on state, SPC resourceName |
| Pod chạy trên Standard node pool không có WIF | Node pool đang dùng GCE_METADATA | nodePools workloadMetadataConfig, GKE_METADATA |
| Autopilot từ chối nodeSelector WIF | Selector dành cho Standard bị dùng trên Autopilot | Gỡ iam.gke.io/gke-metadata-server-enabled selector |
| SecretProviderClass tạo được nhưng file không xuất hiện | Pod không dùng đúng CSI driver hoặc SPC name/namespace sai | Volume driver, provider gke, kubectl get spc |
| CSI file không cập nhật khi đổi version | Không bật rotation, cluster version cũ, pin phiên bản cố định | version support, flags, versions/latest |
| File đã đổi nhưng Java vẫn dùng password cũ | App chỉ đọc startup, HikariCP vẫn dùng old credentials | App reload, pool refresh, rollout |
| Kubernetes Secret env không đổi | Env không tự refresh khi Secret object update | Rolling restart hoặc cập nhật app mechanism |
| Kubernetes Secret subPath không đổi | subPath không nhận auto updates | Mount directory trực tiếp, thay cách tổ chức volume |
| SecretSync không tạo K8s Secret | GKE dưới 1.33, flag chưa bật, SecretSync/SPC/KSA sai | GKE version, sync flags, CRDs/events |
| KSA khác lại truy cập được secret production | IAM principalSet quá rộng, node credentials, trùng identity ở nhiều clusters | Effective policy, identity sameness, hostNetwork |
| **ImagePullBackOff** | Registry auth/image URL/node pull identity | Artifact Registry reader, image digest và node/event |
| Java client trả 429/5xx | Secret Manager quota/service/network hoặc quá nhiều fetch | Retry/backoff, cache, quotas, Monitoring |
| Pod có WIF nhưng không gọi được Cloud Storage | SecretAccessor không liên quan Storage roles | Thêm bucket-specific role phù hợp, không phải secret Admin |
| Namespace khác không mount được secret | SecretProviderClass/KSA khác namespace | Đồng bộ namespace, KSA principal và binding |

### 17.1. Lệnh chỉ đọc nên dùng

~~~bash
# Đúng cluster/namespace trước mọi chẩn đoán
kubectl config current-context
kubectl get pod -n shop
kubectl get serviceaccount orders-ksa -n shop -o yaml
kubectl get secretproviderclass -n shop

kubectl describe pod orders-secret-test -n shop
kubectl get events -n shop --sort-by=.lastTimestamp

gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001

gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(workloadIdentityConfig,addonsConfig.secretManagerConfig)"
~~~

**Không thêm các lệnh cat/print secret payload vào log tập trung chỉ để debug.** Khi bắt buộc xác minh nội dung, làm trong môi trường được phép theo quy trình dữ liệu mật và không lưu plaintext vào ticket.

### 17.2. Chia lỗi theo tầng

1. **Pod chưa chạy:** image pull, scheduler, admission, PodSecurity.
2. **Pod đang tạo nhưng volume không mount:** CSI driver, SecretProviderClass, GKE add-on, WIF/IAM.
3. **Pod chạy nhưng Google API trả 403:** identity principal, GSA impersonation, IAM role scope, IAM Deny/VPC SC.
4. **Đọc được secret nhưng ứng dụng lỗi:** version/format, credential ở dịch vụ đích, Java reload/connection pool.
5. **Đổi secret không có tác dụng:** rotation flags/version pin, env vs file, app cache.
6. **Chỉ lỗi sau deploy sang cluster khác:** identity sameness, cluster/nodepool WIF, region, namespace, IAM projectNumber.

## 18. Tình huống tổng hợp: Java API, Cloud SQL và Cloud Storage trên GKE

Doanh nghiệp **Minh Sơn** có hai clusters:

- **shop-staging** thuộc project **shop-stg-001**.
- **shop-production** thuộc project **shop-prod-001**.

Ứng dụng:

- Java/Spring Boot **orders-api** đọc một legacy DB secret từ Secret Manager.
- Worker **image-processor** đọc bucket ảnh gốc và ghi ảnh tối ưu.
- **Cloud SQL PostgreSQL** là managed database; một số dịch vụ có thể dùng Cloud SQL IAM authentication thay password tĩnh.
- Image được build trong Cloud Build và lưu ở Artifact Registry, deploy qua pipeline đã xét duyệt.

### 18.1. Sơ đồ đề xuất

~~~mermaid
flowchart LR
    DEV["CI/CD"] --> REG["Artifact Registry<br/>image by digest"]
    REG --> GKE["GKE Production"]
    GKE --> API["Pod orders-api<br/>KSA orders-ksa"]
    GKE --> IMG["Pod image-processor<br/>KSA images-ksa"]
    API --> WIF["WIF for GKE / IAM"]
    IMG --> WIF
    WIF --> SM["Secret Manager<br/>orders-db-password"]
    WIF --> ST["Cloud Storage<br/>image buckets"]
    API --> SQL["Cloud SQL PostgreSQL"]
    SEC["Kubernetes RBAC/PodSecurity"] --> GKE
    OBS["Cloud Logging/Monitoring"] --> GKE
~~~

### 18.2. Phân quyền đề xuất

| Actor | Cần quyền | Không cấp mặc định |
|---|---|---|
| orders-ksa | secretAccessor **trên secret của orders**; bucket Reader nếu API cần | Secret Manager Admin, Storage Admin toàn project |
| images-ksa | Object Viewer trên input bucket, Object Creator/User trên output bucket theo nghiệp vụ | Quyền đọc DB password |
| CI publisher | Artifact Registry Writer trên repo image đích | SecretAccessor của production runtime |
| Node/image-pull identity | Artifact Registry Reader theo cơ chế GKE | SecretAccessor theo ứng dụng |
| Security team | Policy review, audit logs theo role phù hợp | Quyền xem plaintext secret nếu không cần |
| Rotation service account | Tạo version/rotate credential ở dịch vụ đích | Role rộng trên tất cả secrets |

**Staging và production nên ở projects khác nhau** để tách workload identity pools và giảm nguy cơ dùng nhầm KSA principal. Không dùng một project duy nhất cho cả hai nếu clusters do những nhóm có mức tin cậy khác nhau quản lý.

### 18.3. Chiến lược secret

| Loại bí mật | Nguồn | Cách Pod nhận | Rotation |
|---|---|---|---|
| DB password legacy | Secret Manager | CSI mount hoặc Java SDK | Tạo version mới, phối hợp database credentials, app reload |
| Cloud Storage access | **Không lưu JSON key** | WIF + IAM trực tiếp | Google token ngắn hạn tự làm mới qua ADC |
| TLS certificate ứng dụng | Secret Manager hoặc certificate controller được duyệt | File/CSI/Ingress mechanism tương ứng | Quy trình cấp/gia hạn, reload cert |
| Container registry credentials | Không nhét password vào app Pod nếu GKE pull identity hỗ trợ | Node/service agent, Artifact Registry IAM | Rotate auth qua identity managed |

### 18.4. Ma trận nghiệm thu

| Phép thử | Kết quả mong đợi |
|---|---|
| orders-ksa đọc đúng orders-db-password | Thành công |
| orders-ksa đọc secret của hệ thống nhân sự | **403** |
| images-ksa đọc DB password của orders | **403** |
| KSA chưa cấp quyền gọi Secret Manager | **403** |
| Pod lấy credential qua WIF | Không có JSON key trong image/Pod |
| CSI mount vào đúng container | File tồn tại, app đọc được mà không log plaintext |
| Secret Manager version mới | CSI refresh theo version/interval khi được bật |
| Java chưa reload file mới | Có test phát hiện và runbook reload/rollout |
| Người dùng chỉ có quyền xem Pods | Không xem được secret values |
| Người dùng có quyền tạo Pods trong namespace production | Bị quản trị chặt vì có đường lấy secrets gián tiếp |
| Deploy sang cluster staging | Không dùng chung GKE WIF principal của production |
| Image pull sau rotate node | Thành công với Artifact Registry pull identity đúng |
| Secret Manager tạm có lỗi | App phản ứng theo cache/backoff, đo SLO và cảnh báo |

### 18.5. Khi nào cần lựa chọn khác?

- Nếu ứng dụng Java chỉ cần Google API permissions, **WIF trực tiếp + ADC** thường đơn giản hơn dùng một password/JSON key.
- Nếu ứng dụng chỉ đọc secret ở startup nhưng không hỗ trợ reload, dùng CSI mount và **rolling restart** có kiểm soát khi rotate.
- Nếu chart bắt buộc **secretKeyRef** vào Kubernetes Secret, dùng **SecretSync** và harden RBAC/encryption.
- Nếu môi trường yêu cầu cách ly mạnh giữa teams không tin nhau, dùng **projects/clusters riêng**, không chỉ namespaces.
- Nếu có hàng nghìn Pods cùng fetch latest vào startup, đánh giá rate limits, API retries và caching để tránh thundering herd.

## 19. Bài tập thực hành

### Bài tập A — Phân biệt danh tính và quyền

Một Pod chạy KSA **shop/orders-ksa** và có Kubernetes RBAC quyền **list Pods**. Secret Manager secret **orders-db-password** chưa cấp IAM cho principal nào.

**Câu hỏi:** Pod có thể đọc Secret Manager không? Phải thay đổi gì?

**Đáp án:** Không. Kubernetes RBAC không cấp Google Cloud permissions. Cần bật WIF đúng cluster/node, grant **roles/secretmanager.secretAccessor** trên secret cho direct KSA principal (hoặc dùng GSA impersonation với các grants đúng).

### Bài tập B — Phát hiện quyền cấp quá rộng

IAM binding của secret dùng:

~~~text
principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/namespace/shop
~~~

**Câu hỏi:** Có thể khiến mọi Pod thuộc namespace shop được đọc secret không? Nên thay bằng gì?

**Đáp án:** Selector này bao phủ toàn namespace theo workload pool, rộng hơn một KSA. Nếu chỉ orders-api cần, dùng **principal://.../subject/ns/shop/sa/orders-ksa** hoặc selector hẹp hơn.

### Bài tập C — IAM direct và impersonation

Một nhóm đã annotate KSA:

~~~text
iam.gke.io/gcp-service-account=orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

nhưng Pod vẫn báo 403 khi gọi Secret Manager.

**Đáp án định hướng:** kiểm tra IAM binding **roles/iam.workloadIdentityUser** cho KSA trên GSA, GSA có **secretAccessor** trên secret, KSA namespace/name đúng và cluster/node pool đang dùng WIF. Annotation một mình chưa đủ.

### Bài tập D — Secret rotation

Một secret được CSI mount với **versions/latest**, rotation bật mặc định 120 giây. Sau khi thêm version mới 10 phút, file trong Pod đã thay đổi nhưng Java vẫn xác thực database bằng password cũ.

**Câu hỏi:** Lỗi nằm ở Secret Manager hay ứng dụng?

**Đáp án:** Khi file đã thay đổi, cơ chế fetch/CSI hoạt động. Java có thể đã đọc một lần khi startup hoặc pool giữ credential cũ. Phải implement reload hoặc rollout; kiểm tra database đã chấp nhận password mới và có kế hoạch overlap/rollback.

### Bài tập E — SecretSync và bảo mật Kubernetes

Một Helm chart chỉ hỗ trợ **env.valueFrom.secretKeyRef**.

**Câu hỏi:** Nên sử dụng CSI add-on hay SecretSync? Bí mật tồn tại ở đâu? Những quyền nào phải bảo vệ?

**Đáp án:** Có thể dùng SecretSync để tạo Kubernetes Secret từ Secret Manager khi GKE đủ version. Sau khi đồng bộ, bí mật có mặt trong Kubernetes cluster state và Pod env; cần giới hạn RBAC, quyền tạo Pod/exec, namespace isolation, encryption. Env không tự cập nhật; cần restart/reload.

### Bài tập F — Identity sameness giữa clusters

Hai clusters **dev** và **prod** trong cùng project, đều có namespace **shop** và KSA **orders-ksa**. IAM grant theo subject/ns/shop/sa/orders-ksa.

**Câu hỏi:** Dev có thể được nhận quyền giống prod không? Biện pháp?

**Đáp án:** Có nguy cơ vì principal theo namespace/KSA được chia sẻ trong workload identity pool cấp project. Tách projects theo trust boundary, dùng selectors KSA UID/cluster theo trường hợp, kiểm soát tạo namespace/KSA và audit effective access.

### Bài tập G — Phân loại lỗi

| Triệu chứng | Bước điều tra đầu tiên |
|---|---|
| Pod Pending hoặc ImagePullBackOff | Scheduler, Artifact Registry pull identity và image URL |
| Pod ContainerCreating, FailedMount | CSI driver/add-on, SPC và IAM |
| Pod Running, Secret Manager API 403 | WIF principal, IAM secretAccessor, impersonation |
| CSI file mới nhưng env cũ | Env không tự refresh, app restart |
| Kubernetes Secret base64 trong Git | Secret đã bị lộ, thu hồi credential và loại bỏ lịch sử chứa bí mật theo quy trình |
| Không đọc được secret từ Windows node | Managed CSI add-on không hỗ trợ Windows Server nodes |

### Bài tập H — Thiết kế runbook sự cố

Lập runbook khi một API key bị lộ:

1. Ai có quyền revoke key tại dịch vụ đích?
2. Secret nào/versions nào bị ảnh hưởng?
3. Làm sao thay version trong Secret Manager mà không in plaintext vào logs?
4. GKE dùng SDK, CSI hay SecretSync và rotation/reload ra sao?
5. Ai xác nhận mọi Pods đã chuyển credential mới?
6. Có đường nào từ KSA, GSA, node identity hoặc RBAC khiến key bị lấy lại không?
7. Cần cảnh báo, audit, postmortem và cleanup gì?

**Tiêu chí:** không chỉ thay value trong Secret Manager; phải revoke credential cũ ở dịch vụ đích, xác minh ứng dụng hoạt động, thu hẹp quyền và kiểm toán.

## 20. Runbook triển khai production

### 20.1. Trước khi thay đổi

1. Liệt kê **cluster/project/namespace/KSA**, node pools và trạng thái WIF.
2. Xác minh đúng **Secret Manager project/location/resource path**, secret versions và principal.
3. Chọn mô hình **direct IAM** hoặc **GSA impersonation**; không cấp thừa cả hai khi không cần.
4. Xác định ứng dụng nhận secret qua **SDK, CSI, Kubernetes Secret hay SecretSync**.
5. Đọc hạn chế GKE version/add-on/OS node và chính sách VPC SC.
6. Kiểm tra ai có quyền deploy Pods, exec, get Secrets và sửa KSA/IAM.
7. Chuẩn bị **secret version và rollback plan**, không ghi giá trị vào manifest/CI log.

### 20.2. Khi triển khai

1. Tạo/grant principal ở phạm vi **một secret** trước.
2. Apply KSA và manifests tham chiếu tới **đúng namespace**.
3. Rollout staged workloads, kiểm tra events và readiness.
4. Test đường thành công và **test KSA không có quyền**.
5. Xác minh secret được sử dụng mà không xuất hiện trong logs hoặc crash traces.
6. Ghi lại thay đổi IAM, KSA/serviceAccountName và SecretProviderClass version.

### 20.3. Khi rotation

1. Phát hành credential mới ở dịch vụ đích và Secret Manager.
2. Nếu dùng **latest**, chờ refresh theo interval/capability; nếu pin version, cập nhật manifest có kiểm soát.
3. Kiểm tra ứng dụng/connection pools nhận secret mới.
4. Canary rollout rồi rollout toàn hệ thống với health checks.
5. Khi xác minh đã chuyển thành công, revoke credential cũ và disable/destroy version cũ theo policy.
6. Ghi audit, thời gian, phiên bản và SLO impact.

### 20.4. Khi có 403/FailedMount

1. Phân loại lỗi thuộc image pull, CSI, Kubernetes RBAC hay IAM.
2. Xác định principal thực tế thay vì đoán theo tên Pod.
3. Kiểm tra GKE version, WIF pool, Standard node metadata mode, namespace/KSA/SPC.
4. Đọc IAM secret policy, IAM Deny/VPC SC và Secret Manager API logs.
5. Sửa permission nhỏ nhất hoặc rollback change mới nhất.
6. Không log secret plaintext trong quá trình debug.

## 21. Tổng kết và tài liệu tham khảo

**Tám nguyên tắc cần nhớ:**

1. **Kubernetes RBAC** và **Google Cloud IAM** là hai lớp quyền khác nhau; KSA, IAM SA, node SA và identity pull image không được đánh đồng.
2. **Workload Identity Federation for GKE** cho Pod truy cập Google APIs bằng credential ngắn hạn, tránh JSON private keys; Autopilot bật sẵn, Standard cần kiểm tra cluster lẫn node pools.
3. **IAM trực tiếp cho KSA principal** phù hợp khi API hỗ trợ; **GSA impersonation** là phương án tương thích cần cả **roles/iam.workloadIdentityUser** và KSA annotation.
4. **Kubernetes Secret** là Kubernetes API object; **base64 không phải encryption**. GKE mã hóa dữ liệu cluster at rest, có thêm Cloud KMS application-layer encryption khi cần.
5. **Secret Manager** cung cấp quản lý secret versions, IAM và audit tập trung; ưu tiên **SDK hoặc GKE managed CSI add-on** khi ứng dụng hỗ trợ.
6. **SecretSync** là phương án dành cho ứng dụng cần Kubernetes Secret, nhưng nó **đưa bản sao secret vào cluster** và yêu cầu RBAC/namespace control tương xứng.
7. **Rotation không hoàn tất khi Secret Manager version thay đổi**. File, env, Java memory, database credentials và phiên làm việc phải được cập nhật theo thiết kế.
8. **Least privilege, tách project, kiểm thử âm tính, audit logs và runbook** quan trọng ngang lệnh cấu hình.

**Tài liệu Google Cloud và Kubernetes chính thức:**

1. [About Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — pool/metadata server, IAM principal formats, identity sameness và giới hạn.
2. [Authenticate to Google Cloud APIs from GKE workloads](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) — gcloud cluster/node pool, direct principal, GSA impersonation và KSA annotations.
3. [Use Secret Manager add-on with GKE](https://docs.cloud.google.com/secret-manager/docs/secret-manager-managed-csi-component) — CSI driver, SecretProviderClass, node limitations và rotation.
4. [Synchronize secrets to Kubernetes Secrets](https://docs.cloud.google.com/secret-manager/docs/sync-k8-secrets) — SecretSync resource, GKE version, sync/rotation.
5. [Access secrets in GKE using client libraries](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/workload-identity-secrets) — direct WIF secret access lab.
6. [Secret Manager best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices) — rotate, pin versions, disable-before-destroy và IAM.
7. [Secret Manager access control](https://docs.cloud.google.com/secret-manager/docs/access-control) — secretAccessor và phạm vi IAM.
8. [Encrypt secrets at the application layer in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/encrypting-secrets) — Cloud KMS envelope encryption.
9. [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — data/stringData, env/volume, RBAC và giới hạn 1 MiB.
10. [Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/) — least privilege, access control, Pod escalation và logging.
11. [Kubernetes Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/) — identity tokens, serviceAccountName và permissions.
12. [Kubernetes RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — Roles, RoleBindings và access review.
13. [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam) — bucket-level IAM và workload principals.
