# Quản lý secret bằng tích hợp Azure Key Vault

Một ứng dụng chạy trên **Azure Kubernetes Service (AKS)** cần chuỗi kết nối cơ sở dữ liệu, API token và chứng chỉ TLS. Đưa những giá trị này vào `Dockerfile`, ConfigMap hoặc Git repository khiến thông tin nhạy cảm dễ bị đọc ngoài ý muốn. Chuyển chúng vào Kubernetes Secret có thể cải thiện cách quản lý cấu hình, nhưng nếu không thiết kế quyền truy cập, mã hóa và vòng đời phù hợp, nguy cơ lộ secret vẫn tồn tại.

**Azure Key Vault** là dịch vụ quản lý secret, key và certificate của Azure. Trên AKS, một cách tích hợp phổ biến là **Secrets Store CSI Driver với Azure Key Vault Provider**: Pod có thể đọc giá trị từ Key Vault thông qua **volume dạng file**, thay vì bắt buộc sao chép tất cả giá trị vào Kubernetes Secret. Danh tính truy cập có thể được cấp qua **managed identity** hoặc **Microsoft Entra Workload Identity**, tùy thiết kế và tính năng được hỗ trợ.

Bài thuộc chương **Nền tảng Azure Kubernetes Service** trong module `CLOUD_PROVIDERS_AZURE`. Module giúp người học khám phá Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, compute, lưu trữ và dữ liệu; đồng thời triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Trong bài này, trọng tâm là **quản lý secret an toàn cho workloads AKS**, không phải bí quyết lưu mật khẩu vào manifest Kubernetes.

> Tên add-on, tham số Azure CLI, quy tắc Key Vault RBAC và khả năng CSI rotation có thể khác theo phiên bản AKS/driver/provider. Các ví dụ dùng placeholder và không chứa credential thật. Khi chạy trên môi trường thực, luôn xác nhận subscription, cluster, namespace, quyền và tài liệu tính năng tương ứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Kubernetes Secret**, **Azure Key Vault secret**, **Key Vault key** và **Key Vault certificate**.
2. Giải thích đường đi của secret từ Key Vault tới container qua **Secrets Store CSI Driver**.
3. Bật hoặc xác minh **Azure Key Vault Secrets Provider add-on** trên AKS theo cơ chế hỗ trợ.
4. So sánh **add-on managed identity** và **Microsoft Entra Workload Identity**.
5. Tạo `SecretProviderClass` và Pod dùng CSI volume mà **không hard-code secret value**.
6. Biết khi nào cần **đồng bộ thành Kubernetes Secret**, cùng hệ quả bảo mật và vòng đời.
7. Thiết kế rotation, refresh, rollback và phương án xử lý khi Key Vault không khả dụng.
8. Kiểm soát quyền Key Vault, Kubernetes RBAC, service account, network và audit.
9. Dùng Azure CLI/`kubectl` để xác minh cấu hình và chẩn đoán lỗi mount.
10. Lập quy trình vận hành an toàn, quan sát được và có thể khôi phục.

## 2. Vì sao không đặt mật khẩu trực tiếp trong image hoặc YAML?

Hãy xét ba cách cấu hình:

| Cách | Ví dụ | Rủi ro chính |
|---|---|---|
| Hard-code trong source/image | `DB_PASSWORD=real-password` trong Dockerfile hoặc mã nguồn. | Secret có thể tồn tại lâu dài trong image layers, Git history và artifact. |
| Giá trị thường trong Pod/ConfigMap | `env.value: real-password`. | Người có quyền đọc manifest hoặc log pipeline có thể thấy giá trị. |
| Tham chiếu secret từ nguồn được quản lý | `SecretProviderClass`, CSI volume, identity, Key Vault. | Giảm việc sao chép giá trị, nhưng vẫn phải giới hạn quyền và bảo vệ runtime. |

Với secret thật, **không** thêm vào Git kể cả trong một commit sẽ bị xóa ngay sau đó; lịch sử commit, CI logs hoặc cache có thể đã chứa giá trị. Nếu nghi ngờ bị lộ, **thu hồi/rotate** credential, không chỉ xóa dòng chứa mật khẩu.

### Secret không giống thông số cấu hình thường

- **Thông số không nhạy cảm:** tên môi trường, mức log, thời gian timeout → ConfigMap/env var thông thường khi phù hợp.
- **Secret:** mật khẩu, API key, private key, credential/certificate nhạy cảm → cơ chế bảo vệ chuyên dụng.
- **Identity-based access:** nếu ứng dụng đích hỗ trợ Microsoft Entra authentication, có thể **không cần lưu mật khẩu**. Đây thường là hướng ưu tiên so với tạo thêm một secret chỉ để chứng minh tích hợp.

## 3. Key Vault có những loại đối tượng gì?

| Loại | Mục đích | Ví dụ |
|---|---|---|
| **Secret** | Lưu giá trị bí mật dạng chuỗi/bytes theo API hỗ trợ. | Database password, API token, connection string. |
| **Key** | Quản lý khóa mật mã và các thao tác crypto được hỗ trợ. | Key encryption key, signing key. |
| **Certificate** | Quản lý chứng chỉ và vòng đời liên quan. | Chứng chỉ TLS, chuỗi chứng chỉ, khóa riêng trong cấu hình hỗ trợ. |

**Key Vault secret không đồng nghĩa Kubernetes Secret.** Key Vault là dịch vụ ngoài cluster, có version, policy và audit riêng. Kubernetes Secret là một đối tượng trong Kubernetes API, được lưu/đồng bộ theo cơ chế control plane của cluster.

Không mặc định lấy certificate/key qua CSI sẽ tạo đúng định dạng PEM/PFX cho mọi ứng dụng. Nội dung mount phụ thuộc **objectType, loại object, định dạng được provider hỗ trợ và cấu hình chuyển đổi**. Khi làm việc với private key, cần kiểm tra kỹ quyền đọc và cấu trúc chứng chỉ, đồng thời không xuất private key vào log.

## 4. Kiến trúc tích hợp AKS – Secrets Store CSI Driver – Key Vault

Luồng khái niệm:

```text
                  Microsoft Entra ID
                          |
             Managed identity / Workload Identity
                          |
                          v
                     Azure Key Vault
                      secret / key / cert
                          ^
                          | yêu cầu lấy object có quyền
                          |
AKS cluster               |
┌──────────────────────────────────────────────────────┐
│ Node                                                 │
│  Secrets Store CSI Driver + Azure Key Vault Provider  │
│       |                                              │
│       | CSI volume mount                             │
│       v                                              │
│  Pod: orders-api                                      │
│    /mnt/secrets-store/db-password (file, read-only)  │
│       |                                              │
│       v                                              │
│  Ứng dụng đọc file secret                            │
└──────────────────────────────────────────────────────┘
```

Các thành phần chính:

1. **Key Vault:** nguồn giá trị và policy truy cập.
2. **AKS add-on:** cài và quản lý các thành phần Secrets Store CSI Driver cùng Azure provider theo mô hình AKS.
3. **SecretProviderClass:** Kubernetes custom resource xác định vault nào, các object nào, kiểu object và identity mode.
4. **Pod CSI volume:** khai báo mount và liên kết tới SecretProviderClass.
5. **Identity:** cho phép provider đọc object từ Key Vault theo quyền đã cấp.
6. **Kubernetes RBAC/Pod security:** giới hạn ai có thể triển khai Pod có mount và ai có thể đọc file secret bên trong container.

**Khi ứng dụng đọc trực tiếp file CSI, không bắt buộc có Kubernetes Secret.** Việc đồng bộ sang Kubernetes Secret chỉ là tùy chọn khi một ứng dụng/controller cần giao diện Kubernetes Secret.

### SecretProviderClass nằm ở đâu?

SecretProviderClass là **tài nguyên có namespace**. Pod thường cần tham chiếu một SecretProviderClass trong **cùng namespace**. Tên vault, tên object và identity không được suy ra từ tên file; chúng phải đúng cấu hình đã được phê duyệt.

## 5. Kubernetes Secret và CSI-mounted secret khác nhau ra sao?

| Tiêu chí | Kubernetes Secret thông thường | CSI mount từ Azure Key Vault |
|---|---|---|
| Nguồn dữ liệu | Object do Kubernetes API quản lý. | Key Vault object đọc qua CSI provider. |
| Cách ứng dụng dùng | Env var hoặc volume. | File trong volume CSI, hoặc sync tùy chọn sang Kubernetes Secret. |
| Nơi lưu chính | Cluster control plane/etcd theo mô hình Kubernetes. | Key Vault; file được mount trên node/Pod theo cơ chế CSI. |
| Cách tạo giá trị | API hoặc công cụ đồng bộ/automation. | Vault + identity + SecretProviderClass. |
| Rotation | Phải cập nhật object và xem app refresh thế nào. | Có cơ chế rotation/remount khi bật hỗ trợ; app cần xử lý thay đổi file. |
| Bề mặt truy cập | RBAC cho Kubernetes Secret, quyền Pod/service account. | Key Vault authorization, pod/CSI configuration và runtime file permissions. |
| Rủi ro đặc thù | Giá trị base64 dễ bị hiểu nhầm là đã mã hóa. | Lỗi mount nếu identity, Key Vault, mạng hoặc provider không hoạt động. |

**Base64 không phải mã hóa.** Giá trị `data:` trong Kubernetes Secret thường được biểu diễn base64 để truyền trong API. Bất kỳ ai có quyền đọc Secret và giải mã base64 đều có thể lấy plaintext. Với yêu cầu bảo mật cao, phải kiểm soát Kubernetes RBAC, việc mã hóa dữ liệu control plane theo khả năng nền tảng và toàn bộ đường tạo/phân phối secret.

CSI mount giảm nhu cầu tồn tại bản secret trong Kubernetes API **chỉ khi bạn không bật Secret sync**. Giá trị vẫn xuất hiện ở **runtime filesystem của Pod** và có thể bị đọc bởi tiến trình có quyền; đây không phải một giải pháp “không bao giờ có plaintext”.

## 6. Các phương án xác thực với Azure Key Vault

Hai lựa chọn thường gặp trên AKS:

### A. Managed identity gắn với hạ tầng add-on/node

Khi bật AKS Azure Key Vault Secrets Provider add-on, AKS thường tạo một **user-assigned managed identity** cho add-on trong **node resource group** và cấu hình nó để provider sử dụng theo tính năng hỗ trợ.

Ưu điểm:

- Triển khai nhanh, phù hợp lab hoặc cluster cần cách bắt đầu đơn giản.
- Có thể không phải tạo federated credential riêng cho từng ứng dụng trong cách cấu hình managed identity.

Cần cân nhắc:

- Identity gắn với node/add-on có phạm vi chia sẻ hạ tầng rộng hơn workload cụ thể.
- Nếu cấp quyền đọc quá nhiều secrets cho identity, các workload có khả năng sử dụng cùng identity theo cấu hình và quyền cluster có thể tạo rủi ro truy cập ngang.
- Quản trị viên phải biết **client ID và principal ID** khác nhau: client ID dùng trong một số cấu hình provider, principal/object ID thường dùng cho role assignment.

### B. Microsoft Entra Workload Identity

**Workload Identity** liên kết một **Kubernetes ServiceAccount** với một danh tính Microsoft Entra qua **OIDC issuer + federated identity credential**. Quyền đọc Key Vault được cấp cho identity tương ứng với workload.

Ưu điểm:

- Tách quyền theo ứng dụng/namespace/service account rõ ràng hơn.
- Không cần nhúng client secret dành cho xác thực Entra vào Pod.
- Phù hợp khi có nhiều ứng dụng với phạm vi bí mật khác nhau.

Cần chuẩn bị:

1. AKS bật **OIDC issuer** và **workload identity**.
2. Managed identity hoặc đối tượng Entra phù hợp làm danh tính workload.
3. Federated credential dùng đúng **issuer, audience, subject**.
4. ServiceAccount có annotation client ID đúng.
5. Pod có label bật Workload Identity và dùng đúng ServiceAccount.
6. SecretProviderClass chọn identity phù hợp.
7. Identity có quyền **đọc object trong Key Vault** và có đường mạng tới vault.

**Workload Identity không thay thế CSI Driver.** Workload Identity giải quyết **xác thực**, còn CSI Driver/Key Vault provider giải quyết **lấy secret và mount file**.

### Chọn phương án nào?

| Tình huống | Hướng cân nhắc |
|---|---|
| Lab nhỏ, thử mount một secret, ít nhóm chia sẻ cluster | Add-on managed identity. |
| Nhiều nhóm/namespace có vault và policy khác nhau | Workload Identity theo service account. |
| Ứng dụng gọi trực tiếp Key Vault SDK mà không muốn mount file | Workload Identity + SDK và quyền vault; CSI không bắt buộc. |
| Workload cần Kubernetes Secret cho controller cũ | CSI + optional sync, nhưng cần cân nhắc bề mặt lộ dữ liệu. |

## 7. Quyền Key Vault: control plane khác data plane

Một identity được cấp quyền trên Azure Resource Manager **chưa chắc được phép đọc giá trị secret**. Với Key Vault, quyền quản trị resource và quyền dùng dữ liệu có thể là hai lớp riêng, tùy cấu hình permission model của vault.

| Quyền | Cho phép làm gì? | Ví dụ |
|---|---|---|
| Azure RBAC quản lý resource | Tạo/sửa vault và cấu hình ARM theo role. | Một role quản trị Azure ở scope phù hợp. |
| **Key Vault Secrets User** | Đọc giá trị secret qua mô hình Azure RBAC của Key Vault. | Provider dùng để lấy `db-password`. |
| Quyền dùng Key Vault key/certificate | Truy cập key/certificate theo kiểu object và thao tác. | Role/permission khác tương ứng, không suy từ Secrets User. |
| Kubernetes RBAC | Tạo Pod, ServiceAccount, SecretProviderClass, đọc Kubernetes Secrets. | Role trong namespace. |
| Quyền trong container | Đọc file được mount, mở kết nối tới hệ thống đích. | User/group, volume mount và chính sách Pod. |

Nếu vault dùng **Key Vault access policy model** thay vì Azure RBAC model, quyền cấp phải tuân theo mô hình đó. Không cấp cả hai loại quyền một cách tùy tiện và không suy diễn role assignment không có hiệu lực nghĩa là “Key Vault bị lỗi” trước khi kiểm tra permission model.

### Nguyên tắc least privilege

- Cấp quyền **chỉ đọc secret** cho identity ứng dụng cần đọc.
- Nếu có thể, tách vault/identity theo nhóm sản phẩm hoặc ranh giới bảo mật.
- Không dùng cùng một identity có quyền đọc mọi secret của nhiều môi trường Production/Development.
- Hạn chế quyền tạo/sửa `SecretProviderClass` và Pod đối với người không quản trị workload.
- Rà soát role assignments khi ứng dụng nghỉ dùng hoặc chuyển namespace.

**Một tên SecretProviderClass không phải rào chắn bảo mật.** Người có quyền tạo Pod có thể lựa chọn volume/identity theo khả năng cấu hình; quyền Azure và Kubernetes phải được thiết kế phối hợp.

## 8. Điều kiện tiên quyết cho một bài lab an toàn

Giả sử môi trường học có:

| Tài nguyên | Giá trị minh họa |
|---|---|
| Resource group AKS | `rg-aks-lab` |
| Cluster | `aks-lab` |
| Namespace ứng dụng | `orders` |
| Key Vault | `kv-orders-lab` |
| Key Vault secret | `orders-db-password` |
| Managed identity | `mi-orders-reader` hoặc identity add-on |
| SecretProviderClass | `kv-orders` |
| Container mount path | `/mnt/secrets-store` |
| File sẽ có trong Pod | `/mnt/secrets-store/orders-db-password` |

Bạn cần:

1. Azure CLI, `kubectl` và phiên bản extension tương thích với AKS cluster.
2. Quyền trên AKS và Kubernetes namespace để cấu hình add-on/identity/Pod theo bài lab.
3. Quyền tối thiểu để quản lý role assignment và truy cập Key Vault theo quy trình tổ chức.
4. Cluster đang hoạt động, node đủ capacity, DNS/network tới Key Vault.
5. Một **secret giả lập**, tuyệt đối không phải credential Production.
6. Môi trường thử nghiệm và hạn mức chi phí được phê duyệt.

Trước mọi thao tác ghi, xác minh cluster context:

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

kubectl config current-context
kubectl get nodes
```

`kubectl get nodes` chỉ giúp kiểm tra connectivity tới Kubernetes API và các node, **không chứng minh** quyền dùng Key Vault hay khả năng mount secret.

## 9. Bật Azure Key Vault Secrets Provider add-on

Với AKS được phép thay đổi, add-on có thể được bật qua Azure CLI:

```bash
az aks enable-addons \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --addons azure-keyvault-secrets-provider
```

**Đây là lệnh thay đổi cluster** và phải thực hiện trong môi trường lab/cluster được cấp quyền. AKS quản lý những thành phần add-on theo mô hình của dịch vụ; không nên đồng thời cài thủ công một bản CSI driver khác chồng chéo mà chưa hiểu khả năng tương thích.

### Kiểm tra add-on

```bash
az aks show \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --query "addonProfiles.azureKeyvaultSecretsProvider" \
  --output json

kubectl get csidriver
kubectl get secretproviderclass --all-namespaces
```

Bạn kỳ vọng có CSI driver với tên `secrets-store.csi.k8s.io` và các thành phần Azure provider tương ứng khi triển khai thành công. Nếu `SecretProviderClass` chưa có, điều đó bình thường: đây là resource do người vận hành **tạo sau**, không phải add-on tự tạo cho mọi Pod.

### Identity của add-on

Sau khi bật add-on, AKS có thể cung cấp một identity cho provider. Đọc metadata trả về trong phần `identity.clientId` / `identity.objectId` theo schema thực tế của add-on. **Không tự đoán client ID** từ tên managed identity.

Bảng kiểm:

- Add-on báo trạng thái enabled/succeeded.
- Driver/provider Pods hoặc DaemonSets chạy trên các node phù hợp.
- Có client ID của identity dùng để truy cập vault.
- Key Vault đã cấp quyền read cho đúng principal.
- Node/pod có đường truy cập vault khi mount.

## 10. Mô hình 1: SecretProviderClass dùng add-on managed identity

Sau khi chuẩn bị Key Vault secret và cấp quyền cho identity add-on, tạo `SecretProviderClass` trong namespace `orders`.

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "true"
    userAssignedIdentityID: "<ADDON_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
```

Giải thích các trường:

| Trường | Ý nghĩa |
|---|---|
| `provider: azure` | Chọn Azure Key Vault provider của CSI driver. |
| `useVMManagedIdentity: "true"` | Dùng managed identity được gắn với VM/node theo cách provider hỗ trợ. |
| `userAssignedIdentityID` | Client ID của user-assigned identity cần dùng. |
| `keyvaultName` | Tên Key Vault chứa object. |
| `tenantId` | Microsoft Entra tenant chứa vault/identity theo cấu hình phù hợp. |
| `objects.array[].objectName` | Tên object trong Key Vault. |
| `objectType: secret` | Đây là Key Vault **secret**, không phải key/cert. |
| `objectVersion: ""` | Không khóa cứng vào một version cụ thể theo cú pháp của provider. |

**Lưu ý về quyền:** cấu hình YAML đúng không thay thế việc gán quyền read cho identity. Nếu không có quyền Key Vault hoặc egress bị chặn, Pod có thể thất bại ở bước mount.

### Vì sao có cả tên secret và tên file?

Trong ví dụ, object tên `orders-db-password` sẽ xuất hiện dưới dạng file trong mount path theo cách provider biểu diễn tên object. Nếu cấu hình **objectAlias**, tên file mount có thể là alias thay vì objectName; khi đồng bộ Kubernetes Secret, phải dùng đúng tên nội dung đã mount.

## 11. Pod mount secret thành file chỉ đọc

Với `SecretProviderClass` trên, tạo một Pod minh họa:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-secret-check
  namespace: orders
spec:
  containers:
    - name: checker
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: secrets-store
          mountPath: /mnt/secrets-store
          readOnly: true
  volumes:
    - name: secrets-store
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: kv-orders
```

Đây là Pod phục vụ **kiểm tra mount**, không phải cách tạo database password thật. Các dòng quan trọng:

- `driver: secrets-store.csi.k8s.io`: sử dụng Secrets Store CSI Driver.
- `secretProviderClass: kv-orders`: tìm resource cùng namespace.
- `mountPath: /mnt/secrets-store`: file có thể được đọc tại đây.
- `readOnly: true`: ngăn ứng dụng sửa trực tiếp nội dung volume.

### Xác minh mà không tiết lộ secret

Sau khi tạo trong lab:

```bash
kubectl -n orders get pod orders-secret-check
kubectl -n orders describe pod orders-secret-check

kubectl -n orders exec orders-secret-check -- \
  test -s /mnt/secrets-store/orders-db-password
```

Lệnh `test -s` chỉ kiểm tra file có tồn tại và không rỗng; **không in giá trị secret**. Tránh chạy `cat /mnt/secrets-store/orders-db-password` trong terminal có ghi log hoặc chia sẻ màn hình.

Nếu Pod chưa chạy, xem **Events** của Pod trước khi kết luận code ứng dụng lỗi. Với CSI mount thất bại, Pod có thể không đi tới giai đoạn container start.

## 12. Mô hình 2: Microsoft Entra Workload Identity cho từng ứng dụng

Khi muốn tách quyền rõ ràng giữa `orders-api` và `billing-api`, dùng Workload Identity với service account riêng.

### Bật OIDC issuer và Workload Identity trên AKS

Trong cluster được phê duyệt:

```bash
az aks update \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --enable-oidc-issuer \
  --enable-workload-identity
```

**Lệnh này thay đổi cấu hình cluster.** Trước khi chạy, kiểm tra khả năng hỗ trợ và tác động đến cluster hiện có. Add-on CSI vẫn phải được cài/bật riêng nếu ứng dụng dùng CSI mount.

Xác minh issuer:

```bash
az aks show \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --query "oidcIssuerProfile.issuerUrl" \
  --output tsv
```

### Tạo identity và federated credential

Chuẩn bị user-assigned managed identity riêng cho workload. Federated credential cần khớp chính xác:

| Thành phần | Ví dụ |
|---|---|
| Issuer | URL OIDC issuer được AKS trả về. |
| Subject | `system:serviceaccount:orders:orders-sa` |
| Audience | `api://AzureADTokenExchange` |
| Client ID | Client ID của user-assigned managed identity. |

Minh họa lệnh khi identity và namespace đã được chuẩn bị:

```bash
az identity federated-credential create \
  --resource-group "<IDENTITY_RESOURCE_GROUP>" \
  --identity-name "<WORKLOAD_IDENTITY_NAME>" \
  --name "orders-aks-federation" \
  --issuer "<AKS_OIDC_ISSUER_URL>" \
  --subject "system:serviceaccount:orders:orders-sa" \
  --audiences "api://AzureADTokenExchange"
```

Đây là lệnh tạo credential liên kết và cần quyền tương ứng. Nếu issuer hoặc subject khác dù chỉ một ký tự, token exchange có thể thất bại.

### Kubernetes ServiceAccount

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-sa
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<WORKLOAD_IDENTITY_CLIENT_ID>"
```

### SecretProviderClass dùng Workload Identity

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders-wi
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    clientID: "<WORKLOAD_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
```

Khác biệt quan trọng so với ví dụ trước: Workload Identity dùng **clientID** theo cấu hình của provider thay vì `useVMManagedIdentity: "true"` và `userAssignedIdentityID`. Tùy phiên bản provider, chi tiết tham số hỗ trợ phải được xác minh trong tài liệu của phiên bản đang chạy.

### Pod dùng service account và nhãn Workload Identity

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-wi-check
  namespace: orders
  labels:
    azure.workload.identity/use: "true"
spec:
  serviceAccountName: orders-sa
  containers:
    - name: checker
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: secrets-store
          mountPath: /mnt/secrets-store
          readOnly: true
  volumes:
    - name: secrets-store
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: kv-orders-wi
```

Kiểm tra cả **ServiceAccount annotation**, **Pod label**, **client ID trong SecretProviderClass**, **federated credential** và **quyền Key Vault**. Chỉ gán `serviceAccountName` thôi chưa đủ để AKS tự có quyền đọc vault.

### Một lưu ý về phạm vi truy cập

Workload Identity giúp giảm việc dùng một identity chung cho nhiều workload, nhưng bảo mật vẫn phụ thuộc vào ai có thể **tạo/sửa Pod, ServiceAccount, SecretProviderClass và federation**. Nếu người dùng có quyền sửa template Pod để giả làm workload khác, cần ràng buộc bằng Kubernetes RBAC, admission policy và quản lý namespace thích hợp.

## 13. Gán quyền đọc Key Vault đúng loại object

Giả sử vault được cấu hình theo **Azure RBAC permission model**. Identity cần quyền đọc secret theo vai trò phù hợp.

Lệnh minh họa:

```bash
az role assignment create \
  --assignee-object-id "<IDENTITY_PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "<KEY_VAULT_RESOURCE_ID>"
```

**Đây là lệnh tạo role assignment**, không chạy nếu chưa có phê duyệt. Phân biệt:

- **Client ID:** định danh ứng dụng/managed identity dùng ở một số tham số provider.
- **Principal/Object ID:** đối tượng Entra dùng để cấp Azure RBAC.
- **Resource ID của vault:** phạm vi role assignment.

### Phân quyền theo loại object

Nếu provider lấy:

- **Secret:** quyền đọc secret tương ứng, ví dụ `Key Vault Secrets User` trong RBAC model.
- **Certificate:** quyền xem/lấy chứng chỉ và, khi cần nội dung private key qua secret backing object, quyền phù hợp theo cơ chế đối tượng.
- **Key:** quyền sử dụng/đọc thông tin key hoặc thao tác crypto theo khả năng cung cấp, không mặc định dùng `Key Vault Secrets User`.

Không chỉ sao chép quyền từ ví dụ password cho chứng chỉ hoặc khóa ký số. Với credential có yêu cầu pháp lý, nên phối hợp nhóm security để chọn vault, loại key, scope và rotation phù hợp.

### Kiểm tra quyền mà không xem giá trị

```bash
az role assignment list \
  --assignee "<IDENTITY_PRINCIPAL_ID>" \
  --scope "<KEY_VAULT_RESOURCE_ID>" \
  --output table
```

Kết quả là một phần của việc xác minh; quyền hiệu lực còn có thể chịu ảnh hưởng của permission model, propagation delay, deny assignment hoặc điều kiện truy cập. Tránh đọc secret value chỉ để kiểm tra identity.

## 14. Đồng bộ thành Kubernetes Secret: khi nào nên dùng?

Một số ứng dụng hoặc controller chỉ hỗ trợ đọc **Kubernetes Secret** qua `secretKeyRef`, `envFrom` hoặc nguồn dữ liệu Kubernetes API. Secrets Store CSI Driver có thể **đồng bộ object đã mount** thành Kubernetes Secret nếu cấu hình `secretObjects` và bản driver/provider hỗ trợ.

Ví dụ mở rộng `SecretProviderClass`:

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders-sync
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "true"
    userAssignedIdentityID: "<ADDON_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
  secretObjects:
    - secretName: orders-db-credential
      type: Opaque
      data:
        - objectName: orders-db-password
          key: password
```

Khi Pod tiêu thụ SecretProviderClass này qua CSI mount, driver có thể tạo hoặc cập nhật Kubernetes Secret `orders-db-credential` chứa khóa `password`.

Một ứng dụng cũ có thể dùng:

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credential
        key: password
```

### Hệ quả quan trọng

1. **Dữ liệu đã được sao chép vào Kubernetes Secret.** Bảo mật phải áp dụng cả phía Kubernetes API/etcd.
2. Sync Kubernetes Secret phụ thuộc vào **Pod thực sự mount SecretProviderClass**; không nên giả định chỉ tạo SecretProviderClass là Secret lập tức tồn tại.
3. Cần có đối tượng đang tiêu thụ volume theo yêu cầu driver; khi không còn Pod dùng, vòng đời synced Secret có thể thay đổi theo cơ chế driver.
4. Với `objectAlias`, giá trị `secretObjects.data[].objectName` cần khớp **tên file đã được mount** chứ không nhất thiết là objectName gốc.
5. Nếu **environment variable** được tạo từ Kubernetes Secret, container đang chạy **không tự nhận giá trị mới** khi Secret object thay đổi. Cần restart/rollout Pod theo quy trình.
6. Không xem base64 trong `kubectl get secret -o yaml` là bảo mật; người có quyền đọc có thể lấy giá trị.

**Ưu tiên file CSI mount trực tiếp** nếu ứng dụng có thể đọc secret từ file và không bắt buộc một Kubernetes Secret trung gian.

## 15. Rotation: secret đổi rồi ứng dụng có nhận bản mới không?

Đây là một trong những điểm dễ gây gián đoạn Production nhất.

### Có ba đồng hồ khác nhau

1. **Key Vault rotation/update:** thời điểm secret có phiên bản mới hoặc credential đích được thay.
2. **CSI provider refresh:** thời điểm driver/provider cập nhật file đã mount theo tính năng rotation được bật và chu kỳ polling.
3. **Ứng dụng refresh:** thời điểm tiến trình thực sự đọc lại file, tạo lại connection pool hoặc load lại certificate.

```text
09:00  Secret version A trong Key Vault
       Pod mount file A, ứng dụng đọc A

10:00  Thêm secret version B trong Key Vault
       ↓
10:02+ CSI rotation cập nhật nội dung file theo cấu hình
       ↓
10:05  Ứng dụng re-read/reload và dùng B
       ↓
10:15  Thu hồi credential A sau khi kiểm tra toàn hệ thống
```

Mốc thời gian trong hình chỉ **minh họa**, không phải cam kết SLA. Thời gian thực tế phụ thuộc polling interval, kết nối tới vault, cách provider refresh và hành vi ứng dụng.

### Bật rotation trên add-on

Trong AKS được phép và với tính năng hỗ trợ:

```bash
az aks addon update \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --addon azure-keyvault-secrets-provider \
  --enable-secret-rotation \
  --rotation-poll-interval 2m
```

Lệnh này **thay đổi cluster**. Chu kỳ `2m` là ví dụ cấu hình, không bảo đảm mọi ứng dụng nhận secret sau đúng hai phút. Kiểm tra loại add-on, phiên bản AKS và giá trị poll interval được hỗ trợ trước khi áp dụng.

### Hai bẫy thường gặp

- **Pin version:** nếu `objectVersion` chỉ định chính xác một phiên bản Key Vault, tạo version mới **không tự đổi** object mà provider đang đọc cho tới khi bạn sửa cấu hình.
- **Mount bằng subPath:** nếu container mount secret file qua `subPath`, cơ chế cập nhật file của CSI có thể **không hiển thị** thay đổi như khi mount cả directory. Với nhu cầu rotation, ưu tiên mount **thư mục** và ứng dụng đọc lại đường dẫn đúng cách.

### App cache secret trong bộ nhớ

Nếu ứng dụng đọc mật khẩu lúc startup rồi giữ mãi trong biến, việc file mount được cập nhật **không buộc** connection pool đổi credential. Có thể cần:

- File watcher/reload có kiểm thử.
- Tái tạo connection pool khi credential đổi.
- Rolling restart/rollout theo lịch/phê duyệt.
- Khoảng thời gian **cả A và B cùng hợp lệ** nếu hệ thống đích cho phép, để chuyển đổi an toàn.

## 16. Chứng chỉ TLS qua CSI: lưu ý riêng

Ngoài password, CSI provider có thể lấy certificate trong những định dạng được hỗ trợ để mount vào container. Một số ứng dụng yêu cầu:

- Chứng chỉ và private key ở **hai file riêng**.
- PEM chain đầy đủ, đúng hostname.
- File được cập nhật nhưng server phải **reload TLS context**.
- Quyền đọc file giới hạn trong UID/GID của tiến trình.
- Không restart đột ngột toàn bộ replicas cùng lúc.

Vì vậy, với certificate:

1. Xác định object type/format được Key Vault provider trả về.
2. Xác minh đường dẫn và nội dung bằng cách kiểm tra định dạng **không xuất private key**.
3. Thiết kế rotation với thời điểm chồng lấn hợp lệ của certificate A/B.
4. Kiểm tra readiness và HTTPS handshake từ client.
5. Giám sát expiry trước hạn; không đợi đến khi browser báo certificate expired.

### CSI mount khác Kubernetes TLS Secret

Một Ingress controller thường yêu cầu Kubernetes Secret kiểu `kubernetes.io/tls`; khi đó có thể cần cơ chế đồng bộ phù hợp hoặc controller có tích hợp Key Vault riêng. Không giả định mount file vào một Pod ứng dụng sẽ tự đổi TLS certificate của Ingress controller đang chạy trong Pod khác.

## 17. Bảo mật mạng giữa AKS và Key Vault

Ngay cả khi identity được cấp quyền đúng, provider vẫn phải **kết nối tới Key Vault** và các endpoint danh tính/phụ trợ theo kiến trúc.

Các điểm kiểm tra:

- AKS node/pod có DNS phân giải hostname vault đúng không?
- Network Security Group, Azure Firewall, UDR hoặc egress policy có cho phép luồng cần thiết không?
- Nếu Key Vault dùng **Private Endpoint**, VNet và private DNS zone liên quan (ví dụ tên miền private link của Key Vault theo thiết kế) đã được cấu hình đúng chưa?
- VNet peering/hub-spoke có cho phép đường đi tới private endpoint không?
- Chính sách Key Vault firewall có chặn traffic không?
- Cluster đang dùng node pool hoặc cấu hình mạng mới có thay đổi đường egress không?
- Tài nguyên Entra identity/metadata service có được truy cập qua phương thức đã được hỗ trợ không?

**Private Endpoint không tự trao quyền đọc secret.** Nó giới hạn đường mạng, còn identity/Key Vault authorization vẫn quyết định thao tác `Get` có hợp lệ không.

### Khi vault chuyển từ public sang private

Trước khi chặn public network:

1. Xác minh DNS của các node AKS có thể phân giải tên vault sang private endpoint đúng.
2. Kiểm tra route và firewall cho luồng Key Vault.
3. Dùng một workload lab mount được secret qua mạng private.
4. Giám sát CSI mount và Key Vault logs.
5. Mới áp dụng thay đổi trên Production với cửa sổ rollback đã được thống nhất.

Không coi một lần `curl` từ laptop quản trị là bằng chứng pod/node truy cập private vault được; nguồn mạng và DNS khác nhau.

## 18. Kubernetes RBAC và an toàn của Pod

Azure RBAC trên Key Vault là một lớp; Kubernetes RBAC và Pod isolation là lớp còn lại.

### Những quyền Kubernetes đáng kiểm soát

| Hành động | Rủi ro nếu cấp rộng |
|---|---|
| Tạo/sửa Pod hoặc Deployment | Người dùng có thể chạy container khác để đọc file secret được mount bằng identity mà workload sử dụng. |
| Tạo/sửa SecretProviderClass | Có thể đổi tên Key Vault object hoặc cấu hình truy cập mà identity được cấp quyền. |
| Đọc Kubernetes Secret | Có thể lấy giá trị đã được sync vào API. |
| `kubectl exec` vào Pod | Có thể đọc file secret mà container thấy. |
| Xem logs | Có thể lộ secret nếu ứng dụng vô tình in credential. |
| Sửa ServiceAccount/federation | Có thể mở đường dùng identity khác nếu cấu hình cấp quyền không chặt. |

### Biện pháp giảm thiểu

- Namespace riêng cho team/environment.
- Role/RoleBinding hẹp; hạn chế `secrets get/list/watch` khi không cần.
- Admission policies và Pod Security theo khả năng nền tảng, hạn chế chạy đặc quyền.
- Không mount secret vào sidecar không cần dùng.
- Không dùng shared service account/identity cho hàng loạt workload không liên quan.
- Dùng image tin cậy, quét lỗ hổng, patch và kiểm soát quyền tạo workload.
- Khi cần phân tách mạnh, xem xét cluster/node pool/subscription/vault tách biệt thay vì chỉ dựa vào tên namespace.

**Bất kỳ tiến trình nào có quyền đọc file đã mount đều có thể lấy secret.** CSI không bảo vệ secret khỏi một container đã bị chiếm quyền ở mức đủ cao. Thiết kế workload security vẫn là điều kiện bắt buộc.

## 19. Triển khai bằng GitOps/IaC mà không để lộ secret

Một mô hình GitOps tốt lưu **tham chiếu**, không lưu giá trị bí mật:

```text
Git repository
├── Namespace/ServiceAccount
├── SecretProviderClass: vault name + object names + identity ref
├── Deployment: CSI volume + mountPath
├── RBAC/network policy
└── KHÔNG chứa password/API token/private key
             |
             v
  CI/CD hoặc GitOps controller
             |
             v
  AKS apply manifests
             |
             v
  Pod sử dụng identity → Key Vault → mount secret file
```

### Những gì vẫn phải giữ kín

- Terraform state/IaC outputs có thể chứa secret nếu bạn đã đưa secret value vào biến/output.
- Helm values chứa password plaintext vẫn có thể bị log trong release history hoặc pipeline.
- Kubeconfig/credential quản trị cluster.
- Storage/registry/service principal secrets dùng ngoài Workload Identity.
- Key Vault export, file backup và nội dung log có token.

**SecretProviderClass có tên object và vault**: thường không phải secret value, nhưng đây vẫn có thể là metadata nhạy cảm về kiến trúc; áp dụng phân quyền repository phù hợp.

## 20. Quan sát tích hợp: phải xem nhiều nguồn log

Một sự cố “Pod không start” có thể phát sinh từ ba tầng khác nhau:

| Nguồn | Có thể phát hiện | Không thể kết luận một mình |
|---|---|---|
| **Kubernetes Pod events** | `FailedMount`, timeout, thiếu SecretProviderClass, lỗi lấy object. | Không mô tả đầy đủ policy Key Vault hoặc network. |
| **CSI Driver / Azure Provider logs** | Lỗi giao tiếp provider, identity, mount/rotation. | Không biết ứng dụng đã đọc và dùng secret đúng chưa. |
| **Key Vault diagnostic logs** | Yêu cầu Get, lỗi authorization, tình trạng liên quan vault. | Không chứng minh container process đã reload secret. |
| **Microsoft Entra sign-in/workload identity diagnostics** | Lỗi exchange token/credential khi log có sẵn. | Không chứng minh filesystem mount thành công. |
| **Application logs/metrics** | DB authentication failure, TLS expiry, kết nối thành công/thất bại. | Không giải thích đầy đủ vì sao Key Vault Get bị từ chối. |
| **Azure Activity Log** | Thay đổi Key Vault resource, role assignments, AKS add-on theo control plane. | Không mặc định ghi toàn bộ thao tác đọc giá trị Key Vault. |

### Kiểm tra Pod events

```bash
kubectl -n orders describe pod orders-secret-check

kubectl -n orders get events \
  --sort-by=.metadata.creationTimestamp
```

Đọc các thông báo liên quan `MountVolume.SetUp failed`, `FailedMount`, `SecretProviderClass not found`, `Forbidden`, `Unauthorized` hoặc timeout. Nội dung chính xác phụ thuộc driver/provider.

### Kiểm tra driver/provider Pods

```bash
kubectl -n kube-system get pods
kubectl get csidriver
kubectl -n orders get secretproviderclass
kubectl -n orders get secretproviderclasspodstatus
```

Tìm các Pods/DaemonSets liên quan Secrets Store CSI và Azure Provider trong `kube-system` theo tên thực tế. Chọn đúng Pod và container trước khi dùng `kubectl logs`; tránh copy command dùng tên component của một phiên bản khác.

Tài nguyên `SecretProviderClassPodStatus` có thể hiển thị thông tin object versions được mount theo driver; **không in nội dung secret**. Nó giúp đối chiếu Pod đã nhận version nào trong kịch bản rotation.

## 21. Bảng chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra ưu tiên |
|---|---|---|
| `SecretProviderClass not found` | Tên sai, resource chưa tạo hoặc khác namespace. | So `volumeAttributes.secretProviderClass`, namespace và `kubectl get spc`. |
| Pod dừng ở `ContainerCreating` với `FailedMount` | Driver/provider, identity, vault hoặc network. | Pod events, CSI/provider logs, Key Vault audit. |
| `Forbidden` khi đọc vault | Identity chưa được cấp role hoặc vault dùng permission model khác. | Principal ID, Key Vault RBAC/access policy, scope. |
| `Identity not found` hoặc không lấy được token | Managed identity chưa gắn node; Workload Identity federation/SA mismatch. | Add-on identity, OIDC issuer, subject, audience, client ID. |
| `SecretNotFound` | Sai objectName, vault hoặc version; secret bị disable/deleted. | Metadata object, vault name, tên/version. |
| Timeout tới Key Vault | DNS, firewall, private endpoint, routing hoặc outbound egress. | Kiểm tra đường mạng từ AKS node/pod, không chỉ laptop. |
| Mount có file nhưng ứng dụng báo thiếu credential | App đọc sai path, tên file alias hoặc permission. | mountPath, objectAlias, user UID/GID, app config. |
| Rotation thành công nhưng app vẫn dùng A | Ứng dụng cache, env var không refresh hoặc subPath mount. | Refresh logic, mounted file, pod rollout. |
| Synced Kubernetes Secret không xuất hiện | Không có Pod mount SPC, cấu hình `secretObjects` sai hoặc sync không hỗ trợ. | Pod lifecycle, object mapping, driver events. |
| Certificate mới nhưng client thấy cert cũ | Process/Ingress chưa reload TLS. | TLS endpoint, controller config, rollout/reload. |
| Một namespace đọc được, namespace khác không | Service account/federated credential/identity/RBAC khác nhau. | So subject, Pod label, SPC, vault policy. |
| Image chạy nhưng chỉ một số replicas lỗi | Node/driver deployment khác nhau hoặc rollout/credential chưa đồng bộ. | Pod node placement, plugin logs, identity/rotation state. |

### Quy trình xử lý ngắn

1. Ghi **cluster, namespace, Pod, node, revision/image, thời điểm UTC**.
2. Kiểm tra Pod events và SecretProviderClass có đúng namespace.
3. Xem driver/provider health trên node của Pod.
4. Đối chiếu identity mode: managed identity hay Workload Identity.
5. Đối chiếu Key Vault object metadata, role/scope và trạng thái secret.
6. Kiểm tra DNS/route/firewall khi có timeout.
7. Xác minh file mount tồn tại bằng lệnh **không in nội dung**.
8. Kiểm tra ứng dụng có đọc path đúng và reload được hay không.
9. Sửa **nguyên nhân hẹp nhất**, rollout có kiểm soát, xác minh metrics/logs.
10. Ghi lại timeline và hoàn nguyên các quyền tạm nếu có.

Không giải quyết `Forbidden` bằng cách cấp Owner ở subscription hoặc mở Key Vault cho toàn Internet. Điều đó có thể tạo lỗ hổng lớn hơn sự cố ban đầu.

## 22. Sự cố rotation: cách xử lý an toàn

**Tình huống:** mật khẩu DB vừa được đổi trong Key Vault; Pod vẫn Running nhưng ứng dụng trả nhiều HTTP 500 do xác thực database thất bại.

### Điều tra

1. Xác định secret version mới trong Key Vault và credential nào hệ thống đích chấp nhận.
2. Kiểm tra SecretProviderClass có `objectVersion` cố định không.
3. Xác nhận rotation đã bật và driver/provider không báo lỗi.
4. Xem thông tin object version đã mount mà không đọc giá trị.
5. Kiểm tra ứng dụng đọc file tại startup hay có cơ chế reload.
6. Nếu ứng dụng dùng synced Kubernetes Secret qua env, xác định Pods đã được restart/rollout sau cập nhật chưa.
7. Kiểm tra mọi replica/worker đã chuyển sang credential mới trước khi thu hồi bản cũ.

### Khắc phục

- Ưu tiên phương án **credential chồng lấn** nếu DB hoặc dịch vụ đích hỗ trợ.
- Nếu secret file đã cập nhật nhưng ứng dụng không reload, thực hiện rolling restart/rollout trong khung được phê duyệt.
- Nếu Key Vault reference sai, sửa SecretProviderClass và xác minh mount.
- Nếu đang cố định version cũ, cập nhật version rõ ràng hoặc chuyển sang cơ chế versionless theo yêu cầu kiểm soát.
- Theo dõi kết nối DB và HTTP 5xx trước khi xác nhận thành công.

**Rollback:** trở về credential A chỉ khi nó còn hợp lệ và được Security/DB owner phê duyệt. Không khôi phục secret đã bị thu hồi vì nghi ngờ lộ dữ liệu.

## 23. Sự cố Key Vault không khả dụng và giới hạn của CSI

Khi Key Vault không thể truy cập:

- **Pod đang chạy** có thể vẫn đang sử dụng file mount/giá trị đã tải trước đó tùy trạng thái CSI và ứng dụng.
- **Pod mới hoặc Pod được lập lịch lại** có thể thất bại khi mount nếu không lấy được object hoặc identity token.
- Rotation có thể bị trì hoãn; nếu credential hết hạn trong thời gian đó, ứng dụng có thể gặp lỗi dù Pod vẫn Running.
- Synced Kubernetes Secret có thể tồn tại theo vòng đời của driver/kubernetes object, nhưng **không coi đó là backup độc lập hoặc bảo đảm khởi động khi Key Vault mất**.

Thiết kế phục hồi nên bao gồm:

1. Giám sát Key Vault availability và lỗi CSI mount.
2. Hạn chế phụ thuộc không cần thiết vào việc khởi động Pod mới trong một sự cố Vault đang diễn ra; theo runbook điều hành.
3. Duy trì replica capacity/HA và rolling update có điều kiện.
4. Chuẩn bị Key Vault backup/recovery, soft delete và purge protection theo chính sách.
5. Thiết lập kế hoạch cho secret expiry, token/DB credential lifetime và rotation.
6. Kiểm thử tình huống mất mạng đến vault trong môi trường lab.
7. Nếu yêu cầu SLA nghiêm ngặt, đánh giá kiến trúc phụ thuộc/khả năng cache, chứ không giả định CSI tự giải quyết mọi outage.

**Không hard-code bản mật khẩu dự phòng trong image** để xử lý outage: đó là một credential lâu dài rất khó thu hồi và dễ bị lạm dụng.

## 24. Key Vault soft delete, purge protection và backup

Azure Key Vault hỗ trợ các cơ chế bảo vệ vòng đời secret/key/certificate như **soft delete** và **purge protection** theo điều kiện dịch vụ.

| Cơ chế | Bảo vệ khỏi | Không giải quyết |
|---|---|---|
| Soft delete | Xóa nhầm object hoặc vault trong thời gian giữ lại được hỗ trợ. | Ứng dụng tự động chuyển sang phiên bản mới hoặc lỗi network. |
| Purge protection | Xóa vĩnh viễn sớm hơn thời gian bảo vệ theo cơ chế hỗ trợ. | Người dùng có quyền hợp lệ đọc secret qua CSI. |
| Secret versioning | Lưu các phiên bản giá trị khi thêm version mới. | Tự làm app reload secret khi không có rotation/rollout. |
| Audit/diagnostic logs | Điều tra ai/điều gì đã thao tác trong phạm vi logs. | Ngăn chặn sự cố nếu không có alert/response. |
| Backup/recovery | Phục hồi theo phương thức được vault hỗ trợ. | Tự thay thế kiểm thử vận hành và quyền phục hồi. |

**Quy trình thu hồi khi secret bị lộ** khác rotation định kỳ: phải đánh giá token/session đang còn hiệu lực, quyền downstream, phạm vi ảnh hưởng và log truy cập. Chỉ tạo version mới trong Key Vault chưa tự vô hiệu hóa mọi credential cũ tại hệ thống đích.

## 25. Kết hợp chính sách Kubernetes và kiểm toán

Để biến cấu hình thành quy trình lặp lại, tổ chức nên có:

- **Naming convention:** `spc-<app>-<env>`, `sa-<app>` và tên object rõ owner.
- **Namespace boundaries:** Production khác Development; hạn chế shared identities.
- **Identity ownership:** ai cấp role đọc vault, ai sở hữu ServiceAccount và federation.
- **GitOps templates:** SecretProviderClass, Pod volumes và Kubernetes RBAC được review.
- **Rotation runbook:** ứng dụng nhận secret bằng file hay env, có tự reload không.
- **Secret inventory:** vault, object name, loại object, expiry/rotation, app tiêu thụ; **không** ghi giá trị.
- **Audit review:** thay đổi role, federated credentials, Pod exec và provider logs.
- **CI policy:** scan repositories/manifests để ngăn hard-coded secrets.
- **Break-glass:** quyền tạm theo phê duyệt, có audit và thu hồi sau sự cố.
- **Cost controls:** Key Vault operations, Azure Monitor ingestion và các thành phần mạng.

### Checklist review trước Production

1. Có lý do cụ thể phải dùng secret thay vì identity-based access.
2. Có managed identity hoặc Workload Identity phù hợp ranh giới workload.
3. Vault và object nằm đúng tenant/subscription/region theo chính sách.
4. Role chỉ đủ đọc những object cần thiết.
5. SecretProviderClass và Pod mounts không chứa credential plaintext.
6. Các nhóm không cần thiết không có quyền `kubectl exec` hoặc đọc Kubernetes Secret đã sync.
7. Nếu dùng synced Secret, đã đánh giá bảo mật etcd/RBAC và quy trình refresh.
8. Private networking và DNS được kiểm tra từ cluster.
9. Rotation được thử với cả **Pod đang chạy** lẫn **Pod mới**.
10. Alert, logs và runbook restore đã có người phụ trách.
11. Không có Pod sidecar/container phụ nhận secret ngoài nhu cầu.
12. Chi phí vault, logs và công vận hành phù hợp ngân sách.

## 26. Bài thực hành: bảo vệ mật khẩu cho Orders API

**Bối cảnh:** nhóm có một AKS cluster lab, namespace `orders` và ứng dụng `orders-api` cần một mật khẩu DB giả lập. Secret phải ở Azure Key Vault; Pod đọc từ file CSI. Nhóm cần chứng minh việc đổi mật khẩu không làm lộ giá trị vào Git hay console.

### Yêu cầu

| Thành phần | Giá trị minh họa |
|---|---|
| AKS cluster | `aks-lab` |
| Namespace | `orders` |
| Key Vault | `kv-orders-lab` |
| Key Vault object | `orders-db-password` (secret) |
| SecretProviderClass | `kv-orders` hoặc `kv-orders-wi` |
| Pod | `orders-secret-check` |
| File mount | `/mnt/secrets-store/orders-db-password` |
| Identity | Add-on managed identity hoặc workload-specific identity |
| Rotation | Có quy trình refresh và xác nhận ứng dụng |
| Kiểm thử | Không in giá trị secret |

### Nhiệm vụ

1. Vẽ đường đi Key Vault → identity → CSI provider → Pod file.
2. Giải thích vì sao Kubernetes Secret **không bắt buộc** trong cách mount trực tiếp.
3. Lựa chọn managed identity add-on hay Workload Identity cho cluster nhiều ứng dụng và giải thích.
4. Kiểm tra AKS add-on và các thành phần CSI hoạt động.
5. Cấp quyền read secret theo permission model của Key Vault.
6. Tạo SecretProviderClass đúng namespace và tên object.
7. Tạo Pod mount volume read-only và thử file tồn tại bằng `test -s`.
8. Nếu dùng Workload Identity, kiểm tra ServiceAccount annotation, Pod label và federated credential.
9. Viết runbook rotation khi ứng dụng chỉ đọc secret lúc khởi động.
10. Giải thích vì sao mount bằng `subPath` có thể làm rotation không hiệu quả.
11. Phân tích rủi ro nếu bật sync sang Kubernetes Secret.
12. Đề xuất các nguồn log/cảnh báo để chẩn đoán `FailedMount` và `Forbidden`.
13. Đề xuất cách phản ứng khi Key Vault không truy cập được nhưng Pod hiện hành vẫn chạy.
14. Chọn một phương án backup/khôi phục Key Vault và một biện pháp ngăn secret leak trong CI.

### Lời giải định hướng

**Kiến trúc:**

```text
Key Vault: orders-db-password
     |
     +-- RBAC: workload identity được đọc secret
     |
     v
AKS CSI Driver + Azure Provider
     |
     +-- SecretProviderClass: kv-orders-wi
     |
     v
Pod orders-secret-check
     |
     +-- file /mnt/secrets-store/orders-db-password
     |
     v
App đọc file, KHÔNG log giá trị
```

**Với môi trường đa ứng dụng:** Workload Identity riêng cho service account `orders-sa` thường giúp giới hạn quyền tốt hơn một identity cấp node đọc mọi vault. Nhưng vẫn phải giới hạn quyền tạo Pod/SPC để không bị lợi dụng.

**Kết quả kiểm thử:** Pod `Running`, CSI volume mount thành công, `test -s` trả exit code 0, Key Vault logs có hoạt động hợp lệ theo khả năng thu thập, và logs ứng dụng không chứa secret.

**Rotation:** cập nhật secret version trong Key Vault; nếu CSI rotation bật và không pin version, chờ cơ chế cập nhật file; kiểm tra ứng dụng reload hoặc rolling restart; chỉ thu hồi credential cũ sau khi xác nhận các consumer đã chuyển.

**Nếu có lỗi:** đọc Pod events và driver logs trước; sau đó kiểm tra identity/role hoặc đường mạng. Không sửa bằng cách đưa mật khẩu vào Kubernetes Deployment plaintext.

**Nghiệm thu:** có thể triển khai lại Pod trong namespace lab, xác minh mount thành công mà không in secret; chứng minh secret không nằm trong repo/manifests; mô tả được đường khôi phục khi vault hoặc identity bị thay đổi.

## 27. Tự kiểm tra kiến thức

**Câu 1.** Vì sao Kubernetes Secret biểu diễn base64 không đồng nghĩa secret đã được mã hóa an toàn?

**Đáp án:** Base64 là encoding có thể giải mã dễ dàng. Cần Kubernetes RBAC, bảo vệ control plane và chính sách mã hóa/đọc dữ liệu phù hợp.

**Câu 2.** Vai trò chính của SecretProviderClass là gì?

**Đáp án:** Khai báo nguồn Key Vault, object và identity/config cho Secrets Store CSI Driver để Pod có thể mount dữ liệu.

**Câu 3.** Khi Pod đọc trực tiếp file từ CSI, có bắt buộc tạo Kubernetes Secret không?

**Đáp án:** Không. Secret sync sang Kubernetes Secret là cơ chế tùy chọn cho ứng dụng/controller yêu cầu API Kubernetes Secret.

**Câu 4.** Azure Key Vault Secrets User có phải luôn là quyền đủ để lấy Key Vault key và certificate không?

**Đáp án:** Không. Quyền khác nhau theo object type và hành động; cần kiểm tra role/permission cho key/certificate cụ thể.

**Câu 5.** Workload Identity liên kết identity với thông tin nào của Kubernetes?

**Đáp án:** OIDC issuer, federated credential subject dạng `system:serviceaccount:<namespace>:<serviceaccount>`, audience và client ID của workload identity; Pod dùng service account và label phù hợp.

**Câu 6.** Khi add-on dùng node managed identity, rủi ro chính của việc cấp role đọc toàn bộ vault là gì?

**Đáp án:** Tăng phạm vi secret mà các workloads có khả năng dùng identity chung có thể tiếp cận. Nên hạn chế scope/quyền hoặc tách identity theo workload.

**Câu 7.** Tại sao secret được tạo version mới ở Key Vault nhưng ứng dụng đang chạy vẫn có thể dùng bản cũ?

**Đáp án:** CSI refresh theo cơ chế rotation riêng; ứng dụng có thể cache file/env. Với env var từ Kubernetes Secret, container cần restart để lấy giá trị mới.

**Câu 8.** Mount bằng `subPath` có thể gây vấn đề gì khi rotation?

**Đáp án:** Cơ chế cập nhật file từ CSI có thể không hiển thị qua subPath mount; nên mount directory và thiết kế ứng dụng reload đúng cách.

**Câu 9.** Identity đủ RBAC nhưng mount `Forbidden` hoặc timeout. Nên kiểm tra thêm gì?

**Đáp án:** Permission model của vault, identity/client ID thật, federated credential, trạng thái secret, network, DNS, firewall, private endpoint và logs.

**Câu 10.** Một Pod ở namespace `orders` có thể tham chiếu SecretProviderClass chỉ tồn tại ở namespace `billing` bằng tên không?

**Đáp án:** Không theo cách thông thường; SecretProviderClass là resource có namespace và Pod cần resource đúng namespace.

**Câu 11.** Khi bật sync, Kubernetes Secret có tự tồn tại ngay sau khi tạo SecretProviderClass mà chưa có Pod nào mount không?

**Đáp án:** Không nên giả định như vậy. Đồng bộ thường gắn với Pod thực sự sử dụng CSI mount; cần kiểm tra vòng đời của driver.

**Câu 12.** Vì sao log Pod `FailedMount` không tự chứng minh do Key Vault RBAC?

**Đáp án:** Mount còn có thể lỗi vì thiếu SecretProviderClass, CSI driver, identity, DNS, firewall, secret name/version hoặc network timeout.

**Câu 13.** Khi Key Vault mất kết nối, Pod đã chạy có chắc mọi Pod mới vẫn khởi động được không?

**Đáp án:** Không. Pod mới có thể cần CSI provider lấy object và thất bại; bản đã mount trên Pod đang chạy không đảm bảo cho lần khởi động tiếp theo.

**Câu 14.** Với API có thể đăng nhập Microsoft Entra trực tiếp vào database, có nhất thiết phải lưu database password trong Key Vault không?

**Đáp án:** Không. Nếu dịch vụ đích hỗ trợ identity-based authentication, có thể giảm hoặc loại bỏ secret dạng password.

**Câu 15.** Khi nào nên restart Pod sau rotation?

**Đáp án:** Khi ứng dụng không tự re-read file, sử dụng env var từ synced Kubernetes Secret hoặc workflow yêu cầu rollout để tiêu thụ credential mới. Trước đó phải xác minh phiên bản và khả năng kết nối.

**Câu 16.** Những log nào hữu ích nhất khi một Pod mới không mount được Key Vault secret?

**Đáp án:** Pod events/describe, CSI driver/provider logs, Key Vault diagnostics, dữ liệu về role/identity và thông tin network/DNS; không cần in secret value.

**Câu 17.** Nếu `kubectl exec` vào Pod, người quản trị có thể đọc file mounted secret không?

**Đáp án:** Có thể, nếu tiến trình và quyền file cho phép. Vì vậy cần hạn chế quyền exec và bảo vệ quyền runtime, không chỉ Key Vault RBAC.

**Câu 18.** Vì sao không nên thu hồi credential A ngay khi vừa thêm version B trong Key Vault?

**Đáp án:** Pod, driver hoặc ứng dụng có thể chưa refresh; cần kiểm chứng mọi consumer đã dùng B và không có gián đoạn trước khi thu hồi A, trừ trường hợp sự cố lộ credential cần xử lý khẩn cấp.

**Tóm lại:** Quản lý secret trong AKS là bài toán phối hợp **nguồn bí mật (Key Vault) – danh tính (managed identity/Workload Identity) – cơ chế phân phối (CSI volume) – quyền Kubernetes – vòng đời rotation – quan sát và khôi phục**. Bắt đầu từ một secret lab, cấp quyền tối thiểu, mount file chỉ đọc, tuyệt đối không in giá trị, rồi kiểm thử rotation và sự cố. Một tích hợp tốt không chỉ giúp ứng dụng đọc được secret hôm nay mà còn **giới hạn ai được dùng secret, biết khi nào nó thay đổi và phục hồi an toàn khi có lỗi**.
