# Kiểm tra thay đổi bằng ARM what-if

## 1. Vì sao cần xem trước thay đổi hạ tầng?

Trong phương pháp **Infrastructure as Code (IaC)**, chúng ta mô tả hạ tầng mong muốn bằng mã thay vì chỉnh sửa từng tài nguyên thủ công trên Azure Portal. Với Microsoft Azure, có thể khai báo các tài nguyên như resource group, virtual network, storage account, máy ảo, App Service và cấu hình bảo mật bằng **ARM template** (JSON) hoặc **Bicep** (ngôn ngữ biên dịch thành ARM template).

Giả sử nhóm vận hành đổi cấu hình Storage Account từ cho phép TLS cũ sang chỉ chấp nhận TLS 1.2. Một thay đổi nhỏ trong Bicep có thể ảnh hưởng đến ứng dụng khách đang kết nối. Nghiêm trọng hơn, thay đổi phạm vi triển khai hoặc chế độ triển khai không phù hợp có thể dẫn đến dự kiến xóa tài nguyên. Vì thế, trước khi áp dụng IaC, chúng ta cần biết **Azure dự kiến tạo, sửa hay xóa gì**.

**ARM what-if** là thao tác xem trước thay đổi do Azure Resource Manager cung cấp. Nó so sánh trạng thái tài nguyên hiện có với trạng thái được biểu diễn trong template và parameters, rồi trả về danh sách khác biệt **mà không thực hiện triển khai tài nguyên**. Có thể gọi thao tác này qua Azure CLI, Azure PowerShell hoặc công cụ dùng ARM deployment API.

Trong lộ trình học Azure từ subscription, resource group, mạng, compute, storage đến bảo mật và kiểm soát chi phí, what-if là một bước bảo vệ quan trọng trước khi áp dụng hạ tầng qua CI/CD. Nó bổ sung khả năng đánh giá tác động vào quy trình kiểm tra mã, kiểm thử và phê duyệt thay đổi.

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa **template validation**, **what-if** và **deployment**.
- Chạy what-if với Bicep/ARM template ở phạm vi resource group, và nhận biết cách áp dụng ở các phạm vi khác.
- Phân tích kết quả **Create, Modify, Delete, NoChange** cùng các trường hợp không thể dự đoán chắc chắn.
- Phân biệt ảnh hưởng của chế độ **Incremental** và **Complete**, tránh nhầm việc thiếu khai báo với việc xóa tài nguyên.
- Đưa kết quả what-if vào quy trình pull request, Azure Pipelines và bước phê duyệt trước deployment.
- Biết các giới hạn của what-if và cách kiểm tra lại sau triển khai.

## 2. ARM what-if hoạt động như thế nào?

Azure Resource Manager (ARM) là tầng điều phối triển khai tài nguyên Azure. Khi nhận template và tham số, ARM xác định tài nguyên cần triển khai, trạng thái được yêu cầu và những tài nguyên đang tồn tại trong phạm vi liên quan. What-if thực hiện phần phân tích khác biệt trước khi triển khai thực tế.

~~~mermaid
flowchart TD
    A["Bicep / ARM template"] --> C["ARM what-if"]
    B["Parameters + subscription + scope"] --> C
    D["Trạng thái tài nguyên hiện tại trên Azure"] --> C
    C --> E["Kết quả dự kiến: Create / Modify / Delete / NoChange / khác"]
    E --> F{"Đánh giá thay đổi"}
    F -->|"Chưa đạt"| G["Sửa template, parameters hoặc phạm vi"]
    G --> C
    F -->|"Đạt + được phê duyệt"| H["ARM deployment"]
    H --> I["Kiểm chứng trạng thái thực tế sau deploy"]
~~~

Điểm mấu chốt:

- **What-if là phép dự đoán tại một thời điểm.** Nó có thể gọi Azure để đọc và phân tích trạng thái, nhưng không tạo/sửa/xóa các tài nguyên đích theo template.
- **What-if không phải cơ chế khóa tài nguyên hoặc cam kết kế hoạch.** Giữa lúc xem trước và lúc triển khai, tài nguyên có thể thay đổi do người dùng, automation hoặc dịch vụ khác.
- **What-if không thay thế kiểm thử ứng dụng.** Một thay đổi API, cấu hình mạng hoặc quyền truy cập có thể được báo là Modify nhưng vẫn làm hệ thống ngừng hoạt động nếu tác động nghiệp vụ không được đánh giá.
- **What-if cũng không tự phê duyệt thay đổi.** Mã thoát thành công của lệnh có thể chỉ nói rằng quá trình phân tích chạy thành công, dù kết quả chứa tài nguyên dự kiến bị xóa.

### So sánh ba bước thường dùng

| Bước | Câu hỏi trả lời | Tạo hoặc thay đổi tài nguyên? | Ví dụ Azure CLI |
| --- | --- | --- | --- |
| Kiểm tra/validate template | Khai báo có hợp lệ về cấu trúc, tham số và các kiểm tra hỗ trợ hay không? | Không | `az deployment group validate` |
| What-if | Với trạng thái Azure hiện tại, khác biệt dự kiến của deployment là gì? | Không | `az deployment group what-if` |
| Deploy | Áp dụng trạng thái hạ tầng được khai báo vào Azure | Có thể có | `az deployment group create` |

Validation thành công **không** đồng nghĩa triển khai sẽ không phá vỡ hệ thống. What-if không cho phép thay thế bước validation, vì hai bước cung cấp thông tin bổ sung cho nhau.

## 3. Đọc các loại thay đổi trong kết quả

ARM what-if thường trả về các kiểu thay đổi sau (cách biểu diễn và độ chi tiết có thể phụ thuộc phiên bản công cụ, loại tài nguyên và định dạng kết quả):

| Change type | Ý nghĩa thực hành | Cách đánh giá |
| --- | --- | --- |
| **Create** | Tài nguyên được khai báo và dự kiến cần được tạo mới | Kiểm tra tên, region, SKU, chi phí, quyền, kết nối mạng và quota |
| **Modify** | Tài nguyên hiện có dự kiến có ít nhất một thuộc tính thay đổi | Đọc từng thuộc tính trước/sau; xác định rủi ro downtime, thay đổi quyền hay bảo mật |
| **Delete** | Tài nguyên nằm trong phạm vi phân tích có thể bị xóa theo semantics của deployment | Dừng để xác minh scope, mode, dữ liệu, backup, phụ thuộc và quyền phê duyệt |
| **NoChange** | Công cụ không dự đoán khác biệt cần hiển thị | Vẫn cần kiểm tra trạng thái ứng dụng và các tác động ngoài khả năng dự đoán |
| **Ignore / Deploy / Unsupported** | Kết quả không nằm trong bốn loại trên, thường do phạm vi phân tích hoặc giới hạn suy luận/tài nguyên | Đọc lý do và tài liệu công cụ, không suy diễn là an toàn hay đã biết chính xác thay đổi |

Một kết quả what-if có thể chứa thông tin tài nguyên (resource ID), `changeType`, payload trước/sau và danh sách các trường khác biệt, tùy định dạng. Ví dụ minh họa cách đọc:

~~~text
~ Microsoft.Storage/storageAccounts/stiacdemo12345
  ~ tags.costCenter:
      before: "trial"
      after:  "platform"
  ~ properties.minimumTlsVersion:
      before: "TLS1_0"
      after:  "TLS1_2"
~~~

Đây là **minh họa**, không phải bản sao nguyên văn đầu ra của một phiên bản Azure CLI cụ thể. Dấu `~` biểu thị ý nghĩa sửa đổi trong ví dụ. Khi chạy thật, bạn cần đọc resource ID, tên thuộc tính và giá trị trước/sau trên chính output của mình.

**Đừng chỉ đếm số lượng Modify.** Một thay đổi ở `tags` thường có tác động khác hẳn thay đổi `networkAcls`, `publicNetworkAccess`, `identity`, `sku`, `subnets` hoặc `ipSecurityRestrictions`. Hãy xem bản chất và phạm vi thay đổi.

## 4. Chuẩn bị môi trường thực hành

Ví dụ dưới đây triển khai một **Storage Account** trong một **resource group**. Bạn cần:

1. Có Azure subscription và quyền đọc/phân tích deployment trong phạm vi dự định. Cần các quyền ARM/resource provider phù hợp; quyền cụ thể phụ thuộc deployment và tổ chức.
2. Cài Azure CLI có hỗ trợ Bicep, đăng nhập tài khoản hoặc service principal/workload identity đã được cấp quyền.
3. Có resource group thử nghiệm. Tránh thử chế độ Complete trực tiếp trên resource group đang chứa tài nguyên quan trọng.
4. Lưu template và parameters trong hệ thống quản lý phiên bản để kiểm tra thay đổi thông qua pull request.

Các lệnh sau giả định bạn đã đăng nhập và biết chính xác subscription cần làm việc:

~~~bash
# Xem account và subscription đang chọn.
az account show --query "{name:name,id:id,tenantId:tenantId}" -o table

# Chọn đúng subscription trước mọi thao tác.
az account set --subscription "<subscription-id>"

# Ví dụ tạo resource group lab nếu chưa có (lệnh này THỰC SỰ tạo resource group).
az group create --name rg-iac-whatif-dev --location southeastasia
~~~

Chỉ lệnh **what-if** mới là xem trước. `az group create` trong phần chuẩn bị có thể thay đổi tài nguyên; hãy phân biệt rõ công việc tạo lab ban đầu với thao tác phân tích không triển khai.

### 4.1 Viết template Bicep

Giả sử lưu file `infra/main.bicep`:

~~~bicep
@description('Tên Storage Account phải duy nhất trên toàn Azure, 3-24 ký tự chữ thường/số.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Vị trí triển khai Storage Account.')
param location string = resourceGroup().location

@allowed([
  'dev'
  'test'
  'prod'
])
param environment string = 'dev'

param costCenter string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  tags: {
    environment: environment
    costCenter: costCenter
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageAccountId string = storage.id
~~~

Template này mô tả trạng thái mong muốn: Storage Account loại StorageV2, redundancy LRS, HTTPS bắt buộc, TLS tối thiểu 1.2 và không cho phép public blob access. Tên tài nguyên phải **duy nhất toàn cục**, do đó tên trong bài chỉ là ví dụ và cần thay bằng tên hợp lệ chưa được sử dụng.

Lưu file tham số `infra/parameters/dev.parameters.json`:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "storageAccountName": {
      "value": "stwhatifdemo12345"
    },
    "environment": {
      "value": "dev"
    },
    "costCenter": {
      "value": "platform"
    }
  }
}
~~~

Tham số `location` không được truyền nên Bicep lấy vị trí của resource group. Trong môi trường thật, đặt tên theo quy tắc tổ chức và tách tham số cho từng môi trường; **không đưa password, access key hoặc secret dạng rõ** vào file JSON đã commit.

## 5. Thực hiện ARM what-if với Azure CLI

### 5.1 Validate trước, what-if sau

Ở thư mục gốc repository, chạy:

~~~bash
az deployment group validate \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json

az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental \
  --result-format FullResourcePayloads
~~~

Lệnh `what-if` yêu cầu Azure xem trước thay đổi với các giá trị parameters đã truyền; **không** thực hiện việc tạo Storage Account. Nếu tài nguyên chưa tồn tại, dự kiến thấy **Create**. Nếu tài nguyên đã tồn tại với trạng thái được công cụ xem là khớp, có thể thấy **NoChange**.

`FullResourcePayloads` cho phép nhận nhiều chi tiết hơn để xem thay đổi thuộc tính. Trong trường hợp chỉ muốn biết những resource ID nào thay đổi, có thể xem xét `--result-format ResourceIdOnly`; tuy nhiên định dạng ít chi tiết sẽ không đủ để review cấu hình bảo mật hoặc các thay đổi có rủi ro cao.

### 5.2 Điều chỉnh một thuộc tính và xem khác biệt

Giả sử Storage Account đã được triển khai từ phiên bản template cũ, nơi `costCenter` bằng `trial`. Nay đổi parameters sang `platform` và chạy lại `what-if`.

Kết quả dự kiến có dạng **Modify**, chỉ rõ `tags.costCenter` thay đổi. Nếu bạn đồng thời đổi `minimumTlsVersion`, what-if có thể hiển thị thay đổi đó. Sau đó, người review cần kiểm tra cả:

- Thay đổi có đúng tài nguyên và subscription đang nhắm đến không?
- Có thay đổi bất ngờ về vị trí, tên, SKU, replication, network access hoặc identity không?
- Ứng dụng sử dụng tài nguyên có hỗ trợ cấu hình mới không?
- Có yêu cầu duyệt bảo mật, bảo trì, truyền thông hoặc kế hoạch rollback không?

Chỉ khi đã đánh giá đạt yêu cầu mới triển khai:

~~~bash
az deployment group create \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental
~~~

**Chú ý:** Đây là lệnh **triển khai thật**. Cần chạy đúng sau bước phê duyệt. ARM what-if không thay bạn xác định thay đổi có gây gián đoạn dịch vụ hay không, và một số khác biệt có thể xuất hiện vì API/provider chuẩn hóa cấu hình.

### 5.3 Tùy chọn xác nhận tương tác

Azure CLI hỗ trợ yêu cầu xem what-if và xác nhận ngay trước một số thao tác deployment bằng `--confirm-with-what-if`:

~~~bash
# Dành cho người vận hành tương tác, cần xem và xác nhận trước khi triển khai.
az deployment group create \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --confirm-with-what-if
~~~

Tùy chọn này phù hợp khi người dùng có thể đọc kết quả và quyết định tại terminal. Với pipeline không có tương tác, nên chạy **bước what-if riêng**, công bố kết quả cho người có thẩm quyền và dùng approval gate rõ ràng trước bước deployment.

## 6. Deployment mode thay đổi cách diễn giải kết quả

Trong ARM deployment ở resource-group scope, **Incremental** và **Complete** có ý nghĩa quan trọng:

| Mode | Diễn giải khái quát | Hệ quả khi tài nguyên hiện có không nằm trong template |
| --- | --- | --- |
| **Incremental** | Áp dụng thay đổi với các tài nguyên được khai báo; thường là lựa chọn mặc định | Thường giữ tài nguyên ngoài template, tùy semantics của resource và thuộc tính con; không xem sự thiếu vắng khỏi template là yêu cầu xóa toàn bộ tài nguyên ngoài phạm vi |
| **Complete** | Coi toàn bộ resource group nằm trong phạm vi quản lý của deployment theo các quy tắc tương ứng | Tài nguyên không được khai báo có thể bị dự kiến **Delete**; phải xem xét rất kỹ và tránh áp dụng tùy tiện vào resource group dùng chung |

Vì vậy, nếu xóa một khai báo resource khỏi `main.bicep` nhưng vẫn dùng `--mode Incremental`, bạn **không nên kỳ vọng** Azure tự xóa resource đó. Ngược lại, nếu dùng Complete ở một resource group có các tài nguyên không được template quản lý, what-if có thể báo hàng loạt Delete.

Ví dụ **chỉ để xem trước**, không cần thực hiện deploy:

~~~bash
# Chỉ phân tích tác động nếu chuyển sang Complete.
az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Complete
~~~

Đừng coi Complete là cách mặc định để dọn hạ tầng. Khi cần quản lý vòng đời và xóa có kiểm soát, nên tìm hiểu **Azure Deployment Stacks** và chính sách sở hữu tài nguyên phù hợp. Các API và hành vi xóa có thể khác nhau giữa loại tài nguyên, parent/child resources, nested deployment và phiên bản công cụ. **Delete trong what-if là tín hiệu phải kiểm tra cụ thể**, không phải lời mời tự động chấp nhận.

## 7. Những giới hạn cần hiểu trước khi phê duyệt

### 7.1 Kết quả dự đoán có thể khác thay đổi thực tế

ARM what-if phụ thuộc cách Resource Provider biểu diễn tài nguyên và cách ARM phân giải biểu thức. Một số giá trị trả về từ provider được chuẩn hóa, tính toán tự động hoặc không được biểu diễn giống hệt giá trị khai báo. Biểu thức chạy ở thời điểm deploy (ví dụ một số cách sử dụng `reference()`), thuộc tính chỉ đọc hoặc cấu trúc resource provider phức tạp có thể dẫn tới **noise**, false positive hoặc kết quả không đầy đủ.

Vì vậy:

- Nếu thấy Modify lặp lại dù không sửa template, so sánh các thuộc tính được báo với trạng thái do provider trả về, API version và biểu thức của template.
- Nếu thấy Ignore, Deploy hoặc Unsupported, tìm lý do cụ thể và bổ sung kiểm tra khác; không coi các loại này như NoChange.
- Nếu dùng Bicep module, nested deployment hay resource extension, cần đánh giá **phạm vi triển khai thật** và những tài nguyên bên trong; một preview chỉ có thông tin tổng quát chưa đủ để kết luận rủi ro.
- Nếu template chứa resource khai báo `existing`, hãy nhớ đây là tham chiếu tới tài nguyên đã tồn tại, **không phải yêu cầu triển khai lại** tài nguyên đó chỉ vì có khai báo.

### 7.2 Không dự báo được mọi hậu quả vận hành

Một kết quả Modify không nhất thiết cho biết thao tác có gây restart, thay đổi endpoint, tạm gián đoạn kết nối hoặc vi phạm phụ thuộc ứng dụng hay không. Một thay đổi quota, policy, RBAC, trạng thái tài nguyên, tình trạng khu vực hoặc giới hạn subscription có thể khiến deployment thất bại dù what-if thành công.

What-if cũng không phải kiểm tra chi phí. Nếu dự kiến tăng số máy ảo hoặc chuyển SKU, bạn cần đánh giá **giá dịch vụ theo region, mức tiêu thụ, giới hạn quota và ngân sách** bằng các công cụ chi phí phù hợp; không suy ra chi phí chính xác từ việc có bao nhiêu dòng Create hoặc Modify.

### 7.3 Quyền truy cập và dữ liệu nhạy cảm

What-if là thao tác xem trước, nhưng cần xác thực và có thể cần quyền trên deployment cũng như tài nguyên được phân tích. Không được bỏ qua giới hạn RBAC chỉ vì lệnh không deploy. Kết quả what-if có thể chứa metadata cấu hình, resource ID, tên tài nguyên và giá trị thuộc tính; hạn chế quyền xem logs và artifacts.

Đối với các giá trị nhạy cảm, sử dụng tham số an toàn, Azure Key Vault, identity hoặc cơ chế cấp quyền của pipeline; không in secret vào output hay đính kèm report công khai. Việc công cụ cố gắng che giá trị nhạy cảm **không** thay thế trách nhiệm giữ kín log và artifact.

### 7.4 Khoảng cách giữa preview và deploy

Không có cơ chế mặc định khiến trạng thái được xem trước trở thành một “plan đã khóa” tương tự một artifact bất biến. Nếu sau preview một người chỉnh tài nguyên trên Portal, kết quả trước đó có thể không còn đại diện cho hiện trạng. Vì vậy, trước khi thực hiện thay đổi quan trọng, có thể chạy lại what-if và yêu cầu xét duyệt lại khi diff thay đổi.

Mục tiêu là xem trước và triển khai **cùng commit, cùng parameters, cùng scope, cùng mode**; kể cả vậy vẫn cần kiểm tra kết quả thật sau deployment.

## 8. Tích hợp vào pull request và Azure Pipelines

Một quy trình IaC thích hợp cho nhóm phát triển:

1. Tác giả sửa Bicep, ARM template hoặc parameters trên nhánh tính năng và tạo pull request.
2. CI kiểm tra cú pháp, quy tắc chất lượng, chạy validate và what-if trên scope thử nghiệm/phù hợp.
3. Người review đối chiếu kết quả what-if với yêu cầu thay đổi, đặc biệt là Delete và cấu hình bảo mật/mạng/identity/SKU.
4. Nhánh được bảo vệ và environment approval gate quyết định khi nào bước deploy được phép chạy.
5. Sau deploy, pipeline xác nhận trạng thái, quan sát health/metrics/log và ghi nhận deployment cùng commit đã áp dụng.

~~~mermaid
flowchart LR
    PR["Pull request"] --> CI["Validate + What-if"]
    CI --> R{"Review diff"}
    R -->|"Cần sửa"| PR
    R -->|"Chấp nhận"| A["Merge + approval gate"]
    A --> DEP["Triển khai ARM/Bicep"]
    DEP --> OBS["Kiểm chứng + giám sát"]
~~~

### 8.1 Ví dụ Azure Pipelines YAML

Đây là ví dụ hai stage với **AzureCLI@2**. Giả sử trong repository đã có `infra/main.bicep` và `infra/parameters/dev.parameters.json` ở trên; service connection `sc-azure-infra-dev` đã được cấu hình để truy cập đúng subscription. Environment `azure-iac-dev` cần được cấu hình **Approvals and checks** trong Azure DevOps khi cần người duyệt: khai báo environment trong YAML không tự tạo approval.

~~~yaml
# azure-pipelines.yml
trigger:
  - main

# Với Azure Repos Git, dùng Branch Policies -> Build validation cho PR.
pool:
  vmImage: ubuntu-latest

variables:
  azureServiceConnection: 'sc-azure-infra-dev'
  targetResourceGroup: 'rg-iac-whatif-dev'
  templatePath: 'infra/main.bicep'
  parametersPath: 'infra/parameters/dev.parameters.json'

stages:
  - stage: Preview
    displayName: 'Kiểm tra hạ tầng dự kiến'
    jobs:
      - job: WhatIf
        steps:
          - checkout: self
          - task: AzureCLI@2
            displayName: 'Validate và ARM what-if'
            inputs:
              azureSubscription: 'sc-azure-infra-dev'
              scriptType: bash
              scriptLocation: inlineScript
              inlineScript: |
                set -euo pipefail
                az deployment group validate \
                  --resource-group "$(targetResourceGroup)" \
                  --template-file "$(templatePath)" \
                  --parameters @"$(parametersPath)"
                az deployment group what-if \
                  --resource-group "$(targetResourceGroup)" \
                  --template-file "$(templatePath)" \
                  --parameters @"$(parametersPath)" \
                  --mode Incremental \
                  --result-format FullResourcePayloads

  - stage: Deploy
    displayName: 'Áp dụng sau phê duyệt'
    dependsOn: Preview
    condition: succeeded()
    jobs:
      - deployment: Apply
        environment: 'azure-iac-dev'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self
                - task: AzureCLI@2
                  displayName: 'Áp dụng cùng commit và tham số'
                  inputs:
                    azureSubscription: 'sc-azure-infra-dev'
                    scriptType: bash
                    scriptLocation: inlineScript
                    inlineScript: |
                      set -euo pipefail
                      az deployment group create \
                        --resource-group "$(targetResourceGroup)" \
                        --template-file "$(templatePath)" \
                        --parameters @"$(parametersPath)" \
                        --mode Incremental
~~~

**Giải thích về tính an toàn của ví dụ:**

- Hai stage cùng chạy trong một pipeline sử dụng phiên bản repository đã checkout tại commit kích hoạt. Nên giữ bản template/parameters bất biến trong suốt chu kỳ review và deploy.
- Stage Preview sẽ thất bại nếu các lệnh validate/what-if trả mã lỗi. Tuy nhiên **một what-if thành công vẫn có thể dự kiến Delete**. Nếu muốn chặn Delete tự động, cần xử lý **kết quả có cấu trúc** hoặc áp dụng policy gate riêng; chỉ dùng `condition: succeeded()` là chưa đủ.
- Stage Deploy là một **deployment job** gắn với `azure-iac-dev`. Approval được quản trị ở Azure DevOps Environments; tổ chức cần cấu hình thực tế trước khi coi đây là cổng phê duyệt.
- Service connection nên có quyền tối thiểu và chỉ dùng với các nhánh/job đáng tin cậy. Không cấp credential triển khai cho workflow chạy mã pull request không tin cậy. Có thể tách service connection preview và service connection deploy với mức quyền phù hợp.
- Khi triển khai production, nên áp dụng thêm nhánh được bảo vệ, reviewer bắt buộc, bản tổng hợp thay đổi, kiểm tra lại độ mới của preview và quan sát sau deployment.

### 8.2 Tự động chặn Delete cần phân tích JSON

Đối với các tổ chức cần quy tắc “không có Delete thì mới cho phép deploy”, phải đọc **kết quả máy xử lý được**, không tìm chuỗi trong terminal output đã tô màu. Có thể yêu cầu Azure CLI xuất JSON:

~~~bash
az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental \
  --output json > whatif.json
~~~

Trong ARM what-if result, các thay đổi thường được biểu diễn dưới phần tử `changes`, với `changeType` trên mỗi tài nguyên. Ví dụ bản JSON **rút gọn để minh họa cấu trúc**, không đại diện mọi response:

~~~json
{
  "changes": [
    {
      "resourceId": "/subscriptions/.../resourceGroups/rg-iac-whatif-dev/providers/Microsoft.Storage/storageAccounts/stwhatifdemo12345",
      "changeType": "Modify"
    }
  ]
}
~~~

Khi xây chính sách tự động, hãy kiểm tra schema thực tế theo phiên bản CLI/API đang dùng; nếu thiếu trường, lỗi phân tích hoặc định dạng không như dự kiến, **fail closed** thay vì kết luận “không có Delete”. Chẳng hạn, với JSON có mảng `changes` như ví dụ, đoạn `jq` sau xác nhận schema tối thiểu rồi chặn mọi resource có `changeType == "Delete"`:

~~~bash
set -euo pipefail
jq -e '(.changes | type) == "array" and
       all(.changes[]; (.changeType | type) == "string")' whatif.json >/dev/null

delete_count=$(jq '[.changes[] | select(.changeType == "Delete")] | length' whatif.json)
if [ "$delete_count" -gt 0 ]; then
  echo "ARM what-if dự kiến xóa $delete_count tài nguyên; yêu cầu review."
  exit 1
fi
~~~

Đây chỉ là một **chính sách mẫu** chặn Delete, chưa kiểm tra việc mở public network, thay đổi quyền RBAC, downgrade SKU hoặc nguy cơ chi phí. Với môi trường production, cần bổ sung quy tắc trên các thuộc tính quan trọng, phạm vi cho phép và ngoại lệ có người phê duyệt. Cũng cần kiểm soát quyền đọc file `whatif.json` và thời gian lưu trữ để tránh lộ cấu hình.

## 9. Các phạm vi triển khai khác

ARM/Bicep có các phạm vi deployment như **resource group**, **subscription**, **management group** và **tenant**. What-if cần được gọi với đúng phạm vi của template. Một Bicep file khai báo `targetScope = 'subscription'` không nên được đưa vào lệnh `az deployment group what-if` rồi kỳ vọng Azure tự hiểu chuyển phạm vi.

Ví dụ template ở phạm vi subscription để tạo resource group cần dùng lệnh nhóm `sub`, kèm location cho bản ghi deployment:

~~~bash
az deployment sub what-if \
  --location southeastasia \
  --template-file infra/subscription.bicep \
  --parameters @infra/parameters/sub.parameters.json
~~~

Tương tự, có các nhóm lệnh `az deployment mg ...` và `az deployment tenant ...` theo phạm vi và quyền phù hợp. Khi sử dụng các phạm vi lớn hơn:

- Kiểm tra subscription ID, tenant ID hoặc management group ID trước khi chạy.
- Xem xét các module khai báo resource ở phạm vi khác với deployment cha, theo khả năng mà Bicep/ARM hỗ trợ.
- Áp dụng approval nghiêm ngặt hơn đối với thay đổi policy, role assignment hoặc cấu hình có tác động tới nhiều subscription.
- Không coi preview ở một subscription là bằng chứng giống nhau cho các subscription khác; mỗi môi trường có trạng thái hiện hữu và quyền khác nhau.

## 10. Xử lý lỗi và kết quả bất thường

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thể chạy what-if do lỗi authorization | Sai subscription, token, role hoặc thiếu quyền liên quan đến deployment/resource provider | Kiểm tra `az account show`, scope, service connection, RBAC rồi chạy lại; không cấp Owner một cách tùy tiện |
| Template validate không qua | Sai cú pháp Bicep, parameters thiếu/sai kiểu, resource ID hoặc API version không phù hợp | Sửa template/parameters, validate lại trước what-if |
| Kết quả nhiều Modify dù không đổi code | Provider chuẩn hóa giá trị, biểu thức động, thuộc tính mặc định, read-only hoặc cách ARM so sánh | Đọc đúng property delta; kiểm tra API/provider, loại bớt noise có cơ sở; không bỏ qua tất cả Modify |
| Xuất hiện Delete ngoài dự kiến | Sai scope, mode Complete, template quản lý thiếu tài nguyên hoặc cấu hình điều kiện | Dừng; xác minh template, mode, resource group, tài nguyên phụ thuộc và owner |
| What-if không báo thay đổi nhưng ứng dụng lỗi sau deploy | Tác động runtime, cấu hình ngoài template, thay đổi bên ngoài sau preview hoặc giới hạn của provider | Kiểm tra logs, metrics, health, lịch sử deployment và ứng dụng; không xem NoChange như kiểm thử end-to-end |
| What-if báo Create nhưng deployment thất bại | Tên đã tồn tại toàn cục, quota, policy, vùng không hỗ trợ SKU, tài nguyên bị lock | Kiểm tra thông báo từ resource provider và giới hạn môi trường, điều chỉnh cấu hình rồi chạy lại |
| Không thấy chi tiết diff cần review | Đang dùng định dạng rút gọn hoặc preview bị giới hạn | Sử dụng định dạng đầy đủ và kiểm tra cảnh báo; bổ sung bước review tài nguyên quan trọng |

Khi gặp kết quả bất ngờ, nên giữ lại tối thiểu **commit**, **template/parameters**, **scope**, **mode**, phiên bản công cụ, timestamp và kết quả what-if (đã loại thông tin nhạy cảm). Các dữ kiện này giúp so sánh preview với deployment thực tế và hỗ trợ truy vết sự cố.

## 11. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: Tạo rồi sửa một tài nguyên thử nghiệm

1. Tạo một resource group lab riêng; sửa `storageAccountName` trong parameters thành tên duy nhất.
2. Chạy `az deployment group validate` rồi `az deployment group what-if`; ghi nhận những tài nguyên dự kiến **Create**.
3. Triển khai thật vào resource group lab nếu bạn có quyền và đồng ý sử dụng tài nguyên; sau đó chạy lại what-if với template không đổi.
4. Thay `costCenter` và chạy what-if; tìm thuộc tính dự kiến **Modify**.
5. Đổi `minimumTlsVersion` hoặc `publicNetworkAccess` trong một môi trường thử nghiệm thích hợp, xem diff và giải thích tác động bảo mật trước khi quyết định triển khai.

**Kết quả mong đợi:** bạn thấy được sự khác nhau giữa trạng thái lần đầu, trạng thái sau deploy và diff khi đổi parameters; nhận ra một thay đổi nhỏ trong mã có thể mang ý nghĩa vận hành lớn.

### Bài tập 2: Đánh giá nguy cơ Delete

Giả sử resource group `rg-shared` có hai tài nguyên `A` và `B`, nhưng template chỉ khai báo `A`. Hãy dự đoán:

- Với `Incremental`, việc thiếu `B` thường dẫn đến kết quả như thế nào?
- Với `Complete`, `B` có thể bị dự kiến xử lý ra sao?
- Nếu thấy Delete trên `B`, bạn cần xác nhận các thông tin nào trước khi cho phép deploy?

**Gợi ý đáp án:** Incremental thường giữ `B` dù không có trong template; Complete có thể dự kiến Delete theo semantics tương ứng. Phải dừng để kiểm tra scope/mode, owner, dữ liệu, backup, phụ thuộc, yêu cầu thay đổi và phê duyệt. Không thực hiện deployment Complete vào `rg-shared` chỉ để kiểm chứng phỏng đoán.

### Câu hỏi tự kiểm tra

1. ARM what-if khác `az deployment group validate` ở điểm nào?
2. Vì sao lệnh what-if trả exit code 0 chưa đủ chứng minh thay đổi được phép triển khai?
3. Điều gì khiến kết quả Modify có thể xuất hiện lặp lại dù người dùng không sửa Bicep?
4. Vì sao cùng commit/template/parameters chưa bảo đảm kết quả preview hoàn toàn giống deployment sau đó?
5. Có nên cho phép workflow nhận pull request từ fork sử dụng service connection có quyền thay đổi production không? Giải thích.
6. Khi có Delete hoặc thay đổi quan trọng đối với network, RBAC, Key Vault và storage, quy trình review cần những ai và những bằng chứng nào?

**Điểm cần ghi nhớ:** ARM what-if làm cho việc thay đổi hạ tầng bằng mã dễ quan sát và có thể review trước khi áp dụng. Quy trình an toàn là **validate → what-if → đánh giá tác động → phê duyệt → deploy → kiểm chứng**, với cùng phạm vi, tham số và chế độ triển khai được kiểm soát. Kết quả preview là bằng chứng cho quyết định, không phải bảo đảm tuyệt đối về tác động thực tế.
