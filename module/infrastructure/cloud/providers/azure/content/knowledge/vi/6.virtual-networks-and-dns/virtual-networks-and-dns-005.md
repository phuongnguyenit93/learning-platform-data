# Route table, system route và user-defined route

Khi một máy ảo trong Azure Virtual Network (VNet) gửi gói tin tới địa chỉ IP đích, Azure phải xác định **next hop** (chặng tiếp theo): chuyển trực tiếp trong mạng ảo, gửi tới Internet, chuyển qua virtual network gateway, đưa qua thiết bị mạng ảo, hay loại bỏ gói tin. Quyết định này dựa trên **bảng định tuyến có hiệu lực** của giao diện mạng, gồm các tuyến do Azure cung cấp và những tuyến do người quản trị cấu hình.

Bài học thuộc chương **Mạng ảo và phân giải tên** trong module **CLOUD_PROVIDERS_AZURE**. Module khám phá Microsoft Azure từ subscription, resource group và Entra ID tới mạng ảo, dịch vụ tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí. Sau khi biết cách tạo VNet/subnet, bạn cần hiểu định tuyến để kiểm soát đường đi của lưu lượng giữa các subnet, VNet, mạng tại chỗ và Internet. DNS giải quyết tên thành địa chỉ IP; **routing quyết định đường đi đến địa chỉ IP đó**. Hai chức năng liên quan nhưng không thay thế nhau.

Sau bài học, bạn có thể:

- Giải thích mối liên hệ giữa subnet, system route, route table và effective routes.
- Phân biệt system route, user-defined route (UDR) và tuyến học qua BGP.
- Dự đoán tuyến được chọn dựa trên **longest prefix match** và ưu tiên khi prefix bằng nhau.
- Chọn next hop thích hợp cho Internet, mạng nội bộ, mạng tại chỗ và network virtual appliance (NVA).
- Tạo route table, thêm UDR và liên kết route table với subnet bằng Azure Portal/Azure CLI.
- Kiểm tra effective routes và dùng Network Watcher để tìm nguyên nhân lưu lượng đi sai đường.
- Nhận biết các rủi ro về vòng lặp định tuyến, đường về bất đối xứng, IP forwarding và chi phí.

## 1. Định tuyến diễn ra ở đâu trong Azure?

VNet là phạm vi mạng logic gồm các không gian địa chỉ CIDR và các subnet. Mỗi network interface (NIC) của máy ảo được kết nối với một subnet. Khi NIC gửi gói IP ra ngoài, hạ tầng Azure áp dụng các tuyến có hiệu lực đối với NIC đó để quyết định next hop.

Một route thường có những thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Address prefix | Mạng đích dưới dạng CIDR | 10.40.0.0/16 |
| Next hop type | Kiểu chặng tiếp theo | VirtualAppliance |
| Next hop IP | Địa chỉ của NVA nếu kiểu next hop yêu cầu | 10.20.2.4 |
| Source | Nguồn sinh ra tuyến: system, user hoặc BGP | User |
| State | Trạng thái hoạt động của tuyến trong effective routes | Active hoặc Invalid tùy kết quả |

Ví dụ, tuyến **10.40.0.0/16 → VirtualAppliance 10.20.2.4** nghĩa là lưu lượng đến mạng 10.40.0.0/16 sẽ được chuyển tới NVA có IP riêng 10.20.2.4, nếu tuyến đó được chọn và đường tới NVA hợp lệ.

Để hiểu định tuyến, cần phân biệt ba khái niệm:

1. **System route:** Azure tự tạo khi VNet/subnet tồn tại hoặc khi cấu hình các kết nối mạng phù hợp.
2. **User-defined route (UDR):** người quản trị chủ động cấu hình để thay đổi đường đi mong muốn.
3. **Effective routes:** tập hợp tuyến có hiệu lực trên một NIC sau khi Azure xét các tuyến system, UDR và tuyến được lan truyền từ BGP.

Một tài nguyên Azure mang tên **route table** chủ yếu dùng để chứa **UDR** và cấu hình liên quan đến việc lan truyền BGP. Nó không có nghĩa là tất cả system route đều nằm sẵn trong tài nguyên route table do bạn tạo. NIC vẫn có effective routes ngay cả khi subnet chưa được liên kết với bất kỳ route table tùy chỉnh nào.

## 2. System route: các tuyến Azure tạo tự động

Khi bạn tạo VNet, Azure tự cung cấp các tuyến nền tảng. Những tuyến thường gặp:

| Address prefix | Next hop system điển hình | Ý nghĩa |
|---|---|---|
| Không gian địa chỉ của VNet, ví dụ 10.20.0.0/16 | Virtual network | Chuyển lưu lượng giữa các địa chỉ thuộc VNet |
| 0.0.0.0/0 | Internet | Tuyến mặc định đến các địa chỉ không khớp tuyến cụ thể hơn |
| 10.0.0.0/8 | None | Loại bỏ lưu lượng tới dải riêng này nếu không có tuyến cụ thể hơn |
| 172.16.0.0/12 | None | Tương tự với dải private IPv4 |
| 192.168.0.0/16 | None | Tương tự với dải private IPv4 |
| 100.64.0.0/10 | None | Dải shared address space được Azure xử lý theo tuyến nền tảng |

Các tuyến mẫu trên mô tả định tuyến IPv4 thông dụng. Azure có thể sinh thêm tuyến hệ thống tùy theo địa chỉ VNet và cấu hình mạng; với IPv6 cũng có hành vi riêng. **Không coi bảng này là danh sách cố định của mọi effective route.** Hãy kiểm tra effective routes trên NIC thực tế để biết kết quả.

### Tại sao VNet 10.20.0.0/16 vẫn liên lạc được khi có 10.0.0.0/8 → None?

Một gói đến **10.20.1.10** khớp cả **10.0.0.0/8** và **10.20.0.0/16**. Azure chọn tiền tố **/16** vì nó cụ thể hơn **/8**. Kết quả là gói được định tuyến trong VNet, không bị loại bỏ bởi tuyến None rộng hơn.

### Các tuyến hệ thống có thể được bổ sung

- **VNet peering:** Azure bổ sung các tuyến đến không gian địa chỉ của VNet được peering, với next hop phù hợp cho peering.
- **Virtual network gateway:** khi kết nối VPN/ExpressRoute và quảng bá tuyến được cấu hình, các tuyến đến mạng khác có thể xuất hiện trong effective routes.
- **Service-specific routes:** một số dịch vụ và cấu hình mạng có thể thêm các tuyến đặc thù; cách định tuyến cần được xác minh trên NIC của workload.

System route mặc định 0.0.0.0/0 → Internet **không bảo đảm** VM truy cập Internet được. Khả năng outbound còn phụ thuộc vào phương thức outbound connectivity (ví dụ NAT Gateway hoặc đường egress được hỗ trợ), NSG, firewall, trạng thái tài nguyên và các chính sách khác. Route chỉ xác định đường đi dự kiến.

## 3. User-defined route (UDR) và tài nguyên route table

**UDR** cho phép người quản trị ghi đè hoặc bổ sung lựa chọn định tuyến. Bạn tạo một **route table**, thêm các route vào đó, rồi **associate** route table với subnet cần áp dụng.

~~~text
VNet: vnet-app (10.20.0.0/16)
    |
    +-- subnet-app (10.20.1.0/24) -- [rt-app]
    |                                  |
    |                                  +-- 0.0.0.0/0
    |                                       next hop: 10.20.2.4 (NVA)
    |
    +-- subnet-nva (10.20.2.0/24)
                |
                +-- Firewall/NVA: 10.20.2.4
~~~

Trong ví dụ, các workload ở subnet-app gửi lưu lượng khớp tuyến 0.0.0.0/0 tới NVA thay vì dùng system route mặc định tới Internet. Với đích thuộc chính VNet, system route cụ thể hơn vẫn thường thắng tuyến 0.0.0.0/0.

Các quy tắc phạm vi cần nhớ:

- UDR được áp dụng thông qua **liên kết route table với subnet**, không gắn trực tiếp route table vào từng VM.
- Một subnet có thể liên kết tối đa **một route table** tại một thời điểm.
- Một route table có thể được liên kết với **nhiều subnet**, nếu đáp ứng các giới hạn và yêu cầu mạng của Azure.
- Route table là tài nguyên riêng. Xóa route table hoặc thay đổi tuyến trên table dùng chung có thể ảnh hưởng nhiều subnet cùng lúc.
- Các subnet không liên kết table đó sẽ không chịu các UDR trong table ấy.
- Azure xử lý effective routes riêng cho từng NIC; cấu hình có thể khác nhau theo subnet, peering, gateway và các chính sách tương ứng.

### Khi nào nên dùng UDR?

| Mục tiêu | Ví dụ UDR | Lưu ý |
|---|---|---|
| Đưa egress qua tường lửa tập trung | 0.0.0.0/0 → VirtualAppliance | NVA phải thực sự chuyển tiếp và có đường ra phù hợp |
| Đưa lưu lượng đến mạng đích qua appliance | 10.40.0.0/16 → VirtualAppliance | Kiểm tra đường về và kết nối NVA đến đích |
| Chủ động loại bỏ một dải mạng | 198.51.100.0/24 → None | Chỉ điều khiển route; không thay thế firewall |
| Chỉ định hướng đến Internet | 0.0.0.0/0 → Internet | Phải đánh giá ảnh hưởng bảo mật, forced tunneling và outbound connectivity |
| Định hướng qua virtual network gateway khi được hỗ trợ | Prefix mạng tại chỗ → VirtualNetworkGateway | Phụ thuộc kiến trúc gateway, cấu hình và route propagation |

UDR giúp quyết định **đường đi**, không phân tích nội dung gói tin hay tạo quy tắc allow/deny theo cổng dịch vụ như NSG hoặc firewall.

## 4. Các loại next hop của UDR

Những loại next hop thường được sử dụng:

| Next hop type | Hành vi chính | Trường hợp sử dụng |
|---|---|---|
| **Virtual network** | Chuyển lưu lượng trong hạ tầng VNet theo đích có thể truy cập | Các tuyến tùy chỉnh cần hướng về VNet |
| **Internet** | Đưa lưu lượng theo đường Internet của Azure | Chủ động chọn tuyến Internet khi cần |
| **Virtual appliance (VirtualAppliance)** | Đưa gói đến địa chỉ IP riêng của NVA/firewall | Kiểm tra, lọc hoặc điều hướng lưu lượng tập trung |
| **Virtual network gateway (VirtualNetworkGateway)** | Đưa lưu lượng qua gateway phù hợp | Mạng tại chỗ qua kết nối gateway |
| **None** | Loại bỏ gói tin khớp route | Chặn định tuyến đến một prefix |

Khi chọn **VirtualAppliance**, bạn cần cấu hình **next hop IP address**. Đây thường là địa chỉ IP riêng của một appliance có thể được truy cập qua mạng Azure. Địa chỉ IP đó phải thuộc kiến trúc định tuyến hợp lệ và appliance phải được cấu hình để chuyển tiếp các gói đến mạng đích.

**None** là một loại next hop để bỏ gói tin khi route đó được chọn. Nó hữu ích cho thử nghiệm định tuyến và một số trường hợp muốn tránh đường đi tới đích. Tuy nhiên, nếu cần kiểm soát truy cập theo nguồn, đích, protocol, port, người dùng hoặc ứng dụng, hãy dùng NSG/firewall và các chính sách tương ứng.

**VirtualNetworkGateway** không phải lựa chọn mặc định cho mọi kết nối đến mạng khác. Nó chỉ có ý nghĩa khi kiến trúc có gateway phù hợp và những điều kiện định tuyến liên quan được đáp ứng. Một số kiến trúc hub-spoke, Azure Virtual WAN hoặc VPN/ExpressRoute có yêu cầu định tuyến riêng, cần kiểm tra theo tài liệu dịch vụ.

## 5. Azure chọn route nào? Longest prefix và ưu tiên

Quy tắc quan trọng nhất là **longest prefix match**: khi nhiều tuyến khớp cùng một địa chỉ đích, Azure ưu tiên route có **prefix dài nhất** (mạng đích cụ thể nhất). Ví dụ, /24 cụ thể hơn /16, còn /16 cụ thể hơn /0.

Nếu nhiều tuyến khớp **cùng một prefix**, thứ tự ưu tiên thông thường là:

1. **User-defined route (UDR)**.
2. **BGP route**.
3. **System route**.

Thứ tự trên chỉ áp dụng **sau khi đã so sánh độ dài prefix**. Một system route /24 có thể thắng UDR /16 vì /24 cụ thể hơn. Một tuyến BGP /24 cũng có thể thắng UDR /16. Đừng suy luận UDR luôn thắng mọi route bất kể prefix.

### Ví dụ tính toán đường đi

Giả sử VM nằm trong VNet **10.20.0.0/16**. Sau khi cấu hình gateway và route table, effective routes có thể chứa các tuyến sau:

| Nguồn | Prefix | Next hop |
|---|---|---|
| System | 10.20.0.0/16 | Virtual network |
| System | 10.0.0.0/8 | None |
| System | 0.0.0.0/0 | Internet |
| User | 10.40.0.0/16 | VirtualAppliance 10.20.2.4 |
| BGP | 10.40.8.0/24 | Virtual network gateway |
| User | 0.0.0.0/0 | VirtualAppliance 10.20.2.4 |

Với từng IP đích:

| IP đích | Các tuyến có thể khớp | Tuyến được chọn | Lý do |
|---|---|---|---|
| 10.20.1.20 | 10.0.0.0/8, 10.20.0.0/16, 0.0.0.0/0 | System 10.20.0.0/16 | /16 cụ thể hơn /8 và /0 |
| 10.40.8.25 | 10.0.0.0/8, UDR 10.40.0.0/16, BGP 10.40.8.0/24, 0.0.0.0/0 | BGP 10.40.8.0/24 | /24 cụ thể nhất |
| 10.40.50.25 | 10.0.0.0/8, UDR 10.40.0.0/16, 0.0.0.0/0 | UDR 10.40.0.0/16 | /16 cụ thể nhất |
| 8.8.8.8 | System 0.0.0.0/0, UDR 0.0.0.0/0 | UDR 0.0.0.0/0 | Cùng /0, User ưu tiên hơn System |

Ví dụ này là một tập route **giả định** nhằm minh họa cơ chế chọn đường; tuyến BGP chỉ xuất hiện khi có gateway và route propagation phù hợp. Effective routes thực tế có thể khác do các quy tắc cấu hình và khả năng kết nối của hệ thống.

### Nếu một route có trạng thái Invalid?

Không nên chỉ đọc các prefix rồi kết luận route đang được sử dụng. Trong **Effective routes**, bạn cũng cần xem **State** (ví dụ Active/Invalid), Source và Next hop. Tuyến Invalid không được sử dụng như tuyến đang hoạt động. Một số tuyến có thể bị vô hiệu hóa vì có tuyến ưu tiên hơn hoặc do cấu hình; hãy dựa trên trạng thái và công cụ chẩn đoán thực tế.

## 6. Tình huống thiết kế: buộc egress đi qua firewall/NVA

Trong kiến trúc hub-spoke hoặc VNet nội bộ, bạn có thể muốn tất cả lưu lượng ra ngoài đi qua một firewall để ghi log và áp dụng chính sách.

~~~text
VM ứng dụng
10.20.1.10 (subnet-app)
       |
       | UDR: 0.0.0.0/0 -> 10.20.2.4
       v
Firewall/NVA
10.20.2.4 (subnet-nva)
       |
       | Quy tắc firewall, SNAT/routing phù hợp
       v
Đích ngoài VNet / Internet
       |
       | Đường về phải hợp lệ
       v
VM ứng dụng nhận phản hồi
~~~

Các điều kiện kỹ thuật:

- **NVA phải có khả năng chuyển tiếp gói:** nếu dùng VM làm router/firewall, bật **IP forwarding** ở Azure NIC và cấu hình forwarding trong hệ điều hành/ứng dụng. Azure Firewall là dịch vụ quản lý có mô hình triển khai và next hop riêng.
- **Có đường đi tới NVA:** IP 10.20.2.4 phải là địa chỉ next hop có thể được mạng nguồn truy cập.
- **Có đường về:** kiểm tra tuyến từ NVA tới mạng đích và tuyến phản hồi trở lại máy nguồn. Đường đi bất đối xứng có thể khiến stateful firewall bỏ gói.
- **Kiểm tra NSG và firewall:** route đúng chưa đủ; NSG và quy tắc firewall có thể vẫn chặn lưu lượng.
- **Tránh vòng lặp:** không cấu hình route trên chính subnet NVA khiến gói quay trở lại NVA hoặc lặp giữa hai thiết bị.
- **Xem xét HA:** nếu NVA bị lỗi, UDR vẫn có thể chuyển gói vào một next hop không đáp ứng. Cần thiết kế khả dụng cao và phương án dự phòng phù hợp.

**Forced tunneling** là cách chuyển lưu lượng mặc định qua một điểm kiểm soát hoặc mạng tại chỗ. Nó có ích cho bảo mật và kiểm toán nhưng có thể làm tăng độ trễ, tạo phụ thuộc vào firewall/gateway và ảnh hưởng lưu lượng dịch vụ Azure. Đánh giá các ngoại lệ, dịch vụ bắt buộc truy cập và chính sách định tuyến trước khi triển khai ở production.

## 7. BGP routes và gateway route propagation

Khi dùng VPN Gateway hoặc ExpressRoute, các tuyến từ mạng kết nối có thể được quảng bá qua **BGP** để Azure biết cách đến những prefix ở mạng tại chỗ.

Ví dụ, văn phòng quảng bá **172.20.0.0/16** qua VPN Gateway. Nếu tuyến BGP được lan truyền tới subnet ứng dụng, VM trong subnet có thể học route đến 172.20.0.0/16 qua gateway mà không cần tự tạo UDR cho từng subnet.

Route table có tùy chọn về **BGP route propagation**. Nếu bạn tắt propagation trên route table của một subnet, những tuyến BGP được gateway quảng bá có thể không xuất hiện trong effective routes của subnet đó. Điều này hữu ích trong một số thiết kế muốn chủ động định tuyến bằng UDR nhưng cũng có thể khiến workload mất đường tới mạng tại chỗ.

Khi xem xét propagation:

1. Xác định prefix mà gateway quảng bá và nơi các prefix cần được sử dụng.
2. Kiểm tra việc chia sẻ gateway và các điều kiện cấu hình liên quan nếu dùng VNet peering.
3. Đối chiếu UDR có prefix cụ thể hơn hoặc trùng prefix BGP hay không.
4. Kiểm tra effective routes trước/sau thay đổi và thử nghiệm kết nối hai chiều.

**Không tắt BGP propagation chỉ để sửa một route không mong muốn** khi chưa hiểu tác động trên các kết nối VPN/ExpressRoute. Một số subnet đặc biệt và dịch vụ mạng có yêu cầu riêng về route table và propagation.

## 8. Cấu hình route table trong Azure Portal

Giả sử bạn có một VNet với subnet ứng dụng và cần tạo UDR đưa mạng đích **10.40.0.0/16** qua một appliance.

1. Mở [Azure Portal](https://portal.azure.com/), xác nhận subscription và resource group.
2. Tìm **Route tables**, chọn **Create**.
3. Chọn subscription, resource group, region và tên dễ nhận biết, ví dụ **rt-app-egress**.
4. Xem tùy chọn **Propagate gateway routes** và giữ cấu hình phù hợp với kiến trúc.
5. Tạo route table.
6. Trong route table, mở **Routes > Add**. Nhập tên **to-remote-via-nva**, address prefix **10.40.0.0/16**, next hop type **Virtual appliance**, next hop address **10.20.2.4**.
7. Vào **Subnets > Associate** (hoặc vào cấu hình subnet trong VNet) và gắn route table với đúng subnet ứng dụng.
8. Kiểm tra route table đang liên kết với subnet nào và xác minh bằng effective routes trên NIC của một VM trong subnet.

Giao diện Portal có thể thay đổi tên mục hoặc cách bố trí. Nếu table được liên kết với nhiều subnet, một thay đổi trong Routes có thể ảnh hưởng đến tất cả subnet ấy.

## 9. Cấu hình bằng Azure CLI

Các lệnh sau minh họa cách tạo route table và UDR, không yêu cầu bạn phải có sẵn ứng dụng thật. Chọn đúng subscription và dùng tên tài nguyên của môi trường riêng.

### Kiểm tra tài khoản và subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

Trong Cloud Shell, tài khoản thường đã được đăng nhập. Hãy kiểm tra subscription trước khi thay đổi tài nguyên.

### Tạo route table

~~~bash
az network route-table create \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --location southeastasia
~~~

Ví dụ dùng cú pháp nối dòng của Bash. Trong PowerShell, có thể viết lại thành một dòng hoặc dùng cú pháp nối dòng riêng của PowerShell. Thay region bằng region được phép trong subscription.

### Thêm route đến NVA

Giả sử mạng đích **10.40.0.0/16** phải đi qua appliance **10.20.2.4**:

~~~bash
az network route-table route create \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --name to-remote-via-nva \
  --address-prefix 10.40.0.0/16 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address 10.20.2.4
~~~

**Lệnh trên chỉ nên chạy nếu NVA 10.20.2.4 thực sự tồn tại và có đường chuyển tiếp đúng.** Nếu chưa có NVA, hãy dùng bài thực hành không có NVA ở mục 12.

### Gắn route table vào subnet

~~~bash
az network vnet subnet update \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --route-table rt-app-lab
~~~

Gắn route table với subnet thay đổi hành vi định tuyến của workload nằm trong subnet đó. Nếu subnet có ứng dụng đang chạy, hãy khảo sát tác động trước và bố trí thời gian thay đổi phù hợp.

### Kiểm tra route table và route đã cấu hình

~~~bash
az network route-table show \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --output json

az network route-table route list \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --output table
~~~

Xem liên kết route table của subnet:

~~~bash
az network vnet subnet show \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --query "{name:name, routeTable:routeTable.id}" \
  --output json
~~~

Các lệnh **show/list** cho biết cấu hình của route table và subnet. Chúng chưa chứng minh gói tin thật sẽ đi qua next hop; cần kiểm tra effective routes và các thành phần mạng liên quan.

## 10. Kiểm tra effective routes và chẩn đoán sự cố

Khi một VM không thể truy cập đích, đừng chỉ xem UDR vừa tạo. Azure còn có system routes, BGP routes, NSG, firewall và các trạng thái tài nguyên ảnh hưởng tới kết quả.

### Effective routes trên NIC

Trong Portal:

1. Mở **Network interfaces** hoặc NIC đang gắn với VM cần kiểm tra.
2. Tìm **Effective routes** trong phần hỗ trợ/chẩn đoán.
3. Xem địa chỉ đích, source, state, next hop type và next hop IP.
4. Đối chiếu route đang Active với prefix đích và quy tắc longest prefix.

Trong Azure CLI, có thể dùng:

~~~bash
az network nic show-effective-route-table \
  --resource-group <VM_RESOURCE_GROUP> \
  --name <NIC_NAME> \
  --output table
~~~

Việc hiển thị effective routes phụ thuộc vào NIC và trạng thái của VM/network. Nếu VM chưa tồn tại hoặc chưa ở trạng thái hỗ trợ truy vấn, bạn có thể kiểm tra cấu hình route table nhưng chưa thể quan sát đầy đủ effective routes như với VM đang chạy.

### Network Watcher: Next hop

Azure Network Watcher có công cụ **Next hop** để kiểm tra Azure sẽ chọn next hop nào cho lưu lượng xuất phát từ một VM tới địa chỉ IP đích. Khi điều tra, hãy chọn đúng VM/NIC, source IP và destination IP rồi so sánh với route bạn dự đoán.

Nếu route có vẻ đúng mà vẫn không kết nối được:

- Kiểm tra **Effective security rules** trên NIC/subnet; NSG có thể chặn.
- Kiểm tra firewall/NVA có rule cho phép và có bật forwarding không.
- Kiểm tra **đường phản hồi** của máy đích, gateway hoặc appliance.
- Kiểm tra DNS có phân giải sang đúng IP mong muốn không. DNS sai có thể khiến bạn đang chẩn đoán nhầm tuyến.
- Với VNet peering, xác nhận peering đã Connected và các tùy chọn forwarded traffic/gateway transit phù hợp.
- Với kết nối tại chỗ, kiểm tra BGP advertisements, route propagation, gateway và trạng thái VPN/ExpressRoute.

Đối với sự cố gián đoạn sau khi cập nhật UDR, ghi lại thời điểm thay đổi, route table, subnet, destination IP và kết quả trước/sau. Những bằng chứng này giúp khoanh vùng nguyên nhân mà không phải gỡ hàng loạt cấu hình.

## 11. Phân biệt UDR với NSG, DNS và firewall

| Thành phần | Câu hỏi chính mà nó giải quyết | Ví dụ |
|---|---|---|
| **Route / UDR** | Gói tin tới IP đích phải đi đâu tiếp? | Chuyển 0.0.0.0/0 qua firewall |
| **NSG** | Cho phép hay chặn lưu lượng theo quy tắc L3/L4? | Chặn TCP 22 từ Internet |
| **Azure Firewall/NVA** | Kiểm soát lưu lượng qua thiết bị chính sách tập trung | Ghi log và lọc egress |
| **DNS** | Tên miền phân giải thành địa chỉ IP nào? | app.internal.example → 10.20.1.10 |
| **NAT Gateway** | Dịch địa chỉ nguồn và cung cấp outbound connectivity theo mô hình dịch vụ | Ổn định địa chỉ IP outbound của subnet |

Một UDR có next hop **VirtualAppliance** không đồng nghĩa NVA tự động cho phép hoặc chặn nội dung lưu lượng. Nếu NVA chưa được cấu hình, đường đi có thể bị mất. Một UDR **None** loại bỏ gói khớp prefix được chọn, nhưng không diễn đạt chính sách ứng dụng theo tài khoản, URL hoặc port như một firewall.

### Lưu ý với Private Endpoint và các dịch vụ PaaS

Private Endpoint dùng địa chỉ IP riêng trong VNet và có các hành vi định tuyến đặc biệt tùy dịch vụ/cấu hình. Không nên mặc định rằng UDR 0.0.0.0/0 sẽ ép mọi luồng Private Endpoint đi qua NVA. Route cụ thể hơn có thể được ưu tiên; việc áp dụng route table cho subnet Private Endpoint và thay đổi chính sách mạng cần theo khả năng hỗ trợ của dịch vụ và cấu hình tương ứng.

Ngoài ra, endpoint dịch vụ, quản lý hạ tầng Azure và một số subnet đặc biệt (ví dụ GatewaySubnet) có các hạn chế hoặc ngoại lệ. Hãy kiểm tra tài liệu cho chính dịch vụ đang triển khai, đặc biệt khi thiết kế forced tunneling trên phạm vi rộng.

### Ảnh hưởng chi phí và vận hành

Tạo VNet và route table đơn giản thường không trực tiếp tạo lưu lượng tính phí, nhưng kiến trúc sử dụng **Azure Firewall, VPN Gateway, NAT Gateway, appliance VM, peering, lưu lượng ra Internet và giám sát** có thể phát sinh chi phí. UDR có thể khiến lưu lượng đi qua thêm thiết bị hoặc khu vực mạng, tạo độ trễ và chi phí truyền dữ liệu. Ước tính chi phí trước khi áp dụng ở quy mô lớn và theo dõi bằng Cost Management.

## 12. Bài thực hành: tạo UDR an toàn và quan sát cấu hình

Mục tiêu: tạo VNet riêng, một subnet, route table và tuyến **198.51.100.0/24 → None**, sau đó liên kết bảng định tuyến với subnet. Dải **198.51.100.0/24** thuộc địa chỉ dành cho tài liệu/ví dụ, nên thích hợp để minh họa mà không cần chạy máy ảo hoặc NVA.

**Đầu ra mong đợi:** thấy UDR trong route table, thấy route table gắn với subnet và giải thích được vì sao gói tới 198.51.100.10 chọn UDR /24 thay cho system route 0.0.0.0/0. Không cần tạo máy ảo để hoàn thành phần cấu hình này.

### Chuẩn bị

- Azure CLI đã đăng nhập và chọn đúng subscription dùng cho thực hành.
- Có quyền tạo resource group, VNet, subnet, route table và UDR.
- Region được chọn cho phép tạo các tài nguyên cơ bản này.
- Không dùng tên resource group/subnet của hệ thống đang vận hành để tránh ảnh hưởng người khác.

### Bước 1: tạo resource group riêng

~~~bash
az group create \
  --name rg-az-routing-lab \
  --location southeastasia \
  --tags environment=learning purpose=routing-lab
~~~

### Bước 2: tạo VNet và subnet thử nghiệm

~~~bash
az network vnet create \
  --resource-group rg-az-routing-lab \
  --name vnet-routing-lab \
  --location southeastasia \
  --address-prefixes 10.60.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.60.1.0/24
~~~

### Bước 3: tạo route table

~~~bash
az network route-table create \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --location southeastasia
~~~

### Bước 4: thêm UDR bỏ gói tới prefix minh họa

~~~bash
az network route-table route create \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --name drop-documentation-prefix \
  --address-prefix 198.51.100.0/24 \
  --next-hop-type None
~~~

**Giải thích:** nếu một VM có NIC trong subnet-app gửi gói đến 198.51.100.10, route /24 mới cụ thể hơn route Internet 0.0.0.0/0. Azure sẽ chọn next hop None và bỏ gói đó. Với một IP khác không khớp tuyến /24 và không có tuyến cụ thể hơn, hành vi vẫn dựa trên route nền tảng/những route có hiệu lực khác.

### Bước 5: liên kết route table với subnet

~~~bash
az network vnet subnet update \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --route-table rt-app-lab
~~~

### Bước 6: kiểm tra kết quả

~~~bash
az network route-table route list \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --output table

az network vnet subnet show \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --query "{subnet:name,routeTable:routeTable.id}" \
  --output json
~~~

Bạn cần thấy route **drop-documentation-prefix** với next hop **None**, và trường routeTable của **snet-app** trỏ đến **rt-app-lab**. Nếu muốn kiểm tra bằng công cụ Effective routes/Next hop, hãy sử dụng một VM thử nghiệm đã có hoặc VM chỉ được tạo trong phạm vi ngân sách cho phép. **Không bắt buộc tạo VM** cho bài này.

### Bước 7: dọn dẹp

Khi đã hoàn thành, xác nhận resource group chỉ chứa tài nguyên của bài lab và không có dữ liệu cần giữ, rồi xóa cả nhóm:

~~~bash
az group delete --name rg-az-routing-lab --yes
~~~

Kiểm tra nhóm còn tồn tại không:

~~~bash
az group exists --name rg-az-routing-lab
~~~

Giá trị **false** cho biết resource group đã biến mất khỏi ARM. Dữ liệu chi phí có thể cập nhật trễ, vì vậy vẫn nên kiểm tra Cost Management nếu có triển khai thêm tài nguyên tính phí.

### Kết quả cần ghi

| Hạng mục | Bằng chứng |
|---|---|
| Subscription/region | Tên subscription, subscription ID và region đã dùng |
| VNet | vnet-routing-lab: 10.60.0.0/16 |
| Subnet | snet-app: 10.60.1.0/24 |
| Route table | rt-app-lab |
| UDR | 198.51.100.0/24 → None |
| Association | snet-app gắn với rt-app-lab |
| Dọn dẹp | Kết quả xóa rg-az-routing-lab |

## 13. Tình huống lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy UDR trong effective routes | Table chưa liên kết subnet, kiểm tra nhầm NIC/subnet, hoặc route không hợp lệ | Xem subnet association, NIC, Source và State |
| Gói vẫn đi đến một IP dù có route None rộng | Tồn tại route cụ thể hơn tới IP đó | So sánh longest prefix; kiểm tra mọi route Active |
| Lưu lượng Internet ngừng sau khi đặt 0.0.0.0/0 → NVA | NVA chưa sẵn sàng, thiếu forwarding/SNAT/egress | Kiểm tra NVA, IP forwarding, đường đi và đường về |
| Lưu lượng đến mạng tại chỗ bị mất sau khi sửa table | Tắt BGP propagation hoặc UDR đã thay thế route gateway | Kiểm tra BGP, gateway, prefix và trạng thái |
| Traffic có route đúng nhưng vẫn timeout | NSG, firewall, ứng dụng đích hoặc đường về chặn | Kiểm tra Effective security rules, logs và reverse path |
| VNet peering hoạt động nhưng forwarded traffic không qua được | Chưa cho phép forwarded traffic hoặc topology/UDR chưa phù hợp | Kiểm tra tùy chọn peering ở hai chiều và cấu hình NVA |
| Sửa route table gây lỗi nhiều ứng dụng | Cùng route table gắn vào nhiều subnet | Liệt kê Subnets được associate trước mỗi lần thay đổi |
| Có route 0.0.0.0/0 → Internet nhưng VM không ra Internet | Thiếu cơ chế outbound connectivity hoặc bị NSG/firewall chặn | Kiểm tra NAT/outbound, NSG, IP và cấu hình dịch vụ |
| Khó xác định lỗi là DNS hay route | Hostname đang phân giải đến IP không mong đợi | Phân giải DNS trước, dùng IP đích thực tế để tra route |

Trong sự cố production, ưu tiên thu thập route table, effective routes, thời điểm thay đổi và kết quả Network Watcher trước khi sửa. Tránh xóa hoặc thay nhiều UDR cùng lúc vì sẽ khó xác định thay đổi nào gây ra hoặc giải quyết lỗi.

## 14. Câu hỏi tự kiểm tra

1. Vì sao NIC trong Azure có effective routes ngay cả khi subnet chưa được associate với một route table tự tạo?
2. Khi đích là 10.20.1.10, vì sao route system 10.20.0.0/16 có thể thắng route 10.0.0.0/8 → None?
3. Nếu system route và UDR cùng có prefix 0.0.0.0/0, Azure thường ưu tiên tuyến nào?
4. Một route BGP /24 và một UDR /16 cùng khớp IP đích. Tuyến nào được chọn và vì sao?
5. Tại sao gắn UDR 0.0.0.0/0 → VirtualAppliance chưa đủ để lưu lượng Internet hoạt động?
6. Khác biệt giữa route với next hop None và một quy tắc deny của NSG là gì?
7. Tắt BGP route propagation có thể ảnh hưởng thế nào đến kết nối on-premises?
8. Vì sao phải kiểm tra cả đường đi và đường về khi dùng stateful firewall?
9. Muốn xác định route đang được áp dụng cho một VM, nên xem route đã cấu hình hay effective routes của NIC?
10. DNS có quyết định next hop của gói tin sau khi hostname đã được phân giải không?

## 15. Tài liệu tham khảo

- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview) — system routes, UDR, BGP, next hop và quy tắc chọn tuyến.
- [Create, change, or delete an Azure route table](https://learn.microsoft.com/azure/virtual-network/manage-route-table) — tạo route table, liên kết subnet và quản lý UDR.
- [Azure CLI: az network route-table](https://learn.microsoft.com/cli/azure/network/route-table) — nhóm lệnh quản lý route table.
- [Azure CLI: az network route-table route](https://learn.microsoft.com/cli/azure/network/route-table/route) — thêm, xem và xóa từng route.
- [Network Watcher next hop](https://learn.microsoft.com/azure/network-watcher/next-hop-overview) — công cụ chẩn đoán lựa chọn next hop.
- [Diagnose a virtual machine routing problem](https://learn.microsoft.com/azure/virtual-network/diagnose-network-routing-problem) — chẩn đoán kết nối và effective routes.

Một thiết kế định tuyến đúng phải xác định được **IP đích, prefix khớp cụ thể nhất, next hop và đường phản hồi**. Khi dùng UDR để đưa lưu lượng qua firewall/gateway, hãy xác nhận hành vi trên NIC thực tế và phối hợp với NSG, DNS, routing của NVA, chính sách bảo mật cũng như chi phí vận hành.
