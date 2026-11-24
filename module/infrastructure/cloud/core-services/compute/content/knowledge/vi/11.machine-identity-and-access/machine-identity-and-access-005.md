# RDP và quản lý danh tính đăng nhập Windows

## Mục tiêu bài học

Remote Desktop Protocol (RDP) cho phép người quản trị kết nối tới giao diện máy tính Windows từ xa để vận hành máy ảo, xử lý sự cố hoặc quản trị máy chủ. Một kết nối RDP an toàn cần nhiều thành phần phối hợp: đường mạng được giới hạn, dịch vụ Remote Desktop được cấu hình đúng, người dùng được xác thực, quyền đăng nhập được cấp theo vai trò và phiên làm việc được giám sát.

Sau bài học này, bạn có thể:

- Giải thích RDP, Network Level Authentication (NLA) và vai trò của mã hóa kết nối.
- Thiết kế đường truy cập RDP qua VPN, RD Gateway hoặc dịch vụ Bastion.
- Phân biệt tài khoản local, Active Directory và Microsoft Entra ID trong môi trường Windows.
- Cấp quyền Remote Desktop theo nhóm và nguyên tắc least privilege.
- Bảo vệ thông tin xác thực, áp dụng MFA và quản lý mật khẩu quản trị cục bộ.
- Theo dõi đăng nhập thành công, thất bại và vòng đời phiên RDP.

## 1. RDP là gì?

RDP là giao thức truy cập máy tính từ xa do Microsoft phát triển. RDP client trên máy quản trị kết nối tới RDP host, thường là Windows client hoặc Windows Server, để hiển thị desktop và gửi thao tác bàn phím, chuột. Phiên RDP cũng có thể chuyển tiếp một số tài nguyên như clipboard, ổ đĩa, máy in hoặc thiết bị, tùy chính sách được cho phép.

Trong môi trường cloud, RDP thường được dùng để:

- Quản trị Windows VM và cài đặt phần mềm.
- Kiểm tra dịch vụ, Event Viewer, Task Manager và cấu hình hệ điều hành.
- Khắc phục sự cố khi ứng dụng hoặc agent trong guest OS gặp lỗi.
- Thực hiện các tác vụ quản trị cần giao diện đồ họa.

RDP chỉ cung cấp kênh làm việc từ xa. Nó không tự quyết định người dùng có được phép quản trị máy hay không. Hệ điều hành Windows vẫn xác thực danh tính và kiểm tra quyền đăng nhập; firewall, security group và hệ thống mạng quyết định máy khách nào có thể tiếp cận dịch vụ.

Cổng mặc định của RDP là TCP 3389. Một số cấu hình có thể sử dụng UDP để cải thiện trải nghiệm truyền dữ liệu. Cổng có thể thay đổi, nhưng đổi cổng không thay thế kiểm soát truy cập mạng và xác thực mạnh.

~~~mermaid
flowchart LR
    A["Máy quản trị / RDP client"] --> B["VPN hoặc mạng riêng"]
    B --> C["Firewall / Security Group"]
    C --> D["Windows VM / RDP host"]
    D --> E["Xác thực Windows"]
    E --> F["Kiểm tra quyền đăng nhập"]
    F --> G["Desktop session"]
~~~

## 2. Xác thực và mã hóa phiên RDP

Một phiên RDP có nhiều lớp bảo vệ.

**TLS** bảo vệ kênh kết nối bằng mã hóa và xác thực máy chủ dựa trên chứng thư khi được cấu hình đúng. Chứng thư RDP cần có danh tính phù hợp với máy chủ và được client tin cậy. Cảnh báo chứng thư không nên bị bỏ qua theo thói quen; cần xác minh tên máy và nguồn cấp chứng thư.

**Network Level Authentication (NLA)** yêu cầu người dùng xác thực trước khi Windows tạo đầy đủ phiên desktop. NLA thường sử dụng CredSSP để thực hiện xác thực ban đầu. Cơ chế này giảm việc cấp tài nguyên phiên cho các kết nối chưa được xác thực và nên được bật trên các máy hỗ trợ.

**Windows authorization** kiểm tra tài khoản có quyền đăng nhập từ xa hay không, bao gồm thành viên nhóm local và chính sách User Rights Assignment.

NLA không thay thế TLS, firewall, MFA hoặc quyền tối thiểu. Một tài khoản có mật khẩu yếu vẫn có thể bị đoán nếu dịch vụ có thể tiếp cận rộng. Một kết nối đã mã hóa vẫn có thể cấp quyền quá mức nếu nhóm đăng nhập được cấu hình sai.

Các nguyên tắc nên áp dụng:

- Bật NLA trên host khi client và hệ điều hành hỗ trợ.
- Dùng TLS với chứng thư được quản lý phù hợp; theo dõi ngày hết hạn.
- Cập nhật Windows và RDP client theo quy trình bản vá.
- Giới hạn địa chỉ nguồn có thể kết nối tới RDP host.
- Dùng MFA ở lớp truy cập hỗ trợ MFA, chẳng hạn VPN, RD Gateway hoặc Bastion có tích hợp danh tính.
- Không coi việc đổi cổng 3389 thành một cổng khác là biện pháp bảo mật chính.

## 3. Thiết kế đường truy cập RDP an toàn

Không nên mở cổng RDP trực tiếp ra toàn bộ Internet. Máy Windows có thể bị dò quét liên tục; nếu dịch vụ lộ ra ngoài, tổ chức phải đối mặt với password spraying, brute force, khai thác lỗ hổng và rủi ro từ credential bị đánh cắp.

Các mô hình truy cập phổ biến:

### 3.1. VPN vào mạng riêng

Người quản trị kết nối VPN trước, sau đó RDP tới địa chỉ private của VM. Security Group hoặc firewall chỉ cho phép nguồn là dải mạng VPN hoặc subnet quản trị.

Ưu điểm là máy ảo không cần địa chỉ RDP công khai. Tuy nhiên, VPN cũng phải dùng MFA, thiết bị được quản lý, quyền truy cập theo vai trò và logging.

### 3.2. Remote Desktop Gateway

RD Gateway cho phép người dùng truy cập máy Windows nội bộ qua một gateway được kiểm soát. Client kết nối tới gateway qua HTTPS, thường là TCP 443; gateway chuyển tiếp phiên RDP tới máy đích theo chính sách.

RD Gateway có thể kết hợp:

- Connection Authorization Policy (CAP) để xác định ai được kết nối qua gateway.
- Resource Authorization Policy (RAP) để giới hạn máy đích người dùng được phép truy cập.
- NPS hoặc giải pháp xác thực bổ sung để tích hợp MFA, tùy kiến trúc.

Gateway cần được vá lỗi, đặt trong vùng mạng phù hợp, có chứng thư hợp lệ, giới hạn quyền quản trị và giám sát log.

### 3.3. Bastion do nhà cung cấp cloud quản lý

Dịch vụ Bastion cung cấp điểm truy cập quản trị vào VM qua mặt phẳng quản lý của cloud. Tùy nhà cung cấp, người dùng có thể kết nối qua trình duyệt hoặc client mà không cần public IP trên VM. Dịch vụ có thể tích hợp IAM, MFA, nhật ký phiên hoặc các tùy chọn kiểm soát khác.

Cần kiểm tra tính năng thực tế theo SKU, khu vực, loại VM và cấu hình mạng. Bastion không tự động bảo đảm mọi phiên đều có MFA hoặc được ghi hình; hãy xác minh và bật đúng tùy chọn cần thiết.

~~~mermaid
flowchart TD
    U["Người quản trị"] --> M["MFA và kiểm tra thiết bị"]
    M --> V["VPN / RD Gateway / Cloud Bastion"]
    V --> P["Private subnet"]
    P --> FW["Firewall chỉ cho phép nguồn quản trị"]
    FW --> VM["Windows VM: RDP + NLA"]
    VM --> AU["Windows group và logon policy"]
~~~

### 3.4. Quy tắc mạng cần có

- Không gán public IP cho VM chỉ để tiện RDP nếu có thể dùng private access.
- Chỉ cho phép TCP 3389 từ subnet quản trị, VPN hoặc gateway cụ thể.
- Chỉ mở UDP RDP nếu đã xác định cần thiết và nguồn truy cập vẫn bị giới hạn.
- Dùng cả cloud security group/NSG và Windows Defender Firewall theo nguyên tắc nhiều lớp.
- Không dùng rule nguồn 0.0.0.0/0 hoặc Any cho RDP.
- Rà soát rule tạm sau khi hoàn tất sự cố hoặc đợt bảo trì.
- Tách mạng quản trị khỏi mạng phục vụ ứng dụng và dữ liệu khi kiến trúc cho phép.

## 4. Các loại danh tính đăng nhập Windows

Windows có thể xác thực nhiều loại danh tính. Cách quản lý phụ thuộc VM là máy độc lập, domain-joined hay Entra ID-joined.

| Loại danh tính | Phạm vi quản lý | Ví dụ | Điểm cần lưu ý |
|---|---|---|---|
| Local account | Riêng trên từng máy Windows | Tài khoản local vmadmin | Dễ bắt đầu nhưng có nguy cơ trùng mật khẩu và khó quản lý số lượng lớn |
| Active Directory Domain Services (AD DS) | Miền Active Directory của tổ chức | CONTOSO\alice | Quản lý tập trung bằng domain group, GPO và quy trình vòng đời tài khoản |
| Microsoft Entra ID | Danh tính cloud của tổ chức | alice@contoso.example | Hỗ trợ Conditional Access và MFA trong cấu hình, phiên bản Windows và luồng đăng nhập tương thích |
| Hybrid identity | Đồng bộ hoặc liên kết danh tính on-premises và cloud | Tài khoản tổ chức được đồng bộ | Cần hiểu nguồn danh tính chuẩn và cách xử lý khi tài khoản bị khóa hoặc thu hồi |

**Xác thực (authentication)** trả lời câu hỏi người dùng là ai. **Ủy quyền (authorization)** xác định người đó được phép làm gì sau khi xác thực. Đăng nhập thành công vào máy không đồng nghĩa người dùng được phép cài phần mềm, sửa firewall hoặc thay đổi cấu hình bảo mật.

Đối với VM cloud, cần xác minh cách nhà cung cấp và phiên bản Windows hỗ trợ domain join hoặc Entra ID sign-in. Không phải mọi Windows image, edition hay loại VM đều hỗ trợ cùng một luồng đăng nhập. Hãy dùng tài liệu triển khai chính thức của dịch vụ đang chạy.

## 5. Cấp quyền Remote Desktop theo nhóm

Windows sử dụng nhóm local và User Rights Assignment để kiểm soát ai có thể đăng nhập qua Remote Desktop Services.

Hai nhóm thường gặp:

- **Administrators:** thành viên có quyền quản trị máy; chỉ cấp cho người thực sự cần quyền này.
- **Remote Desktop Users:** nhóm dành cho người được phép đăng nhập từ xa nhưng không mặc nhiên có toàn quyền quản trị.

Chính sách User Rights Assignment có hai mục quan trọng:

- **Allow log on through Remote Desktop Services:** xác định nhóm/tài khoản được phép đăng nhập qua RDP.
- **Deny log on through Remote Desktop Services:** xác định nhóm/tài khoản bị từ chối đăng nhập từ xa.

Chính sách Deny thường có hiệu lực ưu tiên khi một tài khoản đồng thời nằm trong nhóm Allow và Deny. Khi dùng Group Policy, cần kiểm tra cả GPO ở cấp OU/domain và chính sách local để tránh cấu hình ghi đè ngoài dự kiến.

### Ví dụ thêm nhóm domain vào Remote Desktop Users

Chạy PowerShell với quyền quản trị trên Windows VM:

~~~powershell
Add-LocalGroupMember -Group "Remote Desktop Users" -Member "CONTOSO\ops-rdp"
~~~

Tên nhóm local có thể được bản địa hóa theo ngôn ngữ Windows. Với domain, nên thêm nhóm bảo mật đã được phê duyệt thay vì thêm từng người dùng riêng lẻ.

Kiểm tra thành viên:

~~~powershell
Get-LocalGroupMember -Group "Remote Desktop Users"
~~~

Kiểm tra chính sách đăng nhập bằng Local Security Policy (secpol.msc) hoặc Group Policy Management. Trên máy được quản lý bằng domain, thay đổi local có thể bị GPO ghi đè ở lần cập nhật chính sách tiếp theo.

### Mô hình phân quyền gợi ý

| Vai trò | Quyền RDP | Quyền quản trị |
|---|---|---|
| Vận hành ứng dụng | Được phép theo nhóm được duyệt | Chỉ quyền cần cho ứng dụng |
| Windows administrator | Được phép | Admin theo nhiệm vụ và thời hạn |
| Developer | Chỉ khi có nhu cầu hỗ trợ được phê duyệt | Không cấp local admin mặc định |
| Auditor | Có thể chỉ cần log hoặc truy cập báo cáo | Không cần đăng nhập RDP nếu không có lý do |
| Service account | Không dùng cho đăng nhập tương tác | Quyền dịch vụ riêng, không dùng làm tài khoản người |

Không cấp quyền Domain Admin chỉ để người dùng có thể RDP vào một VM. Tài khoản quản trị miền và tài khoản quản trị máy chủ nên được tách theo phạm vi trách nhiệm.

## 6. Bảo vệ tài khoản quản trị cục bộ

Tài khoản local administrator thường được tạo sẵn trong image hoặc lúc triển khai VM. Nếu nhiều máy dùng chung một mật khẩu, việc lộ một máy có thể tạo đường truy cập sang các máy khác.

Windows LAPS (Local Administrator Password Solution) giúp tự động quản lý và xoay vòng mật khẩu tài khoản quản trị cục bộ. Tùy môi trường, mật khẩu có thể được sao lưu vào Active Directory hoặc Microsoft Entra ID theo cấu hình được hỗ trợ.

LAPS giúp:

- Tạo mật khẩu local admin duy nhất cho từng máy.
- Xoay vòng mật khẩu theo chính sách.
- Giới hạn người có thể đọc mật khẩu.
- Ghi nhận hoạt động truy cập và quản lý mật khẩu theo khả năng của nền tảng danh tính.

Các bước triển khai ở mức khái niệm:

1. Chọn tài khoản local admin được quản lý và xác nhận tên tài khoản.
2. Chuẩn bị schema, quyền đọc/ghi và policy cho AD DS hoặc Entra ID theo môi trường.
3. Bật policy LAPS trên các máy mục tiêu.
4. Xác minh mật khẩu được backup và được xoay vòng.
5. Giới hạn quyền đọc mật khẩu cho nhóm hỗ trợ được phê duyệt.
6. Kiểm tra audit và quy trình break-glass.

Không nên lưu mật khẩu local admin trong file cấu hình, script bootstrap, ticket hoặc tài liệu chia sẻ. Không dùng một mật khẩu local admin giống nhau cho toàn bộ VM.

## 7. MFA và chính sách truy cập có điều kiện

MFA yêu cầu người dùng chứng minh danh tính bằng nhiều yếu tố, chẳng hạn mật khẩu kết hợp ứng dụng xác thực, khóa bảo mật hoặc yếu tố sinh trắc học được nền tảng hỗ trợ.

RDP truyền thống tới một máy Windows không tự động có MFA chỉ vì Windows account có bật MFA ở một dịch vụ khác. Cần thiết kế MFA ở một điểm thực thi phù hợp:

- VPN có tích hợp MFA.
- RD Gateway tích hợp NPS hoặc nhà cung cấp MFA.
- Cloud Bastion có hỗ trợ xác thực qua danh tính cloud và MFA.
- Entra ID sign-in cho VM khi hệ điều hành, extension và luồng đăng nhập được hỗ trợ.

Conditional Access có thể áp dụng điều kiện như người dùng, nhóm, mức rủi ro, trạng thái thiết bị hoặc vị trí truy cập, tùy giấy phép và cấu hình. Chính sách phải được thử nghiệm để tránh khóa nhầm toàn bộ tài khoản quản trị. Cần có tài khoản khẩn cấp được kiểm soát riêng theo quy trình tổ chức.

Nên yêu cầu MFA cho quyền quản trị và truy cập từ xa, đồng thời dùng thiết bị quản trị được quản lý. MFA giảm nguy cơ từ mật khẩu bị đánh cắp nhưng không thay thế cập nhật bản vá, kiểm soát mạng hoặc bảo vệ endpoint.

## 8. Bảo vệ credential trong phiên RDP

Khi kết nối từ xa, credential có thể bị lộ nếu người dùng lưu mật khẩu không an toàn, kết nối tới host giả mạo hoặc cho phép chuyển tiếp tài nguyên quá rộng.

Các biện pháp nên xem xét:

- Không chia sẻ file RDP có nhúng credential hoặc thông tin truy cập nhạy cảm.
- Tránh lưu mật khẩu trong Remote Desktop client trên máy dùng chung.
- Xác minh tên máy và chứng thư server trước khi chấp nhận kết nối.
- Sử dụng Remote Credential Guard khi môi trường domain và client/host hỗ trợ. Cơ chế này giúp credential không bị gửi tới remote host theo cách thông thường.
- Chỉ bật Restricted Admin mode khi hiểu rõ hành vi và tác động tới xác thực tới tài nguyên khác.
- Giới hạn clipboard, drive, printer, COM/LPT và thiết bị được chuyển hướng theo nhu cầu công việc.
- Không tải file nhạy cảm về máy cá nhân không được quản lý.
- Dùng privileged access workstation hoặc máy quản trị chuyên dụng cho tài khoản có quyền cao.

Remote Credential Guard và Restricted Admin có điều kiện tương thích riêng; không bật đại trà nếu chưa thử nghiệm ứng dụng, domain và luồng xác thực. Một số tác vụ truy cập tài nguyên từ máy đích tới máy thứ ba có thể hoạt động khác khi credential delegation bị hạn chế.

## 9. Cấu hình RDP trên Windows VM

Trước khi bật RDP, xác nhận VM thuộc đúng subscription/project, môi trường và owner. Bật Remote Desktop cần đi cùng thay đổi firewall và rule mạng tương ứng.

Có thể bật Remote Desktop trong Settings hoặc Server Manager. Trên hệ thống được quản lý bằng policy, hãy cấu hình bằng GPO hoặc công cụ quản trị chuẩn của tổ chức.

Ví dụ PowerShell minh họa trên máy Windows:

~~~powershell
# Cho phép kết nối Remote Desktop ở cấp hệ điều hành
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name 'fDenyTSConnections' -Value 0

# Bật yêu cầu Network Level Authentication
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name 'UserAuthentication' -Value 1

# Bật rule firewall có sẵn cho Remote Desktop
Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'
~~~

Tên display group của Windows Firewall có thể khác theo ngôn ngữ hệ điều hành. Trước khi bật rule, cần cấu hình phạm vi địa chỉ nguồn để chỉ cho phép subnet quản trị hoặc gateway.

Kiểm tra listener và firewall:

~~~powershell
Get-Service -Name TermService
Get-NetTCPConnection -LocalPort 3389 -State Listen
Get-NetFirewallRule -DisplayGroup 'Remote Desktop'
~~~

Đây là ví dụ cấu hình trong guest OS; cloud security group/NSG vẫn phải cho phép nguồn truy cập hợp lệ. Không mở rule rộng trên host chỉ vì cần kiểm tra kết nối.

## 10. Vòng đời cấp và thu hồi quyền truy cập

Quyền RDP nên được quản lý theo vòng đời nhân sự và nhiệm vụ vận hành.

### Onboarding

- Xác nhận người dùng, quản lý phê duyệt, lý do và thời hạn cần truy cập.
- Thêm người dùng vào nhóm domain hoặc Entra ID phù hợp.
- Cấp quyền tới đúng VM hoặc nhóm VM.
- Bật MFA và yêu cầu thiết bị quản trị đáp ứng chính sách.
- Hướng dẫn sử dụng gateway, kiểm tra chứng thư và quy tắc xử lý dữ liệu.

### Thay đổi vai trò

- Rà soát nhóm hiện tại khi người dùng đổi nhóm hoặc dự án.
- Thu hồi quyền cũ trước hoặc cùng thời điểm cấp quyền mới.
- Không để quyền tạm thời trở thành quyền vĩnh viễn do quên dọn dẹp.
- Rà soát quyền admin riêng với quyền RDP thông thường.

### Offboarding

- Vô hiệu hóa hoặc thu hồi danh tính theo quy trình HR/IAM.
- Thu hồi session/token và quyền VPN, Bastion hoặc RD Gateway.
- Xóa người dùng khỏi nhóm truy cập RDP.
- Thu hồi quyền đọc secret và local admin password.
- Kiểm tra tài khoản local, credential cache và khóa truy cập liên quan.
- Lưu audit phục vụ điều tra và kiểm toán.

### Just-in-time access

Với máy production, có thể cấp quyền RDP tạm thời trong một khoảng thời gian ngắn, gắn với ticket hoặc yêu cầu thay đổi. Hệ thống tự động bật rule hoặc thêm quyền trong thời hạn đã duyệt rồi thu hồi sau đó. Cần ghi lại người yêu cầu, người phê duyệt, VM đích, thời gian và lý do.

## 11. Giám sát đăng nhập và phiên RDP

Audit giúp phát hiện password spraying, đăng nhập bất thường và quyền bị sử dụng sai mục đích.

Các nguồn log quan trọng:

- Windows Security log.
- TerminalServices LocalSessionManager và RemoteConnectionManager.
- Log của VPN, RD Gateway, Bastion và hệ thống IAM.
- Cloud audit log cho thay đổi security group, VM và danh tính.

Một số Windows Security Event ID thường hữu ích:

| Event ID | Ý nghĩa thường gặp | Cách sử dụng |
|---|---|---|
| 4624 | Đăng nhập thành công | Xem Logon Type 10 cho RemoteInteractive; đối chiếu tài khoản và địa chỉ nguồn |
| 4625 | Đăng nhập thất bại | Phát hiện mật khẩu sai lặp lại, tài khoản bị khóa hoặc nguồn bất thường |
| 4648 | Đăng nhập sử dụng explicit credentials | Điều tra ứng dụng hoặc tiến trình cung cấp credential rõ ràng |
| 4778 | Phiên workstation được kết nối lại | Theo dõi reconnect trong môi trường có session |
| 4779 | Phiên workstation bị ngắt kết nối | Phân tích disconnect và vòng đời phiên |

Các Event ID và trường chi tiết phụ thuộc phiên bản Windows, audit policy và cấu hình Remote Desktop Services. Cần kiểm tra log thực tế của máy thay vì chỉ dựa vào một mã sự kiện.

Với TerminalServices LocalSessionManager, có thể theo dõi các sự kiện đăng nhập, disconnect và reconnect như 21, 24 và 25. RemoteConnectionManager có thể ghi nhận sự kiện xác thực kết nối. Cần bật đúng channel và chuyển log về nơi lưu trữ tập trung.

Nên cảnh báo khi:

- Có nhiều lần đăng nhập thất bại từ một nguồn hoặc trên nhiều tài khoản.
- Tài khoản quản trị đăng nhập ngoài khung giờ hoặc từ thiết bị không quen thuộc.
- Một tài khoản mới được thêm vào nhóm Administrators hoặc Remote Desktop Users.
- NLA bị tắt, firewall rule bị mở rộng hoặc chứng thư RDP thay đổi bất thường.
- Phiên quản trị kéo dài bất thường hoặc nhiều phiên đồng thời không phù hợp với vai trò.

Log cần được lưu tập trung, đồng bộ thời gian và giới hạn quyền xóa/sửa. Không ghi password, token hoặc nội dung nhạy cảm của clipboard vào log.

## 12. Quản lý phiên và vận hành máy chủ

Một phiên RDP có thể bị disconnect nhưng tiến trình người dùng vẫn tiếp tục chạy trên máy chủ, tùy cấu hình session và chính sách. Disconnect không giống sign out.

Cần thiết lập:

- Idle session timeout phù hợp với mức độ nhạy cảm của máy.
- Giới hạn thời gian phiên kéo dài và phiên disconnected.
- Quy tắc sign out khi hoàn tất tác vụ quản trị.
- Giới hạn số phiên đồng thời theo vai trò và năng lực máy.
- Chính sách khóa màn hình và xác thực lại khi quay lại.
- Lịch bảo trì và thông báo trước khi restart máy.

Windows client và Windows Server có mô hình phiên và điều kiện cấp phép khác nhau. Nếu triển khai máy chủ Remote Desktop Session Host cho nhiều người dùng đồng thời, cần kiểm tra edition, vai trò RDS và yêu cầu Remote Desktop Services Client Access License (RDS CAL) phù hợp. Không nên giả định mọi Windows VM đều cho phép số lượng phiên tương tác không giới hạn.

## 13. Xử lý sự cố RDP

Khi không kết nối được, kiểm tra theo từng lớp để khoanh vùng nguyên nhân.

| Triệu chứng | Kiểm tra |
|---|---|
| Timeout | VM có đang chạy không; route, VPN, Bastion, NSG và firewall có cho phép nguồn không |
| Connection refused | TermService có chạy không; listener có lắng nghe cổng cấu hình không |
| Không xác thực được | Tài khoản có tồn tại, mật khẩu còn hiệu lực, NLA/CredSSP tương thích và thời gian hệ thống chính xác không |
| Authentication thành công nhưng bị từ chối logon | Nhóm Remote Desktop Users/Administrators và Allow/Deny logon rights |
| Bị ngắt ngay sau kết nối | GPO, session limit, licensing, profile, endpoint security hoặc lỗi dịch vụ |
| Kết nối chậm | Độ trễ mạng, packet loss, chất lượng gateway, độ phân giải và tài nguyên VM |
| Cảnh báo chứng thư | Tên máy, thời hạn, trust chain và chứng thư được gán cho listener |

Một số lệnh kiểm tra từ máy client:

~~~powershell
Test-NetConnection -ComputerName vm01.internal.example -Port 3389
~~~

Nếu dùng cổng tùy chỉnh, thay 3389 bằng cổng listener thực tế. Lệnh này chỉ kiểm tra khả năng mở kết nối TCP từ client tới host; nó không xác nhận tài khoản được phép đăng nhập.

Trên máy đích, kiểm tra dịch vụ:

~~~powershell
Get-Service -Name TermService
Get-NetTCPConnection -State Listen
~~~

Sau khi xác định đúng lớp lỗi, kiểm tra Windows Security log, TerminalServices log và log của gateway. Không khắc phục timeout bằng cách mở RDP ra toàn Internet; hãy sửa đúng route hoặc rule nguồn.

## 14. Mẫu thiết kế cho Windows VM production

Một cấu hình tham khảo cho VM production có thể gồm:

1. VM đặt trong private subnet, không có public IP dành cho RDP.
2. Quản trị viên truy cập qua VPN có MFA hoặc Cloud Bastion/RD Gateway được phê duyệt.
3. Security Group chỉ cho phép RDP từ subnet quản trị hoặc gateway.
4. Windows bật NLA, dùng TLS certificate hợp lệ và nhận bản vá định kỳ.
5. Người dùng được quản lý bằng AD DS hoặc Entra ID theo kiến trúc tổ chức.
6. Nhóm RDP riêng cấp quyền đăng nhập; nhóm local Administrators chỉ dành cho quản trị viên được phê duyệt.
7. Local admin password được quản lý bằng Windows LAPS.
8. MFA, Conditional Access và JIT access được áp dụng ở các lớp hỗ trợ.
9. Clipboard, drive redirection và các thiết bị chuyển hướng được giới hạn theo nhu cầu.
10. Windows Security log, TerminalServices log và cloud audit log được chuyển về hệ thống tập trung.
11. Có quy trình onboarding, access review, offboarding và break-glass.
12. Có runbook kiểm tra kết nối, khôi phục quyền truy cập và điều tra đăng nhập bất thường.

## 15. Lỗi thường gặp và cách tránh

**Mở TCP 3389 ra Internet:** VM trở thành mục tiêu dò quét và tấn công credential. Dùng private access, VPN, RD Gateway hoặc Bastion; giới hạn nguồn truy cập.

**Chỉ đổi cổng RDP:** bot quét cổng vẫn có thể tìm ra dịch vụ. Giữ trọng tâm ở network isolation, NLA, MFA, patching và least privilege.

**Dùng chung tài khoản Administrator:** khó xác định ai thực hiện thao tác và khó thu hồi quyền từng người. Dùng danh tính cá nhân, nhóm truy cập và audit.

**Dùng cùng local admin password trên nhiều VM:** lộ một máy có thể ảnh hưởng nhiều máy. Dùng Windows LAPS và mật khẩu duy nhất theo máy.

**Thêm mọi người vào Administrators để sửa lỗi đăng nhập:** cấp quyền quá mức và tăng tác động khi tài khoản bị xâm phạm. Cấp quyền RDP riêng qua nhóm phù hợp.

**Tắt NLA để xử lý client cũ:** làm giảm lớp bảo vệ trước khi tạo phiên. Ưu tiên cập nhật client hoặc sửa tương thích; chỉ dùng ngoại lệ có thời hạn và được phê duyệt nếu thật sự cần.

**Bỏ qua cảnh báo chứng thư:** có thể kết nối tới host giả mạo hoặc sai máy. Xác minh danh tính server và trust chain.

**Lưu credential trong file RDP hoặc máy dùng chung:** credential có thể bị người khác lấy. Dùng xác thực được quản lý, MFA và thiết bị quản trị chuyên dụng.

**Không thu hồi quyền sau khi hỗ trợ sự cố:** quyền tạm thời có thể tồn tại lâu dài. Gắn thời hạn và tự động thu hồi sau khi ticket kết thúc.

**Không xem log:** tấn công password spraying hoặc tài khoản bị lạm dụng có thể không được phát hiện. Thu thập log tập trung và cảnh báo hành vi bất thường.

## 16. Checklist bảo vệ truy cập Windows qua RDP

- [ ] VM không mở RDP trực tiếp cho toàn Internet.
- [ ] Đường truy cập dùng VPN, RD Gateway hoặc Bastion được phê duyệt.
- [ ] Security Group/NSG và Windows Firewall giới hạn nguồn truy cập.
- [ ] NLA được bật và client tương thích.
- [ ] TLS certificate của RDP host hợp lệ và được tin cậy.
- [ ] Danh tính người dùng được quản lý tập trung khi phù hợp.
- [ ] Quyền RDP được cấp qua nhóm và theo nguyên tắc least privilege.
- [ ] Allow/Deny logon rights và GPO đã được kiểm tra.
- [ ] Tài khoản local admin có mật khẩu duy nhất và được quản lý bằng LAPS.
- [ ] MFA được áp dụng tại lớp truy cập hỗ trợ.
- [ ] Credential Guard hoặc cơ chế bảo vệ credential phù hợp đã được đánh giá.
- [ ] Clipboard, drive và thiết bị chuyển hướng được giới hạn.
- [ ] Có timeout cho phiên idle/disconnected và quy tắc sign out.
- [ ] Security log, TerminalServices log và cloud audit log được lưu tập trung.
- [ ] Có quy trình onboarding, access review, offboarding và JIT.
- [ ] Đã thử nghiệm khôi phục truy cập trong môi trường kiểm soát.

RDP là kênh quản trị quan trọng đối với Windows VM, nhưng độ an toàn phụ thuộc vào cả đường mạng, xác thực, quyền đăng nhập và cách bảo vệ phiên làm việc. Hãy đưa RDP vào mạng quản trị riêng, bật NLA và TLS, dùng danh tính cá nhân hoặc nhóm được quản lý, áp dụng MFA tại điểm truy cập phù hợp, xoay vòng local admin bằng LAPS và giám sát log. Cấp quyền theo nhiệm vụ và thu hồi khi hết nhu cầu giúp giảm nguy cơ tài khoản bị lạm dụng trong suốt vòng đời máy ảo.
