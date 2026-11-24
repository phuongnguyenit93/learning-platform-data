# Nhiều giao diện mạng, nhiều địa chỉ IP và định tuyến tại hệ điều hành

Một máy ảo cloud thường bắt đầu với một giao diện mạng (network interface) và một địa chỉ IP. Tuy nhiên, workload thực tế có thể cần nhiều đường kết nối: một đường cho lưu lượng người dùng, một đường cho quản trị, một đường tới hệ thống dữ liệu riêng hoặc nhiều địa chỉ IP để phục vụ các dịch vụ khác nhau. Khi đó, máy chủ cần được cấu hình nhiều giao diện mạng (multi-NIC), nhiều địa chỉ IP và quy tắc định tuyến phù hợp.

Thêm NIC hoặc IP mới chỉ là một phần của cấu hình. Gói tin còn phải đi qua route table của cloud, chính sách bảo mật của mạng ảo, firewall trong hệ điều hành và bảng định tuyến của chính máy chủ. Nếu các lớp này không thống nhất, máy có thể nhận được request nhưng gửi response qua sai giao diện, không truy cập được gateway hoặc tạo ra đường đi bất đối xứng.

Bài học này thuộc chương **Kết nối mạng cho workload** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, hiểu multi-NIC, địa chỉ IP và định tuyến tại hệ điều hành giúp thiết kế đường truyền rõ ràng, kiểm soát luồng vào/ra và vận hành workload nhiều mạng an toàn.

## 1. Giao diện mạng và địa chỉ IP

### 1.1. Network interface là gì?

**Network interface (NIC)** là giao diện mà hệ điều hành sử dụng để gửi và nhận frame mạng. Trên máy chủ vật lý, NIC thường là card mạng hoặc cổng mạng. Trên VM cloud, NIC thường là thiết bị mạng ảo được nền tảng cung cấp và gắn vào máy ảo.

Mỗi NIC có các thuộc tính như:

- Tên giao diện trong hệ điều hành, ví dụ **eth0**, **ens5**, **ens192** hoặc tên ổn định do hệ điều hành tạo.
- Địa chỉ MAC.
- Một hoặc nhiều địa chỉ IPv4/IPv6.
- MTU (Maximum Transmission Unit).
- Trạng thái link và tốc độ truyền được hệ điều hành quan sát.
- Route, gateway và DNS liên quan đến mạng.
- Chính sách bảo mật và subnet tương ứng trong cloud control plane.

Tên giao diện không phải định danh ổn định trên mọi hệ thống. Thứ tự NIC có thể thay đổi khi thay image, kernel hoặc cấu hình máy. Khi tự động hóa, nên dùng tên dự đoán được, MAC, metadata hoặc định danh do nền tảng cung cấp thay vì giả định NIC đầu tiên luôn là **eth0**.

### 1.2. Nhiều địa chỉ IP trên một NIC

Một NIC có thể gắn nhiều địa chỉ IP. Ví dụ, một máy chủ có thể dùng:

- IP chính cho quản trị hoặc kết nối nội bộ.
- IP phụ cho một dịch vụ riêng.
- Nhiều IP để phục vụ nhiều virtual host, listener hoặc ứng dụng cần bind vào địa chỉ cụ thể.
- Địa chỉ IPv6 bên cạnh IPv4.

Nhiều IP trên cùng NIC vẫn chia sẻ cùng đường truyền vật lý hoặc ảo và thường thuộc cùng subnet. Việc có thêm IP không tự tạo thêm băng thông hay một đường mạng độc lập.

Trong cloud, địa chỉ IP thường phải được khai báo hoặc gắn trong control plane của nhà cung cấp trước khi cấu hình trong guest OS. Một số nền tảng kiểm tra địa chỉ nguồn/đích ở lớp ảo hóa; tự ý gán IP không được nền tảng cấp có thể khiến gói tin bị loại bỏ. Cần làm theo quy trình của loại NIC và dịch vụ đang sử dụng.

### 1.3. Nhiều NIC trên một máy

Một máy có thể gắn nhiều NIC, mỗi NIC kết nối vào một subnet hoặc mạng ảo khác nhau. Ví dụ:

| NIC | Subnet minh họa | Vai trò |
|---|---|---|
| **ens5** | **10.10.1.0/24** | Nhận lưu lượng ứng dụng từ mạng frontend |
| **ens6** | **10.20.1.0/24** | Kết nối tới database hoặc dịch vụ backend |
| **ens7** | **10.30.1.0/24** | Mạng quản trị hoặc giám sát |

Thiết kế này có thể giúp tách luồng mạng, áp dụng chính sách bảo mật riêng và kiểm soát đường đi. Tuy nhiên, mỗi NIC vẫn dùng chung CPU, bộ nhớ, kernel và có thể dùng chung một số thành phần hạ tầng của VM. Multi-NIC không tự động mang lại tính sẵn sàng cao hoặc gộp băng thông.

### 1.4. Phân biệt NIC, IP và subnet

- **NIC:** giao diện gửi/nhận dữ liệu.
- **IP address:** địa chỉ logic được gán cho giao diện hoặc endpoint.
- **Subnet:** phạm vi địa chỉ IP và chính sách mạng mà endpoint thuộc về.
- **Gateway:** điểm chuyển tiếp gói tin tới mạng khác.
- **Route:** quy tắc chọn next hop hoặc giao diện để chuyển gói tin.
- **Route table:** tập hợp các route được hệ điều hành hoặc cloud control plane sử dụng.

Một NIC có thể có nhiều IP; một subnet có thể có nhiều NIC; một route table có thể chứa nhiều đường tới các subnet và gateway khác nhau. Không nên nhầm số lượng IP với số lượng NIC hoặc số lượng đường mạng độc lập.

## 2. Khi nào cần nhiều NIC hoặc nhiều IP?

### 2.1. Tách lưu lượng frontend và backend

Một ứng dụng có thể nhận request từ frontend network và truy cập database qua backend network. Gắn NIC riêng cho từng mạng giúp áp dụng security group, route và firewall phù hợp với từng luồng.

Ví dụ:

- **ens5** nhận kết nối HTTPS từ load balancer.
- **ens6** kết nối tới database trong subnet riêng.
- Ứng dụng chỉ lắng nghe địa chỉ frontend cho request người dùng.
- Kết nối database đi ra qua địa chỉ backend.

Cách thiết kế này giúp giảm khả năng dịch vụ backend vô tình lộ ra mạng người dùng. Tuy nhiên, firewall ở cả cloud và hệ điều hành vẫn cần được cấu hình đúng.

### 2.2. Tách mạng quản trị và mạng dữ liệu

Mạng quản trị có thể dùng cho SSH/RDP, monitoring, backup hoặc công cụ vận hành. Mạng dữ liệu phục vụ request của ứng dụng. Tách NIC giúp giới hạn cổng và địa chỉ được phép truy cập theo mục đích.

Không nên để mạng quản trị có default route hoặc public exposure nếu không cần thiết. Có thể chỉ cho phép kết nối quản trị từ bastion, VPN hoặc hệ thống quản lý tập trung.

### 2.3. Kết nối nhiều mạng hoặc nhiều tenant

Một appliance mạng, proxy, gateway hoặc máy xử lý dữ liệu có thể cần kết nối nhiều VPC/VNet, subnet hoặc mạng đối tác. Mỗi NIC có thể gắn vào một mạng riêng, trong khi hệ điều hành thực hiện routing hoặc firewall giữa các giao diện.

Trường hợp này đòi hỏi kiểm tra kỹ phạm vi tin cậy, IP overlap, route propagation, source/destination check và quyền forwarding. Không phải mọi VM nhiều NIC đều được phép làm router giữa các subnet.

### 2.4. Nhiều IP cho nhiều dịch vụ

Một máy chủ có thể sử dụng nhiều IP trên cùng NIC để:

- Bind các dịch vụ vào địa chỉ riêng.
- Duy trì địa chỉ dịch vụ khi chuyển ứng dụng hoặc thực hiện failover theo cơ chế được nền tảng hỗ trợ.
- Phục vụ nhiều endpoint hoặc nhiều chứng chỉ/virtual host theo kiến trúc ứng dụng.
- Phân biệt lưu lượng theo địa chỉ nguồn.

Nhiều IP trên một NIC phù hợp khi cần nhiều endpoint nhưng không cần tách đường truyền hoặc subnet.

### 2.5. Tách đường đi và chính sách lưu lượng

Máy có thể cần gửi một số loại lưu lượng qua gateway khác nhau. Ví dụ, traffic tới mạng nội bộ đi qua NIC backend, còn truy cập Internet đi qua NIC frontend. Khi đó, route table và policy routing của hệ điều hành cần phản ánh chính sách mong muốn.

Chỉ gắn thêm NIC không đảm bảo kernel chọn đúng NIC cho từng kết nối. Phải xác định route, source address và hành vi trả lời của máy chủ.

## 3. Luồng định tuyến qua các lớp mạng

Một gói tin đi từ workload ra ngoài có thể chịu ảnh hưởng của nhiều lớp:

~~~mermaid
flowchart TB
    APP["Ứng dụng / tiến trình"]
    OS["Network stack và route table của hệ điều hành"]
    NIC["NIC và địa chỉ IP nguồn"]
    VNET["Subnet, route table và chính sách mạng của cloud"]
    GW["Gateway / NAT / Firewall / Peering"]
    DEST["Mạng đích hoặc dịch vụ"]

    APP --> OS
    OS --> NIC
    NIC --> VNET
    VNET --> GW
    GW --> DEST
~~~

Đối với lưu lượng đi vào, chiều xử lý thường đi từ mạng đích qua route table, security policy và NIC, sau đó tới firewall và socket của ứng dụng.

Cần phân biệt hai loại định tuyến:

1. **Định tuyến trong guest OS:** kernel chọn NIC, next hop và địa chỉ nguồn để gửi packet.
2. **Định tuyến trong cloud network:** route table của subnet/VPC/VNet, gateway, peering, NAT hoặc firewall quyết định packet được chuyển tiếp trong hạ tầng ảo.

Route đúng trong Linux không bù được route thiếu ở cloud. Tương tự, cloud route table đúng không sửa được việc kernel gửi response ra sai NIC.

### 3.1. Thứ tự chọn route trong Linux

Linux sử dụng cơ sở dữ liệu định tuyến (FIB) để xác định đường đi. Với cấu hình thông thường, kernel xem xét:

- Các policy routing rule theo thứ tự ưu tiên.
- Bảng route được rule chỉ định, thường có các bảng **local**, **main** và **default**.
- Prefix phù hợp nhất (longest prefix match).
- Metric và các thuộc tính route khi có nhiều lựa chọn cùng mức phù hợp.
- Địa chỉ nguồn và giao diện đầu ra theo kết quả route lookup.

**ip rule** xác định thứ tự tra cứu bảng. **ip route** hiển thị hoặc thay đổi các route trong bảng được chọn. Vì vậy, kiểm tra riêng **ip route** mà bỏ qua **ip rule** có thể không giải thích được đường đi thực tế.

Các lệnh xem trạng thái:

~~~bash
ip -br link
ip -br addr
ip rule show
ip route show table main
ip route show table local
~~~

**ip -br link** hiển thị trạng thái giao diện ngắn gọn; **ip -br addr** hiển thị IP; **ip rule show** liệt kê policy rule; **ip route** xem route table.

### 3.2. Longest prefix match và metric

Khi nhiều route cùng phù hợp, Linux ưu tiên route có prefix cụ thể hơn. Ví dụ route tới **10.20.1.0/24** thường được chọn thay vì default route **0.0.0.0/0** khi đích nằm trong subnet đó.

Metric được dùng để so sánh các route có mức phù hợp tương đương trong cùng ngữ cảnh tra cứu. Metric thấp thường được ưu tiên hơn. Tuy nhiên, metric không thay thế policy routing theo địa chỉ nguồn và không tự giải quyết mọi tình huống multi-homing.

### 3.3. Default route

Default route là đường đi được dùng khi không có route cụ thể hơn. Trên máy một NIC, thường có một default gateway. Trên máy nhiều NIC, nhiều default route có thể gây khó đoán đường đi, đặc biệt khi request đi vào một NIC nhưng response lại đi ra NIC khác.

Nếu hai NIC nối tới hai gateway, chỉ đặt hai default route với metric khác nhau có thể khiến mọi traffic chủ động khởi tạo ưu tiên một NIC, trong khi response của kết nối đến NIC còn lại cần đi ra chính NIC đó. Policy routing thường là cách rõ ràng hơn khi cần chọn đường theo địa chỉ nguồn hoặc chính sách.

## 4. Địa chỉ nguồn và định tuyến bất đối xứng

### 4.1. Địa chỉ nguồn được chọn như thế nào?

Khi ứng dụng mở kết nối mà không bind địa chỉ nguồn, kernel thường chọn source IP dựa trên route và giao diện đầu ra. Nếu máy có nhiều NIC, source IP được chọn có thể khác với IP mà người vận hành dự kiến.

Ứng dụng có thể bind vào một địa chỉ IP cụ thể. Tuy nhiên, bind source IP chỉ kiểm soát địa chỉ nguồn ở socket; route lookup vẫn phải có đường đi hợp lệ cho địa chỉ đó.

Kiểm tra route cho một đích:

~~~bash
ip route get 203.0.113.80
~~~

Kiểm tra route với source IP cụ thể:

~~~bash
ip route get 203.0.113.80 from 10.20.1.10
~~~

**203.0.113.80** thuộc dải địa chỉ dành cho tài liệu ví dụ, không phải địa chỉ dịch vụ thực. Thay bằng địa chỉ đích của môi trường khi kiểm thử.

### 4.2. Định tuyến bất đối xứng là gì?

**Asymmetric routing** xảy ra khi packet đi và về sử dụng đường khác nhau. Ví dụ:

1. Client gửi request tới **10.20.1.10** qua **ens6**.
2. Máy chủ nhận packet trên **ens6**.
3. Ứng dụng tạo response.
4. Kernel chọn default route qua **ens5**.
5. Response đi ra **ens5**, trong khi client hoặc firewall kỳ vọng nó quay lại qua **ens6**.

Một số mạng cho phép định tuyến bất đối xứng; một số firewall stateful, NAT hoặc chính sách kiểm tra nguồn có thể loại bỏ response. Vì vậy, phải kiểm tra cả đường đi và đường về, không chỉ xác nhận packet đã tới máy.

### 4.3. Source-based policy routing

Linux có thể dùng **ip rule** để chọn bảng định tuyến dựa trên source IP, interface, firewall mark hoặc các thuộc tính khác. Cách phổ biến trong multi-NIC là tạo một bảng riêng cho mỗi NIC và thêm rule dựa trên địa chỉ nguồn.

Ví dụ, một VM có hai NIC:

| NIC | IP | Gateway | Vai trò |
|---|---|---|---|
| **ens5** | **10.10.1.10/24** | **10.10.1.1** | Frontend |
| **ens6** | **10.20.1.10/24** | **10.20.1.1** | Backend |

Mục tiêu là traffic có source IP **10.10.1.10** sử dụng bảng 100 và đi qua **ens5**; traffic có source IP **10.20.1.10** sử dụng bảng 200 và đi qua **ens6**.

~~~bash
# Route của mạng frontend trong bảng 100
ip route add 10.10.1.0/24 dev ens5 src 10.10.1.10 table 100
ip route add default via 10.10.1.1 dev ens5 table 100

# Route của mạng backend trong bảng 200
ip route add 10.20.1.0/24 dev ens6 src 10.20.1.10 table 200
ip route add default via 10.20.1.1 dev ens6 table 200

# Chọn bảng theo địa chỉ nguồn
ip rule add priority 100 from 10.10.1.10/32 table 100
ip rule add priority 110 from 10.20.1.10/32 table 200
~~~

Đây là ví dụ minh họa. Gateway phải thực sự tồn tại và có thể truy cập trong subnet tương ứng; route table cloud cũng phải cho phép đường đi. Nếu các route kết nối trực tiếp đã được cài vào bảng khác, cần thiết kế rule và route sao cho không tạo vòng lặp hoặc bỏ qua route quan trọng.

Kiểm tra cấu hình:

~~~bash
ip rule show
ip route show table 100
ip route show table 200
ip route get 203.0.113.80 from 10.10.1.10
ip route get 203.0.113.80 from 10.20.1.10
~~~

Kết quả route lookup cần chỉ ra đúng interface và gateway dự kiến. Sau đó phải kiểm thử kết nối thực tế, bởi route lookup chỉ cho biết quyết định của kernel, không chứng minh gateway, firewall hoặc mạng đích đang hoạt động.

### 4.4. Bảng định tuyến và tên bảng

Linux có các bảng định tuyến được định nghĩa sẵn như:

- **local** (ID 255): route tới địa chỉ cục bộ và broadcast.
- **main** (ID 254): bảng định tuyến thông thường.
- **default** (ID 253): bảng mặc định ít dùng trong cấu hình thông thường.
- Các bảng tùy chỉnh: có thể dùng ID số hoặc tên được khai báo trong **/etc/iproute2/rt_tables**.

Có thể khai báo tên để dễ quản lý:

~~~text
100 frontend
200 backend
~~~

Sau đó dùng tên bảng trong lệnh **ip route** và **ip rule** nếu hệ thống đã có cấu hình này. Khi tự động hóa, nên quản lý ID và tên nhất quán trên mọi máy.

## 5. Cấu hình nhiều địa chỉ IP trên một NIC

### 5.1. Thêm địa chỉ phụ

Trên Linux, **ip addr** có thể gắn thêm địa chỉ vào một giao diện:

~~~bash
ip addr add 10.10.1.11/24 dev ens5
ip -br addr show dev ens5
~~~

Ví dụ dùng một địa chỉ trong dải private minh họa. Trước khi chạy, cần bảo đảm IP đã được cấp hoặc cho phép trong cloud control plane, chưa bị máy khác sử dụng và prefix phù hợp với cấu hình subnet.

Xóa địa chỉ phụ:

~~~bash
ip addr del 10.10.1.11/24 dev ens5
~~~

Lệnh **ip** thay đổi trạng thái runtime. Cấu hình có thể mất sau reboot hoặc khi network manager/cloud-init ghi lại cấu hình. Muốn duy trì, cần khai báo bằng công cụ quản lý mạng của hệ điều hành.

### 5.2. Bind ứng dụng vào địa chỉ cụ thể

Một ứng dụng có thể lắng nghe trên:

- **0.0.0.0**: mọi địa chỉ IPv4 cục bộ.
- **127.0.0.1**: loopback IPv4.
- Một địa chỉ cụ thể như **10.10.1.11**: chỉ nhận kết nối qua địa chỉ đó.
- **::**: mọi địa chỉ IPv6, tùy cấu hình socket và hệ điều hành.

Bind vào địa chỉ cụ thể giúp giới hạn interface logic mà dịch vụ tiếp nhận. Tuy nhiên, firewall vẫn cần cho phép đúng nguồn, đích và port. Bind **0.0.0.0** không có nghĩa dịch vụ tự động truy cập được từ Internet; điều đó còn phụ thuộc public IP, route, NAT và security policy.

### 5.3. Source address selection với nhiều IP

Khi một NIC có nhiều IP, kernel cần chọn source IP cho kết nối đi ra. Ứng dụng có thể bind source IP; nếu không, kernel chọn theo route và quy tắc địa chỉ nguồn của hệ điều hành.

Điều này có ý nghĩa với:

- Dịch vụ cần response từ đúng IP mà client đã kết nối.
- Máy chủ gửi email hoặc kết nối đối tác có allowlist IP.
- Ứng dụng có nhiều endpoint hoặc tenant.
- Hệ thống có nhiều NAT/public IP ánh xạ tới các private IP khác nhau.

Cần kiểm thử cả kết nối inbound và outbound sau khi thêm IP. Một IP được gắn trên NIC không tự động có NAT hoặc public reachability.

### 5.4. ARP và nhiều IP cùng subnet

Với IPv4, ARP ánh xạ địa chỉ IP trong mạng cục bộ sang địa chỉ MAC. Khi một host có nhiều IP trên nhiều NIC cùng subnet hoặc nhiều NIC cùng kết nối một broadcast domain, phản hồi ARP có thể gây hành vi khó dự đoán (ví dụ ARP flux) nếu kernel và mạng không được cấu hình phù hợp.

Thiết kế cloud thường tách NIC theo subnet riêng. Nếu cần nhiều NIC trong cùng subnet hoặc nhiều địa chỉ cùng subnet trên nhiều interface, cần hiểu cách nhà cung cấp triển khai mạng ảo và kiểm tra ARP behavior, source address selection cùng các tham số kernel liên quan. Không nên thêm NIC trùng subnet chỉ để tăng băng thông khi chưa có thiết kế rõ.

## 6. Cấu hình nhiều NIC trên Linux

### 6.1. Khám phá giao diện

Trước khi sửa cấu hình, xác định tên NIC, MAC, IP, MTU và route hiện tại:

~~~bash
ip -br link
ip -br addr
ip -d link show
ip route
ip rule
~~~

Có thể dùng **ethtool** để xem một số thuộc tính của NIC nếu driver hỗ trợ:

~~~bash
ethtool ens5
ethtool -S ens5
~~~

Không phải mọi NIC ảo đều cung cấp đầy đủ thông tin tốc độ hoặc counter qua **ethtool**. Dùng metric của cloud provider khi cần xác minh băng thông và giới hạn dịch vụ.

### 6.2. Cấu hình runtime bằng iproute2

Có thể bật giao diện và gán IP:

~~~bash
ip link set ens6 up
ip addr add 10.20.1.10/24 dev ens6
~~~

Nếu cần route tới một mạng cụ thể:

~~~bash
ip route add 10.30.0.0/16 via 10.20.1.1 dev ens6
~~~

Nếu route đã tồn tại, lệnh **add** có thể báo **File exists**; hãy kiểm tra trạng thái trước khi thay đổi. Không nên xóa route hoặc flush toàn bộ bảng định tuyến trên máy production khi chưa hiểu tác động, vì có thể làm mất phiên quản trị đang dùng.

### 6.3. Cấu hình bền vững

Lệnh **ip** thường chỉ thay đổi trạng thái runtime. Để cấu hình tồn tại qua reboot, dùng công cụ quản lý mạng phù hợp với hệ điều hành, ví dụ:

- Netplan trên một số bản Ubuntu.
- NetworkManager trên nhiều bản Linux desktop/server.
- systemd-networkd trên hệ thống dùng systemd-networkd.
- Cấu hình mạng do cloud-init hoặc agent của nhà cung cấp quản lý.

Không nên đồng thời để nhiều công cụ quản lý cùng ghi một NIC. Cloud-init có thể tạo lại cấu hình từ metadata khi máy khởi động; thay đổi trực tiếp file do cloud-init sinh ra có thể bị ghi đè. Cần xác định nguồn cấu hình chuẩn và lưu thay đổi trong IaC hoặc image bootstrap.

Một quy trình an toàn gồm:

1. Lưu lại **ip addr**, **ip route** và **ip rule** hiện tại.
2. Xác định công cụ quản lý NIC.
3. Thêm địa chỉ, route và policy rule trong cấu hình bền vững.
4. Kiểm tra cú pháp trước khi áp dụng.
5. Áp dụng qua console hoặc phiên quản trị có phương án rollback.
6. Kiểm tra lại sau reboot hoặc sau khi cloud-init chạy.

### 6.4. Thứ tự khởi tạo và DHCP

Một NIC có thể nhận IP, route và DNS qua DHCP. Khi nhiều NIC cùng bật DHCP, hệ điều hành có thể cài nhiều default route hoặc thay đổi thứ tự ưu tiên theo metric. Điều này đôi khi làm đường ra thay đổi sau reboot hoặc renew lease.

Có thể cần cấu hình DHCP chỉ lấy địa chỉ trên NIC phụ nhưng không cài default route, hoặc đặt route metric và policy routing phù hợp. Cú pháp tùy network manager và bản phân phối; không sao chép cấu hình của hệ điều hành này sang hệ điều hành khác nếu chưa kiểm tra tài liệu.

## 7. Reverse path filtering và firewall

### 7.1. Reverse path filtering (rp_filter)

Linux có cơ chế **reverse path filtering** để kiểm tra tính hợp lý của địa chỉ nguồn dựa trên route ngược. Cơ chế này có thể giúp giảm một số kiểu giả mạo địa chỉ nguồn, nhưng chế độ strict có thể loại bỏ packet hợp lệ trong kiến trúc định tuyến bất đối xứng.

Ba giá trị thường gặp của **rp_filter**:

| Giá trị | Chế độ | Ý nghĩa |
|---|---|---|
| **0** | Disabled | Không kiểm tra reverse path bằng cơ chế này |
| **1** | Strict | Đường ngược tốt nhất phải đi qua interface nhận packet |
| **2** | Loose | Chỉ cần có route tới source address qua một interface nào đó |

Kiểm tra giá trị:

~~~bash
sysctl net.ipv4.conf.all.rp_filter
sysctl net.ipv4.conf.default.rp_filter
sysctl net.ipv4.conf.ens5.rp_filter
sysctl net.ipv4.conf.ens6.rp_filter
~~~

Nếu multi-NIC sử dụng policy routing hoặc đường về bất đối xứng, strict mode có thể làm rơi packet. Loose mode có thể phù hợp hơn trong một số thiết kế, nhưng làm giảm mức kiểm tra nguồn. Không nên tắt **rp_filter** trên toàn máy theo thói quen; hãy xác định đường đi thực tế, yêu cầu bảo mật và giá trị có hiệu lực từ cấu hình **all** cùng interface tương ứng. **default** được dùng làm giá trị khởi tạo cho interface mới.

### 7.2. Firewall trong guest OS

Firewall như **nftables**, **iptables**, **firewalld** hoặc **ufw** có thể áp dụng chính sách theo interface, source IP, destination IP, protocol và port.

Ví dụ chính sách:

- Cho phép HTTPS tới frontend NIC từ load balancer.
- Cho phép kết nối database chỉ qua backend NIC.
- Chỉ cho phép SSH/RDP qua mạng quản trị.
- Chặn forwarding giữa các NIC nếu máy không làm router.
- Ghi log có giới hạn cho các packet bị drop để hỗ trợ điều tra.

Không nên coi NIC riêng là ranh giới bảo mật duy nhất. Cần kết hợp cloud security group/firewall, subnet ACL, firewall trong guest OS và xác thực ở tầng ứng dụng.

### 7.3. IP forwarding

Nếu máy chủ chỉ chạy ứng dụng, thường không cần forward packet giữa các NIC. Nếu máy đóng vai trò router, NAT gateway, firewall hoặc appliance mạng, cần bật forwarding và cấu hình route, firewall, NAT cùng các chính sách cloud tương ứng.

Trên Linux, có thể kiểm tra:

~~~bash
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding
~~~

Bật IP forwarding không tự tạo ra một router an toàn. Cần xác định rõ interface tin cậy, route được phép, chính sách forward, source/destination validation và khả năng kiểm soát lưu lượng hai chiều.

Một số nền tảng cloud có cơ chế kiểm tra source/destination trên NIC hoặc VM. Nếu dùng VM làm router, phải bật hoặc điều chỉnh tính năng tương ứng theo hướng dẫn nhà cung cấp. Nếu không, packet được forward bởi Linux vẫn có thể bị hạ tầng cloud loại bỏ.

## 8. Multi-NIC trong container và Kubernetes

### 8.1. Network namespace

Container Linux thường chạy trong network namespace riêng. Vì vậy, bảng định tuyến và danh sách interface bên trong container có thể khác với host.

Kiểm tra từ trong container:

~~~bash
ip -br addr
ip route
ip rule
~~~

Một host có hai NIC không có nghĩa container tự động nhìn thấy cả hai. CNI quyết định interface và route được cấp vào network namespace của pod hoặc container.

### 8.2. Nhiều mạng cho một pod

Trong Kubernetes, CNI mặc định thường cấp một network interface chính cho pod. Nếu workload cần nhiều mạng, có thể dùng giải pháp như Multus CNI kết hợp các CNI phụ để gắn thêm interface vào pod.

Ví dụ khái niệm:

- Interface chính dùng cho giao tiếp cluster và Service.
- Interface phụ kết nối mạng dữ liệu hoặc thiết bị chuyên dụng.
- Pod có route riêng để gửi một số lưu lượng qua interface phụ.

Cần xác minh plugin, NetworkAttachmentDefinition, địa chỉ IPAM, route và quyền truy cập theo phiên bản CNI đang dùng. Multi-NIC trên node không tự động tạo multi-NIC cho từng pod.

### 8.3. Routing trong pod

Route table của pod thuộc network namespace của pod. Nếu pod có nhiều interface, cần kiểm tra route ngay bên trong pod và bảo đảm ứng dụng chọn đúng interface/source IP.

Không nên thay đổi route trên host để xử lý một vấn đề chỉ xảy ra trong pod mà chưa xác định namespace. Tương tự, policy route trong pod có thể cần quyền hoặc cơ chế CNI hỗ trợ; không nên cấp **NET_ADMIN** cho container một cách tùy tiện.

## 9. Thiết kế và kiểm thử một máy chủ hai NIC

### 9.1. Mục tiêu thiết kế

Giả sử một VM Linux cần hai NIC:

- NIC frontend nhận HTTPS từ load balancer trong subnet frontend.
- NIC backend kết nối database trong subnet backend.
- Response cho kết nối frontend phải quay về qua frontend.
- Kết nối tới database phải đi qua backend.
- Không cho phép forwarding tùy ý giữa hai subnet.

~~~mermaid
flowchart TB
    CLIENT["Client / Load balancer"]
    DB["Database"]
    subgraph VM["Linux VM"]
      APP["Ứng dụng"]
      F["ens5<br/>10.10.1.10"]
      B["ens6<br/>10.20.1.10"]
      APP --> F
      APP --> B
    end
    CLIENT -->|"HTTPS"| F
    B -->|"Database connection"| DB
~~~

### 9.2. Các bước cấu hình

**Bước 1: Cấu hình cloud control plane**

- Tạo hoặc chọn hai subnet đúng mục đích.
- Gắn hai NIC vào VM theo giới hạn của loại instance.
- Gán IP chính và IP phụ trong control plane nếu cần.
- Thiết lập route table cho từng subnet.
- Cấu hình security group/firewall để chỉ cho phép luồng cần thiết.
- Xác minh cả hai NIC cùng nằm trong phạm vi zone/region được nền tảng hỗ trợ.

**Bước 2: Xác minh guest OS**

~~~bash
ip -br link
ip -br addr
ip route
ip rule
~~~

Đối chiếu tên NIC, MAC và IP với metadata hoặc cấu hình từ cloud. Không tự đoán thứ tự interface.

**Bước 3: Cấu hình route và policy rule**

Nếu cả hai NIC có gateway riêng và response cần đi đúng NIC theo source IP, tạo route table riêng và policy rule như ví dụ ở mục 4.3. Nếu backend chỉ cần kết nối tới một subnet nội bộ, có thể chỉ cần route cụ thể tới subnet backend mà không cần default route thứ hai.

**Bước 4: Cấu hình firewall**

Cho phép HTTPS qua frontend NIC và database port qua backend NIC. Chặn forwarding nếu VM không đóng vai trò router. Kiểm tra cả firewall cloud và firewall trong guest.

**Bước 5: Kiểm tra ứng dụng**

Xác nhận ứng dụng bind đúng địa chỉ, database client dùng backend route và listener không mở trên interface ngoài dự kiến.

### 9.3. Kiểm thử đường đi

Các lệnh hữu ích:

~~~bash
# Kiểm tra địa chỉ và route
ip -br addr
ip rule show
ip route show table main

# Kiểm tra route theo source IP
ip route get 203.0.113.80 from 10.10.1.10
ip route get 203.0.113.80 from 10.20.1.10

# Kiểm tra socket đang lắng nghe
ss -lntup

# Quan sát packet trên từng NIC
tcpdump -ni ens5
tcpdump -ni ens6
~~~

Kết quả route lookup cần chỉ ra đúng interface và gateway dự kiến. Sau đó phải kiểm thử kết nối thực tế, bởi route lookup chỉ cho biết quyết định của kernel, không chứng minh gateway, firewall hoặc mạng đích đang hoạt động.

**tcpdump** cần quyền phù hợp và có thể thu thập dữ liệu nhạy cảm. Chỉ capture interface, host và port cần thiết; giới hạn thời gian và bảo vệ file capture theo chính sách vận hành.

## 10. Những sai lầm thường gặp

**Cho rằng thêm NIC tự động tạo thêm băng thông.** Băng thông phụ thuộc loại VM, giới hạn NIC, vNIC, CPU và hạ tầng cloud. Nhiều NIC có thể cùng chia sẻ giới hạn tổng của instance.

**Đặt nhiều default route mà không có policy.** Kernel có thể chọn đường ra không đúng với kết nối vào, gây asymmetric routing. Cần xác định source IP và route lookup.

**Chỉ cấu hình route trong guest OS.** Cloud route table, security group, NAT và source/destination validation vẫn có thể chặn packet.

**Gán IP trong Linux mà không đăng ký với cloud.** Nền tảng có thể không chấp nhận IP nguồn chưa được cấp. Luôn đồng bộ control plane và guest OS.

**Dùng metric để thay thế mọi policy rule.** Metric chọn ưu tiên giữa các route tương đương; nó không tự phân biệt luồng theo source IP hoặc tenant.

**Bỏ qua rp_filter.** Strict reverse path filtering có thể loại packet trong một số kiến trúc multi-homing. Cần kiểm tra chế độ thực tế và điều chỉnh có đánh giá bảo mật.

**Dùng cùng subnet trên nhiều NIC mà không hiểu ARP.** Có thể gây ARP flux hoặc route khó dự đoán. Chỉ triển khai khi nền tảng và hệ điều hành hỗ trợ rõ ràng.

**Nghĩ NIC quản trị là an toàn tuyệt đối.** Nếu firewall hoặc route cho phép truy cập từ mạng không tin cậy, NIC riêng không tạo ra bảo vệ đầy đủ.

**Sửa route qua phiên SSH đang phụ thuộc vào route đó.** Một thay đổi sai có thể làm mất kết nối quản trị. Nên có console ngoài băng, rollback hoặc cửa sổ thay đổi có kiểm soát.

**Chỉ kiểm tra chiều request.** Firewall stateful, NAT hoặc source validation có thể làm response bị drop. Luôn kiểm tra hai chiều và route thực tế.

## 11. Checklist trước khi triển khai

- [ ] Xác định vai trò của từng NIC và từng địa chỉ IP.
- [ ] Kiểm tra giới hạn số NIC, subnet, zone và loại VM.
- [ ] Đăng ký IP chính/phụ trong cloud control plane trước khi cấu hình guest OS.
- [ ] Xác minh MAC, tên interface, MTU và địa chỉ thực tế.
- [ ] Kiểm tra route table cloud và route table của hệ điều hành.
- [ ] Xác định default route, metric và policy routing cần thiết.
- [ ] Kiểm tra source IP được chọn cho từng luồng.
- [ ] Xác minh đường về và nguy cơ asymmetric routing.
- [ ] Kiểm tra **rp_filter** và tác động tới thiết kế multi-homing.
- [ ] Cấu hình firewall theo NIC, source, destination và port.
- [ ] Chỉ bật IP forwarding khi máy thực sự làm router.
- [ ] Đồng bộ cấu hình bền vững với NetworkManager, Netplan, systemd-networkd hoặc cloud-init.
- [ ] Kiểm tra route và interface bên trong network namespace của container/pod.
- [ ] Kiểm thử packet trên từng NIC và cả hai chiều.
- [ ] Chuẩn bị console hoặc phương án rollback trước khi thay đổi route production.

## 12. Ghi nhớ

- **NIC** là giao diện mạng; **IP** là địa chỉ logic; **subnet** xác định phạm vi địa chỉ và chính sách mạng.
- Một NIC có thể có nhiều IP; một VM có thể có nhiều NIC, nhưng số lượng IP/NIC không tự động làm tăng băng thông hoặc tính sẵn sàng.
- Định tuyến xảy ra ở cả cloud network và guest OS; hai lớp phải thống nhất.
- Linux dùng **ip route** để quản lý route và **ip rule** để chọn bảng theo chính sách.
- Multi-NIC có nhiều gateway cần chú ý source IP, default route và asymmetric routing.
- Source-based policy routing giúp response đi đúng NIC theo địa chỉ nguồn.
- **rp_filter** strict có thể ảnh hưởng thiết kế đường đi bất đối xứng; mọi điều chỉnh phải cân nhắc bảo mật.
- Cấu hình runtime bằng **ip** có thể mất sau reboot; cần lưu trong công cụ quản lý mạng chuẩn.
- Container và pod có network namespace riêng; phải kiểm tra interface và route trong đúng namespace.
- Luôn kiểm tra cả đường đi, đường về, firewall và cloud route table trước khi đưa cấu hình vào production.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| NIC | Network Interface Card/Controller, giao diện mạng của máy chủ hoặc VM. |
| Multi-NIC | Kiến trúc một máy sử dụng nhiều giao diện mạng. |
| Secondary IP | Địa chỉ IP bổ sung trên cùng NIC hoặc tài nguyên mạng theo cách nhà cung cấp hỗ trợ. |
| Subnet | Phạm vi địa chỉ IP và chính sách mạng. |
| Gateway | Thiết bị hoặc endpoint chuyển tiếp packet sang mạng khác. |
| Route table | Bảng quy tắc chọn đường đi cho packet. |
| Default route | Route được dùng khi không có route cụ thể hơn. |
| Metric | Giá trị ưu tiên tương đối giữa các route tương đương. |
| Policy routing | Định tuyến dựa trên source, mark hoặc thuộc tính khác ngoài địa chỉ đích. |
| Asymmetric routing | Đường đi và đường về của packet sử dụng các tuyến khác nhau. |
| Source address selection | Cơ chế chọn địa chỉ IP nguồn cho kết nối đi ra. |
| ARP | Address Resolution Protocol, ánh xạ IPv4 trong mạng cục bộ sang địa chỉ MAC. |
| rp_filter | Cơ chế reverse path filtering của Linux để kiểm tra đường ngược tới địa chỉ nguồn. |
| Network namespace | Không gian mạng riêng của tiến trình/container, có interface và route table riêng. |
| CNI | Container Network Interface, giao diện chuẩn để tích hợp mạng cho container và pod. |
| Multus CNI | Meta-plugin Kubernetes hỗ trợ gắn nhiều network interface vào pod thông qua các CNI khác. |
| IP forwarding | Chuyển tiếp packet giữa các interface ở lớp IP. |
| MTU | Maximum Transmission Unit, kích thước payload tối đa của một frame/packet trên liên kết theo cấu hình. |
