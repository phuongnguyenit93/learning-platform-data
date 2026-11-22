# Bảo mật image, admission policy và workload AKS

Một ứng dụng chạy trên **Azure Kubernetes Service (AKS)** có thể được triển khai thành công về mặt YAML nhưng vẫn chứa image có lỗ hổng, chạy bằng quyền root, gắn hostPath nhạy cảm, giữ mật khẩu trong biến môi trường hoặc mở kết nối mạng rộng hơn nhu cầu. Các cấu hình này tạo rủi ro dù cluster đã được triển khai bằng dịch vụ Kubernetes do Azure quản lý.

Bảo mật AKS vì vậy phải được tổ chức thành nhiều lớp: **kiểm soát nguồn image**, **kiểm tra image trong pipeline**, **xác minh image và policy tại thời điểm Kubernetes nhận yêu cầu**, **giảm quyền của Pod**, **giới hạn danh tính/mạng**, rồi **giám sát lúc chạy**. Một công cụ đơn lẻ không thay thế toàn bộ quy trình.

Bài học thuộc chương **Vận hành AKS** của module **CLOUD_PROVIDERS_AZURE**. Trong bối cảnh người học đã tiếp cận subscription, resource group, Microsoft Entra ID, mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu trên Azure, chúng ta xây dựng một mô hình vận hành có thể ngăn các bản triển khai không đạt chuẩn đi vào cluster mà vẫn có đường xử lý ngoại lệ, rollback và quan sát rõ ràng.

> **Nguyên tắc quan trọng:** Quét image chỉ cho biết những vấn đề mà bộ quét phát hiện tại thời điểm đánh giá. **Admission policy** kiểm soát yêu cầu tạo/cập nhật tài nguyên Kubernetes. **Runtime protection** phát hiện, ngăn chặn hoặc hỗ trợ ứng phó với hành vi khi container đang chạy. Ba lớp không đồng nghĩa và phải phối hợp với nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả những rủi ro supply chain của container: image giả mạo, tag bị ghi đè, dependency có CVE, secrets nằm trong image và build không tái lập.
2. Thiết kế chuỗi **source → build → scan → sign/attest → registry → admission → runtime**.
3. Phân biệt Azure Container Registry (ACR), Microsoft Defender for Containers, Azure Policy add-on, Pod Security Admission (PSA), Gatekeeper và các admission controller khác.
4. Giải thích **mutating/validating admission**, các policy **Audit/Deny/Warn**, phạm vi áp dụng và hậu quả nếu webhook không khả dụng.
5. Xây dựng workload AKS tuân thủ các kiểm soát cơ bản: non-root, cấm privilege escalation, giảm Linux capabilities, seccomp, read-only root filesystem, resource limits.
6. Áp dụng các mức **Privileged**, **Baseline**, **Restricted** của Kubernetes Pod Security Standards theo namespace và thử chính sách từ audit/warn trước khi enforce.
7. Cấu hình nguyên tắc image chỉ được lấy từ registry được duyệt; hiểu sự khác biệt giữa **allowed registry**, **digest pinning** và **signature verification**.
8. Tách danh tính kéo image của kubelet khỏi danh tính workload trong Pod; áp dụng least privilege và Microsoft Entra Workload ID khi phù hợp.
9. Phân biệt RBAC, NetworkPolicy, Kubernetes Secrets và admission policies.
10. Chẩn đoán trường hợp Deployment bị từ chối, Pod không tạo được, ImagePullBackOff hoặc container chạy nhưng thiếu quyền; lập runbook và báo cáo độ phủ chính sách.

## 2. Mô hình đe dọa: cần bảo vệ những gì?

Giả sử hệ thống Orders có các thành phần:

- Source code của **orders-api** và **orders-worker**.
- Build pipeline tạo container image.
- ACR chứa các image nội bộ.
- AKS cluster có namespace development, staging và production.
- Azure SQL Database, Azure Storage và Key Vault là dịch vụ phụ thuộc.
- Azure Monitor/Log Analytics và Microsoft Defender for Cloud phục vụ quan sát, phát hiện rủi ro.

Các kịch bản đáng quan tâm:

| Rủi ro | Đường tấn công/sự cố | Hậu quả |
|---|---|---|
| Dependency có CVE | Image dùng thư viện/base image chưa vá | Kẻ tấn công khai thác ứng dụng hoặc hệ điều hành trong container |
| Image không tin cậy | Pipeline/Deployment tham chiếu registry công khai không kiểm soát | Code chưa được kiểm duyệt chạy trên node |
| Mutable tag | Tag production bị ghi đè thành nội dung khác | Hai lần deploy cùng tag không còn bảo đảm cùng artifact |
| Secret trong image | Token được đưa vào Dockerfile, layer hoặc Git | Credential có thể lộ ngay cả khi file cuối bị xóa |
| Pod quyền cao | privileged, hostPID, hostPath nhạy cảm, root + capabilities rộng | Tăng nguy cơ ảnh hưởng node và các workload khác |
| ServiceAccount rộng quyền | Pod có thể đọc Secret, sửa Deployment, xem tài nguyên không cần thiết | Di chuyển ngang trong cluster hoặc leo thang quyền |
| Network quá mở | Pod được phép gọi mọi namespace/Internet | Di chuyển ngang, exfiltration dữ liệu |
| Thiếu guardrails | Manifest không đạt chuẩn vẫn được API server nhận | Sai cấu hình lan rộng qua CI/CD |
| Runtime không được quan sát | Container có tiến trình/kết nối bất thường nhưng không có cảnh báo | Thời gian phát hiện và khắc phục kéo dài |

Cách bảo vệ hợp lý phải bắt đầu từ **threat model và trust boundary**, không chỉ từ việc bật một add-on.

## 3. Kiến trúc phòng thủ nhiều lớp

~~~mermaid
flowchart LR
    SRC["Git source + dependency"] --> CI["CI: build, test, SCA, SBOM"]
    CI --> SCAN["Quét image + kiểm tra policy"]
    SCAN --> SIGN["Ký/attest artifact theo digest"]
    SIGN --> ACR["Azure Container Registry"]
    ACR --> ADM["Admission policy AKS"]
    ADM --> NODE["Node/kubelet pull image"]
    NODE --> POD["Pod chạy với quyền tối thiểu"]
    POD --> OBS["Logs, metrics, Defender, điều tra"]
    ID["Entra ID / Workload Identity"] -. "Định danh và quyền" .-> POD
    NET["NetworkPolicy / VNet / firewall"] -. "Giới hạn traffic" .-> POD
~~~

### 3.1. Mỗi lớp trả lời một câu hỏi khác nhau

| Lớp | Câu hỏi |
|---|---|
| Source & dependency | Mã nguồn và thư viện có đến từ nguồn được tin cậy không? |
| Build & image scan | Artifact có CVE, secret, package nguy hiểm hay vấn đề cấu hình đã biết không? |
| Registry | Ai được push/pull/xóa image? Artifact có được lưu, bảo vệ và kiểm toán không? |
| Provenance & signature | Image đang triển khai có đúng artifact từ quy trình build được tin cậy không? |
| Admission policy | Manifest mới có vi phạm quy tắc deployment của cluster không? |
| Pod/runtime hardening | Nếu ứng dụng bị khai thác, quyền hạn của nó bị giới hạn đến đâu? |
| Kubernetes/Azure IAM | Pod và người vận hành có đúng quyền API/data plane không? |
| Network | Pod có thể kết nối đến những đích nào? |
| Runtime monitoring | Có phát hiện hành vi bất thường, lỗ hổng mới hay policy drift không? |

**Bài toán không kết thúc khi admission cho phép Pod.** Mã có thể chứa lỗ hổng chưa được phát hiện, ứng dụng có thể lỗi logic hoặc một lỗ hổng mới được công bố sau khi image đã chạy.

## 4. Image là artifact phải quản lý như một release

Một image OCI thường gồm manifest, các filesystem layers, cấu hình image và metadata. Một tên image gồm:

~~~text
<registry-login-server>/<repository>:<tag>

Ví dụ:
acrordersprod.azurecr.io/orders/orders-api:2.4.1
~~~

Một tham chiếu theo digest:

~~~text
acrordersprod.azurecr.io/orders/orders-api@sha256:<digest-thuc-te>
~~~

Trong đó:

- **Registry** quyết định nơi tìm artifact.
- **Repository** xác định nhóm image.
- **Tag** là tên thân thiện, nhưng có thể thay đổi nếu registry cho phép ghi đè.
- **Digest** định danh nội dung manifest của image; giúp xác định artifact chính xác đã được kiểm thử.

### 4.1. Vì sao tag latest không đủ?

Tình huống:

1. Pipeline A push image an toàn lên **orders-api:latest**.
2. Một pipeline hoặc tài khoản khác ghi đè cùng tag.
3. Pod mới pull tag đó nhưng nhận nội dung khác.
4. Pod cũ vẫn đang dùng image cache/manifest trước đó.

Kết quả: cùng cấu hình YAML có thể dẫn đến các phiên bản chạy khác nhau. Dùng release tag bất biến và **pin digest** khi cần tính tái lập.

**imagePullPolicy: Always** buộc kubelet kiểm tra image reference khi khởi động container, nhưng **không làm tag trở thành bất biến** và **không thay thế chữ ký số**.

### 4.2. SBOM và provenance

- **SBOM (Software Bill of Materials):** danh mục thành phần, thư viện và phiên bản có trong artifact.
- **Build provenance:** bằng chứng nguồn code, workflow, builder và mối liên hệ với digest được phát hành.
- **Image signature/attestation:** chứng cứ mật mã hoặc tuyên bố được ký về artifact, dùng trong một quy trình xác minh tin cậy.

Không có SBOM không đồng nghĩa image chắc chắn độc hại; nhưng không biết thành phần khiến việc điều tra CVE, chuẩn bị bản vá và trả lời kiểm toán khó khăn hơn.

### 4.3. Image signed khác image scanned

Một image **đã ký** có thể vẫn có CVE: chữ ký xác nhận nguồn và tính toàn vẹn theo cơ chế ký, không bảo đảm code an toàn tuyệt đối. Một image **đã quét** có thể vẫn bị thay thế nếu Deployment dùng tag mutable và không kiểm chứng digest/provenance.

Khi yêu cầu bảo mật cao, quy trình cần cả **kiểm tra vulnerability** và **xác minh nguồn gốc/nội dung image**.

## 5. Azure Container Registry: kiểm soát đầu vào image

ACR là private registry do Azure quản lý, được dùng để lưu image và artifact OCI cho AKS.

### 5.1. Phân tách quyền

| Chủ thể | Quyền cần có | Không nên cấp mặc định |
|---|---|---|
| CI/CD của Orders | Push image vào repository Orders theo permission mode hỗ trợ | Owner toàn subscription |
| AKS kubelet identity | Pull image cần deploy | AcrPush, registry admin |
| Security scanner | Đọc artifact/metadata cần quét | Quyền ghi/xóa không cần thiết |
| Developer | Quyền đọc/test theo môi trường | Quyền ghi đè release production |
| Ứng dụng trong Pod | Quyền gọi Storage/SQL/Key Vault theo nghiệp vụ | Quyền quản trị registry hoặc AKS |

Với ACR ở chế độ **RBAC Registry Permissions**, kubelet thường được cấp role **AcrPull**. Với **RBAC Registry + ABAC Repository Permissions**, cần role như **Container Registry Repository Reader** và có thể áp dụng điều kiện theo repository. Lệnh **az aks --attach-acr** không thay cho việc cấp role repository phù hợp trong chế độ ABAC.

### 5.2. Kiểm tra thông tin ACR và AKS

Các lệnh **chỉ đọc**, dùng đúng subscription và tài nguyên được phép:

~~~bash
az login
az account set --subscription "<subscription-id>"

ACR_NAME="<acr-name>"
AKS_RG="<aks-resource-group>"
AKS_NAME="<aks-cluster-name>"

az acr show \
  --name "$ACR_NAME" \
  --query "{name:name,loginServer:loginServer,sku:sku.name,id:id}" \
  --output json

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,identity:identity,kubelet:identityProfile.kubeletidentity}" \
  --output json
~~~

Những lệnh này **không chứng minh node kéo image thành công**. Cần kiểm tra đúng identity, role assignment, ACR permission mode, đường mạng và Pod Events.

### 5.3. Registry private không tự chặn được image ngoài

Việc AKS có kết nối tới ACR không đồng nghĩa Deployment chỉ được phép tham chiếu ACR đó. Một developer có quyền tạo Pod vẫn có thể khai báo image public nếu **chưa có admission guardrail và network controls phù hợp**.

Để giới hạn nguồn image, cần policy cho phép danh sách registry/repository theo quy định; kiểm tra cả **containers**, **initContainers** và **ephemeralContainers** theo phạm vi khả thi.

## 6. Quét image trước và sau khi triển khai

### 6.1. Quét ở pipeline

Trong CI/CD, quét những thành phần sau khi build và trước khi phát hành:

- Thư viện ứng dụng, dependency trực tiếp và gián tiếp.
- OS packages trong base image và image cuối.
- Secrets lộ trong source, build context hoặc filesystem layers.
- Cấu hình Dockerfile nguy hiểm khi có công cụ kiểm tra tương ứng.
- Policy về license và nguồn package theo yêu cầu tổ chức.
- Image manifest, architecture, provenance và SBOM.

Công cụ quét có thể là Microsoft Defender for Cloud/Defender for Containers theo tính năng hỗ trợ, Trivy, Grype hoặc công cụ doanh nghiệp. Đội ngũ phải quy định rõ phiên bản, database lỗ hổng và tiêu chí release thay vì chỉ viết “đã scan”.

### 6.2. Lựa chọn ngưỡng chặn release

Ví dụ quy định minh họa:

| Phát hiện | Hành động gợi ý | Lưu ý |
|---|---|---|
| Critical có bản vá, có đường khai thác liên quan | Block release, sửa và rebuild | Cần đối chiếu triage thực tế |
| High chưa có bản vá nhưng workload phơi lộ trực tiếp | Security review, mitigation, exception có hạn | Không tự xem scanner là quyết định cuối cùng |
| Medium trong dependency không dùng tại runtime | Theo dõi/đánh giá reachability | Cần bằng chứng, không bỏ qua vô thời hạn |
| Hard-coded secret | Block, revoke/rotate secret, rebuild image | Xóa file ở layer cuối chưa đủ để loại secret khỏi lịch sử layer |
| Base image không rõ nguồn | Block hoặc yêu cầu chứng minh trust | Cân nhắc mirror image được duyệt |

Không áp dụng quy tắc “mọi CVE High đều bị chặn bất kể hoàn cảnh” nếu tổ chức chưa đánh giá rủi ro, false positives và phương án xử lý ngoại lệ. Nhưng cũng không **bỏ qua mọi cảnh báo chỉ để pipeline xanh**.

### 6.3. Scan là hoạt động liên tục

Một image đã vượt kiểm tra hôm qua có thể xuất hiện CVE mới hôm nay. Bởi vậy cần:

1. Theo dõi phát hiện lỗ hổng mới trên images trong registry và workload đang chạy theo tính năng hỗ trợ.
2. Xác định image digest và Pod/namespace dùng image đó.
3. Ưu tiên theo mức độ nghiêm trọng, mức phơi lộ, khả năng khai thác và độ quan trọng nghiệp vụ.
4. Rebuild với base image/dependency đã vá.
5. Phát hành lại bằng digest mới.
6. Kiểm tra rollback, application health và cập nhật bằng chứng xử lý.

**Defender for Containers** có những khả năng đánh giá lỗ hổng image, tư thế bảo mật và cảnh báo runtime theo gói/khu vực/điều kiện kết nối; không tự đồng nghĩa rằng **mọi image có CVE sẽ bị Kubernetes admission chặn**. Muốn chặn cần chính sách và công cụ enforcement được thiết lập rõ.

## 7. Ký image và xác minh provenance

Một đường kiểm soát phù hợp:

~~~mermaid
flowchart LR
    C["Commit được review"] --> B["Build được kiểm soát"]
    B --> T["Test + scan + SBOM"]
    T --> D["Digest bất biến"]
    D --> S["Sign/attest digest"]
    S --> ACR["ACR"]
    ACR --> V["Admission verify signature/provenance"]
    V --> AKS["Pod được phép chạy"]
~~~

### 7.1. Xác minh ở đâu?

- **Trước push:** xác minh source, dependencies và quá trình build.
- **Sau push:** lấy image digest thật từ registry, lưu metadata provenance và chữ ký tương ứng.
- **Trước deploy:** pipeline hoặc admission kiểm tra release có nằm trong danh sách được phép và có chữ ký/attestation hợp lệ.
- **Sau deploy:** truy xuất digest đang chạy, so sánh với artifact đã được phê duyệt.

Một công cụ như **Sigstore Cosign** có thể ký/xác minh OCI image. Nhưng **ACR lưu image không tự khiến Kubernetes mặc định kiểm tra chữ ký ở admission**. Nếu muốn chặn image không có chữ ký, phải triển khai giải pháp xác minh phù hợp như một admission controller/policy engine được hỗ trợ và quản trị trusted keys/identities.

### 7.2. Ví dụ lệnh verify minh họa

Giả sử tổ chức dùng Cosign ở chế độ khóa được phê duyệt:

~~~bash
# IMAGE_DIGEST phải là tham chiếu registry/repository@sha256:... có thật
# cosign.pub là khóa công khai được quản trị và phân phối tin cậy
cosign verify --key cosign.pub "$IMAGE_DIGEST"
~~~

Lệnh trên là **ví dụ kiểm tra bằng công cụ**, không phải bước triển khai tự động trong bài. Xác minh keyless signature thường cần ràng buộc certificate identity và OIDC issuer, cùng chính sách trust riêng; không mặc định tất cả chữ ký Cosign hợp lệ đều tương đương với build nội bộ được phê duyệt.

### 7.3. Cách chính sách chữ ký có thể bị thiết kế sai

- Chỉ kiểm tra có chữ ký mà không kiểm tra **ai ký**.
- Dùng key công khai lấy từ cùng repository không đáng tin cậy với image.
- Không pin digest trong Deployment nhưng lại xác minh một digest khác.
- Cho phép bypass admission không có audit.
- Không bảo vệ khóa ký hoặc danh tính CI/CD.
- Không có quy trình revoke/rotate trust khi signer bị xâm phạm.

**Allowed registry**, **digest pinning**, **signature validation** và **vulnerability scanning** là bốn điều kiện khác nhau. Chỉ bật một trong số đó chưa đủ cho chuỗi cung ứng an toàn.

## 8. Admission control của Kubernetes hoạt động thế nào?

Một yêu cầu tạo/cập nhật Pod được gửi đến **Kubernetes API server**. Sau xác thực và phân quyền, các admission controller được cấu hình có thể điều chỉnh hoặc kiểm tra đối tượng trước khi ghi vào API.

~~~mermaid
flowchart LR
    U["kubectl / GitOps / CI"] --> AUTH["Authentication + Authorization"]
    AUTH --> MUT["Mutating admission<br/>nếu có"]
    MUT --> VAL["Validating admission + policy"]
    VAL --> Q{"Hợp lệ?"}
    Q -->|Không| DENY["Từ chối API request"]
    Q -->|Có| STORE["Lưu object → scheduler → kubelet"]
    STORE --> RUN["Pod chạy"]
~~~

Sơ đồ mô tả luồng logic rút gọn; Kubernetes có nhiều admission plugin và webhook với thứ tự, cơ chế gọi lại và điều kiện riêng.

### 8.1. Mutating admission

Có thể bổ sung hoặc điều chỉnh một số thuộc tính trước khi object được lưu, ví dụ inject labels, một sidecar hoặc default cấu hình được chính sách cho phép.

**Rủi ro:** thay đổi ngầm có thể làm manifest thực tế khác manifest trong Git. Cần xem resource sau admission và ghi rõ chính sách áp dụng.

### 8.2. Validating admission

Kiểm tra yêu cầu; nếu vi phạm điều kiện enforce, API server từ chối thao tác.

Ví dụ:

- Image không đến từ registry được phê duyệt.
- Pod khai báo **privileged: true**.
- Không có cấu hình seccomp, allowPrivilegeEscalation hoặc resource limits theo quy định.
- HostPath mount bị cấm.
- Deployment thiếu labels quản trị bắt buộc.
- Workload chạy trong namespace không được cấp phép.

### 8.3. Admission không phải runtime security

Admission kiểm tra đối tượng tại thời điểm nhận yêu cầu. Nó **không tự theo dõi mọi syscall** sau khi container chạy; cũng không tự xóa hoặc sửa những Pod đã tồn tại chỉ vì ngày hôm sau bạn tăng policy.

Muốn đánh giá tài nguyên hiện hữu cần audit/background scan, inventory hoặc controller phù hợp. Muốn phát hiện runtime behavior cần telemetry/runtime security riêng.

### 8.4. Controller là một mắt xích quan trọng

Nếu bạn tạo một Deployment, API server có thể chấp nhận Deployment nhưng **Pod template sau đó bị admission từ chối khi ReplicaSet tạo Pod**. Khi ấy:

- Deployment resource vẫn tồn tại.
- ReplicaSet không tạo được Pod mong muốn.
- Events có thể báo **FailedCreate** và policy violation.
- **kubectl rollout status** timeout.

Do đó, kiểm tra thành công của **kubectl apply** chưa đủ. Cần xác minh rollout, Pod status và Events.

## 9. Các cơ chế admission và policy trên AKS

Có nhiều cấp độ kiểm soát, không nên xem chúng hoàn toàn tương đương.

| Cơ chế | Trọng tâm | Giới hạn cần nhớ |
|---|---|---|
| **Kubernetes Pod Security Admission (PSA)** | Thực thi Pod Security Standards theo namespace bằng enforce/audit/warn | Không thay thế policy tùy chỉnh về registry, labels hoặc chữ ký image |
| **Azure Policy add-on for AKS** | Áp dụng/audit các định nghĩa Azure Policy liên quan Kubernetes, dùng thành phần policy/Gatekeeper theo hỗ trợ | Phụ thuộc extension/add-on, policy assignment, phạm vi và tính năng hỗ trợ |
| **OPA Gatekeeper** | ConstraintTemplate/Constraint kiểm tra các tài nguyên Kubernetes | Phải vận hành webhook/policy, xem xung đột với policy do add-on quản lý |
| **Kyverno** | Policy theo Kubernetes-native YAML, validate/mutate/generate và các tính năng khác tùy phiên bản | Cần cài đặt/vận hành, chọn policy và theo dõi performance/availability |
| **ValidatingAdmissionPolicy (CEL)** | Kiểm tra bằng CEL ngay trong Kubernetes khi phiên bản hỗ trợ | Không mặc nhiên kiểm tra chữ ký image hoặc gọi scanner bên ngoài |
| **Custom admission webhook** | Logic kiểm tra riêng bằng service | Phải thiết kế TLS, độ sẵn sàng, timeout, fail policy và bảo mật |

Lựa chọn cơ chế phải theo **AKS version, addons, độ phủ yêu cầu, khả năng vận hành và chính sách tổ chức**. Không cài nhiều admission engine cho cùng một quy tắc nếu chưa có ownership và chiến lược xử lý xung đột.

## 10. Pod Security Standards: Privileged, Baseline, Restricted

Kubernetes định nghĩa ba cấp bảo vệ Pod:

### 10.1. Privileged

Mức **Privileged** gần như không đặt giới hạn theo Pod Security Standards. Chỉ thích hợp khi namespace hoặc workload có yêu cầu hệ thống đặc biệt được kiểm soát và phê duyệt rõ, chẳng hạn một số thành phần hạ tầng.

Không sử dụng Privileged làm chuẩn mặc định cho ứng dụng nghiệp vụ.

### 10.2. Baseline

**Baseline** nhằm chặn những kỹ thuật nâng quyền phổ biến mà không buộc tất cả ứng dụng phải đáp ứng mức chặt nhất. Thích hợp làm bước chuẩn hóa ban đầu cho môi trường có nhiều workload cũ.

### 10.3. Restricted

**Restricted** yêu cầu cấu hình chặt hơn, phù hợp với workload ứng dụng thông thường có thể chạy với quyền hạn thấp, bao gồm các giới hạn security context, capabilities, seccomp và những tùy chọn bảo vệ khác theo phiên bản chính sách.

Một image cũ chạy bằng root, cần ghi vào root filesystem hoặc phụ thuộc Linux capabilities rộng có thể không đáp ứng Restricted ngay. Cần sửa image/app trước, thay vì hạ enforcement toàn namespace một cách vô thời hạn.

### 10.4. Ba hành động PSA

| Chế độ | Điều xảy ra |
|---|---|
| **enforce** | Từ chối yêu cầu Pod mới/được cập nhật nếu vi phạm mức được gán |
| **audit** | Ghi dấu vi phạm vào audit annotations/log phù hợp, không tự chặn |
| **warn** | Trả warning cho client khi gửi yêu cầu không đạt chuẩn, không tự chặn |

PSA đánh giá theo **namespace labels**. Điều này không làm những Pod đang chạy bị tự động evict khi bạn đổi label; nhưng việc tạo lại Pod khi rollout hoặc node failure có thể bị chặn theo policy mới.

## 11. Thực hành PSA: đi từ Warn/Audit đến Enforce

**Điều kiện:** có kubeconfig của AKS lab, quyền quản lý namespace/labels theo RBAC và cluster dùng Kubernetes version hỗ trợ PSA. Chỉ thực hành trên namespace được phê duyệt.

### 11.1. Tạo namespace thử nghiệm

~~~bash
az aks get-credentials \
  --resource-group "<aks-rg>" \
  --name "<aks-name>"

kubectl config current-context

kubectl create namespace orders-security-lab
~~~

Không tạo lại namespace đang tồn tại hoặc tự gắn policy lên **kube-system**. Namespace hạ tầng có thể chạy các Pod đặc biệt không tương thích Restricted.

### 11.2. Bật cảnh báo và audit trước

~~~bash
NS="orders-security-lab"

kubectl label namespace "$NS" \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted \
  --overwrite
~~~

Khi tạo Pod vi phạm, client có thể thấy warning, nhưng yêu cầu không nhất thiết bị từ chối vì chưa bật **enforce=restricted**.

### 11.3. Một Pod cố ý vi phạm để kiểm thử

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: insecure-demo
  namespace: orders-security-lab
spec:
  containers:
    - name: app
      image: nginx:alpine
      securityContext:
        privileged: true
~~~

Lưu manifest làm **insecure-demo.yaml** trong thư mục lab nếu thực hành và chạy:

~~~bash
kubectl apply --dry-run=server -f insecure-demo.yaml
~~~

Kubernetes có thể trả warning do Pod privileged. **Server-side dry run** yêu cầu các thành phần admission liên quan hỗ trợ dry-run; nếu webhook cấu hình không phù hợp, phép thử có thể thất bại vì điều kiện kỹ thuật chứ không nhất thiết vì policy.

Không triển khai Pod privileged thật trên production để kiểm tra admission. Chỉ dùng **dry-run trong môi trường lab**.

### 11.4. Chuyển sang enforce theo quy trình

Sau khi đã sửa workload, đánh giá policy violations và được owner duyệt:

~~~bash
kubectl label namespace "$NS" \
  pod-security.kubernetes.io/enforce=restricted \
  --overwrite
~~~

Thử lại:

~~~bash
kubectl apply --dry-run=server -f insecure-demo.yaml
~~~

Mong đợi yêu cầu bị từ chối với thông báo Pod Security Standard liên quan. Nếu không có warning/deny, kiểm tra label, namespace, API version, loại workload và cấu hình PSA của cluster.

### 11.5. Quản lý phiên bản policy

PSA hỗ trợ label như **pod-security.kubernetes.io/enforce-version**, **audit-version**, **warn-version** trong những phiên bản Kubernetes hỗ trợ. Có thể sử dụng **latest** hoặc pin một Kubernetes minor version theo chính sách.

Không để rollout AKS Kubernetes version tự làm mức enforcement thay đổi ngoài ý muốn nếu tổ chức yêu cầu hành vi nhất quán. Đồng thời phải có lịch nâng phiên bản policy để không giữ tiêu chuẩn quá cũ.

### 11.6. Những việc PSA không làm thay bạn

PSA không tự:

- Buộc image chỉ đến từ ACR nội bộ.
- Kiểm tra digest/chữ ký/provenance.
- Đọc báo cáo CVE từ scanner.
- Cấp NetworkPolicy hoặc giới hạn egress.
- Cấp workload identity/Key Vault permissions.
- Quét toàn bộ file system trong container đang chạy.

Đó là lý do cần chính sách admission khác và các lớp phòng thủ bổ sung.

## 12. Mẫu Deployment có security context giảm quyền

Một workload chạy trong namespace Restricted cần được chuẩn bị từ **Dockerfile/image** đến Pod spec.

### 12.1. Manifest minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-security-lab
  labels:
    app: orders-api
    team: orders
spec:
  replicas: 2
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        team: orders
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          # Thay bằng image/digest thật đã build và được phê duyệt.
          image: acrordersprod.azurecr.io/orders/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
~~~

**Đây là mẫu security manifest**, không phải manifest chạy nguyên trạng: digest placeholder phải được thay, image cần thật sự hỗ trợ UID 10001, root filesystem read-only, ghi tạm ở **/tmp** và cung cấp **/ready** cùng **/health**. Nếu image không có những thuộc tính đó, Pod có thể được admission cho phép nhưng ứng dụng vẫn crash.

### 12.2. Ý nghĩa từng kiểm soát

| Trường | Mục đích | Điểm cần lưu ý |
|---|---|---|
| **runAsNonRoot** | Yêu cầu process không chạy root | Image/entrypoint phải tương thích |
| **runAsUser/runAsGroup** | Chỉ định UID/GID không đặc quyền | File trong image phải có permission phù hợp |
| **allowPrivilegeEscalation: false** | Ngăn process nâng quyền thông qua cơ chế được kernel quản lý | Không thay thế toàn bộ sandbox/container isolation |
| **capabilities.drop: ALL** | Loại các Linux capabilities mặc định | Một số app đặc biệt cần capability có lý do, review riêng |
| **seccompProfile: RuntimeDefault** | Dùng seccomp profile mặc định của runtime | Có thể chặn syscall mà app cũ cần |
| **readOnlyRootFilesystem: true** | Cấm ghi vào root FS của container | Mount thư mục ghi dữ liệu tạm phù hợp |
| **automountServiceAccountToken: false** | Không tự đưa Kubernetes API token vào Pod khi không cần | Không dùng bừa cho app cần Kubernetes API hoặc Workload Identity |
| **requests/limits** | Giới hạn và lập lịch sử dụng tài nguyên | Giá trị quá thấp gây throttling hoặc OOM |
| **probes** | Phân biệt app còn chạy và sẵn sàng phục vụ | Probe sai có thể gây restart/gián đoạn |
| **emptyDir /tmp** | Cho phép ghi tạm cần thiết với root FS read-only | Nội dung không bền vững qua lifecycle Pod |

Mẫu dùng **readOnlyRootFilesystem** để tăng hardening, nhưng trường này không phải lúc nào cũng là điều kiện cốt lõi của Pod Security Standards Restricted theo tất cả phiên bản. Tổ chức có thể đặt policy riêng chặt hơn mức Restricted.

### 12.3. Vì sao chạy non-root có thể lỗi?

Image có thể chứa:

- File chỉ root đọc được.
- Entrypoint tự sửa quyền hoặc ghi vào **/usr**, **/opt**.
- Process cố bind port đặc quyền hoặc dùng capability bị drop.
- Ứng dụng lưu log vào thư mục read-only.
- Thư viện native yêu cầu syscall bị seccomp chặn.

Phải **sửa Dockerfile/code và kiểm thử image**, không khắc phục mọi lỗi bằng **runAsUser: 0**, **privileged: true** hoặc cho quyền ghi toàn filesystem.

## 13. Ví dụ Java container tương thích với nguyên tắc non-root

Để thấy mối liên hệ giữa cấu hình image và Kubernetes, đây là ứng dụng Java HTTP tối giản phục vụ một endpoint health. Nó chỉ để minh họa security posture, không thay thế Spring Boot/Jetty/Tomcat trong production.

### 13.1. File HealthServer.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class HealthServer {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
                System.getenv().getOrDefault("PORT", "8080"));

        HttpServer server = HttpServer.create(
                new InetSocketAddress("0.0.0.0", port), 0);

        server.createContext("/health", exchange -> {
            byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.createContext("/ready", exchange -> {
            byte[] bytes = "READY".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        System.out.println("Java health server on port " + port);
    }
}
~~~

### 13.2. Dockerfile nhiều giai đoạn

~~~dockerfile
# Mẫu học tập: production cần pin base image digest, kiểm tra CVE.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY HealthServer.java .
RUN javac HealthServer.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/HealthServer.class /app/

# Không cần root để lắng nghe port 8080.
USER 10001:10001
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "HealthServer"]
~~~

Image chỉ chứa mã mẫu và JRE. Vì app không cần ghi vào **/app**, có thể áp dụng read-only root filesystem với volume tạm cho những đường dẫn cần ghi; điều kiện cụ thể của JRE/base image phải được kiểm thử.

Lệnh build/test local:

~~~bash
docker build -t orders-health:lab .
docker run --rm -p 8080:8080 orders-health:lab
~~~

Trong terminal khác:

~~~bash
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/ready
~~~

Nếu muốn push vào ACR, phải có registry được phê duyệt, quyền push đúng và image scan. Không ghi secret trong Dockerfile, build args hoặc layers.

### 13.3. Kiểm tra dưới securityContext thực tế

Build chạy local **không đủ** để khẳng định sẽ chạy dưới Restricted PSA trong AKS. Khi đưa image vào namespace staging:

1. Pin image digest và bảo đảm node có quyền pull.
2. Tạo Deployment với UID/GID, seccomp, capabilities và filesystem restrictions mong muốn.
3. Xem Pod Events, readiness/liveness, logs và exit code.
4. Kiểm tra endpoints bằng port-forward hoặc Service nội bộ.
5. Test ứng dụng khi scale-out, Pod restart và mất kết nối dependency.
6. Chỉ promote production khi security policy và smoke tests đều đạt.

## 14. Azure Policy add-on cho AKS

**Azure Policy** có thể áp dụng các định nghĩa/chính sách liên quan Kubernetes cho những cluster AKS được hỗ trợ. Azure Policy add-on tích hợp với các thành phần policy trên cluster (dựa trên Gatekeeper trong kiến trúc hỗ trợ), cho phép kiểm tra, ghi nhận compliance và từ chối những thao tác không phù hợp theo policy assignment.

### 14.1. Tác dụng và giới hạn

Các yêu cầu thường được thực thi hoặc đánh giá qua policy definitions phù hợp:

- Chỉ cho phép image từ một danh sách registry.
- Không cho container chạy privileged.
- Không cho phép host namespaces/hostPath không được duyệt.
- Buộc security context hoặc resource configuration theo policy.
- Kiểm soát các trường khác của Pod/cluster mà định nghĩa hỗ trợ.

**Không phải mọi Azure Policy definition đều hỗ trợ mọi AKS version, object kind hoặc effect.** Một định nghĩa **Audit** có thể chỉ ghi nhận compliance; muốn chặn phải chọn **Deny** hoặc cơ chế tương ứng được hỗ trợ và không có exclusion.

### 14.2. Bật add-on

Với AKS lab đã có và gói/tính năng được hỗ trợ:

~~~bash
az aks enable-addons \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --addons azure-policy
~~~

Kiểm tra:

~~~bash
az aks show \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --query "addonProfiles.azurepolicy" \
  --output json
~~~

Trước khi bật trên production, xác minh cluster version, quyền, chi phí/nguồn telemetry, trạng thái add-on hiện có và các yêu cầu của Azure Policy. Không thử bật/tắt nhiều lần để giải quyết một lỗi admission chưa được chẩn đoán.

### 14.3. Gán policy ở đúng Azure scope

Ví dụ vận hành trong Portal:

1. Mở **Azure Policy → Definitions** và tìm định nghĩa built-in áp dụng cho **Kubernetes Service/AKS** với ý định “Allowed container images/registries” hoặc hardening tương ứng.
2. Đọc điều kiện, parameters, effect và các giới hạn của định nghĩa hiện hành.
3. Chọn **Assign**, scope phù hợp subscription/resource group/cluster và thiết lập parameters.
4. Bắt đầu với **Audit** khi thích hợp; xem compliance và các workload bị ảnh hưởng.
5. Chỉnh image, manifests và quy trình deploy để đáp ứng.
6. Chuyển sang **Deny** theo change window và quy trình phê duyệt.
7. Xác minh bằng **server-side dry-run**, rollout staging và policy compliance.

Tên chính xác của built-in definitions và effects có thể thay đổi theo Azure Policy catalog. Không hard-code một ID không được xác minh làm tiêu chuẩn cho mọi subscription.

### 14.4. Scope và exclusions

Nếu policy gán ở subscription chứa nhiều AKS clusters, tác động có thể rộng hơn một namespace sản xuất. Cần xem:

- Azure scope và excluded scopes/notScopes.
- Các trường hợp **policy exemption** được duyệt.
- Namespace exclusions theo hỗ trợ/giới hạn của policy add-on.
- Cluster và namespaces chưa có quyền vận hành rõ.
- Khi nâng AKS/Kubernetes, policy có tương thích với phiên bản mới không?
- Resource hiện có được audit như thế nào, object mới bị chặn ra sao?

Không dùng exclusion **kube-system** như lý do để cấp quyền broad exemption cho mọi namespace nghiệp vụ. Tài nguyên hệ thống cần policy phù hợp vai trò của chúng.

## 15. Một policy minh họa: chỉ cho image từ ACR nội bộ

Có nhiều cách để kiểm tra image registry. Một cách **Kubernetes-native** trên những version hỗ trợ là **ValidatingAdmissionPolicy** sử dụng CEL. Dưới đây là ví dụ đơn giản để hiểu logic kiểm tra chuỗi image; nó **không xác minh chữ ký hoặc độ an toàn image**.

### 15.1. Policy kiểm tra Pod image references

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: approved-acr-images.example.com
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        object.spec.containers.all(c,
          c.image.startsWith('acrordersprod.azurecr.io/')) &&
        (!has(object.spec.initContainers) ||
          object.spec.initContainers.all(c,
            c.image.startsWith('acrordersprod.azurecr.io/'))) &&
        (!has(object.spec.ephemeralContainers) ||
          object.spec.ephemeralContainers.all(c,
            c.image.startsWith('acrordersprod.azurecr.io/')))
      message: "Pod images must use the approved ACR."
~~~

Policy kiểm tra ba nhóm container tham chiếu image và từ chối chuỗi không có prefix được phép. Đây là **ví dụ kiểm tra registry prefix**, có các giới hạn:

- Không bảo đảm repository/tag/digest tồn tại.
- Không kiểm tra image được ký hay scanner đã duyệt.
- Không tự hạn chế registry credentials hoặc outbound traffic.
- Chỉ kiểm tra **Pod create/update** theo resourceRules đã định; không tự audit mọi image hiện hữu ở mọi controller.
- Không kiểm tra Deployment template tại thời điểm Deployment được tạo; Pod do controller sinh ra mới là object bị kiểm tra trong ví dụ.
- Chưa giải quyết các rủi ro đường dẫn image, alias hoặc cách phân phối artifact; security review cần đánh giá policy thực tế.

### 15.2. Binding để chỉ thử trong namespace được đánh dấu

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: approved-acr-images-lab
spec:
  policyName: approved-acr-images.example.com
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        policies.example.com/require-acr: "true"
~~~

Gắn label vào namespace lab:

~~~bash
kubectl label namespace orders-security-lab \
  policies.example.com/require-acr=true \
  --overwrite
~~~

**Không thực thi mẫu trên production khi chưa thử kỹ.** ValidatingAdmissionPolicy phụ thuộc phiên bản Kubernetes/AKS và các API features được hỗ trợ. CEL expression, matching rules, yêu cầu phê duyệt policy và bảo vệ quyền tạo Binding phải được kiểm tra trong cluster thực tế.

Khi cần thay đổi/đánh giá trước Deny, xem **Warn/Audit** trong validationActions theo cách API hỗ trợ. Hạn chế scope qua namespace labels và giám sát Events trước khi mở rộng.

### 15.3. Phòng tránh policy bypass

- Đảm bảo policy không bỏ sót initContainers/ephemeralContainers trong phạm vi cần thiết.
- Hạn chế ai được sửa **namespace labels** và các Binding.
- Hạn chế ai được tạo/sửa **ValidatingAdmissionPolicy**.
- Kiểm soát workloads chạy trong namespaces không áp dụng label.
- Dùng policy cùng mục tiêu ở CI/CD và admission nhưng có ownership rõ ràng.
- Không nhầm **registry prefix validation** với signature verification.
- Xem các cơ chế bypass được tài liệu Kubernetes cho phép hoặc API admission không đánh giá, nếu có.

## 16. Gatekeeper và Kyverno: lựa chọn chính sách nâng cao

### 16.1. Gatekeeper

**OPA Gatekeeper** dùng ConstraintTemplate và Constraint để kiểm tra tài nguyên Kubernetes. Azure Policy add-on có thể triển khai/thao tác thành phần Gatekeeper cho những Azure Policy definitions được hỗ trợ.

Nếu đội ngũ muốn tự quản lý Gatekeeper constraints, phải quyết định rõ:

- Dùng Gatekeeper được Azure Policy add-on quản lý hay cài đặt riêng?
- Ai là owner của CRDs, templates và webhook?
- Có xung đột/ghi đè với policy đồng bộ từ Azure không?
- Chính sách nào chỉ audit và chính sách nào enforce?
- Có cơ chế exemption và audit resources hiện hữu không?
- Có khả năng chịu lỗi và theo dõi latency của webhook không?

Không tự sửa các tài nguyên managed bởi add-on khi chưa hiểu vòng đời quản lý và hỗ trợ.

### 16.2. Kyverno

**Kyverno** cho phép viết policy theo Kubernetes YAML cho những nhiệm vụ validate/mutate/generate và các khả năng image verification tùy phiên bản.

Một tổ chức có thể chọn Kyverno để:

- Yêu cầu image từ ACR nội bộ hoặc pin digest.
- Kiểm tra securityContext và metadata.
- Xác minh image signature/attestation theo trust policy được cấu hình.
- Tạo/report policy violations theo khả năng của công cụ.

Nhưng cài thêm policy engine làm tăng dependency của API server và gánh nặng nâng cấp. Không thêm Kyverno chỉ để giải quyết một yêu cầu mà PSA hoặc Azure Policy built-in đã đáp ứng tốt.

### 16.3. Chọn công cụ theo yêu cầu

| Nhu cầu | Cơ chế cần cân nhắc |
|---|---|
| Chặn privileged/root posture phổ biến | PSA Restricted/Baseline, policy cụ thể |
| Allowed registry/repository | Azure Policy, Gatekeeper, Kyverno hoặc ValidatingAdmissionPolicy |
| Xác minh chữ ký/provenance | Giải pháp admission có image verification thực sự |
| Giới hạn namespace metadata/labels | CEL, Gatekeeper/Kyverno hoặc Azure Policy phù hợp |
| Bảo vệ network runtime | NetworkPolicy + CNI thực thi, NSG/Azure Firewall khi phù hợp |
| Truy cập Azure data plane | Microsoft Entra Workload ID + RBAC data-plane |
| Phát hiện runtime compromise | Defender for Containers và telemetry/runtime tooling |
| Audit compliance đa cluster | Azure Policy/Defender dashboard và báo cáo riêng |

**Một định nghĩa policy “allowed registries” không tự làm image được ký hoặc không có CVE**. Cần tuyên bố chính xác cơ chế nào đáp ứng kiểm soát nào.

## 17. Admission webhooks: fail-open, fail-closed và độ sẵn sàng

Một validating/mutating webhook cần service endpoint có thể truy cập từ API server theo kiến trúc Kubernetes/AKS được hỗ trợ. Nếu webhook bị lỗi, hết chứng chỉ hoặc timeout:

- Với **failurePolicy: Fail**, yêu cầu thuộc phạm vi policy có thể bị từ chối: **fail-closed**.
- Với **failurePolicy: Ignore**, API server có thể cho request tiếp tục khi webhook không phản hồi: **fail-open** đối với kiểm soát đó.

Hai lựa chọn có trade-off rõ ràng:

| Chế độ | Lợi ích | Rủi ro |
|---|---|---|
| Fail | Không bỏ qua guardrail khi webhook lỗi | Có thể chặn deployment hoặc vận hành khi policy service outage |
| Ignore | Giảm tác động availability khi webhook lỗi | Workload không đạt chuẩn có thể được chấp nhận trong khoảng lỗi |

**Không chuyển webhook sang Ignore trên production chỉ vì một lần deploy bị kẹt.** Xác minh root cause, thời gian lỗi, phạm vi áp dụng, exception phê duyệt và phương án phục hồi trước.

### 17.1. Các chỉ số vận hành admission

- Request count và deny rate theo policy.
- Admission webhook latency/timeouts.
- TLS/certificate expiration và service health.
- Những namespace/app thường vi phạm.
- Số exemption đang hoạt động và ngày hết hạn.
- Số Pod đã tồn tại trước khi policy enforce nhưng chưa được sửa.
- Rollout failures do admission và thời gian giải quyết.

Nếu policy chặn hệ thống, cần một **break-glass runbook** có thời hạn, chủ sở hữu và audit log; không trao cluster-admin rộng rãi cho mọi developer để bypass.

## 18. Kubernetes RBAC: admission không thay thế quyền truy cập API

**Kubernetes RBAC** quyết định ai có thể thực hiện hành động trên resources. Admission đánh giá object/hành động sau những bước xác thực và ủy quyền tương ứng.

Ví dụ:

- Người dùng có quyền tạo Deployment trong **orders-prod**, nhưng admission có thể từ chối Pod template vi phạm khi Pod được tạo.
- Một Pod đã được admission cho phép **không nên tự có quyền list mọi Secret**.
- Cluster-admin có thể thay đổi nhiều tài nguyên, do đó đặc quyền này phải rất hạn chế.

### 18.1. ServiceAccount riêng cho workload

Nếu Pod không cần gọi Kubernetes API:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders-security-lab
automountServiceAccountToken: false
~~~

Khi dùng ServiceAccount này, Deployment phải tham chiếu:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
~~~

Đây là đoạn minh họa cần đặt đúng vị trí trong Deployment spec, **không phải manifest độc lập** cho toàn bộ Deployment. Dùng một ServiceAccount riêng giúp quản trị quyền dễ hơn so với để nhiều ứng dụng phụ thuộc vào default ServiceAccount.

### 18.2. Role namespace-scoped

Một job vận hành hợp lệ có thể cần quyền **get/list Pods** trong namespace, nhưng không cần quyền đọc Secrets hoặc cập nhật ClusterRole:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-viewer
  namespace: orders-security-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-viewer-binding
  namespace: orders-security-lab
subjects:
  - kind: ServiceAccount
    name: orders-observer
    namespace: orders-security-lab
roleRef:
  kind: Role
  name: pod-viewer
  apiGroup: rbac.authorization.k8s.io
~~~

Ví dụ giả định **ServiceAccount orders-observer** đã được tạo trong namespace. Không cấp thêm **secrets/get** chỉ vì một script gặp Forbidden; xem lại chức năng và nhu cầu quyền.

### 18.3. Kiểm tra quyền

~~~bash
kubectl auth can-i get pods \
  --as=system:serviceaccount:orders-security-lab:orders-observer \
  -n orders-security-lab

kubectl auth can-i list secrets \
  --as=system:serviceaccount:orders-security-lab:orders-observer \
  -n orders-security-lab
~~~

Việc impersonate với **--as** cần quyền **impersonate** tương ứng; nếu lệnh bị từ chối, đó có thể là hạn chế của người chạy lệnh, không chứng minh ServiceAccount có quyền sai. Một cluster admin được ủy quyền có thể kiểm chứng theo phương pháp được phép.

## 19. Workload Identity: truy cập Azure không dùng static secret

Một ứng dụng cần đọc Blob hoặc Key Vault không nên nhúng storage key/client secret dài hạn trong image. **Microsoft Entra Workload ID** cho AKS là lựa chọn quan trọng để đưa danh tính vào workload.

### 19.1. Phân biệt kubelet và workload identity

| Danh tính | Việc cần làm |
|---|---|
| **AKS kubelet identity** | Pull image từ ACR trước khi container chạy |
| **AKS control plane identity** | Thao tác Azure control plane theo thiết kế cluster |
| **Workload identity gắn với ServiceAccount** | Java/Node/Python trong Pod gọi Azure APIs theo RBAC đã cấp |
| **CI/CD identity** | Build, scan, sign và push artifact |

Không gán **AcrPush** cho workload identity của Orders chỉ để ứng dụng đọc Blob. Không dùng imagePullSecrets/admin password khi tích hợp kubelet managed identity đã được hỗ trợ và có thể dùng an toàn.

### 19.2. Điều kiện Workload ID

Cần cấu hình AKS OIDC issuer và Workload Identity, một user-assigned managed identity hoặc ứng dụng Entra phù hợp, **federated identity credential** khớp issuer/subject/audience, cùng quyền data plane trên Azure resource đích.

Ví dụ Azure CLI để bật các tính năng trên **cluster đã được phê duyệt**, nếu hiện chưa bật:

~~~bash
az aks update \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --enable-oidc-issuer \
  --enable-workload-identity
~~~

Đây là thao tác thay đổi cấu hình cluster; không chạy trên production nếu chưa có change plan và kiểm tra tương thích.

### 19.3. ServiceAccount cho Java API

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api-azure
  namespace: orders-security-lab
  annotations:
    azure.workload.identity/client-id: "<managed-identity-client-id>"
~~~

Pod dùng ServiceAccount này cần label nhận diện workload identity theo cơ chế AKS:

~~~yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api-azure
~~~

Đây chỉ là **các đoạn YAML để chèn vào Deployment**, không phải manifest deploy được nếu đứng độc lập. Phải có federated credential có subject như **system:serviceaccount:orders-security-lab:orders-api-azure**, issuer đúng AKS OIDC, audience phù hợp và role assignment ở đích.

Khi sử dụng Workload Identity, **không áp dụng máy móc automountServiceAccountToken: false** từ mẫu Pod không cần API; Workload Identity cần projected token/injection theo cơ chế được hỗ trợ. Kiểm tra cách ServiceAccount token được cấp và mount bởi webhook/SDK thực tế.

### 19.4. Cấp quyền Azure data plane

Quy trình đầy đủ:

1. Tạo hoặc xác định danh tính Azure được cấp phép.
2. Cấu hình federated credential khớp cluster issuer, namespace và ServiceAccount.
3. Gán role thấp nhất cho đích: ví dụ chỉ đọc Blob ở scope phù hợp hoặc đọc Key Vault secrets khi được phép.
4. Đảm bảo Pod dùng đúng ServiceAccount và SDK hỗ trợ Workload Identity.
5. Kiểm tra connection, role propagation và network/private DNS.
6. Theo dõi lỗi 401/403; không giải quyết bằng cách cấp Owner toàn subscription.

Workload Identity chỉ xử lý **xác thực/danh tính**, không tự bảo đảm đường mạng đến Blob/Key Vault hoặc cấp role đúng.

## 20. Kubernetes NetworkPolicy và ranh giới mạng

Admission có thể cấm Pod cấu hình nguy hiểm, nhưng **không tự hạn chế traffic chạy thật**. Muốn chặn di chuyển ngang cần NetworkPolicy hoặc kiểm soát mạng khác.

### 20.1. Default-deny trong một namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: orders-security-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Chính sách này nhằm mặc định chặn ingress/egress cho Pods thuộc namespace khi **network plugin/dataplane thực sự thực thi NetworkPolicy**.

**Lưu ý:** áp dụng default-deny mà chưa tạo allow rules có thể làm ứng dụng mất DNS, database, metrics hoặc Kubernetes API connectivity. Chỉ thử trong lab và lập trước ma trận traffic.

### 20.2. Cho phép DNS theo nhãn thực tế

Ví dụ minh họa chỉ cho DNS query tới những Pod CoreDNS có label phù hợp:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: orders-security-lab
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Phải xác minh label CoreDNS và cơ chế DNS thực tế trên cluster.** Không phải mọi AKS cluster đều dùng đúng nhãn **k8s-app: kube-dns**, và DNS forwarding, NodeLocal DNSCache hoặc dataplane cụ thể có thể cần quy tắc khác.

### 20.3. Đừng nhầm NetworkPolicy với NSG

- **Kubernetes NetworkPolicy** áp dụng với Pod traffic theo network plugin thực thi.
- **Azure NSG** áp dụng trong mạng Azure ở scope NIC/subnet theo thiết kế.
- **Azure Firewall/NVA** có thể thực thi chính sách tập trung cho ingress/egress.
- **Private Endpoint** đem lại đường private tới dịch vụ PaaS được hỗ trợ.
- **Admission policy** kiểm tra manifest, không trực tiếp lọc packet runtime.

Bảo mật mạng AKS yêu cầu thiết kế nhiều lớp phù hợp với CNI/network plugin, UDR, DNS, firewall và data plane của cluster.

## 21. ResourceQuota, LimitRange và kiểm soát abuse

Giảm quyền hệ điều hành chưa đủ nếu một người dùng có thể tạo quá nhiều Pod, yêu cầu CPU/memory vô hạn hoặc chiếm tất cả resources.

### 21.1. ResourceQuota theo namespace

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-security-lab
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "30"
~~~

ResourceQuota giới hạn tổng mức sử dụng/kê khai trong namespace theo cơ chế Kubernetes. Nó không thay thế yêu cầu **requests/limits** đúng cho từng container hoặc hệ thống autoscaling/cluster capacity.

### 21.2. LimitRange

**LimitRange** có thể đặt min/max/default requests/limits theo namespace khi phù hợp. Khi giới hạn mặc định được thêm tại admission, giá trị thực tế của Pod có thể khác manifest gốc.

Tuy nhiên, không nên dựa vào LimitRange để tự xác định các mức tài nguyên tối ưu cho ứng dụng. Phải đo CPU, memory, GC, startup và peak load. Requests quá thấp gây scheduling/overcommit, limits quá thấp gây throttling hoặc OOMKills.

### 21.3. Vì sao quota cũng là biện pháp bảo mật?

Một workload bị xâm nhập hoặc một người dùng triển khai sai có thể tạo nhiều Pods/Jobs gây mất availability của các nhóm khác. Quota và quyền create/update trong Kubernetes RBAC giúp giảm phạm vi ảnh hưởng.

Dù vậy, ResourceQuota ở một namespace không giải quyết mọi trường hợp resource exhaustion của cluster; cần node pool isolation, autoscaling limits, pod priority, budgets và monitoring theo mô hình vận hành.

## 22. Secrets, Key Vault và bảo vệ dữ liệu

### 22.1. Kubernetes Secret không phải nơi mặc nhiên an toàn tuyệt đối

Một đối tượng **Secret** trong Kubernetes chứa dữ liệu được mã hóa Base64 trong manifest khi dùng data field, nhưng **Base64 không phải encryption**. Quyền đọc Secrets, cấu hình encryption at rest và access tới etcd/API là những vấn đề riêng.

Không commit manifest chứa secret plaintext hoặc chuỗi Base64 của mật khẩu vào Git. Không ghi các token trong output CI hoặc Pod logs.

### 22.2. Key Vault và CSI Driver

AKS có thể tích hợp **Azure Key Vault provider for Secrets Store CSI Driver** theo tính năng hỗ trợ. Workload có thể mount secrets/certificates từ Key Vault theo cấu hình SecretProviderClass, danh tính và network phù hợp; một số chế độ có thể đồng bộ tới Kubernetes Secret khi được cấu hình.

Những điểm cần kiểm tra:

- Chỉ mount secrets ứng dụng thật sự cần.
- Dùng identity riêng cho workload và quyền Key Vault tối thiểu.
- Network/Private Endpoint/DNS tới Key Vault phải hoạt động.
- Xác minh cơ chế **rotation** và cách process reload secret khi thay đổi.
- Giảm nguy cơ secret bị ghi vào log hoặc file tạm.
- Không coi CSI driver là cách thay thế admission hoặc container hardening.

### 22.3. Dữ liệu trên Persistent Volume

Policy image và securityContext không tự bảo vệ dữ liệu lưu trên PersistentVolume. Cần:

- StorageClass/PVC phù hợp.
- Quyền filesystem/UID/GID, fsGroup khi cần và được hỗ trợ.
- Backup/snapshot/restore cho volume.
- Encryption và identity ở lớp lưu trữ.
- Quy trình xóa/retention và phân loại dữ liệu.
- Không mount hostPath/host filesystem nhạy cảm vào app Pod để giải quyết lỗi permission.

## 23. Giám sát compliance, admission và runtime

Bảo mật production cần bằng chứng có thể kiểm tra, không chỉ danh sách tick ở tài liệu thiết kế.

### 23.1. Các nguồn quan sát

| Nguồn dữ liệu | Câu hỏi cần trả lời |
|---|---|
| Azure Policy compliance | Cluster/namespace/resource nào vi phạm những định nghĩa được gán? |
| PSA warnings/audit | Pod nào không đạt Baseline/Restricted trong thời gian quan sát? |
| Admission webhook metrics/logs | Policy nào từ chối, timeout hoặc lỗi TLS? |
| Kubernetes Events | ReplicaSet/Pod có bị FailedCreate vì admission không? |
| ACR diagnostic logs | Ai push/pull và thay đổi gì ở registry theo log hỗ trợ? |
| Defender for Containers | Những lỗ hổng/cảnh báo tư thế/runtime nào được phát hiện theo cấu hình? |
| Azure Activity Log | Ai đổi AKS, ACR, role, policy assignment ở Azure control plane? |
| Kubernetes audit logs | Ai tạo/sửa Pod/Role/Secret/Policy theo cấu hình audit? |
| Container Insights/Azure Monitor | Process restart, OOM, node resource, logs, requests |
| CI/CD provenance | Release đang chạy build từ commit, builder và digest nào? |

Các dữ liệu trên có điều kiện bật/tính phí riêng. **Không mặc định AKS đã gửi toàn bộ Kubernetes audit log đến Log Analytics**, hoặc Defender đã bật mọi tính năng chỉ vì cluster được tạo trong Azure.

### 23.2. Những KPI nên báo cáo

- Tỷ lệ images production được **pin digest**.
- Tỷ lệ image đã scan và thời gian xử lý CVE Critical/High theo policy.
- Tỷ lệ Pods đạt Restricted security posture.
- Số policy **Deny**, số vi phạm **Audit/Warn** theo team/namespace.
- Số exemption còn hiệu lực, quá hạn hoặc thiếu owner.
- Tỷ lệ workload dùng managed/workload identity thay credential tĩnh.
- Số workloads còn dùng privileged/hostPath/hostNetwork có lý do và phê duyệt.
- Admission webhook availability/latency.
- Thời gian từ phát hiện image bị lỗi đến rebuild/rollout bản vá.
- Chi phí bảo mật/quan sát và tác động đến release lead time.

Đừng đánh giá “zero violation” là tốt nếu policy đã bị tắt hoặc toàn bộ namespaces bị exclude. KPI phải đi cùng **độ phủ chính sách**.

## 24. Khắc phục sự cố khi admission hoặc security policy chặn rollout

### 24.1. Những lỗi cần phân biệt

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| **kubectl apply bị Forbidden** | Thiếu Kubernetes RBAC | kubectl auth can-i, RoleBinding, context |
| **admission webhook denied** | Manifest vi phạm validating policy | Đọc policy/message/fields bị chặn |
| **violates PodSecurity restricted** | root, privileged, capabilities hoặc seccomp không đạt | Kiểm tra securityContext và version PSS |
| **Deployment tồn tại nhưng 0 Pods** | ReplicaSet Pod create bị admission từ chối | kubectl describe rs/deployment, Events |
| **ImagePullBackOff** | ACR role/network/tag/digest lỗi | kubelet identity, Pod Events, registry, DNS |
| **CrashLoopBackOff** | Image đã pull nhưng app crash | kubectl logs, entrypoint, filesystem permissions |
| **CreateContainerConfigError** | Secret/ConfigMap/key hoặc volume thiếu | Describe Pod, references |
| **403 Key Vault/Blob** | Workload identity/role sai hoặc thiếu network | ServiceAccount, federation, data plane RBAC |
| **Pod chạy nhưng không gọi SQL** | NetworkPolicy, DNS, firewall, Private Endpoint | Network traffic matrix, CNI và effective routes |
| **Webhook timeout** | Admission backend/TLS/mạng lỗi | Webhook service, certificate, timeout/failurePolicy |
| **Policy compliant nhưng image có CVE** | Policy chỉ kiểm tra cấu hình, scanner độc lập | Scan/Defender findings và digest thực tế |
| **Kubernetes API vẫn cho privileged Pod** | Namespace không enforce, exemption, sai scope | Namespace labels, bindings, constraints, policy effects |

### 24.2. Lệnh chẩn đoán Kubernetes

~~~bash
NS="orders-security-lab"

kubectl get namespace "$NS" --show-labels

kubectl get deployments,replicasets,pods -n "$NS"

kubectl get events -n "$NS" --sort-by=.lastTimestamp

kubectl describe deployment orders-api -n "$NS"

kubectl get pods -n "$NS" -o wide
~~~

Nếu Pod đã tồn tại, lấy tên thật:

~~~bash
POD="<pod-name>"

kubectl describe pod "$POD" -n "$NS"

kubectl logs "$POD" -n "$NS" --tail=100
~~~

Nếu Pod **không được tạo vì admission**, **không có application logs** để đọc. Hãy xem **ReplicaSet events, webhook logs và API admission rejection**, không lặp đi lặp lại lệnh logs.

### 24.3. Khi lỗi do policy không phù hợp workload

1. Xác nhận owner workload, namespace và policy bị chặn.
2. Kiểm tra chính xác trường vi phạm.
3. Tìm cách sửa image/manifest: non-root user, thư mục writable riêng, dropping capabilities, pin digest.
4. Thử **server-side dry-run** hoặc staging namespace.
5. Nếu business cần exception, tạo quy trình có chủ sở hữu, scope hẹp, thời hạn và audit.
6. Không sửa policy toàn cluster chỉ vì một ứng dụng legacy.
7. Sau khi deploy, xác minh Ready, kết nối dependency và kết quả scanner.

### 24.4. Khi webhook bị lỗi hạ tầng

- Kiểm tra controller/Pods của webhook có Ready không.
- Kiểm tra Service/Endpoints và kết nối từ API server theo kiến trúc AKS.
- Kiểm tra TLS CA bundle, certificate expiration và cách rotate.
- Kiểm tra quá tải CPU/memory, network policy và timeout.
- Đọc **failurePolicy** và tác động thực tế đến API availability.
- Thực hiện phục hồi qua runbook đã được phê duyệt.

**Không xóa MutatingWebhookConfiguration hoặc ValidatingWebhookConfiguration bất kỳ** chỉ để “unblock” deployment. Hành động này có thể vô hiệu hóa guardrail bảo mật của toàn cluster.

## 25. Triển khai policy theo nhiều giai đoạn

Thay đổi guardrail cho cluster production cần được xem như một release có kiểm soát.

### 25.1. Giai đoạn 1 — Inventory

Thu thập:

- Namespaces và owners.
- Workloads/DaemonSets đang dùng root, privileged, hostPath, hostNetwork.
- Images đến từ registry nào, có digest không.
- Secrets/static credentials và ServiceAccounts.
- NetworkPolicies hiện có, ingress/egress needs.
- Build pipeline và scanner đang dùng.
- Số Pod chạy phiên bản cũ, không có kế hoạch rebuild.
- Hệ thống hạ tầng có yêu cầu ngoại lệ hợp lệ không.

### 25.2. Giai đoạn 2 — Audit/Warn

- Bật **PSA warn/audit** cho namespace thí điểm.
- Gán Azure Policy definitions ở effect **Audit** khi phù hợp.
- Thu thập violations theo team.
- Làm rõ false positives hoặc workload legacy.
- Sửa image/manifest và dùng staging tests.
- Xây bảng policy exception có ngày hết hạn.

### 25.3. Giai đoạn 3 — Enforce phạm vi nhỏ

- Chọn namespace ít rủi ro.
- Bật **PSA enforce** hoặc admission **Deny** cho quy tắc đã kiểm thử.
- Kiểm tra rollout, deploy bằng CI/CD và khả năng scale-out.
- Theo dõi FailedCreate và webhook latency.
- Mở rộng dần sang production theo ownership.

### 25.4. Giai đoạn 4 — Continuous compliance

- Scan/rebuild images thường xuyên.
- Kiểm soát signing keys/identities.
- Audit exceptions và revoke khi hết hạn.
- Kiểm tra policy khi nâng AKS/Kubernetes version.
- Đo độ phủ và tỷ lệ chặn có ích.
- Diễn tập sự cố admission và rollback policy.
- Báo cáo với nhóm vận hành về rủi ro tồn đọng.

**Lưu ý:** Một policy ở chế độ Deny chủ yếu chặn thao tác mới; **không mặc nhiên sửa mọi tài nguyên đã tồn tại**. Phải có kế hoạch thay thế/rollout những Pod cũ còn vi phạm.

## 26. Runbook ứng phó khi phát hiện image độc hại

Một incident giả định: scanner phát hiện CVE có khả năng khai thác trong image **orders-api@sha256:...**, đang chạy tại nhiều namespaces.

### 26.1. Phản ứng

1. Xác thực cảnh báo: CVE nào, image digest nào, workload nào thực sự đang chạy?
2. Xác định mức phơi lộ và khả năng khai thác theo môi trường.
3. Thông báo owner/SecOps; kích hoạt incident process khi cần.
4. Hạn chế tiếp tục deploy digest rủi ro bằng CI/CD/admission policy phù hợp.
5. Build image đã vá, quét, ký/attest và phát hành digest mới.
6. Rollout có kiểm soát, health check và đo tỷ lệ lỗi.
7. Nếu có dấu hiệu compromise, thu thập forensic/logs, kiểm tra identities/secrets, áp dụng containment và rotation theo quy trình.
8. Kiểm tra mọi clusters/namespaces không còn dùng digest cũ.
9. Xem lại policy exception, image retention, root cause và bổ sung giám sát.

### 26.2. Không xóa mọi Pod để “sửa CVE”

Nếu Deployment vẫn tham chiếu image lỗi, controller có thể tạo lại Pod với chính image đó. Xóa Pods mà không đổi Deployment và nguồn image **không phải remediation**.

Ngoài ra, nếu image mới chưa qua kiểm thử hoặc runtime không tương thích, deploy khẩn cấp có thể gây outage; cần cân đối containment, rollout an toàn và rollback theo mức độ rủi ro.

## 27. Chi phí và vận hành

Bảo mật image/admission là một phần của chi phí sở hữu AKS, nhưng cũng giúp hạn chế gián đoạn và nguy cơ sự cố lớn.

| Thành phần | Chi phí/tác động có thể phát sinh |
|---|---|
| ACR | Registry SKU, dung lượng image/layer, build tasks, network/geo-replication theo tính năng |
| Microsoft Defender for Containers | Phí gói/tính năng bảo vệ, quét, runtime hoặc resource coverage theo bảng giá hiện hành |
| Azure Policy/Gatekeeper/Kyverno | Quản lý policy và tài nguyên cluster cho controllers/webhooks; telemetry theo cấu hình |
| AKS node pools | Compute, managed disks và capacity cho workload plus policy agents |
| Azure Monitor/Log Analytics | Ingestion, retention, alerting, Kubernetes audit logs |
| Network | Private Endpoint, NAT Gateway, firewall và egress theo mô hình |
| CI/CD & scanning | Build minutes/runners, scan tools, artifact signing/key management |
| Vận hành | Triage CVE, xử lý false positive, exception, nâng version và incident response |

Không giả định **bật Azure Policy add-on làm mọi kiểm soát không tốn tài nguyên**. Controller/webhook có CPU/memory và quản trị riêng; dữ liệu log có thể phát sinh phí.

### 27.1. Chỉ số hiệu quả

Bên cạnh số policy vi phạm, đo:

- Thời gian từ phát hiện CVE tới khi phát hành bản vá.
- Số image được triển khai không qua CI/CD chuẩn.
- Thời gian chờ admission và tỷ lệ webhook errors.
- Số incidents do quá quyền trong Kubernetes/Entra.
- Số secrets được loại khỏi images/repos.
- Tỷ lệ node/pod được bảo vệ và quan sát.
- Số deployment lỗi do policy thay vì lỗi ứng dụng.
- Phí scanner, log retention, controllers và môi trường thử nghiệm.

Kiểm soát tốt phải làm giảm rủi ro **mà không tạo điểm lỗi duy nhất không được quản lý**.

## 28. Checklist bảo mật AKS trước production

- [ ] Đã có danh sách registry/repository được phê duyệt.
- [ ] CI/CD có kiểm soát source, dependency, image build và CVE scanning.
- [ ] Image production được version hóa/digest pinning theo chính sách.
- [ ] Chữ ký/provenance được xác minh bằng giải pháp thực sự thực thi nếu yêu cầu.
- [ ] CI/CD push, kubelet pull và workload identity có quyền riêng và tối thiểu.
- [ ] ACR permission mode (RBAC/ABAC) và role đã được xác nhận.
- [ ] Không dùng ACR admin password hoặc Docker registry credential dài hạn nếu không cần.
- [ ] PSA Baseline/Restricted được triển khai theo từng namespace phù hợp.
- [ ] Azure Policy/admission engine có owner, scope, effect và exception rõ ràng.
- [ ] Policy kiểm tra đúng resource kinds và các loại container liên quan.
- [ ] Container chạy non-root khi khả thi, không privilege escalation, drop capabilities, seccomp.
- [ ] Root filesystem read-only khi phù hợp; có thư mục tạm được quản lý.
- [ ] Không mount hostPath nhạy cảm hoặc dùng host namespaces ngoài yêu cầu được duyệt.
- [ ] ServiceAccount riêng, Kubernetes RBAC thấp nhất, hạn chế automount token.
- [ ] Workload Identity/Key Vault được cấu hình cho quyền Azure data plane.
- [ ] Kubernetes Secrets được quản lý; không có secret trong image/Git/log.
- [ ] NetworkPolicy được CNI thực thi và có allow rules cần thiết cho DNS/dependencies.
- [ ] ResourceQuota/LimitRange, requests/limits và node isolation hợp lý.
- [ ] Có monitoring cho admission denies, webhook timeout, image CVEs và runtime alerts.
- [ ] Có runbook khi webhook lỗi, CVE khẩn cấp hoặc Pod bị policy chặn.
- [ ] Đã thử rollout/rollback, exception có thời hạn và backup/DR theo workload.
- [ ] Chi phí ACR, AKS, Defender, logs và policy components được theo dõi.

## 29. Bài tập thực hành

### Bài tập 1: Phân lớp bảo mật

Cho pipeline Orders: Git → build JAR → Docker image → ACR → AKS → Azure SQL.

Hãy vẽ sơ đồ có ít nhất sáu lớp kiểm soát. Chỉ ra lớp nào giải quyết CVE, provenance, allowed registry, Pod privileges, data identity, network isolation và runtime detection.

### Bài tập 2: PSA trên namespace staging

Trong AKS lab:

1. Tạo namespace **orders-security-lab**.
2. Gắn nhãn **warn=restricted** và **audit=restricted**.
3. Thử manifest Pod privileged bằng **kubectl apply --dry-run=server**.
4. Ghi lại warning.
5. Chuyển **enforce=restricted**.
6. Thử lại manifest và quan sát thông báo deny.
7. Giải thích vì sao Pod cũ đang chạy không tự bị evict.

Không làm trên namespace hệ thống hoặc production.

### Bài tập 3: Hardening Java API

Ứng dụng Java cần port 8080 và ghi file tạm vào **/tmp**. Hãy viết Deployment có UID non-root, seccomp RuntimeDefault, drop ALL capabilities, allowPrivilegeEscalation false, readOnlyRootFilesystem true, emptyDir /tmp, requests/limits và probes.

Sau đó giải thích vì sao image/Dockerfile phải hỗ trợ cấu hình này.

### Bài tập 4: Allowed ACR policy

Giả sử tổ chức chỉ cho phép image từ **acrordersprod.azurecr.io**. Viết một biểu thức kiểm tra prefix image trong containers/initContainers và nêu giới hạn của cách làm đó. So sánh **allowed registry**, **pin digest**, **verify signature** và **CVE scan**.

### Bài tập 5: Workload Identity

Một Pod cần đọc Blob nhưng không cần quyền sửa Deployment:

1. Phân biệt kubelet identity và workload identity.
2. Xác định ServiceAccount/namespace.
3. Mô tả OIDC issuer, federated credential và role data plane.
4. Giải thích tại sao cấp AcrPull cho Pod không đồng nghĩa đọc Blob.
5. Xử lý lỗi 403 Blob mà không dùng Owner toàn subscription.

### Bài tập 6: NetworkPolicy

Thiết kế default-deny cho **orders-security-lab**, sau đó chỉ cho phép DNS, request nội bộ từ ingress và outbound đến dịch vụ phụ thuộc được duyệt. Nêu các điều kiện về network plugin/CNI, DNS và Private Endpoint.

### Bài tập 7: Admission incident

Deployment đã được API nhận nhưng không tạo được Pod, Events báo **FailedCreate** và **violates PodSecurity restricted**.

- Bạn kiểm tra resource nào trước?
- Vì sao không nên bắt đầu bằng logs của Pod?
- Khi nào sửa Dockerfile, khi nào sửa manifest?
- Nếu cần ngoại lệ khẩn cấp, phải có các giới hạn gì?
- Làm sao chứng minh rollout mới vừa an toàn vừa Healthy?

### Bài tập 8: CVE mới xuất hiện

Một image chạy production có CVE Critical sau ba tuần vận hành. Hãy lập kế hoạch triage, rebuild, scan, sign, rollout, verify digest, revoke/rotate secrets nếu cần và audit các namespace dùng phiên bản cũ.

### Câu hỏi tự kiểm tra

1. Vì sao quét image và admission policy không thay thế nhau?
2. imagePullPolicy Always có bảo đảm image tag bất biến không?
3. Digest và image signature có cùng vai trò không?
4. PSA hỗ trợ những mức security và hành động nào?
5. Khi tăng namespace lên Restricted, Pod đang chạy có tự bị xóa không?
6. Admission webhook fail-closed và fail-open khác nhau ra sao?
7. Vì sao Deployment có thể tạo thành công nhưng ReplicaSet không tạo được Pod?
8. Kubernetes RBAC khác admission policy thế nào?
9. Khi nào dùng Azure Policy add-on thay vì tự viết Gatekeeper/Kyverno?
10. Azure Policy “allowed registry” có tự xác minh chữ ký không?
11. readOnlyRootFilesystem có yêu cầu thay đổi cách Java app ghi tệp tạm không?
12. Vì sao Workload Identity không giải quyết trực tiếp bước kubelet pull image?
13. Kubernetes NetworkPolicy có hoạt động khi CNI không hỗ trợ enforcement không?
14. Một image có chữ ký hợp lệ có thể vẫn chứa CVE không?
15. Khi Pod không tồn tại do admission, cần đọc sự kiện nào?
16. Vì sao không nên dùng namespace exemption không có thời hạn?
17. Tại sao công cụ scan phải theo dõi lỗ hổng mới sau khi image đã deploy?
18. Một policy tuân thủ 100% nhưng không áp dụng lên namespace nào có ý nghĩa bảo mật không?

## 30. Tài liệu tham khảo

- [Security concepts for Azure Kubernetes Service](https://learn.microsoft.com/azure/aks/concepts-security)
- [AKS security best practices for clusters and workloads](https://learn.microsoft.com/azure/aks/operator-best-practices-cluster-security)
- [Microsoft Defender for Containers overview](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction)
- [Understand Azure Policy for Kubernetes](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes)
- [Azure Policy add-on for AKS](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes#install-the-azure-policy-add-on-for-aks)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [Kubernetes admission controllers](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)
- [Kubernetes Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
- [Kubernetes security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [ACR RBAC and ABAC repository permissions](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication)
- [Sigstore Cosign documentation](https://docs.sigstore.dev/cosign/overview/)
- [Azure Kubernetes Service pricing](https://azure.microsoft.com/pricing/details/kubernetes-service/)

