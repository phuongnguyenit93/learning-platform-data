# Kết nối AKS với Azure Container Registry

Trong một hệ thống triển khai trên Microsoft Azure, ứng dụng container thường được xây dựng từ source code, đóng gói thành image, lưu tại registry rồi triển khai lên **Azure Kubernetes Service (AKS)**. Khi image được lưu trong **Azure Container Registry (ACR)** ở chế độ private, cluster phải có cơ chế xác thực và đường mạng thích hợp để các node Kubernetes kéo image. Nếu không, Deployment có thể được Kubernetes chấp nhận nhưng Pod mãi ở trạng thái **ErrImagePull** hoặc **ImagePullBackOff**.

**Kết nối AKS với ACR** không chỉ là đăng nhập Docker. Đây là bài toán phối hợp **Azure identity**, **Azure RBAC hoặc quyền repository**, **kubelet**, **registry**, **network/DNS** và **Kubernetes deployment**. Cấp nhầm quyền cho control plane thay vì kubelet, cấu hình registry private endpoint sai DNS hoặc dùng sai tên image đều có thể khiến workload không khởi động.

Bài học thuộc chương **Nền tảng Azure Kubernetes Service** trong module **CLOUD_PROVIDERS_AZURE**, nơi người học triển khai kiến trúc Azure từ subscription, resource group, Microsoft Entra ID, mạng, compute, lưu trữ đến bảo mật, quan sát và chi phí. Chúng ta sẽ thiết kế và thực hành luồng **build image → push vào ACR → cấp quyền cho AKS → deploy Pod → xác minh image pull**, sau đó xử lý các tình huống production.

> **Ý chính:** Quyền **kéo image** thường thuộc về **danh tính kubelet của AKS** hoặc cơ chế image pull được cluster cấu hình, **không phải** danh tính của Java/Node.js container đang chạy. Trong phần lớn mô hình AKS dùng managed identity với ACR ở chế độ RBAC registry truyền thống, dùng **az aks --attach-acr** giúp cấp quyền AcrPull cho kubelet identity. Với ACR bật chế độ **RBAC Registry + ABAC Repository Permissions**, cần đường cấu hình quyền khác; không dùng attach-acr như thể nó luôn hỗ trợ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của ACR, AKS, node, kubelet, Pod và container image trong quy trình triển khai.
2. Phân biệt quyền **push image** của CI/CD với quyền **pull image** của node AKS.
3. Hiểu **control plane identity**, **kubelet identity**, **workload identity** và vì sao chúng không thay thế nhau.
4. Chọn cách kết nối phù hợp với **ACR RBAC Registry Permissions** hoặc **ACR RBAC Registry + ABAC Repository Permissions**.
5. Dùng Azure CLI để đọc cấu hình, attach ACR vào AKS hoặc gán quyền cho kubelet identity theo mô hình được hỗ trợ.
6. Build/push một image thử nghiệm bằng **az acr build** và triển khai Kubernetes Deployment tham chiếu registry private.
7. Kiểm tra Pod events, rollout, node image pull và xử lý **401/403/404**, DNS hoặc network timeout.
8. Thiết kế ACR private endpoint, DNS, egress và các quyền ở subscription/resource group khác nhau.
9. Quản trị image tag/digest, bảo mật supply chain, CI/CD, rotation và rollback.
10. Xem chi phí registry, build, network, AKS nodes, quan sát và lập checklist production.

## 2. Vị trí của ACR trong kiến trúc AKS

**Azure Container Registry (ACR)** là dịch vụ registry do Azure quản lý, lưu trữ OCI/Docker images và các artifact được hỗ trợ. **AKS** điều phối container trên các node Kubernetes. Khi khai báo một Pod với image private, node phải lấy manifest/layers từ registry để tạo container.

~~~mermaid
flowchart LR
    DEV["Source code"] --> CI["Build/test/scan"]
    CI -->|"Push"| ACR["Azure Container Registry<br/>myregistry.azurecr.io"]
    AKS["AKS control plane"] -->|"Lập lịch Pod"| NODE["AKS node + kubelet"]
    NODE -->|"Pull image qua identity và network"| ACR
    NODE --> POD["Pod chạy container"]
    POD --> DATA["Azure SQL / Storage / Key Vault"]
~~~

Điểm quan trọng trong sơ đồ:

- **CI/CD** cần quyền **push** (và thường đọc) image vào ACR.
- **Kubelet trên node** cần quyền **pull** image từ ACR để khởi tạo Pod.
- **Ứng dụng trong Pod** cần quyền riêng để truy cập Storage, Key Vault, database hoặc dịch vụ khác nếu có.
- Quyền pull không tự cho phép push, xóa repository, đổi registry network rule hay truy cập dữ liệu ứng dụng.

Đừng kết luận rằng một lệnh **docker login** chạy thành công trên máy developer chứng minh node AKS kéo được image. Hai môi trường có danh tính, mạng và DNS khác nhau.

### 2.1. Những thành phần thường có mặt

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Subscription/resource group | Phạm vi quản lý, cấp quyền, tính phí | rg-aks-lab, rg-acr-lab |
| ACR registry | Lưu image/OCI artifact | acrordersdemo123 |
| Login server | Endpoint dùng trong tên image | acrordersdemo123.azurecr.io |
| Repository | Phân nhóm image theo tên | orders-api |
| Tag/digest | Xác định phiên bản nội dung image | orders-api:1.0.0 hoặc sha256 digest |
| AKS cluster | Quản lý workload Kubernetes | aks-orders-lab |
| Node pool và kubelet | Chạy Pod, kéo image | Linux agent pool |
| Kubernetes Deployment | Mong muốn số Pod và container image | orders-api |
| Kubernetes Service | Endpoint tới Pod sau khi khởi động | ClusterIP cho lab |
| Azure identity/RBAC | Xác thực và phân quyền với ACR | Kubelet identity + AcrPull |
| Network/DNS | Đường đến ACR login/data endpoints | Public egress hoặc Private Endpoint |

### 2.2. Tên image chính xác

Một image trong ACR có dạng:

~~~text
<registry-name>.azurecr.io/<repository>:<tag>

Ví dụ:
acrordersdemo123.azurecr.io/aks-pull-demo:1.0.0
~~~

Trong production có thể tham chiếu bằng digest:

~~~text
acrordersdemo123.azurecr.io/aks-pull-demo@sha256:<digest-thuc-te>
~~~

Tên registry là một phần của image reference. **myregistry** không giống **myregistry.azurecr.io**; tag **1.0.0** cũng khác **1.0** và **latest**. Kubernetes không tự tìm image ở registry private nếu bạn chỉ khai báo tên repository không kèm hostname.

## 3. Phân biệt các loại danh tính và quyền

Đây là phần quyết định liệu AKS có kéo được image hay không.

### 3.1. Control plane identity

AKS dùng **control plane identity** để quản lý những tài nguyên Azure cần cho hoạt động của cluster theo cấu hình, ví dụ load balancer hoặc network resources. Với cluster dùng managed identity, trường **identity** trong tài nguyên AKS thể hiện một phần thông tin danh tính này.

**Không mặc định** cấp AcrPull cho control plane identity là đủ để kubelet kéo image.

### 3.2. Kubelet identity

**Kubelet identity** được AKS sử dụng cho các hoạt động ở node, đặc biệt là xác thực để **pull image từ ACR** trong mô hình managed identity phổ biến.

Thông tin thường nằm ở:

~~~text
AKS identityProfile.kubeletidentity
    ├── clientId
    ├── objectId
    └── resourceId
~~~

Kubelet identity có thể được AKS tự quản lý hoặc là user-assigned managed identity được cấu hình. Khi cấp role cho một principal, cần dùng đúng **object ID/principal ID** theo API/CLI, không nhầm **client ID**, resource ID và object ID.

### 3.3. Workload identity của Pod

**Microsoft Entra Workload ID cho AKS** cho phép ứng dụng trong Pod có quyền Azure theo Kubernetes service account và liên kết danh tính được cấu hình. Nó thích hợp cho truy cập Blob Storage, Key Vault và những dịch vụ khác từ ứng dụng.

Nhưng ở thời điểm **image pull**, Pod chưa chạy, nên không thể dựa vào token mà ứng dụng sẽ nhận sau khi khởi động để giải quyết xác thực pull ban đầu. **Workload identity không tự thay thế kubelet identity trong image pull**.

### 3.4. CI/CD identity

Pipeline build/push cần danh tính riêng, có phạm vi **push** vào registry hoặc repository được phê duyệt.

Không dùng quyền của một tài khoản CI/CD để cấp trực tiếp **Owner/Contributor** toàn subscription cho node AKS. Phân tách nhiệm vụ giúp giảm tác động nếu pipeline hoặc workload bị xâm nhập.

### 3.5. Vai trò registry hay gặp

| Role/quyền | Dùng cho | Ghi chú |
|---|---|---|
| **AcrPull** | Kubelet AKS đọc/pull image từ ACR ở chế độ RBAC registry thông thường | Không cho push image |
| **AcrPush** | Pipeline/đội được phép đẩy image theo mô hình RBAC registry hỗ trợ | Quyền rộng hơn pull, không cấp cho kubelet chỉ để deploy |
| **Container Registry Repository Reader** | Đọc/pull repository trong chế độ ACR **RBAC Registry + ABAC Repository Permissions** | Có thể kết hợp điều kiện ABAC để giới hạn repository theo cấu hình |
| **Container Registry Repository Writer** hoặc role phù hợp khác | Quản lý nội dung repository theo mô hình ABAC hỗ trợ | Chọn quyền theo chức năng push/metadata thật sự cần |
| **Owner/User Access Administrator/Role Based Access Control Administrator** | Quản lý role assignments theo scope và điều kiện | Không cấp cho kubelet để kéo image |

Danh sách quyền thực tế có thể thay đổi theo chế độ ACR và dịch vụ. **AcrPull** và **Container Registry Repository Reader** không phải hai tên role hoán đổi trong mọi permission mode.

## 4. Chọn mô hình ACR permissions trước khi dùng attach-acr

ACR có những mô hình kiểm soát quyền. Hai cấu hình thường gặp:

### 4.1. RBAC Registry Permissions

Đây là mô hình RBAC registry truyền thống. Bạn có thể cấp role **AcrPull** tại phạm vi ACR cho kubelet identity.

Với AKS và ACR đáp ứng điều kiện, Azure CLI có hỗ trợ:

~~~bash
# Khi tạo AKS mới (minh họa phần tham số)
az aks create ... --attach-acr <acr-name-or-resource-id>

# Với AKS đã tồn tại
az aks update ... --attach-acr <acr-name-or-resource-id>
~~~

Các lệnh hoàn chỉnh ở phần thực hành. Trong trường hợp này, **attach-acr** giúp cấu hình role assignment cần thiết; nó không sao chép image vào cluster hoặc tự tạo Kubernetes Deployment.

### 4.2. RBAC Registry + ABAC Repository Permissions

Với ACR dùng mô hình **RBAC Registry + ABAC Repository Permissions**, có thể cần role **Container Registry Repository Reader** cho principal pull, kèm ABAC condition theo repository khi cần giới hạn phạm vi.

**Không dựa vào az aks --attach-acr trong mô hình này**: đường tích hợp attach-acr không hỗ trợ cấp đúng các role ABAC repository theo cách registry yêu cầu. Thay vào đó, xác định kubelet identity và gán role phù hợp qua Azure RBAC với scope/condition chính xác.

Một registry có nhiều repository cho các nhóm khác nhau có thể dùng điều kiện ABAC để tránh một kubelet identity đọc tất cả image. Việc giới hạn theo repository và cách các điều kiện được thực thi phải được kiểm tra trong tài liệu/quy trình hiện hành.

### 4.3. Quy tắc quyết định

~~~mermaid
flowchart TD
    A["AKS cần pull ACR private"] --> B{"ACR permission mode?"}
    B -->|"RBAC Registry Permissions"| C["Attach ACR hoặc gán AcrPull<br/>cho kubelet identity"]
    B -->|"RBAC Registry + ABAC Repository Permissions"| D["Gán Container Registry Repository Reader<br/>và ABAC condition khi cần"]
    C --> E["Xác minh role assignment"]
    D --> E
    E --> F["Xác minh DNS và đường mạng node → registry"]
    F --> G["Deploy Pod, xem Events và image pull"]
~~~

Không cố sửa lỗi ABAC bằng cách bật **ACR admin user** hoặc cấp **Contributor** ở subscription. Hãy giải quyết đúng quyền và đúng principal trước.

## 5. Điều kiện tiên quyết của bài thực hành

Ví dụ xuyên suốt dùng:

| Giá trị | Tên minh họa |
|---|---|
| Subscription | subscription lab đã được duyệt |
| Region | southeastasia |
| Resource group ACR | rg-acr-lab |
| Resource group AKS | rg-aks-lab |
| ACR name | acrordersdemo123 *(phải duy nhất)* |
| AKS cluster | aks-orders-lab |
| Repository | aks-pull-demo |
| Image tag | 1.0.0 |
| Kubernetes namespace | acr-pull-lab |
| Deployment | aks-pull-demo |
| Service | aks-pull-demo (ClusterIP) |

Các tên là **ví dụ**. Trước khi chạy lệnh tạo tài nguyên:

1. Có quyền quản trị đúng subscription/resource group và quyền gán role khi cần. **Network Contributor** hoặc **Contributor** thông thường không mặc nhiên có quyền tạo role assignment.
2. Kiểm tra ACR và AKS đã tồn tại hay chưa, tránh đè hoặc sửa tài nguyên production.
3. Xác minh **permission mode** của ACR: truyền thống hay ABAC repository.
4. Xác nhận cùng tenant hoặc có phương án xác thực cross-tenant được hỗ trợ; các lệnh attach/gán role minh họa giả định **cùng Microsoft Entra tenant**.
5. Kiểm tra quota AKS nodes/VM, địa chỉ VNet, kubeconfig và network policy của tổ chức.
6. Xác định ACR dùng public endpoint hay Private Link, AKS có đường đến login server và data endpoints không.
7. Có Azure CLI, **kubectl** và công cụ tạo image như Docker hoặc **az acr build** theo quyền đã cấp.
8. Có ngân sách và phương án dọn lab; AKS nodes và ACR có thể tiếp tục tính phí ngay cả khi chưa chạy application Pod.

**Không cần** tạo cluster mới nếu đã có AKS lab. Hãy ưu tiên dùng tài nguyên được chủ sở hữu cho phép thay vì tạo một cluster thứ hai chỉ để thử image pull.

## 6. Bước A: tạo ACR hoặc xác minh registry đã có

Ví dụ Bash trong Azure Cloud Shell hoặc shell có Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

ACR_RG="rg-acr-lab"
REGION="southeastasia"
ACR_NAME="<globally-unique-acr-name>"

az group create \
  --name "$ACR_RG" \
  --location "$REGION"

az acr create \
  --resource-group "$ACR_RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --location "$REGION" \
  --admin-enabled false
~~~

Nếu registry đã tồn tại, **không chạy az acr create**; dùng các lệnh đọc ở phần sau. Tên ACR phải hợp lệ và duy nhất trong namespace ACR, thường chỉ dùng ký tự chữ/số phù hợp giới hạn của dịch vụ.

### 6.1. Đọc registry ID và login server

~~~bash
ACR_ID=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --query id --output tsv)

LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --query loginServer --output tsv)

printf "ACR_ID=%s\nLOGIN_SERVER=%s\n" "$ACR_ID" "$LOGIN_SERVER"
~~~

Kết quả kỳ vọng có dạng:

~~~text
ACR_ID=/subscriptions/<id>/resourceGroups/rg-acr-lab/providers/Microsoft.ContainerRegistry/registries/acrordersdemo123
LOGIN_SERVER=acrordersdemo123.azurecr.io
~~~

Kiểm tra các biến không rỗng và trỏ đúng registry. Nếu ACR ở subscription khác, hãy lấy **resource ID** dưới đúng subscription/tenant được cấp quyền thay vì tin rằng registry trùng tên hoặc subscription hiện tại là đúng.

### 6.2. Xác định permission mode

Xem trong **Azure Portal → Container registries → registry → Access control (IAM) / Properties** hoặc phần cấu hình về **role assignment permissions mode** mà phiên bản Portal hiện hành cung cấp.

Với Azure CLI/API, có thể xem JSON cấu hình registry rồi đối chiếu trường **roleAssignmentMode** khi dịch vụ/API và phiên bản CLI hỗ trợ:

~~~bash
az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --output json
~~~

Tên/khả năng hiển thị trường có thể phụ thuộc phiên bản API và giao diện. **Không suy luận permission mode từ SKU Basic/Standard/Premium**: SKU và mô hình phân quyền là những quyết định khác nhau.

## 7. Bước B: xác minh hoặc tạo AKS cluster

### 7.1. Nếu đã có AKS

~~~bash
AKS_RG="rg-aks-lab"
AKS_NAME="aks-orders-lab"

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,location:location,provisioningState:provisioningState,identity:identity,kubeletIdentity:identityProfile.kubeletidentity}" \
  --output json
~~~

Quan sát:

- Cluster đang ở trạng thái hoạt động phù hợp.
- Mô hình identity là **managed identity** hay cơ chế khác.
- Có **kubeletidentity** nào và ID tương ứng.
- Cluster nằm đúng subscription/tenant và region.
- Node pool có node sẵn sàng để thực hiện pull.

Không ghi secrets từ output quản trị vào repository. Các trường identity/public metadata có thể được ghi vào runbook ở phạm vi phù hợp.

### 7.2. Nếu cần tạo AKS lab mới

**Đây là thao tác có thể phát sinh chi phí AKS/node VM, disk, network và logs.** Chỉ thực hiện trong môi trường được duyệt, sau khi kiểm tra quota và SKU/feature.

~~~bash
az group create \
  --name "$AKS_RG" \
  --location "$REGION"

az aks create \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --location "$REGION" \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --enable-managed-identity \
  --generate-ssh-keys
~~~

Lệnh này minh họa cluster Linux nhỏ dùng managed identity. Khả năng hỗ trợ node VM size, quota, phiên bản Kubernetes mặc định và các tùy chọn network có thể thay đổi theo region/subscription. Có môi trường yêu cầu cấu hình VNet, Azure Policy, network plugin, private cluster hoặc SKU/tier riêng; không coi mẫu tạo tối giản là thiết kế production.

**Không cần** tạo cluster mới nếu đã có cluster lab đáp ứng điều kiện.

### 7.3. Đọc kubelet identity đúng mục đích

~~~bash
KUBELET_OBJECT_ID=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity.objectId" \
  --output tsv)

KUBELET_CLIENT_ID=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity.clientId" \
  --output tsv)

printf "Kubelet objectId: %s\n" "$KUBELET_OBJECT_ID"
printf "Kubelet clientId: %s\n" "$KUBELET_CLIENT_ID"
~~~

Nếu object ID rỗng hoặc cluster dùng **service principal** cũ, **dừng phần gán role minh họa và xác định đúng principal thực sự dùng để image pull**. Không tự gán role cho bất kỳ identity nào “trông có vẻ liên quan”.

Khi đổi node pool/identity hoặc tái tạo cluster, hãy kiểm tra role assignment còn gắn với principal hiện tại hay không.

## 8. Bước C1: attach ACR vào AKS trong chế độ RBAC registry

**Áp dụng cho ACR sử dụng RBAC Registry Permissions và AKS phù hợp với cơ chế attach-acr.** Với cluster mới, có thể dùng **--attach-acr** trong lệnh tạo cluster; với cluster đã tồn tại, dùng update.

### 8.1. Attach vào AKS đang tồn tại

~~~bash
az aks update \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --attach-acr "$ACR_ID"
~~~

Tham số **--attach-acr** có thể nhận tên registry hoặc resource ID trong những điều kiện hỗ trợ; dùng **ACR_ID** giúp tránh chọn nhầm khi registry nằm ở resource group/subscription khác.

**Thao tác này làm gì?**

- Xác định registry mục tiêu.
- Cấu hình/gán quyền **AcrPull** cho principal phù hợp của AKS, thông thường là **kubelet identity** khi cluster dùng managed identity.
- Tạo điều kiện để node pull image từ private registry.

**Thao tác này không làm gì?**

- Không build/push image.
- Không tạo Kubernetes Deployment/Pod.
- Không cấp quyền push cho CI/CD.
- Không mở firewall, private endpoint hoặc DNS.
- Không tự cho phép ứng dụng trong Pod đọc Blob/Key Vault.
- Không bảo đảm pull thành công nếu role chưa propagate hoặc network chưa đến được ACR.

### 8.2. Attach ngay khi tạo cluster

Với lab mới và ACR RBAC registry truyền thống:

~~~bash
az aks create \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --location "$REGION" \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --enable-managed-identity \
  --generate-ssh-keys \
  --attach-acr "$ACR_ID"
~~~

**Chỉ dùng một trong hai đường tạo cluster:** nếu cluster đã tồn tại, dùng **az aks update**, không chạy lại **az aks create**. Nếu đang dùng ACR ABAC repository mode, hãy chuyển sang bước C2 bên dưới.

### 8.3. Gán AcrPull thủ công khi không dùng attach-acr

Trường hợp được tổ chức cho phép quản lý role assignment trực tiếp:

~~~bash
az role assignment create \
  --assignee-object-id "$KUBELET_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "$ACR_ID"
~~~

Điều kiện:

- Kubelet identity là managed identity/service principal đúng của cluster.
- Người chạy có quyền **tạo role assignment** trên ACR scope.
- Principal và registry thuộc mô hình tenant/quyền hỗ trợ.
- Registry đang ở permission mode phù hợp với **AcrPull**.

Không tự động gán AcrPull trên toàn subscription nếu chỉ một registry cần được pull. Role assignment có thể mất một thời gian để có hiệu lực; nếu Pod vừa được tạo trước khi quyền propagate, xem Events và cho kubelet retry thay vì liên tục thêm quyền cao hơn.

### 8.4. Kiểm tra role assignment

~~~bash
az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --include-inherited \
  --output table
~~~

Nếu không có quyền đọc IAM, kết quả có thể bị hạn chế. Cần phân biệt **không thấy role do thiếu quyền** với **role chưa tồn tại**. Hãy dùng principal/object ID thực tế để kiểm tra.

## 9. Bước C2: ACR có ABAC repository permissions

**Đây là nhánh thay thế C1, không phải bước cộng thêm cho mọi registry.**

Nếu registry chọn **RBAC Registry + ABAC Repository Permissions**, người quản trị cần cấp **Container Registry Repository Reader** cho kubelet identity theo permission mode ACR.

### 9.1. Gán role Reader theo scope ACR

Ví dụ minh họa ở phạm vi registry:

~~~bash
az role assignment create \
  --assignee-object-id "$KUBELET_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Registry Repository Reader" \
  --scope "$ACR_ID"
~~~

Lệnh trên chỉ nên dùng sau khi đã xác nhận registry thực sự ở ABAC mode, kubelet identity đúng và quyền gán role hợp lệ. Nếu không có điều kiện repository, role có thể cho quyền đọc rộng trên các repository thuộc scope đó theo chính sách được áp dụng.

### 9.2. Khi chỉ muốn AKS pull một repository

Một tổ chức có nhiều nhóm dùng chung ACR có thể muốn:

~~~text
AKS Orders     → chỉ pull repository orders/*
AKS Payments   → chỉ pull repository payments/*
CI Orders      → push repository orders/* nhưng không sửa payments/*
~~~

Khi ACR hỗ trợ ABAC repository conditions, người quản trị có thể gắn **condition** vào role assignment để giới hạn repository. Điều kiện, cú pháp biểu thức và permission semantics cần được thực hiện qua hướng dẫn IAM/ACR chính thức, không tự suy từ cách Kubernetes đặt namespace.

**Namespace Kubernetes không tự giới hạn repository ACR mà kubelet identity có thể pull.** Kubelet identity thường dùng ở cấp cluster/node pool theo mô hình AKS; muốn ranh giới phân quyền kéo image giữa các nhóm phải thiết kế phù hợp ở ACR IAM và kiến trúc cluster, kết hợp workload admission policies.

### 9.3. Một số giới hạn theo tổ hợp quyền

- **attach-acr** không thay thế quy trình cấp **Container Registry Repository Reader** trong ABAC mode.
- Nếu registry chuyển permission mode sau khi đã attach AKS, phải **đánh giá lại role** và kiểm thử image pull.
- Không chỉ dựa vào tên role cũ để kết luận authorization đang có hiệu lực.
- Hệ thống quản lý identity/quyền cross-tenant có điều kiện riêng; bài học này giả định same tenant cho ví dụ CLI.
- Sau gán quyền, chờ propagation và tạo một Pod kiểm tra bằng image private để xác minh thực tế.

## 10. Bước D: build và push image thử nghiệm vào ACR

Bài lab cần có một image thực sự trong ACR. Ta dùng container web nhỏ với **Nginx** chỉ để kiểm tra quyền pull. Đây không phải triển khai ứng dụng production; container được tạo từ image công khai trong môi trường được phê duyệt.

### 10.1. File Dockerfile minh họa

Trong một thư mục dự án lab, tạo hai file:

**Dockerfile**

~~~dockerfile
# Demo đơn giản, production cần pin digest và quét CVE.
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
~~~

**index.html**

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>AKS ACR demo</title></head>
<body><h1>AKS da keo image tu ACR thanh cong</h1></body>
</html>
~~~

Ứng dụng chỉ nghe HTTP/80 **bên trong cluster**; bài này không cần công khai ra Internet. Image base được kéo từ public registry nên quá trình build cần network phù hợp và có thể chịu ảnh hưởng của rate limiting; production nên dùng base image đã được duyệt và quản lý.

### 10.2. Build image bằng ACR Tasks

Từ thư mục chứa Dockerfile:

~~~bash
REPO="aks-pull-demo"
TAG="1.0.0"

az acr build \
  --registry "$ACR_NAME" \
  --image "$REPO:$TAG" \
  .
~~~

Lệnh yêu cầu quyền phù hợp để gửi build lên ACR và sử dụng khả năng build được registry/tier hỗ trợ. Một số tổ chức dùng CI/CD build rồi push thay vì ACR Tasks; cả hai cần nguyên tắc bảo mật image và tag.

### 10.3. Xác minh image có trong registry

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "$REPO" \
  --output table
~~~

Với quyền phù hợp, có thể xem manifest/digest và metadata bằng cơ chế ACR/OCI đang hỗ trợ. Đừng dùng thành công của build làm bằng chứng Pod đã pull được.

Tạo image reference:

~~~bash
IMAGE="$LOGIN_SERVER/$REPO:$TAG"
printf "Deploy image: %s\n" "$IMAGE"
~~~

Kiểm tra **LOGIN_SERVER** có đúng với ACR đã cấp role và image **REPO:TAG** có mặt không. Nếu dùng ACR ở subscription khác, đừng lấy login server của registry này rồi gán quyền cho registry khác.

### 10.4. Vì sao không dùng latest trong production?

Tag **latest** không bảo đảm tính bất biến. Nếu pipeline push một image mới lên cùng tag, các node có cache khác nhau có thể dùng image khác nhau theo imagePullPolicy và thời điểm chạy.

Khuyến nghị:

- Dùng tag theo release hoặc commit SHA.
- Lưu **image digest**.
- Với workload quan trọng, triển khai **repository@sha256:digest** để cố định nội dung.
- Lưu SBOM, kết quả scan và nguồn build.
- Thiết lập quy trình cấm tự ý ghi đè tag production.
- Có chính sách retention/garbage collection để tránh xóa image đang cần rollback.

## 11. Bước E: cấu hình kubectl và kiểm tra cluster đích

### 11.1. Lấy credentials cho cluster lab

~~~bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"
~~~

Lệnh này cập nhật kubeconfig theo cơ chế CLI. Trước khi deploy, **kiểm tra context** để tránh gửi lệnh sang cluster production ngoài ý muốn:

~~~bash
kubectl config current-context

kubectl cluster-info

kubectl get nodes -o wide
~~~

Nếu nodes không Ready, phải xử lý tình trạng AKS trước khi chẩn đoán ACR pull. Một Deployment tạo thành công có thể chờ scheduling vì không có node capacity mà không liên quan đến registry.

### 11.2. Tạo namespace riêng cho lab

~~~bash
NS="acr-pull-lab"

kubectl create namespace "$NS"
~~~

Nếu namespace đã tồn tại, không xóa/tạo lại chỉ để chạy ví dụ. Có thể dùng namespace được tổ chức chỉ định thay vì tạo mới.

### 11.3. Kiểm tra quyền Kubernetes

Quyền Azure quản lý AKS (management plane) không đồng nghĩa quyền Kubernetes có thể tạo Deployment. Nếu cluster bật Kubernetes RBAC và Microsoft Entra integration, danh tính của người dùng cần quyền trên namespace tương ứng.

Lệnh kiểm tra quyền:

~~~bash
kubectl auth can-i create deployments -n "$NS"
kubectl auth can-i get pods -n "$NS"
~~~

Nếu không có quyền, phối hợp cluster admin để cấp Role/RoleBinding phù hợp; không xin **cluster-admin** toàn cluster chỉ để chạy một Deployment lab.

## 12. Bước F: triển khai Pod tham chiếu image ACR

### 12.1. Tạo Deployment trực tiếp bằng kubectl

~~~bash
kubectl create deployment aks-pull-demo \
  --namespace "$NS" \
  --image "$IMAGE" \
  --replicas 1
~~~

Ví dụ này không cần **imagePullSecret** khi kubelet identity đã được cấp quyền phù hợp và ACR/network đáp ứng điều kiện.

Xem rollout và Pod:

~~~bash
kubectl rollout status deployment/aks-pull-demo \
  --namespace "$NS" \
  --timeout=180s

kubectl get pods \
  --namespace "$NS" \
  -o wide
~~~

Nếu timeout, **đừng kết luận image pull sai ngay**. Cần xem events để phân biệt Pending do scheduler, ErrImagePull hay container CrashLoopBackOff.

### 12.2. Cùng Deployment dưới dạng YAML

Ví dụ manifest để quản lý qua GitOps/IaC. **Thay** IMAGE_PLACEHOLDER bằng tên image ACR đầy đủ trước khi apply:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aks-pull-demo
  namespace: acr-pull-lab
  labels:
    app: aks-pull-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aks-pull-demo
  template:
    metadata:
      labels:
        app: aks-pull-demo
    spec:
      containers:
        - name: web
          image: IMAGE_PLACEHOLDER
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 80
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 256Mi
~~~

**imagePullPolicy: Always** trong lab giúp kubelet kiểm tra registry khi khởi tạo container, kể cả khi node có cache. Điều này tiện kiểm tra quyền và network, nhưng không sửa sai role/DNS. Ở production, có thể chọn policy theo artifact digest và cách vận hành; pin digest mới là cách rõ ràng nhất để bảo đảm nội dung image bất biến.

Lưu manifest vào **deployment.yaml** khi thực hành, thay IMAGE_PLACEHOLDER bằng **$LOGIN_SERVER/aks-pull-demo:1.0.0** hoặc digest thật, rồi áp dụng:

~~~bash
kubectl apply -f deployment.yaml
~~~

Không chạy **kubectl apply** với placeholder chưa thay: Kubernetes sẽ cố pull image sai. Không đưa manifest chứa credential thực vào source control.

### 12.3. Phục vụ thử nội bộ bằng ClusterIP

~~~bash
kubectl expose deployment aks-pull-demo \
  --namespace "$NS" \
  --name aks-pull-demo \
  --port 80 \
  --target-port 80 \
  --type ClusterIP
~~~

Không cần tạo public LoadBalancer để chứng minh image pull; điều đó có thể phát sinh phí networking và mở thêm bề mặt truy cập.

Từ máy có kubeconfig/đường mạng phù hợp:

~~~bash
kubectl port-forward \
  --namespace "$NS" \
  service/aks-pull-demo 8080:80
~~~

Trong terminal khác:

~~~bash
curl --fail --show-error http://127.0.0.1:8080/
~~~

Nếu trả nội dung trang demo, Pod đã chạy và Service kết nối đúng. Nhưng để chứng minh cluster thực sự có quyền kéo image private, cần thêm **Pod events, image digest/imageID** và kiểm tra registry ở đúng cấu hình; một node đã cache image có thể che lỗi pull nếu policy không buộc kiểm tra.

### 12.4. Tách tình trạng image pull và tình trạng ứng dụng

| Tình trạng Pod | Ý nghĩa thường gặp | Ưu tiên xử lý |
|---|---|---|
| **Pending** | Chưa được schedule hoặc chờ điều kiện | Xem node capacity, taints, PVC, scheduler events |
| **ContainerCreating** | Đang chuẩn bị môi trường/container | Xem image pull, CNI, volume |
| **ErrImagePull** | Kubelet kéo image thất bại | Xem registry permission, image reference, network |
| **ImagePullBackOff** | Kubelet đang retry với backoff sau pull failure | Đọc Events để tìm lỗi gốc |
| **Running nhưng NotReady** | Process chạy nhưng readiness fail | Kiểm tra port, readiness probe, application logs |
| **CrashLoopBackOff** | Container đã khởi động nhưng crash/restart | Kiểm tra command, env, logs, resources |
| **Running + Ready** | Pod có thể phục vụ theo readiness | Tiếp tục smoke test và kiểm tra dependency |

## 13. Xác minh tích hợp AKS–ACR bằng công cụ chuyên dụng

### 13.1. az aks check-acr

Azure CLI cung cấp lệnh kiểm tra kết nối ACR trong bối cảnh AKS:

~~~bash
az aks check-acr \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --acr "$LOGIN_SERVER"
~~~

Lệnh có thể tạo tài nguyên kiểm tra trong cluster và cần quyền/điều kiện vận hành phù hợp. Nó hỗ trợ đánh giá khả năng node/cluster truy cập registry, xác thực hoặc network trong những phạm vi công cụ thực hiện.

**Kết quả PASS của công cụ này hữu ích, nhưng không thay thế kiểm tra Deployment với image thật**, nhất là registry dùng ABAC repository permissions, private networking, chính sách admission hoặc khác biệt image manifest.

Nếu chạy check-acr lỗi vì RBAC Kubernetes, node chưa Ready hoặc policy cấm tạo Pod thử nghiệm, cần xử lý điều kiện công cụ trước khi kết luận registry có sự cố.

### 13.2. Xem chi tiết Pod và Events

~~~bash
kubectl get pods -n "$NS" -o wide

kubectl describe deployment/aks-pull-demo -n "$NS"

kubectl get events \
  -n "$NS" \
  --sort-by=.lastTimestamp
~~~

Để xem đúng Pod đang lỗi:

~~~bash
kubectl get pods \
  -n "$NS" \
  -l app=aks-pull-demo
~~~

Sau khi lấy **POD_NAME** thực tế:

~~~bash
POD_NAME="<pod-name-from-kubectl-get>"

kubectl describe pod "$POD_NAME" -n "$NS"

kubectl get pod "$POD_NAME" \
  -n "$NS" \
  -o jsonpath='{.status.containerStatuses[*].imageID}'
~~~

Dữ liệu Events thường chứa thông báo như **failed to pull image**, **unauthorized**, **manifest unknown**, **dial tcp timeout** hoặc lỗi DNS. Tìm **lỗi gốc** trước khi liên tục sửa vai trò.

### 13.3. Xem logs đúng thời điểm

Nếu container đã chạy:

~~~bash
kubectl logs deployment/aks-pull-demo \
  -n "$NS" \
  --tail=100
~~~

Nếu image **chưa pull được**, container chưa chạy và **không có application logs** để đọc. Hãy ưu tiên **kubectl describe pod** và Events thay vì mất thời gian tìm log ứng dụng.

### 13.4. Kiểm tra image reference mà cluster đang dùng

~~~bash
kubectl get deployment aks-pull-demo \
  -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[*].image}'
~~~

Đối chiếu chính xác registry login server, repository và tag/digest. Một lỗi typo như **aks-pull-dmeo** có thể trả 404/manifest unknown dù quyền và mạng đều đúng.

## 14. ImagePullBackOff: quy trình phân tích theo lớp

**ImagePullBackOff là biểu hiện, không phải nguyên nhân gốc.** Phân tích theo thứ tự từ cấu hình image đến quyền và network.

~~~mermaid
flowchart TD
    A["Pod ImagePullBackOff"] --> B{"Image reference/tag có tồn tại?"}
    B -->|Không| C["Sửa registry/repository/tag/digest"]
    B -->|Có| D{"Registry auth/role đúng?"}
    D -->|Không| E["Kiểm tra kubelet identity, permission mode, role"]
    D -->|Có| F{"Node tới được ACR login và data endpoints?"}
    F -->|Không| G["Kiểm tra DNS, firewall, Private Link, route"]
    F -->|Có| H["Kiểm tra image manifest, OS/arch, policy, registry health"]
    H --> I["Tạo Pod mới / chờ backoff rồi xác minh"]
~~~

### 14.1. Bước 1: kiểm tra tên image và registry

Trước tiên:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "aks-pull-demo" \
  --output table
~~~

Kiểm tra:

- Registry login server trong Pod có đúng không.
- Repository có đúng chữ hoa/chữ thường và đường dẫn.
- Tag/digest thực sự được push.
- Manifest có tương thích OS/architecture của node.
- Image có bị xóa theo retention policy hoặc purge job không.

Image không tồn tại là lỗi **404/manifest unknown**; cấp quyền nhiều hơn không tạo ra manifest bị thiếu.

### 14.2. Bước 2: kiểm tra kubelet identity và quyền

~~~bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity" \
  --output json

az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --include-inherited \
  --output table
~~~

- Với registry **RBAC Registry Permissions**, xác nhận kubelet có **AcrPull** hoặc quyền tương đương được chấp nhận.
- Với registry **ABAC Repository Permissions**, xác nhận **Container Registry Repository Reader** và condition (nếu có) cho đúng repository.
- Nếu role mới tạo, cho phép thời gian propagation trước khi kết luận thất bại.
- Nếu cluster đã đổi identity hoặc được tạo lại, role có thể đang gán cho principal cũ.
- Nếu AKS dùng service principal thay managed identity, phải kiểm tra loại identity riêng.

### 14.3. Bước 3: kiểm tra mạng từ node tới ACR

Một lỗi dạng **i/o timeout**, **dial tcp**, **DNS lookup failure** hoặc TLS handshake có thể không liên quan tới RBAC.

Kiểm tra:

1. Node AKS có đường egress tới ACR login server trên **HTTPS/443** không?
2. ACR public network access/firewall có cho phép đường đi đó không?
3. ACR đã dùng private endpoint chưa, node resolve được IP private đúng không?
4. Tên miền và endpoint dữ liệu của ACR có được phân giải/đi qua firewall không?
5. NSG, UDR, Azure Firewall, NVA, proxy hoặc NAT có chặn lưu lượng không?
6. Cluster private/public và registry private/public có được kết nối bằng kiến trúc đúng không?

**Không mở public access hoặc firewall 0.0.0.0/0** chỉ để làm lỗi biến mất trong production. Chẩn đoán đúng đường đi rồi chỉ cho phép endpoint/traffic cần thiết.

### 14.4. Bước 4: kiểm tra chính sách và giới hạn

Khi role và network đều đúng, kiểm tra:

- AKS node OS/CPU architecture có hỗ trợ image đó không.
- Manifest list/OCI media type có tương thích runtime không.
- Kubernetes admission policy có chặn image registry/tag không.
- ACR có áp dụng image quarantine/signing/scan rules hoặc policy của tổ chức không.
- Registry và data endpoint có đang ở trạng thái dịch vụ phù hợp không.
- Cluster có quota, disk pressure, container runtime hoặc CNI errors không.
- Một policy bắt buộc pull bằng digest đã được ký có đang từ chối tag không.

Không dùng **kubectl delete pod** lặp đi lặp lại như phương án duy nhất. Deployment controller có thể tạo Pod mới nhưng nếu nguyên nhân gốc chưa được xử lý, lỗi vẫn tái diễn.

## 15. Private ACR, Private Endpoint và DNS

Một ACR public endpoint có thể phù hợp lab, nhưng production có thể yêu cầu image chỉ đi qua mạng riêng và giới hạn public network access.

### 15.1. Public ACR với AKS dùng egress được kiểm soát

Khi ACR dùng public endpoint, các node AKS phải có đường HTTPS tới registry. Nếu AKS nằm trong subnet private, luồng outbound có thể đi qua NAT Gateway, Azure Firewall hoặc đường egress được hỗ trợ.

Cần xem:

- Public network access và firewall rules của ACR.
- Egress source IP hoặc chính sách cho phép network access.
- DNS resolution của ACR login server và data endpoints.
- NSG/UDR/fqdn filtering rules.
- Có proxy/TLS inspection ảnh hưởng chứng chỉ hay không.
- Đường đi của các endpoint xác thực Entra/Azure liên quan khi lấy token.

**Không bảo đảm egress IP ổn định** của node nếu kiến trúc mạng không được thiết kế để giữ nó.

### 15.2. ACR Private Link

Để dùng **private endpoint** cho ACR:

- Kiểm tra **SKU** ACR và khả năng hỗ trợ Private Link theo bảng tính năng hiện hành; Private Endpoint thường yêu cầu tier phù hợp như **Premium**.
- Tạo private endpoint tới registry ở VNet/subnet thích hợp.
- Bảo đảm AKS node có route tới private IP, thông qua cùng VNet, VNet peering hoặc kết nối khác được hỗ trợ.
- Cấu hình **Private DNS Zone**, thường liên quan tới **privatelink.azurecr.io**, cùng các records được Azure tạo/khuyến nghị.
- Xem cả **login endpoint** và **data endpoints** cho image layers.
- Nếu vô hiệu hóa public network access, xác minh toàn bộ client pull/push/build còn đường riêng phù hợp.
- Kiểm tra network policies, UDR và firewall nếu route đi qua thiết bị kiểm tra.

~~~mermaid
flowchart LR
    NODE["AKS nodes/kubelet<br/>subnet AKS"] -->|"HTTPS trong VNet/peering"| PE["ACR Private Endpoint<br/>private IP"]
    PE --> ACR["ACR Premium<br/>private registry"]
    DNS["Private DNS Zone<br/>privatelink.azurecr.io"] -. "Tên registry → private IP" .-> NODE
    CI["CI/CD build/push"] -->|"Đường riêng phải được thiết kế"| PE
~~~

### 15.3. Private AKS và Private ACR không phải một khái niệm

- **Private AKS cluster** nói về private access đến Kubernetes **API server/control plane**.
- **Private ACR** nói về đường tới **registry** để push/pull image.
- Một AKS private cluster vẫn có thể pull public ACR nếu network policy/egress cho phép.
- Một AKS public cluster vẫn có thể pull private ACR khi nodes có đường mạng và DNS private đúng.

Đừng cấu hình private cluster rồi giả định toàn bộ traffic đến ACR tự đi qua Private Link.

### 15.4. Lỗi DNS thường gặp

Nếu ACR có private endpoint mà kubelet vẫn resolve login server sang địa chỉ public hoặc data endpoint không phân giải được:

1. Kiểm tra private DNS zone và VNet link.
2. Kiểm tra A-record/aliases liên quan được Azure tạo cho registry và data endpoints.
3. Kiểm tra custom DNS server và conditional forwarder.
4. Kiểm tra ACR region và geo-replication nếu có.
5. Test DNS từ **một môi trường mạng tương đương AKS node**, không chỉ từ laptop.
6. Kiểm tra HTTPS/443 và firewall sau khi DNS đúng.

**Không tự tạo A-record thủ công bừa bãi** nếu không hiểu lifecycle endpoint và cách Azure quản lý private DNS.

## 16. Cross-subscription, cross-tenant và multi-cluster

### 16.1. AKS và ACR ở hai resource group hoặc subscription

AKS ở **rg-aks-prod** và ACR ở **rg-platform-acr** có thể có role assignment phù hợp. Với hai subscription trong **cùng tenant**, dùng **ACR resource ID** làm scope khi attach hoặc gán quyền theo mô hình được hỗ trợ.

Người thao tác cần:

- Quyền đọc cấu hình cluster/identity.
- Quyền đọc ACR và phù hợp để tạo role assignment trên ACR scope.
- Quyền điều khiển AKS khi gọi update.
- Kết nối mạng giữa node và ACR.
- Quy trình phê duyệt giữa chủ sở hữu hai subscription.

Không giả định **Contributor ở AKS RG** đủ để tạo role assignment ở ACR subscription.

### 16.2. Cross-tenant

Nếu AKS và ACR thuộc **Microsoft Entra tenants khác nhau**, các cơ chế tích hợp managed identity/attach-acr có giới hạn và yêu cầu riêng. Không thực hiện theo hướng dẫn same-tenant một cách máy móc.

Khi cross-tenant là yêu cầu thực tế:

1. Xem tài liệu chính thức về hỗ trợ AKS–ACR cross-tenant cho phiên bản dịch vụ.
2. Xác định cơ chế auth được tổ chức chấp nhận: federated identity, service principal hoặc registry credential theo khả năng hỗ trợ.
3. Thiết kế rotation, secret storage và least privilege.
4. Kiểm tra registry network, tenant policies và role scope.
5. Thử image pull trong môi trường không production trước khi mở rộng.

Không dùng admin credentials dài hạn của ACR như giải pháp mặc định khi không hiểu trust boundary giữa tenants.

### 16.3. Nhiều AKS clusters dùng chung ACR

Có thể nhiều cluster cùng pull image từ một registry khi được cấp quyền. Tuy nhiên cần quản lý:

- Ai được push release vào registry?
- Cluster dev có thể pull image production không?
- Registry có repository-specific ABAC conditions không?
- Network từ các region/VNet đến ACR có ổn định không?
- Có cần geo-replication (tính năng/tier hỗ trợ) để tối ưu đường truy cập không?
- Nếu registry bị outage, nodes mới hoặc Pod cần pull lại có bị ảnh hưởng không?

Một registry trung tâm giúp chuẩn hóa image nhưng cũng là một dependency chung. Xem xét replication, backup/export chiến lược và image retention theo yêu cầu DR.

## 17. imagePullSecrets: khi nào dùng và khi nào không?

Kubernetes hỗ trợ **imagePullSecrets** để truyền registry credentials cho việc kéo private image. Cơ chế này hữu ích khi registry ngoài Azure, mô hình cross-tenant đặc biệt hoặc integration managed identity không khả dụng.

Ví dụ cấu trúc Pod nếu một Kubernetes Secret tên **regcred** đã được tạo an toàn:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: private-image-test
  namespace: acr-pull-lab
spec:
  imagePullSecrets:
    - name: regcred
  containers:
    - name: app
      image: example-registry.invalid/repo/app:1.0.0
~~~

**Đây là ví dụ cấu trúc, không phải manifest chạy ngay**: hostname **example-registry.invalid** là placeholder và Secret **regcred** phải tồn tại trong cùng namespace theo Kubernetes requirements.

### 17.1. Rủi ro của imagePullSecrets

- Secret có vòng đời, hết hạn hoặc bị rotate.
- Người có quyền đọc Secret trong namespace có thể tiếp cận credential nếu control không đủ chặt.
- Secret phải được quản lý cho nhiều namespace/service account theo chính sách.
- Credential có thể được cấp quá rộng, ví dụ admin account registry.
- Nếu Secret hết hạn, Pod mới sẽ lỗi dù Pod cũ đang chạy bình thường.

Với AKS + ACR ở cùng tenant và môi trường hỗ trợ, **kubelet managed identity + role pull** thường giảm gánh nặng quản lý password so với registry username/password.

### 17.2. Không đặt registry password trong Git

Không tạo imagePullSecret bằng username/password thật rồi commit YAML Secret dạng Base64 và tưởng rằng đã mã hóa an toàn. **Base64 là encoding, không phải encryption**.

Nếu bắt buộc dùng secret credentials, cần secret management/rotation, RBAC, encryption at rest theo cluster config và quy trình CI/CD an toàn. Không cho quyền đọc secret rộng toàn cluster.

## 18. Cập nhật image, rollout và rollback

### 18.1. Build một version mới

Ví dụ image version **1.0.1** được pipeline build/push:

~~~bash
az acr build \
  --registry "$ACR_NAME" \
  --image "aks-pull-demo:1.0.1" \
  .
~~~

Trong cluster, cập nhật Deployment:

~~~bash
kubectl set image \
  deployment/aks-pull-demo \
  web="$LOGIN_SERVER/aks-pull-demo:1.0.1" \
  -n "$NS"

kubectl rollout status \
  deployment/aks-pull-demo \
  -n "$NS" \
  --timeout=180s
~~~

Nhớ rằng **web** là tên container trong Deployment **manifest YAML ví dụ**; nếu bạn dùng lệnh **kubectl create deployment** trước đó, tên container có thể khác. Xác minh **.spec.template.spec.containers[].name** trước khi gọi **kubectl set image**:

~~~bash
kubectl get deployment aks-pull-demo \
  -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[*].name}'
~~~

Không dùng lệnh set image với tên container tự đoán.

### 18.2. Rollback

Nếu release mới pull image được nhưng readiness/application lỗi, có thể quay về revision trước khi Deployment còn giữ rollout history:

~~~bash
kubectl rollout history \
  deployment/aks-pull-demo \
  -n "$NS"

kubectl rollout undo \
  deployment/aks-pull-demo \
  -n "$NS"

kubectl rollout status \
  deployment/aks-pull-demo \
  -n "$NS" \
  --timeout=180s
~~~

Rollback workload **không tự rollback database schema hoặc dữ liệu**. Nếu image cũ bị purge khỏi ACR, node mới có thể không pull lại được; do đó image retention là một phần của khả năng rollback.

### 18.3. Vì sao chọn image digest?

Tag có thể được ghi đè, nên deploy bằng image digest giúp xác định đúng artifact đã được kiểm thử:

~~~text
image: acrordersdemo123.azurecr.io/orders-api@sha256:<digest-da-xac-minh>
~~~

Tất cả môi trường nên tham chiếu cùng artifact/digest khi quy trình yêu cầu “build once, deploy many”. Pipeline cần lưu digest sau push và dùng nó trong Deployment/GitOps manifests.

Không dùng digest minh họa chưa tồn tại; hãy lấy giá trị thực từ registry metadata bằng công cụ được phê duyệt.

## 19. CI/CD và bảo vệ chuỗi cung ứng image

Một pipeline production thường có:

~~~mermaid
flowchart LR
    GIT["Git commit"] --> BUILD["Build/test"]
    BUILD --> SCAN["SCA/CVE/SBOM và policy"]
    SCAN --> PUSH["Push versioned image vào ACR"]
    PUSH --> DIGEST["Ghi nhận digest"]
    DIGEST --> MANIFEST["Cập nhật Deployment/GitOps manifest"]
    MANIFEST --> AKS["AKS rolling rollout"]
    AKS --> HEALTH["Readiness/smoke test"]
    HEALTH --> OBS["Logs, metrics, alerts"]
~~~

### 19.1. Phân tách ba quyền

1. **CI/CD build/push:** chỉ được push repository/phạm vi cần thiết.
2. **AKS kubelet pull:** chỉ được đọc image cần deploy theo permission mode phù hợp.
3. **Ứng dụng runtime:** nhận quyền data plane theo service account/workload identity; không cần quyền push registry.

Việc phân chia hạn chế rủi ro supply-chain: một Pod bị xâm nhập không nên có khả năng tự thay image production trong registry.

### 19.2. Nội dung image và chính sách bảo mật

- Base image từ nguồn có độ tin cậy và được cập nhật bản vá.
- Quét vulnerability và kiểm tra thành phần phụ thuộc.
- Dùng tag bất biến/digest; tránh **latest** cho production.
- Không đưa password, token, SSH key hoặc connection string vào Dockerfile/image layer.
- Sử dụng admission policy để giới hạn registries được phép và image digest/signature nếu yêu cầu.
- Kiểm tra khả năng tương thích CPU architecture với node pool (amd64/arm64).
- Có quy trình thu hồi image bị lỗi hoặc chứa CVE nghiêm trọng.
- Giữ đủ image versions cho rollback theo chính sách retention.

### 19.3. ACR Tasks và AKS là hai nguồn tính phí khác nhau

Build image bằng **az acr build** có thể dùng năng lực build/Tasks của registry; triển khai lên AKS sử dụng tài nguyên node của cluster. Đừng suy luận image build trong ACR nghĩa là đã chạy ứng dụng, hoặc build pipeline thành công nghĩa là Node/Kubelet đã kéo image.

## 20. Monitoring và chi phí

### 20.1. Monitor điều gì?

| Nguồn | Tín hiệu | Ý nghĩa |
|---|---|---|
| AKS/Kubernetes Events | Pulling, Pulled, Failed, BackOff | Phân biệt pull success và lý do failure |
| Pod status | ContainerCreating, ImagePullBackOff, Ready | Pod đã khởi động được chưa |
| Deployment rollout | Available/Unavailable replicas | Release có đạt desired state không |
| ACR metrics/diagnostics | Authentication, requests, pull/push hoạt động theo log có hỗ trợ | Phát hiện tải/lỗi registry |
| Azure Activity Log | Role assignment, registry/network config, AKS update | Audit thay đổi control plane |
| Azure Monitor/Container Insights | Node, container CPU/memory, logs | Theo dõi runtime sau pull |
| CI/CD pipeline logs | Build/push/digest/deploy version | Truy vết image source |
| Cost Management | ACR, AKS nodes, networking, logs | Kiểm soát tổng chi phí |

Không mặc định registry audit/diagnostic logs đã bật. Cần cấu hình diagnostic settings và retention phù hợp, đồng thời loại bỏ secret/PII trước khi lưu logs.

### 20.2. Các dòng chi phí thường gặp

| Thành phần | Có thể phát sinh chi phí |
|---|---|
| ACR SKU | Registry tier và các khả năng được cấp theo gói |
| ACR Storage | Dung lượng image layers/manifests và artifact lưu |
| ACR Tasks/Build | Tính năng build/automation theo bảng giá và quota |
| ACR geo-replication / Private Link | Tính năng tier, region replica và lưu lượng/private networking liên quan |
| AKS nodes | VM compute, managed disks, node pool và quota |
| AKS management tier | Phí theo loại gói/tier hoặc chính sách dịch vụ |
| Load Balancer/NAT Gateway/Firewall | Dịch vụ mạng và lưu lượng theo cấu hình |
| Log Analytics/Monitor | Ingestion, retention, alerts |
| Egress giữa region/Internet | Phí mạng khi áp dụng |

**Attach ACR không làm image pull miễn phí trong mọi tình huống.** Quá trình vận hành registry, storage, compute nodes, logging hoặc network vẫn có thể phát sinh phí.

Nếu AKS và ACR ở hai region, tính độ trễ/pull time và phí truyền dữ liệu theo hướng và cấu hình. Với cluster lớn, image size và số lần node scale-out có thể ảnh hưởng đáng kể tới băng thông.

### 20.3. Theo dõi trong Azure Cost Management

1. Chọn đúng subscription/resource group hoặc các scope billing của tổ chức.
2. Nhóm theo service/resource/meter để tách registry, AKS compute, storage và networking.
3. Đối chiếu với lịch build/push, node scale-out, rollout và image pull.
4. Kiểm tra các registry replicas, private endpoints và dịch vụ mạng có còn cần thiết không.
5. Áp dụng tag owner/environment/costCenter ở những resource hỗ trợ.
6. Đặt budget/alerts và rà soát định kỳ.

Dữ liệu Cost Management có thể chậm cập nhật; không kết luận giá bằng 0 ngay sau khi xóa Pod hoặc registry resource.

## 21. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| **ErrImagePull / ImagePullBackOff** | Quyền, image reference hoặc network lỗi | kubectl describe pod, Events |
| **401 Unauthorized** | Kubelet không có token/quyền, auth không đúng | Xem kubelet identity và role đúng permission mode |
| **403 Forbidden** | Principal được xác thực nhưng bị deny bởi RBAC/ABAC hoặc registry network policy | Kiểm tra role, condition, firewall và network access |
| **404 Manifest unknown** | Repo/tag/digest sai hoặc artifact đã bị xóa | az acr repository show-tags, kiểm tra exact reference |
| **i/o timeout / dial tcp** | Node không tới được registry/data endpoint | Kiểm tra DNS, NSG, firewall, UDR, NAT, Private Link |
| **x509 certificate error** | TLS interception/proxy/certificate chain hoặc endpoint sai | Kiểm tra cert, proxy, DNS, network path |
| **No matching manifest** | Image không hỗ trợ OS/CPU architecture của node | Kiểm tra platform image và node architecture |
| **Role assignment tồn tại nhưng Pod vẫn lỗi** | Role chưa propagate, principal cũ, ABAC mode, network | Chờ propagation, xác minh object ID/mode/Events |
| **az aks --attach-acr lỗi** | Quyền tạo role assignment thiếu, ACR ABAC mode hoặc scope/tenant sai | Đọc lỗi cụ thể và chọn nhánh tích hợp đúng |
| **kubectl get pods: Forbidden** | Thiếu Kubernetes RBAC, không phải ACR permission | Kiểm tra context, RoleBinding và cluster auth |
| **Pod Pending** | Node resource/taints/PVC/quotas | kubectl describe pod, scheduler events |
| **CrashLoopBackOff** | Image pull đã thành công nhưng app crash | kubectl logs, command, config, memory |
| **Running nhưng NotReady** | Readiness probe sai hoặc app chưa sẵn sàng | Kiểm tra probe/path/port/dependencies |
| **Pod mới lỗi, Pod cũ vẫn chạy** | Cached image, registry role/network vừa đổi, tag bị xóa | Kiểm tra pullPolicy, tag/digest và identity hiện hành |
| **Dọn ACR tag làm rollback lỗi** | Image version cũ bị purge | Giữ image retention theo release/rollback policy |

### 21.1. Quy trình điều tra tiêu chuẩn

1. Lấy **namespace, Deployment, Pod, node, image reference và thời điểm lỗi**.
2. Xem **Pod Events** để biết HTTP status hoặc loại network error.
3. Xác nhận repository/tag/digest tồn tại trong ACR.
4. Đọc **AKS kubelet identity** (không nhầm control plane identity).
5. Xác định ACR **RBAC registry** hay **ABAC repository**.
6. Kiểm tra role/condition và scope; chờ propagation nếu mới cấp.
7. Xác nhận node có đường **DNS/HTTPS tới ACR login và data endpoints**.
8. Dùng **az aks check-acr** khi công cụ phù hợp.
9. Tạo Pod thử trong lab với image chính xác và theo dõi rollout.
10. Khi pull đã thành công, chuyển sang debug process/startup/readiness nếu Pod chưa Ready.

Không điều tra bằng cách cấp Owner cho node hoặc vô hiệu hóa ACR firewall ở production mà không có thay đổi được phê duyệt.

## 22. Dọn dẹp lab và thu hồi quyền

Sau khi đã xác nhận kết quả và lưu log cần thiết:

### 22.1. Xóa workload Kubernetes trong namespace lab

~~~bash
kubectl delete deployment aks-pull-demo \
  -n "$NS"

kubectl delete service aks-pull-demo \
  -n "$NS"
~~~

Nếu namespace **acr-pull-lab** chỉ được tạo cho bài thực hành và không chứa tài nguyên khác:

~~~bash
kubectl delete namespace "$NS"
~~~

Không xóa namespace production hoặc xóa namespace khi không rõ tài nguyên bên trong.

### 22.2. Thu hồi AcrPull có kiểm soát

Nếu một role **AcrPull** được gán riêng để thử nghiệm và không còn workload sử dụng, chủ sở hữu IAM có thể xem role assignment và thu hồi theo quy trình. Ví dụ **chỉ cho ACR RBAC Registry Permissions**:

~~~bash
az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --output table
~~~

Không xóa role assignment chỉ vì vừa hoàn thành lab nếu kubelet identity đó còn cần ACR cho workload khác. Nếu gán bằng **attach-acr**, có thể dùng **az aks update --detach-acr** theo khả năng hỗ trợ khi owner xác nhận và đã kiểm tra mọi dependency.

### 22.3. Dọn các tài nguyên Azure

- **ACR:** xóa chỉ khi registry tạo riêng cho lab, không chứa image/repository dùng chung.
- **AKS cluster:** xóa chỉ nếu là cluster lab được chủ sở hữu phê duyệt, đã xuất logs hoặc dữ liệu cần giữ.
- **Resource group:** không xóa hàng loạt nếu chứa tài nguyên khác.
- **Private endpoints, DNS, NAT, Log Analytics:** xem chi phí và các dependency trước khi xóa.
- **Role assignments:** thu hồi riêng theo phạm vi, không ảnh hưởng các ứng dụng khác.

Với mục tiêu học tích hợp ACR, không cần xóa AKS cluster đang dùng chung chỉ vì đã xóa Deployment.

## 23. Checklist trước production

- [ ] ACR và AKS được chọn đúng subscription, region, tenant và owner.
- [ ] Image có tên đầy đủ **loginServer/repository:tag** hoặc digest thật.
- [ ] Repository/tag đã tồn tại, image hỗ trợ OS/architecture node.
- [ ] Kubelet identity được xác định đúng object ID; không nhầm control plane/workload identity.
- [ ] Permission mode của ACR đã được kiểm tra: RBAC Registry hay ABAC Repository.
- [ ] Role pull đúng mô hình, đúng principal, đúng scope; dùng ABAC condition nếu yêu cầu giới hạn repository.
- [ ] CI/CD push identity không dùng chung quyền quản lý/pull với kubelet nếu không cần.
- [ ] Không bật ACR admin user hoặc lưu registry password trong manifests cho trường hợp managed identity đã hỗ trợ.
- [ ] Node có đường HTTPS/443 tới registry login và data endpoints.
- [ ] Nếu dùng Private Endpoint, đã kiểm tra Private DNS Zone, VNet link, UDR/firewall và data endpoint.
- [ ] Cùng tenant/cross-subscription/cross-tenant được thiết kế theo khả năng hỗ trợ.
- [ ] AKS nodes Ready, Kubernetes RBAC cho người deploy đúng namespace.
- [ ] Deployment pull thành công từ registry private, Pods Ready và smoke tests đạt.
- [ ] Có cơ chế ghi image digest, scan CVE, SBOM và provenance theo chính sách.
- [ ] Rollout/rollback được thử; image retention giữ những release cần thiết.
- [ ] Log, Events, alert và audit IAM/network thay đổi đã được cấu hình.
- [ ] Chi phí registry/AKS nodes/build/network/monitoring được theo dõi.
- [ ] Có runbook khi image pull thất bại và khi registry/network ngừng hoạt động.
- [ ] Có chủ sở hữu cho role assignments, secrets và lịch rà soát quyền.

## 24. Bài tập thực hành

### Bài 1: Phân biệt danh tính

AKS có control plane managed identity, kubelet identity và một Pod dùng Microsoft Entra Workload ID để đọc Blob Storage.

Hãy trả lời:

1. Danh tính nào thường dùng để pull image private từ ACR?
2. Danh tính nào dùng để gọi Azure Storage bên trong Pod?
3. Vì sao cấp **AcrPull** cho control plane identity chưa chắc đủ?
4. Khi Pod chưa pull được image, workload identity có thể tự sửa lỗi đó không?

### Bài 2: Triển khai end-to-end

Trong môi trường lab được phê duyệt:

1. Tạo/đọc ACR và lấy login server/resource ID.
2. Xác định ACR permission mode.
3. Đọc kubelet identity của AKS.
4. Dùng **attach-acr** nếu registry là RBAC Registry Permissions hoặc cấp role phù hợp nếu ABAC.
5. Build/push image Nginx demo lên ACR.
6. Tạo Deployment tham chiếu image private.
7. Xem Events, imageID và rollout.
8. Port-forward Service và đọc trang web.
9. Dọn Deployment/Service mà không xóa nhầm registry dùng chung.

### Bài 3: Chẩn đoán ImagePullBackOff

Một Pod có image:

~~~text
acrordersdemo123.azurecr.io/orders-api:2.4.1
~~~

Events báo **unauthorized**. Người vận hành vừa cấp role Contributor trên resource group AKS cho danh tính của Pod, nhưng lỗi không thay đổi. Hãy mô tả từng bước kiểm tra: kubelet identity, ACR scope, permission mode, role assignment, propagation, registry network.

### Bài 4: Chuyển registry sang ABAC mode

Một tổ chức bật **RBAC Registry + ABAC Repository Permissions** để chỉ cho phép cluster Orders pull repository **orders/**. Trước đó họ dùng **az aks update --attach-acr**.

Hãy giải thích tại sao cần đánh giá lại quyền pull và đề xuất cấu hình **Container Registry Repository Reader** với điều kiện repository phù hợp thay vì giữ nguyên giả định AcrPull.

### Bài 5: Private ACR không pull được

Registry có Private Endpoint, public access đã tắt, role đúng, nhưng kubelet báo **dial tcp: i/o timeout**. Hãy vẽ đường:

~~~text
AKS node → DNS → private IP ACR → login/data endpoints
~~~

Nêu cách xác minh VNet peering, private DNS zone, subnet delegation/routing, firewall và các endpoint cần thiết. Vì sao chạy **docker pull** thành công trên laptop nằm ngoài VNet không chứng minh node có đường pull?

### Bài 6: CI/CD và rollback

Pipeline deploy image **orders-api:3.0.0** vào AKS, sau đó cần rollback **2.9.0**:

1. Quyền push và pull nên phân chia thế nào?
2. Vì sao không nên ghi đè tag **latest**?
3. Cần giữ digest/manifest nào để rollback?
4. Làm sao xem **kubectl rollout history/undo**?
5. Nếu tag 2.9.0 đã bị purge khỏi ACR thì chuyện gì xảy ra khi scale-out?
6. Vì sao rollback image không tự rollback database?

### Câu hỏi tự kiểm tra

1. **az aks --attach-acr** cấp quyền gì và thường gắn với identity nào?
2. Quyền kéo image khác quyền ứng dụng đọc Azure Storage như thế nào?
3. Vai trò của **AcrPull** trong ACR RBAC Registry Permissions là gì?
4. Khi nào cần **Container Registry Repository Reader** thay vì AcrPull?
5. Tại sao attach-acr không giải quyết được mọi trường hợp registry ABAC?
6. Kubernetes imagePullSecrets có rủi ro gì nếu dùng registry admin password?
7. ImagePullBackOff có luôn là lỗi RBAC không?
8. Khi nào kubectl logs không giúp chẩn đoán image pull?
9. Vì sao có ACR Private Endpoint nhưng vẫn cần kiểm tra DNS và data endpoints?
10. Khi nào nên dùng image digest thay vì mutable tag?
11. Kubernetes namespace có tự hạn chế kubelet pull repository theo tên namespace không?
12. Lệnh **az aks check-acr** khác kiểm thử Pod với image thật ở điểm nào?
13. Vì sao dừng Pod hoặc xóa Deployment không làm chi phí AKS nodes/ACR bằng 0?
14. Nếu cluster có nhiều node và chỉ node mới pull lỗi, phải kiểm tra điều gì?

## 25. Tài liệu tham khảo

- [Authenticate with Azure Container Registry from AKS — Microsoft Learn](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration)
- [Azure Container Registry authentication overview](https://learn.microsoft.com/azure/container-registry/container-registry-authentication)
- [Azure Container Registry repository permissions and ABAC](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [Azure Container Registry roles and permissions](https://learn.microsoft.com/azure/container-registry/container-registry-roles)
- [Azure Container Registry Private Link](https://learn.microsoft.com/azure/container-registry/container-registry-private-link)
- [ACR networking best practices](https://learn.microsoft.com/azure/container-registry/container-registry-firewall-access-rules)
- [Azure CLI: az aks](https://learn.microsoft.com/cli/azure/aks)
- [Azure CLI: az acr](https://learn.microsoft.com/cli/azure/acr)
- [Kubernetes images](https://kubernetes.io/docs/concepts/containers/images/)
- [Kubernetes debugging Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)
- [Azure Container Registry pricing](https://azure.microsoft.com/pricing/details/container-registry/)
- [Azure Kubernetes Service pricing](https://azure.microsoft.com/pricing/details/kubernetes-service/)

