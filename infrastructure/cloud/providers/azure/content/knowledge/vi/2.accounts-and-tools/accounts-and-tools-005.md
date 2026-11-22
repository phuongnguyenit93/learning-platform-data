# Quản lý Azure bằng Azure PowerShell

Azure PowerShell là bộ lệnh PowerShell dùng để đăng nhập Azure, xem và quản lý tài nguyên, triển khai hạ tầng, kiểm tra hoạt động và tự động hóa các công việc vận hành. Công cụ này phù hợp khi bạn muốn kết hợp thao tác Azure với khả năng xử lý dữ liệu, biến, vòng lặp, hàm và script của PowerShell.

Trong hệ sinh thái Microsoft Azure, bạn sẽ làm việc với tenant Microsoft Entra ID, subscription, resource group và nhiều loại tài nguyên như mạng ảo, máy ảo, tài khoản lưu trữ và dịch vụ dữ liệu. Azure PowerShell cung cấp một cách nhất quán để thao tác với các thành phần đó, nhưng quyền thực hiện vẫn phụ thuộc vào danh tính và vai trò được cấp trong Azure.

Sau bài học, bạn có thể:

- Cài đặt và kiểm tra Azure PowerShell.
- Đăng nhập bằng tài khoản phù hợp và chọn đúng tenant, subscription.
- Tra cứu resource group và tài nguyên trong phạm vi được phép.
- Tạo resource group, gắn thẻ và chuẩn bị triển khai tài nguyên.
- Dùng script để tự động hóa thao tác có kiểm soát.
- Áp dụng các nguyên tắc cơ bản về bảo mật, giám sát và chi phí khi quản lý Azure.

## 1. Azure PowerShell hoạt động như thế nào?

Azure PowerShell là tập hợp các module PowerShell. Module chính thường được cài đặt là `Az`; module này tập hợp các module theo dịch vụ, chẳng hạn:

| Module | Phạm vi thường gặp |
|---|---|
| `Az.Accounts` | Đăng nhập, tài khoản, tenant và subscription context |
| `Az.Resources` | Resource group, tài nguyên, triển khai template và thẻ |
| `Az.Compute` | Máy ảo và tài nguyên tính toán |
| `Az.Network` | Virtual network, subnet, network interface và cấu hình mạng |
| `Az.Storage` | Storage account và thao tác lưu trữ |
| `Az.Monitor` | Thông tin giám sát và metric |

Các lệnh Azure thường có dạng `Verb-AzNoun`, ví dụ `Get-AzResourceGroup`, `New-AzResourceGroup` và `Get-AzVM`. Tiền tố `Az` giúp nhận biết lệnh thuộc bộ module Azure. Các động từ PowerShell quen thuộc có ý nghĩa nhất quán: `Get` để đọc, `New` để tạo, `Set` để cập nhật, `Remove` để xóa và `Update` để cập nhật một phần tùy theo cmdlet.

Khi chạy một cmdlet, Azure PowerShell gửi yêu cầu đến API quản lý Azure hoặc API dữ liệu của dịch vụ tương ứng. Vì vậy, việc một lệnh có thể chạy hay không phụ thuộc vào nhiều yếu tố: module đã cài, kết nối đang dùng, subscription context, quyền RBAC, trạng thái tài nguyên và loại API mà lệnh gọi đến.

### Phân biệt Azure PowerShell, Azure CLI và Azure Cloud Shell

- **Azure PowerShell** cung cấp cmdlet và tích hợp sâu với ngôn ngữ PowerShell. Đây là lựa chọn thuận tiện khi bạn cần xử lý đối tượng, viết hàm hoặc kết hợp với công cụ quản trị Windows.
- **Azure CLI** cung cấp lệnh `az` và thường trả kết quả dạng JSON. Công cụ này phù hợp với nhiều script đa nền tảng và quy trình đã dùng CLI.
- **Azure Cloud Shell** là môi trường shell chạy trên Azure Portal. Cloud Shell có thể cung cấp cả Bash và PowerShell, kèm ngữ cảnh đăng nhập thuận tiện. Nó là môi trường chạy lệnh, không phải một bộ lệnh thay thế cho Azure PowerShell.

Ba công cụ có thể quản lý cùng một tài nguyên Azure. Hãy chọn công cụ phù hợp với môi trường và chuẩn của nhóm, đồng thời tránh trộn nhiều cách xác thực trong cùng một script nếu không có lý do rõ ràng.

## 2. Cài đặt và kiểm tra Azure PowerShell

Bạn có thể dùng PowerShell 7 trên Windows, macOS hoặc Linux. PowerShell 7 thường là lựa chọn phù hợp cho môi trường mới. Một số máy Windows vẫn có Windows PowerShell 5.1; hãy kiểm tra phiên bản và chính sách của môi trường trước khi cài đặt module.

Mở PowerShell và kiểm tra phiên bản:

```powershell
$PSVersionTable.PSVersion
```

Cài module `Az` cho tài khoản hiện tại:

```powershell
Install-Module -Name Az -Repository PSGallery -Scope CurrentUser
```

Nếu PowerShell hỏi xác nhận cài đặt từ PowerShell Gallery, hãy kiểm tra nguồn và xác nhận theo chính sách của tổ chức. Trên máy do doanh nghiệp quản lý, có thể cần dùng repository nội bộ hoặc nhờ quản trị viên cấu hình nguồn module được phép.

Kiểm tra module đã cài:

```powershell
Get-InstalledModule -Name Az -AllVersions
Get-Module -Name Az -ListAvailable
```

Nạp module khi cần:

```powershell
Import-Module Az
Get-Command -Module Az.Accounts
```

`Az` là meta-module gồm nhiều module con. Nếu máy chỉ cần quản lý một vài dịch vụ, tổ chức có thể chọn cài các module con cần thiết để giảm phạm vi phụ thuộc. Khi dùng module con, hãy bảo đảm module tương ứng với cmdlet đã được cài.

Để cập nhật phiên bản đã cài bằng PowerShell Gallery:

```powershell
Update-Module -Name Az
```

Trong môi trường làm việc chung, nên thống nhất phiên bản module, kiểm thử thay đổi trước khi cập nhật máy chạy tác vụ quan trọng và tuân theo quy trình quản lý phần mềm của tổ chức.

## 3. Đăng nhập vào Azure

### Đăng nhập tương tác

Trên máy làm việc cá nhân, cách đơn giản nhất là:

```powershell
Connect-AzAccount
```

PowerShell mở luồng đăng nhập của Microsoft. Đăng nhập bằng tài khoản thuộc tenant được cấp quyền truy cập subscription cần quản lý. Nếu tổ chức yêu cầu chọn tenant cụ thể, có thể chỉ định tenant ID:

```powershell
$tenantId = "00000000-0000-0000-0000-000000000000"
Connect-AzAccount -TenantId $tenantId
```

Giá trị trên chỉ là ví dụ định dạng. Hãy thay bằng tenant ID do tổ chức cung cấp. Không đưa thông tin đăng nhập hoặc token vào mã nguồn.

Trong một số môi trường không thể mở cửa sổ trình duyệt, có thể dùng đăng nhập bằng mã thiết bị:

```powershell
Connect-AzAccount -UseDeviceAuthentication
```

Lệnh sẽ hướng dẫn bạn mở trang đăng nhập và nhập mã được cung cấp. Chỉ nhập mã trong phiên đăng nhập do chính bạn khởi tạo.

### Kiểm tra danh tính và subscription

Sau khi đăng nhập, xem context hiện tại:

```powershell
Get-AzContext
```

Context cho biết tài khoản, tenant và subscription mà các cmdlet Azure sẽ sử dụng mặc định. Liệt kê các subscription mà tài khoản có thể truy cập:

```powershell
Get-AzSubscription |
    Select-Object Name, Id, TenantId, State
```

Một tài khoản có thể truy cập nhiều tenant hoặc subscription. Không nên giả định subscription đang được chọn là subscription cần thao tác.

Chọn subscription bằng ID:

```powershell
$subscriptionId = "11111111-1111-1111-1111-111111111111"
Set-AzContext -SubscriptionId $subscriptionId
```

Xác nhận lại trước khi tiếp tục:

```powershell
$context = Get-AzContext
$context | Format-List Account, Tenant, Subscription, Environment
```

Nếu cần xem các context đã lưu:

```powershell
Get-AzContext -ListAvailable
```

Một context sai có thể khiến lệnh đọc nhầm môi trường hoặc tạo tài nguyên trong subscription ngoài dự kiến. Với thao tác có ảnh hưởng đến chi phí hoặc dữ liệu, hãy kiểm tra context ngay trước khi chạy.

### Làm việc trong môi trường tự động hóa

Đối với script chạy trên máy chủ hoặc pipeline, tránh phụ thuộc vào cửa sổ đăng nhập tương tác. Ưu tiên danh tính được quản lý (managed identity), workload identity federation hoặc service principal được cấu hình theo chính sách bảo mật.

Ví dụ, trên tài nguyên Azure đã bật system-assigned managed identity:

```powershell
Connect-AzAccount -Identity
```

Với user-assigned managed identity, có thể chỉ định client ID:

```powershell
$managedIdentityClientId = "22222222-2222-2222-2222-222222222222"
Connect-AzAccount -Identity -AccountId $managedIdentityClientId
```

Service principal dùng chứng chỉ là một lựa chọn khác cho tự động hóa:

```powershell
$tenantId = "00000000-0000-0000-0000-000000000000"
$appId = "33333333-3333-3333-3333-333333333333"
$thumbprint = "CERTIFICATE_THUMBPRINT"

Connect-AzAccount `
    -ServicePrincipal `
    -TenantId $tenantId `
    -ApplicationId $appId `
    -CertificateThumbprint $thumbprint
```

Chứng chỉ phải được cài trong kho chứng chỉ mà tiến trình có thể truy cập. Service principal cần được cấp quyền phù hợp trên đúng phạm vi Azure. Bảo vệ khóa riêng, giới hạn thời hạn và quyền sử dụng chứng chỉ, đồng thời luân chuyển chứng chỉ theo quy trình của tổ chức.

Không lưu client secret, mật khẩu, access token hoặc nội dung chứng chỉ riêng trong file `.ps1`, repository Git, log pipeline hay tài liệu hướng dẫn. Nếu cần bí mật, hãy dùng kho bí mật được quản lý như Azure Key Vault và cơ chế cấp danh tính phù hợp.

## 4. Hiểu phạm vi quản lý: tenant, subscription và resource group

Các phạm vi này có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Microsoft Entra tenant | Danh bạ danh tính, ứng dụng và nhóm; hỗ trợ xác thực và quản lý danh tính |
| Subscription | Phạm vi quản lý và tính phí cho tài nguyên Azure; chứa các resource group |
| Resource group | Nhóm logic các tài nguyên có vòng đời hoặc mục đích quản lý liên quan |
| Resource | Một thành phần cụ thể như virtual network, VM, storage account hoặc database |

Azure RBAC cho phép cấp vai trò ở các phạm vi khác nhau và quyền có thể được kế thừa xuống phạm vi con. Đăng nhập thành công chỉ chứng minh danh tính đã được xác thực; điều đó không có nghĩa tài khoản có quyền tạo, sửa hoặc xóa mọi tài nguyên.

## 5. Xem và tạo resource group

Liệt kê resource group trong subscription hiện tại:

```powershell
Get-AzResourceGroup |
    Select-Object ResourceGroupName, Location, ProvisioningState
```

Xem chi tiết một resource group:

```powershell
$rgName = "rg-learning-dev"
Get-AzResourceGroup -Name $rgName
```

Tạo resource group mới:

```powershell
$rgName = "rg-learning-dev"
$location = "southeastasia"
$tags = @{
    environment = "dev"
    owner       = "platform-team"
    purpose     = "learning"
}

New-AzResourceGroup -Name $rgName -Location $location -Tag $tags
```

`Location` là vùng Azure lưu metadata của resource group. Tài nguyên bên trong có thể có quy tắc vị trí riêng; khi thiết kế kiến trúc, hãy chọn vùng được tổ chức cho phép và đáp ứng yêu cầu độ trễ, tính sẵn sàng, lưu trú dữ liệu và chi phí.

Thẻ (tag) là cặp khóa và giá trị gắn với tài nguyên hoặc resource group. Thẻ như `environment`, `owner`, `costCenter` và `application` giúp phân loại tài nguyên, lọc báo cáo và phân bổ chi phí. Thẻ ở resource group không tự động bảo đảm mọi tài nguyên con đều có cùng thẻ; hãy kiểm tra chính sách kế thừa hoặc cơ chế gắn thẻ của tổ chức.

Để tránh tạo lặp resource group trong script, có thể kiểm tra trước:

```powershell
$rgName = "rg-learning-dev"
$location = "southeastasia"
$rg = Get-AzResourceGroup -Name $rgName -ErrorAction SilentlyContinue

if ($null -eq $rg) {
    New-AzResourceGroup -Name $rgName -Location $location
}
else {
    Write-Output "Resource group da ton tai: $rgName"
}
```

Đây là một ví dụ về thao tác có thể chạy lại an toàn hơn: script kiểm tra trạng thái hiện tại trước khi tạo. Với tài nguyên phức tạp, cần thiết kế từng bước để có thể chạy lặp mà không tạo bản sao hoặc vô tình ghi đè cấu hình.

## 6. Tra cứu tài nguyên Azure

Liệt kê tài nguyên trong resource group:

```powershell
Get-AzResource -ResourceGroupName $rgName |
    Sort-Object ResourceType, Name |
    Select-Object Name, ResourceType, Location, ResourceGroupName
```

Lọc theo loại tài nguyên, ví dụ storage account:

```powershell
Get-AzResource `
    -ResourceGroupName $rgName `
    -ResourceType "Microsoft.Storage/storageAccounts"
```

Các cmdlet chuyên biệt thường trả về đối tượng có thuộc tính và phương thức phù hợp hơn cho từng dịch vụ:

```powershell
# Máy ảo trong resource group
Get-AzVM -ResourceGroupName $rgName

# Virtual network trong resource group
Get-AzVirtualNetwork -ResourceGroupName $rgName

# Storage account trong resource group
Get-AzStorageAccount -ResourceGroupName $rgName
```

Bạn có thể dùng pipeline PowerShell để lọc và trình bày kết quả:

```powershell
Get-AzResource -ResourceGroupName $rgName |
    Where-Object ResourceType -eq "Microsoft.Network/virtualNetworks" |
    Select-Object Name, Location, ResourceId
```

Khi cần truy vấn tài nguyên trên nhiều subscription hoặc lọc một lượng lớn tài nguyên, Azure Resource Graph là công cụ phù hợp. Cài module nếu môi trường chưa có:

```powershell
Install-Module -Name Az.ResourceGraph -Scope CurrentUser
```

Ví dụ truy vấn tên, loại và vùng của một số tài nguyên:

```powershell
Search-AzGraph -Query @"
Resources
| project name, type, location, resourceGroup, subscriptionId
| limit 20
"@
```

Kết quả truy vấn chỉ bao gồm tài nguyên trong phạm vi mà danh tính hiện tại có thể đọc. Nếu thiếu kết quả, hãy kiểm tra subscription context, quyền đọc và phạm vi truy vấn.

## 7. Triển khai hạ tầng bằng Azure PowerShell

Azure PowerShell có thể gọi các cmdlet tạo tài nguyên riêng lẻ hoặc triển khai hạ tầng khai báo bằng ARM template và Bicep. Với hệ thống có nhiều tài nguyên liên quan, nên mô tả hạ tầng bằng template để có thể xem xét, quản lý phiên bản và triển khai lặp lại.

Ví dụ triển khai một Bicep file vào resource group đã tạo:

```powershell
$rgName = "rg-learning-dev"
$templateFile = ".\main.bicep"
$parameterFile = ".\dev.parameters.json"

New-AzResourceGroupDeployment `
    -ResourceGroupName $rgName `
    -TemplateFile $templateFile `
    -TemplateParameterFile $parameterFile `
    -WhatIf
```

`-WhatIf` hiển thị các thay đổi dự kiến để bạn xem xét trước khi triển khai. Sau khi kiểm tra template, tham số, subscription context và quyền truy cập, chạy lại lệnh và bỏ `-WhatIf` để thực hiện triển khai:

```powershell
New-AzResourceGroupDeployment `
    -ResourceGroupName $rgName `
    -TemplateFile $templateFile `
    -TemplateParameterFile $parameterFile
```

`-WhatIf` giúp phát hiện thay đổi ngoài dự kiến nhưng không thay thế việc kiểm tra nội dung template, dữ liệu đầu vào, quyền và tác động vận hành. Một số loại thao tác hoặc nhà cung cấp tài nguyên có thể thể hiện kết quả dự kiến ở mức độ khác nhau.

Nếu triển khai ở phạm vi subscription, Azure PowerShell cũng có cmdlet triển khai subscription như `New-AzDeployment`. Hãy chọn đúng phạm vi triển khai vì resource group deployment và subscription deployment có mục đích khác nhau.

## 8. Quản lý các dịch vụ thường gặp

Sau khi chọn context và resource group, bạn có thể dùng module theo dịch vụ để xem trạng thái và cấu hình.

### Tính toán

```powershell
Get-AzVM -ResourceGroupName $rgName |
    Select-Object Name, Location, HardwareProfile, ProvisioningState
```

Cmdlet chuyên biệt cho VM giúp xem cấu hình máy ảo. Khi thay đổi kích thước, trạng thái chạy hoặc đĩa, hãy kiểm tra tác động đến ứng dụng, thời gian gián đoạn và chi phí trước khi thực hiện.

### Mạng

```powershell
Get-AzVirtualNetwork -ResourceGroupName $rgName |
    Select-Object Name, Location, AddressSpace, Subnets
```

Khi quản lý mạng ảo, cần hiểu quan hệ giữa virtual network, subnet, network security group, route table, public IP và kết nối mạng. Thay đổi dải địa chỉ hoặc quy tắc bảo mật có thể ảnh hưởng đến kết nối của nhiều workload.

### Lưu trữ

```powershell
Get-AzStorageAccount -ResourceGroupName $rgName |
    Select-Object StorageAccountName, Location, Sku, Kind, ProvisioningState
```

Storage account là tài nguyên quản lý ở control plane. Các thao tác với blob, file, queue hoặc table là thao tác dữ liệu (data plane) và có thể cần quyền riêng. Vì vậy, có quyền xem storage account không đồng nghĩa có quyền đọc hoặc sửa dữ liệu bên trong.

### Dữ liệu và ứng dụng

Với dịch vụ cơ sở dữ liệu hoặc nền tảng ứng dụng, hãy dùng module Az tương ứng và kiểm tra tài liệu của cmdlet theo phiên bản đang cài. Phân biệt quyền quản lý cấu hình tài nguyên với quyền truy cập dữ liệu, thông tin kết nối và quyền của ứng dụng. Không đưa chuỗi kết nối hoặc thông tin xác thực vào đầu ra lệnh hay log.

## 9. Tự động hóa script có kiểm soát

Một script quản lý Azure nên làm rõ bốn điều: danh tính nào đang chạy, context nào được chọn, tài nguyên nào sẽ bị tác động và kết quả nào cần xác minh.

Ví dụ script kiểm tra kết nối, xác nhận subscription rồi liệt kê tài nguyên của một resource group:

```powershell
$ErrorActionPreference = "Stop"

$subscriptionId = "11111111-1111-1111-1111-111111111111"
$rgName = "rg-learning-dev"

try {
    $context = Get-AzContext
    if ($null -eq $context) {
        throw "Chua co Azure context. Hay dang nhap truoc khi chay script."
    }

    Set-AzContext -SubscriptionId $subscriptionId | Out-Null

    $context = Get-AzContext
    if ($context.Subscription.Id -ne $subscriptionId) {
        throw "Subscription context khong dung voi gia tri du kien."
    }

    $resourceGroup = Get-AzResourceGroup -Name $rgName
    Get-AzResource -ResourceGroupName $resourceGroup.ResourceGroupName |
        Select-Object Name, ResourceType, Location
}
catch {
    Write-Error "Khong the hoan tat thao tac Azure: $($_.Exception.Message)"
    throw
}
```

Các điểm cần lưu ý:

- `$ErrorActionPreference = "Stop"` giúp lỗi không kết thúc mặc định của nhiều cmdlet được chuyển thành lỗi có thể xử lý trong `catch`.
- Script chọn subscription rõ ràng rồi kiểm tra lại context trước khi truy cập resource group.
- `try/catch` giúp báo lỗi tại một điểm tập trung; không nên bắt lỗi rồi tiếp tục như thể thao tác đã thành công.
- Giá trị ID trong ví dụ phải được thay bằng ID của môi trường được phép quản lý.

Với script chạy định kỳ, hãy ghi log đủ để truy vết thời điểm, danh tính thực thi, subscription, tài nguyên bị tác động và kết quả. Không ghi token, mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm vào log. Đặt giới hạn thời gian, xử lý lỗi tạm thời có kiểm soát và tránh chạy đồng thời nhiều phiên có thể sửa cùng một tài nguyên.

## 10. Bảo mật và quản trị

Azure PowerShell sử dụng danh tính và quyền của phiên đăng nhập hiện tại. Áp dụng các nguyên tắc sau:

1. **Quyền tối thiểu:** cấp vai trò Azure RBAC vừa đủ cho công việc, tại phạm vi nhỏ nhất phù hợp. Tránh dùng quyền Owner hoặc Contributor rộng cho script chỉ cần đọc dữ liệu.
2. **Danh tính riêng cho tự động hóa:** dùng managed identity hoặc service principal riêng cho từng workload; không dùng tài khoản cá nhân để chạy tác vụ nền lâu dài.
3. **Xác thực mạnh:** tuân theo chính sách MFA, Conditional Access và phương thức xác thực của tổ chức. Với tự động hóa, ưu tiên cơ chế không cần lưu mật khẩu lâu dài.
4. **Kiểm tra context:** xác nhận tenant, subscription và cloud environment trước thao tác tạo, cập nhật hoặc xóa.
5. **Bảo vệ dữ liệu xác thực:** không chia sẻ profile, token cache hoặc chứng chỉ riêng giữa người dùng; quản lý vòng đời bí mật trong kho được phê duyệt.
6. **Theo dõi thay đổi:** dùng Activity Log, Azure Monitor và quy trình kiểm soát thay đổi để xác định ai đã làm gì, ở đâu và khi nào.

Nếu một cmdlet báo lỗi `AuthorizationFailed` hoặc `Forbidden`, hãy kiểm tra danh tính trong `Get-AzContext`, phạm vi tài nguyên, vai trò RBAC và thời gian lan truyền thay đổi quyền. Đăng nhập lại không tự cấp thêm quyền.

## 11. Giám sát và kiểm soát chi phí

Azure PowerShell hỗ trợ truy vấn tài nguyên và thông tin vận hành; Azure Monitor và Cost Management cung cấp dữ liệu chuyên biệt cho giám sát và chi phí.

Ví dụ đọc Activity Log của resource group trong 24 giờ gần nhất:

```powershell
$endTime = Get-Date
$startTime = $endTime.AddHours(-24)

Get-AzActivityLog `
    -ResourceGroupName $rgName `
    -StartTime $startTime `
    -EndTime $endTime
```

Activity Log giúp xem các sự kiện quản lý như tạo, cập nhật hoặc xóa tài nguyên. Để theo dõi hiệu năng ứng dụng, hãy cấu hình metric, log, cảnh báo và workspace phù hợp trong Azure Monitor; việc chỉ liệt kê tài nguyên không cho biết ứng dụng đang hoạt động tốt hay không.

Để kiểm soát chi phí:

- Gắn thẻ tài nguyên theo môi trường, nhóm sở hữu, ứng dụng và trung tâm chi phí.
- Kiểm tra SKU, kích thước, vùng triển khai và số lượng tài nguyên trước khi tạo.
- Theo dõi mức sử dụng và chi phí trong Cost Management; cấu hình ngân sách và cảnh báo theo quy trình của tổ chức.
- Tắt hoặc thu hồi tài nguyên thử nghiệm khi không còn cần thiết, sau khi xác nhận không có dữ liệu hoặc phụ thuộc cần giữ lại.
- Định kỳ rà soát tài nguyên không còn được sử dụng, dung lượng lưu trữ, snapshot, IP công cộng và các dịch vụ có tính phí liên tục.

Quyền đọc tài nguyên không nhất thiết bao gồm quyền xem chi tiết chi phí. Nếu không truy cập được dữ liệu Cost Management, hãy yêu cầu vai trò phù hợp ở phạm vi subscription hoặc billing account theo chính sách của tổ chức.

## 12. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `Connect-AzAccount` không chạy | Module thiếu hoặc lỗi phiên bản; trình duyệt hoặc phương thức xác thực không phù hợp | Kiểm tra `$PSVersionTable`, `Get-Module -ListAvailable Az.Accounts` và thử phương thức đăng nhập được tổ chức cho phép |
| Không thấy subscription | Đăng nhập sai tenant hoặc tài khoản chưa được cấp quyền | Xem `Get-AzContext` và `Get-AzSubscription`; xác nhận tenant ID với quản trị viên |
| `ResourceGroupNotFound` | Sai tên, sai subscription context hoặc resource group đã bị xóa | Kiểm tra `Get-AzContext` rồi liệt kê bằng `Get-AzResourceGroup` |
| `AuthorizationFailed` | Thiếu vai trò hoặc quyền ở phạm vi cần thao tác | Xác nhận principal, scope và role assignment; chờ quyền mới được áp dụng nếu vừa thay đổi |
| Cmdlet không được nhận diện | Module tương ứng chưa cài hoặc chưa nạp | Dùng `Get-Command <TenCmdlet> -All` và kiểm tra module Az cần thiết |
| Triển khai thất bại | Template, tham số, quota, vùng hoặc nhà cung cấp tài nguyên có vấn đề | Đọc chi tiết deployment operation và lỗi của resource provider; kiểm tra quota và tham số đầu vào |
| Đọc được tài nguyên nhưng không đọc được dữ liệu | Có quyền control plane nhưng thiếu quyền data plane | Kiểm tra cơ chế xác thực và vai trò dữ liệu trên dịch vụ cụ thể |

Khi xử lý lỗi, lưu lại thông báo lỗi, thời điểm, cmdlet, tenant, subscription và resource ID liên quan. Loại bỏ token, mật khẩu và thông tin nhạy cảm trước khi chia sẻ log để nhờ hỗ trợ.

## 13. Xóa tài nguyên và dọn dẹp môi trường thử nghiệm

Xóa một resource group sẽ xóa các tài nguyên nằm trong group đó và có thể gây mất dữ liệu hoặc gián đoạn dịch vụ. Trước khi xóa, cần xác nhận môi trường, chủ sở hữu, phụ thuộc, chính sách lưu giữ và bản sao lưu.

Có thể xem trước tác động bằng `-WhatIf`:

```powershell
Remove-AzResourceGroup -Name $rgName -WhatIf
```

Chỉ sau khi đã xác minh đúng resource group và được phép thực hiện, mới chạy lệnh xóa thực tế:

```powershell
Remove-AzResourceGroup -Name $rgName -Force
```

`-Force` bỏ qua lời nhắc xác nhận tương tác; nó không làm thao tác an toàn hơn và không thay thế bước kiểm tra. Không đưa lệnh xóa vào script tự động chạy trên môi trường quan trọng nếu chưa có cơ chế phê duyệt và bảo vệ phù hợp.

## 14. Bài thực hành

Thực hiện bài tập trong subscription thử nghiệm mà bạn được phép sử dụng:

1. Mở PowerShell và kiểm tra phiên bản.
2. Cài hoặc xác nhận module `Az` đã có.
3. Đăng nhập Azure, liệt kê subscription và chọn đúng subscription thử nghiệm.
4. Tạo resource group `rg-learning-dev` tại vùng được tổ chức cho phép, gắn các thẻ `environment=dev` và `owner=learning`.
5. Dùng `Get-AzResourceGroup` để kiểm tra resource group và `Get-AzResource` để liệt kê tài nguyên trong group.
6. Chạy `Get-AzContext` một lần nữa và ghi lại tenant cùng subscription đang được chọn.
7. Dùng `-WhatIf` để xem trước thao tác dọn dẹp. Chỉ xóa resource group nếu đó là môi trường thử nghiệm do bạn tạo và không còn dữ liệu cần giữ.

Ví dụ lệnh kiểm tra cuối bài:

```powershell
Get-AzContext
Get-AzResourceGroup -Name "rg-learning-dev"
Get-AzResource -ResourceGroupName "rg-learning-dev"
```

Bạn đã hoàn thành bài thực hành khi có thể giải thích danh tính nào đang đăng nhập, context đang trỏ đến subscription nào, resource group thuộc vùng nào, các thẻ dùng để làm gì và cách kiểm tra tác động trước khi xóa tài nguyên.

## 15. Ghi nhớ

Azure PowerShell giúp quản lý Azure bằng các cmdlet có thể kết hợp thành script và quy trình tự động hóa. Để sử dụng an toàn, hãy cài module phù hợp, xác thực bằng danh tính được phê duyệt, chọn và kiểm tra tenant cùng subscription context, hiểu phạm vi RBAC, dùng template cho hạ tầng có nhiều thành phần và kiểm tra trước các thay đổi quan trọng. Kết hợp việc tra cứu tài nguyên với Azure Monitor và Cost Management để quản lý cả trạng thái vận hành lẫn chi phí của kiến trúc.
