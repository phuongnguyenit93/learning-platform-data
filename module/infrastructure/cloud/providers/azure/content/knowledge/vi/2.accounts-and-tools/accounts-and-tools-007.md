# Truy vấn tài nguyên bằng Azure Resource Graph

## 1. Azure Resource Graph giải quyết bài toán gì?

Trong một môi trường Microsoft Azure, tài nguyên thường trải rộng trên nhiều subscription, resource group và region. Khi số lượng máy ảo, tài khoản lưu trữ, cơ sở dữ liệu, mạng ảo và các dịch vụ khác tăng lên, việc mở từng resource group để kiểm kê trở nên chậm và dễ bỏ sót. Người vận hành cần trả lời những câu hỏi ở phạm vi rộng như:

- Tổ chức đang có bao nhiêu máy ảo và chúng nằm ở region nào?
- Những tài nguyên nào đang thiếu tag owner hoặc environment?
- Có những storage account nào chưa bật yêu cầu HTTPS?
- Một resource group đang chứa các loại tài nguyên nào?
- Những managed disk nào chưa gắn với máy ảo?

**Azure Resource Graph (ARG)** là dịch vụ truy vấn giúp khám phá thông tin tài nguyên Azure ở quy mô lớn. ARG lập chỉ mục metadata của tài nguyên được quản lý thông qua Azure Resource Manager (ARM), sau đó cho phép truy vấn bằng ngôn ngữ dạng Kusto Query Language (KQL). Bạn có thể truy vấn nhiều subscription trong cùng một lần, tùy theo phạm vi được chọn và quyền truy cập của tài khoản.

ARG đặc biệt hữu ích cho kiểm kê, quản trị, kiểm tra cấu hình, báo cáo và tìm kiếm tài nguyên. Kết quả truy vấn chỉ cung cấp thông tin để phân tích; ARG không phải công cụ thực thi thay đổi cấu hình tài nguyên.

## 2. ARG hoạt động như thế nào?

Khi tài nguyên được tạo hoặc thay đổi thông qua Azure, metadata của tài nguyên được đưa vào hệ thống chỉ mục của Resource Graph. Khi gửi truy vấn, ARG đánh giá câu lệnh trên dữ liệu đã lập chỉ mục và trả về những bản ghi mà người dùng có quyền xem trong phạm vi truy vấn.

Luồng làm việc tổng quát:

~~~mermaid
flowchart TD
    A[Azure resources] --> B[Azure Resource Manager]
    B --> C[Resource Graph index]
    D[Người vận hành] --> E[Portal, Azure CLI hoặc PowerShell]
    E --> F[Truy vấn KQL]
    C --> F
    F --> G[Kết quả theo scope và RBAC]
    G --> H[Kiểm kê, báo cáo, kiểm tra quản trị]
~~~

ARG được tối ưu cho việc truy vấn metadata tài nguyên, không phải hệ thống phân tích mọi loại dữ liệu phát sinh trong ứng dụng. Cần phân biệt:

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Tìm máy ảo, storage account, network, tag, region và thuộc tính tài nguyên | Azure Resource Graph |
| Phân tích log ứng dụng, log nền tảng và dữ liệu log đã thu thập | Azure Monitor Logs / Log Analytics |
| Theo dõi CPU, bộ nhớ, request rate và metric theo thời gian | Azure Monitor Metrics |
| Thực hiện triển khai hoặc thay đổi cấu hình tài nguyên | ARM/Bicep, Azure CLI, PowerShell hoặc công cụ triển khai phù hợp |

ARG là dịch vụ truy vấn chỉ đọc. Dữ liệu được lập chỉ mục có thể có độ trễ so với thay đổi vừa xảy ra trên tài nguyên. Vì vậy, khi cần xác nhận trạng thái tức thời của một thay đổi mới triển khai, hãy kiểm tra trực tiếp tài nguyên hoặc API của dịch vụ liên quan.

## 3. Phạm vi truy vấn và quyền truy cập

### 3.1. Scope

Khi mở Resource Graph Explorer hoặc chạy truy vấn từ công cụ dòng lệnh, bạn chọn phạm vi tài nguyên cần khảo sát. Phạm vi có thể gồm một hoặc nhiều subscription; trong Azure Portal, người dùng có thể chọn các subscription hoặc management group mà họ có quyền truy cập.

Truy vấn nhiều subscription giúp tạo báo cáo tập trung. Ví dụ, đội vận hành có thể thống kê toàn bộ máy ảo của môi trường phát triển, kiểm thử và production mà không phải mở từng subscription riêng.

### 3.2. RBAC lọc kết quả

Azure Resource Graph áp dụng quyền truy cập dựa trên Azure role-based access control (RBAC). Người dùng chỉ nhìn thấy những tài nguyên nằm trong phạm vi mà họ được cấp quyền đọc. Nếu một subscription hoặc resource group không xuất hiện trong kết quả, hãy kiểm tra scope đã chọn và quyền của tài khoản trước khi kết luận rằng tài nguyên không tồn tại.

Trong thực tế, vai trò Reader ở scope phù hợp thường được dùng để đọc tài nguyên. Tổ chức cũng có thể cấp vai trò chuyên biệt cho quyền truy vấn Resource Graph theo chính sách của mình. Quyền truy vấn ARG và quyền đọc tài nguyên phải đáp ứng yêu cầu của môi trường; kết quả không vượt qua quyền RBAC hiện có.

Một truy vấn chạy thành công không chứng minh người dùng đã nhìn thấy toàn bộ tài nguyên trong tenant. Báo cáo kiểm kê chỉ đầy đủ khi phạm vi subscription/management group và quyền truy cập đã được xác nhận.

## 4. Resource Graph Explorer trong Azure Portal

Resource Graph Explorer là giao diện trực quan để viết, chạy và xem kết quả truy vấn.

Quy trình cơ bản:

1. Đăng nhập Azure Portal bằng tài khoản có quyền đọc các subscription cần khảo sát.
2. Mở **Resource Graph Explorer** từ thanh tìm kiếm của Portal.
3. Chọn các subscription hoặc phạm vi được hỗ trợ mà bạn muốn truy vấn.
4. Viết câu lệnh KQL trong vùng soạn thảo.
5. Chọn **Run query** để thực thi.
6. Xem bảng kết quả, điều chỉnh truy vấn và lưu câu lệnh hữu ích để tái sử dụng nếu cần.

Ví dụ truy vấn tất cả tài nguyên trong scope đã chọn:

~~~kusto
Resources
| project name, type, resourceGroup, location, subscriptionId
| order by type asc, name asc
~~~

**Resources** là bảng chứa metadata của các tài nguyên Azure trong phạm vi người dùng có thể đọc. Mỗi dòng thường đại diện cho một tài nguyên. Một số cột thường dùng:

| Cột | Ý nghĩa |
|---|---|
| id | Resource ID đầy đủ của tài nguyên |
| name | Tên tài nguyên |
| type | Loại tài nguyên, thường biểu diễn theo dạng namespace/type |
| resourceGroup | Resource group chứa tài nguyên |
| subscriptionId | ID subscription |
| location | Region của tài nguyên, nếu loại tài nguyên có thuộc tính vị trí |
| tags | Các tag được gắn vào tài nguyên |
| properties | Các thuộc tính chi tiết do resource provider công bố |
| sku | Thông tin SKU, nếu tài nguyên có trường này |

Không phải mọi loại tài nguyên đều có đầy đủ các cột mang ý nghĩa như nhau. Ví dụ, tài nguyên global có thể không có location; một loại tài nguyên có thể không cung cấp sku hoặc một thuộc tính cụ thể trong properties.

## 5. Cú pháp KQL thường dùng

ARG sử dụng cú pháp truy vấn kiểu KQL. Một truy vấn cơ bản thường bắt đầu bằng tên bảng, sau đó nối các toán tử bằng ký tự |. ARG hỗ trợ một tập con các khả năng KQL phù hợp với metadata tài nguyên; không nên giả định rằng mọi hàm hoặc toán tử của Azure Data Explorer đều có thể dùng trong Resource Graph.

Các toán tử thường gặp:

| Toán tử | Mục đích |
|---|---|
| where | Lọc các dòng theo điều kiện |
| project | Chọn các cột cần hiển thị |
| extend | Tạo cột tính toán từ dữ liệu hiện có |
| summarize | Gom nhóm và tính tổng hợp như count() |
| order by | Sắp xếp kết quả |
| take | Giới hạn số dòng trả về |
| join | Kết hợp dữ liệu từ các bảng hoặc tập kết quả |

### 5.1. Lọc theo loại tài nguyên

Ví dụ, chỉ lấy máy ảo Azure:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location, subscriptionId
| order by name asc
~~~

Toán tử **=~** so sánh chuỗi không phân biệt chữ hoa/chữ thường. Dùng toán tử này hữu ích khi so sánh giá trị type, vì cách viết hoa/thường có thể không đồng nhất trong các truy vấn hoặc dữ liệu đầu vào.

### 5.2. Lọc theo resource group hoặc region

~~~kusto
Resources
| where resourceGroup =~ 'rg-production'
| project name, type, location, id
| order by type asc
~~~

Lọc tài nguyên ở một region:

~~~kusto
Resources
| where location =~ 'southeastasia'
| project name, type, resourceGroup, location
| order by resourceGroup asc, name asc
~~~

Tên region trong dữ liệu thường dùng dạng định danh như southeastasia. Hãy kiểm tra giá trị thực tế của cột location nếu kết quả không như mong đợi.

### 5.3. Thống kê số lượng theo loại tài nguyên

~~~kusto
Resources
| summarize total = count() by type
| order by total desc
~~~

Truy vấn này tạo báo cáo tổng số tài nguyên theo từng loại. Có thể dùng cùng cách để thống kê theo region:

~~~kusto
Resources
| summarize total = count() by location
| order by total desc
~~~

Nếu cần thống kê theo cả region và loại:

~~~kusto
Resources
| summarize total = count() by location, type
| order by location asc, total desc
~~~

### 5.4. Truy vấn tag

Tag thường được dùng để phân loại tài nguyên theo môi trường, chủ sở hữu, trung tâm chi phí hoặc ứng dụng. Vì tags là dữ liệu dạng dynamic, nên chuyển giá trị sang chuỗi khi muốn so sánh rõ ràng:

~~~kusto
Resources
| extend environment = tostring(tags['environment'])
| where environment =~ 'production'
| project name, type, resourceGroup, environment
| order by resourceGroup asc
~~~

Tìm tài nguyên thiếu tag owner:

~~~kusto
Resources
| where isempty(tostring(tags['owner']))
| project name, type, resourceGroup, subscriptionId
| order by subscriptionId asc, resourceGroup asc
~~~

Kết quả truy vấn thứ hai có thể dùng làm danh sách cần xử lý trong một đợt chuẩn hóa tag. ARG chỉ phát hiện và liệt kê tài nguyên thiếu tag; việc bổ sung tag cần được thực hiện qua quy trình quản trị hoặc công cụ có quyền ghi phù hợp.

### 5.5. Kiểm tra cấu hình storage account

Ví dụ liệt kê một số thuộc tính bảo mật phổ biến của tài khoản lưu trữ:

~~~kusto
Resources
| where type =~ 'microsoft.storage/storageaccounts'
| project name,
          resourceGroup,
          location,
          httpsOnly = properties.supportsHttpsTrafficOnly,
          minimumTlsVersion = properties.minimumTlsVersion
| order by name asc
~~~

Truy vấn này giúp rà soát nhanh các thuộc tính được Resource Graph lập chỉ mục. Nếu một cột trả về giá trị rỗng, cần xác định thuộc tính đó có được resource provider cung cấp cho loại tài nguyên và thời điểm tương ứng hay không. Không nên tự động diễn giải giá trị rỗng thành cấu hình an toàn hoặc không an toàn.

### 5.6. Tìm managed disk chưa gắn với máy ảo

Thuộc tính managedBy của managed disk thể hiện tài nguyên máy ảo đang quản lý hoặc sử dụng disk đó. Có thể lọc những disk chưa có giá trị này để tiếp tục điều tra:

~~~kusto
Resources
| where type =~ 'microsoft.compute/disks'
| where isempty(managedBy)
| project name, resourceGroup, location, diskSizeGB = properties.diskSizeGB, id
| order by resourceGroup asc, name asc
~~~

Disk không có managedBy có thể là disk chưa gắn với máy ảo, nhưng không nên xóa ngay chỉ dựa trên kết quả này. Disk có thể được giữ lại có chủ đích để sao lưu, phục hồi, di chuyển hoặc chờ gắn vào workload khác. Hãy xác minh owner, thời gian sử dụng và chính sách lưu giữ trước khi thực hiện hành động.

### 5.7. Kết hợp Resources và ResourceContainers

ARG có bảng **ResourceContainers** để truy vấn các container như subscription và resource group. Ví dụ, lấy danh sách resource group:

~~~kusto
ResourceContainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
| project name, subscriptionId, location, tags
| order by subscriptionId asc, name asc
~~~

Có thể kết hợp thông tin máy ảo với tên subscription:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project vmName = name, resourceGroup, subscriptionId, location
| join kind=leftouter (
    ResourceContainers
    | where type =~ 'microsoft.resources/subscriptions'
    | project subscriptionId, subscriptionName = name
) on subscriptionId
| project vmName, subscriptionName, resourceGroup, location
| order by subscriptionName asc, vmName asc
~~~

Toán tử **join** ghép bản ghi theo khóa subscriptionId. Dùng **leftouter** giúp giữ các máy ảo ở vế trái ngay cả khi không tìm thấy bản ghi subscription tương ứng trong tập dữ liệu được truy vấn.

## 6. Chạy truy vấn bằng Azure CLI

Azure CLI cung cấp lệnh az graph query thông qua extension Resource Graph. Nếu máy chưa có extension, cài đặt bằng:

~~~bash
az extension add --name resource-graph
~~~

Đăng nhập và chọn subscription phù hợp:

~~~bash
az login
az account set --subscription '<subscription-id>'
~~~

Chạy truy vấn và hiển thị kết quả dạng bảng:

~~~bash
az graph query --graph-query "Resources | where type =~ 'microsoft.compute/virtualmachines' | project name, resourceGroup, location, subscriptionId" --output table
~~~

Có thể chỉ định nhiều subscription trong tham số --subscriptions khi tài khoản có quyền truy cập:

~~~bash
az graph query --graph-query "Resources | summarize total = count() by type | order by total desc" --subscriptions '<subscription-id-1>' '<subscription-id-2>' --output table
~~~

Khi viết truy vấn dài, nên lưu câu lệnh trong file hoặc biến của shell để dễ đọc và tái sử dụng. Kết quả JSON hữu ích khi cần đưa dữ liệu sang script xử lý tiếp; --output table phù hợp cho kiểm tra nhanh trên terminal.

## 7. Chạy truy vấn bằng Azure PowerShell

Nếu quy trình vận hành dùng PowerShell, cài module Resource Graph:

~~~powershell
Install-Module -Name Az.ResourceGraph -Scope CurrentUser
~~~

Đăng nhập Azure và đặt subscription:

~~~powershell
Connect-AzAccount
$subscriptionId = '<subscription-id>'
Set-AzContext -Subscription $subscriptionId
~~~

Sau đó chạy truy vấn:

~~~powershell
$query = @'
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location, subscriptionId
| order by name asc
'@

Search-AzGraph -Query $query -Subscription $subscriptionId
~~~

Search-AzGraph trả về các bản ghi phù hợp với truy vấn và phạm vi được chỉ định. Với kết quả lớn, hãy đọc hướng dẫn của phiên bản module đang cài về phân trang và tham số số lượng bản ghi; không nên giả định một lần gọi luôn trả về toàn bộ dữ liệu của một môi trường lớn.

## 8. Làm việc với kết quả lớn và tối ưu truy vấn

Một truy vấn trên nhiều subscription có thể trả về lượng dữ liệu đáng kể. Để kết quả dễ đọc và giảm dữ liệu không cần thiết:

- Lọc sớm bằng where, đặc biệt là type, subscriptionId, resourceGroup hoặc location.
- Chỉ lấy các cột cần dùng bằng project; tránh đưa toàn bộ properties vào báo cáo nếu không cần.
- Dùng summarize khi mục tiêu là số liệu tổng hợp thay vì danh sách chi tiết.
- Dùng take trong giai đoạn thử nghiệm để kiểm tra cấu trúc dữ liệu trước khi mở rộng truy vấn.
- Chọn scope subscription hoặc management group đúng với câu hỏi cần trả lời.
- Khi truy vấn trả về nhiều trang, sử dụng cơ chế phân trang của công cụ hoặc API đang dùng để lấy các trang tiếp theo.

Ví dụ chỉ xem thử 20 máy ảo:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location
| take 20
~~~

take giúp kiểm tra nhanh hình dạng dữ liệu, nhưng không bảo đảm mẫu kết quả đại diện cho toàn bộ môi trường. Khi lập báo cáo chính thức, cần bỏ giới hạn thử nghiệm hoặc áp dụng quy tắc phân trang thích hợp.

## 9. Giới hạn và lưu ý khi diễn giải kết quả

ARG rất hữu ích cho kiểm kê, nhưng cần hiểu rõ nguồn dữ liệu và giới hạn của nó:

1. **Dữ liệu là metadata đã lập chỉ mục.** Một thay đổi vừa thực hiện có thể chưa xuất hiện ngay trong kết quả. Không dùng ARG làm bằng chứng duy nhất cho trạng thái tức thời của một thao tác.
2. **Kết quả phụ thuộc RBAC và scope.** Tài nguyên ngoài phạm vi quyền đọc có thể không xuất hiện, dù chúng tồn tại trong tenant.
3. **Không phải mọi thuộc tính đều có mặt.** Cấu trúc properties khác nhau giữa các resource provider và loại tài nguyên; một trường có thể rỗng hoặc không được lập chỉ mục như mong đợi.
4. **ARG dùng tập con KQL.** Một số toán tử, hàm hoặc mẫu truy vấn có trong Azure Data Explorer có thể không được hỗ trợ hoặc có giới hạn trong Resource Graph.
5. **Có giới hạn về kích thước và số lượng kết quả.** Truy vấn quy mô lớn cần phân trang theo cơ chế của Portal, CLI, PowerShell hoặc API; không nên chỉ dựa vào trang kết quả đầu tiên.
6. **ARG không thay thế log và metric.** Dữ liệu hiệu năng, sự kiện theo thời gian và nội dung log cần được thu thập, phân tích bằng các dịch vụ Azure Monitor phù hợp.
7. **Kết quả không phải lệnh khắc phục.** Một dòng kết quả cho thấy cấu hình cần xem xét; việc sửa đổi phải qua công cụ triển khai hoặc quy trình vận hành có kiểm soát.

## 10. Quy trình thực hành kiểm kê một subscription

Giả sử bạn vừa tiếp nhận một subscription mới và cần lập báo cáo ban đầu. Có thể thực hiện theo quy trình:

1. Xác nhận subscription cần khảo sát và tài khoản có quyền đọc tài nguyên.
2. Mở Resource Graph Explorer, chọn đúng subscription và chạy truy vấn liệt kê name, type, resourceGroup, location, id.
3. Chạy truy vấn summarize để đếm tài nguyên theo type và location.
4. Kiểm tra tag owner và environment; tạo danh sách các tài nguyên thiếu thông tin quản trị.
5. Kiểm tra một số cấu hình quan trọng, ví dụ thuộc tính HTTPS/TLS của storage account.
6. Đối chiếu các kết quả bất thường với Portal hoặc cấu hình trực tiếp của tài nguyên trước khi kết luận.
7. Xuất hoặc lưu báo cáo theo quy trình nội bộ, ghi lại thời điểm truy vấn và scope đã chọn.
8. Chuyển các phát hiện thành công việc có owner và thời hạn; chỉ thực hiện thay đổi sau khi xác minh tác động và có quyền phù hợp.

Một báo cáo tốt cần ghi rõ truy vấn đã dùng, thời điểm chạy, danh sách subscription trong scope và giới hạn quyền truy cập. Điều này giúp người đọc hiểu dữ liệu phản ánh phần nào của môi trường.

## 11. Lỗi thường gặp

- **Không tìm thấy az graph.** Kiểm tra extension resource-graph đã được cài trong Azure CLI chưa.
- **Không có kết quả.** Kiểm tra subscription scope, quyền RBAC, tên bảng, điều kiện where và cách viết giá trị type.
- **Thiếu một số subscription.** Xác nhận tài khoản có quyền đọc ở các subscription đó và chúng đã được chọn trong scope.
- **Thuộc tính trả về rỗng.** Kiểm tra schema của loại tài nguyên; không phải resource provider nào cũng cung cấp cùng thuộc tính.
- **Truy vấn KQL bị từ chối.** Kiểm tra toán tử/hàm có nằm trong tập tính năng Resource Graph hỗ trợ hay không.
- **Báo cáo không có tài nguyên mới tạo.** Chờ chỉ mục cập nhật hoặc kiểm tra trực tiếp tài nguyên để xác nhận trạng thái mới nhất.
- **Xóa tài nguyên dựa trên một truy vấn đơn lẻ.** Dùng kết quả làm đầu vào điều tra, xác nhận owner và phụ thuộc trước khi thực hiện thao tác có tác động.

## 12. Ghi nhớ

Azure Resource Graph giúp truy vấn metadata tài nguyên Azure trên nhiều subscription bằng cú pháp KQL, phù hợp cho kiểm kê, tìm kiếm, thống kê và kiểm tra quản trị. Bắt đầu với bảng Resources để truy vấn tài nguyên và ResourceContainers để truy vấn subscription hoặc resource group. Chọn đúng scope, hiểu giới hạn RBAC, lọc sớm và chỉ chiếu các cột cần thiết. Kết quả phản ánh dữ liệu đã lập chỉ mục và quyền người dùng; hãy đối chiếu với Portal, ARM hoặc công cụ giám sát chuyên biệt khi cần xác nhận trạng thái tức thời, log, metric hay thực hiện thay đổi.
