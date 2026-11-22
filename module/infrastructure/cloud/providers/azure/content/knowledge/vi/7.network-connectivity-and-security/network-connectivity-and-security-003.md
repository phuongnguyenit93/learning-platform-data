# Kết hợp ExpressRoute và VPN cho dự phòng

Một ứng dụng trên Microsoft Azure có thể cần trao đổi dữ liệu liên tục với trung tâm dữ liệu doanh nghiệp: truy vấn cơ sở dữ liệu nội bộ, đồng bộ danh tính, gửi giao dịch tới hệ thống ERP hoặc sử dụng các dịch vụ vẫn đặt tại chỗ (on-premises). Nếu toàn bộ lưu lượng phụ thuộc vào một kết nối WAN, sự cố nhà mạng, thiết bị mạng hoặc cấu hình định tuyến có thể làm gián đoạn ứng dụng dù các tài nguyên Azure vẫn hoạt động bình thường.

**ExpressRoute** cung cấp kết nối riêng từ mạng doanh nghiệp đến mạng Microsoft thông qua nhà cung cấp kết nối. **Site-to-Site VPN (S2S VPN)** thiết lập đường hầm IPsec/IKE qua Internet công cộng. Khi cùng kết nối một mạng on-premises tới Azure Virtual Network (VNet) bằng cả hai phương thức, doanh nghiệp có thể ưu tiên ExpressRoute để vận hành hằng ngày và duy trì VPN làm đường dự phòng khi đường chính không còn hoạt động.

Trong mô-đun CLOUD_PROVIDERS_AZURE, kiến trúc này liên hệ trực tiếp đến subscription, resource group, mạng ảo, VPN Gateway, ExpressRoute Gateway, Azure Monitor, quyền quản trị và chi phí. Điểm quan trọng nhất của bài học là **tính sẵn sàng phụ thuộc vào cả hai đầu đường truyền và chính sách định tuyến**, không chỉ vào việc hai kết nối đều đang ở trạng thái Connected.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của ExpressRoute và VPN trong thiết kế kết nối hybrid có dự phòng.
2. Nhận diện các thành phần: ExpressRoute circuit, private peering, ExpressRoute virtual network gateway, VPN gateway, local network gateway và BGP.
3. Thiết kế VNet có đồng thời ExpressRoute Gateway và route-based VPN Gateway theo điều kiện hỗ trợ của Azure.
4. Mô tả lựa chọn đường đi, chuyển sang VPN khi ExpressRoute gặp sự cố và chuyển về đường chính sau khi khôi phục.
5. Xây dựng checklist giám sát, diễn tập failover và khắc phục lỗi định tuyến bất đối xứng.
6. Đánh giá yêu cầu mã hóa, phân tách mạng, giới hạn dịch vụ và chi phí của đường dự phòng.

Kiến thức nền nên có: địa chỉ IP/CIDR, route table, Azure Virtual Network, subnet, Azure VPN Gateway, Azure RBAC và cách đọc trạng thái tài nguyên trên Azure Portal hoặc Azure CLI.

## 2. So sánh ExpressRoute và Site-to-Site VPN

| Tiêu chí | ExpressRoute | Site-to-Site VPN |
|---|---|---|
| Đường truyền | Kết nối riêng qua nhà cung cấp hoặc vị trí peering của Microsoft | Đường hầm IPsec/IKE trên Internet |
| Đặc điểm lưu lượng | Không đi qua Internet công cộng theo tuyến ExpressRoute thông thường | Gói tin đi qua Internet nhưng nội dung đường hầm được bảo vệ bằng IPsec |
| Mã hóa | Không tự động mã hóa đầu cuối chỉ vì dùng ExpressRoute | Đường hầm VPN dùng mã hóa IPsec/IKE khi cấu hình đúng |
| Năng lực | Nhiều lựa chọn băng thông, tùy circuit, gateway và provider | Phụ thuộc VPN Gateway SKU, thiết bị, đường Internet và cấu hình IPsec |
| Độ trễ | Thường ổn định hơn nhờ kết nối riêng, vẫn phụ thuộc nhà cung cấp và tuyến thực tế | Có thể biến động theo đường Internet |
| Công nghệ định tuyến | BGP trên private peering, kết nối circuit với VNet gateway | Có thể sử dụng BGP trong cấu hình hỗ trợ; có các hình thức cấu hình tuyến khác |
| Vai trò trong kiến trúc này | Đường chính cho lưu lượng hybrid | Đường dự phòng khi tuyến ExpressRoute bị rút hoặc không khả dụng |
| Chi phí | Circuit, provider, gateway và lưu lượng theo mô hình giá liên quan | VPN Gateway, IP công cộng, Internet/transit và lưu lượng phát sinh |
| Đối tượng phù hợp | Workload yêu cầu kết nối riêng và ổn định | Mở rộng kết nối nhanh, dự phòng hoặc kết nối địa điểm chưa có circuit |

**ExpressRoute không mặc nhiên là đường truyền đã được mã hóa.** Dù dùng mạng riêng, dữ liệu nhạy cảm vẫn nên dùng TLS hoặc giải pháp mã hóa theo yêu cầu bảo mật. Site-to-Site VPN mã hóa luồng qua Internet; điều này không làm cho Internet trở thành đường truyền có SLA hoặc độ ổn định giống kết nối riêng.

ExpressRoute circuit vốn có cơ chế kết nối vật lý dự phòng ở phía Microsoft và nhà cung cấp theo mô hình dịch vụ. Tuy nhiên, dự phòng bên trong cùng một circuit không loại bỏ mọi điểm lỗi chung như cùng tòa nhà kết nối, thiết bị CPE, nhà cung cấp hoặc sự cố cấu hình định tuyến. VPN dự phòng có giá trị nhất khi đường Internet và thiết bị triển khai của nó được thiết kế giảm phụ thuộc chung với ExpressRoute.

## 3. Kiến trúc kết hợp trong một Azure Virtual Network

### 3.1. Mô hình kết nối

Giả sử doanh nghiệp có trung tâm dữ liệu nội bộ sử dụng mạng 172.20.0.0/16 và VNet hub trên Azure dùng 10.40.0.0/16. Mô hình logic:

~~~mermaid
flowchart LR
    D["On-premises DC\n172.20.0.0/16"] --> R["Router/Firewall\ncủa doanh nghiệp"]
    R -->|Nhà cung cấp kết nối riêng| C["ExpressRoute circuit\nPrivate Peering"]
    C --> EG["ExpressRoute Gateway"]
    R -->|Internet + IPsec/IKE| V["VPN Site-to-Site"]
    V --> VG["VPN Gateway"]
    subgraph A["Azure: Hub VNet 10.40.0.0/16"]
      EG --> H["Hub network / shared services"]
      VG --> H
      H --> S["Ứng dụng, dịch vụ dữ liệu,\nworkload hợp lệ"]
    end
~~~

Trong mô hình này:

- ExpressRoute circuit và private peering tạo đường kết nối riêng từ mạng doanh nghiệp tới Microsoft.
- **ExpressRoute virtual network gateway** kết nối VNet với circuit.
- **Route-based VPN Gateway** thiết lập đường hầm tới thiết bị VPN on-premises qua Internet.
- Hai loại gateway phục vụ hai kiểu kết nối riêng biệt nhưng cùng đưa lưu lượng đến mạng VNet khi cấu hình coexistence được hỗ trợ.
- BGP và chính sách route ở hai phía quyết định đường chính và cách chuyển tuyến.

Sơ đồ là mô hình logic. Trên Azure, ExpressRoute Gateway và VPN Gateway được triển khai là hai gateway khác loại. Không cấu hình một gateway có thể tự đổi kiểu giữa ExpressRoute và VPN.

### 3.2. Các thành phần bắt buộc và chức năng

| Thành phần | Chức năng |
|---|---|
| Hub VNet | Mạng ảo Azure kết nối về doanh nghiệp; có thể làm trung tâm kết nối tới workload khác |
| GatewaySubnet | Subnet dành riêng cho các virtual network gateway trong VNet |
| ExpressRoute circuit | Circuit được nhà cung cấp và Microsoft cấp phát, liên kết với private peering |
| ExpressRoute Gateway | Điểm kết nối giữa VNet và ExpressRoute circuit |
| VPN Gateway | Gateway cho kết nối Site-to-Site dùng IPsec/IKE |
| Local Network Gateway | Đối tượng Azure mô tả địa chỉ public, BGP peer và/hoặc tiền tố mạng phía on-premises |
| VPN connection | Cấu hình kết nối giữa Azure VPN Gateway và site nội bộ |
| Customer Edge router/firewall | Thiết bị on-premises, quản lý BGP, IPsec, route policy và khả năng chuyển mạch |
| Azure Monitor/Network Watcher | Theo dõi tình trạng gateway, circuit, tuyến và kết nối ứng dụng |

Các dịch vụ Azure thường chịu sự khác biệt về region, SKU, loại gateway và giới hạn coexistence. Vì vậy, phải kiểm tra tài liệu hỗ trợ và quota của **đúng subscription, vùng và SKU** trước khi triển khai. Không suy ra mọi tổ hợp SKU đều hỗ trợ chạy đồng thời ExpressRoute và VPN.

### 3.3. Quy hoạch địa chỉ IP

Ví dụ phân hoạch hợp lệ:

| Phạm vi | Dải CIDR minh họa | Mục đích |
|---|---|---|
| On-premises | 172.20.0.0/16 | Mạng doanh nghiệp |
| Azure hub VNet | 10.40.0.0/16 | Kết nối hybrid và dịch vụ chia sẻ |
| GatewaySubnet trong hub | 10.40.255.0/26 | Subnet cho gateway theo thiết kế |
| Workload subnet trong hub | 10.40.10.0/24 | Ứng dụng/dịch vụ đặt ở hub nếu cần |
| Azure spoke VNet (tùy chọn) | 10.41.0.0/16 | Một workload được peering với hub |

Điều kiện quan trọng là **không chồng lấn dải địa chỉ** giữa các mạng cần định tuyến với nhau. Nếu hệ thống đang có CIDR trùng nhau, phải thiết kế lại địa chỉ hoặc xem xét cơ chế NAT được sản phẩm hỗ trợ; NAT không nên là biện pháp chữa cháy thiếu kiểm soát vì làm phức tạp truy vết và chuyển tuyến.

GatewaySubnet cần đủ không gian địa chỉ cho các gateway đang dùng và nhu cầu mở rộng. Ví dụ /26 ở trên là lựa chọn quy hoạch minh họa, không thay thế yêu cầu subnet tối thiểu của từng SKU và tính năng. Nếu GatewaySubnet đã tồn tại với kích thước nhỏ, phải đánh giá tác động trước khi mở rộng hoặc triển khai gateway bổ sung.

Nếu dùng mô hình hub-spoke và gateway transit qua VNet peering, hãy kiểm tra cấu hình Allow gateway transit/Use remote gateways và ràng buộc của các mạng peered. Spoke không mặc nhiên nhìn thấy mọi route on-premises chỉ vì đã peering với hub; cần xác minh route propagation, UDR và cả tuyến quay về.

## 4. Điều kiện để ExpressRoute và VPN dự phòng cho nhau

### 4.1. Điều kiện về gateway

Thiết kế kết hợp thông thường cần:

1. ExpressRoute circuit đã được provisioning thành công và private peering có cấu hình định tuyến phù hợp.
2. Azure VNet dùng ExpressRoute Gateway hỗ trợ kết nối circuit.
3. VPN Gateway là loại **route-based**, thuộc SKU và cấu hình được Azure hỗ trợ cho coexistence.
4. Có GatewaySubnet đủ lớn và địa chỉ IP/public IP cho VPN Gateway theo yêu cầu SKU.
5. On-premises có thiết bị VPN tương thích IPsec/IKE và có đường Internet riêng hoặc khả năng sử dụng Internet khi đường ExpressRoute gián đoạn.
6. Các phạm vi route, BGP ASN, BGP peering IP và các chính sách trên router đã được thiết kế đồng bộ.

Khi cần dự phòng tốt hơn ở phía VPN, có thể triển khai mô hình **active-active VPN Gateway** và nhiều thiết bị/tunnel ở on-premises nếu SKU, thiết bị và kịch bản phù hợp. Active-active chủ yếu tăng khả năng chịu lỗi của đường VPN; nó không biến VPN thành đường truyền riêng và không bảo đảm failover ứng dụng nếu tuyến quảng bá sai.

**Không dùng một VPN Gateway policy-based cho ví dụ này.** Kịch bản kết hợp ExpressRoute với VPN và tự động chuyển tuyến nhờ BGP cần thiết kế route-based và xác thực khả năng hỗ trợ của SKU.

### 4.2. Hai đường truyền nên độc lập nhất có thể

Mục tiêu có đường dự phòng sẽ bị suy giảm nếu cả hai cùng phụ thuộc:

- Một router vật lý duy nhất làm điểm kết nối chung.
- Một nguồn điện, switch hoặc cổng WAN không có dự phòng.
- Một tuyến cáp hoặc một nhà cung cấp bị đứt là mất cả ExpressRoute lẫn Internet.
- Một firewall hoặc một tập quy tắc BGP có lỗi đồng loạt áp lên cả hai đường.
- Cùng một cơ chế xác thực hoặc hệ thống quản trị nằm phía sau chính kết nối bị sự cố.

Cần lập sơ đồ các điểm phụ thuộc và thử nghiệm từng tình huống lỗi. Trong hệ thống có yêu cầu RTO/RPO khắt khe, có thể cần **hai ExpressRoute circuit ở các peering location/provider khác nhau**, VPN dự phòng thêm một lớp, hoặc kiến trúc đa vùng; chỉ một ExpressRoute circuit cộng một VPN tunnel không giải quyết mọi loại sự cố.

## 5. BGP quyết định đường nào được chọn

### 5.1. Vì sao BGP hữu ích cho failover?

BGP (Border Gateway Protocol) cho phép các phía quảng bá prefix có thể đến được và rút route khi phiên/đường liên quan không còn khả dụng. Khi có ExpressRoute và VPN kết nối cùng VNet, Azure và on-premises có thể học prefix qua hai nguồn và đưa ra quyết định chọn tuyến theo chính sách định tuyến.

Ví dụ cả hai đường đều cho phép tới:

~~~text
On-premises prefix: 172.20.0.0/16

Đường chính: ExpressRoute private peering
Đường dự phòng: Site-to-Site VPN sử dụng BGP
~~~

Trong các cấu hình coexistence thông thường của Azure, **ExpressRoute được ưu tiên hơn VPN đối với cùng một prefix on-premises khi các điều kiện lựa chọn route tương đương**. Tuy nhiên, route selection còn bị tác động bởi **longest-prefix match**, UDR, cấu hình Azure network, trạng thái BGP và chính sách on-premises. Không coi câu “ExpressRoute luôn ưu tiên” là một quy tắc tuyệt đối cho mọi gói tin.

Ví dụ quan trọng: nếu VPN quảng bá 172.20.10.0/24 còn ExpressRoute chỉ quảng bá 172.20.0.0/16, lưu lượng tới 172.20.10.5 có thể ưu tiên VPN vì /24 cụ thể hơn /16. Đây là lỗi thiết kế thường gặp khi hai đường có tập route không đồng nhất.

### 5.2. Điều khiển hai chiều lưu lượng

Cần phân biệt **chiều Azure → on-premises** và **chiều on-premises → Azure**.

| Chiều lưu lượng | Ai chủ yếu chọn đường? | Cần kiểm tra |
|---|---|---|
| Azure → on-premises | Route hiệu lực tại nguồn Azure, tuyến học qua các gateway và UDR liên quan | Prefix, ưu tiên ER/VPN, route propagation, gateway health |
| On-premises → Azure | Router/firewall của doanh nghiệp với chính sách BGP/local preference/route policy | Local preference, prefix-list, AS path, next hop, tunnel và khả năng quay về |
| Giữa các VNet spoke qua hub | Route của spoke, VNet peering/gateway transit và cấu hình kiểm soát lưu lượng | UDR, gateway transit, route propagation, firewall/NVA |

Một đầu chọn ExpressRoute trong khi đầu kia chọn VPN có thể tạo **asymmetric routing**. Đường đi bất đối xứng không phải lúc nào cũng thất bại, nhưng firewall trạng thái, NAT, hệ thống kiểm tra lưu lượng và thiết bị on-premises thường có thể từ chối gói vì không thấy đầy đủ phiên ở cả hai hướng.

Vì vậy, phải xác minh cả hướng đi lẫn hướng về, đặc biệt với dịch vụ dùng TCP, private endpoint, firewall trung gian hoặc NAT.

### 5.3. Chính sách route tham khảo

Một chính sách ban đầu có thể như sau:

| Route/prefix | Qua ExpressRoute | Qua VPN | Mục tiêu |
|---|---|---|---|
| 172.20.0.0/16 (on-prem) | Quảng bá | Quảng bá cùng prefix | Azure có thể dùng VPN khi ER không khả dụng |
| 10.40.0.0/16 (Azure hub) | Quảng bá hợp lệ | Quảng bá hợp lệ | On-premises có đường tới hub qua hai phương thức |
| 10.41.0.0/16 (spoke, nếu có) | Theo khả năng transit/định tuyến đã xác nhận | Theo khả năng transit/định tuyến đã xác nhận | Lưu lượng đến workload đúng thiết kế |
| 0.0.0.0/0 | Chỉ nếu có yêu cầu và thiết kế forced tunneling | Không tự ý quảng bá | Tránh đổi đường Internet ngoài ý muốn |

Trên router doanh nghiệp, chính sách BGP có thể tăng mức ưu tiên route đến Azure qua ExpressRoute và để VPN ở mức dự phòng. Cách thực hiện phụ thuộc thiết bị và quy trình mạng nội bộ: có thể dùng local preference hoặc chính sách lựa chọn đường đi phù hợp. Không sao chép một bộ giá trị local preference mà chưa kiểm tra các tuyến hiện có trong hệ thống.

**Không quảng bá route rộng hoặc không thuộc quyền quản lý.** Dùng prefix-list, route filter, hạn chế max-prefix theo khả năng thiết bị và giám sát sự cố route leak. Nếu sử dụng UDR với next hop là network virtual appliance hoặc vô hiệu hóa BGP route propagation trên subnet, hành vi chuyển tuyến tự động có thể khác thiết kế ban đầu.

### 5.4. Trình tự khi đường ExpressRoute gặp sự cố

Một luồng failover kỳ vọng:

~~~mermaid
sequenceDiagram
    participant O as Mạng on-premises
    participant E as ExpressRoute
    participant B as VPN/BGP
    participant A as Azure workload
    O->>E: Lưu lượng production qua tuyến ưu tiên
    E->>A: Kết nối hoạt động
    Note over E: Mất tuyến hoặc route hợp lệ
    E--xA: Đường chính không còn khả dụng
    Note over O,A: BGP/route policy cập nhật và hội tụ
    O->>B: Chọn tuyến VPN dự phòng
    B->>A: Lưu lượng qua IPsec tunnel
    Note over O,A: Kiểm tra chiều về và trạng thái ứng dụng
~~~

Cần đáp ứng đồng thời các điều kiện:

1. Hệ thống phát hiện tuyến ExpressRoute bị mất hoặc không còn được chọn.
2. Các route dùng VPN vẫn được quảng bá và chấp nhận.
3. Router doanh nghiệp và Azure cùng có tuyến quay về hợp lệ.
4. Tunnel VPN, firewall, NAT và dịch vụ ứng dụng đủ khả năng phục vụ lưu lượng.
5. Trạng thái kết nối ứng dụng có thể phục hồi nếu các phiên TCP trước đó bị gián đoạn.

**Failover không đồng nghĩa không gián đoạn.** BGP cần thời gian phát hiện, rút route và hội tụ; phiên hiện có có thể phải kết nối lại. Thời gian thực tế phụ thuộc cấu hình và điều kiện mạng, không nên hứa một số giây cố định nếu chưa đo được trong môi trường thật.

### 5.5. Failback khi ExpressRoute trở lại

Khi route ExpressRoute được khôi phục và chính sách ưu tiên áp dụng, lưu lượng có thể chuyển từ VPN về ER. Cần:

- Xác nhận cả hai phiên BGP/đường VPN và ExpressRoute đã ổn định.
- Kiểm tra route nhận được thực sự tương ứng với prefix mong muốn.
- Theo dõi tránh hiện tượng route flapping (liên tục rút/quảng bá) gây chuyển tuyến lặp lại.
- Đánh giá tải ứng dụng và firewall state khi đường đi thay đổi.
- Kiểm tra dịch vụ và độ trễ sau failback, không chỉ dựa trên trạng thái gateway.

Một số thay đổi về BGP policy hay timer có thể tối ưu hội tụ nhưng cũng tăng khả năng flap. Thử trong môi trường kiểm thử và theo hướng dẫn nhà cung cấp trước khi điều chỉnh production.

## 6. Quy trình triển khai từng bước

Đây là trình tự thiết kế để triển khai bằng Azure Portal hoặc Infrastructure as Code; tên menu và hỗ trợ tính năng có thể thay đổi theo phiên bản Azure.

### Bước 1. Thu thập thông tin kết nối

Ghi rõ:

- Subscription ID, resource group, Azure region và VNet cần kết nối.
- CIDR Azure hub, các spoke và mạng on-premises; xác minh không trùng.
- Băng thông, độ trễ, khả năng chịu ngắt phiên và yêu cầu khôi phục của ứng dụng.
- ExpressRoute circuit hiện có, nhà cung cấp, private peering, BGP ASN/peering IP, trạng thái provisioning.
- CPE/router on-premises, IP public VPN, loại IKE/IPsec, BGP ASN và các prefix được phép quảng bá.
- Chiến lược tuyến chính/dự phòng, giám sát, quyền quản trị, kế hoạch diễn tập và rollback.

Nếu có kết nối ExpressRoute đang hoạt động, cần lập danh sách các prefix đang được dùng trước khi thêm VPN. Không nên thay đổi hàng loạt routing policy trên đường chính trong cùng đợt tạo đường dự phòng.

### Bước 2. Quy hoạch VNet và GatewaySubnet

Ví dụ cấu trúc:

~~~text
Subscription: sub-connectivity-prod
Resource group: rg-hub-network-prod
Region: southeastasia

Hub VNet: vnet-hub-prod-sea
  Address space: 10.40.0.0/16

  GatewaySubnet: 10.40.255.0/26
  Subnet-App:    10.40.10.0/24

ExpressRoute Gateway: gw-er-hub-prod
VPN Gateway:          gw-vpn-hub-prod
~~~

GatewaySubnet là subnet dành riêng cho gateway. Không đặt VM, firewall appliance hoặc dịch vụ ứng dụng trong GatewaySubnet. Dải /26 ví dụ phải nằm trong address space của VNet và không trùng subnet khác.

Trước khi triển khai, xác nhận SKU ExpressRoute Gateway, VPN Gateway và tính năng gateway coexistence được hỗ trợ trong region. Với hệ thống nhiều zone, cân nhắc gateway SKU hỗ trợ zone redundancy nếu đáp ứng yêu cầu sẵn sàng.

### Bước 3. Kết nối ExpressRoute

Trình tự ở mức quản trị:

1. Đặt/cấp phát ExpressRoute circuit ở mô hình và nhà cung cấp phù hợp.
2. Hoàn tất provisioning giữa nhà cung cấp và Microsoft.
3. Cấu hình private peering và BGP với doanh nghiệp theo thông tin provider.
4. Tạo ExpressRoute Gateway trong hub VNet.
5. Liên kết circuit với gateway qua kết nối ExpressRoute tương ứng.
6. Xác minh trạng thái circuit, peering, BGP routes và truy cập tới subnet Azure.

Đường private peering không phải là kết nối tự động chỉ vì circuit được tạo. Cần xác minh phiên BGP và tuyến thực tế trước khi chuyển sang bước dự phòng.

### Bước 4. Thiết lập VPN làm đường dự phòng

1. Triển khai route-based VPN Gateway trong cùng hub VNet theo điều kiện coexistence.
2. Tạo Local Network Gateway mô tả site on-premises, gồm IP public và cấu hình BGP/prefix khi cần.
3. Tạo Site-to-Site VPN connection từ VPN Gateway đến Local Network Gateway.
4. Cấu hình tương ứng trên firewall/router on-premises, gồm IKE/IPsec, peer IP, chính sách bảo mật và BGP nếu dùng.
5. Xác minh trạng thái tunnel, BGP peer và các route đã học.
6. Đảm bảo tuyến ExpressRoute vẫn được ưu tiên theo thiết kế, không để việc thêm VPN làm chuyển lưu lượng chính ngoài ý muốn.

Khóa chia sẻ trước (pre-shared key) hoặc credential VPN cần được lưu theo chính sách quản lý bí mật; không ghi vào repository, lịch sử terminal hay tài liệu công khai.

### Bước 5. Điều chỉnh route và kiểm thử từ hai hướng

Kiểm tra:

- Azure đã học prefix on-premises qua cả hai đường được kỳ vọng.
- On-premises đã nhận được các prefix Azure cần thiết qua cả ExpressRoute và VPN.
- Khi cả hai hoạt động, tuyến đang chọn đúng là đường chính.
- NSG, Azure Firewall/NVA, UDR và firewall on-premises cho phép lưu lượng ứng dụng.
- Không có route mặc định ngoài dự kiến kéo lưu lượng Internet qua data center.
- Các spoke/Private Endpoint chỉ dùng được đường hybrid khi cấu hình route và DNS phù hợp.

**DNS là một phần của bài toán hybrid.** Khi ứng dụng gọi tên riêng nội bộ, cần xác minh DNS resolver, Private DNS zone/link và khả năng phân giải qua tuyến dự phòng. Kết nối IP thành công không bảo đảm ứng dụng chạy được nếu DNS phụ thuộc vào đường chính đã hỏng.

### Bước 6. Thiết lập giám sát, alert và diễn tập

Tạo dashboard theo dõi trạng thái circuit, BGP, VPN tunnel, lỗi và khả năng truy cập dịch vụ. Cấu hình Action Group hoặc hệ thống quản lý sự cố để có người nhận cảnh báo. Sau đó kiểm tra một lần chuyển tuyến có kiểm soát và một lần failback, ghi lại bằng chứng thực tế.

## 7. Quan sát trạng thái bằng Azure CLI

Các lệnh sau chủ yếu **đọc thông tin cấu hình và trạng thái**, phù hợp để khảo sát trước/sau diễn tập. Ví dụ cú pháp chạy trong Bash; thay các tên cho đúng tài nguyên trong môi trường của bạn.

### 7.1. Kiểm tra subscription và hai gateway

~~~bash
az account show --output table

az network vnet-gateway show \
  --resource-group rg-hub-network-prod \
  --name gw-er-hub-prod \
  --query "{name:name,type:gatewayType,sku:sku.name,state:provisioningState}" \
  --output table

az network vnet-gateway show \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --query "{name:name,type:gatewayType,sku:sku.name,bgp:enableBgp,state:provisioningState}" \
  --output table
~~~

Đừng nhầm provisioningState thành tình trạng lưu lượng end-to-end. Một gateway ở trạng thái Succeeded vẫn có thể có tunnel down, route sai hoặc firewall chặn kết nối.

### 7.2. Kiểm tra kết nối và trạng thái BGP

~~~bash
az network vnet-gateway connection show \
  --resource-group rg-hub-network-prod \
  --name conn-er-hub \
  --query "{name:name,type:connectionType,status:connectionStatus}" \
  --output table

az network vnet-gateway connection show \
  --resource-group rg-hub-network-prod \
  --name conn-vpn-onprem \
  --query "{name:name,type:connectionType,status:connectionStatus}" \
  --output table

az network vnet-gateway list-bgp-peer-status \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --output table
~~~

Kiểm tra các route đã học từ BGP tại gateway được hỗ trợ:

~~~bash
az network vnet-gateway list-learned-routes \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --output table
~~~

Tên lệnh, hỗ trợ và cột trả về phụ thuộc phiên bản Azure CLI, gateway và cấu hình BGP. Nếu không thấy route mong muốn, kiểm tra BGP ở cả hai đầu, prefix filter và trạng thái tunnel. Không xem một lệnh trả về rỗng là bằng chứng chắc chắn on-premises không có tuyến nếu người chạy thiếu quyền hoặc truy vấn sai đối tượng.

### 7.3. Kiểm tra ExpressRoute circuit

~~~bash
az network express-route show \
  --resource-group rg-connectivity-prod \
  --name er-main-prod \
  --query "{name:name,sku:sku.tier,circuitState:circuitProvisioningState,providerState:serviceProviderProvisioningState}" \
  --output table
~~~

Circuit provisioned không đồng nghĩa BGP private peering, gateway connection và khả năng gọi ứng dụng đã hoạt động đúng. Phải xác minh trạng thái peering và kiểm tra kết nối thực tế, cùng thông tin nhà cung cấp nếu nghi lỗi tại mạng carrier.

### 7.4. Kiểm thử từ máy nguồn đến đích thật

Từ VM hoặc ứng dụng được phép truy cập, thử kết nối đến một dịch vụ nội bộ với port thực tế. Ví dụ trong PowerShell trên Windows VM:

~~~powershell
Test-NetConnection -ComputerName 172.20.10.20 -Port 443
~~~

Hoặc trên Linux, nếu dịch vụ hỗ trợ HTTPS và có chứng chỉ phù hợp:

~~~bash
curl --connect-timeout 5 --max-time 15 \
  https://internal.example.invalid/health
~~~

Địa chỉ và hostname trong ví dụ chỉ là placeholder. Kiểm thử cần có đích thật và cơ chế xác thực hợp lệ; không bỏ kiểm tra TLS chỉ để nhận mã HTTP thành công.

Bên cạnh kết nối, ghi nhận độ trễ, tỷ lệ lỗi, thời gian hội tụ, kết quả DNS, đường về và tình trạng session dài. Trạng thái Connected ở gateway là chỉ dấu cần thiết nhưng chưa đủ chứng minh trải nghiệm ứng dụng.

## 8. Kịch bản diễn tập failover và failback

### 8.1. Chuẩn bị trước diễn tập

Diễn tập phải có lịch, người chịu trách nhiệm, phạm vi người dùng bị ảnh hưởng và kế hoạch khôi phục. Trên production, chỉ thực hiện theo change approval và runbook của tổ chức. Nên thử mô hình trên môi trường kiểm thử hoặc một phạm vi nhỏ trước.

Checklist ban đầu:

1. Cả ExpressRoute và VPN đang hoạt động; peer BGP ở trạng thái đúng.
2. Ghi snapshot route table phía Azure/on-premises và trạng thái hai gateway.
3. Có hệ thống đo kiểm end-to-end: TCP/application health, DNS, timeout và error rate.
4. Xác định mốc bắt đầu, tiêu chí pass/fail, ngưỡng dừng thử nghiệm và trách nhiệm rollback.
5. Có đường quản trị ngoài băng để khôi phục khi cấu hình route làm mất kết nối chính.
6. Nhóm ứng dụng, hạ tầng, security và provider đã nắm được cửa sổ thử nghiệm phù hợp.

### 8.2. Ma trận kiểm thử

| Kịch bản | Thao tác mô phỏng có kiểm soát | Kết quả cần quan sát |
|---|---|---|
| Tất cả đường hoạt động | Kiểm tra kết nối và route khi hai đường up | Lưu lượng đi ExpressRoute theo chính sách; VPN sẵn sàng |
| Mất tuyến ExpressRoute | Phối hợp router/provider ngắt hoặc rút quảng bá tại phạm vi kiểm thử | VPN được chọn sau hội tụ; ứng dụng phục hồi |
| ExpressRoute trở lại | Khôi phục route/peering ở phạm vi thử nghiệm | Lưu lượng quay về ER khi ổn định, không flap |
| VPN đường dự phòng hỏng khi ER còn hoạt động | Mô phỏng VPN tunnel down riêng biệt | Ứng dụng vẫn chạy trên ER, cảnh báo đường dự phòng có tác dụng |
| Lỗi một nhánh phía on-premises | Cô lập một thiết bị/tunnel trong mô hình nhiều thiết bị | Các tuyến còn lại duy trì kết nối theo thiết kế |
| Sai route hoặc route bị lọc | Thử bộ route policy trong lab | Phát hiện mất prefix, không có route leak hoặc đường mặc định ngoài ý muốn |
| DNS qua đường dự phòng | Truy vấn tên nội bộ khi ER bị ngắt trong bài thử | Tên vẫn phân giải, ứng dụng truy cập đúng đích |

**Không thực hiện thao tác xóa gateway/circuit hoặc tắt kết nối production chỉ để “thử nhanh”.** Việc rút route, thay đổi chính sách peering hoặc cắt mạng có thể gây gián đoạn rộng. Thử nghiệm phải được giới hạn, ghi chép và có đường rollback.

### 8.3. Đo thời gian chuyển tuyến

Chọn một mốc khách quan cho RTO của kết nối hoặc ứng dụng:

- T0: thời điểm mất tuyến ExpressRoute được hệ thống quan sát.
- T1: thời điểm route hợp lệ qua VPN được chọn ở cả hai đầu.
- T2: thời điểm probe TCP và ứng dụng đáp ứng trở lại.
- T3: thời điểm các tác vụ cần thiết hoạt động ổn định theo tiêu chí.

Có thể đo:

~~~text
Thời gian hội tụ mạng  = T1 - T0
Thời gian phục hồi ứng dụng = T2 - T0
Thời gian ổn định hoàn toàn = T3 - T0
~~~

Không giả định thời gian hội tụ mạng bằng thời gian ứng dụng phục hồi. Các session TCP, connection pool cơ sở dữ liệu, DNS cache, firewall state và cơ chế retry có thể khiến phục hồi ứng dụng muộn hơn. Cần chạy nhiều lần trong điều kiện phù hợp, lưu kết quả đo thực tế và đối chiếu với yêu cầu nghiệp vụ.

### 8.4. Bằng chứng và rollback

Một hồ sơ diễn tập tối thiểu nên gồm:

~~~yaml
testId: NET-DR-ER-VPN-001
environment: non-production
primaryPath: ExpressRoute
backupPath: Site-to-Site VPN
scope:
  azureVnet: vnet-hub-prod-sea
  onPremPrefix: 172.20.0.0/16
preconditions:
  - "BGP peers established"
  - "Gateway connection health verified"
  - "Application probe baseline captured"
observations:
  - "Record T0, T1, T2, T3 in UTC"
  - "Capture route changes and path after failover"
  - "Capture error rate and DNS behavior"
result: "<PASS_OR_FAIL_WITH_EVIDENCE>"
rollback:
  - "Restore original on-prem routing policy"
  - "Verify both paths and primary route preference"
  - "Confirm application health"
~~~

Ví dụ là một biểu mẫu, không phải kết quả thử nghiệm đã thực hiện. Lưu thông tin trong change ticket và đối chiếu với Azure Monitor, BGP route snapshot, log thiết bị on-premises. Không đưa khóa VPN hoặc thông tin nhạy cảm vào ticket.

## 9. Giám sát và vận hành sau triển khai

### 9.1. Những tín hiệu cần theo dõi

| Thành phần | Tín hiệu gợi ý | Điều cần cảnh báo |
|---|---|---|
| ExpressRoute circuit | Circuit/provider provisioning, lưu lượng và chất lượng kết nối, tình trạng peering | Đường chính mất, provider gặp sự cố, lưu lượng bất thường |
| ExpressRoute gateway | Gateway health, route availability, dữ liệu liên quan theo khả năng SKU | Azure không còn đường hợp lệ tới on-premises |
| VPN Gateway | Tunnel connection status, BGP peer status, ingress/egress, lỗi tunnel | Đường backup không sẵn sàng dù ER vẫn chạy |
| Mạng on-premises | BGP neighbor state, prefix nhận/quảng bá, interface, ISP availability | Lỗi CPE, thiếu prefix hoặc hai đường phụ thuộc cùng điểm lỗi |
| Ứng dụng | TCP success, DNS, HTTP 5xx, độ trễ, retry và timeout | Failover chỉ thành công trên mạng nhưng workload vẫn lỗi |
| Định tuyến | Route hiệu lực, UDR, firewall/NVA logs | Sai next hop, asymmetric routing, route leak hoặc route flapping |
| Chi phí | ExpressRoute, gateway, băng thông và lưu lượng | Đường backup phát sinh phí liên tục hoặc lưu lượng VPN cao ngoài ý muốn |

Đặt cảnh báo riêng cho **đường dự phòng không khả dụng** ngay cả khi đường ExpressRoute vẫn hoạt động. Nếu chỉ theo dõi ứng dụng, sự cố VPN có thể không được phát hiện cho tới lúc ExpressRoute thật sự hỏng.

Azure Monitor có các metric và cơ chế diagnostic khác nhau theo loại gateway/circuit và gói dịch vụ. Hãy chọn metric được tài nguyên hiện tại hỗ trợ và thiết lập Action Group, runbook, escalation cùng các ngưỡng đã thử nghiệm.

### 9.2. Runbook xử lý sự cố

Một runbook thực tế nên trả lời:

1. Cảnh báo bắt đầu từ circuit, gateway, BGP session, tunnel hay ứng dụng?
2. Lưu lượng thực tế đang qua ExpressRoute hay VPN?
3. Route đang được học/quảng bá có đúng prefix và scope không?
4. Lỗi xảy ra một chiều hay cả hai chiều?
5. VPN có đủ tải khi toàn bộ lưu lượng chuyển sang không?
6. Có phụ thuộc nhà cung cấp, thiết bị on-premises, DNS, firewall hoặc private endpoint không?
7. Ai liên hệ nhà mạng, ai được đổi route và ai xác nhận khôi phục?
8. Có cần giữ hệ thống chạy trên VPN thêm một khoảng ổn định trước khi failback không?

Trong sự cố thật, ưu tiên duy trì dịch vụ và thu thập log hiện trạng trước thay đổi nếu khả thi. Đừng liên tục chỉnh nhiều route policy cùng lúc vì sẽ khó xác định thay đổi nào giải quyết lỗi.

## 10. Bảo mật của kiến trúc dự phòng

### 10.1. Mã hóa và bảo vệ dữ liệu

ExpressRoute sử dụng tuyến kết nối riêng nhưng không nên được coi là cơ chế mã hóa dữ liệu hoàn chỉnh. Áp dụng TLS ở tầng ứng dụng hoặc giải pháp mã hóa phù hợp khi dữ liệu cần bảo mật đầu cuối. VPN dùng IPsec/IKE nhưng cần cấu hình thuật toán, key lifetime, certificate hoặc PSK phù hợp chính sách tổ chức.

Khi muốn thêm lớp mã hóa trên tuyến ExpressRoute, phải đánh giá giải pháp phù hợp với ExpressRoute tier, thiết bị, topology và tác động vận hành. Không tự suy ra cấu hình VPN dự phòng có thể đồng thời mã hóa mọi lưu lượng ExpressRoute.

### 10.2. Phân quyền và mạng

- Dùng Azure RBAC với quyền tối thiểu cho người quản trị circuit, gateway, route và diagnostic settings.
- Bảo vệ thông tin thiết bị BGP, IPsec, public IP và chính sách peering ở phạm vi người cần biết.
- Kiểm soát NSG, Azure Firewall và thiết bị on-premises đồng nhất cho **cả hai** đường truyền; không tạo một đường VPN “ít kiểm soát hơn” vì chỉ dùng khi có sự cố.
- Giới hạn prefix được quảng bá và chấp nhận; tránh vô tình cung cấp kết nối tới subnet nhạy cảm.
- Áp dụng cơ chế DNS, firewall inspection, logging và segmentation nhất quán trên đường chính và dự phòng.
- Kiểm tra các yêu cầu về dữ liệu, quy định và vị trí lưu lượng khi một tuyến bị hỏng.

### 10.3. Dự phòng không phải một bản sao bảo mật

Nếu một hệ thống phụ thuộc vào firewall hoặc dịch vụ DNS duy nhất ở on-premises, việc thêm VPN không giải quyết điểm lỗi chung đó. Tương tự, nếu service account dùng để sửa route bị vô hiệu hóa trong lúc có sự cố, nhóm có thể không thao tác khôi phục được. Cần cân nhắc đường quản trị ngoài băng, phân quyền dự phòng và quy trình khẩn cấp.

## 11. Chi phí và hiệu năng

Đường dự phòng có thể phát sinh chi phí **ngay cả khi không được chọn cho lưu lượng ứng dụng**. Các thành phần cần tính gồm:

- ExpressRoute circuit theo băng thông/tier và hợp đồng với nhà cung cấp.
- ExpressRoute Gateway theo SKU, thời gian sử dụng và lưu lượng áp dụng.
- VPN Gateway và các địa chỉ IP public theo cấu hình được chọn.
- Nhà cung cấp Internet, đường WAN phụ, thiết bị firewall/router và vận hành.
- Lưu lượng egress, xử lý dữ liệu hoặc phí liên quan tùy mô hình giá và khu vực.
- Azure Monitor/Log Analytics, Network Watcher và các thành phần giám sát có tính phí.

Trước khi triển khai, lập bảng chi phí ở trạng thái bình thường và khi toàn bộ lưu lượng chuyển sang VPN. Kiểm tra VPN Gateway throughput theo loại workload, thuật toán IPsec, số tunnel và hiệu năng thiết bị đầu kia. Băng thông danh nghĩa không nhất thiết tương ứng với thông lượng ứng dụng đạt được khi có mã hóa và nhiều phiên đồng thời.

Ví dụ một ứng dụng cần truyền dữ liệu liên tục với mức tải lớn có thể chạy tốt trên ExpressRoute nhưng bị tăng latency và giảm throughput trên VPN dự phòng. Khi đó, doanh nghiệp cần quyết định chức năng nào phải giữ khi mất đường chính, có cần giảm tải tạm thời hay đầu tư thêm Internet/VPN Gateway/SKU phù hợp.

Azure Cost Management có thể hỗ trợ theo dõi chi phí, nhưng budget alert không mặc nhiên giới hạn hoặc dừng kết nối mạng khi vượt ngân sách. Không dùng biện pháp tiết kiệm tự động làm ngắt VPN dự phòng mà chưa đánh giá tác động tới tính sẵn sàng.

## 12. Những lỗi thường gặp

### 12.1. VPN Connected nhưng không tự chuyển tuyến

**Nguyên nhân có thể:** BGP chưa bật, phiên BGP không thiết lập, prefix bị lọc, VPN không quảng bá cùng mạng cần thiết, route propagation bị vô hiệu hóa hoặc UDR đang cố định next hop.

**Cách kiểm tra:** đối chiếu BGP peer, các route learned/advertised và effective routes tại subnet nguồn, cả hai chiều. Đừng chỉ nhìn connectionStatus.

### 12.2. Khi cả hai đường up, lưu lượng lại qua VPN

**Nguyên nhân có thể:** prefix VPN cụ thể hơn prefix ExpressRoute, chính sách router on-premises ưu tiên sai hoặc UDR đang điều hướng qua network appliance.

**Cách kiểm tra:** so sánh prefix và prefix length của tuyến, chính sách local preference ở on-premises, UDR và log firewall. Chỉnh ở nguồn chính sách đã xác định sau khi có phương án rollback.

### 12.3. Azure gọi được on-premises nhưng on-premises không gọi ngược

**Nguyên nhân có thể:** route quay về sai, NAT, firewall trạng thái, NSG, DNS hoặc thiết bị trên đường dự phòng thiếu rule.

**Cách kiểm tra:** thử TCP ở cả hai hướng, đối chiếu IP nguồn/đích sau NAT, phân tích route và log firewall. Không đánh giá thành công chỉ bằng ping vì ICMP có thể bị chặn riêng.

### 12.4. BGP đã Established nhưng ứng dụng không truy cập được

**Nguyên nhân có thể:** BGP neighbor up nhưng prefix chưa được chấp nhận, subnet không nhận route, DNS không giải đúng, firewall chặn port hoặc đường dự phòng không đủ thông lượng.

**Cách kiểm tra:** phân biệt BGP session state với route thực tế, kiểm tra effective routes, gateway connection và application probe.

### 12.5. Failback gây gián đoạn dù ER đã khỏe

**Nguyên nhân có thể:** route flap, hai chiều chuyển thời điểm khác nhau, session bị mất, thiết bị NAT/firewall còn state của đường VPN hoặc app không retry.

**Cách kiểm tra:** so sánh timeline BGP, thay đổi route, thời gian mất kết nối và log ứng dụng. Xác định tiêu chí ổn định đường chính trước khi cho phép chuyển về.

### 12.6. Mất cả ExpressRoute và VPN trong cùng sự cố

**Nguyên nhân có thể:** hai đường cùng router, cùng đường truyền vật lý, chung ISP, chung nguồn điện hoặc lỗi chính sách route áp lên cả hai.

**Cách khắc phục:** lập sơ đồ phụ thuộc, thêm thiết bị/ISP độc lập hoặc đa circuit theo yêu cầu nghiệp vụ, kiểm tra toàn bộ chuỗi từ ứng dụng tới nhà mạng.

## 13. Tình huống thực tế: ứng dụng đơn hàng hybrid

Giả sử một công ty có ứng dụng nhận đơn hàng trên App Service ở Azure và cơ sở dữ liệu nghiệp vụ cũ trong data center. Ứng dụng thường truy cập dịch vụ nội bộ qua hub VNet bằng ExpressRoute; Site-to-Site VPN qua Internet được cấu hình dự phòng.

### Trạng thái bình thường

~~~text
App Service / workload Azure
    ↓ Kết nối VNet / tuyến hybrid phù hợp
Hub VNet
    ↓ ExpressRoute Gateway
ExpressRoute private peering
    ↓
On-premises API 172.20.10.20:443
~~~

Tại thời điểm này, hai gateway đều được giám sát. VPN tunnel được duy trì ở trạng thái sẵn sàng, BGP route kiểm tra đầy đủ và chi phí backup được đưa vào ngân sách. Nhóm ứng dụng chạy probe định kỳ tới API nội bộ.

### Khi đường ExpressRoute gặp sự cố

BGP route của ExpressRoute không còn sử dụng được. Nếu cấu hình hai phía đúng và tunnel VPN khỏe, route qua VPN được chọn. Một số kết nối đang chạy có thể timeout; ứng dụng sử dụng retry có giới hạn, connection timeout và cơ chế kiểm soát gửi lại thao tác để tránh tạo trùng đơn hàng.

Nhóm vận hành kiểm tra:

- Trạng thái VPN/BGP đã hội tụ.
- API nội bộ truy cập được qua cổng 443.
- DNS trả về IP kỳ vọng.
- Lỗi ứng dụng trở về mức chấp nhận được.
- Lưu lượng và CPU của VPN Gateway/thiết bị on-premises nằm trong khả năng chịu tải.

Khi ExpressRoute khôi phục, nhóm xác minh đường chính ổn định, theo dõi failback và ghi số liệu vào hồ sơ sự cố. Cách này cho thấy mục tiêu cuối cùng là **duy trì hoạt động nghiệp vụ**, không chỉ đưa tunnel vào trạng thái xanh.

## 14. Tự kiểm tra kiến thức

1. **Vì sao kết hợp ExpressRoute và VPN?** ExpressRoute phục vụ kết nối riêng chính; Site-to-Site VPN cung cấp đường truyền thay thế qua Internet khi tuyến chính không còn khả dụng.
2. **ExpressRoute có tự mã hóa mọi gói tin không?** Không. Cần bảo vệ dữ liệu bằng TLS hoặc giải pháp mã hóa phù hợp.
3. **Một VNet có thể có cả ExpressRoute Gateway và VPN Gateway không?** Có trong những cấu hình coexistence được Azure hỗ trợ; phải dùng gateway, SKU và GatewaySubnet phù hợp.
4. **Tại sao cùng một prefix quan trọng?** Nếu VPN quảng bá một prefix cụ thể hơn, longest-prefix match có thể khiến lưu lượng đi VPN ngay cả khi ExpressRoute đang khỏe.
5. **BGP session Established có đồng nghĩa kết nối ứng dụng hoạt động không?** Không. Cần kiểm tra route thực tế, DNS, firewall, hai chiều và ứng dụng.
6. **Chiều on-premises → Azure chọn tuyến theo cùng một cơ chế với Azure → on-premises không?** Không nhất thiết. Router doanh nghiệp có chính sách BGP riêng; cả hai chiều phải được kiểm tra.
7. **Failover có bảo đảm không mất phiên TCP không?** Không. Thời gian hội tụ và firewall state có thể làm phiên cũ bị ngắt; ứng dụng cần khả năng retry phù hợp.
8. **VPN dự phòng không có lưu lượng có thể phát sinh chi phí không?** Có. Gateway và những thành phần duy trì hoạt động thường có chi phí riêng.
9. **Vì sao cần thử DNS trong diễn tập?** Tên nội bộ có thể phụ thuộc DNS resolver qua tuyến đã lỗi, dù IP routing trên đường dự phòng vẫn hoạt động.
10. **Khi đường ExpressRoute hồi phục, cần quan sát gì?** Tính ổn định BGP, tuyến quay về ER, hiện tượng flap, khả năng kết nối hai chiều và trạng thái ứng dụng.
11. **Một VPN tunnel dự phòng có loại bỏ mọi single point of failure không?** Không. Cả hai tuyến vẫn có thể cùng phụ thuộc router, ISP, nguồn điện hoặc chính sách cấu hình.
12. **Phép đo nào phản ánh ứng dụng phục hồi?** Thời gian đạt lại tiêu chí phục vụ ứng dụng (ví dụ T2 − T0), không chỉ thời điểm BGP đổi tuyến.

## 15. Tài liệu tham khảo

- [Azure ExpressRoute documentation](https://learn.microsoft.com/azure/expressroute/) — tổng quan circuit, peering, gateway và hướng dẫn triển khai.
- [ExpressRoute and VPN coexistence](https://learn.microsoft.com/azure/expressroute/expressroute-howto-coexist-resource-manager) — cấu hình ExpressRoute và Site-to-Site VPN đồng thời trong VNet bằng Azure Resource Manager.
- [Azure VPN Gateway documentation](https://learn.microsoft.com/azure/vpn-gateway/) — IPsec/IKE, Site-to-Site VPN, SKU và gateway configuration.
- [BGP with Azure VPN Gateway](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview) — nguyên lý và yêu cầu sử dụng BGP.
- [Azure VNet traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview) — route selection, system routes, BGP và user-defined routes.
- [Azure Network Watcher](https://learn.microsoft.com/azure/network-watcher/) — công cụ kiểm tra và giám sát kết nối.
- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — metrics, diagnostic data và alerting.

Khi đưa kiến trúc vào production, hãy đối chiếu yêu cầu coexistence, hỗ trợ SKU, hạn mức và tính năng theo tài liệu Microsoft tại thời điểm triển khai. Trạng thái gateway, route và chất lượng ứng dụng phải được kiểm chứng bằng một đợt diễn tập có kiểm soát trước khi công nhận mục tiêu dự phòng đã đạt được.
