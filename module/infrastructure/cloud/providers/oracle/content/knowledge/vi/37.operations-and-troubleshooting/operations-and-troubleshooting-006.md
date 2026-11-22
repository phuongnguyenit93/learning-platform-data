# Chẩn đoán lỗi SSH, routing, NSG và DNS

## 1. Mục tiêu và phạm vi

Bài học thuộc chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_ORACLE**, tập trung vào Oracle Cloud Infrastructure (OCI). Ta kết hợp kiến thức về tenancy, compartment, IAM, VCN và Compute để tìm điểm hỏng trên một kết nối, sau đó khôi phục bằng thay đổi có thể kiểm chứng và hoàn tác.

Sau bài học, bạn có thể:

- Phân biệt lỗi phân giải tên, lỗi thiết lập TCP và lỗi xác thực SSH.
- Lần theo đường đi và đường về qua route table, gateway, NSG, Security List và hệ điều hành.
- Chẩn đoán DNS trong VCN, giữa các VCN và giữa OCI với mạng tại chỗ.
- Dùng bằng chứng từ client, máy đích và công cụ OCI để chọn đúng thay đổi.
- Ghi lại kết quả, cập nhật cấu hình tự động hóa và thu hồi tài nguyên chẩn đoán để kiểm soát chi phí.

Các ví dụ chủ yếu dành cho Linux Compute thông thường. Với DB System hoặc dịch vụ cơ sở dữ liệu được quản lý, phép kiểm tra IP, route và DNS vẫn hữu ích; quyền truy cập hệ điều hành và cách kết nối phải theo loại dịch vụ. Kết nối được TCP tới một cổng cơ sở dữ liệu chưa xác nhận tài khoản, TLS, wallet hay dịch vụ cơ sở dữ liệu hoạt động đúng.

## 2. Xác định kết nối cần chẩn đoán

### 2.1. Vẽ đường đi trước khi sửa

Một phiên SSH trực tiếp qua IPv4 có thể được hình dung như sau:

```text
Client
  | phân giải hostname thành địa chỉ IP
  | TCP từ cổng tạm thời tới cổng SSH
  v
Mạng client / VPN / firewall doanh nghiệp
  v
Internet Gateway của VCN + ánh xạ public IP
  v
VNIC đích: Security Lists và các NSG áp dụng
  v
Firewall hệ điều hành -> sshd -> tài khoản và authorized_keys
  ^
  | phản hồi cần có đường về và được các lớp kiểm soát cho phép
```

Đây là sơ đồ để khoanh vùng, không biểu diễn thứ tự xử lý nội bộ từng gói tin của OCI. Nếu truy cập private IP qua VPN, FastConnect hoặc Bastion, hãy thay phần đường Internet bằng đường truy cập thực tế.

Dùng một bộ địa chỉ nhất quán trong bài:

| Thành phần | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| VCN | `10.20.0.0/16` | Mạng của ứng dụng |
| Subnet quản trị | `10.20.10.0/24` | Chứa jump host trong mô hình tự quản |
| Jump host | `10.20.10.5` | Chuyển tiếp SSH tới máy ứng dụng |
| Subnet ứng dụng | `10.20.20.0/24` | Subnet private |
| Compute ứng dụng | `10.20.20.10` | Máy cần chẩn đoán |
| Public IP của một máy thử public | `198.51.100.20` | Đích thử SSH từ Internet |
| Public IP thoát ra của client | `203.0.113.10` | Nguồn cho rule Internet |
| DNS tại chỗ | `172.16.0.53` | DNS của mạng kết nối qua DRG |
| FQDN ứng dụng | `app01.app.learnvcn.oraclevcn.com` | Tên minh họa theo DNS label |

Các địa chỉ public trong bảng dành cho tài liệu, không dùng để kết nối thật. Thay bằng địa chỉ, hostname và cổng đã xác minh trong môi trường của bạn. Cổng SSH mặc định là 22; nếu đã đổi cổng, thay đồng bộ trong lệnh và rule.

### 2.2. Ghi lại một lần thử có thể tái hiện

Trước khi kiểm tra, ghi:

1. Thời điểm và múi giờ; lệnh đã chạy; thông báo lỗi nguyên văn.
2. Region, compartment, OCID của instance, VNIC, subnet và VCN liên quan.
3. IP nguồn thực tế sau NAT/VPN; IP đích; IPv4 hay IPv6; giao thức và cổng.
4. Kiểu truy cập: public IP, private IP qua mạng doanh nghiệp, jump host hay OCI Bastion.
5. Thay đổi gần nhất: route, NSG, DHCP options, image, SSH key hoặc cấu hình OS.
6. Phạm vi ảnh hưởng: một client, một máy, một subnet hay nhiều ứng dụng.

Ví dụ một yêu cầu SSH cụ thể:

```text
Thời điểm: <thời điểm UTC của lần thử>
Nguồn tại biên OCI: 203.0.113.10:<cổng do client/NAT chọn>
Đích public: 198.51.100.20:22/TCP
Private IP tương ứng: <private IP xác minh trên VNIC>
Kết quả: Connection timed out sau khoảng 5 giây
Thay đổi gần nhất: cập nhật danh sách IP quản trị
```

Quyền xem instance trong Console là quyền trên tài nguyên OCI. Đăng nhập SSH còn phụ thuộc tài khoản và khóa trong máy khách. Nếu gặp `NotAuthorizedOrNotFound` khi xem mạng, xác minh region, OCID và IAM với người quản trị; không coi việc không thấy tài nguyên là bằng chứng tài nguyên đã bị xóa.

## 3. Phân loại triệu chứng từ client

### 3.1. Dùng thông báo lỗi để chọn lớp kiểm tra

| Triệu chứng | Bằng chứng hiện có | Kiểm tra tiếp |
| --- | --- | --- |
| `Could not resolve hostname` | Client chưa có địa chỉ để kết nối | Resolver, hostname, search domain, bản ghi |
| `Connection timed out` | Chưa thiết lập TCP trong thời hạn thử | IP đích, đường đi/về, rule, firewall, tình trạng máy |
| `No route to host` hoặc `Network is unreachable` | Có lỗi định tuyến hoặc phản hồi lỗi mạng | Route tại client/OS, VPN, gateway; không kết luận riêng NSG |
| `Connection refused` | Có phản hồi từ chối chủ động | Sai IP/cổng, dịch vụ chưa lắng nghe hoặc firewall REJECT |
| `Permission denied (publickey)` | Đã tới dịch vụ SSH và bước xác thực | Username, khóa, quyền file, cấu hình SSH |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Host key khác giá trị client đã lưu | Xác minh danh tính máy qua kênh quản trị tin cậy |
| Bắt tay được nhưng truyền dữ liệu bị treo | Đường đi cơ bản đã hoạt động | MTU, mất gói, tài nguyên OS, kết nối theo dõi trạng thái |

Một thông báo chỉ giúp ưu tiên giả thuyết. Chẳng hạn, timeout có thể do firewall trong máy đích thả gói dù route và NSG đều đúng. Oracle có hướng dẫn riêng cho các nhóm lỗi SSH thường gặp trong [Troubleshooting the SSH Connection](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-ssh-connection.htm).

### 3.2. Tách phép thử TCP khỏi phép thử SSH

Trên Linux có OpenSSH và biến thể `nc` hỗ trợ các tùy chọn dưới đây:

```bash
nc -vz -w 5 198.51.100.20 22

ssh -vvv -o ConnectTimeout=5 -o ConnectionAttempts=1 \
  -o IdentitiesOnly=yes -i ~/.ssh/oci_lab_key \
  opc@198.51.100.20
```

Trên Windows PowerShell:

```powershell
Test-NetConnection -ComputerName 198.51.100.20 -Port 22 -InformationLevel Detailed

ssh -vvv -o ConnectTimeout=5 -o ConnectionAttempts=1 -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\oci_lab_key" opc@198.51.100.20
```

`TcpTestSucceeded: True` chỉ cho biết kết nối TCP thành công; nó chưa kiểm tra khóa SSH. Địa chỉ nguồn hiển thị trên client có thể là IP LAN hoặc VPN, khác public IP sau NAT mà OCI nhận được.

Trong log `ssh -vvv`, tìm mốc kết nối TCP, trao đổi phiên bản SSH, đề nghị khóa và chấp nhận khóa. Tùy chọn `-i` chọn file khóa; `IdentitiesOnly=yes` giúp tránh việc thử nhiều identity ngoài ý muốn. Tham khảo cách dùng tùy chọn trong [OpenSSH ssh(1)](https://man.openbsd.org/ssh).

Thử numeric IP trước, rồi thử hostname trên cùng đường truy cập. Nếu TCP tới IP thành công nhưng hostname không phân giải được, ưu tiên nhánh DNS. Không dùng ping làm điều kiện bắt buộc: ICMP và TCP/22 có thể được cho phép khác nhau.

## 4. Chẩn đoán routing trên OCI và trong hệ điều hành

### 4.1. Kết nối trực tiếp qua public IPv4

Kiểm tra đồng thời:

- Đúng instance, đúng VNIC/private IP đang gắn public IP được dùng.
- Subnet cho phép public IP; bản thân nhãn public subnet không đảm bảo instance đã có public IP.
- Internet Gateway tồn tại và đang bật.
- Route table hiệu lực có đường tới client qua Internet Gateway; cấu hình thông dụng là `0.0.0.0/0 -> Internet Gateway`.
- Security rules và OS cho phép lưu lượng cần thiết.

Public IP là ánh xạ do OCI cung cấp; khi kiểm tra `ip addr` trong guest, thông thường bạn thấy private IP của VNIC. Đối chiếu ánh xạ trên OCI thay vì tự gán public IP vào OS. Các điều kiện truy cập Internet trực tiếp được mô tả trong [Internet Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingIGs.htm).

Một lỗi thực tế là sửa đúng rule trong một route table nhưng subnet đang dùng bảng khác. Ngoài bảng gắn với subnet, hãy kiểm tra route table gắn trực tiếp với VNIC hoặc private IP nếu môi trường dùng **per-resource routing**.

Route ưu tiên prefix dài hơn. Ví dụ, trong bảng hiệu lực:

| Destination | Target | Hệ quả khi đích là `203.0.113.10` |
| --- | --- | --- |
| `0.0.0.0/0` | Internet Gateway | Route tổng quát |
| `203.0.113.0/24` | DRG | Route được chọn vì cụ thể hơn |

Máy có thể nhận SYN qua public IP nhưng gửi phản hồi về DRG theo route thứ hai. Cần so sánh cấu hình với đường về dự kiến, không chỉ tìm sự tồn tại của default route. Xem quy tắc chọn route và per-resource routing trong [VCN Route Tables](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingroutetables.htm).

### 4.2. Máy private cần một đường truy cập private

NAT Gateway cho phép tài nguyên không có public IP khởi tạo kết nối ra Internet và nhận phản hồi. Nó không cung cấp chuyển tiếp cổng để client Internet khởi tạo SSH vào máy private. Vì vậy, `0.0.0.0/0 -> NAT Gateway` không giải quyết yêu cầu SSH từ laptop vào private IP. Xem [NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm).

Chọn đường truy cập đã được thiết kế:

| Đường truy cập | Các điểm cần kiểm tra |
| --- | --- |
| Jump host tự quản | Client tới jump host; sau đó jump host tới private IP đích |
| VPN/FastConnect | Route phía client, mạng tại chỗ, DRG và VCN; cả chiều về |
| OCI Bastion | Session, CIDR allowlist, endpoint và kết nối tới target |
| Cloud Shell qua private networking | Mạng private đã cấu hình và quyền sử dụng tương ứng |

Ví dụ với jump host tự quản, khi cả hai chặng dùng cùng identity:

```bash
ssh -J opc@198.51.100.20 \
  -o IdentitiesOnly=yes -i ~/.ssh/oci_lab_key \
  opc@10.20.20.10
```

Nếu hai chặng dùng khóa khác nhau, cấu hình từng host trong SSH config. Không cần sao chép private key lên jump host. Đây là mô hình jump host tự quản; OCI Bastion cung cấp lệnh kết nối theo session riêng.

Với OCI Bastion, kiểm tra session còn hiệu lực và public IP thoát ra của client có trong allowlist. Managed SSH cần OpenSSH, Oracle Cloud Agent và Bastion plugin ở target; port forwarding có yêu cầu khác. Nếu dùng port forwarding để tới SSH, máy đích vẫn phải có SSH server hoạt động. Tham khảo [Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

Với VPN/FastConnect, đối chiếu CIDR quảng bá, route table của DRG attachment, route VCN và route mạng tại chỗ. CIDR trùng nhau hoặc thiếu route chiều về có thể làm phép thử thất bại dù tunnel đang hiển thị UP.

### 4.3. Xem quyết định định tuyến trong guest

Các lệnh sau chạy **trong instance**, qua phiên còn hoạt động hoặc kênh console được phép:

```bash
ip -br addr
ip route
ip rule show
ip route show table all
ip route get 203.0.113.10
```

`ip route get` giúp xác định interface và source IP mà Linux dự kiến chọn. Nó không hiển thị Internet Gateway, NAT Gateway hay toàn bộ route OCI. Với nhiều VNIC, chú ý source IP, policy routing và đường về có đi qua interface mong muốn hay không.

Hai subnet cùng VCN thường có local routing sẵn; không cần tự thêm default route Internet để chúng nói chuyện bằng private IP. Nếu đã đưa traffic qua firewall appliance hoặc thiết lập route cụ thể, phải xét đường mới này.

Không thêm route OS ngẫu nhiên chỉ vì SSH timeout. Trước hết xác định lỗi nằm ở route guest hay route của hạ tầng.

## 5. Chẩn đoán NSG và Security List

### 5.1. Tìm đúng tập rule đang áp dụng

Security List gắn với subnet và áp dụng cho các VNIC trong subnet đó. Vì vậy, thay đổi một Security List dùng chung có thể ảnh hưởng nhiều máy. Xem [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm).

NSG áp dụng cho VNIC hoặc tài nguyên đã được gắn vào nhóm. Tạo NSG có rule đúng nhưng quên gắn VNIC đích thì rule không bảo vệ hay mở kết nối cho VNIC đó. Máy nhiều VNIC cần kiểm tra đúng VNIC nhận traffic. NSG cũng cho phép tham chiếu NSG nguồn/đích trong cùng VCN. Xem [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

Đối với NSG và Security List, các rule cho phép được hợp lại trên VNIC; không có thứ tự deny/allow như ACL có số thứ tự. Xóa rule SSH ở NSG chưa chắc thu hồi được SSH nếu Security List còn cho phép.

Với một máy thử public, rule ingress stateful tối thiểu có thể là:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Direction | Ingress |
| Source type | CIDR |
| Source | `203.0.113.10/32` |
| Protocol | TCP |
| Source port | All |
| Destination port | `22` |
| Stateless | No |

Client thường dùng cổng nguồn tạm thời. Đặt source port bằng 22 sẽ không khớp với phần lớn phiên SSH do client khởi tạo.

Nếu dùng jump host qua private IP, nguồn quan sát trên target thường là private IP của jump host. Với OCI Bastion, xác minh private endpoint làm nguồn ở chặng tới target; không mặc định dùng public IP laptop cho mọi chặng.

### 5.2. Phân biệt stateful và stateless

Rule stateful theo dõi kết nối và cho phép phản hồi tương ứng; không cần mở toàn bộ egress chỉ để trả lời một kết nối ingress đã được theo dõi. Rule stateless yêu cầu cho phép riêng chiều về. Khi traffic cùng chiều khớp cả hai loại, stateless được ưu tiên và không tạo trạng thái theo cách stateful.

Ví dụ cặp rule stateless cho SSH vào máy thử:

| Chiều tại VNIC server | CIDR đối tác | Source port | Destination port |
| --- | --- | --- | --- |
| Ingress TCP | Nguồn `203.0.113.10/32` | All | `22` |
| Egress TCP | Đích `203.0.113.10/32` | `22` | All |

Có thể thu hẹp cổng đích chiều về nếu xác minh được dải cổng thực tế, kể cả NAT. Các nguyên tắc hợp rule, theo dõi trạng thái và ngoại lệ stateless nằm trong [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Kiểm tra cả điểm nguồn và điểm đích: NSG egress của jump host cũng có thể chặn SYN trước khi nó tới server. Một phép thử thành công trên phiên SSH đang mở chưa xác nhận phiên mới sẽ kết nối được; hãy mở một phiên mới sau thay đổi.

Nếu endpoint dùng security attribute của **Zero Trust Packet Routing (ZPR)**, kiểm tra policy ZPR tương ứng bên cạnh NSG/Security List. Đây là một lớp kiểm soát bổ sung được lưu ý trong [tài liệu NSG](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

## 6. Kiểm tra SSH và firewall trong máy đích

### 6.1. Có tiến trình lắng nghe không?

Trên Oracle Linux dùng systemd:

```bash
sudo ss -lntp
sudo systemctl status sshd --no-pager
sudo journalctl -u sshd --since "15 minutes ago" --no-pager
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T
df -h
df -i
```

Trên Ubuntu, unit dịch vụ thường là `ssh`; kiểm tra unit và cơ chế socket activation thực tế của image. Các ví dụ tương ứng:

```bash
sudo systemctl status ssh --no-pager
sudo journalctl -u ssh --since "15 minutes ago" --no-pager
```

Đọc kết quả theo câu hỏi cụ thể:

- Cổng đúng đã LISTEN chưa? Lắng nghe trên private IP, mọi địa chỉ hay chỉ loopback?
- Log có lỗi cú pháp, thiếu host key, từ chối người dùng hoặc giới hạn kết nối không?
- Phân vùng hoặc inode đã đầy khiến dịch vụ hay phiên đăng nhập gặp lỗi không?
- Cấu hình hiệu lực có bị thay đổi bởi file include hoặc khối `Match` không?

`sshd -t` kiểm tra cấu hình trước khi áp dụng; `sshd -T` hiển thị cấu hình hiệu lực, có thể kết hợp `-C` để xét điều kiện kết nối trong khối Match. Xem [OpenSSH sshd(8)](https://man.openbsd.org/sshd.8).

Nếu cần thay đổi cấu hình SSH, giữ một phiên quản trị đang mở, sao lưu cấu hình theo quy trình vận hành, kiểm tra cú pháp rồi áp dụng bằng cơ chế của hệ điều hành. Kiểm tra phiên đăng nhập mới trước khi đóng phiên cũ.

### 6.2. Firewall OS là lớp độc lập

Chọn lệnh phù hợp với firewall đang được quản lý trên image; không giả định tất cả công cụ đều được cài:

```bash
# firewalld: xác định zone đang gắn với interface trước.
sudo firewall-cmd --get-active-zones

# Ví dụ chỉ khi interface thực sự thuộc zone public:
sudo firewall-cmd --zone=public --list-all

# Nếu hệ thống sử dụng nftables:
sudo nft list ruleset

# Nếu hệ thống sử dụng iptables:
sudo iptables -S
sudo iptables -L -n -v
```

Tìm rule áp dụng cho đúng interface, nguồn, cổng và thứ tự xử lý. Không tắt toàn bộ firewall hay flush ruleset để thử kết nối. Một bộ đếm tăng trên rule DROP/REJECT cùng lúc thử SSH là bằng chứng hữu ích hơn việc chỉ nhìn rule allow ở một chain khác.

Không trộn thay đổi thủ công bằng nhiều công cụ nếu firewall do một dịch vụ hoặc hệ thống quản lý cấu hình sở hữu.

### 6.3. Khi TCP thành công nhưng khóa bị từ chối

Với platform image thông dụng, Oracle Linux thường dùng `opc`, Ubuntu dùng `ubuntu`; custom image có thể khác. Private key trên client phải tương ứng public key được cấp cho tài khoản đích. Trên Windows cần kiểm soát ACL của private key theo hướng dẫn hệ điều hành; `chmod` trong ví dụ Linux không thay thế việc kiểm tra ACL Windows. Xem [Connecting to a Linux Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm).

Ví dụ kiểm tra trên Oracle Linux:

```bash
# Client Linux:
chmod 600 ~/.ssh/oci_lab_key

# Trên target, kiểm tra đường dẫn mặc định của tài khoản opc:
sudo namei -l /home/opc/.ssh/authorized_keys
sudo stat -c '%U:%G %a %n' \
  /home/opc /home/opc/.ssh /home/opc/.ssh/authorized_keys
sudo ssh-keygen -lf /home/opc/.ssh/authorized_keys
```

Kiểm tra owner của home, `.ssh`, `authorized_keys`; quyền ghi không phù hợp; nội dung public key bị xuống dòng hoặc thiếu; tài khoản bị khóa; và log xác thực. Nếu SELinux đang bật, kiểm tra context và log liên quan trước khi sửa. Đường dẫn authorized keys có thể đã được đổi trong cấu hình SSH.

Có thể so fingerprint mà không đưa private key lên server:

```bash
# Client: lấy public key tương ứng, sau đó tính fingerprint.
ssh-keygen -y -f ~/.ssh/oci_lab_key | ssh-keygen -lf -
```

Nếu host key thay đổi, xác minh fingerprint qua console tin cậy, ví dụ với host key Ed25519:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Chỉ sau khi xác nhận máy đã được tạo lại hoặc host key đã được thay hợp lệ mới cập nhật mục tương ứng trong `known_hosts`. Không tắt kiểm tra host key để vượt cảnh báo. Các tùy chọn fingerprint và quản lý host key được mô tả trong [OpenSSH ssh-keygen(1)](https://man.openbsd.org/ssh-keygen).

### 6.4. Khi mọi đường SSH đều mất

Instance Console Connection hỗ trợ xem và xử lý sự cố qua serial console hoặc VNC console, với IAM và điều kiện kết nối riêng. Console history cũng có thể giúp nhận diện lỗi boot. Kết nối console không mặc nhiên cấp một phiên root đã đăng nhập.

Dùng quy trình phục hồi phù hợp để kiểm tra OS, firewall và SSH; ưu tiên xác định nguyên nhân trước khi reboot. Reboot làm mất một số bằng chứng tạm thời và có thể gián đoạn ứng dụng. Tham khảo [Troubleshooting Instances Using Instance Console Connection](https://docs.oracle.com/en-us/iaas/Content/Compute/References/serialconsole.htm).

## 7. Chẩn đoán DNS từ ứng dụng tới resolver

### 7.1. Xác định resolver và tên được hỏi

Chạy trong máy gặp lỗi, không chỉ trên laptop người quản trị:

```bash
cat /etc/resolv.conf

# Có trên nhiều hệ thống dùng systemd-resolved:
resolvectl status

# Đi qua cơ chế phân giải của hệ điều hành:
getent ahostsv4 app01.app.learnvcn.oraclevcn.com

# Hỏi DNS, ghi rõ FQDN và loại bản ghi:
dig app01.app.learnvcn.oraclevcn.com. A +time=2 +tries=1
dig app01.app.learnvcn.oraclevcn.com. AAAA +time=2 +tries=1

# Đối chiếu với resolver mặc định của OCI từ trong instance:
dig @169.254.169.254 app01.app.learnvcn.oraclevcn.com. A +time=2 +tries=1
```

Nếu công cụ chưa có, dùng tiện ích tương đương sẵn trong image hoặc cài theo quy trình được phép; tránh đổi DNS chỉ để cài công cụ. Trên Windows:

```powershell
Resolve-DnsName -Name app01.app.learnvcn.oraclevcn.com -Type A
Resolve-DnsName -Name app01.app.learnvcn.oraclevcn.com -Type A -Server 169.254.169.254
```

Lệnh chỉ định `169.254.169.254` được dùng từ môi trường OCI phù hợp; laptop ngoài OCI không có đường trực tiếp tới resolver link-local này.

`getent` phản ánh thứ tự tra cứu của OS, có thể gồm `/etc/hosts`; `dig` hỏi DNS và không đại diện đầy đủ cho cách ứng dụng tra tên. Nếu `resolv.conf` trỏ tới `127.0.0.53`, đó có thể là stub resolver cục bộ; xem upstream bằng công cụ quản lý resolver. Dấu chấm cuối FQDN giúp tránh ảnh hưởng của search suffix.

### 7.2. Phân biệt các kết quả DNS

| Kết quả | Ý nghĩa cần hiểu | Hướng điều tra |
| --- | --- | --- |
| `NOERROR`, có answer | Query có câu trả lời | IP có đúng không; thử TCP tới IP đó |
| `NOERROR`, không có loại record yêu cầu | Chưa chắc tên không tồn tại | Thử đúng A/AAAA/CNAME; xem answer và authority |
| `NXDOMAIN` | Hệ thống phân giải báo tên không tồn tại trong ngữ cảnh được hỏi | Chính tả, zone/view, tên bị che, negative cache |
| `SERVFAIL` | Resolver không hoàn tất xử lý | Upstream, forwarding, DNSSEC, lỗi phục vụ |
| `REFUSED` | Máy chủ từ chối xử lý query | Chính sách truy vấn hoặc recursion |
| Timeout, không có phản hồi | Chưa nhận được câu trả lời DNS | Địa chỉ resolver, route, UDP/TCP, firewall |

Các mã phản hồi DNS được định nghĩa trong [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html). Timeout không phải là mã `NXDOMAIN`.

Đọc cả `SERVER`, status, answer, authority và TTL. Chỉ nhìn `dig +short` có thể bỏ mất thông tin cần để phân biệt các trường hợp trên.

### 7.3. DNS trong VCN

Tên hệ thống của một instance được hình thành từ hostname và DNS label của subnet/VCN; display name không phải lúc nào cũng là hostname đó. Internet and VCN Resolver có thể phân giải tên public mà instance chưa có đường Internet cho ứng dụng. Do đó:

- Tra được tên public không xác nhận HTTPS hoặc SSH ra Internet hoạt động.
- Sửa hostname trong OS không tự sửa bản ghi DNS do OCI quản lý.
- Thay DHCP options cần được client nhận lại; kiểm tra cấu hình đang có trong guest.

Không sửa lâu dài `/etc/resolv.conf` nếu file do DHCP hoặc dịch vụ OS sinh lại. Tham khảo [DNS in a Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns.htm).

Với private zone tự tạo, xác minh record tồn tại trong đúng zone và private view; view đã gắn với resolver của VCN nơi client gửi query. Private DNS resolver dùng cấu hình view, zone và rule để trả lời, chứ không chỉ dựa vào việc hai máy có IP liên thông. Xem [Private DNS Resolvers](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-Private-resolver.htm).

Để thử tình huống một máy thành công, một máy thất bại, lập bảng:

| Máy thử | Subnet | Resolver thực tế | Câu hỏi giống nhau | Kết quả |
| --- | --- | --- | --- | --- |
| app01 | app | Resolver OCI | `db.internal.example. A` | Private IP |
| app02 | app | DNS custom cũ | `db.internal.example. A` | NXDOMAIN |

Bảng minh họa này tạo giả thuyết cấu hình resolver khác nhau; cần kiểm tra thực tế trước khi thay đổi. Sau khi sửa bản ghi hoặc resolver, xét cả TTL, negative cache, cache OS và cache riêng của runtime ứng dụng.

## 8. DNS giữa các VCN và với mạng tại chỗ

### 8.1. Phân biệt listening endpoint và forwarding endpoint

- **Listening endpoint** nhận query từ mạng khác vào resolver của VCN.
- **Forwarding endpoint** gửi query từ resolver OCI tới DNS đích theo rule.
- Instance hỏi `169.254.169.254` không cần tạo listening endpoint chỉ cho thao tác đó.

Endpoint có địa chỉ trong subnet và cần được xét cùng routing, NSG và Security List tương ứng. Không dùng resolver link-local của một VCN làm địa chỉ DNS đích trực tiếp cho máy tại chỗ. Xem [Resolver Endpoints](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_endpoints.htm).

Một luồng forwarding tới mạng tại chỗ:

```text
Ứng dụng OCI
  -> resolver của VCN
  -> rule khớp corp.example
  -> forwarding endpoint
  -> route VCN / DRG / VPN hoặc FastConnect
  -> DNS 172.16.0.53
  -> phản hồi theo đường về
```

Để chẩn đoán chặng DNS qua endpoint thông thường, xét ít nhất:

| Điểm kiểm soát | Query cần cho phép | Phản hồi cần cho phép |
| --- | --- | --- |
| OCI forwarding endpoint | Egress tới DNS đích, destination port 53 | Từ DNS đích, source port 53 |
| OCI listening endpoint | Ingress từ DNS/client được phép, destination port 53 | Tới DNS/client, source port 53 |
| Firewall/DNS tại chỗ | Query từ IP nguồn thực tế của endpoint | Phản hồi về nguồn query |

Kiểm tra cả UDP và TCP. Với stateless, phải có rule chiều về tường minh, hướng tới cổng tạm thời của bên hỏi; với stateful, kiểm tra trạng thái và giới hạn theo dõi kết nối. Oracle có hướng dẫn riêng cho [lỗi kết nối Private DNS giữa các mạng](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/troubleshooting_network-connectivity.htm).

Tại một máy thử có đường tới DNS tại chỗ:

```bash
dig @172.16.0.53 host01.corp.example. A +time=2 +tries=1
dig @172.16.0.53 host01.corp.example. A +tcp +time=2 +tries=1
```

Phép thử từ máy Compute chỉ kiểm tra nguồn của máy đó. Nó không thay thế phép kiểm tra forwarding endpoint, vì route, source IP và rule có thể khác.

DNS cần hỗ trợ TCP bên cạnh UDP; việc chặn TCP/53 có thể làm một số câu hỏi thất bại, đặc biệt khi cần chuyển sang TCP cho phản hồi bị cắt ngắn. Xem [RFC 7766 — DNS Transport over TCP](https://www.rfc-editor.org/rfc/rfc7766.html).

### 8.2. Kiểm tra view và thứ tự forwarding

Private DNS xét private views trước, rồi resolver rules, rồi Internet khi không có kết quả khớp trước đó. Một private zone `example.com` có thể trả `NXDOMAIN` cho `host01.corp.example.com` và che rule forward `corp.example.com`.

Khi dùng custom DHCP settings, kiểm tra yêu cầu cấu hình `169.254.169.254` trong danh sách nameserver để truy vấn private views/rules theo hướng dẫn OCI. Các trường hợp này được giải thích trong [Common Private DNS Issues](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/troubleshooting_general.htm).

Resolver rules được xét theo thứ tự; rule đã khớp thực hiện forwarding và không thử rule sau chỉ vì DNS đích lỗi. Hai rule cùng điều kiện không tự tạo failover. Xem [Resolver Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_rules.htm).

Khi xử lý sự cố, ghi riêng tên được hỏi, view/zone có thể khớp, rule đầu tiên khớp và DNS đích. Kiểm tra vòng lặp nếu DNS OCI và DNS tại chỗ cùng chuyển tiếp một hậu tố cho nhau. Kết nối mạng giữa hai VCN thành công chưa xác nhận private DNS đã được cấu hình chia sẻ hoặc chuyển tiếp đúng.

## 9. Kết hợp công cụ OCI với bằng chứng trong guest

### 9.1. Network Path Analyzer

Tạo phép phân tích với đúng nguồn, đích, giao thức, cổng nguồn/đích nếu cần và chiều kiểm tra. Với TCP/UDP, kiểm tra hai chiều giúp phát hiện vấn đề đường về.

Network Path Analyzer phân tích cấu hình; nó không gửi gói tin thật và không kiểm tra tiến trình `sshd`, firewall trong guest hay khóa người dùng. Kết quả còn phụ thuộc quyền thấy các tài nguyên liên quan. Nếu công cụ báo đường khả dụng nhưng SSH vẫn lỗi, chuyển sang bằng chứng runtime. Xem [Network Path Analyzer](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/path_analyzer.htm).

### 9.2. VCN Flow Logs

Bật capture tại VNIC hoặc phạm vi phù hợp, lọc theo nguồn, đích và khoảng thời gian của lần thử. Flow Logs cho biết traffic được chấp nhận hoặc từ chối bởi security rules của mạng OCI; sampling và capture filter ảnh hưởng dữ liệu nhận được. Xem [Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

- `REJECT` là bằng chứng cần điều tra rule tại VNIC tương ứng.
- `ACCEPT` không xác nhận firewall OS đã cho qua hay ứng dụng đã xử lý.
- Không có bản ghi chưa đủ để kết luận không có traffic: kiểm tra điểm bật log, filter, sampling và thời gian.

Một số traffic link-local như VCN DNS, DHCP và block storage không xuất hiện trong Flow Logs. Đừng dùng việc thiếu log cho query `169.254.169.254` làm bằng chứng NSG chặn DNS. Xem [Details for VCN Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_vcn_flow_logs.htm).

### 9.3. Bắt gói có phạm vi

Nếu có quyền và công cụ trong guest, bắt gói đúng lần thử, giới hạn số gói:

```bash
# Trên target SSH:
sudo tcpdump -ni any -c 40 'tcp port 22'

# Trên máy gửi query DNS:
sudo tcpdump -ni any -c 40 '(udp port 53 or tcp port 53)'
```

| Quan sát khi thử SSH mới | Giả thuyết được ưu tiên |
| --- | --- |
| Không thấy SYN ở guest | Sai đích hoặc bị chặn trước điểm bắt; kiểm tra interface/filter |
| SYN vào lặp lại, không có SYN-ACK | Firewall OS, listener hoặc đường phản hồi |
| SYN vào, SYN-ACK ra lặp lại, thiếu ACK | Phản hồi không tới client hoặc bị client chặn |
| Hoàn tất bắt tay, sau đó lỗi publickey | Đi sâu vào username, khóa và policy SSH |

Đây là suy luận từ gói tin tại điểm quan sát, cần đối chiếu với cấu hình và log. Nếu nghi MTU, đối chiếu kích thước gói, retransmission và thông báo ICMP trên đường thực tế; không thay MTU toàn hệ thống chỉ dựa vào một phiên bị treo.

## 10. Quy trình xử lý từ đầu đến cuối

1. **Chốt đối tượng:** đúng tenancy, region, compartment, instance và VNIC; ghi IP nguồn/đích thực tế.
2. **Tái hiện tối thiểu:** một lệnh TCP và một lệnh SSH có thời hạn; ghi mốc thời gian.
3. **Tách DNS:** đối chiếu hostname với numeric IP; ghi resolver và kết quả A/AAAA.
4. **Xét routing:** đường client, route table hiệu lực của OCI, gateway và đường về.
5. **Xét security:** tập NSG/Security List trên từng VNIC, stateful/stateless, lớp ZPR nếu áp dụng.
6. **Xét guest:** listener, firewall, route OS, dịch vụ và log xác thực.
7. **Đối chiếu bằng chứng:** Network Path Analyzer, Flow Logs và bắt gói khi cần.
8. **Sửa một nguyên nhân đã có bằng chứng:** lưu cấu hình trước/sau và cách hoàn tác.
9. **Xác nhận phục hồi:** kết nối mới trên đường truy cập ban đầu; kiểm tra cả dịch vụ phụ thuộc.
10. **Hoàn tất vận hành:** thu hồi rule/session thử, cập nhật IaC và ghi biện pháp ngăn lặp lại.

Không đổi DNS, NSG và route cùng lúc trong một phép thử. Nếu nhiều thành phần cần sửa, thực hiện theo từng bước có kết quả quan sát riêng để biết thay đổi nào giải quyết nguyên nhân nào.

## 11. Các tình huống minh họa

### 11.1. Đổi mạng làm SSH public timeout

**Quan sát:** instance hoạt động; người khác vẫn SSH được. Client vừa chuyển sang một kết nối Internet mới.

**Giả thuyết:** public IP nguồn sau NAT thay đổi, không còn khớp CIDR quản trị.

**Cách xác minh:** lấy IP thoát ra từ thiết bị biên hoặc phương pháp đã được tổ chức chấp thuận; đối chiếu rule hiệu lực và lần thử có mốc thời gian. Không dùng riêng IP LAN trong `Test-NetConnection` để so với rule public.

**Xử lý:** cập nhật đúng CIDR nguồn được phép hoặc dùng đường Bastion/VPN đã thiết kế. Mở phiên mới để xác nhận và thu hồi rule thử.

### 11.2. Ping không trả lời nhưng SSH báo lỗi khóa

**Quan sát:** `ping` timeout; `ssh -vvv` đã tới xác thực và báo `Permission denied (publickey)`.

**Suy luận:** ICMP không quyết định trạng thái TCP/22. Có đủ bằng chứng để ưu tiên username, identity và authorized keys.

**Xử lý:** đối chiếu image, tài khoản và fingerprint; kiểm tra log SSH. Không cần mở ICMP hoặc thay route để giải quyết lỗi xác thực này.

### 11.3. Có route NAT nhưng không SSH được vào máy private

**Quan sát:** máy private tải gói cập nhật được; laptop không tới `10.20.20.10:22` từ Internet.

**Suy luận:** đường outbound hoạt động không cung cấp đường inbound tới private IP.

**Xử lý:** thử bằng OCI Bastion, jump host hoặc kết nối private đã được phê duyệt. Với jump host, kiểm tra từng chặng và rule nguồn tại target.

### 11.4. DNS đúng ở máy quản trị, sai trong ứng dụng

**Quan sát:** tên cơ sở dữ liệu trả private IP ở một máy thử nhưng `NXDOMAIN` trong máy ứng dụng.

**Cách xác minh:** hỏi cùng FQDN, cùng record type; so resolver thực tế, DHCP options, private view và cache. Nếu ứng dụng chạy trong container, kiểm tra từ chính môi trường mạng của container.

**Xử lý:** sửa cấu hình resolver/view hoặc record ở đúng nơi tạo query. Sau đó thử kết nối tới IP trả về và kết nối bằng hostname từ ứng dụng.

### 11.5. NSG có rule SSH nhưng SYN không đến target

**Quan sát:** người vận hành vừa thêm rule vào NSG `admin-access`; traffic vẫn bị từ chối.

**Cách xác minh:** kiểm tra VNIC của IP đích có thực sự thuộc `admin-access`; kiểm tra NSG egress phía nguồn nếu dùng jump host; đối chiếu VNIC ghi nhận `REJECT`.

**Xử lý:** sửa quan hệ gắn NSG hoặc rule đã xác định sai, rồi tạo kết nối mới. Đồng thời kiểm tra không còn rule rộng ở Security List khiến cấu hình thực tế khác ý định.

Các tình huống trên là ví dụ suy luận để học quy trình, không phải kết quả đã chạy trên tenancy cụ thể.

## 12. Thực hành có kiểm soát

Dùng môi trường lab đã có quyền quản trị và kênh khôi phục. Với từng bài thử, ghi cấu hình ban đầu, hành động, kết quả dự kiến, bằng chứng thực tế và bước hoàn tác.

| Bài thử | Thao tác trong lab | Kết quả cần quan sát |
| --- | --- | --- |
| Sai username | SSH bằng tài khoản không tồn tại | TCP có thể thành công, xác thực thất bại |
| Sai khóa | Dùng một private key khác của lab | Log cho thấy khóa không được chấp nhận |
| Sai nguồn SSH | Tạm thay CIDR của rule lab, giữ đường phục hồi | Phiên mới thất bại; xác minh tập rule khác không còn cho phép |
| Sai đường về | Sửa route trong bảng riêng của lab | Đối chiếu NPA và gói SYN/SYN-ACK trước khi hoàn tác |
| Tên không tồn tại | Hỏi FQDN thử không có record | Nhận NXDOMAIN nếu zone/ngữ cảnh tương ứng trả lời như vậy |
| So UDP và TCP DNS | Hỏi cùng DNS đích bằng hai chế độ | Phân biệt sự khác nhau theo transport nếu có |

Không thực hành phá route hoặc chặn SSH trên bảng dùng chung với môi trường thật. Sau mỗi bài, hoàn tác và chứng minh kết nối mới hoạt động; không dựa vào phiên cũ còn mở.

Kiểm soát tài nguyên chẩn đoán bằng phạm vi log phù hợp, thời gian lưu theo nhu cầu và việc thu hồi máy thử hoặc tài nguyên tạm sau lab. Khi triển khai thật, đưa thay đổi đã xác nhận vào Terraform/Resource Manager hoặc công cụ cấu hình đang quản lý để lần triển khai sau không khôi phục cấu hình lỗi.

## 13. Tiêu chí kết thúc sự cố

Có thể đóng sự cố khi đã ghi nhận:

- Kết nối mới thành công từ nguồn cần phục vụ và bằng đúng hostname hoặc IP dự kiến.
- DNS trả đúng địa chỉ trong đúng môi trường; TCP và xác thực được kiểm tra riêng.
- Nguyên nhân có bằng chứng và thay đổi khắc phục được mô tả rõ.
- Rule, session, capture và tài nguyên thử đã được thu hồi theo nhu cầu.
- Cấu hình tự động hóa đã đồng bộ; không còn thay đổi thủ công chưa được ghi nhận.
- Có cách phát hiện lặp lại: cảnh báo phù hợp, phép thử kết nối hoặc kiểm tra DNS từ điểm đại diện.

Một biên bản ngắn có thể dùng cấu trúc:

```text
Phạm vi ảnh hưởng:
Thời gian bắt đầu / phục hồi, kèm múi giờ:
Nguồn -> đích / giao thức / cổng:
Triệu chứng và lệnh tái hiện:
Bằng chứng ở client, OCI và guest:
Nguyên nhân:
Thay đổi khắc phục và cách hoàn tác:
Kết quả kiểm tra phiên mới / DNS / dịch vụ:
Cập nhật IaC, giám sát và việc cần làm tiếp:
```

Đích của chẩn đoán là giải thích được vì sao kết nối hỏng và vì sao thay đổi đã khôi phục nó, với quyền truy cập và cấu hình mạng phù hợp nhu cầu vận hành.
