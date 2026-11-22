# Lưu Terraform state từ xa trong Azure Storage

Một nhóm đang dùng Terraform để dựng Azure Virtual Network, Azure App Service, Azure SQL, Azure Key Vault và các quyền của ứng dụng Spring Boot. Lập trình viên A chạy **terraform apply** trên laptop; file **terraform.tfstate** được tạo tại máy của A. Ngày hôm sau lập trình viên B chạy cùng mã nhưng không có file state đó. Terraform không nhận được lịch sử quản lý tài nguyên từ lần chạy trước, dẫn đến plan có thể sai, quản lý chồng chéo, tranh chấp thay đổi và khó kiểm toán. Nếu hai pipeline cùng apply trên cùng môi trường, tình huống còn nguy hiểm hơn.

**Terraform state** lưu sự ánh xạ giữa cấu hình Terraform và đối tượng hạ tầng được quản lý. Với Azure, backend **azurerm** có thể lưu state dưới dạng **blob trong Azure Storage** để nhiều người hoặc hệ thống CI/CD cùng sử dụng một nguồn state tập trung. Backend này hỗ trợ **state locking bằng Azure Blob lease**, giúp ngăn hai thao tác ghi state đồng thời khi các clients tôn trọng cơ chế khóa. Tuy nhiên, việc đặt state vào storage chỉ an toàn khi có **Azure RBAC data-plane, Microsoft Entra ID, quản lý network, versioning/recovery, giám sát và quy trình xử lý lock**.

Bài thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình tìm hiểu Microsoft Azure từ subscription, resource group, Entra ID tới mạng ảo, compute, storage và dữ liệu, quản trị Terraform remote state là yêu cầu nền tảng để triển khai kiến trúc Azure nhất quán, bảo vệ tài nguyên, giám sát thay đổi và kiểm soát chi phí.

> **Nguyên tắc xuyên suốt:** Terraform state **không phải** mã nguồn thông thường. Nó có thể chứa tên tài nguyên, resource IDs, connection strings, generated passwords, secret-derived attributes và những dữ liệu được provider trả về. **Không commit state vào Git, không xuất nguyên state vào CI logs, và không mở blob/public access**. Dù Terraform đánh dấu một output là **sensitive**, giá trị vẫn có thể nằm trong state được lưu ở backend.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Terraform state, resource address, provider identity và mối liên hệ với tài nguyên Azure thật.
2. So sánh local backend và **azurerm remote backend** về cộng tác, đồng thời, bảo mật và khôi phục.
3. Mô tả **Azure Storage account, blob service, container, blob key, Blob lease và versioning**.
4. Thiết kế mô hình bootstrap backend **trước khi** chạy terraform init.
5. Tạo StorageV2 account/container chuyên cho state bằng Azure CLI trong môi trường lab có phê duyệt.
6. Sử dụng Microsoft Entra ID và **Storage Blob Data Contributor** để thao tác với state blob theo nguyên tắc quyền tối thiểu.
7. Viết cấu hình **terraform { backend "azurerm" { ... } }** và khởi tạo bằng terraform init.
8. Phân biệt **backend authentication** với **azurerm provider authentication**; biết giới hạn của access keys, SAS và OIDC.
9. Đọc plan, apply, state list, state show và state pull **mà không để lộ dữ liệu nhạy cảm**.
10. Hiểu **locking bằng Blob lease**, cách xử lý lock conflict/lock timeout và lúc nào mới cân nhắc force-unlock.
11. Tách state theo application, environment và workstream; không xem Terraform workspaces là ranh giới bảo mật.
12. Di chuyển local state sang remote state bằng **terraform init -migrate-state** và chuẩn bị rollback.
13. Thiết kế backup bằng blob versioning/soft delete, quyền khôi phục và quy trình disaster recovery có kiểm soát.
14. Cấu hình firewall, Private Endpoint, private DNS và network path cho self-hosted agents.
15. Tích hợp CI/CD sử dụng OIDC/workload identity federation và bảo vệ PR jobs.
16. Giám sát storage operations/lock anomalies, state drift, retention, quota và FinOps.
17. Thực hành negative tests, troubleshooting và lập checklist trước production.

## 2. Tình huống xuyên suốt: Orders API và ba môi trường

Giả sử nhóm vận hành ứng dụng Java **Orders API** trên Azure App Service, với tài nguyên được quản lý bằng Terraform:

- **Network**: virtual network, subnet, route và private endpoint.
- **Compute**: Azure App Service Plan, Web App hoặc dịch vụ container.
- **Data**: Azure SQL và storage phụ trợ.
- **Security**: managed identity, Azure RBAC và Key Vault.
- **Observability**: Azure Monitor, Application Insights và diagnostic settings.

Ba môi trường **dev**, **staging**, **prod** có vòng đời khác nhau. Nhóm muốn:

- Terraform của từng môi trường có một nguồn state rõ ràng.
- CI/CD dùng identity có quyền chính xác, không copy storage key.
- Hai job apply cùng một state không âm thầm ghi đè nhau.
- Mọi lần plan biết đang thao tác với state key nào, subscription nào.
- Production state chỉ được truy cập từ actor/agent được phê duyệt.
- Khi lỡ ghi hỏng hoặc xóa blob, có bản có thể phục hồi.
- Tránh mất state khi xóa resource group ứng dụng.
- Biết chi phí của state storage, network, logs và agent workloads.

Ví dụ layout logic:

~~~text
Azure subscription: platform-shared
  Resource group: rg-iac-state-prod
    Storage account: stiacstateprod001
      Blob container: tfstate
        orders/prod/network.tfstate
        orders/prod/app.tfstate
        orders/prod/data.tfstate

Azure subscription: application-dev
  Resource group: rg-orders-dev
    VNet, App Service, SQL, Key Vault...

Azure subscription: application-prod
  Resource group: rg-orders-prod
    VNet, App Service, SQL, Key Vault...
~~~

**Tên chỉ minh họa.** Storage account name phải duy nhất theo phạm vi dịch vụ Azure, chỉ gồm chữ thường và số theo quy tắc hiện hành, nên **st iac state prod** không thể dùng khoảng trắng. Với production, chọn tên có hậu tố duy nhất theo naming convention.

## 3. Terraform state là gì và tại sao bắt buộc quản trị?

Một resource trong configuration:

~~~hcl
resource "azurerm_resource_group" "orders" {
  name     = "rg-orders-dev"
  location = "southeastasia"
}
~~~

Terraform lưu quan hệ giữa **resource address** như **azurerm_resource_group.orders** và resource Azure thực như ARM resource ID, cùng những thuộc tính cần để thực hiện refresh/plan. State còn có metadata phụ thuộc Terraform/provides và có thể ghi giá trị nhạy cảm.

### 3.1. Ba đối tượng không được nhầm

| Đối tượng | Chứa gì? | Có thể thay thế cái nào? |
|---|---|---|
| **Terraform configuration (.tf)** | Khai báo trạng thái mong muốn | Không tự là bản ghi tài nguyên đang quản lý |
| **Terraform state (.tfstate)** | Ánh xạ resource addresses và thực tế Terraform theo dõi | Không thay thế configuration hoặc Azure |
| **Azure live resources** | Tài nguyên đang tồn tại trên Azure | Không tự mang đầy đủ Terraform resource address |

Terraform dùng configuration, state và provider API để lập kế hoạch. Không có state, việc import/hủy/thay đổi resource có thể trở nên nguy hiểm, dù tài nguyên Azure vẫn còn.

### 3.2. State có thể chứa những thông tin nào?

- Resource IDs, DNS names, subnet IDs, private endpoint IDs.
- Managed identity principal IDs và role assignment metadata.
- Kết quả do providers trả về, có thể bao gồm connection strings hoặc secrets tùy resource/provider.
- Random passwords từ **random_password** resource.
- Outputs, kể cả outputs được đánh dấu **sensitive**.
- Thông số cấu hình và các attributes dùng để tính diff.

**sensitive=true** thường che giá trị trong một số giao diện CLI/output, **không mã hóa hoặc xóa giá trị khỏi state**. Vì vậy state storage cần được bảo vệ như một nguồn dữ liệu có thể chứa secrets.

### 3.3. State không phải là nhật ký bất biến

Khi Terraform apply thành công, state có thể được cập nhật. Khi apply lỗi giữa chừng, state và Azure resources có thể ở trạng thái khác nhau. Cần versioning/recovery và một quy trình reconcilliation, không coi state là “file backup giao dịch” của toàn Azure.

## 4. Local backend và remote backend

| Tiêu chí | Local state | Azure Storage remote state |
|---|---|---|
| Vị trí | Máy làm việc/CI workspace | Azure Blob được chỉ định |
| Cộng tác | Khó chia sẻ an toàn | Nhiều actors dùng chung state có kiểm soát |
| Khóa chống đồng thời | Local filesystem behavior, khó phối hợp nhiều máy | **Blob lease locking** |
| Khôi phục | Phụ thuộc local backup | Blob versioning/soft delete/backup policy nếu cấu hình |
| Truy cập | Quyền local filesystem | Azure RBAC data-plane + network |
| Tính sẵn sàng | Phụ thuộc máy | Phụ thuộc Azure Storage, mạng, identity |
| Audit | Local/CI logs | Azure Storage logs + Activity Log khi bật |
| Chi phí | Local disk | Storage operations, capacity, networking/monitoring |
| Rủi ro | Mất laptop, lộ file, concurrent applies | Rò state do quyền rộng, lỗi mạng, lock, deletion |

Remote backend là một công cụ quan trọng cho production nhưng **không tự giải quyết** việc ai được thay Terraform code, ai được chạy apply, ai quản lý Azure resources hay liệu ứng dụng có an toàn.

### 4.1. Vì sao không dùng Git để lưu tfstate?

- State có thể chứa sensitive values.
- Git history khó xóa triệt để khi lộ.
- Merge conflicts không phản ánh được tính nhất quán với Azure.
- Git không cung cấp lease locking thích hợp cho Terraform operations.
- Git clone/fork làm nhân bản file ra nhiều máy.
- Cơ chế Git review dành cho code, không dành cho giao thức cập nhật state nội bộ.

Không giải quyết bằng cách **gitignore** file remote state rồi đưa một bản backup plaintext lên repository khác.

## 5. Kiến trúc backend azurerm

~~~mermaid
flowchart LR
    DEV["Terraform CLI<br/>developer / CI job"] --> AUTH["Microsoft Entra ID<br/>Azure CLI / OIDC"]
    DEV --> BACK["Terraform azurerm backend"]
    AUTH --> BACK
    BACK --> SA["Azure Storage Account<br/>Blob service"]
    SA --> CON["Container: tfstate"]
    CON --> BLOB["Blob key:<br/>orders/prod/app.tfstate"]
    BACK -. "Blob lease for lock" .-> BLOB
    DEV --> PROV["Terraform azurerm provider"]
    PROV --> ARM["Azure Resource Manager<br/>VNet/App Service/SQL..."]
    MON["Azure Monitor / Logs"] -. "operations, alerts" .-> SA
~~~

**Tách hai đường:**

1. **Backend data plane**: đọc/ghi blob state, tạo/giải phóng lease, dùng Azure Storage authorization và network.
2. **Provider control/data plane**: tạo/sửa/xóa tài nguyên Azure như App Service, SQL, RBAC, mạng; permissions có thể khác backend.

Terraform init kết nối **backend** từ sớm, thậm chí trước khi provider config được dùng. Do đó **đăng nhập thành công vào AzureRM provider không tự chứng minh** backend có quyền Storage Blob Data Contributor.

### 5.1. Thành phần Storage

| Thành phần | Ví dụ | Chức năng |
|---|---|---|
| Resource group backend | rg-iac-state-prod | Tổ chức vòng đời state |
| Storage account | stiacstateprod001 | Boundary quản trị/network/replication/encryption |
| Blob service | Default blob endpoint | Lưu object data |
| Container | tfstate | Namespace các blobs |
| Blob key | orders/prod/app.tfstate | Tên object của một Terraform state |
| Blob lease | Lease trên state blob | Lock chống writer khác khi backend sử dụng |
| RBAC | Storage Blob Data Contributor | Thao tác blob data/lease theo scope |
| Versioning | Lịch sử blob versions | Khôi phục sau ghi/xóa sai theo policy |
| Soft delete | Giữ deleted versions/blobs trong retention | Hỗ trợ recovery |
| Private endpoint | Storage Blob private path | Hạn public exposure nếu cần |

### 5.2. Container không phải Git folder

Một blob key **orders/prod/app.tfstate** có dấu **/**, nhìn như thư mục; trong object storage, đó là **tên key**. Các công cụ Azure Portal/CLI có thể hiển thị hierarchy dạng ảo; đừng gắn RBAC/security boundary vào “thư mục” trừ khi tính năng/ACL tương ứng thực sự hỗ trợ.

## 6. Thiết kế backend trước khi tạo tài nguyên

### 6.1. Cô lập theo vòng đời

**Storage account giữ state không nên bị xóa bởi chính một Terraform stack đang dùng nó.** Nếu Terraform của app tự quản lý và destroy storage chứa state của app, hậu quả có thể là mất quyền quản lý, mất backup/lock và khó khôi phục.

Mô hình an toàn:

- Bootstrap backend bằng platform IaC/CLI thủ công có kiểm soát hoặc một **bootstrap Terraform stack với state riêng**.
- Quản lý state storage lifecycle, RBAC, logs bằng nhóm platform/guarded process.
- Terraform stacks của Orders API chỉ **tham chiếu backend có sẵn**.
- Bảo vệ state storage resource khỏi accidental delete theo policy/locks và break-glass runbook.

### 6.2. Tách dev/staging/prod

| Thiết kế | Ưu điểm | Rủi ro |
|---|---|---|
| Một account + container, nhiều blob keys | Dễ quản trị, ít resources | Blast radius nếu data-plane role quá rộng |
| Một account, nhiều containers | Phân tách scope RBAC tốt hơn | Network/encryption/account vẫn dùng chung |
| Storage account riêng theo môi trường | Ranh giới RBAC/network rõ hơn | Chi phí/vận hành tăng |
| Subscription riêng cho prod state | Cách ly mạnh, governance rõ | Cross-subscription ops/permissions |
| Một blob cho cả dev/prod | Đơn giản bề ngoài | **Không nên**: state collision/phá môi trường |

**Blob key duy nhất không phải ranh giới an toàn**. Nếu principal có Storage Blob Data Contributor trên toàn account, nó có thể có quyền đọc/ghi state của nhiều keys. Khi yêu cầu isolation mạnh, tách container/account/subscription, gán vai trò ở scope phù hợp và dùng identities khác.

### 6.3. Tách stacks theo blast radius

Ví dụ:

~~~text
orders/dev/network.tfstate
orders/dev/app.tfstate
orders/dev/data.tfstate

orders/staging/network.tfstate
orders/staging/app.tfstate
orders/staging/data.tfstate

orders/prod/network.tfstate
orders/prod/app.tfstate
orders/prod/data.tfstate
~~~

Một network stack riêng giúp các thay đổi App Service không nắm quyền sửa network chung, nhưng tạo dependency outputs. Cần đánh giá quản lý reference/output security và tránh state graph quá phân mảnh.

### 6.4. Quy tắc đặt tên

- Storage account name hợp lệ, duy nhất toàn cầu, không chứa bí mật.
- Container name rõ chức năng như **tfstate**.
- Blob key có prefix application/environment/workstream.
- Không reuse **orders/prod/app.tfstate** cho staging bằng cách sửa một biến trong pipeline.
- Ghi backend identifiers trong tài liệu vận hành, không ghi access keys.
- Không đặt PII, password hoặc token vào blob key.
- Resource tags: owner, service, environment, retention class, cost center theo quy ước.

## 7. Lab Azure CLI: bootstrap Storage account và container

Ví dụ dưới đây là **hướng dẫn để người học chạy trên Azure lab đã được phê duyệt**, không phải thao tác đã được thực hiện trong quá trình biên soạn bài. Azure Storage, Log Analytics và network resources có thể phát sinh chi phí. Không áp dụng nguyên trạng vào subscription production hoặc shared storage.

### 7.1. Điều kiện tiên quyết

- Azure subscription lab và một resource group được phép tạo.
- Azure CLI đã đăng nhập bằng identity phù hợp.
- Quyền tạo Storage Account; **quyền tạo Azure role assignment** do administrator/delegated principal nắm.
- Quyền sử dụng Terraform CLI tương thích với **azurerm backend**.
- Storage account name mới, hợp lệ và duy nhất.
- Network tới Azure ARM và Azure Blob service.
- Mục tiêu lab tạo storage **không public container** và ưu tiên Entra data-plane auth.
- Có kế hoạch dọn lab/retention sau thực hành.

### 7.2. Đăng nhập và xác định subscription

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --query \
  "{name:name,id:id,tenantId:tenantId}" \
  --output json
~~~

**Không** đoán subscription từ default Azure CLI account khi bạn có nhiều tenants hoặc subscriptions. Dùng subscription ID được phê duyệt và kiểm tra lại trước khi tạo resource.

### 7.3. Tạo resource group riêng cho backend

~~~bash
RG="rg-tfstate-lab"
REGION="southeastasia"

az group create \
  --name "$RG" \
  --location "$REGION"
~~~

State backend RG nên do platform team quản lý. Trong production, không để Terraform stack Orders API tự xóa nhóm này trong một lần **terraform destroy**.

### 7.4. Tạo StorageV2 account

~~~bash
# PHẢI thay tên bằng tên Azure Storage chưa được dùng,
# 3-24 ký tự, chỉ chữ thường và số.
SA="<globally-unique-storage-account>"

az storage account create \
  --name "$SA" \
  --resource-group "$RG" \
  --location "$REGION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --allow-shared-key-access false

az storage account show \
  --name "$SA" \
  --resource-group "$RG" \
  --query "{id:id,name:name,publicAccess:allowBlobPublicAccess,sharedKeyAllowed:allowSharedKeyAccess}" \
  --output json
~~~

**Standard_LRS** chỉ là lựa chọn lab, không phải đề xuất dự phòng cho mọi production backend. Chọn LRS/ZRS/GRS/GZRS theo yêu cầu tính sẵn sàng và thảm họa, cùng khả năng hỗ trợ của vùng/tier hiện hành.

**allow-shared-key-access=false** giúp giảm phụ thuộc account keys và yêu cầu workload dùng Entra auth cho Blob data, nhưng cần đảm bảo Terraform azurerm backend version/auth method đã hỗ trợ. Một số công cụ legacy có thể chưa tương thích; không bật/tắt tùy tiện trên production storage.

### 7.5. Kiểm tra identity và gán data-plane role

Lấy Azure resource ID của storage account và object ID người làm lab:

~~~bash
SA_ID=$(az storage account show \
  --name "$SA" \
  --resource-group "$RG" \
  --query id --output tsv)

USER_OID=$(az ad signed-in-user show \
  --query id --output tsv)

echo "Backend storage account resource ID obtained"
~~~

Người có quyền tạo role assignment, **không nhất thiết chính developer**, có thể cấp trong lab:

~~~bash
az role assignment create \
  --assignee-object-id "$USER_OID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$SA_ID"
~~~

**Storage Blob Data Contributor** là data-plane role thường được yêu cầu để backend đọc, ghi và lease state blob. **Reader/Contributor** ở ARM scope không tự tương đương với quyền Blob data.

Role assignment có thể mất thời gian để propagate. Không “sửa” lỗi 403 bằng cách bật shared keys hoặc cấp Owner toàn subscription khi chưa kiểm tra identity/scope/network.

### 7.6. Tạo container private bằng Entra login

~~~bash
CONTAINER="tfstate"

az storage container create \
  --name "$CONTAINER" \
  --account-name "$SA" \
  --auth-mode login \
  --public-access off

az storage container show \
  --name "$CONTAINER" \
  --account-name "$SA" \
  --auth-mode login \
  --query "{name:name,publicAccess:properties.publicAccess}" \
  --output json
~~~

Nếu CLI version không hỗ trợ một option, kiểm tra lệnh **az storage container create --help**; đừng bỏ tùy chọn auth-mode và vô tình chuyển sang shared key. Container private không có nghĩa identity có role ở account scope chỉ đọc đúng một blob; role scope vẫn quyết định data access.

### 7.7. Bật phục hồi blob với versioning và soft delete

Với backend lab chưa có policy chung:

~~~bash
az storage account blob-service-properties update \
  --account-name "$SA" \
  --resource-group "$RG" \
  --enable-versioning true \
  --enable-delete-retention true \
  --delete-retention-days 14
~~~

Versioning có thể giúp phục hồi **những bản ghi state trước đó**. Soft delete giúp phục hồi blob bị xóa trong retention. Các tính năng này không tự thay off-site backup, incident response, hoặc một bản kiểm soát state hợp lệ.

**Không bật immutability/WORM/legal hold cho state blob đang được Terraform ghi và lock** mà chưa đánh giá kỹ: một object không thể cập nhật có thể phá cơ chế state write/locking. Nếu compliance cần immutable archive, thiết kế bản sao archive riêng và kiểm chứng cách phục hồi.

### 7.8. Kiểm chứng container/data-plane

~~~bash
az storage blob list \
  --account-name "$SA" \
  --container-name "$CONTAINER" \
  --auth-mode login \
  --query "[].name" \
  --output table
~~~

Mới bootstrap, container có thể chưa có blob. **Không tự tạo file state giả** bằng thao tác upload một JSON rỗng: backend sẽ không thể parse state hợp lệ.

### 7.9. Khi nào không mở storage public network?

Trong một lab ngắn hạn, network public có thể được tổ chức cho phép với Entra auth và firewall/conditional policies. Production nhạy cảm thường yêu cầu **Private Endpoint, private DNS, controlled agent egress, public access disabled**. Cấu hình network cần được thiết kế **trước** khi khóa backend, nếu không Terraform init từ laptop hoặc Microsoft-hosted agent có thể mất kết nối.

## 8. Viết Terraform backend azurerm

### 8.1. Backend block trong Terraform

Trong dự án IaC, file **backend.tf**:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  backend "azurerm" {
    resource_group_name  = "rg-tfstate-lab"
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/dev/app.tfstate"

    use_azuread_auth = true
    use_cli          = true
  }
}
~~~

**Tên storage account chỉ là ví dụ, không được giả định tồn tại**. Thay bằng account vừa tạo và xác minh backend hỗ trợ các authentication settings trong **Terraform CLI version** đang chạy.

- **resource_group_name**: resource group chứa Storage account backend.
- **storage_account_name**: tên Storage account.
- **container_name**: container Blob lưu state.
- **key**: blob object name đại diện cho **một state**.
- **use_azuread_auth**: yêu cầu dùng Microsoft Entra ID để xác thực blob data plane.
- **use_cli**: phương thức sử dụng Azure CLI authentication theo khả năng backend version.

### 8.2. Terraform provider là một cấu hình riêng

Một file **providers.tf**:

~~~hcl
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = "<application-subscription-id>"
}
~~~

Với AzureRM provider 4.x, cần xác định subscription ID phù hợp (trực tiếp hoặc environment). Provider có thể cần scopes/permissions để tạo resource group/App Service/role assignment; những permissions **không phải** Storage Blob Data Contributor của backend.

**Tách quyền lý tưởng**:

~~~text
Terraform Backend Identity:
    Read / write / lease one authorized state container

Terraform Provider Identity:
    Manage approved Azure resources
    on approved subscription/resource group
~~~

Nếu pipeline dùng một identity cho cả hai, tối thiểu nó cần kết hợp hai nhóm quyền phù hợp. Khi tách jobs/identities, cần đảm bảo quá trình init và plan/apply nhận đúng identity tại từng bước.

### 8.3. Backend không chấp nhận Terraform variables trong block

Không viết:

~~~hcl
terraform {
  backend "azurerm" {
    # SAI: backend init xảy ra trước variable evaluation.
    key = var.state_key
  }
}
~~~

Một backend block được xử lý từ giai đoạn **terraform init**, trước khi regular variables/provider evaluation sẵn sàng. Không dùng **var**, **local** hoặc interpolations tùy ý để dựng backend configuration. Thay bằng **partial backend configuration** hoặc tạo file config từ CI với dữ liệu không nhạy cảm được kiểm soát.

### 8.4. Partial backend configuration

File **backend.tf**:

~~~hcl
terraform {
  backend "azurerm" {}
}
~~~

File **backend.dev.hcl**:

~~~hcl
resource_group_name  = "rg-tfstate-lab"
storage_account_name = "stexampleiaclab001"
container_name       = "tfstate"
key                  = "orders/dev/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Khởi tạo:

~~~bash
terraform init -backend-config=backend.dev.hcl
terraform validate
terraform plan
~~~

Một bản production tương ứng có file **backend.prod.hcl**, với storage account/container/key khác và identity/network khác. Tuy nhiên **đổi file backend** trên một working directory đã init cần xem xét reconfigure/migrate, không tự chạy init rồi nghĩ chắc chắn Terraform đã chọn đúng state mới.

**Lưu ý bảo mật:** Backend configs và các flag truyền vào **terraform init -backend-config** có thể được lưu trong **.terraform/** và plan artifacts. Vì vậy chỉ đặt **non-secret coordinates** vào backend HCL, không để client secrets, SAS tokens, access keys. Những file có placeholders phải được điền trước khi chạy.

### 8.5. Một ví dụ state stack nhỏ

Trong **main.tf** của một lab project riêng, có thể khai báo:

~~~hcl
resource "azurerm_resource_group" "orders_demo" {
  name     = "rg-orders-demo"
  location = "southeastasia"
  tags = {
    application = "orders"
    environment = "lab"
  }
}
~~~

Chỉ chạy **terraform apply** khi có subscription lab và quyền tạo resource. Đây là ví dụ minh họa resource; **không có resource nào được tạo khi viết bài**.

### 8.6. Terraform init làm những gì?

Một lần **terraform init** thông thường:

1. Đọc backend configuration.
2. Kiểm tra backend coordinates và authentication.
3. Khởi tạo truy cập tới storage container/blob.
4. Tải/kiểm tra state từ xa khi đã tồn tại.
5. Tải provider plugins và modules theo lockfile/config.
6. Cập nhật metadata **.terraform/** của working directory.
7. Thông báo nếu backend configuration đã thay đổi hoặc yêu cầu migrate.

**terraform init thành công không chứng minh** user có quyền tạo resource Azure trong provider subscription; chỉ chứng minh những bước init cần thiết đã hoạt động.

## 9. Terraform CLI: quan sát và kiểm soát remote state

### 9.1. Những lệnh cần hiểu

| Lệnh | Ý nghĩa | Rủi ro |
|---|---|---|
| **terraform init** | Kết nối backend, plugins/modules | Auth/backend mismatch |
| **terraform fmt -check** | Kiểm tra format HCL | Không gọi resource deploy |
| **terraform validate** | Kiểm tra cấu trúc HCL/providers | Không chứng minh Azure RBAC |
| **terraform plan** | Tính diff dự kiến theo state/live API | Output/plan file có thể nhạy cảm |
| **terraform apply** | Thay resource và cập nhật state | Thay hạ tầng thật |
| **terraform state list** | Liệt kê resource addresses đang quản lý | Metadata có thể nhạy cảm |
| **terraform state show** | Xem attributes của một resource | **Có thể in sensitive values** |
| **terraform state pull** | Tải raw state JSON | **Cực kỳ nhạy cảm** |
| **terraform state mv/rm** | Sửa mapping trong state | Có thể phá quản lý resource |
| **terraform force-unlock** | Gỡ khóa state theo lock ID | Rủi ro ghi đồng thời |
| **terraform workspace list** | Liệt kê logical workspaces | Không tạo security isolation |

### 9.2. Chuỗi lệnh lab khuyến nghị

~~~bash
terraform version
terraform fmt -check -recursive
terraform init -backend-config=backend.dev.hcl
terraform validate

# Plan có thể đọc resources và đề nghị thay đổi,
# kiểm tra đích, subscription và backend key trước khi chạy.
terraform plan
~~~

**Không mặc định chạy terraform apply** khi chỉ học remote state. Plan có thể gọi Azure APIs và có quyền đọc cấu hình nhạy cảm; CI logs phải được bảo vệ. Nếu tạo binary plan bằng **terraform plan -out=plan.bin**, coi plan.bin như sensitive artifact.

### 9.3. Sau khi init, blob state xuất hiện lúc nào?

Terraform có thể tạo/lưu state blob khi có thay đổi state hoặc thao tác ghi state cần thiết; không bảo đảm **terraform init** trên một backend mới sẽ tạo blob ngay nếu chưa có state cần lưu. Đừng tự tạo một JSON placeholder thay Terraform.

Khi state đã được ghi, blob name sẽ tương ứng với **key** được cấu hình, ví dụ **orders/dev/app.tfstate**. Trên Azure Portal, tên có dấu / có thể hiển thị như thư mục ảo.

### 9.4. Kiểm tra blob metadata mà không tải state value

~~~bash
az storage blob list \
  --account-name "$SA" \
  --container-name "tfstate" \
  --auth-mode login \
  --query "[].{name:name,etag:properties.etag,lastModified:properties.lastModified}" \
  --output table
~~~

Việc list names/ETags không hiển thị state JSON, nhưng **resource names và metadata** cũng có thể nhạy cảm. Lệnh cần quyền data plane tương ứng.

### 9.5. Không xuất raw state trong terminal

Tránh:

~~~bash
# Không chạy trên production nếu không có incident approval.
terraform state pull
terraform show -json plan.bin
terraform output -json
~~~

Các lệnh có thể cho thấy state hoặc outputs nhạy cảm. Nếu cần backup/forensics, thực hiện qua quy trình lưu file mã hóa/quyền hẹp, tránh stdout/CI logs. **sensitive outputs** không biến raw JSON thành vô hại.

### 9.6. Thao tác apply an toàn

Một quy trình có kiểm soát:

1. Review backend coordinates và environment/subscription.
2. Xác thực identity, Azure data-plane/backend permission, provider permission.
3. Chạy fmt/validate.
4. Lấy plan và đánh giá diff.
5. Người/automation có quyền phê duyệt cho apply.
6. Bảo đảm không có apply khác đang chạy cùng state key.
7. Chạy apply với locking, có timeout phù hợp.
8. Quan sát run log, state update và Azure resources.
9. Nếu apply fail giữa chừng, không xóa state; điều tra state/live drift.

## 10. State locking bằng Azure Blob lease

### 10.1. Lock giải quyết vấn đề gì?

Nếu CI job A và B cùng dùng **orders/prod/app.tfstate**:

~~~text
A reads state version N
B reads state version N
A creates resource X and updates state N+1
B also applies based on stale state N
→ Risk of duplicated/overwritten/conflicting operations
~~~

Backend **azurerm** dùng cơ chế **Blob lease** để lock state khi các Terraform operations ghi/đòi khóa. Một job đang giữ lease có thể khiến job kia **chờ hoặc fail với lỗi lock** thay vì âm thầm ghi chồng state.

### 10.2. Luồng locking

~~~mermaid
sequenceDiagram
    participant A as Terraform Job A
    participant B as Terraform Job B
    participant ST as Azure Blob state
    A->>ST: Acquire blob lease
    ST-->>A: Lease acquired
    B->>ST: Acquire lease
    ST-->>B: Locked / wait or fail
    A->>ST: Read, plan/apply and write state
    A->>ST: Release lease
    B->>ST: Acquire lease after release
    ST-->>B: Lease acquired
~~~

Sơ đồ mô hình hóa cơ chế locking; details về renew/lease durations là implementation của backend. Blob lease **không là distributed transaction bao trùm Azure resources**: apply có thể thay Azure resource nhưng fail ghi state, cần reconcile.

### 10.3. Lock timeout

Một lệnh apply có thể sử dụng:

~~~bash
terraform apply -lock-timeout=5m
~~~

**-lock-timeout** cho Terraform đợi lock trong một khoảng trước khi fail, không bảo đảm sẽ acquire nếu holder không release. Khoảng thời gian phù hợp phụ thuộc độ dài apply, queue, team concurrency và CI timeout.

### 10.4. Các trường hợp cần điều tra

- Hai applies vào đúng một key.
- Job A bị kill giữa apply.
- Network connectivity mất khi đang lock.
- Azure Storage throttling/service timeout.
- Terraform client state/backend configuration thay đổi.
- Storage blob có lease do một công cụ khác nắm giữ.

Khi thấy **Error acquiring the state lock**, trước tiên tìm run đang hoạt động và lock metadata. Không tự chạy force-unlock ngay.

### 10.5. Vì sao không dùng -lock=false?

~~~bash
# Anti-pattern, không chạy cho shared/prod state:
terraform apply -lock=false
~~~

Tắt locking cho shared state có thể gây ghi đồng thời và mất đồng bộ giữa state với Azure live resources. Chỉ có những kịch bản rất đặc biệt, cô lập và được chuyên gia đánh giá mới có thể bàn tới flag này; không dùng như giải pháp chung cho lock errors.

### 10.6. Force-unlock là thao tác break-glass

Terraform hỗ trợ:

~~~bash
# CHỈ minh họa cú pháp; yêu cầu approval và LOCK_ID thật.
terraform force-unlock "<verified-lock-id>"
~~~

Trước khi làm:

1. Xác minh **đúng backend key** và environment.
2. Kiểm tra Azure Pipelines/GitHub Actions/Jenkins jobs liên quan đã dừng.
3. Xác minh không có người đang apply từ laptop.
4. Xem lock metadata, holder/creation time và audit logs.
5. Thông báo nhóm sở hữu.
6. Bảo vệ/backup state theo policy nếu nghi hỏng.
7. Có incident/ticket/approval.
8. Chỉ unlock khi xác nhận stale lock; thử lại một plan an toàn.
9. Theo dõi trạng thái state và Azure resources sau đó.

**Force-unlock một lock còn hợp lệ có thể cho phép hai writers cùng thao tác, gây hư state**. Không dùng **az storage blob lease break** như phản xạ đầu tiên; đó là thao tác storage cấp thấp và có thể phá assumptions của Terraform backend.

## 11. Microsoft Entra ID và Storage Blob data-plane permissions

### 11.1. Quyền quản lý resource khác quyền dữ liệu blob

| Quyền | Ý nghĩa | Có đủ để state read/write? |
|---|---|---|
| Azure Reader trên RG | Xem metadata resources | Không |
| Azure Contributor trên RG | Quản lý Azure resources | Không tự có direct Blob data-plane permission |
| **Storage Blob Data Reader** | Đọc blob data | Không đủ để ghi/lease state |
| **Storage Blob Data Contributor** | Đọc/ghi/xóa/điều khiển blob theo role | Thường phù hợp với backend |
| Storage Blob Data Owner | Data-plane quyền rộng hơn | Thường không cần |
| Owner/User Access Administrator | Có quyền gán role ở scope thích hợp | Không thay data-plane role nếu chưa gán |

**Lưu ý:** Người có một số quyền quản trị storage account có thể có khả năng truy xuất account keys khi Shared Key enabled, từ đó gián tiếp mở data access. Vì vậy account management roles cũng phải được kiểm soát; **disable Shared Key** giúp giảm một đường leo quyền khi công cụ tương thích.

### 11.2. Scope gán role

Một identity chỉ cần một state container không nên có **Storage Blob Data Contributor** ở mọi storage accounts trong subscription. Gán ở scope thấp nhất được backend và vận hành hỗ trợ:

~~~text
/subscriptions/<id>
  /resourceGroups/<rg>
    /providers/Microsoft.Storage/storageAccounts/<account>
      /blobServices/default/containers/<container>
~~~

Container-scoped role assignment có thể phù hợp để hạn đọc/ghi container riêng, sau khi container được bootstrap. Nếu các lệnh init/backend còn cần một ARM read/endpoint lookup quyền rộng hơn trong auth flow cụ thể, phân tích và cấp read-only ARM permission cần thiết, không cấp Owner.

### 11.3. Azure CLI auth ở local

Một cấu hình có thể dùng:

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-lab"
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/dev/app.tfstate"
    use_azuread_auth     = true
    use_cli              = true
  }
}
~~~

Đăng nhập local:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
terraform init
~~~

Nếu môi trường Azure CLI có nhiều tài khoản/tenants, phải kiểm tra identity thực và token. **Backend auth** phụ thuộc Terraform CLI/backend implementation, không phải tự kế thừa mọi cài đặt provider.

### 11.4. Không lưu account key/SAS trong HCL

Một cấu hình xấu:

~~~hcl
terraform {
  backend "azurerm" {
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/prod/app.tfstate"

    # ANTI-PATTERN: KHÔNG dùng credential thật trong source.
    access_key = "DO_NOT_PUT_REAL_STORAGE_KEYS_HERE"
  }
}
~~~

Nếu credential từng bị commit, chỉ xóa dòng ở HEAD là **chưa đủ** vì Git history và CI logs có thể đã lộ. Cần đánh giá exposure, thu hồi/rotate key/SAS theo chính sách, scan history/artifacts và chuyển sang Entra auth.

## 12. Backend authentication và Provider authentication không đồng nhất

### 12.1. Hai điểm đăng nhập có thể khác tenant/subscription

Ví dụ:

~~~text
Backend:
    Storage subscription = platform-shared
    Storage RBAC = Storage Blob Data Contributor
    Backend blob key = orders/prod/app.tfstate

Provider:
    Application subscription = application-prod
    Azure resource permissions = scoped Contributor + roles
~~~

Một pipeline có thể được cấp hai identities hoặc một identity có hai nhóm permissions. Tuy nhiên với **least privilege** và separation of duties, tách permissions sẽ dễ audit hơn.

### 12.2. Sai lầm rất thường gặp

Một người cấu hình:

~~~hcl
provider "azurerm" {
  features {}
  subscription_id = "<app-subscription-id>"
}
~~~

rồi nghĩ backend tự biết subscription chứa storage account. **Không đúng**: backend block cần coordinates và authentication riêng; backend init diễn ra trước provider initialization.

### 12.3. Authentication strategy

| Phương thức | Mục tiêu | Đánh đổi |
|---|---|---|
| Azure CLI/interactive Entra | Developer lab | Không lý tưởng cho unattended CI |
| Managed identity | Azure-hosted runner có identity | Runner network/identity phải chuẩn |
| OIDC/workload identity federation | CI/CD với short-lived token | Setup federation/claim/config phức tạp |
| Service principal secret/certificate | Legacy/non-OIDC workloads | Credential lifecycle và leak risk |
| Storage account key | Legacy backend authentication | Quyền rộng, credential static, cần rotate |
| SAS token | Scoped/delegated storage access | Expiry/revocation, secret handling |

Ưu tiên **OIDC/managed identity/Entra blob auth** khi Terraform CLI/backend version và Azure DevOps/GitHub platform hỗ trợ. Không bật cả năm cơ chế rồi để backend chọn ngẫu nhiên.

## 13. Terraform workspaces và state key isolation

### 13.1. Workspaces là gì?

Terraform **CLI workspaces** cho phép nhiều state instances của cùng một configuration theo backend hỗ trợ. Với azurerm backend, các non-default workspaces có thể dùng **workspace_key_prefix**/naming convention do backend quản lý.

Ví dụ:

~~~bash
terraform workspace list
terraform workspace new dev
terraform workspace select dev
terraform workspace show
~~~

**Không kết luận** key thực trong Blob chỉ bằng cách nhìn tên workspace và tự ghép string. Xem backend documentation và kiểm tra Blob object names sau init/operations.

### 13.2. Workspaces không phải boundary bảo mật

Nếu một identity có quyền đọc toàn container, việc đổi workspace name **không thu hẹp** permissions. Khi prod/dev cần RBAC/network isolation, dùng storage account/container và identities riêng.

### 13.3. Chọn workspaces hay backend key riêng?

| Mục tiêu | Gợi ý |
|---|---|
| PR ephemeral environments với cùng permissions và lifecycle | Workspaces có thể tiện |
| Long-lived prod/staging/dev cần isolation | Backend key/container/account riêng |
| Network state và application state khác owners | Separate state keys và stacks |
| Multi-tenant dữ liệu nhạy cảm | Separate backend security scopes |
| Dễ kiểm tra CI/CD target | Explicit backend coordinates per environment |

Không dùng **terraform workspace select prod** làm biện pháp duy nhất ngăn một PR job deploy production. Cần RBAC/service connection approval/branch rules.

### 13.4. Không thay tên key để “chuyển môi trường”

Nếu state hiện tại quản lý resource dev, đổi **key** từ dev sang prod mà không có controlled migration/authorization có thể khiến Terraform trông thấy **empty/new state**, đề nghị tạo lại resources hoặc làm hỏng môi trường. Tất cả thay đổi backend coordinates cần review và dry-run.

## 14. Terraform state và outputs có thể chứa secrets

### 14.1. Terraform sensitive flag bảo vệ giao diện, không phải storage

~~~hcl
output "connection_string" {
  value     = azurerm_storage_account.example.primary_connection_string
  sensitive = true
}
~~~

Đây là mẫu HCL minh họa phụ thuộc resource tồn tại trong project. **sensitive=true** chủ yếu giảm tiết lộ tại những CLI outputs/UI; **không xóa hoặc tự mã hóa giá trị trong state**.

### 14.2. Tránh đưa secret vào state ngay từ thiết kế

- Sử dụng **managed identity/Entra auth** thay connection strings/account keys nếu dịch vụ hỗ trợ.
- Không dùng Terraform **random_password** tạo mật khẩu rồi xuất raw vào outputs nếu có thể chọn identity-based flow.
- Nếu bắt buộc quản lý một secret, giới hạn state readers và hiểu rằng **Key Vault Secret resource metadata** hoặc provider attributes có thể nằm trong state.
- Tránh data sources đọc secret value không cần thiết.
- Không đưa sensitive outputs vào CI logs hoặc issue trackers.
- Không dùng CLI **terraform state pull** để cung cấp secret cho app runtime.

## 15. Di chuyển local state lên Azure Storage: terraform init -migrate-state

### 15.1. Vì sao không copy file thủ công?

Giả sử nhóm đã có **terraform.tfstate** local đang quản lý 20 Azure resources. Nếu chỉ thêm backend block, xóa file local rồi init, Terraform có thể thấy remote state trống và đề nghị tạo lại tài nguyên. Nếu upload một file state bằng Storage Explorer tùy tiện, dễ sai blob key, format, đồng thời hoặc bỏ qua migration protocol.

**Dùng Terraform migration mechanism**, không coi backend migration là thao tác file copy đơn giản.

### 15.2. Runbook trước migration

1. **Chọn owner và change window** cho stack.
2. Thông báo mọi người ngừng chạy **plan/apply/state commands** trên stack.
3. Xác minh branch/commit/version Terraform và provider lockfile.
4. Xác minh state local hiện tại có đúng resources và subscription.
5. Kiểm tra không còn job apply đang chạy.
6. Chuẩn bị storage account/container/key riêng đã có Entra role/network.
7. Kiểm tra destination state blob **chưa chứa state của stack khác**.
8. Lưu một bản backup local state và supporting files theo **secure backup runbook**, không upload vào Git/chat.
9. Ghi rollback plan, person responsible và tiêu chí xác minh.
10. Không thay resource definitions cùng lúc với migration nếu không cần thiết.

Nếu local state bị thất lạc/không đầy đủ, cần xử lý import/recovery theo runbook trước; migration không thể tự tạo lại resource-to-address mapping từ Azure.

### 15.3. Trước migration: local backend

Một Terraform project có configuration:

~~~hcl
terraform {
  required_version = ">= 1.6.0"
  # Chưa có backend block: dùng local state mặc định.
}
~~~

Kiểm tra local state theo cách **không làm lộ values**:

~~~bash
terraform version
terraform state list
terraform plan
~~~

**terraform state list** có thể liệt kê resource addresses/tên hạ tầng; coi metadata này là nội bộ. Không cần gọi **terraform state pull** và in raw JSON.

### 15.4. Thêm partial azurerm backend

Sửa file **backend.tf**:

~~~hcl
terraform {
  backend "azurerm" {}
}
~~~

File **backend.prod.hcl**:

~~~hcl
resource_group_name  = "rg-iac-state-prod"
storage_account_name = "stexampleiacprod001"
container_name       = "tfstate"
key                  = "orders/prod/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Tên minh họa, thay bằng storage coordinates thật đã được approved. **File backend chỉ có non-secret metadata**, không chứa account key/client secret.

### 15.5. Khởi chạy migration

Khi đã freeze writers, Azure CLI identity được cấp role và kết nối tới storage:

~~~bash
az login
az account set --subscription "<backend-subscription-id>"

terraform init \
  -migrate-state \
  -backend-config=backend.prod.hcl
~~~

Terraform có thể hỏi xác nhận việc **copy/migrate existing state**. Chỉ xác nhận khi nguồn/đích chính xác. Trong automated migration, không tự thêm cờ bỏ prompt cho production nếu chưa có approval và guard chặn destination collision.

**Không chạy đồng thời một terraform apply khác** trong lúc migration. Migration và backend switching là thay đổi vận hành nhạy cảm.

### 15.6. Xác minh sau migration

1. Chạy **terraform state list** và kiểm tra resource addresses/đếm resources có lý.
2. Xác minh blob key tồn tại trong đúng storage account/container bằng **metadata-only list**.
3. Ghi state lineage/serial theo quy trình bảo mật nếu cần, **không in raw state**.
4. Chạy **terraform plan** với identity/provider permissions đúng.
5. Plan kỳ vọng **no changes** nếu code và live resources không đổi (ngoại lệ các drift/provider normalization thực).
6. Kiểm tra lease/locking bằng test có kiểm soát, không apply song song trên prod.
7. Cập nhật runbooks/team docs/CI backend config references.
8. Xác nhận mọi developer/pipeline đã chuyển sang remote backend.
9. Đưa local backup vào kho an toàn với retention; không để state plaintext dư thừa trong desktop/CI workspace.

Nếu plan đề nghị tạo lại toàn bộ resources, **dừng ngay**, không apply. Kiểm tra đúng key/workspace, migration result, source state và subscription, tránh tạo tài nguyên trùng.

### 15.7. terraform init -reconfigure khác -migrate-state

| Tùy chọn | Mục đích | Nguy cơ |
|---|---|---|
| **terraform init -migrate-state** | Chuyển existing state sang backend mới theo workflow | Cần nguồn/đích đúng và freeze writers |
| **terraform init -reconfigure** | Bỏ backend config đã cache và cấu hình lại | **Không tự copy state** |
| **terraform init -backend=false** | Không khởi tạo backend (phù hợp một số offline validation) | Không thực hiện remote state operations |
| **terraform force-unlock** | Gỡ state lock khi stale và được duyệt | Rủi ro đồng thời/ghi đè state |

**Không dùng -reconfigure làm “cách migrate nhanh hơn”**. Nếu backend key mới trống, Terraform có thể coi stack như chưa từng được quản lý.

### 15.8. Rollback migration

Nếu migration sai mà chưa apply thêm:

- Dừng writers và xác định backend nào hiện chứa **source of truth**.
- So state metadata/lineage bằng công cụ và quyền được duyệt.
- Không đồng thời chạy operations trên local và remote copies.
- Phục hồi từ secure backup/blob version **theo runbook**.
- Dùng Terraform backend migration/reconfigure một cách có kiểm soát, ghi change ticket.
- Chỉ tiếp tục plan/apply sau khi state mapping và Azure resources được xác minh.

Khi đã có apply mới vào remote state, rollback về backup cũ có thể làm mất các thay đổi vừa tạo. Cần **reconcile**, không khôi phục bản cũ một cách mù quáng.

## 16. Versioning, soft delete và thiết kế backup

### 16.1. Vì sao cần backup state?

Rủi ro:

- Lỡ xóa blob state hoặc container.
- Lỡ chạy Terraform state rm/mv với address sai.
- Apply thất bại sau một phần thay đổi Azure resources.
- Pipeline khác dùng nhầm backend key.
- Principal bị xâm nhập ghi state giả/tùy tiện.
- Mất/quá hạn các files backup local.
- Storage account bị xóa, region/network outage.
- Các thay đổi state từ một provider version không tương thích hoặc thao tác migration sai.

### 16.2. Blob versioning

Với versioning enabled, Azure Blob Storage có thể lưu các versions trước của state blob khi bị ghi đè. Điều này giúp chọn thời điểm phục hồi khi **bản state mới bị hỏng hoặc không mong muốn**, trong giới hạn service/retention.

**Không tự hiểu mọi version đều là bản state nhất quán với Azure live resources.** Một apply có thể đã tạo/sửa Azure resources trước khi ghi state. Chọn backup đúng serial/lineage/time cần xem audit và actual resources.

### 16.3. Soft delete

Soft delete giữ blob đã bị xóa theo retention period, giúp recovery khi người vận hành xóa nhầm. Cần phân biệt:

- **Blob soft delete**.
- **Container soft delete**, nếu được bật riêng theo khả năng.
- **Blob versioning**.
- **Storage account/resource deletion** (không được blob soft delete tự bảo vệ mọi trường hợp).
- **Off-site/cross-region recovery/backup**.

Không nhầm các tính năng trên thành “Azure Storage tự sao lưu mọi thứ vĩnh viễn”.

### 16.4. Replication không phải backup lịch sử

| Redundancy | Ý nghĩa khái quát | Điều không bảo đảm |
|---|---|---|
| **LRS** | Bản sao đồng bộ trong một vùng/địa điểm theo Storage service | Không tự chống region failure |
| **ZRS** | Bản sao trên availability zones khi hỗ trợ | Không tự phục hồi state logic sai |
| **GRS/RA-GRS** | Replication qua region cặp phù hợp | Không bảo đảm zero RPO hoặc active write ở secondary |
| **GZRS/RA-GZRS** | Kết hợp zone và geo redundancy khi hỗ trợ | Không thay đổi runbook failover/recovery |
| **Versioning/soft delete** | Giữ dữ liệu lịch sử để restore | Không tự bảo vệ khỏi storage account deletion/attacker quyền cao |

Một state bị cập nhật sai logic có thể được **replicate thành công** tới vùng thứ hai. Do đó geo replication và backup version là hai mục tiêu khác nhau.

### 16.5. Quy trình phục hồi state an toàn

Khi nghi state bị mất/hỏng:

1. Đặt stack vào **maintenance/freeze**; dừng plan/apply writers.
2. Xác định đúng Storage account, container, blob key và state workspace.
3. Xem Azure Storage diagnostic/Activity logs để xác định lần ghi/xóa cuối.
4. Xem blob versions/soft-deleted objects theo quyền được duyệt.
5. Bảo toàn một bản raw evidence ở nơi bảo mật, không đưa vào CI log.
6. So candidate version với Terraform state lineage, serial, resource addresses và actual Azure resources.
7. Chọn recovery point có reasoning/chứng cứ, không chọn newest chỉ theo timestamp.
8. Khôi phục bằng phương thức Azure Storage/Terraform được tổ chức hỗ trợ.
9. Kiểm tra lease, lock/authorization, không phá lock của writer đang chạy.
10. Chạy một **terraform plan** có giám sát, không apply ngay.
11. Xử lý drift bằng import/moved blocks/state commands nếu thật sự cần và có approval.
12. Ghi postmortem: nguyên nhân, ảnh hưởng, RPO/RTO, policy fix.

**Không xuất raw state lên chat/ticket** để nhờ review. State có thể chứa credentials dù report không hiển thị chúng.

### 16.6. Backup encryption và immutable archive

Storage mã hóa dữ liệu at rest theo dịch vụ; có thể yêu cầu customer-managed keys theo chính sách. Với backup archive cần chống sửa/xóa, xem immutable storage/archive **riêng**. Đừng đặt legal hold trên **active state blob** một cách tùy tiện: Terraform cần cập nhật state và thực hiện lease operations.

### 16.7. Recovery point objective

- **RPO**: lượng state change tối đa chấp nhận mất (ví dụ một apply).
- **RTO**: thời gian khôi phục khả năng plan/apply có kiểm soát.
- **Durability vs recoverability**: lưu bền bỉ chưa đủ nếu không biết version nào phù hợp.
- **Incident command**: ai có quyền restore phiên bản state, ai xác nhận với Azure resources?

Đặt SLO/RPO/RTO theo mức độ quan trọng của stack, không dùng một con số áp chung.

## 17. Storage security, encryption, resource locks và quyền xóa

### 17.1. Security controls nhiều lớp

~~~mermaid
flowchart TD
    ID["Microsoft Entra ID<br/>managed/OIDC identity"] --> RBAC["Storage Blob Data Contributor<br/>scoped access"]
    RBAC --> NET["VNet / Firewall / Private Endpoint"]
    NET --> TLS["HTTPS TLS 1.2+"]
    TLS --> BLOB["State blob"]
    BLOB --> VER["Versioning + soft delete"]
    BLOB --> MON["Audit logs + alerts"]
    ARM["ARM management governance"] --> GUARD["Resource lock / Azure Policy"]
    GUARD --> BLOB
~~~

Các tầng trong sơ đồ là **mô hình kiểm soát**, không phải thứ tự thuật toán authorization nội bộ.

### 17.2. Tắt public blob access khác với tắt network public endpoint

- **Allow Blob anonymous public access = false** ngăn các container/blob public access theo account policy.
- **Public network access = disabled** hạn network public endpoint và cần private connectivity phù hợp.
- **Azure AD/RBAC** quyết định caller được thao tác data plane thế nào.
- **Private Endpoint** quyết định kết nối mạng riêng và DNS.
- **Shared Key access disabled** giảm đường auth bằng account keys khi tất cả tooling tương thích.

Một storage account không cho anonymous access vẫn có thể reachable từ public network với **authenticated requests** nếu firewall/network mở. Không nhầm hai controls.

### 17.3. Azure Resource Lock

Một resource lock dạng **CanNotDelete** trên storage account/backend RG có thể giảm nguy cơ xóa qua ARM, nhưng nó:

- Không tự cấm sửa blob state ở data plane.
- Không thay thế permissions và blob versioning.
- Có thể làm các hoạt động platform cần thiết bị chặn.
- Cần break-glass governance và audit riêng.

Không nhầm **ARM resource lock** với **Terraform state lock** hoặc Azure Blob lease. Chúng giải quyết các vấn đề khác nhau.

### 17.4. Encryption

Azure Storage cung cấp encryption at rest cho blob data và HTTPS in transit. Nếu dùng **customer-managed key (CMK)**, cần Key Vault/Managed HSM, identity và key rotation/recovery policy phù hợp. Một key bị revoke hoặc Key Vault outage có thể ảnh hưởng khả năng truy cập encrypted storage, tác động trực tiếp tới Terraform init/plan/apply.

**Encryption at rest không thay RBAC**: caller có quyền đọc blob vẫn có thể nhận state plaintext qua API được phép.

### 17.5. Deny permissions và break-glass

Production nên:

- Tách identity bootstrap/storage administrator khỏi Terraform runtime.
- Gán container-scoped Blob Data Contributor nếu khả thi.
- Hạn quyền xóa container/account ở management plane.
- Giám sát role assignments và shared key/network policy changes.
- Có break-glass identity/timebound approval, không để credential cố định trong CI.
- Định kỳ diễn tập read-only restore/test backend availability bằng snapshot/test clone an toàn.

## 18. Private Endpoint và private DNS cho remote state

### 18.1. Vì sao backend cần network path?

Terraform init/plan/apply cần kết nối HTTPS tới **Blob endpoint** của Azure Storage. Nếu storage account chỉ chấp nhận private network, một Microsoft-hosted agent mặc định ở internet có thể **không nằm trong VNet**, dù pipeline có Azure service connection và data role hợp lệ.

**Có token + có RBAC chưa đủ** nếu network policy chặn.

### 18.2. Azure Blob FQDN

Public endpoint thường có dạng:

~~~text
https://<storage-account>.blob.core.windows.net
~~~

Khi dùng Private Endpoint, client vẫn dùng FQDN thông thường; DNS nội bộ phân giải qua private DNS zone:

~~~text
privatelink.blob.core.windows.net
~~~

Không thay storage account hostname bằng raw private IP để “vượt DNS”, vì TLS hostname validation và service routing có thể lỗi.

### 18.3. Mô hình mạng

~~~mermaid
flowchart LR
    AGENT["Terraform agent<br/>inside approved VNet"] --> DNS["VNet DNS resolver"]
    DNS --> PE["Private Endpoint<br/>Blob service"]
    PE --> SA["Azure Storage account<br/>tfstate container"]
    AGENT --> ID["Microsoft Entra token endpoint"]
    AGENT --> ARM["ARM API for provider resources"]
    SOC["Azure Monitor"] -. "storage logs" .-> SA
~~~

Cần xem đồng thời:

- Egress agent tới Azure Storage Blob private endpoint.
- Private DNS zone link và DNS forwarding nếu dùng hub-and-spoke.
- Entra token acquisition path.
- Azure Resource Manager endpoints cho provider.
- VNet route tables, NSG, Azure Firewall/NAT, proxy.
- Region/cross-subscription network design.

### 18.4. Microsoft-hosted vs self-hosted agents

| Agent | Khi storage chỉ private |
|---|---|
| Microsoft-hosted agent mặc định | Thường **không** kết nối trực tiếp VNet private endpoint |
| Self-hosted agent trong VNet | Có thể dùng private DNS/routing nếu cấu hình đúng |
| Managed DevOps Pools/agent networking capabilities được hỗ trợ | Kiểm tra khả năng VNet injection theo sản phẩm/plan |
| Local developer qua VPN/ExpressRoute | Có thể nếu DNS và routing về VNet đúng |

Không mở storage public access cho cả internet chỉ để một pipeline bắt đầu chạy. Chọn agent/network design đúng, hoặc cân nhắc firewall allowlist có governance nếu policy cho phép.

### 18.5. Checklist network

1. Storage account public network access setting.
2. Private Endpoint Blob service tồn tại và connection approved.
3. Private DNS zone **privatelink.blob.core.windows.net** đã link đúng VNet.
4. Agent thực resolve storage account FQDN ra IP mong muốn.
5. Firewall/NSG/routes/proxy cho HTTPS đi qua.
6. Entra token endpoint reachable.
7. Role Storage Blob Data Contributor đúng principal.
8. Terraform backend không vô tình dùng shared key flow bị disable.
9. Azure Monitor diagnostics có thể gửi logs tới destination đã duyệt.
10. Failures được phân loại network/TLS vs 403 RBAC.

### 18.6. Private Endpoint của Blob khác File/Queue/Table

Azure Storage có nhiều subservices như Blob, File, Queue, Table. Terraform **azurerm backend** lưu state trên **Blob service**, nên Private Endpoint cần phục vụ đúng **Blob subresource** (và các endpoints bổ sung nếu workflow dùng dịch vụ khác). Không cho rằng File endpoint private đã đủ.

## 19. OIDC/workload identity federation cho Terraform CI/CD

### 19.1. Mục tiêu

Một pipeline mỗi ngày chạy **terraform init/plan/apply**. Nếu lưu Storage account key hoặc một service principal password lâu hạn trong CI variables, credential có thể bị lộ bởi logs, untrusted PR code hoặc người có quyền quản trị pipeline.

**OIDC federation** cho CI identity lấy short-lived Entra token theo claims được trust mà không phải giữ client secret lâu hạn. Nhiều môi trường hỗ trợ:

- Azure DevOps Azure Resource Manager service connection với Workload Identity Federation.
- GitHub Actions OIDC với federated identity credential.
- Azure-hosted runner dùng managed identity.
- Các hệ thống khác khi backend hỗ trợ credential exchange tương ứng.

### 19.2. Điều kiện chính

- Terraform CLI/backend azurerm version hỗ trợ **use_oidc** và Entra blob auth.
- Federated identity credential khớp issuer/subject/audience do CI platform phát.
- Entra app/service principal hoặc user-assigned managed identity được tạo đúng.
- Storage account/container gán **Storage Blob Data Contributor** cho principal đó.
- Terraform provider có quyền riêng để plan/apply Azure resources.
- Agent network tới Blob/ARM/Entra endpoints.
- Pipeline chỉ được cấp OIDC token theo source trust/branch/resource authorization.
- Backend config và variables không lưu static client secret/SAS.

### 19.3. Backend block theo OIDC

Một mẫu **backend configuration** cho runtime đã hỗ trợ OIDC:

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-iac-state-prod"
    storage_account_name = "stexampleiacprod001"
    container_name       = "tfstate"
    key                  = "orders/prod/app.tfstate"
    use_azuread_auth     = true
    use_oidc             = true
  }
}
~~~

Client ID, tenant ID, subscription ID và OIDC token/request parameters được CI platform/credential flow cung cấp theo backend version. **Đừng trộn use_cli=true trong ví dụ local với OIDC setup này rồi mặc định backend chọn đúng phương thức**.

### 19.4. Azure DevOps service connection cần xác minh

Với Azure DevOps:

1. Tạo **Azure Resource Manager service connection** sử dụng Workload Identity Federation theo hướng dẫn tổ chức.
2. Hạn subscription/resource group/resource scope cần thiết.
3. Bảo vệ connection bằng pipeline permissions và approvals/checks.
4. Cấp Blob data role trên state container cho đúng service principal.
5. Cấp provider resource permissions theo tầng khác.
6. Trong job được duyệt, đưa **federated token và principal metadata** vào Terraform backend bằng cơ chế được backend version hỗ trợ.
7. Không echo ID token hoặc access token ra logs.
8. Chạy init/plan từ branch tin cậy; apply có review gate.
9. Kiểm tra backend identity thật qua audit và role assignments.

**Quan trọng:** Có AzureCLI@2 task login qua một service connection **không tự bảo đảm** Terraform backend được cấp đúng OIDC token hoặc dùng được service-principal login trong Azure CLI mode. Cần kiểm tra **Terraform azurerm backend auth docs** của release và cách chuyển token/metadata tương ứng. Mẫu pipeline ở mục sau thể hiện các bước an toàn, không giả vờ “azureSubscription” tự biến mọi backend CLI auth thành quyền hợp lệ.

### 19.5. GitHub Actions OIDC

GitHub OIDC cũng cần:

- Repository/environment/branch subject phù hợp.
- Workflow có **id-token: write** chỉ khi cần.
- Azure login/OIDC setup theo action/tool version.
- Principal có Azure Blob Data Contributor cho state.
- Provider credentials và subscription được tách chính xác.
- Protected environments/required reviewers cho production.

Không đặt role backend prod trên identity mà mọi PR từ fork đều có thể impersonate.

## 20. CI/CD pipeline pattern với Terraform remote state

### 20.1. Ba tầng cần tách

| Tầng | Mục đích | Quyền |
|---|---|---|
| **PR static validation** | fmt/validate/module tests | Không cần quyền đọc production state |
| **Trusted plan** | Đọc remote state + Azure resources, lập diff | Blob data read/write lease và provider read phù hợp |
| **Approved apply** | Thực thi diff, ghi state | Blob Data Contributor + provider write/role theo nhiệm vụ |

Terraform plan thường cần state lock (trừ một số chế độ), nên ngay cả plan job cũng có thể cần quyền lease/write trên state blob. Không cho rằng **Storage Blob Data Reader** là đủ cho mọi remote plan.

### 20.2. Static validation PR không cần init backend thật

Một PR job có thể:

~~~bash
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate -no-color
~~~

Điều này có thể tải provider/modules nếu chưa cache nhưng **không cần truy cập production remote state**, giúp giảm blast radius của untrusted source. Với providers/modules private, vẫn phải thiết kế feed credentials theo trust boundary.

### 20.3. Trusted plan job

Trong một job đã được cấp đúng federation/managed identity, network và backend config:

~~~bash
terraform init \
  -input=false \
  -backend-config=backend.prod.hcl

terraform validate -no-color

terraform plan \
  -input=false \
  -lock-timeout=5m \
  -out=plan.bin
~~~

**plan.bin là sensitive artifact**. Nếu lưu để apply sau approval, cần encryption, giới hạn download/access, ràng buộc run ID/commit/TTL và lifecycle. Không chạy **terraform show -json plan.bin** rồi in toàn bộ vào public PR comments.

### 20.4. Approved apply

Khi được duyệt, apply **chính binary plan** từ trusted run tương ứng để hạn chế việc code/input thay đổi giữa plan và apply:

~~~bash
terraform apply \
  -input=false \
  -lock-timeout=5m \
  plan.bin
~~~

Cần lưu ý saved plan có thể không còn phù hợp nếu remote state đã đổi; Terraform có thể báo **stale plan**. Không bỏ qua điều này bằng -lock=false hoặc force-unlock. Hãy re-plan với source/approval mới.

### 20.5. Không commit credentials và plans

Trong Git repository thường cần ignore:

~~~text
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
plan.bin
crash.log
crash.*.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
~~~

**.terraform.lock.hcl** là dependency selection lockfile và **thường nên được commit** để pin provider selections/checksums; đừng nhầm nó với **Terraform state lock** hoặc Blob lease. Tùy quy trình, giữ lockfile trong source control và review mỗi lần thay providers.

### 20.6. Concurrency guard ngoài Terraform lease

Azure Pipelines/CI có thể serial hóa applies theo environment hoặc resource bằng deployment environment locks/checks/job concurrency, giảm các jobs cạnh tranh cùng state. Nhưng **Terraform Blob lease vẫn quan trọng** nếu người dùng có thể chạy từ máy local hoặc CI khác.

Guard tối thiểu:

- Chỉ một approved apply job cho một state key tại một thời điểm.
- Không dùng cùng blob key cho dev và prod.
- CI branch/permission checks không cho PR tự apply prod.
- Có alert khi apply giữ lock quá lâu.
- Có runbook kiểm tra stale lock/force-unlock.
- Sau apply, xác minh state updated và drift policy.

## 21. Kiểm soát thay đổi backend qua Pull Request

### 21.1. Những file thay đổi nhạy cảm

- **backend.tf** hoặc backend HCL files.
- Terraform provider versions.
- **.terraform.lock.hcl**.
- CI workflow truyền backend config/credentials.
- Terraform modules tạo Storage account/RBAC.
- IAM role assignments/service connections.
- Network private endpoint/firewall của state account.
- Retention/versioning/diagnostic settings.

Một PR chỉ đổi **key = "orders/prod/app.tfstate"** sang một key khác có thể nguy hiểm như sửa hàng trăm Azure resources. Người review cần hiểu đó là **state migration**, không phải đổi tên tùy ý.

### 21.2. Thay đổi state key cần quy trình riêng

Trước khi merge:

1. Xác định từ key cũ sang key mới, owner và lý do.
2. Xác minh state hiện tại và source of truth.
3. Freeze apply writers.
4. Backup state secure.
5. Migrate bằng Terraform-supported flow.
6. Xác minh resource address count và no unexpected change plan.
7. Cập nhật CI/agents/approvals.
8. Giữ recovery point theo retention.
9. Chỉ mở lại apply sau khi hoàn tất.

### 21.3. Đừng dùng default backend ngầm định cho prod

Nếu pipeline không tìm thấy **backend.prod.hcl**, không tự fallback sang local state hoặc backend dev. **Fail fast** với log chỉ nêu file/config thiếu, không in credentials.

### 21.4. Có cần commit backend.hcl không?

File chỉ chứa resource group, storage account, container, key và các flags **không nhạy cảm** có thể được quản lý qua Git theo governance. Tuy nhiên một tổ chức vẫn có thể coi infrastructure coordinates là sensitive metadata; lúc đó dùng protected config library/templates. **Không bao giờ commit account keys/SAS/client secrets**.

## 22. Drift, import và sửa state có kiểm soát

### 22.1. Drift là gì?

Drift xảy ra khi actual Azure resource đã bị sửa ngoài Terraform hoặc state không còn khớp thực tế. Ví dụ platform operator đổi App Service plan qua Azure Portal, nhưng Terraform configuration vẫn giữ SKU cũ.

**terraform plan** có thể phát hiện diff sau khi refresh state/provider read, nhưng không phải mọi external change đều được phát hiện tức thì hoặc được biểu diễn đầy đủ bởi provider.

### 22.2. State loss khác infrastructure loss

- **Mất state**: resources Azure có thể vẫn tồn tại, nhưng Terraform không biết mappings.
- **Mất resource**: state có thể vẫn ghi địa chỉ của tài nguyên không còn.
- **Lệch state**: state có old attributes/resource IDs.
- **Out-of-band change**: Azure resource vẫn tồn tại nhưng bị đổi ngoài IaC.

Không xử lý mọi trường hợp bằng **terraform destroy** rồi apply mới.

### 22.3. Khi nào dùng terraform import?

Nếu Azure resource tồn tại nhưng state không quản lý, có thể cần **terraform import** hoặc **import blocks** theo Terraform version. Trước khi import:

1. Xác định resource ID thật và resource address mong muốn.
2. Kiểm tra state key hiện tại có mapping trùng không.
3. Đảm bảo import không làm Terraform quản lý cùng resource từ hai state khác nhau.
4. Review provider resource schema.
5. Import trong change window có locking.
6. Chạy plan và giải quyết diff.
7. Ghi record về nguồn gốc/hậu quả.

**Import không thay code hoàn chỉnh**: Terraform cần configuration tương ứng để không đề nghị phá resource ở plan kế tiếp.

### 22.4. State commands nguy hiểm

| Lệnh | Tác dụng | Rủi ro |
|---|---|---|
| terraform state list | Xem addresses | Ít rủi ro thao tác, vẫn lộ metadata |
| terraform state show | Xem attributes | Lộ sensitive attributes |
| terraform state mv | Di chuyển resource address mapping | Sai mapping ảnh hưởng plan |
| terraform state rm | Bỏ resource khỏi state, resource có thể vẫn tồn tại | Resource thành unmanaged |
| terraform import | Gắn existing resource vào address | Duplicate management nếu sai |
| terraform force-unlock | Bỏ state lock | Concurrent writes |
| terraform state pull | Xuất raw state | Data exposure |
| terraform state push | Ghi raw state | Data corruption nếu dùng sai |

Các lệnh ghi state cần approval, backup, owner và post-change plan. Không chạy thử trên production để học cú pháp.

## 23. Terraform state dưới góc nhìn bảo mật chuỗi cung ứng

Terraform HCL là cấu hình triển khai nhưng modules/providers và external data sources có thể chạy code/đọc tài nguyên nhạy cảm. Pipeline IaC không thể chỉ dựa vào blob security.

### 23.1. Trust chain

~~~mermaid
flowchart TD
    GIT["Git commit + review"] --> MOD["Terraform modules/providers"]
    MOD --> PLAN["Plan artifact + approval"]
    PLAN --> APPLY["Approved apply job"]
    APPLY --> ARM["Azure live resources"]
    APPLY --> BLOB["Azure Blob remote state"]
    ID["OIDC/managed identity"] --> APPLY
    RBAC["Blob data + provider RBAC"] --> APPLY
    AUDIT["Logs/alerts/provenance"] -. "observe" .-> BLOB
~~~

### 23.2. Kiểm soát providers/modules

- Pin provider versions trong required_providers và commit **.terraform.lock.hcl**.
- Chạy **terraform init -lockfile=readonly** trong CI khi policy yêu cầu không tự đổi lockfile.
- Dùng trusted Terraform module registries/sources, pin module versions/commits.
- Review thay đổi remote modules, tránh branch HEAD không pin trong production.
- Không đưa access tokens vào source URLs hay backend configs.
- Giới hạn network egress/identity của CI runners.
- Tách PR validation khỏi approved apply.
- Scan IaC policy violations, secrets và unsafe network/resource configs.
- Xác nhận source commit/run plan trước apply.

### 23.3. Attacker có thể sửa gì nếu lấy được state access?

Một principal có data-plane write vào state blob có thể:

- Đọc sensitive attributes đã lưu.
- Ghi/xóa state, gây mất resource mappings.
- Gây lock/availability issues.
- Làm cho plan áp sai nếu state bị chỉnh sửa.
- Che dấu một số thay đổi trong góc nhìn Terraform.

Vì vậy **Storage Blob Data Contributor** đối với production state là quyền nhạy cảm, không chỉ “quyền để upload một file”.

### 23.4. Phát hiện và ứng cứu state tampering

Khi nghi state bị sửa không được phép:

1. Freeze CI applies.
2. Kiểm tra storage logs/role changes.
3. Bảo vệ evidence và phiên bản blob trước đó.
4. Kiểm tra principal, IP, source commit và pipeline run.
5. So Terraform state lineage/serial và Azure live inventory một cách bảo mật.
6. Revoke compromised identity/credential theo incident runbook.
7. Restore/reconcile state theo approval.
8. Chạy plan trong môi trường có kiểm soát.
9. Kiểm tra có secrets bị lộ từ state, rotate khi cần.
10. Bổ sung detection/least privilege/network controls.

Không tự phục hồi một bản state cũ rồi cho phép apply production ngay khi chưa đánh giá các Azure resources đã thay đổi.


## 24. Chia sẻ state và bảo vệ dữ liệu xuất từ Terraform

### 24.1. terraform_remote_state không phải secret isolation

Terraform **terraform_remote_state** data source cho phép một stack lấy outputs từ state khác. Tuy giao diện chỉ hiển thị outputs, quyền backend có thể cho phép đọc **toàn bộ state snapshot** chứa dữ liệu nhạy cảm.

Nếu cần xuất một vài giá trị không nhạy cảm giữa stacks, cân nhắc:

- Azure App Configuration cho non-secret configuration.
- Azure Key Vault cho secrets.
- ARM resource IDs theo naming/lookup/data sources có quyền hạn phù hợp.
- Pipeline artifacts/contract manifest được bảo vệ và không chứa secrets.
- Khả năng publishing outputs đã chọn trong một data store có data-plane RBAC hẹp.

Không cấp **Storage Blob Data Reader** trên toàn production state chỉ để một stack dev đọc một URL.

### 24.2. Plan files và crash logs cũng cần bảo vệ

**terraform plan -out=plan.bin** có thể chứa sensitive values/context. Terraform debug logs (TF_LOG) có thể chứa request/response details. Artifact của CI và crash logs cần bảo vệ như state:

- Restricted retention, access và download permissions.
- Không publish plan.bin như artifact public.
- Không in raw **terraform show -json** trong PR comments.
- Bật redaction và hạn debug level.
- Nếu lộ state/plan, phân loại incident và rotate impacted credentials.

### 24.3. Quy tắc xuất dữ liệu từ một state cho stack khác

| Nhu cầu | Cách phù hợp | Điều cần tránh |
|---|---|---|
| Stack app cần subnet ID | Data source ARM/approved output contract | Cấp quyền đọc toàn network state nếu không cần |
| App runtime cần API secret | Managed identity + Key Vault | Đọc Terraform state để lấy secret |
| CI cần thông tin môi trường | Secure non-secret config manifest | Paste raw tfstate vào pipeline variables |
| Stack khác cần storage endpoint | Azure resource data source/App Configuration | Public state blob |
| Điều tra state corruption | Authorized encrypted backup/forensics | Gửi state JSON qua chat/ticket |
| Rollback đã được duyệt | Blob versions + Terraform reconciliation | Copy state cũ đè khi còn apply |

Khi publish selected outputs ra một destination riêng, phải xét **data classification, audience, cập nhật/retention và permission** của destination đó. Không phải mọi Terraform output đều có thể xem là cấu hình công khai.

## 25. Troubleshooting backend azurerm

Remote state failure có thể đến từ **backend configuration, identity, RBAC, network, storage metadata, lock hoặc Terraform CLI**. Tìm đúng tầng trước khi sửa.

### 25.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Init báo container not found | Sai storage account/container hoặc chưa bootstrap | Azure CLI list container bằng Entra |
| Init báo blob state not found | First run chưa có state hoặc key sai | Xác minh key/lifecycle; không tạo JSON rỗng |
| 401 Unauthorized | Token thiếu/sai audience hoặc auth flow | Azure CLI/OIDC/managed identity/backend version |
| 403 AuthorizationPermissionMismatch | Không đủ Blob data-plane role | Principal + scope + role assignment |
| 403 do firewall | Agent ngoài allowed network | Public access/Private Endpoint/DNS/firewall |
| Shared Key bị từ chối | Account disable shared key nhưng backend đang dùng key flow | use_azuread_auth/identity method |
| 404 sai storage name | Backend coordinates nhầm | Backend HCL/ARM metadata |
| 409 LeaseAlreadyPresent / lock conflict | Job khác giữ lease hoặc stale lock | Active runs, lock metadata, -lock-timeout |
| 412 Precondition Failed | Lease/ETag/precondition conflict tùy operation | Concurrency và state version/lock |
| “Error acquiring state lock” | Active writer hoặc unreleased lock | Tìm job/actor, không force-unlock vội |
| State đang trống bất thường | Đổi key/workspace mà không migrate | So backend config trước/sau |
| Terraform đề nghị tạo lại toàn bộ resources | Sai state key hoặc migration failed | **STOP**, xác minh lineage/address |
| “Backend configuration changed” | Đã đổi backend HCL/flags | Chọn migrate hay reconfigure có chủ đích |
| Auth local OK, CI lỗi | CI identity khác developer | OIDC/MI principal, token, environment |
| Init OK nhưng plan 403 Azure resources | Backend đủ quyền, provider thiếu quyền | Provider subscription/RBAC |
| Init 403 Blob nhưng Azure Portal xem account OK | Chỉ có ARM read, thiếu blob data permission | Storage Blob Data Contributor |
| DNS trả public IP dù dùng Private Endpoint | Private DNS zone/link/forwarder sai | Resolve từ đúng CI runner |
| Terraform apply fail sau resource create | Provider/API/network/partial operation | State/live reconciliation, không xóa state |
| Blob versioning không thấy lịch sử | Feature chưa bật hoặc policy/lifecycle | Blob service properties, timestamps |
| Git lỡ chứa terraform.tfstate | Secret exposure | Contain repo, scan/rotate credentials |
| Shared backend account sắp bị xóa | Management lifecycle/lock thiếu | Stop ops, protect evidence, incident |

### 25.2. Quy trình điều tra 401 và 403

Một 403 thường dễ bị hiểu sai là thiếu quyền Azure Subscription Contributor:

1. Xác định lỗi từ **Azure Blob backend** hay **AzureRM provider**.
2. Xác định **storage account/container/key** đúng.
3. Xác định **principal object ID** thực của người/CI agent.
4. Kiểm tra backend auth mode **use_azuread_auth**, **use_cli** hoặc **use_oidc**.
5. Kiểm tra Azure role **Storage Blob Data Contributor** được gán đúng scope.
6. Kiểm tra role propagation/conditional access/tenant mismatch.
7. Kiểm tra storage account **allowSharedKeyAccess** và CLI backend support.
8. Kiểm tra firewall/publicNetworkAccess/private endpoint approval.
9. Từ **đúng host/runner**, resolve storage FQDN và kiểm tra HTTPS.
10. Đối chiếu Azure Storage diagnostic log và Azure Activity Log role changes.
11. Retest bằng metadata-only Blob operation trên **container lab** trước.
12. Ghi root cause; không dùng account key để bypass control khi không được phê duyệt.

### 25.3. Phân biệt lỗi network và RBAC

Hai runs dùng cùng principal/data role nhưng khác agents:

~~~text
Developer laptop via corporate VPN → terraform init OK
Microsoft-hosted agent (not in VNet) → terraform init Forbidden
~~~

Nguyên nhân có thể là network restriction dù token hợp lệ. Đổi sang self-hosted agent trong VNet với private DNS/route đúng có thể giải quyết; **không cần cấp Owner** hoặc public access toàn internet.

### 25.4. Đọc backend coordinates khi init báo state trống

Kiểm tra:

- Resource group của **storage account backend**, không phải App Service resource group.
- Storage account name không có typo.
- Container tồn tại và private.
- Key đúng **orders/prod/app.tfstate**, không phải **orders/dev/app.tfstate**.
- Terraform workspace hiện tại.
- Backend config đã được re-initialize khi đổi.
- Identity có quyền đọc đúng container.
- Có previous state ở nguồn cần migrate không.

**Không chạy apply** nếu plan đề nghị tạo resources đã tồn tại mà nguyên nhân là state missing.

### 25.5. Khi lock conflict

Nếu pipeline A đang apply và B không acquire lease:

- Chờ hoặc queue B với **-lock-timeout** theo policy.
- Hỏi owner A và xem Azure DevOps run status.
- Nếu A treo, quyết định cancel/terminate theo runbook.
- Đợi backend giải phóng lease nếu operation còn hoạt động.
- Chỉ force-unlock sau khi chắc không còn writers, có approval và đã ghi lock ID.
- Dùng plan để kiểm tra drift sau unlock.
- Bổ sung CI concurrency/agent timeout kiểm soát tranh chấp lần sau.

### 25.6. Lỗi plan stale

Một saved plan được tạo từ state serial N. Job khác apply làm state sang N+1; apply plan cũ có thể bị Terraform từ chối. Đây là **bảo vệ đúng**, không phải lỗi cần bypass. Re-plan từ commit/variables đã được review, tạo approval mới nếu policy yêu cầu. Không quay state về N chỉ để dùng binary plan cũ.

### 25.7. Lỗi sau storage account key rotation

Nếu backend legacy dùng access key, rotation có thể khiến các automation giữ key cũ mất quyền. Hướng lâu dài là Entra auth. Trong sự cố:

1. Xác định thực sự backend đang dùng key, SAS hay Entra.
2. Đọc rotation timeline/Key Vault references theo kênh được duyệt.
3. Không in key.
4. Chuyển/cập nhật secrets qua approved secure variable store.
5. Retest backend access và sau đó lập kế hoạch loại bỏ key flow.
6. Kiểm tra các bản sao credential cũ trong Git/CI logs/workspaces.

## 26. Monitoring và audit cho remote state

### 26.1. Ba nguồn cần kết hợp

| Nguồn | Quan sát gì? | Giới hạn |
|---|---|---|
| **Azure Storage Blob diagnostic logs** | Blob data-plane operations: read/write/delete/lease-related requests theo cấu hình | Không ghi mọi thay đổi Terraform code |
| **Azure Activity Log** | Storage account/network/IAM/diagnostic settings ARM changes | Không phải danh sách từng lần đọc state blob |
| **Terraform CI/apply logs** | Commit, runner, init/plan/apply outcome, state lock conflict | Không nên có raw state/credentials |

Microsoft Entra sign-in/workload telemetry và agent network logs cũng hữu ích khi điều tra token/Private Endpoint failure.

### 26.2. Bật diagnostics cho Blob service

Trong Azure Portal:

1. Mở Storage account backend.
2. Chọn **Monitoring → Diagnostic settings** hoặc **Blob service → Diagnostic settings** theo UI.
3. Chọn categories hỗ trợ như **StorageRead, StorageWrite, StorageDelete** cho Blob service.
4. Gửi logs tới Log Analytics workspace hoặc destination đã được platform/SOC duyệt.
5. Xác nhận category/destination/schema và retention.
6. Không lưu raw state JSON vào custom logs.
7. Bật cảnh báo nếu diagnostic settings hoặc access policies bị thay trái phép.

Diagnostic categories thường gắn với **Blob service resource** bên dưới storage account; không mặc định mọi category đều hiển thị khi tạo setting ở account root.

Ví dụ CLI **chỉ đọc** để xem categories:

~~~bash
BLOB_SERVICE_ID="$SA_ID/blobServices/default"

az monitor diagnostic-settings categories list \
  --resource "$BLOB_SERVICE_ID" \
  --output table
~~~

### 26.3. Table schema của Log Analytics

Azure Storage resource-specific logs có thể xuất hiện ở **StorageBlobLogs** (khi đã cấu hình resource-specific destination mode), hoặc các event diagnostics trong **AzureDiagnostics** theo mode/tài nguyên. Tên fields/columns thay đổi theo schema.

Query khám phá:

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(24h)
| take 10
~~~

Nếu workspace chưa có bảng này, xem diagnostic setting/destination mode/ingestion lag. Không kết luận state không bị truy cập chỉ vì query table-not-found.

### 26.4. KQL: thống kê Blob operations

Nếu bảng **StorageBlobLogs** tồn tại với các cột tương ứng:

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(7d)
| summarize Requests = count()
    by OperationName, StatusCode
| order by Requests desc
~~~

Từ kết quả, phân biệt đọc/ghi/lease operations, 403, 409 lock conflict và thời gian tăng đột biến. **KQL chỉ là ví dụ cho schema phù hợp**; inspect bảng actual và sửa field names khi cần.

### 26.5. KQL: thất bại data-plane theo thời gian

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(24h)
| where toint(StatusCode) >= 400
| summarize Failures = count()
    by bin(TimeGenerated, 15m), OperationName, StatusCode
| order by TimeGenerated asc
~~~

Một 404 đơn lẻ khi kiểm tra state chưa tồn tại có thể là bước bình thường; một loạt 403 sau rotation identity mới là tín hiệu vận hành cần điều tra.

### 26.6. KQL: Azure Activity Log cho storage account

Chỉ khi Azure Activity Logs đã được route vào **AzureActivity** ở workspace:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where ResourceProviderValue =~ "MICROSOFT.STORAGE"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

Để kiểm tra **Azure role assignment** cần xem **Microsoft.Authorization** operations, có thể ở scope khác storage account; không chỉ lọc provider Storage.

### 26.7. Chỉ số vận hành

- Terraform **init success rate** theo environment.
- **Plan/apply duration**, queue wait và failure rate.
- **Lock acquire wait time**, lock conflict count.
- **Storage 401/403/409/429/5xx** theo agent/identity.
- Azure Storage service availability, latency và transactions.
- Blob storage capacity/versions/retention growth.
- Audit log ingestion/retention health.
- Number of **unexpected state readers/writers**.
- Pipeline changes đến backend config/role/network.
- Drift/plan unexpected changes count.
- Recovery drill success, RPO/RTO.

### 26.8. Alert khi có dấu hiệu xâm nhập

Những sự kiện cần ưu tiên:

1. Blob state bị đọc từ principal/source network không có trong inventory.
2. Storage Blob Data Contributor được gán trên scope rộng ngoài approval.
3. State blob bị delete/overwrite ngoài approved apply window.
4. Diagnostic settings bị tắt hoặc chuyển destination.
5. Shared Key access bị bật lại trái chính sách.
6. Public network access mở rộng không được duyệt.
7. Nhiều lock failures hoặc forced unlock events liên quan incident.
8. Terraform plan/apply từ commit/runner không được phê duyệt.
9. Provider/lockfile/backend config bị sửa bất thường.

Một BlobRead thành công không tự chứng minh exfiltration; hãy tương quan principal, CI run, storage key, IP, change ticket và sự kiện tiếp theo.

## 27. FinOps cho Terraform backend

### 27.1. Chi phí đến từ đâu?

| Thành phần | Ảnh hưởng |
|---|---|
| Storage account Blob | Dung lượng state và object versions |
| Replication LRS/ZRS/GRS/GZRS | Chi phí/durability theo tier/region |
| Data-plane operations | Read/write/list/lease/metadata requests |
| Versioning/soft delete | Số versions và retention của old state |
| Private Endpoint | Private Link connection và data processing theo bảng giá |
| Azure Monitor | Diagnostic ingestion, retention, query/alerts |
| CI agents | Terraform init/plan/apply runtime, queue/parallelism |
| Network/Firewall/NAT | Egress, VPN/ExpressRoute và supporting infrastructure |
| Backup/DR | Secondary copies, testing và vận hành |
| Security governance | Access reviews, scanning, recovery drills |

State file thường không lớn như data lake, nhưng chi phí **version history, logs, private endpoints và CI compute** có thể đáng kể khi hàng trăm stacks thay đổi liên tục.

### 27.2. Tính ví dụ operations

Giả sử có 40 stacks, mỗi stack chạy 2 plans/ngày và 1 apply/ngày:

~~~text
40 stacks × (2 plans + 1 apply)
= 120 Terraform operations/ngày
~~~

Đây **không phải 120 billable Blob transactions**. Một init/plan/apply có thể tạo nhiều read/list/lease/write/metadata calls, do backend implementation, retries và storage service responses. Đo Azure Storage metrics thực trước khi dự toán phí.

### 27.3. Quản lý version growth

Giả sử trung bình 20 state writes/ngày, mỗi version 2 MiB:

~~~text
20 writes/day × 2 MiB × 30 days
≈ 1,200 MiB of version data/month
~~~

Đây là phép tính gần đúng không tính compression, metadata, existing base blob, retries và growth. Nếu retention kéo dài một năm và nhiều stacks, version data có thể tăng. Đặt lifecycle/retention **không xóa recovery points cần thiết**. Test restore trước khi rút retention.

### 27.4. Không tối ưu chi phí bằng cách làm mất khả năng phục hồi

- Đừng tắt soft delete/versioning mà không có backup thay thế.
- Đừng bỏ Terraform locking để “chạy nhanh”.
- Đừng dùng anonymous blob/public network mở để tiết kiệm thời gian.
- Đừng gom mọi prod/dev states vào một container với quyền rộng chỉ để giảm số resources nếu security boundary quan trọng.
- Đừng xóa approved backup phiên bản cũ khi chưa biết RPO/incident retention.
- Đừng chạy plan liên tục mỗi phút nếu drift SLO không yêu cầu.
- Hạn duplicate CI runs, tận dụng queue/concurrency kiểm soát.
- Dùng budgets/tags/Cost Management cho backend resources và monitoring.

### 27.5. Lựa chọn redundancy

Chọn LRS/ZRS/GRS/GZRS từ **business continuity requirements**, service region availability, storage failover procedure và cost. Geo-redundant storage không tạo guarantee rằng Terraform state luôn nhất quán với Azure resources ở mọi thời điểm failover.

## 28. Quy trình lab end-to-end và tiêu chí nghiệm thu

### 28.1. Chuẩn bị

1. Tạo subscription/resource group lab được duyệt.
2. Tạo StorageV2 account riêng cho Terraform backend.
3. Disable anonymous blob access; ưu tiên Entra data-plane auth.
4. Gán Storage Blob Data Contributor cho lab identity ở scope phù hợp.
5. Tạo container **tfstate** private qua **--auth-mode login**.
6. Bật versioning và soft delete theo retention lab.
7. Kiểm tra CLI/Terraform versions và backend feature support.
8. Thiết kế một state key **orders/lab/app.tfstate**.
9. Đảm bảo không có Terraform apply khác trên key đó.
10. Không sử dụng secret production hoặc subscription production.

### 28.2. Terraform project

Tạo **backend.tf** với partial backend:

~~~hcl
terraform {
  required_version = ">= 1.6.0"
  backend "azurerm" {}
}
~~~

Tạo **backend.lab.hcl**:

~~~hcl
resource_group_name  = "rg-tfstate-lab"
storage_account_name = "stexampleiaclab001"
container_name       = "tfstate"
key                  = "orders/lab/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Tạo **main.tf** có một resource group đơn giản theo mục 8 hoặc một module chỉ yêu cầu **plan**. Cấu hình provider subscription ID với lab ID, không dùng production.

### 28.3. Init, validate và plan

~~~bash
terraform fmt -check -recursive
terraform init -backend-config=backend.lab.hcl
terraform validate
terraform plan -lock-timeout=2m
~~~

Ghi lại:

- Backend storage account/container/key (non-secret metadata).
- Identity đang chạy (principal alias/object ID đã được kiểm soát).
- Plan outcome.
- Network path.
- Storage Blob data role.
- Những logs/lease events quan sát được.

### 28.4. Apply nhỏ nếu được phê duyệt

Nếu lab owner cho phép:

~~~bash
terraform apply -lock-timeout=2m
~~~

Đọc kỹ plan trước xác nhận. Sau apply, kiểm tra metadata blob state tồn tại và tài nguyên lab được tạo theo dự kiến. Không xuất raw state JSON ra terminal.

### 28.5. Kiểm tra locking bằng hai terminal lab

- Terminal A chạy operation hợp lệ đang giữ lock trên **lab state**.
- Terminal B khởi chạy một plan/apply khác cùng key trong thời điểm A còn giữ lock theo kịch bản được owner thiết kế.
- Quan sát B chờ hoặc nhận lock conflict.
- Không dùng -lock=false hoặc force-unlock trong bước test.
- Khi A hoàn thành, B có thể retry/tiếp tục theo timeout policy.
- Ghi lock wait time và thông điệp lỗi đã sanitize.

**Không tạo tranh chấp trên production state** để học locking.

### 28.6. Thử thay đổi backend key có kiểm soát

Trên một bản lab hoàn toàn riêng, sao lưu an toàn rồi kiểm tra **terraform init -migrate-state** theo runbook. Không tự sửa key dev thành prod để xem Terraform làm gì.

### 28.7. Test negative permissions

- Identity A có Storage Blob Data Contributor → backend init/plan có thể hoạt động nếu provider/network permissions đáp ứng.
- Identity B chỉ có ARM Reader/Contributor mà không có Blob data role → backend blob access bị từ chối khi cần.
- Identity C chỉ có Storage Blob Data Reader → có thể đọc state nhưng thường không đủ write/lease cho plan/apply.
- Identity D có RBAC nhưng ngoài private network → network failure/403.
- Không cấp quyền mới tự động từ job runtime để vượt một negative test.

### 28.8. Thử recovery trên bản sao lab

1. Bật versioning và ghi ít nhất hai state versions hợp lệ qua Terraform operations.
2. Tạo backup/recovery point theo policy.
3. Chỉ trên **state clone hoặc sandbox** được duyệt, mô phỏng xóa/sai state.
4. Khôi phục candidate version qua Storage recovery process.
5. Chạy plan để xác minh resource mapping.
6. Ghi RPO/RTO, không paste state data.
7. Dọn lab theo owner/retention policy.

### 28.9. Báo cáo nghiệm thu mẫu

| Hạng mục | Kết quả kỳ vọng |
|---|---|
| Backend Storage account | Tồn tại, do platform/lab sở hữu |
| Container | Private, không anonymous access |
| Blob key | Unique per stack/environment |
| Backend authentication | Microsoft Entra ID |
| Runtime data role | Storage Blob Data Contributor đúng scope |
| CLI/provider subscription | Kiểm tra riêng |
| Terraform init | PASS |
| Terraform validate | PASS |
| Terraform plan | Expected diff/no unexpected resources |
| Lock test | Competing operation waits/fails safely |
| Backup | Versioning/soft delete configured |
| Recovery drill | Restore + plan validation trên clone |
| Network | Approved path, DNS/TLS valid |
| Audit | Blob diagnostic metadata available |
| Secrets in logs | None |
| Production resources changed | None |

Đây là **tiêu chí kỳ vọng**, không phải một run thực tế đã được thực hiện khi soạn bài.

## 29. Anti-patterns: những cách làm dễ phá state

| Anti-pattern | Hệ quả | Phương án an toàn |
|---|---|---|
| Commit **terraform.tfstate** vào Git | Lộ secrets/history, merge conflict | Azure remote state private + restricted backups |
| Dùng một blob key cho dev/prod | State collision và thao tác nhầm môi trường | Unique key/account/container per environment |
| Terraform app tự quản lý/destroy backend storage của chính nó | Mất nơi lưu state và recovery | Bootstrap backend tách vòng đời |
| Đặt account key trong backend.tf | Credential leakage qua Git/plan/.terraform | Entra auth + scoped RBAC |
| Lưu account key trong CI YAML | Bất kỳ PR/script có quyền có thể đọc | OIDC/managed identity + secure resources |
| Tin ARM Contributor tự có Blob Data Contributor | Init/plan 403 | Gán data-plane role riêng |
| Cấp Storage Blob Data Owner toàn subscription | Blast radius lớn | Container-scoped Data Contributor nếu khả thi |
| Tắt state lock khi gặp 409 | Concurrent writes, state corruption | Chờ, xem active jobs, lock timeout |
| Force-unlock khi job A đang apply | Hai writers cùng update state | Break-glass runbook sau khi xác minh |
| Upload JSON rỗng thành state blob | Backend parse lỗi / mất mapping | Để Terraform quản lý state lifecycle |
| Chuyển key mà dùng init -reconfigure thay migrate | Backend mới trống | Terraform init -migrate-state |
| Khôi phục state version cũ rồi apply ngay | State/live resources không khớp | Freeze → inspect → restore → plan |
| Chỉ bật GRS mà không có version history | Replicate cả state bị ghi sai | Versioning/soft delete + DR |
| Đặt active state dưới immutability policy cứng | Không ghi hoặc lease được | Immutable archive riêng nếu cần |
| Public anonymous blob access | State lộ ra internet | Disable anonymous access |
| Storage public network cho mọi IP để CI chạy | Exposed state endpoint | Private Endpoint/approved agent egress |
| Kết nối Blob bằng private IP thay FQDN | TLS/DNS lỗi | Dùng FQDN và private DNS |
| Coi Terraform workspace là security boundary | Principal đọc được state khác | Separate RBAC scopes/containers/accounts |
| Dùng terraform_remote_state để lấy API key | Đọc state rộng hơn cần thiết | Managed identity + Key Vault |
| Publish plan.bin public | Rò sensitive values | Secure short-lived artifact |
| Debug bằng TF_LOG TRACE rồi đưa lên ticket | Có thể lộ token/state/HTTP metadata | Sanitized logs và incident protocol |
| Provider và backend dùng sai subscriptions | Có thể tạo/sửa sai tài nguyên | Explicit IDs, guard và approval |
| Bỏ qua drift sau restore | State không còn khớp live resources | Import/reconcile + plan |
| Bỏ qua RBAC propagation | 403 và retry storm | IAM validation, bounded retry |
| Không review backend.tf changes | Thay state key/identity trái ý muốn | Code owners, PR gates |
| Chỉ theo dõi Azure Activity Log | Bỏ sót Blob data-plane operations | Storage Blob diagnostics |
| Tắt versioning để tiết kiệm mà không có backup | Mất recovery points | RPO/retention/FinOps |
| Reuse self-hosted agent cho untrusted PR và prod apply | Credential/runner compromise | Isolated trust boundaries |
| Apply saved stale plan bằng cách bỏ lock | Phá state assumptions | Re-plan/re-approve |

## 30. Bảng lựa chọn kiến trúc backend

### 30.1. Local hay remote?

| Tình huống | Lựa chọn | Lý do |
|---|---|---|
| Bài tập Terraform ngắn trên máy cá nhân, không shared | Local state có thể tạm đủ | Ít phức tạp, chấp nhận rủi ro giới hạn |
| Nhiều người cùng quản lý Azure resources | Azure Storage remote backend | Cộng tác, lock, audit và recovery |
| Pipeline CI/CD triển khai môi trường shared | Azure Storage remote backend | Source of truth tập trung |
| PR chưa được tin cậy chỉ cần fmt/validate | Init backend=false cho validation | Không cần prod state permission |
| Production compliance cao | Backend cô lập account/subscription/private network | Blast radius thấp, audit |
| Cross-region DR quan trọng | Redundancy + versioning + recovery drill | Replication không thay history |
| Stack ephemeral không nhạy cảm | Keys/workspaces theo lifecycle được kiểm soát | Nhanh nhưng không phải boundary RBAC |
| Nhiều teams có security ownership khác nhau | Containers/accounts và identities tách | Least privilege |
| App runtime cần secret | Key Vault, **không** remote state | Secret access isolation |

### 30.2. Chọn cách auth

| Bối cảnh | Cách gợi ý | Điều kiện |
|---|---|---|
| Developer local lab | Azure CLI user login + Entra blob auth | Backend version, Blob data role |
| Self-hosted agent Azure VM | Managed identity | Identity/network/RBAC đúng |
| Azure DevOps hoặc GitHub trusted CI | OIDC federation | Pipeline/service-connection identity và backend support |
| Legacy automation | Service principal certificate/secret được quản lý | Có rotation/secure storage, kế hoạch chuyển đổi |
| Account key/SAS | Chỉ tương thích legacy với approval | Credential handling cực chặt, không commit |
| PR từ fork | Không truy cập prod backend | Chỉ static validation |

### 30.3. Chọn scope isolation

**Nên xem storage account/container/key là ba cấp tổ chức khác nhau:**

- **Account**: network, encryption, redundancy, management boundary.
- **Container**: có thể phân tách Blob data-plane RBAC theo scope được hỗ trợ.
- **Blob key**: định danh state riêng nhưng **không tự là quyền truy cập**.

Nhu cầu “team app chỉ được đọc một key” không mặc định giải quyết được bằng việc đặt prefix tên. Cần thiết kế RBAC và resource isolation phù hợp.

### 30.4. Tách state càng nhỏ càng tốt?

Không tuyệt đối. Tách quá nhỏ dẫn tới:

- Nhiều dependencies giữa stacks.
- Phức tạp tham chiếu outputs.
- Nhiều CI pipelines, nhiều approvals.
- Khó đồng bộ cross-stack changes.

Tách quá lớn dẫn tới:

- Một plan thay cả network/DB/app.
- Nhiều người tranh cùng state lock.
- Role cần quyền rất rộng.
- Blast radius lớn khi apply sai.

Chọn boundaries theo **ownership, deploy cadence, security, concurrency và dependency graph**, không chỉ theo số files.

## 31. Checklist production

### 31.1. Bootstrap và thiết kế

- [ ] Backend storage được bootstrap **trước** stacks cần nó.
- [ ] Storage RG/account không do cùng stack tự destroy.
- [ ] Storage name/container/key đúng quy tắc, non-secret coordinates.
- [ ] Có unique state key cho mỗi stack/môi trường.
- [ ] Prod/dev/staging isolation đủ theo threat model.
- [ ] Có owner, tags, platform change governance.
- [ ] Có tài liệu backend identifiers và recovery contacts.
- [ ] Không có state plaintext trong Git/CI artifacts.
- [ ] Chọn StorageV2/SKU/region/redundancy theo SLO/RPO/RTO.

### 31.2. Identity và RBAC

- [ ] Backend dùng Entra auth (OIDC/managed identity/Azure CLI) nếu hỗ trợ.
- [ ] Không lưu Storage account key/SAS trong backend config.
- [ ] Runtime/CI principal thực đã được xác minh bằng object ID.
- [ ] Storage Blob Data Contributor ở scope thấp nhất thích hợp.
- [ ] Provider permissions được xác định **riêng** backend permissions.
- [ ] CI plan/apply chỉ dùng trusted identities.
- [ ] Untrusted PR jobs không có production state access.
- [ ] IAM role assignment và Shared Key policy được audit.
- [ ] Có runbook propagation/token expiry/client ID mismatch.
- [ ] Có quy trình revoke và rotate credentials nếu exposure.

### 31.3. Blob service và network

- [ ] Container private và anonymous public access disabled.
- [ ] HTTPS/TLS policy phù hợp.
- [ ] Shared Key disabled nếu toolchain/auth hoàn toàn tương thích.
- [ ] Firewall/public network/private endpoint được phê duyệt.
- [ ] DNS **privatelink.blob.core.windows.net** đúng từ CI agent.
- [ ] Agent egress tới Entra/ARM/Blob đáp ứng.
- [ ] Private Endpoint dùng Blob subresource đúng.
- [ ] Không nối thẳng private IP hoặc disable TLS.
- [ ] Blob versioning được bật nếu policy yêu cầu.
- [ ] Blob soft delete/container recovery policy được định nghĩa.
- [ ] Không áp immutability policy phá state write/lease.
- [ ] Resource delete protection/ARM lock được xem xét.
- [ ] Có recovery drill và break-glass account/roles.

### 31.4. Terraform và CI/CD

- [ ] Terraform CLI/backend azurerm version được pin/kiểm thử.
- [ ] .terraform.lock.hcl được quản lý đúng.
- [ ] Backend config không dùng var/local interpolation bất hợp lệ.
- [ ] PR có fmt/validate nhưng không cần prod backend.
- [ ] Plan dùng đúng backend key/provider subscription.
- [ ] Apply chỉ từ approved run và plan/commit phù hợp.
- [ ] CI concurrency/lock timeout rõ.
- [ ] Không dùng -lock=false với shared state.
- [ ] Force-unlock chỉ theo break-glass runbook.
- [ ] Binary plans được bảo vệ như state.
- [ ] Không log raw state, full plan JSON, sensitive outputs.
- [ ] Backend key changes có migration playbook riêng.
- [ ] Sau migration có no unexpected changes plan.
- [ ] Có runbook import/reconcile cho drift/state loss.
- [ ] Không apply khi state rỗng bất ngờ.

### 31.5. Monitoring, FinOps và DR

- [ ] Storage Blob diagnostics được bật theo policy.
- [ ] Activity Log cho ARM/network/IAM changes có retention.
- [ ] Log workspace/table schema được kiểm thử.
- [ ] Alert unexpected Blob read/write/delete, 403/409/429 spikes.
- [ ] Alert khi public access/Shared Key policy/diagnostic settings bị đổi.
- [ ] Có dashboard Terraform plan/apply/lock wait/queue failures.
- [ ] RPO/RTO và version retention được owner phê duyệt.
- [ ] Test phục hồi state trên sandbox/clone.
- [ ] Có state tampering/credential exposure incident response.
- [ ] Có budget và theo dõi storage versions/log ingestion/private endpoint.
- [ ] Không dọn state/backup trước khi policy cho phép.
- [ ] Có quy trình đổi Terraform/provider versions có kiểm soát.
- [ ] Có checklist stop-writers trước mọi restoration/migration.

## 32. Bài tập thực hành

### Bài 1: Vì sao cần remote state?

Hai developer cùng một Terraform repo, A đã apply nhưng B không có local state. Phân tích:

- Tại sao plan của B có thể nguy hiểm?
- Remote backend thay đổi tình hình thế nào?
- Blob lease có bảo đảm mọi tài nguyên Azure luôn nhất quán không?
- Những dữ liệu nào có thể bị lộ nếu commit local state vào Git?

### Bài 2: Bootstrap Azure Storage

Trên subscription lab:

1. Tạo RG backend riêng.
2. Tạo StorageV2 account với HTTPS/TLS và anonymous public disabled.
3. Gán Storage Blob Data Contributor cho lab principal.
4. Tạo container tfstate bằng **--auth-mode login**.
5. Bật versioning/soft delete theo policy.
6. Xác minh container private.
7. Giải thích vì sao backend RG không nên do Terraform app stack tự destroy.

### Bài 3: Viết backend azurerm

Tạo **backend.tf** và **backend.lab.hcl** với:

~~~text
resource_group_name = rg-tfstate-lab
container_name      = tfstate
key                 = orders/lab/app.tfstate
auth                = Microsoft Entra ID
~~~

Viết đầy đủ cú pháp HCL, giữ credentials ngoài file và chạy fmt/init/validate trên lab.

### Bài 4: Phân biệt backend và provider

Backend nằm trong **platform subscription**, app resources nằm trong **application subscription**. Vẽ hai nhóm permissions và identities. Giải thích vì sao Azure Contributor ở app subscription chưa chắc giúp terraform init backend thành công.

### Bài 5: Role scoped vào container

Gán Storage Blob Data Contributor ở container scope cho một workload lab thay vì toàn account (khi service/permissions hỗ trợ). Negative test một container khác và ghi kết quả.

### Bài 6: Terraform init migrate

Giả sử có local state với 5 resources demo:

1. Freeze writers.
2. Backup state an toàn.
3. Tạo remote backend rỗng đúng key.
4. Chạy **terraform init -migrate-state**.
5. Verify state list và blob metadata.
6. Chạy plan không có unexpected recreate.
7. Nêu khi nào không dùng **-reconfigure** để migrate.

### Bài 7: Collision giữa hai môi trường

Cả dev và prod vô tình có:

~~~text
key = orders/shared/app.tfstate
~~~

Giải thích failure mode và thiết kế naming/RBAC guard để ngăn PR đổi key hoặc dùng nhầm backend. Không chạy apply để tái hiện trên production.

### Bài 8: Lock conflict

Hai Terraform jobs truy cập cùng state. Job A giữ lock, job B báo 409.

- Dùng **-lock-timeout=5m** khi thích hợp.
- Kiểm tra run A.
- Khi nào phải đợi?
- Khi nào mới dùng **terraform force-unlock**?
- Vì sao **-lock=false** nguy hiểm?

### Bài 9: Plan stale

Một trusted plan được lưu lúc state serial N, nhưng job khác đã apply và nâng state lên N+1. Tại sao phải re-plan/re-approve, không khôi phục state cũ chỉ để apply được plan?

### Bài 10: Versioning và DR

Thiết kế backup cho state 2 MiB, 20 writes/ngày, retention 30 ngày. Tính xấp xỉ data growth, chọn versioning/soft delete/replication, và lập recovery drill trên bản sao.

### Bài 11: Lỗi Private DNS

Self-hosted CI runner trong VNet không resolve được **storage.blob.core.windows.net** qua private endpoint.

- Xác định private DNS zone.
- Kiểm tra VNet link/forwarder.
- Xác minh FQDN/TLS path.
- Kiểm tra ARM vs Blob connectivity.
- Không dùng raw private IP hay mở public internet.

### Bài 12: OIDC trong CI

Thiết kế service connection federation cho trusted apply. Ghi:

- Principal/client ID, tenant, trust claims.
- Blob data role và provider permissions.
- Source branch/approval guard.
- Backend OIDC support/version.
- Vì sao không commit client secret.
- Cách ngăn untrusted PR lấy prod state.

### Bài 13: Sensitive outputs

Terraform có **random_password** hoặc output connection string **sensitive=true**. Giải thích vì sao state blob vẫn nhạy cảm, vì sao không dùng **terraform_remote_state** như API đọc secret, và phương án managed identity/Key Vault thay thế.

### Bài 14: CI tách validate/plan/apply

Thiết kế ba stages: PR static validation (backend=false), trusted plan, approved apply. Giải thích permissions của từng job, plan artifact retention và lock controls.

### Bài 15: State tampering

SOC phát hiện một principal lạ ghi state blob và thay role assignment:

1. Dừng applies.
2. Thu thập Blob diagnostics/Activity Log/CI run evidence.
3. Xác minh storage RBAC.
4. Chọn blob version recovery point.
5. Reconcile Azure resources.
6. Rotate credentials lộ từ state nếu có.
7. Postmortem/control improvements.

### Bài 16: Drift và import

Một Azure Resource Group được tạo ngoài Terraform, nhưng ứng dụng muốn quản lý nó trong stack. Viết kế hoạch import/block với source ID/address, review state, locking, plan và approval. Tránh quản lý cùng resource từ hai states khác nhau.

### Bài 17: Gia tăng chi phí

So sánh một account chung nhiều states với ba accounts dev/staging/prod. Tính yếu tố storage transactions, versions, redundancy, Private Endpoints, log ingestion và blast radius. Lý giải lựa chọn theo cost **và** security, không chỉ số resource.

### Bài 18: Khôi phục sai version

Một operator muốn restore state bản hôm qua nhưng hôm nay có ba resources được tạo. Tại sao không được ghi đè ngay? Nêu trình tự freeze, compare, restore-on-clone, plan, import/reconcile và authorization.

## 33. Câu hỏi tự kiểm tra

1. Terraform state lưu những thông tin gì?
2. Vì sao state không phải Git configuration file bình thường?
3. Local backend có vấn đề gì khi nhiều người cùng apply?
4. Azure azurerm backend sử dụng dịch vụ Azure nào để lưu state?
5. Storage account, container và blob key khác nhau thế nào?
6. Dấu slash trong blob key có tạo folder security boundary không?
7. Terraform backend khác azurerm provider như thế nào?
8. Vì sao backend auth và provider auth cần kiểm tra riêng?
9. Một identity có Azure Contributor có chắc đọc/ghi Blob được không?
10. Role **Storage Blob Data Reader** có đủ để Terraform lock/write state không?
11. Vì sao **Storage Blob Data Contributor** có tính nhạy cảm cao?
12. Khi nào cần scope RBAC tới container thay vì account?
13. Azure CLI login khác OIDC CI authentication ở đâu?
14. Tại sao không commit access_key/SAS/client_secret trong backend.tf?
15. **use_azuread_auth** có ý nghĩa gì?
16. Khi nào dùng **use_cli** và khi nào dùng **use_oidc**?
17. Vì sao backend block không chấp nhận **var.state_key**?
18. Partial backend config giúp giải quyết vấn đề gì?
19. Vì sao backend storage phải được bootstrap trước?
20. Tại sao không để stack Orders API tự destroy storage state?
21. **terraform init** làm những gì?
22. **terraform init -migrate-state** khác **-reconfigure** thế nào?
23. Nếu chuyển key khiến Terraform thấy state trống, có nên apply không?
24. Terraform init thành công có nghĩa provider đủ quyền tạo resource chưa?
25. Vì sao **terraform plan -out** có thể là sensitive artifact?
26. **terraform state pull** có nên in ra CI logs không?
27. **sensitive=true** có tự mã hóa hoặc loại bỏ output khỏi state không?
28. Vì sao **terraform_remote_state** có thể đọc nhiều dữ liệu hơn outputs?
29. Blob lease khóa state để ngăn vấn đề gì?
30. -lock-timeout có khác -lock=false không?
31. Khi nào có thể dùng **terraform force-unlock**?
32. Tại sao force-unlock đang có active apply nguy hiểm?
33. Blob versioning và soft delete bảo vệ khỏi những tình huống nào?
34. Geo-replication có phục hồi được state logic bị ghi sai không?
35. Khi restore version cũ, vì sao phải so với Azure live resources?
36. Azure Resource Lock và Terraform state lock khác nhau ra sao?
37. Vì sao không bật immutable WORM policy tùy tiện trên active state?
38. Khi storage có Private Endpoint, Terraform dùng hostname nào?
39. Private DNS zone của Azure Blob thường là gì?
40. Vì sao Microsoft-hosted agent có thể không tới private Blob endpoint?
41. Có Entra token và RBAC đúng đã đủ truy cập state khi firewall deny chưa?
42. Trường hợp nào gây 403 từ Blob backend?
43. Error 409/lease conflict nên xử lý thế nào?
44. Vì sao OIDC giúp giảm rủi ro credential lâu hạn trong CI?
45. Untrusted PR nên chạy Terraform init backend=false khi nào?
46. Tại sao Terraform .terraform.lock.hcl khác state lease lock?
47. Nguồn log nào cho Blob data-plane operations?
48. Azure Activity Log có ghi mọi lần đọc tfstate blob không?
49. Những thứ nào có thể làm tăng chi phí backend ngoài dung lượng state?
50. Khi nào remote Azure Storage backend chưa phải lựa chọn đáng chi phí/độ phức tạp?

## 34. Tài liệu tham khảo

- [Terraform azurerm backend — HashiCorp](https://developer.hashicorp.com/terraform/language/backend/azurerm)
- [Terraform backend configuration](https://developer.hashicorp.com/terraform/language/backend)
- [Terraform state overview](https://developer.hashicorp.com/terraform/language/state)
- [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking)
- [terraform init command](https://developer.hashicorp.com/terraform/cli/commands/init)
- [terraform force-unlock](https://developer.hashicorp.com/terraform/cli/commands/force-unlock)
- [Terraform CLI state commands](https://developer.hashicorp.com/terraform/cli/commands/state)
- [Terraform remote state data source](https://developer.hashicorp.com/terraform/language/state/remote-state-data)
- [Terraform workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [Terraform dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [Store Terraform state in Azure Storage — Microsoft Learn](https://learn.microsoft.com/azure/developer/terraform/store-state-in-azure-storage)
- [Authenticate Terraform to Azure](https://learn.microsoft.com/azure/developer/terraform/authenticate/authenticate-to-azure)
- [Azure Blob Storage introduction](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Authorization for Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Assign an Azure role for access to Blob data](https://learn.microsoft.com/azure/storage/blobs/assign-azure-role-data-access)
- [Azure Storage authorization overview](https://learn.microsoft.com/azure/storage/common/authorize-data-access)
- [Prevent Shared Key authorization for Azure Storage](https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent)
- [Azure Storage private endpoints](https://learn.microsoft.com/azure/storage/common/storage-private-endpoints)
- [Storage networking and firewalls](https://learn.microsoft.com/azure/storage/common/storage-network-security)
- [Blob versioning overview](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview)
- [Concurrency management and Blob leases](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy)
- [Monitor Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/monitor-blob-storage)
- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings)
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log)
- [Azure Monitor reference: StorageBlobLogs](https://learn.microsoft.com/azure/azure-monitor/reference/tables/storagebloblogs)
- [Azure Blob Storage pricing](https://azure.microsoft.com/pricing/details/storage/blobs/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Azure DevOps Pipelines](https://learn.microsoft.com/azure/devops/pipelines/)
- [Azure service connections](https://learn.microsoft.com/azure/devops/pipelines/library/service-endpoints)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)




