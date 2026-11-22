# Khai báo Azure Functions và tài nguyên liên quan bằng Bicep

Azure Functions là dịch vụ serverless chạy mã theo HTTP request, message hoặc event. Khi triển khai vào Azure, một Function App thường cần nhiều tài nguyên đi kèm: hosting plan, Storage Account, Application Insights, managed identity, quyền truy cập, cấu hình ứng dụng, trigger và đôi khi cả virtual network, queue, Key Vault hoặc deployment slot.

**Bicep** là ngôn ngữ Infrastructure as Code (IaC) khai báo tài nguyên Azure. Thay vì tạo từng tài nguyên bằng Portal, ta mô tả trạng thái mong muốn trong file .bicep, đưa tham số theo môi trường và triển khai qua Azure Resource Manager (ARM). Bicep biên dịch thành ARM template, hỗ trợ type checking, module hóa, dependency graph và what-if để xem trước thay đổi.

Với Java serverless, cần phân biệt hai phần triển khai: Bicep tạo và cấu hình hạ tầng; pipeline build Java, tạo package và triển khai mã function. Tách hai phần này giúp thay đổi code không phải tái tạo toàn bộ hạ tầng và giúp tài nguyên Azure có thể được review, tái lập và quản lý bằng version control.

## 1. Mô hình tài nguyên của một Azure Function App

Một Function App là đơn vị triển khai và cấu hình chứa một hoặc nhiều function. Nó chạy trên một hosting plan, dùng một runtime, có identity và kết nối tới các dịch vụ lưu trữ hoặc event source.

Một kiến trúc Java Function App thường có các tài nguyên:

| Tài nguyên | Vai trò |
|---|---|
| Resource group | Nhóm tài nguyên theo ứng dụng, môi trường hoặc vòng đời |
| App Service plan / hosting plan | Cấp compute và xác định cách scale, chi phí, giới hạn |
| Function App | Host mã function, runtime và cấu hình |
| Storage Account | Lưu host state, lease, artifact hoặc dữ liệu binding tùy workload |
| Application Insights | Thu thập telemetry, trace, exception và dependency |
| Log Analytics workspace | Nơi lưu và truy vấn log/telemetry theo cấu hình |
| Managed identity | Danh tính của Function App khi truy cập dịch vụ Azure |
| Role assignment | Cấp quyền RBAC cho identity trên từng tài nguyên |
| Queue, topic hoặc event source | Phát message/event để kích hoạt function |
| Key Vault | Lưu secret và certificate khi cần |
| Virtual network và subnet | Kết nối private tới database hoặc dịch vụ nội bộ |
| Deployment slot | Tạo staging slot để kiểm thử và swap nếu hosting plan hỗ trợ |

Sơ đồ tổng quan:

~~~mermaid
flowchart TD
    RG["Resource group"] --> PLAN["Function hosting plan"]
    RG --> FA["Java Function App"]
    RG --> ST["Storage Account"]
    RG --> LAW["Log Analytics workspace"]
    LAW --> AI["Application Insights"]
    FA -->|"System-assigned identity"| ID["Managed identity"]
    ID -->|"RBAC role assignments"| ST
    ID --> KV["Key Vault"]
    FA -->|"Telemetry"| AI
    Q["Queue / Event source"] -->|"Trigger or binding"| FA
    VNET["Virtual network"] -. "Private access when required" .-> FA
    FA --> SLOT["Deployment slot (supported plans)"]
~~~

Không phải mọi ứng dụng đều cần tất cả các tài nguyên này. Hãy bắt đầu từ trigger, quyền và dependency thật sự của function; sau đó bổ sung storage, monitoring và network theo nhu cầu.

## 2. Bicep và Azure Resource Manager

Bicep là ngôn ngữ khai báo. File Bicep mô tả tài nguyên và thuộc tính mong muốn; Azure Resource Manager (ARM) thực hiện deployment và điều phối thứ tự tạo tài nguyên.

Một file Bicep thường có các thành phần:

- **Parameters:** giá trị đầu vào theo môi trường, như tên app, location, SKU hoặc cấu hình runtime.
- **Variables:** giá trị tính toán lại được trong template, như tên tài nguyên hoặc role definition ID.
- **Resources:** tài nguyên Azure cần tạo hoặc cập nhật.
- **Modules:** phần template được tách thành file riêng để tái sử dụng.
- **Outputs:** thông tin cần trả về sau deployment, như Function App name hoặc hostname.

Ví dụ tối giản:

~~~bicep
param location string = resourceGroup().location
param functionAppName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stordersdemo001'
  location: location
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

output storageAccountId string = storage.id
~~~

Khai báo này tạo một Storage Account và xuất ID của nó. Bicep dùng cú pháp có type, nên IDE và compiler có thể phát hiện nhiều lỗi tên thuộc tính hoặc kiểu dữ liệu trước khi gửi deployment.

Bicep không phải script tuần tự. Bạn mô tả trạng thái mong muốn; ARM tự xác định dependency từ các tham chiếu tài nguyên. Nếu cần một dependency không thể suy ra từ tham chiếu, có thể khai báo dependsOn, nhưng nên ưu tiên tham chiếu trực tiếp để dependency graph rõ ràng.

## 3. Chọn deployment scope và tổ chức file

Bicep hỗ trợ nhiều scope:

- **Resource group:** thường dùng khi tạo Function App và các tài nguyên ứng dụng trong cùng một resource group.
- **Subscription:** dùng khi tạo resource group, policy hoặc tài nguyên cấp subscription.
- **Management group:** dùng cho governance trên nhiều subscription.
- **Tenant:** dùng cho một số thao tác ở phạm vi tenant.

Với một ứng dụng serverless thông thường, triển khai ở resource group là lựa chọn dễ quản lý. Resource group nên phản ánh vòng đời và quyền sở hữu. Không nhất thiết phải tạo một resource group cho từng function nếu chúng có cùng release lifecycle và security boundary.

Một cấu trúc repository có thể như sau:

~~~text
infra/
  main.bicep
  modules/
    function-app.bicep
    storage.bicep
    monitoring.bicep
    network.bicep
    role-assignments.bicep
  parameters/
    dev.bicepparam
    staging.bicepparam
    prod.bicepparam
src/
  OrdersFunction/
pom.xml
host.json
~~~

Cấu trúc này chỉ là gợi ý. Với hệ thống nhỏ, một file Bicep có thể dễ đọc hơn. Khi nhiều resource hoặc team cùng sở hữu hạ tầng, module hóa giúp tách trách nhiệm và tái sử dụng.

## 4. Parameters, variables và bảo vệ cấu hình

Không hardcode các giá trị khác nhau giữa dev, staging và production trong resource definition. Dùng parameters để truyền các giá trị theo môi trường.

Ví dụ:

~~~bicep
@description('Tên Function App, phải duy nhất toàn cục')
param functionAppName string

@description('Azure region triển khai tài nguyên')
param location string = resourceGroup().location

@description('Java runtime version')
@allowed([
  '17'
  '21'
])
param javaVersion string = '21'

@description('SKU của Linux Premium plan')
@allowed([
  'EP1'
  'EP2'
  'EP3'
])
param planSku string = 'EP1'

~~~

Bicep hỗ trợ decorator như @description, @allowed, @minValue, @maxValue, @minLength và @maxLength. Chúng giúp xác thực input và mô tả hợp đồng của template.

Với secret, dùng secure parameter:

~~~bicep
@secure()
param externalApiKey string
~~~

Tuy nhiên, secure parameter chỉ bảo vệ cách ARM xử lý giá trị trong deployment metadata; không làm cho việc truyền secret qua command line trở nên an toàn. Ưu tiên Key Vault reference hoặc managed identity để function lấy secret lúc chạy. Không commit secret vào file .bicepparam, source control hoặc log pipeline.

## 5. Chọn hosting plan trước khi khai báo Function App

Hosting plan ảnh hưởng cách khai báo tài nguyên, scale, networking, deployment và chi phí. Các lựa chọn thường gặp:

| Plan | Đặc điểm | Khi cân nhắc |
|---|---|---|
| Flex Consumption | Serverless theo event, scale linh hoạt, hỗ trợ cấu hình instance memory và concurrency | Workload event-driven cần scale theo tải và mô hình consumption hiện đại |
| Consumption (legacy) | Consumption-based, scale theo trigger, có giới hạn runtime và tính năng | Ứng dụng hiện hữu hoặc workload phù hợp giới hạn của plan |
| Premium | Có instance luôn sẵn sàng, hỗ trợ VNet và slot theo giới hạn plan | Cần giảm cold start, chạy lâu hơn hoặc kết nối mạng riêng |
| Dedicated (App Service) | Chạy trên App Service plan có capacity được cấp | Workload cần compute ổn định hoặc dùng chung plan với ứng dụng App Service |
| Azure Container Apps | Function chạy trong môi trường Container Apps, phát hành qua image/revision | Cần container workflow và khả năng quản lý revision/traffic |

Không nên dùng cùng một resource property set cho mọi plan. Flex Consumption dùng cấu hình functionAppConfig riêng; Premium/Dedicated thường dùng App Service plan và siteConfig; Azure Container Apps có mô hình container app/revision. Hãy chọn đúng schema/API version theo plan và region.

Ví dụ chính trong bài dùng Linux Premium plan để minh họa App Service plan, Function App, managed identity và RBAC. Khi triển khai Flex Consumption, cần dùng mẫu resource tương ứng của Flex thay vì chỉ đổi SKU của Premium.

## 6. Khai báo Storage Account

Azure Functions cần storage cho các hoạt động host và một số trigger/binding. Storage account cũng có thể chứa dữ liệu ứng dụng, nhưng nên phân biệt storage dành cho host với storage nghiệp vụ để dễ cấp quyền và quản lý vòng đời.

Ví dụ Storage Account:

~~~bicep
param location string = resourceGroup().location
param storageAccountName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

output storageId string = storage.id
output storageName string = storage.name
~~~

Tên Storage Account phải duy nhất toàn cục, dài từ 3 đến 24 ký tự và chỉ chứa chữ thường cùng chữ số. Bicep có thể tạo tên từ prefix và uniqueString(resourceGroup().id) để giảm nguy cơ trùng:

~~~bicep
var generatedStorageName = toLower('stfn' + uniqueString(resourceGroup().id))
~~~

Không bật public blob access nếu ứng dụng không có nhu cầu. Nếu dùng managed identity cho host storage, có thể tắt shared key access sau khi xác nhận các extension và quy trình vận hành đều hỗ trợ identity-based connection.

Storage redundancy như LRS, ZRS, GRS hoặc GZRS cần được chọn theo yêu cầu durability, region availability, recovery và chi phí. Không chọn redundancy chỉ theo thói quen; kiểm tra khả năng hỗ trợ của region và loại storage account.

## 7. Khai báo hosting plan và Java Function App

Ví dụ dưới đây tạo Linux Premium plan và một Function App dùng Java 21. Đây là cấu hình minh họa; runtime version và SKU cần được xác nhận theo region, subscription và yêu cầu của workload.

~~~bicep
param location string = resourceGroup().location
param functionAppName string
param javaVersion string = '21'
param planSku string = 'EP1'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-' + functionAppName
  location: location
  kind: 'elastic'
  sku: {
    name: planSku
    tier: 'ElasticPremium'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'JAVA|' + javaVersion
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'java'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
      ]
    }
  }
}

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionPrincipalId string = functionApp.identity.principalId
~~~

Một số thuộc tính:

- serverFarmId liên kết Function App với hosting plan.
- kind xác định đây là Function App chạy Linux.
- linuxFxVersion chọn Java stack version trên Linux App Service.
- FUNCTIONS_EXTENSION_VERSION chọn major version của Azure Functions host.
- FUNCTIONS_WORKER_RUNTIME=java chọn Java language worker.
- WEBSITE_RUN_FROM_PACKAGE=1 cấu hình chạy từ package đối với mô hình deployment hỗ trợ setting này.

Với Flex Consumption, không sao chép nguyên cấu hình này. Flex khai báo runtime, deployment storage, scaling và concurrency qua functionAppConfig; không dùng App Service plan EP1 hoặc dựa vào WEBSITE_RUN_FROM_PACKAGE=1 như ví dụ Premium.

## 8. Managed identity và RBAC cho host storage

Managed identity cho phép Function App truy cập dịch vụ Azure mà không phải nhúng password hoặc account key vào cấu hình. Với system-assigned identity, Azure tạo principal gắn với vòng đời Function App. Khi xóa Function App, identity này cũng bị xóa.

Để dùng identity-based connection cho AzureWebJobsStorage, cấu hình app settings thay cho connection string:

~~~bicep
{
  name: 'AzureWebJobsStorage__accountName'
  value: storage.name
}
{
  name: 'AzureWebJobsStorage__credential'
  value: 'managedidentity'
}
~~~

Function App cần được cấp quyền phù hợp trên Storage Account. Với host storage, các role thường cần gồm Storage Blob Data Owner, Storage Queue Data Contributor và Storage Account Contributor; nếu workload dùng Table storage hoặc extension khác, có thể cần thêm role tương ứng. Hãy xác nhận role requirements theo loại trigger, extension bundle và phiên bản Functions runtime.

Ví dụ role assignment cho system-assigned identity:

~~~bicep
var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var queueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'

resource hostBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, blobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      blobDataOwnerRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, queueDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      queueDataContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostStorageManagementRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, storageAccountContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageAccountContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
~~~

Các role ID trên là built-in role definition ID. Role assignment có scope là Storage Account và principal là identity của Function App. Tham chiếu functionApp.identity.principalId tạo dependency để ARM tạo Function App trước khi gán quyền.

RBAC có thể mất một khoảng thời gian để propagation. Nếu function khởi động ngay sau khi role assignment vừa được tạo, host có thể tạm thời gặp lỗi authorization. Pipeline nên chờ và kiểm tra readiness trước khi xem deployment là hoàn tất.

Không dùng Storage Account Contributor cho dữ liệu nghiệp vụ nếu function chỉ cần đọc một blob hoặc ghi một queue. Với dữ liệu ứng dụng, tạo role assignment riêng ở scope container, queue hoặc resource phù hợp để giảm quyền.

## 9. Application Insights và Log Analytics

Application Insights giúp quan sát invocation, exception, dependency và trace của function. Workspace-based Application Insights lưu dữ liệu trong Log Analytics workspace, giúp truy vấn cùng các log Azure khác.

Ví dụ:

~~~bicep
param location string = resourceGroup().location
param workspaceName string
param appInsightsName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

output workspaceId string = workspace.id
output appInsightsId string = appInsights.id
~~~

Kết nối Function App tới Application Insights qua app setting:

~~~bicep
{
  name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
  value: reference(appInsights.id, '2020-02-02').ConnectionString
}
~~~

Trong template tổng, có thể đặt app setting này trong siteConfig.appSettings của Function App. Tham chiếu reference tạo dependency tới Application Insights. Nếu dùng OpenTelemetry hoặc cấu hình telemetry khác, cần xác định cách instrument phù hợp với Java runtime và extension đang dùng.

Retention ảnh hưởng chi phí và thời gian điều tra. Chọn retention theo yêu cầu vận hành, audit và chính sách dữ liệu; tránh log payload chứa token, secret hoặc dữ liệu cá nhân không cần thiết.

## 10. Kết hợp các tài nguyên thành một template

Dưới đây là mẫu tổng hợp rút gọn cho Linux Premium Java Function App. Mẫu nhấn mạnh mối liên hệ giữa hosting plan, Storage, monitoring, identity và RBAC. Trước khi dùng production, hãy tách parameters, kiểm tra API version và bổ sung network, tags, alert, Key Vault cùng resource policy theo môi trường.

~~~bicep
@description('Azure region')
param location string = resourceGroup().location

@description('Function App name, globally unique')
param functionAppName string

@description('Java runtime version available in the selected region')
@allowed([
  '17'
  '21'
])
param javaVersion string = '21'

@description('Premium plan SKU')
@allowed([
  'EP1'
  'EP2'
  'EP3'
])
param planSku string = 'EP1'

var storageName = toLower('stfn' + uniqueString(resourceGroup().id))
var workspaceName = 'law-' + functionAppName
var appInsightsName = 'appi-' + functionAppName

var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var queueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-' + functionAppName
  location: location
  kind: 'elastic'
  sku: {
    name: planSku
    tier: 'ElasticPremium'
  }
  properties: {
    reserved: true
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'JAVA|' + javaVersion
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'java'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: reference(appInsights.id, '2020-02-02').ConnectionString
        }
      ]
    }
  }
}

resource hostBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, blobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      blobDataOwnerRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, queueDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      queueDataContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, storageAccountContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageAccountContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionPrincipalId string = functionApp.identity.principalId
output storageAccountName string = storage.name
output applicationInsightsName string = appInsights.name
~~~

Đây là baseline minh họa cho một Function App Linux Premium dùng identity-based host storage. Cần xác minh các role cần thiết theo trigger/extension thực tế. Nếu function chỉ dùng một số tính năng, có thể giảm role. Nếu triển khai Flex Consumption, thay resource configuration theo schema Flex; không dùng nguyên plan Premium trong mẫu.

Tên Storage Account được sinh từ resource group ID. Nếu cần giữ tên ổn định qua lần chuyển resource group, hãy truyền tên làm parameter và quản lý quy tắc naming riêng. Không đổi tên tài nguyên Azure hiện hữu bằng cách sửa thuộc tính name; nhiều loại tài nguyên cần tạo resource mới và migrate dữ liệu.

## 11. App settings, connection strings và Key Vault

App settings đưa cấu hình vào process của Function App. Những setting phổ biến:

| Setting | Mục đích |
|---|---|
| FUNCTIONS_EXTENSION_VERSION | Major version của Functions host |
| FUNCTIONS_WORKER_RUNTIME | Language worker, ví dụ java |
| AzureWebJobsStorage__accountName | Storage account dùng identity-based host connection |
| AzureWebJobsStorage__credential | Chọn managed identity credential |
| APPLICATIONINSIGHTS_CONNECTION_STRING | Kết nối Application Insights |
| WEBSITE_RUN_FROM_PACKAGE | Chạy từ package trong các plan hỗ trợ |
| APP_ENV | Tên môi trường ứng dụng |
| ORDERS_QUEUE_NAME | Tên queue nghiệp vụ |

Không nhúng secret vào Bicep hoặc file parameter được commit. Có hai cách thường dùng:

1. **Key Vault reference:** app setting chứa reference tới secret trong Key Vault. Function App identity được cấp quyền đọc secret.
2. **Managed identity trực tiếp:** Java code dùng Azure SDK DefaultAzureCredential hoặc Managed Identity credential để lấy secret hoặc gọi dịch vụ.

Ví dụ app setting tham chiếu Key Vault:

~~~bicep
{
  name: 'PAYMENT_API_KEY'
  value: '@Microsoft.KeyVault(SecretUri=https://kv-orders.vault.azure.net/secrets/payment-api-key/)'
}
~~~

Để reference hoạt động, Function App cần identity phù hợp và Key Vault cần cấp quyền đọc secret bằng RBAC hoặc access policy theo cấu hình vault. Nếu dùng user-assigned identity để resolve Key Vault reference, cần cấu hình identity reference tương ứng cho Function App. Kiểm tra trạng thái resolution trong Azure Portal hoặc diagnostic log.

Với Java code, không nên đọc app setting một lần rồi giả định secret không bao giờ rotation. Xác định cách refresh/caching phù hợp với TTL của secret và yêu cầu bảo mật.

## 12. Khai báo trigger và binding liên quan

Bicep tạo tài nguyên Azure và cấu hình ứng dụng, còn trigger/binding thường được định nghĩa trong mã Java bằng annotation. Khi deploy package, Azure Functions host đọc metadata được sinh từ Java build để đăng ký trigger.

Ví dụ Queue Trigger:

~~~java
@FunctionName("processOrder")
public void run(
    @QueueTrigger(
        name = "message",
        queueName = "orders",
        connection = "OrdersStorage"
    ) String message,
    final ExecutionContext context
) {
    context.getLogger().info("Received an order event");
    // Validate and process idempotently.
}
~~~

App setting OrdersStorage xác định connection tới Storage Queue theo cấu hình binding. Nếu dùng identity-based connection, cần khai báo các setting theo quy tắc của extension, ví dụ queue service URI và credential, đồng thời cấp role Storage Queue Data Message Processor cho identity. Tên setting cụ thể và role cần thiết phụ thuộc extension/version.

Với Service Bus, Event Hubs hoặc Cosmos DB trigger, Bicep có thể tạo namespace, queue, event hub, database hoặc subscription và cấp RBAC. Function package chứa annotation/binding tương ứng. Hãy kiểm tra rằng:

- Tên queue/topic trong annotation khớp resource được tạo.
- Connection setting trỏ đúng namespace/account.
- Function identity có role nhận message hoặc đọc event.
- Trigger có retry, poison message, checkpoint hoặc DLQ policy phù hợp.
- Staging không vô tình dùng cùng event source production nếu không chủ đích.

## 13. Network integration và private resources

Nếu function cần truy cập database hoặc API private, có thể cấu hình VNet integration trên hosting plan hỗ trợ. Bicep thường phải khai báo VNet, subnet dành riêng cho integration, security group và route theo kiến trúc mạng.

Những điều cần xác định:

- Hosting plan có hỗ trợ VNet integration và yêu cầu subnet riêng hay không.
- Subnet có đủ address space cho scale-out và các network interface cần thiết không.
- Security group cho phép outbound tới database hoặc dịch vụ đích.
- DNS phân giải đúng private endpoint.
- Route tới internet, NAT hoặc service endpoint được cấu hình đúng.
- Storage, Key Vault và các dependency có private endpoint nếu yêu cầu.
- Network restriction có cho phép deployment pipeline và runtime truy cập không.

Không phải cứ đặt Function App trong VNet là nó tự có quyền truy cập mọi tài nguyên private. Network path và authorization là hai lớp khác nhau. Security group có thể cho phép kết nối nhưng managed identity vẫn cần RBAC; ngược lại, role đúng không giúp kết nối thành công nếu DNS hoặc route sai.

Với Flex Consumption, VNet integration và network configuration có các yêu cầu riêng theo mô hình plan. Không sao chép cấu hình subnet của Premium sang Flex mà chưa kiểm tra tài liệu plan.

## 14. Deployment slot và tài nguyên phụ thuộc

Với Consumption, Premium hoặc Dedicated plan có hỗ trợ slot, có thể khai báo slot bằng resource type Microsoft.Web/sites/slots. Ví dụ:

~~~bicep
resource stagingSlot 'Microsoft.Web/sites/slots@2023-12-01' = {
  parent: functionApp
  name: 'staging'
  location: location
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      appSettings: [
        {
          name: 'APP_ENV'
          value: 'staging'
        }
      ]
    }
  }
}
~~~

Đây là phần minh họa cấu trúc resource; cần bổ sung cấu hình runtime, identity, storage, app settings và quyền riêng cho slot theo cách triển khai thực tế. Slot không được hỗ trợ trên Flex Consumption; Azure Functions trên Azure Container Apps dùng revisions.

Một số setting phải sticky để không bị hoán đổi khi swap, ví dụ database, storage, queue và cờ disable trigger. Bicep có thể quản lý slot app settings và cấu hình slot-specific theo schema của Microsoft.Web. Hãy kiểm tra sau deployment rằng setting đã được đánh dấu slot setting thật sự; chỉ tạo cùng tên app setting không tự làm nó sticky.

Managed identity và một số network setting có hành vi riêng theo slot. Đừng giả định system-assigned identity của production và staging là cùng một principal. Cấp role assignment đúng cho từng identity và giới hạn nguồn event mà staging được phép xử lý.

## 15. Tách Bicep thành modules

Khi template lớn lên, tách resource theo trách nhiệm. Ví dụ module Storage:

~~~bicep
// modules/storage.bicep
param storageAccountName string
param location string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
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

output storageId string = storage.id
output storageName string = storage.name
~~~

File chính gọi module:

~~~bicep
module storageModule './modules/storage.bicep' = {
  name: 'storageDeployment'
  params: {
    storageAccountName: storageName
    location: location
  }
}

output storageAccountId string = storageModule.outputs.storageId
~~~

Module giúp:

- Tái sử dụng mẫu đã được chuẩn hóa.
- Tách quyền sở hữu giữa team application, platform và security.
- Kiểm thử và review thay đổi độc lập.
- Giảm kích thước file chính.
- Chuẩn hóa naming, tagging, diagnostics và security baseline.

Không tạo module cho từng resource nhỏ nếu việc truyền parameter và output khiến template khó hiểu hơn. Một module nên gom các tài nguyên có cùng trách nhiệm và vòng đời.

Có thể dùng registry để chia sẻ module nội bộ giữa nhiều repository. Khi dùng module registry, pin version rõ ràng để build không tự nhận thay đổi ngoài ý muốn.

## 16. Parameters file cho dev, staging và production

Có thể tạo file .bicepparam cho từng môi trường:

~~~bicep
// parameters/dev.bicepparam
using '../main.bicep'

param location = 'southeastasia'
param functionAppName = 'fn-orders-dev-001'
param javaVersion = '21'
param planSku = 'EP1'
~~~

~~~bicep
// parameters/prod.bicepparam
using '../main.bicep'

param location = 'southeastasia'
param functionAppName = 'fn-orders-prod-001'
param javaVersion = '21'
param planSku = 'EP2'
~~~

Không để secret trong file parameter. Tên Function App phải duy nhất toàn cục; các tên khác cần tuân theo giới hạn của loại resource. Môi trường production có thể cần SKU, redundancy, retention, private networking và alert khác dev.

Tránh sao chép toàn bộ template cho từng môi trường. Giữ một module/entrypoint chung và thay đổi parameter để giảm drift. Với khác biệt kiến trúc thực sự như Flex so với Premium, có thể có module hoặc entrypoint riêng thay vì ép tất cả vào một template nhiều nhánh khó đọc.

## 17. Validate, what-if và triển khai Bicep

Một quy trình cơ bản:

1. Kiểm tra cú pháp và type.
2. Chạy linter để phát hiện pattern không tốt.
3. Xem trước thay đổi với what-if.
4. Deploy vào môi trường dev/staging.
5. Kiểm tra resource provisioning và role assignment.
6. Deploy code package.
7. Chạy smoke test.
8. Promote cấu hình sang production qua pipeline.

Các lệnh thường dùng:

~~~bash
az bicep build --file infra/main.bicep
az bicep lint --file infra/main.bicep
az deployment group what-if \
  --resource-group rg-orders-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
~~~

Khi kết quả what-if đã được review:

~~~bash
az deployment group create \
  --resource-group rg-orders-dev \
  --name orders-infra-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
~~~

What-if giúp nhìn thấy resource sẽ được tạo, sửa hoặc xóa trước deployment. Đặc biệt chú ý thay đổi có thể gây replacement, như tên resource, SKU, network hoặc storage setting. Một thay đổi có vẻ nhỏ trong template có thể dẫn đến resource replacement hoặc restart Function App.

Không chạy deployment production trực tiếp từ máy cá nhân mà không có review và kiểm soát quyền. Dùng service connection hoặc workload identity federation/OIDC của pipeline với quyền tối thiểu trên đúng subscription/resource group.

## 18. Tách triển khai hạ tầng và triển khai code

Bicep mô tả hạ tầng, còn Java package chứa handler và dependency. Hai phần có thể được phát hành độc lập:

~~~mermaid
flowchart TD
    A["Source commit"] --> B["Build Java with Maven"]
    A --> C["Validate Bicep"]
    B --> D["Publish immutable ZIP artifact"]
    C --> E["What-if and deploy infrastructure"]
    E --> F["Wait for identity/RBAC propagation"]
    D --> G["Deploy package to Function App"]
    F --> G
    G --> H["Smoke test HTTP/event trigger"]
    H --> I["Promote release"]
~~~

Ví dụ pipeline có thể:

- Chạy mvn -B clean verify và tạo deployment package.
- Chạy Bicep build/lint/what-if.
- Deploy tài nguyên vào resource group.
- Chờ RBAC propagation và kiểm tra health.
- Deploy package vào Function App bằng Azure Functions deploy task hoặc ZIP deployment.
- Chạy smoke test.
- Ghi lại commit SHA, artifact checksum và deployment name.

Nếu thay đổi code thường xuyên, không cần redeploy Storage Account hoặc workspace mỗi lần. Nếu thay đổi IAM hoặc network, cần triển khai hạ tầng trước khi phát hành code phụ thuộc vào quyền/cấu hình mới.

## 19. Quản lý drift, thay đổi và rollback

IaC chỉ hiệu quả khi Bicep là nguồn sự thật. Nếu ai đó thay đổi app setting, role assignment hoặc network rule trực tiếp trong Portal, trạng thái thực tế có thể khác template. Đây là configuration drift.

Các cách quản lý:

- Hạn chế quyền thay đổi production thủ công.
- Review mọi thay đổi IaC qua pull request.
- Chạy what-if trước deploy.
- Định kỳ kiểm tra drift và đối chiếu cấu hình.
- Giữ deployment history và artifact version.
- Pin module version và API version.
- Không xóa resource chỉ vì nó không xuất hiện trong một file template nhỏ; kiểm tra deployment mode và ownership.
- Dùng existing resource khi tham chiếu tài nguyên do stack khác quản lý.

Rollback hạ tầng không phải lúc nào cũng đơn giản như rollback code. Đổi SKU, storage configuration hoặc schema có thể gây replacement hoặc mất dữ liệu. Với database và storage, ưu tiên migration tương thích ngược, backup và recovery plan. Với Function App, giữ package version cũ trong artifact repository và triển khai lại khi cần.

## 20. Bảo mật và nguyên tắc least privilege

Bicep có thể tạo IAM/RBAC, network rule và secret reference, nhưng template hợp lệ không đồng nghĩa thiết kế đã an toàn.

Các nguyên tắc:

- Bật HTTPS-only và TLS tối thiểu phù hợp.
- Tắt public blob access nếu không cần.
- Dùng managed identity thay cho credential dài hạn.
- Cấp role assignment tại scope nhỏ nhất có thể.
- Tách identity của function theo workload hoặc ranh giới quyền.
- Không ghi secret vào output hoặc deployment log.
- Dùng Key Vault và RBAC cho secret.
- Hạn chế quyền deploy của pipeline theo resource group và môi trường.
- Bảo vệ Bicep parameter và state/secret của pipeline.
- Kiểm tra public network access, private endpoint và egress.
- Bật diagnostic settings và retention theo chính sách.
- Gắn tag owner, environment, data classification và cost center.

Đặc biệt, quyền deploy hạ tầng thường rộng hơn quyền runtime của function. Pipeline cần quyền tạo resource và role assignment theo quy trình được kiểm soát; Function App identity chỉ cần quyền đọc/ghi những tài nguyên nghiệp vụ mà handler thực sự dùng.

## 21. Sự cố thường gặp khi khai báo Azure Functions bằng Bicep

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Function App không tạo được | SKU hoặc API version không hỗ trợ ở region | Kiểm tra plan, region, quota và resource provider |
| Host không khởi động | Runtime stack, worker setting hoặc package không tương thích | Kiểm tra linuxFxVersion, FUNCTIONS_WORKER_RUNTIME, host logs |
| AzureWebJobsStorage authorization failure | Thiếu role hoặc identity connection setting sai | Kiểm tra principalId, role assignment, accountName và credential |
| Function không nhận message | Binding connection, queue name hoặc data-plane role sai | Kiểm tra annotation, app settings và role của trigger |
| Application Insights không có telemetry | Connection string thiếu hoặc SDK/extension chưa cấu hình | Kiểm tra app settings, instrumentation và log |
| Function không gọi được database private | DNS, route, subnet hoặc security group sai | Kiểm tra VNet integration và private endpoint |
| Deployment package không được nhận diện | ZIP có thư mục cha hoặc thiếu host.json | Kiểm tra cấu trúc ZIP và build output |
| Deployment báo thành công nhưng trigger không chạy | Function metadata, extension hoặc trigger setting sai | Kiểm tra host indexing và function logs |
| Bicep báo conflict role assignment | Role assignment name không ổn định hoặc đã tồn tại khác principal | Dùng GUID ổn định và kiểm tra scope/principal/role |
| What-if cho thấy resource replacement | Thay đổi thuộc tính immutable hoặc tên resource | Review change trước deploy và lập migration plan |

Khi gặp lỗi, kiểm tra theo từng lớp: ARM provisioning, identity/RBAC, app configuration, runtime startup, trigger connectivity và business logic. Không kết luận function code sai khi resource chưa được cấp quyền hoặc host chưa khởi động.

## 22. Checklist production cho Bicep và Azure Functions

Trước khi đưa template vào production, hãy kiểm tra:

1. Hosting plan phù hợp với runtime, scale, networking và yêu cầu deployment chưa?
2. API version của các resource provider có hỗ trợ thuộc tính đang dùng không?
3. Resource names có hợp lệ và ổn định không?
4. Parameters có mô tả, validation và default hợp lý không?
5. Secret có bị hardcode trong Bicep hoặc parameter file không?
6. Storage Account có HTTPS-only, TLS và public access setting phù hợp không?
7. Function App có managed identity không?
8. Role assignment có đúng principal, role và scope tối thiểu không?
9. AzureWebJobsStorage có cấu hình identity/connection đúng theo runtime không?
10. Java runtime, Functions host version và package có tương thích không?
11. App settings có đầy đủ và phân tách theo môi trường không?
12. Application Insights và Log Analytics có retention phù hợp không?
13. Trigger/binding có nguồn event và quyền data-plane đúng không?
14. VNet, subnet, DNS, route và private endpoint đã được kiểm thử chưa?
15. Slot hoặc revision strategy có phù hợp hosting plan không?
16. Bicep đã build, lint và what-if trước deploy chưa?
17. Hạ tầng và code package có pipeline riêng với artifact bất biến không?
18. Có kiểm tra readiness sau khi role assignment và resource provisioning hoàn tất không?
19. Có theo dõi drift, deployment history và chi phí không?
20. Có backup, rollback và recovery plan cho dữ liệu và resource quan trọng không?

## Tài liệu tham khảo

- [Bicep documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Azure Functions app settings reference](https://learn.microsoft.com/azure/azure-functions/functions-app-settings)
- [Configure an identity-based connection for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference#connecting-to-host-storage-with-an-identity)
- [Azure Functions Java developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Deploy Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies)
- [What-if operation for ARM deployments](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if)

## Kết luận

Bicep giúp khai báo Function App và các tài nguyên Azure liên quan thành một cấu hình có thể review, tái sử dụng và triển khai nhất quán. Một template đầy đủ cần mô hình hóa hosting plan, Function App, Storage, monitoring, managed identity, role assignment và những dependency như queue, Key Vault hoặc network theo đúng nhu cầu.

Với Java Function, Bicep nên quản lý hạ tầng và cấu hình runtime; Maven/CI pipeline quản lý build và package mã. Dùng parameters và modules để phân tách môi trường, managed identity để tránh credential dài hạn, RBAC theo least privilege và what-if để xem trước thay đổi. Khi kết hợp IaC với artifact bất biến, kiểm thử readiness và quy trình drift/rollback, nhóm có thể triển khai serverless có kiểm soát và dễ vận hành hơn.

