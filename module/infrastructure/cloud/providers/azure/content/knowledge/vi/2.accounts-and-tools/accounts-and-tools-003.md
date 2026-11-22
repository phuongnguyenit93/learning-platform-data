# Sử dụng Azure Portal và Cloud Shell

Trong chương **Tài khoản và công cụ**, Azure Portal và Azure Cloud Shell là hai cách làm việc trực tiếp với tài nguyên Microsoft Azure. Portal cung cấp giao diện đồ họa để khám phá dịch vụ, cấu hình và quan sát trạng thái. Cloud Shell cung cấp terminal trên trình duyệt để truy vấn, thực hiện lệnh và chuẩn bị các thao tác có thể lặp lại.

Khi học hệ sinh thái Azure, điều quan trọng không chỉ là tìm được nút tạo tài nguyên. Bạn cần biết mình đang dùng danh tính nào, ở tenant nào, thao tác trên subscription nào, có quyền gì và kết quả được xác minh ở đâu. Những kỹ năng đó sẽ được dùng lại khi triển khai mạng ảo, dịch vụ tính toán, storage, cơ sở dữ liệu và giám sát ứng dụng.

Bài học kết hợp giải thích với một lab nhỏ: tạo một resource group riêng trên Portal, kiểm tra bằng Cloud Shell, cập nhật tag rồi dọn dẹp. Lab không yêu cầu tạo VM, database hay storage account cho ứng dụng. Các lệnh là hướng dẫn để người học chủ động thực hiện trong subscription lab có quyền phù hợp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Tìm tài nguyên và các trang quản trị quan trọng trong Azure Portal.
- Phân biệt tenant, subscription và phạm vi quyền trước khi thao tác.
- Khởi động Cloud Shell với Bash hoặc PowerShell và chọn chế độ lưu tệp phù hợp.
- Kiểm tra context bằng Azure CLI hoặc Azure PowerShell.
- Đối chiếu cùng một resource group giữa giao diện và dòng lệnh.
- Phân biệt dữ liệu của phiên shell với tài nguyên Azure, đồng thời biết cách kiểm tra lỗi và chi phí liên quan.

## 1. Portal và Cloud Shell phục vụ những việc gì?

**Azure Portal** là giao diện web thống nhất để tạo, quản lý và theo dõi tài nguyên Azure. Bạn truy cập tại [Azure Portal](https://portal.azure.com/), đăng nhập rồi tìm dịch vụ hoặc tài nguyên cần làm việc. Xem [tổng quan Azure Portal](https://learn.microsoft.com/en-us/azure/azure-portal/azure-portal-overview).

**Azure Cloud Shell** là môi trường dòng lệnh được Azure quản lý, truy cập qua trình duyệt, có sẵn nhiều công cụ và tích hợp xác thực với tài khoản của bạn. Nó có thể được mở từ thanh công cụ Portal hoặc tại [Cloud Shell](https://shell.azure.com/). Xem [tổng quan Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/overview).

| Công việc | Portal | Cloud Shell |
| --- | --- | --- |
| Khám phá một dịch vụ mới | Thuận tiện để xem các mục cấu hình | Thuận tiện khi đã biết nhóm lệnh cần dùng |
| Kiểm tra một tài nguyên | Đọc các trang Overview, Properties và trạng thái | Lấy các thuộc tính cụ thể, lọc đầu ra |
| Tạo cấu hình lần đầu | Wizard hướng dẫn các trường cần nhập | Lệnh thể hiện tham số rõ ràng, có thể lưu thành script |
| Kiểm kê nhiều tài nguyên | Dùng danh sách và bộ lọc | Dùng truy vấn hoặc vòng lặp có kiểm soát |
| Xử lý lỗi triển khai | Xem thông báo và chi tiết thao tác | Đọc mã lỗi, kết quả lệnh và đối chiếu định danh |
| Chuẩn bị tự động hóa | Giúp hiểu cấu hình cần thiết | Là bước chuyển sang script và Infrastructure as Code |

Hai công cụ làm việc với cùng hệ thống tài nguyên Azure theo quyền của danh tính đang dùng. Một thay đổi được thực hiện thành công qua dòng lệnh có thể được nhìn thấy trên Portal sau khi tải lại dữ liệu.

Có quyền mở Cloud Shell không đồng nghĩa có thêm quyền quản trị. Một lệnh gọi API vẫn phải qua xác thực, phân quyền và các quy tắc quản trị áp dụng tại phạm vi đích.

## 2. Nắm rõ danh tính và phạm vi làm việc

Trước mỗi thao tác tạo, cập nhật hoặc xóa, cần trả lời bốn câu hỏi:

1. **Account:** tôi đang đăng nhập bằng tài khoản nào?
2. **Tenant/directory:** danh tính và subscription đang gắn với directory nào?
3. **Subscription:** tài nguyên và chi phí thuộc subscription nào?
4. **Scope:** thao tác nhắm tới subscription, resource group hay một tài nguyên cụ thể?

### Tenant, subscription và resource group

**Microsoft Entra tenant** là ranh giới quản lý danh tính của tổ chức. **Subscription** là phạm vi chứa tài nguyên Azure và gắn với cơ chế thanh toán, quota cùng các chính sách liên quan. **Resource group** là nhóm quản lý những tài nguyên có quan hệ, thường có vòng đời tương đồng.

Một tài khoản có thể truy cập nhiều tenant và nhiều subscription. Tên subscription có thể gần giống nhau; khi thực hành nên đối chiếu **subscription ID** để xác định đích.

Ví dụ một định danh resource group:

```text
/subscriptions/<subscription-id>/resourceGroups/rg-portal-shell-lab-01
```

Định danh đầy đủ giúp phân biệt các nhóm có cùng tên ở các subscription khác nhau.

### Xác thực và phân quyền là hai việc khác nhau

Đăng nhập thành công chứng minh hệ thống nhận diện được danh tính. Khả năng đọc hoặc thay đổi một tài nguyên còn phụ thuộc quyền tại đúng scope.

Ví dụ:

- Vai trò Reader ở scope thích hợp thường phục vụ việc xem tài nguyên quản lý.
- Vai trò cho phép quản lý tài nguyên không nhất thiết cho phép cấp quyền cho người khác.
- Quyền quản lý storage account không tự đồng nghĩa có quyền đọc mọi dữ liệu blob.
- Vai trò quản trị directory và vai trò Azure RBAC trên subscription phục vụ các phạm vi khác nhau.

Khi gặp lỗi quyền, cần xác định thao tác cụ thể bị từ chối và scope tương ứng. Việc yêu cầu một vai trò rộng hơn mà chưa biết thiếu quyền ở đâu làm khó kiểm soát hệ thống.

## 3. Điều hướng Azure Portal có phương pháp

Giao diện có thể thay đổi theo dịch vụ, ngôn ngữ hiển thị và phiên bản Portal. Hãy tìm theo chức năng và tên dịch vụ, thay vì chỉ ghi nhớ vị trí một nút.

### Các thành phần thường dùng

| Thành phần | Cách sử dụng |
| --- | --- |
| Global search | Tìm dịch vụ như Resource groups, Virtual networks, Storage accounts hoặc tài nguyên theo tên |
| Portal menu và All services | Khám phá danh mục dịch vụ |
| Home và Recent resources | Quay lại tài nguyên vừa làm việc |
| Notifications | Xem tiến trình hoặc thông báo của thao tác gần đây |
| Settings | Điều chỉnh giao diện, directory và bộ lọc subscription |
| Cloud Shell | Mở terminal trong giao diện |
| Service/resource menu | Truy cập các trang riêng của dịch vụ hoặc tài nguyên |
| Breadcrumb | Quay lại phạm vi trước trong luồng điều hướng |

Khi tìm kiếm, phân biệt kết quả là **dịch vụ** với **một tài nguyên cụ thể**. Mở dịch vụ Resource groups đưa bạn đến danh sách nhóm; mở tên một nhóm đưa bạn đến nhóm đó.

### Kiểm tra directory và bộ lọc subscription

Trong Portal settings, mục **Directories + subscriptions** cho phép xem directory hiện tại, chuyển directory và điều chỉnh bộ lọc subscription. Bộ lọc có thể làm một subscription bị ẩn khỏi các danh sách thông thường. Xem [thiết lập Portal và bộ lọc subscription](https://learn.microsoft.com/en-us/azure/azure-portal/set-preferences).

Khi không thấy tài nguyên mong đợi, hãy kiểm tra theo thứ tự:

1. Tài khoản đăng nhập có đúng không?
2. Directory hiện tại có đúng không?
3. Subscription có nằm trong bộ lọc không?
4. Danh sách đang lọc theo tên, loại, region hoặc resource group nào?
5. Danh tính có quyền đọc tại scope cần thiết không?

Bộ lọc là công cụ điều chỉnh cách hiển thị. Nó không thay đổi quyền RBAC và không phải cơ chế ngăn dòng lệnh thao tác lên subscription khác.

## 4. Đọc một trang tài nguyên trên Portal

Khi mở một tài nguyên, đừng bắt đầu bằng việc đổi cấu hình. Trước hết, xác minh tên, loại tài nguyên, subscription, resource group, region và định danh.

Các mục thường gặp gồm:

| Mục | Câu hỏi được giải đáp |
| --- | --- |
| Overview | Tôi đang xem tài nguyên nào và trạng thái tổng quát ra sao? |
| Properties hoặc JSON view | Các thuộc tính và định danh cụ thể là gì? |
| Activity log | Những thao tác quản lý nào đã được ghi nhận tại scope này? |
| Access control (IAM) | Quyền Azure RBAC được gán ở đây như thế nào? |
| Tags | Tài nguyên được gắn metadata quản lý nào? |
| Locks | Có khóa quản trị ảnh hưởng đến cập nhật hoặc xóa không? |
| Deployments | Có các lần triển khai ARM/Bicep nào tại scope được hỗ trợ? |
| Monitoring | Có metric, log, cảnh báo nào phù hợp với dịch vụ? |

Không phải loại tài nguyên nào cũng có mọi mục trên.

### Activity log không phải log ứng dụng

Activity log ghi nhận các hoạt động quản lý, chẳng hạn tạo, cập nhật, xóa hoặc lỗi triển khai. Nó không thay thế log nghiệp vụ, log truy cập dữ liệu hay dữ liệu chẩn đoán của ứng dụng. Các loại log đó cần được xem ở đúng nguồn và có thể cần cấu hình thu thập. Xem [Activity log trong Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log).

Khi xem một lỗi, nên ghi lại thời điểm, scope, operation, mã lỗi và correlation ID nếu có. Một thông báo tổng quát như “deployment failed” thường cần mở chi tiết để thấy thao tác con thực sự thất bại.

Activity log có độ trễ hiển thị. Không tìm thấy sự kiện ngay lập tức chưa đủ để kết luận thao tác không xảy ra. Các yêu cầu bị từ chối trước khi một thao tác quản lý bắt đầu cũng có thể không tạo bản ghi tại đây.

### Deployment thành công cần được đối chiếu với tài nguyên

Một deployment ghi nhận quá trình triển khai cấu hình. Sau khi thành công, vẫn cần kiểm tra tài nguyên kết quả và hành vi mong muốn.

Ví dụ, “tạo web app thành công” chưa chứng minh ứng dụng truy cập được database hoặc xử lý được yêu cầu người dùng. Trong lab này, kết quả cần kiểm tra đơn giản hơn: đúng resource group, đúng subscription và đúng tag.

## 5. Cloud Shell chạy ở đâu và được xác thực như thế nào?

Cloud Shell chạy trên một host tạm thời do Azure cung cấp cho phiên của người dùng. Công cụ hỗ trợ Bash và PowerShell; môi trường host là Linux, kể cả khi bạn chọn PowerShell. Các công cụ như Azure CLI và Azure PowerShell được chuẩn bị sẵn theo môi trường dịch vụ. Xem [tính năng Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/features).

Vì vậy:

- Đường dẫn của máy cá nhân như `C:\Projects\app` không tự xuất hiện trong Cloud Shell.
- Chọn PowerShell không có nghĩa đang dùng Windows PowerShell trên máy Windows.
- Cài thêm gói hoặc thay đổi trạng thái host không đồng nghĩa thay đổi đó tồn tại ở phiên sau.
- Cloud Shell phù hợp với quản trị tương tác; công việc chạy nền lâu dài nên dùng dịch vụ thực thi thích hợp.

Cloud Shell tích hợp xác thực cho Azure CLI và Azure PowerShell. Trong tình huống thông thường, bạn không cần bắt đầu bằng việc chạy lại lệnh đăng nhập. Tuy nhiên, vẫn phải kiểm tra tenant và subscription đích trước khi gọi lệnh quản lý.

### Phiên shell và tài nguyên Azure có vòng đời khác nhau

| Đối tượng | Khi đóng hoặc kết thúc phiên Cloud Shell |
| --- | --- |
| Biến shell và tiến trình đang chạy | Không nên kỳ vọng tiếp tục tồn tại |
| Tệp trong phiên ephemeral | Không được giữ lại cho phiên sau |
| Tệp thuộc cơ chế lưu trữ persistent được cấu hình | Có thể được giữ lại theo cấu hình lưu trữ |
| Resource group, VM, database đã tạo trong Azure | Vẫn tồn tại cho đến khi được thay đổi hoặc xóa |
| Tài nguyên lưu trữ dùng cho Cloud Shell | Vẫn tồn tại nếu chưa được dọn dẹp riêng |

Đóng cửa sổ terminal không hoàn tác lệnh tạo tài nguyên và không dừng việc tính phí của các tài nguyên còn tồn tại.

## 6. Khởi động Cloud Shell và lựa chọn lưu tệp

### Điều kiện cần chuẩn bị

Bạn cần tài khoản Azure hợp lệ, subscription phù hợp, quyền sử dụng các tài nguyên liên quan và kết nối trình duyệt đáp ứng yêu cầu của tổ chức.

Tài liệu khởi động Cloud Shell yêu cầu resource provider `Microsoft.CloudShell` được đăng ký trong subscription. Có thể kiểm tra tại **Subscriptions → subscription đích → Resource providers**. Nếu chưa đăng ký và bạn không có quyền thực hiện, cần người quản trị phụ trách subscription xử lý. Xem [bắt đầu phiên ephemeral](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/ephemeral).

### Mở phiên đầu tiên

1. Đăng nhập Portal và xác minh tài khoản, directory.
2. Chọn biểu tượng Cloud Shell trên thanh công cụ.
3. Chọn Bash hoặc PowerShell.
4. Chọn subscription dùng cho thiết lập Cloud Shell.
5. Chọn có gắn storage hay không, rồi hoàn thành các bước được hiển thị.
6. Chờ xuất hiện dấu nhắc lệnh trước khi thao tác.

Hai chế độ lưu tệp phục vụ nhu cầu khác nhau:

| Chế độ | Phù hợp khi | Điều cần nhớ |
| --- | --- | --- |
| Ephemeral, không yêu cầu storage account | Truy vấn nhanh hoặc thực hành không cần giữ tệp | Tệp trong phiên không được lưu qua lần sử dụng sau |
| Persistent, gắn Azure Files storage | Cần giữ script, cấu hình hoặc tệp công việc | Cần storage phù hợp, quyền truy cập và chi phí lưu trữ |

Với lab resource group trong bài, chế độ ephemeral có thể đủ vì các thao tác chính không cần lưu tệp giữa các phiên.

### Khi cần lưu trữ persistent

Bạn có thể chọn tạo storage mới hoặc dùng storage hiện có theo luồng được Cloud Shell hỗ trợ. Hãy chọn rõ subscription, resource group và vị trí tài nguyên lưu trữ. Xem [khởi động với persistent storage](https://learn.microsoft.com/en-us/azure/cloud-shell/quickstart).

Khi cấu hình lưu trữ persistent, Cloud Shell sử dụng Azure Files để lưu nội dung được hỗ trợ, gồm image của thư mục home và file share được gắn tại `clouddrive`. Tệp ngoài phạm vi được lưu không tự tồn tại ở phiên sau. Xem [cách Cloud Shell lưu tệp](https://learn.microsoft.com/en-us/azure/cloud-shell/persisting-shell-storage).

Không nên đặt storage phục vụ Cloud Shell vào resource group lab mà bạn dự định xóa cuối buổi. Nếu xóa group chứa storage này, bạn có thể mất cả dữ liệu shell đã lưu.

Vị trí storage của Cloud Shell, vị trí host chạy phiên shell và region của tài nguyên ứng dụng là các quyết định khác nhau. Việc mở shell ở một vị trí không tự buộc VM hoặc database phải được tạo ở cùng vị trí đó.

## 7. Chọn Bash hay PowerShell

Lựa chọn shell nên dựa trên công cụ và cú pháp bạn muốn dùng:

| Nội dung | Bash với Azure CLI | PowerShell với mô-đun Az |
| --- | --- | --- |
| Công cụ Azure thường dùng | `az` | Cmdlet như `Get-AzResourceGroup` |
| Tạo biến | `labName="demo"` | `$labName = "demo"` |
| Đọc biến | `"$labName"` | `$labName` |
| Kết quả Azure | Azure CLI thường xuất JSON hoặc định dạng được chọn | Đối tượng PowerShell |
| Lọc dữ liệu | `--query` của Azure CLI hoặc công cụ xử lý phù hợp | `Where-Object`, `Select-Object` |
| Chọn subscription | `az account set` | `Set-AzContext` |
| Kiểm tra context | `az account show` | `Get-AzContext` |

Azure CLI cũng có thể chạy trong PowerShell. **Shell** và **công cụ quản lý Azure** là hai lớp khác nhau. Chuyển sang PowerShell không tự chuyển mọi lệnh `az` thành cmdlet Az.

Ví dụ cú pháp Bash sau không phải cú pháp gán biến PowerShell:

```bash
labResourceGroup="rg-portal-shell-lab-01"
```

Trong PowerShell, cách viết tương ứng là:

```powershell
$labResourceGroup = "rg-portal-shell-lab-01"
```

Để tránh nhầm lẫn khi mới học, hãy đi trọn nhánh Bash/CLI hoặc PowerShell/Az cho một thao tác, rồi mới so sánh hai cách.

## 8. Kiểm tra và chọn context trong Azure CLI

Các ví dụ ở phần này dùng Bash. Giá trị đặt trong dấu `<...>` là chỗ cần thay bằng thông tin của subscription lab.

### Xem danh sách subscription và context hiện tại

```bash
az account list --query "[].{Name:name,Id:id,Tenant:tenantId,Default:isDefault}" --output table
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

Đối chiếu `Id` và `Tenant` với thông tin trên Portal. Việc Portal đang lọc một subscription không phải bằng chứng rằng Azure CLI đang chọn cùng subscription đó.

### Chọn subscription bằng ID

```bash
labSubscriptionId="<subscription-id>"
az account set --subscription "$labSubscriptionId"
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

Chỉ tiếp tục khi lệnh chọn context thành công và kết quả đúng đích. Nếu lệnh trả lỗi, dừng nhánh thao tác đó để xử lý nguyên nhân.

Đối với các lệnh quản lý trong lab, bài học tiếp tục truyền `--subscription "$labSubscriptionId"` để thể hiện rõ đích, ngay cả khi đã chọn context mặc định.

### Chọn định dạng đầu ra

- `--output table`: tiện quan sát một tập trường ngắn.
- `--output json`: tiện xem cấu trúc và thuộc tính lồng nhau.
- `--output tsv`: phù hợp khi cần lấy giá trị đơn giản để xử lý tiếp.
- `--query`: lọc hoặc biến đổi kết quả bằng biểu thức JMESPath.

Ví dụ chỉ đọc tên và vị trí resource group:

```bash
az group list --subscription "$labSubscriptionId" --query "[].{Name:name,Region:location}" --output table
```

`--query` thay đổi đầu ra được hiển thị; nó không đổi resource group hoặc cấp thêm quyền.

## 9. Kiểm tra và chọn context trong Azure PowerShell

Nếu chọn PowerShell/Az, sử dụng context của mô-đun Az:

```powershell
Get-AzSubscription | Select-Object Name, Id, TenantId
Get-AzContext
```

Tiếp theo chọn subscription lab:

```powershell
$labSubscriptionId = "<subscription-id>"
$labContext = Set-AzContext -SubscriptionId $labSubscriptionId -ErrorAction Stop

$labContext.Subscription | Select-Object Name, Id
$labContext.Tenant | Select-Object Id
```

`-ErrorAction Stop` giúp lỗi PowerShell dừng nhánh thực thi thay vì tiếp tục như thể việc chọn context đã thành công. Đối chiếu subscription và tenant trước các bước thay đổi tài nguyên.

Azure PowerShell dùng context để giữ thông tin subscription và xác thực. Xem [Azure PowerShell context](https://learn.microsoft.com/en-us/powershell/azure/context-persistence).

Khi dùng cả `az` và cmdlet Az trong một shell, phải kiểm tra context của **từng công cụ**. `az account set` không thay cho `Set-AzContext`, và việc đổi directory trong Portal cũng không phải bước xác minh context của hai công cụ này.

Ví dụ đọc resource group bằng context đã xác minh:

```powershell
Get-AzResourceGroup -DefaultProfile $labContext |
    Select-Object ResourceGroupName, Location
```

Đừng dựa vào tên context để suy ra mọi thuộc tính. Hãy kiểm tra subscription ID và tenant ID mà context thực sự chứa.

## 10. Lab: tạo resource group trên Portal

### Chuẩn bị đích thực hành

Dùng một subscription được phép thực hành và resource group mới, chưa dùng cho công việc khác.

| Thông tin | Giá trị minh họa |
| --- | --- |
| Subscription | Subscription lab mà bạn đã xác minh ID |
| Resource group | `rg-portal-shell-lab-01` |
| Region metadata | `Southeast Asia`, nếu chính sách cho phép |
| Tag môi trường | `Environment=Lab` |
| Tag mục đích | `Purpose=PortalCloudShell` |

Nếu tên group đã tồn tại trong subscription đích, chọn tên lab khác rồi dùng nhất quán ở tất cả các bước. Không tận dụng một group có sẵn mà bạn chưa biết nội dung.

Resource group là vùng chứa quản lý. Việc tạo một group rỗng không tạo VM, database hoặc dịch vụ tính toán có tính phí. Nếu bạn chọn persistent Cloud Shell, tài nguyên storage phục vụ shell là một phần riêng cần theo dõi.

### Tạo và ghi nhận kết quả

Trên Portal, tìm **Resource groups**, chọn **Create**, điền subscription, tên group và region. Thêm hai tag của lab nếu giao diện hỗ trợ tại bước đó; nếu chưa có, thêm qua mục Tags sau khi group được tạo. Kiểm tra phần tổng hợp rồi gửi yêu cầu tạo.

Khi thao tác hoàn thành:

- Mở group và kiểm tra subscription ID, tên, region cùng các tag.
- Ghi lại resource ID để đối chiếu.
- Xác minh group chưa chứa tài nguyên ứng dụng nào.
- Quan sát Notifications và Activity log khi cần tìm thông tin thao tác.

Region của resource group là nơi lưu metadata của group. Các tài nguyên được tạo trong group sau này có thuộc tính vị trí riêng theo khả năng của từng dịch vụ. Xem [quản lý resource group trên Portal](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal).

Nếu chỉ được cấp quyền trên một resource group có sẵn, bạn có thể không có quyền tạo group ở cấp subscription. Trong trường hợp đó, cần một môi trường lab được chuẩn bị phù hợp trước khi làm phần tạo và xóa group.

## 11. Lab: kiểm tra và cập nhật bằng Cloud Shell

Chọn **một** nhánh công cụ dưới đây. Cả hai cùng làm việc với group đã tạo trên Portal, không yêu cầu tạo thêm group.

### Nhánh A: Bash với Azure CLI

Khôi phục hoặc khai báo biến của phiên hiện tại và kiểm tra context theo phần 8:

```bash
labSubscriptionId="<subscription-id>"
labResourceGroup="rg-portal-shell-lab-01"

az account set --subscription "$labSubscriptionId"
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

Sau khi xác minh đúng subscription và không có lỗi, đọc group:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query "{Name:name,Id:id,Region:location,Tags:tags}" --output json
```

Kết quả cần có tên group, resource ID chứa subscription đích và hai tag ban đầu. Định dạng region trong API thường là tên mã như `southeastasia`, có thể khác cách Portal hiển thị tên.

Để thực hành một thay đổi nhỏ, thêm tag `VerifiedBy=CloudShell`:

```bash
az group update --subscription "$labSubscriptionId" --name "$labResourceGroup" --set tags.VerifiedBy=CloudShell --output json
```

Đọc lại tag bằng một lệnh riêng:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query tags --output json
```

Lệnh đọc lại là bước xác minh trạng thái sau cập nhật, thay vì chỉ dựa vào việc terminal không hiện thông báo lỗi. Tham khảo [nhóm lệnh Azure CLI cho resource group](https://learn.microsoft.com/en-us/cli/azure/group?view=azure-cli-latest).

### Nhánh B: PowerShell với mô-đun Az

Tạo context bằng subscription lab như phần 9:

```powershell
$labSubscriptionId = "<subscription-id>"
$labResourceGroup = "rg-portal-shell-lab-01"

$labContext = Set-AzContext -SubscriptionId $labSubscriptionId -ErrorAction Stop
$labContext.Subscription | Select-Object Name, Id
$labContext.Tenant | Select-Object Id
```

Sau khi xác minh đúng đích, lấy group và đọc thuộc tính:

```powershell
$labGroup = Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop
$labGroup | Select-Object ResourceGroupName, Location, ResourceId
$labGroup.Tags
```

Cmdlet `Get-AzResourceGroup` trả về đối tượng có thể tiếp tục xử lý trong PowerShell. Xem [tài liệu Get-AzResourceGroup](https://learn.microsoft.com/en-us/powershell/module/az.resources/get-azresourcegroup).

Thêm tag theo thao tác merge để giữ các tag khác:

```powershell
$labTagUpdate = @{ VerifiedBy = "CloudShell" }
Update-AzTag -ResourceId $labGroup.ResourceId -Operation Merge -Tag $labTagUpdate -DefaultProfile $labContext -ErrorAction Stop

(Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop).Tags
```

`Merge` bổ sung khóa mới hoặc cập nhật khóa cùng tên; `Replace` có ý nghĩa thay toàn bộ tập tag. Không dùng hai thao tác này như thể tương đương. Xem [tài liệu Update-AzTag](https://learn.microsoft.com/en-us/powershell/module/az.resources/update-aztag).

### Đối chiếu lại trên Portal

Quay lại đúng resource group và dùng Refresh hoặc mở lại mục Tags. Kiểm tra:

```text
Environment = Lab
Purpose     = PortalCloudShell
VerifiedBy  = CloudShell
```

Nếu chưa thấy tag mới, đối chiếu resource ID trước khi kết luận cập nhật thất bại. Sau đó kiểm tra lại dữ liệu tải về, scope và thông báo lỗi nếu có.

Tag là metadata dạng văn bản, phù hợp phân loại mục đích, môi trường hoặc đơn vị phụ trách. Không đặt secret trong tag. Tài nguyên con không tự kế thừa tag của group chỉ vì nằm trong group đó. Xem [hướng dẫn sử dụng tag Azure](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources).

### Bằng chứng hoàn thành lab

| Điều cần chứng minh | Bằng chứng |
| --- | --- |
| Portal và shell đang nhắm cùng đích | Subscription ID và resource ID khớp |
| Đã đọc đúng group | Tên, region và tag được trả về đúng |
| Thay đổi đã được áp dụng | Lệnh đọc lại thấy `VerifiedBy=CloudShell` |
| Portal phản ánh thay đổi | Mục Tags hiển thị cùng giá trị sau Refresh |
| Phạm vi lab còn gọn | Group chỉ chứa những gì bạn chủ động tạo |

Các bằng chứng này giúp phân biệt “lệnh đã được nhập” với “trạng thái đích đã đúng”.

## 12. Làm việc với tệp và trình soạn thảo

Cloud Shell có trình soạn thảo tích hợp. Bạn có thể dùng nút Editor hoặc lệnh:

```bash
code .
```

Để mở một tệp cụ thể:

```bash
code lab-notes.txt
```

Đây là editor của Cloud Shell trong trình duyệt. Lệnh không có nghĩa sẽ mở một cửa sổ VS Code trên máy cá nhân. Xem [sử dụng Cloud Shell editor](https://learn.microsoft.com/en-us/azure/cloud-shell/use-cloud-shell-editor).

Một quy trình thực hành với tệp:

1. Kiểm tra thư mục làm việc hiện tại.
2. Tạo hoặc mở tệp cần dùng.
3. Lưu tệp trước khi thực thi hoặc tải xuống.
4. Xác minh tệp ở phạm vi lưu trữ phù hợp với chế độ phiên.
5. Tải về hoặc lưu vào kho quản lý phiên bản được phép nếu cần giữ lâu dài.

Bạn có thể dùng điều khiển upload/download của Cloud Shell để trao đổi tệp với máy cá nhân. Việc upload không tự biến tệp thành tài nguyên Azure Resource Manager.

### Kiểm tra vị trí hiện tại

Trong Bash:

```bash
pwd
ls
```

Trong PowerShell:

```powershell
Get-Location
Get-ChildItem
```

Khi dùng persistent storage, chỉ chọn thư mục `clouddrive` sau khi xác minh share đã được gắn thành công. Khi dùng ephemeral, cần xuất những tệp muốn giữ trước khi kết thúc phiên.

Nếu PowerShell đang đứng ở drive `Azure:`, đó là cách điều hướng dữ liệu tài nguyên do provider cung cấp, không phải thư mục tệp ứng dụng thông thường. Chuyển về thư mục home bằng `Set-Location ~` khi cần thao tác với tệp.

### Phân biệt dữ liệu nguồn, kết quả và thông tin nhạy cảm

Có thể lưu script và ghi chú đã loại bỏ thông tin nhạy cảm để tái sử dụng. Đối với kết quả lệnh, hãy chọn đúng các trường cần thiết thay vì xuất toàn bộ cấu hình.

Thông tin đăng nhập, token, private key, connection string và các giá trị secret cần được quản lý theo cơ chế của tổ chức. Một tệp trong home persistent hoặc lịch sử shell có thể tồn tại lâu hơn bạn dự kiến. Không coi terminal trên trình duyệt là nơi lưu bí mật mặc định.

## 13. Chi phí, thời gian phiên và giới hạn thực hành

Máy chủ phiên Cloud Shell được cung cấp miễn phí theo mô hình dịch vụ, nhưng storage persistent và các tài nguyên Azure bạn tạo vẫn có chi phí riêng. Xem phần pricing của [tổng quan Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/overview).

Cần tách ba nhóm:

| Nhóm | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| Môi trường shell | Host tạm thời cho phiên tương tác | Dùng đúng mục đích quản trị |
| Dữ liệu shell lưu lâu dài | Azure Files và storage liên quan | Biết vị trí, quyền truy cập và nhu cầu giữ dữ liệu |
| Tài nguyên được quản lý | VM, disk, database, storage ứng dụng | Kiểm tra SKU, vòng đời và chi phí ở subscription đích |

Một số tài nguyên tiếp tục có chi phí dù bạn đóng Portal hoặc Cloud Shell. Dọn dẹp cần dựa trên trạng thái thực tế của tài nguyên, không dựa trên việc cửa sổ trình duyệt đã đóng.

Cloud Shell dành cho tương tác và có timeout khi không hoạt động. Không dùng việc để terminal mở làm cơ chế bảo đảm một tác vụ chạy lâu sẽ hoàn thành. Xem [FAQ và xử lý sự cố Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/faq-troubleshooting).

Đối với thao tác Azure chạy bất đồng bộ, phiên terminal có thể mất kết nối sau khi nền tảng đã nhận yêu cầu. Khi quay lại, hãy truy vấn trạng thái tài nguyên hoặc operation trước khi gửi lại một thao tác có tác dụng phụ.

## 14. Xử lý các lỗi thường gặp

### 14.1. Không thấy subscription hoặc resource group

Đừng tạo lại ngay một group cùng tên ở subscription khác. Trước tiên kiểm tra tài khoản, tenant, bộ lọc Portal và context công cụ.

Trong Azure CLI:

```bash
az account list --output table
az account show --output json
```

Trong PowerShell/Az:

```powershell
Get-AzSubscription
Get-AzContext
```

Nếu Portal thấy tài nguyên nhưng shell không thấy, so sánh ID đầy đủ. Hai danh sách có thể đang chịu các bộ lọc hoặc context khác nhau.

### 14.2. AuthorizationFailed hoặc thao tác bị từ chối

Đọc thông báo để xác định principal, action và scope. Những nguyên nhân có thể cần xem xét gồm:

- Thiếu quyền tại phạm vi đích.
- Đang dùng nhầm danh tính hoặc tenant.
- Quyền mới được cấp chưa được phản ánh trong phiên hiện tại.
- Một thao tác khác bị chặn bởi policy, lock hoặc điều kiện quản trị tương ứng.

Các nguyên nhân này không phải cùng một lỗi. Chẳng hạn, `RequestDisallowedByPolicy` cho biết cần xem chính sách liên quan; việc tăng quyền RBAC không tự làm yêu cầu vượt qua policy.

Nếu cần nhờ người quản trị, cung cấp thông tin thao tác và scope đã xác minh, cùng thông báo lỗi đã loại bỏ secret.

### 14.3. Không khởi động được hoặc không gắn được storage

Kiểm tra lần lượt các điều kiện có liên quan đến chế độ phiên:

1. Provider `Microsoft.CloudShell` đã được đăng ký chưa?
2. Subscription có hoạt động và có thể được sử dụng không?
3. Bạn có quyền cần thiết để tạo hoặc dùng storage đã chọn không?
4. Azure Policy có chặn region, loại tài nguyên hoặc cấu hình storage không?
5. Cấu hình mạng của storage có tương thích với phương án Cloud Shell đang dùng không?
6. Trình duyệt, mạng doanh nghiệp hoặc chính sách truy cập có làm gián đoạn phiên không?

Không chọn một storage khác ngẫu nhiên chỉ để vượt qua lỗi. Cần biết storage thuộc ai và có dữ liệu gì trước khi dùng hoặc thay đổi cấu hình.

### 14.4. Lệnh đúng nhưng cú pháp bị báo lỗi

Kiểm tra shell đang chọn, cách khai báo biến, dấu nháy và tham số. Một lỗi phổ biến là dán cú pháp Bash vào PowerShell hoặc ngược lại.

Azure CLI có trợ giúp tích hợp:

```bash
az group --help
az group show --help
```

PowerShell có thể tra cứu cmdlet:

```powershell
Get-Help Get-AzResourceGroup -Examples
Get-Command Update-AzTag
```

Khi dùng Azure CLI bên trong PowerShell, đây vẫn là chương trình `az`; cách xử lý mã thoát của chương trình ngoài không giống hoàn toàn lỗi cmdlet. Không gắn `-ErrorAction Stop` vào một lệnh `az` rồi kỳ vọng nó hoạt động như cmdlet Az.

### 14.5. Không kết nối được tài nguyên dùng private endpoint

Có quyền quản lý tài nguyên chưa chứng minh có đường mạng để truy cập endpoint dữ liệu. Cloud Shell tiêu chuẩn không tự nằm trong VNet ứng dụng của bạn.

Cần kiểm tra DNS, định tuyến và thiết kế truy cập riêng được tổ chức hỗ trợ. Azure có phương án Cloud Shell tích hợp virtual network cho nhu cầu phù hợp. Không mở public access của tài nguyên chỉ để che đi một vấn đề chưa xác định về kết nối. Phân biệt lỗi mạng với lỗi phân quyền sẽ giúp chọn cách xử lý đúng.

### 14.6. Tệp biến mất sau khi mở phiên mới

Xác định phiên trước là ephemeral hay persistent, tệp nằm ở đâu và storage có còn tồn tại không. Đồng thời phân biệt tệp trong filesystem của shell với tài nguyên Azure do lệnh đã tạo.

Một script bị mất không đồng nghĩa những tài nguyên script đó tạo đã biến mất. Hãy kiểm kê subscription hoặc group đích trước khi chạy lại.

## 15. Dọn dẹp lab đúng phạm vi

Lab trong bài chỉ yêu cầu resource group và tag. Trước khi xóa, mở đúng group, kiểm tra subscription ID, resource ID cùng danh sách tài nguyên bên trong.

Nếu group đã chứa tài nguyên khác, cần xác định nguồn gốc và mục đích của chúng trước khi tiếp tục. Đặc biệt, không xóa group đang chứa storage persistent của Cloud Shell khi dữ liệu đó vẫn cần được giữ.

### Dọn bằng Azure Portal

Mở đúng group lab, chọn **Delete resource group**, đọc phạm vi xóa và hoàn thành bước xác nhận của Portal. Xóa resource group có thể kéo theo các tài nguyên bên trong; đây không phải thao tác chỉ xóa tên nhóm.

Sau khi yêu cầu hoàn thành, tải lại danh sách để xác minh group không còn. Nếu thao tác thất bại, xem chi tiết lỗi và lock liên quan thay vì mặc định mọi tài nguyên đã được dọn.

### Dọn bằng Azure CLI

Dùng các biến lab đã được xác minh trong phiên hiện tại. Đọc lại đích và nội dung trước:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query "{Name:name,Id:id,Tags:tags}" --output json
az resource list --subscription "$labSubscriptionId" --resource-group "$labResourceGroup" --query "[].{Name:name,Type:type,Id:id}" --output json
```

Chỉ khi kết quả đúng phạm vi lab và mọi tài nguyên bên trong được phép xóa, thực hiện:

```bash
az group delete --subscription "$labSubscriptionId" --name "$labResourceGroup"
```

Ví dụ giữ bước xác nhận của CLI. Khi thao tác kết thúc thành công, kiểm tra:

```bash
az group exists --subscription "$labSubscriptionId" --name "$labResourceGroup"
```

Kết quả mong đợi là `false` khi truy vấn đúng subscription và không có lỗi. Nếu kết quả hoặc lệnh có lỗi, chưa đủ bằng chứng kết luận đã dọn xong.

### Dọn bằng Azure PowerShell

Nếu đi theo nhánh Az, đọc lại group và liệt kê tài nguyên trước:

```powershell
Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop
Get-AzResource -ResourceGroupName $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop |
    Select-Object Name, ResourceType, ResourceId
```

Sau khi xác minh phạm vi xóa:

```powershell
Remove-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -Confirm -ErrorAction Stop
```

Có thể quay lại Portal và Refresh để kiểm tra kết quả. Chỉ cần chọn một cách xóa; không chạy liên tiếp cả ba cách.

Việc dọn group lab không tự dọn một storage account riêng dùng cho Cloud Shell. Những tài nguyên đó cần được giữ hoặc dọn theo quyết định về dữ liệu shell, độc lập với lab.

## 16. Từ thao tác tương tác đến quy trình có thể lặp lại

Portal hữu ích để hiểu các tùy chọn và kiểm tra kết quả. Cloud Shell giúp diễn đạt thao tác dưới dạng lệnh. Khi một quy trình được dùng lặp lại, nên chuyển các tham số rõ ràng vào script hoặc Infrastructure as Code được quản lý phiên bản.

Một chu trình thực hành tốt là:

```text
Xác định đích và quyền
→ Quan sát trạng thái ban đầu
→ Thực hiện thay đổi có phạm vi rõ ràng
→ Đọc lại trạng thái bằng API hoặc công cụ
→ Đối chiếu hành vi mong muốn
→ Ghi nhận kết quả và dọn tài nguyên lab
```

Khi chuẩn bị script, không nên lấy lịch sử terminal rồi chạy lại toàn bộ. Lịch sử có thể chứa lệnh thử sai, thao tác xóa hoặc giả định về context của một phiên cũ.

Script tái sử dụng cần có tham số đích rõ ràng, xử lý lỗi và các bước xác minh phù hợp với mức tác động. Các lệnh trong bài là nền tảng để hiểu quy trình; môi trường sản xuất còn cần kiểm soát thay đổi theo cách vận hành của tổ chức.

## 17. Tự kiểm tra mức hiểu

1. Vì sao tài nguyên hiện trên Portal nhưng `az group show` có thể trả về không tìm thấy?
2. Đổi bộ lọc subscription của Portal có thay cho `az account set` không?
3. Khi đã dùng `az account set`, vì sao vẫn cần kiểm tra `Get-AzContext` nếu chuyển sang cmdlet Az?
4. Một phiên Cloud Shell ephemeral kết thúc thì VM đã tạo từ phiên đó có tự bị xóa không?
5. Vì sao tag trên resource group không chứng minh mọi tài nguyên con đều có tag tương ứng?
6. Khi lệnh cập nhật tag thành công, bạn sẽ lấy bằng chứng trạng thái mới bằng cách nào?
7. Trước khi xóa group lab, cần kiểm tra điều gì để tránh làm mất storage persistent của Cloud Shell?

Bạn hoàn thành bài học khi có thể sử dụng Portal để nhận diện đúng tài nguyên, dùng Cloud Shell để truy vấn và thay đổi có phạm vi rõ ràng, rồi xác minh kết quả bằng định danh và trạng thái thực tế. Kỹ năng này tạo nền tảng cho các bài triển khai, giám sát, bảo vệ và kiểm soát chi phí ứng dụng Azure tiếp theo.
