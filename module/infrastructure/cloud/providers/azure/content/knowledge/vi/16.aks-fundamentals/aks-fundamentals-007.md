# AKS Workload Identity cho pod

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Người học sẽ biết triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Nền tảng Azure Kubernetes Service**, bài học này tập trung vào **AKS Workload Identity**: cho phép ứng dụng chạy trong Kubernetes pod nhận quyền truy cập tài nguyên Azure bằng danh tính Microsoft Entra ID mà không cần nhúng client secret hoặc storage access key vào container.

Hãy tưởng tượng một Java API chạy trên AKS cần đọc chuỗi kết nối từ Azure Key Vault. Cách làm kém an toàn là lưu client secret vào Kubernetes Secret, đưa secret đó vào biến môi trường của pod rồi dùng để xác thực với Microsoft Entra ID. Khi secret bị sao chép từ cấu hình, log hoặc image, kẻ tấn công có thể sử dụng nó ngoài cluster cho tới khi được thu hồi. **Microsoft Entra Workload ID** dùng cơ chế liên kết tin cậy giữa token ServiceAccount do AKS phát hành và Microsoft Entra ID để ứng dụng lấy access token cho đúng tài nguyên Azure, giảm phụ thuộc vào thông tin xác thực tĩnh.

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa **Kubernetes ServiceAccount**, **managed identity**, **AKS cluster identity**, **kubelet identity** và **Workload Identity**.
- Mô tả luồng **OIDC issuer → projected ServiceAccount token → federated identity credential → Entra access token → Azure RBAC**.
- Bật OIDC issuer và workload identity trên AKS theo quy trình được hỗ trợ.
- Tạo **user-assigned managed identity**, thiết lập federated identity credential và gán quyền Azure RBAC tối thiểu.
- Cấu hình ServiceAccount, annotation, pod label, deployment và sử dụng Azure SDK trong ứng dụng Java.
- Kiểm tra kết quả xác thực, chẩn đoán lỗi issuer/subject/audience, pod mutation, RBAC và đường mạng.
- Thiết kế ranh giới namespace, vòng đời danh tính, CI/CD, giám sát và chi phí khi chạy production.

## 1. Vấn đề mà AKS Workload Identity giải quyết

Một ứng dụng trong pod thường cần truy cập tài nguyên nằm **ngoài Kubernetes**, chẳng hạn:

- Azure Key Vault để đọc secrets hoặc certificate theo quyền đã được cấp.
- Azure Storage để tải/ghi blob bằng Entra ID và Azure RBAC.
- Azure SQL hoặc dịch vụ hỗ trợ Microsoft Entra authentication.
- Azure Service Bus, Event Hubs hoặc các API Azure hỗ trợ bearer access token.

Ứng dụng phải chứng minh danh tính với dịch vụ đích. Với một Kubernetes cluster thông thường, ServiceAccount token của pod được phát hành bởi Kubernetes, **không tự động là Entra access token** để gọi Key Vault. AKS Workload Identity kết nối hai miền tin cậy đó thông qua **OpenID Connect (OIDC) federation**.

```text
Pod trong AKS
  |
  | Projected Kubernetes ServiceAccount token
  | (JWT có issuer, subject và audience)
  v
Microsoft Entra ID
  |
  | Đối chiếu federated identity credential của managed identity
  | và xác minh token từ OIDC issuer tin cậy
  v
Entra access token dành cho Key Vault / Storage / dịch vụ đích
  |
  v
Dịch vụ Azure kiểm tra Azure RBAC / quyền dữ liệu
  |
  +-- Đủ quyền và mạng hợp lệ -> cho phép thao tác
  +-- Không đủ quyền / điều kiện -> từ chối
```

**Hai lớp không được nhầm lẫn:**

1. **Federation/authentication** cho biết pod có thể đổi token Kubernetes lấy token Entra của danh tính nào.
2. **Authorization ở dịch vụ đích** cho biết danh tính ấy có được đọc một secret, ghi một blob hoặc gửi message hay không.

Tạo federated credential thành công không tự gán quyền vào Key Vault. Ngược lại, gán role Azure RBAC cho managed identity không giúp pod lấy token nếu issuer, ServiceAccount hoặc workload identity webhook cấu hình sai.

### 1.1. Trước và sau khi dùng Workload Identity

| Khía cạnh | Client secret đặt trong pod | AKS Workload Identity |
|---|---|---|
| Tài liệu xác thực ứng dụng giữ | Client secret/certificate có vòng đời riêng | Projected ServiceAccount token và thông tin identity không bí mật |
| Phân phối bí mật tĩnh | Phải quản lý, thay thế và ngăn rò rỉ | Không cần client secret của Entra application cho luồng này |
| Trust source | Entra application credential | OIDC issuer của AKS và federated credential |
| Quyền ở Azure | Vẫn cần Azure RBAC hoặc cơ chế quyền của dịch vụ | Vẫn cần Azure RBAC hoặc cơ chế quyền của dịch vụ |
| Phạm vi workload | Secret có thể bị sao chép, dùng ngoài pod nếu lộ | Token được ràng buộc issuer/subject/audience và thời hạn; vẫn cần chống đánh cắp token |
| Quản lý vòng đời | Rotation secret, phân phối bản mới | Quản lý ServiceAccount, federated credential, managed identity, role |

Workload Identity **giảm rủi ro bí mật tĩnh**, không có nghĩa pod không còn credential. Projected token vẫn là thông tin nhạy cảm trong thời gian có hiệu lực; phải bảo vệ nó khỏi log, exfiltration và các workload không được phép đọc.

## 2. Các thành phần và danh tính cần phân biệt

### 2.1. AKS cluster identity

AKS có danh tính được control plane sử dụng để **quản lý hạ tầng Azure của cluster** theo chức năng được hỗ trợ. Nó phục vụ những hành động như quản lý tài nguyên liên quan, không mặc nhiên là danh tính mọi ứng dụng chạy trong pod.

### 2.2. Kubelet identity

Kubelet identity gắn với hoạt động node/kubelet trong những tác vụ được AKS hỗ trợ, thường được nhắc đến khi cấp quyền **pull image từ Azure Container Registry**. Việc kubelet tải được image không cho phép code Java chạy trong pod tự đọc Key Vault.

### 2.3. Kubernetes ServiceAccount

**ServiceAccount (SA)** là một danh tính ở **bên trong Kubernetes**, có phạm vi **namespace**. Một pod có thể chạy với `serviceAccountName`. Kubernetes API Server phát hành token có thể mang subject:

```text
system:serviceaccount:<namespace>:<service-account-name>
```

Ví dụ:

```text
system:serviceaccount:orders:orders-kv-reader
```

ServiceAccount và Kubernetes RBAC điều khiển quyền truy cập **Kubernetes API**. Chúng không tự cấp quyền Azure Key Vault. Đặt tên ServiceAccount không tạo ra một Entra application hoặc Azure managed identity.

### 2.4. User-assigned managed identity

**User-assigned managed identity (UAMI)** là tài nguyên Azure có Entra service principal tương ứng. Nó có:

| Thuộc tính | Ý nghĩa | Cách dùng trong bài |
|---|---|---|
| **Resource ID** | Azure Resource Manager ID của UAMI | Định danh resource khi quản lý |
| **Client ID** | Application/client identifier | Annotation ServiceAccount `azure.workload.identity/client-id` |
| **Principal ID** | Object ID của service principal trong Entra tenant | Assignee khi tạo Azure RBAC role assignment |
| **Tenant ID** | Entra tenant liên quan | Kiểm tra issuer/trust và credential |

**Client ID khác Principal ID.** Dùng client ID khi annotation yêu cầu client ID; dùng principal/object ID khi tạo role assignment với `--assignee-object-id`.

Trong một số mô hình, AKS Workload Identity cũng có thể liên kết với Entra application đăng ký riêng, nhưng bài thực hành chọn **UAMI** để có một tài nguyên danh tính do Azure quản lý, dễ gán Azure RBAC.

### 2.5. Federated identity credential (FIC)

**Federated identity credential** là quan hệ tin cậy gắn với UAMI/Entra application, mô tả token bên ngoài nào được phép đổi lấy Entra access token của danh tính đó. Ba trường trọng tâm:

- **Issuer:** OIDC issuer URL của AKS cluster.
- **Subject:** chính xác `system:serviceaccount:<namespace>:<serviceaccount>`.
- **Audience:** thông thường `api://AzureADTokenExchange` trong Azure public cloud theo luồng Workload Identity.

Issuer, subject và audience phải **khớp** với các claims của projected token. Chỉ đặt cùng tên ServiceAccount trong một cluster khác không tự đủ nếu issuer khác. Tên namespace/ServiceAccount và issuer là một phần của ranh giới quyền, không phải metadata trang trí.

### 2.6. OIDC issuer và webhook

Khi AKS bật **OIDC issuer**, cluster có địa chỉ issuer để Microsoft Entra ID có thể kiểm tra token do Kubernetes phát hành theo cơ chế federation. Khi bật **workload identity**, thành phần admission webhook của dịch vụ có thể mutate pod đáp ứng điều kiện, cấp projected token volume và environment variables cho Azure Identity SDK.

Trong cấu hình thường gặp, một pod dùng Workload Identity cần:

1. ServiceAccount được annotation với **client ID** của UAMI.
2. Pod template mang label **`azure.workload.identity/use: "true"`** để webhook nhận diện.
3. Pod chỉ định đúng `serviceAccountName` và chạy trên cluster đã bật các tính năng cần thiết.
4. FIC có issuer/subject/audience chính xác, Azure role tại dịch vụ đích đã được cấp.

**Chỉ annotation ServiceAccount nhưng quên label trên pod** có thể khiến webhook không inject token và environment variables như mong đợi.

## 3. Luồng xác thực từ pod đến Azure Key Vault

```mermaid
sequenceDiagram
    participant P as Java Pod (orders namespace)
    participant K as AKS OIDC issuer
    participant E as Microsoft Entra ID
    participant V as Azure Key Vault

    Note over P: SA orders-kv-reader và pod label workload identity
    K-->>P: Projected ServiceAccount JWT
    P->>E: Yêu cầu token bằng federated JWT
    E->>K: Xác minh issuer/chữ ký theo OIDC metadata
    E->>E: Đối chiếu FIC: issuer, subject, audience
    E-->>P: Access token cho Key Vault
    P->>V: Đọc secret với Entra access token
    V->>V: Kiểm tra RBAC/quyền + network
    V-->>P: Dữ liệu nếu được phép; lỗi nếu bị từ chối
```

Sơ đồ trình bày **luồng logic**; các bước kiểm tra token và trao đổi metadata có thể sử dụng cache và cơ chế nội bộ, không đồng nghĩa có một kết nối mạng trực tiếp tới issuer trên mọi yêu cầu.

### 3.1. Các biến môi trường và token được webhook cung cấp

Với pod được mutate, Azure Identity SDK thường sử dụng:

| Tên | Chức năng |
|---|---|
| `AZURE_CLIENT_ID` | Chỉ định Entra client ID của managed identity mà workload muốn dùng |
| `AZURE_TENANT_ID` | Tenant để trao đổi token |
| `AZURE_FEDERATED_TOKEN_FILE` | Đường dẫn bên trong container tới projected ServiceAccount token |
| `AZURE_AUTHORITY_HOST` | Endpoint authority của cloud nếu được cung cấp/cần dùng |

Nội dung file tại `AZURE_FEDERATED_TOKEN_FILE` là một **JWT có thời hạn**, không phải access token trực tiếp để gọi Key Vault. Azure Identity SDK đọc token đó, thực hiện token exchange với Entra ID và nhận access token phù hợp với dịch vụ đích.

**Không log giá trị token**, không mount token sang container không cần quyền và không sao chép token ra bên ngoài cluster. Biến `AZURE_CLIENT_ID` là định danh, không phải secret; nhưng projected token vẫn phải được bảo vệ.

### 3.2. Token và quyền có vòng đời khác nhau

Projected ServiceAccount token có thời hạn và được Kubernetes quản lý/luân chuyển theo cấu hình hỗ trợ. Entra access token có thời hạn riêng, được SDK cache và làm mới theo cơ chế thích hợp. Nếu ứng dụng tự đọc JWT một lần lúc startup rồi giữ mãi, nó có thể lỗi sau khi token hết hạn.

Nếu thu hồi role Key Vault của UAMI, điều đó không tự chặn ngay tất cả access tokens đã phát hành trong mọi tình huống. Phải thiết kế quy trình phản ứng sự cố theo thời gian hiệu lực token, cơ chế thu hồi khả dụng và chính sách dịch vụ đích.

## 4. Workload Identity khác với các cách tiếp cận trước đây

| Giải pháp | Cách tiếp cận | Nhận xét |
|---|---|---|
| **Static client secret** | Secret/certificate của Entra application đặt trong workload | Phải quản lý credential, rotation và tránh exfiltration |
| **Managed identity gắn node/kubelet** | Dùng danh tính của hạ tầng/node | Không tạo ranh giới độc lập theo pod nếu mọi pod dùng chung identity |
| **AAD Pod Identity (legacy)** | Dùng thành phần chặn/định tuyến token tới Azure Instance Metadata Service | Giải pháp cũ; với AKS mới nên ưu tiên Workload Identity theo khuyến nghị hiện hành |
| **AKS Workload Identity** | Kubernetes OIDC token federation với Entra ID | Hỗ trợ ranh giới namespace + ServiceAccount + FIC và SDK tương thích |
| **Kubernetes Secret chứa access key** | Pod dùng key của Storage/Key Vault/ứng dụng | Dễ cấp quá rộng, khó thu hồi/kiểm toán theo workload |

Một lợi ích nổi bật là **không cần cơ chế pod giả lập truy cập Instance Metadata Service (IMDS) của node** để lấy danh tính. Tuy nhiên, code phải dùng SDK/credential tương thích và cluster cần bật đúng chức năng. Không giả định việc nâng AKS tự chuyển mọi ứng dụng cũ sang Workload Identity.

## 5. Thiết kế quyền theo namespace và ServiceAccount

Giả sử cluster dùng ba ứng dụng:

```text
AKS: aks-orders-prod
|
+-- Namespace orders
|    +-- ServiceAccount orders-kv-reader
|    +-- Deployment orders-api
|
+-- Namespace payments
|    +-- ServiceAccount payments-kv-reader
|    +-- Deployment payments-api
|
+-- Namespace reporting
     +-- ServiceAccount reports-blob-reader
     +-- CronJob reports-export
```

Một thiết kế least privilege có thể dùng:

| Pod/ServiceAccount | Managed identity | Quyền Azure dữ liệu |
|---|---|---|
| `orders/orders-kv-reader` | `mi-orders-kv-prod` | Đọc những secret cần cho orders |
| `payments/payments-kv-reader` | `mi-payments-kv-prod` | Đọc các secret của payments |
| `reporting/reports-blob-reader` | `mi-reports-blob-prod` | Đọc dữ liệu từ container Blob được phê duyệt |

Không dùng một UAMI có quyền đọc mọi secret và blob của tổ chức cho tất cả pod, trừ khi đã cân nhắc đầy đủ lý do và phạm vi rủi ro. Một managed identity có thể có **nhiều FIC** được dịch vụ hỗ trợ, nhưng như vậy nhiều ServiceAccount có thể cùng mượn quyền Azure của identity đó; cần ghi nhận và kiểm soát quan hệ này.

### 5.1. Kubernetes RBAC là lớp riêng

Kubernetes RBAC trả lời: *pod hoặc người dùng này có được gọi Kubernetes API, đọc ConfigMaps hay sửa Deployments không?* Azure RBAC trả lời: *UAMI có được đọc Key Vault secret, gửi Service Bus message hay ghi Storage blob không?*

Workload Identity **không tự cấp cho ServiceAccount quyền quản trị Kubernetes**. Ngược lại, có quyền tạo/sửa ServiceAccount, Pod hoặc FIC trong phạm vi không được kiểm soát có thể trở thành con đường chiếm quyền Azure. Phải bảo vệ cả **Kubernetes API authorization** và **Azure resource/IAM authorization**.

### 5.2. Namespace không phải hàng rào bảo mật duy nhất

Một pod ở namespace khác dùng ServiceAccount có cùng tên sẽ có **subject khác** vì subject chứa namespace. Nhưng người có quyền tạo/đổi Deployment ở đúng namespace và chọn ServiceAccount tin cậy có thể tạo pod sử dụng identity được liên kết. Vì vậy:

- Hạn chế người được tạo/sửa pod, deployment và ServiceAccount trong namespace nhạy cảm.
- Dùng admission policies để ngăn pod không được phê duyệt tự chọn ServiceAccount đặc quyền.
- Giới hạn quyền tạo/sửa federated credentials và role assignments trong Azure.
- Áp dụng network policy, pod security, quản lý image và chống lộ token trong workload.
- Tách identity cho ứng dụng có dữ liệu hoặc chủ sở hữu khác nhau.

## 6. Thực hành: cấu hình AKS Workload Identity với Azure CLI

Chúng ta sẽ cấu hình để một pod Java trong namespace `orders` sử dụng **user-assigned managed identity** đọc một secret của Azure Key Vault. Đây là môi trường thử nghiệm có kiểm soát, không phải script áp dụng nguyên xi lên production.

**Điều kiện ban đầu:**

1. Một AKS cluster đã tồn tại, đang chạy phiên bản Kubernetes/AKS hỗ trợ **OIDC issuer** và **Workload Identity**.
2. Có Azure CLI, tiện ích `kubectl`, quyền phù hợp với cluster và namespace, và quyền cập nhật cấu hình AKS.
3. Có quyền tạo user-assigned identity và federated credential, đồng thời có quyền tạo Azure role assignment tại phạm vi Key Vault phù hợp.
4. Một Key Vault đã có sẵn trong môi trường dev với mô hình **Azure RBAC permission** (nếu dùng ví dụ role `Key Vault Secrets User`).
5. Mạng của AKS có thể truy cập endpoint trao đổi token của Entra ID và Key Vault theo cấu hình hiện tại.
6. Image container thử nghiệm có mã Java dùng Azure Identity SDK đã được build và có thể pull từ registry. Bài học không tự tạo image ứng dụng hoặc Key Vault mới.

### 6.1. Đặt biến Bash và kiểm tra subscription

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

AKS_RG="rg-aks-dev"
AKS_NAME="aks-orders-dev"
IDENTITY_RG="rg-orders-identity-dev"
LOCATION="southeastasia"
UAMI_NAME="mi-orders-kv-reader-dev"

NAMESPACE="orders"
SERVICE_ACCOUNT="orders-kv-reader"
FIC_NAME="fic-aks-orders-dev"

VAULT_RG="rg-security-dev"
VAULT_NAME="kv-orders-dev-example"
SECRET_NAME="demo-message"
```

Các giá trị ví dụ phải được thay bằng tên tài nguyên có thật. Không in secret value vào shell output hoặc logs. Không để nhiệm vụ thử nghiệm thay đổi resource group production ngoài phạm vi được phê duyệt.

### 6.2. Bật OIDC issuer và Workload Identity

Nếu cluster chưa bật, có thể dùng lệnh cập nhật:

```bash
az aks update \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --enable-oidc-issuer \
  --enable-workload-identity
```

Nếu cluster đã bật hai tính năng, chỉ cần xác minh cấu hình; không cần chạy update lặp đi lặp lại. Việc bật tính năng trên cluster thật phải theo quy trình thay đổi, xem xét khả năng hỗ trợ của phiên bản AKS và các ứng dụng đang chạy.

Lấy issuer URL chính xác:

```bash
AKS_OIDC_ISSUER=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "oidcIssuerProfile.issuerUrl" \
  --output tsv)

echo "$AKS_OIDC_ISSUER"
```

Giá trị thường có dạng URL HTTPS do AKS cung cấp; **không tự gõ hoặc đoán URL issuer**. Một ký tự khác, bao gồm dấu `/` cuối URL khi có, có thể dẫn tới lỗi đối chiếu liên kết federation.

Kiểm tra cấu hình cluster:

```bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{oidc:oidcIssuerProfile,workloadIdentity:securityProfile.workloadIdentity}" \
  --output json
```

Nếu issuer rỗng hoặc tính năng chưa ở trạng thái mong đợi, không tiếp tục tạo FIC bằng một issuer giả. Hãy giải quyết điều kiện cluster trước.

### 6.3. Tạo user-assigned managed identity

```bash
az identity create \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --location "$LOCATION"

UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query id --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query clientId --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query principalId --output tsv)
```

Tại bước này, UAMI **chưa có quyền Key Vault** và ServiceAccount **chưa được liên kết** với danh tính. Chỉ tạo identity không làm cho bất cứ pod nào lập tức sử dụng được nó.

### 6.4. Tạo federated identity credential

Subject được xây chính xác từ namespace và tên ServiceAccount:

```bash
FIC_SUBJECT="system:serviceaccount:$NAMESPACE:$SERVICE_ACCOUNT"

az identity federated-credential create \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --name "$FIC_NAME" \
  --issuer "$AKS_OIDC_ISSUER" \
  --subject "$FIC_SUBJECT" \
  --audience "api://AzureADTokenExchange"
```

Kiểm tra lại bằng lệnh chỉ đọc:

```bash
az identity federated-credential show \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --name "$FIC_NAME" \
  --output json
```

Đặc biệt đối chiếu:

| Trường FIC | Giá trị phải khớp |
|---|---|
| `issuer` | `AKS_OIDC_ISSUER` của đúng AKS cluster |
| `subject` | `system:serviceaccount:orders:orders-kv-reader` |
| `audiences` | `api://AzureADTokenExchange` theo luồng token exchange đang dùng |
| UAMI | Danh tính mà app cần nhận access token |

Federated credential có giới hạn số lượng và các ràng buộc theo dịch vụ. Nếu nhiều cluster hoặc namespace cùng dùng một UAMI, phải kiểm kê mọi FIC để tránh một identity trở thành nơi tập trung đặc quyền không cần thiết.

### 6.5. Gán Azure RBAC để đọc secret trong Key Vault

Với Key Vault dùng mô hình **Azure RBAC permission**, một ví dụ role data plane là `Key Vault Secrets User`. Xác nhận chế độ của vault:

```bash
az keyvault show \
  --resource-group "$VAULT_RG" \
  --name "$VAULT_NAME" \
  --query "{id:id,vaultUri:properties.vaultUri,rbacEnabled:properties.enableRbacAuthorization}" \
  --output json
```

Nếu `rbacEnabled` không phải `true`, ví dụ role assignment này **không đủ** để quyết định truy cập secret; vault có thể dùng **access policy model** và cần quy trình tương ứng. Không chuyển mô hình permission của Key Vault production chỉ để chạy một lab.

Lấy Resource ID và gán quyền:

```bash
VAULT_ID=$(az keyvault show \
  --resource-group "$VAULT_RG" \
  --name "$VAULT_NAME" \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
```

Scope vault được dùng cho bài thực hành đơn giản. Trong production, nếu chỉ cần một secret, cân nhắc **scope của secret** hoặc ranh giới vault phù hợp và điều kiện Azure RBAC/Key Vault hỗ trợ để hạn chế quyền hơn nữa. Không cấp `Key Vault Administrator`, `Owner` hoặc toàn bộ `Contributor` chỉ vì ứng dụng cần `get` một secret.

Đọc lại RBAC:

```bash
az role assignment list \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
```

Role assignment có thể cần thời gian để lan truyền. Nếu vừa cấp quyền xong mà ứng dụng bị từ chối, kiểm tra đúng Object ID, role, scope và permission model trước khi mở rộng quyền.

## 7. Cấu hình Kubernetes ServiceAccount và workload pod

### 7.1. Lấy kubeconfig của đúng cluster

```bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"

kubectl config current-context
kubectl get namespaces
```

**Quan trọng:** `az aks get-credentials` có thể thay đổi kubeconfig/current context trên máy bạn. Kiểm tra `kubectl config current-context` trước mọi lệnh `apply` hoặc `rollout`; không chạy nhầm vào AKS production.

### 7.2. Tạo namespace và ServiceAccount

```bash
kubectl create namespace "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: $SERVICE_ACCOUNT
  namespace: $NAMESPACE
  annotations:
    azure.workload.identity/client-id: "$UAMI_CLIENT_ID"
EOF
```

Annotation `azure.workload.identity/client-id` trỏ đến **Client ID**, không phải Principal ID. Azure Workload Identity có thêm các annotation tùy chọn theo tính năng, ví dụ tenant ID hoặc thời hạn projected ServiceAccount token. Chỉ dùng chúng khi thiết kế cần và SDK/cluster hỗ trợ; cấu hình mặc định phù hợp giúp giảm sai sót.

Kiểm tra đối tượng:

```bash
kubectl get serviceaccount "$SERVICE_ACCOUNT" \
  -n "$NAMESPACE" -o yaml
```

Một ServiceAccount chỉ trở thành nguồn danh tính Azure hợp lệ khi **FIC khớp issuer/subject/audience**, pod dùng ServiceAccount đó và workload mutation/token exchange hoạt động. Annotation không tự phát hành quyền RBAC trên Azure.

### 7.3. Deployment mẫu với Workload Identity

Giả định có image `acrordersdev001.azurecr.io/orders-api:1.0.0` chứa Java application đã tích hợp Azure Identity SDK. Đây chỉ là image **minh họa**, cần được build/push trước khi chạy. Quyền **pull ACR của AKS kubelet** là chủ đề khác và phải được thiết lập riêng nếu ACR riêng tư.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-kv-reader
      containers:
        - name: orders-api
          image: acrordersdev001.azurecr.io/orders-api:1.0.0
          imagePullPolicy: IfNotPresent
          env:
            - name: KEY_VAULT_URL
              value: "https://kv-orders-dev-example.vault.azure.net/"
          ports:
            - containerPort: 8080
```

Trong `spec.template.metadata.labels`, label **`azure.workload.identity/use: "true"`** báo cho webhook thực hiện mutation. Không đặt label chỉ ở metadata của Deployment mà quên **Pod template**. `serviceAccountName` phải khớp SA ở namespace `orders`, và `azure.workload.identity/client-id` trên SA phải khớp managed identity có FIC.

Tên Key Vault, image, cổng 8080 và số replicas là ví dụ. Với production cần cấu hình resource requests/limits, probes, network policy, logging, policy ảnh an toàn và phương án rollout phù hợp. Không lưu secret của Key Vault vào manifest.

### 7.4. Kiểm tra pod đã được mutate

Sau khi apply manifest trong môi trường thử nghiệm:

```bash
kubectl get pods -n "$NAMESPACE" -l app=orders-api
kubectl describe deployment orders-api -n "$NAMESPACE"

# Chỉ xem PodSpec/metadata, không in nội dung JWT.
kubectl get pods -n "$NAMESPACE" \
  -l app=orders-api \
  -o json
```

Trong PodSpec đã mutate, hãy tìm những environment variables như `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE` và projected service account token volume, theo cấu hình webhook và container. Không in/copy **nội dung** file token. Nếu không thấy injection, kiểm tra label, ServiceAccount, trạng thái webhook và xem pod có được tạo **sau** khi áp dụng cấu hình hay không.

**Lưu ý vòng đời:** admission mutation xảy ra khi Pod được tạo. Thay annotation trên ServiceAccount không bảo đảm một pod đang chạy được tự mutate lại. Khi cần, tạo/restart pod mới theo quy trình rollout:

```bash
# Chỉ khi đã phê duyệt thay đổi và có workload sẵn sàng.
# kubectl rollout restart deployment/orders-api -n "$NAMESPACE"
```

Kubernetes authorization, Pod Security Admission/admission policies và ranh giới network vẫn phải được kiểm tra. Việc thấy các biến môi trường không chứng minh token exchange với Entra ID đã thành công.

## 8. Ứng dụng Java lấy secret bằng Azure Identity SDK

Ứng dụng Java nên sử dụng **Azure SDK for Java** hỗ trợ Workload Identity. Khi pod có các environment variables và projected token file do webhook cấu hình, SDK có thể thực hiện federated token exchange mà ứng dụng không phải tự ghép HTTP request hoặc giữ client secret.

Những thư viện Maven thường cần gồm:

```xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
  <version><!-- Phiên bản ổn định đã kiểm thử, hỗ trợ Workload Identity --></version>
</dependency>
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-security-keyvault-secrets</artifactId>
  <version><!-- Phiên bản tương thích đã kiểm thử --></version>
</dependency>
```

Đây là mô tả dependency: trong `pom.xml` thật phải dùng các **version hợp lệ** theo BOM hoặc release chính thức được tổ chức kiểm tra; không copy nội dung placeholder thành dependency trống.

### 8.1. Mẫu Java sử dụng DefaultAzureCredential

```java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class WorkloadIdentityKeyVaultDemo {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        DefaultAzureCredential credential =
                new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        // Secret phải tồn tại và identity phải có quyền đọc phù hợp.
        KeyVaultSecret secret = client.getSecret("demo-message");

        // Không in giá trị secret vào console, log hay HTTP response.
        System.out.println("Retrieved secret metadata: " + secret.getName());
    }
}
```

Trong pod AKS được mutate, phiên bản `azure-identity` tương thích có thể phát hiện `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` và `AZURE_FEDERATED_TOKEN_FILE` để sử dụng Workload Identity. Trong môi trường phát triển, `DefaultAzureCredential` có thể chọn một credential khác (Azure CLI, IDE, v.v.) tùy cấu hình; vì thế test chạy tốt trên laptop **không đủ** chứng minh nó dùng Workload Identity khi lên AKS.

### 8.2. Chọn WorkloadIdentityCredential tường minh

Nếu cần làm rõ **production trên AKS phải dùng đúng federation**, ứng dụng có thể sử dụng `WorkloadIdentityCredentialBuilder` với SDK tương thích:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class ExplicitWorkloadIdentityDemo {
    public static void main(String[] args) {
        TokenCredential credential =
                new WorkloadIdentityCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(System.getenv("KEY_VAULT_URL"))
                .credential(credential)
                .buildClient();

        String name = client.getSecret("demo-message").getName();
        System.out.println("Fetched secret metadata for: " + name);
    }
}
```

Ví dụ này giả định environment variables hợp lệ đã được inject. Khi dùng credential tường minh, nếu projected token bị thiếu thì chương trình sẽ gặp lỗi ở luồng xác thực thay vì vô tình chuyển sang một credential khác có quyền rộng hơn.

**Không đặt `AZURE_CLIENT_SECRET` hoặc account key vào Deployment** để “dự phòng” khi federation hỏng. Cần sửa nguyên nhân trust/annotation/permission, không bỏ qua mô hình Workload Identity.

### 8.3. Lưu ý về token refresh

Ứng dụng nên tạo SDK credential/client theo vòng đời phù hợp, tránh lấy projected JWT rồi lưu vào biến tĩnh mãi mãi. Azure SDK quản lý việc lấy và cache access token theo khả năng của credential, trong khi Kubernetes luân chuyển projected ServiceAccount token.

Nếu một thư viện tự viết đọc `AZURE_FEDERATED_TOKEN_FILE` thay cho Azure SDK, đội phát triển phải tự xử lý expiration, refresh, đối chiếu audience và lỗi trao đổi token. Khi không có yêu cầu đặc thù, ưu tiên SDK chính thức.

## 9. Kiểm chứng end-to-end sau triển khai

Một bài kiểm tra đủ tốt phải xác minh **ba kết quả riêng**:

1. Pod nhận cấu hình federation do webhook inject.
2. Pod có thể đổi projected Kubernetes token lấy access token của UAMI.
3. Dịch vụ đích thực thi quyền Azure RBAC và network theo đúng ma trận.

### 9.1. Kiểm tra đối tượng cấu hình

```bash
kubectl get serviceaccount "$SERVICE_ACCOUNT" \
  -n "$NAMESPACE" -o yaml

kubectl get deployment orders-api \
  -n "$NAMESPACE" -o yaml

az identity federated-credential list \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --output table

az role assignment list \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
```

Kiểm tra ServiceAccount annotation, pod template label, FIC issuer/subject/audience và quyền của **đúng principal**. Không dùng account quản trị Azure CLI làm phép thử thay thế cho UAMI của pod.

### 9.2. Quan sát pod và ứng dụng

```bash
kubectl get deployment orders-api -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l app=orders-api
kubectl describe deployment orders-api -n "$NAMESPACE"

# Chỉ xem log ứng dụng đã được thiết kế không in secrets/tokens.
kubectl logs deployment/orders-api -n "$NAMESPACE" --tail=100
```

Ứng dụng demo phải phản hồi rằng nó **đã đọc được metadata của secret** hoặc thực hiện thao tác nghiệp vụ được phép, nhưng không được ghi secret value ra log. Một log “token exchange successful” do code tự đặt cũng chưa chứng minh thao tác Key Vault đã được Azure cho phép; nên kiểm tra một request dữ liệu hợp lệ.

### 9.3. Kiểm thử phủ định (negative tests)

Để chứng minh nguyên tắc ít quyền nhất, thử những trường hợp **có chủ đích trong môi trường test**:

| Thử nghiệm | Kết quả kỳ vọng |
|---|---|
| Pod `orders/orders-kv-reader` đọc secret đã cấp quyền | Thành công |
| Một SA khác không có FIC phù hợp cố dùng cùng UAMI | Không trao đổi token thành công |
| SA của namespace `payments` dùng tên `orders-kv-reader` nhưng không có FIC của namespace đó | Không khớp subject, bị từ chối |
| UAMI orders thử đọc dữ liệu ở vault khác mà không được phân quyền | Bị từ chối ở lớp authorization |
| Pod không có label workload identity cần thiết | Không được webhook inject theo cấu hình thông thường |
| Key Vault chỉ cho phép private endpoint nhưng pod không có đường mạng | Kết nối không hoạt động dù identity/RBAC đúng |

Không thực hiện negative test bằng cách xóa role hoặc sửa FIC đang phục vụ production. Hãy dùng tài nguyên lab, danh tính tách biệt và quy trình có thể khôi phục.

## 10. Khi nào không nên dùng Workload Identity theo cùng một cách?

AKS Workload Identity rất phù hợp cho **ứng dụng trong pod cần gọi Azure data-plane APIs bằng Entra ID**. Nhưng cần chọn cơ chế đúng cho từng mục đích:

| Nhu cầu | Danh tính/quyền nên xem xét |
|---|---|
| Pod Java đọc Key Vault | Workload Identity của pod + Key Vault data-plane authorization |
| Pod ghi Blob Storage | Workload Identity + Storage Blob Data Contributor ở scope phù hợp |
| Pod gửi Service Bus message | Workload Identity + Azure Service Bus Data Sender phù hợp |
| Kubelet kéo image ACR trước khi pod chạy | AKS kubelet identity/attach ACR hoặc cơ chế image pull được hỗ trợ |
| AKS quản lý load balancer, subnet hoặc resource nền tảng | Cluster/control-plane identity |
| Người quản trị triển khai Kubernetes manifest | Kubernetes RBAC và Entra integration của control plane khi hỗ trợ |
| CI/CD triển khai Helm chart | Danh tính pipeline và quyền truy cập AKS/Kubernetes riêng |

**Điểm quan trọng:** pod **không thể dùng Workload Identity của chính ứng dụng để giải quyết mọi lỗi image pull xảy ra trước khi container khởi động**. Quá trình pull image thường do node/kubelet thực hiện, sử dụng một luồng xác thực khác. Nếu pod ở trạng thái `ImagePullBackOff`, phải kiểm tra registry auth của node/kubelet, tên image, DNS và firewall thay vì chỉ cấp role Key Vault cho UAMI.

### 10.1. Azure RBAC không đồng nhất giữa các dịch vụ

Key Vault có thể dùng permission model **Azure RBAC** hoặc **access policies**. Azure Storage có các role data plane như `Storage Blob Data Reader`/`Contributor`. Service Bus có các role gửi/nhận thông điệp. Một role `Contributor` ở Azure Resource Manager không có nghĩa ứng dụng được quyền đọc mọi dữ liệu ở mọi dịch vụ.

Trong mọi bài thực hành, luôn chọn **role đúng dịch vụ, đúng thao tác, đúng scope**, rồi xác minh firewall và private endpoint của dịch vụ đích.

## 11. Sự cố thường gặp và cách điều tra

### 11.1. Bảng triệu chứng – nguyên nhân – cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Không thấy `AZURE_FEDERATED_TOKEN_FILE` trong pod | Thiếu label `azure.workload.identity/use`, sai Pod template, webhook không mutate hoặc pod được tạo trước thay đổi | YAML Deployment/Pod, SA annotation, webhook và tạo pod mới có kiểm soát |
| Không thấy `AZURE_CLIENT_ID` hoặc client ID sai | SA chưa annotation đúng hoặc pod dùng SA khác | `serviceAccountName`, `azure.workload.identity/client-id`, UAMI clientId |
| Entra trả lỗi “No matching federated identity record” | FIC issuer/subject/audience không khớp | So khớp issuer URL thật, namespace, tên SA, audience |
| Token exchange thất bại sau khi đổi cluster | OIDC issuer thay đổi hoặc FIC đang trỏ cluster cũ | Lấy lại issuer từ đúng AKS, xem FIC và cập nhật theo quy trình |
| Lỗi tenant/client mismatch | Chọn sai UAMI hoặc tenant, annotation sai client ID | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, identity metadata |
| SDK không tìm thấy credential phù hợp | SDK cũ, thiếu Workload Identity hỗ trợ hoặc thiếu biến/token file | Phiên bản SDK, startup logs, PodSpec injection |
| `401 Unauthorized` khi gọi Azure service | Access token sai audience, hết hạn hoặc luồng xác thực lỗi | SDK credential, resource scope/token audience, thời hạn |
| `403 Forbidden` từ Key Vault | Identity hợp lệ nhưng thiếu role, sai permission model hoặc quyền dữ liệu | RBAC/access policy, principal ID, vault/secret scope |
| Timeout hoặc không phân giải được Key Vault | DNS, egress, private endpoint, UDR/NSG/Azure Firewall | DNS/route/firewall/network connectivity từ cluster |
| Pod chạy nhưng `ImagePullBackOff` | Registry pull do kubelet/node thất bại | ACR role cho kubelet, image tag, network và registry credentials |
| Một pod chạy được, pod khác lỗi | Namespace, SA, annotation, label hoặc identity khác nhau | So sánh PodSpec, SA, FIC và role |
| Sau sửa ServiceAccount pod cũ vẫn lỗi | Admission mutation và projected token không được cập nhật theo mong muốn trên pod cũ | Tạo pod/restart Deployment mới theo quy trình |

Thông báo lỗi cụ thể phụ thuộc phiên bản Azure Identity SDK, Azure service, Kubernetes và cách logging. Không dùng bảng để kết luận chắc chắn “403 luôn là thiếu role”: các lớp networking, firewall và dịch vụ đích có thể trả lỗi khác nhau.

### 11.2. Quy trình điều tra có thứ tự

1. **Xác định ứng dụng và namespace:** Pod/Deployment nào lỗi, ServiceAccount nào đang được dùng?
2. **Kiểm tra pod mutation:** label `azure.workload.identity/use` nằm đúng ở Pod template chưa? Projected token volume và environment variables có tồn tại không?
3. **Kiểm tra OIDC issuer:** Cluster đã bật OIDC issuer/workload identity? FIC có khớp issuer chính xác không?
4. **Kiểm tra subject và audience:** Namespace/SA có khác chữ hoa-thường, tên hoặc dấu phân tách không?
5. **Kiểm tra managed identity:** Client ID trong annotation có đúng UAMI? Principal ID của UAMI có đúng đối tượng được gán RBAC?
6. **Kiểm tra SDK:** Ứng dụng có dùng bản Azure Identity hỗ trợ Workload Identity và đọc token file đúng cách không?
7. **Kiểm tra dịch vụ đích:** Azure RBAC/access policies, scope, data-plane action và thời gian lan truyền quyền.
8. **Kiểm tra mạng:** OIDC/Entra token endpoint và dịch vụ đích có reachable qua DNS, route, firewall/private endpoint không?
9. **Thử request thật:** Pod có thể thực hiện thao tác dữ liệu được phép không? Các thao tác bị cấm có tiếp tục bị chặn không?
10. **Khắc phục tối thiểu:** Sửa đúng annotation/FIC/role/network, tạo revision/pod mới khi cần, ghi nhận bằng chứng.

### 11.3. Không log JWT để debug

Projected ServiceAccount token có thể chứa các claims như issuer, subject, audience và thời gian. Dù claims hữu ích cho chẩn đoán, **JWT thô là bearer token**, không nên copy vào chat, issue tracker, log aggregation hoặc gửi email. Nếu cần xác minh claims trong môi trường test, dùng công cụ được phê duyệt, giới hạn quyền xem và xử lý an toàn, không xuất dữ liệu nhạy cảm ra nơi công cộng.

Ghi lại thông tin sau thường đủ: timestamp UTC, AKS cluster, namespace, SA name, UAMI client/principal ID, FIC name, Key Vault resource ID, error code và request/correlation ID của dịch vụ đích.

## 12. Quản lý vòng đời và xoay vòng quyền

### 12.1. Khi xóa hoặc đổi tên ServiceAccount

FIC tham chiếu **subject** gắn với namespace và ServiceAccount. Nếu đổi tên SA, đổi namespace hoặc chuyển workload sang cluster khác, cần cập nhật/tạo **federated credential mới** tương ứng với issuer và subject mới. Một deployment dùng SA mới sẽ không tự có quyền chỉ vì UAMI cũ còn tồn tại.

Để migration an toàn:

1. Tạo SA/FIC mới cho đích mới, giới hạn quyền và verify token exchange.
2. Triển khai canary pod dùng danh tính mới và kiểm thử Azure service.
3. Chuyển traffic/workload theo kế hoạch.
4. Thu hồi FIC/role assignment cũ khi không còn workload phụ thuộc.
5. Kiểm tra tokens đã được cấp, logs và trạng thái workloads còn chạy.

### 12.2. Khi xóa user-assigned managed identity

UAMI là tài nguyên độc lập. Xóa Deployment hoặc ServiceAccount **không tự xóa UAMI**. UAMI cũng có thể được nhiều workload hoặc FIC sử dụng; xóa mà không kiểm kê có thể làm các pod khác mất khả năng lấy token mới.

Khi thu hồi quyền Azure, có thể xóa role assignment hoặc FIC liên quan theo chính sách. Cần hiểu khác biệt giữa **ngừng cấp token mới** và **vô hiệu hóa access token đã phát hành**; hiệu lực thu hồi tức thời phụ thuộc thời hạn token và khả năng dịch vụ.

### 12.3. Đổi cluster hoặc tạo lại AKS

OIDC issuer là một phần của trust. Khi cluster mới có issuer khác, FIC cũ không tự xác thực token mới. Quy trình DR/cluster migration phải gồm việc:

- Kiểm tra issuer URL của cluster thay thế.
- Cấp FIC tương ứng cho các SA quan trọng.
- Xác nhận Azure RBAC của UAMI vẫn đúng scope và tenant.
- Kiểm tra webhook injection trên cluster mới.
- Thử các request dữ liệu thực tế trước khi chuyển traffic production.

Không copy nguyên xi ServiceAccount YAML từ cluster cũ rồi cho rằng federation vẫn có hiệu lực nếu chưa kiểm tra FIC issuer.

## 13. Giám sát và quản trị an toàn

AKS Workload Identity nằm trên ranh giới **Kubernetes và Microsoft Entra ID**. Các nguồn thông tin có thể gồm:

| Lớp | Tín hiệu cần theo dõi | Mục đích |
|---|---|---|
| Kubernetes | Pod/deployment events, webhook behavior, ServiceAccount changes | Phát hiện lỗi injection, thay SA và mutation |
| Ứng dụng | Token acquisition failures, request latency, dependency errors | Phân biệt lỗi xác thực, phân quyền và network |
| Azure IAM | UAMI, FIC, role assignment changes qua Activity Log | Truy vết ai mở rộng hoặc thu hồi quyền |
| Microsoft Entra ID | Workload identity/sign-in events khi có quyền và dữ liệu | Phân tích token exchange, trust failures |
| Key Vault / Storage / dịch vụ đích | Diagnostic logs, access denied và request ID | Xác minh data-plane authorization |
| AKS networking | DNS, egress/Firewall, private endpoints, network policies | Phát hiện vấn đề đường truyền |

Thiết lập alert phù hợp cho việc thêm FIC mới vào một UAMI nhạy cảm, mở rộng scope của role assignment, token-exchange failures tăng bất thường và truy cập dữ liệu từ workload không được phê duyệt.

### 13.1. Kiểm soát thay đổi

- Quản lý AKS config, UAMI, FIC và role assignments qua **Infrastructure as Code** được review.
- Quản lý Kubernetes ServiceAccount, Deployment và policy qua manifest/Helm/GitOps, tránh chỉnh trực tiếp ngoài quy trình.
- Ghi owner, môi trường, namespace, ServiceAccount, purpose và scope cho từng identity.
- Kiểm tra thay đổi namespace, tên SA, AKS issuer trước khi áp dụng manifest.
- Dùng audit logs và secret-safe diagnostics; không đưa Entra token/Kubernetes JWT vào log.

**Có FIC không có nghĩa ai cũng được quyền dùng identity.** Bề mặt quyền còn gồm người có thể tạo pod ở namespace tương ứng, chỉnh SA, sửa identity resources hoặc tự cấp role. Cần review tập quyền này cùng nhau.

## 14. Các nguyên tắc bảo mật cần áp dụng ở production

### 14.1. Chỉ cấp quyền cần thiết cho từng workload

Ví dụ, pod `orders-api` chỉ đọc secret, vì vậy quyền `Key Vault Secrets User` trên scope phù hợp tốt hơn quyền quản trị toàn vault. Nếu pod chỉ gửi sự kiện, cân nhắc role gửi message thay vì role quản trị Service Bus namespace.

Một bảng chính sách dễ kiểm toán:

| Workload | ServiceAccount | UAMI | Tài nguyên Azure | Quyền |
|---|---|---|---|---|
| `orders-api` | `orders/orders-kv-reader` | `mi-orders-kv-prod` | Key Vault/secret của orders | Chỉ đọc secret |
| `payments-api` | `payments/payments-kv-reader` | `mi-payments-kv-prod` | Key Vault/secret của payments | Chỉ đọc secret |
| `orders-worker` | `orders/orders-bus-sender` | `mi-orders-bus-prod` | Service Bus queue/topic cần gửi | Data Sender |
| `report-export` | `reporting/reports-blob-writer` | `mi-report-export-prod` | Storage container xuất báo cáo | Ghi dữ liệu theo nhu cầu |

Nguyên tắc là **mỗi identity có lý do, owner và phạm vi rõ**; không nhất thiết mỗi pod replica cần UAMI riêng. Các replicas của cùng một deployment có thể cùng dùng ServiceAccount/UAMI nếu chúng thực thi cùng chức năng và cùng quyền. Với hai ứng dụng khác trách nhiệm hoặc dữ liệu, nên tách identity và ranh giới cấp quyền.

### 14.2. Hạn chế người được điều khiển ServiceAccount

Người có thể sửa Deployment để chọn `serviceAccountName: orders-kv-reader`, hoặc sửa ServiceAccount annotation, có khả năng ảnh hưởng tới danh tính mà pod nhận. Do đó:

1. Hạn chế Kubernetes RBAC ở namespace; không cấp quyền tạo pod/deployment tự do cho nhóm không đáng tin.
2. Dùng admission policies và workload security controls để ràng buộc ServiceAccount được phép.
3. Giới hạn quyền sửa FIC, managed identity và Azure role assignments.
4. Kiểm tra nhóm vận hành, pipeline và GitOps controller nào có quyền thay manifest.
5. Theo dõi các thay đổi tăng quyền và triển khai không thuộc pipeline được phê duyệt.

Một label hoặc annotation **không tự tạo hàng rào an ninh** nếu bất kỳ người dùng nào cũng được sửa nó. Quyền vào Kubernetes API và quy trình review manifest là thành phần không thể thiếu.

### 14.3. Bảo vệ projected token trong container

Projected token không phải secret tĩnh lâu dài, nhưng vẫn có thể được **sử dụng như bearer credential** trong khoảng thời gian hợp lệ. Cần:

- Không đọc/in `AZURE_FEDERATED_TOKEN_FILE` vào stdout, crash report hoặc HTTP response.
- Không gắn volume token cho sidecar hoặc container không cần quyền, trong phạm vi cấu hình hỗ trợ.
- Hạn chế quyền filesystem và quyền thực thi của container, bật Pod Security controls theo chuẩn tổ chức.
- Không cho pod không đáng tin dùng cùng ServiceAccount đặc quyền.
- Cập nhật SDK và OS/container base image; scan image trước release.
- Thiết lập NetworkPolicy/egress policy phù hợp để giảm khả năng lạm dụng token nếu pod bị chiếm quyền.

Nếu app cần dùng nhiều identity cho các dịch vụ khác nhau, hãy thiết kế tách workload hoặc dùng cơ chế identity/credential được Azure hỗ trợ. Không tự giả định một pod sẽ được webhook inject đồng thời nhiều identity mà không có cấu hình rõ.

### 14.4. Cẩn thận khi cấp quyền cho Key Vault hoặc Storage

**Authentication thành công** chưa đủ để khẳng định an toàn:

- Không đặt một quyền đọc cả vault vào UAMI nếu chỉ cần một nhóm secrets nhỏ và chính sách cho phép scope hẹp.
- Đối với Blob, dùng `Storage Blob Data Reader` khi chỉ đọc; chỉ cấp `Contributor` khi cần ghi.
- Nếu dữ liệu lưu qua private endpoint, thiết kế DNS, route, firewall và sự sẵn sàng của mạng.
- Với những hoạt động nhạy cảm, ghi audit và tạo alert thay vì chỉ trông vào việc token exchange đã chạy.
- Khi thu hồi quyền, kiểm tra cả role assignments kế thừa ở subscription/resource group và các quyền cũ từ mô hình khác.

### 14.5. Tách dev/test/prod

Không nên dùng chung UAMI production cho pod thử nghiệm nếu có thể tránh. Một thiết kế dễ kiểm soát:

```text
aks-orders-dev    -> orders/orders-kv-reader -> mi-orders-kv-dev
aks-orders-test   -> orders/orders-kv-reader -> mi-orders-kv-test
aks-orders-prod   -> orders/orders-kv-reader -> mi-orders-kv-prod
```

Mặc dù namespace/SA giống nhau, **issuer của các AKS clusters khác nhau** và các UAMI riêng giúp tránh việc quyền môi trường này lan sang môi trường khác. Nếu cố dùng một UAMI cho nhiều cluster, phải ghi rõ tất cả FIC và ảnh hưởng khi một cluster bị xâm nhập.

## 15. Vận hành nhiều loại workload: Deployment, CronJob và Job

### 15.1. Deployment với nhiều replicas

Một `Deployment` có ba replicas thường tạo ba pod sử dụng **cùng một ServiceAccount** trong pod template. Mỗi pod được cấp projected ServiceAccount token theo cơ chế Kubernetes và đổi token với Entra ID khi ứng dụng cần.

Không tạo ba federated credentials khác nhau chỉ vì có ba replicas có cùng issuer/subject/audience. FIC ràng buộc theo ServiceAccount, không theo tên pod hoặc replica index.

### 15.2. CronJob dùng Workload Identity

`CronJob` tạo `Job`, sau đó Job tạo pod. Label và ServiceAccount phải nằm trong **pod template của Job**, không chỉ metadata của CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
  namespace: reporting
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            azure.workload.identity/use: "true"
        spec:
          serviceAccountName: reports-blob-writer
          restartPolicy: Never
          containers:
            - name: report
              image: acrordersdev001.azurecr.io/report-export:1.0.0
```

Cần tạo ServiceAccount `reporting/reports-blob-writer`, FIC và role Storage trước; YAML này chỉ minh họa vị trí label/SA. Image phải tồn tại và quyền pull phải được xử lý riêng. Với CronJob, không đặt một UAMI quản trị rộng chỉ vì job chỉ chạy vài phút mỗi ngày.

### 15.3. Sidecar và init container

Nếu một Pod có nhiều containers, phải xem container nào thực sự cần Azure credential. Mutating webhook và projected volume có thể đưa thông tin identity vào các containers theo cơ chế cấu hình của dịch vụ; tránh giả định mọi sidecar an toàn khi dùng chung pod và token volume. Cần kiểm tra version của webhook, annotation điều khiển hành vi skip containers nếu hỗ trợ và nguyên tắc tách trách nhiệm giữa containers.

Không nên dùng init container có quyền đọc bí mật rồi lưu giá trị đó vào volume chung không được bảo vệ trong suốt vòng đời pod. Khi có lựa chọn phù hợp, ứng dụng chính nên tự gọi dịch vụ Azure thông qua SDK và managed identity để tránh tạo bản sao credential không cần thiết.

## 16. Infrastructure as Code và quy trình phát hành

Với hệ thống production, nên quản lý hai mặt của AKS Workload Identity:

1. **Azure-side:** AKS OIDC/workload identity settings, user-assigned identity, federated identity credential, Azure RBAC, Key Vault/Storage/Service Bus.
2. **Kubernetes-side:** namespace, ServiceAccount, annotations, Deployment/CronJob pod labels, network policies và admission/security settings.

Một chuỗi triển khai có thứ tự:

```text
1. AKS sẵn sàng + OIDC issuer + workload identity enabled
                         |
                         v
2. Tạo user-assigned managed identity
                         |
                         v
3. Tạo FIC với issuer/subject/audience chính xác
                         |
                         v
4. Gán Azure RBAC data-plane đúng resource/scope
                         |
                         v
5. Tạo namespace + Kubernetes ServiceAccount annotation
                         |
                         v
6. Triển khai Pod template có label workload identity
                         |
                         v
7. Canary test token exchange + Azure data access + deny test
                         |
                         v
8. Rollout và giám sát production
```

**Không phải mọi bước đều phải chạy bằng tay.** Có thể sử dụng Bicep/ARM/Terraform cho Azure resources và Helm/Kustomize/GitOps cho Kubernetes manifests. Nhưng dù dùng công cụ nào, phải điều phối **phụ thuộc** giữa OIDC issuer, FIC, client ID, role assignment và pod.

### 16.1. Tài liệu hóa mapping danh tính

Một manifest **khái niệm** (không phải schema deploy được trực tiếp):

```yaml
cluster: aks-orders-prod
namespace: orders
serviceAccount: orders-kv-reader
oidcIssuer: "<issuer-url-from-cluster>"
managedIdentity:
  name: mi-orders-kv-prod
  clientId: "<client-id>"
federatedCredential:
  subject: "system:serviceaccount:orders:orders-kv-reader"
  audience: "api://AzureADTokenExchange"
azurePermissions:
  - resource: "<key-vault-resource-id>"
    role: "Key Vault Secrets User"
owner: orders-platform-team
```

Việc lưu mapping như vậy giúp phát hiện FIC không còn dùng, tránh lẫn tenant và kiểm tra quyền sau khi chuyển cluster hoặc ứng dụng. Không cần lưu token, client secret hoặc giá trị Key Vault secret trong manifest.

### 16.2. Rollback và thay đổi an toàn

Thay đổi FIC hoặc role có thể làm các pod tạo mới mất khả năng lấy token. Quy trình an toàn:

- Tạo role/FIC mới và kiểm thử bằng canary trước khi cắt luồng cũ nếu đổi identity.
- Không xóa FIC cũ trong lúc workload khác vẫn dùng issuer/subject đó.
- Chọn rollout có health checks và thông tin lỗi rõ ràng.
- Theo dõi token errors và Key Vault/Storage access denied sau triển khai.
- Sau khi chuyển hoàn tất, thu hồi cấu hình và quyền cũ theo chính sách.

Đừng rollback bằng cách đưa client secret vào Kubernetes Secret để tránh sửa lỗi chính; điều đó tái tạo đúng rủi ro mà Workload Identity giúp giảm.

## 17. Tác động chi phí và khả năng mở rộng

AKS Workload Identity chủ yếu là một **cơ chế danh tính và federation**, không phải một worker pool bổ sung tương tự node pool. Tuy nhiên, kiến trúc tổng thể vẫn phát sinh chi phí từ:

| Thành phần | Yếu tố chi phí/giới hạn cần tính |
|---|---|
| AKS | Node VM, disk, network, control plane tier và monitoring theo mô hình sử dụng |
| Microsoft Entra/identity | Các tính năng danh tính/giám sát/điều kiện license theo dịch vụ liên quan |
| Key Vault/Storage/Service Bus | Operations, dung lượng, throughput, logs và network |
| Network | Private endpoint, NAT, Firewall, DNS và dữ liệu truyền |
| Observability | Log Analytics ingestion, retention, metrics và alerts |
| Vận hành federation | Số danh tính/FIC, kiểm soát quyền, policy và quy trình kiểm thử |

Không mặc định mỗi token exchange có một mức phí độc lập giống việc tạo VM; kiểm tra bảng giá và hạn mức chính thức theo tenant/dịch vụ. Với số lượng lớn workloads, vấn đề thường là **quản trị danh tính, quota FIC và role assignments, latency token acquisition hoặc khả năng endpoint dịch vụ**, không chỉ chi phí Kubernetes manifests.

Để sử dụng hiệu quả:

- Dùng một ServiceAccount/UAMI cho các replicas thực sự cùng mục đích/quyền, tránh tạo identity thừa cho mỗi replica.
- Dùng cache/token refresh của SDK để không yêu cầu token trên mọi request nghiệp vụ.
- Quản lý số FIC theo tổ chức và tránh reuse UAMI xuyên môi trường một cách vô thức.
- Thiết lập metrics cho lỗi xác thực, lỗi quyền, latency Key Vault và trạng thái pod.
- Rà soát các UAMI, FIC, roles không còn workload sử dụng.

## 18. Bài tập tình huống

### Tình huống A: API chỉ đọc secret

AKS production có namespace `orders`, Deployment `orders-api` và Key Vault `kv-orders-prod` dùng Azure RBAC. Yêu cầu: chỉ pod API được phép đọc secret cần thiết; không lưu client secret.

**Nhiệm vụ:**

1. Chọn loại managed identity và lý do.
2. Xác định subject đúng cho ServiceAccount `orders-kv-reader`.
3. Mô tả issuer và audience trong FIC.
4. Xác định role dữ liệu tối thiểu ở Key Vault.
5. Chỉ ra vị trí annotation trên ServiceAccount và label trên Pod template.
6. Nêu cách kiểm tra khi application logs trả `403`.

**Hướng giải:** dùng UAMI riêng cho orders hoặc một identity có ranh giới tương đương; FIC có subject `system:serviceaccount:orders:orders-kv-reader`, issuer AKS OIDC đúng và audience token exchange phù hợp. SA dùng `azure.workload.identity/client-id`, Pod template dùng `azure.workload.identity/use: "true"`. Gán quyền đọc secret ở scope phù hợp, kiểm tra vault permission model/RBAC, principal, DNS và private endpoint.

### Tình huống B: đổi namespace làm lỗi xác thực

Đội vận hành chuyển Deployment từ `orders` sang `orders-v2`, giữ nguyên tên ServiceAccount và client ID. Pod được mutate nhưng Entra token exchange thất bại.

**Câu hỏi:** Vì sao chỉ sửa namespace trong manifest chưa đủ? Nên đổi gì và kiểm tra ra sao?

**Hướng giải:** subject trong FIC cũ là `system:serviceaccount:orders:orders-kv-reader`, còn token mới mang `system:serviceaccount:orders-v2:orders-kv-reader`. Phải tạo hoặc thay FIC tương ứng, test canary rồi dọn FIC cũ theo quy trình, không mở rộng role quyền dữ liệu để giải quyết sai subject.

### Tình huống C: Key Vault đọc được từ laptop nhưng không đọc được trong pod

Developer dùng `az login` trên laptop và đọc Key Vault thành công, nhưng Java API trong AKS gặp lỗi. Laptop có quyền riêng của người dùng; pod phải dùng UAMI.

**Nhiệm vụ:** mô tả cách phân biệt:

- Workload Identity webhook chưa inject token.
- FIC issuer/subject/audience không khớp.
- UAMI chưa được gán Key Vault role.
- Key Vault bị chặn mạng/private endpoint.
- Java SDK cũ hoặc chọn nhầm credential.

**Hướng giải:** kiểm tra PodSpec/SA, AKS issuer, FIC, UAMI client/principal ID, quyền Key Vault và SDK. Phép thử trên laptop không chứng minh identity của pod có quyền. Giữ log an toàn, không in JWT hoặc secret values.

### Tình huống D: nhiều nhóm dùng chung UAMI

Ba namespace `orders`, `payments` và `hr` đều dùng chung một UAMI có quyền đọc tất cả secrets. Một pod thuộc nhóm HR bị chiếm quyền.

**Nhiệm vụ:** đánh giá blast radius và đề xuất migration sang UAMI/FIC/roles riêng, thiết kế admission/RBAC bảo vệ ServiceAccount, kế hoạch rollout và cách thu hồi quyền cũ.

**Hướng giải:** chia UAMI theo domain/quyền dữ liệu, giới hạn Azure role ở vault/secret phù hợp, định nghĩa FIC theo issuer và subject, triển khai canary, kiểm thử dữ liệu ngoài phạm vi bị từ chối, rồi thu hồi FIC và role dùng chung không còn cần thiết.

## 19. Câu hỏi tự kiểm tra

**1. ServiceAccount trong Kubernetes có tự cấp quyền Azure Key Vault không?** Không. Nó cung cấp danh tính Kubernetes; cần federation với managed identity và quyền ở dịch vụ Azure.

**2. Ba trường FIC quan trọng nhất là gì?** Issuer, subject và audience.

**3. Subject của SA `orders-kv-reader` trong namespace `orders` là gì?** `system:serviceaccount:orders:orders-kv-reader`.

**4. Annotation `azure.workload.identity/client-id` dùng Client ID hay Principal ID?** Client ID của managed identity.

**5. Pod label nào thường cần để workload identity webhook mutate pod?** `azure.workload.identity/use: "true"` đặt trên Pod template.

**6. Workload Identity có giải quyết việc kubelet pull private image từ ACR không?** Không trực tiếp; image pull có luồng node/kubelet/registry riêng.

**7. Entra token exchange thành công có chứng minh được đọc Key Vault secret không?** Không. Key Vault còn kiểm tra role/access policy và các điều kiện mạng.

**8. Vì sao đổi namespace có thể làm federation thất bại?** Subject của ServiceAccount token chứa namespace; FIC phải khớp subject mới.

**9. User-assigned identity có bị xóa khi xóa Deployment không?** Không. UAMI là tài nguyên Azure độc lập cần dọn theo quy trình riêng.

**10. Vì sao dùng Java Azure Identity SDK thay vì tự đọc token một lần?** SDK hỗ trợ token exchange, caching và làm mới token theo cơ chế tương thích.

## 20. Checklist production

- [ ] AKS đang dùng phiên bản hỗ trợ, đã bật OIDC issuer và Workload Identity theo quy trình.
- [ ] Lấy issuer URL từ **đúng cluster**, không tự suy từ tên cluster.
- [ ] Đã chọn user-assigned identity hoặc mô hình federation được hỗ trợ phù hợp, ghi rõ owner.
- [ ] FIC có issuer, subject, audience chính xác; kiểm kê FIC trùng/thừa.
- [ ] Đã phân biệt UAMI Resource ID, Client ID và Principal/Object ID.
- [ ] Azure RBAC/data-plane permission được cấp đúng action và scope; không cấp quyền quản trị chỉ để đọc dữ liệu.
- [ ] Vault/Storage/Service Bus permission model và điều kiện mạng đã được kiểm tra.
- [ ] Kubernetes ServiceAccount có annotation client ID chính xác.
- [ ] Pod template có label `azure.workload.identity/use: "true"` và chỉ định đúng `serviceAccountName`.
- [ ] Pod mới đã được webhook mutate, có projected token và environment variables cần thiết.
- [ ] Ứng dụng dùng Azure SDK tương thích; token và secret value không bị log hoặc lưu cứng.
- [ ] Đã thử token exchange và thao tác Azure thật, cùng negative tests về quyền ngoài phạm vi.
- [ ] Kubernetes RBAC/admission policy ngăn workload không được phép chọn ServiceAccount đặc quyền.
- [ ] Identity của pod được phân biệt với AKS cluster identity và kubelet identity.
- [ ] Đã xét token refresh, RBAC propagation, webhook mutation khi rollout và trường hợp mất mạng.
- [ ] Đã có logging, alerts, CI/CD/IaC, runbook và kế hoạch đổi cluster/namespace/identity.
- [ ] Đã kiểm tra giới hạn số FIC, số identity, hiệu năng và chi phí tài nguyên liên quan.
- [ ] Có phương án migration, rollback và thu hồi quyền cũ an toàn cho production.

## Kết luận

**AKS Workload Identity** dùng **Kubernetes ServiceAccount token dựa trên OIDC** kết hợp **federated identity credential** của Microsoft Entra ID để cho pod nhận **Azure access token** của một danh tính được phê duyệt. Nhờ đó, ứng dụng có thể truy cập Key Vault, Storage, Service Bus và những dịch vụ hỗ trợ mà **không phải lưu client secret trong container**. Nhưng token exchange thành công chưa đủ: tài nguyên đích vẫn kiểm tra Azure RBAC hoặc cơ chế phân quyền tương ứng và các điều kiện kết nối mạng.

Để vận hành an toàn, hãy bảo đảm **issuer–subject–audience khớp chính xác**, ServiceAccount có annotation client ID đúng, Pod template có workload identity label, ứng dụng dùng SDK tương thích và Azure permissions tuân thủ least privilege. Khi kết hợp với Kubernetes RBAC, admission controls, bảo vệ projected tokens, CI/CD, logging và quản lý vòng đời danh tính, Workload Identity trở thành nền tảng xác thực đáng tin cậy cho ứng dụng chạy trên AKS.
