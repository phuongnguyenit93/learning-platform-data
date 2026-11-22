# Quản lý SSH, RDP và truy cập quản trị an toàn

Một nhóm kỹ thuật vận hành Azure Virtual Machines (VM) thường cần đăng nhập vào máy Linux bằng SSH hoặc vào máy Windows bằng Remote Desktop Protocol (RDP) để cập nhật phần mềm, đọc log và xử lý sự cố. Nếu mở thẳng cổng 22 hoặc 3389 ra Internet và cho phép bất kỳ IP nào thử đăng nhập, máy ảo trở thành mục tiêu của quét cổng, dò mật khẩu và khai thác lỗ hổng. Ngược lại, khóa toàn bộ quyền truy cập mà không chuẩn bị đường khôi phục có thể khiến nhóm vận hành bị mất quyền quản trị khi cần xử lý sự cố khẩn cấp.

Bài học này hướng dẫn thiết kế **đường truy cập quản trị an toàn, có kiểm soát và có thể kiểm toán** cho cả Linux lẫn Windows VM trên Microsoft Azure. Trọng tâm gồm SSH key, RDP, Azure Bastion, kết nối mạng riêng, Network Security Group (NSG), Just-in-Time (JIT), Microsoft Entra ID, Azure RBAC, các phương án xử lý khi mất kết nối và quy trình vận hành lâu dài.

Bài thuộc chương **Máy ảo Azure** của module `CLOUD_PROVIDERS_AZURE`. Trong module này, bạn khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Quyết định về truy cập VM phải được thiết kế nhất quán với mạng, danh tính, giám sát và các yêu cầu của toàn hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **SSH**, **RDP**, **Azure Bastion**, **VPN/ExpressRoute** và truy cập trực tiếp qua public IP.
- Giải thích vì sao nên để VM dùng **private IP**, giới hạn đường quản trị và tránh mở cổng quản trị rộng ra Internet.
- Tạo cặp **SSH public/private key** và xử lý khóa riêng an toàn.
- Xác định cấu hình RDP, Network Level Authentication (NLA), firewall và quyền đăng nhập Windows.
- Áp dụng Azure RBAC và Microsoft Entra ID cho quản trị VM, phân biệt quyền trên Azure resource với quyền bên trong hệ điều hành.
- Thiết kế NSG, JIT và cơ chế cấp quyền quản trị đúng người, đúng thời điểm.
- Kiểm tra đường đi SSH/RDP bằng Azure Portal, Azure CLI và các lệnh chẩn đoán không phá hủy.
- Lập runbook khi không kết nối được máy ảo và khi nghi ngờ tài khoản bị lộ.
- Chọn biện pháp phù hợp với rủi ro, khả năng sẵn sàng và chi phí vận hành.

## 2. SSH và RDP hoạt động như thế nào?

### SSH dành cho Linux và các hệ thống hỗ trợ SSH

**Secure Shell (SSH)** thiết lập phiên quản trị được mã hóa giữa client và máy chủ. Với Linux VM, SSH thường sử dụng TCP **22**. Kết nối có thể dùng khóa công khai, mật khẩu hoặc các cơ chế xác thực mở rộng được máy chủ hỗ trợ.

```text
Máy quản trị            Kết nối SSH             Linux VM
SSH client   =================================> sshd :22
  |                                                      |
  |-- xác minh host key của server                       |
  |-- xác thực người dùng bằng key/identity               |
  |-- mở terminal hoặc kênh chuyển tiếp được cho phép    |
```

Điểm mạnh của SSH là tính linh hoạt khi vận hành qua terminal và automation. Nhưng phiên được mã hóa **không tự bảo đảm an toàn** nếu khóa riêng bị lộ, client không xác minh đúng host key, máy chủ cho phép xác thực yếu hoặc mạng mở cổng 22 cho mọi nguồn.

### RDP dành cho Windows

**Remote Desktop Protocol (RDP)** cung cấp phiên desktop và công cụ quản trị Windows từ xa. Windows VM thường dùng TCP **3389**; một số triển khai có thêm thành phần giao thức khác theo cấu hình.

```text
Máy quản trị              Kết nối RDP             Windows VM
Remote Desktop Client  ========================> RDP service :3389
  |                                                       |
  |-- xác thực và kiểm tra chứng chỉ/host                 |
  |-- kiểm tra NLA, quyền đăng nhập                       |
  |-- mở phiên Windows nếu được phép                      |
```

**Network Level Authentication (NLA)** yêu cầu xác thực sớm trước khi tạo đầy đủ phiên Remote Desktop, giúp giảm một phần bề mặt tấn công. NLA không thay thế MFA, bản vá hệ điều hành hay giới hạn mạng nguồn.

### Phân biệt đăng nhập máy ảo và quản trị tài nguyên Azure

Người có thể nhấn **Start/Stop VM** trong Azure Portal chưa chắc đăng nhập được vào Linux/Windows guest. Ngược lại, tài khoản local administrator trong VM không mặc nhiên được tạo/xóa VM, thay đổi NSG hoặc truy cập Key Vault trên Azure. Đây là **hai ranh giới quyền riêng**.

| Lớp | Ví dụ quyền | Hệ thống kiểm soát |
|---|---|---|
| **Azure control plane** | Đọc VM metadata, bật/tắt VM, sửa NIC/NSG, gắn extension. | Azure RBAC và Azure Resource Manager. |
| **Đăng nhập hệ điều hành** | SSH với tài khoản Linux, RDP với tài khoản Windows, quyền sudo/Administrators. | Hệ điều hành và cơ chế xác thực/ủy quyền đã cấu hình. |
| **Kết nối mạng** | TCP tới private IP trên port 22/3389. | VNet, route, NSG, firewall và kết nối VPN/Bastion. |
| **Tài nguyên ứng dụng** | Đọc database, file share, Azure Storage. | RBAC/data plane, ứng dụng và chính sách riêng. |

Muốn đăng nhập thành công, **cả quyền danh tính, tuyến mạng và dịch vụ trong guest OS** đều phải phù hợp.

## 3. Mô hình đe dọa và nguyên tắc bảo vệ

Những rủi ro thường gặp với truy cập quản trị VM:

1. **Quét cổng Internet:** public IP với TCP 22/3389 được mở có thể bị dò tìm liên tục.
2. **Dò mật khẩu/credential stuffing:** tài khoản dùng password yếu hoặc tái sử dụng.
3. **Rò rỉ SSH private key:** kẻ tấn công dùng khóa bị đánh cắp để đăng nhập.
4. **Lạm dụng tài khoản có quyền cao:** quyền Owner/Contributor hoặc local admin tồn tại thường trực.
5. **Máy quản trị bị nhiễm mã độc:** phiên SSH/RDP có thể bị chiếm dù đường truyền mã hóa.
6. **Di chuyển ngang:** từ một VM bị kiểm soát truy cập sang nhiều VM khác nếu cùng mật khẩu/khóa hoặc mạng mở quá rộng.
7. **Mất khả năng khôi phục:** NSG quá chặt, sshd lỗi, Windows Firewall chặn hoặc khóa bị thay nhưng không có đường dự phòng.

Áp dụng các nguyên tắc:

- **Private-first:** ưu tiên VM không có public IP, truy cập qua kênh quản trị được kiểm soát.
- **Least privilege:** chỉ cấp quyền cần thiết ở Azure và trong guest OS.
- **Strong authentication:** dùng SSH key/identity phù hợp; áp dụng MFA và chính sách Conditional Access cho điểm vào danh tính khi được hỗ trợ.
- **Just-in-time:** cấp mở cổng hoặc đặc quyền trong khoảng thời gian cần thiết.
- **Defense in depth:** mạng, danh tính, hệ điều hành, logging và quản trị khóa hỗ trợ nhau.
- **Auditable access:** ghi nhận người quản trị, thời điểm, loại thay đổi và sự kiện đăng nhập.
- **Recoverability:** chuẩn bị đường xử lý sự cố để khôi phục quyền mà không phải mở tất cả cổng ra Internet.

## 4. Các đường truy cập quản trị VM trên Azure

| Phương án | Đường kết nối | Lợi ích | Hạn chế/cân nhắc |
|---|---|---|---|
| **Azure Bastion** | Quản trị viên dùng Portal hoặc client được hỗ trợ → Bastion → private IP VM. | Không cần public IP trên VM; điểm vào tập trung, tích hợp Azure. | Phí Bastion, RBAC, cấu hình subnet/SKU và những yêu cầu kết nối. |
| **Point-to-site VPN** | Máy quản trị → VPN → VNet → private IP VM. | Truy cập riêng cho kỹ sư từ xa, có thể dùng các công cụ SSH/RDP quen thuộc. | Quản lý VPN client, danh tính, routes và thiết bị đầu cuối. |
| **Site-to-site VPN/ExpressRoute** | Mạng công ty → kết nối hybrid → private IP VM. | Phù hợp văn phòng/trung tâm dữ liệu có network controls tập trung. | Chi phí kết nối, định tuyến, DNS và khả năng dự phòng. |
| **Jump host/privileged access workstation** | Thiết bị tin cậy → điểm trung gian được kiểm soát → VM. | Có thể tích hợp quy trình ghi nhận phiên, phần mềm quản trị. | Jump host là tài nguyên cần hardening, giám sát, cập nhật và bảo vệ riêng. |
| **Public IP + NSG/JIT** | IP quản trị được phép → Internet → VM. | Có thể đáp ứng tình huống ngoại lệ có thời hạn. | Tiếp xúc Internet; cần hạn chế chặt source/time và tránh dùng làm mặc định. |

**Đề xuất mặc định cho VM Production:** để VM **không có public IP**, đặt trong subnet riêng, quản trị thông qua **Azure Bastion** hoặc một kết nối riêng được phê duyệt. Nếu buộc dùng public IP, cần lý do nghiệp vụ, hạn chế nguồn, thời gian, quyền truy cập và kế hoạch loại bỏ đường mở trực tiếp.

Không nhầm cổng SSH/RDP của guest VM với các cổng phục vụ ứng dụng. Một web server có thể cần HTTPS 443 từ Application Gateway nhưng **không cần 22/3389 từ Internet**.

## 5. Minh họa kiến trúc private administration

Giả sử một ứng dụng chạy trong VNet `10.80.0.0/16`:

```text
                               Microsoft Entra ID
                                      |
                               RBAC / MFA / PIM
                                      |
Quản trị viên -- Azure Portal --> Azure Bastion
                                      |
                      VNet: 10.80.0.0/16
                            |
                AzureBastionSubnet: 10.80.0.0/26
                            |
                      Private VM subnets
                    /                      \
            snet-linux                  snet-windows
             10.80.1.0/24                10.80.2.0/24
                 |                           |
           Linux VM                     Windows VM
           10.80.1.10                   10.80.2.10
          SSH TCP:22                    RDP TCP:3389
           no public IP                  no public IP
```

Trong sơ đồ:

- Bastion là điểm vào phục vụ kết nối quản trị thông qua hạ tầng Azure theo SKU/tính năng được hỗ trợ.
- VM vẫn chỉ dùng private IP; không cần NAT/port forwarding công khai cho SSH hoặc RDP.
- NSG trên subnet/NIC của VM chỉ cho phép cổng quản trị từ nguồn được phê duyệt, chẳng hạn dải `AzureBastionSubnet`, thay vì `0.0.0.0/0`.
- Các cổng phục vụ ứng dụng và các cổng quản trị được quản lý bằng các quy tắc riêng.
- Quyền Portal/Bastion và quyền đăng nhập guest OS đều cần được xác minh.

**Azure Bastion không tự thay thế phân quyền trong VM.** Người có quyền mở giao diện kết nối vẫn phải được phép xác thực theo phương thức SSH/RDP áp dụng, trừ các luồng tích hợp danh tính đã được cấu hình đầy đủ.

## 6. Azure Bastion: quản trị không cần public IP trên VM

**Azure Bastion** là dịch vụ PaaS để mở phiên SSH/RDP tới VM qua private IP. Người quản trị có thể kết nối từ Azure Portal bằng trình duyệt; một số SKU hỗ trợ **native client**, tunneling, shareable links, session recording hoặc các khả năng khác. Không giả định mọi SKU đều hỗ trợ toàn bộ tính năng.

### Thành phần cần chuẩn bị

1. **VNet đích** có VM hoặc VNet liên thông bằng cách được dịch vụ hỗ trợ.
2. Subnet dành riêng tên chính xác **`AzureBastionSubnet`**, thường cần **/26 hoặc rộng hơn cho triển khai Bastion hiện hành**, tùy SKU và giới hạn dịch vụ.
3. Azure Bastion resource và cấu hình frontend/phương thức kết nối phù hợp SKU.
4. Đường mạng từ Bastion đến private IP và TCP 22/3389 của guest VM.
5. Quyền Azure RBAC để xem/sử dụng Bastion, VM và tài nguyên mạng liên quan theo luồng Portal.
6. Phương thức đăng nhập guest OS: SSH key/identity, tài khoản Windows hoặc tích hợp Microsoft Entra nếu hỗ trợ.

Một số SKU có các yêu cầu khác nhau về public IP của **chính Bastion**. Trường hợp phổ biến Bastion có frontend public IP do Azure quản lý, nhưng **VM đích vẫn không cần public IP**. Các cấu hình private-only Bastion có điều kiện SKU/thiết kế riêng; hãy xác minh trước khi lựa chọn.

### Quy trình tạo Bastion bằng Azure Portal

1. Mở **Virtual networks**, chọn VNet chứa VM hoặc mạng quản trị phù hợp.
2. Tạo subnet tên `AzureBastionSubnet`, CIDR không chồng lấn và đúng kích thước tối thiểu của SKU.
3. Mở **Bastions**, tạo tài nguyên trong subscription/resource group/region phù hợp.
4. Chọn SKU, VNet, subnet và frontend IP theo thiết kế đã phê duyệt.
5. Kiểm tra NSG trên Bastion subnet và VM subnet theo **các rule Bastion yêu cầu**; không chỉ mở 22/3389 mà bỏ qua traffic quản lý đặc thù của Bastion.
6. Chờ trạng thái triển khai thành công và xác minh VM đích không cần public IP.

### Kết nối vào Linux VM

1. Mở Azure Portal → **Virtual machines** → chọn Linux VM.
2. Chọn **Connect → Bastion** hoặc chức năng tương ứng.
3. Chọn cách xác thực được môi trường hỗ trợ, ví dụ SSH private key hoặc danh tính tích hợp.
4. Xác minh đúng VM, tài khoản Linux và kết nối.
5. Ghi lại tác vụ quản trị rồi đóng phiên sau khi hoàn thành.

### Kết nối vào Windows VM

1. Mở VM Windows → **Connect → Bastion**.
2. Chọn kiểu xác thực được hỗ trợ (Windows credential/Entra-based login nếu đã cấu hình đủ).
3. Xác minh tài khoản có quyền Remote Desktop logon trong Windows.
4. Thực hiện quản trị và thoát phiên.

**Không chia sẻ private key hoặc mật khẩu qua chat, ticket hay tài liệu đào tạo.** Nếu cơ chế kết nối yêu cầu cung cấp credential, phải dùng giao diện và quy trình bảo mật do tổ chức phê duyệt.

### Bastion không phải giải pháp “bật lên là xong”

Các lỗi vẫn có thể xuất hiện:

- NSG trên subnet Bastion hoặc VM ngăn cản traffic cần thiết.
- Windows Firewall/sshd chặn kết nối trong guest.
- VM tắt, lỗi hệ điều hành hoặc NIC không hoạt động.
- Người dùng thiếu quyền Azure để vào Bastion/VM hoặc thiếu quyền login guest.
- SKU không hỗ trợ native client, tunneling hoặc tính năng cần dùng.
- VNet peering/route hoặc DNS không thỏa điều kiện khi VM ở mạng khác.

**Chi phí:** Bastion có chi phí theo SKU/thời gian sử dụng và những thành phần liên quan. Với môi trường lab, kiểm soát tài nguyên sau khi thực hành; với Production, cân nhắc dùng Bastion tập trung theo kiến trúc và điều kiện kết nối.

## 7. Quản lý SSH key an toàn cho Linux VM

**SSH public-key authentication** thường là lựa chọn ưu tiên cho Linux VM khi không dùng đăng nhập Microsoft Entra. Mỗi kỹ sư có cặp khóa riêng, không dùng chung private key của cả nhóm.

### Tạo SSH key

Ví dụ tạo cặp khóa RSA 4096 bit trên máy quản trị được tổ chức cho phép:

```bash
ssh-keygen -t rsa -b 4096 \
  -C "azure-admin-workstation" \
  -f ~/.ssh/azure_vm_admin
```

Lệnh sẽ tạo:

- `~/.ssh/azure_vm_admin`: **private key**, không được tiết lộ.
- `~/.ssh/azure_vm_admin.pub`: **public key**, có thể cung cấp cho hệ thống để đăng ký xác thực.

Khi được hỏi, nên dùng **passphrase mạnh** bảo vệ private key và quản lý bằng SSH agent/secret management phù hợp. Với thiết bị có hỗ trợ phần cứng/hardware-backed key, có thể cân nhắc các loại khóa khác tùy khả năng SSH client, hệ điều hành và công cụ triển khai.

**Không lưu private key trong repository hoặc gửi lên cloud storage không được quản lý**. Chỉ public key được đưa lên VM qua quy trình cấp quyền.

### Đăng ký public key cho tài khoản Linux

Khi tạo Linux VM, có thể chọn SSH public key authentication qua Portal/CLI. Với VM đã tồn tại, quy trình cấp khóa mới cần sự cho phép và một đường truy cập quản trị hiện có; public key được đưa vào `~/.ssh/authorized_keys` của đúng tài khoản nếu cấu hình SSH server sử dụng cơ chế đó.

Trong Linux, permission không phù hợp có thể khiến sshd bỏ qua khóa. Ví dụ quyền thường dùng:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

Đây là ví dụ trong **guest OS**, không phải lệnh chạy trên Azure Portal. Cần kiểm tra ownership của file, user, SELinux/AppArmor hoặc cấu hình sshd tùy bản phân phối. Không sửa hàng loạt quyền khi chưa xác định chính xác máy và thư mục.

### Kết nối qua private IP

Nếu workstation **đã có kết nối mạng riêng tới VNet**, ví dụ qua VPN:

```bash
ssh -i ~/.ssh/azure_vm_admin azureuser@10.80.1.10
```

Nếu không có VPN/Bastion/native tunnel hoặc route tới private IP, lệnh này **không thể tự xuyên qua Internet**. Địa chỉ `10.80.1.10` chỉ là ví dụ RFC 1918.

Khi SSH hiển thị fingerprint của host mới, cần **xác minh host key qua kênh đáng tin cậy** trước khi chấp nhận. Nếu cảnh báo host key thay đổi ngoài kế hoạch, không tự bỏ qua kiểm tra; có thể là VM được tạo lại hợp lệ, nhưng cũng có thể là kết nối sai máy hoặc bị can thiệp.

### Bảo vệ cấu hình sshd

Các biện pháp hardening thường cân nhắc:

- Giảm hoặc vô hiệu hóa password authentication **sau khi** đã xác minh key-based/Entra login và đường khôi phục hoạt động.
- Hạn chế login trực tiếp bằng `root`; dùng tài khoản riêng với `sudo` theo nguyên tắc tối thiểu.
- Loại bỏ khóa của nhân viên đã chuyển nhóm/nghỉ việc.
- Duy trì hệ điều hành và OpenSSH cập nhật.
- Giới hạn source IP ở **NSG và guest firewall**.
- Ghi log các lần xác thực thành công/thất bại và cảnh báo bất thường.
- Không sao chép một private key dùng chung cho nhiều VM/nhân viên nếu có thể dùng identity-based access hoặc khóa riêng.

Tránh thay đổi `sshd_config`, restart sshd hoặc vô hiệu hóa password auth trên VM Production khi **chưa thử được một phiên thứ hai** và chưa có Bastion/Serial Console/Run Command thích hợp để phục hồi.

## 8. RDP trên Windows VM: tài khoản, NLA và chính sách truy cập

RDP cung cấp desktop nên thuận tiện cho công cụ Windows, nhưng cũng có rủi ro khi phơi bày cổng 3389 hoặc dùng tài khoản mật khẩu yếu.

### Cấu hình cơ bản cần xem

| Yếu tố | Kiểm tra |
|---|---|
| Remote Desktop | Được bật khi cần quản trị và theo chính sách tổ chức. |
| **NLA** | Được bật nếu client và cấu hình xác thực tương thích. |
| Quyền đăng nhập | Tài khoản thuộc nhóm/role được phép Remote Desktop logon; không mặc định mọi user Azure có quyền. |
| Windows Firewall | Cho phép RDP trên profile thích hợp nhưng không mở quá rộng. |
| NSG | Chỉ cho phép TCP 3389 từ Bastion subnet hoặc mạng quản trị tin cậy. |
| Bản vá | Hệ điều hành, Remote Desktop Services và thành phần xác thực cập nhật. |
| Ghi log | Windows Security events và log Remote Desktop được theo dõi. |
| Chứng chỉ/identity | Có cơ chế xác minh server và chính sách xác thực phù hợp. |

### Kết nối RDP khi có VPN/mạng riêng

Nếu máy quản trị có kết nối riêng tới VNet và được phép:

```powershell
mstsc /v:10.80.2.10
```

Trên Windows, `mstsc` sẽ mở Remote Desktop Connection đến private IP. Lệnh này không tự tạo VPN và cũng không vượt qua NSG/Windows Firewall; phải có route, quyền và service đang hoạt động.

Kiểm tra kết nối TCP từ client Windows:

```powershell
Test-NetConnection -ComputerName 10.80.2.10 -Port 3389
```

Kết quả TCP `True` chỉ cho biết cổng có thể thiết lập kết nối trong điều kiện kiểm tra; **không chứng minh** tài khoản được phép đăng nhập hoặc NLA/certificate đã hợp lệ.

### Không vô hiệu hóa NLA để “sửa nhanh”

Nếu RDP báo lỗi NLA, chứng chỉ hoặc tài khoản, hãy kiểm tra:

1. Kiểu tài khoản đang dùng (local, domain hoặc Microsoft Entra).
2. Đồng bộ thời gian, phân giải tên và trạng thái domain/identity nếu phụ thuộc.
3. Quyền Remote Desktop logon trong Windows và chính sách local/group policy.
4. Trạng thái dịch vụ RDP, Windows Firewall và NSG.
5. Khả năng dùng Bastion/Serial Console hoặc công cụ phục hồi được phê duyệt.

Việc tắt NLA hoặc mở cổng 3389 cho toàn Internet để thử nghiệm có thể làm tăng rủi ro; chỉ dùng giải pháp theo chính sách bảo mật và kế hoạch quay lui được duyệt.

## 9. Network Security Group: giới hạn đúng nguồn truy cập

**Network Security Group (NSG)** lọc lưu lượng mạng ở phạm vi subnet/NIC của Azure. NSG rules dùng direction, protocol, source/destination, port và **priority**. Số priority nhỏ hơn được xử lý trước trong tập quy tắc áp dụng.

Một ví dụ chính sách dành cho VM:

| Rule logic | Nguồn | Đích | Port | Kết quả |
|---|---|---|---|---|
| Allow SSH from Bastion | `10.80.0.0/26` | `snet-linux` | TCP 22 | Allow |
| Allow RDP from Bastion | `10.80.0.0/26` | `snet-windows` | TCP 3389 | Allow |
| Allow SSH from admin VPN | Dải máy quản trị có phê duyệt | Linux VM/subnet | TCP 22 | Allow nếu cần |
| Allow RDP from admin VPN | Dải máy quản trị có phê duyệt | Windows VM/subnet | TCP 3389 | Allow nếu cần |
| Deny public admin | Các nguồn không được phép | VM quản trị | TCP 22/3389 | Deny theo thiết kế |
| App traffic | Nguồn ứng dụng/load balancer hợp lệ | Port ứng dụng | Theo dịch vụ | Allow |

Azure NSG có default rules, bao gồm các quy tắc cho VirtualNetwork và từ chối inbound khác. Khi thiết kế deny/allow cụ thể, **phải đánh giá effective security rules** của subnet và NIC cùng đường định tuyến thực tế. Không chỉ nhìn một rule rồi kết luận nguồn công khai đã bị chặn.

### Ba lỗi cấu hình NSG dễ gặp

**Lỗi 1: Mở SSH/RDP cho mọi nguồn**

```text
Source:      0.0.0.0/0
Destination: VM public IP
Port:        22 hoặc 3389
Action:      Allow
```

Một quy tắc như vậy tạo bề mặt tấn công lớn. Nếu có public IP và đường route thích hợp, kẻ tấn công Internet có thể liên tục thử kết nối. Không dùng làm mặc định Production.

**Lỗi 2: Allow quá rộng trong VirtualNetwork**

Tag `VirtualNetwork` có thể bao gồm nhiều phạm vi được Azure coi thuộc mạng ảo theo mô hình routing, không chỉ máy quản trị cần thiết. Với cổng nhạy cảm, nên đặt source prefix chính xác và kiểm tra đường đi, nhất là khi có peering/hybrid routes.

**Lỗi 3: Chặn traffic bắt buộc của Azure Bastion**

NSG trên `AzureBastionSubnet`, nếu có, phải đáp ứng các rule đặc thù mà dịch vụ Bastion yêu cầu, bao gồm các đường quản lý/tín hiệu và kết nối tới VM theo tài liệu hiện hành. Không chỉ sao chép rule cho NSG của VM sang Bastion subnet mà bỏ qua các yêu cầu nền tảng.

### NSG không xác thực danh tính người dùng

NSG chỉ nhìn các thuộc tính mạng, không biết ai đang cầm SSH key hay ai đăng nhập RDP. Vì vậy **NSG + identity + guest OS policy** phải kết hợp. Một kết nối từ VPN hợp lệ vẫn có thể là máy quản trị đã bị xâm nhập.

## 10. Just-in-Time VM access (JIT)

**Just-in-Time (JIT) VM access** là chức năng bảo vệ giúp quản lý thời điểm mở cổng quản trị cho VM, thường thông qua Microsoft Defender for Cloud với kế hoạch/tính năng phù hợp. Nó giảm thời gian cổng bị mở, đặc biệt khi có tình huống phải quản trị qua đường mạng trực tiếp.

Ví dụ quy trình:

1. VM có cổng quản trị bị giới hạn/đóng theo chính sách thông thường.
2. Người có quyền thích hợp gửi yêu cầu JIT cho VM, chọn cổng, source IP/range và khoảng thời gian được phép.
3. Hệ thống áp dụng quy tắc tạm thời theo cơ chế hỗ trợ.
4. Quản trị viên kết nối trong khung thời gian hợp lệ.
5. Hết thời hạn, quyền truy cập qua đường đó được thu hẹp lại theo chính sách.

JIT cần tính năng và quyền phù hợp; khả năng quản lý có thể phụ thuộc **Defender for Servers plan**, NSG/Azure Firewall và cấu hình môi trường. Không giả định JIT được bật miễn phí trên mọi subscription.

### JIT có thay thế Bastion không?

Không. JIT chủ yếu **giảm cửa sổ mở cổng**; nó không tự tạo một kênh quản trị riêng, không tự mã hóa lại RDP và không làm public IP trở nên vô hại. Với VM không có public IP, Bastion/VPN thường là mô hình quản trị thuận tiện hơn. Có thể dùng JIT bổ sung trong thiết kế thích hợp nhưng cần kiểm tra xung đột và độ phức tạp vận hành.

## 11. Microsoft Entra ID và Azure RBAC cho VM login

Azure có các khả năng đăng nhập guest OS tích hợp **Microsoft Entra ID** cho những phiên bản Linux/Windows VM được hỗ trợ. Khi triển khai đúng, người dùng có thể dùng danh tính tổ chức thay vì quản lý tài khoản/key local riêng lẻ ở tất cả VM.

### Các vai trò login thường gặp

| Azure RBAC role | Ý nghĩa chính |
|---|---|
| **Virtual Machine User Login** | Cho phép người dùng đăng nhập VM bằng Microsoft Entra với quyền thường, theo tính năng hỗ trợ. |
| **Virtual Machine Administrator Login** | Cho phép đăng nhập VM bằng Microsoft Entra với quyền quản trị tương ứng, theo tính năng hỗ trợ. |
| **Reader** | Đọc metadata tài nguyên; có thể cần bổ sung trong một số luồng Portal/Bastion/client. |
| **Virtual Machine Contributor** | Quản lý nhiều thuộc tính Azure VM; **không mặc nhiên là quyền đăng nhập guest**. |

Role `Virtual Machine Administrator Login` nên được cấp ở scope hẹp nhất thích hợp, ví dụ VM hoặc resource group của nhóm chịu trách nhiệm. Không cấp ở subscription rộng chỉ vì triển khai ban đầu dễ hơn.

### Điều kiện trước khi dùng Entra login

Tùy hệ điều hành và tính năng:

- VM dùng OS/image được hỗ trợ.
- Có **VM extension** hoặc thành phần xác thực Entra thích hợp, cấu hình identity cần thiết.
- VM truy cập được các endpoint danh tính theo yêu cầu hoặc có kết nối mạng phù hợp.
- User được cấp login role đúng scope và không bị Conditional Access/tenant policy chặn.
- Client và lệnh kết nối tương thích với phương thức Entra.
- Với Windows, trạng thái join/đăng ký thiết bị, RDP/NLA và hỗ trợ client có thể ảnh hưởng khả năng login.

Một ví dụ cho Linux với Azure CLI và thành phần SSH hỗ trợ Microsoft Entra:

```bash
az ssh vm \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<LINUX_VM_NAME>"
```

Lệnh chỉ hoạt động khi các điều kiện Entra SSH, CLI/extension, quyền và phương thức kết nối mạng đều phù hợp. Có thể cần cài Azure CLI SSH extension theo quy trình môi trường. **Nó không tự vượt qua NSG hay biến private IP thành địa chỉ truy cập được từ Internet.**

### Vai trò của MFA và Conditional Access

Khi user đăng nhập qua Microsoft Entra, chính sách MFA/Conditional Access có thể áp dụng theo luồng và tính năng hỗ trợ. Tuy nhiên:

- Đăng nhập vào **Azure Portal** bằng MFA **không tự có nghĩa** mọi phiên SSH bằng local key hoặc RDP bằng local password cũng được MFA.
- Guest OS account còn tồn tại với password yếu vẫn có thể là đường vòng nếu mạng cho phép.
- Cần loại bỏ tài khoản/đường đăng nhập không còn cần thiết theo kế hoạch và bảo đảm có phương án break-glass.

**Privilege Identity Management (PIM)**, nếu có và được cấp phép, có thể giúp cấp role quản trị VM theo thời gian, qua phê duyệt và MFA. Đây là lớp quản trị quyền bổ sung; không thay thế cấu hình đường mạng.

## 12. Azure Bastion, VPN và jump host: chọn theo vận hành

Một tổ chức có thể kết hợp các đường truy cập để cân bằng bảo mật, chi phí và tính sẵn sàng:

| Tình huống | Phương án ưu tiên | Lý do |
|---|---|---|
| Vài VM trong một VNet, quản trị viên dùng Portal | Azure Bastion | Không cần public IP trên VM và ít thành phần tự quản lý. |
| Nhiều VM, nhóm vận hành dùng terminal/scripts từ máy quản trị chuẩn | VPN hoặc Bastion native client nếu SKU hỗ trợ | Có kết nối riêng và quy trình SSH/RDP quen thuộc. |
| Nhiều site on-premises kết nối Azure | S2S VPN/ExpressRoute và network controls | Tập trung trên mạng doanh nghiệp; cần route/NSG rõ ràng. |
| Đặc quyền phải được ghi nhận qua nền tảng PAM | Jump host/bastion hoặc giải pháp PAM phù hợp | Gắn phiên với identity/phê duyệt/log theo yêu cầu. |
| Sự cố khẩn cấp khi VPN bị mất | Azure Bastion hoặc kênh phục hồi khác được phê duyệt | Đường quản trị độc lập hơn với kết nối văn phòng. |
| VM lab dùng public IP tạm thời | NSG source restriction + JIT nếu có | Chỉ nên dùng có thời hạn, gỡ bỏ sau thực hành. |

Với jump host tự quản lý, phải harden hệ điều hành, cập nhật bản vá, bảo vệ danh tính và ghi log của **chính jump host**. Nếu nó bị xâm nhập, kẻ tấn công có thể dùng vị trí mạng trung gian để truy cập rất nhiều VM.

Nếu dùng VPN/Bastion cho private VM, hãy kiểm tra đường **return route**, DNS, và firewall ở cả hai đầu. Có tunnel “Connected” chưa chắc SSH/RDP đã hoạt động.

## 13. Quy trình triển khai an toàn trong Azure Portal

### Giai đoạn A: Thiết kế trước khi tạo VM

1. Xác định VM phục vụ Production, Development hay môi trường thử nghiệm.
2. Chọn subnet chứa VM và subnet/bộ hạ tầng quản trị riêng.
3. Đặt chính sách **không cấp public IP mặc định** cho NIC VM.
4. Chọn đường quản trị được hỗ trợ: Bastion, VPN hoặc hybrid private connectivity.
5. Lập bảng các nhóm người dùng cần SSH/RDP và các tác vụ được phép thực hiện.
6. Chọn cơ chế xác thực Linux SSH key/Entra, Windows RDP/Entra hoặc domain.
7. Chuẩn bị monitoring, guest patching, backup/restore và đường phục hồi khẩn cấp.

### Giai đoạn B: Tạo VM và mạng

1. Mở [Azure Portal](https://portal.azure.com/) trong đúng tenant/subscription.
2. Tạo VM Linux/Windows ở resource group và region phù hợp.
3. Chọn VNet/subnet, đặt **Public IP = None** nếu kiến trúc dùng private access.
4. Chọn phương thức login được phê duyệt; Linux ưu tiên SSH key/Entra khi hỗ trợ.
5. Tạo/gắn NSG có rule theo nguồn quản trị thật sự cần thiết, không mở 22/3389 toàn Internet.
6. Chọn patching, monitoring và identity settings theo tiêu chuẩn vận hành.
7. Kiểm tra VM được provision thành công, NIC có private IP dự kiến.

### Giai đoạn C: Tạo kênh quản trị

1. Triển khai Azure Bastion hoặc kết nối VPN/ExpressRoute theo kiến trúc.
2. Nếu Bastion, chuẩn bị `AzureBastionSubnet` theo giới hạn SKU và cấu hình quyền truy cập.
3. Nếu VPN/hybrid, kiểm tra routes tới VM subnet và DNS.
4. Cấp Azure RBAC ở scope phù hợp, sau đó xác minh quyền login trong OS.
5. Kiểm tra SSH/RDP từ đúng nguồn quản trị, ghi lại bằng chứng và lỗi nếu có.
6. Nếu có JIT/PIM, xác nhận quy trình yêu cầu, hết hạn quyền và audit trail.

### Giai đoạn D: Nghiệm thu

- VM Production không có public IP quản trị ngoài yêu cầu được duyệt.
- SSH/RDP không truy cập được từ nguồn Internet không được phép.
- Người quản trị hợp lệ kết nối được từ Bastion/VPN theo quyền được cấp.
- Người không có role/credential cần thiết không đăng nhập guest được.
- Log guest, Azure Activity Log và Entra logs (khi áp dụng) hiển thị hoạt động cần quan sát.
- Có phương án khôi phục khi sshd/Windows Remote Desktop ngừng hoạt động.
- Có kế hoạch thay/thu hồi khóa hoặc quyền khi nhân sự thay đổi.
- Chi phí Bastion, VPN, monitoring và license được dự toán.

## 14. Kiểm tra trạng thái VM, NIC và NSG bằng Azure CLI

Các lệnh dưới đây là **lệnh đọc**, không mở cổng và không sửa cấu hình. Thay placeholder bằng tài nguyên của tổ chức.

### Kiểm tra tenant và subscription

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### Xem VM và private/public IP

```bash
az vm show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>" \
  --show-details \
  --query "{Name:name,PowerState:powerState,PrivateIps:privateIps,PublicIps:publicIps}" \
  --output json
```

Nếu VM có public IP ngoài dự kiến, phải kiểm tra thiết kế NIC/load balancer/public endpoint trước khi điều chỉnh. Xóa public IP khi không có phương án quản trị thay thế có thể làm mất quyền truy cập.

### Liệt kê NSG rules

```bash
az network nsg rule list \
  --resource-group "<RESOURCE_GROUP>" \
  --nsg-name "<NSG_NAME>" \
  --output table
```

### Kiểm tra effective NSG rules trên NIC

```bash
az network nic list \
  --resource-group "<RESOURCE_GROUP>" \
  --query "[].{NIC:name,PrivateIp:ipConfigurations[0].privateIPAddress,NSG:networkSecurityGroup.id}" \
  --output table

az network nic list-effective-nsg \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<NIC_NAME>" \
  --output json
```

Tên lệnh và yêu cầu môi trường có thể thay đổi theo phiên bản Azure CLI. Nếu chưa có hỗ trợ cho lệnh effective NSG hoặc VM/NIC không ở trạng thái tương thích, kiểm tra cú pháp bằng `az network nic --help` và dùng **Effective security rules** trong Portal/Network Watcher. Không suy diễn “không đọc được effective NSG” là không có NSG.

### Kiểm tra VM instance view

```bash
az vm get-instance-view \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>" \
  --output json
```

Instance view giúp xem trạng thái VM và một số thông tin runtime/extension. Nhưng VM ở trạng thái `VM running` **không bảo đảm** sshd hoặc Remote Desktop Services đang phục vụ đúng.

### Kiểm tra nguồn kết nối từ máy quản trị

Trên Linux/macOS hoặc workstation có OpenSSH:

```bash
ssh -v -i ~/.ssh/azure_vm_admin azureuser@10.80.1.10
```

Trên Windows:

```powershell
Test-NetConnection -ComputerName 10.80.2.10 -Port 3389
```

Chỉ chạy kiểm tra từ mạng và thiết bị được phép. `ssh -v` có thể hiển thị nhiều chi tiết kết nối; khi chia sẻ log, hãy che IP nội bộ hoặc định danh nhạy cảm theo chính sách tổ chức.

## 15. Chẩn đoán lỗi: mạng, xác thực hay hệ điều hành?

Một lỗi “không vào được VM” phải được phân loại trước khi thay đổi cấu hình.

| Triệu chứng | Lớp lỗi khả dĩ | Các bước cần xác minh |
|---|---|---|
| TCP timeout khi SSH/RDP | Route, NSG, firewall, VM/NIC, Bastion/VPN | Kiểm tra VM running, private IP, route, NSG và điểm vào. |
| `Connection refused` | Dịch vụ SSH/RDP không lắng nghe, local firewall hoặc sai port | Kiểm tra service trong guest, port, local firewall và cấu hình listener. |
| SSH báo `Permission denied (publickey)` | Sai user, sai private/public key, authorized_keys, permission | Kiểm tra user, fingerprint, ownership, sshd config và nguồn khóa. |
| SSH báo host key changed | VM tạo lại, DNS/IP trỏ khác, hoặc rủi ro giả mạo | Xác minh host identity qua kênh độc lập, không tắt host key checking bừa bãi. |
| RDP báo không đủ quyền | Windows logon rights, account, local/group policy | Kiểm tra nhóm Remote Desktop Users/Administrators và quyền logon. |
| RDP lỗi NLA hoặc chứng chỉ | Identity/domain/time/certificate/client support | Kiểm tra danh tính, NLA, CA, policy và trạng thái client. |
| Bastion mở được nhưng không vào được VM | NSG VM, guest firewall, SSH/RDP service, user login | Xem Bastion connectivity, target IP/port và guest logs. |
| VPN Connected nhưng VM unreachable | Thiếu route hai chiều, NSG, overlapping CIDR hoặc DNS | Kiểm tra Effective routes và truy cập bằng private IP trước hostname. |
| Entra login báo access denied | Login role thiếu, extension lỗi, policy hoặc VM không hỗ trợ | Kiểm tra Azure RBAC, VM extension, Entra sign-in logs và OS. |
| VM chạy nhưng không có network | Route/NSG, DHCP/NIC, guest firewall, OS network config | Dùng Network Watcher và kênh khôi phục ngoài SSH/RDP. |

### Phương pháp điều tra từng lớp

1. **Định danh đích:** xác nhận đúng subscription, resource group, VM name, NIC và private IP.
2. **Trạng thái VM:** kiểm tra VM running và OS boot bình thường.
3. **Nguồn truy cập:** xác nhận Bastion/VPN hoặc workstation đang dùng mạng quản trị được phép.
4. **Đường mạng:** kiểm tra route, NSG effective rules, firewalls và port.
5. **Dịch vụ guest:** xác nhận sshd hoặc Remote Desktop Services đang chạy, lắng nghe đúng port.
6. **Xác thực:** kiểm tra username, key/identity, Entra roles, domain/NLA.
7. **Ủy quyền:** kiểm tra quyền sudo/Windows local admin sau khi xác thực thành công.
8. **Ghi bằng chứng:** thời gian UTC, account, IP nguồn/đích, status, rule/extension và cách khắc phục.

Thay đổi từng yếu tố có kiểm soát. Nếu sửa cùng lúc NSG, firewall và password, rất khó biết nguyên nhân thật và dễ để lại một cửa truy cập không an toàn.

## 16. Phục hồi truy cập khi SSH/RDP hoàn toàn thất bại

Nếu không thể đăng nhập qua kênh thông thường, không nên ngay lập tức gắn public IP và mở tất cả cổng. Azure cung cấp một số cơ chế hỗ trợ phục hồi, với điều kiện tiên quyết khác nhau.

### Azure VM Run Command

**Run Command** cho phép thực thi tác vụ trong guest thông qua kênh quản lý VM/agent khi điều kiện hỗ trợ đầy đủ. Có thể dùng để đọc trạng thái dịch vụ, kiểm tra cấu hình hoặc thực hiện thao tác khắc phục được phê duyệt mà không cần SSH/RDP.

Điều kiện:

- VM Agent và trạng thái VM đủ điều kiện thực hiện.
- Người dùng có quyền Azure RBAC tương ứng.
- Guest OS/extension và đường quản lý phù hợp.
- Các lệnh phải được kiểm tra để không làm lỗi cấu hình nghiêm trọng hơn.

Không dùng Run Command để đặt mật khẩu admin chung cho nhiều VM hoặc tắt toàn bộ firewall theo một script thiếu kiểm soát.

### Azure Serial Console

**Serial Console** hỗ trợ truy cập kênh console để chẩn đoán VM, đặc biệt khi networking trong guest có vấn đề. Tính năng có yêu cầu về boot diagnostics, loại OS/VM, quyền và cấu hình hỗ trợ; không phải mọi môi trường đều sẵn sàng nếu chưa chuẩn bị.

Đây là một **đường khôi phục đặc quyền**: chỉ cấp cho nhóm vận hành được phép, có log và tài khoản break-glass phù hợp.

### Boot diagnostics và recovery

Boot diagnostics giúp xem thông tin boot/screenshot/serial logs khi VM không lên được hệ điều hành. Khi OS disk hoặc cấu hình guest hỏng nặng, có thể cần phương án cứu hộ/restore từ backup theo quy trình của tổ chức, ví dụ gắn đĩa vào VM cứu hộ được cách ly, kiểm tra offline rồi phục hồi. Đây là thao tác nhạy cảm và có thể gây mất dữ liệu nếu thực hiện sai.

### Quy trình break-glass khuyến nghị

1. Tạo incident và xác nhận VM/tài nguyên thật sự cần khôi phục.
2. Đọc trạng thái VM, NIC, NSG, các thay đổi gần đây trong Activity Log.
3. Chọn kênh có quyền tối thiểu, chẳng hạn Bastion, Run Command hoặc Serial Console theo nguyên nhân.
4. Lấy phê duyệt của người chịu trách nhiệm nếu cần quyền đặc biệt.
5. Thực hiện một thay đổi có thể quay lui, kiểm tra lại dịch vụ.
6. Xác nhận các rule tạm thời đã đóng, key/credential break-glass đã được thay hoặc vô hiệu hóa theo chính sách.
7. Ghi đầy đủ timeline, người thực hiện và bài học để tránh tái diễn.

Không viết runbook yêu cầu “tắt NSG rồi bật lại” nếu chưa có phương án thay đổi an toàn; các thao tác đó có thể tạo lỗ hổng ngay trong thời điểm sự cố.

## 17. Nhật ký truy cập và kiểm toán hoạt động quản trị

Quản lý SSH/RDP an toàn cần biết **ai đăng nhập, từ đâu, khi nào và đã thay đổi cấu hình gì**. Không có một nguồn log duy nhất trả lời toàn bộ câu hỏi.

| Nguồn | Ghi nhận | Không nên hiểu nhầm |
|---|---|---|
| **Azure Activity Log** | Thay đổi control plane: NSG, NIC, VM, Bastion, extension, role assignment theo tài nguyên. | Không phải nhật ký đầy đủ từng lệnh SSH hoặc từng phiên RDP bên trong guest. |
| **Microsoft Entra sign-in logs** | Các hoạt động xác thực qua Entra khi dùng cơ chế tương ứng. | Local SSH key/password login không tự trở thành Entra sign-in event. |
| **Linux auth logs/journald** | Đăng nhập SSH, thất bại xác thực, sshd và các hoạt động hệ thống theo cấu hình. | Cần bảo vệ, tập trung và quản lý retention. |
| **Windows Security Event Log** | Sự kiện đăng nhập và thất bại trong Windows theo audit policy. | Log có thể không ghi đủ nếu chính sách audit chưa bật. |
| **Windows TerminalServices logs** | Sự kiện về phiên RDP và dịch vụ Remote Desktop. | Không thay thế log ứng dụng và thay đổi hệ thống. |
| **Bastion diagnostics/metrics** | Hoạt động dịch vụ/phiên theo tính năng và cấu hình logs của SKU. | Mức chi tiết có thể khác; không mặc định mọi phiên đều được ghi video. |
| **Defender for Cloud / Sentinel / SIEM** | Tín hiệu phát hiện nguy cơ và phân tích tập trung khi triển khai. | Phụ thuộc gói dịch vụ, cấu hình và quy trình phản ứng. |

### Ví dụ xem log SSH trên Linux

Trên các Linux distribution dùng systemd, tên service có thể là `ssh` hoặc `sshd`:

```bash
sudo journalctl -u ssh --since "2 hours ago"
```

Nếu không có bản ghi, kiểm tra tên service và cấu hình logging thay vì kết luận không ai đăng nhập. Một số distribution ghi auth log vào `/var/log/auth.log` hoặc `/var/log/secure`.

### Ví dụ xem sự kiện đăng nhập trên Windows

Chạy trong Windows PowerShell với quyền phù hợp:

```powershell
Get-WinEvent -FilterHashtable @{
    LogName   = 'Security'
    Id        = 4624,4625
    StartTime = (Get-Date).AddHours(-24)
} | Select-Object TimeCreated, Id, ProviderName, Message
```

Event ID `4624` thường là logon thành công và `4625` là logon thất bại; để xác định RDP cần kiểm tra **logon type**, nguồn và các log TerminalServices liên quan, không chỉ event ID. Tránh ghi lại mật khẩu hoặc token khi xuất nhật ký.

### Chính sách giám sát đề xuất

- Cảnh báo VM Production bất ngờ có public IP hoặc rule inbound cho TCP 22/3389 từ `0.0.0.0/0`.
- Phát hiện nhiều lần SSH/RDP login thất bại trong thời gian ngắn.
- Theo dõi role assignment quản trị VM hoặc thay đổi Entra role/extension ngoài khung bảo trì.
- Cảnh báo khi Bastion, VPN hoặc đường truy cập quản trị quan trọng không khả dụng.
- Theo dõi khóa/credential sắp hết hiệu lực, host patching, guest agent và Defender alerts theo dịch vụ đã triển khai.
- Định kỳ kiểm tra quyền admin tồn tại quá lâu và các phiên truy cập từ nguồn bất thường.

Nếu sử dụng Azure Policy, có thể đặt chính sách kiểm toán/chặn public IP hoặc NSG rules quá rộng theo khả năng rule definition được hỗ trợ. Phải thử nghiệm để tránh chặn những trường hợp ngoại lệ hợp lệ và có quy trình xử lý exception.

## 18. Chi phí, năng lực quản trị và tiêu chuẩn hóa

Truy cập an toàn có chi phí, nhưng so sánh chi phí cần tính cả nhân sự vận hành và rủi ro bảo mật.

| Thành phần | Tác động chi phí và vận hành |
|---|---|
| **Azure Bastion** | Chi phí theo SKU/thời gian sử dụng, tính năng và traffic theo mô hình hiện hành. |
| **VPN/ExpressRoute** | Gateway, circuit/provider, dữ liệu và công sức vận hành mạng. |
| **Jump host** | VM, OS license nếu có, patching, monitoring, backup, hardening. |
| **Defender for Cloud/JIT** | Gói bảo vệ, license và khả năng hỗ trợ. |
| **Microsoft Entra/PIM/Conditional Access** | Chính sách danh tính và giấy phép áp dụng. |
| **Azure Monitor/Log Analytics/SIEM** | Ingestion, retention, phân tích/cảnh báo. |
| **VM quản trị và endpoint bảo mật** | Máy quản trị đạt chuẩn, bảo vệ thiết bị, MFA, khóa phần cứng nếu có. |

Không có một mức giá cố định đúng cho mọi thiết kế. Hãy dự toán với **Azure Pricing Calculator**, SKU, region, số VM, khung giờ sử dụng và yêu cầu truy cập cụ thể.

### Tiêu chuẩn vận hành nên có

1. Mẫu cấu hình VM theo IaC (Bicep/Terraform/ARM) với **public IP mặc định không có**.
2. Bộ NSG rules đã được duyệt cho subnet quản trị và subnet VM.
3. Tiêu chuẩn nhận diện user, cấp quyền Entra/RBAC, PIM và phân tách nhóm.
4. Quy trình phát hành/thu hồi SSH public key, reset credential và xử lý thiết bị thất lạc.
5. Runbook Bastion/VPN/JIT, quy trình break-glass và cách quay lui.
6. Tập trung log, retention và cảnh báo cho SSH/RDP.
7. Kiểm thử truy cập hợp lệ và truy cập bị từ chối sau mỗi lần thay đổi mạng.
8. Rà soát quyền administrator và các ngoại lệ theo lịch.
9. Kiểm soát chi phí Bastion/Defender/VPN khi mở rộng số VM và subscription.

## 19. Bài thực hành: quản trị hai Azure VM không dùng public IP

**Bối cảnh:** Nhóm triển khai ứng dụng nội bộ có hai VM trong một VNet. Một máy Linux xử lý API, một máy Windows phục vụ tác vụ quản trị. Cả hai phải được quản trị từ bên ngoài Azure qua đường đã phê duyệt nhưng không được nhận kết nối SSH/RDP trực tiếp từ Internet.

| Thành phần | Giá trị giả định |
|---|---|
| Subscription | `Development` |
| VNet | `vnet-app-dev` – `10.80.0.0/16` |
| Bastion subnet | `AzureBastionSubnet` – `10.80.0.0/26` |
| Linux subnet | `snet-linux` – `10.80.1.0/24` |
| Windows subnet | `snet-windows` – `10.80.2.0/24` |
| Linux VM | `vm-linux-01` – `10.80.1.10` |
| Windows VM | `vm-windows-01` – `10.80.2.10` |
| Public IP trên VM | Không có |
| Linux auth | SSH key riêng của quản trị viên hoặc Entra SSH được hỗ trợ |
| Windows auth | Quyền RDP phù hợp; NLA bật |
| Kênh quản trị | Azure Bastion hoặc VPN được phê duyệt |

### Nhiệm vụ

1. Vẽ sơ đồ đường truy cập từ quản trị viên tới từng VM.
2. Chọn mô hình identity cho Linux và Windows; phân biệt RBAC Azure với quyền guest.
3. Đề xuất source/destination/port cho NSG inbound vào Linux và Windows subnet.
4. Lập checklist triển khai Bastion, bao gồm subnet và SKU.
5. Nêu lý do VM không cần public IP.
6. Kiểm tra theo hai tình huống: quản trị viên có quyền kết nối thành công và người không được cấp quyền bị từ chối.
7. Giả sử Linux SSH báo `Permission denied (publickey)`: lập bước điều tra.
8. Giả sử Windows VM không nhận RDP, nhưng Azure Portal cho thấy VM running: lập bước điều tra.
9. Đề xuất đường khôi phục khẩn cấp nếu cả Bastion lẫn SSH/RDP không hoạt động.
10. Nêu ba cảnh báo an ninh và hai khoản chi phí cần quản lý.

### Lời giải tham khảo

**Thiết kế mạng:** VM chỉ dùng private IP. Bastion nằm trong `AzureBastionSubnet` và kết nối tới VM trong cùng mạng hoặc qua topology được dịch vụ hỗ trợ. NSG inbound vào Linux VM chỉ cho phép SSH từ Bastion subnet (và từ mạng quản trị qua VPN nếu có nhu cầu được duyệt); Windows VM tương tự với RDP. Không tạo rule internet-wide cho port 22/3389.

**Đăng nhập:** Linux ưu tiên SSH public key cho user riêng hoặc Entra SSH khi hỗ trợ. Windows sử dụng Windows account/Entra login phù hợp và bật NLA. Cấp role Azure để dùng Bastion và role login khi triển khai Entra login; không cấp Owner chỉ vì người dùng cần SSH.

**Lỗi SSH publickey:** xác minh user, đúng private key, public key trong authorized_keys, ownership/permissions, loại khóa, trạng thái sshd và log xác thực. Không tự bật password auth công khai để “sửa nhanh”.

**Lỗi RDP:** kiểm tra Bastion tới VM port 3389, NSG hiệu lực, Windows Firewall, RDP service, NLA, Windows logon rights và Windows event logs. Nếu network thất bại, kiểm tra route/NIC; nếu network thông nhưng login thất bại, kiểm tra identity/policy.

**Phục hồi:** dùng Azure Run Command hoặc Serial Console theo điều kiện hỗ trợ và quyền được phê duyệt, thu thập bằng chứng rồi thay đổi có kiểm soát. Cần giám sát Bastion, guest OS và tài khoản quản trị.

**Nghiệm thu:** hai VM không có public IP; người hợp lệ có thể đăng nhập qua đường quản trị; nguồn/identity không được phép bị chặn; log ghi lại các sự kiện cần thiết; có tài liệu về phương án phục hồi và chi phí.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Máy Linux Production chỉ cần quản trị từ nhóm vận hành. Cách an toàn hơn việc mở TCP 22 từ Internet là gì?

A. Dùng Azure Bastion hoặc VPN để truy cập private IP, NSG giới hạn nguồn.  
B. Mở `0.0.0.0/0` vào TCP 22 nhưng đổi port tùy ý.  
C. Chia sẻ một mật khẩu root cho toàn nhóm.

**Đáp án: A.** Đường quản trị riêng và hạn chế nguồn giúp giảm đáng kể bề mặt tấn công.

**Câu 2.** Azure RBAC role `Virtual Machine Contributor` có mặc nhiên cho phép SSH bằng Microsoft Entra vào Linux VM không?

**Đáp án:** Không. Quản trị resource và đăng nhập guest là hai phạm vi quyền khác nhau; cần tính năng Entra login được cấu hình và role login tương ứng.

**Câu 3.** Vì sao Bastion thường cho phép VM không có public IP?

**Đáp án:** Bastion tiếp nhận phiên quản trị theo mô hình dịch vụ và kết nối qua mạng Azure tới private IP VM. Public IP, nếu cần ở một số SKU, là của Bastion chứ không phải của mỗi VM.

**Câu 4.** SSH báo host key changed. Có nên vô hiệu hóa StrictHostKeyChecking ngay không?

**Đáp án:** Không. Cần kiểm tra VM có được tạo lại/đổi DNS hay không và xác minh fingerprint từ kênh tin cậy trước khi chấp nhận khóa mới.

**Câu 5.** Windows RDP qua VPN có TCP 3389 reachable, nhưng login bị từ chối. Lỗi chắc chắn do NSG không?

**Đáp án:** Không. Đường TCP có thể đã thông; cần kiểm tra tài khoản, quyền Remote Desktop, NLA, domain/identity và guest logs.

**Câu 6.** NLA có thay thế MFA hoặc giới hạn mạng nguồn không?

**Đáp án:** Không. NLA là một lớp bảo vệ RDP, không thay cho danh tính mạnh và NSG/Bastion/VPN.

**Câu 7.** JIT VM access giúp làm gì và có thay thế Bastion không?

**Đáp án:** JIT giới hạn thời gian/các nguồn được mở cổng quản trị theo cấu hình hỗ trợ. Nó không thay thế kênh quản trị riêng hay tự cung cấp xác thực cho phiên SSH/RDP.

**Câu 8.** Vì sao `0.0.0.0/0` trên cổng 3389 là rủi ro dù tài khoản có password?

**Đáp án:** Cổng quản trị bị phơi bày cho các nguồn Internet, tăng nguy cơ dò mật khẩu và khai thác; password không giải quyết toàn bộ rủi ro.

**Câu 9.** SSH key của nhân viên nghỉ việc nên xử lý thế nào?

**Đáp án:** Thu hồi public key/quyền Entra liên quan, kết thúc phiên/quyền truy cập theo chính sách, kiểm tra key dùng chung và log, đồng thời tránh dùng chung private key để có thể thu hồi theo từng người.

**Câu 10.** VM chạy nhưng không vào được SSH/RDP. Cần kiểm tra lớp nào trước khi reset password?

**Đáp án:** Xác minh đường mạng, VM/NIC, route, NSG, Bastion/VPN và guest service; sau đó mới kiểm tra xác thực. Reset password khi đường mạng đang lỗi có thể không giúp gì.

**Câu 11.** Azure Activity Log có mặc định chứa toàn bộ lệnh Linux đã chạy trong phiên SSH không?

**Đáp án:** Không. Activity Log ghi control-plane Azure; cần guest logging, auditd/session controls hoặc công cụ tương ứng để theo dõi hành động bên trong OS.

**Câu 12.** Khi nào nên sử dụng Run Command hoặc Serial Console?

**Đáp án:** Khi đường quản trị bình thường không hoạt động và có đủ điều kiện/ủy quyền để truy cập kênh phục hồi. Không dùng như lý do để cấp quyền đặc biệt thường trực.

**Câu 13.** Với Bastion đã triển khai, có thể bỏ toàn bộ NSG và guest firewall vì “Bastion tự an toàn” không?

**Đáp án:** Không. Cần giữ kiểm soát mạng và guest OS phù hợp, đồng thời cấu hình các rule mà Bastion yêu cầu để tránh vừa mở quá rộng vừa chặn nhầm dịch vụ.

**Câu 14.** Trong thiết kế quản trị VM, điều gì quan trọng hơn việc “cổng SSH đổi từ 22 sang 2222”?

**Đáp án:** Đặt VM ở private network, giới hạn nguồn, xác thực mạnh, phân quyền tối thiểu, bản vá, logging và đường khôi phục. Đổi port đơn thuần không phải kiểm soát bảo mật căn bản.

**Tóm lại:** truy cập quản trị Azure VM an toàn cần kết hợp **đường mạng riêng + xác thực mạnh + phân quyền tối thiểu + logging + khả năng phục hồi**. SSH và RDP là giao thức quản trị, còn Azure Bastion, VPN, NSG, JIT, Microsoft Entra ID và Azure RBAC quyết định ai có thể tiếp cận VM và trong điều kiện nào. Một phương án tốt phải cho phép người được ủy quyền xử lý sự cố kịp thời, đồng thời hạn chế tối đa cơ hội truy cập ngoài ý muốn.
