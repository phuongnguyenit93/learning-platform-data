# Không thể SSH hoặc RDP: kiểm tra danh tính, mạng và dịch vụ đăng nhập

Khi không thể kết nối SSH hoặc RDP tới một máy ảo trên đám mây, nguyên nhân có thể nằm ở nhiều lớp: danh tính không hợp lệ, máy chủ không sẵn sàng, DNS hoặc route sai, firewall chặn cổng, dịch vụ đăng nhập dừng, hoặc hệ điều hành từ chối phiên làm việc. Thông báo lỗi ở máy khách thường chỉ phản ánh nơi kết nối bị dừng, chưa chắc chỉ ra nguyên nhân gốc.

Cách xử lý hiệu quả là xác định kết nối thất bại ở giai đoạn nào, sau đó kiểm tra từng lớp theo thứ tự từ máy khách tới máy chủ. SSH thường dùng TCP cổng 22; RDP thường dùng TCP cổng 3389 và có thể dùng UDP cho một số chức năng. Cổng thực tế có thể đã được đổi theo chính sách của hệ thống. Không nên mở rộng quyền truy cập mạng hoặc tắt cơ chế bảo vệ chỉ để thử kết nối; hãy xác minh đúng nguồn, đích, danh tính và dịch vụ cần thiết.

Bài học này hướng dẫn chẩn đoán lỗi SSH trên Linux và RDP trên Windows trong môi trường máy tính đám mây. Sau bài học, bạn có thể:

- Phân loại lỗi theo danh tính, phân giải tên, kết nối TCP, bắt tay giao thức và tạo phiên đăng nhập.
- Kiểm tra tài khoản, khóa SSH, mật khẩu, MFA, quyền đăng nhập và chính sách máy chủ.
- Xác minh địa chỉ IP, DNS, route, VPN, bastion, security group, firewall và network ACL.
- Kiểm tra dịch vụ SSH hoặc Remote Desktop, log hệ điều hành và trạng thái máy ảo.
- Dùng console hoặc kênh quản trị ngoài băng để phục hồi khi không thể đăng nhập từ mạng.
- Khôi phục kết nối an toàn và ghi nhận nguyên nhân để ngăn sự cố tái diễn.

## 1. Xác định chính xác kết nối thất bại ở đâu

Một phiên đăng nhập từ xa có thể được chia thành các giai đoạn:

1. **Xác định đích:** máy khách phân giải tên máy thành địa chỉ IP và chọn địa chỉ/cổng cần kết nối.
2. **Định tuyến:** gói tin đi qua mạng máy khách, VPN hoặc bastion, route của cloud, subnet và network interface của VM.
3. **Thiết lập TCP:** máy khách mở kết nối tới cổng SSH hoặc RDP; firewall và security group phải cho phép luồng phù hợp.
4. **Bắt tay giao thức:** hai bên thương lượng SSH hoặc RDP, xác minh host key/chứng chỉ và các thuật toán.
5. **Xác thực danh tính:** máy chủ kiểm tra public key, mật khẩu, certificate, MFA hoặc cơ chế xác thực được cấu hình.
6. **Cấp quyền và tạo phiên:** tài khoản được phép đăng nhập, shell hoặc desktop session khởi tạo thành công.

Phân biệt lỗi ở từng giai đoạn giúp tránh thay đổi sai lớp. Ví dụ:

| Triệu chứng | Giai đoạn có khả năng lỗi | Hướng kiểm tra đầu tiên |
|---|---|---|
| DNS name không phân giải | Xác định đích | DNS resolver, bản ghi và search domain |
| Connection timed out | Định tuyến hoặc TCP | IP đích, route, VPN, security group và firewall |
| Connection refused | TCP tới máy đích nhưng không có listener hoặc bị từ chối chủ động | Dịch vụ SSH/RDP, cổng lắng nghe và firewall máy chủ |
| SSH báo Permission denied | Xác thực hoặc chính sách tài khoản | Username, private key, authorized_keys, certificate, AllowUsers/AllowGroups |
| RDP báo credentials không hợp lệ | Xác thực | Tên miền/tài khoản, mật khẩu, NLA, quyền đăng nhập và trạng thái tài khoản |
| Host key hoặc certificate warning | Bắt tay và xác minh máy chủ | Fingerprint, chứng chỉ, DNS và việc thay thế VM |
| Đăng nhập được nhưng phiên bị đóng | Tạo phiên hoặc workload | Shell/profile, desktop session, tài nguyên và log hệ điều hành |

Thông báo lỗi là manh mối, không phải kết luận. Một firewall có thể gửi TCP reset khiến máy khách báo refused; một dịch vụ không lắng nghe cũng tạo ra biểu hiện tương tự. Hãy kết hợp kết quả từ máy khách, console cloud và log máy chủ.

## 2. Kiểm tra trạng thái máy ảo và đường truy cập trên cloud

Trước khi thay đổi cấu hình trong hệ điều hành, xác minh máy ảo và mạng cloud:

- Instance đang ở trạng thái running và không có sự kiện dừng, reboot, host maintenance hoặc lỗi cấp phát.
- System health check và instance health check đạt nếu nhà cung cấp có cung cấp.
- Network interface gắn đúng VM, đúng subnet và đúng security group/firewall policy.
- Địa chỉ IP hiện tại đúng với địa chỉ mà người dùng đang kết nối. Public IP động có thể đã thay đổi sau khi stop/start.
- Route table có đường đi giữa mạng nguồn và subnet đích.
- Network ACL, firewall cloud hoặc policy mạng trung gian cho phép cả chiều đi và chiều về của kết nối.
- Nếu VM nằm trong private subnet, người dùng có VPN, bastion, jump host hoặc kênh quản trị riêng phù hợp.

Không phải mọi VM đều cần public IP. Máy chủ production thường nên nằm trong private network và chỉ nhận kết nối quản trị từ VPN, bastion hoặc dịch vụ quản trị được kiểm soát. Nếu IP đích thay đổi, cập nhật DNS hoặc inventory theo quy trình thay đổi được phê duyệt.

### Xác định đường đi của kết nối

Vẽ đường đi từ máy khách tới VM:

~~~text
Máy quản trị
    |
    +-- VPN hoặc mạng doanh nghiệp
            |
            +-- Bastion / access gateway (nếu có)
                    |
                    +-- Cloud route / firewall / security group
                            |
                            +-- Network interface của VM
                                    |
                                    +-- Firewall hệ điều hành
                                            |
                                            +-- sshd hoặc Remote Desktop Services
~~~

Mỗi chặng có thể có chính sách riêng. Một security group cho phép cổng 22 không có nghĩa firewall trong Linux cũng cho phép. Tương tự, Windows Firewall có thể chặn RDP dù rule ở cloud đã mở.

### Kiểm tra địa chỉ IP và DNS

Trên Linux hoặc macOS:

~~~bash
getent hosts vm-01.example.internal
dig +short vm-01.example.internal
ip route get 10.20.1.15
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName vm-01.example.internal
Test-NetConnection vm-01.example.internal -Port 3389
Test-NetConnection vm-01.example.internal -Port 22
~~~

Thay tên miền, địa chỉ và cổng bằng giá trị thực tế. Nếu DNS trả về nhiều địa chỉ, xác định máy khách đang thử địa chỉ nào. So sánh kết quả phân giải trong mạng VPN với khi ở ngoài VPN; split-horizon DNS có thể trả về các địa chỉ khác nhau theo vị trí.

Nếu kết nối bằng IP hoạt động nhưng bằng hostname không hoạt động, tập trung vào DNS, search suffix, resolver và cache. Nếu hostname phân giải đúng nhưng TCP không mở được, tiếp tục kiểm tra route và firewall.

## 3. Kiểm tra khả năng kết nối TCP từ máy khách

### Với SSH

~~~bash
nc -vz -w 5 vm-01.example.internal 22
~~~

Hoặc dùng SSH ở chế độ verbose:

~~~bash
ssh -vvv -o ConnectTimeout=8 alice@vm-01.example.internal
~~~

Verbose output cho biết máy khách đã phân giải tên, chọn địa chỉ, mở socket, nhận host key và thử các phương thức xác thực nào. Không chia sẻ log chưa lọc nếu có thông tin nhạy cảm như username, hostname nội bộ hoặc địa chỉ mạng.

### Với RDP

Trên Windows:

~~~powershell
Test-NetConnection vm-win-01.example.internal -Port 3389 -InformationLevel Detailed
~~~

Kết quả quan trọng là TCP connect có thành công hay không, địa chỉ đích được chọn và interface/route nguồn. Lệnh này chỉ kiểm tra TCP; nó không xác minh RDP, NLA, chứng chỉ hoặc quyền đăng nhập.

### Diễn giải kết quả TCP

- **TcpTestSucceeded = True:** đường TCP tới cổng đã mở. Tiếp tục kiểm tra giao thức, xác thực và chính sách đăng nhập.
- **Timed out:** gói tin có thể bị drop ở route, VPN, firewall, security group hoặc máy chủ không phản hồi. Kiểm tra từng chặng và flow log nếu có.
- **Connection refused:** đích có thể reachable nhưng không có dịch vụ lắng nghe, dịch vụ dùng cổng khác hoặc firewall gửi reset.
- **No route to host / Network is unreachable:** kiểm tra route, subnet, VPN, gateway và interface máy khách.

Ping không phải phép thử thay thế cho TCP. ICMP có thể bị chặn trong khi SSH/RDP hoạt động, hoặc ping thành công nhưng cổng TCP vẫn bị chặn.

## 4. Kiểm tra danh tính và quyền đăng nhập

Khi TCP đã kết nối nhưng xác thực thất bại, hãy kiểm tra danh tính trước khi thay đổi mạng.

### SSH trên Linux

Kiểm tra các yếu tố:

- Username có đúng với tài khoản trên VM không? Username của image cloud có thể khác nhau theo bản phân phối và image do tổ chức tạo.
- Máy khách đang dùng đúng private key không?
- Public key tương ứng đã được cài vào tài khoản đích hoặc được SSH CA tin cậy chưa?
- Private key có passphrase và đã được nạp vào SSH agent chưa?
- Certificate còn hiệu lực, đúng principal và được ký bởi CA mà server tin cậy không?
- Tài khoản có bị khóa, hết hạn, thiếu shell hợp lệ hoặc bị chặn bởi AllowUsers/AllowGroups không?
- Home directory, thư mục .ssh và authorized_keys có owner/mode đúng không?

Chỉ định identity rõ ràng:

~~~bash
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes alice@vm-01.example.internal
ssh-add -l
ssh-keygen -lf ~/.ssh/id_ed25519.pub
~~~

Trên máy chủ, khi có console hoặc quyền quản trị khác:

~~~bash
id alice
getent passwd alice
sudo passwd -S alice
sudo chage -l alice
sudo namei -l /home/alice/.ssh/authorized_keys
sudo sshd -T | grep -Ei 'pubkeyauthentication|passwordauthentication|allowusers|allowgroups|denyusers|denygroups'
~~~

Đường dẫn home có thể khác với ví dụ. Kiểm tra owner và mode theo chính sách hệ thống; thông thường thư mục .ssh chỉ cho chủ sở hữu truy cập và authorized_keys không cho nhóm/người khác ghi.

Khóa mật khẩu bằng passwd không nhất thiết vô hiệu hóa SSH public key. Nếu tài khoản có authorized_keys hoặc được xác thực bằng certificate, cần thu hồi đúng phương thức đó. Ngược lại, việc xóa khóa khỏi authorized_keys không thu hồi một certificate còn hợp lệ nếu server vẫn tin cậy CA và principal.

### RDP trên Windows

Kiểm tra:

- Username có thuộc đúng máy cục bộ hoặc domain không? Có thể cần dạng DOMAIN\\username hoặc username@domain.
- Mật khẩu có còn hiệu lực, tài khoản có bị khóa hoặc hết hạn không?
- Người dùng có quyền đăng nhập qua Remote Desktop Services không?
- Người dùng hoặc nhóm có nằm trong Remote Desktop Users hoặc nhóm quản trị được phép không?
- Chính sách domain có chặn đăng nhập RDP, yêu cầu MFA hoặc giới hạn máy nguồn không?
- Network Level Authentication (NLA) có được hỗ trợ bởi máy khách và đường xác thực không?
- Máy có tham gia domain và liên lạc được với domain controller không?

Trên Windows PowerShell với quyền phù hợp:

~~~powershell
Get-LocalUser
Get-LocalGroupMember -Group "Remote Desktop Users"
Get-Service -Name TermService
Get-NetFirewallRule -DisplayGroup "Remote Desktop"
~~~

Nếu dùng domain, kiểm tra nhóm domain và chính sách Group Policy có hiệu lực. Đừng thêm người dùng vào nhóm Administrators chỉ để giải quyết lỗi RDP; cấp đúng quyền Remote Desktop và quyền truy cập tài nguyên cần thiết.

### Thời gian và MFA

Certificate SSH, Kerberos, TLS và nhiều hệ thống MFA phụ thuộc thời gian chính xác. Nếu đồng hồ máy khách, VM hoặc domain controller lệch đáng kể, certificate có thể bị xem là chưa hiệu lực/hết hạn hoặc Kerberos từ chối xác thực. Kiểm tra đồng bộ thời gian và NTP trước khi thay certificate hoặc reset mật khẩu.

Với MFA, xác minh người dùng đã đăng ký đúng phương thức, thiết bị còn hoạt động và policy áp dụng cho đúng nhóm. Không tắt MFA trên toàn hệ thống để xử lý lỗi của một tài khoản.

## 5. Kiểm tra dịch vụ SSH trên Linux

Nếu TCP cổng 22 bị từ chối hoặc VM reachable nhưng không có SSH handshake, kiểm tra dịch vụ:

~~~bash
sudo systemctl status sshd
sudo systemctl status ssh
sudo ss -lntp | grep ':22'
sudo sshd -t
~~~

Tên unit phụ thuộc bản phân phối; thường là sshd trên RHEL-family và ssh trên Ubuntu/Debian. Dùng đúng tên service của máy.

Nếu service dừng:

1. Đọc log trước khi restart.
2. Kiểm tra cấu hình bằng sshd -t.
3. Xác định nguyên nhân như lỗi cú pháp, thiếu host key, quyền file hoặc port bị chiếm.
4. Sửa thay đổi đã xác định và kiểm tra lại.
5. Khởi động hoặc reload dịch vụ theo quy trình.
6. Kiểm tra socket lắng nghe và thử kết nối từ một máy khách được phép.

Log thường có trong journal:

~~~bash
sudo journalctl -u sshd --since "30 minutes ago"
sudo journalctl -u ssh --since "30 minutes ago"
~~~

Kiểm tra các thiết lập thường gây khóa truy cập:

- Port có đổi khỏi 22 không?
- ListenAddress có giới hạn vào IP/interface không còn tồn tại không?
- AllowUsers hoặc AllowGroups có loại tài khoản ra không?
- AuthenticationMethods có yêu cầu kết hợp key và MFA không?
- AuthorizedKeysFile có trỏ tới đường dẫn khác không?
- TrustedUserCAKeys, AuthorizedPrincipalsFile hoặc RevokedKeys có được cập nhật đúng không?
- PAM, SELinux hoặc quyền home directory có ngăn xác thực không?

Không ghi đè toàn bộ sshd_config bằng một mẫu trên mạng. Hãy xem cấu hình hiệu lực, include file và thay đổi gần nhất. Nếu cần sửa, giữ phiên quản trị hiện tại mở, kiểm tra cú pháp và thử phiên mới trước khi đóng phiên cũ.

### Kiểm tra firewall Linux

Tùy hệ thống, firewall có thể được quản lý bằng nftables, firewalld hoặc UFW:

~~~bash
sudo nft list ruleset
sudo firewall-cmd --list-all
sudo ufw status verbose
~~~

Chỉ một số lệnh phù hợp với mỗi máy. Xác minh rule cho phép đúng cổng SSH từ đúng mạng quản trị. Không flush toàn bộ ruleset hoặc tắt firewall để thử kết nối trên máy production; thay đổi như vậy có thể làm lộ dịch vụ khác.

## 6. Kiểm tra dịch vụ RDP trên Windows

RDP thường cần Remote Desktop Services hoạt động, listener trên đúng cổng và Windows Firewall cho phép kết nối từ nguồn hợp lệ.

Trên Windows Server, kiểm tra dịch vụ:

~~~powershell
Get-Service -Name TermService
Get-NetTCPConnection -LocalPort 3389 -State Listen
Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections
~~~

Giá trị fDenyTSConnections bằng 1 thường cho biết kết nối Remote Desktop bị từ chối ở thiết lập hệ thống; bằng 0 cho biết thiết lập cho phép RDP. Group Policy, firewall hoặc chính sách khác vẫn có thể chặn.

Kiểm tra rule firewall:

~~~powershell
Get-NetFirewallRule -DisplayGroup "Remote Desktop" |
    Select-Object DisplayName, Enabled, Profile, Direction, Action
~~~

Kiểm tra listener và cổng thực tế. Mặc định là 3389, nhưng tổ chức có thể dùng cổng khác. Nếu đổi cổng, phải đồng bộ listener, firewall, security group, tài liệu kết nối và hệ thống giám sát.

Các log liên quan thường nằm trong Event Viewer:

- Windows Logs → System: lỗi dịch vụ, driver và khởi động.
- Applications and Services Logs → Microsoft → Windows → TerminalServices-LocalSessionManager.
- Applications and Services Logs → Microsoft → Windows → TerminalServices-RemoteConnectionManager.
- Security: sự kiện đăng nhập thành công/thất bại nếu audit policy ghi nhận.

Có thể đọc nhanh một số sự kiện gần đây bằng PowerShell:

~~~powershell
Get-WinEvent -LogName "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational" -MaxEvents 50
Get-WinEvent -LogName "Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational" -MaxEvents 50
~~~

Nếu RDP bắt tay được nhưng thất bại ở NLA/CredSSP, kiểm tra domain connectivity, thời gian, trạng thái tài khoản, cập nhật bảo mật và khả năng tương thích của client. Không hạ mức bảo mật CredSSP hoặc tắt NLA trên toàn hệ thống như một bước thử nghiệm chung. Nếu có ngoại lệ tạm thời được phê duyệt, phải giới hạn phạm vi, thời gian và có kế hoạch khôi phục cấu hình.

## 7. Kiểm tra firewall, security group và route

Để kết nối quản trị hoạt động, cần có luồng mạng hai chiều phù hợp. Với TCP, gói SYN đi từ máy khách tới máy chủ; phản hồi SYN-ACK phải quay lại được qua route và chính sách mạng. Network ACL stateless có thể cần rule cho cả cổng đích và ephemeral port ở chiều trả về. Security group stateful thường tự theo dõi trạng thái kết nối, nhưng vẫn cần xác minh hành vi cụ thể của nền tảng.

### Ma trận kiểm tra

| Lớp mạng | SSH | RDP | Câu hỏi cần trả lời |
|---|---|---|---|
| Máy khách | TCP tới cổng SSH đã cấu hình | TCP tới cổng RDP đã cấu hình | Máy khách có route và dùng đúng IP/cổng không? |
| VPN/bastion | Cho phép nguồn quản trị tới VM | Cho phép nguồn quản trị tới VM | Tunnel, policy và jump path còn hoạt động không? |
| Cloud security group | Cho phép TCP 22 hoặc cổng tùy chỉnh từ CIDR quản trị | Cho phép TCP 3389 hoặc cổng tùy chỉnh từ CIDR quản trị | Rule có gắn đúng NIC/VM và đúng nguồn không? |
| Network ACL/firewall mạng | Cho phép luồng đi và trả về | Cho phép luồng đi và trả về | Có rule deny ưu tiên cao hơn hoặc thiếu ephemeral return path không? |
| Firewall hệ điều hành | Cho phép sshd nhận kết nối | Cho phép Remote Desktop nhận kết nối | Profile, interface và source scope có đúng không? |
| Dịch vụ | sshd lắng nghe | TermService/listener hoạt động | Dịch vụ có bind đúng IP và port không? |

Ưu tiên rule nguồn là dải IP quản trị, VPN hoặc bastion đã biết. Tránh rule mở 0.0.0.0/0 hoặc ::/0 cho SSH/RDP. Nếu cần truy cập tạm thời từ một địa chỉ mới, hãy dùng rule hẹp, có thời hạn và gỡ sau khi hoàn tất.

### Dùng flow log và packet capture

Nếu cloud có VPC/VNet flow logs hoặc firewall logs, kiểm tra xem luồng tới IP/port đích bị ACCEPT hay REJECT và ở interface nào. Flow log giúp xác định lớp mạng chặn nhưng không chứng minh dịch vụ đang lắng nghe.

Trên Linux, nếu được phép và cần phân tích sâu, có thể quan sát gói tin:

~~~bash
sudo tcpdump -ni any 'tcp port 22'
~~~

Nếu thấy SYN tới nhưng không có SYN-ACK, kiểm tra firewall host, listener, route trả về và trạng thái kernel. Nếu không thấy SYN, lỗi có thể nằm trước VM: máy khách, VPN, route, security group hoặc network ACL. Packet capture có thể chứa metadata nhạy cảm; lưu và chia sẻ theo chính sách bảo mật.

## 8. DNS, địa chỉ IP và host identity

VM có thể được thay thế hoặc cấp lại IP sau thao tác stop/start, scale-in/scale-out hoặc rebuild. Một hostname cũ có thể trỏ tới IP không còn thuộc máy dự kiến. Trước khi sửa firewall hoặc key, xác minh:

- DNS A/AAAA record đang trả về địa chỉ nào?
- IP đó có gắn với đúng instance/network interface trong console không?
- DNS TTL và cache trên máy khách có làm chậm cập nhật không?
- Máy đang kết nối qua private IP hay public IP?
- Có NAT, proxy hoặc load balancer ở giữa không?

Với SSH, nếu host key thay đổi, không xóa cảnh báo một cách máy móc. Đối chiếu fingerprint mới qua console, hệ thống quản lý cấu hình hoặc kênh tin cậy. Khi VM đã được tạo lại hợp lệ, cập nhật known_hosts theo quy trình.

Với RDP, client có thể cảnh báo certificate của máy chủ không được tin cậy, hết hạn hoặc hostname không khớp. Xác minh chứng chỉ và tên máy chủ; không bỏ qua cảnh báo trên máy production chỉ để tiếp tục kết nối.

## 9. Khi không thể đăng nhập: dùng kênh quản trị ngoài băng

Nếu SSH/RDP không hoạt động, cần một kênh quản trị độc lập với chính đường truy cập đang lỗi. Tùy nền tảng, có thể dùng:

- Serial console hoặc boot diagnostics của VM.
- Cloud run command/guest agent, nếu agent đã được cài và còn kết nối control plane.
- Session manager hoặc access gateway do nhà cung cấp quản lý.
- Rescue mode, recovery image hoặc detach boot volume để kiểm tra từ một máy cứu hộ.
- Console của hypervisor hoặc công cụ quản trị nội bộ được phê duyệt.

Kênh ngoài băng cần được cấp quyền chặt, ghi log và bảo vệ bằng MFA. Nếu guest agent cũng bị lỗi sau cập nhật, run command có thể không hoạt động; cần có phương án console hoặc rescue đã chuẩn bị trước.

### Quy trình phục hồi an toàn

1. Xác minh instance ID và vùng để chắc chắn đang thao tác đúng máy.
2. Giữ nguyên phiên quản trị còn hoạt động nếu có; tránh reboot liên tục.
3. Thu thập console output, boot log, flow log và thời điểm thay đổi.
4. Xác định lớp lỗi: danh tính, mạng, firewall, dịch vụ hay hệ điều hành.
5. Thay đổi tối thiểu để khôi phục đúng đường truy cập; không tắt hàng loạt biện pháp bảo vệ.
6. Kiểm tra cấu hình và mở phiên kết nối mới từ mạng quản trị hợp lệ.
7. Xác nhận quyền của tài khoản, log và trạng thái dịch vụ.
8. Gỡ rule tạm, thu hồi thông tin xác thực không còn cần và ghi nhận nguyên nhân.

Ví dụ, nếu SSH bị khóa do sửa sai AllowGroups, có thể dùng serial console để khôi phục file cấu hình từ bản chuẩn, chạy sshd -t, reload dịch vụ và thử kết nối bằng một tài khoản đã được cấp quyền. Không nên mở cổng SSH toàn Internet để né lỗi AllowGroups.

## 10. Cây quyết định chẩn đoán

~~~mermaid
flowchart TD
    A["Không thể SSH hoặc RDP"] --> B["VM running và health checks đạt?"]
    B -- "Không" --> C["Kiểm tra trạng thái cloud, boot và console"]
    B -- "Có" --> D["Hostname phân giải đúng IP?"]
    D -- "Không" --> E["Kiểm tra DNS, cache, IP và record"]
    D -- "Có" --> F["TCP tới đúng cổng thành công?"]
    F -- "Không" --> G["Kiểm tra route, VPN, bastion, SG, ACL và host firewall"]
    F -- "Có" --> H["Bắt tay SSH/RDP thành công?"]
    H -- "Không" --> I["Kiểm tra listener, host key/certificate, TLS/NLA và log"]
    H -- "Có" --> J["Xác thực danh tính thành công?"]
    J -- "Không" --> K["Kiểm tra username, key/password, MFA, account policy"]
    J -- "Có" --> L["Phiên shell/desktop tạo thành công?"]
    L -- "Không" --> M["Kiểm tra quyền đăng nhập, profile, shell, session và tài nguyên"]
    L -- "Có" --> N["Theo dõi, ghi nhận và đóng sự cố"]
~~~

Cây quyết định là hướng dẫn phân loại. Trong thực tế, có thể nhiều lỗi cùng tồn tại, chẳng hạn DNS trỏ sai IP đồng thời security group của VM mới chưa được cấu hình.

## 11. Ví dụ 1: SSH timeout sau khi thay đổi security group

Một kỹ sư kết nối tới Linux VM qua VPN. Trước đây SSH hoạt động, nhưng sau khi nhóm thay đổi security group, lệnh SSH chờ rồi timeout.

**Bước 1: Xác nhận VM.** Console cho thấy VM running và health checks đạt. Địa chỉ private IP không đổi.

**Bước 2: Xác minh DNS và TCP.** Hostname phân giải đúng private IP. Lệnh Test-NetConnection hoặc nc tới cổng 22 thất bại.

**Bước 3: Kiểm tra đường mạng.** VPN vẫn kết nối; route tới subnet còn tồn tại. Flow log cho thấy luồng từ CIDR VPN tới TCP 22 bị REJECT.

**Bước 4: Sửa rule đúng phạm vi.** Nhóm xác nhận CIDR nguồn quản trị hợp lệ và cập nhật security group cho phép TCP 22 từ dải đó. Không mở cổng cho toàn Internet.

**Bước 5: Kiểm tra tiếp lớp máy chủ.** TCP mở thành công, nhưng nếu SSH vẫn từ chối, tiếp tục kiểm tra sshd, host key và danh tính thay vì tiếp tục chỉnh security group.

Bài học: timeout thường gợi ý vấn đề đường mạng hoặc gói tin bị drop. Flow log và phép thử TCP giúp xác định lớp cần xử lý.

## 12. Ví dụ 2: RDP kết nối được nhưng đăng nhập thất bại

Một quản trị viên có thể mở TCP 3389 tới Windows VM, nhưng Remote Desktop báo không thể đăng nhập bằng thông tin xác thực hiện tại.

**Bước 1: Kiểm tra TCP.** Test-NetConnection trả về TcpTestSucceeded=True, cho thấy đường TCP tới cổng hoạt động.

**Bước 2: Xác định loại tài khoản.** Quản trị viên xác nhận tài khoản thuộc domain hay local và dùng đúng định dạng username. Nếu là domain account, máy cần liên lạc được với domain controller.

**Bước 3: Kiểm tra trạng thái tài khoản và quyền.** Xác minh tài khoản không bị khóa/hết hạn và thuộc nhóm được phép đăng nhập RDP. Kiểm tra chính sách Deny log on through Remote Desktop Services có áp dụng không.

**Bước 4: Kiểm tra NLA và log.** Đọc log TerminalServices và Security để xác định lỗi xảy ra ở giai đoạn xác thực hay tạo phiên. Kiểm tra thời gian hệ thống và domain connectivity nếu có lỗi Kerberos.

**Bước 5: Khôi phục đúng chính sách.** Sửa nhóm hoặc policy đã cấu hình sai theo quy trình thay đổi, sau đó thử lại từ máy quản trị. Không cấp quyền Administrator hoặc tắt NLA một cách rộng rãi chỉ để làm kết nối thành công.

Bài học: khi TCP đã mở, cần chuyển trọng tâm sang xác thực, quyền đăng nhập, NLA và domain.

## 13. Những sai lầm thường gặp

1. **Mở cổng 22/3389 ra toàn Internet:** làm tăng bề mặt tấn công và không giải quyết được lỗi danh tính hoặc dịch vụ.
2. **Chỉ thử ping:** ICMP không xác minh được TCP, SSH hay RDP.
3. **Đổi mật khẩu ngay khi gặp lỗi:** có thể không liên quan nếu kết nối chưa tới giai đoạn xác thực.
4. **Xóa known_hosts khi thấy host key warning:** có thể bỏ qua dấu hiệu giả mạo máy chủ.
5. **Tắt firewall hoặc NLA để thử:** có thể làm giảm bảo mật và che mất nguyên nhân gốc.
6. **Dùng sai IP sau khi VM được tạo lại:** DNS hoặc inventory có thể chưa cập nhật.
7. **Sửa sshd_config mà không kiểm tra:** lỗi cú pháp hoặc AllowGroups sai có thể khóa toàn bộ quyền SSH.
8. **Khóa mật khẩu nhưng quên public key/certificate:** tài khoản vẫn có thể đăng nhập qua phương thức khác.
9. **Bỏ qua chiều trả về của network ACL:** TCP handshake không hoàn tất dù rule chiều đi đã đúng.
10. **Cấp quyền Administrator/root quá rộng:** giải quyết tạm thời nhưng tạo rủi ro quyền hạn lâu dài.

## 14. Checklist xử lý sự cố SSH/RDP

- [ ] Xác nhận đúng VM, instance ID, vùng, trạng thái running và health checks.
- [ ] Xác minh hostname, IP, port và DNS record hiện tại.
- [ ] Kiểm tra VPN, bastion, route, security group, network ACL và firewall cloud.
- [ ] Kiểm tra TCP tới đúng cổng từ đúng máy khách/mạng nguồn.
- [ ] Xác minh host key hoặc certificate máy chủ qua kênh tin cậy.
- [ ] Kiểm tra dịch vụ SSH/RDP, listener và firewall trong hệ điều hành.
- [ ] Kiểm tra username, tài khoản, public key/certificate, mật khẩu và MFA.
- [ ] Kiểm tra nhóm, quyền đăng nhập, sudo hoặc Remote Desktop Users.
- [ ] Đọc log máy chủ và log mạng tại đúng thời điểm thử kết nối.
- [ ] Dùng console hoặc kênh quản trị ngoài băng nếu đường đăng nhập chính bị lỗi.
- [ ] Thử lại từ phiên mới sau khi sửa và xác minh chức năng cần dùng.
- [ ] Thu hồi rule tạm, khôi phục chính sách bảo mật và ghi nhận nguyên nhân.

## 15. Bài tập vận dụng

Một nhóm vận hành có một Linux VM và một Windows VM trong private subnet. Người quản trị kết nối qua VPN. Sáng nay, SSH tới Linux VM báo timeout; RDP tới Windows VM mở được TCP 3389 nhưng từ chối thông tin đăng nhập.

1. Hãy xác định thứ tự kiểm tra cho từng máy và giải thích vì sao hai lỗi cần đi theo hai nhánh khác nhau.
2. Với Linux VM, những thông tin nào cần kiểm tra trong console cloud, flow log và firewall trước khi truy cập hệ điều hành?
3. Với Windows VM, cần kiểm tra username/domain, trạng thái tài khoản, nhóm đăng nhập, NLA và log nào?
4. Nếu Linux VM không thể truy cập qua SSH nhưng guest agent còn hoạt động, có thể dùng kênh nào để kiểm tra sshd và firewall?
5. Sau khi khôi phục, nhóm cần làm gì để không phải mở SSH/RDP công khai trong lần xử lý tiếp theo?

Gợi ý: timeout trên Linux cần ưu tiên xác minh IP, route, VPN, security group, ACL và firewall host trước khi thay đổi khóa. TCP 3389 đã mở trên Windows nên tập trung vào danh tính, trạng thái tài khoản, quyền RDP, NLA và domain connectivity. Dùng run command hoặc session manager nếu được cấu hình và cấp quyền. Duy trì VPN/bastion, rule nguồn hẹp, MFA và kênh console dự phòng.

## Kết luận

Chẩn đoán lỗi SSH/RDP hiệu quả bắt đầu bằng việc xác định kết nối dừng ở DNS, route, TCP, bắt tay, xác thực hay tạo phiên. Kiểm tra trạng thái VM, danh tính, security group, firewall và dịch vụ theo đúng lớp giúp giới hạn thay đổi và tránh mở rộng quyền truy cập không cần thiết. Khi đường đăng nhập chính không hoạt động, dùng console hoặc kênh quản trị ngoài băng đã được bảo vệ, sau đó xác minh kết nối và quyền trước khi đóng sự cố.
