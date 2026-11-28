# Remote PowerShell control — Kiểm soát PowerShell từ xa trong Windows PAM

## 1. Mục tiêu và phạm vi

PowerShell Remoting giúp quản trị viên vận hành Windows từ xa bằng lệnh và đối tượng có cấu trúc. Trong hệ thống quản lý truy cập đặc quyền, câu hỏi cần trả lời không chỉ là “máy này có kết nối được không”, mà còn là: ai được kết nối, từ thiết bị nào, vào endpoint nào, được làm việc gì, trong bao lâu và bằng chứng nào chứng minh điều đã xảy ra.

Bài học thuộc chương **Windows PAM**, trong phạm vi quản lý đặc quyền cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Ta kết hợp kiểm kê đường quản trị, least privilege, quyền tạm thời JIT, giới hạn thao tác JEA, quản lý danh tính thực thi, giám sát phiên và thu hồi truy cập. Đề bài trực tiếp là **Remote PowerShell control**: thiết kế và kiểm chứng đường điều khiển từ xa.

Sau bài học, người học có thể:

- Phân biệt transport, xác thực, quyền vào endpoint và quyền thực thi trên tài nguyên.
- Thiết kế đường quản trị đi qua máy trạm quản trị hoặc broker được kiểm soát.
- Dùng endpoint JEA để giới hạn thao tác mà không cấp shell quản trị tổng quát.
- Nhận diện rủi ro second hop, quyền tồn tại sau thời hạn JIT và đường truy cập thay thế.
- Xây dựng kiểm thử cho phép, từ chối, thu hồi và thu thập bằng chứng.

Các ví dụ triển khai endpoint sử dụng **Windows PowerShell 5.1 x64 trên Windows member server trong miền AD**. Máy chủ ví dụ là `app01.corp.example`; miền minh họa là `CORP`. Đây không phải cấu hình dành cho domain controller. PowerShell 7 và remoting qua SSH cần được kiểm kê, thiết kế và kiểm thử riêng theo engine và transport thực tế.

## 2. Bốn lớp quyết định một phiên có được phép hay không

Một kết nối thành công trải qua nhiều quyết định độc lập:

| Lớp | Câu hỏi cần trả lời | Ví dụ kiểm soát | Lỗi thiết kế thường gặp |
| --- | --- | --- | --- |
| Đường mạng và transport | Nguồn nào đến được dịch vụ nào? | Firewall, phân đoạn mạng, listener, TLS | Mọi workstation đều tới được cổng quản trị |
| Xác thực | Người gọi và máy đích là ai? | Kerberos, chứng thư máy chủ, danh tính cá nhân | Dùng IP rồi chấp nhận phương thức ngoài dự kiến |
| Quyền vào endpoint | Danh tính này có được mở cấu hình phiên này không? | ACL session configuration, nhóm được phê duyệt | Chỉ kiểm tra thành viên local administrator |
| Quyền thao tác và tài nguyên | Được gọi lệnh nào, trên đối tượng nào? | JEA, kiểm tra tham số, ACL tài nguyên | Có JEA nhưng được chạy script tùy ý |

HTTPS không thay thế việc giới hạn lệnh. ACL endpoint cũng không tự hạn chế thao tác nếu endpoint cung cấp shell đầy đủ. Ngược lại, một role JEA chặt vẫn chưa đủ nếu người đó có đường vào endpoint tổng quát bằng đặc quyền khác.

Cần phân biệt hai danh tính:

- **Connecting user**: người hoặc workload khởi tạo kết nối.
- **Run-as identity**: tài khoản mà tiến trình thực sự dùng để thao tác trên máy đích.

Nếu endpoint chạy dưới virtual account hoặc gMSA, hai danh tính có thể khác nhau. Kiểm toán phải nối được người khởi tạo với danh tính thực thi; chỉ nhìn tài khoản xuất hiện trong một sự kiện ứng dụng là chưa đủ.

## 3. Kiến trúc đường quản trị có kiểm soát

Xét tình huống bộ phận vận hành cần xem tình trạng dịch vụ trên máy ứng dụng. Một số thao tác khắc phục có thể được phê duyệt riêng, nhưng không có nhu cầu trở thành Domain Admin.

~~~mermaid
flowchart LR
    U["Người vận hành có danh tính riêng"] --> P["PAM: yêu cầu, phê duyệt, MFA, thời hạn"]
    P --> A["PAW hoặc broker quản trị"]
    A -->|"Đúng nguồn, đích, transport"| W["WinRM trên máy ứng dụng"]
    W --> E["Endpoint JEA theo nhiệm vụ"]
    E --> R["Tài nguyên được cho phép"]
    P --> L["Kho bằng chứng tập trung"]
    W --> L
    E --> L
    R --> L
~~~

PAW là máy trạm dành cho quản trị, với mức bảo vệ và cách sử dụng tách khỏi thiết bị làm việc thông thường. Broker là điểm trung gian thực thi hoặc chuyển tiếp tác vụ theo chính sách. Cần biết broker có thực sự chấm dứt và tạo lại phiên, hay chỉ chuyển tiếp lưu lượng mạng.

Với một thiết kế minh họa:

1. Người vận hành yêu cầu quyền `RemoteRead` trên `app01`, gắn ticket và thời hạn 20 phút.
2. PAM xác minh người dùng, thiết bị và người phê duyệt; sau đó cấp điều kiện truy cập tạm thời.
3. Chỉ PAW hoặc broker được phép tới listener quản trị của máy đích.
4. Phiên phải chọn endpoint `PAM.RemoteRead`.
5. Endpoint chỉ cung cấp thao tác đọc trạng thái dịch vụ xác định trước.
6. Khi hết hạn, hệ thống đóng quyền tạo phiên mới và xử lý phiên đang tồn tại.
7. Ticket, quyết định cấp quyền, phiên và kết quả được đối chiếu trong kho bằng chứng.

**MFA ở cổng PAM không tự bảo vệ mọi kết nối WinRM trực tiếp.** Nếu người dùng vẫn có credential hoặc token đủ quyền, cùng đường mạng khác tới máy đích, họ có thể tạo đường truy cập nằm ngoài cổng đó. Vì vậy phải kiểm chứng đường mạng và quyền trên máy đích, không chỉ giao diện yêu cầu quyền.

## 4. Chọn transport và xác thực

### 4.1. WinRM, HTTP và HTTPS

PowerShell Remoting qua WinRM thường dùng HTTP cổng 5985 hoặc HTTPS cổng 5986. Trong môi trường miền, Kerberos có thể cung cấp xác thực hai chiều và mã hóa thông điệp ngay cả khi transport là HTTP. Vì vậy không được kết luận mọi phiên WinRM qua HTTP đều truyền nội dung lệnh dưới dạng rõ. HTTPS bổ sung TLS ở lớp transport; Basic không tự cung cấp mã hóa. Các đặc tính này được Microsoft mô tả trong [Security considerations for PowerShell Remoting using WinRM](https://learn.microsoft.com/en-us/powershell/scripting/learn/remoting/winrmsecurity).

Trong thiết kế của bài, ta chọn **HTTPS và Kerberos** cho đường quản trị miền. Đây là lựa chọn kiến trúc minh họa nhằm thống nhất kiểm tra TLS và danh tính miền, không phải khẳng định Kerberos bắt buộc chạy trên HTTPS.

Baseline cần xác định:

- Tên DNS dùng để kết nối và SPN phù hợp với đường xác thực Kerberos.
- Chứng thư máy chủ có SAN phù hợp, private key được bảo vệ, chuỗi tin cậy hợp lệ và vòng đời gia hạn rõ ràng.
- Danh sách nguồn được truy cập và nhóm máy đích tương ứng.
- Listener nào được phép tồn tại; có đường HTTP hoặc listener khác cần đóng theo chính sách hay không.
- Cơ chế xác thực nào được phép trên client và server; tác động tới công cụ vận hành đang sử dụng.

Không đưa `-SkipCACheck`, `-SkipCNCheck` hoặc bỏ qua kiểm tra chứng thư vào cấu hình vận hành để xử lý lỗi triển khai PKI. Khi chứng thư sai tên hoặc hết hạn, cần khắc phục nguyên nhân.

### 4.2. Kerberos, Negotiate và TrustedHosts

Trong đường quản trị miền, kết nối bằng FQDN và yêu cầu `-Authentication Kerberos` giúp kiểm tra trực tiếp thiết kế Kerberos. Nếu gặp lỗi, kiểm tra DNS, thời gian, khả năng liên hệ domain controller, quan hệ tin cậy và SPN trước khi đổi phương thức xác thực.

`Negotiate` là cơ chế thương lượng, không phải bằng chứng Kerberos chắc chắn đã được dùng. Tên IP hoặc tình huống workgroup thường không đáp ứng các điều kiện Kerberos thông thường. Khi có ngoại lệ workgroup hoặc chéo miền, phải mô tả rõ cách xác minh máy đích và quản lý danh tính cho ngoại lệ.

`TrustedHosts` không phải firewall, danh sách người dùng được phép hay cơ chế cấp quyền endpoint. Thêm một máy vào danh sách cũng không biến nó thành máy đã được chứng minh tin cậy bằng Kerberos. Cấu hình wildcard làm phạm vi chấp nhận của client rộng hơn và không phải biện pháp sửa lỗi mặc định.

Nếu yêu cầu là “chỉ Kerberos”, việc ghi `-Authentication Kerberos` trong script mẫu chưa chứng minh toàn hệ thống đã ngăn mọi phương thức khác. Phải kiểm tra cả chính sách server, client được quản lý và các công cụ truy cập khác.

### 4.3. Đừng gộp WinRM với PowerShell qua SSH

PowerShell qua SSH tạo host trên máy đích bằng SSH subsystem. Nó có đường xác thực, cấu hình daemon và vòng đời khóa riêng. Theo [PowerShell remoting over SSH](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/ssh-remoting-in-powershell), mô hình này không cung cấp cùng cơ chế endpoint configuration và JEA của WinRM.

Do đó endpoint JEA `PAM.RemoteRead` không tự ràng buộc một người đang vào máy bằng SSH shell. Bản kiểm kê phải bao gồm WinRM, SSH, RDP, công cụ quản trị ứng dụng, agent tự động hóa và các đường quản trị khác có mặt trong hệ thống.

## 5. Giới hạn endpoint và danh tính thực thi

### 5.1. Đặt quyền theo nhiệm vụ

Thay vì cấp “remote admin”, hãy diễn đạt quyền dưới dạng:

> Trong cửa sổ được phê duyệt, từ PAW được quản lý, người vận hành được gọi endpoint RemoteRead trên nhóm máy APP-LAB và chỉ đọc trạng thái dịch vụ W32Time.

Từ mô tả này mới suy ra nhóm truy cập, endpoint, role capability và kiểm thử. Không bắt đầu bằng nhóm quản trị rộng rồi tìm cách giảm quyền bằng hướng dẫn sử dụng.

| Nhiệm vụ | Endpoint minh họa | Thao tác công bố | Phạm vi | Điều kiện |
| --- | --- | --- | --- | --- |
| Chẩn đoán cơ bản | PAM.RemoteRead | Get-PamServiceState | Dịch vụ W32Time trên máy được giao | Ticket, cửa sổ ngắn |
| Khắc phục dịch vụ | PAM.AppRecovery | Hàm khắc phục chuyên biệt | Dịch vụ ứng dụng cụ thể | Phê duyệt thay đổi, kiểm tra sức khỏe |
| Điều tra sự cố | Endpoint điều tra riêng | Bộ thao tác đọc đã rà soát | Máy trong sự cố | Incident ID, kiểm soát dữ liệu |
| Khẩn cấp | Đường break-glass riêng | Theo kịch bản khẩn cấp | Đích cụ thể | Cảnh báo, rà soát sau sử dụng |

Các endpoint ngoài lab chỉ là ví dụ thiết kế. Chúng không tự tồn tại sau khi triển khai endpoint đọc trong phần thực hành.

### 5.2. Chọn run-as identity có chủ đích

Virtual account trong JEA là danh tính tạm thời cho phiên. Mặc định, virtual account trên member server có thể thuộc Administrators; trên domain controller có đặc điểm đặc quyền khác và rủi ro lớn hơn. Có thể dùng `RunAsVirtualAccountGroups` để chỉ định nhóm phù hợp thay cho nhóm quản trị mặc định. gMSA phù hợp với một số tác vụ cần danh tính mạng nhưng làm tăng yêu cầu đối chiếu hành động với người khởi tạo. Xem [JEA Security Considerations](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/jea/security-considerations).

Với thao tác chỉ đọc trạng thái dịch vụ, không có lý do mặc định phải cấp local administrator cho runtime. Lab dùng một nhóm local riêng, không được lồng vào nhóm quản trị. Quyền truy vấn dịch vụ của nhóm đó vẫn phải kiểm tra trên baseline Windows thực tế.

Nếu chuyển sang tác vụ khởi động lại dịch vụ, hãy ủy quyền quyền tối thiểu trên đúng service object và rà soát khả năng thay đổi cấu hình, executable, thư mục và dependency của dịch vụ. Được điều khiển một dịch vụ nhưng đồng thời được sửa binary của nó có thể tạo đường thực thi mã mạnh hơn mục tiêu ban đầu.

### 5.3. JEA cần hạn chế cả cú pháp lẫn ngữ nghĩa

Một role cho gọi `Get-Service` nhưng không bắt buộc chỉ định tên có thể vẫn cho phép liệt kê ngoài phạm vi mong muốn. Một wrapper nhận tham số `Name` nhưng bên trong ghép chuỗi rồi gọi `Invoke-Expression` lại tạo đường thực thi khác.

Mẫu phù hợp hơn là hàm có tham số bắt buộc, giá trị cho phép rõ ràng và lời gọi cmdlet trực tiếp. Không công bố shell bên ngoài, trình thông dịch hoặc hàm chạy script tùy ý cho role nghiệp vụ. Microsoft trình bày cách giới hạn cmdlet, tham số và wrapper trong [JEA Role Capabilities](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/jea/role-capabilities).

Ngoài định nghĩa role, phải bảo vệ mã phía sau endpoint. Người sử dụng endpoint không được sửa module, role capability, session configuration hoặc dependency mà runtime sẽ nạp. Đổi một module có quyền ghi rộng có thể thay đổi hành vi endpoint mà không cần chỉnh ACL truy cập.

## 6. Lab: endpoint chỉ đọc trạng thái một dịch vụ

### 6.1. Điều kiện thực hành

Dùng member server lab với Windows PowerShell 5.1 x64 và dịch vụ `W32Time` tồn tại. Nhóm AD `CORP\PAM_RemoteRead_Eligible` đã được tạo bởi quy trình quản lý danh tính. Người thử nghiệm không phải local administrator và chỉ được kích hoạt thành viên nhóm theo cửa sổ lab.

Các điều kiện phải được chuẩn bị trước:

- WinRM HTTPS có listener và chứng thư phù hợp.
- PAW phân giải được `app01.corp.example` và dùng được Kerberos tới máy đích.
- Firewall chỉ mở đường cần thiết từ PAW hoặc broker.
- Có đường quản trị phục hồi được kiểm thử trước khi thay đổi endpoint.
- Có collector nhận log và người kiểm tra việc chuyển log.
- Chưa có module, role hoặc endpoint trùng tên ví dụ.

Các khối lệnh là hướng dẫn triển khai trên máy lab, không phải tập lệnh cấu hình WinRM toàn diện. Không chạy chúng trên domain controller. Đăng ký hoặc thay đổi endpoint có thể tác động dịch vụ WinRM và phiên đang dùng; thực hiện trong cửa sổ bảo trì phù hợp.

### 6.2. Kiểm tra trạng thái hiện tại

Chạy trong Windows PowerShell 5.1 x64 với quyền quản trị trên máy lab:

~~~powershell
$PSVersionTable.PSVersion

Get-Service -Name WinRM, W32Time

Get-ChildItem -Path WSMan:\localhost\Listener

Get-PSSessionConfiguration | Select-Object Name, Permission

Get-Item -Path WSMan:\localhost\Service\AllowUnencrypted

Get-ChildItem -Path WSMan:\localhost\Service\Auth
~~~

Đây là kiểm tra cấu hình và điều kiện ban đầu. Chỉ thấy listener chưa chứng minh chứng thư được client chấp nhận; chỉ thấy endpoint chưa chứng minh người dùng thực tế bị giới hạn đúng. Ghi lại kết quả để so sánh sau triển khai.

Không bật lại toàn bộ remoting như thao tác sửa lỗi lặp đi lặp lại: việc đó có thể thay đổi trạng thái endpoint hoặc rule ngoài mục tiêu dự kiến.

### 6.3. Tạo runtime group và vị trí lưu cấu hình

~~~powershell
$runtimeGroup = 'PAM_RemoteReadRuntime'
$moduleRoot = Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules\CorpPamRemoteRead'
$roleRoot = Join-Path $moduleRoot 'RoleCapabilities'
$configRoot = 'C:\ProgramData\PAM\RemoteRead'
$transcriptRoot = Join-Path $configRoot 'Transcripts'

if (Get-LocalGroup -Name $runtimeGroup -ErrorAction SilentlyContinue) {
    throw 'Runtime group already exists; review its ownership and rights first.'
}

if (Test-Path -LiteralPath $moduleRoot) {
    throw 'Module path already exists; do not overwrite an existing deployment.'
}

if (Get-PSSessionConfiguration -Name 'PAM.RemoteRead' -ErrorAction SilentlyContinue) {
    throw 'Endpoint already exists; use the approved update procedure.'
}

New-LocalGroup -Name $runtimeGroup -Description 'Runtime group for the PAM RemoteRead lab'

New-Item -ItemType Directory -Path $roleRoot -Force | Out-Null
New-Item -ItemType Directory -Path $configRoot -Force | Out-Null
New-Item -ItemType Directory -Path $transcriptRoot -Force | Out-Null

$manifestParameters = @{
    Path = Join-Path $moduleRoot 'CorpPamRemoteRead.psd1'
    ModuleVersion = '1.0.0'
    Description = 'Constrained remote service-state queries'
}
New-ModuleManifest @manifestParameters
~~~

Trước bước tiếp theo, cấu hình và kiểm tra NTFS ACL:

| Vị trí | Chủ thể quản lý | Quyền runtime cần có |
| --- | --- | --- |
| Module và RoleCapabilities | SYSTEM, quản trị viên triển khai được chỉ định | Đọc, thực thi; không sửa |
| File cấu hình endpoint | Nhóm triển khai được chỉ định | Không có quyền sửa cấu hình |
| Thư mục transcript | Nhóm quản lý log, runtime theo chính sách | Đủ tạo và ghi transcript |
| Kho bằng chứng tập trung | Bộ phận quản lý bằng chứng độc lập | Runtime không được sửa bằng chứng đã nhận |

Trong lab biệt lập, có thể cấp Modify cho runtime group trên **đúng thư mục transcript** để kiểm chứng luồng ghi:

~~~powershell
$runtimeAccount = '{0}\{1}' -f $env:COMPUTERNAME, $runtimeGroup
$runtimeGrant = '{0}:(OI)(CI)M' -f $runtimeAccount

& icacls.exe $transcriptRoot /grant $runtimeGrant
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to grant transcript write permissions.'
}

Get-Acl -LiteralPath $moduleRoot | Format-List
Get-Acl -LiteralPath $transcriptRoot | Format-List
~~~

Modify ở đây là lựa chọn đơn giản cho lab, cho phép sửa hoặc xóa nội dung trong thư mục đó. **Không xem transcript local là bằng chứng bất biến.** Khi vận hành, thiết kế ACL ghi phù hợp, chuyển log kịp thời tới kho độc lập và kiểm chứng cả trường hợp runtime hoặc local administrator bị chiếm quyền. Không mở quyền ghi module để giải quyết lỗi transcript.

### 6.4. Tạo role capability bằng một hàm giới hạn

~~~powershell
$queryFunction = @{
    Name = 'Get-PamServiceState'
    ScriptBlock = {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory = $true)]
            [ValidateSet('W32Time')]
            [string]$Name
        )

        $service = Microsoft.PowerShell.Management\Get-Service -Name $Name -ErrorAction Stop
        $service | Microsoft.PowerShell.Utility\Select-Object -Property Name, DisplayName, Status
    }
}

$rolePath = Join-Path $roleRoot 'CorpPamRemoteReadRole.psrc'

$roleParameters = @{
    Path = $rolePath
    ModulesToImport = @(
        'Microsoft.PowerShell.Management',
        'Microsoft.PowerShell.Utility'
    )
    VisibleFunctions = 'Get-PamServiceState'
    FunctionDefinitions = $queryFunction
}

New-PSRoleCapabilityFile @roleParameters
~~~

Người gọi chỉ thấy hàm nghiệp vụ được công bố cùng các lệnh nền tảng của restricted session. Hàm bắt buộc nhận `Name`, chỉ chấp nhận `W32Time` và trả về ba thuộc tính. Lời gọi `Get-Service` bên trong không làm cmdlet đó tự trở thành lệnh công khai cho người dùng.

Tên role được đặt riêng để giảm rủi ro trùng role capability trong module khác. Module được nạp vào ngữ cảnh có quyền thực thi; quyền sửa module phải được quản trị chặt như quyền sửa endpoint.

### 6.5. Tạo và đăng ký session configuration

~~~powershell
$configPath = Join-Path $configRoot 'PAM.RemoteRead.pssc'

$roleDefinitions = @{
    'CORP\PAM_RemoteRead_Eligible' = @{
        RoleCapabilities = 'CorpPamRemoteReadRole'
    }
}

$configParameters = @{
    Path = $configPath
    SessionType = 'RestrictedRemoteServer'
    LanguageMode = 'NoLanguage'
    RunAsVirtualAccount = $true
    RunAsVirtualAccountGroups = @($runtimeGroup)
    TranscriptDirectory = $transcriptRoot
    RoleDefinitions = $roleDefinitions
}

New-PSSessionConfigurationFile @configParameters

if (-not (Test-PSSessionConfigurationFile -Path $configPath)) {
    throw 'Invalid session configuration file.'
}

Register-PSSessionConfiguration -Name 'PAM.RemoteRead' -Path $configPath -Force

Get-PSSessionConfiguration -Name 'PAM.RemoteRead' | Format-List Name, Permission
~~~

Cấu hình nhóm virtual account giúp runtime không nhận nhóm quản trị mặc định. Nếu truy vấn dịch vụ bị từ chối bởi baseline máy lab, kiểm tra quyền service object và cấu hình runtime; không chuyển người dùng thành administrator để làm kiểm thử “xanh”.

`Test-PSSessionConfigurationFile` kiểm tra tính hợp lệ của file, không chứng minh role đáp ứng least privilege. Cần thử quyền hiệu lực với danh tính thật sau khi nhóm JIT đã kích hoạt. Cách dùng session configuration và transcript được trình bày trong [JEA Session Configurations](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/jea/session-configurations).

### 6.6. Kiểm thử từ PAW bằng danh tính được cấp quyền

Đăng nhập PAW bằng danh tính vận hành đang có quyền tạm thời. Phiên đăng nhập hoặc ticket cũ có thể chưa phản ánh thay đổi nhóm; phải kiểm tra theo cơ chế cập nhật token của môi trường.

~~~powershell
$sessionOptions = New-PSSessionOption -IdleTimeout 300000

$sessionParameters = @{
    ComputerName = 'app01.corp.example'
    ConfigurationName = 'PAM.RemoteRead'
    Authentication = 'Kerberos'
    UseSSL = $true
    SessionOption = $sessionOptions
}

$session = $null

try {
    $session = New-PSSession @sessionParameters

    $session | Select-Object Id, InstanceId, ComputerName, ConfigurationName, State

    Invoke-Command -Session $session -ScriptBlock {
        Get-Command
    }

    Invoke-Command -Session $session -ScriptBlock {
        Get-PamServiceState -Name 'W32Time'
    }
}
finally {
    if ($null -ne $session) {
        Remove-PSSession -Session $session
    }
}
~~~

Kết quả nghiệp vụ phải chỉ chứa trạng thái `W32Time`. Có thể thấy thêm thuộc tính remoting do PowerShell bổ sung để nhận diện nguồn đối tượng. Dịch vụ đang dừng hay đang chạy đều là kết quả hợp lệ; lab không thay đổi trạng thái dịch vụ.

`IdleTimeout 300000` đề nghị thời gian nhàn rỗi 5 phút ở client, trong giới hạn server cho phép. Nó không phải hạn mức 5 phút cho tổng thời gian phiên và không triển khai cửa sổ JIT 20 phút. Cần cấu hình hạn mức phía server và cơ chế thu hồi riêng.

Khối `finally` dọn phiên do chương trình này tạo ra khi đường thực thi còn hoạt động. Nó không bảo đảm chạy khi PAW tắt đột ngột, không dọn phiên của client khác và không thay thế xử lý phiên trên máy đích.

### 6.7. Kiểm thử từ chối

Tạo phiên thử nghiệm mới và thực hiện từng yêu cầu riêng để phân biệt nguyên nhân:

~~~powershell
$session = New-PSSession @sessionParameters

try {
    Invoke-Command -Session $session -ScriptBlock {
        Get-PamServiceState -Name 'WinRM'
    }
}
finally {
    Remove-PSSession -Session $session
}
~~~

Yêu cầu trên phải bị từ chối do giá trị ngoài `ValidateSet`. Tiếp tục kiểm thử bằng các phiên riêng:

- Gọi `Get-Service -Name W32Time` trực tiếp: cmdlet không được công bố.
- Gọi `Get-PamServiceState -Name '*'`: wildcard không được chấp nhận.
- Gọi hàm thiếu `Name`: không được trả về danh sách toàn bộ dịch vụ.
- Thử lệnh chỉ đọc không được công bố như `Get-Process`: phải bị từ chối.
- Dùng người ngoài nhóm được cấp quyền: không được thực hiện nhiệm vụ.
- Dùng nguồn mạng ngoài PAW hoặc broker: bị chặn theo chính sách mạng.
- Thử endpoint tổng quát bằng cùng danh tính: không được có shell quản trị đầy đủ.

Không dùng lệnh thay đổi nhóm quản trị hoặc tắt dịch vụ thật làm “kiểm thử từ chối” đầu tiên. Cấu hình sai có thể khiến phép thử đó thành công và gây thay đổi ngoài dự kiến. Kiểm thử phá vỡ ranh giới mạnh hơn cần môi trường chuyên dụng và kế hoạch hoàn nguyên.

## 7. JIT phải bao phủ cả phiên đang chạy

Có ba mốc khác nhau:

- Hết thời hạn phê duyệt trong PAM.
- Danh tính không còn đủ điều kiện tạo phiên mới.
- Mọi phiên và tác vụ liên quan đã kết thúc hoặc bị thu hồi.

Ba mốc này không tự trùng nhau. Bỏ một người khỏi nhóm AD không bảo đảm token của phiên đã tạo biến mất. Thu hồi membership cũng không sửa lại quyền đã nằm trong một phiên hoặc ticket đang còn giá trị theo cách mà người quản trị có thể mặc định tin tưởng.

| Thời điểm | Hành động | Điều cần quan sát |
| --- | --- | --- |
| T0 | Cấp quyền 20 phút | Ticket, người phê duyệt, nguồn và đích |
| T0 + 2 phút | Mở phiên JEA, chạy lệnh được phép | Phiên, transcript tương ứng |
| T0 + 20 phút | Quyền hết hạn | Ghi nhận thu hồi, chặn phiên mới theo SLA |
| Sau hết hạn | Thử tiếp trên phiên cũ | Phiên cũ được xử lý theo chính sách |
| Sau xử lý | Thử kết nối lại, đối chiếu tác vụ | Không còn thực thi vượt thời hạn |

Nếu hệ thống chỉ ngăn kết nối mới, hãy ghi đúng năng lực đó trong thiết kế và backlog. Đừng báo “thu hồi tức thì” khi phép thử trên phiên cũ vẫn chạy thành công.

Đóng phiên bình thường từ client dùng `Remove-PSSession`. Tuy nhiên, `Get-PSSession` không tham số chỉ phản ánh các phiên được biết trong ngữ cảnh client hiện tại; kết quả rỗng không chứng minh máy đích không còn phiên nào. Cần cơ chế kiểm kê và chấm dứt phiên phía đích hoặc broker có đủ phạm vi quản lý.

Windows PowerShell còn hỗ trợ disconnected sessions: một số phiên và lệnh có thể tiếp tục ở server khi client mất kết nối. Đóng terminal hoặc cắt mạng không phải bằng chứng mọi tác vụ đã dừng. Xem [about_Remote_Disconnected_Sessions](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_remote_disconnected_sessions?view=powershell-7.5).

Với tình huống nghi ngờ chiếm quyền:

1. Chặn cấp quyền mới và cô lập nguồn hoặc đích theo kế hoạch ứng phó.
2. Xác định phiên, danh tính thực thi, tiến trình và tác vụ liên quan.
3. Dùng cơ chế quản trị phía đích hoặc broker đã kiểm thử để kết thúc đúng phiên.
4. Kiểm tra tác vụ đã tách khỏi phiên và thay đổi bền vững đã tạo ra.
5. Xử lý credential hoặc danh tính bị lộ theo quy trình quản lý bí mật.
6. Xác nhận kết nối lại và tiếp tục thực thi đều bị chặn; lưu bằng chứng.

Có thể vô hiệu hóa endpoint trong tình huống khẩn cấp:

~~~powershell
Disable-PSSessionConfiguration -Name 'PAM.RemoteRead' -Force
~~~

Đây là thao tác quản trị có thể ảnh hưởng dịch vụ và phiên, cần đường phục hồi. Tài liệu [Disable-PSSessionConfiguration](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/disable-pssessionconfiguration) mô tả việc vô hiệu hóa cấu hình để ngăn tạo phiên. Không dùng riêng kết quả lệnh này để chứng nhận mọi tiến trình đã chạy trước đó đều kết thúc.

## 8. Second hop và kiểm soát credential

Giả sử người vận hành đi từ PAW A tới máy ứng dụng B. Từ B, script lại đọc file hoặc gọi dịch vụ trên máy C. Đây là bài toán second hop: quyền xác thực tới B không mặc nhiên trở thành quyền thay mặt người dùng truy cập C.

Ví dụ, lệnh đọc trạng thái dịch vụ local chạy thành công, nhưng script chẩn đoán đọc `\\files01\diagnostics\config.json` lại bị từ chối. Trước khi “sửa xác thực”, cần hỏi tác vụ có thật sự cần truy cập C trong phiên tương tác hay không.

| Nhu cầu | Hướng xử lý | Điểm cần kiểm soát |
| --- | --- | --- |
| Chỉ cần cấu hình đã duyệt | Chuẩn bị dữ liệu local qua triển khai | Nguồn, tính toàn vẹn dữ liệu |
| Cần chạy tác vụ trên C | Tác vụ trực tiếp được phê duyệt tới C | Quyền, bằng chứng riêng cho C |
| Dịch vụ cần tài nguyên mạng | Runtime identity chuyên biệt, có thể là gMSA | Phạm vi tài nguyên, máy được dùng danh tính |
| Bắt buộc delegation | Thiết kế theo giao thức và trust cụ thể | Khả năng hỗ trợ, phạm vi, kiểm thử |

CredSSP có thể giải quyết một số trường hợp bằng cách chuyển thông tin xác thực tới máy trung gian, nhưng tăng rủi ro nếu máy đó bị chiếm quyền. Không bật CredSSP hàng loạt để xử lý mọi lỗi truy cập. KCD hoặc RBCD cũng không phải lời giải tự động cho mọi đường WinRM second hop; phải đối chiếu giao thức và giới hạn hỗ trợ. Xem [Making the second hop in PowerShell Remoting](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/ps-remoting-second-hop).

Nếu endpoint dùng gMSA để gọi C, tài nguyên ở C nhìn thấy danh tính gMSA theo thiết kế, không tự nhìn thấy từng người vận hành. Khi đó nối transcript, ticket và người khởi tạo là phần bắt buộc của kiểm toán.

Không ghi password, token hoặc private key vào script, tham số dòng lệnh hay transcript để tiện thực hành. Với credential lấy từ vault, phải xác định nơi nó được giải mã, tiến trình nào nhìn thấy, thời gian tồn tại và cơ chế thu hồi hoặc luân chuyển sau sử dụng.

## 9. Bằng chứng và phát hiện truy cập ngoài chính sách

### 9.1. Chuỗi bằng chứng cần nối được

Một hồ sơ truy cập cần giúp người rà soát trả lời:

> Ticket nào cho phép người nào, từ thiết bị nào, vào máy nào, dùng endpoint nào, dưới runtime identity nào, thực hiện thao tác gì và kết thúc lúc nào?

Các trường nên thu thập gồm:

- Request ID, ticket, lý do, người phê duyệt và cửa sổ truy cập.
- Danh tính khởi tạo, thiết bị và địa chỉ nguồn.
- Máy đích, engine, transport, endpoint và định danh phiên nếu có.
- Runtime identity, thao tác, tham số phù hợp chính sách và kết quả.
- Thời điểm tạo, kết thúc, hết hạn, thu hồi và kết quả thử lại.
- Phiên bản cấu hình endpoint, role capability và module.
- Vị trí bằng chứng, thời gian collector nhận và tình trạng toàn vẹn.

Không giả định Request ID tự xuất hiện trong mọi WinRM event. Nếu sản phẩm không hỗ trợ truyền ID xuyên suốt, thiết kế phép đối chiếu dựa trên nguồn có thật và ghi rõ mức độ chắc chắn. Ghi chú do người dùng tự nhập là dữ liệu bổ sung, không phải bằng chứng quyết định cấp quyền.

### 9.2. Các lớp log bổ sung cho nhau

Với Windows PowerShell 5.1, các nguồn hữu ích gồm log WinRM, `Microsoft-Windows-PowerShell/Operational`, Security log theo audit policy, transcript JEA và log tài nguyên được quản lý.

Script Block Logging có thể ghi sự kiện 4104 khi được bật. Windows PowerShell 5.1 và PowerShell 7 có kênh và cấu hình logging cần kiểm tra tương ứng; không nên dùng tên kênh của engine này để kết luận engine kia không có hoạt động. Logging cũng có thể chứa dữ liệu nhạy cảm, nên phải kiểm soát quyền đọc và bảo vệ dữ liệu. Xem [about_Logging cho Windows PowerShell 5.1](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_logging?view=powershell-5.1).

Ví dụ truy vấn chẩn đoán local trên máy lab từ ngữ cảnh quản trị hợp lệ:

~~~powershell
$since = (Get-Date).AddMinutes(-30)

Get-WinEvent -FilterHashtable @{
    LogName = 'Microsoft-Windows-WinRM/Operational'
    StartTime = $since
} -MaxEvents 30 | Select-Object TimeCreated, Id, ProviderName, Message

Get-WinEvent -FilterHashtable @{
    LogName = 'Microsoft-Windows-PowerShell/Operational'
    Id = 4104
    StartTime = $since
} -MaxEvents 30 | Select-Object TimeCreated, Id, Message
~~~

Không có kết quả có thể do chưa bật policy, chưa chuyển log, truy vấn sai thời gian hoặc thiếu quyền đọc. Nó không chứng minh chưa có phiên. Transcript cũng không phải bản ghi bất biến của mọi sự kiện hệ điều hành, mọi tác dụng phụ hoặc mọi lần đánh cắp dữ liệu.

Để kiểm tra quyền hiệu lực của một người trên endpoint, quản trị viên có thể dùng:

~~~powershell
Get-PSSessionCapability -ConfigurationName 'PAM.RemoteRead' -Username 'CORP\pam.reader01'
~~~

Kết quả phải đối chiếu với nhóm JIT và phiên thực tế, đặc biệt khi membership vừa thay đổi. Cách rà soát quyền và đối chiếu người kết nối với tài khoản thực thi được nêu trong [Auditing and Reporting on JEA](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/jea/audit-and-report).

### 9.3. Những tín hiệu đáng theo dõi

Phát hiện nên gắn với chính sách cụ thể thay vì chỉ cảnh báo “có PowerShell”:

| Tín hiệu | Lý do cần xem xét | Dữ liệu đối chiếu |
| --- | --- | --- |
| Nguồn ngoài PAW kết nối cổng quản trị | Có thể có đường đi ngoài kiểm soát | Firewall, thiết bị, xác thực |
| Role đọc dùng endpoint tổng quát | Sai quyền hoặc đường truy cập thay thế | ACL endpoint, nhóm, log phiên |
| Xác thực ngoài baseline | Ngoại lệ chưa được kiểm soát | Cấu hình, sự kiện xác thực |
| Thao tác sau thời hạn quyền | Thu hồi chưa bao phủ phiên | JIT, phiên phía đích, transcript |
| Role hoặc module đổi ngoài cửa sổ triển khai | Ranh giới thao tác có thể đã đổi | Hash, người sửa, quản lý cấu hình |
| Có phiên nhưng collector không nhận bằng chứng | Khoảng trống quan sát | Sức khỏe agent, hàng đợi, dung lượng |

Đối với đường quản trị đặc quyền cao, cần định nghĩa rõ khi logging hỏng thì ngừng cấp phiên hay cho phép tiếp tục theo ngoại lệ nào. Quyết định phải được kiểm thử và ghi nhận, không để người vận hành tự mở rộng quyền khi gặp lỗi.

## 10. Xử lý lỗi theo từng lớp

| Hiện tượng | Khả năng cần kiểm tra | Cách tiếp cận |
| --- | --- | --- |
| Không kết nối được cổng | Firewall, listener, mạng | Kiểm tra đúng nguồn, đích, cổng |
| Lỗi TLS | Tên, hạn chứng thư, trust, private key | Sửa chứng thư hoặc listener |
| Kerberos thất bại | DNS, thời gian, SPN, trust, DC | Giữ phương thức dự kiến, kiểm tra miền |
| Access denied trước tạo phiên | Endpoint ACL, nhóm, token | Kiểm tra danh tính thật và cấp quyền |
| Vào phiên nhưng không thấy hàm | Mapping, module, tên capability | Rà soát cấu hình, quyền đọc module |
| Hàm bị từ chối tài nguyên | Quyền runtime hoặc ACL service | Kiểm tra run-as và quyền tối thiểu |
| Lệnh ngoài phạm vi chạy được | Role rộng hoặc cộng gộp quyền | Kiểm tra membership, capability hiệu lực |
| Không có transcript | ACL thư mục, dung lượng, cấu hình | Kiểm tra local và collector |
| Hết JIT nhưng phiên vẫn chạy | Phiên hoặc token còn hiệu lực | Thu hồi phiên, đo độ trễ |

Một người có thể nhận nhiều role qua nhóm lồng nhau hoặc nhiều mapping. Quyền hiệu lực có thể rộng hơn role mà người triển khai đang nhìn. Cần rà soát phép hợp quyền thực tế, không chỉ một file `.psrc`.

Khi gặp lỗi, thay đổi nhỏ nhất ở đúng lớp gây lỗi. Không đồng thời mở firewall, thêm TrustedHosts và cấp administrator: cách đó làm mất khả năng xác định nguyên nhân, đồng thời tạo đường quản trị có thể vượt phạm vi đã phê duyệt.

## 11. Tình huống vận hành: đọc trạng thái rồi yêu cầu khắc phục

Một nhân viên được phê duyệt role RemoteRead để điều tra cảnh báo đồng bộ thời gian trên `app01`. Kết quả cho thấy W32Time đang dừng. Nhân viên yêu cầu bổ sung quyền khởi động lại máy vì đó là cách họ từng xử lý sự cố tương tự.

Phân tích theo nhiệm vụ:

1. Quyền đã cấp chỉ hỗ trợ đọc trạng thái; nó không hàm ý được thay đổi máy.
2. Khởi động lại cả máy ảnh hưởng ứng dụng và người dùng, rộng hơn thao tác đang cần điều tra.
3. Trước khi cấp quyền mới, đối chiếu nguyên nhân, phụ thuộc và quy trình thay đổi.
4. Nếu khắc phục được phê duyệt, dùng thao tác giới hạn riêng, có kiểm tra trước và sau.
5. Nếu cần credential khác, lấy qua quy trình danh tính và vault, không mượn tài khoản đồng nghiệp.
6. Sau xử lý, kiểm chứng kết quả và thu hồi quyền bổ sung theo cửa sổ đã cấp.

Hồ sơ kết thúc nên ghi yêu cầu ban đầu, kết quả đọc, quyết định khắc phục, người phê duyệt, thao tác thực tế, kết quả sau thay đổi và bằng chứng thu hồi. Chỉ có transcript ghi `Get-PamServiceState` chưa chứng minh thay đổi sau này cũng đã được phê duyệt.

## 12. Tiêu chí nghiệm thu

Triển khai Remote PowerShell control đạt mục tiêu bài khi chứng minh được trên môi trường thử nghiệm:

- Danh tính đúng, từ nguồn đúng, vào endpoint đúng và chạy được thao tác được giao.
- Danh tính hoặc nguồn ngoài phạm vi bị từ chối.
- Tham số ngoài danh sách, lệnh không công bố và endpoint tổng quát không tạo quyền vượt nhiệm vụ.
- Runtime có quyền tài nguyên cần thiết, không nhận đặc quyền rộng ngoài dự kiến.
- Người dùng nghiệp vụ không thể sửa cấu hình, module hoặc role capability.
- Thời hạn JIT được kiểm tra với cả kết nối mới và phiên đang tồn tại.
- Disconnect, timeout, kết thúc phiên và thu hồi được phân biệt bằng kết quả quan sát.
- Ticket, người khởi tạo, runtime identity, thao tác và kết quả đối chiếu được trong kho bằng chứng.
- Mất logging, thay đổi cấu hình, lỗi xác thực và second hop có quy trình xử lý rõ ràng.
- Đường phục hồi được kiểm thử khi vô hiệu hóa hoặc cập nhật endpoint.

Quản lý PowerShell từ xa trong PAM là quản lý toàn bộ vòng đời quyền thực thi. Mức kiểm soát được thể hiện qua phạm vi thao tác, khả năng thu hồi và bằng chứng đối chiếu được.
