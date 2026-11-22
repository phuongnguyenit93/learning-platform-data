# Thiết kế network appliance và định tuyến lưu lượng kiểm tra

Một ứng dụng trên Microsoft Azure có thể gồm nhiều Virtual Network (VNet): VNet của web frontend, VNet của dịch vụ nghiệp vụ, VNet chứa dữ liệu và VNet dùng chung của đội nền tảng. Khi các mạng cần trao đổi, **VNet peering** tạo khả năng kết nối IP riêng, nhưng không tự bảo đảm mọi luồng đều được **kiểm tra bởi firewall hoặc thiết bị bảo mật** trước khi đến đích.

Trong chương **Kết nối và bảo vệ mạng** của module **CLOUD_PROVIDERS_AZURE**, bài học này tập trung vào việc thiết kế **Network Virtual Appliance (NVA)** và **định tuyến lưu lượng kiểm tra** (traffic inspection). Mục tiêu là hiểu đường đi của gói tin, dùng route table/UDR để đưa những luồng cần kiểm tra qua thiết bị, duy trì đường trả về đối xứng, không để gián đoạn ứng dụng và biết cách giám sát, xử lý sự cố, đánh giá chi phí.

Ví dụ xuyên suốt: ứng dụng Orders triển khai ở Azure, có hai spoke VNet và một hub VNet. Đội bảo mật muốn lưu lượng giữa hai spoke đi qua một firewall/NVA trong hub để thực thi chính sách và ghi log, thay vì để hai spoke giao tiếp trực tiếp ngoài điểm kiểm soát.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Giải thích network appliance, NVA, Azure Firewall và các lớp kiểm tra lưu lượng.
- Phân biệt luồng **north–south**, **east–west** và mục tiêu của **service insertion**.
- Xác định cách VNet peering, **User Defined Route (UDR)**, Network Security Group (NSG), IP forwarding và firewall policy phối hợp.
- Thiết kế tuyến **đi và về** qua thiết bị kiểm tra, hiểu ảnh hưởng của stateful inspection và asymmetric routing.
- Lập sơ đồ hub–spoke với CIDR không chồng lấn, bảng luồng nguồn–đích–port và các route có chủ đích.
- Tạo route table, route, liên kết subnet và kiểm tra effective routes bằng Azure CLI.
- Đánh giá high availability (HA), khả năng mở rộng, logging, DNS và chi phí của NVA.
- Chẩn đoán trường hợp peering Connected nhưng lưu lượng bị chặn, bỏ qua firewall hoặc đi một chiều.

## 2. Network appliance là gì?

**Network appliance** là thành phần xử lý traffic ở lớp mạng, vận chuyển hoặc ứng dụng. Trên Azure, appliance có thể là VM chạy phần mềm router/firewall của bên thứ ba, hoặc một dịch vụ mạng được quản lý như Azure Firewall trong một kiến trúc có chức năng tương đương ở những khía cạnh nhất định.

Một số nhiệm vụ phổ biến:

| Nhiệm vụ | Ví dụ | Điều cần lưu ý |
|---|---|---|
| Lọc lưu lượng | Chỉ cho phép spoke ứng dụng gọi TCP/443 đến spoke dữ liệu | Rule phải gắn với nguồn, đích, cổng và hướng cụ thể |
| Kiểm soát outbound | Chỉ cho phép workload truy cập những endpoint cần thiết | Route mặc định phải đưa traffic đến firewall và có đường ra mạng hợp lệ |
| Stateful firewall | Theo dõi trạng thái phiên TCP/UDP | Đường đi và về không nên qua hai firewall độc lập không chia sẻ state |
| IDS/IPS | Phát hiện hoặc chặn một số hành vi nguy hiểm | Cần chính sách cập nhật, dữ liệu ghi log, cân nhắc false positive |
| NAT/SNAT/DNAT | Chuyển đổi địa chỉ/port theo yêu cầu | NAT có thể làm mất địa chỉ nguồn gốc trong log hoặc ảnh hưởng kết nối |
| Định tuyến | Chuyển gói tin giữa các subnet/VNet | NVA phải thực sự bật forwarding và có route đến đích |
| Kiểm soát ứng dụng | Xử lý lưu lượng ở lớp ứng dụng theo sản phẩm | Không mặc nhiên đọc được payload đã mã hóa TLS |

**NVA** là cách gọi thường dùng cho appliance triển khai trên hạ tầng máy ảo Azure. Một NVA có thể chạy firewall, router, proxy hay giải pháp SD-WAN do khách hàng hoặc nhà cung cấp phần mềm quản lý. **Azure Firewall** là dịch vụ firewall do Azure quản lý; nó không yêu cầu người dùng tự quản lý VM hệ điều hành như một NVA truyền thống.

Một hệ thống chỉ có NVA trên sơ đồ nhưng không có route đưa traffic qua đó **chưa thực sự có kiểm tra lưu lượng**.

### 2.1. Chọn công cụ theo phạm vi bảo vệ

- **NSG:** lọc L3/L4 cho NIC hoặc subnet theo rule, hiệu quả để phân đoạn và giới hạn các luồng. NSG không thay thế một firewall tập trung có khả năng ghi nhận/kiểm soát nâng cao.
- **Azure Firewall:** dịch vụ firewall được quản lý, thường đặt tại hub để thực thi network/application rules và logging theo gói tính năng được chọn.
- **NVA bên thứ ba:** dùng khi cần tính năng, chính sách, tích hợp, chuỗi thiết bị hoặc vận hành phù hợp với giải pháp của tổ chức; khách hàng phải hiểu và quản lý HA, update, license và throughput.
- **Web Application Firewall (WAF):** tập trung bảo vệ HTTP/HTTPS ở lớp ứng dụng; không phải bộ định tuyến lưu lượng chung cho mọi giao thức.
- **Azure DDoS Protection:** tăng khả năng bảo vệ trước tấn công từ chối dịch vụ ở phạm vi hỗ trợ; không thay cho kiểm tra rule của từng kết nối.
- **Azure Virtual WAN/Secured virtual hub:** là lựa chọn kiến trúc cho hệ thống nhiều kết nối quy mô lớn; tính năng định tuyến và bảo mật khác mô hình NVA tự quản lý.

Chỉ chọn NVA khi có yêu cầu cụ thể mà dịch vụ managed hoặc các kiểm soát sẵn có không đáp ứng phù hợp. Việc thêm thiết bị vào đường truyền tạo thêm điểm phụ thuộc, độ trễ, chi phí và gánh nặng vận hành.

## 3. Những kiểu lưu lượng cần kiểm tra

Đầu tiên, hãy phân loại các luồng theo hướng và ranh giới tin cậy:

### 3.1. North–south

**North–south traffic** thường là lưu lượng ra/vào hệ thống từ bên ngoài một vùng mạng:

- Người dùng Internet truy cập ứng dụng web.
- Workload truy cập Internet để tải dependency hoặc gọi API ngoài.
- Mạng on-premises truy cập hệ thống Azure qua VPN Gateway/ExpressRoute.

Traffic vào từ Internet có thể cần Azure Front Door, Application Gateway/WAF, Load Balancer, firewall hoặc thiết bị khác tùy kiến trúc. Traffic ra Internet thường được kiểm soát bằng default route, egress firewall, chính sách DNS và cơ chế SNAT/egress phù hợp.

### 3.2. East–west

**East–west traffic** là luồng giữa các tài nguyên và vùng mạng nội bộ:

- API ở spoke A gọi dịch vụ dữ liệu ở spoke B.
- VM quản trị ở hub truy cập workload trong spoke.
- Microservice trong một VNet liên lạc với microservice khác qua peering.

Không phải mọi luồng east–west đều phải đi qua firewall tập trung. Quyết định inspection dựa vào dữ liệu, trust boundary, compliance, throughput, độ trễ và chi phí.

### 3.3. Bảng chính sách luồng trước khi tạo route

Ví dụ cho ứng dụng Orders:

| Nguồn | Đích | Port/giao thức | Yêu cầu | Chính sách |
|---|---|---|---|---|
| Spoke-app 10.10.1.0/24 | Spoke-data 10.20.1.10 | TCP/443 | Bắt buộc kiểm tra | Allow có logging qua NVA |
| Spoke-data 10.20.1.0/24 | Spoke-app 10.10.1.0/24 | Kết nối mới tùy ý | Không có nhu cầu | Deny theo firewall policy |
| Spoke-app | API bên ngoài được duyệt | TCP/443 | Kiểm soát egress | Định tuyến qua egress firewall khi cần |
| Máy vận hành | NVA management interface | HTTPS/SSH theo thiết kế | Chỉ đội vận hành | Giới hạn nguồn và phân quyền |
| Spoke-app | DNS resolver nội bộ | TCP/UDP 53 theo hệ thống | Phải hoạt động | Cho phép theo luồng DNS |

Bảng này chỉ mô tả **các luồng được phép khởi tạo**, không có nghĩa lưu lượng phản hồi của một phiên hợp lệ cũng bị chặn. Với stateful inspection, firewall cần thấy đủ phiên để đưa ra quyết định nhất quán.

## 4. Kiến trúc tham chiếu: hub–spoke có NVA

Thiết kế ba VNet dùng dải IP **không chồng lấn**:

| VNet | CIDR | Resource group | Vai trò |
|---|---|---|---|
| vnet-security-hub | 10.0.0.0/16 | rg-security-hub | Chứa NVA và dịch vụ mạng dùng chung |
| vnet-orders-app | 10.10.0.0/16 | rg-orders-app | Chứa API/app workload |
| vnet-orders-data | 10.20.0.0/16 | rg-orders-data | Chứa dịch vụ dữ liệu hoặc backend |
| snet-nva trong hub | 10.0.1.0/24 | thuộc hub VNet | NVA có private IP minh họa 10.0.1.4 |
| snet-app trong spoke A | 10.10.1.0/24 | thuộc spoke A | Tài nguyên ứng dụng |
| snet-data trong spoke B | 10.20.1.0/24 | thuộc spoke B | Dịch vụ đích |

Sơ đồ đường đi:

~~~mermaid
flowchart LR
    A["Spoke A – Orders App<br/>10.10.0.0/16"]
    H["Hub VNet<br/>10.0.0.0/16"]
    F["NVA / Firewall<br/>10.0.1.4"]
    B["Spoke B – Data<br/>10.20.0.0/16"]
    A <-->|"Peering A–Hub"| H
    H <-->|"Peering Hub–B"| B
    H --- F
    A -. "UDR đích 10.20.0.0/16" .-> F
    B -. "UDR đích 10.10.0.0/16" .-> F
~~~

**Hai đường nét đứt tượng trưng cho ý đồ next hop**, không phải một liên kết L2 trực tiếp từ spoke đến NVA. Route trên mỗi spoke chọn private IP của NVA làm next hop; lưu lượng thực tế đi qua peering với hub và được NVA chuyển tiếp tới spoke đích theo định tuyến đã thiết kế.

Không tạo peering trực tiếp A↔B nếu yêu cầu là buộc lưu lượng đi qua điểm kiểm tra ở hub, trừ khi đã phân tích rõ cách tránh đường vòng/bypass. Peering **không có tính bắc cầu**: A peering với hub và B peering với hub không tự tạo route A→B; NVA kết hợp UDR và cấu hình forwarding đóng vai trò xử lý transit.

### 4.1. Tuyến đi và tuyến về

Giả sử máy nguồn **10.10.1.10** ở spoke A gọi dịch vụ **10.20.1.10:443** tại spoke B:

1. Subnet của nguồn có UDR: **10.20.0.0/16 → Virtual appliance 10.0.1.4**.
2. Azure gửi gói từ spoke A sang hub theo peering liên quan tới next hop.
3. NVA nhận gói, áp dụng firewall policy, sau đó chuyển tiếp đến mạng **10.20.0.0/16** qua kết nối hub–spoke B.
4. Máy đích trả lời **10.10.1.10**.
5. Subnet của máy đích có UDR: **10.10.0.0/16 → Virtual appliance 10.0.1.4**.
6. NVA thấy lưu lượng phản hồi của phiên và chuyển về spoke A.

Nếu thiếu UDR chiều về, gói trả lời có thể bị drop vì không có route transit, hoặc đi đường khác trong một kiến trúc phức tạp. Với **stateful firewall**, đi/về qua hai node không chia sẻ state có thể làm phiên thất bại dù cả hai hướng đều có đường mạng.

### 4.2. Kịch bản chỉ một spoke và Internet

Trong trường hợp chỉ kiểm soát egress, subnet ứng dụng có thể dùng default route:

~~~text
0.0.0.0/0 → Virtual appliance → 10.0.1.4
~~~

Khi đó NVA hoặc Azure Firewall phải có **đường ra Internet hợp lệ**, thực thi NAT theo kiến trúc và cho phép dịch vụ cần thiết. Ép route mặc định sang một VM không có khả năng forwarding/egress sẽ khiến các kết nối outbound mất đường ra.

Default route ảnh hưởng phạm vi rộng; không nên dùng cho buổi thực hành ban đầu khi chỉ muốn kiểm tra traffic A→B.

## 5. Luật định tuyến và cách UDR tác động

Azure sử dụng **system routes**, có thể nhận route được quảng bá qua gateway/BGP trong trường hợp hỗ trợ, và cho phép cấu hình **User Defined Routes (UDR)** trong route table.

Một subnet có thể liên kết với một route table chứa nhiều route. Khi quyết định đường đi, Azure xét prefix đích và loại route theo nguyên tắc của nền tảng. Quy tắc cần nhớ:

- **Prefix khớp dài nhất** thường được ưu tiên. Route /24 cụ thể có thể thắng một route /16 hoặc 0.0.0.0/0.
- Khi prefix trùng nhau, UDR thường được ưu tiên hơn route từ gateway/BGP và system route, với các ngoại lệ do nền tảng quy định.
- UDR có next hop **Virtual appliance** sẽ gửi traffic đến IP do bạn chỉ định, nhưng **không tự làm thiết bị đó biết chuyển tiếp**.
- Một UDR ở subnet không tự áp dụng cho mọi subnet của VNet. Cần xác định chính xác subnet nào sẽ gắn route table.
- NSG và Azure Firewall policy được đánh giá độc lập với việc chọn route. Có route đến đích không có nghĩa policy sẽ cho phép.

Các next-hop type quen thuộc:

| Next hop | Ý nghĩa điển hình |
|---|---|
| Virtual network | Route nội bộ được Azure quản lý theo mô hình mạng |
| Virtual network peering | System route đến prefix của VNet peer |
| Virtual network gateway | Đường qua VPN/ExpressRoute gateway khi có cấu hình phù hợp |
| Virtual appliance | Đi qua private IP của NVA hoặc điểm tiếp nhận được thiết kế hỗ trợ |
| Internet | Đi ra tuyến Internet theo cơ chế nền tảng và cấu hình liên quan |
| None | Loại bỏ gói đến prefix theo route đó |

**Lưu ý:** next hop type hiển thị trong **effective routes** và giá trị được phép khai báo khi tạo UDR có thể khác cách gọi. Khi tạo custom route cho NVA, dùng **VirtualAppliance** và **next-hop-ip-address** theo cú pháp Azure CLI.

### 5.1. Ví dụ route table

Trong mô hình A–hub–B:

| Vị trí gắn route table | Address prefix | Next-hop type | Next-hop IP |
|---|---|---|---|
| snet-app, spoke A | 10.20.0.0/16 | Virtual appliance | 10.0.1.4 |
| snet-data, spoke B | 10.10.0.0/16 | Virtual appliance | 10.0.1.4 |

Từ đây, chỉ các prefix đã chọn được chủ động đưa qua NVA. Nếu cần kiểm tra nhiều luồng khác, hãy bổ sung route theo ma trận traffic, sau khi xem tác động và các route hiệu lực sẵn có.

### 5.2. UDR không tự thay thế quy hoạch mạng

Trước khi viết route, hãy:

1. Kiểm tra hai VNet không có address space chồng lấn.
2. Xác nhận peering hub↔spoke đều **Connected**.
3. Xác nhận forward traffic qua peering được cấu hình theo luồng dự kiến.
4. Xác nhận NVA ở địa chỉ private IP tĩnh đúng và đạt trạng thái hoạt động.
5. Kiểm tra sự hiện diện của các route rộng khác (ví dụ default route).
6. Xác nhận NSG và firewall policy cho luồng cần thiết.
7. Dự đoán đường phản hồi và NAT nếu có.

## 6. Peering và Forwarded Traffic

Với mô hình hub–spoke, cần peering hai chiều giữa hub và từng spoke, kèm các lựa chọn phù hợp cho traffic được chuyển tiếp. **Allow forwarded traffic** quyết định peering có chấp nhận traffic được chuyển tiếp bởi appliance từ phía peer hay không; nó không tạo route và không bật forwarding trên NVA.

Các việc cần xác nhận:

- **Hub ↔ Spoke A** có hai peering, trỏ đến đúng remote VNet.
- **Hub ↔ Spoke B** có hai peering, trỏ đến đúng remote VNet.
- **Allow virtual network access** cho phép các luồng trực tiếp cần thiết theo thiết kế.
- **Allow forwarded traffic** được bật ở các hướng peering cần chấp nhận forwarded traffic qua NVA.
- Bất kỳ trường hợp **gateway transit/use remote gateways** nào đều có lý do riêng, không bật mặc định chỉ vì có NVA.

Ví dụ kiểm tra peering bằng Azure CLI:

~~~bash
az network vnet peering list \
  --resource-group rg-security-hub \
  --vnet-name vnet-security-hub \
  --query "[].{name:name,state:peeringState,allowVnet:allowVirtualNetworkAccess,forwarded:allowForwardedTraffic,remote:remoteVirtualNetwork.id}" \
  --output table
~~~

Nếu chỉ có một đầu peering, trạng thái có thể chưa **Connected**. Nếu không thấy traffic đi được qua hub, hãy kiểm tra cả cấu hình của hai spoke, không chỉ peering trên hub.

**Không bật forwarded traffic cho mọi quan hệ không cần thiết**; nó cho phép một loại hành vi transit rộng hơn và phải đi kèm quy tắc lọc, routing được review.

## 7. Yêu cầu riêng với NVA chạy trên VM

Một NVA tự quản lý thường là VM có một hoặc nhiều network interface. Để thực sự chuyển tiếp lưu lượng, bạn phải đáp ứng **hai tầng** cấu hình:

1. **Azure NIC IP forwarding:** cho phép network interface nhận/chuyển tiếp traffic có source/destination không nhất thiết là IP gắn với NIC theo cách NVA sử dụng.
2. **Hệ điều hành hoặc phần mềm appliance:** bật routing/IP forwarding, firewall/packet processing, interface policy và các route cần thiết.

Nếu chỉ bật trên NIC Azure mà quên bật trong OS, traffic vẫn có thể bị drop. Nếu bật trong OS nhưng NIC Azure chưa cho phép forwarding, traffic cũng không đi theo ý định.

### 7.1. Ví dụ bật IP forwarding ở Azure NIC

Ví dụ dành cho **NVA được phép dùng làm router**, không áp dụng tự động cho VM ứng dụng:

~~~bash
az network nic update \
  --resource-group rg-security-hub \
  --name "<nva-nic-name>" \
  --ip-forwarding true
~~~

Kiểm tra trạng thái:

~~~bash
az network nic show \
  --resource-group rg-security-hub \
  --name "<nva-nic-name>" \
  --query "{name:name,ipForwarding:enableIPForwarding,privateIPs:ipConfigurations[].privateIPAddress}" \
  --output json
~~~

Trên Linux có thể dùng lệnh **read-only** để xem IPv4 forwarding:

~~~bash
sysctl net.ipv4.ip_forward
~~~

Nếu kết quả là **0**, host chưa bật IPv4 routing ở mức kernel. Cách cấu hình bền vững, firewall của hệ điều hành và yêu cầu nhiều interface phụ thuộc image/phần mềm NVA. Đừng tự bật forwarding trên một máy chưa được cấu hình làm router và chưa có chính sách kiểm soát phù hợp.

### 7.2. Private IP và địa chỉ next hop

Next-hop IP phải là địa chỉ **reachable** trong mạng, thuộc cấu hình NVA hoặc điểm next hop được dịch vụ hỗ trợ. Trong lab này minh họa **10.0.1.4**, nhưng không được mặc định IP đó đã được cấp cho VM. Hãy kiểm tra IP của NIC và thiết lập cấp IP tĩnh theo phương pháp được hỗ trợ trước khi trỏ UDR.

Với một giải pháp **HA qua Internal Load Balancer (ILB)**, kiến trúc có thể dùng frontend IP của load balancer làm điểm tiếp nhận traffic theo mô hình HA ports được Azure và nhà cung cấp NVA hỗ trợ. Không thay next-hop IP của UDR sang một load-balancer frontend bất kỳ nếu chưa xác minh kiến trúc hỗ trợ, probe, flow symmetry và cơ chế failover.

### 7.3. Phân biệt forward, NAT và proxy

- **Forward/routing:** NVA chuyển traffic giữa mạng, thường cố gắng giữ nguyên địa chỉ gốc.
- **SNAT:** thay đổi source IP/port; có thể giúp kiểm soát đường phản hồi nhưng làm mất thông tin nguồn ở phía đích nếu không có logging.
- **DNAT:** đổi destination IP/port, thường dùng cho inbound publishing.
- **Proxy:** ứng dụng kết nối đến proxy, proxy tạo kết nối khác đến đích; có các yêu cầu protocol và TLS khác packet forwarding thuần túy.

Đừng bật NAT chỉ để che một lỗi routing mà chưa hiểu ảnh hưởng đến audit, security policy và tính đúng đắn của ứng dụng.

## 8. Thực hành định tuyến traffic A → NVA → B bằng Azure CLI

**Giả định**: các VNet, subnet, peering và NVA đã được tạo đúng thiết kế và NVA đã hoạt động; subscription và resource group hợp lệ; hai đầu peering hỗ trợ forwarded traffic theo hướng cần dùng. Bài này chỉ minh họa tạo UDR và gắn vào subnet. Không tự tạo firewall policy hay bảo đảm NVA đã sẵn sàng chỉ bằng các lệnh này.

Chỉ chạy trong **sandbox/lab được phê duyệt**. Việc gắn route table có thể thay đổi tức thời đường mạng của nhiều máy trong một subnet, vì vậy không chạy trên production khi chưa có kế hoạch thay đổi và rollback.

### 8.1. Chuẩn bị biến và xác nhận mạng

Các lệnh sử dụng cú pháp **Bash** trong Azure Cloud Shell hoặc shell đã có Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

APP_RG="rg-orders-app"
DATA_RG="rg-orders-data"
APP_VNET="vnet-orders-app"
DATA_VNET="vnet-orders-data"
APP_SUBNET="snet-app"
DATA_SUBNET="snet-data"
NVA_IP="10.0.1.4"

# Xem địa chỉ của hai VNet
az network vnet show \
  --resource-group "$APP_RG" \
  --name "$APP_VNET" \
  --query "{name:name,prefixes:addressSpace.addressPrefixes}" \
  --output json

az network vnet show \
  --resource-group "$DATA_RG" \
  --name "$DATA_VNET" \
  --query "{name:name,prefixes:addressSpace.addressPrefixes}" \
  --output json
~~~

Xác nhận **10.10.0.0/16** và **10.20.0.0/16** là những mạng đích đúng, không overlap, NVA_IP là private IP của appliance. Ghi lại route table hiện có trên từng subnet để không ghi đè một cấu hình khác mà chủ sở hữu chưa phê duyệt.

~~~bash
az network vnet subnet show \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --query "{name:name,addressPrefix:addressPrefix,routeTable:routeTable.id}" \
  --output json

az network vnet subnet show \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --query "{name:name,addressPrefix:addressPrefix,routeTable:routeTable.id}" \
  --output json
~~~

### 8.2. Tạo route table cho spoke A

~~~bash
az network route-table create \
  --resource-group "$APP_RG" \
  --name "rt-orders-app-inspection" \
  --location southeastasia

az network route-table route create \
  --resource-group "$APP_RG" \
  --route-table-name "rt-orders-app-inspection" \
  --name "to-orders-data-via-nva" \
  --address-prefix "10.20.0.0/16" \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$NVA_IP"
~~~

Route này đưa traffic từ **subnet gắn route table** khi đi đến **10.20.0.0/16** qua appliance. Nó chưa áp dụng cho subnet cho đến khi association được tạo.

### 8.3. Tạo route table cho spoke B

~~~bash
az network route-table create \
  --resource-group "$DATA_RG" \
  --name "rt-orders-data-inspection" \
  --location southeastasia

az network route-table route create \
  --resource-group "$DATA_RG" \
  --route-table-name "rt-orders-data-inspection" \
  --name "to-orders-app-via-nva" \
  --address-prefix "10.10.0.0/16" \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$NVA_IP"
~~~

Route B→A đóng vai trò đường phản hồi hoặc đường khởi tạo từ B khi có policy cho phép. Một kết nối đã được phép khởi tạo từ A vẫn phải được NVA xử lý statefully và có đường về tương thích.

### 8.4. Gắn route table vào subnet

**Chỉ tiếp tục nếu các subnet chưa có route table khác hoặc đã duyệt việc cập nhật route table hiện hữu.** Azure cho phép một subnet liên kết với một route table tại một thời điểm; thay liên kết có thể làm mất route cần thiết từ bảng cũ.

~~~bash
az network vnet subnet update \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --route-table "rt-orders-app-inspection"

az network vnet subnet update \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --route-table "rt-orders-data-inspection"
~~~

Sau đó kiểm tra association:

~~~bash
az network vnet subnet show \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --query "routeTable.id" \
  --output tsv

az network vnet subnet show \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --query "routeTable.id" \
  --output tsv
~~~

### 8.5. Kiểm tra nội dung bảng định tuyến

~~~bash
az network route-table route list \
  --resource-group "$APP_RG" \
  --route-table-name "rt-orders-app-inspection" \
  --output table

az network route-table route list \
  --resource-group "$DATA_RG" \
  --route-table-name "rt-orders-data-inspection" \
  --output table
~~~

Mong đợi: route A có prefix **10.20.0.0/16**, route B có prefix **10.10.0.0/16**, cùng next-hop IP là địa chỉ NVA phù hợp. **Chưa thể kết luận traffic thật đã đi qua NVA** chỉ từ kết quả cấu hình route table.

## 9. Xác minh bằng effective routes và kiểm tra kết nối

### 9.1. Effective routes

Trên NIC của VM nguồn ở spoke A, chạy:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-app-resource-group>" \
  --name "<vm-app-nic-name>" \
  --output table
~~~

Làm tương tự với NIC của VM đích ở spoke B:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-data-resource-group>" \
  --name "<vm-data-nic-name>" \
  --output table
~~~

Tìm route đến prefix phía còn lại. Kiểm tra:

- Next hop là **Virtual appliance** đúng địa chỉ hay không.
- Có route cụ thể hơn làm traffic bypass NVA không.
- Có route **None**, gateway hoặc default route gây ảnh hưởng không.
- Route có trạng thái active và nguồn route phù hợp không.

Một số dịch vụ PaaS hoặc workload không có NIC để dùng trực tiếp lệnh này. Khi đó, cần sử dụng công cụ chẩn đoán phù hợp với nền tảng và cấu hình của dịch vụ.

### 9.2. Kiểm tra nguồn–đích–port

Giả sử VM A dùng 10.10.1.10 và dịch vụ ở B dùng 10.20.1.10:443. Từ VM A, thử đúng port:

~~~bash
nc -vz -w 5 10.20.1.10 443
~~~

Nếu đây là HTTPS thực, kiểm tra hostname/TLS đúng thay vì chỉ kiểm tra port TCP:

~~~bash
curl --connect-timeout 5 https://api.orders.internal/health
~~~

Tên DNS trên chỉ là ví dụ, cần có bản ghi và certificate hợp lệ trong lab. Ping không phải phép thử kết luận: ICMP có thể bị chặn dù TCP/443 được cho phép.

### 9.3. Xác nhận traffic thật đi qua appliance

Đây là bước **quan trọng nhất** để xác nhận inspection:

1. Phát sinh một kết nối có đánh dấu thời gian và IP/port rõ ràng từ spoke A.
2. Tìm session hoặc log tương ứng trên NVA/Azure Firewall.
3. Xác nhận **IP nguồn và đích, rule được áp dụng, chiều traffic, hành động allow/deny**.
4. Kiểm tra route chiều về và session state nếu là firewall stateful.
5. Thử một luồng bị chính sách từ chối để xác nhận rule thực sự có hiệu lực.
6. Kiểm tra logs trên workload và những thành phần trung gian khi kết nối thất bại.

Nếu kết nối A→B thành công nhưng NVA không có log, đừng kết luận “đã được bảo vệ”. Có thể traffic đã đi đường khác, logging chưa bật, rule không ghi log, SNAT thay địa chỉ hoặc có sai sót trong cách truy vấn log.

### 9.4. Network Watcher

Có thể dùng các khả năng phù hợp của Azure Network Watcher:

- **Connection troubleshoot** để kiểm tra khả năng kết nối đến IP/port và hỗ trợ tìm nguyên nhân.
- **IP flow verify** để đánh giá NSG rule ảnh hưởng tới một luồng khi nguồn/đích được hỗ trợ.
- **Effective security rules** để xem tập hợp NSG rule áp dụng lên NIC.
- **Effective routes** để xác định UDR và các nguồn định tuyến khác.
- **Traffic analytics / flow logging được hỗ trợ** để quan sát luồng theo cấu hình của tổ chức.

Tính năng, quyền, điều kiện hỗ trợ và chi phí logging có thể thay đổi. Trước khi sử dụng, xác nhận loại tài nguyên, vùng triển khai và nguồn dữ liệu đã được cấu hình.

## 10. High availability: tránh một NVA thành điểm lỗi duy nhất

Một NVA VM đơn lẻ có thể tạo ra **single point of failure**. Nếu thiết bị dừng, reboot, mất khả năng xử lý hoặc hết dung lượng, nhiều workload có thể mất kết nối dù VNet và peering vẫn hoạt động.

### 10.1. Kiến trúc HA điển hình

Tùy sản phẩm và khả năng hỗ trợ:

- **Active–standby:** một NVA xử lý chính, một NVA sẵn sàng thay thế. Cần cơ chế failover, cập nhật đường đi và đồng bộ state nếu sản phẩm yêu cầu.
- **Active–active:** nhiều NVA xử lý đồng thời. Cần phân phối luồng, kiểm soát stickiness/session symmetry và giới hạn theo thiết kế.
- **Internal Standard Load Balancer + HA ports:** trong mô hình NVA được hỗ trợ, có thể dùng một frontend IP và health probes để phân phối traffic tới những NVA backend, đồng thời routing phải phù hợp với kiểu triển khai.
- **Availability Zones/Availability Sets:** giúp phân tán instance khi dịch vụ/khu vực hỗ trợ, nhưng không tự sửa logic route hoặc bảo đảm stateful flow.
- **Azure Firewall được quản lý:** thay việc tự duy trì các VM NVA bằng cơ chế HA và scale của dịch vụ Azure theo cấu hình/khu vực hỗ trợ.

Không phải mọi vendor NVA đều hỗ trợ các mô hình trên theo cùng cách. Hãy dùng kiến trúc tham khảo và hướng dẫn cụ thể của nhà cung cấp. Đặc biệt, **không coi load balancer frontend IP là next hop hợp lệ cho mọi tình huống** chỉ vì muốn có HA.

### 10.2. Stateful inspection và tính đối xứng

Một session có thể gồm các gói:

~~~text
Client A → Firewall 1 → Server B
Server B → Firewall 2 → Client A
~~~

Nếu Firewall 1 và Firewall 2 không chia sẻ trạng thái, thiết bị thứ hai có thể từ chối response vì không thấy gói khởi tạo. Do đó HA cần giải quyết:

1. Cách chọn node cho chiều đi và chiều về.
2. Session affinity hoặc cách đồng bộ state theo sản phẩm.
3. Ảnh hưởng của SNAT đến đường trả về và log.
4. Health probe đánh giá đúng khả năng forwarding, không chỉ VM còn chạy.
5. Hành vi failover: phiên hiện hữu được giữ hay phải kết nối lại.
6. Route và policy có đồng nhất giữa các instance không.

### 10.3. Fail-open hay fail-closed?

- **Fail-closed:** khi thiết bị không sẵn sàng, luồng phải kiểm tra bị chặn. Thích hợp khi yêu cầu an ninh quan trọng hơn việc tiếp tục kết nối.
- **Fail-open:** có đường bypass khi thiết bị lỗi. Có thể duy trì dịch vụ nhưng phải được phê duyệt vì traffic có thể đi ngoài điểm kiểm soát.

Azure không tự đưa ra chính sách này thay nhóm vận hành. Hãy ghi quyết định, điều kiện kích hoạt và cách kiểm toán.

### 10.4. Kiểm thử failover

Trong sandbox, có thể thử ngắt một NVA node hoặc làm health probe chuyển trạng thái theo quy trình được phê duyệt, sau đó đo:

- Thời gian khôi phục các kết nối mới.
- Ảnh hưởng đến phiên đã thiết lập.
- Log kiểm tra có tiếp tục được ghi không.
- Traffic có đi bypass ngoài ý muốn không.
- Route/peering, DNS, policy và backend health có còn hợp lệ không.

Không làm failover test đột ngột trên production khi chưa có kế hoạch và phương án phục hồi.

## 11. Khi nào cần định tuyến động và Azure Route Server?

Khi số VNet và NVA tăng, quản lý hàng loạt UDR thủ công có thể khó mở rộng. Một số giải pháp NVA hỗ trợ **BGP**; trong những kiến trúc được hỗ trợ, **Azure Route Server** giúp trao đổi thông tin route giữa NVA và nền tảng mạng Azure.

Tuy nhiên:

- Route Server **không phải firewall**, không tự kiểm tra payload hay lọc traffic.
- BGP peering không thay thế việc thiết kế policy, route trên các subnet và đường trả về.
- Khả năng quảng bá route và cách route được tiêu thụ phải theo kiến trúc Azure Route Server và NVA cụ thể.
- Khi có UDR và BGP cùng prefix, cần hiểu quy tắc chọn route trước khi triển khai.
- Có thêm control plane và dependency, phải cân nhắc HA, giới hạn, giám sát và chi phí.

Với lab hai spoke, UDR minh bạch và đủ để học nguyên lý. Với môi trường nhiều subscription, cần so sánh cách vận hành UDR/IaC, Route Server, Virtual WAN hoặc một kiến trúc firewall được quản lý.

## 12. DNS, TLS và giới hạn của kiểm tra payload

Traffic có thể được **định tuyến qua NVA** nhưng khả năng nhận diện/kiểm tra ứng dụng còn phụ thuộc cấu hình thực tế.

### 12.1. DNS

Các điểm cần đánh giá:

- Workload sử dụng Azure-provided DNS, custom DNS, Azure Private DNS hay Private Resolver?
- Hostname của dịch vụ đích trỏ về private IP hay public IP?
- DNS server có nằm trong VNet khác, khiến DNS traffic cũng cần route/NSG phù hợp không?
- Có Private Endpoint cần private DNS zone và VNet link riêng không?

Một hostname trả IP khác kỳ vọng sẽ làm traffic đi theo một route khác. Vì vậy phải kiểm tra kết quả **nslookup/dig** trước khi nghi ngờ UDR.

### 12.2. TLS và ứng dụng

NVA có thể nhìn thấy IP nguồn/đích và port của một kết nối TLS mà không đọc được nội dung bên trong. Muốn **TLS inspection/decryption** phải có tính năng hỗ trợ, chính sách riêng, chứng chỉ/tổ chức tin cậy và sự chấp thuận về bảo mật, pháp lý, quyền riêng tư.

Không coi “traffic đi qua firewall” đồng nghĩa “mọi payload HTTPS đã được quét”. Một số loại lưu lượng có cơ chế mã hóa, certificate pinning hoặc giao thức không tương thích với TLS interception.

### 12.3. Private Endpoint

Private Endpoint cho phép truy cập một dịch vụ cụ thể bằng private IP theo hỗ trợ của Azure. Nó không tự thay thế yêu cầu kiểm soát giữa mọi subnet/VNet; ngược lại, peering không tự cấp quyền truy cập dữ liệu vào dịch vụ có Private Endpoint.

Nếu lưu lượng đến Private Endpoint cần đi qua thiết bị kiểm tra, phải xem các giới hạn về route, network policy của subnet chứa private endpoint và đường đi theo dịch vụ cụ thể. Không ép route chung rồi giả định traffic Private Endpoint sẽ tuân theo mọi UDR như VM thông thường.

## 13. Ghi log, giám sát và quan sát lưu lượng kiểm tra

Một hệ thống firewall thực tế cần **bằng chứng** rằng policy đã áp dụng. Tối thiểu nên thu thập:

| Nguồn dữ liệu | Nội dung cần xem |
|---|---|
| Firewall/NVA traffic logs | Time, source IP, destination IP, port, protocol, action, rule, session |
| NVA system/health | CPU, memory, NIC throughput, packet drop, session count, interface/HA status |
| Azure Monitor metrics | Tình trạng dịch vụ/tài nguyên được quản lý, xu hướng lỗi và throughput |
| Azure Activity Log | Ai đã thay route table, peering, NIC, NSG hoặc cấu hình hạ tầng |
| NSG/virtual network flow telemetry được hỗ trợ | Luồng mạng có bị từ chối/cho phép tại ranh giới tương ứng |
| Ứng dụng nguồn/đích | HTTP status, timeout, TLS error, connection reset, latency |
| Cost Management | Chi phí VM, license, Load Balancer, Azure Firewall, peering và log |

Khi phân tích sự cố, đặt cùng **mốc thời gian** và **correlation ID** nếu có. Log của NVA có thể hiển thị IP sau NAT; cần liên hệ với bản ghi NAT/session để tìm nguồn gốc.

Một số dữ liệu kết nối và log có thể chứa địa chỉ, định danh hoặc thông tin nhạy cảm. Hãy dùng RBAC, retention và chính sách truy cập log phù hợp.

### 13.1. Thiết lập cảnh báo vận hành

Các cảnh báo nên bao gồm:

- NVA không healthy hoặc một node HA bị mất.
- Session/throughput/CPU gần giới hạn của giải pháp.
- Packet drop, timeout hoặc kết nối bị reset tăng bất thường.
- Route table/peering bị thay đổi ngoài change window.
- Luồng trọng yếu không còn xuất hiện trong log inspection.
- Chi phí network/egress tăng khác thường.

Đừng dùng số lượng denied traffic một mình để đánh giá nguy cơ; một policy hoạt động tốt có thể chặn nhiều kết nối không hợp lệ. Đọc kèm trend, nguồn, đích và mức độ quan trọng của workload.

## 14. Phân tích lỗi thường gặp

| Triệu chứng | Khả năng gây lỗi | Cách kiểm tra |
|---|---|---|
| Peering Connected nhưng A không gọi được B | Thiếu UDR, NVA không forward, NSG/firewall chặn | Effective routes, peering forwarded traffic, NIC/OS forwarding, rule NVA |
| A→B đến NVA nhưng không đến B | NVA thiếu route, firewall deny, NIC forwarding tắt | Traffic log, routing table trên NVA, NIC IP forwarding |
| B phản hồi nhưng A không nhận | Thiếu route về, asymmetric path, session state | Route trên subnet B, NAT, firewall session logs |
| Kết nối thành công nhưng không có log NVA | Traffic bypass hoặc logging chưa đúng | So sánh route hiệu lực, log filter, NAT và time range |
| Không tạo được peering | CIDR hai VNet trùng nhau hoặc thiếu quyền | VNet address spaces và RBAC hai phía |
| Route table tồn tại nhưng traffic không đổi | Bảng chưa liên kết subnet đúng | subnet.routeTable.id và effective routes |
| Chỉ một subnet bị lỗi | Route table/NSG chỉ áp dụng subnet đó | Association, NSG effective rules, NIC subnet |
| Cổng TCP mở nhưng ứng dụng lỗi | DNS, TLS, auth, policy ứng dụng | nslookup, certificate, application logs |
| Outbound Internet hỏng sau khi thêm 0.0.0.0/0 | NVA không có đường egress hoặc thiếu SNAT | Next hop, firewall/NAT, routing, Internet policy |
| Một node NVA lỗi gây mất kết nối rộng | Chưa có HA hoặc health probe sai | Backend health, stateful session, route/failover behavior |
| Lưu lượng Private Endpoint không theo route dự kiến | Network policies/route behavior đặc thù | Kiến trúc Private Link, effective routing và điều kiện hỗ trợ |
| Chi phí tăng mạnh | Lưu lượng peering/firewall/logging lớn, hairpin traffic | Cost Management, byte counters, traffic matrix |

### 14.1. Quy trình điều tra từng hop

Khi A không gọi được B:

1. **Xác minh DNS:** hostname đích trỏ tới IP nào?
2. **Xác minh route A:** effective route tới IP B chọn next hop nào?
3. **Xác minh peering:** A↔hub và hub↔B đều Connected? Forwarded traffic đúng hướng?
4. **Xác minh NVA ingress:** gói có đến NVA không?
5. **Xác minh NVA policy/forwarding:** rule allow/deny, IP forwarding, routing của appliance?
6. **Xác minh route B:** B có thể trả lời qua NVA không?
7. **Xác minh session:** đường đi/về có cùng stateful node hoặc cơ chế state sharing phù hợp không?
8. **Xác minh ứng dụng:** listener, firewall OS, TLS và authentication có hoạt động không?

Không khắc phục bằng cách mở NSG **Any/Any** hoặc tắt toàn bộ firewall để “thử cho nhanh” trên production. Nếu cần kiểm thử cô lập, thực hiện trong lab, ghi phạm vi và khôi phục ngay sau khi có kết quả.

### 14.2. Kiểm chứng route trên một máy cụ thể

Một lệnh ví dụ:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-rg>" \
  --name "<vm-nic>" \
  --output table
~~~

Nếu NIC không cho đọc effective routes, hãy kiểm tra điều kiện của tài nguyên và dùng công cụ phù hợp của Azure Network Watcher, thay vì kết luận mạng không có route.

## 15. Thay đổi và rollback có kiểm soát

Thay UDR, peering hoặc firewall policy có thể gây outage cho nhiều dịch vụ. Trước khi triển khai:

1. Chụp lại logic hiện tại của route table/subnet association, peering và firewall rule.
2. Liệt kê những prefix và ứng dụng bị ảnh hưởng.
3. Chuẩn bị phương án rollback đã được duyệt, gồm cả cách truy cập NVA nếu đường quản trị đi qua nó.
4. Áp dụng từng nhóm subnet khi khả thi thay vì cập nhật tất cả cùng lúc.
5. Đo kết nối hợp lệ và kiểm tra denied traffic trước/sau.
6. Kiểm tra giám sát và owner xác nhận ứng dụng ổn định.

Đối với lab đã tạo **route table mới** và subnet ban đầu **không có route table**, có thể gỡ association:

~~~bash
az network vnet subnet update \
  --resource-group rg-orders-app \
  --vnet-name vnet-orders-app \
  --name snet-app \
  --remove routeTable

az network vnet subnet update \
  --resource-group rg-orders-data \
  --vnet-name vnet-orders-data \
  --name snet-data \
  --remove routeTable
~~~

Chỉ thực hiện khi đúng môi trường lab và không có route table cũ cần phục hồi. Nếu trước đó subnet đã có route table riêng, **rollback phải gắn lại đúng route table ban đầu**, không đơn giản là xóa mọi association. Xác minh subnet và kết nối sau rollback.

Khi chắc chắn route table mới không còn được dùng, có thể dọn riêng các tài nguyên lab:

~~~bash
az network route-table delete \
  --resource-group rg-orders-app \
  --name rt-orders-app-inspection

az network route-table delete \
  --resource-group rg-orders-data \
  --name rt-orders-data-inspection
~~~

Không xóa NVA, VNet, peering, subnet hoặc resource group có tài nguyên khác khi chưa xác nhận dependency và quyền sở hữu.

## 16. Hiệu năng, giới hạn và chi phí

### 16.1. Dung lượng cần dự toán

NVA có thể trở thành nút thắt cổ chai khi toàn bộ traffic đi qua một điểm. Dự toán dựa trên:

- Throughput chiều vào/ra và lưu lượng đồng thời, giờ cao điểm.
- Số kết nối mới mỗi giây, session đang duy trì và session timeout.
- Packet size, tỷ lệ small packets, số rule, IPS/TLS inspection nếu có.
- Giới hạn NIC/VM/CPU/memory của appliance và quy mô HA.
- Overhead của logging, mã hóa, NAT, load balancer và định tuyến qua region.

Đừng lấy băng thông danh nghĩa của NIC làm throughput inspection bảo đảm. Kiểm thử theo profile traffic thực và điều kiện của vendor.

### 16.2. Chi phí cần tính

| Thành phần | Chi phí có thể phát sinh |
|---|---|
| NVA VM | Compute, disk, IP và license/phần mềm |
| Azure Firewall | Mô hình phí của tier được chọn, xử lý dữ liệu và các tính năng bổ sung |
| Load Balancer | Quy tắc tính phí của SKU/cấu hình và xử lý dữ liệu tương ứng |
| VNet peering | Phí traffic regional/global theo nơi triển khai và chiều truyền |
| Log và giám sát | Ingestion, retention, truy vấn, cảnh báo và hệ thống SIEM |
| Egress | Phí theo dịch vụ, tuyến và vùng/Internet theo bảng giá áp dụng |
| HA/DR | Nhiều instance, subnet, thiết bị phụ trợ và nhân sự vận hành |

Định tuyến A→hub→B có thể tăng quãng đường đi, lượng dữ liệu qua các peering và chi phí so với route trực tiếp. Hãy đo bằng Azure Cost Management và đối chiếu bảng giá hiện hành trước khi chọn một kiến trúc kiểm tra mọi luồng.

### 16.3. Những quyết định nên ghi thành ADR

Một **Architecture Decision Record** nên nêu:

- Vì sao cần kiểm tra luồng này và rủi ro nếu bypass.
- Chọn Azure Firewall, NVA hay giải pháp khác vì lý do nào.
- IP plan, prefix, subnet association, UDR và routing hai chiều.
- Phạm vi NAT, DNS, TLS inspection và logging.
- Mô hình HA, failover, fail-open/fail-closed.
- Owner, quyền vận hành, quy trình update và backup cấu hình.
- Capacity, chi phí dự toán, SLA/SLO và cách theo dõi.
- Cách kiểm thử route/inspection sau mỗi thay đổi.

## 17. Kiểm tra kiến trúc trước production

- [ ] Đã định nghĩa rõ trust boundaries và traffic matrix nguồn–đích–port.
- [ ] Đã phân biệt egress, inbound và east–west cần inspection.
- [ ] Mọi VNet có CIDR không overlap và peering hai chiều cần thiết.
- [ ] Đã kiểm tra peering **Allow forwarded traffic** ở những hướng liên quan.
- [ ] NVA hoặc Azure Firewall thực sự nằm trên route được lựa chọn.
- [ ] Azure NIC và guest/NVA forwarding đã cấu hình nếu dùng NVA VM.
- [ ] Next-hop IP hợp lệ, ổn định và có phương án HA nếu cần.
- [ ] Subnet route tables không ghi đè các route quan trọng trước đó.
- [ ] Đường đi và về được kiểm tra, không có asymmetric routing ngoài thiết kế.
- [ ] Firewall policy và NSG chỉ cho phép traffic được phê duyệt.
- [ ] DNS, Private Endpoint, TLS và đường truy cập quản trị được xem xét riêng.
- [ ] Có log chứng minh traffic đi qua appliance và rule áp dụng.
- [ ] Đã thử traffic hợp lệ, traffic bị chặn, failure/failover và rollback trong môi trường thích hợp.
- [ ] Đã dự toán throughput, HA, chi phí peering/firewall và retention log.
- [ ] Cấu hình và thay đổi được quản lý qua IaC/pipeline hoặc quy trình được kiểm soát.

## 18. Bài tập thực hành và câu hỏi suy luận

### Bài tập 1: Thiết kế routing qua NVA

Cho ba VNet như ví dụ: hub 10.0.0.0/16, spoke A 10.10.0.0/16, spoke B 10.20.0.0/16. NVA ở hub có IP 10.0.1.4.

Hãy vẽ sơ đồ, viết route cần đặt ở subnet A và B để traffic TCP/443 từ A tới B đi qua NVA, và giải thích vì sao chỉ peering A–hub, hub–B không đủ.

**Tiêu chí đạt:** có UDR hai phía, next hop đúng IP, hiểu forwarded traffic và đảm bảo đường trả về.

### Bài tập 2: Tìm nguyên nhân bypass

Một VM A gọi được VM B, nhưng log NVA không ghi nhận traffic. Hãy trình bày thứ tự kiểm tra: DNS, effective route, direct peering, subnet route-table association, NAT, logging và firewall rules.

### Bài tập 3: Đánh giá rủi ro của default route

Đội vận hành muốn thêm 0.0.0.0/0 → NVA vào mọi subnet. Liệt kê những kiểm tra cần có trước triển khai: DNS, outbound access, PaaS/private endpoints, HA, SNAT, bandwidth, monitoring và rollback.

### Bài tập 4: Thiết kế HA cho stateful firewall

Hai NVA active–active có thể xử lý traffic bằng load balancer. Giải thích vì sao chỉ có hai VM chưa đủ đảm bảo HA stateful, và cần điều kiện gì về session affinity, đường về, health probe, forwarding và failover.

### Bài tập 5: Tính toán chi phí ở mức thiết kế

So sánh kiến trúc (A) mỗi spoke có các rule NSG, kết nối trực tiếp có kiểm soát với (B) toàn bộ east–west đi qua hub NVA. Hãy liệt kê các yếu tố chi phí, hiệu năng và độ phức tạp cần đưa vào quyết định. Không cần tự bịa đơn giá.

### Câu hỏi tự kiểm tra

1. UDR với next hop VirtualAppliance tự động bật IP forwarding trên VM không?
2. Peering Connected có đảm bảo traffic đi qua NVA không?
3. Vì sao stateful firewall thường cần đường đi và về đối xứng?
4. Khác biệt giữa NSG, WAF, NVA và Azure Firewall là gì?
5. Bật Allow forwarded traffic có tự tạo route giữa các spoke không?
6. Khi nào SNAT có thể che khuất IP nguồn và làm khó phân tích log?
7. Vì sao nên kiểm tra effective routes thay vì chỉ đọc cấu hình route table?
8. Kết nối TCP thành công nhưng NVA không có log có chứng minh traffic an toàn không?
9. Có thể dùng Azure Route Server thay thế mọi firewall rule không?
10. Tại sao route 0.0.0.0/0 cần được review nghiêm ngặt hơn một route /16 phục vụ một luồng cụ thể?

## 19. Tài liệu tham khảo

- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Virtual Network peering overview](https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview)
- [Hub-spoke network topology in Azure](https://learn.microsoft.com/azure/architecture/networking/architecture/hub-spoke)
- [Azure Firewall documentation](https://learn.microsoft.com/azure/firewall/overview)
- [Azure Load Balancer HA ports overview](https://learn.microsoft.com/azure/load-balancer/load-balancer-ha-ports-overview)
- [Azure Route Server overview](https://learn.microsoft.com/azure/route-server/overview)
- [Azure Network Watcher connection troubleshoot](https://learn.microsoft.com/azure/network-watcher/network-watcher-connectivity-overview)
- [Network security groups overview](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Azure Virtual Network pricing](https://azure.microsoft.com/pricing/details/virtual-network/)

