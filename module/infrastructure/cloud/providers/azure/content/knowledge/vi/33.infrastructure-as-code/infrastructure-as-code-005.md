# Quản lý parameter theo môi trường và bảo vệ giá trị nhạy cảm

Một ứng dụng thường dùng chung bản thiết kế hạ tầng nhưng cần cấu hình khác nhau ở **development (dev)**, **testing/staging (test)** và **production (prod)**. Ví dụ, môi trường dev có thể dùng Azure Storage mức dự phòng LRS để tiết kiệm chi phí, còn production yêu cầu mức dự phòng cao hơn, giám sát chặt hơn và quyền truy cập hạn chế hơn. Đồng thời, mỗi môi trường cần thông tin kết nối và thông tin xác thực riêng. Đặt toàn bộ những giá trị này trực tiếp vào template vừa khó bảo trì vừa dễ làm lộ bí mật.

Trong chương **Hạ tầng dưới dạng mã (Infrastructure as Code – IaC)** của lộ trình Microsoft Azure, chúng ta sẽ xây dựng cách **tách mã khai báo hạ tầng khỏi tham số cấu hình từng môi trường**, kiểm soát việc thay đổi parameter và bảo vệ những giá trị nhạy cảm từ lúc lưu trữ cho tới khi triển khai. Trọng tâm là **Bicep, file .bicepparam, ARM deployment, Azure Key Vault, Microsoft Entra ID** và cách đưa những thành phần này vào quy trình CI/CD. Các nguyên tắc cũng áp dụng khi dùng ARM JSON hoặc những công cụ IaC khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao một template nên phục vụ nhiều môi trường và xác định parameter nào cần thay đổi theo môi trường.
2. Viết Bicep có parameter, giá trị mặc định, ràng buộc và file **.bicepparam** riêng cho dev, test, prod.
3. Phân loại cấu hình thông thường, dữ liệu nhạy cảm và thông tin bí mật; quyết định loại nào được lưu trong Git.
4. Dùng **@secure()**, **Azure Key Vault** và cơ chế tham chiếu secret khi triển khai ARM/Bicep.
5. Thiết kế danh tính, quyền truy cập, phê duyệt và kiểm tra trước khi triển khai để hạn chế rò rỉ hoặc dùng sai cấu hình môi trường.
6. Chẩn đoán lỗi parameter và lập phương án thay đổi, xoay vòng bí mật, rollback.

## 2. Parameter là gì và vì sao phải phân tách?

**Template** mô tả các tài nguyên, quan hệ phụ thuộc và cấu hình hạ tầng cần tạo. **Parameter** là đầu vào để điều chỉnh template cho một lần triển khai: tên workload, Azure region, SKU, môi trường, tag, kích thước, tên Key Vault hoặc thông tin xác thực mà một tài nguyên yêu cầu.

Giả sử nhóm vận hành dịch vụ **orders-api** trên Azure. Cả ba môi trường đều cần Storage Account và tài nguyên ứng dụng, nhưng khác yêu cầu về chi phí, giám sát, dự phòng, quy mô và quyền. Nếu tạo ba bản sao Bicep rồi sửa tay từng bản, lỗi cấu hình và khác biệt ngoài ý muốn sẽ tích lũy rất nhanh.

Cách thiết kế phổ biến:

~~~text
main.bicep                 Template hạ tầng dùng chung
env/
  dev.bicepparam           Giá trị không nhạy cảm cho dev
  test.bicepparam          Giá trị không nhạy cảm cho test
  prod.bicepparam          Giá trị không nhạy cảm cho prod
~~~

Đây là cấu trúc ví dụ trong tài liệu; các tệp trên chưa được tạo trong dự án thực tế.

| Nhóm giá trị | Ví dụ | Đặt ở đâu? |
| --- | --- | --- |
| **Đầu vào dùng chung** | Mã workload, loại tài nguyên, quy tắc đặt tag | Template hoặc giá trị mặc định hợp lý |
| **Cấu hình theo môi trường** | environment, location, SKU, số instance, tên resource group, tag cost center | File .bicepparam trong Git khi không nhạy cảm |
| **Định danh tham chiếu** | Tên Key Vault, tên managed identity, URI endpoint không chứa token | File parameter hoặc kho cấu hình được kiểm soát |
| **Giá trị nhạy cảm** | Thông tin topo nội bộ, định danh tài nguyên được phân loại hạn chế | Chỉ lưu ở hệ thống có quyền truy cập phù hợp với chính sách |
| **Secret** | Mật khẩu, khóa API, private key, token, connection string chứa credential | Azure Key Vault hoặc kho secret được quản lý; chỉ truyền qua đường bảo mật |

**Secret** là giá trị mà người khác có thể dùng để chứng thực hoặc chiếm quyền truy cập. Một **Key Vault URI** thông thường chỉ xác định vị trí tham chiếu và không tự cung cấp quyền đọc secret; tuy nhiên, metadata đó vẫn có thể cần bảo vệ theo chính sách tổ chức.

Parameter giúp tái sử dụng template, nhưng **không nên parameter hóa mọi thứ**. Các quy tắc bảo mật bắt buộc, ví dụ chặn public blob access, có thể được cố định trong template hoặc thực thi bằng Azure Policy để tránh người triển khai vô tình nới lỏng chúng.

## 3. Ma trận parameter theo môi trường

Trước khi viết Bicep, tạo một **hợp đồng cấu hình** quy định giá trị và chủ sở hữu của chúng:

| Parameter | Dev | Test | Prod | Nguyên tắc |
| --- | --- | --- | --- | --- |
| **environment** | dev | test | prod | Danh sách giá trị cho phép |
| **resourceGroup** | rg-orders-dev | rg-orders-test | rg-orders-prod | Phân tách vòng đời và quyền |
| **location** | Chọn region phát triển | Chọn region kiểm thử phù hợp | Theo yêu cầu dữ liệu và DR | Kiểm tra dịch vụ có hỗ trợ region |
| **storageSku** | Standard_LRS | Standard_LRS | Standard_ZRS nếu region hỗ trợ | Thẩm định chi phí và khả năng sẵn có |
| **loggingRetention** | Thời gian ngắn | Phù hợp kiểm thử | Theo yêu cầu vận hành/tuân thủ | Không thấp hơn yêu cầu kiểm toán |
| **workloadCode** | order | order | order | Ổn định để truy vết tài nguyên |
| **keyVaultName** | Vault dev | Vault test | Vault prod | Tách bí mật và quyền giữa các môi trường |
| **adminPassword** | Secret riêng dev | Secret riêng test | Secret riêng prod | Không ghi giá trị trực tiếp vào Git |

**Không sao chép secret từ dev sang production.** Tách secret và danh tính từng môi trường giảm tác động khi một tài khoản hoặc pipeline bị xâm nhập. Trong hệ thống lớn, production có thể nằm ở subscription riêng với pipeline service connection và người phê duyệt riêng.

Đặc biệt cần phân biệt:

- **Thông số chọn môi trường:** dev, test, prod; đây là dữ liệu cấu hình.
- **Thông số vận hành:** SKU, instance count, retention; đây là cấu hình chịu sự quản trị về chi phí và độ sẵn sàng.
- **Thông số bí mật:** password, access token; đây là dữ liệu chỉ được cung cấp cho thành phần cần dùng.

## 4. Thiết kế template Bicep có ràng buộc parameter

### 4.1. Ví dụ main.bicep

Template sau tạo một Storage Account để minh họa cùng một Bicep áp dụng cho nhiều môi trường:

~~~bicep
targetScope = 'resourceGroup'

@description('Môi trường triển khai được phép.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string

@description('Mã workload: 3-5 ký tự chữ thường hoặc số.')
@minLength(3)
@maxLength(5)
param workloadCode string = 'order'

@description('Vùng Azure triển khai.')
param location string = resourceGroup().location

@description('Mức dự phòng Storage được phép dùng.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
])
param storageSku string = 'Standard_LRS'

@description('Tag bổ sung để quản lý tài nguyên và chi phí.')
param resourceTags object = {}

var storageName = toLower(format(
  'st{0}{1}{2}',
  workloadCode,
  environment,
  uniqueString(resourceGroup().id)
))

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: storageSku
  }
  kind: 'StorageV2'
  tags: union(resourceTags, {
    environment: environment
    workload: workloadCode
  })
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageAccountId string = storage.id
output storageAccountName string = storage.name
~~~

**Phân tích thiết kế:**

- **@allowed** giới hạn giá trị môi trường và SKU; giá trị sai bị phát hiện khi kiểm tra/triển khai.
- **@minLength** và **@maxLength** kiểm tra độ dài mã workload. Do Storage Account chỉ cho phép chữ thường và số, pipeline hoặc quy trình review còn phải kiểm tra tập ký tự đầu vào; decorator độ dài tự nó không kiểm tra được quy tắc này.
- **uniqueString(resourceGroup().id)** tạo phần tên có tính ổn định khi cùng resource group được triển khai lại. Hàm này **không tạo giá trị bí mật** và không bảo đảm tên không bao giờ trùng với tài nguyên thuộc người khác; tên Storage Account còn phải duy nhất toàn cục.
- **location** mặc định theo resource group nhưng có thể thay đổi khi yêu cầu kiến trúc cho phép.
- **union** gắn tag hệ thống **environment/workload** để người dùng không vô tình thay thế bằng các tag trùng tên trong resourceTags.
- **allowBlobPublicAccess: false** là chính sách bảo vệ được giữ cố định trong template.
- Hai **output** chỉ công bố ID và tên tài nguyên, không chứa thông tin đăng nhập.

Chú ý rằng **Standard_ZRS** không sẵn có cho mọi tổ hợp region và loại storage. Ví dụ cần thay SKU hoặc region theo thực tế của subscription; đây cũng là nguyên nhân phải chạy kiểm tra trước deployment.

### 4.2. File env/dev.bicepparam

~~~bicep
using '../main.bicep'

param environment = 'dev'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_LRS'

param resourceTags = {
  owner: 'platform-team'
  costCenter: 'dev-training'
  lifecycle: 'short'
}
~~~

### 4.3. File env/test.bicepparam

~~~bicep
using '../main.bicep'

param environment = 'test'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_LRS'

param resourceTags = {
  owner: 'qa-team'
  costCenter: 'orders-qa'
  lifecycle: 'temporary'
}
~~~

### 4.4. File env/prod.bicepparam

~~~bicep
using '../main.bicep'

param environment = 'prod'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_ZRS'

param resourceTags = {
  owner: 'operations'
  costCenter: 'orders-production'
  lifecycle: 'long'
}
~~~

Giá trị trong ba ví dụ là minh họa, chưa xác nhận quyền truy cập hoặc tính khả dụng của ZRS tại region đã chọn. Định nghĩa **using '../main.bicep'** cho biết file parameter áp dụng cho template nào; đường dẫn là tương đối với file **.bicepparam**.

Khi Bicep/CLI đã hỗ trợ **.bicepparam**, người triển khai có thể chỉ rõ file đó và công cụ sẽ lấy template từ câu lệnh **using**. Không cần sao chép **main.bicep** thành ba phiên bản và không cần đưa secret vào những file này.

## 5. Chạy what-if và triển khai đúng môi trường

Giả sử resource group đã được tạo, người thực hiện đăng nhập Azure CLI và chọn đúng subscription. Một quy trình thực hành an toàn cho dev:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az deployment group what-if \
  --resource-group rg-orders-dev \
  --parameters ./env/dev.bicepparam

az deployment group create \
  --resource-group rg-orders-dev \
  --parameters ./env/dev.bicepparam
~~~

Lệnh **what-if** dự đoán thay đổi đối với hạ tầng hiện tại trước khi áp dụng. Hãy kiểm tra tên tài nguyên, SKU, region, tag, các thay đổi mang tính phá hủy và tác động đến môi trường. What-if hữu ích nhưng có giới hạn khi phân tích những biểu thức hoặc tài nguyên phức tạp; không coi nó là bằng chứng rằng mọi thay đổi đều an toàn.

Với test/prod, chọn file và resource group tương ứng. Ví dụ:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --parameters ./env/prod.bicepparam
~~~

**Không tự động triển khai production chỉ vì what-if thành công.** Production nên dùng service connection hoặc danh tính có phạm vi riêng, có bước approval và policy phù hợp. Các lệnh trên giả định phiên bản Azure CLI/Bicep hỗ trợ file **.bicepparam**, Azure resource group đã tồn tại và danh tính có quyền cần thiết.

Một lỗi nghiêm trọng là chọn **prod.bicepparam** nhưng lại truyền resource group **rg-orders-dev**. Template có thể tạo tài nguyên mang nhãn prod trong nhóm dev nếu không có kiểm tra bổ sung. Vì vậy pipeline cần đối chiếu **environment ↔ subscription ↔ resource group ↔ file parameter ↔ service connection** trước lệnh triển khai.

## 6. Phân biệt parameter thông thường, secret và cấu hình runtime

Không phải mọi giá trị cấu hình đều được giải quyết trong cùng giai đoạn.

| Thời điểm | Ví dụ | Cơ chế phù hợp |
| --- | --- | --- |
| **Biên dịch/chuẩn bị IaC** | environment, workloadCode, SKU | Bicep parameter và .bicepparam |
| **Triển khai tài nguyên** | Mật khẩu quản trị được resource provider yêu cầu | Tham số **@secure()** và tham chiếu Azure Key Vault |
| **Ứng dụng đang chạy** | API key dùng mỗi khi gọi dịch vụ ngoài | Managed identity để đọc Key Vault hoặc cơ chế secret reference runtime của dịch vụ |
| **Pipeline điều phối** | Tên môi trường, resource group, tên service connection | Pipeline parameter/variable không nhạy cảm, với chính sách quyền |

**Ưu tiên loại bỏ secret nếu có thể.** Ví dụ, ứng dụng trên Azure dùng **managed identity** để truy cập Storage, Key Vault hoặc dịch vụ Azure khác có thể không cần lưu mật khẩu lâu dài. Nếu vẫn phải dùng credential, giữ nó ở nơi quản lý secret chuyên dụng.

Các giá trị như **client secret**, khóa ký, mật khẩu hoặc connection string có khóa truy cập tuyệt đối không nên xuất hiện trực tiếp trong Git, file **.bicepparam** được commit, comment YAML, output template hoặc file log.

## 7. Bicep @secure(): cần thiết nhưng chưa đủ

### 7.1. Khai báo secure parameter

Trong Bicep, dùng decorator **@secure()** với parameter kiểu **string** hoặc **object** chứa bí mật:

~~~bicep
@description('Mật khẩu quản trị SQL được cung cấp lúc triển khai.')
@secure()
param sqlAdminPassword string
~~~

ARM đánh dấu đầu vào tương ứng là secure string, giúp tránh ghi giá trị rõ vào dữ liệu parameter trong lịch sử triển khai. Tuy nhiên, **@secure() không phải là một kho bí mật**: người triển khai vẫn phải lấy giá trị từ nguồn an toàn và chuyển nó qua cơ chế phù hợp.

**Những điều @secure() không tự làm được:**

- Không xóa một password đã commit trong lịch sử Git.
- Không bảo vệ giá trị nếu script cố tình in ra stdout, bật debug/tracing hoặc truyền vào công cụ ghi log.
- Không ngăn việc đưa secret vào output, tag, metadata hoặc thuộc tính tài nguyên công khai/đọc được nếu tác giả template viết như vậy.
- Không thay thế RBAC, mã hóa, quy trình xoay vòng secret hay quyền tối thiểu.

Quy tắc: **không output secure parameter**, không ghép nó vào tên tài nguyên hoặc diagnostic log, và chỉ dùng nó ở thuộc tính thật sự cần để cấu hình dịch vụ. Một giá trị bí mật được truyền vào resource provider có thể chịu quy tắc hiển thị và lưu trữ riêng của dịch vụ đó; phải kiểm tra behavior của loại tài nguyên.

### 7.2. Ví dụ module database.bicep nhận secure parameter

Để minh họa đường truyền secret, module dưới đây khai báo Azure SQL logical server:

~~~bicep
targetScope = 'resourceGroup'

param sqlServerName string
param sqlAdminUser string
param location string = resourceGroup().location

@secure()
param sqlAdminPassword string

resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdminUser
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    publicNetworkAccess: 'Disabled'
  }
}

output sqlServerId string = sqlServer.id
~~~

Đây là ví dụ tập trung vào việc dùng secure parameter. Để có hệ thống SQL hoạt động, cần thiết kế tiếp các tài nguyên và cấu hình như database, kết nối private endpoint/DNS, firewall theo chính sách, backup và giám sát. Tạo Azure SQL có thể phát sinh chi phí; tên logical server phải duy nhất và mật khẩu phải đáp ứng chính sách Azure SQL. Không chạy đoạn mã chỉ để thử secret trên subscription production khi chưa đánh giá.

## 8. Lấy secret từ Azure Key Vault khi triển khai

Azure Key Vault cung cấp nơi lưu giữ và quản lý vòng đời của secret, key và certificate. Trong bài này chúng ta quan tâm **secret**. Một secret có tên, giá trị và có thể có nhiều **version**, hỗ trợ xoay vòng hoặc cố định version cho một đợt phát hành.

### 8.1. Phương án A — Tham chiếu Key Vault trong ARM JSON parameters

Một file ARM parameters **JSON** có thể dùng trường **reference** thay vì đưa giá trị password vào file. Ví dụ, nếu triển khai module **database.bicep** ở phần trước:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "sqlServerName": {
      "value": "sql-orders-prod-example"
    },
    "sqlAdminUser": {
      "value": "sqladminprod"
    },
    "sqlAdminPassword": {
      "reference": {
        "keyVault": {
          "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-secrets-prod/providers/Microsoft.KeyVault/vaults/kv-orders-prod"
        },
        "secretName": "sql-admin-password"
      }
    }
  }
}
~~~

Các chuỗi đặt trong dấu ngoặc nhọn góc là **placeholder** phải được thay bằng giá trị thực. Giá trị secret không xuất hiện trong JSON. Những trường khác phải trùng tên parameter của Bicep đích. Lệnh triển khai:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --template-file ./database.bicep \
  --parameters @./env/prod.secure.parameters.json

az deployment group create \
  --resource-group rg-orders-prod \
  --template-file ./database.bicep \
  --parameters @./env/prod.secure.parameters.json
~~~

Đây là **cơ chế file ARM JSON parameters**, khác cú pháp **.bicepparam** ở phần 4. Không trộn hai loại cú pháp trong cùng một file. Trong dự án thật, lựa chọn một cơ chế tổ chức nhất quán theo phiên bản toolchain và chính sách đội.

**Điều kiện để ARM tham chiếu Key Vault hoạt động:**

1. Secret **sql-admin-password** đã tồn tại trong vault.
2. Vault được cấu hình **enabledForTemplateDeployment** theo cơ chế ARM template deployment.
3. Danh tính thực hiện deployment được cấp quyền **Microsoft.KeyVault/vaults/deploy/action** phù hợp trên phạm vi vault; kiểm tra mô hình quyền của tenant/subscription.
4. Danh tính vẫn có đủ quyền trên resource group đích để triển khai Azure SQL.
5. Các chính sách tenant, vault, networking và Azure Policy không ngăn thao tác triển khai.

Ví dụ thay đổi cấu hình vault khi người quản trị đã được phép thực hiện:

~~~bash
az keyvault update \
  --name kv-orders-prod \
  --enabled-for-template-deployment true
~~~

Lệnh này thay đổi thuộc tính bảo mật của vault, vì vậy phải được review và giới hạn theo quy tắc phân quyền của tổ chức. Không cấp quyền quản trị rộng chỉ để sửa lỗi reference. Việc bật template deployment tự nó không cho mọi principal đọc tất cả secret.

**Không khai báo secret theo literal value trong file JSON.** Nếu một file chứa password đã được đẩy lên Git, phải coi giá trị đó đã lộ: thu hồi/xoay vòng credential và xử lý lịch sử kho mã theo quy trình ứng phó, thay vì chỉ xóa dòng ở commit mới.

### 8.2. Phương án B — Hàm getSecret() khi truyền tham số cho Bicep module

Bicep hỗ trợ gọi **getSecret()** từ Key Vault resource kiểu **existing** để truyền secret vào **secure parameter của module**:

~~~bicep
targetScope = 'resourceGroup'

param sqlServerName string
param sqlAdminUser string
param vaultName string
param vaultResourceGroup string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
  scope: resourceGroup(vaultResourceGroup)
}

module database './database.bicep' = {
  name: 'deploy-orders-sql'
  params: {
    sqlServerName: sqlServerName
    sqlAdminUser: sqlAdminUser
    sqlAdminPassword: vault.getSecret('sql-admin-password')
  }
}
~~~

Trong ví dụ này, file **database.bicep** là module đã khai báo **@secure() param sqlAdminPassword string** ở phần 7.2. Các parameter **vaultName** và **vaultResourceGroup** là định danh không chứa giá trị secret. Người triển khai vẫn phải đáp ứng các điều kiện quyền và thiết lập Key Vault ở phương án A.

Giới hạn cần nhớ: **getSecret() dùng trong ngữ cảnh gán giá trị cho secure parameter của module**. Không sử dụng nó để tạo output, chuyển thành một chuỗi thông thường hoặc đọc tùy ý trong biểu thức tính tên tài nguyên. Khi cần bí mật lúc **ứng dụng đang chạy**, ưu tiên managed identity và cơ chế runtime, không dùng deployment để sao chép password vào các output.

### 8.3. Nên dùng version secret cố định hay latest?

| Lựa chọn | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| **Tham chiếu version cụ thể** | Tái hiện deployment chính xác hơn, dễ audit | Xoay vòng phải có bước cập nhật tham chiếu |
| **Tham chiếu version mới nhất** | Thuận tiện để tự dùng bản vừa xoay vòng khi redeploy | Cùng template có thể dùng secret khác ở hai thời điểm |

Chính sách phụ thuộc quy trình rotation. Với secret version không được chỉ rõ trong ARM reference, cơ chế triển khai thường lấy phiên bản hiện hành theo cách Key Vault giải quyết tham chiếu. Đừng giả định ứng dụng đang chạy sẽ nhận secret mới ngay lập tức: hành vi làm mới phụ thuộc từng dịch vụ và cách ứng dụng tải secret.

## 9. Runtime secret: quản lý theo danh tính thay vì đưa vào template

Nếu ứng dụng chỉ cần API key hoặc connection string khi xử lý yêu cầu, một thiết kế phù hợp là cấp **managed identity** cho ứng dụng, rồi cho danh tính đó quyền đọc đúng secret trong Key Vault.

~~~mermaid
flowchart LR
  A["Git: main.bicep + env/prod.bicepparam"] --> B["CI/CD: validate và approval"]
  B --> C["ARM/Bicep deployment"]
  C --> D["Azure workload có managed identity"]
  V["Azure Key Vault: secret production"] -. "Đọc secret bằng identity được cấp quyền" .-> D
  C --> E["Resource configuration không chứa giá trị secret"]
~~~

Ví dụ: ứng dụng App Service có thể dùng **Key Vault references** trong app settings, còn Azure Container Apps có cơ chế tham chiếu Key Vault cho secret phù hợp. Cần xác minh tính năng hiện có, cấu hình identity, quyền và hành vi refresh của đúng dịch vụ. Không đưa connection string có password vào output của Bicep hoặc truyền qua resource tags.

Đối với Azure Storage và các API hỗ trợ Microsoft Entra ID, nên cân nhắc **RBAC qua managed identity** thay cho account key. Điều này giảm nhu cầu lưu bí mật lâu dài, đồng thời cho phép cấp/thu hồi quyền bằng chính sách.

## 10. Tách phạm vi và quyền truy cập từng môi trường

### 10.1. Một template, nhiều ranh giới quyền

~~~mermaid
flowchart TB
  G["Repository chứa IaC và parameter không nhạy cảm"] --> CI["Build: lint, validate, what-if"]
  CI --> DG["Deploy DEV"]
  CI --> TG["Deploy TEST"]
  CI --> PG["Prod approval + deploy PROD"]
  DG --> DEV["Subscription/RG dev + Key Vault dev"]
  TG --> TEST["Subscription/RG test + Key Vault test"]
  PG --> PROD["Subscription/RG prod + Key Vault prod"]
~~~

Việc tách subscription không bắt buộc trong mọi tổ chức, nhưng là lựa chọn hữu ích khi có yêu cầu cô lập môi trường, giới hạn chi phí hoặc áp dụng chính sách quản trị riêng. Ít nhất, hãy tách resource group, identity và secret theo phạm vi được chấp nhận.

| Vai trò | Quyền phù hợp | Không nên cấp mặc định |
| --- | --- | --- |
| Developer | Đọc/sửa Bicep, dùng môi trường dev theo nhu cầu | Quyền đọc secret production |
| CI validation | Đọc mã, thực hiện lint/validate/what-if với quyền tối thiểu | Owner toàn subscription |
| CI/CD dev deploy | Deploy vào RG dev | Quyền deploy RG production |
| Production deploy identity | Deploy đúng phạm vi production và tham chiếu vault theo cơ chế được phê duyệt | Quản trị không giới hạn mọi vault |
| Runtime managed identity | Đọc secret cụ thể cần cho workload, dùng tài nguyên theo RBAC | Quyền tạo/xóa secret hoặc quản trị vault |
| Approver | Xem kết quả kiểm tra và phê duyệt triển khai | Mật khẩu dùng chung với pipeline |

**Key Vault data plane** và **management plane** có cách phân quyền riêng. Với RBAC, chọn đúng vai trò và phạm vi cho thao tác cần thiết. Cơ chế **Microsoft.KeyVault/vaults/deploy/action** của ARM template deployment là một quyền cụ thể; không đồng nhất nó với quyền đọc secret trực tiếp của ứng dụng qua API Key Vault.

### 10.2. Service connection và đăng nhập CI/CD

Khi Azure Pipelines hoặc GitHub Actions triển khai IaC:

- Ưu tiên **workload identity federation/OIDC** khi hỗ trợ để tránh lưu client secret dài hạn.
- Có **service connection** hoặc danh tính riêng cho production, với subscription/resource group được giới hạn.
- Dùng branch protection, protected environment, approval và chính sách kiểm tra PR trước deploy.
- Không cho pipeline chạy từ pull request không đáng tin cậy nhận quyền truy cập production.
- Ghi nhận ai phê duyệt, commit nào, file parameter nào, subscription/RG nào và deployment ID nào đã được dùng.

**Pipeline parameter** và **pipeline variable** là công cụ điều phối, không tự động trở thành secret store. Đặc biệt, Azure Pipelines **runtime parameters** không nên được dùng để nhập mật khẩu; các giá trị đó có thể xuất hiện trong lịch sử hoặc giao diện chạy pipeline. Nếu cần secret trong job, dùng cơ chế secret variable/Key Vault phù hợp, nhưng với ARM deployment nên ưu tiên **Key Vault reference** để không cần chuyển plaintext secret qua command line.

## 11. Pipeline mẫu: kiểm tra và triển khai parameter theo môi trường

Với mục đích minh họa, dưới đây là một Azure Pipelines job cho **dev**, triển khai template ở phần 4. Môi trường prod nên có job được bảo vệ riêng và service connection riêng.

~~~yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: ValidateDev
    displayName: 'Kiểm tra thay đổi hạ tầng DEV'
    jobs:
      - job: WhatIf
        steps:
          - task: AzureCLI@2
            inputs:
              azureSubscription: 'sc-azure-orders-dev'
              scriptType: 'bash'
              scriptLocation: 'inlineScript'
              inlineScript: |
                az account show --query id -o tsv
                az deployment group what-if \
                  --resource-group rg-orders-dev \
                  --parameters ./env/dev.bicepparam

  - stage: DeployDev
    displayName: 'Triển khai hạ tầng DEV'
    dependsOn: ValidateDev
    condition: succeeded()
    jobs:
      - deployment: Apply
        environment: 'iac-dev'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self
                - task: AzureCLI@2
                  inputs:
                    azureSubscription: 'sc-azure-orders-dev'
                    scriptType: 'bash'
                    scriptLocation: 'inlineScript'
                    inlineScript: |
                      az deployment group create \
                        --resource-group rg-orders-dev \
                        --parameters ./env/dev.bicepparam
~~~

**Giả định của ví dụ:** Azure DevOps project có service connection tên **sc-azure-orders-dev**, môi trường **iac-dev**, resource group **rg-orders-dev**, các tệp Bicep tồn tại và agent có phiên bản Azure CLI/Bicep phù hợp. Job deployment có **checkout: self** để bảo đảm tìm thấy các file IaC khi chạy. Đối với production cần cấu hình approval/check ở Azure DevOps environment và kiểm tra quyền service connection; chỉ viết tên environment trong YAML **không tự tạo chính sách phê duyệt**.

What-if nên được lưu làm bằng chứng review có kiểm soát, nhưng phải kiểm tra log trước khi chia sẻ: một số output có thể chứa metadata nhạy cảm và thiết lập debug dễ vô tình làm lộ thông tin. Các bản build IaC không nên in biến bí mật hoặc bật chế độ trace shell khi sử dụng credential.

**Đối chiếu môi trường trước deploy** có thể xây dựng thành một bước chặn:

1. Xác minh tenant ID/subscription ID thực tế của service connection.
2. Xác minh resource group thuộc đúng subscription và môi trường.
3. Xác minh file **env/dev.bicepparam** chứa **environment = dev** và tham chiếu đúng template.
4. Kiểm tra các thay đổi từ what-if, Azure Policy và ngưỡng chi phí.
5. Chỉ khi đủ điều kiện mới chạy lệnh create với cùng file parameter.

Với production, tổ chức có thể yêu cầu hai người phê duyệt hoặc áp dụng policy riêng, nhưng mức độ kiểm soát phải xuất phát từ yêu cầu rủi ro thực tế.

## 12. Kiểm soát thay đổi và version hóa parameter

Một thay đổi nhỏ như **storageSku = Standard_ZRS** có thể làm thay đổi chi phí, yêu cầu region hoặc cách xử lý dữ liệu. Vì vậy file parameter cần được quản trị như mã nguồn.

Quy trình đề xuất:

1. **Pull request** cho thay đổi Bicep hoặc .bicepparam.
2. **Review ma trận môi trường**, kiểm tra xem giá trị ở prod có hợp lý và có vi phạm chính sách hay không.
3. **Validate và what-if** trong đúng subscription/RG, ghi nhận các thay đổi có khả năng ảnh hưởng đến tính sẵn sàng.
4. **Phê duyệt triển khai** theo quyền của môi trường đích.
5. **Lưu bản ghi deploy** gồm commit, phiên bản tool, parameter file, deployment ID, kết quả kiểm tra.
6. **Theo dõi hậu triển khai** và chuẩn bị giá trị parameter của bản trước để rollback nếu dịch vụ và loại tài nguyên cho phép.

Khi thay đổi **template interface** (ví dụ đổi tên parameter), phải cập nhật tất cả file **.bicepparam** và pipeline tiêu thụ. Để tránh đứt gãy khi nhiều pipeline chưa nâng cấp cùng lúc, cân nhắc giá trị mặc định có kiểm soát hoặc giai đoạn chuyển tiếp.

**Không nên cố định password mặc định** trong Bicep để tránh lỗi thiếu parameter. Nếu một secret bắt buộc, hãy khai báo tham số secure không có default và để deployment thất bại khi chưa được cấp đúng nguồn bí mật.

## 13. Chiến lược secret rotation và rollback

Các giá trị thông thường và secret có vòng đời khác nhau:

| Thay đổi | Hành động | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Đổi region/SKU | Review parameter, what-if, apply | Tài nguyên có thể không hỗ trợ region hoặc cần thay thế |
| Đổi Key Vault name | Cập nhật tham chiếu, cấp quyền cho identity | Bản cũ không truy cập được secret |
| Xoay vòng API key | Tạo version mới, cập nhật consumer, thu hồi version cũ | Dịch vụ chưa làm mới secret hoặc có cache |
| Xoay vòng SQL admin password | Phối hợp phía server và ứng dụng dùng credential | Mất kết nối nếu thay đổi không đồng bộ |
| Rollback Bicep | Khôi phục commit/parameter được duyệt, chạy what-if | Dữ liệu và thay đổi phá hủy không tự được đảo ngược |

Một cách xoay vòng an toàn cho runtime secret thường là **phát hành credential mới → cho consumer nhận credential mới → xác minh hoạt động → thu hồi credential cũ**. Tùy hệ thống, có thể cần khoảng chuyển tiếp cho hai credential. Với password chỉ hỗ trợ một giá trị, phải có cửa sổ thay đổi và kế hoạch khôi phục.

**Rollback IaC không đồng nghĩa rollback secret.** Nếu giá trị đã bị lộ thì không nên khôi phục credential cũ chỉ vì muốn quay về một commit trước đó. Khi một secret bị lộ, mục tiêu là thu hồi quyền của bí mật cũ và sửa nguồn lộ, không phải tái sử dụng giá trị bị xâm phạm.

## 14. Những sai lầm thường gặp và cách xử lý

| Vấn đề | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| **Thiếu required parameter** | Deployment báo parameter chưa được cung cấp | Kiểm tra khai báo Bicep, tên trong .bicepparam/JSON và default |
| **Sai kiểu hoặc ngoài @allowed** | Validate báo type mismatch hoặc invalid value | Chuẩn hóa kiểu, chỉnh file môi trường, giữ ràng buộc phù hợp |
| **Sai resource group/subscription** | Resource xuất hiện ở nơi không mong muốn hoặc permission denied | Kiểm tra account, service connection, target và file param trước deploy |
| **Tên Storage không hợp lệ** | Lỗi naming hoặc conflict | Kiểm tra chữ thường/số, độ dài 3–24 và tên duy nhất toàn cục |
| **SKU không hỗ trợ region** | Resource provider từ chối tạo | Kiểm tra khả năng hỗ trợ region, chọn SKU/region khác |
| **Cannot retrieve Key Vault secret** | ARM template báo thiếu quyền hoặc không tìm thấy secret | Kiểm tra vault ID, secret name/version, template deployment setting và deploy/action |
| **Secret hiện trong log** | Log hoặc build artifact chứa password/token | Thu hồi/rotation ngay, giới hạn log, loại bỏ cách truyền plaintext và điều tra truy cập |
| **Secret không cập nhật ở runtime** | Ứng dụng tiếp tục dùng key cũ | Kiểm tra refresh/caching, reload/restart và quyền của managed identity |
| **What-if khác thực tế** | Deployment thay đổi nhiều hơn dự đoán | Kiểm tra điều kiện runtime, provider behavior, Azure Policy và drift |
| **Quyền quá rộng** | CI có quyền Owner/Key Vault Admin không cần thiết | Tách identity và thu hẹp Azure RBAC/Key Vault permissions |
| **Drift sau sửa tay trên Portal** | Template áp dụng lại thay đổi ngoài ý muốn | Ghi nhận drift và đưa thay đổi hợp lệ trở lại IaC |

Khi xảy ra lỗi về secret, nên đi theo thứ tự **định danh vault/secret → identity dùng để lấy secret → quyền → cơ chế ARM/runtime → log an toàn**. Không “chữa” bằng cách copy password ra YAML hoặc cấp quyền Owner trên toàn subscription.

## 15. Bài thực hành: một Bicep cho dev và prod

**Bối cảnh:** Nhóm orders-api muốn dùng chung một template Storage cho dev và prod. Production có chính sách duyệt nghiêm ngặt hơn. Một module SQL tách riêng cần password từ Key Vault.

### Bài A — Parameter không nhạy cảm

1. Tạo **main.bicep** theo phần 4 trong repository thực hành được phép chỉnh sửa.
2. Tạo các file **env/dev.bicepparam** và **env/prod.bicepparam**, giữ cùng workloadCode nhưng thay environment, tag và SKU.
3. Tạo resource group đúng môi trường và chạy **what-if** vào dev.
4. Kiểm tra tên Storage Account được tạo từ quy tắc, xác nhận tag **environment = dev**.
5. Sau khi có quyền, kiểm tra what-if cho prod rồi so sánh SKU và tập tài nguyên dự kiến.

**Điều kiện đạt:** Không sửa **main.bicep** giữa hai lần chọn môi trường, không hardcode subscription trong template dùng chung, không có secret trong file parameter.

### Bài B — Tham chiếu secret

1. Đọc module **database.bicep** ở phần 7 và xác nhận parameter **sqlAdminPassword** được đánh dấu **@secure()**.
2. Tạo Key Vault và secret thử nghiệm bằng một quy trình được phép, tách biệt với production thật.
3. Chuẩn bị file ARM JSON parameters theo phần 8 với **reference** tới vault/secret; không ghi password literal.
4. Xác minh quyền ARM template deployment, chạy validate/what-if trên resource group thử nghiệm.
5. Quan sát thông tin deployment mà không bật debug lộ secret; kiểm tra giá trị password không xuất hiện trong source, parameter file, output, log chia sẻ.
6. Dọn các tài nguyên thử nghiệm theo chính sách và lưu bản ghi kết quả, không sao chép giá trị bí mật vào báo cáo.

**Điều kiện đạt:** Template nhận đúng tham số secure, reference hoạt động với quyền cần thiết, secret không bị đưa vào Git và không được công bố qua output.

### Bài C — Tình huống lỗi môi trường

Giả sử người vận hành chọn **prod.bicepparam** nhưng pipeline đang dùng service connection dev. Hãy viết bước kiểm tra phát hiện mismatch trước lệnh **create** bằng cách đối chiếu subscription, resource group và giá trị environment. Sau đó mô tả ai được quyền phê duyệt production và bằng chứng cần ghi lại.

**Điều kiện đạt:** Pipeline chặn được tổ hợp sai môi trường và không cần in secret để giải thích lỗi.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Có nên lưu giá trị **Standard_ZRS** trong Git?  
**Đáp án:** Có thể, vì đây là cấu hình thường; cần review chi phí, hỗ trợ vùng và khả năng sẵn sàng.

**Câu 2.** Có nên lưu mật khẩu Azure SQL trong file **prod.bicepparam** chỉ vì repository private?  
**Đáp án:** Không. Repository private vẫn có nguy cơ rò rỉ qua lịch sử commit, fork, runner và quyền người dùng. Dùng Key Vault và secure parameter.

**Câu 3.** Decorator **@secure()** có làm secret an toàn khi đưa vào output không?  
**Đáp án:** Không. Nó đánh dấu dữ liệu đầu vào nhạy cảm trong ARM deployment, nhưng tác giả template vẫn có thể làm lộ dữ liệu qua output, logs hoặc thuộc tính tài nguyên.

**Câu 4.** Khi nào dùng file **.bicepparam**, khi nào dùng **ARM JSON reference**?  
**Đáp án:** .bicepparam thuận tiện để định nghĩa đầu vào có kiểu và dùng chung với Bicep; ARM JSON parameters hỗ trợ cấu trúc **reference** để ARM lấy secret từ Key Vault khi deployment. Cần chọn công cụ phù hợp và tránh trộn cú pháp.

**Câu 5.** Vì sao nên ưu tiên managed identity cho secret dùng khi ứng dụng chạy?  
**Đáp án:** Vì ứng dụng có thể được cấp quyền trực tiếp, giảm việc phân phối credential tĩnh qua pipeline hoặc template và giúp thu hồi quyền tập trung.

**Câu 6.** Vì sao what-if không thể thay thế approval production?  
**Đáp án:** What-if chỉ dự đoán thay đổi với những giới hạn nhất định; nó không đánh giá toàn bộ tác động nghiệp vụ, an toàn dữ liệu, lịch bảo trì hoặc quyền phê duyệt.

## 17. Checklist trước khi triển khai IaC thực tế

- [ ] Template dùng chung cho nhiều môi trường, parameter có kiểu, mô tả và ràng buộc.
- [ ] Mỗi môi trường có file parameter không nhạy cảm riêng, được review trong Git.
- [ ] Pipeline đối chiếu subscription, resource group, environment và file parameter.
- [ ] Secret không xuất hiện trong Git, output, tên tài nguyên, tag hoặc log.
- [ ] Secure parameter được đánh dấu **@secure()** khi cần dùng secret lúc deployment.
- [ ] Key Vault reference hoặc **getSecret()** được áp dụng đúng ngữ cảnh với quyền đủ và không dư.
- [ ] Workload dùng managed identity để truy cập tài nguyên/secret lúc runtime khi khả thi.
- [ ] Quyền deploy dev/test/prod được phân tách; production có approval và Azure Policy phù hợp.
- [ ] What-if, review, kiểm tra chi phí và cấu hình được thực hiện trước apply.
- [ ] Có hồ sơ deployment, kế hoạch rotation secret và phương án rollback đã đánh giá tác động.

Quản lý parameter tốt giúp các môi trường **khác nhau ở những giá trị được kiểm soát** nhưng **giống nhau ở nguyên tắc kiến trúc và bảo mật**. Trong Microsoft Azure, kết hợp Bicep, .bicepparam, Azure Key Vault, Microsoft Entra ID và quy trình CI/CD có phê duyệt sẽ làm cấu hình dễ tái sử dụng, dễ truy vết và giảm nguy cơ làm lộ giá trị nhạy cảm.
