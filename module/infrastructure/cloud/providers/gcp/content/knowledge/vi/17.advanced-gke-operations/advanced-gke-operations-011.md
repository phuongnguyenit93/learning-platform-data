# Binary Authorization và chính sách cho workload GKE

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Binary Authorization** (BinAuthz) kiểm soát *image nào được triển khai* trên Google Kubernetes Engine (GKE), và phân biệt với IAM, Kubernetes RBAC, Pod Security Admission.
2. Hiểu **image digest**, **attestor**, **attestation**, **Artifact Analysis note** và vai trò của Cloud Build, Artifact Registry, Cloud KMS trong chuỗi cung ứng phần mềm.
3. Cấu hình **project-singleton policy** với các chế độ **ALWAYS_ALLOW**, **ALWAYS_DENY**, **REQUIRE_ATTESTATION**, **DRYRUN_AUDIT_LOG_ONLY** và **ENFORCED_BLOCK_AND_AUDIT_LOG**.
4. Thực hành bật enforcement cho cluster, xuất/nhập policy, kiểm thử Pod bị chặn và Pod có attestation hợp lệ; sử dụng breakglass có kiểm toán khi khẩn cấp.
5. Phân biệt **deploy-time enforcement** với **Continuous Validation (CV)** trên các Pods đang chạy, nhận diện giới hạn phạm vi quét và trạng thái Preview của CV.
6. Thiết kế quy trình CI/CD cho ứng dụng Java trên GKE theo nguyên tắc ít đặc quyền, có khả năng rollback, giám sát và kiểm soát chi phí.

## 1. Tại sao workload cần chính sách trước khi chạy?

Trong mô-đun **CLOUD_PROVIDERS_GCP**, hệ thống sử dụng project, IAM, VPC, Compute Engine, GKE, Cloud Run, storage và database. Một ứng dụng Java có thể đã qua kiểm thử, được build thành container image và đẩy lên **Artifact Registry**. Nhưng một developer có quyền tạo Deployment trên cluster vẫn có thể nhập một image lạ nếu không có cơ chế kiểm tra image tại thời điểm triển khai.

Ví dụ: cluster production của cửa hàng chỉ được phép chạy image:

- Được build bằng pipeline đã phê duyệt.
- Được kiểm tra/phê duyệt bởi nhóm bảo mật.
- Có **sha256 digest cố định** tương ứng với bản release thực tế.

**Binary Authorization** là một điểm kiểm soát *admission*: kiểm tra image trong PodSpec theo **policy**, trước khi cho phép Pod dùng image đó được triển khai. Nó không tự quét mã độc, không thay thế kiểm thử ứng dụng và không cấp quyền đọc Artifact Registry.

~~~mermaid
flowchart LR
    SOURCE["Git commit"] --> BUILD["Cloud Build<br/>build + test + scan"]
    BUILD --> REG["Artifact Registry<br/>image@sha256:digest"]
    BUILD --> APPROVE["Security/release approver<br/>attestation"]
    APPROVE --> NOTE["Artifact Analysis<br/>note / occurrence"]
    REG --> DEPLOY["GKE Deployment"]
    DEPLOY --> GATE{"Binary Authorization<br/>enforcement policy"}
    NOTE --> GATE
    GATE -->|Hợp lệ| POD["Pod được tạo"]
    GATE -->|Không hợp lệ| DENY["Từ chối + Audit Log"]
~~~

### Chính sách GKE không phải một lớp duy nhất

| Lớp | Câu hỏi | Công cụ minh họa |
|---|---|---|
| **Identity** | Ai được phép triển khai hoặc gọi GKE API? | Google Cloud IAM, Kubernetes RBAC |
| **Image admission** | Image được phép triển khai không? | **Binary Authorization** |
| **Pod security** | Container có chạy privileged, hostPath, root không? | Pod Security Admission, Policy Controller/Gatekeeper |
| **Runtime** | Image đang chạy còn tuân thủ policy không? | **Binary Authorization CV**, Cloud Logging/Monitoring |
| **Data/API access** | Pod có thể đọc secret, bucket, database nào? | Workload Identity Federation for GKE, IAM, NetworkPolicy |

Vì mỗi lớp chặn một kiểu rủi ro, **BinAuthz không thay thế** least-privilege RBAC, vulnerability scanning, network isolation hay runtime hardening.

## 2. Những khái niệm cần phân biệt

| Thành phần | Vai trò | Không nên nhầm |
|---|---|---|
| **Container image** | Gói mã và dependencies được chạy bởi container | Mã nguồn Git hoặc Kubernetes Deployment |
| **Tag** (ví dụ `orders:1.2.0`) | Tên có thể được trỏ sang image khác | Định danh content bất biến |
| **Digest** (`sha256:...`) | Định danh content của manifest image | Hash của một file JAR riêng lẻ |
| **Attestor** | Thực thể xác minh chữ ký cho một loại phê duyệt | Người có IAM Writer trong Artifact Registry |
| **Attestation** | Bản ghi được ký liên kết với image digest, biểu thị điều kiện/phê duyệt theo quy trình | Bằng chứng tự động rằng image không còn lỗ hổng |
| **Artifact Analysis note** | Metadata gốc cho loại attestation | Một bản sao image blob |
| **Occurrence** | Bản ghi attestation gắn với image cụ thể | Policy cho phép triển khai |
| **Project-singleton policy** | Bộ quy tắc deploy-time enforcement của một project | CV platform policy |
| **CV platform policy** | Các checks giám sát image của Pods đang chạy | Admission rule để chặn Pod mới |

**Đường dẫn image theo digest** minh họa:

~~~text
asia-southeast1-docker.pkg.dev/shop-prod-001/containers/orders-api@sha256:<64-ky-tu-hex>
~~~

Chuỗi trên là placeholder, không phải digest thật; khi triển khai thay bằng digest có thật từ registry/build output. Nên sử dụng digest trong manifests production để giảm rủi ro tag bị ghi đè. Một attestation xác nhận **digest**, không phải tên tag mutable.

### Attestation có nghĩa gì?

Ví dụ nhóm bảo mật chỉ ký khi: source được review, unit/integration tests thành công, vulnerability gate chấp nhận rủi ro và release owner phê duyệt. Khi đó attestation là **bằng chứng đã áp quy trình phê duyệt**. Nếu người ký hoặc pipeline bị chiếm quyền, chữ ký hợp lệ vẫn có thể đi cùng image xấu. Vì vậy quản lý **signing key và quyền tạo attestation** quan trọng ngang chính sách chặn.

## 3. Cách deploy-time enforcement đánh giá policy

Một project có **một** Binary Authorization **project-singleton policy**. Những GKE clusters bật enforcement trong project dùng policy đó, trừ khi có các quy tắc phù hợp ở phạm vi cụ thể.

### 3.1. Evaluation mode và enforcement mode

| Trường | Giá trị | Hành vi |
|---|---|---|
| `evaluationMode` | **ALWAYS_ALLOW** | Cho phép image thuộc phạm vi rule |
| `evaluationMode` | **ALWAYS_DENY** | Đánh dấu image thuộc phạm vi rule không hợp lệ |
| `evaluationMode` | **REQUIRE_ATTESTATION** | Yêu cầu attestation hợp lệ được xác minh bởi **tất cả attestors** trong `requireAttestationsBy` |
| `enforcementMode` | **DRYRUN_AUDIT_LOG_ONLY** | **Không chặn**, nhưng ghi vi phạm vào Cloud Audit Logs |
| `enforcementMode` | **ENFORCED_BLOCK_AND_AUDIT_LOG** | Chặn deployment vi phạm và ghi log |

Các trường này **độc lập**: `ALWAYS_DENY` đi cùng **dry-run** vẫn cho Pod được tạo để đánh giá tác động; chuyển sang **enforced** sẽ chặn. `ALWAYS_ALLOW` cùng `ENFORCED_BLOCK_AND_AUDIT_LOG` vẫn cho phép mọi image trong rule — điều rất dễ bị hiểu sai.

### 3.2. Chính sách mặc định chưa an toàn theo ý nghĩa “chỉ nhận image đáng tin”

Khi tạo project, default Binary Authorization policy có dạng:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: ALWAYS_ALLOW
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
~~~

Do đó **bật Binary Authorization trên cluster nhưng chưa sửa policy vẫn có thể cho mọi image ứng dụng được triển khai**. Cần tự xác định rule và thí nghiệm với chế độ dry-run trước khi chặn production.

### 3.3. Policy evaluation và các ngoại lệ

| Trường policy | Ý nghĩa |
|---|---|
| `defaultAdmissionRule` | Áp dụng khi không có rule cụ thể hơn |
| `clusterAdmissionRules` | Rule riêng cho cluster, khóa theo **LOCATION.CLUSTER_NAME**; khi khớp, thay thế default rule |
| `kubernetesNamespaceAdmissionRules` | Rule theo namespace GKE |
| `kubernetesServiceAccountAdmissionRules` | Rule theo Kubernetes ServiceAccount, khóa **NAMESPACE:SERVICE_ACCOUNT** |
| `admissionWhitelistPatterns` | Exemption theo image path/pattern |
| `globalPolicyEvaluationMode: ENABLE` | Đánh giá system policy để miễn trừ những image hệ thống do Google quản lý |

Các rule theo namespace/KSA hữu ích khi staging và production cùng project, nhưng **nên tách project theo ranh giới tin cậy** khi có thể. Không giả định mọi rule được kết hợp bằng AND; chúng có semantics chọn rule, cần đọc policy cuối cùng và kiểm thử.

**Giữ `globalPolicyEvaluationMode: ENABLE`** trong hầu hết hệ thống GKE. Nếu tắt, các image hệ thống GKE có thể bị chặn khi có cập nhật nền tảng; quản trị viên phải tự duy trì allowlist hệ thống.

### 3.4. Exempt images có thể làm mất hiệu lực policy

Ví dụ allowlist:

~~~yaml
admissionWhitelistPatterns:
  - namePattern: asia-southeast1-docker.pkg.dev/shop-prod-001/approved-system-images/**
~~~

Đây là ví dụ **chính sách có khả năng mở rộng phạm vi miễn trừ**; chỉ dùng cho thành phần có owner rõ ràng. Pattern `**` có thể match nhiều image/subpath hơn `*`. Không thêm `**` cho cả project hay một registry công khai chỉ để xử lý lỗi 403.

## 4. Giới hạn và thời điểm thực thi cần nhớ

**BinAuthz enforcement chỉ kiểm tra lúc triển khai, không phải quét liên tục mỗi giây.**

- Nếu policy hôm nay đổi từ allow sang deny, **Pod đang chạy không tự bị kết thúc**. Khi Pod mới được tạo/triển khai lại, admission có thể áp rule mới.
- Theo tài liệu GKE hiện hành, deploy-time enforcement kiểm tra image trong các trường **`containers`** và **`ephemeralContainers`** của PodSpec; **không kiểm tra `initContainers` và image volumes ở thời điểm deploy**. Vì vậy không được coi BinAuthz là cơ chế kiểm tra tất cả image trong Pod.
- **Continuous Validation** có thể kiểm tra image của **init và ephemeral containers** khi giám sát Pod đang chạy; CV chỉ **ghi logs, không kill Pods**.
- Một image vượt qua BinAuthz vẫn có thể có CVE mới, secret bị lộ hoặc cấu hình Pod không an toàn.
- Nếu Binary Authorization backend không khả dụng, có cơ chế **fail open** trong các trường hợp được ghi nhận ở audit logs. Không tuyên bố “BinAuthz luôn fail closed trong mọi sự cố”.

**Kết luận vận hành:** cần bổ sung **Pod Security Admission/Policy Controller**, image vulnerability scanning, IAM least privilege, audit và CV nếu phù hợp. <https://docs.cloud.google.com/binary-authorization/docs/setting-up>

## 5. Chuẩn bị mô hình thực hành an toàn

Ví dụ cho một project **lab** (mọi giá trị đều giả định):

| Thuộc tính | Giá trị |
|---|---|
| Project | **shop-dev-001** |
| GKE cluster | **gke-release-lab** |
| Region | **asia-southeast1** |
| Artifact Registry | **asia-southeast1-docker.pkg.dev/shop-dev-001/containers** |
| Attestor | **release-approver** |
| Artifact Analysis note | **release-note** |
| Cloud KMS key | **global/release-ring/release-signing** |
| Namespace | **shop** |

Lưu ý: bật GKE, Artifact Registry, Cloud KMS, logging và Binary Authorization có thể phát sinh chi phí. **Không thực hiện trên production**, và không nhập policy chặn mọi image trước khi lưu bản policy hiện có. Lab chỉ mô tả lệnh, không tạo tài nguyên thực.

### 5.1. Kiểm tra ngữ cảnh và API

~~~bash
gcloud config get-value project
gcloud auth list
gcloud container clusters list --project=shop-dev-001
gcloud artifacts repositories list --project=shop-dev-001 \
  --location=asia-southeast1

# Thao tác thay đổi project; chỉ chạy với quyền được giao.
gcloud services enable binaryauthorization.googleapis.com \
  containeranalysis.googleapis.com \
  cloudkms.googleapis.com \
  --project=shop-dev-001
~~~

Để xem và sửa policy cần quyền Binary Authorization phù hợp, chẳng hạn **roles/binaryauthorization.policyViewer** hoặc **roles/binaryauthorization.policyEditor**. Quyền cập nhật GKE cluster, cấp IAM, tạo attestor, ký bằng KMS và upload image **khác nhau**; không cấp Owner chỉ để làm theo bài.

### 5.2. Xem policy và lưu bản gốc

~~~bash
gcloud container binauthz policy export \
  --project=shop-dev-001 > policy-original.yaml

gcloud container clusters describe gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(name,binaryAuthorization)"
~~~

**policy-original.yaml** là file xuất để review/rollback trong môi trường thực hành, không phải một file được tạo bởi worker trong repository học tập. Nếu policy hiện có chứa rule cho nhiều clusters, giữ nguyên những rule không liên quan trong bản chỉnh sửa.

### 5.3. Bật enforcement trên cluster lab

~~~bash
gcloud container clusters update gke-release-lab \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE
~~~

Lệnh này thay đổi cluster; có thể cần vài phút trước khi policy phát huy tác dụng. Nếu cluster đã bật **Continuous Validation**, dùng mode **`POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE`** và giữ đúng các policy bindings — nếu chọn mode enforcement-only, **CV có thể bị tắt**.

## 6. Thiết kế một enforcement policy theo hai giai đoạn

### 6.1. Giai đoạn 1 — Dry-run để ghi nhận tác động

Sau khi đã tạo attestor (phần 7), file policy mẫu:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
~~~

**Giải thích:** mọi image ứng dụng trong phạm vi rule thiếu attestation vẫn được **cho deploy** nhưng có log vi phạm. Không dùng dry-run như giải pháp bảo vệ production lâu dài.

Để thử:

~~~bash
# Xem diff chính sách trước khi import.
gcloud container binauthz policy import policy-dryrun.yaml \
  --project=shop-dev-001

gcloud container binauthz policy export --project=shop-dev-001
~~~

**Import thay đổi project-singleton policy**, có thể tác động mọi cluster đã bật enforcement cùng project. Sử dụng project lab riêng, change record và backup; trong bài, lệnh trên chỉ là ví dụ quy trình.

### 6.2. Giai đoạn 2 — Enforce khi mọi release đã được ký

Giữ nguyên các trường khác, chỉ đổi:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
~~~

Thực hiện trên file policy **đầy đủ** (giữ `name`, `globalPolicyEvaluationMode` và các rule cần thiết), sau đó mới nhập:

~~~bash
gcloud container binauthz policy import policy-enforced.yaml \
  --project=shop-dev-001
~~~

**Không lưu chỉ đoạn `defaultAdmissionRule` vào file rồi import**: chính sách cần định dạng đầy đủ. Khi một rule cần **hai attestors**, cả hai phải có attestation được chấp nhận cho đúng image digest, không phải “một trong hai”.

### 6.3. Chính sách riêng cho cluster production

Ví dụ rút gọn, để staging vẫn audit-only nhưng prod chặn:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
clusterAdmissionRules:
  asia-southeast1.gke-release-lab:
    evaluationMode: REQUIRE_ATTESTATION
    enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
    requireAttestationsBy:
      - projects/shop-dev-001/attestors/release-approver
~~~

**Cluster rule khớp thay thế default rule**, không phải thực thi cả hai. Đây là ví dụ khi một project có nhiều clusters với yêu cầu khác nhau; cách phân tách dự án theo môi trường vẫn có thể dễ quản trị và cô lập quyền hơn.

## 7. Tạo attestor, khóa ký và attestation

Một **attestor** chưa có public key không thể xác minh chữ ký. **Cloud KMS** là lựa chọn được khuyến nghị để bảo vệ private signing key; không lưu khóa ký trong repository, Docker image hoặc máy CI dùng chung.

### 7.1. Tạo Artifact Analysis note

Ví dụ lệnh dành cho **Cloud Shell/Bash**, không chạy trực tiếp trong PowerShell với cùng cú pháp:

~~~bash
# Nội dung file note-payload.json (không chứa private key):
cat > note-payload.json <<'EOF'
{
  "name": "projects/shop-dev-001/notes/release-note",
  "attestation": {
    "hint": {"human_readable_name": "Approved production release"}
  }
}
EOF

curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-binary @note-payload.json \
  "https://containeranalysis.googleapis.com/v1/projects/shop-dev-001/notes/?noteId=release-note"
~~~

Binary Authorization sử dụng **global Artifact Analysis API endpoint**, không dùng regional Artifact Analysis storage/endpoint cho note này. Tài khoản thao tác phải có quyền quản trị Artifact Analysis note; lệnh tạo note có side effect, chỉ chạy trong project lab.

### 7.2. Tạo attestor tham chiếu note

~~~bash
gcloud container binauthz attestors create release-approver \
  --project=shop-dev-001 \
  --attestation-authority-note=release-note \
  --attestation-authority-note-project=shop-dev-001

gcloud container binauthz attestors describe release-approver \
  --project=shop-dev-001
~~~

### 7.3. Tạo khóa bất đối xứng trong Cloud KMS

~~~bash
gcloud kms keyrings create release-ring \
  --project=shop-dev-001 \
  --location=global

gcloud kms keys create release-signing \
  --project=shop-dev-001 \
  --location=global \
  --keyring=release-ring \
  --purpose=asymmetric-signing \
  --default-algorithm=ec-sign-p256-sha256 \
  --protection-level=software
~~~

**Phiên bản khóa** mới có thể là `1`, nhưng luôn kiểm tra kết quả thực tế. Production nên giới hạn rõ quyền **KMS sign** cho release pipeline có phê duyệt; người thay đổi policy BinAuthz không nên đương nhiên có quyền ký mọi image.

### 7.4. Đăng ký public key cho attestor

~~~bash
gcloud container binauthz attestors public-keys add \
  --project=shop-dev-001 \
  --attestor=release-approver \
  --keyversion-project=shop-dev-001 \
  --keyversion-location=global \
  --keyversion-keyring=release-ring \
  --keyversion-key=release-signing \
  --keyversion=1

gcloud container binauthz attestors describe release-approver \
  --project=shop-dev-001
~~~

Public key được attestor dùng để xác minh; private key vẫn trong Cloud KMS. Với môi trường nhiều project, cần cấu hình IAM cho **attestor/note/occurrences** theo tài liệu multi-project; không mặc định service agent ở cluster project đọc được toàn bộ tài nguyên bảo mật ở project khác.

### 7.5. Ký đúng image digest sau khi hoàn tất kiểm thử

Giả sử CI đã build và push image ứng dụng Java. Lấy **digest thực tế** từ Artifact Registry/build metadata và review kết quả:

~~~bash
gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/shop-dev-001/containers \
  --include-tags \
  --project=shop-dev-001
~~~

Sau khi xác nhận image URL có dạng `.../orders-api@sha256:<digest-thuc>`, điền chính xác giá trị đó vào biến `IMAGE_TO_ATTEST`:

~~~bash
IMAGE_TO_ATTEST="asia-southeast1-docker.pkg.dev/shop-dev-001/containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST"

# Thao tác KÝ và tạo attestation, chỉ sau khi release được phê duyệt:
gcloud container binauthz attestations sign-and-create \
  --project=shop-dev-001 \
  --artifact-url="$IMAGE_TO_ATTEST" \
  --attestor=release-approver \
  --attestor-project=shop-dev-001 \
  --keyversion-project=shop-dev-001 \
  --keyversion-location=global \
  --keyversion-keyring=release-ring \
  --keyversion-key=release-signing \
  --keyversion=1

gcloud container binauthz attestations list \
  --project=shop-dev-001 \
  --attestor=release-approver \
  --attestor-project=shop-dev-001 \
  --artifact-url="$IMAGE_TO_ATTEST"
~~~

Lệnh ký không tự chạy test, scan hoặc kiểm tra phê duyệt: **pipeline/approver phải thực thi các bước đó trước khi ký**. Digest chưa được thay thật sẽ làm lệnh lỗi; không dùng placeholder để deploy production.

**Chuỗi trách nhiệm:**

~~~text
CI builder (push image) → Security/release approver (quyết định)
 → KMS signer (ký digest) → Artifact Analysis attestation
 → GKE Binary Authorization (xác minh chữ ký trong policy)
~~~

### 7.6. built-by-cloud-build attestor

Google Cloud còn hỗ trợ attestor **built-by-cloud-build** để triển khai image có attestation do Cloud Build tạo trong quy trình được hỗ trợ. Đây là phương án đơn giản hơn tự quản lý một signer cơ bản, nhưng **“được Cloud Build xây” không đồng nghĩa đã được bảo mật phê duyệt**. Với hệ thống rủi ro cao, thêm một attestor **release-approved** độc lập hoặc kiểm tra provenance/vulnerability theo chính sách tổ chức.

## 8. Thử nghiệm admission và kiểm tra Pod

### 8.1. Deployment dùng digest bất biến

Manifest sau cố ý chứa placeholder chưa đủ 64 ký tự hex:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
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
      serviceAccountName: orders-ksa
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/shop-dev-001/containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
~~~

Ứng dụng Java phải thực sự có endpoint `/actuator/health/readiness` và một image digest tồn tại; đây là mẫu biểu diễn policy, **không phải manifest chạy được khi chưa thay placeholder**. Việc được BinAuthz cho phép không bảo đảm readiness probe thành công hoặc Pod được cấp đủ RAM/CPU.

### 8.2. Kiểm thử tích cực và tiêu cực

~~~bash
gcloud container clusters get-credentials gke-release-lab \
  --project=shop-dev-001 \
  --region=asia-southeast1

kubectl config current-context
kubectl get namespace shop

# Chỉ áp dụng sau khi thay digest thật và thiết lập quyền.
kubectl apply -f orders-deployment.yaml
kubectl get deployment orders-api -n shop
kubectl get pods -n shop
kubectl get events -n shop --sort-by=.lastTimestamp
~~~

Đánh giá ít nhất bốn trường hợp:

| Trường hợp | Kỳ vọng khi enforced REQUIRE_ATTESTATION |
|---|---|
| Image digest hợp lệ, attestor đã ký | **Pod được admit**, các điều kiện Kubernetes còn lại vẫn áp dụng |
| Cùng image nhưng **digest khác chưa có attestation** | **Bị chặn tại admission** |
| Image đúng digest, KSA thiếu quyền đọc Cloud Storage | **BinAuthz có thể cho chạy**, nhưng app gọi Storage bị 403 |
| Image đã ký nhưng Pod vi phạm Pod Security Admission | **Bị chặn bởi policy Pod Security**, không phải do BinAuthz |

Nếu Pod bị chặn, xem lỗi như `imagepolicywebhook.image-policy.k8s.io` hoặc `Denied by attestor`. Phân biệt lỗi admission với **ImagePullBackOff** (thường xảy ra *sau* khi Pod được tạo và liên quan image URL/registry/IAM pull).

### 8.3. Không đánh đồng kubectl apply thành công với Pod đã chạy

`kubectl apply` với **Deployment** có thể thành công vì Kubernetes nhận Deployment object, nhưng ReplicaSet tiếp tục tạo Pods và bị admission webhook từ chối. Phải kiểm tra:

~~~bash
kubectl describe deployment orders-api -n shop
kubectl get replicaset -n shop
kubectl describe replicaset -n shop
kubectl get events -n shop --sort-by=.lastTimestamp
~~~

Vì **Pod không được tạo**, `kubectl logs` của Pod không tồn tại thường không giúp ích. Xem **ReplicaSet events** và **Cloud Audit Logs** thay thế.

## 9. Continuous Validation (CV): giám sát Pods đang chạy

**Continuous Validation** với **check-based platform policies** hiện là **Preview** theo tài liệu Google Cloud; khác hoàn toàn deployment policy ở phần 6.

| Đặc điểm | Deploy-time enforcement | CV |
|---|---|---|
| Policy | **Project-singleton policy** | Một hoặc nhiều **platform policies** |
| Thời điểm | Khi image được đưa vào Pod/triển khai | Kiểm tra định kỳ Pods đang chạy |
| Hành động vi phạm | Chặn hoặc dry-run theo enforcementMode | **Ghi vi phạm vào Cloud Logging, không kết thúc Pod** |
| Phạm vi image | `containers`, `ephemeralContainers`; không quét init/image volumes lúc deploy | Có kiểm tra **init/ephemeral containers** trong các lần đánh giá |
| Cập nhật policy | Tác động chính tới deployments mới | Có thể phát hiện Pod đang chạy không còn phù hợp |
| Tình trạng | Enforcement thông thường | Check-based CV **Preview** |

CV kiểm tra các Pods ít nhất mỗi **24 giờ**; với Pod ngắn hạn có thể có log sau khi Pod đã kết thúc. CV **không chặn runtime ngay lập tức** khi phát hiện lỗ hổng hoặc vi phạm.

Các checks được hỗ trợ theo tài liệu gồm: **trusted directory, image freshness, vulnerability, simple signing attestation, Sigstore signature, SLSA/provenance**. Tính khả dụng, quota và điều kiện kiểm tra phụ thuộc tính năng.

### 9.1. Ví dụ một CV platform policy

File **cv-policy.yaml** minh họa một bộ check vừa yêu cầu nguồn tin cậy vừa yêu cầu image mới hơn 30 ngày:

~~~yaml
gkePolicy:
  checkSets:
    - displayName: Company image quality
      checks:
        - displayName: Trusted Artifact Registry directory
          trustedDirectoryCheck:
            trustedDirPatterns:
              - asia-southeast1-docker.pkg.dev/shop-dev-001/containers
        - displayName: Image freshness
          imageFreshnessCheck:
            maxUploadAgeDays: 30
~~~

Chính sách 30 ngày ở đây chỉ minh họa kỹ thuật; với release dài hạn được support, policy “mọi image phải mới trong 30 ngày” có thể tạo cảnh báo quá mức và cần ngoại lệ hợp lệ.

### 9.2. Tạo platform policy bằng beta CLI

~~~bash
gcloud beta container binauthz policy create cv-review \
  --platform=gke \
  --policy-file=cv-policy.yaml \
  --project=shop-dev-001

gcloud beta container binauthz policy describe cv-review \
  --platform=gke \
  --project=shop-dev-001
~~~

Khác với lệnh **`gcloud container binauthz policy import`** ở phần 6, lệnh này tạo một **CV platform policy có tên**, không sửa project-singleton enforcement policy.

### 9.3. Bật CV mà không vô tình tắt enforcement

~~~bash
# Chỉ chạy khi đã được phép thay đổi cluster.
gcloud beta container clusters update gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --binauthz-evaluation-mode=POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE \
  --binauthz-policy-bindings=name=projects/shop-dev-001/platforms/gke/policies/cv-review
~~~

**Cảnh báo:** nếu dùng `--binauthz-evaluation-mode=POLICY_BINDINGS`, enforcement hiện có **sẽ bị tắt**, chỉ còn CV monitoring. Nếu chọn `PROJECT_SINGLETON_POLICY_ENFORCE`, CV đang cấu hình cũng có thể bị tắt. Vì vậy sau khi update phải readback mode và các bindings đang có, tránh làm mất một policy khác.

~~~bash
gcloud container clusters describe gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(binaryAuthorization)"
~~~

CV logs là bằng chứng để security/ops **tạo ticket, chặn release tiếp theo, sửa image và rollout lại**, không tự làm thao tác đó. Legacy continuous validation dùng project-singleton policy đã **deprecated**; nên sử dụng **check-based platform policies** khi triển khai mới.

## 10. Breakglass trong tình huống khẩn cấp

Nếu một release cần triển khai nhưng thiếu attestation và sự cố production nghiêm trọng, GKE có cơ chế **breakglass** để bỏ qua **BinAuthz enforcement** cho Pod đó. Đây là lối thoát khẩn có **audit log**, không phải cách sửa chính sách thiếu ổn định.

### 10.1. Label chính xác và vị trí trong Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: emergency-hotfix
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: emergency-hotfix
  template:
    metadata:
      labels:
        app: emergency-hotfix
        image-policy.k8s.io/break-glass: "true"
    spec:
      containers:
        - name: hotfix
          image: asia-southeast1-docker.pkg.dev/shop-dev-001/containers/hotfix@sha256:REPLACE_WITH_REAL_DIGEST
~~~

**Label phải nằm trong `spec.template.metadata.labels` của Pod template**, không chỉ ở `Deployment.metadata.labels`. Pod được gắn label `image-policy.k8s.io/break-glass: "true"` sẽ bypass enforcement BinAuthz và phát sinh breakglass audit event **dù image có vi phạm policy hay không**.

### 10.2. Runbook bắt buộc khi dùng

1. Incident commander xác nhận sự cố và lựa chọn không còn cách được phê duyệt nhanh hơn.
2. Review image digest, nguồn build và tác động; tuyệt đối không đưa một image không rõ nguồn chỉ vì “đang khẩn”.
3. Chỉ người có quyền thay đổi workload được duyệt mới được đặt label; giám sát sự kiện breakglass.
4. Áp dụng cho đúng workload, ghi **ticket, người phê duyệt, digest, thời điểm và lý do**.
5. Sau khi release hợp lệ được ký, tạo rollout mới **không còn breakglass label**.
6. Kiểm tra audit logs, đối chiếu CV và hoàn tất hậu kiểm.

**Lưu ý:** quyền tạo Pod trong cluster có thể đồng nghĩa người đó có thể đặt label breakglass. Do đó cần **RBAC, admission policies và quy trình giám sát** để chống lạm dụng. Breakglass chỉ bypass Binary Authorization; không bypass IAM, Pod Security Admission, Artifact Registry image pull permissions hay network policy.

## 11. Audit logs, cảnh báo và phản ứng với vi phạm

GKE có thể ghi các kết quả BinAuthz vào **Cloud Audit Logs**, gồm **blocked deployments, breakglass, dry-run violations, fail-open**. CV ghi vi phạm vào **Cloud Logging**, theo một luồng riêng.

### 11.1. Xem sự kiện deployment bị chặn

Ví dụ bộ lọc Logs Explorer:

~~~text
resource.type="k8s_cluster"
logName:"cloudaudit.googleapis.com%2Factivity"
(protoPayload.methodName="io.k8s.core.v1.pods.create" OR
 protoPayload.methodName="io.k8s.core.v1.pods.update")
protoPayload.response.status="Failure"
(protoPayload.response.reason="VIOLATES_POLICY" OR
 protoPayload.response.reason="Forbidden")
~~~

Tùy phiên bản cluster và nội dung sự kiện, thông tin **reason** có thể khác. Mở một log mẫu để xác nhận principal, resource, image reference và rule/attestor bị từ chối.

### 11.2. Giám sát breakglass, dry-run và fail-open

| Loại | Dấu hiệu log hữu ích | Phản ứng |
|---|---|---|
| **Breakglass** | `image-policy.k8s.io/break-glass` | Kiểm tra incident ticket, approver, Pod và thời hạn ngoại lệ |
| **Dry-run** | `imagepolicywebhook.image-policy.k8s.io/dry-run` | Phân tích tác động trước khi chuyển sang enforce |
| **Fail-open** | `image-policy.k8s.io/failed-open`, `imagepolicywebhook.image-policy.k8s.io/failed-open` hoặc biến thể | Đánh giá mức rủi ro khi backend kiểm tra tạm không khả dụng |
| **CV violation** | Check-based platform policy logs | Xác định Pod/image/check lỗi, tạo ticket và rollout bản sửa |

Ví dụ tìm sự kiện breakglass trong một tuần:

~~~bash
gcloud logging read \
  'resource.type="k8s_cluster" AND "image-policy.k8s.io/break-glass"' \
  --project=shop-dev-001 \
  --freshness=7d \
  --order=desc \
  --limit=50
~~~

**Không coi “không thấy log” là bằng chứng tuyệt đối không có vi phạm.** Kiểm tra project, time window, quyền Logs Viewer, exclusions, cấu hình logging và hình thức lọc trước khi kết luận.

### 11.3. Dashboard vận hành

Những tín hiệu nên đo:

- Tỷ lệ **deployments bị BinAuthz chặn** trên tổng các đợt triển khai.
- Số sự kiện **breakglass** và thời gian tồn tại của ngoại lệ.
- **Fail-open** và dry-run violations theo cluster/namespace/team.
- **CV findings** theo image digest, loại check và mức ưu tiên.
- Thời gian từ build đến attestation, số release bị trì hoãn do thiếu chữ ký.
- **Pod rollout readiness**, error rate và rollback duration để đo tác động lên SLO người dùng.

Đặt alerts có owner và runbook thay vì tự động xóa mọi Pod bị CV cảnh báo: CV violation có thể đòi hỏi điều tra rủi ro, fix bản build, hoặc lên lịch rollout an toàn.

## 12. Phân tách trách nhiệm và bảo mật chuỗi cung ứng

### 12.1. Không để cùng một principal vừa sửa chính sách vừa ký release

| Principal / nhóm | Quyền cần thiết | Không nên tự động có |
|---|---|---|
| **Build runner** | Đọc source, build/test, push Artifact Registry | Quyền chỉnh BinAuthz policy, ký release độc lập |
| **Security/release approver** | Quyền ký KMS và tạo attestation trong phạm vi được duyệt | Quyền sửa image tùy ý sau khi ký |
| **Platform policy admin** | Binary Authorization Policy Editor, review rule | KMS signer quyền rộng |
| **GKE deployer** | Quyền cập nhật Kubernetes workloads qua IAM/RBAC | Artifact Registry Admin hoặc KMS sign |
| **GKE image pull identity** | Artifact Registry Reader | Quyền ký hoặc chỉnh policy |
| **Auditor** | Policy Viewer, Cloud Logging Viewer | Quyền phá bỏ hoặc thay đổi gate |

Để dùng **Cloud KMS asymmetric signing**, principal ký cần quyền `cloudkms.cryptoKeyVersions.useToSign` qua role phù hợp được cấp ở key cần dùng. Để tạo attestation còn cần quyền trên Artifact Analysis occurrence và tài nguyên liên quan; trong mô hình nhiều project, service agent của BinAuthz cần quyền đọc attestors/notes/occurrences theo hướng dẫn chính thức.

### 12.2. Registry, chữ ký và admission là ba ranh giới khác nhau

- **Artifact Registry IAM:** ai được push/pull image.
- **KMS/attestor:** ai có thể ký phê duyệt một image digest.
- **BinAuthz policy:** chữ ký nào được GKE tin khi deployment.

Nếu một image bị xoá hoặc runtime pull identity thiếu quyền, Pod có thể rơi vào **ImagePullBackOff** dù đã vượt qua BinAuthz. Ngược lại, nếu có quyền pull nhưng thiếu attestation, Pod có thể bị chặn tại admission. Mỗi lỗi cần xử lý tại đúng lớp.

### 12.3. Tăng cường policy GKE

Kết hợp:

1. **Pin image digests** để rollout chính xác.
2. **Vulnerability scanning, SBOM và build provenance**, rồi chỉ ký khi đạt điều kiện.
3. **Pod Security Admission** hoặc **Policy Controller** cho privileged, hostPath, capabilities, resource limits hoặc nguồn registry theo chính sách.
4. **Workload Identity Federation for GKE** để ứng dụng Java đọc Cloud Storage/Secret Manager mà không cần static keys.
5. **NetworkPolicy, private clusters/VPC và IAM least privilege** để giảm hậu quả khi container bị chiếm quyền.
6. **Backups và khả năng rollback** cho service/data; BinAuthz không khôi phục ứng dụng sau deploy lỗi.

Với **Cloud Run**, Binary Authorization cũng có tích hợp nhưng **cú pháp cấu hình service và mô hình deploy khác GKE**; không dùng nguyên các lệnh `gcloud container clusters update` cho Cloud Run.

## 13. Sự cố thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Bật BinAuthz mà image lạ vẫn chạy | Policy mặc định `ALWAYS_ALLOW` hoặc `DRYRUN` | Export policy, kiểm tra evaluation/enforcement modes |
| Pod bị chặn `Denied by attestor` | Image digest chưa có attestation hoặc signer/public key không khớp | `attestations list`, attestor describe, image digest |
| Chữ ký có nhưng deployment vẫn bị chặn | Policy đòi **nhiều** attestors, sai cluster rule hoặc mismatch digest | `requireAttestationsBy`, clusterAdmissionRules, digest chính xác |
| Image tag `v1` deploy sai version | Tag bị đổi, build/push race | Pin digest, kiểm tra registry manifest |
| Deployment object tạo được nhưng Pods không xuất hiện | ReplicaSet bị admission từ chối | `kubectl describe rs`, Events, Cloud Audit Logs |
| Pod tạo được nhưng `ImagePullBackOff` | Node/pull identity thiếu Artifact Registry Reader, digest không tồn tại | `kubectl describe pod`, registry IAM |
| Pod đã chạy trước khi policy siết vẫn còn chạy | Enforce chủ yếu tại deployment mới | CV, plan rollout/replace phù hợp |
| CV logs có lỗi nhưng Pod vẫn phục vụ | **CV không terminate Pods** | Xác định check và đưa fix qua release process |
| Bật CV xong enforcement mất tác dụng | Dùng mode `POLICY_BINDINGS` thay vì kết hợp | Describe cluster evaluation mode |
| Cluster/system workloads lỗi sau policy change | Tắt `globalPolicyEvaluationMode` hoặc allowlist thiếu system images | Rollback policy, bật lại system policy |
| Không truy vấn được attestation | Thiếu quyền đọc Artifact Analysis/attestor cross-project | IAM service agent, attestor note/resource |
| Ghi attestation lỗi KMS | Thiếu `useToSign`, sai key version, key disabled | KMS IAM, algorithm, signing key state |
| Không thấy audit event breakglass | Log filter/project/time sai hoặc label không nằm trong Pod template | `image-policy.k8s.io/break-glass`, Pods, Cloud Audit Logs |
| `initContainer` không bị chặn lúc deploy | **Giới hạn documented của deploy-time enforcement** | Pod Security/Policy Controller và CV |
| Fail-open event | BinAuthz backend unavailable/timeout | Điều tra hệ thống kiểm soát, kiểm kê Pods được admit |

### 13.1. Quy trình chẩn đoán có thứ tự

1. Xem **`kubectl get events`**, `describe deployment/replicaset/pod` để biết Pod có được tạo không.
2. Nếu bị admission từ chối, xác nhận **policy project**, **cluster evaluation mode**, **rule áp dụng** và **attestor list**.
3. Đối chiếu image `@sha256:...` từ manifest với **attestation artifact URL**, không so sánh mỗi tag.
4. Kiểm tra attestor public key, KMS key version và quyền Artifact Analysis nếu ký/xác minh lỗi.
5. Nếu Pod được tạo nhưng pull/runtime thất bại, chuyển sang **Artifact Registry, node identity, Kubernetes scheduling và ứng dụng Java**.
6. Tìm Cloud Audit Logs tương ứng; xem có breakglass, dry-run hay fail-open.
7. Chỉ chỉnh policy sau khi review ảnh hưởng; thử trên staging rồi áp vào production theo change control.

## 14. Tình huống tổng hợp: nền tảng Java thương mại điện tử

Công ty **Thịnh An** có:

- `orders-api`, `payment-adapter` và `inventory-worker` trên **GKE**, xây dựng bằng Cloud Build.
- Images ở **Artifact Registry**; dữ liệu giao dịch trong **Cloud SQL**; ảnh sản phẩm trong **Cloud Storage**.
- Cluster production sử dụng BinAuthz enforce; cluster thử nghiệm dùng dry-run trong giai đoạn chuyển đổi.
- Nhóm security độc lập giữ **Cloud KMS signing key**; nhóm platform quản trị policy.

### 14.1. Luồng release được kiểm soát

~~~mermaid
flowchart TB
    A["Commit + review"] --> B["Cloud Build: tests + SBOM + scan"]
    B --> C["Push image vào Artifact Registry"]
    C --> D["Ghi nhận digest bất biến"]
    D --> E["Release approval / KMS attestation"]
    E --> F["GKE deploy theo digest"]
    F --> G{"BinAuthz admission"}
    G -->|Pass| H["Rollout + readiness + SLO"]
    G -->|Fail| I["Block + Audit Log + ticket"]
    H --> J["CV: giám sát image đang chạy"]
    J -->|Finding| K["Investigation + bản release sửa"]
~~~

### 14.2. Chọn chính sách theo giai đoạn

| Giai đoạn | Enforcement | CV | Tiêu chí lên giai đoạn sau |
|---|---|---|---|
| **Staging** | `REQUIRE_ATTESTATION + DRYRUN` | Có thể bật Preview trong lab | Không còn false positives làm tắc pipeline hợp lệ |
| **Canary production** | `REQUIRE_ATTESTATION + ENFORCED` trên cluster/đường triển khai được chọn | Check-only theo policy phù hợp | Rollout không bị chặn ngoài dự kiến; readiness đạt |
| **Production ổn định** | Enforced toàn phạm vi workload đã duyệt | Theo dõi vi phạm và kết quả checks | Mọi image mới được pin/attested, có on-call/rollback |
| **Incident khẩn cấp** | Breakglass chỉ với approver và audit | CV tiếp tục ghi findings | Xóa exception sau hotfix được ký |

### 14.3. Tính sẵn sàng và chi phí

- **SLO:** thiếu attestation có thể cản trở scale out, rolling update hoặc tự phục hồi sau node failure nếu Pod mới không được admit. Phải đảm bảo các image đang deploy đã được attested và vẫn có thể pull.
- **Độ tin cậy:** dùng multi-replica, readiness probes, PodDisruptionBudget và rollback digest; BinAuthz không giúp Java API chịu lỗi Cloud SQL.
- **Chi phí:** tính GKE/Artifact Registry, Cloud KMS signing operations, Artifact Analysis/attestation storage, Binary Authorization service, logging/monitoring và scanning theo bảng giá hiện hành. **CV Preview** có điều kiện giá/khả dụng riêng; không đưa một giá cố định không được xác minh.
- **Vận hành:** ghi policy version và image digest vào release record, hạn chế người đổi policy trong giờ cao điểm.

## 15. Bài tập và đáp án định hướng

### Bài tập A — Phân biệt dry-run và enforce

Cho policy:

~~~yaml
defaultAdmissionRule:
  evaluationMode: ALWAYS_DENY
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
~~~

**Hỏi:** Một Pod không thuộc exemption có bị chặn không? **Đáp án:** Không do rule này, vì dry-run cho phép deploy nhưng ghi vi phạm. Nếu đổi sang `ENFORCED_BLOCK_AND_AUDIT_LOG`, Pod sẽ bị chặn.

### Bài tập B — Kiểm tra digest và attestation

Image `orders-api:v2` lúc ký trỏ tới digest **A**; sau đó publisher đổi tag `v2` sang digest **B**. Policy yêu cầu attestor release-approver.

**Hỏi:** Image B có tự được chấp thuận không? **Đáp án:** Không. Attestation xác minh digest A không đồng nghĩa có attestation cho B. Dùng digest trong manifest và xác nhận attestation cho đúng image được deploy.

### Bài tập C — Hai attestors

Rule:

~~~yaml
evaluationMode: REQUIRE_ATTESTATION
enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
requireAttestationsBy:
  - projects/shop-dev-001/attestors/ci-build
  - projects/shop-dev-001/attestors/security-approved
~~~

**Hỏi:** Chỉ có attestation của ci-build có đủ không? **Đáp án:** Không, cần attestation hợp lệ từ **tất cả** attestors được liệt kê. Thiếu một attestor là vi phạm rule.

### Bài tập D — Triệu chứng sau khi bật CV

Kỹ sư cập nhật GKE cluster bằng:

~~~text
--binauthz-evaluation-mode=POLICY_BINDINGS
~~~

**Hỏi:** Vấn đề có thể xảy ra? **Đáp án:** Mode này chỉ bật CV monitoring, có thể **vô tình tắt project-singleton enforcement**. Nếu cần cả hai, dùng `POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE` và giữ đúng bindings.

### Bài tập E — Một Pod có initContainer không đáng tin

**Hỏi:** Deploy-time enforcement có chắc chặn image trong `initContainers` không? **Đáp án:** Không; tài liệu GKE nêu deploy-time chỉ kiểm tra `containers` và `ephemeralContainers`. Dùng thêm controls Kubernetes/Pod Security và giám sát CV theo phạm vi được hỗ trợ.

### Bài tập F — Tình huống khẩn cấp

Một sự cố production cần hotfix ngay. Image đã được build nhưng attestation pipeline chậm. Nhóm vận hành muốn thêm `image-policy.k8s.io/break-glass: "true"`.

**Hãy viết checklist:** ai phê duyệt, digest nào, tác động gì, ai có quyền thay Pod template, log ở đâu, khi nào gỡ label và ký lại. **Đáp án định hướng:** Breakglass chỉ dùng có phê duyệt, ticket, giám sát và thời gian hết hạn vận hành; label phải ở **Pod template**, không phải chỉ Deployment metadata.

### Bài tập G — Thiết kế chính sách cho hai team

Team payment có yêu cầu **security attestation**, team reporting chỉ cần build origin trong giai đoạn thử nghiệm.

**Yêu cầu:** đề xuất phân vùng bằng project/cluster/namespace/KSA, IAM signer, policy dry-run/enforce và kiểm thử âm tính. **Định hướng:** tách trust boundary khi có thể, không dùng exemptions quá rộng, không cho build runner tự ký bằng khóa security, và chạy kiểm thử lỗi attestor/digest trên staging.

## 16. Ghi nhớ và tài liệu tham khảo

**Tám điểm chốt:**

1. **Binary Authorization** kiểm soát **image ở admission**, không xác nhận mã nguồn hay runtime hoàn toàn an toàn.
2. **Digest cố định** quan trọng hơn tag mutable; **attestation là xác nhận/phê duyệt có chữ ký** đối với image digest.
3. **Project-singleton policy** dùng để chặn lúc triển khai; bật cluster mà giữ **ALWAYS_ALLOW** không tự tạo lớp an toàn.
4. **DRYRUN_AUDIT_LOG_ONLY** cho triển khai và ghi vi phạm; **ENFORCED_BLOCK_AND_AUDIT_LOG** chặn vi phạm.
5. **Attestor** là authority xác minh; tách người ký/phê duyệt khỏi người build và quản trị policy.
6. **CV platform policies** (Preview) giám sát các Pods đang chạy; CV **ghi log, không kill Pods**.
7. **Breakglass** dùng Pod label có audit log, chỉ dành cho sự cố cần ngoại lệ đã phê duyệt.
8. Kết hợp **IAM/RBAC, Pod Security, registry protection, scanning, CI/CD, monitoring và rollback** để có lớp bảo vệ đầy đủ.

**Tài liệu Google Cloud chính thức:**

1. [Binary Authorization overview](https://docs.cloud.google.com/binary-authorization/docs/overview) — mô hình enforce và attestation.
2. [Concepts and policies](https://docs.cloud.google.com/binary-authorization/docs/key-concepts) — các loại policy, attestor và signature.
3. [Set up Binary Authorization for GKE](https://docs.cloud.google.com/binary-authorization/docs/setting-up) — phạm vi enforcement và các bước thiết lập.
4. [Configure policy using gcloud](https://docs.cloud.google.com/binary-authorization/docs/configuring-policy-cli) — evaluation/enforcement, cluster/namespace/KSA rules.
5. [Policy YAML reference](https://docs.cloud.google.com/binary-authorization/docs/policy-yaml-reference) — cú pháp rule và exemptions.
6. [Get started using gcloud with GKE](https://docs.cloud.google.com/binary-authorization/docs/getting-started-cli) — tạo attestor, Cloud KMS và attestation.
7. [Create attestations](https://docs.cloud.google.com/binary-authorization/docs/making-attestations) — ký image digest và xác minh.
8. [Built by Cloud Build attestor](https://docs.cloud.google.com/binary-authorization/docs/deploy-cloud-build) — chứng thực image từ Cloud Build.
9. [Continuous Validation overview](https://docs.cloud.google.com/binary-authorization/docs/overview-cv) — Preview, phạm vi và giới hạn.
10. [Quickstart continuous validation](https://docs.cloud.google.com/binary-authorization/docs/quickstart-cv) — platform policy và cluster binding.
11. [Use breakglass](https://docs.cloud.google.com/binary-authorization/docs/using-breakglass) — Pod label và audit.
12. [View Binary Authorization GKE audit logs](https://docs.cloud.google.com/binary-authorization/docs/viewing-audit-logs) — blocked, breakglass, fail-open, dry-run.
