# Network interface và cấu hình IP cho workload

Một ứng dụng chạy trên Azure cần giao tiếp với cơ sở dữ liệu, dịch vụ nội bộ, Internet hoặc người dùng bên ngoài. Để lưu lượng đi đúng nơi và được kiểm soát, người vận hành phải hiểu **network interface (NIC)**, địa chỉ IP, subnet, định tuyến, DNS và các lớp bảo vệ mạng.

Trong module **CLOUD_PROVIDERS_AZURE**, bài học thuộc chương **Mạng ảo và phân giải tên**. Kiến thức này là nền tảng khi triển khai workload trên Azure Virtual Machines (VM), thiết kế mạng ứng dụng, kết nối tới dịch vụ lưu trữ và dữ liệu, kiểm tra bảo mật cũng như giám sát sự cố mạng. Trọng tâm là cấu hình NIC và IP cho workload, trước hết qua VM; một số dịch vụ PaaS sử dụng cơ chế kết nối khác nên không có NIC của VM để cấu hình trực tiếp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt VNet, subnet, NIC, IP configuration, private IP và public IP.
2. Hiểu cách Azure cấp phát IP động hoặc tĩnh và tại sao cấu hình IP trong Azure khác cấu hình trong hệ điều hành khách.
3. Tạo, kiểm tra và cập nhật NIC cùng IP configuration bằng Azure Portal hoặc Azure CLI.
4. Quyết định khi nào workload cần public IP, nhiều địa chỉ IP hoặc nhiều NIC.
5. Hiểu tác động của Network Security Group (NSG), route table, DNS và cấu hình mạng trong guest OS.
6. Chẩn đoán các vấn đề thường gặp và thực hiện thay đổi an toàn.

## 2. NIC nằm ở đâu trong mạng Azure?

**Azure Virtual Network (VNet)** là miền mạng logic riêng của workload. VNet được chia thành các **subnet**, mỗi subnet có dải IP riêng trong không gian địa chỉ của VNet. **NIC** là tài nguyên Azure nối máy ảo với một subnet, giữ các cấu hình IP và một số thuộc tính mạng của kết nối.

~~~
VNet: 10.20.0.0/16
  |
  +-- Subnet app: 10.20.1.0/24
  |      |
  |      +-- NIC web-nic
  |             |
  |             +-- ipconfig1: 10.20.1.10 (private IPv4)
  |             +-- Public IP: tùy nhu cầu
  |             |
  |             +-- VM web-01
  |
  +-- Subnet data: 10.20.2.0/24
         |
         +-- NIC db-nic
                |
                +-- ipconfig1: 10.20.2.10 (private IPv4)
                +-- VM db-01
~~~

Trong hình, VM web-01 và db-01 có private IP trên các subnet khác nhau của cùng VNet. Các tài nguyên có thể giao tiếp qua định tuyến nội bộ của Azure nếu không bị NSG, firewall, route hoặc chính sách mạng khác chặn.

**NIC không đồng nghĩa với VM.** NIC là tài nguyên mạng có vòng đời và cấu hình riêng, được gắn vào một VM phù hợp. Một VM có thể có nhiều NIC khi kích thước máy ảo và cách triển khai hỗ trợ. Một NIC không đồng thời được gắn cho nhiều VM.

| Thành phần | Trách nhiệm |
|---|---|
| VNet | Xác định không gian mạng riêng và khả năng kết nối |
| Subnet | Chia dải địa chỉ, làm phạm vi áp dụng nhiều cấu hình mạng |
| NIC | Kết nối VM với mạng, chứa IP configuration, NSG và các thiết lập phù hợp |
| IP configuration (ipconfig) | Mô tả private IP và tham chiếu public IP nếu có |
| Private IP | Địa chỉ giao tiếp trong VNet hoặc qua các mạng được kết nối |
| Public IP | Tài nguyên địa chỉ Internet được liên kết với endpoint tương ứng |
| NSG | Kiểm soát lưu lượng được phép theo quy tắc inbound/outbound |
| Route table | Điều khiển đường đi của gói tin ở mức subnet |
| DNS | Ánh xạ tên miền sang địa chỉ IP để workload tìm đúng đích |

## 3. IP configuration của một NIC

Mỗi NIC có ít nhất **một IP configuration**. Một IP configuration chứa các thông tin quan trọng:

- Tên cấu hình, ví dụ `ipconfig1`.
- Subnet và private IP được cấp trong phạm vi subnet đó.
- Phương thức cấp phát private IPv4: **Dynamic** hoặc **Static**.
- Phiên bản IP: IPv4 hoặc IPv6 nếu mạng và workload hỗ trợ.
- Tham chiếu tới một **public IP resource**, nếu cần gán public IP cho cấu hình.
- Thuộc tính đánh dấu **primary** khi NIC có nhiều IP configuration.

### Primary NIC khác primary IP configuration

Hai khái niệm thường bị nhầm:

- **Primary NIC**: card mạng chính của VM khi VM dùng nhiều NIC. VM có các giới hạn và quy tắc riêng cho primary NIC, phụ thuộc cách triển khai.
- **Primary IP configuration**: cấu hình IP chính bên trong một NIC. Khi NIC có nhiều cấu hình, một cấu hình được đánh dấu primary.

Một VM chỉ có một NIC vẫn có thể có nhiều IP configuration trên NIC đó. Ngược lại, một VM có nhiều NIC không có nghĩa mỗi NIC chứa nhiều địa chỉ IP. Việc thêm NIC còn phải đáp ứng giới hạn số NIC của kích thước VM và yêu cầu kết nối trong cùng VNet.

### Vì sao workload có nhiều địa chỉ IP?

Một số tình huống hợp lý:

- Máy chủ phục vụ nhiều endpoint hoặc địa chỉ dịch vụ.
- Ứng dụng cũ phụ thuộc địa chỉ IP riêng cho từng tiến trình.
- Thiết bị ảo mạng (network virtual appliance, NVA) cần nhiều interface để xử lý lưu lượng.
- Thiết kế cần tách lưu lượng quản trị và lưu lượng ứng dụng bằng nhiều subnet/NIC, khi được hỗ trợ.

Không nên tự động thêm NIC hoặc địa chỉ IP chỉ để “tăng tốc”. Nhiều NIC làm cấu hình route, firewall, IP trong guest OS và giám sát phức tạp hơn. Năng lực mạng còn phụ thuộc kích thước VM, nền tảng và tính năng như Accelerated Networking.

## 4. Private IPv4: Dynamic và Static

Private IP dùng cho lưu lượng nội bộ, không phải địa chỉ được định tuyến trực tiếp từ Internet công cộng. Với NIC, private IPv4 thường nằm trong dải địa chỉ của subnet mà NIC tham gia.

### Dynamic

Ở chế độ **Dynamic**, Azure chọn một địa chỉ còn khả dụng từ subnet. Đây là **cấp phát do Azure quản lý**, khác với việc tự đặt IP tùy ý trong hệ điều hành. Không nên dựa vào một địa chỉ Dynamic như một cam kết bất biến cho hệ thống cần địa chỉ cố định dài hạn.

### Static

Ở chế độ **Static**, người quản trị chọn một địa chỉ còn hợp lệ trong subnet và Azure giữ địa chỉ đó cho IP configuration cho tới khi thay đổi hoặc giải phóng cấu hình. Ví dụ, một workload có yêu cầu định tuyến nội bộ cố định có thể dùng `10.20.1.10` trong subnet `10.20.1.0/24`.

**Static private IP không phải địa chỉ public IP.** Tính “static” ở đây chỉ nói về cách cấp phát địa chỉ bên trong VNet.

### Các địa chỉ Azure dành riêng

Azure dành riêng **5 địa chỉ IPv4** trong mỗi subnet: bốn địa chỉ đầu và địa chỉ cuối. Với subnet `10.20.1.0/24`:

| Dải/địa chỉ | Ý nghĩa |
|---|---|
| `10.20.1.0` | Địa chỉ mạng, được Azure dành riêng |
| `10.20.1.1` | Gateway mặc định của subnet |
| `10.20.1.2` và `10.20.1.3` | Địa chỉ Azure dành riêng |
| `10.20.1.4` đến `10.20.1.254` | Dải địa chỉ thường có thể cấp cho tài nguyên |
| `10.20.1.255` | Địa chỉ cuối subnet, được Azure dành riêng |

Vì vậy, subnet `/24` có tối đa **251 địa chỉ IPv4 sử dụng được** theo quy tắc cấp phát của Azure. Số địa chỉ còn trống thực tế thấp hơn nếu đã có NIC, private endpoint hoặc tài nguyên khác dùng IP.

> Khi chọn static IP, cần kiểm tra subnet, các địa chỉ đã dùng và kế hoạch IP của toàn môi trường. Tránh “đoán” địa chỉ dựa trên tên máy hoặc chỉ kiểm tra bằng lệnh ping: một địa chỉ không trả lời ping vẫn có thể đã được cấp phát.

### Điểm quan trọng: private IP trong Azure và trong guest OS

Với cấu hình NIC IPv4 thông thường, **chọn Static tại Azure nhưng vẫn để địa chỉ IPv4 chính trong guest OS nhận qua DHCP**. Azure cấp đúng địa chỉ đã giữ trên NIC thông qua cơ chế mạng của nền tảng.

Không tự chuyển địa chỉ chính của VM sang cấu hình IP tĩnh trong Windows/Linux rồi cho rằng Azure đã biết thay đổi đó. Việc cấu hình lệch giữa guest OS và NIC có thể làm mất truy cập từ xa hoặc tạo lỗi khó chẩn đoán.

Khi gán **nhiều private IP trên cùng một NIC**, các địa chỉ phụ thường cần được cấu hình tương ứng trong guest OS theo hướng dẫn cho hệ điều hành. Azure quản lý IP configuration ở control plane; guest OS cần biết những địa chỉ mà ứng dụng sẽ thực sự dùng.

## 5. Public IP và kết nối Internet

Một VM có thể chỉ dùng private IP và vẫn kết nối đến tài nguyên nội bộ qua VNet, VNet peering, VPN hoặc ExpressRoute, tùy kiến trúc. VM **không bắt buộc có public IP** để trở thành thành phần của ứng dụng.

Khi cần truy cập từ Internet vào VM, có thể liên kết một tài nguyên **Public IP address** vào IP configuration của NIC. Tuy nhiên, có public IP không có nghĩa mọi cổng đều được mở; NSG và các kiểm soát an ninh vẫn quyết định lưu lượng nào được phép.

### Các lựa chọn phổ biến

| Mục tiêu | Cách kết nối nên cân nhắc |
|---|---|
| Quản trị VM mà không mở SSH/RDP ra Internet | Azure Bastion hoặc truy cập qua mạng riêng có kiểm soát |
| Web công khai với nhiều máy chủ | Azure Application Gateway, Azure Load Balancer hoặc dịch vụ frontend phù hợp |
| VM chỉ cần truy cập Internet từ bên trong | Thiết kế outbound rõ ràng như NAT Gateway tại subnet |
| Một VM thử nghiệm cần endpoint Internet | Standard public IP gắn NIC và NSG giới hạn IP nguồn/cổng |
| Ứng dụng chỉ phục vụ mạng nội bộ | Private IP, private DNS và tuyến kết nối riêng |

### Standard Public IP và phạm vi dùng

Với triển khai mới, ưu tiên **Standard SKU Public IP** khi cần public IP trực tiếp. Standard public IP sử dụng phân bổ tĩnh; địa chỉ được quản lý như một tài nguyên Azure riêng, không phải đặt trực tiếp trong hệ điều hành VM.

Các tài nguyên public IP có quy định về region, zone, SKU và khả năng kết hợp với tài nguyên đích. Trước khi tạo, cần xác nhận public IP tương thích với NIC, Load Balancer hoặc dịch vụ liên quan. Một public IP IPv4 không tự biến subnet IPv4 thành IPv6.

**Ingress** (lưu lượng đi vào ứng dụng) và **egress** (lưu lượng đi ra Internet) là hai bài toán khác nhau. NAT Gateway phục vụ outbound tại phạm vi subnet và không tự mở cổng inbound từ Internet đến từng VM. Không dựa vào outbound IP ngầm định của nền tảng khi hệ thống yêu cầu địa chỉ nguồn cố định hoặc cấu hình lâu dài.

## 6. IPv4, IPv6 và dual-stack

IPv4 là lựa chọn phổ biến cho nhiều workload Azure, nhưng một số kiến trúc hỗ trợ **dual-stack**, tức cùng mạng/workload có địa chỉ IPv4 và IPv6.

Khi thiết kế IPv6 cần xem xét đồng thời:

1. Không gian địa chỉ IPv6 của VNet và subnet.
2. Khả năng hỗ trợ IPv6 của loại VM, NIC, public IP và dịch vụ liên quan.
3. Network Security Group, firewall, route và DNS record `AAAA`.
4. Cách ứng dụng mở socket, ghi log, kiểm tra IP nguồn và ưu tiên giao thức.
5. Giới hạn và hành vi của thành phần ở giữa như load balancer, proxy hoặc kết nối hybrid.

Không giả định rằng mọi thao tác CLI hay dịch vụ hỗ trợ IPv6 giống IPv4. Với môi trường chủ yếu dùng IPv4, hãy hoàn thiện luồng IPv4 trước và kiểm thử dual-stack như một thay đổi kiến trúc riêng.

## 7. NSG, route và DNS ảnh hưởng NIC như thế nào?

NIC chứa IP configuration nhưng khả năng kết nối thực tế còn phụ thuộc **quyền đi qua mạng** và **đường đi của gói tin**.

### Network Security Group

NSG có thể được gắn tại **subnet** và/hoặc **NIC**. Các quy tắc inbound/outbound dùng địa chỉ nguồn, đích, cổng, giao thức và độ ưu tiên để cho phép hoặc từ chối lưu lượng.

Nếu cả subnet và NIC có NSG, lưu lượng phải đáp ứng các rule có hiệu lực ở các tầng áp dụng. NSG có tính **stateful**: khi một luồng được cho phép, lưu lượng phản hồi của luồng đó được xử lý tương ứng; điều này không có nghĩa mọi kết nối mới theo chiều ngược lại đều được phép.

Ví dụ, một VM có public IP gắn NIC nhưng NSG không cho phép TCP/22 từ mạng quản trị thì không thể SSH trực tiếp từ Internet qua cổng đó. Không mở `0.0.0.0/0` vào SSH/RDP chỉ để kiểm tra kết nối nếu có phương án truy cập quản trị an toàn hơn.

Có thể xem **effective security rules** trong Azure Portal hoặc bằng công cụ mạng khi NIC được gắn với một VM phù hợp.

### Route table và next hop

Subnet có system routes của Azure và có thể có **user-defined routes (UDR)** để chuyển một số lưu lượng qua firewall hoặc NVA. Kết quả là dù IP đích nằm trong dải bạn mong đợi, gói tin vẫn có thể đi theo tuyến khác.

Các lỗi định tuyến thường gặp: tuyến `0.0.0.0/0` gửi toàn bộ lưu lượng qua firewall chưa cho phép, mạng nguồn và đích dùng CIDR chồng lấn, thiếu route hồi đáp hoặc NVA không chuyển tiếp gói tin.

### DNS

DNS giúp ứng dụng tìm dịch vụ qua tên thay vì hard-code IP. Một VNet có thể dùng DNS do Azure cung cấp hoặc DNS server tùy chỉnh. Azure cũng cho phép cấu hình DNS server ở cấp NIC trong các trường hợp hỗ trợ.

Nếu sử dụng DNS server riêng, cần bảo đảm đường mạng và NSG cho phép VM truy cập resolver đó. Thay đổi DNS ở VNet/NIC có thể cần gia hạn DHCP lease, làm mới cấu hình mạng hoặc khởi động lại VM tùy tình huống để guest OS nhận thiết lập mới.

**DNS không cấp IP cho NIC.** DNS giải tên; Azure control plane quản lý IP configuration; DHCP giúp guest OS nhận cấu hình IP chính.

## 8. Thực hành đọc và tạo NIC bằng Azure CLI

Các lệnh dưới đây giả định bạn có quyền tại subscription thử nghiệm và đã chuẩn bị **VNet, subnet** hợp lệ. Thay các tên ví dụ theo môi trường thực tế. Bài thực hành dùng Bash hoặc Azure Cloud Shell ở chế độ Bash.

Đầu tiên xác nhận subscription để tránh thao tác nhầm môi trường:

~~~bash
az account show --query "{subscription:name, id:id, tenant:tenantId}" -o table
~~~

Khai báo biến ví dụ:

~~~bash
RG="rg-network-lab"
VNET="vnet-lab"
SUBNET="snet-app"
NIC="nic-app-01"
IP="10.20.1.10"
~~~

Ví dụ giả sử `snet-app` thuộc `vnet-lab`, có prefix `10.20.1.0/24` và địa chỉ `10.20.1.10` còn trống. **Đây là thông số minh họa; không thực thi lệnh tạo tài nguyên nếu chưa xác nhận chúng tồn tại và không trùng với môi trường khác.**

### Bước 1: kiểm tra subnet

~~~bash
az network vnet subnet show \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$SUBNET" \
  --query "{id:id,prefix:addressPrefix,prefixes:addressPrefixes}" \
  -o json
~~~

Một subnet có thể trả về `addressPrefix` hoặc `addressPrefixes` tùy cấu hình và mô hình dữ liệu. Xác nhận private IP dự kiến nằm trong prefix IPv4 thích hợp, không thuộc các địa chỉ Azure dành riêng và chưa bị tài nguyên khác sử dụng.

### Bước 2: tạo NIC với private IP tĩnh

~~~bash
az network nic create \
  --resource-group "$RG" \
  --name "$NIC" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET" \
  --private-ip-address "$IP"
~~~

Tùy chọn `--private-ip-address` chọn private IPv4 cụ thể cho NIC; Azure sẽ kiểm tra tính hợp lệ và khả dụng khi tạo. Nếu muốn Azure tự cấp phát, bỏ tùy chọn này để sử dụng cơ chế Dynamic mặc định trong trường hợp thông thường.

### Bước 3: xác nhận IP configuration

~~~bash
az network nic show \
  --resource-group "$RG" \
  --name "$NIC" \
  --query "{name:name,vm:virtualMachine.id,ipConfigs:ipConfigurations[].{name:name,privateIp:privateIPAddress,allocation:privateIPAllocationMethod,primary:primary}}" \
  -o json
~~~

Kết quả phải cho thấy private IP và allocation method tương ứng. Nếu trường `virtualMachine` là `null`, NIC chưa được gắn vào VM. Một NIC tồn tại chưa chứng minh rằng workload bên trong VM đã hoạt động.

Xem chi tiết cấu hình chính:

~~~bash
az network nic ip-config show \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  -o json
~~~

Tên mặc định thường là `ipconfig1` với NIC tạo bằng Azure CLI; nếu tên thực tế khác, lấy từ danh sách IP configuration rồi thay cho phù hợp.

### Bước 4: cập nhật private IP khi có kế hoạch thay đổi

Ví dụ muốn chuyển địa chỉ sang `10.20.1.12` (sau khi đã xác nhận địa chỉ khả dụng):

~~~bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  --private-ip-address "10.20.1.12"
~~~

Thay IP của NIC đang phục vụ traffic có thể làm rớt kết nối, khiến DNS/allowlist lỗi và yêu cầu cập nhật ứng dụng phụ thuộc. Một số thay đổi kết nối NIC cần dừng và deallocate VM tùy thao tác; hãy kiểm tra yêu cầu cụ thể, chuẩn bị cửa sổ bảo trì và đường quản trị dự phòng trước khi thực hiện.

## 9. Gắn Public IP khi workload thực sự cần

Khi có yêu cầu hợp lệ cho kết nối Internet vào VM, tạo tài nguyên Standard Public IP:

~~~bash
PIP="pip-app-01"

az network public-ip create \
  --resource-group "$RG" \
  --name "$PIP" \
  --sku Standard \
  --allocation-method Static
~~~

Liên kết public IP vào một IP configuration của NIC:

~~~bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  --public-ip-address "$PIP"
~~~

Kiểm tra địa chỉ được cấp:

~~~bash
az network public-ip show \
  --resource-group "$RG" \
  --name "$PIP" \
  --query "{address:ipAddress,sku:sku.name,allocation:publicIPAllocationMethod}" \
  -o json
~~~

Để người dùng thực sự kết nối, cần kiểm tra tiếp: VM đã gắn NIC và đang chạy, NSG cho phép cổng ứng dụng từ nguồn phù hợp, firewall bên trong OS cho phép, tiến trình lắng nghe đúng interface và route hoạt động.

**Public IP có thể phát sinh chi phí ngay cả khi workload không nhận nhiều traffic.** Trong bài lab, phải kiểm tra tài nguyên còn tồn tại sau khi hoàn tất và xóa khi không còn cần thiết theo quyền cùng quy trình của môi trường.

Nếu chỉ muốn dịch vụ web được truy cập công khai, hãy cân nhắc Application Gateway hoặc Load Balancer có public frontend để che giấu từng VM phía sau và kiểm soát lưu lượng tập trung.

## 10. Nhiều IP configuration và nhiều NIC

### Thêm private IP thứ hai vào cùng NIC

Trong môi trường thử nghiệm và sau khi bảo đảm `10.20.1.11` còn trống:

~~~bash
az network nic ip-config create \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig-secondary" \
  --private-ip-address "10.20.1.11"
~~~

Xem cả hai IP configuration:

~~~bash
az network nic show \
  --resource-group "$RG" \
  --name "$NIC" \
  --query "ipConfigurations[].{name:name,privateIp:privateIPAddress,primary:primary}" \
  -o table
~~~

Trong guest OS, địa chỉ private IPv4 phụ thường phải được cấu hình trên interface theo tài liệu Azure và hệ điều hành. Nếu chỉ thêm ở Azure Portal/CLI mà không cấu hình tương ứng trong guest, ứng dụng có thể không bind hoặc không phản hồi ở địa chỉ phụ.

### Khi nào cần nhiều NIC?

Một VM có thể dùng nhiều NIC nếu kích thước VM hỗ trợ. Mỗi NIC có thể nối tới subnet phù hợp trong **cùng một VNet** của VM; các NIC có thể nối các subnet khác nhau trong VNet đó. Các kịch bản thường gặp gồm NVA, firewall ảo hoặc máy chủ có yêu cầu phân tách luồng mạng.

Với nhiều NIC, guest OS cần cấu hình đúng interface, route và default gateway. Đặt nhiều default route không chủ đích dễ gây **asymmetric routing**: lưu lượng đi vào một NIC nhưng phản hồi qua NIC khác, khiến firewall hoặc thiết bị trung gian loại bỏ gói tin.

### IP forwarding

Azure NIC có tùy chọn **IP forwarding** cho trường hợp VM phải nhận hoặc gửi lưu lượng không có địa chỉ đích/nguồn là IP của chính NIC, ví dụ NVA chuyển tiếp traffic. Khi bật IP forwarding ở Azure NIC, vẫn phải cấu hình forwarding/routing trong guest OS và kiểm soát bằng NSG, route table cùng firewall.

**Không cần bật IP forwarding cho VM ứng dụng thông thường** chỉ để nó gọi API hoặc giao tiếp tới database.

### Accelerated Networking

Accelerated Networking có thể giảm độ trễ và chi phí xử lý mạng trên những loại VM, hệ điều hành và image được hỗ trợ. Việc có thể bật hay không phụ thuộc môi trường triển khai, và đây là tính năng hiệu năng, không thay thế thiết kế subnet/IP hoặc chính sách an ninh.

## 11. Cấu hình mạng bên trong guest OS

Azure quản lý cấu hình tại control plane; Windows hoặc Linux trong VM vẫn phải có một **interface thực sự hoạt động** và nhận thông tin IP, route, DNS phù hợp.

### Linux

Các lệnh kiểm tra thường dùng:

~~~bash
ip -br address
ip route
ip route get 10.20.2.10
resolvectl status
~~~

`ip -br address` hiển thị IPv4/IPv6 trên interface; `ip route` xem bảng định tuyến; `ip route get` giúp quan sát đường đi dự kiến đến đích. `resolvectl` chỉ có trên hệ thống dùng trình phân giải hỗ trợ lệnh đó; trên image khác có thể kiểm tra cấu hình DNS bằng công cụ tương ứng.

### Windows

Trong PowerShell:

~~~powershell
Get-NetIPConfiguration
Get-NetIPAddress -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv4
Get-DnsClientServerAddress
~~~

Đây là các lệnh đọc trạng thái. Không vội sửa địa chỉ chính bằng `netsh`, `ip addr add` hoặc cấu hình network manager để “khớp Azure”: trước tiên phải xác nhận cấu hình ở NIC và cơ chế DHCP do Azure cung cấp. Với IP phụ, làm theo hướng dẫn cấu hình địa chỉ phụ của hệ điều hành và kiểm tra ảnh hưởng đến route.

## 12. Chẩn đoán mất kết nối theo từng lớp

Khi VM không kết nối được tới workload khác, nên điều tra theo thứ tự có khả năng cô lập nguyên nhân:

1. **Azure scope:** xác nhận subscription, resource group, VNet, subnet, NIC, VM và region.
2. **NIC/IP configuration:** kiểm tra private IP, public IP association, primary/secondary và attachment vào VM.
3. **Guest OS:** xác nhận interface có đúng IP, mask, route và DNS; ứng dụng có lắng nghe đúng địa chỉ/cổng không.
4. **NSG:** kiểm tra cả rule ở subnet và NIC; xem effective security rules nếu phù hợp.
5. **Routing:** kiểm tra system routes, UDR, next hop, VNet peering, VPN, firewall và route hồi đáp.
6. **DNS:** phân biệt lỗi không phân giải tên với lỗi kết nối tới IP đã biết.
7. **Ứng dụng và dịch vụ đích:** kiểm tra firewall bên trong VM, trạng thái dịch vụ, TLS, authentication và log.

### Công cụ Azure Network Watcher

Azure Network Watcher hỗ trợ các chức năng tùy môi trường, như:

- **IP flow verify:** kiểm tra theo rule NSG xem một luồng giả định được phép hay bị chặn.
- **Next hop:** kiểm tra next hop của luồng mạng.
- **Connection troubleshoot:** giúp kiểm tra khả năng kết nối tới đích và thông tin chẩn đoán.
- **Effective security rules/effective routes:** xem các quy tắc và tuyến có hiệu lực với NIC khi VM và vùng hỗ trợ.

Kết quả của một công cụ không tự xác nhận toàn bộ chuỗi ứng dụng. Ví dụ, NSG cho phép TCP/443 nhưng web server không lắng nghe hoặc firewall OS chặn thì truy cập vẫn thất bại.

### Bảng triệu chứng

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| VM không có IP như dự kiến | NIC chọn Dynamic, static IP sai subnet hoặc guest OS cấu hình lệch | IP configuration ở Azure và thông tin DHCP trong guest |
| Không SSH/RDP được dù có public IP | NSG, firewall OS, route, VM không chạy hoặc dịch vụ không lắng nghe | Port, rule inbound, nguồn truy cập và trạng thái VM |
| Ping không trả lời | ICMP bị chặn hoặc đích không phản hồi | Kiểm tra kết nối TCP phù hợp thay vì chỉ dựa vào ping |
| Không kết nối được database theo hostname | DNS sai, thiếu private DNS link hoặc tên trỏ sai IP | Tra cứu DNS và so với private IP đích |
| Kết nối được IP nhưng không kết nối được tên | DNS phân giải sai hoặc ứng dụng dùng bản ghi cache cũ | Resolver, TTL, record A/AAAA và cache |
| VM có nhiều NIC nhưng lưu lượng trả về đi sai | Default route hoặc UDR tạo đường bất đối xứng | Guest route, next hop và route hồi đáp |
| IP phụ hoạt động từ Azure nhưng ứng dụng không nghe | Chưa cấu hình IP phụ trong guest hoặc ứng dụng chỉ bind vào IP chính | Guest interface và socket binding |
| VM chỉ cần outbound nhưng thiếu Internet | Chưa có thiết kế egress rõ ràng, UDR/firewall/NSG chặn | NAT Gateway, route mặc định và outbound rules |

## 13. Thiết kế một workload web–data an toàn

Giả sử ứng dụng có hai tầng:

- **Web VM** trong subnet `10.20.1.0/24`, private IP `10.20.1.10`.
- **Database VM** trong subnet `10.20.2.0/24`, private IP `10.20.2.10`.

Yêu cầu: người dùng có thể truy cập web; database không được mở public IP; web chỉ được kết nối database qua cổng cần thiết.

Một phương án:

~~~mermaid
flowchart TD
  U[Người dùng Internet] --> F[Public frontend hoặc application gateway]
  F --> W[Web VM / NIC 10.20.1.10]
  W -->|Cổng DB được cho phép| D[DB VM / NIC 10.20.2.10]
  W --> N[NAT Gateway hoặc đường egress được kiểm soát]
  D --> P[Private DNS và dịch vụ nội bộ]
~~~

Các quyết định chính:

- Web VM có private IP tĩnh nếu cấu hình hoặc tích hợp yêu cầu địa chỉ cố định; frontend public nên được quản lý tại lớp ingress phù hợp.
- Database chỉ dùng private IP, không gắn public IP trực tiếp.
- NSG tại subnet hoặc NIC chỉ cho phép cổng ứng dụng cần thiết; ưu tiên tham chiếu nhóm ứng dụng hoặc phạm vi mạng được phê duyệt.
- DNS nội bộ trỏ tên database tới private IP hoặc endpoint riêng theo kiến trúc, tránh hard-code IP khi không cần thiết.
- Workload có nhu cầu gọi dịch vụ ngoài Internet sử dụng đường outbound được quản trị, ví dụ NAT Gateway, cùng logging và firewall phù hợp.
- Khi thay địa chỉ database hoặc di chuyển workload, cập nhật DNS, cấu hình client và kiểm tra kết nối, thay vì chỉ đổi IP ở Azure.

Thiết kế này thể hiện vai trò của NIC trong một kiến trúc lớn hơn: NIC cấp địa chỉ và điểm kết nối cho VM; **bảo mật và tính sẵn sàng** còn do subnet, NSG, routing, DNS, frontend và bản thân ứng dụng quyết định.

## 14. Checklist thay đổi IP trong môi trường đang vận hành

Một thay đổi nhỏ ở IP configuration có thể ảnh hưởng nhiều hệ thống. Trước khi thay đổi, ghi rõ:

- NIC và IP configuration nào chịu tác động; subscription/resource group/region nào đang được sử dụng.
- IP mới có nằm trong subnet, không thuộc địa chỉ dành riêng và chưa cấp phát cho tài nguyên khác không.
- Ứng dụng, DNS, NSG, route, load balancer, allowlist, monitoring hoặc bên thứ ba nào đang tham chiếu IP cũ.
- Thay đổi có yêu cầu dừng/deallocate VM hay làm mới guest OS không.
- Cách quan sát kết nối trước/sau, tiêu chí thành công và thời điểm triển khai.
- Kế hoạch khôi phục bằng IP/cấu hình ban đầu và quyền thao tác cần thiết.
- Người chịu trách nhiệm thông báo, kiểm thử, cập nhật hồ sơ IPAM và dọn tài nguyên thử nghiệm.

Sau khi thực hiện, xác nhận cả ba cấp: **Azure NIC/IP**, **guest OS**, **kết nối ứng dụng thực tế**. Một lệnh cập nhật thành công ở Azure không đồng nghĩa tất cả client đã chuyển sang IP mới.

## 15. Bài thực hành và câu hỏi tự kiểm tra

### Tình huống

Bạn cần chuẩn bị NIC cho một VM ứng dụng trong VNet `10.20.0.0/16`, subnet `10.20.1.0/24`, với private IP `10.20.1.10`. Workload kết nối tới database nội bộ ở `10.20.2.10` và không cần inbound public IP.

**Nhiệm vụ:**

1. Giải thích tại sao địa chỉ `10.20.1.1` không hợp lệ để tự gán cho NIC này.
2. Tạo NIC với private IP `10.20.1.10` bằng Azure CLI, sau khi xác nhận subnet và địa chỉ còn trống.
3. Dùng `az network nic show` xác nhận IP allocation method và tên IP configuration.
4. Giải thích vì sao VM nên tiếp tục nhận địa chỉ IPv4 chính bằng DHCP dù NIC được đặt Static trong Azure.
5. Mô tả các rule NSG tối thiểu để web VM kết nối tới database theo cổng ứng dụng đã được phê duyệt.
6. Liệt kê thao tác kiểm tra nếu VM không phân giải được tên database nhưng truy cập bằng IP vẫn hoạt động.
7. Đề xuất cách cấp outbound Internet nếu workload cần cập nhật gói mà vẫn không có public IP trực tiếp.
8. Mô tả tác động và kế hoạch kiểm thử nếu private IP thay đổi từ `10.20.1.10` sang `10.20.1.12`.

### Câu hỏi tự kiểm tra

**Câu 1.** Một NIC có thể chứa bao nhiêu IP configuration? Việc có hai private IP trên Azure có bảo đảm guest OS tự sử dụng được cả hai không?

**Câu 2.** Static private IP khác Standard public IP ở điểm nào về phạm vi sử dụng và chức năng?

**Câu 3.** Vì sao không nên gắn public IP trực tiếp cho mọi VM production?

**Câu 4.** Khi NSG cho phép traffic nhưng workload vẫn không truy cập được, bạn sẽ kiểm tra các lớp nào tiếp theo?

**Câu 5.** Với VM có nhiều NIC, lỗi định tuyến bất đối xứng có thể xuất hiện từ cấu hình nào?

**Tiêu chí hoàn thành:** bạn có thể mô tả vai trò của NIC và IP configuration, tạo/đọc được cấu hình NIC bằng Azure CLI, chọn Dynamic hoặc Static hợp lý, phân biệt public/private IP và điều tra kết nối từ Azure control plane tới guest OS.

## Kết luận

Network interface là điểm kết nối mạng của VM trên Azure; IP configuration quyết định địa chỉ private, phương thức cấp phát và liên kết public IP khi cần. Một cấu hình đúng phải đồng bộ với subnet, routing, NSG, DNS và trạng thái mạng trong guest OS. Khi hiểu rõ sự khác biệt giữa **Static tại Azure** và **DHCP trong VM**, cũng như giữa **IP có thể truy cập** và **traffic thực sự được phép**, bạn sẽ triển khai workload ổn định hơn và giảm nguy cơ gián đoạn khi vận hành mạng Azure.

