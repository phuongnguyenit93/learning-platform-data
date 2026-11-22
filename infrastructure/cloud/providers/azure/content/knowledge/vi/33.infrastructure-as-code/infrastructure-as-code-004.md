# Tham chiếu tài nguyên có sẵn và quản lý dependency

## 1. Vì sao cần phân biệt tài nguyên có sẵn và tài nguyên cần tạo?

Khi triển khai hạ tầng trên Microsoft Azure bằng **Infrastructure as Code (IaC)**, một ứng dụng thường dùng chung những tài nguyên đã tồn tại: Log Analytics workspace do nhóm vận hành quản lý, virtual network dùng chung, storage account chứa dữ liệu, hoặc App Service plan của một môi trường. Định nghĩa lại các tài nguyên này như tài nguyên cần tạo có thể khiến lần triển khai cố gắng cập nhật cấu hình mà nhóm ứng dụng không sở hữu.

Trong hệ sinh thái **CLOUD_PROVIDERS_AZURE**, bài học này nối kiến thức về subscription, resource group, danh tính và quyền truy cập với việc triển khai ứng dụng bằng **Bicep/ARM template**. Hai câu hỏi phải được trả lời riêng:

1. **Tham chiếu:** Tài nguyên nào đã tồn tại, nằm ở scope nào, có định danh Azure Resource Manager (ARM) nào và triển khai hiện tại được phép sử dụng ra sao?
2. **Thứ tự triển khai:** Tài nguyên nào thực sự được tạo trong lần triển khai này, và tài nguyên nào phải sẵn sàng trước khi tài nguyên khác có thể tạo hoặc cấu hình?

Ví dụ, một ứng dụng mới dùng Log Analytics workspace `law-shared` đã tồn tại. IaC phải lấy đúng resource ID của workspace và truyền cho Application Insights. Khi workspace được quản lý bởi một deployment khác, template ứng dụng **không được giả định** rằng việc tham chiếu sẽ tạo mới workspace hoặc chờ deployment bên ngoài hoàn tất.

Sau bài này, bạn có thể khai báo `existing` bằng Bicep, tham chiếu tài nguyên trong hoặc ngoài resource group, hiểu dependency tự động/tường minh, tổ chức dependency qua module và kiểm tra các rủi ro trước khi triển khai.

## 2. Mô hình tài nguyên trong Azure Resource Manager

Mỗi tài nguyên Azure có **resource type**, **name**, **scope** và **resource ID**. Với tài nguyên cấp resource group, ID có dạng:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>
/providers/<resource-provider>/<resource-type>/<resource-name>
~~~

Dòng trên được xuống hàng để dễ đọc; **resource ID thực tế là một chuỗi liên tục**. Chẳng hạn:

~~~text
/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-observability/providers/Microsoft.OperationalInsights/workspaces/law-shared
~~~

Các tài nguyên cấp subscription, management group, tenant và tài nguyên con có cấu trúc ID tương ứng với scope và quan hệ cha–con của chúng. Không nên tự nối chuỗi ID khi Bicep hoặc ARM có sẵn cách tạo định danh theo loại tài nguyên.

| Khái niệm | Ý nghĩa | Ảnh hưởng khi triển khai |
| --- | --- | --- |
| `resource name` | Tên tài nguyên tại scope thích hợp | Tên trùng nhưng khác scope có thể chỉ đến tài nguyên khác |
| `resource type` | Ví dụ `Microsoft.OperationalInsights/workspaces` | Xác định provider và các thuộc tính/API liên quan |
| `scope` | Subscription, resource group hoặc phạm vi khác | Quyết định nơi ARM tìm hoặc tạo tài nguyên |
| `resource ID` | Định danh đầy đủ, gồm scope và loại tài nguyên | Thường được dịch vụ khác sử dụng để liên kết |
| `apiVersion` | Phiên bản API của resource provider | Quyết định cú pháp/thuộc tính có thể đọc và khai báo |
| `dependency` | Quan hệ tài nguyên cần chờ tài nguyên khác hoàn tất triển khai | Kiểm soát thứ tự thực hiện **trong deployment** |

**Điểm mấu chốt:** `existing` trả lời câu hỏi *tham chiếu cái gì*; `dependsOn` và các dependency tự động trả lời câu hỏi *triển khai cái gì trước*. Chúng giải quyết hai vấn đề khác nhau.

## 3. Khai báo tài nguyên có sẵn bằng Bicep

Bicep dùng từ khóa `existing` để khai báo tài nguyên đã được tạo trước đó. Khai báo này tạo một **symbolic reference** để sử dụng trong template; nó không thêm thao tác tạo, cập nhật hay xóa chính tài nguyên được tham chiếu.

### 3.1. Tham chiếu trong cùng resource group

Tạo file `main.bicep` như sau. Ví dụ giả sử Log Analytics workspace `law-shared` đã có trong resource group nhận deployment; template chỉ tạo mới Application Insights liên kết với workspace đó.

~~~bicep
targetScope = 'resourceGroup'

@description('Tên Log Analytics workspace đã tồn tại trong resource group hiện tại.')
param workspaceName string

@description('Tên Application Insights cần tạo.')
param componentName string

@description('Vùng triển khai Application Insights.')
param location string = resourceGroup().location

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: componentName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

output applicationInsightsId string = appInsights.id
output connectedWorkspaceId string = workspace.id
~~~

Đọc từng thành phần:

- `workspace ... existing` xác định workspace đã có. Do không khai báo `scope`, Bicep dùng resource group hiện tại của deployment.
- `workspace.id` cung cấp resource ID để gắn vào `WorkspaceResourceId`; không phải connection string hoặc access key.
- `appInsights` không có `existing`, vì vậy ARM sẽ tạo hoặc cập nhật tài nguyên đó theo khai báo.
- `appInsights.id` là ID của tài nguyên được deployment quản lý. Nếu template được chạy lại với cùng tên, ARM sẽ đối chiếu trạng thái mong muốn thay vì cố tạo một bản sao độc lập.

**Lưu ý về kiểm tra tồn tại:** Việc sử dụng riêng `workspace.id` về cơ bản có thể tạo ID từ tên và scope; điều đó **không phải** bằng chứng workspace thực sự tồn tại. Dịch vụ liên kết hoặc resource provider sẽ kiểm tra ID khi xử lý cấu hình. Nếu mã đọc thuộc tính runtime của workspace, ARM có thể thực hiện lời gọi `reference` và trả lỗi sớm hơn.

### 3.2. Tham chiếu ở resource group hoặc subscription khác

Trong tổ chức có resource group dùng chung, phải khai báo `scope` tường minh. Đoạn Bicep độc lập sau trả về ID của storage account nằm ở một resource group có thể thuộc subscription khác:

~~~bicep
targetScope = 'resourceGroup'

@description('Subscription chứa storage account dùng chung.')
param sharedSubscriptionId string

@description('Resource group chứa storage account.')
param sharedResourceGroupName string

@description('Tên storage account đã được tạo.')
param storageAccountName string

resource sharedStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(sharedSubscriptionId, sharedResourceGroupName)
}

output sharedStorageId string = sharedStorage.id
~~~

Nếu tài nguyên ở **resource group khác trong cùng subscription**, có thể dùng `scope: resourceGroup(sharedResourceGroupName)`. Hàm `resourceGroup(subscriptionId, name)` cho phép tham chiếu resource group của subscription được chỉ định, khi loại tài nguyên và kiểu deployment hỗ trợ scope đó.

Một deployment không tự động được cấp quyền trên subscription hoặc resource group khác. Identity thực hiện triển khai cần quyền thích hợp để đọc/điều khiển tài nguyên, đồng thời các dịch vụ tiêu thụ tài nguyên có thể cần quyền bổ sung ở **data plane**. Quyền ARM và quyền truy cập dữ liệu là hai lớp khác nhau.

### 3.3. Tài nguyên con dưới tài nguyên cha đã tồn tại

Có thể tạo tài nguyên mới **bên trong** tài nguyên cha có sẵn. Ví dụ sau tạo một blob container qua management plane trong storage account và blob service `default` đã tồn tại:

~~~bicep
targetScope = 'resourceGroup'

param storageAccountName string
param containerName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

output containerId string = blobContainer.id
~~~

`parent` xác lập đường dẫn tài nguyên cha–con; `existing` trên `storage` và `blobService` không chuyển quyền quản lý toàn bộ storage account sang template này. Chỉ `blobContainer` là đối tượng được khai báo để triển khai. Storage account cần tồn tại, blob service khả dụng và identity triển khai phải có quyền management-plane tương ứng để tạo container.

## 4. Dependency hoạt động như thế nào?

Azure Resource Manager có thể triển khai các tài nguyên **song song** nếu không có quan hệ phụ thuộc. Khi một tài nguyên phải chờ tài nguyên khác, ARM cần một dependency để sắp xếp thứ tự.

~~~mermaid
flowchart LR
    A["NSG mới"] -->|"dependency: tạo trước"| B["Virtual network mới"]
    C["Log Analytics workspace có sẵn"] -.->|"resource ID dùng để liên kết"| D["Application Insights mới"]
~~~

Mũi tên liền diễn tả dependency triển khai giữa hai tài nguyên cùng được quản lý trong một deployment. Mũi tên nét đứt diễn tả quan hệ tham chiếu đến tài nguyên ngoài phạm vi tạo mới; nó **không** biến workspace có sẵn thành tác vụ tạo trước trong deployment hiện tại.

### 4.1. Dependency tự động từ symbolic reference

Trong Bicep, khi một tài nguyên **được tạo trong cùng deployment** dùng thuộc tính của tài nguyên khác được tạo cùng deployment, trình biên dịch thường sinh dependency cần thiết. Ví dụ:

~~~bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param nsgName string = 'nsg-app'
param vnetName string = 'vnet-app'

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'app'
        properties: {
          addressPrefix: '10.42.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}
~~~

Ở đây, `vnet` dùng `nsg.id` của **NSG mới**. Bicep có đủ thông tin để yêu cầu ARM triển khai NSG trước virtual network. Không cần thêm `dependsOn: [nsg]` vì như vậy chỉ lặp lại quan hệ đã được suy ra.

Tương tự, khi một tài nguyên mới dùng `parent` trỏ tới tài nguyên cha **mới**, Bicep tự hiểu quan hệ cha–con và tạo dependency phù hợp.

### 4.2. Tham chiếu đến `existing` không tạo dependency triển khai

Xét tình huống thay NSG mới ở ví dụ trên bằng NSG có sẵn:

~~~bicep
resource sharedNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' existing = {
  name: 'nsg-shared'
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-app'
  location: resourceGroup().location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.50.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'app'
        properties: {
          addressPrefix: '10.50.1.0/24'
          networkSecurityGroup: {
            id: sharedNsg.id
          }
        }
      }
    ]
  }
}
~~~

ARM sẽ sử dụng ID của `nsg-shared` khi tạo virtual network, **không** triển khai NSG đó. Nếu NSG chưa tồn tại hoặc ID sai, quá trình tạo liên kết có thể thất bại. Nếu NSG được tạo bởi pipeline khác, cần bảo đảm pipeline tạo NSG hoàn tất thành công **trước khi** bắt đầu deployment phụ thuộc.

Đừng dùng `existing` như một cách buộc hai deployment độc lập chờ nhau. Thứ tự giữa các pipeline/deployment phải được bảo đảm bằng pipeline orchestration, stage/job dependency hoặc cơ chế điều phối tương ứng.

### 4.3. Khi nào cần `dependsOn` tường minh?

Bicep hỗ trợ thuộc tính `dependsOn` cho tài nguyên hoặc module khi **thứ tự triển khai thực sự cần thiết** nhưng không thể suy ra từ reference/`parent`. Ví dụ khung cú pháp:

~~~bicep
// Bổ sung trong khai báo của một tài nguyên hoặc module được tạo mới:
// dependsOn: [
//   resourceCreatedEarlier
// ]
~~~

Chỉ thêm vào **đối tượng được tạo trong cùng deployment** (hoặc module triển khai trong deployment) sau khi chứng minh chúng có quan hệ thực tế. Thêm dependency không cần thiết sẽ làm giảm tính song song; xây dependency hai chiều còn có thể gây lỗi `CircularDependency`.

Với `existing`, không có tác vụ tạo resource tương ứng để chờ. Việc thêm `dependsOn` nhằm chờ một tài nguyên do deployment khác quản lý không giải quyết được vấn đề đồng bộ giữa hai deployment.

## 5. Dependency giữa các Bicep module

Khi tách hạ tầng thành module, nguyên tắc vẫn giống nhau: **truyền đầu ra của module tạo tài nguyên sang module hoặc tài nguyên tiêu thụ**. Việc đọc `module.outputs` tạo ra dependency cần thiết giữa các thao tác triển khai.

Ví dụ có hai file trong cùng thư mục.

**File `workspace.bicep` — tạo Log Analytics workspace:**

~~~bicep
targetScope = 'resourceGroup'

param workspaceName string
param location string

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

output workspaceId string = workspace.id
~~~

**File `main.bicep` — gọi module và tạo Application Insights:**

~~~bicep
targetScope = 'resourceGroup'

param workspaceName string
param componentName string
param location string = resourceGroup().location

module monitoring './workspace.bicep' = {
  name: 'deploy-monitoring-workspace'
  params: {
    workspaceName: workspaceName
    location: location
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: componentName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: monitoring.outputs.workspaceId
  }
}
~~~

Do `appInsights` sử dụng `monitoring.outputs.workspaceId`, ARM biết rằng module `monitoring` phải hoàn tất trước khi cấu hình tài nguyên tiêu thụ. Không cần khai báo lại thứ tự bằng `dependsOn`.

**Lựa chọn kiến trúc:** Nếu workspace thuộc nhóm nền tảng và được tạo trong pipeline độc lập, module ứng dụng nên nhận `workspaceName`/scope hoặc `workspaceResourceId` làm đầu vào, rồi dùng resource `existing` hoặc truyền trực tiếp ID phù hợp. Tránh kéo workspace vào module ứng dụng như một tài nguyên tạo mới, vì điều đó khiến deployment ứng dụng có thể thay đổi hạ tầng dùng chung.

## 6. Tương đương trong ARM JSON template

Bicep là ngôn ngữ khai báo biên dịch thành ARM JSON template. Trong ARM JSON truyền thống **không có từ khóa `existing` tương đương trực tiếp**. Với tài nguyên đã tồn tại, thường dùng `resourceId(...)` để dựng ID, hoặc `reference(...)` để đọc thông tin của nó.

Ví dụ ARM JSON dưới đây chỉ triển khai Application Insights và liên kết với Log Analytics workspace đã có trong cùng resource group:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "workspaceName": {
      "type": "string"
    },
    "componentName": {
      "type": "string"
    }
  },
  "resources": [
    {
      "type": "Microsoft.Insights/components",
      "apiVersion": "2020-02-02",
      "name": "[parameters('componentName')]",
      "location": "[resourceGroup().location]",
      "kind": "web",
      "properties": {
        "Application_Type": "web",
        "WorkspaceResourceId": "[resourceId('Microsoft.OperationalInsights/workspaces', parameters('workspaceName'))]"
      }
    }
  ]
}
~~~

Một số hàm ARM liên quan:

| ARM expression | Mục đích |
| --- | --- |
| `resourceId('Microsoft.Storage/storageAccounts', name)` | Dựng resource ID tại resource group hiện tại |
| `resourceId(rgName, 'Microsoft.Storage/storageAccounts', name)` | Dựng ID ở resource group khác thuộc cùng subscription |
| `resourceId(subscriptionId, rgName, 'Microsoft.Storage/storageAccounts', name)` | Dựng ID ở subscription/resource group chỉ định |
| `reference(resourceId(...), apiVersion)` | Yêu cầu ARM đọc thuộc tính runtime từ resource provider |
| `listKeys(resourceId(...), apiVersion)` | Gọi thao tác liệt kê khóa nếu resource provider hỗ trợ và identity có quyền |

**Cẩn trọng với dependency trong ARM JSON:** `resourceId(...)` chỉ xây dựng một ID; nó **không** tự tạo dependency. Khi cả nguồn và đích **đều được tạo trong cùng template**, cần thiết lập dependency theo cơ chế ARM (ví dụ `dependsOn`) nếu phép tham chiếu không tự tạo dependency. Trong ARM JSON, một số dạng `reference` sử dụng **tên tài nguyên trong cùng template** có thể suy ra dependency; dùng **resource ID đầy đủ** thường không làm vậy. Trong Bicep, symbolic reference thường giúp compiler tự xử lý quan hệ này rõ ràng hơn.

Không dùng `listKeys` hoặc đầu ra chứa secret chỉ để tìm ID. Nếu ứng dụng cần truy cập workspace, storage hay Key Vault, ưu tiên cơ chế identity và phân quyền phù hợp thay vì đưa credential ra output hoặc log deployment.

## 7. Cách xác định dependency đúng

Khi đọc một template, phân loại từng liên kết theo bảng sau:

| Tình huống | Cách khai báo | Ai bảo đảm thứ tự/sự tồn tại? |
| --- | --- | --- |
| Tài nguyên A mới cần ID của B mới trong cùng Bicep deployment | Tham chiếu `b.id` hoặc `b.properties...` | Bicep/ARM suy ra dependency |
| Tài nguyên con mới có cha mới | `parent: parentResource` | Bicep/ARM suy ra dependency |
| Tài nguyên A mới dùng B có sẵn | `b ... existing` và `b.id` | Nhóm vận hành phải bảo đảm B tồn tại; không có thao tác tạo B |
| Tài nguyên A cần kết quả từ module B | Dùng `moduleB.outputs.someValue` | ARM chờ module B hoàn tất |
| A và B mới cần thứ tự nhưng không có property reference | `dependsOn` tường minh nếu thật sự cần | ARM chờ theo khai báo |
| A và B được tạo bởi **hai pipeline khác nhau** | Đầu ra truyền giữa pipeline, stage/job ordering, kiểm tra điều kiện sẵn sàng | Công cụ điều phối pipeline, không phải `existing` |

Đối với dependency phức tạp, hãy vẽ sơ đồ các tài nguyên **do deployment hiện tại sở hữu** và hướng mũi tên từ tài nguyên tiên quyết đến tài nguyên tiêu thụ. Nếu phát hiện A phụ thuộc B và B lại phụ thuộc A, cần thay đổi thiết kế: tách giai đoạn tạo cơ sở khỏi giai đoạn cấu hình liên kết, hoặc loại bỏ tham chiếu vòng; đổi thứ tự dòng Bicep sẽ không giải quyết được chu trình.

## 8. Triển khai an toàn và xác minh

### Bước 1: Xác nhận resource ID và scope thực tế

Ví dụ với workspace đã có:

~~~bash
az account show --query "{subscription:id, tenant:tenantId}" -o json
az resource show \
  --resource-group rg-observability \
  --resource-type Microsoft.OperationalInsights/workspaces \
  --name law-shared \
  --query "{id:id,location:location}" -o json
~~~

Đầu tiên xác nhận subscription hiện hành, sau đó xác minh đúng workspace tại resource group dự kiến. Khi có nhiều subscription, chỉ rõ subscription mục tiêu bằng `--subscription` hoặc đặt context thích hợp trước khi chạy lệnh. Đọc được ID không đồng nghĩa identity ứng dụng có mọi quyền trên workspace.

### Bước 2: Đánh giá thay đổi trước khi áp dụng

Với ví dụ `main.bicep` ở mục 3.1, sau khi tài nguyên có sẵn đã được xác minh trong resource group mục tiêu:

~~~bash
az deployment group what-if \
  --resource-group rg-app \
  --template-file main.bicep \
  --parameters workspaceName=law-shared componentName=appi-demo
~~~

Lệnh này là ví dụ khi workspace nằm **trong chính `rg-app`**; nếu workspace nằm tại `rg-observability`, cần dùng phiên bản Bicep có `scope` tường minh như mục 3.2. Trước khi triển khai thực tế, đối chiếu đầu ra `what-if`: thay đổi dự kiến phải tập trung vào tài nguyên ứng dụng được quản lý; không nên có cập nhật bất ngờ lên hạ tầng dùng chung. `what-if` dự đoán thay đổi, không thay thế hoàn toàn kiểm tra quyền và tính hợp lệ tại thời điểm triển khai.

Khi kết quả phù hợp, có thể triển khai bằng:

~~~bash
az deployment group create \
  --resource-group rg-app \
  --template-file main.bicep \
  --parameters workspaceName=law-shared componentName=appi-demo
~~~

Đối với môi trường dùng chung, cần chọn đúng scope, parameter file và quy trình phê duyệt nội bộ trước khi thực hiện lệnh tạo.

### Bước 3: Kiểm tra liên kết sau triển khai

~~~bash
az resource show \
  --resource-group rg-app \
  --resource-type Microsoft.Insights/components \
  --name appi-demo \
  --query "{id:id,workspace:properties.WorkspaceResourceId}" -o json
~~~

So sánh `workspace` trong đầu ra với resource ID xác minh ở bước 1. Đồng thời kiểm tra trạng thái deployment và tính năng thực tế của dịch vụ; chỉ xuất hiện đúng ID chưa chứng minh dữ liệu telemetry đang được gửi thành công.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| `ResourceNotFound` / `ParentResourceNotFound` | Sai tên/scope hoặc cha có sẵn chưa tồn tại | Kiểm tra ID, subscription, resource group, loại tài nguyên và thứ tự provisioning bên ngoài |
| `InvalidResourceReference` hoặc lỗi liên kết | ID hợp lệ về cú pháp nhưng resource không tồn tại/không tương thích | Dò ID thực tế; kiểm tra vùng, kiểu tài nguyên và giới hạn dịch vụ |
| `AuthorizationFailed` / `LinkedAuthorizationFailed` | Identity thiếu quyền ở resource/scope được tham chiếu | Kiểm tra quyền RBAC tại cả scope triển khai và scope tài nguyên liên kết |
| `CircularDependency` | Các tài nguyên mới phụ thuộc vòng nhau | Sửa đồ thị dependency; tách tạo resource và bước cấu hình |
| Deployment chạy trước tài nguyên dùng chung | Pipeline bên ngoài chưa hoàn tất; tham chiếu `existing` không chờ | Thêm stage/job dependency và xác minh readiness |
| Triển khai thay đổi hạ tầng dùng chung ngoài dự kiến | Tài nguyên có sẵn bị khai báo như tài nguyên mới, hoặc scope sai | Chuyển sang `existing`, kiểm tra phạm vi sở hữu, chạy `what-if` |
| Không đọc được thuộc tính runtime | Chỉ có quyền dựng ID nhưng thiếu quyền đọc resource; API version không phù hợp | Kiểm tra quyền, phiên bản API và truy vấn resource provider |

Cũng cần phân biệt **readiness** với **deployment success**. Một tài nguyên có thể được ARM báo triển khai thành công nhưng dịch vụ phụ thuộc còn cần cấu hình mạng, phân quyền, DNS hoặc thời gian khởi tạo. Với hệ thống nhiều deployment, kiểm tra sức khỏe dịch vụ là trách nhiệm của quy trình điều phối, không nên giải quyết bằng `dependsOn` giả tạo.

## 10. Thực hành: ứng dụng dùng workspace do nhóm nền tảng quản lý

**Bối cảnh:** Nhóm nền tảng quản lý `law-shared` trong `rg-observability`; nhóm ứng dụng triển khai `appi-orders-dev` vào `rg-orders-dev`, cùng subscription. Nhóm ứng dụng cần quản lý Application Insights mà không sửa cấu hình workspace dùng chung.

1. Tạo `main.bicep` dựa trên mục 3.1 và bổ sung tham số `sharedResourceGroupName`. Trong khai báo `workspace ... existing`, đặt `scope: resourceGroup(sharedResourceGroupName)`.
2. Truyền `workspaceName=law-shared`, `sharedResourceGroupName=rg-observability` và `componentName=appi-orders-dev` khi gọi `what-if` với resource group đích `rg-orders-dev`.
3. Xác nhận kết quả không bao gồm thao tác tạo/cập nhật Log Analytics workspace. Kiểm tra `WorkspaceResourceId` dự kiến trùng với ID tài nguyên dùng chung.
4. Giả lập về mặt thiết kế tình huống workspace được tạo trong pipeline khác: xác định stage nào phải chạy trước và điều kiện nào chứng minh workspace đã sẵn sàng. Sau đó xem thử điều gì xảy ra khi chỉ giữ `existing` nhưng bỏ điều kiện chờ ở pipeline.

**Tiêu chí đạt:** Bicep chỉ có một tài nguyên mới thuộc quyền quản lý của ứng dụng; workspace được khai báo `existing` với đúng scope; liên kết sử dụng `workspace.id`; có bước xác minh sự tồn tại và quyền truy cập; dependency giữa các pipeline được xử lý rõ ràng. Không cần thay `existing` thành tài nguyên tạo mới chỉ để ép thứ tự.

## 11. Ghi nhớ khi thiết kế IaC Azure

- Dùng `existing` cho tài nguyên đã có, xác định đúng **tên + type + scope** và tách rõ quyền sở hữu giữa các nhóm.
- Dùng symbolic reference tới tài nguyên **mới** và `module.outputs` để Bicep suy ra dependency; chỉ thêm `dependsOn` khi có lý do kỹ thuật cụ thể.
- Phân biệt resource ID, quyền ARM, quyền data plane và trạng thái sẵn sàng của dịch vụ. Có ID chưa đảm bảo có quyền hoặc dịch vụ đã hoạt động.
- Điều phối các deployment độc lập bằng pipeline/stage và kiểm tra điều kiện sẵn sàng; `existing` không tự đồng bộ những deployment đó.
- Xem kết quả `what-if`, xác minh resource ID và kiểm tra liên kết sau triển khai để giảm nguy cơ ảnh hưởng tài nguyên dùng chung.

Nắm chắc cách tham chiếu tài nguyên hiện có và quản lý dependency giúp một kiến trúc Azure có thể tái sử dụng hạ tầng nền tảng, triển khai các thành phần theo đúng thứ tự và kiểm soát rõ tài nguyên nào thuộc phạm vi quản lý của mỗi template.
