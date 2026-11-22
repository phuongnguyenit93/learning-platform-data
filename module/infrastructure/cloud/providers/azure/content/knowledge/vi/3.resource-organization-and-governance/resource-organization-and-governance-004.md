# Quy ước đặt tên và chiến lược gắn tag

Khi một hệ thống Azure chỉ có vài tài nguyên, bạn có thể nhận ra chúng bằng cách nhìn vào portal. Khi hệ thống có nhiều ứng dụng, môi trường, nhóm vận hành và subscription, việc tìm đúng tài nguyên hoặc xác định chi phí của một nhóm trở nên khó khăn hơn. Một quy ước đặt tên rõ ràng giúp con người nhận diện tài nguyên nhanh chóng; một chiến lược gắn tag bổ sung thông tin quản trị, phân loại và phân bổ chi phí.

Trong hệ sinh thái Microsoft Azure, các tài nguyên tính toán, mạng, lưu trữ và dữ liệu được triển khai bên trong subscription và resource group. Vì vậy, tên và tag cần thể hiện được ứng dụng, môi trường, khu vực, chủ sở hữu và mục đích sử dụng ở mức vừa đủ. Quy ước tốt cũng phải phù hợp với giới hạn tên riêng của từng dịch vụ và có thể được áp dụng nhất quán qua Azure Portal, Azure CLI, Bicep, Terraform hoặc pipeline triển khai.

## 1. Tại sao cần quy ước đặt tên và tag?

Một quy ước thống nhất giải quyết nhiều vấn đề vận hành:

- **Nhận diện nhanh:** nhìn tên có thể biết tài nguyên thuộc ứng dụng nào, môi trường nào và nằm ở khu vực nào.
- **Tìm kiếm và lọc:** tag cho phép lọc tài nguyên theo nhóm, chủ sở hữu, môi trường, dự án hoặc trung tâm chi phí.
- **Phân bổ chi phí:** nhóm tài chính và kỹ thuật có thể phân tích mức sử dụng theo ứng dụng, phòng ban hoặc cost center.
- **Quản trị và bảo mật:** tag có thể biểu thị mức độ quan trọng, phân loại dữ liệu hoặc yêu cầu backup để các nhóm vận hành áp dụng quy trình phù hợp.
- **Tự động hóa:** script và chính sách có thể dựa trên tên, tag hoặc cả hai để kiểm tra, triển khai, báo cáo và dọn dẹp tài nguyên.
- **Bàn giao và kiểm toán:** người mới tiếp nhận hệ thống có thể hiểu cấu trúc tài nguyên mà không phải lần theo từng cấu hình.

Tên tài nguyên và tag phục vụ hai mục đích bổ sung cho nhau. Tên là định danh dễ đọc, thường khó thay đổi sau khi triển khai. Tag là metadata dạng khóa và giá trị, linh hoạt hơn khi chủ sở hữu, trung tâm chi phí hoặc trạng thái vòng đời thay đổi. Không nên cố nhồi mọi thông tin vào tên tài nguyên.

## 2. Thiết kế quy ước đặt tên

### 2.1. Chọn các thành phần có ý nghĩa

Một mẫu tên tổng quát có thể gồm:

~~~text
<resource-type>-<workload>-<environment>-<region>-<instance>
~~~

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| resource-type | Loại tài nguyên Azure | rg, vnet, nsg, vm, kv |
| workload | Ứng dụng hoặc hệ thống mà tài nguyên phục vụ | orders, learning, billing |
| environment | Môi trường triển khai | dev, test, stg, prod |
| region | Khu vực Azure | southeastasia, eastasia |
| instance | Số thứ tự hoặc vai trò của bản thể | 001, 002, api, data |

Không phải tài nguyên nào cũng cần đủ năm thành phần. Resource group có thể dùng mẫu ngắn hơn như:

~~~text
rg-<workload>-<environment>-<region>
~~~

Ví dụ:

- rg-orders-dev-southeastasia
- vnet-orders-prod-southeastasia
- nsg-orders-prod-southeastasia-app
- vm-orders-prod-southeastasia-001

Tên resource group và tên tài nguyên nên cho thấy mối liên hệ với workload. Nếu có nhiều bản thể cùng loại, thêm số thứ tự hoặc vai trò để phân biệt. Số thứ tự nên có độ rộng cố định, chẳng hạn 001, 002, 003, để tên được sắp xếp dễ đọc.

### 2.2. Dùng từ viết tắt có kiểm soát

Tên dịch vụ Azure có thể dài. Từ viết tắt giúp tên ngắn hơn, nhưng chỉ hữu ích khi cả nhóm hiểu cùng một nghĩa. Có thể xây dựng danh mục dùng chung như sau:

| Từ viết tắt | Loại tài nguyên |
|---|---|
| rg | Resource group |
| vnet | Virtual network |
| snet | Subnet |
| nsg | Network security group |
| pip | Public IP address |
| vm | Virtual machine |
| st | Storage account |
| kv | Key Vault |
| app | App Service hoặc ứng dụng, tùy quy ước đã định nghĩa |
| sql | Azure SQL resource |
| law | Log Analytics workspace |
| aks | Azure Kubernetes Service |

Danh mục này là quy ước nội bộ, không phải danh sách bắt buộc của Azure. Đặc biệt, không dùng một từ viết tắt cho hai ý nghĩa khác nhau trong cùng tổ chức. Nếu app có thể chỉ App Service hoặc tên ứng dụng, hãy ghi rõ cách dùng trong tài liệu quy ước.

### 2.3. Chuẩn hóa môi trường và khu vực

Nên chọn một tập giá trị môi trường cố định, ví dụ:

- dev: phát triển.
- test: kiểm thử.
- stg: staging hoặc tiền sản xuất.
- prod: production.

Không trộn lẫn các cách viết như production, prd, live và prod cho cùng một môi trường. Khi thêm môi trường mới, hãy cập nhật danh mục chuẩn và thông báo cho các nhóm liên quan.

Với khu vực, có thể dùng tên location của Azure, chẳng hạn southeastasia hoặc eastasia. Nếu tổ chức muốn dùng mã ngắn như sea, hãy lập bảng ánh xạ tập trung và bảo đảm mọi nhóm hiểu cùng một nghĩa. Không tự tạo mã vùng khác nhau trong từng dự án.

Có thể xem tên location Azure mà subscription hỗ trợ bằng Azure CLI:

~~~bash
az account list-locations --query "[].{Name:name, DisplayName:displayName}" --output table
~~~

Tên location dùng trong lệnh triển khai thường là giá trị ở cột Name. Danh sách khu vực và khả năng cung cấp từng dịch vụ có thể thay đổi; hãy xác minh trước khi chọn khu vực cho workload.

### 2.4. Tuân thủ giới hạn riêng của từng loại tài nguyên

Azure không áp dụng một quy tắc tên duy nhất cho mọi dịch vụ. Mỗi resource provider quy định độ dài, ký tự hợp lệ, phạm vi duy nhất và khả năng đổi tên riêng. Một số tên chỉ cần duy nhất trong resource group hoặc subscription; một số khác phải duy nhất trên phạm vi toàn cầu vì được dùng trong endpoint công khai.

Ví dụ, Storage Account có quy tắc chặt hơn nhiều loại tài nguyên: tên phải viết thường, chỉ gồm chữ cái và chữ số, có độ dài từ 3 đến 24 ký tự và duy nhất trên Azure. Vì vậy, mẫu có dấu gạch ngang không thể áp dụng trực tiếp cho Storage Account.

Ví dụ:

| Tài nguyên | Ví dụ tên | Lưu ý |
|---|---|---|
| Resource group | rg-orders-prod-sea | Có thể dùng dấu gạch ngang theo quy ước |
| Virtual network | vnet-orders-prod-sea | Kiểm tra giới hạn tên của dịch vụ mạng |
| Network security group | nsg-orders-prod-sea-app | Thể hiện vai trò mạng |
| Virtual machine | vm-orders-prod-sea-001 | Có thể cần phối hợp tên Azure resource và hostname của hệ điều hành |
| Storage account | stordersprodsea001 | Chữ thường và chữ số, không có dấu gạch ngang |
| Key Vault | kv-orders-prod-sea-01 | Kiểm tra giới hạn tên và tính duy nhất của dịch vụ |

Các ví dụ trên minh họa cách đặt tên, không bảo đảm tên đã có thể đăng ký. Tên của tài nguyên có namespace toàn cầu có thể đã được người khác sử dụng. Trước khi chuẩn hóa, hãy tra cứu tài liệu naming rules của đúng dịch vụ và thử xác thực bằng công cụ triển khai.

Một số tài nguyên khó hoặc không thể đổi tên sau khi tạo. Đổi tên đôi khi đồng nghĩa với tạo tài nguyên mới, di chuyển dữ liệu, cập nhật tham chiếu và chuyển hướng lưu lượng. Vì vậy, cần thống nhất quy ước trước khi triển khai production.

### 2.5. Những nguyên tắc nên áp dụng

Một quy ước dễ vận hành thường có các đặc điểm sau:

1. **Ngắn gọn:** chỉ đưa vào tên những thông tin giúp nhận diện tài nguyên.
2. **Nhất quán:** cùng một thành phần luôn có cùng thứ tự và cách viết.
3. **Dễ đọc:** dùng chữ thường, dấu gạch ngang khi dịch vụ cho phép và từ viết tắt phổ biến đã được thống nhất.
4. **Ổn định:** tránh đưa thông tin thường xuyên thay đổi như tên cá nhân, ngày triển khai hoặc số phiên bản ứng dụng vào tên tài nguyên lâu dài.
5. **Không chứa dữ liệu nhạy cảm:** không đưa mật khẩu, token, thông tin cá nhân, tên khách hàng bí mật hoặc dữ liệu nội bộ nhạy cảm vào tên.
6. **Phù hợp giới hạn dịch vụ:** kiểm tra độ dài và ký tự hợp lệ của từng resource type.
7. **Có thể mở rộng:** dự trù trường hợp nhiều instance, nhiều vùng hoặc nhiều workload cùng tên.

Không nhất thiết phải đưa tenant ID, subscription ID hoặc mọi cấp tổ chức vào tên. Các thông tin này đã có trong cấu trúc quản lý Azure và có thể được lưu ở hệ thống kiểm kê hoặc tag nếu thực sự cần báo cáo.

## 3. Xây dựng chiến lược gắn tag

### 3.1. Tag là gì?

Tag là cặp khóa và giá trị gắn với subscription, resource group hoặc tài nguyên được hỗ trợ. Ví dụ:

~~~text
Environment = prod
Application = orders
Owner = team-platform
CostCenter = CC042
ManagedBy = IaC
~~~

Tag giúp bổ sung ngữ cảnh cho tài nguyên mà tên không thể thể hiện hết. Một tài nguyên có thể có nhiều tag, nhưng cần giữ bộ tag vừa đủ và thống nhất. Tag không thay thế resource ID, RBAC hay cấu hình kỹ thuật của tài nguyên.

### 3.2. Xác định bộ tag chuẩn

Trước khi gắn tag, hãy thống nhất khóa, ý nghĩa, kiểu giá trị, nhóm chịu trách nhiệm và nơi bắt buộc áp dụng. Một bộ tag khởi đầu có thể gồm:

| Tag | Mục đích | Ví dụ giá trị |
|---|---|---|
| Environment | Môi trường triển khai | dev, test, stg, prod |
| Application | Tên ứng dụng hoặc workload | orders |
| Owner | Nhóm chịu trách nhiệm vận hành | team-platform |
| CostCenter | Mã trung tâm chi phí | CC042 |
| BusinessUnit | Đơn vị nghiệp vụ | commerce |
| ManagedBy | Cách quản lý tài nguyên | IaC, Portal, Automation |
| DataClassification | Mức phân loại dữ liệu | public, internal, confidential |
| Criticality | Mức độ quan trọng của workload | low, medium, high, critical |
| ExpiryDate | Ngày dự kiến kết thúc tài nguyên tạm thời | 2026-12-31 |
| BackupPolicy | Chính sách backup dự kiến áp dụng | daily-30d |

Không phải mọi tag đều cần áp dụng cho mọi tài nguyên. Ví dụ, ExpiryDate hữu ích cho môi trường lab hoặc tài nguyên tạm thời; BackupPolicy có ý nghĩa với tài nguyên cần sao lưu. Hãy phân loại tag thành:

- **Bắt buộc:** thiếu tag sẽ khiến triển khai không đạt chuẩn, ví dụ Environment, Application, Owner và CostCenter.
- **Theo điều kiện:** chỉ bắt buộc với workload hoặc loại dữ liệu nhất định, ví dụ DataClassification, Criticality và BackupPolicy.
- **Tùy chọn:** hỗ trợ tìm kiếm hoặc vận hành nhưng không cần cho mọi tài nguyên.

Đối với hệ thống nhiều nhóm, cần có người sở hữu danh mục tag và quy trình đề xuất thay đổi. Tránh để mỗi nhóm tự tạo khóa mới như CostCentre, Cost_Center, costcenter và CostCenter cho cùng một thông tin.

### 3.3. Chuẩn hóa giá trị tag

Khóa tag cần có cách viết thống nhất, ví dụ PascalCase như Environment và CostCenter. Giá trị nên lấy từ danh mục được phê duyệt, thay vì nhập tự do. Ví dụ, môi trường chỉ nhận dev, test, stg hoặc prod; không nhận đồng thời production, live và prd.

Đối với tag có ngày tháng, nên dùng định dạng ISO 8601 dạng ngày YYYY-MM-DD để dễ sắp xếp và xử lý tự động. Đối với Owner, ưu tiên tên nhóm hoặc địa chỉ liên hệ dùng chung thay vì tên cá nhân, để quyền sở hữu không mất hiệu lực khi nhân sự thay đổi.

Không lưu mật khẩu, khóa truy cập, token, dữ liệu cá nhân hoặc thông tin bí mật trong tag. Tag là metadata văn bản có thể xuất hiện trong báo cáo, truy vấn, hoạt động quản trị và dữ liệu chi phí. Không dùng tag làm cơ chế cấp quyền hoặc làm ranh giới bảo mật.

### 3.4. Gắn tag ở đúng cấp

Tag có thể được áp dụng ở nhiều cấp:

- **Subscription:** các thuộc tính chung của phạm vi quản lý hoặc đơn vị chịu trách nhiệm.
- **Resource group:** thông tin chung cho một nhóm tài nguyên cùng workload và vòng đời.
- **Resource:** thuộc tính riêng của một tài nguyên, chẳng hạn vai trò, chính sách backup hoặc chủ sở hữu chuyên biệt.

Một resource group có thể chứa nhiều tài nguyên cùng ứng dụng và môi trường. Gắn tag ở cấp resource group giúp mô tả nhóm đó, nhưng không có nghĩa tag tự động được sao chép sang từng tài nguyên con. Nếu cần tag đồng nhất ở cấp resource, hãy dùng Azure Policy hoặc cơ chế triển khai để áp dụng và kiểm tra.

Cần lưu ý rằng một số loại tài nguyên hoặc thao tác nhất định có giới hạn về hỗ trợ tag. Hãy kiểm tra khả năng gắn tag của resource type trước khi thiết kế quy trình bắt buộc.

## 4. Kết hợp naming convention và tag trong một mô hình

Tên nên chứa thông tin ổn định để nhận diện nhanh; tag chứa metadata phục vụ quản trị và báo cáo. Ví dụ, một ứng dụng bán hàng có thể tổ chức như sau:

~~~text
Subscription: sub-commerce-prod

Resource group:
  rg-orders-prod-southeastasia

Resources:
  vnet-orders-prod-southeastasia
  nsg-orders-prod-southeastasia-app
  vm-orders-prod-southeastasia-001
  kv-orders-prod-sea-01
  stordersprodsea001
~~~

Các tài nguyên trong resource group có thể dùng bộ tag:

~~~text
Environment      = prod
Application      = orders
Owner            = team-commerce-platform
CostCenter       = CC042
BusinessUnit     = commerce
ManagedBy        = IaC
DataClassification = confidential
Criticality      = high
~~~

Tên resource group và tài nguyên giúp kỹ sư nhận ra workload, môi trường và khu vực. Tag giúp nhóm vận hành lọc tất cả tài nguyên production của ứng dụng orders, còn nhóm tài chính tổng hợp chi phí theo CostCenter. Nếu chủ sở hữu thay đổi từ team-commerce-platform sang nhóm khác, có thể cập nhật tag Owner mà không phải đổi tên từng tài nguyên.

Không cần lặp lại mọi thành phần của tên vào tag. Chỉ giữ tag khi có nhu cầu lọc, báo cáo, tự động hóa hoặc quản trị tương ứng. Ví dụ, nếu khu vực đã được thể hiện rõ trong tên và Azure Resource Graph đã cung cấp location riêng, tag Region chỉ cần thiết khi có một quy trình báo cáo cụ thể yêu cầu nó.

## 5. Áp dụng tag bằng Azure CLI

Azure CLI cho phép tạo resource group kèm tag ngay từ đầu. Ví dụ sau tạo resource group cho môi trường phát triển tại Southeast Asia:

~~~bash
az group create \
  --name rg-orders-dev-southeastasia \
  --location southeastasia \
  --tags Environment=dev Application=orders Owner=team-platform CostCenter=CC042 ManagedBy=IaC
~~~

Đọc tag hiện tại của resource group:

~~~bash
az group show \
  --name rg-orders-dev-southeastasia \
  --query tags \
  --output json
~~~

Cập nhật một số tag của resource group:

~~~bash
az group update \
  --name rg-orders-dev-southeastasia \
  --set tags.Environment=dev tags.Owner=team-platform tags.CostCenter=CC042
~~~

Lọc tài nguyên theo tag Environment:

~~~bash
az resource list \
  --tag Environment=dev \
  --query "[].{Name:name, Type:type, ResourceGroup:resourceGroup}" \
  --output table
~~~

Các lệnh trên giả định bạn đã đăng nhập bằng Azure CLI và đang chọn đúng subscription. Kiểm tra subscription hiện tại trước khi chạy lệnh tạo hoặc cập nhật:

~~~bash
az account show --output table
~~~

Khi chạy trong môi trường doanh nghiệp, hãy tuân thủ quy trình triển khai và quyền truy cập đã được cấp. Không chạy lệnh thay đổi trên production nếu chưa xác minh subscription, resource group và phạm vi tác động.

## 6. Tự động hóa và thực thi quy ước bằng Azure Policy

Tài liệu quy ước chỉ có tác dụng khi các nhóm thực sự áp dụng. Azure Policy giúp kiểm tra và thực thi một số yêu cầu tag ở phạm vi subscription hoặc management group.

Một chiến lược quản trị có thể triển khai theo các bước:

1. **Định nghĩa chuẩn:** công bố mẫu tên, danh mục tag, giá trị hợp lệ và tài nguyên thuộc phạm vi áp dụng.
2. **Kiểm tra khi tạo:** dùng module Bicep, Terraform hoặc pipeline để xác thực tên và tag trước khi gửi yêu cầu triển khai.
3. **Báo cáo sai lệch:** dùng Azure Policy để kiểm tra tài nguyên thiếu tag hoặc có giá trị không hợp lệ.
4. **Tự động bổ sung:** dùng policy phù hợp để thêm tag mặc định hoặc kế thừa tag từ resource group khi có thể.
5. **Khắc phục tài nguyên cũ:** đánh giá các tài nguyên đã tồn tại và chạy remediation khi policy hỗ trợ.
6. **Theo dõi định kỳ:** tổng hợp mức tuân thủ, tài nguyên thiếu Owner hoặc CostCenter và chi phí chưa phân bổ được.

Các policy về tag thường dùng hiệu ứng Audit, Modify hoặc Append tùy mục đích và loại tài nguyên. Audit giúp phát hiện sai lệch; Modify có thể sửa hoặc thêm thuộc tính khi đáp ứng điều kiện và quyền remediation; Append có thể bổ sung giá trị trong quá trình tạo hoặc cập nhật theo định nghĩa policy. Cần đọc kỹ hành vi của từng policy definition trước khi gán ở phạm vi rộng.

Ví dụ, nếu muốn mọi tài nguyên phải có tag CostCenter, có thể bắt đầu bằng policy Audit để thống kê tài nguyên chưa đáp ứng. Sau khi xác định được nhóm chịu trách nhiệm và cách khắc phục, tổ chức có thể chuyển sang quy trình triển khai bắt buộc hoặc policy Modify phù hợp. Không nên bật chính sách từ chối triển khai trên toàn bộ môi trường trước khi kiểm tra các workload hiện có.

### Kế thừa tag từ resource group

Azure không tự động sao chép tag của resource group xuống tất cả tài nguyên con. Nếu muốn tài nguyên nhận tag Environment hoặc CostCenter từ resource group, có thể dùng Azure Policy với hiệu ứng Modify và logic kế thừa phù hợp.

Cần xác định rõ ưu tiên khi tài nguyên đã có tag riêng. Ví dụ, policy có thể chỉ bổ sung tag khi thiếu, hoặc ghi đè theo chuẩn quản trị. Hai hành vi này có tác động khác nhau: ghi đè có thể xóa thông tin phân loại riêng của tài nguyên. Hãy thử nghiệm ở subscription phi production và xác định quy tắc ưu tiên trước khi triển khai rộng.

Azure Policy cũng không thay thế việc thiết kế tag taxonomy. Policy chỉ thực thi những quy tắc đã được tổ chức định nghĩa; nếu danh mục tag thiếu rõ ràng, việc tự động hóa có thể làm dữ liệu metadata thiếu nhất quán trên diện rộng.

## 7. Dùng tag để quản lý chi phí và vòng đời

### Phân tích chi phí

Trong Cost Management, tag hỗ trợ nhóm và lọc dữ liệu chi phí theo ứng dụng, môi trường hoặc CostCenter khi dữ liệu sử dụng có hỗ trợ tag tương ứng. Nhờ vậy, tổ chức có thể trả lời các câu hỏi:

- Ứng dụng orders đang tiêu thụ bao nhiêu chi phí?
- Môi trường dev và test có đang chiếm tỷ trọng quá lớn không?
- Nhóm nào chịu trách nhiệm cho tài nguyên có chi phí tăng bất thường?
- Chi phí nào chưa được gán vào CostCenter?

Tag cần được áp dụng nhất quán và đúng thời điểm để báo cáo có ý nghĩa. Việc bổ sung tag không nhất thiết làm thay đổi dữ liệu chi phí lịch sử đã được ghi nhận. Nếu cần phân tích chi phí cũ, hãy kiểm tra khả năng sử dụng tag inheritance hoặc các chức năng phân tích hiện có trong Cost Management, đồng thời ghi rõ giới hạn dữ liệu.

Tag không tự làm giảm chi phí. Nó giúp xác định ai sở hữu tài nguyên và chi phí phát sinh ở đâu; nhóm vận hành vẫn cần phân tích mức sử dụng, thay đổi kích thước, lịch chạy, chính sách lưu trữ và vòng đời tài nguyên.

### Quản lý vòng đời

Tag ExpiryDate có thể dùng để nhận diện tài nguyên thử nghiệm hoặc môi trường tạm thời. Ví dụ, một resource group cho workshop có thể có:

~~~text
Environment = lab
Owner = team-training
ExpiryDate = 2026-12-31
ManagedBy = IaC
~~~

Một quy trình tự động có thể tìm các resource group đã quá hạn, thông báo cho Owner và yêu cầu xác nhận trước khi dọn dẹp. Không nên xóa tài nguyên chỉ vì ngày hết hạn đã qua nếu chưa kiểm tra phụ thuộc, dữ liệu cần giữ lại và quy trình phê duyệt.

Đối với dữ liệu quan trọng, cần có chính sách backup, retention và quy trình khôi phục độc lập. Tag BackupPolicy chỉ mô tả hoặc phân loại yêu cầu; nó không tự cấu hình backup nếu không có dịch vụ hoặc automation thực thi chính sách đó.

## 8. Những lỗi thường gặp và cách khắc phục

**Mỗi nhóm tự đặt tên theo cách riêng.** Tài nguyên cùng loại trở nên khó tìm và khó tự động hóa. Hãy công bố một mẫu tên chung, danh mục viết tắt và quy tắc ngoại lệ.

**Dùng một mẫu tên cho mọi loại tài nguyên.** Storage Account, Key Vault, VM và resource group có giới hạn khác nhau. Hãy xác thực tên theo từng resource type và điều chỉnh thành phần khi cần.

**Đưa tên cá nhân hoặc thông tin nhạy cảm vào tên và tag.** Thông tin này có thể xuất hiện trong portal, báo cáo và dữ liệu vận hành. Hãy dùng tên nhóm và mã nội bộ đã được phê duyệt; không lưu bí mật trong metadata.

**Tạo nhiều khóa tag cho cùng một ý nghĩa.** Các khóa Owner, owner, ResourceOwner và Contact có thể làm báo cáo bị phân mảnh. Hãy duy trì từ điển tag chuẩn và kiểm tra trước khi thêm khóa mới.

**Dùng giá trị tag tự do.** Một nhóm nhập prod, nhóm khác nhập production và nhóm khác nhập live. Hãy dùng danh sách giá trị cho phép, kiểm tra ở pipeline hoặc Azure Policy.

**Cho rằng tag của resource group tự động áp dụng cho tài nguyên con.** Tag không tự kế thừa. Hãy triển khai policy hoặc quy trình IaC để gắn tag lên đúng phạm vi.

**Dùng tag như cơ chế bảo mật.** Người dùng có thể đọc hoặc sửa tag nếu được cấp quyền phù hợp; tag cũng không tự ngăn truy cập. Hãy dùng Entra ID, Azure RBAC, Azure Policy và các cơ chế bảo vệ dữ liệu tương ứng.

**Coi tag là dữ liệu luôn chính xác.** Owner có thể chuyển nhóm, CostCenter có thể thay đổi và tài nguyên có thể bị triển khai ngoài pipeline chuẩn. Hãy kiểm tra định kỳ và xác định người chịu trách nhiệm cập nhật metadata.

## 9. Quy trình đề xuất cho một nhóm Azure

Một nhóm mới có thể bắt đầu bằng quy trình ngắn sau:

1. Chọn cách phân tách subscription và resource group theo ứng dụng, môi trường và ranh giới quản trị.
2. Viết mẫu tên cho resource group, mạng, máy tính, lưu trữ, dữ liệu và các dịch vụ nền tảng.
3. Lập danh mục viết tắt, mã vùng và giá trị môi trường được phép.
4. Chọn các tag bắt buộc như Environment, Application, Owner và CostCenter; xác định tag có điều kiện cho dữ liệu, backup và vòng đời.
5. Tích hợp quy tắc vào Bicep/Terraform hoặc pipeline để tên và tag được tạo nhất quán.
6. Dùng Azure Policy để audit, phát hiện thiếu tag và triển khai remediation theo từng giai đoạn.
7. Theo dõi chi phí theo tag trong Cost Management và rà soát tài nguyên thiếu chủ sở hữu.
8. Cập nhật quy ước khi có workload, dịch vụ hoặc yêu cầu quản trị mới.

Nên lưu quy ước trong tài liệu kỹ thuật dùng chung, có người sở hữu và có lịch rà soát. Khi một ngoại lệ được chấp nhận, hãy ghi lại lý do và phạm vi áp dụng để ngoại lệ không trở thành một quy ước thứ hai ngoài ý muốn.

## 10. Tự kiểm tra

1. Tên tài nguyên và tag có cùng mục đích không? **Không.** Tên giúp nhận diện ổn định; tag bổ sung metadata để lọc, báo cáo và tự động hóa.
2. Có thể dùng mẫu có dấu gạch ngang cho mọi tài nguyên Azure không? **Không.** Quy tắc tên phụ thuộc resource type; Storage Account chẳng hạn không cho phép dấu gạch ngang.
3. Tag của resource group có tự động được sao chép xuống tài nguyên con không? **Không.** Cần dùng Azure Policy hoặc cơ chế triển khai để kế thừa hay áp dụng tag.
4. Có nên lưu access key hoặc mật khẩu trong tag không? **Không.** Tag là metadata, không phải kho bí mật.
5. Tag CostCenter có thể hỗ trợ điều gì? **Phân tích và phân bổ chi phí** theo trung tâm chi phí khi dữ liệu sử dụng hỗ trợ tag.
6. Azure Policy có thể giúp gì cho chiến lược tag? **Audit, bổ sung hoặc sửa tag theo quy tắc** và giúp phát hiện tài nguyên không tuân thủ.
7. Khi Owner thay đổi, có cần đổi tên mọi tài nguyên không? **Thông thường không.** Cập nhật tag Owner và hệ thống quản lý liên quan; tên tài nguyên nên giữ ổn định nếu không có lý do kỹ thuật để thay đổi.

## 11. Tài liệu tham khảo

- [Azure resource naming rules](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-name-rules) — giới hạn tên theo từng loại tài nguyên.
- [Define your naming convention](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming) — hướng dẫn xây dựng quy ước đặt tên trong Azure.
- [Use tags to organize your Azure resources and management hierarchy](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources) — cách gắn và quản lý tag.
- [Azure Policy documentation](https://learn.microsoft.com/azure/governance/policy/) — kiểm tra và thực thi chính sách quản trị.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — phân tích và quản lý chi phí Azure.

Các giới hạn tên, khả năng hỗ trợ tag và hành vi của từng policy có thể khác theo dịch vụ. Khi triển khai thực tế, hãy kiểm tra tài liệu chính thức của resource provider và thử nghiệm quy ước trong subscription phát triển trước khi áp dụng cho production.
