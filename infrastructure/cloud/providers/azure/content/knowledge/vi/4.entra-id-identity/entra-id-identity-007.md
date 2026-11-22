# Workload identity federation cho ứng dụng và pipeline

Khi triển khai ứng dụng trên Microsoft Azure, ứng dụng và pipeline CI/CD thường phải gọi Azure Resource Manager, Key Vault, Storage hoặc dịch vụ dữ liệu. Để thực hiện các tác vụ này, chúng cần một danh tính và quyền truy cập. Một cách triển khai cũ là tạo client secret cho service principal, lưu secret trong hệ thống CI/CD rồi dùng nó để đăng nhập. Cách này phát sinh việc lưu trữ, phân phối, xoay vòng và thu hồi bí mật.

**Workload identity federation (WIF)** cho phép Microsoft Entra ID tin cậy một nhà phát hành token bên ngoài (identity provider, IdP), nhận một token OIDC hợp lệ từ workload và đổi token đó lấy access token của Microsoft Entra ID. Nhờ vậy, ứng dụng hoặc pipeline có thể truy cập tài nguyên Azure mà không phải lưu client secret dài hạn cho danh tính Azure.

Trong mô-đun CLOUD_PROVIDERS_AZURE, bài học này kết nối phần Microsoft Entra ID với triển khai tự động, quản trị subscription/resource group, phân quyền Azure RBAC và truy cập an toàn vào các dịch vụ lưu trữ, tính toán hoặc dữ liệu trên Azure.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

1. Giải thích workload identity là gì và cơ chế federation dựa trên OpenID Connect (OIDC) hoạt động thế nào.
2. Phân biệt application registration, service principal, managed identity và federated identity credential.
3. Hiểu vai trò của issuer, subject, audience và cách Microsoft Entra ID đối chiếu các giá trị này khi nhận token.
4. Cấu hình luồng đăng nhập không dùng client secret cho GitHub Actions, hiểu cách thực hiện tương ứng trong Azure DevOps và AKS.
5. Cấp quyền Azure theo nguyên tắc đặc quyền tối thiểu, xử lý lỗi phổ biến và xác định rủi ro bảo mật.

Bạn nên nắm những khái niệm cơ bản về Microsoft Entra tenant, Azure subscription, resource group, Azure RBAC, Azure CLI và CI/CD. Các ví dụ CLI giả định tài khoản quản trị đang thao tác được phép tạo danh tính hoặc role assignment. Không yêu cầu tạo tài nguyên trả phí để hiểu lý thuyết.

## 2. Vì sao workload cần một danh tính riêng?

Workload là chương trình hoặc quy trình tự động cần gọi dịch vụ khác: API backend, công việc chạy theo lịch, container trên Kubernetes, job trong pipeline, hoặc script triển khai hạ tầng.

Ví dụ, một pipeline triển khai ứng dụng orders phải:

- Đọc cấu hình deployment và kết nối tới Azure.
- Tạo hoặc cập nhật App Service, Storage Account hay các tài nguyên trong một resource group.
- Đôi khi lấy thông tin từ Key Vault hoặc đẩy artifact vào một dịch vụ Azure.
- Ghi nhận trạng thái triển khai và kết thúc phiên làm việc.

Nếu pipeline sử dụng tên người dùng và mật khẩu cá nhân, tài khoản có thể bị khóa, thay đổi mật khẩu hoặc nghỉ việc. Nếu dùng client secret dài hạn của service principal, nhóm phải quản lý bí mật đó trong từng hệ thống CI/CD và xử lý nguy cơ lộ secret.

WIF giải quyết phần xác thực bằng việc dựa trên mối quan hệ tin cậy giữa Microsoft Entra ID và IdP của workload. Token OIDC do IdP cấp có thời hạn ngắn và được trao đổi với Entra ID; pipeline không cần nhận trước một mật khẩu hoặc client secret Azure. Tuy vậy, WIF **không tự cấp quyền truy cập**: danh tính liên kết vẫn cần được cấp đúng Azure RBAC role hoặc quyền ở dịch vụ đích.

## 3. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa trong bài học |
|---|---|
| Workload identity | Danh tính của ứng dụng, pod, job hoặc quy trình tự động, thay vì một người dùng tương tác |
| OpenID Connect (OIDC) | Giao thức danh tính xây dựng trên OAuth 2.0; IdP có thể phát hành token chứa các claim mô tả chủ thể và ngữ cảnh |
| Identity provider (IdP) | Bên phát hành OIDC token, ví dụ GitHub Actions hoặc OIDC issuer của cụm Kubernetes |
| Microsoft Entra application | Đối tượng đăng ký ứng dụng trong Entra tenant, có application (client) ID |
| Service principal | Danh tính ứng dụng trong tenant, thường là đối tượng được gán quyền Azure RBAC |
| User-assigned managed identity | Danh tính do Azure quản lý có vòng đời độc lập với tài nguyên sử dụng nó; một số kịch bản hỗ trợ cấu hình federated credentials trên danh tính này |
| Federated identity credential (FIC) | Cấu hình tin cậy trên ứng dụng Entra hoặc user-assigned managed identity, xác định issuer, subject và audience được chấp nhận |
| Access token của Microsoft Entra | Token được cấp sau khi trao đổi thành công, dùng để gọi Azure Resource Manager hoặc API đích |
| Azure RBAC | Cơ chế kiểm soát quyền đối với tài nguyên Azure, độc lập với việc xác thực qua federation |

Một application registration và service principal có liên quan nhưng không phải cùng đối tượng. Application (client) ID dùng để chỉ ứng dụng cần đăng nhập; service principal là đại diện của ứng dụng trong tenant và thường được gán role. Đừng nhầm client ID với object ID của service principal khi cấp quyền.

**Managed identity** là lựa chọn tự nhiên cho workload chạy trên các dịch vụ Azure có hỗ trợ. System-assigned managed identity gắn vòng đời với tài nguyên; user-assigned managed identity có thể được sử dụng lại theo thiết kế. Trong môi trường như AKS Workload Identity, Kubernetes service account có thể liên kết với user-assigned managed identity thông qua federation. Nếu ứng dụng chạy trên một dịch vụ Azure đã hỗ trợ truy cập managed identity trực tiếp, thường không cần tự cấu hình federation bên ngoài.

## 4. Cơ chế hoạt động của workload identity federation

Luồng điển hình từ GitHub Actions hoặc Kubernetes đến Azure gồm các bước:

1. **Đăng ký tin cậy:** quản trị viên tạo app registration hoặc user-assigned managed identity, rồi thêm federated identity credential mô tả IdP và workload được phép đăng nhập.
2. **Workload bắt đầu:** pipeline chạy một job hoặc pod được khởi tạo trong môi trường có hỗ trợ phát hành OIDC token.
3. **Nhận token từ IdP:** job hoặc pod nhận một token có chữ ký và các claim, ví dụ issuer, subject và audience.
4. **Đổi token:** workload gửi token do IdP cấp đến endpoint token của Microsoft Entra ID và chỉ rõ client ID của danh tính đích.
5. **Entra kiểm tra:** Entra xác minh token và đối chiếu với federated identity credential. Khi phù hợp, Entra cấp access token cho tài nguyên/API đích.
6. **Gọi dịch vụ Azure:** workload sử dụng access token để truy cập dịch vụ. Azure RBAC và quyền dữ liệu của dịch vụ tiếp tục quyết định thao tác nào được phép.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant W as Ứng dụng / Pipeline
    participant I as OIDC Identity Provider
    participant E as Microsoft Entra ID
    participant A as API hoặc tài nguyên Azure
    W->>I: Yêu cầu OIDC token theo ngữ cảnh workload
    I-->>W: JWT có iss, sub, aud và chữ ký
    W->>E: Đổi assertion OIDC lấy access token
    E->>E: Kiểm tra token và FIC
    E-->>W: Access token Entra ID
    W->>A: Gọi API với access token
    A->>A: Kiểm tra quyền được cấp
    A-->>W: Kết quả hoặc lỗi phân quyền
~~~

### Issuer, subject và audience

Ba trường quan trọng trong cấu hình FIC là:

- **Issuer (iss):** URL định danh bên cấp OIDC token. Ví dụ với GitHub Actions là https://token.actions.githubusercontent.com.
- **Subject (sub):** định danh ngữ cảnh workload mà Entra cho phép. Với GitHub Actions, subject có thể chứa tổ chức, repository và nhánh hoặc GitHub Environment; với Kubernetes, subject có thể chỉ một service account trong namespace.
- **Audience (aud):** đối tượng nhận token mà IdP khai báo. Với các cấu hình trao đổi token Azure phổ biến, giá trị được dùng là api://AzureADTokenExchange.

Ví dụ cho một workflow chạy từ nhánh main:

~~~json
{
  "name": "github-orders-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:EXAMPLE_ORG/orders-api:ref:refs/heads/main",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
~~~

Ở chế độ FIC thông thường, các giá trị issuer, subject và audience phải khớp với token thực tế theo quy tắc đối chiếu được Entra hỗ trợ. Khác biệt nhỏ như chữ hoa/chữ thường, tên nhánh, dấu gạch chéo cuối URL hoặc việc dùng GitHub Environment có thể khiến đăng nhập thất bại. Không nên tự đoán subject; hãy lấy theo tài liệu và giá trị token/thuộc tính chính thức của IdP. Những tính năng khớp subject linh hoạt, nếu được hỗ trợ trong môi trường cụ thể, phải được đánh giá phạm vi tin cậy riêng.

**Điểm phân biệt:** token OIDC ban đầu chứng minh danh tính workload trước Entra. Nó không mặc nhiên là access token để gọi Azure Resource Manager. Access token Entra được cấp sau khi trao đổi thành công và có đối tượng nhận cùng quyền hạn riêng.

## 5. Lựa chọn loại danh tính cho từng kịch bản

| Kịch bản | Danh tính Azure thường phù hợp | Nơi cấp OIDC token |
|---|---|---|
| GitHub Actions triển khai hạ tầng | Entra app + service principal + FIC | GitHub Actions OIDC provider |
| Azure DevOps pipeline | Danh tính của Azure Resource Manager service connection hỗ trợ WIF | Azure DevOps OIDC issuer theo service connection |
| Pod trong Azure Kubernetes Service | User-assigned managed identity + FIC liên kết service account | AKS OIDC issuer |
| Ứng dụng chạy trên App Service/VM hỗ trợ managed identity | System-assigned hoặc user-assigned managed identity trực tiếp | Azure managed identity endpoint; thường không cần FIC |
| Workload trong hệ thống CI hoặc Kubernetes ngoài Azure | Entra app hoặc user-assigned managed identity, khi kịch bản và IdP được hỗ trợ | OIDC issuer đáng tin cậy của hệ thống ngoài |

Sự khác nhau không nằm ở “Azure hay ngoài Azure” đơn thuần; điều quan trọng là IdP có phát hành token phù hợp, danh tính đích có hỗ trợ FIC cho kịch bản đó, và SDK hoặc công cụ có thể thực hiện token exchange.

## 6. Thực hành: GitHub Actions dùng OIDC đăng nhập Azure

Giả sử repository EXAMPLE_ORG/orders-api triển khai vào resource group rg-orders-dev trong subscription dành cho phát triển. Ta muốn chỉ workflow chạy từ nhánh main có thể dùng danh tính triển khai.

### 6.1. Chuẩn bị thông tin và điều kiện

Cần có:

- Quyền tạo app registration hoặc service principal trong tenant (hoặc một danh tính có sẵn do quản trị viên cấp).
- Quyền tạo role assignment tại phạm vi dự định triển khai.
- Quyền quản lý GitHub repository và cấu hình workflow.
- Azure CLI đã đăng nhập vào đúng tenant, subscription.
- Resource group đích đã tồn tại, ví dụ rg-orders-dev.

Kiểm tra Azure CLI:

~~~bash
az account show --output table
~~~

Để tránh sai môi trường, có thể chọn subscription rõ ràng trước khi cấu hình:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### 6.2. Tạo ứng dụng Entra và service principal

Ví dụ dưới đây dùng Bash trong terminal đã cài Azure CLI. Thay toàn bộ giá trị có dấu ngoặc nhọn hoặc dấu < > bằng thông tin thật:

~~~bash
APP_ID="$(az ad app create --display-name 'app-orders-deploy-dev' --query appId --output tsv)"
az ad sp create --id "$APP_ID" --output none
SP_OBJECT_ID="$(az ad sp show --id "$APP_ID" --query id --output tsv)"
echo "Application client ID: $APP_ID"
echo "Service principal object ID: $SP_OBJECT_ID"
~~~

APP_ID là application (client) ID sẽ được workflow dùng để đăng nhập. SP_OBJECT_ID là object ID của service principal sẽ được gán Azure RBAC role. Không tạo client secret hoặc certificate nếu chỉ triển khai theo phương thức federation này.

Nếu tổ chức đã có app registration dành cho deployment, có thể sử dụng lại theo chính sách của tổ chức thay vì tự tạo danh tính mới. Nên tách danh tính giữa development và production khi phạm vi quyền hoặc quy trình phê duyệt khác nhau.

### 6.3. Khai báo federated identity credential

Tạo tệp cấu hình JSON ở máy quản trị với nội dung sau:

~~~json
{
  "name": "github-orders-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:EXAMPLE_ORG/orders-api:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "OIDC trust for the main branch deployment workflow"
}
~~~

Giả sử lưu là github-main-fic.json, đăng ký FIC cho app:

~~~bash
az ad app federated-credential create --id "$APP_ID" --parameters @github-main-fic.json
~~~

Đọc lại cấu hình:

~~~bash
az ad app federated-credential list --id "$APP_ID" --output json
~~~

Trong GitHub Actions, subject của token thay đổi theo loại ngữ cảnh. Ví dụ khi workflow dùng GitHub Environment tên production, subject thường có dạng:

~~~text
repo:EXAMPLE_ORG/orders-api:environment:production
~~~

Subject này khác với subject theo nhánh main. Nếu workflow dùng environment, cấu hình FIC phải khớp ngữ cảnh environment, và nên bật environment protection rules như required reviewers, branch restrictions và các điều kiện triển khai phù hợp. Chỉ thêm FIC cho các nhánh, môi trường và repository thực sự được phép.

### 6.4. Cấp quyền ở phạm vi nhỏ nhất

Cho pipeline thử nghiệm chỉ đọc tài nguyên trong resource group đích, role Reader đủ để kiểm tra đăng nhập. Ví dụ:

~~~bash
SCOPE="/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-orders-dev"
az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal --role Reader --scope "$SCOPE"
~~~

Nếu pipeline thực sự cần tạo hoặc cập nhật tài nguyên, nhóm quản trị mới cân nhắc role phù hợp như Contributor ở resource group cụ thể hoặc custom role với hành động cần thiết. Tránh dùng Owner hoặc Contributor ở toàn subscription chỉ để kiểm tra một workflow.

Azure RBAC trên mặt phẳng quản lý (management plane) không đồng nghĩa với quyền đọc secret hoặc dữ liệu thực tế. Ví dụ, nếu workload cần đọc bí mật trong Key Vault dùng Azure RBAC permission model, phải cấp role dữ liệu phù hợp như Key Vault Secrets User trên phạm vi cần thiết. Với Storage Blob, cần role dữ liệu phù hợp như Storage Blob Data Reader hoặc Storage Blob Data Contributor tùy thao tác.

### 6.5. Cấu hình workflow GitHub Actions

Trong repository GitHub, khai báo các **Actions variables** có giá trị tương ứng:

| Variable | Giá trị |
|---|---|
| AZURE_CLIENT_ID | Application (client) ID của app Entra |
| AZURE_TENANT_ID | Microsoft Entra tenant ID |
| AZURE_SUBSCRIPTION_ID | Azure subscription ID |

Các ID này là định danh cấu hình, không phải client secret. Dù vậy, không cần công khai chúng không kiểm soát; hãy áp dụng quyền quản lý repository và workflow theo chính sách tổ chức.

Ví dụ workflow tại .github/workflows/azure-readonly.yml:

~~~yaml
name: Azure OIDC smoke test

on:
  push:
    branches:
      - main

permissions:
  contents: read
  id-token: write

jobs:
  verify-azure:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Sign in with workload identity federation
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify identity and resource group access
        run: |
          az account show --query "{subscription:id,tenant:tenantId}" --output table
          az group show --name rg-orders-dev --query "{name:name,location:location}" --output table
~~~

Quyền id-token: write cho phép job yêu cầu OIDC token từ GitHub theo cơ chế của GitHub Actions; nó không tự cấp quyền ghi tài nguyên Azure. Bước azure/login thực hiện trao đổi token theo FIC đã khai báo. Bước cuối chỉ đọc thông tin của resource group đã được cấp quyền Reader. Nếu thay bằng lệnh az group list để liệt kê tất cả resource group ở subscription, quyền Reader chỉ ở một resource group có thể không đủ. Không nên mở rộng quyền lên toàn subscription chỉ để một bước smoke test thuận tiện hơn.

Các giới hạn bảo mật của repository vẫn rất quan trọng. Nếu kẻ tấn công có thể sửa workflow chạy trên nhánh hoặc environment được FIC tin cậy, họ có thể yêu cầu OIDC token dưới ngữ cảnh đó và sử dụng các quyền của danh tính Azure. Vì vậy, bảo vệ nhánh, kiểm soát quyền ghi repository, bắt buộc review và giới hạn các workflow được phép triển khai vẫn là yêu cầu bắt buộc.

## 7. Azure DevOps: service connection dùng workload identity federation

Azure DevOps cung cấp cách cấu hình Azure Resource Manager service connection với xác thực workload identity federation. Ý tưởng tương tự GitHub Actions, nhưng **issuer và subject được tạo theo cơ chế của Azure DevOps service connection**. Không sao chép issuer/subject của GitHub sang Azure DevOps.

Quy trình tổng quát:

1. Trong Azure DevOps project, mở Project settings → Service connections.
2. Tạo hoặc chỉnh sửa Azure Resource Manager service connection và chọn phương thức Workload identity federation nếu khả dụng.
3. Chọn cơ chế tạo danh tính tự động hoặc nhập thông tin đăng ký thủ công, tùy quyền và giao diện Azure DevOps.
4. Với cấu hình thủ công, lấy **issuer và subject do service connection cung cấp**, đăng ký FIC tương ứng trong Entra app hoặc danh tính được hỗ trợ; không tự suy diễn chuỗi claim.
5. Cấp Azure RBAC role cho danh tính ở phạm vi resource group hoặc resource cần triển khai.
6. Xác minh service connection; giới hạn những pipeline được phép sử dụng kết nối này.

Ví dụ pipeline YAML thực hiện thao tác chỉ đọc:

~~~yaml
trigger:
  - main

pool:
  vmImage: ubuntu-latest

steps:
  - task: AzureCLI@2
    displayName: Verify Azure workload federation
    inputs:
      azureSubscription: 'sc-orders-dev-wif'
      scriptType: bash
      scriptLocation: inlineScript
      inlineScript: |
        az account show --query "{subscription:id,tenant:tenantId}" --output table
        az group show --name rg-orders-dev --query "{name:name,location:location}" --output table
~~~

Tên sc-orders-dev-wif là tên service connection minh họa; pipeline phải tham chiếu đúng kết nối đã được tạo và cho phép sử dụng. AzureCLI@2 sử dụng danh tính do service connection cung cấp. Pipeline không cần lưu client secret của service principal.

**Lưu ý vận hành:** một số tổ chức có service connection cũ dùng secret hoặc certificate. Việc chuyển sang WIF cần kiểm tra loại connection, quyền trong Azure DevOps, khả năng của extension/task và quy trình phê duyệt. Sau khi chuyển đổi thành công và xác minh mọi pipeline đang dùng cấu hình mới, mới thu hồi credential cũ theo quy trình an toàn.

## 8. Ứng dụng trên AKS: Kubernetes service account liên kết với managed identity

Với Azure Kubernetes Service (AKS), workload identity federation giúp pod dùng Kubernetes service account token để lấy access token từ Entra ID. Cách này không cần đưa client secret của một ứng dụng Azure vào Kubernetes Secret.

Ví dụ ứng dụng orders-api cần đọc secret từ Azure Key Vault:

~~~text
Pod orders-api
  ↓ gắn Kubernetes ServiceAccount orders-api
AKS OIDC issuer
  ↓ phát hành token có subject system:serviceaccount:orders:orders-api
Microsoft Entra ID
  ↓ so khớp FIC của user-assigned managed identity
Access token
  ↓
Azure Key Vault (kiểm tra quyền dữ liệu)
~~~

### 8.1. Điều kiện chuẩn bị

- Cụm AKS đã bật OIDC issuer và tính năng workload identity.
- Namespace orders và Kubernetes service account orders-api sẽ được tạo.
- Có user-assigned managed identity cho ứng dụng.
- Quyền thao tác trên identity và quyền gán Azure RBAC ở phạm vi Key Vault đích.
- Ứng dụng sử dụng Azure Identity SDK hoặc cơ chế lấy token tương thích với workload identity.

Đọc issuer URL của cụm AKS đã cấu hình:

~~~bash
AKS_ISSUER="$(az aks show --resource-group '<AKS_RESOURCE_GROUP>' --name '<AKS_CLUSTER_NAME>' --query oidcIssuerProfile.issuerUrl --output tsv)"
echo "$AKS_ISSUER"
~~~

Nếu OIDC issuer chưa bật, cần cấu hình cluster theo hướng dẫn AKS trước khi tiếp tục. Khi đưa issuer URL vào FIC, dùng chính xác chuỗi do AKS trả về, bao gồm cả dấu gạch chéo cuối nếu có.

### 8.2. Tạo user-assigned managed identity và FIC

Giả sử identity được đặt trong resource group rg-orders-identity:

~~~bash
az identity create --name id-orders-api --resource-group rg-orders-identity
AZURE_CLIENT_ID="$(az identity show --name id-orders-api --resource-group rg-orders-identity --query clientId --output tsv)"
AZURE_PRINCIPAL_ID="$(az identity show --name id-orders-api --resource-group rg-orders-identity --query principalId --output tsv)"
~~~

Tạo federated credential tin cậy đúng service account:

~~~bash
az identity federated-credential create \
  --name fic-aks-orders-api \
  --identity-name id-orders-api \
  --resource-group rg-orders-identity \
  --issuer "$AKS_ISSUER" \
  --subject "system:serviceaccount:orders:orders-api" \
  --audiences "api://AzureADTokenExchange"
~~~

Trong subject Kubernetes:

- orders đứng đầu là namespace.
- orders-api đứng sau là tên Kubernetes service account.
- Đổi tên namespace hoặc service account làm thay đổi subject của token và có thể khiến FIC không còn khớp.

Gán quyền phù hợp cho managed identity vào Key Vault đích. Ví dụ khi Key Vault dùng Azure RBAC permission model:

~~~bash
KEY_VAULT_ID="$(az keyvault show --name '<KEY_VAULT_NAME>' --query id --output tsv)"
az role assignment create --assignee-object-id "$AZURE_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope "$KEY_VAULT_ID"
~~~

Đây là role dành cho thao tác đọc secret theo permission model tương ứng; nó không thay thế các điều kiện mạng, firewall, private endpoint hoặc cấu hình quyền của Key Vault. Nếu Key Vault sử dụng access policy model, cách cấp quyền khác và phải tuân theo cấu hình thực tế.

### 8.3. Khai báo service account và pod

Ví dụ Kubernetes manifest, thay placeholder client ID và image trước khi triển khai:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<USER_ASSIGNED_IDENTITY_CLIENT_ID>"
---
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
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: "<REGISTRY>/orders-api:1.0"
~~~

AKS workload identity webhook sử dụng label của pod và annotation trên service account để thiết lập các thông tin cần thiết cho SDK, bao gồm đường dẫn token được project vào container và thông tin client ID. Ứng dụng dùng Azure Identity SDK phù hợp để lấy token; không cần nhúng client secret vào mã nguồn.

Ví dụ Java sử dụng Azure Identity và Azure Key Vault Secrets SDK (cần khai báo các dependency phù hợp trong ứng dụng):

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public class VaultExample {
    public static void main(String[] args) {
        SecretClient client = new SecretClientBuilder()
            .vaultUrl(System.getenv("KEY_VAULT_URL"))
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        // Chỉ minh họa truy cập: không ghi giá trị secret vào log.
        boolean found = client.getSecret("orders-api-config") != null;
        System.out.println("Secret available: " + found);
    }
}
~~~

Cần cấp quyền cho service principal của managed identity ở tài nguyên đích, kiểm tra network access và bảo đảm ứng dụng sử dụng phiên bản Azure Identity SDK hỗ trợ workload identity. DefaultAzureCredential tự lựa chọn loại credential khả dụng theo môi trường theo thứ tự quy định của SDK; trên AKS workload identity, pod cần được cấu hình đúng để SDK có thể sử dụng federated token.

## 9. Bảo mật và phân quyền theo từng lớp

WIF loại bỏ nhu cầu phân phối client secret dài hạn trong nhiều kịch bản, nhưng không làm danh tính Azure trở nên vô hại. Một pipeline có thể có quyền cập nhật production nếu được cấp role rộng, bất kể cách xác thực là secret hay OIDC.

Có thể phân tích thành ba lớp kiểm soát:

| Lớp | Câu hỏi cần trả lời | Biện pháp |
|---|---|---|
| Identity provider | Workload nào được phát hành OIDC token? | GitHub branch protection, environment approvals, Azure DevOps pipeline permissions, Kubernetes RBAC |
| Microsoft Entra ID | Token nào được phép trao đổi cho danh tính Azure? | FIC giới hạn issuer/subject/audience; danh tính riêng theo môi trường |
| Azure và dịch vụ đích | Danh tính Azure được làm gì? | Azure RBAC tối thiểu, data-plane role, scope cụ thể, network policy |

Một số nguyên tắc thiết kế:

1. **Tách danh tính dev/prod:** app hoặc managed identity riêng giúp giảm phạm vi ảnh hưởng khi một pipeline gặp sự cố.
2. **Giới hạn FIC:** chỉ tin cậy repository, nhánh, environment hoặc service account đã được phê duyệt. Đừng cho nhiều workflow không liên quan dùng chung danh tính có quyền cao.
3. **Bảo vệ nguồn token:** thiết lập quyền sửa workflow, code review, protected branch và GitHub Environment rules; kiểm soát service connection trong Azure DevOps.
4. **Cấp quyền đúng scope:** ưu tiên resource hoặc resource group cụ thể, áp dụng custom role khi cần; không cấp Owner ở subscription nếu không có lý do rõ ràng.
5. **Phân biệt management plane và data plane:** role thao tác ARM chưa chắc cho phép truy cập dữ liệu Key Vault, Blob hoặc cơ sở dữ liệu.
6. **Không ghi token vào log:** OIDC assertion và access token đều là vật mang quyền trong thời hạn hiệu lực; tránh in ra stdout, artifact hoặc thông báo lỗi công khai.
7. **Duy trì kiểm toán:** theo dõi sign-in log của service principal/managed identity khi khả dụng, Azure Activity Log và nhật ký triển khai CI/CD.
8. **Thu hồi kịp thời:** khi repository, branch, service account hoặc đối tác không còn được tin cậy, xóa FIC, giảm hoặc thu hồi role assignment và vô hiệu hóa pipeline liên quan.

Giới hạn số lượng FIC và khả năng dùng một số cấu hình federation có thể khác theo loại danh tính hoặc dịch vụ. Hãy thiết kế số danh tính và FIC theo hướng dễ quản lý, đồng thời kiểm tra hạn mức hiện hành.

## 10. Kiểm tra và xử lý sự cố

Khi workflow đăng nhập thất bại, hãy kiểm tra theo từng chặng: IdP đã cấp token chưa, Entra đã chấp nhận token chưa và Azure đã cho phép thao tác chưa.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không lấy được OIDC token trong GitHub Actions | Thiếu quyền id-token: write, workflow/trigger không phù hợp, chính sách repository | Kiểm tra permissions, event, job và cấu hình repository |
| Entra báo không tìm thấy federated credential phù hợp | Issuer, subject hoặc audience không khớp | Đối chiếu chính xác token claim với FIC; kiểm tra nhánh và environment |
| Entra báo ứng dụng không tồn tại hoặc sai tenant | Client ID, tenant ID hoặc đối tượng đăng ký không đúng | Kiểm tra app registration, service principal và tenant được chọn |
| Đăng nhập được nhưng Azure trả 403/AuthorizationFailed | Chưa có Azure RBAC role cần thiết hoặc scope không đúng | Kiểm tra object ID, role assignment, scope và thời gian lan truyền quyền |
| Đọc Key Vault/Storage thất bại dù đã đăng nhập | Thiếu data-plane role, access policy, cấu hình mạng hoặc endpoint | Kiểm tra permission model và kết nối tới dịch vụ đích |
| AKS pod không nhận credential | Thiếu pod label, service-account annotation, tính năng cluster chưa bật | Kiểm tra manifest, OIDC issuer, FIC subject và Azure Identity SDK |
| Pipeline trước đây dùng secret nhưng giờ lỗi sau chuyển đổi | Service connection hoặc task chưa dùng WIF đúng cách | Kiểm tra loại connection, tương thích task, issuer/subject và quyền pipeline |

Một số mã lỗi Microsoft Entra thuộc nhóm AADSTS70021 hoặc AADSTS700213 thường liên quan đến việc không tìm thấy FIC phù hợp với assertion. Đừng chỉ sửa audience theo phỏng đoán; kiểm tra chính xác issuer, subject, tenant và cấu hình đăng ký. Thông báo lỗi chi tiết có thể khác theo thời điểm và loại client.

Các lệnh kiểm tra hữu ích:

~~~bash
# Kiểm tra app FIC trong Entra ID
az ad app federated-credential list --id "<APP_CLIENT_ID>" --output json

# Kiểm tra FIC của user-assigned managed identity
az identity federated-credential list --identity-name "<IDENTITY_NAME>" --resource-group "<IDENTITY_RG>" --output json

# Kiểm tra subscription hiện tại
az account show --output table

# Kiểm tra role assignment tại resource group, bao gồm quyền kế thừa
az role assignment list --assignee "<APP_CLIENT_ID>" --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>" --include-inherited --output table
~~~

Các lệnh kiểm tra cần được chạy bằng tài khoản có quyền đọc thông tin liên quan. Role assignment có thể cần một khoảng thời gian để được áp dụng. Khi cần bật debug log, giới hạn người xem log và tránh chia sẻ JWT hoặc access token nguyên vẹn.

## 11. So sánh cách xác thực cho workload

| Phương thức | Lợi ích | Giới hạn và thời điểm phù hợp |
|---|---|---|
| Service principal + client secret | Tương thích rộng, cấu hình quen thuộc | Phải bảo quản và xoay vòng secret; chỉ dùng khi chưa thể áp dụng phương án phù hợp hơn |
| Service principal + certificate | Không phải mật khẩu dạng text; có thể quản lý vòng đời chứng chỉ | Vẫn phải quản lý private key và thời hạn chứng chỉ |
| Managed identity trực tiếp | Azure quản lý credential; thuận tiện cho dịch vụ Azure hỗ trợ | Phụ thuộc tài nguyên và môi trường thực thi được hỗ trợ |
| Workload identity federation | Không cần client secret Azure dài hạn; dựa trên OIDC trust và token ngắn hạn | Cần IdP/SDK/service connection hỗ trợ, FIC đúng và bảo vệ ngữ cảnh phát hành token |

Ví dụ quyết định:

- Một App Service trên Azure cần đọc Key Vault: ưu tiên managed identity trực tiếp nếu dịch vụ và thư viện hỗ trợ.
- GitHub Actions cần triển khai Bicep vào resource group: dùng OIDC và FIC cho Entra app với quyền phù hợp.
- Azure DevOps cần triển khai ứng dụng: dùng Azure Resource Manager service connection cấu hình workload identity federation.
- Pod AKS cần kết nối Azure Storage hoặc Key Vault: dùng AKS Workload Identity liên kết Kubernetes service account với user-assigned managed identity.

## 12. Câu hỏi tự kiểm tra

1. **Workload identity federation loại bỏ điều gì?** Nó có thể loại bỏ nhu cầu lưu client secret Azure dài hạn cho nhiều workload, nhờ token OIDC được trao đổi với Microsoft Entra ID.
2. **Ba claim quan trọng để ghép FIC thông thường là gì?** Issuer, subject và audience.
3. **Đăng nhập bằng OIDC thành công có đồng nghĩa với quyền Contributor không?** Không. Azure RBAC được cấp riêng cho danh tính ở một phạm vi xác định.
4. **GitHub Actions cần quyền gì để yêu cầu OIDC token?** Thông thường cần quyền job id-token: write.
5. **Subject cho nhánh main có giống subject cho GitHub Environment production không?** Không; phải cấu hình FIC khớp với ngữ cảnh sử dụng.
6. **Vì sao nên tạo danh tính riêng cho development và production?** Để phân tách quyền, giảm thiểu ảnh hưởng của sự cố và áp dụng kiểm soát phê duyệt khác nhau.
7. **Một pod AKS cần gì để dùng workload identity?** Cụm hỗ trợ OIDC issuer/workload identity, Kubernetes service account được liên kết, FIC khớp, pod được cấu hình đúng và SDK hỗ trợ.
8. **Nếu Azure trả 403 sau khi đăng nhập thành công, nên kiểm tra gì trước?** Azure RBAC role hoặc quyền data plane tại scope đích, thay vì vội đổi FIC.
9. **Có được in access token vào log để debug không?** Không; token có thể bị sử dụng để truy cập tài nguyên trong thời hạn hiệu lực.

## 13. Tài liệu tham khảo

- [Microsoft Entra workload identity federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) — nguyên lý, đối tượng và khả năng hỗ trợ WIF.
- [Federated identity credentials for Microsoft Entra applications](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust) — cấu hình quan hệ tin cậy.
- [GitHub Actions: OpenID Connect với Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure) — tạo và sử dụng OIDC token trong GitHub Actions.
- [Azure Login Action](https://github.com/Azure/login) — cách đăng nhập Azure từ GitHub Actions.
- [Azure DevOps workload identity federation](https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure) — cấu hình service connection cho pipeline.
- [AKS workload identity](https://learn.microsoft.com/azure/aks/workload-identity-overview) — kết nối Kubernetes service account với Entra và managed identity.
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview) — quản lý phạm vi và vai trò truy cập.

Các giao diện Azure Portal, quy trình tạo service connection, hạn mức và khả năng federation có thể thay đổi theo dịch vụ. Trong thực hành, đối chiếu tài liệu chính thức của nhà cung cấp OIDC và Microsoft Entra trước khi cấp quyền production.
