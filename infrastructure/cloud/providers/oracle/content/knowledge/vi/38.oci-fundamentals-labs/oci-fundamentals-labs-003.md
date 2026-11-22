# Bài thực hành triển khai Compute và truy cập qua Bastion

## 1. Mục tiêu và tình huống thực hành

Trong chương **Thực hành nền tảng OCI** của module **CLOUD_PROVIDERS_ORACLE**, bài này kết nối kiến thức về compartment, IAM, VCN, Compute và lưu trữ thành một quy trình triển khai có thể kiểm chứng: tạo một máy Oracle Linux chỉ có địa chỉ riêng, rồi quản trị máy qua Oracle Cloud Infrastructure Bastion.

Giả sử nhóm phát triển cần một máy thử nghiệm cho ứng dụng Java. Người vận hành cần SSH để kiểm tra hệ điều hành và chuẩn bị môi trường, nhưng nhóm không muốn cấp public IP cho máy hoặc duy trì một máy trung gian để đăng nhập.

Kết thúc bài, người học có thể:

- Triển khai một Compute instance vào private subnet và xác nhận máy không có public IP.
- Phân biệt quyền IAM, quyền kết nối mạng và quyền đăng nhập hệ điều hành.
- Tạo Bastion với allowlist giới hạn theo địa chỉ IPv4 công cộng của máy thực hành.
- Tạo phiên SSH port forwarding, dựng tunnel và đăng nhập bằng khóa của máy đích.
- Thử thêm Managed SSH khi Oracle Cloud Agent và Bastion plugin đã sẵn sàng.
- Thu thập bằng chứng vận hành, chẩn đoán lỗi theo từng chặng và dọn tài nguyên sau lab.

Bài dùng Console để tạo hạ tầng và OpenSSH trên máy cá nhân để kết nối. Phần CLI cuối bài là tùy chọn, không bắt buộc cài thêm công cụ để hoàn thành luồng chính.

## 2. Kiến trúc và những lớp kiểm soát độc lập

### 2.1. Kiến trúc được triển khai

~~~mermaid
flowchart LR
    Client["Máy cá nhân<br/>IPv4 công cộng nằm trong allowlist"]
    PublicEndpoint["Endpoint dịch vụ OCI Bastion<br/>TCP 22, khóa của session"]
    subgraph VCN["VCN 10.38.0.0/16"]
        subgraph PrivateSubnet["Private subnet 10.38.10.0/24"]
            BastionPE["Private endpoint của Bastion<br/>BastionPrivateIP"]
            VM["Oracle Linux Compute<br/>Private IP, không public IP<br/>sshd TCP 22"]
        end
        SGW["Service Gateway"]
    end
    OSN["Oracle Services Network<br/>Các dịch vụ được hỗ trợ trong region"]
    Client -->|"SSH tunnel"| PublicEndpoint
    PublicEndpoint -->|"Kết nối do dịch vụ quản lý"| BastionPE
    BastionPE -->|"TCP 22, NSG cho phép nguồn /32"| VM
    VM -->|"Route theo service CIDR label"| SGW
    SGW --> OSN
~~~

Bastion trong bài là **dịch vụ OCI Bastion**, không phải một Compute VM tự cài làm jump host. Người học tạo tài nguyên Bastion, phiên truy cập và các quy tắc mạng; không phải cập nhật hệ điều hành của một máy trung gian.

VCN có một private subnet dùng chung cho Compute và private endpoint của Bastion. Bài tạo Service Gateway cùng route đến Oracle Services Network ngay từ đầu, phù hợp với hướng dẫn tạo Bastion và phục vụ phần thực hành Managed SSH. Service Gateway không cấp public IP cho Compute. Xem [hướng dẫn tạo Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-bastion.htm).

### 2.2. Không nhầm ba lớp xác thực và phân quyền

| Lớp | Câu hỏi cần trả lời | Cấu hình trong lab |
| --- | --- | --- |
| IAM | Ai được tạo Compute, Bastion hoặc session? | Group và policy trong compartment lab |
| Mạng | Gói tin từ đâu được đến endpoint và máy đích? | Client CIDR allowlist, security list, NSG và firewall hệ điều hành |
| SSH | Người kết nối chứng minh danh tính bằng gì? | Khóa của session và khóa đăng nhập người dùng Linux |

Có quyền tạo session không tự động làm cho TCP 22 thông suốt. Tunnel chạy được cũng không có nghĩa khóa đăng nhập Linux hợp lệ.

Đặc biệt, phải phân biệt hai địa chỉ nguồn:

- **Client public IPv4**: địa chỉ mà endpoint Bastion nhìn thấy khi máy cá nhân kết nối qua Internet; dùng trong client CIDR allowlist.
- **Bastion private endpoint IPv4**: địa chỉ nguồn trong VCN khi Bastion tiếp cận Compute; dùng trong ingress rule cho máy đích.

Không dùng địa chỉ LAN như `192.168.1.10` của laptop cho allowlist Internet, và không dùng public IPv4 của laptop làm nguồn NSG cho chặng Bastion đến Compute.

### 2.3. Chọn loại session

| Tiêu chí | SSH port forwarding — luồng chính | Managed SSH — phần mở rộng |
| --- | --- | --- |
| Đích phiên | Private IP và TCP port cụ thể | Compute Linux, người dùng hệ điều hành và SSH port |
| Agent trên máy đích | Không phụ thuộc Oracle Cloud Agent | Cần Oracle Cloud Agent và Bastion plugin hoạt động |
| Đăng nhập Linux trong bài | Dùng khóa VM đã cung cấp khi tạo instance | Dùng khóa đã khai báo cho Managed SSH session |
| Cách thao tác | Giữ tunnel ở terminal A, SSH từ terminal B | Dùng lệnh SSH do Console cung cấp |

Port forwarding chuyển tiếp TCP tới dịch vụ đích. Bản thân loại session này không yêu cầu dịch vụ đích là SSH; tuy nhiên, **vì lab chuyển tiếp tới TCP 22 để đăng nhập Linux, máy đích vẫn phải chạy SSH server**. Điều kiện của Managed SSH được Oracle mô tả trong [Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

## 3. Chuẩn bị môi trường, quyền và chi phí

### 3.1. Điều kiện trước khi bắt đầu

Chuẩn bị một tenancy OCI, một region được phép dùng và compartment lab riêng, ví dụ `OCILab`. Tài khoản cần được quản trị viên đưa vào group có quyền phù hợp. Nếu tổ chức có Security Zone hoặc chính sách mạng bổ sung, dùng cấu hình lab được tổ chức cho phép.

Trên máy cá nhân cần:

- OpenSSH client với các lệnh `ssh` và `ssh-keygen`.
- Khả năng kết nối TCP 22 ra endpoint Bastion của region.
- Hai terminal trong cùng một môi trường thực thi.
- Cách xác định public IPv4 hiện tại, ví dụ trang thông tin kết nối do tổ chức cung cấp hoặc thông tin egress từ quản trị mạng.

Các ví dụ local bên dưới dùng **Bash trên Linux, macOS hoặc WSL**. Nếu chọn WSL, mở cả hai terminal trong WSL và lưu khóa ở thư mục home của WSL. Nếu dùng OpenSSH trong PowerShell, thay đường dẫn khóa bằng đường dẫn Windows thực tế và viết lệnh trên một dòng; các lệnh Linux sau khi đã SSH vào VM giữ nguyên.

VPN, proxy hoặc chuyển từ Wi-Fi sang mạng di động có thể làm thay đổi địa chỉ egress. Xác định public IPv4 trên đúng đường mạng sẽ dùng để mở SSH tunnel. Không mặc định egress của trình duyệt và terminal luôn giống nhau.

### 3.2. Chọn tài nguyên trong giới hạn ngân sách

Trước khi tạo VM, kiểm tra shape, số OCPU, RAM, dung lượng boot volume, quota và chi phí ước tính ở region đã chọn. Chọn một VM nhỏ có image Oracle Linux tương thích kiến trúc CPU và phù hợp hạn mức của tenancy. Bài không phụ thuộc một tên shape cố định.

Theo [bảng giá Oracle Cloud](https://www.oracle.com/cloud/price-list/), dịch vụ Bastion được niêm yết miễn phí tại thời điểm soạn bài. Compute, boot volume, backup và các tài nguyên bổ sung vẫn phải được đánh giá chi phí riêng. Không suy ra toàn bộ lab miễn phí từ việc Bastion miễn phí.

Nên dành khoảng 60–90 phút cho lần đầu; phiên Bastion có thể phải tạo lại nếu hết hạn trước khi hoàn thành. Gắn free-form tag như `purpose=oci-compute-bastion-lab` và `owner=<ten-cua-ban>` để dễ tìm tài nguyên sau buổi học.

### 3.3. Policy cho người triển khai lab

Ví dụ sau giả định quản trị viên đã tạo compartment `OCILab` và group `OCILabBuilders` trong identity domain `Default`. Thay bằng tên thật. Người học không cần tự cấp quyền cho chính mình.

~~~text
Allow group 'Default'/'OCILabBuilders' to manage instance-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage volume-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage virtual-network-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to manage bastion-family in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to read instance-agent-plugins in compartment OCILab
Allow group 'Default'/'OCILabBuilders' to inspect work-requests in compartment OCILab
~~~

Đây là bộ quyền cho **người xây dựng và dọn toàn bộ lab trong một compartment riêng**. Quyền quản lý mạng cho phép tạo VCN, subnet, gateway và NSG; quyền Compute và volume phục vụ vòng đời VM cùng lưu trữ; quyền Bastion phục vụ tài nguyên Bastion và session.

Nếu môi trường dùng image tùy chỉnh ở compartment khác, defined tags, khóa mã hóa riêng hoặc tài nguyên dùng chung, quản trị viên cần cấp quyền tương ứng theo tài nguyên thật. Lab chọn platform image Oracle Linux để tránh phụ thuộc ảnh Marketplace hoặc ảnh nội bộ.

Bộ quyền này rộng hơn nhu cầu của người chỉ đăng nhập một máy đã có sẵn. Trong vận hành thực tế, tách người quản trị mạng, người tạo VM và người tạo session; giới hạn quyền theo compartment và nhiệm vụ. Đối chiếu [quyền cho Compute](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/instances.htm) và [Bastion IAM Policies](https://docs.oracle.com/en-us/iaas/Content/Bastion/Reference/bastionpolicyreference.htm) khi thiết kế policy cho môi trường thật.

## 4. Chốt tham số và chuẩn bị hai cặp khóa SSH

### 4.1. Bảng tham số

| Tham số | Giá trị lab hoặc cách lấy |
| --- | --- |
| Compartment | `OCILab` |
| Region | Một region đã chọn, dùng nhất quán trong Console và CLI |
| VCN | `vcn-oci-lab`, CIDR `10.38.0.0/16` |
| Subnet | `subnet-private-lab`, regional private subnet, CIDR `10.38.10.0/24` |
| Route table | `rt-private-lab` |
| Service Gateway | `sgw-oci-lab` |
| Security list | `sl-private-lab` |
| NSG cho VM | `nsg-compute-ssh` |
| Compute | `vm-oci-lab`, Oracle Linux platform image |
| Bastion | `BastionLab` |
| Local TCP port | `2222`, đổi nếu đang có tiến trình sử dụng |
| Người dùng Linux | `opc` cho Oracle Linux trong lab |
| Thời hạn phiên | 30 phút cho mỗi lần thực hành kết nối |

Các tên VCN, subnet và instance ở đây là tên tài nguyên mẫu. Riêng tên Bastion dùng chữ và số để phù hợp yêu cầu đặt tên của dịch vụ.

Ngoài tên hiển thị, ghi lại OCID của compartment, instance, Bastion và session. Ghi thêm private IP của VM và private endpoint IP của Bastion sau khi tạo. OCID giúp xác định đúng tài nguyên khi có nhiều tên trùng nhau.

### 4.2. Tạo khóa trên máy cá nhân

Trong Bash local:

~~~bash
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh/oci-lab-vm" -C "oci-lab-vm"
ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh/oci-lab-session" -C "oci-lab-session"

chmod 600 "$HOME/.ssh/oci-lab-vm" "$HOME/.ssh/oci-lab-session"
~~~

Đặt passphrase khi được hỏi. Nếu tên file đã tồn tại, chọn tên mới và cập nhật toàn bộ lệnh sau đó, không ghi đè khóa đang sử dụng.

| File | Đưa vào đâu? | Mục đích |
| --- | --- | --- |
| `oci-lab-vm.pub` | Mục SSH public key khi tạo Compute | Cấp khả năng xác thực Linux cho chủ khóa VM |
| `oci-lab-vm` | Chỉ giữ trên máy cá nhân | SSH tới `opc` qua tunnel |
| `oci-lab-session.pub` | Mục SSH public key khi tạo session | Khai báo khóa được dùng với session |
| `oci-lab-session` | Chỉ giữ trên máy cá nhân | Xác thực kết nối tới Bastion session |

Chỉ upload file có đuôi `.pub`. Không copy private key lên VM, không dán vào Console, user data, Git hoặc báo cáo bài học. Không cần bật SSH agent forwarding cho lab.

## 5. Tạo mạng riêng và đường đến Oracle Services Network

### 5.1. Tạo VCN và các thành phần mạng

Trong Console, chọn đúng region và compartment `OCILab`. Mở **Networking → Virtual cloud networks** rồi tạo VCN `vcn-oci-lab` với CIDR `10.38.0.0/16`.

Dùng luồng tạo VCN thủ công để chủ động chọn tài nguyên. Bật DNS resolution cho VCN; giữ DHCP options dùng bộ phân giải do VCN cung cấp.

Tạo lần lượt:

1. Route table `rt-private-lab`.
2. Security list `sl-private-lab`.
3. Regional subnet `subnet-private-lab`, CIDR `10.38.10.0/24`.
4. Đặt subnet thành **private**, không cho VNIC nhận public IPv4.
5. Gắn subnet với `rt-private-lab`, DHCP options của VCN và `sl-private-lab`.

Trong security list riêng của lab:

- Không có ingress cho TCP 22.
- Nếu có rule ingress cho toàn bộ giao thức hoặc toàn bộ cổng từ VCN/subnet, bỏ rule đó khỏi cấu hình lab.
- Có thể giữ các rule ICMP phục vụ chẩn đoán và Path MTU nếu đã được cấu hình.
- Luồng chính giữ egress stateful cho mọi giao thức tới `0.0.0.0/0` để tránh trộn bài học SSH với bài học lọc chiều ra.

Egress rule chỉ cho phép lưu lượng ở lớp bảo mật mạng; nó không tự tạo đường đi. Bài không tạo Internet Gateway, NAT Gateway hoặc default route Internet. VM vẫn không có đường truy cập Internet tổng quát. Với production, thiết kế egress theo dịch vụ cần dùng và kiểm thử riêng.

Nếu subnet tự gắn thêm default security list, kiểm tra danh sách security list đang áp dụng và bỏ association thừa hoặc bỏ những ingress mở rộng trong tài nguyên lab riêng. Mục tiêu là không có đường cho phép SSH nào ngoài rule NSG sẽ thêm sau.

### 5.2. Tạo Service Gateway và route

Trong VCN, tạo Service Gateway `sgw-oci-lab`, chọn service CIDR label tương ứng **All <region> Services in Oracle Services Network** của region hiện tại.

Trong `rt-private-lab`, thêm route:

| Trường | Giá trị |
| --- | --- |
| Destination type | Service |
| Destination service | All <region> Services in Oracle Services Network |
| Target type | Service Gateway |
| Target | `sgw-oci-lab` |

Không thay service CIDR label bằng `0.0.0.0/0`. Không tự nhập một IP public cố định của dịch vụ Oracle.

Service Gateway cho phép tới các dịch vụ Oracle được hỗ trợ trong region, không thay thế NAT để tải tùy ý từ Internet. Các lệnh kiểm tra lab không yêu cầu `dnf install`, tải JDK hoặc tải ứng dụng từ kho công cộng. Xem [Access to Oracle Services: Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm).

### 5.3. Tạo NSG cho Compute

Tạo `nsg-compute-ssh` trong `vcn-oci-lab`. Tạm thời chưa thêm ingress SSH vì chưa biết địa chỉ private endpoint của Bastion.

Giữ NSG không có các rule ingress rộng. Ở bước tạo VM, gắn NSG này vào primary VNIC.

Security list và NSG có hiệu lực theo **hợp các rule cho phép**. NSG hẹp không thu hồi một rule SSH rộng ở security list; vì vậy bước kiểm tra security list ở trên là bắt buộc cho cấu hình lab. Cơ chế này được giải thích trong [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

**Điểm kiểm tra:** subnet là private; route table có route tới Service Gateway; subnet không có ingress TCP 22 rộng; NSG đã được tạo trong đúng VCN.

## 6. Triển khai Oracle Linux Compute

Vào **Compute → Instances → Create instance**. Cấu hình:

| Nhóm cấu hình | Lựa chọn |
| --- | --- |
| Tên và compartment | `vm-oci-lab`, `OCILab` |
| Image | Oracle Linux platform image còn được hỗ trợ |
| Shape | VM nhỏ phù hợp ngân sách, quota và kiến trúc image |
| Availability domain | Một AD có capacity cho shape đã chọn |
| VCN/subnet | `vcn-oci-lab` / `subnet-private-lab` |
| Primary VNIC | Gắn `nsg-compute-ssh` |
| Public IPv4 | Không cấp |
| SSH key | Upload hoặc paste nội dung `oci-lab-vm.pub` |
| Boot volume | Dung lượng cần thiết cho image, nằm trong ngân sách |
| User data | Để trống; không cần tải package cho lab |

Giữ Oracle Cloud Agent hoạt động nếu image hỗ trợ. Luồng port forwarding không phụ thuộc Bastion plugin, nên có thể hoàn thành kết nối cơ bản trước khi thực hành Managed SSH.

Kiểm tra màn hình tổng hợp trước khi tạo, nhất là public IP, shape và boot volume. Sau khi instance chuyển sang **Running**:

1. Mở chi tiết primary VNIC.
2. Ghi lại private IPv4 được cấp; trong các ví dụ sau dùng `10.38.10.25`, nhưng phải thay bằng giá trị thật.
3. Xác nhận public IP trống.
4. Xác nhận VNIC đang thuộc `nsg-compute-ssh`.
5. Ghi lại OCID của instance và boot volume.

Không ép chọn private IP giống ví dụ nếu địa chỉ đó đã được cấp cho tài nguyên khác. Trạng thái Running chỉ xác nhận vòng đời máy; SSH server có thể cần thêm thời gian để sẵn sàng.

Quy trình và các trường có thể thay đổi theo phiên bản Console; đối chiếu [Creating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm) nếu tên mục hiển thị khác.

**Điểm kiểm tra:** có đúng một VM lab Running trong private subnet, có boot volume và private IP, không có public IP.

## 7. Tạo Bastion và mở đúng đường tới Compute

### 7.1. Tạo tài nguyên Bastion

Trong Console, tìm dịch vụ **Bastion**, thường nằm trong **Identity & Security**. Chọn compartment `OCILab`, tạo Bastion với:

- Name: `BastionLab`.
- Target VCN: `vcn-oci-lab`.
- Target subnet: `subnet-private-lab`.
- Client CIDR allowlist: public IPv4 hiện tại của máy thực hành, dạng `<IP-thuc>/32`.
- Maximum session time-to-live: 30 phút cho lab.
- Không cần bật tính năng FQDN hoặc SOCKS5.

Ví dụ `203.0.113.25/32` chỉ minh họa cú pháp; đây không phải địa chỉ để dùng nguyên xi. Nếu truy cập qua mạng doanh nghiệp có nhiều địa chỉ egress, dùng danh sách CIDR đã được quản trị viên xác nhận.

Chờ Bastion hoạt động rồi ghi lại **Private endpoint IP address**. Ví dụ giả định là `10.38.10.10`; thay bằng địa chỉ thực tế.

Không mở allowlist thành `0.0.0.0/0` để chữa lỗi. Thời hạn tối đa hiện được cấu hình trong khoảng 30–180 phút; lab chọn đầu thấp của khoảng này. Tham khảo [Creating a Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-bastion.htm).

### 7.2. Thêm ingress SSH vào NSG của VM

Trong `nsg-compute-ssh`, thêm một rule:

| Trường | Giá trị |
| --- | --- |
| Direction | Ingress |
| Stateless | Không chọn, dùng stateful |
| Source type | CIDR |
| Source CIDR | `<BastionPrivateIP>/32` |
| IP protocol | TCP |
| Source port | All |
| Destination port | `22` |
| Description | SSH from OCI Bastion private endpoint |

Với ví dụ trên, source là `10.38.10.10/32`. Không dùng private IP của VM làm source, và không giới hạn source port thành 22: phía kết nối thường dùng cổng nguồn tạm thời.

Rule stateful theo dõi luồng kết nối và cho phép lưu lượng trả lời tương ứng. Các rule egress của subnet trong lab cũng đã cho phép đường đi cần thiết.

Địa chỉ Bastion và VM nằm cùng VCN nên có kết nối nội bộ; không thêm route Internet cho chặng SSH này. Nếu dùng Bastion ở subnet khác trong cùng VCN, phải kiểm tra cấu hình bảo mật và đường đi của cả hai subnet.

Oracle hướng dẫn dùng private endpoint IP của Bastion để cho phép truy cập máy đích trong [Allowing Network Access From the Bastion](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connectingtosessions.htm).

**Điểm kiểm tra:** allowlist chứa IP công cộng của client; ingress TCP 22 của VM chỉ cho phép private endpoint IP của Bastion. Hai giá trị này có vai trò khác nhau.

## 8. Tạo phiên port forwarding và đăng nhập

### 8.1. Tạo session

Mở `BastionLab` → **Sessions → Create session**:

1. Chọn **SSH port forwarding session**.
2. Đặt tên phiên dễ nhận biết, ví dụ `ssh-vm-lab`.
3. Chọn máy đích hoặc nhập private IP thật của `vm-oci-lab`.
4. Đặt target port thành `22`.
5. Cung cấp public key `oci-lab-session.pub`.
6. Đặt TTL 30 phút, không vượt mức tối đa của Bastion.
7. Tạo phiên và chờ trạng thái **Active**.

Ghi lại OCID, private IP đích, port đích và thời điểm hết hạn. Chọn **Copy SSH command** của đúng session vừa tạo. Không lấy lệnh từ session đã hết hạn hoặc session của máy khác.

Tham khảo các trường tạo phiên trong [Creating a Port Forwarding Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-session-port-forwarding.htm).

### 8.2. Terminal A: giữ SSH tunnel

Ưu tiên lệnh do Console sinh, thay placeholder private key và local port. Dạng lệnh dưới đây minh họa cách ràng buộc listener chỉ trên loopback; phải thay session OCID, hostname và private IP bằng giá trị thật:

~~~bash
ssh -i "$HOME/.ssh/oci-lab-session" -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -N -L 127.0.0.1:2222:10.38.10.25:22 -p 22 ocid1.bastionsession.oc1.REGION.REPLACE_ME@host.bastion.REGION.oci.oraclecloud.com
~~~

Không đoán hostname từ tên hiển thị region. Lấy nguyên phần user `<session_OCID>@<host>` từ lệnh mà Console cung cấp.

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `-i oci-lab-session` | Khóa xác thực vào Bastion session |
| `-N` | Không mở remote shell trên endpoint Bastion |
| `-L 127.0.0.1:2222:<VM_IP>:22` | Chuyển TCP từ loopback local tới SSH của VM |
| `IdentitiesOnly=yes` | Ưu tiên dùng danh tính đã chỉ định |
| `ExitOnForwardFailure=yes` | Thoát nếu không thiết lập được forwarding, ví dụ local port đã bận |
| `ServerAliveInterval` | Gửi keepalive; không gia hạn TTL của session |

Nếu có yêu cầu xác nhận host key lần đầu, kiểm tra đúng hostname và đối chiếu fingerprint qua nguồn tin cậy của môi trường khi có. Không tắt `StrictHostKeyChecking` để bỏ qua cảnh báo.

Sau khi xác thực, terminal có thể đứng yên và không hiện dấu nhắc. Đây là trạng thái bình thường của tunnel có `-N`; giữ terminal mở. Việc tạo listener thành công chưa chứng minh SSH server đích truy cập được, vì kết nối tới đích được sử dụng khi có client đi qua tunnel.

### 8.3. Terminal B: SSH vào Oracle Linux

Trong terminal local thứ hai:

~~~bash
ssh -i "$HOME/.ssh/oci-lab-vm" -o IdentitiesOnly=yes -o HostKeyAlias=oci-lab-vm -p 2222 opc@127.0.0.1
~~~

Lần này dùng **khóa VM**, không phải khóa session. Địa chỉ `127.0.0.1:2222` là đầu local của tunnel; không phải public endpoint của Compute.

`HostKeyAlias=oci-lab-vm` giúp lưu host key theo tên logic của VM thay vì chỉ theo cổng local. Với nhiều VM, dùng alias khác nhau. Nếu tạo lại VM, xác minh việc thay đổi host key trước khi cập nhật bản ghi cũ.

Trước khi chấp nhận host key máy đích trong môi trường cần bảo đảm cao, đối chiếu fingerprint qua kênh quản trị tin cậy, ví dụ console connection được cấp quyền riêng. Khi đang có kênh quản trị tin cậy vào máy, có thể đọc fingerprint bằng `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` nếu khóa đó tồn tại và là thuật toán client đang dùng. Đọc fingerprint từ chính kết nối chưa được xác minh không tạo ra bằng chứng độc lập.

Luồng hai terminal này tương ứng với [Connecting to a Port Forwarding Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connect-port-forwarding.htm). Không dùng `-A` hoặc mở local listener ra toàn bộ mạng bằng `0.0.0.0`.

## 9. Kiểm chứng kết quả và thử giới hạn truy cập

### 9.1. Kiểm tra bên trong VM

Sau khi đăng nhập thành công, chạy trên **Oracle Linux VM**:

~~~bash
whoami
hostname
cat /etc/os-release
ip -brief address
ip route
sudo systemctl is-active sshd
sudo ss -lntp '( sport = :22 )'
~~~

Kết quả mong đợi:

- `whoami` trả về `opc`.
- Thông tin hệ điều hành khớp Oracle Linux đã chọn.
- Interface chính có private IP đúng với primary VNIC trong Console.
- `sshd` hoạt động và lắng nghe trên TCP 22.

Lệnh `ip route` trong guest thường có default route tới virtual router của subnet. Điều đó không chứng minh subnet có Internet Gateway hoặc NAT Gateway: quyết định đi tiếp nằm ở route table của OCI.

Tương tự, không dùng riêng `ip address` trong guest để kết luận có hay không public IP OCI. Kiểm tra trường public IP của primary VNIC trong Console là bằng chứng trực tiếp cho yêu cầu của bài.

### 9.2. Các phép thử có kiểm soát

| Phép thử | Cách làm | Kết quả mong đợi |
| --- | --- | --- |
| Khóa VM đúng | SSH ở terminal B bằng `oci-lab-vm` | Vào được `opc` |
| Khóa sai ở lớp Linux | Thoát shell, thử terminal B với `oci-lab-session` thay cho `oci-lab-vm` | Bị từ chối nếu khóa session chưa được cấp quyền trên VM |
| Đóng tunnel | Thoát shell, nhấn Ctrl+C ở terminal A rồi SSH lại từ terminal B | Không kết nối được tới local port 2222 |
| Thu hồi phiên | Mở lại tunnel bằng phiên hợp lệ, sau đó xóa session trong Console | Phiên bị thu hồi; không tạo lại kết nối bằng session cũ |
| Hết TTL | Quan sát một phiên hết hạn hoặc xem thời điểm hết hạn | Muốn truy cập lại phải tạo session hợp lệ mới |

Thực hiện phép thử khóa sai **trước phần Managed SSH** để khóa session chưa được plugin cấp quyền cho `opc`. Giữ tùy chọn `IdentitiesOnly=yes` và tránh cấu hình SSH local tự thêm nhiều IdentityFile, nếu không phép thử có thể vô tình dùng một khóa hợp lệ khác.

Không lấy việc sửa NSG rồi quan sát một SSH connection đang mở làm phép thử thu hồi quyết định: connection tracking có thể ảnh hưởng lưu lượng đã tồn tại. Muốn thử lại rule mạng, đóng kết nối cũ và mở kết nối mới. Muốn kết thúc quyền truy cập lab ngay, xóa session và kiểm tra lại trạng thái.

Sau phép thử thu hồi, tạo session mới nếu còn thực hành phần tiếp theo. Không mở rộng CIDR để làm cho kết quả thử “thành công”.

## 10. Phần mở rộng: kết nối bằng Managed SSH

Phần này dùng lại VM và hạ tầng mạng vừa tạo; không cần tạo thêm Compute.

### 10.1. Chuẩn bị plugin

Mở chi tiết `vm-oci-lab`, tìm mục **Oracle Cloud Agent** hoặc danh sách agent plugins trong phần quản lý instance:

1. Xác nhận các plugin không bị dừng hàng loạt.
2. Bật plugin **Bastion**.
3. Chờ trạng thái **Running**, không chỉ dựa vào công tắc Enabled.
4. Nếu plugin chưa Running, kiểm tra DNS, route đến Service Gateway, egress HTTPS và agent của image.

Thay đổi trạng thái plugin có thể mất vài phút; hướng dẫn Oracle lưu ý có thể tới 10 phút. Xem [Managing Plugins with Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/manage-plugins.htm).

Có thể kiểm tra dịch vụ từ shell đang hoạt động bằng:

~~~bash
sudo systemctl status oracle-cloud-agent --no-pager
sudo systemctl status sshd --no-pager
~~~

Không tắt firewall hoặc mở ingress từ Internet để sửa trạng thái plugin. Plugin cần đường liên lạc với dịch vụ; luồng SSH tới máy đích vẫn cần rule TCP 22 từ Bastion private endpoint.

### 10.2. Tạo và dùng Managed SSH session

Trong `BastionLab`, tạo session mới:

- Session type: **Managed SSH session**.
- Target instance: `vm-oci-lab`.
- Operating system username: `opc`.
- Port: `22`.
- Public key: `oci-lab-session.pub`.
- TTL: 30 phút.

Chờ phiên Active, chọn **Copy SSH command**, thay `<privateKey>` bằng đường dẫn tới `oci-lab-session` ở mọi vị trí được lệnh yêu cầu. Lệnh thường có thành phần proxy qua endpoint Bastion; giữ nguyên cấu trúc được Console tạo.

Với Managed SSH, khóa được khai báo cho session tham gia vào cơ chế cấp quyền trên máy thông qua plugin. Không áp dụng máy móc quy tắc “bước SSH vào VM phải dùng khóa VM” của luồng port forwarding cho loại session này.

Sau khi đăng nhập, chạy lại `whoami` và `hostname`, xác nhận vẫn là cùng VM. Thực hiện theo [Creating a Managed SSH Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/create-session-managed-ssh.htm) và [Connecting to a Managed SSH Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/connect-managed-ssh.htm).

## 11. Tùy chọn: kiểm tra tài nguyên bằng OCI CLI

Phần này giả định OCI CLI đã được cấu hình xác thực với đúng tenancy, region và quyền của lab. Không dùng SSH private key thay cho API signing key.

Các biến và lệnh bên dưới chạy trong **Bash local có OCI CLI**, không phải mặc định trên VM:

~~~bash
export OCI_CLI_REGION="REPLACE_WITH_REGION_ID"
export INSTANCE_OCID="REPLACE_WITH_INSTANCE_OCID"
export BASTION_OCID="REPLACE_WITH_BASTION_OCID"

oci compute instance get --instance-id "$INSTANCE_OCID"
oci bastion bastion get --bastion-id "$BASTION_OCID"
oci bastion session list --bastion-id "$BASTION_OCID" --all
~~~

Đối chiếu lifecycle state, OCID và thông tin đích của session với Console. Không suy ra tên hoặc IP từ thứ tự trả về trong danh sách.

Có thể tạo một **session port forwarding mới** bằng CLI:

~~~bash
export VM_PRIVATE_IP="10.38.10.25"

oci bastion session create-port-forwarding --bastion-id "$BASTION_OCID" --display-name "ssh-vm-cli" --target-private-ip "$VM_PRIVATE_IP" --target-port 22 --ssh-public-key-file "$HOME/.ssh/oci-lab-session.pub" --session-ttl 1800 --wait-for-state ACTIVE
~~~

Thay private IP trước khi chạy. Lệnh tạo thêm một session thật; không chạy lặp vô hạn nếu chưa hiểu trạng thái phiên trước. TTL ở CLI tính bằng giây, nên `1800` tương ứng 30 phút. Lấy lệnh SSH do dịch vụ cung cấp trong thông tin session hoặc từ Console.

Phần CLI giúp tách thao tác tạo session khỏi việc mở kết nối SSH. Khi tự động hóa hạ tầng đầy đủ, cần quản lý các OCID đầu vào và phụ thuộc tài nguyên rõ ràng; không đưa private key vào mã Terraform hoặc Git. Các tham số session được mô tả tại [OCI CLI: create-port-forwarding](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/bastion/session/create-port-forwarding.html).

## 12. Quan sát vận hành và xử lý lỗi

### 12.1. Lưu bằng chứng có ích

Trước khi dọn tài nguyên, ghi lại các giá trị hoặc ảnh chụp cần thiết:

| Bằng chứng | Điều cần chứng minh |
| --- | --- |
| Instance và primary VNIC | VM thuộc private subnet, public IP trống |
| NSG và các security list của subnet | Không có rule SSH rộng hơn nguồn Bastion đã chọn |
| Bastion | Đúng target VCN, subnet và client allowlist |
| Session | Đúng target private IP, port 22, TTL và trạng thái |
| Kết quả lệnh Linux | Đăng nhập được đúng user và đúng máy |
| Kết quả thử thu hồi | Session cũ không còn dùng để mở lại kết nối |
| Danh sách tài nguyên sau cleanup | Không còn boot volume hoặc tài nguyên lab bị bỏ quên |

Không đưa private key, passphrase, token hoặc API credential vào bằng chứng. Nếu chia sẻ công khai, che các định danh và địa chỉ không cần thiết.

Nếu được cấp quyền Audit, tìm sự kiện tạo/xóa Bastion session trong đúng compartment và khoảng thời gian. Audit giúp trả lời ai gọi API và lúc nào; không mặc định nó ghi lại nội dung từng lệnh shell được chạy qua SSH. Muốn lưu vết thao tác trong Linux, cần thiết kế cơ chế log hệ điều hành riêng. Xem [Securing Bastion — Auditing](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/bastion_security.htm).

### 12.2. Chẩn đoán theo chặng

Đường kiểm tra là: **IAM và trạng thái tài nguyên → máy cá nhân đến endpoint Bastion → private endpoint đến TCP 22 của VM → xác thực Linux**.

| Triệu chứng | Lớp có khả năng liên quan | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Không thấy instance hoặc Bastion | Sai region, compartment hoặc quyền | Kiểm tra bộ lọc trước, rồi policy và group |
| `NotAuthorizedOrNotFound` | Quyền hoặc định danh | Đối chiếu OCID, region, compartment và IAM; không kết luận ngay tài nguyên đã bị xóa |
| Không tạo được VM | Quota, capacity, image/shape hoặc policy | Đọc work request; chọn shape/AD phù hợp sau khi kiểm tra ngân sách |
| Terminal A timeout trước xác thực | Mạng client hoặc endpoint | Kiểm tra DNS, egress TCP 22, hostname và đường VPN |
| Bastion đóng kết nối sớm | Allowlist hoặc session không hợp lệ | Kiểm tra IP egress, session Active, TTL và OCID trong lệnh |
| Terminal A báo `Permission denied (publickey)` | Xác thực session | Kiểm tra khóa session, public key đã khai báo và policy thuật toán của SSH client |
| Terminal A chạy nhưng terminal B timeout | Chặng Bastion đến VM | Kiểm tra private IP đích, NSG gắn đúng VNIC, source /32, TCP 22 và firewall Linux |
| Terminal B báo `Permission denied (publickey)` | Đăng nhập Linux | Kiểm tra user `opc`, khóa VM và authorized keys |
| `Address already in use` tại local | Cổng 2222 đã bận | Dừng tunnel cũ hoặc đổi cả local port và lệnh SSH terminal B |
| Managed SSH tạo thất bại | Plugin, agent hoặc đường dịch vụ | Xác nhận plugin Running, DNS, SGW route, egress HTTPS và user hợp lệ |
| Đang kết nối thì bị ngắt | TTL, mất mạng hoặc idle | Kiểm tra thời hạn phiên và mạng; keepalive không kéo dài TTL |

Để lấy thêm thông tin, thêm `-v` vào **lệnh SSH đang lỗi**. Theo hướng dẫn Oracle cho Bastion, không dùng `-vv` hoặc `-vvv`. Phân biệt thông báo từ terminal A với terminal B trước khi đổi khóa.

Nếu public IPv4 thay đổi, sửa Bastion allowlist rồi **tạo session mới**; thay đổi allowlist không cập nhật các session đã tồn tại. Đây là chi tiết được nêu trong [Problems Connecting to a Session](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/troubleshooting_connect_session_failed.htm).

Nếu đã SSH được bằng port forwarding nhưng Managed SSH vẫn thất bại, điều đó giúp thu hẹp vấn đề vào agent, plugin hoặc điều kiện riêng của Managed SSH. Xem [Managed SSH Session Creation Failed](https://docs.oracle.com/en-us/iaas/Content/Bastion/Tasks/troubleshooting_managed_ssh_session_creation_failed.htm).

## 13. Dọn tài nguyên và kiểm soát chi phí còn lại

Chỉ xóa các tài nguyên đã tạo cho bài này, đối chiếu tên, OCID, compartment và tag trước khi thao tác. Nếu có tài nguyên dùng chung, giữ nguyên và nhờ chủ sở hữu xử lý phần phụ thuộc.

Thực hiện theo thứ tự:

1. Thoát mọi shell trên VM bằng `exit`.
2. Dừng các tunnel local bằng Ctrl+C.
3. Xóa toàn bộ session lab còn tồn tại, gồm cả session tạo bằng CLI hoặc Managed SSH.
4. Xóa `BastionLab`, chờ private endpoint do dịch vụ quản lý được giải phóng.
5. Terminate `vm-oci-lab`. Nếu không cần giữ dữ liệu lab, chủ động chọn **xóa boot volume kèm theo** trong hộp thoại.
6. Kiểm tra mục Boot Volumes, Block Volumes và Backups để xóa phần lab còn sót, nếu có.
7. Xóa `nsg-compute-ssh` sau khi không còn VNIC tham gia.
8. Xóa private subnet khi không còn tài nguyên hoặc private endpoint phụ thuộc.
9. Xóa route tới Service Gateway, sau đó xóa Service Gateway và các route table, security list riêng của lab khi không còn được gắn.
10. Xóa VCN sau khi các thành phần phụ thuộc đã được dọn. Các đối tượng mặc định của VCN được xử lý cùng quy trình xóa VCN.
11. Nếu đã tạo group hoặc policy chỉ dùng cho buổi lab, quản trị viên thu hồi phần đó sau khi xác nhận không còn người dùng phụ thuộc.

Nếu Console từ chối xóa subnet vì vẫn có VNIC/private endpoint, đọc tài nguyên phụ thuộc thay vì thử xóa tài nguyên khác ngẫu nhiên. Kiểm tra Bastion đã thực sự được xóa và Compute đã kết thúc vòng đời.

Không coi thao tác Stop instance là cleanup hoàn chỉnh. Boot volume, backup hoặc tài nguyên khác còn giữ lại vẫn cần được xem xét riêng. Hướng dẫn [Terminating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/terminatinginstance.htm) cho phép chủ động xóa boot volume cùng VM; kiểm tra lựa chọn thực tế thay vì dựa vào mặc định.

Chi phí trong Console có thể cập nhật trễ. Đối chiếu danh sách tài nguyên để xác nhận cleanup trước, rồi kiểm tra báo cáo chi phí sau khi dữ liệu xuất hiện.

## 14. Tiêu chí hoàn thành và giới hạn của mô hình

Lab hoàn thành khi có đủ bằng chứng sau:

- Một Oracle Linux Compute đã chạy trong private subnet và không có public IP.
- Bastion chỉ nhận client từ CIDR egress đã xác định.
- Ingress SSH của VM chỉ được cấp từ private endpoint của Bastion; đã kiểm tra cả NSG lẫn security list.
- Port forwarding hoạt động với hai lớp khóa đúng vai trò.
- Đã xác minh user, hostname và SSH server ở máy đích.
- Đã thử đóng tunnel hoặc thu hồi session và xác nhận không mở lại kết nối bằng phiên cũ.
- Nếu thực hiện phần mở rộng, Managed SSH hoạt động sau khi Bastion plugin Running.
- Tài nguyên lab, đặc biệt boot volume và các session phát sinh, đã được kiểm kê và dọn.

Mô hình này có một VM và một boot volume gắn với vòng đời máy; nó chưa cung cấp tính sẵn sàng cao cho ứng dụng. Bastion là đường quản trị, không thay load balancer, cơ chế phục hồi VM hoặc chiến lược backup. Khi phát triển thành môi trường chạy ứng dụng Java hay cơ sở dữ liệu Oracle, cần thiết kế thêm phân bố tài nguyên, phục hồi dữ liệu, giám sát và phân quyền theo vai trò.

Điểm cần giữ lại từ bài thực hành là một chuỗi kiểm chứng rõ ràng: đúng người được tạo session, đúng nguồn được đi qua mạng, đúng khóa được đăng nhập máy, quyền truy cập hết hạn theo thiết kế và tài nguyên được dọn khi không còn dùng.

