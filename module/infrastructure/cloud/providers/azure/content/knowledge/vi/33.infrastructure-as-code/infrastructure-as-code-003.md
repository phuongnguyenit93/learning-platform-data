# Module Bicep và tái sử dụng thành phần hạ tầng

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, các dịch vụ tính toán, lưu trữ và dữ liệu; mục tiêu là biết triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Thuộc chương **Hạ tầng dưới dạng mã**, bài học này hướng dẫn cách xây dựng **module Bicep** để đóng gói một thành phần hạ tầng Azure thành hợp đồng có thể tái sử dụng, kiểm thử, quản lý phiên bản và triển khai an toàn ở nhiều môi trường.

**Tình huống xuyên suốt:** một nhóm Java triển khai ứng dụng đặt hàng trên Azure App Service/AKS, dùng Azure Storage lưu hóa đơn, Virtual Network cho truy cập nội bộ, Key Vault lưu bí mật, Azure Monitor giám sát và Azure SQL lưu dữ liệu. Nếu mỗi ứng dụng tự copy hàng trăm dòng ARM/Bicep để tạo Storage Account, nhóm sẽ sớm gặp khác biệt về TLS, logging, tags, SKU, network security và lifecycle. Module Bicep giúp đưa các quyết định được chuẩn hóa vào một nơi, để ứng dụng sử dụng qua **parameters/outputs** với thay đổi có kiểm soát.

Sau bài học, bạn có thể:

- Giải thích **Bicep, Azure Resource Manager và module deployment**; phân biệt module với resource, file tham số và nested deployment.
- Thiết kế **hợp đồng module** gồm inputs, defaults, constraints, outputs, scope, dependencies và trách nhiệm bảo mật.
- Xây module hoàn chỉnh cho **Storage Account**, tham chiếu từ file **main.bicep**, triển khai nhiều môi trường bằng **.bicepparam**.
- Sử dụng **module local, Bicep registry (OCI trên Azure Container Registry), Azure Verified Modules** và **Template Specs** ở mức thích hợp.
- Áp dụng **module scopes**, vòng lặp, điều kiện, dependency inference, composability và tách resource group/subscription deployment.
- Kiểm tra hạ tầng bằng **build/linter, validate, what-if, deployment outputs** và test sau deploy.
- Tổ chức repository, semantic versioning, CI/CD, Azure RBAC, secure parameters, Azure Policy, monitoring, cost và quy trình rollback.
- Phát hiện các lỗi thường gặp: thiếu output, sai scope, resource name trùng, role assignment thiếu quyền, circular dependency, module version drift và thay đổi gây xóa resource.

## 1. Bicep nằm ở đâu trong hệ sinh thái Azure IaC?

**Bicep** là ngôn ngữ khai báo hạ tầng do Microsoft xây dựng để author **Azure Resource Manager (ARM) templates** thuận tiện hơn JSON. Bạn mô tả trạng thái mong muốn của Azure resources; Bicep compiler biến tài liệu thành ARM template, sau đó **Azure Resource Manager deployment engine** thực hiện các resource provider operations.

```text
Source repository
  |
  +-- main.bicep
  +-- modules/storage.bicep
  +-- modules/network.bicep
  +-- environments/dev.bicepparam
  +-- environments/prod.bicepparam
  |
  v
Bicep compiler / module restore
  |
  v
ARM deployment template + parameter values
  |
  v
Azure Resource Manager
  |
  +--> Microsoft.Storage resource provider
  +--> Microsoft.Network resource provider
  +--> Microsoft.KeyVault resource provider
  +--> Microsoft.Insights resource provider
  |
  v
Azure resources and deployment outputs
```

**Bicep không phải một process quản lý hạ tầng đang chạy mãi.** Deployment đi qua ARM. Nó không tự chạy Java application code, không thay thế Azure RBAC, không tự bật monitoring cho mọi resource và không bảo đảm một ứng dụng production đã healthy chỉ vì ARM deployment thành công.

### 1.1. Khai báo khác ra lệnh tuần tự

Lệnh CLI thủ công kiểu:

```bash
az group create ...
az storage account create ...
az network vnet create ...
```

là một **chuỗi thao tác imperative**. Bicep định nghĩa **resources, properties và relationships**; engine xác định các phụ thuộc và xử lý provisioning. Tính khai báo giúp review diff, chuẩn hóa và tái chạy deployment, nhưng vẫn phải thiết kế vòng đời và tránh thay đổi phá hủy.

### 1.2. Bicep module thực chất là gì?

Một **module** là một file Bicep (hoặc module từ registry/Template Spec) được **gọi trong file Bicep khác** qua từ khóa `module`. Nó nhóm resources và logic cho một năng lực nhất định: storage, networking, observability, compute, data, identity...

Khi compile, việc gọi module được biểu diễn dưới dạng **nested ARM deployment** (thông qua deployment resources) theo behavior của Bicep/ARM. Không hiểu module là thư viện Java hay hàm chạy trong JVM.

### 1.3. Những gì module không làm

- Không tự thay Azure subscription-level permissions.
- Không tự biết resource nào thuộc dev/prod nếu caller không truyền scope/params đúng.
- Không tự bảo đảm mọi dependency đạt readiness ở cấp ứng dụng.
- Không thay Azure Policy hoặc architecture review.
- Không miễn phí: nó tạo resources thật, có quota, cost và lifecycle.
- Không “ẩn” secret khỏi người có quyền thích hợp chỉ bằng cách đặt `@secure()` lên mọi output.

## 2. Vì sao cần module thay vì copy/paste Bicep?

Giả sử ba dự án có cùng yêu cầu Azure Storage:

| Thuộc tính | Nhóm A | Nhóm B | Nhóm C |
|---|---|---|---|
| Minimum TLS | 1.2 | Bỏ mặc định | 1.2 |
| Public blob access | Disabled | Enabled | Disabled |
| Diagnostic settings | Có | Không | Không |
| Tags owner/costCenter | Có | Thiếu | Khác schema |
| Naming | Theo convention | Tự đặt | Tự đặt |
| SKU/redundancy | Standard_LRS | Standard_GRS | Standard_LRS |

Khi tổ chức đổi chính sách (ví dụ yêu cầu không public blob access), việc sửa nhiều bản copy rất dễ bỏ sót. **Module** tập trung các yêu cầu ổn định và expose khác biệt có chủ đích:

```text
                  platform/storage module
                  +----------------------+
                  | TLS >= 1.2           |
                  | Blob public disabled |
                  | Required tags        |
                  | Controlled SKU       |
                  +----------------------+
                         ^      ^      ^
                         |      |      |
                     Orders   Billing  Support
                       App      App      App
```

**Nhưng không nên biến mọi thứ thành một “siêu module”.** Nếu module tạo luôn network, SQL, AKS, storage, logs và business resources chỉ để deploy một API đơn giản, inputs quá nhiều và thay đổi một thành phần có thể gây ảnh hưởng toàn hệ thống. Chia theo **ranh giới vòng đời/ownership**, không chỉ theo tên Azure resource type.

### 2.1. Các lợi ích có thể đo

- **Consistency:** cùng security defaults, naming, tagging và logging patterns.
- **Reuse:** nhiều teams dùng cùng cấu phần qua một hợp đồng.
- **Reviewability:** thay đổi module được review tại một nơi.
- **Maintainability:** phần root template tập trung composition thay vì chi tiết từng property.
- **Governance:** có thể áp policy/approval/CI validation cho module.
- **Testing:** test module riêng và test composition trước rollout.
- **Versioning:** rollout bản mới theo ứng dụng, tránh cập nhật toàn bộ fleet bất ngờ.

### 2.2. Rủi ro của tái sử dụng

Một bug trong shared module có thể lặp ở nhiều deployments. Một version bị publish đè hoặc một output đổi tên không có migration có thể làm nhiều callers fail. Vì vậy **module phải có version, owner, tests, compatibility contract và deprecation policy**.

## 3. Từ khóa nền tảng của Bicep

| Từ khóa/khái niệm | Công dụng | Ví dụ |
|---|---|---|
| `targetScope` | Scope mặc định của template | `targetScope = 'resourceGroup'` |
| `param` | Input từ deployment/caller | `param location string` |
| `@description` | Mô tả cho người sử dụng | `@description('Azure region')` |
| `@allowed` | Giới hạn tập giá trị | SKU/environment allowlist |
| `@minLength`, `@maxLength` | Constraints chuỗi/array theo loại hỗ trợ | Storage name length |
| `@secure` | Đánh dấu secure parameter | Password/API key đầu vào |
| `var` | Biến tính từ inputs | Suffix/tags/derived settings |
| `resource` | Tạo/quản lý Azure resource | `Microsoft.Storage/storageAccounts` |
| `existing` | Tham chiếu resource đã tồn tại | Key Vault/Log Analytics workspace |
| `module` | Gọi module khác | `module storage './modules/storage.bicep' = {...}` |
| `scope` | Chọn deployment scope của module | Resource group khác |
| `output` | Kết quả public của template/module | Resource ID, endpoint |
| `dependsOn` | Dependency rõ ràng khi inference không đủ | Hiếm khi cần viết tay |
| `if`, `for` | Conditional deployment và lặp resource/module | Optional diagnostics, multi-region |

### 3.1. File `main.bicep` và `modules/*.bicep`

`main.bicep` không phải keyword bắt buộc: đó là **quy ước** cho file entrypoint. Module cũng là file Bicep hợp lệ, có thể build/validate/triển khai riêng nếu có parameters và scope phù hợp. Root template quyết định cách compose modules.

### 3.2. Bicep dùng API version của resource provider

```bicep
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  // ...
}
```

Ngày sau `@` là **ARM resource API version**, không phải Bicep compiler version hoặc Azure SDK for Java version. Chọn API version được hỗ trợ/tương thích với các properties bạn cần, và kiểm tra release/deprecation khi nâng; không tự chọn một phiên bản mới hơn nếu chưa kiểm chứng.

### 3.3. Khác biệt giữa tên symbolic và Azure resource name

```bicep
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stordersdev123456'
  // ...
}
```

`storage` là **symbolic name** để tham chiếu trong Bicep, còn `stordersdev123456` là **tên tài nguyên Azure thực**. Đổi symbolic name không nhất thiết đổi resource; đổi `name`/scope có thể tạo resource mới và để lại resource cũ theo deployment mode/lifecycle.

## 4. Hợp đồng module: inputs, outputs và invariants

Một module tốt giống một **public API**: caller biết phải truyền gì, module cam kết cung cấp gì và không phải biết chi tiết resource layout nội bộ.

### 4.1. Inputs nên có

- **Tên hoặc prefix:** phải tuân thủ resource naming rules và tính unique.
- **Location:** thường tham số hóa, tránh hard-code region.
- **SKU/tier:** đưa lựa chọn phù hợp vào tập được phép.
- **Tags:** environment, owner, cost center theo policy.
- **Network/security controls:** những lựa chọn thực sự có biến thể được phê duyệt.
- **Existing resource IDs:** references tới Log Analytics workspace, VNet/subnet, identity khi cần.
- **Feature flags:** chỉ cho optional resources có lifecycle rõ.

### 4.2. Outputs nên có

- **Resource ID** chuẩn để modules khác tham chiếu.
- **Tên/endpoint** không nhạy cảm khi caller cần.
- **Principal ID** của managed identity trong trường hợp module identity (không phải client secret).
- **Subnet ID/Key Vault URI** tùy loại module.

**Không output password, Key Vault secret value, Storage Account key hoặc connection string chứa khóa**. ARM deployment outputs và history có thể là điểm lộ thông tin nếu thiết kế sai. Với secrets, dùng managed identity/Key Vault reference hoặc secure parameter passing có giới hạn.

### 4.3. Không expose mọi thuộc tính

Nếu một storage module nhận 60 params tương ứng 60 properties của resource, nó có thể chỉ là một wrapper mỏng không có giá trị chuẩn hóa. Expose phần caller cần thay và giữ **security defaults** có chủ đích. Một escape hatch cho special cases cần review thay vì `param disableSecurity bool = false` vô điều kiện.

### 4.4. Bảng hợp đồng

| Trường | Bắt buộc? | Mặc định | Quy tắc |
|---|---|---|---|
| `storageAccountName` | Có | Không | 3–24 ký tự, lowercase letters/digits, globally unique |
| `location` | Không | Location của resource group | Region được phê duyệt |
| `skuName` | Không | `Standard_LRS` | Tập SKU được hỗ trợ |
| `tags` | Không | `{}` | Bổ sung required tags tại caller/policy |
| Output `storageAccountId` | Có | N/A | ARM resource ID, không chứa secret |
| Output `blobEndpoint` | Có khi caller cần | N/A | Blob service endpoint |

**Constraints trong module không thay Azure naming/Policy validation**. Ví dụ `@minLength` và `@maxLength` chưa kiểm tra ký tự hợp lệ và tính globally unique. Cần preflight naming và deployment validation.

## 5. Cấu trúc repository cho một project module hóa

Ví dụ tổ chức source:

```text
infrastructure/
├── main.bicep
├── modules/
│   ├── storage.bicep
│   ├── network.bicep
│   ├── diagnostics.bicep
│   └── identity.bicep
├── environments/
│   ├── dev.bicepparam
│   ├── staging.bicepparam
│   └── prod.bicepparam
├── bicepconfig.json
└── docs/
    └── module-contracts.md
```

**Đây là sơ đồ thư mục minh họa trong bài học, không phải thao tác tạo các file bên ngoài file Markdown được giao.** Trong thực tế, tùy đội có thể quản lý central modules trong repo riêng và consumer templates trong các service repos.

### 5.1. Tách public modules và app composition

- **Platform modules:** storage, network, monitoring, identity, security patterns.
- **App composition:** chọn modules, instances, environment names, integration.
- **Environment parameters:** vùng/SKU/naming/tags; không chứa plaintext secrets.
- **Policy/CI:** validate, what-if, approval, deployment và post-deployment verification.

### 5.2. Quy tắc naming file

Dùng **tên biểu đạt capability**, ví dụ `storage-account.bicep`, `network-vnet.bicep`, `sql-database.bicep`, thay vì `common.bicep` chứa mọi loại resource. Với module lớn, dùng hierarchical directories và README mô tả inputs/outputs; không tạo circular imports/module references.

### 5.3. Tính tái sử dụng là phương tiện, không phải mục tiêu tự thân

Nếu một resource chỉ xuất hiện một lần và có lifecycle riêng, đưa vào root Bicep có thể đơn giản hơn. Trích thành module khi có **tái dùng thực, ownership boundary, complexity hoặc policy cần đóng gói**.

## 6. Bài thực hành lõi: viết module Storage Account

Chúng ta sẽ thiết kế file giả định **`modules/storage.bicep`** tại một repository Bicep. Ví dụ tập trung vào storage account an toàn ở mức nền tảng; yêu cầu production có network/diagnostics nâng cao sẽ được mở rộng sau.

### 6.1. Mã module hoàn chỉnh

```bicep
targetScope = 'resourceGroup'

@description('Storage account name: 3-24 lowercase letters/digits, globally unique.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Azure region where the storage account is created.')
param location string = resourceGroup().location

@description('Storage redundancy SKU approved for this workload.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
])
param skuName string = 'Standard_LRS'

@description('Resource tags.')
param tags object = {}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  tags: tags
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
  }
}

@description('ARM resource ID of the deployed storage account.')
output storageAccountId string = storageAccount.id

@description('Blob service endpoint, without an account key.')
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
```

**Phạm vi bảo mật của ví dụ:** `allowBlobPublicAccess: false` cấm anonymous Blob public access, nhưng **`publicNetworkAccess: 'Enabled'` không có nghĩa storage account chỉ truy cập được qua private network**. Dịch vụ vẫn có public service endpoint với authorization. Production yêu cầu private-only cần thiết kế firewall, `defaultAction: Deny`/network rules hoặc private endpoint và private DNS theo policy, **không đem ví dụ tối giản này áp dụng nguyên trạng rồi tuyên bố đã private**.

### 6.2. Tại sao có decorators?

- `@description` làm rõ API contract cho caller.
- `@minLength`, `@maxLength` bắt được một số giá trị sai trước/ở deployment.
- `@allowed` chặn SKU tùy tiện ngoài danh sách module chấp nhận.
- `param location` cho phép đa region và local validation.
- `output storageAccountId` là đầu ra ổn định để modules khác dùng.

Decorators không thay kiểm thử **tên storage globally unique, SKU hỗ trợ trong region, pricing, encryption/network policy**. Cần validation qua ARM/Policy trước deploy production.

### 6.3. Idempotency đúng nghĩa

Nếu deploy cùng template với cùng resource ID và properties, ARM có thể update/no-op resource hiện có theo mô hình declarative. **Idempotency không đồng nghĩa mọi thay đổi đều vô hại**: đổi tên, SKU, property bất khả sửa hoặc replacement lifecycle có thể bị từ chối hoặc tạo resource khác. Luôn xem `what-if` và chính sách migration cho resource chứa dữ liệu.

## 7. File entrypoint gọi module với `module`

File **`main.bicep`** sẽ làm root template ở resource group scope:

```bicep
targetScope = 'resourceGroup'

@description('Environment name.')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string

@description('Storage account name. Must be globally unique.')
param storageAccountName string

param location string = resourceGroup().location
param owner string = 'orders-platform'
param costCenter string = 'commerce'

var commonTags = {
  environment: environment
  owner: owner
  costCenter: costCenter
  managedBy: 'bicep'
}

module storage './modules/storage.bicep' = {
  name: 'storage-${environment}-${uniqueString(resourceGroup().id)}'
  params: {
    storageAccountName: storageAccountName
    location: location
    skuName: environment == 'prod' ? 'Standard_ZRS' : 'Standard_LRS'
    tags: commonTags
  }
}

@description('Storage account ARM ID for downstream modules.')
output storageId string = storage.outputs.storageAccountId

@description('Storage Blob endpoint for applications using managed identity.')
output storageBlobEndpoint string = storage.outputs.blobEndpoint
```

### 7.1. Cú pháp đọc từ trên xuống

`module storage ... = { ... }` khai báo một **module deployment resource**. Trong đó:

- `'./modules/storage.bicep'` là file local được gọi.
- `name` là **ARM nested deployment name**, không phải storage account name.
- `params` ánh xạ từ caller inputs tới public parameters của module.
- `storage.outputs...` đọc các outputs của module sau deployment.

### 7.2. Hai tên dễ nhầm

```text
Nested deployment name:
  storage-prod-<short-deterministic-suffix>

Actual Azure Storage Account name:
  stordersprodxxxxxxxx
```

**Tên nested deployment** cần hợp lệ/ổn định/không đụng nhau trong scope nếu nhiều deployments song song. **Tên storage account** phải globally unique, dài 3–24 ký tự và chỉ lowercase letters/digits. `uniqueString(...)` tạo suffix xác định theo inputs, nhưng không đảm bảo tránh xung đột toàn cầu trong mọi trường hợp; phải validate/tạo naming convention phù hợp.

### 7.3. Caller không cần biết resource symbol nội bộ

Caller chỉ dùng `storage.outputs.storageAccountId`, không biết module định nghĩa resource symbolic name `storageAccount` hay sau đó refactor logic thành nhiều resources. Đây là yếu tố cốt lõi của **encapsulation**.

### 7.4. Không đưa secret vào output

Nếu root cần kết nối Blob, nên dùng **managed identity + Storage Blob Data Contributor/Reader** và endpoint, không output storage account key hoặc connection string chứa Shared Key. Trong CI, deployment outputs có thể bị log; cần bảo vệ cả outputs được coi là không nhạy cảm nếu có tên/ID tài nguyên nội bộ.

## 8. File tham số `.bicepparam` cho dev và prod

Đừng tạo hai bản `main-dev.bicep` và `main-prod.bicep` gần giống nhau chỉ để khác region/SKU. Dùng **cùng composition template**, khác parameter files.

### 8.1. `environments/dev.bicepparam`

```bicep
using '../main.bicep'

param environment = 'dev'
param storageAccountName = 'stordersdev123456'
param location = 'southeastasia'
param owner = 'orders-team'
param costCenter = 'commerce-dev'
```

### 8.2. `environments/prod.bicepparam`

```bicep
using '../main.bicep'

param environment = 'prod'
param storageAccountName = 'stordersprod123456'
param location = 'southeastasia'
param owner = 'orders-team'
param costCenter = 'commerce-prod'
```

Các account names chỉ để minh họa; **không đảm bảo còn trống hoặc globally unique**. Tham số SKU được root chọn theo environment; production cần kiểm tra **Standard_ZRS** availability/region và requirements trước deploy.

### 8.3. Dùng parameter file với CLI

```bash
az login
az account set --subscription "<approved-nonproduction-subscription-id>"

RG="rg-orders-dev"
az group create --name "$RG" --location southeastasia

# Bicep CLI and Azure CLI version phải tương thích .bicepparam.
az deployment group what-if \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam

az deployment group create \
  --name orders-storage-dev \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

Với tooling hỗ trợ `.bicepparam` và `using '../main.bicep'`, Azure CLI có thể xác định template từ parameter file. Trên CLI cũ, cú pháp/capabilities có thể khác; **nâng/kiểm tra Azure CLI/Bicep versions** trước khi chạy CI. Lệnh tạo resource group và deploy là **các bước thực hành có thể tính phí**; chỉ chạy trên môi trường được phép, không tự dùng subscription production.

### 8.4. Parameter file không phải vault chứa secret

Không commit `param sqlAdminPassword = 'P@ssword...'` trong repo. Dùng cơ chế secret references được Bicep/ARM hỗ trợ, CI secure variables/Key Vault, hoặc thiết kế ứng dụng dùng managed identity không cần mật khẩu. **`.bicepparam` là source file, không phải lớp mã hóa dữ liệu**.

## 9. Module thứ hai: Virtual Network và subnet

Để thấy module không chỉ có Storage, tạo một module network với interface rõ ràng. Module **`modules/network.bicep`** này sở hữu một VNet và một subnet dành cho ứng dụng; ví dụ không bao gồm NSG/UDR/peering và cần mở rộng theo network policy thực tế.

### 9.1. Nội dung module network

```bicep
targetScope = 'resourceGroup'

@description('Virtual Network name.')
param vnetName string

@description('Subnet name for the application.')
param appSubnetName string = 'snet-app'

@description('VNet CIDR.')
param vnetCidr string = '10.40.0.0/16'

@description('Application subnet CIDR, contained in the VNet range.')
param appSubnetCidr string = '10.40.1.0/24'

param location string = resourceGroup().location
param tags object = {}

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetCidr
      ]
    }
  }
}

resource appSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: vnet
  name: appSubnetName
  properties: {
    addressPrefix: appSubnetCidr
  }
}

output vnetId string = vnet.id
output appSubnetId string = appSubnet.id
```

**Vì sao dùng resource con?** `appSubnet` khai báo `parent: vnet` nên Bicep/ARM hiểu quan hệ resource và thứ tự cần thiết. Không viết `dependsOn: [vnet]` chỉ để nhắc lại một dependency đã được Bicep suy ra.

### 9.2. Caller kết hợp hai modules

Trong một file root cần cả network và storage, có thể khai báo:

```bicep
module network './modules/network.bicep' = {
  name: 'network-${environment}'
  params: {
    vnetName: 'vnet-orders-${environment}'
    appSubnetName: 'snet-orders'
    vnetCidr: '10.40.0.0/16'
    appSubnetCidr: '10.40.1.0/24'
    location: location
    tags: commonTags
  }
}

output applicationSubnetId string = network.outputs.appSubnetId
```

Đây là **fragment cần đặt vào `main.bicep` ở phần 7**, dùng các symbols `environment`, `location`, `commonTags` đã định nghĩa ở đó. Không copy fragment thành file độc lập rồi mong build được. Mỗi môi trường phải chọn CIDR không chồng lấn; dev/staging/prod ở những VNets peered/hybrid cần có kế hoạch IP riêng.

### 9.3. Module VNet nên sở hữu cái gì?

Có hai hướng:

1. **Module VNet + subnet** vì hai resource có lifecycle cùng một team/network service.
2. **Module VNet** và **module subnet/NSG/route** tách riêng vì platform team quản lý VNet còn product team quản lý subnet/attachments.

Chọn theo **ownership và change frequency**. Nếu nhiều modules cùng sửa property `subnets` của một VNet bằng những deployment paths khác nhau, có nguy cơ **last writer wins/lost updates**. Quy định rõ module nào là **single writer** của từng resource/child resource.

## 10. Giao tiếp giữa modules bằng outputs

Ví dụ một module private networking hoặc application compute cần subnet đã được tạo:

```text
network module
  |
  +-- output appSubnetId
              |
              v
        compute module
        param subnetId
              |
              v
        compute resource
```

Một thành phần composition root có thể viết:

```bicep
module network './modules/network.bicep' = {
  name: 'orders-network'
  params: {
    vnetName: 'vnet-orders-dev'
    appSubnetName: 'snet-app'
  }
}

module application './modules/application.bicep' = {
  name: 'orders-app'
  params: {
    subnetId: network.outputs.appSubnetId
  }
}
```

**Đây là ví dụ composition schematic:** file `application.bicep` phải được team tự định nghĩa, có `param subnetId string` và resource cụ thể. Nhờ dùng `network.outputs.appSubnetId`, Bicep suy ra **dependency** giữa hai module deployments mà không cần viết `dependsOn` thủ công.

### 10.1. Output là hợp đồng cần version

Nếu phiên bản module 1.1 xuất `appSubnetId` mà bản 2.0 đổi thành `subnetResourceId`, caller cũ sẽ bị lỗi khi compile/restore. Thay đổi tên/kiểu output là **breaking change**. Quy tắc tốt:

- Giữ output name/shape ổn định trong cùng major version.
- Thêm output mới thay vì xóa output cũ ngay.
- Cung cấp migration note khi đổi contract.
- Có consumer test compile các caller phổ biến trước publish.

### 10.2. Đừng xuất một object lớn thiếu schema

Output `output everything object = storageAccount` hoặc xuất nguyên resource state khiến caller lệ thuộc implementation, tăng bề mặt nhạy cảm và có thể gặp vấn đề với runtime properties. Chỉ xuất **IDs/names/URIs cần thiết**, kiểu ổn định. Nếu cần metadata phức tạp, định nghĩa object contract có schema/version rõ.

### 10.3. Dependency inference có giới hạn

ARM/Bicep biết thứ tự từ references, parent/scope và outputs; nó không thể tự hiểu **nghiệp vụ ngoài ARM** như “cần 10 phút sau DB provision để data migration hoàn tất”. Những bước schema migrations, app health checks hoặc Key Vault RBAC propagation cần **deployment pipeline orchestration và readiness tests**, không phải lạm dụng `dependsOn`.

## 11. Khi nào cần `dependsOn`?

Ví dụ:

```bicep
module storage './modules/storage.bicep' = {
  name: 'orders-storage'
  params: {
    storageAccountName: storageAccountName
  }
}

module other './modules/other.bicep' = {
  name: 'orders-other'
  params: {
    // Tham chiếu output sẽ tạo dependency tự động.
    storageResourceId: storage.outputs.storageAccountId
  }
}
```

Đây là **fragment illustrative**, cần định nghĩa `storageAccountName` ở root và file `other.bicep` tương ứng. Vì `other` sử dụng output của `storage`, thứ tự đã được suy ra. `dependsOn` chỉ cần thiết khi có dependency **không biểu diễn qua expression/scope** và được chứng minh rõ ràng.

### 11.1. Anti-pattern: biến mọi module thành tuần tự

```bicep
// Không nên tạo dây chuyền phụ thuộc không cần thiết:
// network -> storage -> keyvault -> sql -> app -> monitor
```

Storage và VNet có thể deploy song song nếu độc lập; ép tuần tự làm tăng thời gian triển khai và làm debugging khó. Cần một **dependency DAG** phản ánh resource relationships, không theo thứ tự file hoặc sở thích cá nhân.

### 11.2. Module compilation không chứng minh runtime readiness

Một module output resource ID sau ARM deployment thành công không bảo đảm **ứng dụng Java trong App Service đã kết nối SQL** hoặc **AKS Pods healthy**. Thêm smoke tests/health gates sau deployment.

## 12. Scope: module chạy ở resource group, subscription, management group hay tenant?

Bicep/ARM hỗ trợ các target scopes như **resource group**, **subscription**, **management group** và **tenant** theo loại tài nguyên và module. Không phải mọi resource type có thể triển khai tại mọi scope; cần đúng API/resource provider và quyền Azure RBAC.

### 12.1. Resource group scope

```bicep
targetScope = 'resourceGroup'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: resourceGroup().location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}
```

Đây là một **fragment**, cần khai báo `param storageAccountName string` nếu dùng độc lập. Thường dùng `az deployment group create` để deploy một ứng dụng vào resource group.

### 12.2. Subscription scope tạo resource group rồi gọi module

```bicep
targetScope = 'subscription'

@description('Azure region for the resource group and storage.')
param location string
param resourceGroupName string
param storageAccountName string

resource appRg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

module storage './modules/storage.bicep' = {
  name: 'storage-${uniqueString(subscription().id, resourceGroupName)}'
  scope: appRg
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

output storageId string = storage.outputs.storageAccountId
```

Module `storage.bicep` có `targetScope = 'resourceGroup'`, còn root ở subscription. Trường `scope: appRg` chuyển deployment sang resource group vừa khai báo; đây là **cross-scope module deployment** hợp lệ khi permissions và API hỗ trợ.

CLI tương ứng:

```bash
az deployment sub what-if \
  --location southeastasia \
  --template-file ./subscription-main.bicep \
  --parameters location=southeastasia \
               resourceGroupName=rg-orders-dev \
               storageAccountName="<globally-unique-storage-name>"

az deployment sub create \
  --location southeastasia \
  --template-file ./subscription-main.bicep \
  --parameters location=southeastasia \
               resourceGroupName=rg-orders-dev \
               storageAccountName="<globally-unique-storage-name>"
```

`--location` ở subscription deployment là nơi lưu **deployment metadata**, khác tham số `location` cho resource group/storage; có thể giống nhau nhưng là hai khái niệm. Tạo resource group tại subscription scope yêu cầu quyền ARM tương ứng. **Không chạy trên subscription production ngoài change review**.

### 12.3. Gọi module vào resource group đã tồn tại

Từ root có `targetScope = 'subscription'`:

```bicep
param sharedResourceGroupName string
param storageAccountName string

resource sharedRg 'Microsoft.Resources/resourceGroups@2022-09-01' existing = {
  name: sharedResourceGroupName
}

module storage './modules/storage.bicep' = {
  name: 'shared-storage-module'
  scope: sharedRg
  params: {
    storageAccountName: storageAccountName
  }
}
```

Đoạn này **không tạo** `sharedRg` vì có `existing`; nếu RG chưa tồn tại, deployment sẽ thất bại khi ARM cần scope đó. `existing` giúp tham chiếu, không cấp quyền tự động hoặc đổi ownership của tài nguyên.

### 12.4. Scope là một phần hợp đồng

Một module network hoặc storage thường target resource group; module tạo Azure Policy assignment có thể cần subscription/management group; module role assignments có scope gắn đúng target resource. Nếu caller gắn `scope` không tương thích targetScope/resource types, Bicep compiler hoặc ARM sẽ báo lỗi. Không giải quyết bằng cách cấp subscription Owner thay vì sửa scope.

## 13. Module có điều kiện `if` và feature flags

Một app đôi khi chỉ cần diagnostics workspace trong production. Có thể dùng **conditional deployment** khi module thực sự optional.

```bicep
param deployDiagnostics bool = true
param logAnalyticsWorkspaceId string = ''

module diagnostics './modules/diagnostics.bicep' = if (deployDiagnostics) {
  name: 'orders-diagnostics'
  params: {
    workspaceId: logAnalyticsWorkspaceId
    targetResourceId: storage.outputs.storageAccountId
  }
}
```

Đây là **fragment composition**: cần module `diagnostics.bicep` do team định nghĩa, và module `storage` như phần 7. Các resource types có diagnostic categories và scopes khác nhau; **không tự coi một module diagnostics generic hoạt động với mọi Azure resource**.

### 13.1. Rủi ro output của module được skip

Khi `deployDiagnostics = false`, module không được triển khai. Nếu caller vẫn truy cập `diagnostics.outputs...` không có guard, deployment có thể fail hoặc phát sinh cảnh báo compiler về nullable/conditional resource. Chỉ truy cập outputs khi **điều kiện tương ứng được bảo đảm**, sử dụng guarded conditional expression theo Bicep version hỗ trợ.

### 13.2. Feature flag nên rõ về lifecycle

Đổi `deployDiagnostics` từ `true` sang `false` **không tự chứng minh logs cũ được giữ/xóa đúng chính sách**. Tùy deployment mode, resources có thể tiếp tục tồn tại hoặc bị xử lý khác. Trước khi tắt một module có resources, cần migration plan, what-if và retention decision.

## 14. Module collection với vòng lặp `for`

Khi cần nhiều Storage Accounts theo môi trường/regions, có thể lặp module:

```bicep
targetScope = 'resourceGroup'

@description('Globally unique Storage Account names.')
param storageAccountNames array

@description('Default region for all accounts in this example.')
param location string = resourceGroup().location

@batchSize(1)
module storageAccounts './modules/storage.bicep' = [
  for (accountName, index) in storageAccountNames: {
    name: 'storage-${index}-${uniqueString(resourceGroup().id)}'
    params: {
      storageAccountName: accountName
      location: location
    }
  }
]

output storageIds array = [
  for i in range(0, length(storageAccountNames)):
    storageAccounts[i].outputs.storageAccountId
]
```

### 14.1. `@batchSize` và giới hạn đồng thời

`@batchSize(1)` minh họa **triển khai tuần tự từng iteration** để giảm tranh chấp/quota hoặc xử lý thứ tự nếu thật sự cần. Nếu các accounts độc lập, deployment song song thường nhanh hơn; không bật batch size 1 mọi nơi vì thói quen.

### 14.2. Giới hạn loop và quotas

ARM/Bicep có giới hạn về loop/resource counts, nested deployment, throttling và quota của từng resource provider. Một loop tạo 1.000 Storage Accounts có thể vượt quota/cost/policy dù compile hợp lệ. Đặt **upper bound**, ownership và policy; dùng orchestration theo waves khi cần.

### 14.3. Tên deployment phải ổn định

Trong collection, `name` nested deployment phải **duy nhất trong scope khi nhiều instances deploy**. Sử dụng index tạo tên ổn định theo vị trí, nhưng nếu **đổi thứ tự array**, instance mapping và resource names có thể thay đổi. Với workloads cần identity ổn định, cân nhắc dùng một **stable logical key** thay index và kiểm tra name lengths.

### 14.4. Các outputs của collection

`storageIds` là một array có thứ tự theo collection. Consumer không nên giả định index 0 luôn là region eastus nếu đầu vào có thể sắp xếp lại; dùng input object có name/region và output mapping theo contract khi cần.

## 15. Thiết kế modules nhỏ, ghép thành một hệ thống lớn

Một kiến trúc minh họa:

```text
subscription/main.bicep
    |
    +-- resource group(s)
              |
              v
application/main.bicep
    |
    +-- network module
    |      +-- VNet/subnet/NSG
    |
    +-- identity module
    |      +-- managed identity
    |
    +-- storage module
    |      +-- storage account
    |
    +-- key-vault module
    |      +-- Key Vault (no secret values in outputs)
    |
    +-- database module
    |      +-- Azure SQL database/server
    |
    +-- compute module
    |      +-- App Service/AKS/workload configuration
    |
    +-- observability module
           +-- Log Analytics/diagnostic settings/alerts
```

### 15.1. Loại dependency nên encode

- Compute module cần subnet ID: lấy `network.outputs...`.
- App Service/VM/AKS identity cần role assignment scope: tham chiếu **resource ID + principal ID**.
- Diagnostic settings cần workspace ID: tham chiếu **workspace module output**.
- Database firewall/private endpoint cần network/subnet config: tham chiếu **network outputs**.

### 15.2. Loại dependency không nên encode bằng cách “đợi đại”

- Java application migration phải chạy sau SQL database provision.
- Key Vault secrets do security team provision cần đã có trước khi pod startup.
- Azure RBAC token propagation cần được kiểm tra khi gọi data plane.
- App configuration/slots/traffic switching cần smoke tests.

Những phần này thường cần **pipeline sequencing, IaC outputs + ứng dụng health checks**, không phải một module chứa sleep script/VM extension tùy tiện.

### 15.3. Ownership và team boundaries

VNet core có thể do platform team sở hữu, workload subnet do team network/product quản lý theo policy. Đừng để root app template tự sửa central shared VNet/NSG nếu team đó không được quyền; dùng `existing` resources và expose contract rõ, hoặc tách deployments theo scope/approvals.

## 16. Những kiểu module giúp giảm coupling

| Kiểu | Mục đích | Ví dụ |
|---|---|---|
| **Resource module** | Bao một resource + defaults quan trọng | Storage Account |
| **Pattern module** | Một nhóm resources phối hợp có lifecycle chung | Private Endpoint + DNS zone group cho service cụ thể |
| **Composite module** | Kết hợp nhiều modules thành workload baseline | Java App Service + identity + diagnostic settings |
| **Policy module** | Gán guardrail/RBAC ở scope thích hợp | Azure Policy assignment |
| **Integration module** | Kết nối các resources đã tồn tại | Role assignment/diagnostic settings |

### 16.1. Chọn granularity theo vận hành

Module “resource” quá nhỏ nếu chỉ bọc một resource và lặp tất cả properties mà không enforce chính sách; module “composite” quá lớn nếu thay đổi mọi resource trong một deployment. **Ranh giới hợp lý** thường dựa vào:

- Cùng team chịu trách nhiệm.
- Cùng vòng đời deploy/update/delete.
- Shared security/compliance invariants.
- Outputs public API ổn định và số inputs quản lý được.
- Có thể test riêng với chi phí chấp nhận được.

### 16.2. Reuse không đồng nghĩa mọi app phải giống nhau

Dev có thể dùng `Standard_LRS`, prod có thể cần `Standard_ZRS` hoặc geo redundancy; một app có private-only access, app khác có public endpoint với firewall. Module nên định nghĩa **một tập lựa chọn được phê duyệt**, không hard-code một cấu hình duy nhất cho mọi service mà bỏ business requirement.

## 17. Ba nguồn module: local, registry và Template Specs

Bicep hỗ trợ nhiều cách lấy module. Việc chọn nguồn tác động đến **cache, auth, versioning, governance, network và khả năng build CI**.

| Loại | Cú pháp tham chiếu khái niệm | Đặc điểm | Khi nào dùng |
|---|---|---|---|
| **Local file** | `'./modules/storage.bicep'` | Nằm trong source repo, đi cùng commit | Module nhỏ/same team, cần sửa đồng bộ |
| **OCI module trong registry** | `'br:contoso.azurecr.io/bicep/modules/storage:1.2.0'` | Phiên bản publish qua registry, phải restore | Platform module chia sẻ nhiều repositories |
| **Template Spec** | `'ts:<subscription>/<rg>/<spec>:<version>'` | ARM Template Spec version Azure resource | Tổ chức dùng Template Specs/governance ARM |
| **Azure Verified Modules (AVM)** | Registry module qua public alias/path được công bố | Thư viện modules có kiểm thử/pattern và conventions | Tăng tốc adoption, nhưng vẫn cần review |

**Local module path** được resolve theo file caller. Với registry, Bicep phải tải artifact về module cache (hoặc sử dụng cache còn hợp lệ), và identity/build environment cần quyền read phù hợp. Template Specs cần access và proper scope/version; không phải một file local tự động.

### 17.1. Chọn theo ranh giới tổ chức

- Một service repo có 3 modules chỉ dùng ở đó: bắt đầu bằng **local modules**.
- Platform team cung cấp storage/network baselines cho 20 services: **private OCI Bicep registry** với version pin và release notes thường phù hợp.
- Tổ chức có governance dựa trên **ARM Template Specs**: có thể tham chiếu versions đã phê duyệt.
- Những patterns chuẩn phổ biến: đánh giá **AVM** để tránh tái chế thiết kế, nhưng phải kiểm tra contract, outputs, defaults và security.

### 17.2. Không nhầm Bicep registry với container image registry

Bicep modules trên Azure Container Registry dùng **OCI artifact storage**, nhưng **không phải Docker image để chạy container**. Repository/tags của module cũng không tự tạo AKS/Container Apps workloads; ARM vẫn là nơi triển khai resources.

## 18. Publish module Bicep lên Azure Container Registry

Giả sử platform team có ACR `contoso.azurecr.io` và đã tạo repository cho modules (quyền/scope được cấu hình). Một lệnh mẫu:

```bash
az login
az account set --subscription "<approved-platform-subscription-id>"

# Kiểm tra Azure CLI Bicep subcommands và version trước CI.
az bicep version

az bicep publish \
  --file ./modules/storage.bicep \
  --target br:contoso.azurecr.io/bicep/modules/storage:1.2.0
```

**Chưa chạy lệnh trên ACR thật nếu chưa có quyền/approval; đây là thao tác ghi artifact vào registry.** Azure CLI/Bicep version phải hỗ trợ publish và URI hợp lệ, deployer phải có quyền registry push theo **permission mode** của ACR. Trong classic registry RBAC có các roles như AcrPull/AcrPush; trong mode RBAC+ABAC repository permissions có các repository reader/writer roles khác. Không tự khẳng định một role hoạt động trong mọi permission mode.

### 18.1. Consumer dùng module đã publish

```bicep
targetScope = 'resourceGroup'

param storageAccountName string
param location string = resourceGroup().location

module storage 'br:contoso.azurecr.io/bicep/modules/storage:1.2.0' = {
  name: 'storage-from-registry'
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

output storageResourceId string = storage.outputs.storageAccountId
```

Khi build, Bicep restore module definition theo URI và validate params/outputs. Không cần copy module implementation vào repo consumer, nhưng **phiên bản được tham chiếu phải giữ contract và artifact ổn định**.

### 18.2. Restore dependency

```bash
az bicep restore --file ./main.bicep
az bicep build --file ./main.bicep
```

Một runner offline chưa cache module sẽ không restore được registry artifact. Để reproducible, pin versions, dùng registry có availability và IAM phù hợp, bảo vệ CI credentials, và có chính sách cache/retention rõ.

### 18.3. Không publish bằng mutable tag thiếu kiểm soát

Tag `1.2.0` là convention version; registry có thể cho phép một số dạng overwrite theo quyền/cấu hình. **Không tự coi mọi tag mặc định immutable**. Dùng release pipeline để ngăn re-publish cùng tag, retention/ownership policy và provenance; giữ source revision/build artifact mapping. Nếu một module không đổi URI nhưng nội dung đổi, consumer builds có thể lệch do cache và phá reproducibility.

### 18.4. Security của private registry

Một private Bicep registry phải:

- Có writers/publishers được cấp quyền tối thiểu.
- Consumers read theo repositories/scopes được phép.
- Ghi audit logs cho publish/delete/rewrite.
- Tách modules non-prod/test khỏi modules đã phát hành.
- Có review, version và kiểm thử trước publish.
- Không lưu secrets/connection strings/plaintext credentials trong module sources.
- Có strategy khi module không còn hỗ trợ hoặc registry outage.

## 19. Bicep module aliases qua `bicepconfig.json`

Để không viết lặp FQDN/repository prefix, Bicep hỗ trợ **module aliases** trong cấu hình.

### 19.1. JSON config minh họa

```json
{
  "moduleAliases": {
    "br": {
      "platform": {
        "registry": "contoso.azurecr.io",
        "modulePath": "bicep/modules"
      }
    }
  }
}
```

### 19.2. Dùng alias trong caller

```bicep
module storage 'br/platform:storage:1.2.0' = {
  name: 'orders-storage'
  params: {
    storageAccountName: storageAccountName
  }
}
```

**Đây là fragment** có `storageAccountName` được khai báo ở root. Alias `platform` phải tồn tại và được resolve từ `bicepconfig.json` đúng hierarchy. Nếu consumer checkout repo thiếu config, module restore có thể fail hoặc không resolve đúng registry. Quyết định alias là **API của build environment**, cần version cùng source repository.

### 19.3. Alias không tự đổi authorization

Alias rút gọn URI; nó không tự cung cấp Azure Container Registry pull permission. CI agent/developer vẫn cần đăng nhập đúng tenant/principal và có network path để đọc registry. Không nhúng account password vào alias config.

## 20. Azure Verified Modules (AVM)

**Azure Verified Modules** là tập hợp mô-đun IaC do cộng đồng và Microsoft đóng góp/duy trì theo các tiêu chí/chính sách xác minh cụ thể. Bicep AVM modules được phân phối qua public Bicep registry, với conventions về parameters, diagnostics, role assignments, locks, private endpoints tùy module.

### 20.1. Vì sao nên xem AVM trước khi tự viết lại?

- Đã có nhiều resources và patterns phổ biến.
- Thường có docs/examples và hướng dẫn sử dụng.
- Có automated validation conventions và versioned releases.
- Giúp giảm các lỗi lặp lại về naming, tagging, diagnostics và security properties.

### 20.2. Không mặc định module AVM phù hợp mọi security policy

AVM không thay security review của tổ chức: default settings có thể khác policy, networking/zone setup khác architecture, outputs/cấu trúc params khác version trước. Khi consumer sử dụng AVM:

1. Chọn đúng module type (**resource module** hoặc **pattern module**).
2. Kiểm tra **version được publish** và compatibility với CLI/Bicep.
3. Đọc **params/outputs**, required/optional features và examples của đúng release.
4. Test security defaults với Azure Policy, negative network/IAM checks.
5. Dùng **version cụ thể**, không bám một nhãn “latest” giả định luôn ổn.
6. Có regression plan trước nâng major/minor version.

### 20.3. Cách tham chiếu ở mức khái niệm

```text
br/public:avm/res/<provider>/<resource-type>:<published-version>
```

Đây là **mẫu URI với placeholders**, không phải một module path/version có thể build nguyên văn. Chọn **exact verified registry reference** từ tài liệu/registry của module bạn sử dụng. Các AVM patterns có path khác; đừng suy tất cả theo một dạng duy nhất.

### 20.4. Wrapper nội bộ cho AVM

Platform team có thể tạo module local/private wrapper:

```text
Orders App
   |
   v
Internal platform/storage module
   |
   v
Pinned AVM storage resource module
   |
   v
Azure Storage Account
```

Wrapper chỉ expose **điều chỉnh được duyệt**, thêm tags/security/monitoring baseline và giảm coupling của apps với AVM contract. Tuy vậy, wrapper không nên che mọi feature cần thiết hoặc khiến upgrades khó theo dõi.

## 21. Template Specs làm nguồn module

**Azure Resource Manager Template Specs** cho phép lưu versioned ARM template trong Azure dưới dạng resource có quản trị. Bicep có thể tham chiếu Template Spec như module theo URI `ts:` khi compiler/ARM/permissions hỗ trợ.

### 21.1. URI mẫu

```text
ts:<subscription-id>/<resource-group-name>/<template-spec-name>:<version>
```

Ví dụ schematic:

```bicep
module storage 'ts:00000000-0000-0000-0000-000000000000/rg-templates/storage-standard:1.2.0' = {
  name: 'storage-from-template-spec'
  params: {
    storageAccountName: storageAccountName
  }
}
```

Đây là **fragment dùng subscription ID giả**, cần thay resource IDs, version, params contract và permissions; không chạy như template hoàn chỉnh. Template Specs không phải **Azure Policy** và không tự động approve deployment nếu module không đáp ứng chính sách.

### 21.2. Khi nào chọn ACR registry hay Template Spec?

| Tiêu chí | OCI Bicep registry (ACR) | Azure Template Specs |
|---|---|---|
| Artifact chính | Bicep module được publish thành OCI artifact | ARM template spec version resource |
| Reference | `br:...:version` / alias | `ts:...:version` |
| Mục tiêu | Chia sẻ Bicep modules giữa repositories | Tái sử dụng ARM template versions được quản lý trong Azure |
| Access | ACR repository/registry permissions | ARM RBAC trên Template Spec resources |
| Pipeline | Build/validate/publish Bicep module | Build ARM template/spec version deployment |
| Governance | Registry, tag/version policy | Azure resource RBAC, version lifecycle |

Không có lựa chọn tốt nhất chung. Tổ chức có thể dùng **local modules + private registry** cho Bicep và Template Specs cho legacy ARM templates.

## 22. SemVer và compatibility contract của modules

Một module shared là **dependency** của consumer. Hãy áp dụng cách phát hành có thể dự đoán, ví dụ **semantic versioning** (quy ước quản trị, không phải tính năng ARM tự áp):

| Thay đổi | Phiên bản theo convention | Rủi ro |
|---|---|---|
| Sửa docs/naming comment không đổi output | Patch | Thấp, vẫn test |
| Sửa bug nhưng không đổi input/output contract | Patch | Có thể đổi property defaults, vẫn cần what-if |
| Thêm optional param với default an toàn | Minor | Có thể ảnh hưởng behavior tùy default |
| Thêm output mới | Minor | Thường backwards compatible |
| Đổi tên required param hoặc output | Major | Caller build fail |
| Đổi default từ public enabled sang private-only | Major hoặc migration release | Có thể phá network workloads |
| Đổi resource type/name/scope | Major + migration | Có thể tạo/xóa resource chứa dữ liệu |
| Đổi default SKU/HA của database | Major hoặc change-management | Cost, availability và lifecycle |

**SemVer không thay thế what-if**: một patch nhỏ vẫn có thể làm ARM update không mong muốn nếu implementation thay resource properties. Khi release module, tạo changelog **what changed**, **who is affected** và **migration instructions**.

### 22.1. Version pin trong consumer

```text
Service A -> platform/storage:1.2.0
Service B -> platform/storage:1.2.0
Service C -> platform/storage:1.3.0
```

Điều này cho phép rollout theo waves. **Không âm thầm update mọi service tới latest** bằng một shared alias trỏ mutable tag. Một module có security critical fix có thể cần coordinated rollout và deadline; vẫn cần canary/what-if per environment.

### 22.2. Breaking changes thường thấy

- Đổi `storageAccountName` từ string sang object hoặc required param mới.
- Đổi output `storageAccountId` sang `id`.
- Đưa resource sang resource group khác/scope khác.
- Đổi naming khiến Azure xem là resource mới.
- Thay network defaults khiến consumers mất access.
- Đổi role assignment schema làm identity mất data-plane access.

### 22.3. Deprecation contract

Khi module phiên bản cũ có lỗ hổng hoặc sắp bị Azure API retire:

1. Công bố impacted versions.
2. Đưa bản thay thế đã test.
3. Cung cấp migration/rollback instructions.
4. Cảnh báo consumers trong dependency inventory.
5. Giới hạn publish/consumption của deprecated version theo policy.
6. Theo dõi rollout và cảnh báo modules còn ở version cũ.

Không xóa artifact cũ khi clients còn cần restore, trừ khi đó là quyết định security emergency có kế hoạch thay thế.

## 23. Định nghĩa “module chất lượng” theo hợp đồng

Một module có thể được xem là reusable-ready khi:

```text
Inputs
  - Typed and documented
  - Required fields explicit
  - Safe defaults and validation

Outputs
  - Stable names and types
  - Only necessary public data
  - No raw credentials

Security
  - Azure Policy and RBAC-compatible
  - No accidental public exposure
  - No secret values in logs/outputs

Operations
  - Tags, diagnostics and lifecycle
  - Tested updates, not only fresh create
  - What-if / negative tests / rollback guidance

Distribution
  - Pinned API/module versions
  - Signed/reviewed publishing workflow where supported
  - Changelog, ownership and deprecation notice
```

### 23.1. Module contract tests

Không chỉ test “deploy lần đầu thành công”. Cần:

- Valid values compile/validate và resource được tạo.
- Invalid SKU/name bị chặn ở bước thích hợp.
- Update parameters không tự xóa resource không liên quan.
- Required tags/security defaults tồn tại sau deploy.
- Outputs được các modules downstream sử dụng đúng kiểu.
- Không rò rỉ sensitive values trong outputs/deployment logs.
- Có thể deploy dev và prod dưới scope/permissions đúng.
- Concurrency và module deployment names không conflict.

### 23.2. Tái sử dụng cần documentation

Docs nên ghi:

- Module purpose/non-goals.
- Inputs/outputs, defaults, constraints.
- Supported API/Bicep versions và deployment scopes.
- Security/network assumptions.
- Example `module` usage, test environment.
- Pricing implications và resource lifecycle.
- Change log và rollback/migration advice.

Nếu người dùng phải đọc 1.000 dòng implementation để đoán `skuName` hoặc output ID, module chưa có API contract đủ tốt.

## 24. Kiểm tra Bicep trước khi triển khai: build, validate, what-if

Một pipeline triển khai module tốt có **ít nhất ba tầng kiểm chứng**:

```text
Source code + pinned modules
       |
       v
1) Static Bicep compilation / linter checks
       |
       v
2) ARM validate in correct deployment scope
       |
       v
3) What-if + change/security review
       |
       v
4) Deploy to test/staging
       |
       v
5) Runtime post-deploy assertions
       |
       v
6) Production approval + deployment
```

### 24.1. Bicep build

```bash
# Đọc phiên bản compiler thực tế.
az bicep version

# Compile Bicep và chạy diagnostics/linter theo config.
az bicep build --file ./main.bicep
```

Build có thể tạo **ARM JSON artifact** trong working directory nếu chạy trên repo thực. Ở bài học này **không thực thi lệnh**, chỉ giải thích. Build giúp bắt **syntax/type/resource properties/module references/linter diagnostics**, không chứng minh Azure resource đã được tạo hoặc tên globally unique.

### 24.2. ARM validate

```bash
RG="rg-orders-dev"
az deployment group validate \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

Trong môi trường tương thích `.bicepparam`, CLI có thể lấy template từ file `using`. Nếu CLI cũ không hỗ trợ, nâng toolchain hoặc dùng tổ hợp template/parameter được version đó hỗ trợ. **Validation không thay thế deployment**: resource provider, permissions, quota và network/data-plane checks có thể tạo lỗi chỉ khi apply.

### 24.3. What-if

```bash
az deployment group what-if \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

What-if so sánh desired template với trạng thái Azure để **dự báo thay đổi**. Nó giúp nhận ra resource create/modify/delete/ignore/unknown theo behavior của engine nhưng **không phải bảo đảm tuyệt đối**: runtime values, reference functions, provider behavior hoặc permissions có thể khiến kết quả có `Ignore/NoChange/unknown` không như mong đợi. Cần đọc chi tiết và kiểm tra thay đổi nhạy cảm.

### 24.4. Đọc what-if như một security review

Ví dụ:

```text
~ Microsoft.Storage/storageAccounts/stordersprod...
    properties.publicNetworkAccess:
      'Disabled' => 'Enabled'

+ Microsoft.Network/privateEndpoints/new-endpoint

- Microsoft.KeyVault/vaults/kv-orders-prod
```

**Đây là output minh họa, không phải kết quả từ Azure.** Nếu PR làm public network access chuyển từ Disabled sang Enabled hoặc dự báo xóa vault/database, dừng deployment và yêu cầu review security/owner. Không bỏ qua chỉ vì mã Bicep compile xanh.

### 24.5. Automated tests sau deploy

Ví dụ test assertions:

- Storage account tồn tại tại đúng resource group/subscription.
- Minimum TLS và `allowBlobPublicAccess=false` đúng.
- Resource tags owner/environment/costCenter được áp.
- App managed identity có data-plane role thực sự.
- Private endpoint/DNS khi production policy yêu cầu, và public access bị deny.
- Diagnostic settings gửi logs vào đúng Log Analytics workspace.
- Output resource IDs khớp actual deployed IDs.
- Java application có thể upload/download một synthetic Blob bằng intended identity.

Chỉ có **post-deployment integration tests** mới xác minh end-to-end behavior. Static IaC test không thay thế **runtime policy/network/identity**.

## 25. Bicep linter, conventions và secure parameters

### 25.1. Vì sao cần linter?

Compiler có thể build hợp lệ nhưng code vẫn chứa các patterns nguy hiểm: parameters không dùng, hard-coded locations, unnecessary dependencies, output secret hoặc implementation phức tạp. Bicep có **analyzers/linter rules** cấu hình trong `bicepconfig.json` theo phiên bản.

Các lớp rule thường cần:

| Nhóm | Mục tiêu |
|---|---|
| Syntax/type correctness | Templates compile được |
| Unused params/vars | Không có dead/ambiguous interface |
| No unnecessary `dependsOn` | Dependency graph chính xác |
| Secure param defaults | Không hard-code plaintext secret |
| No hardcoded environment URLs | Không trỏ nhầm endpoints vùng/tenant |
| Naming/tagging | Organizational conventions |
| Allowed resource APIs/SKUs | Security/governance compatible |

Tên và mức độ rule thực tế cần đối chiếu **Bicep CLI version** đang pin; không đặt một linter option theo tài liệu cũ rồi cho rằng pipeline đã chạy.

### 25.2. Secure parameter

```bicep
@secure()
@description('Database admin password, injected from an approved secret source.')
param adminPassword string
```

`@secure()` giúp ARM xử lý parameter nhạy cảm theo cơ chế secure parameter (không đưa value vào deployment history như parameter thường). Nhưng nó **không làm nguồn plaintext an toàn** nếu bạn commit password vào source hoặc in ra logs. Không xuất value qua `output`, không ghép vào tag, resource name hoặc public URL.

### 25.3. Tham chiếu Key Vault secret cho module

Một pattern Bicep hỗ trợ khi đúng quyền/configuration là pass secret trực tiếp cho **secure parameter của module**:

```bicep
param keyVaultName string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

module database './modules/database.bicep' = {
  name: 'orders-database'
  params: {
    adminPassword: keyVault.getSecret('sql-admin-password')
  }
}
```

Đây là **fragment cần module `database.bicep` thật** với `@secure() param adminPassword string` và các parameters khác. `getSecret()` chỉ hợp lệ trong ngữ cảnh Bicep/ARM được hỗ trợ, thường **trong module params**, không phải một method Java hay cách tự do in secret vào `var`. Key Vault phải cho phép **template deployment secret access** theo điều kiện/nền tảng phù hợp và deployment principal phải có quyền tương ứng; điều này có các giới hạn/risks và không nên bật tùy tiện chỉ để ví dụ pass. Khi có thể, **prefer managed identity cho application/database workload**, tránh truyền mật khẩu admin nếu dịch vụ hỗ trợ Entra authentication.

### 25.4. Secure output và dữ liệu nhạy cảm

Những Bicep phiên bản mới có khả năng xử lý secure outputs theo cú pháp/tính năng được công bố, nhưng cách an toàn mặc định là **không output secret**. Không dựa vào một decorator để cho phép CI log values, bởi logs/shell/third-party consumers vẫn có thể tiết lộ dữ liệu nếu sử dụng sai.

## 26. Governance: Azure Policy, RBAC và resource locks

### 26.1. Bicep không vượt Azure Policy

Nếu tổ chức có Azure Policy `deny` đối với Storage Accounts cho phép anonymous Blob, deployment module có `allowBlobPublicAccess=true` có thể bị chặn, kể cả file compile và what-if có thể hiển thị change hợp lệ về mặt schema.

```text
Bicep template
    |
    v
ARM deployment
    |
    +--> Azure Policy check / deny / modify where configured
    |
    +--> RBAC permissions
    |
    +--> Resource provider validation / quotas
    |
    v
Resource created or deployment failed
```

Modules nên có **safe defaults aligned với policy**, nhưng vẫn phải dùng **Azure Policy as guardrail** cho mọi producers (Portal/CLI/Terraform/scripts), không chỉ các file Bicep do team kiểm soát.

### 26.2. Phân biệt deployment identity và runtime identity

| Identity | Công việc | Quyền ví dụ |
|---|---|---|
| **CI deployment principal** | Tạo/sửa ARM resources | RBAC tại target RG/subscription theo nhu cầu |
| **Java app managed identity** | Đọc Blob/Key Vault data plane | Storage Blob Data Reader, Key Vault Secrets User |
| **Platform module publisher** | Publish OCI module artifact | ACR repository write theo permission mode |
| **Module consumer build agent** | Restore OCI module artifact | ACR repository read |
| **Network owner** | Tạo Private Endpoint/VNet/DNS links | Azure Network resource permissions |
| **Security owner** | Quản trị Policy/RBAC approval | Scoped Azure Policy/role assignment rights |

**CI có quyền ARM Contributor không đồng nghĩa Java app có quyền đọc Blob/Key Vault.** Nếu module tạo role assignments, CI có thể cần role assignment permissions đặc biệt và scope hẹp. Không tự cấp Owner toàn subscription để giải quyết `AuthorizationFailed`.

### 26.3. Least privilege cho cross-scope module

Root subscription template có thể tạo resource group, còn module con ở RG sẽ dùng **cùng effective deployment identity** với RBAC tương ứng. Nếu CI không có quyền tại target scope, module fail. Phân tách infra provisioning và role assignment approvals khi yêu cầu, thay vì một principal nắm tất cả trong môi trường production.

### 26.4. Resource locks và deletion safety

Resource lock như `CanNotDelete` hoặc `ReadOnly` có thể ngăn một số thao tác quản lý và thay đổi update/delete theo scope. Không coi lock là cơ chế thay authorization/backup, và phải kiểm tra behavior khi IaC deployment cần update resource. Với tài nguyên dữ liệu quan trọng, dùng **backup/restore, soft delete, purge protection, lifecycle review và deployment protections** phù hợp.

## 27. Mô hình triển khai nhiều môi trường bằng modules

### 27.1. Cùng code, khác tham số và scope

```text
                  same pinned module contract
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
               dev         staging         prod
              /   \\          /   \\         /   \\
           RG-dev  ...   RG-staging ...   RG-prod ...
           LRS            LRS              ZRS/GRS
           small          medium           production tiers
           test tags      preprod tags     owner/cost tags
```

Không dùng một `environment` string để tự động cấp quyền production hoặc chọn subscription. Subscription ID/RG scope và CI federation environment phải được xác minh độc lập; `param environment='prod'` chỉ là giá trị đầu vào, không phải authorization boundary.

### 27.2. Dev vs staging vs prod

| Thuộc tính | Dev | Staging | Prod |
|---|---|---|---|
| Subscription/RG | Non-prod | Non-prod có kiểm soát | Production riêng |
| Module version | Can test next release | Release candidate | Approved version |
| Storage SKU | Cost-optimized | Gần production khi cần | Business continuity yêu cầu |
| Network | Test VNet/limited public theo policy | Production-like private paths | Least privilege/private endpoints |
| Identity | Test managed identity | Federated/workload identity test | Runtime managed identity |
| Monitoring | Cơ bản | Validated alert rules | Full telemetry/SLO/runbook |
| Deployment approval | Developer/team | Test/owner | Change/production approvers |
| Data | Synthetic | Synthetic/test class | Production data |

Đừng dùng production secrets/key material trong môi trường staging chỉ vì module outputs trông giống nhau.

### 27.3. Chi phí version upgrade theo environment

Module bản 1.3 thêm một diagnostic settings hoặc Private Endpoint có thể tăng storage/logging/network bill. Tập thay đổi **không chỉ là code**; cùng module version có tác động khác nhau theo region, SKU và traffic. Trong PR/release hãy ghi **estimated cost + what-if** cho từng environment.

### 27.4. Tách scope và state ownership

Một deployment root cho dev không được ghi vào resource group prod. Ràng buộc target subscription/RG bằng **CI environment/identity allowlist**, không chỉ thông qua tên từ file `dev.bicepparam`. Với shared network resources, dùng **existing references** và giao ownership cho network team, tránh team app tái deploy đè.

## 28. CI/CD cho module và consumer

Thiết kế hai pipeline riêng:

1. **Module publishing pipeline:** test và phát hành artifact module.
2. **Consumer deployment pipeline:** restore pinned modules, what-if và deploy app infrastructure.

### 28.1. Module publishing pipeline

```text
PR to platform-modules
  |
  +-- compile + linter
  +-- validate module contracts
  +-- deploy integration fixture into test RG
  +-- assert security/outputs/idempotency
  +-- run what-if on existing fixture (update test)
  +-- review API/versions/changelog
  |
  v
Trusted release branch/tag
  |
  +-- sign/review provenance as supported by policy
  +-- publish immutable version to ACR/Template Spec
  +-- verify artifact can be restored by consumer
  +-- record source revision + artifact version
```

### 28.2. Consumer deployment pipeline

```text
PR to orders-service
  |
  +-- pin module versions
  +-- az bicep restore/build
  +-- parameter validation + static policy checks
  +-- ARM validate + what-if against test scope
  +-- security/cost review when necessary
  |
  v
Merge
  |
  +-- deploy dev + smoke test
  +-- deploy staging + integration tests
  +-- production approval
  +-- production what-if + change gate
  +-- production deploy
  +-- app/API/identity/network health checks
  +-- record outputs, deployment/incident links
```

### 28.3. GitHub Actions skeleton

```yaml
name: bicep-deployment-review

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  validate-nonprod:
    runs-on: ubuntu-latest
    environment: nonproduction
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_NONPROD_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_NONPROD_SUBSCRIPTION_ID }}
      - name: Compile Bicep
        run: az bicep build --file ./infrastructure/main.bicep
      - name: Preview non-prod changes
        run: |
          az deployment group what-if \
            --resource-group rg-orders-dev \
            --parameters ./infrastructure/environments/dev.bicepparam
```

**Đây là workflow skeleton kích hoạt thủ công trên trusted branch/environment**, không phải pipeline copy-paste hoàn chỉnh hay job an toàn cho PR không tin cậy. Cần cấu hình workload identity federation/OIDC trust, GitHub protected environments, pinned action versions theo security policy, repo paths, test scopes, approvals, branch protection và output checks. Một PR từ fork/untrusted code **không nên có Azure write credentials hoặc quyền deploy production**; chạy static build/lint ở PR riêng. Đừng nhầm GitHub Actions expression với Bicep string interpolation: chúng được xử lý ở hai công cụ và thời điểm khác nhau.

### 28.4. OIDC không tự cấp quyền Azure

OIDC federation chứng minh một workload CI phù hợp trust claims; Azure RBAC ở scope deployment và ACR repository permissions vẫn quyết định được phép làm gì. Dùng separate identities cho **module publisher**, **dev deployer** và **prod deployer**.

### 28.5. Không chạy deploy production khi chưa có diff

Với changes ảnh hưởng Key Vault, SQL, VNet, firewall hoặc resources có dữ liệu:

- Bắt buộc **what-if** từ intended target subscription/RG.
- Review security/network + data lifecycle.
- Tách migration steps khi cần.
- Approval theo chính sách tổ chức.
- Có rollback/forward-fix plan và post-deploy tests.

### 28.6. Version lock & supply-chain

Pin **module versions**, Azure CLI/Bicep version, CI actions; không dùng mutable `latest`/main branch để lấy platform module trong production. Ghi SBOM/provenance artifacts khi quy trình cung cấp, bảo vệ registry khỏi unauthorized publish/overwrite và theo dõi CVE/config vulnerabilities liên quan.

## 29. Phát hiện drift và triển khai có chủ đích

**Drift** là trạng thái Azure thực tế khác template/parameters đã được duyệt, ví dụ ai đó bật public Blob access trên Portal hoặc thay subnet NSG.

### 29.1. Tại sao drift nguy hiểm?

- Module source trong Git nói **Disabled** nhưng actual resource đang **Enabled**.
- Một deploy lại có thể đổi trạng thái và gây outage bất ngờ.
- Báo cáo compliance sai nếu chỉ kiểm tra source code.
- Các teams cùng sửa một shared resource gây conflict.

### 29.2. Phương pháp

1. Định kỳ chạy **what-if** trên scope được phép hoặc công cụ drift detection phù hợp.
2. Dùng Azure Policy compliance views cho các security invariants.
3. Dùng Azure Activity Log theo dõi management changes.
4. Đối chiếu tags/owner/schema và resource inventory.
5. Triage: thay đổi hợp lệ chưa phản ánh IaC hay thay đổi không được phép?
6. Tạo PR cập nhật code hoặc revert thay đổi có approval.

### 29.3. Không “chạy lại IaC” bừa bãi

Nếu actual SQL database khác template do migration chính đáng, deployment “sửa drift” có thể phá dữ liệu/network. Cần **what-if + owner review** và kiểm tra có nhiều writers cùng quản lý resource không.

### 29.4. Incremental deployment và deletion semantics

ARM deployments thường dùng **incremental mode** để tạo/cập nhật resources được khai báo, nhưng không xóa tất cả resources vắng trong template như nhiều người tưởng. Cơ chế complete mode có rủi ro xóa và đang được thay thế/khuyến cáo chuyển sang **Deployment Stacks** cho quản lý deletion lifecycle theo feature hiện hành. Không mặc định xóa module `if false` sẽ tự xóa toàn bộ resources cũ; hãy chọn **resource deletion strategy** có chủ đích, kiểm chứng `what-if` và backup.

### 29.5. Deployment Stacks khác module

**Module** là cách cấu trúc template. **Deployment Stack** là một mô hình quản lý tập resources được deployment sở hữu, với deletion/detach policies và scope. Có thể dùng cả hai, nhưng chúng không phải từ đồng nghĩa và có lifecycle/permission khác nhau.

## 30. Rollback: phân biệt code rollback và resource rollback

Giả sử module storage version 1.3 thay `publicNetworkAccess` sang Disabled. Ứng dụng chưa dùng Private Endpoint, nên outage xảy ra.

### 30.1. Điều gì không tự rollback?

- Rollback Git commit không tự đổi resource Azure.
- ARM deployment thất bại giữa chừng không bảo đảm mọi resource provider đã undo.
- Xóa module declaration không tự xóa/revert resource theo incremental behavior.
- Restore module version cũ không chắc đủ để khôi phục dữ liệu/permissions.
- Storage Account/SQL name, region, encryption hoặc delete operation có thể có side effects/irreversibility.

### 30.2. Kế hoạch rollback

```text
Detect impact via application SLI
      |
      v
Pause further rollout
      |
      v
Inspect deployment operations and actual resource state
      |
      v
Choose forward-fix or approved rollback template/params
      |
      v
Run what-if against current scope
      |
      v
Approve and redeploy safely
      |
      v
Verify network/identity/data/application health
      |
      v
Record incident + regression tests
```

### 30.3. Không dùng destructive rebuild để “sửa nhanh”

Nếu một storage account chứa production invoices, **không xóa/tạo lại bằng tên mới** chỉ để vượt một lỗi property update. Cần backup, migration, data integrity và RPO/RTO review. Với resource có dữ liệu, bảo toàn **resource identity và data lifecycle** là ưu tiên.

### 30.4. Thử rollback trong staging

Module upgrade test nên có:

1. Deploy bản N trên test resources.
2. Ghi trạng thái/ID/data fixture.
3. Deploy bản N+1, chạy what-if và verify.
4. Thử rollback/forward-fix nếu design cho phép.
5. Kiểm tra data preservation và policy.
6. Rút kinh nghiệm cho release notes.

## 31. Tagging, diagnostics và cost control trong reusable modules

Một module được nhiều team dùng là nơi tốt để chuẩn hóa **metadata, chi phí và observability**, nhưng không nên nhét mọi alert vào mọi resource một cách không kiểm soát.

### 31.1. Tags nên có semantic rõ

Ví dụ:

```bicep
param environment string
param owner string
param costCenter string
param additionalTags object = {}

var requiredTags = {
  environment: environment
  owner: owner
  costCenter: costCenter
  managedBy: 'bicep'
}

// Quy tắc ưu tiên cần được team xác nhận.
var finalTags = union(additionalTags, requiredTags)
```

Ở đây `requiredTags` được merge sau, nên các trường trùng tên trong `additionalTags` không được phép ghi đè required values theo semantics `union` phù hợp. **Đây là fragment**, các params và `finalTags` phải được sử dụng trong resource/module thực. Cần kiểm tra tagging policy và **cost attribution** của tổ chức, không đưa password/email/PII vào tags.

### 31.2. Diagnostics là cross-cutting concern

Một module Storage Account có thể nhận `logAnalyticsWorkspaceId` để tạo diagnostic settings khi được bật, nhưng mỗi resource/subresource có **diagnostic categories riêng**. Ví dụ:

- Storage Account service endpoints có các logs/metrics đặc thù; diagnostic settings của Blob service có thể cần scope ở **blobServices** chứ không phải account root.
- Azure SQL, Service Bus, AKS và Key Vault dùng resource types/categories khác nhau.
- Azure Monitor metric alerts cần đúng signal/dimension/granularity và action group.

Vì vậy **một module diagnostics “generic” chỉ với resource ID không phải lúc nào cũng đủ**. Có thể dùng pattern module cho từng resource type, hoặc một composite wrapper hiểu target scopes/available categories.

### 31.3. Đừng để module tự tạo hàng chục workspaces

Nếu mỗi workload deploy module tạo một Log Analytics workspace, observability costs, retention, RBAC và cross-workspace investigation có thể bị phân mảnh. Platform team có thể quản lý **shared workspace theo environment/region/data classification**, apps chỉ nhận output ID/reference qua parameter. Ngược lại, tenant/data isolation có thể cần workspace riêng. Lựa chọn phải dựa trên **security & operational boundary**, không chỉ reuse.

### 31.4. Tags không chứng minh resource an toàn

`environment=prod` không phải Azure RBAC permission. Resource vẫn có thể lộ public internet hoặc thiếu encryption. Kết hợp module defaults, Azure Policy, actual resource properties, post-deploy tests và audit.

### 31.5. Ảnh hưởng chi phí của mỗi module version

| Thay đổi trong module | Chi phí có thể thay đổi | Cần kiểm tra |
|---|---|---|
| Storage LRS → ZRS/GRS | Storage/redundancy billing | Region availability, DR requirements |
| Bật Private Endpoint | Endpoint hourly/data-processing charge | VNet/DNS/cross-region traffic |
| Thêm Log Analytics diagnostics | Log ingestion/retention | Categories, data volumes, compliance |
| Bật Azure Monitor alerts | Alert rule/evaluations/actions | Severity, noise và budget |
| Thay App Service Plan SKU | Compute cost/capacity | Load/SLO và scaling |
| Thêm NAT gateway/firewall | Hourly/data charges | Security, egress, routing |
| Tạo Azure SQL secondary | DB/licensing/storage/replication | RPO/RTO, region/HA |

**What-if không phải báo giá**. Kết hợp Azure Pricing Calculator/Cost Management, quy định budget và cost-review trước nâng module production.

## 32. Tích hợp application Java với outputs Bicep

Bicep cung cấp **resource IDs/endpoints**, không nên cung cấp raw secret. Một pattern an toàn:

```text
main.bicep
  |
  +-- storage.outputs.blobEndpoint
  +-- identity.outputs.clientId
  +-- keyvault.outputs.vaultUri
  |
  v
Approved application configuration / deployment manifest
  |
  v
Java application (managed/workload identity)
  |
  +-- Azure Blob SDK with TokenCredential
  +-- SecretClient for Key Vault
  |
  v
Azure data-plane operations
```

### 32.1. Java Blob SDK ở runtime

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String blobEndpoint = System.getenv("AZURE_BLOB_ENDPOINT");
if (blobEndpoint == null || !blobEndpoint.startsWith("https://")) {
    throw new IllegalArgumentException("Expected HTTPS Blob endpoint");
}

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();
```

Đây là **fragment** cần Azure SDK Java dependencies và composition code, không phải module Bicep. Runtime credential/identity phải có data-plane RBAC như `Storage Blob Data Reader/Contributor` theo nghiệp vụ và network path. **Storage Account được tạo bằng Bicep không tự cấp Java app quyền đọc Blob**.

### 32.2. Truyền outputs vào cấu hình đúng cách

Sau ARM deployment có thể đọc outputs (thay placeholders):

```bash
az deployment group show \
  --resource-group "rg-orders-dev" \
  --name "orders-storage-dev" \
  --query "properties.outputs" \
  --output json
```

Chỉ đưa **non-secret outputs** vào app settings hoặc pipeline variables. Với sensitive deployment outputs, không in JSON ra console; module contract nên tránh trả secrets. Cần kiểm tra exact **deployment name**, vì Bicep module nested deployment và root deployment có tên khác nhau.

### 32.3. Không giao owner toàn subscription cho Java service

Java app làm data-plane operations nên dùng **managed/workload identity** và quyền tối thiểu. ARM deployment identity dùng để tạo resources/role assignments là principal khác; không đưa CI client secret hoặc subscription Owner token vào runtime app settings.

### 32.4. Test application sau deploy

Sau khi tạo storage/identity/network:

1. Đọc expected Blob endpoint từ root output/known resource.
2. Deploy app với managed/workload identity đúng.
3. Chạy synthetic upload/download (đường mạng cho phép).
4. Kiểm tra Blob metadata và response.
5. Chạy negative RBAC check khi cần.
6. Kiểm tra logs/traces/metrics và cleanup fixture.

Một pipeline chỉ báo “Bicep deployment succeeded” chưa chứng minh ứng dụng Java hoạt động.

## 33. Kiểm thử module theo ba cấp độ

### 33.1. Static checks

Không cần Azure resource thật:

- Bicep build/linter và module restoration.
- Type/allowed values/contract checks.
- Không có hardcoded secret.
- Kiểm tra tags, baseline TLS/public access.
- Cấm unpinned external module references theo policy.
- Kiểm tra không có module cycles/unnecessary dependsOn.

### 33.2. ARM validate/what-if

Sử dụng subscription/resource group test:

- Valid API/provider properties tại region.
- Role assignment permissions và policies/validation.
- Dự báo modify/replace/delete của resource đã tồn tại.
- Scope assignment và parameter file correctness.

**Không thay thế runtime test.** ARM validate/what-if có thể không đánh giá hết giá trị runtime/hậu quả của provider updates.

### 33.3. Live integration tests

Trên **non-production subscription/RG**:

- Deploy module vào resource test.
- Gọi Azure API đọc properties actual.
- Kiểm tra security policy/Network ACL thực.
- Test tạo resource lần hai cùng params (idempotent behavior).
- Test update an toàn qua vài params được phép.
- Test output contract với module downstream.
- Test deletion/cleanup có guard và phù hợp retention.

### 33.4. Ma trận kiểm thử

| Test | Build | Validate/What-if | Azure live |
|---|---|---|---|
| Parameter missing/type sai | Có | Có thể | Không cần |
| Resource API property hợp lệ | Một phần | Một phần | Có |
| Tên storage globally unique | Không | Có thể | **Có** |
| Tag security default đúng | Contract test | Dự báo | **Có** |
| RBAC hiệu lực data plane | Không | Role definition/scope | **Có** |
| Private DNS/443 connectivity | Không | Không đầy đủ | **Có** |
| App Java đọc Blob thành công | Không | Không | **Có** |
| Update không phá dữ liệu | Không | Dự báo | **Cần test** |
| Module 1.3 backwards compatible | Compile consumer | What-if | Test upgrade |
| Chi phí deployment | Không | Không định giá | Actual Cost Management |

### 33.5. Chỉ sử dụng synthetic data

Không copy production SQL database/password/customer PII vào test environment chỉ để kiểm thử module. Với Azure Storage, tạo Blob fixture nhỏ, dùng resource names có prefix/run ID và **cleanup test-owned resources** sau khi test.

### 33.6. Cleanup phải có owner

```text
test resource group: rg-module-it-<run-id>
tags:
  purpose=module-integration-test
  owner=platform-iac
  runId=<run-id>
  expiresAt=<timestamp>
```

Nếu CI bị kill trước `finally`/post step, cần scheduled janitor với **resource ID allowlist, owner/run ID, age và active-build check**. **Không xóa mọi resource group bắt đầu bằng "rg-test"** vì có thể thuộc team khác hoặc còn đang chạy.

## 34. Troubleshooting khi module Bicep không triển khai được

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| `BCP...` compile error | Sai syntax/type/output/param/namespace | Bicep compiler message & line, docs API version |
| `Unable to restore module` | ACR URI/alias/network/login/role/cache | Registry path/version, module alias config, ACR permissions |
| `Module not found` | Sai local relative path hoặc registry artifact tag | Root path, case sensitivity/CI filesystem |
| `InvalidTemplate` | Sai scope/ARM constraints/API properties | ARM validation errors, targetScope & resource provider |
| `StorageAccountAlreadyTaken` | Tên globally unique bị trùng | Naming convention/namespace logic |
| `LocationNotAvailable` hoặc SKU không hợp lệ | Region/SKU/service limit | Resource provider availability và subscription quota |
| `AuthorizationFailed` | Deployment identity thiếu ARM role ở scope | Principal ID, subscription/RG, role assignment |
| `RequestDisallowedByPolicy` | Azure Policy deny/modify | Policy assignment/exemption và remediation |
| `DeploymentFailed` | Provider failed, quota/conflict | Deployment operations và nested module error details |
| `Circular dependency` | Modules references tạo DAG vòng | Refactor graph/outputs, không thêm dependsOn vòng |
| `Deployment name conflict` | Cùng nested name/scope deploy song song | Unique stable module deployment names |
| `what-if unknown/ignore` | Runtime/reference limitations | Review high-risk properties, staging test |
| `output missing` | Module conditional skip hoặc contract đổi | Guard conditional, pin versions, output schema |
| Java SDK 403 sau deploy | Data-plane RBAC/ACL/private endpoint | Runtime identity, network, role propagation |
| Resource sai tags/SKU | Parameter file sai hoặc drift | Actual Azure properties, correct env scopes |

### 34.1. Đọc ARM deployment operations

```bash
RG="rg-orders-dev"
DEPLOYMENT="orders-storage-dev"

az deployment group show \
  --resource-group "$RG" \
  --name "$DEPLOYMENT" \
  --output json

az deployment operation group list \
  --resource-group "$RG" \
  --name "$DEPLOYMENT" \
  --output json
```

Ở các lệnh, tên subcommand/parameter có thể thay đổi theo Azure CLI version, nên kiểm tra `az deployment operation group --help` tương ứng. Khi lỗi ở **nested deployment**, lần theo resource/deployment name của module và xem **inner error**. Không chỉ nhìn dòng cuối `DeploymentFailed`.

### 34.2. Sai subscription nguy hiểm hơn sai YAML

Một template hợp lệ triển khai vào subscription nhầm có thể tạo resource thật, phát sinh tiền và mất tuân thủ. Trước mọi deployment:

```bash
az account show \
  --query "{subscription:id, tenant:tenantId, name:name}" \
  --output json
```

CI cần allowlist subscription/RG và identity scope. Không dựa duy nhất vào file name `prod.bicepparam` để đoán target môi trường.

### 34.3. Azure CLI của developer và CI khác version

Local Bicep compile được nhưng CI fail có thể do toolchain cũ, module registry support khác hoặc API version mismatch. **Pin Azure CLI/Bicep versions**, dùng same build image và chạy integration test trên exact versions.

### 34.4. Module thay đổi nhưng caller không lấy bản mới

Với ACR, module cache/tag mutation có thể khiến kết quả local/CI khác nhau. Đừng “clear cache” rồi coi đó là giải pháp nguồn gốc. Cần **artifact immutable version**, verify digest/provenance và update consumer URI có review.

### 34.5. Lỗi role assignment và data-plane permission

Module có thể tạo managed identity và gán role cho Storage/Key Vault; ARM báo thành công nhưng data-plane call vẫn 403 do **role propagation, principal mismatch, token cache hoặc network ACL**. Test từ đúng workload runtime, dùng bounded wait, không tự cấp Owner.

## 35. Runbook 1: Module registry restore hoặc publish bị lỗi

**Triệu chứng:** build báo không restore được `br:...` hoặc release pipeline publish failed.

1. Kiểm tra version/tên registry hostname/repository path/tag đúng.
2. Kiểm tra `bicepconfig.json` alias và vị trí config được sử dụng.
3. Kiểm tra ACR availability/network/private endpoint/firewall/DNS nếu áp dụng.
4. Xác minh identity thực và repository read/write role theo ACR permission mode.
5. Kiểm tra artifact/version đã tồn tại và có release record không.
6. Chạy restore trên trusted test runner có network/IAM đúng.
7. Nếu publish bị từ chối vì tag đã tồn tại, **không overwrite bất chấp policy**; phát hành version mới.
8. Sau fix, build consumer sample và test module outputs.
9. Ghi incident và cập nhật pipeline guards.

**Không hard-code registry admin password vào `bicepconfig.json` hoặc source code** để chữa nhanh authentication.

## 36. Runbook 2: What-if báo thay đổi nguy hiểm

**Triệu chứng:** what-if cho thấy storage account replacement, public network enabled hoặc Key Vault resource deletion.

1. Dừng automatic production deploy gate.
2. Xác nhận subscription/RG và module version/parameter file được dùng.
3. Kiểm tra diff nguồn, ARM resource IDs, properties và scope.
4. Phân tích cách thay đổi ảnh hưởng **data preservation, RPO/RTO, RBAC và networking**.
5. Kiểm tra khả năng result `Ignore/unknown` và limitations của what-if.
6. Chạy thử trên staging fixture với data/permissions giả lập.
7. Chọn migration/forward-fix hoặc rollback plan có review.
8. Lấy approval của resource owner/security/cost owner.
9. Deploy theo waves, post-deploy tests và monitoring.

**Không để pipeline auto-approve destructive changes chỉ vì Bicep compile xanh.**

## 37. Runbook 3: Module upgrade làm Java app lỗi

**Triệu chứng:** ARM deployment báo Succeeded nhưng Java app mất kết nối Azure SQL/Storage/Key Vault.

1. Xác minh app SLI/health và phạm vi khách hàng bị ảnh hưởng.
2. Xem resource change history và module version/what-if.
3. Kiểm tra resource ID/name/scope có đổi không.
4. Kiểm tra public network/private endpoint/DNS/firewall sau upgrade.
5. Kiểm tra managed identity client ID/principal ID và data-plane RBAC.
6. Kiểm tra app configs lấy resource endpoint từ outputs có bị stale không.
7. Nếu là role propagation, dùng bounded retries và logs phân biệt auth/network.
8. Chọn mitigations bảo toàn dữ liệu, không delete/recreate bừa bãi.
9. Verify app synthetic transaction và Azure Monitor alerts.
10. Thêm regression integration test cho module release sau.

Nếu thay đổi network security không tương thích app, ưu tiên **sửa private connectivity** thay vì mở public endpoint không được phê duyệt.

## 38. Case study: Module Bicep cho nền tảng đặt hàng trên Azure

### 38.1. Bối cảnh

Một công ty có ba Java services:

- **Orders API:** Spring Boot trên App Service/AKS, dùng Azure SQL.
- **Receipt Worker:** đọc queue và lưu hóa đơn vào Azure Blob Storage.
- **Notification Worker:** dùng Azure Service Bus để gửi thông báo.

Hạ tầng chung gồm VNet, Key Vault, managed identities, Log Analytics, storage và alerting. Các services phải tách **dev/staging/prod**, có owner/costCenter và **private network** ở production.

### 38.2. Thiết kế module

```text
iac/
  modules/
    network.bicep          # VNet/subnets/NSG baseline
    storage.bicep          # Storage account TLS/anonymous access policy
    identity.bicep         # User-assigned managed identities
    keyvault.bicep         # Vault RBAC/access policy model
    database.bicep         # SQL resource pattern
    compute.bicep          # App Service or AKS pattern
    monitoring.bicep       # Workspace/diagnostics/alerts as supported
    private-link.bicep     # Resource-specific PE/DNS pattern
  main.bicep               # Composition + dependency wiring
  environments/
    dev.bicepparam
    staging.bicepparam
    prod.bicepparam
```

Trong thực tế đây chỉ là **sơ đồ**, các module chưa được định nghĩa trong bài sẽ cần implementation/contract riêng. Trọng tâm của bài là **nguyên tắc thiết kế và hai module mẫu Storage/VNet** đã có code thực ở trên.

### 38.3. Các contract quan trọng

| Module | Inputs chính | Outputs cho caller |
|---|---|---|
| Network | VNet name, CIDRs, region, tags | VNet ID, subnet IDs |
| Storage | Account name, SKU, tags, network policy | Account ID, Blob endpoint |
| Identity | Identity name, region, tags | Resource ID, client ID, principal ID |
| Key Vault | Vault name, RBAC settings, network/diag integration | Vault resource ID, URI |
| Database | Name, SKU, identity, network rules | Server/db IDs, FQDN |
| Compute | Plan/cluster name, subnet ID, identity IDs | Host/cluster IDs, endpoints |
| Monitoring | Workspace ID, categories, action group | Workspace/alert resource IDs |
| Private Link | Target resource/subresource, subnet ID, DNS zone | PE ID, approved connection status as observed |

**Không output DB admin password hoặc storage account key.** Java runtime dùng identity phù hợp và config endpoint.

### 38.4. Dependency flow

```text
Network --> Private Link --> Storage/Key Vault private access
   |
   +------> Compute
               |
Identity ------+------> Data plane RBAC
               |
Storage ID ----+------> Blob endpoint/config
               |
Database ID ---+------> SQL connection target
               |
Monitoring ----+------> Diagnostics/alerts
```

Không gán mọi modules đều dependsOn mọi module. Với Azure Private Endpoint, đường dependency đến resource đã tồn tại và subnet rõ, nhưng **DNS readiness và RBAC propagation** vẫn cần tests sau ARM deployment.

### 38.5. Lộ trình triển khai

1. Platform team phát hành module version `storage:1.2.0` và `network:1.0.0` từ test-validated source.
2. Orders app pin versions trong root template.
3. Bicepparam dev chỉ định RG/SKU/region/naming; CI build/validate/what-if.
4. Deploy dev, test synthetic Blob/SQL/service.
5. Deploy staging với network/identity production-like; kiểm tra private DNS và role assignments.
6. Production what-if/scope/security/cost review.
7. Deploy prod với approval và canary workloads.
8. Smoke test Orders API, Receipt Worker, Key Vault/SQL access.
9. Theo dõi Azure Monitor và cost; ghi deployment version, outputs và incident links.

### 38.6. Một failure scenario

Module version 1.3 thay network default từ public sang private-only (đúng security policy), nhưng App Service chưa có outbound VNet Integration. ARM deployment thành công; Java app kết nối Blob/Key Vault bị lỗi.

Phân tích:

- **Module contract change:** network assumption mới là breaking behavior.
- **Dependency outside ARM:** app runtime network configuration.
- **Testing gap:** staging chưa có canary/negative network tests.
- **Action:** kiểm tra PE/DNS/VNet Integration, giữ least privilege, sửa kết nối riêng hoặc rollback có phê duyệt, rồi thêm integration tests.

Đây là ví dụ cho thấy **reusable modules cần versioned behavior contract**, không chỉ public param schema.

### 38.7. Tiêu chí nghiệm thu

```text
MODULES
  source revision/version pinned
  build and contract validation pass
  no plaintext credentials in params/outputs

AZURE
  correct subscription/RG/scope
  security baseline and Azure Policy pass
  resource IDs/tags/SKU/network as expected

RUNTIME
  Java app uses intended managed identity
  data-plane permissions work
  private routes/DNS where required
  synthetic transaction succeeds

OPERATIONS
  metrics/logs/alerts usable
  what-if reviewed
  cost/owner/rollback documented
```

## 39. Bài tập thực hành

### Bài tập A — Viết module Storage đầu tiên

**Đề bài:** tự tạo `modules/storage.bicep` từ phần 6 với parameters `storageAccountName`, `location`, `skuName`, `tags` và outputs `storageAccountId`, `blobEndpoint`. Dùng `main.bicep` gọi module.

**Yêu cầu:**

1. Tên account có constraints và được test bằng tên hợp lệ.
2. HTTPS-only và minimum TLS 1.2.
3. Anonymous Blob public access disabled.
4. Không output account key.
5. `az bicep build` thành công.

**Hướng giải:** dùng `resource Microsoft.Storage/storageAccounts`, `@allowed` SKU, outputs resource ID/endpoint; xác minh security properties sau deploy. Nếu tổ chức cần private-only, thêm module networking riêng và test đúng policy.

### Bài tập B — Tách environment bằng `.bicepparam`

Một team copy `main-dev.bicep` sang `main-prod.bicep`. Hai file chỉ khác tên, SKU và tags.

**Nhiệm vụ:** tái cấu trúc thành một `main.bicep` với `dev.bicepparam` và `prod.bicepparam`, kiểm tra naming/scope an toàn.

**Hướng giải:** module được dùng chung, caller truyền environment/SKU/names; CI chọn subscription/RG bằng identity và allowlist, không dựa vào environment string để quyết định quyền.

### Bài tập C — Thêm VNet/Subnet module

Tạo `modules/network.bicep` có inputs `vnetName`, `vnetCidr`, `appSubnetName`, `appSubnetCidr` và output `appSubnetId`.

**Nhiệm vụ:** giải thích parent resource/child resource và vì sao không cần manual `dependsOn` khi subnet có `parent: vnet`.

**Hướng giải:** dùng `resource vnet` và `resource subnet ... { parent: vnet }`; xác minh CIDRs không overlap.

### Bài tập D — Tạo dependency giữa modules

Ứng dụng cần app subnet ID. Hãy viết composition Bicep gọi network module rồi compute module dùng `network.outputs.appSubnetId`.

**Nhiệm vụ:** giải thích cơ chế infer dependency; nếu compute module hoàn toàn độc lập, có nên ép dependsOn network không?

**Hướng giải:** reference outputs sẽ tạo dependency. Không thêm dependsOn nếu compute không thực sự cần network.

### Bài tập E — Cross-scope deployment

Từ subscription scope, tạo `rg-orders-dev` rồi gọi `storage.bicep` target resourceGroup.

**Nhiệm vụ:** viết `targetScope='subscription'`, `resource appRg` và `module storage {scope: appRg}`. Nêu cách gọi `az deployment sub create` và các quyền cần.

**Hướng giải:** module scope là RG được tạo; CLI cần deployment location và identity có quyền ở subscription + target RG.

### Bài tập F — Module có điều kiện

Một module diagnostics chỉ được bật ở production. Viết `module diagnostics ... = if (enableDiagnostics)`.

**Nhiệm vụ:** nêu cách tránh đọc output khi module bị skip và lý do **tắt điều kiện không tự bảo đảm xóa diagnostic settings cũ**.

**Hướng giải:** guarded references và rõ resource lifecycle/deletion policy; dùng what-if và review.

### Bài tập G — Module loop và quota

Ứng dụng cần ba Storage Accounts: uploads, processing, archive. Viết array inputs và module collection để tạo ba accounts.

**Nhiệm vụ:** đặt nested deployment names không trùng, giải thích `@batchSize(1)` và nguy cơ đổi thứ tự array.

**Hướng giải:** stable logical name nên được ưu tiên, quotas/cost phải được xem xét; `batchSize(1)` chỉ dùng khi cần tuần tự.

### Bài tập H — Publish module lên ACR

Platform team có một Azure Container Registry riêng chứa Bicep modules.

**Nhiệm vụ:** lập quy trình build → integration test → approval → publish version `1.2.0` → restore từ consumer. Nêu quyền publish/restore khác nhau và cách phòng overwrite tag.

**Hướng giải:** `az bicep publish` với `br:...:1.2.0`, consumer pin URI, service principals/managed identities có đúng role tùy ACR permission mode; immutable release convention.

### Bài tập I — Module alias và build lỗi

Một consumer sử dụng `br/platform:storage:1.2.0` nhưng CI báo không resolve alias.

**Nhiệm vụ:** tìm nguyên nhân và thiết kế fix.

**Hướng giải:** thiếu/không thấy đúng `bicepconfig.json`, `moduleAliases.br.platform` sai registry/modulePath hoặc artifact không tồn tại; tiếp tục kiểm tra ACR network/RBAC.

### Bài tập J — So sánh AVM và module tự viết

Nhóm muốn chuẩn hóa Storage Account. Hãy so:

- Sử dụng AVM module version đã publish.
- Viết resource module nội bộ.
- Wrapper AVM enforce security defaults.

**Nhiệm vụ:** chọn phương án và ghi rõ contract/version/upgrade tests.

**Hướng giải:** chọn theo organizational policy và capability; AVM có thể giảm effort nhưng vẫn cần verify network/diagnostics/outputs và release pinning.

### Bài tập K — Secure parameter và Key Vault

Một bạn đưa SQL admin password vào `prod.bicepparam` và output lại connection string.

**Nhiệm vụ:** nêu hai lỗi bảo mật và đề xuất cách truyền secure parameter hoặc loại password bằng Entra-managed identity khi khả thi.

**Hướng giải:** `@secure()`, secret source được bảo vệ; tuyệt đối không commit plaintext/echo outputs; identity/RBAC cho data plane.

### Bài tập L — What-if cho resource có dữ liệu

What-if báo đổi `storageAccount.name` từ `stordersprod01` sang `stordersprod02` và thêm Private Endpoint.

**Nhiệm vụ:** đánh giá nguy cơ replacement/data loss/old resource lifecycle, migration plan, cost và approval gates.

**Hướng giải:** không deploy tự động; inventory dữ liệu, backup/migration, owner review, post-cutover connectivity tests.

### Bài tập M — Azure Policy deny

`az deployment group validate` có vẻ hợp lệ nhưng deploy thất bại `RequestDisallowedByPolicy` do module bật anonymous Blob public access.

**Nhiệm vụ:** nêu vì sao module vẫn có thể compile và phương án sửa đúng.

**Hướng giải:** Azure Policy là governance layer riêng; cập nhật module defaults/params đáp ứng policy, kiểm thử trong test subscription; không đề xuất cấp Owner để bỏ policy.

### Bài tập N — Java không truy cập được Blob sau deployment

Bicep đã tạo Storage Account, Java SDK dùng `DefaultAzureCredential` nhưng nhận 403.

**Nhiệm vụ:** phân biệt resource provision thành công và data-plane authorization/network; viết checklist kiểm tra principal, Storage Blob Data role, firewall/DNS/private endpoint.

**Hướng giải:** RBAC và network là điều kiện độc lập; chạy test từ intended runtime identity, không fallback sang shared account key.

### Bài tập O — Backwards compatibility

Module `storage:1.3.0` đổi output `storageAccountId` thành `id`; nhiều app imports bản 1.2.0.

**Nhiệm vụ:** phân loại breaking change, đề xuất deprecation/migration và CI consumer compilation tests.

**Hướng giải:** giữ output cũ trong minor releases, thêm alias mới nếu cần; breaking removal phát hành major version kèm migration docs.

### Bài tập P — Reuse theo nhóm sở hữu

Platform team quản lý VNet, team product quản lý App Service, security team quản lý Key Vault. Hãy thiết kế modules và target scopes, xác định resource references dạng `existing` và outputs cần trao đổi.

**Hướng giải:** ownership rõ, app không sửa shared VNet, dùng resource IDs/approved scopes; tách deployment identities và review.

### Bài tập Q — Drift và rollback

Một operator bật public network access trên Portal, trong khi Bicep source để Disabled.

**Nhiệm vụ:** thiết kế kiểm tra drift bằng what-if + Azure Policy/Activity Log, xử lý thay đổi theo quy trình, rollback không gây outage.

**Hướng giải:** xác minh business need, security impact và owners; dùng audited approved change thay vì blind reapply.

### Bài tập R — Tính chi phí module upgrade

Module storage bản mới bật ZRS, Private Endpoint và diagnostic logs.

**Nhiệm vụ:** lập bảng khoản phí có thể phát sinh, cách ước tính và so sánh cost/availability/security trước prod rollout.

**Hướng giải:** Pricing Calculator/Cost Management, region/SKU/Log Analytics ingestion/PE data processing, what-if + canary.

### Bài tập S — Xây CI release gate

Thiết kế workflow cho service Java deploy modules Bicep với các giai đoạn:

```text
PR -> build -> restore -> validate -> what-if -> review
   -> dev deploy -> runtime smoke -> staging test
   -> prod approval -> prod what-if -> deploy -> monitoring
```

**Nhiệm vụ:** xác định identity nào cần ACR read, ai được publish module và ai có quyền deploy production.

**Hướng giải:** tách publisher/consumer/deployer identities, pin versions, OIDC federation với RBAC phù hợp, bảo vệ GitHub/Azure pipelines.

### Bài tập T — Thiết kế module hợp đồng production-ready

Tự xây bảng contract cho module `keyvault-private.bicep` với:

- Params: vault name, location, identity, subnet ID, private DNS zone ID, tags.
- Outputs: vault resource ID, vault URI, private endpoint resource ID.
- RBAC/Policy: không cho data plane public theo yêu cầu.
- Tests: DNS resolve private IP, Secrets User allow, no-role deny, public network deny, secrets không log.

**Nhiệm vụ:** chỉ ra điểm nào Bicep có thể khai báo và điểm nào cần **post-deploy test**.

**Hướng giải:** ARM có thể tạo vault/PE/zone group/roles; **runtime DNS, RBAC propagation và Java SecretClient read** phải được kiểm tra ngoài compiler.

## 40. Câu hỏi tự kiểm tra

**1. Bicep là gì?** Ngôn ngữ khai báo để tạo và triển khai ARM templates cho Azure resources.

**2. Bicep module là gì?** File/module reference được gọi từ Bicep template khác, đóng gói resources và hợp đồng params/outputs.

**3. Module có phải ứng dụng Java chạy trong Azure không?** Không. Nó được biên dịch/triển khai qua ARM, không chạy trong JVM.

**4. Vì sao module giúp giảm drift giữa teams?** Chuẩn hóa defaults/contract/versions và giúp kiểm tra thay đổi tập trung.

**5. Module nào nên trích riêng?** Thành phần có reuse thực, lifecycle/ownership boundary hoặc policy/complexity cần đóng gói.

**6. `targetScope` làm gì?** Xác định deployment scope mặc định của file Bicep.

**7. Symbolic resource name khác actual Azure name?** Symbol để tham chiếu nội bộ; `name` là tên tài nguyên được Azure dùng.

**8. `param` khác `var`?** Param là input của deployment/caller; var là expression tính bên trong template.

**9. `output` dùng để làm gì?** Expose kết quả có contract rõ cho caller/downstream modules.

**10. Có nên output Storage Account key?** Không; tránh secret exposure và dùng managed identity/data-plane RBAC khi phù hợp.

**11. `@allowed` giúp gì?** Giới hạn tham số vào tập được duyệt, không thay Azure Policy.

**12. `@secure()` có làm plaintext secret trong Git an toàn?** Không. Nó không mã hóa source file hay CI log.

**13. `module storage './modules/storage.bicep'` có nghĩa gì?** Gọi module local relative path với params và deployment name.

**14. Tên của module deployment có giống tên Storage Account không?** Không. Một là ARM nested deployment name; một là resource name thật.

**15. Tại sao Storage Account cần globally unique name?** Do quy tắc tên của Azure Storage service.

**16. `allowBlobPublicAccess=false` có đồng nghĩa public network disabled?** Không; nó chặn anonymous blob access, không tự tắt public endpoint.

**17. Hai môi trường dev/prod có cần copy root template?** Thường không; dùng cùng Bicep composition + parameter files/scopes khác.

**18. `.bicepparam` có an toàn cho password literal không?** Không; là source file, nên tránh plaintext secrets.

**19. Khi nào Bicep suy ra module dependency?** Khi downstream module tham chiếu resource/module output hoặc quan hệ được biểu diễn trong expression/scope.

**20. Khi nào nên dùng `dependsOn`?** Chỉ khi dependency thật chưa được Bicep infer từ các references/relations.

**21. Resource `existing` có tạo mới resource không?** Không; nó tham chiếu resource đang tồn tại để dùng metadata/scope.

**22. Module target RG có thể gọi từ root subscription không?** Có, khi `scope` chỉ đúng RG và principal có quyền tương ứng.

**23. Subnet child resource cần `parent: vnet` để làm gì?** Diễn tả quan hệ resource và dependency với VNet.

**24. `if (flag)` làm gì với module?** Chỉ deploy module khi điều kiện đúng; cần guard mọi output bị conditional.

**25. Tắt flag có chắc xóa resources module cũ không?** Không; phụ thuộc deployment/lifecycle mode, cần strategy riêng.

**26. `@batchSize(1)` có tác dụng gì?** Giới hạn module loop deployments tuần tự một instance tại một thời điểm.

**27. Vì sao không loop 1000 resources bừa bãi?** ARM/provider quotas, cost và deployment limits có thể bị vượt.

**28. Local module khác OCI registry module?** Local cùng repository/source revision; OCI publish và restore theo version/ref từ registry.

**29. `br:...` dùng để làm gì?** Reference OCI Bicep module từ registry như ACR.

**30. `bicepconfig.json` alias có tự cấp ACR permission không?** Không; chỉ rút gọn module URI, identity vẫn cần registry read role.

**31. Bicep module trên ACR có phải Docker image?** Không, là OCI artifact chứa module.

**32. Vì sao pin module version?** Để reproducible builds, review upgrades và tránh mutable dependency drift.

**33. AVM là gì?** Azure Verified Modules, tập module Bicep/Terraform theo tiêu chí/chính sách công bố, cần đánh giá version/security trước dùng.

**34. Có nên mặc định AVM phù hợp mọi policy nội bộ?** Không; phải review params/defaults/features và có thể dùng wrapper.

**35. Template Spec có giống Azure Policy không?** Không; nó lưu versioned template, không tự enforce compliance.

**36. Đổi tên output module là breaking change?** Có thể làm mọi callers dùng output cũ compile fail.

**37. `az bicep build` có deploy resource Azure không?** Không; nó compile template.

**38. `az deployment group validate` có đủ bảo đảm runtime không?** Không; deployment/provider/runtime network/IAM có thể vẫn lỗi.

**39. `what-if` dùng để làm gì?** Dự báo resource changes trước khi deploy; không đảm bảo mọi runtime behavior được biết.

**40. Tại sao what-if xóa vault/SQL phải chặn?** Vì resource data lifecycle, compliance và user impact có thể nghiêm trọng.

**41. Azure Policy có thể chặn Bicep deployment không?** Có; Bicep không bypass governance.

**42. CI ARM Contributor có chắc có quyền read Blob không?** Không; data-plane RBAC là quyền riêng.

**43. Module có tự bảo đảm app Java kết nối SQL/Blob thành công không?** Không; phải smoke/integration test từ runtime.

**44. Drift là gì?** Actual Azure resources khác expected template/policy state.

**45. Vì sao Git rollback không đồng nghĩa Azure resource rollback?** Resource state phải được redeploy/migrate có chủ đích; có thay đổi không đảo được.

**46. Deployment Stacks khác module?** Stacks quản lý resource lifecycle/deletion behavior; modules là cấu trúc template.

**47. Có nên tự xóa tất cả RG tiền tố test khi cleanup CI không?** Không; phải xác minh owner/run ID, resource IDs và job lifecycle.

**48. Vì sao không lấy average của what-if findings thành “risk score” tự động?** Mỗi thay đổi có impact khác nhau, cần phân tích resource/data/security và owner approval.

**49. Khi nâng module, cần kiểm tra gì?** Version contract, what-if, security/cost, staging deployment, runtime smoke và rollback plan.

**50. Module reusable-ready cần gì?** Typed documented inputs/outputs, safe defaults, version pinning, tests, IAM/security, lifecycle/owner và change governance.

## 41. Checklist chuẩn bị triển khai production

### 41.1. Hợp đồng module

- [ ] Module purpose, owner, scope và non-goals được ghi rõ.
- [ ] Inputs có type, description, required/default, constraints phù hợp.
- [ ] SKU/tier/network defaults align Azure Policy và business needs.
- [ ] Không hard-code account secrets, tenant-specific credentials hoặc production-only resource IDs tùy tiện.
- [ ] Outputs có tên/kiểu ổn định, không lộ secret/password/key.
- [ ] Resource/module symbolic names và actual resource naming được phân biệt.
- [ ] Azure API versions được chọn và kiểm thử, không tự dùng unsupported latest.
- [ ] Module boundaries phù hợp ownership/lifecycle và không tạo siêu module.
- [ ] Có migration/deprecation contract cho breaking changes.
- [ ] Có version, changelog, release owner và tài liệu samples.

### 41.2. Composition, dependencies và scopes

- [ ] Root Bicep composition chỉ gọi modules cần thiết, không copy implementation.
- [ ] Module input-output references tạo dependency rõ và tự động khi có thể.
- [ ] Không thêm unnecessary `dependsOn` làm deployment tuần tự vô lý.
- [ ] Cross-scope modules đúng `targetScope` và `scope`.
- [ ] Shared resources được tham chiếu bằng `existing` theo ownership.
- [ ] Child resources không bị nhiều writers cùng quản lý thiếu kiểm soát.
- [ ] Conditional modules và outputs được guard đúng.
- [ ] Loop module names unique/stable, số iterations có quota/cost guard.
- [ ] Subnet CIDR, VNet, peering, identities và DNS resources có plans riêng.
- [ ] Application readiness được kiểm tra sau ARM deployment.

### 41.3. Registry và supply chain

- [ ] Local module paths đúng và build trên CI filesystem.
- [ ] External module versions được pin cụ thể.
- [ ] ACR/private registry URI, alias và network connectivity được kiểm tra.
- [ ] Publisher và consumer có quyền repository write/read đúng permission mode.
- [ ] Artifact versions không bị overwrite tùy ý; build provenance có audit.
- [ ] AVM/Template Specs được chọn đúng release và contract.
- [ ] Có consumer compilation/integration tests khi nâng shared module.
- [ ] Không dùng floating “latest” module reference cho production.
- [ ] Có kế hoạch module registry outage/cache/retention.
- [ ] Toolchain Bicep/CLI versions được pin và kiểm tra compatibility.

### 41.4. Parameter files và Azure environments

- [ ] `.bicepparam` có `using` đúng root và env values hợp lệ.
- [ ] Dev/staging/prod sử dụng target subscriptions/RGs được allowlist.
- [ ] CI identity được phân scope, không chỉ dựa `param environment`.
- [ ] Naming globally unique/constraints được kiểm tra trước deploy.
- [ ] Region/SKU/service quotas đúng và có owner/cost center tags.
- [ ] Prod không trộn secret/data của dev/staging.
- [ ] Không commit plaintext secret trong parameter/source/config files.
- [ ] Có policy dành cho private networking/diagnostics/retention riêng theo environment.
- [ ] Rollback/DR plan liên quan resources có dữ liệu được phê duyệt.

### 41.5. Validation và change safety

- [ ] Bicep build/linter clean hoặc diagnostics đã được triage.
- [ ] ARM validate chạy ở đúng deployment scope.
- [ ] What-if từ **target subscription/RG thật** được review trước deploy.
- [ ] Destructive changes, public exposure, role/network changes có explicit approval.
- [ ] Modules được test trên non-prod RG với synthetic fixtures.
- [ ] Test idempotent redeploy và update of existing resources.
- [ ] Azure Policy/RBAC/quota/region errors được kiểm tra và report rõ.
- [ ] Runtime Java/Blob/Key Vault/SQL smoke tests sau deployment pass.
- [ ] Failed/partial ARM deployments có runbook, không giả định tự rollback.
- [ ] Resource drift/Activity Log/Policy compliance có monitoring.

### 41.6. Vận hành, bảo mật và chi phí

- [ ] Deployment identity và workload managed identity tách biệt.
- [ ] Data-plane RBAC roles scope tối thiểu, có kiểm thử thực.
- [ ] Private Endpoint/DNS/network paths được test theo production requirement.
- [ ] Không output secrets vào ARM deployment history/CI logs.
- [ ] Monitoring/diagnostic settings đúng categories và workspace governance.
- [ ] Cost impact của module upgrade được dự báo bằng Pricing Calculator và actual cost.
- [ ] Có alert/budget cho resources và logs/Private Endpoint costs.
- [ ] IaC changes có audit và policy-as-code, editor/deployer privileges tách biệt.
- [ ] Không xóa resources shared/production trong automated cleanup.
- [ ] Có approval, smoke verification và rollback/forward-fix owner sau deploy.
- [ ] Deployment artifacts, source versions, outputs và incidents được traceable.

## 42. Kết luận

**Module Bicep và tái sử dụng thành phần hạ tầng** giúp biến nhiều khai báo Azure rời rạc thành những **hợp đồng có thể sử dụng lại**: inputs có kiểu và constraints, outputs rõ ràng, dependencies được ARM/Bicep suy ra, phạm vi triển khai đúng và implementation được đóng gói. Với **module local**, đội có thể phát triển nhanh trong một repo; với **OCI registry trên ACR, Azure Verified Modules và Template Specs**, đội platform có thể phân phối các thành phần hạ tầng đã kiểm thử theo version cho nhiều ứng dụng và môi trường.

Thiết kế module tốt không dừng ở việc code ngắn hơn. Nó cần **safe defaults, parameterization, least-privilege Azure RBAC, network/data-plane security, diagnostics/tags, versioning và lifecycle policy**. Trước khi rollout hãy compile/lint, validate, xem **what-if**, test trên resource Azure không chứa dữ liệu production và chạy **smoke tests với ứng dụng Java** sau deployment. Đặc biệt, **module update không tự đảm bảo resource replacement an toàn, rollback không tự động và output không nên chứa bí mật**.

Khi kết hợp các module có trách nhiệm rõ ràng với **CI/CD approvals, Azure Policy, monitoring và cost governance**, nhóm phát triển có thể tái sử dụng hạ tầng mà vẫn giữ được khả năng kiểm soát theo subscription, resource group, ứng dụng và môi trường. Đó là nền tảng để triển khai kiến trúc Azure nhất quán, kiểm toán được và bền vững khi hệ thống phát triển.
