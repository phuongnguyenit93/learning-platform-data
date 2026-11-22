# DNS trong VPC và DHCP option

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách máy EC2, container và các workload khác **phân giải tên miền** trong Amazon VPC; phân biệt DNS với kết nối mạng thực tế.
- Mô tả **AmazonProvidedDNS / Route 53 VPC Resolver**, các địa chỉ DNS đặc biệt của VPC và hai thuộc tính **enableDnsSupport**, **enableDnsHostnames**.
- Hiểu **DHCP option set** truyền cấu hình DNS, domain suffix, NTP và các thông số khác cho instance như thế nào; tạo, gắn, thay đổi và kiểm chứng option set an toàn.
- Chọn giữa **DNS mặc định của AWS**, **máy chủ DNS tùy chỉnh**, **Route 53 private hosted zone** và **Resolver inbound/outbound endpoints** trong từng tình huống.
- Chẩn đoán lỗi DNS có hệ thống bằng AWS CLI, công cụ hệ điều hành, Route 53 Resolver query logs và kiến thức về VPC, security group, route, IAM.
- Đánh giá tác động của DNS đến ứng dụng an toàn, khả dụng qua nhiều Availability Zone, giám sát và chi phí.

Bài thuộc chương **Mạng VPC** của module **CLOUD_PROVIDERS_AWS**. Trong hệ sinh thái AWS, dù ứng dụng chạy trên EC2, ECS, EKS hay Lambda và truy cập S3, RDS, DynamoDB hoặc SQS, phân giải DNS đúng là điều kiện rất thường gặp để kết nối dịch vụ thành công. DNS hỗ trợ khả năng thay đổi địa chỉ và phục hồi, nhưng DNS **không thay thế** thiết kế mạng, phân quyền, mã hóa hay backup.

## 1. DNS có nhiệm vụ gì trong một VPC?

**Domain Name System (DNS)** chuyển tên dễ nhớ thành các bản ghi phục vụ kết nối. Ví dụ, ứng dụng cần truy cập địa chỉ `api.internal.example.com`; DNS có thể trả về địa chỉ IP riêng của một dịch vụ nội bộ. Sau khi nhận địa chỉ IP, ứng dụng mới mở kết nối TCP/UDP hoặc HTTPS theo đường mạng thích hợp.

| Bản ghi | Mục đích thường gặp | Ví dụ minh họa |
| --- | --- | --- |
| **A** | Tên miền → IPv4 | `api.internal.example.com → 10.20.5.24` |
| **AAAA** | Tên miền → IPv6 | `api.internal.example.com → 2001:db8::24` |
| **CNAME** | Alias từ tên này sang tên khác | `web.example.com → app.example.net` |
| **TXT** | Dữ liệu dạng text; thường dùng xác minh miền, SPF... | `_verify.example.com` |
| **MX** | Máy chủ nhận email cho miền | `example.com` |
| **PTR** | Ánh xạ ngược IP → tên theo miền reverse DNS | Bản ghi reverse có cấu hình tương ứng |

Một số loại bản ghi như **alias record của Route 53** là tính năng ở cấp Route 53, không phải loại bản ghi DNS chuẩn riêng biệt.

Trong đường đi của yêu cầu có ba khái niệm:

1. **Stub resolver / DNS client:** Thành phần trong hệ điều hành hoặc thư viện ứng dụng gửi câu hỏi về tên miền.
2. **Recursive resolver:** Máy chủ nhận câu hỏi rồi tra cứu/cached kết quả. Trong VPC, AWS có dịch vụ **Route 53 VPC Resolver**.
3. **Authoritative DNS:** Nguồn sở hữu bản ghi cho một DNS zone, chẳng hạn một Route 53 hosted zone hoặc DNS doanh nghiệp.

~~~mermaid
flowchart LR
    A[Ứng dụng: api.internal.example.com] --> B[DNS client trên EC2 / container]
    B --> C[Recursive DNS resolver]
    C --> D{Có bản ghi / cache phù hợp?}
    D -->|Có| E[Trả A / AAAA / CNAME...]
    D -->|Cần tra cứu| F[DNS nguồn phù hợp]
    F --> E
    E --> G[Ứng dụng mở kết nối tới IP đích]
~~~

**DNS thành công chưa đồng nghĩa kết nối thành công.** Một tên có thể phân giải đúng thành IP riêng nhưng request vẫn timeout vì route table, security group, NACL, firewall, endpoint, port hoặc ứng dụng không lắng nghe. Ngược lại, EC2 có thể truy cập IP trực tiếp nhưng không gọi được tên do DNS client/resolver lỗi.

## 2. AmazonProvidedDNS / Route 53 VPC Resolver

Khi tạo VPC, AWS cung cấp **Route 53 VPC Resolver** (tên cũ thường gặp: **Route 53 Resolver**, cũng gọi là **Amazon DNS server**). Đây là bộ phân giải DNS tích hợp cho tài nguyên trong VPC; thường không cần tự triển khai máy chủ DNS chỉ để giải tên EC2, dịch vụ AWS hoặc tên Internet.

Các địa chỉ thường dùng để truy cập VPC Resolver:

| Địa chỉ | Ý nghĩa |
| --- | --- |
| **Primary VPC IPv4 CIDR + 2** | Ví dụ VPC `10.20.0.0/16` thì resolver ở `10.20.0.2`; lấy theo **primary IPv4 CIDR** của VPC |
| **169.254.169.253** | Địa chỉ IPv4 link-local dành cho DNS AWS |
| **fd00:ec2::253** | Địa chỉ IPv6 của DNS AWS trong ngữ cảnh hỗ trợ IPv6 |

Các địa chỉ trên là các cách truy cập cùng năng lực phân giải VPC, **không phải ba máy chủ DNS độc lập do bạn quản trị**. Địa chỉ IPv4 `VPC+2` dành cho VPC tương ứng; không coi đó là DNS server công cộng để máy ở Internet hoặc on-premises truy vấn trực tiếp.

Ví dụ với VPC `10.20.0.0/16`:

~~~text
VPC CIDR:                    10.20.0.0/16
AmazonProvidedDNS:           10.20.0.2
Địa chỉ link-local DNS:      169.254.169.253
Địa chỉ DNS IPv6:            fd00:ec2::253
Ví dụ EC2 private IPv4:      10.20.10.34
~~~

Resolver có thể phân giải:

- **Tên DNS mặc định của EC2** theo khả năng và thuộc tính DNS của VPC.
- **Record thuộc Route 53 private hosted zones** được liên kết phù hợp với VPC.
- **Tên miền công cộng** bằng cơ chế recursive lookup.
- **Tên thuộc miền nội bộ khác** khi có Resolver rules/forwarding hoặc cấu hình phân giải tương ứng.

**Trường hợp IPv6-only:** Không áp dụng máy móc giả định rằng mọi instance sẽ lấy DNS như mô hình IPv4 thông thường. AWS có các cơ chế cấp DNS qua DHCP/địa chỉ link-local riêng cho IPv6-only subnet; cần kiểm tra resolver thực tế trong hệ điều hành.

### AmazonProvidedDNS khác Route 53 public hosted zone thế nào?

| Thành phần | Nhiệm vụ |
| --- | --- |
| **Route 53 VPC Resolver** | Nhận câu hỏi DNS từ workload/VPC; trả lời từ thông tin VPC, private hosted zone, cache hoặc truy vấn tiếp |
| **Route 53 public hosted zone** | Lưu bản ghi authoritative cho tên miền công cộng |
| **Route 53 private hosted zone** | Lưu bản ghi DNS nội bộ, chỉ được phân giải trong các VPC đã liên kết hoặc qua cơ chế kết nối Resolver phù hợp |
| **Route 53 Resolver inbound/outbound endpoint** | Kết nối luồng phân giải DNS giữa VPC và mạng/DNS bên ngoài VPC |
| **DHCP option set** | Chỉ cho máy biết DNS server/domain và thông số mạng nên dùng; **không chứa** bản ghi A/CNAME của ứng dụng |

Sử dụng Route 53 public hosted zone không tự tạo kết nối private; sử dụng private hosted zone không tự nối mạng giữa hai VPC. DNS và routing là các lớp cần được thiết kế song song.

## 3. Hai thuộc tính DNS quan trọng của VPC

Amazon VPC có hai thuộc tính ảnh hưởng đến DNS, độc lập với DHCP option set.

| Thuộc tính | Chức năng chính | Khi nào cần quan tâm |
| --- | --- | --- |
| **enableDnsSupport** | Cho phép phân giải thông qua DNS do AWS cung cấp cho VPC | Muốn dùng AmazonProvidedDNS/Route 53 VPC Resolver |
| **enableDnsHostnames** | Kiểm soát khả năng VPC cấp hostname DNS công cộng cho EC2 có public IPv4 theo điều kiện; cùng với DNS support cần cho một số khả năng DNS nội bộ | EC2 public DNS hostname; Route 53 private hosted zones; private DNS của interface VPC endpoint |

**Quy tắc nên nhớ:** Để sử dụng tên tùy chỉnh từ **Route 53 private hosted zone** và **private DNS của interface VPC endpoint**, cần bật **cả hai** `enableDnsSupport=true` và `enableDnsHostnames=true`.

Mặc định của VPC có thể khác nhau theo cách VPC được tạo. Ví dụ, `enableDnsSupport` thường mặc định bật; `enableDnsHostnames` thường mặc định tắt ở VPC tự tạo và bật ở default VPC. Vì vậy hãy kiểm tra giá trị thật thay vì suy đoán.

Kiểm tra bằng AWS CLI, thay VPC ID và Region bằng giá trị thật:

~~~bash
aws ec2 describe-vpc-attribute --vpc-id vpc-0123456789abcdef0 --attribute enableDnsSupport --region ap-southeast-1

aws ec2 describe-vpc-attribute --vpc-id vpc-0123456789abcdef0 --attribute enableDnsHostnames --region ap-southeast-1
~~~

Kết quả tương ứng có cấu trúc như sau (rút gọn):

~~~json
{
  "VpcId": "vpc-0123456789abcdef0",
  "EnableDnsSupport": { "Value": true }
}
~~~

Nếu muốn thay đổi, có thể vào **VPC console → Your VPCs → chọn VPC → Actions → Edit VPC settings**, xem và bật hai thuộc tính được yêu cầu. Với hệ thống đang hoạt động, thay đổi DNS cần được lên kế hoạch, có phương án rollback và quan sát ứng dụng phụ thuộc.

### Ví dụ: private DNS cho dịch vụ nội bộ

Giả sử private hosted zone `internal.example.com` được liên kết với VPC `vpc-app` và chứa:

~~~text
api.internal.example.com.   A   10.20.10.24
db.internal.example.com.    CNAME   database-cluster.internal.example.net.
~~~

EC2 trong VPC, khi dùng VPC Resolver, có thể hỏi những tên này. Tuy nhiên:

- Bản ghi `api` chỉ có ý nghĩa nếu địa chỉ được cập nhật đúng vòng đời ứng dụng; với service động, nên ưu tiên DNS trỏ tới ALB/NLB nội bộ hoặc tài nguyên phù hợp hơn là hardcode private IP.
- Bản ghi `db` phải trỏ tới tên DNS thực sự có thể phân giải; tùy thiết kế, nên dùng hostname endpoint mà RDS/Aurora cung cấp.
- Máy ngoài VPC không tự động phân giải được private hosted zone chỉ nhờ có VPN hay VPC peering. Cần liên kết zone và/hoặc giải pháp Resolver thích hợp.

## 4. DHCP option set là gì?

**DHCP (Dynamic Host Configuration Protocol)** cho phép máy nhận thông số mạng cần dùng, ví dụ địa chỉ IP thuê và thông tin DNS. Trong AWS, **DHCP option set** là một cấu hình mạng gắn với VPC, ảnh hưởng đến các giá trị DHCP server cung cấp cho các instance.

Với VPC thông thường:

~~~mermaid
sequenceDiagram
    participant I as EC2 instance / OS
    participant D as Amazon DHCP server
    participant R as DNS server
    I->>D: Xin/đổi mới DHCP lease
    D-->>I: IP & thông số mạng, DNS, domain, ...
    I->>R: DNS query tới nameserver được cấu hình
    R-->>I: DNS answer
~~~

**Phân biệt hai vai trò:** DHCP option set giúp máy biết **hỏi DNS ở đâu**; DNS resolver trả lời **tên này ứng với địa chỉ nào**. Việc sửa DHCP option set không tạo bản ghi mới trong Route 53 và không tự làm cho private hosted zone của mạng khác xuất hiện.

### Những trường quan trọng

| Tùy chọn | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **domain-name-servers** | Danh sách DNS resolver do instance sử dụng | `AmazonProvidedDNS` hoặc IP DNS nội bộ/Doanh nghiệp |
| **domain-name** | Tên miền/suffix được cung cấp cho DHCP client | Dùng `corp.example.com` làm hậu tố trong một số phép phân giải tên ngắn |
| **ntp-servers** | Máy chủ đồng bộ thời gian | Tích hợp chính sách đồng bộ thời gian doanh nghiệp |
| **netbios-name-servers** | Máy chủ NetBIOS/WINS, chủ yếu môi trường Windows cũ | Ứng dụng phụ thuộc giải tên NetBIOS |
| **netbios-node-type** | Cách Windows NetBIOS phân giải tên | Mạng Windows có yêu cầu NetBIOS |
| **ipv6-address-preferred-lease-time** | Khoảng thời gian ưu tiên của địa chỉ IPv6 cấp qua DHCPv6 | Kiểm soát tần suất renew DHCPv6 phù hợp workload |

AWS cung cấp **default DHCP option set** cho Region; theo cách dùng mặc định, DNS server thường là **AmazonProvidedDNS**. DHCP option set tùy chỉnh dùng khi cần DNS server riêng, domain suffix hoặc chính sách bổ sung. Một option set có thể được gắn với nhiều VPC, nhưng **mỗi VPC chỉ có một DHCP option set tại một thời điểm**.

### Quy tắc vận hành rất quan trọng

1. **DHCP option set không sửa trực tiếp sau khi tạo:** muốn đổi giá trị, tạo **option set mới**, rồi gắn vào VPC.
2. **Gắn option set mới không đòi hỏi reboot/relaunch toàn bộ EC2:** instance thường nhận cập nhật khi gia hạn DHCP lease; có thể mất vài giờ hoặc chủ động renew phù hợp với hệ điều hành.
3. **Thay option set tác động đến toàn VPC**, bao gồm nhiều subnet/AZ. Không thể dùng option set để phân một DNS server khác riêng cho từng subnet như một thuộc tính VPC DHCP độc lập.
4. **Đừng dùng cấu hình “No DHCP option set” để thử tùy tiện:** DNS nhận từ DHCP có thể bị vô hiệu hoặc khác nhau theo loại nền tảng EC2; trên một số Nitro instance, DNS link-local vẫn có thể được cấu hình mặc định. Cần kiểm tra hệ điều hành và hành vi thực tế.
5. **Không nhầm với `enableDnsSupport` và `enableDnsHostnames`:** đây là thuộc tính VPC riêng, không phải tên hai tùy chọn trong DHCP option set.

### Có thể gộp AmazonProvidedDNS và DNS tùy chỉnh không?

AWS cho phép khai báo một số kết hợp DNS server trong option set, nhưng **trộn `AmazonProvidedDNS` với custom DNS server có thể tạo hành vi khó dự đoán** do cách client chuyển sang nameserver khác nhau. Các DNS server được liệt kê không nhất thiết xử lý tất cả zone giống nhau.

**Khuyến nghị triển khai:**

- Với hệ thống chủ yếu trên AWS, ưu tiên để client dùng **AmazonProvidedDNS** và thêm **Resolver forwarding rules** cho miền đặc biệt khi cần.
- Nếu doanh nghiệp bắt buộc dùng DNS tùy chỉnh, hãy cấu hình DNS server tùy chỉnh tự phân giải hoặc **conditional forward** các domain AWS/private cần thiết qua kiến trúc Resolver được hỗ trợ.
- Chỉ trộn nhiều resolver khi hiểu rõ cơ chế client, hành vi failover, split-horizon DNS và đã thử nghiệm.

## 5. Cách chọn DNS theo bài toán

| Nhu cầu | Cấu hình khởi đầu nên đánh giá | Lý do |
| --- | --- | --- |
| EC2/ECS/Lambda trong một VPC, gọi dịch vụ AWS và Internet | AmazonProvidedDNS, bật thuộc tính VPC cần thiết | Ít vận hành, có phân giải VPC và tên công cộng |
| Tên nội bộ `api.internal.example.com` | Route 53 private hosted zone + VPC association | Quản lý bản ghi DNS nội bộ bằng AWS |
| EC2 cần phân giải `corp.example.com` do DNS on-premises quản lý | VPC Resolver outbound endpoint + forwarding rule | Chỉ chuyển đúng miền ra DNS doanh nghiệp |
| Máy tại văn phòng cần phân giải tên của private hosted zone trong AWS | VPC Resolver inbound endpoint + conditional forwarder on-premises | Cung cấp điểm nhận truy vấn được hỗ trợ qua đường kết nối private |
| Ứng dụng bắt buộc dùng DNS của Active Directory/doanh nghiệp | DHCP option set trỏ custom DNS, kèm conditional forwarding cho tên AWS | Duy trì domain services, quản lý namespace phân tán |
| Muốn giám sát DNS query theo VPC | Route 53 VPC Resolver query logging | Xem nguồn query, tên được hỏi, kết quả, hỗ trợ xử lý lỗi |
| Muốn lọc DNS domain độc hại qua VPC Resolver | Route 53 Resolver DNS Firewall | Thiết lập rules theo domain, theo dõi alert/block |

Không phải nhu cầu nào cũng cần inbound/outbound endpoints. Các endpoint này có cấu hình mạng, bảo mật và chi phí riêng. Một hệ thống đơn giản dùng AmazonProvidedDNS và private hosted zone có thể đã đủ.

## 6. Thực hành đọc và thay đổi DHCP option set

> **Môi trường lab:** Dùng VPC thử nghiệm riêng đã được cấp quyền. Các ID `vpc-0123456789abcdef0`, `dopt-0123456789abcdef0`, địa chỉ `10.20.x.x` và domain `example.com` bên dưới là dữ liệu minh họa; thay bằng thông số thật. Không thay option set của VPC production nếu chưa đánh giá phụ thuộc DNS trong toàn VPC.

### Bước 1 — Xem VPC đang dùng DHCP option set nào

~~~bash
aws ec2 describe-vpcs \
  --vpc-ids vpc-0123456789abcdef0 \
  --query 'Vpcs[0].{VpcId:VpcId,Cidr:CidrBlock,DhcpOptionsId:DhcpOptionsId}' \
  --region ap-southeast-1
~~~

Ghi lại **DhcpOptionsId** hiện tại để có đường quay lại nếu việc thử nghiệm thất bại.

### Bước 2 — Xem các tùy chọn đã khai báo

~~~bash
aws ec2 describe-dhcp-options \
  --dhcp-options-ids dopt-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Đọc các entry `domain-name`, `domain-name-servers`, `ntp-servers` và trường khác. Nếu đang dùng cấu hình mặc định, tên DNS có thể là `AmazonProvidedDNS`. Đừng kết luận rằng phải có IP DNS tùy chỉnh mới là cấu hình hợp lệ.

### Bước 3 — Tạo option set mới có DNS nội bộ (khi lab cần)

Ví dụ máy chủ DNS `10.20.10.10` và `10.20.20.10` do nhóm vận hành quản lý, đặt ở các AZ khác nhau; chỉ thực hiện nếu hai máy chủ DNS này **đã tồn tại và có thể truy cập** từ client:

~~~bash
aws ec2 create-dhcp-options \
  --dhcp-configurations \
    Key=domain-name,Values=corp.example.com \
    Key=domain-name-servers,Values=10.20.10.10,10.20.20.10 \
  --region ap-southeast-1
~~~

Lệnh trả về ID của DHCP option set mới. Chú ý: **không có máy chủ DNS hợp lệ ở hai địa chỉ ví dụ thì cấu hình trên sẽ làm hỏng việc phân giải tên** của client nhận nó. Muốn tập trung học DNS mặc định, chỉ cần quan sát option set có sẵn thay vì chạy lệnh thay đổi.

### Bước 4 — Gắn vào VPC thử nghiệm

~~~bash
aws ec2 associate-dhcp-options \
  --dhcp-options-id dopt-0newexample12345 \
  --vpc-id vpc-0123456789abcdef0 \
  --region ap-southeast-1
~~~

ID `dopt-0newexample12345` là chỗ giữ chỗ, **không phải** ID hợp lệ để chạy nguyên văn. Sau khi liên kết, đọc lại VPC và option set, kiểm tra DNS client trong EC2. Trong thực tế, đổi DHCP option set ảnh hưởng đến mọi instance của VPC sau khi chúng nhận DHCP lease mới. Tùy hệ điều hành, có thể chủ động renew lease để thử ngay; phải cân nhắc ảnh hưởng tới kết nối đang hoạt động.

### Bước 5 — Khôi phục phương án cũ sau lab

Gắn lại **DhcpOptionsId đã lưu từ Bước 1** nếu cần rollback. Sau khi không còn VPC sử dụng option set thử nghiệm, có thể xóa nó theo quy trình quản lý tài nguyên của môi trường lab. Không xóa DHCP option set đang gắn với VPC.

## 7. Kiểm tra DNS bên trong EC2: Linux và Windows

Sau khi đọc trạng thái AWS, kiểm tra **cấu hình thực mà hệ điều hành đang sử dụng**. DHCP lease mới và cache/resolved của hệ điều hành có thể khiến kết quả khác với cấu hình mong đợi.

### Linux

~~~bash
# Xem cấu hình nameserver được dùng; resolv.conf có thể do systemd-resolved quản lý
cat /etc/resolv.conf

# Trên hệ thống có systemd-resolved
resolvectl status

# Kiểm tra tên miền với DNS client mặc định của OS
getent hosts api.internal.example.com

# Gửi truy vấn trực tiếp tới AmazonProvidedDNS
dig @169.254.169.253 api.internal.example.com A

# So sánh với DNS nội bộ nếu đã cấu hình và có đường mạng
dig @10.20.10.10 api.internal.example.com A
~~~

**Lưu ý:** `dig @...` giúp kiểm tra một DNS server cụ thể; kết quả có thể khác truy vấn thông qua resolver mặc định của OS. File `/etc/resolv.conf` đôi khi chỉ trỏ đến local stub như `127.0.0.53`; cần xem `resolvectl status` để xác định upstream thực tế. Trên môi trường container, DNS có thể qua DNS proxy của runtime/cluster trước khi tới VPC Resolver.

### Windows PowerShell

~~~powershell
Get-DnsClientServerAddress
ipconfig /all
Resolve-DnsName -Name api.internal.example.com
Resolve-DnsName -Name api.internal.example.com -Server 169.254.169.253
~~~

So sánh kết quả từ resolver mặc định và AmazonProvidedDNS. Nếu máy Windows tham gia Active Directory, cũng cần xem DNS client domain suffix và DNS server của domain controller, vì truy vấn tên nội bộ thường có quy tắc riêng.

### Cách đọc kết quả DNS

| Tín hiệu | Ý nghĩa có thể | Bước tiếp theo |
| --- | --- | --- |
| Có A/AAAA mong đợi | DNS đã trả lời | Kiểm tra TCP/HTTP, route, security group, TLS và dịch vụ đích nếu ứng dụng vẫn lỗi |
| **NXDOMAIN** | Resolver báo tên không tồn tại trong ngữ cảnh trả lời | Kiểm tra zone/record, tên đầy đủ, VPC association, split-horizon và rule forwarding |
| **SERVFAIL** | Resolver không hoàn tất được truy vấn | Kiểm tra upstream DNS, forwarder, lỗi DNSSEC/timeout và log |
| **Timeout** | Không nhận được câu trả lời đúng thời hạn | Kiểm tra IP DNS, routing, SG/NACL dành cho custom DNS, DNS service, endpoint và kết nối hybrid |
| **Trả IP sai / cũ** | Bản ghi/target khác mong đợi, cache hoặc forward vào DNS zone khác | Kiểm tra authoritative source, TTL, cache OS/resolver và quy tắc chọn zone |
| **Lúc được lúc không** | Upstream DNS khác nhau hoặc node/AZ/cấu hình DNS không đồng nhất | Kiểm tra từng server, từ nhiều instance, liên AZ và lúc tải cao |

Tránh dựa hoàn toàn vào `ping`: DNS có thể phân giải đúng nhưng ICMP bị chặn. Với dịch vụ HTTPS, thử `curl` hoặc công cụ ứng dụng phù hợp sau khi đã xác nhận tên và địa chỉ.

## 8. DNS cho môi trường hybrid: inbound và outbound Resolver

Một doanh nghiệp có thể sử dụng cùng lúc:

- VPC chạy ứng dụng trong AWS với zone `aws.corp.example.com`;
- mạng văn phòng/on-premises có DNS riêng authoritative cho `corp.example.com`;
- kết nối mạng riêng thông qua **Site-to-Site VPN** hoặc **Direct Connect**.

**Yêu cầu 1:** EC2 trong VPC cần truy vấn `db.corp.example.com`, do DNS on-premises quản lý.

**Yêu cầu 2:** Máy on-premises cần truy vấn `api.aws.corp.example.com`, do Route 53 private hosted zone quản lý.

~~~mermaid
flowchart TB
    subgraph AWS["AWS Region / VPC"]
      App[EC2 / ECS / Lambda] --> RV[Route 53 VPC Resolver]
      RV --> PHZ[Private hosted zone: aws.corp.example.com]
      RV --> Rule[Forwarding rule: corp.example.com]
      Rule --> OE[Resolver outbound endpoint]
      IE[Resolver inbound endpoint] --> RV
    end
    subgraph OnPrem["Mạng doanh nghiệp"]
      Client[Client on-premises] --> DN[DNS doanh nghiệp]
      DNS[DNS authoritative: corp.example.com] --- DN
    end
    OE -->|Truy vấn đến DNS doanh nghiệp| DN
    DN -->|Forward aws.corp.example.com| IE
~~~

Sơ đồ chỉ thể hiện **luồng DNS logic**; trên thực tế còn cần kết nối mạng riêng, route hai chiều và security group cho các endpoint.

### Outbound: AWS hỏi DNS ở mạng khác

1. Tạo **Route 53 VPC Resolver outbound endpoint** trong VPC thích hợp, thường có IP endpoint trải trên ít nhất hai AZ.
2. Cho endpoint truy cập các DNS server đích trên cổng DNS được dùng (thường **UDP/TCP 53**) qua kết nối mạng hợp lệ.
3. Tạo **Resolver forwarding rule** cho miền cụ thể, ví dụ `corp.example.com`, với IP DNS đích.
4. **Associate rule** với VPC có workload cần sử dụng.
5. Cho EC2 tiếp tục dùng **AmazonProvidedDNS** nếu phù hợp: VPC Resolver tự chuyển query của miền theo rule; không phải đổi DHCP option set sang IP on-premises cho từng máy.

### Inbound: mạng ngoài VPC hỏi DNS của AWS

1. Tạo **Resolver inbound endpoint**, chọn subnet/IP, phân bố AZ và security group phù hợp.
2. DNS on-premises cấu hình **conditional forwarder** cho `aws.corp.example.com` trỏ tới **IP của inbound endpoint**.
3. VPC chứa inbound endpoint phải liên kết đúng private hosted zone hoặc có resolver rule cần thiết.
4. Kiểm tra kết nối VPN/Direct Connect, route, NACL, SG và forwarder trên cả hai phía.

**Quan trọng:** Không forward trực tiếp từ DNS on-premises hoặc DNS ở VPC khác tới địa chỉ **VPC CIDR + 2** (ví dụ `10.20.0.2`); đó không phải cách dùng được hỗ trợ qua biên mạng. Sử dụng **Resolver inbound endpoint** cho luồng vào VPC.

### Tránh vòng lặp chuyển tiếp DNS

Ví dụ sai: VPC Resolver chuyển `corp.example.com` ra DNS on-premises; DNS on-premises lại forward chính `corp.example.com` vào VPC Resolver. Truy vấn quay vòng rồi timeout hoặc SERVFAIL.

Giải pháp là phân rõ **DNS nào authoritative cho từng zone** và viết **conditional forwarding rules một chiều** cho mỗi phần không gian tên, ví dụ:

- `corp.example.com`: on-premises authoritative;
- `aws.corp.example.com`: Route 53 private hosted zone authoritative;
- VPC forward `corp.example.com` ra on-premises, đồng thời ưu tiên phân giải zone `aws.corp.example.com` cục bộ đúng theo quy tắc/độ cụ thể;
- on-premises chỉ forward `aws.corp.example.com` vào inbound endpoint.

Khi có nhiều private hosted zone và Resolver rules trùng/bao phủ miền nhau, cần kiểm tra **quy tắc ưu tiên và độ cụ thể tên miền** theo tài liệu AWS hiện hành; không phỏng đoán thứ tự từ tên rule.

## 9. DHCP custom DNS và Active Directory

Một số ứng dụng Windows/Active Directory cần DNS server là domain controller hoặc DNS tập trung, thay vì chỉ dùng AmazonProvidedDNS.

**Thiết kế mẫu:**

1. EC2 trong VPC nhận DNS server `10.20.10.10` và `10.20.20.10` qua DHCP option set.
2. Hai DNS server này biết cách phân giải domain của tổ chức, ví dụ `ad.corp.example.com`.
3. Đối với private hosted zone AWS, DNS server tùy chỉnh dùng conditional forwarding tới đường Route 53 Resolver được hỗ trợ (ví dụ inbound endpoint nếu cần vượt phạm vi VPC).
4. Đảm bảo DNS server có sẵn qua nhiều AZ, có giám sát health, và có phương án xử lý khi một máy mất kết nối.

**Không nhầm DNS với domain join:** Cấp domain suffix trong DHCP không tự gia nhập AD, không tự tạo record SRV và không cấp quyền truy cập tài nguyên. AD join cần đúng DNS, mạng, đồng bộ thời gian, danh tính và chính sách riêng.

Nếu sử dụng AWS Managed Microsoft AD hoặc dịch vụ tích hợp Active Directory khác, cần làm theo hướng dẫn DNS forwarding và DHCP option set tương ứng với **loại directory** đó. Tránh cấu hình chung cho mọi directory mà không thử các bản ghi SRV/Kerberos.

## 10. DNS và thiết kế độ sẵn sàng qua nhiều AZ

VPC trải trên một Region và có thể chứa subnet tại nhiều Availability Zone. Dịch vụ VPC Resolver tích hợp quản lý bởi AWS, nhưng **đường DNS ứng dụng sử dụng** vẫn có thể có điểm lỗi:

| Thành phần | Rủi ro | Cách giảm rủi ro |
| --- | --- | --- |
| AmazonProvidedDNS | Giới hạn lưu lượng DNS/link-local hoặc cấu hình VPC không đúng | Tối ưu caching, đo lưu lượng, bật DNS attributes đúng |
| Custom DNS trên một EC2 | Máy hoặc AZ gặp sự cố | Chạy nhiều DNS server qua các AZ, giám sát, kiểm thử failover |
| Resolver endpoint | Một IP/ENI endpoint hoặc đường mạng lỗi | Đặt endpoint nhiều IP trên các AZ, đúng security group và route |
| Forwarding rule | Domain đích không khớp, trỏ tới upstream sai | Kiểm tra namespace, ưu tiên rule, giám sát lỗi |
| Private hosted zone | Chưa associate VPC hoặc record sai | Quản lý DNS bằng IaC, review thay đổi và xác thực từ đúng VPC |
| DNS client/cache | Dùng kết quả cũ tới TTL; cache không nhất quán | Chọn TTL theo nhu cầu failover, có quy trình xác minh cache |
| Ứng dụng phụ thuộc hostname | DNS ok nhưng đích không hoạt động | Health check, autoscaling, ALB/NLB, failover DB và retries phù hợp |

AWS có giới hạn lưu lượng với các dịch vụ link-local dùng chung trên instance, trong đó có DNS, IMDS và NTP. Một ứng dụng tạo truy vấn DNS cho từng request, không cache gì, có thể tự gây nghẽn. Sử dụng kết nối/pool và DNS caching hợp lý, nhưng đảm bảo cache không cản trở việc chuyển endpoint khi failover.

**TTL (time to live)** ảnh hưởng tới thời gian client tiếp tục dùng bản ghi cũ, nhưng không bảo đảm mọi client chuyển sang IP mới chính xác tại một thời điểm. Cấu hình failover ứng dụng cần xem thêm timeout, retry, connection pool, circuit breaker, health check và trạng thái database. DNS không giải quyết RPO/RTO của dữ liệu.

## 11. Bảo mật: DNS hữu ích nhưng không phải tường lửa

DNS góp phần vận hành mạng an toàn:

- **Private hosted zone** hạn chế phạm vi phân giải tên nội bộ, song không tự mã hóa dữ liệu hoặc cấp quyền truy cập dịch vụ.
- **IAM** giới hạn ai được sửa VPC settings, DHCP option set, Resolver rules, hosted zones và query logging. Ứng dụng vẫn cần IAM role phù hợp khi gọi API AWS.
- **AWS Route 53 Resolver DNS Firewall** có thể kiểm soát/lọc domain được hỏi qua VPC Resolver, nhưng không kiểm soát mọi giao thức ứng dụng và không thay security group/AWS WAF.
- **Route 53 Resolver query logging** hỗ trợ giám sát DNS query, nguồn phát sinh, phản hồi và sự kiện firewall; bản ghi log có thể chứa tên nội bộ nhạy cảm nên cần bảo vệ quyền truy cập và đặt thời hạn lưu.
- **TLS/HTTPS** bảo vệ nội dung kết nối đến đích; kết quả DNS không thay kiểm tra certificate, authentication hoặc authorization.

**Lưu ý về security group/NACL:** AWS không cho lọc trực tiếp lưu lượng **đến/từ Amazon DNS server** bằng security group hoặc network ACL theo cách thông thường. Nhưng nếu sử dụng **DNS server tùy chỉnh** hoặc **Resolver endpoint** có ENI trong subnet, route, security group và NACL lại rất quan trọng. Tránh nghĩ rằng mở UDP 53 trong security group của EC2 luôn sửa được lỗi AmazonProvidedDNS.

### Các chi phí thường bị bỏ quên

- VPC Resolver có sẵn cho nhu cầu cơ bản; các tính năng bổ sung như **Resolver inbound/outbound endpoint**, **DNS Firewall** và **query logging/dịch vụ lưu log** có thể phát sinh phí riêng.
- Endpoint thường cần nhiều IP/ENI để có khả năng sẵn sàng; chi phí dựa theo cấu hình endpoint và lưu lượng theo biểu giá.
- DNS server tự quản trên EC2 còn có chi phí instance, EBS, cập nhật bảo mật, vận hành và giám sát.
- Nếu truy vấn DNS qua mạng hybrid, tính cả kết nối, truyền dữ liệu và chi phí quản lý đường mạng phù hợp.
- Với Route 53 hosted zone và truy vấn thuộc loại được tính phí, cần đối chiếu bảng giá hiện hành theo dịch vụ.

Kiểm chứng bằng **AWS Pricing Calculator**, **AWS Cost Explorer** và **AWS Budgets**; dùng tags để phân biệt môi trường lab, dev và production. Không chọn custom DNS server chỉ vì nhìn giá EC2 mà bỏ qua nhân lực vận hành.

## 12. Bảng chẩn đoán lỗi DNS thường gặp

| Triệu chứng | Nguyên nhân cần xem | Cách kiểm tra có thứ tự |
| --- | --- | --- |
| Máy phân giải tên Internet được nhưng không thấy record private hosted zone | Hai DNS attributes, zone chưa associate, máy dùng custom DNS không forward đúng | Kiểm tra VPC attributes → DHCP DNS → VPC association/record → custom forwarder |
| `dig @169.254.169.253` có kết quả nhưng ứng dụng báo NXDOMAIN | OS/container hỏi DNS khác hoặc dùng search suffix/cache | Xem `resolvectl`/DNS policy, query cùng tên FQDN với từng nameserver |
| Sau khi đổi DHCP option set, một vài EC2 chưa đổi DNS | DHCP lease chưa renew hoặc OS quản lý DNS theo cấu hình riêng | Đọc config hệ điều hành, renew lease có kiểm soát, kiểm tra lại từ từng AZ |
| DNS on-premises không resolve tên private hosted zone | Chưa có inbound endpoint, rule forward sai, thiếu đường mạng | Test DNS IP inbound endpoint qua VPN/DX, port 53 UDP/TCP, association |
| EC2 không resolve được AD/domain nội bộ | Chọn nhầm DNS server; thiếu outbound rule/endpoint; DNS doanh nghiệp chưa trả lời | So sánh query với AmazonProvidedDNS và custom server; kiểm tra luồng forward |
| Tên trả IP đúng nhưng HTTPS timeout | Route, SG, NACL, endpoint, ứng dụng hoặc firewall | Test TCP/HTTPS đến IP/FQDN; theo dõi Flow Logs và service logs |
| Truy vấn thỉnh thoảng SERVFAIL | DNS upstream không ổn định, loop forwarding, endpoint lỗi, quá tải hoặc quota | Xem resolver query logs, thử từng server, kiểm tra retry/TTL và topology |
| Private DNS của interface endpoint không hoạt động | Thuộc tính VPC DNS, cấu hình private DNS endpoint, SG/NACL | Kiểm tra `enableDnsSupport`, `enableDnsHostnames`, endpoint state và DNS |
| DNS đã chuyển IP nhưng client vẫn gọi đích cũ | Cache TTL, pool kết nối, ứng dụng giữ IP | Kiểm tra TTL thực tế, cache OS/runtime, connection reuse |
| DNS của custom server chỉ hoạt động ở một AZ | DNS server/routing/endpoint IP có điểm lỗi | Thử từ từng AZ, từng nameserver, đo thời gian hồi phục |

**Quy trình xử lý gợi ý:**

~~~text
1. Xác nhận tên cần hỏi và record mong đợi (A/AAAA/CNAME/SRV...).
2. Xác nhận VPC, subnet, DNS attributes, DHCP option set của client.
3. Xem DNS server thực tế trong OS/container.
4. Query trực tiếp từng DNS server để tách lỗi client và lỗi upstream.
5. Nếu private zone: kiểm tra zone/record, VPC association và resolver rules.
6. Nếu hybrid/custom DNS: kiểm tra inbound/outbound endpoint, UDP/TCP 53,
   VPN/Direct Connect, SG/NACL/route và tránh forward loop.
7. Nếu DNS trả lời đúng: chuyển sang kiểm tra TCP/TLS, IAM và ứng dụng.
8. Bật query logging, đo lỗi/độ trễ, xác nhận kết quả từ nhiều AZ;
   chỉ thay cấu hình sau khi biết lớp gây lỗi.
~~~

### Có thể tìm DNS query logs ở đâu?

Trong **Route 53 VPC Resolver → Query logging**, tạo cấu hình log và liên kết với VPC cần theo dõi. Tùy lựa chọn, log có thể được gửi tới **CloudWatch Logs**, **Amazon S3** hoặc luồng phân phối được hỗ trợ. Một bản ghi có thể chứa VPC, nguồn IP/instance, tên cần tra, loại record, response code và câu trả lời.

**Giới hạn cần hiểu:** Resolver có cơ chế caching. Khi một truy vấn được trả từ cache, nó có thể không sinh bản ghi query log mới. Vì vậy “không có log cho lần lặp thứ hai” không nhất thiết là không có truy vấn ở cấp ứng dụng.

## 13. Ví dụ lựa chọn kiến trúc

### Tình huống A — Website mới chỉ dùng dịch vụ AWS

**Yêu cầu:** API chạy ECS/Fargate, truy cập RDS, S3 và SQS; các thành phần triển khai qua nhiều AZ; đội nhỏ muốn ít vận hành.

**Đề xuất:**

- Dùng **AmazonProvidedDNS** và bật hai thuộc tính DNS của VPC khi cần private names/private hosted zone.
- Cho API dùng **hostname endpoint của RDS**, tên endpoint S3/SQS phù hợp và endpoint riêng nếu có.
- Nếu có tên nội bộ cho API, tạo **Route 53 private hosted zone**, record trỏ tới **ALB nội bộ**.
- Giám sát DNS errors và request latency; giữ quyền IAM, SG, backup và budget theo nhu cầu.

**Vì sao:** Không cần vận hành hai máy chủ DNS chỉ để gọi tên dịch vụ AWS. Cơ chế tên của RDS có thể thay địa chỉ khi failover; ứng dụng nên tôn trọng DNS TTL và quản lý kết nối phù hợp.

### Tình huống B — EC2 cần Active Directory trong mạng doanh nghiệp

**Yêu cầu:** Windows EC2 trong VPC phải phân giải `ad.corp.example.com`, các bản ghi SRV của Domain Controller, đồng thời truy cập vài private hosted zones AWS.

**Đề xuất:**

- Cân nhắc DHCP option set để cấu hình DNS domain controllers riêng, phân bố nhiều AZ/vùng mạng theo thiết kế.
- Dùng conditional forwarding phù hợp cho các tên AWS/private. Nếu DNS tùy chỉnh nằm ngoài VPC, dùng **Resolver inbound endpoint** để truy vấn VPC Resolver.
- Đảm bảo VPN/DX, DNS port, thời gian và yêu cầu AD cần thiết; kiểm thử đăng nhập khi một DNS server dừng.

**Vì sao:** AD thường yêu cầu DNS authoritative cho domain của nó; dùng AmazonProvidedDNS độc lập không thay được các record AD.

### Tình huống C — Nhiều account AWS và một trung tâm dữ liệu

**Yêu cầu:** Mỗi nhóm có VPC/account riêng, dùng cùng miền nội bộ và vẫn cần truy vấn tên máy trong trung tâm dữ liệu.

**Đề xuất:**

- Thiết kế **DNS hub/shared services VPC** có Resolver endpoints được quản lý tập trung.
- Chia sẻ Resolver rules tới các VPC cần dùng qua cơ chế quản trị nhiều tài khoản thích hợp (ví dụ AWS Resource Access Manager nơi được hỗ trợ).
- Associate private hosted zones đúng VPC, xác định rõ quyền chủ sở hữu record và cách cập nhật.
- Tránh vòng lặp giữa hub và DNS on-premises; kiểm soát truy cập endpoint, query log và chi phí.

**Vì sao:** Quản lý DNS theo namespace và quy tắc chung giúp giảm cấu hình riêng lẻ trên hàng chục VPC, nhưng đòi hỏi kiểm soát thay đổi chặt hơn.

## 14. Checklist khi triển khai DNS/DHCP cho VPC

- [ ] Đã xác định đúng **Region, VPC ID, primary CIDR** và tên miền cần phân giải.
- [ ] Đã kiểm tra `enableDnsSupport` và `enableDnsHostnames` theo yêu cầu private hosted zone/interface endpoint.
- [ ] Đã đọc **DhcpOptionsId** và cấu hình DNS client thực tế trong OS/container.
- [ ] Đã chọn AmazonProvidedDNS hoặc custom DNS bằng lý do cụ thể, không trộn resolver tùy tiện.
- [ ] Nếu có private hosted zone: record hợp lệ, **VPC association** đúng, nguồn cập nhật record được quản lý.
- [ ] Nếu có hybrid: inbound/outbound endpoint, forward rule, DNS server đích, route và UDP/TCP 53 đã thử.
- [ ] Nếu có custom DNS: triển khai dư thừa qua AZ, giám sát và đã kiểm thử một máy DNS mất kết nối.
- [ ] Đã phân biệt lỗi **DNS resolution** với lỗi **TCP/TLS/SG/NACL/route/IAM** sau phân giải.
- [ ] Đã xem chính sách query logging/DNS Firewall, quyền IAM, bảo mật log và TTL.
- [ ] Có đường rollback khi đổi DHCP option set và lưu ID cấu hình trước thay đổi.
- [ ] Đã kiểm tra hoạt động khi failover, cache TTL, connection pool và ảnh hưởng tới RTO thực tế.
- [ ] Đã ước lượng chi phí Resolver endpoints, logs, DNS server tự quản và thiết lập cảnh báo ngân sách.

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Đọc cấu hình VPC đang chạy

Không thay đổi tài nguyên:

1. Dùng AWS CLI xem `enableDnsSupport`, `enableDnsHostnames` và `DhcpOptionsId`.
2. Đọc DNS server từ DHCP option set và cấu hình DNS client trên một EC2 lab.
3. Giải thích vì sao `10.20.0.2` và `169.254.169.253` có thể cùng đóng vai trò địa chỉ resolver trong VPC `10.20.0.0/16`.
4. So sánh `dig @169.254.169.253 example.com` với `dig example.com`.
5. Ghi lại lớp nào là **AWS VPC setting**, lớp nào là **DHCP option**, lớp nào là **DNS client/OS**.

### Bài tập 2 — Thiết kế private DNS

**Đề bài:** Ứng dụng ở hai AZ cần truy cập `orders.internal.example.com`; phía sau là ALB nội bộ.

Thiết kế tối thiểu:

- VPC attributes cần bật;
- private hosted zone và VPC association;
- loại record và đích trỏ vào ALB;
- cấu hình DNS server mà EC2/ECS client sử dụng;
- bước kiểm tra từ hai subnet, kèm đánh giá SG, route và HTTPS.

**Yêu cầu giải thích:** Tại sao tên DNS của ALB nên dùng thay vì một private IP ngẫu nhiên của task/instance?

### Bài tập 3 — Thiết kế hybrid DNS

Mạng on-premises quản lý `corp.example.com`, còn `aws.corp.example.com` nằm trong Route 53 private hosted zone. EC2 ở VPC và máy ở văn phòng cần phân giải tên của nhau.

Vẽ sơ đồ có đủ:

- DNS on-premises và Route 53 VPC Resolver;
- inbound endpoint, outbound endpoint;
- forwarding rule và domain đích;
- kết nối VPN/Direct Connect;
- lựa chọn nameserver từ DHCP option set;
- cách tránh vòng lặp truy vấn và đảm bảo hoạt động nếu một endpoint IP hỏng.

### Câu hỏi tự kiểm tra

1. **Vì sao private hosted zone của VPC A không tự động phân giải được từ VPC B đã peering?**  
   Vì việc **liên kết DNS zone hoặc cấu hình Resolver** là một vấn đề riêng với kết nối mạng. Peering cho tuyến trao đổi gói tin nhưng không tự chia sẻ mọi DNS zone.

2. **Bật `enableDnsSupport` có tự tạo một DNS record cho ứng dụng không?**  
   Không. Thuộc tính này điều khiển khả năng phân giải bằng AmazonProvidedDNS; record cần được tạo/quản lý ở nguồn authoritative phù hợp.

3. **Đổi DHCP option set hôm nay, có phải mọi EC2 đổi nameserver ngay lập tức không?**  
   Không nên giả định vậy. Máy nhận cấu hình mới khi lease được cập nhật hoặc renew; cache/thiết lập OS còn có thể ảnh hưởng.

4. **Tại sao `dig @169.254.169.253` trả IP đúng nhưng `curl https://api...` vẫn lỗi?**  
   Sau DNS, request còn phụ thuộc route, SG/NACL, TCP/TLS, ứng dụng, chứng chỉ, IAM hoặc chính sách dịch vụ.

5. **Khi nào cần custom DNS server?**  
   Khi có yêu cầu rõ như AD, DNS namespace doanh nghiệp hay chính sách phân giải đặc thù. Với nhiều bài toán đơn giản trên AWS, AmazonProvidedDNS và Resolver rules là phương án ít công vận hành hơn.

## 16. Kết luận

Trong AWS VPC, **Route 53 VPC Resolver/AmazonProvidedDNS** là nền tảng phân giải DNS; **hai thuộc tính DNS VPC** quyết định các khả năng phân giải và cấp hostname; **DHCP option set** định hướng DNS server/domain mà máy sử dụng. Muốn có tên nội bộ, dùng **private hosted zone** với VPC association đúng. Muốn phân giải xuyên biên VPC–on-premises, bổ sung **Resolver inbound/outbound endpoints và conditional forwarding rules**, đồng thời bảo đảm đường mạng hoạt động.

Khi thiết kế ứng dụng AWS an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí, hãy kiểm tra DNS **cùng** Region/AZ, IAM, VPC routing, security group, database failover, logging và ngân sách. Một thiết kế DNS tốt có nguồn authoritative rõ ràng, không có vòng lặp, ít điểm lỗi, có đường rollback và được xác minh từ client thật.

### Tài liệu AWS chính thức

- [Understanding Amazon DNS — Amazon VPC](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html)
- [DNS attributes for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns-updating.html)
- [DHCP option set concepts](https://docs.aws.amazon.com/vpc/latest/userguide/DHCPOptionSetConcepts.html)
- [Work with DHCP option sets](https://docs.aws.amazon.com/vpc/latest/userguide/DHCPOptionSet.html)
- [What is Route 53 VPC Resolver?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver.html)
- [Resolving DNS queries between VPCs and your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-DSN-queries-to-vpc.html)
- [Resolver query logging](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-query-logs.html)
- [Route 53 Resolver DNS Firewall](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-overview.html)

Khả năng dịch vụ, giới hạn và biểu giá có thể thay đổi; khi triển khai, đối chiếu tài liệu AWS và Region đang sử dụng.
