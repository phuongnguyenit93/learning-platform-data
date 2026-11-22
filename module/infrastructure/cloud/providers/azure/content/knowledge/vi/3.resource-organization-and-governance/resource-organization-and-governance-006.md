# Thiết kế custom role và kiểm soát quyền tối thiểu

Trong Microsoft Azure, quyền truy cập tài nguyên được quản lý chủ yếu bằng Azure role-based access control (Azure RBAC). Khi role dựng sẵn không mô tả đúng công việc của một nhóm, bạn có thể tạo custom role để cấp đúng các thao tác cần thiết ở một phạm vi cụ thể.

Thiết kế role là một phần quan trọng của quản trị tài nguyên Azure. Một kiến trúc ứng dụng có thể gồm subscription, resource group, mạng ảo, máy ảo, storage account và cơ sở dữ liệu. Nếu mọi thành viên đều có quyền Contributor trên cả subscription, một lỗi thao tác có thể ảnh hưởng đến nhiều workload. Nếu quyền được chia theo nhiệm vụ, phạm vi và thời hạn, mỗi người chỉ có khả năng thực hiện những công việc được giao.

Bài học này tập trung vào custom role trong Azure RBAC thuộc hệ sinh thái Microsoft Azure. Bạn sẽ học cách phân tích thao tác, thiết kế role definition, chọn scope, gán role cho user/group/workload identity, kiểm tra quyền thực tế và duy trì quyền tối thiểu theo thời gian.

Sau bài học, bạn có thể:

- Phân biệt security principal, role definition, role assignment và scope.
- Giải thích các trường Actions, NotActions, DataActions, NotDataActions và AssignableScopes.
- Xác định khi nào nên dùng built-in role và khi nào cần custom role.
- Thiết kế custom role theo nhiệm vụ, tách quyền quản lý tài nguyên với quyền truy cập dữ liệu.
- Tạo, gán, kiểm tra, cập nhật và gỡ custom role bằng Azure CLI.
- Áp dụng nguyên tắc quyền tối thiểu, nhóm quyền, managed identity và quyền có thời hạn.

## 1. Azure RBAC và các thành phần của một quyền truy cập

Azure RBAC quyết định ai có thể thực hiện thao tác nào trên tài nguyên Azure và ở phạm vi nào. Một quyền truy cập hiệu lực thường được hình thành từ bốn thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Security principal | Danh tính nhận quyền | User, group, service principal hoặc managed identity |
| Role definition | Tập hợp các thao tác được cho phép | Reader, Contributor hoặc custom role VM Operator |
| Scope | Phạm vi tài nguyên mà quyền áp dụng | Management group, subscription, resource group hoặc một resource |
| Role assignment | Liên kết principal, role và scope | Gán VM Operator cho nhóm vận hành tại resource group ứng dụng |

Có thể biểu diễn một role assignment như sau:

~~~text
Principal + Role definition + Scope = Role assignment
~~~

Ví dụ: nhóm **grp-orders-operators** được gán custom role **Orders VM Operator** tại resource group **rg-orders-prod**. Thành viên nhóm có thể thực hiện những thao tác được role cho phép trên các tài nguyên thuộc phạm vi đó và các tài nguyên con phù hợp.

### 1.1. Phân biệt Azure RBAC với Microsoft Entra roles

Microsoft Entra ID quản lý danh tính, nhóm, ứng dụng và xác thực. Entra directory roles như User Administrator hoặc Global Administrator quản lý các đối tượng và chức năng của thư mục danh tính.

Azure RBAC quản lý quyền trên tài nguyên Azure như máy ảo, mạng, storage account, database và resource group. Ví dụ:

- User Administrator có thể quản lý một số đối tượng người dùng trong tenant.
- Reader trên subscription có thể xem thông tin quản lý của các resource trong subscription.
- Storage Blob Data Reader có thể đọc dữ liệu blob trong phạm vi được gán.
- Custom role VM Operator có thể cho phép đọc, khởi động và deallocate máy ảo theo phạm vi được chỉ định.

Có một số vai trò Entra cấp cao có thể có khả năng quản trị quyền Azure, nhưng không nên xem hai hệ thống role là một. Khi thiết kế quyền, hãy xác định rõ công việc cần quản lý danh tính hay quản lý tài nguyên Azure.

### 1.2. Role definition khác role assignment

Role definition mô tả tập thao tác. Bản thân role definition không cấp quyền cho bất kỳ ai.

Role assignment mới cấp role cho một principal ở một scope cụ thể. Cùng một custom role có thể được gán cho nhiều nhóm hoặc workload identity ở những scope khác nhau, miễn là các scope đó nằm trong phạm vi được phép của role definition.

Ví dụ:

- Role definition: **Orders VM Operator**.
- Principal: nhóm **grp-orders-operators**.
- Scope: **/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod**.

Nếu role definition chỉ cho phép đọc, start và deallocate máy ảo, thành viên nhóm không tự có thêm quyền tạo virtual network, cấp role cho người khác hay đọc blob data.

## 2. Hiểu cấu trúc của custom role

Một custom role Azure RBAC có các thuộc tính quan trọng sau:

| Thuộc tính | Công dụng |
|---|---|
| Name | Tên dễ nhận biết của role |
| Id | Định danh duy nhất của role; Azure tạo hoặc quản lý định danh này |
| IsCustom | Cho biết đây là custom role |
| Description | Mô tả nhiệm vụ và giới hạn sử dụng |
| Actions | Các thao tác trên management plane được cho phép |
| NotActions | Các thao tác bị loại khỏi tập Actions của role definition này |
| DataActions | Các thao tác trên data plane được cho phép |
| NotDataActions | Các thao tác bị loại khỏi tập DataActions của role definition này |
| AssignableScopes | Những scope mà role definition có thể được gán |

### 2.1. Actions: thao tác quản lý tài nguyên

Actions chứa các thao tác management plane, chẳng hạn đọc cấu hình máy ảo, khởi động máy ảo, tạo resource hoặc thay đổi cấu hình mạng.

Một operation thường có dạng:

~~~text
Microsoft.<Provider>/<resource-type>/<operation>
~~~

Ví dụ:

- **Microsoft.Compute/virtualMachines/read**: đọc thông tin quản lý của máy ảo.
- **Microsoft.Compute/virtualMachines/start/action**: khởi động máy ảo.
- **Microsoft.Compute/virtualMachines/deallocate/action**: deallocate máy ảo.
- **Microsoft.Network/virtualNetworks/read**: đọc thông tin quản lý của virtual network.

Tên operation phải lấy từ resource provider tương ứng. Không nên đoán tên operation dựa trên tên nút trong Portal hoặc tên lệnh CLI.

### 2.2. DataActions: thao tác trên dữ liệu

DataActions mô tả quyền truy cập dữ liệu bên trong dịch vụ. Ví dụ, đọc blob, ghi dữ liệu vào container hoặc truy cập nội dung của một dịch vụ hỗ trợ Azure RBAC data plane.

Đọc cấu hình storage account và đọc nội dung blob là hai quyền khác nhau:

- **Microsoft.Storage/storageAccounts/read** là thao tác quản lý storage account.
- Đọc nội dung blob cần quyền data plane phù hợp, chẳng hạn role dựng sẵn Storage Blob Data Reader.

Vì vậy, người chỉ cần xem cấu hình storage account không nhất thiết phải được đọc dữ liệu bên trong. Ngược lại, một ứng dụng cần đọc blob thường nên được cấp quyền data plane ở đúng storage account hoặc container cần sử dụng.

Không phải mọi dịch vụ Azure đều biểu diễn quyền dữ liệu bằng DataActions theo cùng một cách. Hãy kiểm tra tài liệu và role operation của đúng dịch vụ trước khi thiết kế.

### 2.3. NotActions và NotDataActions không phải quyền từ chối

Đây là điểm cần hiểu thật chính xác. NotActions loại một số operation khỏi tập Actions của một role definition. NotDataActions loại operation khỏi tập DataActions của role definition đó.

Chúng không tạo ra một lệnh deny độc lập. Azure RBAC tổng hợp quyền từ các role assignment có hiệu lực. Nếu một principal được gán một role khác có quyền đối với operation đã bị loại bởi NotActions, principal vẫn có thể thực hiện operation đó nhờ role assignment còn lại.

Ví dụ:

- Role A cho phép mọi operation thuộc loại máy ảo của Microsoft.Compute.
- NotActions trong Role A loại **Microsoft.Compute/virtualMachines/delete/action**.
- Principal đồng thời được gán Role B có quyền xóa máy ảo.

Principal vẫn có thể có quyền xóa thông qua Role B. Do đó, không dùng NotActions như cơ chế tạo deny hoặc để vô hiệu hóa một quyền đã được cấp từ role khác.

Nếu mục tiêu là không cho phép một cấu hình cụ thể, hãy thiết kế lại các role assignment, dùng Azure Policy cho các quy tắc cấu hình phù hợp, hoặc dùng cơ chế deny assignment do Azure quản lý trong các tình huống được hỗ trợ. Azure Policy không thay thế mọi chức năng kiểm soát quyền truy cập dữ liệu.

### 2.4. Hạn chế wildcard

Wildcard như dấu sao (*) hoặc phạm vi toàn namespace Microsoft.Compute có thể cấp nhiều thao tác hơn nhiệm vụ thực tế. Chúng cũng khiến role khó đánh giá khi resource provider bổ sung operation mới.

Hãy ưu tiên liệt kê operation cụ thể. Chỉ dùng wildcard khi phạm vi rộng là yêu cầu có chủ đích, đã được đánh giá và có người chịu trách nhiệm duy trì.

### 2.5. AssignableScopes và scope của role assignment

Hai khái niệm này có liên quan nhưng không giống nhau:

- AssignableScopes xác định nơi role definition có thể được sử dụng để tạo role assignment. Custom role thường được định nghĩa ở management group hoặc subscription scope.
- Scope trong role assignment xác định tài nguyên thực tế mà principal nhận quyền.

Ví dụ, custom role có AssignableScopes là một subscription có thể được gán tại resource group nằm trong subscription đó. Việc gán ở resource group giúp giới hạn quyền cho đúng ứng dụng hoặc môi trường.

Cấu trúc scope thường gặp:

~~~text
/                                    Root scope
/providers/Microsoft.Management/managementGroups/<management-group-id>
/subscriptions/<subscription-id>
/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/<provider>/<type>/<resource-name>
~~~

Role assignment ở scope cha thường được kế thừa xuống scope con. Vì vậy, gán role ở subscription có phạm vi ảnh hưởng rộng hơn gán role ở một resource group hoặc resource.

## 3. Quy trình thiết kế custom role theo quyền tối thiểu

Quyền tối thiểu (least privilege) nghĩa là principal chỉ được cấp các operation cần cho nhiệm vụ, tại scope cần thiết và trong khoảng thời gian cần thiết. Để đạt được điều đó, hãy thiết kế theo quy trình sau.

### Bước 1: Mô tả nhiệm vụ bằng hành động cụ thể

Bắt đầu từ công việc, không bắt đầu từ tên role. Ví dụ, nhân viên trực vận hành cần:

- Xem trạng thái và cấu hình máy ảo.
- Khởi động máy ảo khi được yêu cầu.
- Deallocate máy ảo khi cần giảm chi phí.
- Không tạo hoặc xóa máy ảo.
- Không thay đổi mạng, firewall hoặc role assignment.
- Không truy cập dữ liệu trong storage account.

Mô tả càng cụ thể thì càng dễ chuyển thành operation và kiểm thử.

### Bước 2: Kiểm tra built-in role trước

Azure có nhiều built-in role được Microsoft duy trì. Hãy tìm role dựng sẵn phù hợp trước khi tạo custom role.

| Built-in role | Mục đích điển hình |
|---|---|
| Reader | Xem thông tin quản lý resource |
| Contributor | Quản lý phần lớn resource nhưng không tự cấp quyền Azure RBAC |
| Owner | Quản lý resource và có thể cấp quyền truy cập |
| Virtual Machine Contributor | Quản lý máy ảo theo quyền được định nghĩa trong role |
| Storage Blob Data Reader | Đọc dữ liệu blob trong phạm vi được gán |

Ví dụ, nếu nhiệm vụ chỉ cần đọc dữ liệu blob, hãy xem xét Storage Blob Data Reader thay vì cấp Contributor cho storage account. Nếu built-in role đã đáp ứng nhiệm vụ và scope, custom role sẽ tạo thêm công việc quản lý mà không đem lại lợi ích rõ ràng.

### Bước 3: Tra cứu operation của resource provider

Azure CLI có thể liệt kê operation do resource provider công bố:

~~~bash
# Liệt kê operation của Microsoft.Compute
az provider operation list \
  --namespace Microsoft.Compute \
  --output table

# Liệt kê operation của Microsoft.Storage
az provider operation list \
  --namespace Microsoft.Storage \
  --output table
~~~

Đối chiếu operation với từng nhiệm vụ. Chú ý phân biệt operation đọc, thao tác thay đổi, thao tác xóa và data operation. Tên operation, điều kiện hỗ trợ và tác động có thể thay đổi theo dịch vụ hoặc API.

Không nên sao chép toàn bộ operation của một provider vào role chỉ vì nhóm người dùng làm việc với provider đó. Hãy chọn đúng operation mà nhiệm vụ yêu cầu.

### Bước 4: Chọn scope nhỏ nhất hợp lý

Hãy chọn scope theo phạm vi chịu trách nhiệm:

- Resource: khi nhiệm vụ chỉ liên quan đến một tài nguyên cụ thể.
- Resource group: khi nhóm chịu trách nhiệm với các resource thuộc một ứng dụng hoặc môi trường.
- Subscription: khi nhiệm vụ áp dụng cho nhiều resource group trong subscription.
- Management group: khi một nhóm quản trị cần thực hiện cùng nhiệm vụ trên nhiều subscription.

Scope càng cao thì quyền kế thừa xuống càng nhiều resource. Tránh gán quyền ở management group hoặc subscription chỉ vì thao tác gán tiện hơn.

### Bước 5: Chọn principal phù hợp

Ưu tiên gán role cho nhóm Entra thay vì gán lặp lại từng người. Khi thành viên thay đổi, quản trị viên có thể cập nhật thành viên nhóm mà không phải tạo hoặc xóa hàng loạt role assignment.

Đối với ứng dụng hoặc dịch vụ, ưu tiên managed identity khi dịch vụ hỗ trợ. Managed identity giúp workload xác thực với Azure mà không phải lưu một client secret dài hạn trong mã nguồn hoặc cấu hình.

Chỉ cấp quyền cho principal thực sự cần thực hiện nhiệm vụ. Không dùng một tài khoản dùng chung cho nhiều ứng dụng hoặc nhiều nhóm công việc không liên quan.

### Bước 6: Xác định thời hạn và cách kiểm tra

Quyền quản trị nhạy cảm nên được cấp trong thời gian cần thiết. Với các vai trò đặc quyền, có thể dùng Microsoft Entra Privileged Identity Management (PIM) for Azure resources để quản lý quyền eligible, kích hoạt theo thời hạn và yêu cầu kiểm soát bổ sung khi phù hợp với cấu hình tổ chức.

Sau khi gán, hãy kiểm tra quyền hiệu lực, thử thao tác được phép bằng danh tính của người nhận và xác nhận thao tác ngoài nhiệm vụ bị từ chối. Thử nghiệm nên được thực hiện trong môi trường an toàn, với dữ liệu và tài nguyên thử nghiệm.

## 4. Ví dụ: custom role chỉ cho phép vận hành máy ảo

Giả sử ứng dụng Orders có resource group production là **rg-orders-prod**. Nhóm vận hành cần xem thông tin máy ảo, khởi động và deallocate máy ảo. Họ không cần tạo, xóa máy ảo, thay đổi mạng hay đọc dữ liệu ứng dụng.

### 4.1. Xác định quyền cần thiết

| Nhiệm vụ | Operation cần có |
|---|---|
| Xem thông tin máy ảo | **Microsoft.Compute/virtualMachines/read** |
| Khởi động máy ảo | **Microsoft.Compute/virtualMachines/start/action** |
| Deallocate máy ảo | **Microsoft.Compute/virtualMachines/deallocate/action** |
| Xóa máy ảo | Không cấp |
| Thay đổi cấu hình máy ảo | Không cấp |
| Cấp role cho người khác | Không cấp |
| Đọc dữ liệu blob | Không cấp DataActions |

Ví dụ này minh họa một role tối giản cho các thao tác trực tiếp trên VM. Nếu nhóm cần dùng Azure Portal để xem thêm trạng thái hoặc resource liên quan, có thể cần các quyền đọc bổ sung. Hãy xác định operation còn thiếu qua kiểm tra thực tế và chỉ thêm quyền đọc cần thiết.

### 4.2. Tạo file định nghĩa role

Tạo file **vm-operator-role.json**:

~~~json
{
  "Name": "Orders VM Operator",
  "IsCustom": true,
  "Description": "Cho phep xem, khoi dong va deallocate VM trong pham vi duoc gan role.",
  "Actions": [
    "Microsoft.Compute/virtualMachines/read",
    "Microsoft.Compute/virtualMachines/start/action",
    "Microsoft.Compute/virtualMachines/deallocate/action"
  ],
  "NotActions": [],
  "DataActions": [],
  "NotDataActions": [],
  "AssignableScopes": [
    "/subscriptions/<subscription-id>"
  ]
}
~~~

Thay **<subscription-id>** bằng ID subscription thật. Ví dụ này chỉ đưa các operation quản lý máy ảo vào Actions. Không thêm quyền đọc hoặc ghi dữ liệu vào DataActions vì nhiệm vụ không cần truy cập dữ liệu.

Mô tả role nên nêu rõ ai sử dụng, được làm gì và phạm vi dự kiến. Tên và mô tả rõ ràng giúp người quản trị đánh giá role assignment trong tương lai.

### 4.3. Tạo custom role

Đăng nhập và kiểm tra subscription hiện tại trước khi tạo role:

~~~bash
az login
az account show --output table
az account set --subscription "<subscription-id>"
~~~

Tạo role definition từ file JSON:

~~~bash
az role definition create \
  --role-definition ./vm-operator-role.json
~~~

Kiểm tra role vừa tạo:

~~~bash
az role definition list \
  --name "Orders VM Operator" \
  --output json
~~~

Nếu lệnh tạo báo lỗi operation hoặc AssignableScopes không hợp lệ, hãy kiểm tra subscription đang chọn, định dạng JSON, operation name và scope. Không mở rộng wildcard chỉ để làm cho lệnh tạo role thành công.

### 4.4. Gán role cho nhóm ở resource group

Role definition được khai báo để dùng trong subscription, nhưng nhóm vận hành chỉ cần quyền trên resource group production.

~~~bash
az role assignment create \
  --assignee-object-id "<group-object-id>" \
  --assignee-principal-type Group \
  --role "Orders VM Operator" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod"
~~~

Thay **<group-object-id>** bằng object ID của nhóm Microsoft Entra. Dùng object ID giúp xác định chính xác principal được gán quyền.

Không gán role ở subscription nếu nhóm chỉ chịu trách nhiệm với **rg-orders-prod**. Khi role assignment đặt ở resource group, quyền được kế thừa đến resource con trong phạm vi phù hợp.

### 4.5. Kiểm tra role assignment

Liệt kê role assignment tại resource group, bao gồm quyền kế thừa:

~~~bash
az role assignment list \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod" \
  --include-inherited \
  --all \
  --output table
~~~

Có thể kiểm tra role definition để xác nhận các operation được khai báo:

~~~bash
az role definition list \
  --name "Orders VM Operator" \
  --output json
~~~

Đánh giá cả quyền trực tiếp và quyền kế thừa. Một principal có thể nhận quyền từ nhiều role assignment, nhiều nhóm hoặc scope cha. Vì vậy, đọc riêng một custom role chưa đủ để kết luận quyền hiệu lực của người dùng.

### 4.6. Kiểm thử theo nhiệm vụ

Dùng một tài khoản thử nghiệm là thành viên của nhóm vận hành. Xác nhận các tình huống:

| Thao tác thử | Kết quả mong đợi |
|---|---|
| Xem thông tin máy ảo trong resource group được gán | Được phép nếu operation đọc cần thiết đã có |
| Khởi động máy ảo thử nghiệm | Được phép |
| Deallocate máy ảo thử nghiệm | Được phép |
| Xóa máy ảo | Bị từ chối nếu không có role khác cấp quyền |
| Tạo virtual network | Bị từ chối nếu không có role khác cấp quyền |
| Cấp role cho người dùng khác | Bị từ chối nếu không có role khác cấp quyền |
| Đọc blob data | Bị từ chối nếu không có role data plane khác cấp quyền |

Kết quả mong đợi chỉ đúng khi principal không nhận thêm quyền từ role assignment khác. Nếu một thao tác đáng lẽ bị chặn nhưng vẫn thành công, hãy kiểm tra role assignment trực tiếp, quyền kế thừa từ resource group/subscription/management group và các nhóm mà principal là thành viên.

Nếu thao tác được phép bị từ chối, kiểm tra operation name, scope, resource provider, trạng thái role assignment và thời gian truyền quyền. Một số thay đổi role assignment có thể cần thời gian để có hiệu lực.

## 5. Kiểm soát quyền tối thiểu trong tổ chức

Custom role chỉ là một phần của quản trị quyền. Một mô hình vận hành tốt cần kết hợp thiết kế role, principal, scope, thời hạn và giám sát.

### 5.1. Phân tách nhiệm vụ

Không nên gom mọi công việc vào một role lớn. Ví dụ, có thể tách:

| Nhóm nhiệm vụ | Quyền phù hợp |
|---|---|
| Xem inventory và cấu hình | Reader ở scope cần xem |
| Vận hành máy ảo | Custom VM Operator hoặc built-in role phù hợp |
| Đọc blob | Storage Blob Data Reader ở storage account/container |
| Triển khai hạ tầng | Role triển khai được giới hạn ở resource group hoặc pipeline identity |
| Quản trị quyền | Role quản lý role assignment, chỉ dành cho nhóm được ủy quyền |

Người triển khai hạ tầng không nhất thiết cần quyền đọc mọi dữ liệu ứng dụng. Người đọc dữ liệu không nhất thiết cần quyền sửa cấu hình storage account. Người quản trị quyền cũng không nên đồng thời là principal chạy ứng dụng nếu không có lý do vận hành rõ ràng.

### 5.2. Gán quyền cho nhóm và managed identity

Đối với nhân viên, dùng nhóm theo nhiệm vụ hoặc trách nhiệm. Ví dụ:

- **grp-orders-readers**: xem thông tin quản lý của ứng dụng Orders.
- **grp-orders-operators**: vận hành máy ảo theo custom role.
- **grp-orders-data-readers**: đọc dữ liệu blob trong phạm vi được phê duyệt.

Đối với workload, dùng managed identity gắn với ứng dụng hoặc dịch vụ. Gán role cho managed identity tại scope mà workload cần truy cập. Tránh nhúng credential của tài khoản cá nhân vào pipeline hoặc ứng dụng.

Không dùng một managed identity chung cho nhiều workload không liên quan nếu điều đó làm mở rộng phạm vi quyền hoặc khiến việc truy vết trách nhiệm khó khăn.

### 5.3. Dùng PIM cho quyền đặc quyền

Một số nhiệm vụ chỉ cần quyền cao trong thời gian ngắn, chẳng hạn xử lý sự cố hoặc thực hiện thay đổi production. PIM for Azure resources có thể hỗ trợ:

- Gán quyền ở trạng thái eligible để người dùng kích hoạt khi cần.
- Giới hạn thời gian kích hoạt.
- Yêu cầu lý do hoặc phê duyệt tùy chính sách.
- Ghi nhận lịch sử kích hoạt để kiểm tra.

PIM cần được cấu hình và đáp ứng điều kiện cấp phép của tổ chức. Không nên cấp permanent Owner hoặc User Access Administrator cho mọi thành viên chỉ để thuận tiện.

### 5.4. Dùng Azure Policy cho quy tắc cấu hình

Azure RBAC quyết định principal có thể gọi operation nào. Azure Policy đánh giá và thực thi các quy tắc về cấu hình tài nguyên, ví dụ:

- Chỉ cho phép triển khai ở các region đã duyệt.
- Yêu cầu resource có tag owner và environment.
- Kiểm soát cấu hình public network access theo chính sách.
- Kiểm tra SKU hoặc cấu hình được tổ chức cho phép.

Azure Policy và Azure RBAC bổ sung cho nhau. Policy không phải công cụ thay thế role assignment để cấp quyền đọc blob hoặc quyền khởi động máy ảo.

### 5.5. Kiểm tra quyền định kỳ

Quyền tối thiểu có thể bị phá vỡ theo thời gian khi nhân viên chuyển nhóm, dự án kết thúc hoặc một role assignment tạm thời không được gỡ. Hãy định kỳ:

1. Liệt kê role assignment ở các scope quan trọng.
2. Tìm role có quyền rộng như Owner, Contributor hoặc User Access Administrator.
3. Kiểm tra quyền được cấp trực tiếp, qua nhóm và qua scope kế thừa.
4. Xác nhận principal còn nhiệm vụ cần quyền đó.
5. Gỡ assignment không còn cần thiết và cập nhật thành viên nhóm.
6. Xem xét custom role có operation thừa hoặc thiếu so với công việc hiện tại.
7. Kiểm tra Activity Log và quy trình access review của tổ chức.

Nên duy trì chủ sở hữu cho mỗi custom role. Người sở hữu có trách nhiệm giải thích mục đích, rà soát operation và đề xuất cập nhật khi workload thay đổi.

## 6. Cập nhật và gỡ custom role an toàn

Khi nhiệm vụ thay đổi, custom role có thể cần thêm hoặc bỏ operation. Hãy cập nhật role definition trong hệ thống quản lý phiên bản, review thay đổi và triển khai theo quy trình tương tự mã hạ tầng.

Cập nhật role definition từ file JSON:

~~~bash
az role definition update \
  --role-definition ./vm-operator-role.json
~~~

Trước khi cập nhật, hãy xem xét tác động với tất cả principal đang được gán role. Một thay đổi trong role definition có thể làm thay đổi quyền của nhiều nhóm hoặc workload cùng lúc.

Khi role không còn được sử dụng:

1. Tìm tất cả role assignment tham chiếu custom role.
2. Xác nhận với chủ sở hữu rằng không còn nhiệm vụ phụ thuộc vào role.
3. Gỡ role assignment khỏi principal ở các scope liên quan.
4. Kiểm tra lại role assignment và các pipeline hoặc cấu hình đang tham chiếu role.
5. Xóa role definition sau khi không còn assignment sử dụng.

Tìm role assignment cần gỡ trong kết quả liệt kê ở phần trước, lấy đúng role assignment ID rồi xóa assignment đó:

~~~bash
az role assignment delete \
  --ids "<role-assignment-id>"
~~~

Sau khi tất cả assignment đã được gỡ, có thể xóa custom role:

~~~bash
az role definition delete \
  --name "Orders VM Operator"
~~~

Nếu role definition vẫn đang được sử dụng hoặc lệnh xóa thất bại, hãy kiểm tra các assignment còn tồn tại và gỡ chúng theo quy trình thay đổi đã được phê duyệt. Không xóa role chỉ dựa trên tên hoặc giả định rằng nhóm không còn sử dụng.

## 7. Điều tra lỗi và đánh giá quyền hiệu lực

Khi một thao tác bị từ chối, lỗi thường có dạng AuthorizationFailed hoặc thông báo thiếu quyền đối với một operation cụ thể. Hãy xử lý theo thứ tự:

1. Xác nhận principal đang đăng nhập hoặc workload identity đang được sử dụng.
2. Xác nhận tenant và subscription đích.
3. Ghi lại operation bị từ chối và resource ID.
4. Kiểm tra role assignment trực tiếp, assignment qua nhóm và assignment kế thừa.
5. Kiểm tra role definition có chứa đúng operation và assignable scope phù hợp.
6. Kiểm tra Azure Policy hoặc điều kiện role assignment nếu có.
7. Chờ thay đổi quyền truyền đến dịch vụ rồi thử lại trong môi trường an toàn.

Một số nguyên nhân phổ biến:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thể khởi động VM | Thiếu operation start/action hoặc scope không bao gồm VM | Kiểm tra role definition và role assignment |
| Đọc được storage account nhưng không đọc được blob | Chỉ có quyền management plane | Cấp data role phù hợp ở storage account hoặc container |
| Thao tác bị từ chối dù custom role có operation | Principal thiếu assignment, sai scope hoặc role chưa có hiệu lực | Kiểm tra principal, scope và thời gian truyền quyền |
| Người dùng vẫn xóa được resource dù NotActions loại operation | Một role assignment khác cấp quyền xóa | Kiểm tra mọi role assignment trực tiếp và kế thừa |
| Role không thể gán ở scope mong muốn | Scope không nằm trong AssignableScopes | Điều chỉnh nơi định nghĩa role hoặc scope gán role theo thiết kế |
| Không xóa được custom role | Role còn role assignment tham chiếu | Liệt kê và gỡ các assignment trước |

Azure Activity Log có thể hỗ trợ điều tra thao tác quản lý và thay đổi role assignment. Hãy lưu thời điểm, principal, resource ID, operation và correlation ID nếu có để đối chiếu các sự kiện liên quan.

## 8. Danh sách rà soát trước khi đưa custom role vào production

Trước khi đưa một custom role vào sử dụng, hãy tự kiểm tra:

- [ ] Nhiệm vụ của principal được mô tả rõ ràng và có chủ sở hữu.
- [ ] Built-in role đã được xem xét trước khi quyết định tạo custom role.
- [ ] Actions và DataActions chỉ chứa operation cần thiết.
- [ ] NotActions/NotDataActions không bị hiểu nhầm là cơ chế deny.
- [ ] Wildcard được loại bỏ hoặc có lý do và phê duyệt cụ thể.
- [ ] AssignableScopes và scope của role assignment phù hợp với phạm vi công việc.
- [ ] Quyền được gán cho đúng nhóm hoặc managed identity.
- [ ] Quyền đặc quyền có thời hạn hoặc cơ chế kích hoạt khi phù hợp.
- [ ] Đã thử thao tác được phép và xác nhận thao tác ngoài nhiệm vụ bị từ chối.
- [ ] Đã kiểm tra quyền hiệu lực từ các role assignment khác và quyền kế thừa.
- [ ] Có quy trình review, cập nhật, access review và gỡ role khi không còn sử dụng.

## 9. Bài tập thực hành

1. Liệt kê các nhiệm vụ của nhóm vận hành một ứng dụng có virtual machine, virtual network và storage account. Chia nhiệm vụ thành quyền management plane và data plane.
2. Tra cứu operation của Microsoft.Compute. Chọn operation để một nhóm chỉ xem, start và deallocate VM; giải thích vì sao không cấp quyền tạo, sửa hoặc xóa VM.
3. Tạo file JSON cho custom role Orders VM Operator, dùng AssignableScopes ở subscription và gán role tại resource group thử nghiệm.
4. Dùng một principal thử nghiệm để xác nhận các thao tác được phép và bị từ chối. Kiểm tra xem principal có role assignment nào khác có thể mở rộng quyền không.
5. Tạo một nhóm chỉ đọc dữ liệu blob. So sánh Storage Blob Data Reader với Reader để giải thích sự khác nhau giữa management plane và data plane.
6. Viết quy trình review custom role định kỳ: ai là chủ sở hữu, kiểm tra operation nào, xử lý thành viên nhóm ra sao và khi nào cần gỡ role assignment.

## 10. Tài liệu tham khảo

- [Azure role-based access control (Azure RBAC)](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Understand Azure role definitions](https://learn.microsoft.com/azure/role-based-access-control/role-definitions)
- [Steps to create a custom role](https://learn.microsoft.com/azure/role-based-access-control/custom-roles)
- [Assign Azure roles using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Azure built-in roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles)
- [What is Microsoft Entra Privileged Identity Management?](https://learn.microsoft.com/entra/id-governance/privileged-identity-management/pim-configure)

