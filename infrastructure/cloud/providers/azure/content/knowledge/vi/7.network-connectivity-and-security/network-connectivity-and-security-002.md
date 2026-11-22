# Kết nối chuyên dụng với ExpressRoute

Một doanh nghiệp có trung tâm dữ liệu tại chỗ và nhiều ứng dụng chạy trên Microsoft Azure thường cần truyền dữ liệu ổn định giữa hai môi trường. Ví dụ, hệ thống quản lý đơn hàng đặt API trên Azure App Service nhưng vẫn sử dụng cơ sở dữ liệu hoặc hệ thống ERP ở trung tâm dữ liệu riêng. Việc truyền dữ liệu qua Internet có thể đáp ứng nhiều nhu cầu, nhưng những workload có lưu lượng lớn, yêu cầu đường truyền nhất quán hoặc mô hình kết nối doanh nghiệp đặc thù có thể cần một phương án khác.

**Azure ExpressRoute** cho phép thiết lập kết nối riêng tới mạng Microsoft thông qua một nhà cung cấp kết nối hoặc vị trí kết nối trực tiếp được hỗ trợ. Lưu lượng của đường ExpressRoute không đi qua Internet công cộng theo cách kết nối VPN site-to-site thông thường. Tuy nhiên, đường truyền riêng **không tự động đồng nghĩa với mã hóa đầu cuối, an toàn tuyệt đối hoặc không bao giờ gián đoạn**. Để triển khai đúng, cần hiểu vai trò của circuit, peering, BGP, gateway, định tuyến, bảo mật, chi phí và khả năng dự phòng.

Bài học thuộc chương **Kết nối và bảo vệ mạng**, trong lộ trình tìm hiểu hệ sinh thái Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, dữ liệu, triển khai, giám sát và kiểm soát chi phí một kiến trúc ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ExpressRoute là gì và khi nào nên chọn so với VPN site-to-site.
2. Nhận diện các thành phần của kiến trúc ExpressRoute: circuit, connectivity provider, peering, BGP, ExpressRoute gateway và VNet.
3. Phân biệt **Azure private peering** với **Microsoft peering**.
4. Hiểu những điều kiện về CIDR, ASN, VLAN, định tuyến, DNS, bảo mật và khả năng sẵn sàng.
5. Lập kế hoạch triển khai kết nối từ mạng tại chỗ tới Azure VNet theo các bước có thể kiểm chứng.
6. Kiểm tra trạng thái tài nguyên bằng Azure portal hoặc Azure CLI và xử lý những lỗi kết nối thường gặp.
7. Đánh giá chi phí và thiết kế phương án dự phòng phù hợp với workload.

## 1. ExpressRoute là gì?

ExpressRoute là dịch vụ kết nối của Azure cho phép doanh nghiệp thiết lập **đường truyền riêng** giữa hạ tầng tại chỗ hoặc địa điểm của nhà cung cấp kết nối với mạng Microsoft. Đường truyền đi qua một **connectivity provider**, ví dụ nhà mạng hoặc nhà cung cấp dịch vụ kết nối tại địa điểm peering, hoặc qua **ExpressRoute Direct** đối với mô hình kết nối vật lý trực tiếp được hỗ trợ.

ExpressRoute được thiết kế cho các tình huống cần:

- Kết nối hybrid giữa trung tâm dữ liệu doanh nghiệp và các VNet chứa ứng dụng trên Azure.
- Truyền khối lượng dữ liệu lớn, kết nối ổn định theo hợp đồng với nhà cung cấp và kiểm soát đường đi ở mức mạng.
- Kết nối nhiều hệ thống nội bộ với workload Azure thông qua kiến trúc hub-and-spoke.
- Tăng lựa chọn về dự phòng và kiểm soát kết nối khi mạng doanh nghiệp phụ thuộc nhiều vào Azure.
- Đáp ứng một số yêu cầu kiến trúc kết nối riêng theo chính sách nội bộ, hợp đồng hoặc quy định của tổ chức.

ExpressRoute thường cung cấp đặc tính độ trễ và độ ổn định có thể dự đoán tốt hơn một đường Internet công cộng, nhưng **không có bảo đảm chung rằng mọi workload đều nhanh hơn VPN**. Kết quả còn phụ thuộc vị trí peering, tuyến truyền dẫn của nhà cung cấp, băng thông, lưu lượng, vùng Azure và thiết kế ứng dụng.

### ExpressRoute không phải là gì?

ExpressRoute **không phải** một địa chỉ Public IP gắn vào máy ảo. Nó không tự tạo DNS riêng, không thay thế tường lửa, không tự bật bảo vệ DDoS cho toàn bộ ứng dụng và không tự cấp quyền truy cập vào mọi Azure resource.

ExpressRoute cũng không phải một cơ chế mã hóa dữ liệu mặc định. Tùy yêu cầu, tổ chức vẫn phải sử dụng TLS cho ứng dụng, mã hóa dữ liệu hoặc một lớp IPsec phù hợp; với ExpressRoute Direct, một số trường hợp có thể sử dụng MACsec trên đường kết nối trực tiếp khi đáp ứng điều kiện hỗ trợ.

## 2. ExpressRoute khác VPN site-to-site như thế nào?

**Azure VPN Gateway** có thể tạo tunnel IPsec/IKE qua Internet giữa mạng tại chỗ và Azure VNet. **ExpressRoute** cung cấp kết nối riêng tới mạng Microsoft thông qua hệ sinh thái provider và sử dụng BGP để trao đổi tuyến. Cả hai đều có thể dùng trong kiến trúc hybrid, nhưng có khác biệt quan trọng.

| Tiêu chí | Site-to-site VPN | ExpressRoute |
|---|---|---|
| Đường kết nối | Tunnel qua mạng Internet | Kết nối riêng qua provider/địa điểm peering hoặc Direct |
| Mã hóa | Thường dùng IPsec/IKE để mã hóa tunnel | Không tự mã hóa lưu lượng theo mặc định |
| Phụ thuộc | ISP/Internet, VPN gateway, thiết bị VPN | Provider hoặc kết nối Direct, circuit, peering, gateway và các thiết bị mạng |
| Triển khai | Thường nhanh hơn nếu hai bên đã có Internet và thiết bị tương thích | Cần chuẩn bị kết nối với nhà cung cấp, cấu hình peering và gateway |
| Băng thông, độ trễ | Phụ thuộc kết nối Internet và cấu hình gateway | Phụ thuộc băng thông circuit, provider và thiết kế đường mạng |
| Chi phí | Gateway, truyền dữ liệu và kết nối Internet | Circuit/port, provider, gateway, truyền dữ liệu theo gói và dịch vụ liên quan |
| Phù hợp | Chi nhánh nhỏ, thử nghiệm, lưu lượng vừa phải hoặc kết nối dự phòng | Hybrid doanh nghiệp, lưu lượng cao hoặc yêu cầu đường truyền riêng |

Không nên chọn ExpressRoute chỉ vì một ứng dụng cần bảo mật: VPN mã hóa qua Internet đôi khi phù hợp hơn và có chi phí dễ tiếp cận hơn. Ngược lại, ExpressRoute có thể phù hợp khi tổ chức đã có hạ tầng WAN, cần kết nối riêng quy mô lớn và chấp nhận công việc quản lý định tuyến, provider, dự phòng và chi phí.

Một số thiết kế hỗ trợ **ExpressRoute và VPN Gateway cùng tồn tại** để tạo đường dự phòng theo điều kiện của gateway, topology và định tuyến. Điều này cần được thiết kế và kiểm chứng riêng; không có cơ chế dự phòng hoàn chỉnh chỉ nhờ tạo thêm một gateway.

## 3. Các thành phần trong kiến trúc ExpressRoute

Hình dung một doanh nghiệp có router tại trung tâm dữ liệu, sử dụng mạng của connectivity provider để đến địa điểm kết nối với Microsoft, sau đó truy cập VNet trên Azure.

~~~text
Trung tâm dữ liệu doanh nghiệp
 +---------------------------+
 | Ứng dụng ERP, máy chủ DB  |
 | Router/Firewall biên      |
 +-------------+-------------+
               |
      Mạng WAN / provider
               |
     ExpressRoute peering location
               |
    Microsoft Enterprise Edge (MSEE)
      |                    |
      +--- BGP peering ----+
               |
       ExpressRoute circuit
               |
      ExpressRoute connection
               |
       ExpressRoute gateway
               |
  Azure VNet / hub / spoke VNet
      |                    |
  API/VM riêng        Private Endpoint
                           |
                      Dịch vụ PaaS
~~~

Đây là sơ đồ logic để giải thích thành phần. Trong triển khai thực tế, ExpressRoute có các đường và phiên BGP dự phòng; thứ tự và đường đi vật lý có thể khác theo provider, vùng và kiểu gateway.

### 3.1. ExpressRoute circuit

**Circuit** là tài nguyên Azure đại diện cho kết nối ExpressRoute đã được đặt hàng theo thông số như provider, peering location, băng thông và SKU. Circuit có thông tin định danh dịch vụ (**service key**) dùng để phối hợp với connectivity provider trong quá trình provisioning.

Tạo circuit trên Azure **chưa đồng nghĩa** kết nối vật lý đã sẵn sàng. Nhà cung cấp phải thực hiện các bước tương ứng để đưa circuit vào trạng thái có thể sử dụng. Nếu dùng Direct, việc chuẩn bị cổng và cross-connect có yêu cầu vận hành riêng.

### 3.2. Connectivity provider và peering location

**Connectivity provider** là tổ chức cung cấp đường truyền từ môi trường doanh nghiệp tới điểm kết nối với Microsoft theo mô hình dịch vụ đã chọn. **Peering location** là địa điểm mạng nơi kết nối trao đổi lưu lượng với mạng Microsoft; nó **không phải** Azure region chứa các máy ảo.

Ví dụ, một circuit có peering location tại Singapore có thể dùng để kết nối tới VNet ở một region Azure được SKU và phạm vi định tuyến cho phép. Cần kiểm tra khả năng phục vụ theo geography, SKU và chính sách dịch vụ hiện hành.

### 3.3. Microsoft Enterprise Edge (MSEE)

MSEE là thiết bị mạng ở phía Microsoft tham gia kết nối peering và trao đổi các tuyến BGP. Doanh nghiệp không tự cấu hình trực tiếp router MSEE như router nội bộ; những tham số cần thiết được khai báo qua cấu hình circuit/peering và phối hợp với provider.

### 3.4. Peering

**Peering** là cấu hình trao đổi tuyến và lưu lượng giữa mạng phía khách hàng/nhà cung cấp với Microsoft trên circuit. Các loại peering có mục đích khác nhau, đặc biệt là **Azure private peering** và **Microsoft peering**.

### 3.5. ExpressRoute virtual network gateway và connection

Trong kiến trúc VNet truyền thống, một **Virtual Network Gateway** có loại **ExpressRoute** được triển khai vào subnet chuyên dụng tên **GatewaySubnet**. Gateway kết nối VNet tới circuit thông qua **connection**. Circuit có trạng thái hoạt động không tự khiến VNet truy cập được mạng tại chỗ khi chưa có gateway, peering và kết nối phù hợp.

Trong một số kiến trúc Azure Virtual WAN, cách triển khai ExpressRoute gateway và kết nối tới hub có khác biệt với gateway của VNet thông thường. Cần chọn đúng mô hình hub trước khi triển khai.

### 3.6. BGP

**Border Gateway Protocol (BGP)** cho phép hai phía trao đổi thông tin về các prefix IP có thể đi tới. ExpressRoute sử dụng BGP cho peering. Nếu các prefix không được quảng bá, không được nhận hoặc bị lọc sai, circuit có thể hiện diện nhưng ứng dụng vẫn không kết nối được.

## 4. Private peering và Microsoft peering

Đây là sự phân biệt quan trọng nhất khi học ExpressRoute.

| Khả năng | Azure private peering | Microsoft peering |
|---|---|---|
| Mục đích | Kết nối mạng tại chỗ với địa chỉ riêng của workload trong Azure VNet | Kết nối đến một số endpoint dịch vụ công cộng của Microsoft theo điều kiện hỗ trợ |
| Điển hình | VM dùng private IP, backend riêng, truy cập Private Endpoint theo thiết kế | Một số dịch vụ Microsoft/Azure công cộng được hỗ trợ và các prefix được cho phép |
| Định tuyến | Trao đổi tuyến mạng riêng qua BGP, sau đó nối với VNet qua gateway/connection | Quảng bá và nhận những prefix hợp lệ theo yêu cầu Microsoft peering |
| Điều kiện | CIDR không chồng lấn, BGP, peering, VNet gateway/connection tương ứng | BGP, public IP prefix phù hợp, xác minh quyền sở hữu và các yêu cầu định tuyến, route filter nếu áp dụng |
| Mục đích không phù hợp | Không tự tạo kết nối tới mọi dịch vụ Microsoft công cộng | Không thay thế private peering để truy cập private IP trong VNet |

### Azure private peering

Đây là lựa chọn thường dùng để xây dựng **hybrid connectivity**. Ví dụ, mạng văn phòng sử dụng **172.20.0.0/16** và VNet Azure sử dụng **10.40.0.0/16**. Hai phía trao đổi tuyến qua BGP để lưu lượng tới private IP của workload Azure đi qua ExpressRoute.

Muốn truy cập Azure SQL Database hoặc Storage Account qua **Private Endpoint**, ứng dụng tại chỗ cần định tuyến tới IP riêng của endpoint và **DNS phải phân giải đúng về địa chỉ riêng**. Private peering không tự tạo Private Endpoint hoặc tự cấu hình DNS.

### Microsoft peering

Microsoft peering được sử dụng để tiếp cận những dịch vụ Microsoft có endpoint công cộng và được hỗ trợ qua ExpressRoute. Đây là cấu hình riêng có quy tắc về các public prefix, quảng bá tuyến và điều kiện kỹ thuật. Những endpoint có thể sử dụng còn phụ thuộc loại dịch vụ và chính sách hiện hành.

Không nên mặc định rằng Microsoft peering là đường kết nối được khuyến nghị cho toàn bộ lưu lượng **Microsoft 365**. Phần lớn triển khai Microsoft 365 được thiết kế để truy cập trực tiếp qua Internet; các ngoại lệ và yêu cầu qua ExpressRoute phải được đánh giá theo hướng dẫn riêng của Microsoft.

**Ghi nhớ:** Kết nối tới một cơ sở dữ liệu PaaS qua private IP của Private Endpoint thường thuộc thiết kế **private peering**, không phải chỉ vì dịch vụ PaaS đó có public endpoint mà phải dùng Microsoft peering.

## 5. Mô hình cung cấp và phạm vi dịch vụ

### ExpressRoute qua nhà cung cấp kết nối

Doanh nghiệp làm việc với một connectivity provider được hỗ trợ tại peering location. Nhà cung cấp quản lý phần mạng thuộc trách nhiệm của họ, trong khi doanh nghiệp quản lý kết nối nội bộ, router, firewall, hệ thống định tuyến và cấu hình Azure.

Trước khi đặt hàng, cần thống nhất loại dịch vụ, vị trí kết nối, băng thông, thời gian triển khai, địa chỉ BGP, VLAN, mô hình dự phòng và trách nhiệm xử lý sự cố giữa các bên.

### ExpressRoute Direct

ExpressRoute Direct là lựa chọn kết nối trực tiếp tới các cổng mạng Microsoft tại những địa điểm được hỗ trợ, thường phù hợp tổ chức có hạ tầng kết nối lớn hoặc nhu cầu kiểm soát trực tiếp cổng kết nối. Direct có yêu cầu riêng về cổng, kết nối vật lý, circuit được tạo trên port và khả năng bảo vệ ở lớp liên kết. Nó không phải là một công tắc giúp circuit hiện có tự trở thành kết nối trực tiếp.

### SKU, geography và lưu lượng dữ liệu

Các circuit ExpressRoute có những tùy chọn SKU, phạm vi định tuyến và hình thức tính phí, ví dụ **Local**, **Standard**, **Premium**, cùng các gói dữ liệu được cung cấp theo cấu hình phù hợp. Phạm vi kết nối giữa các vùng địa lý, số lượng VNet được liên kết, băng thông và tính năng hỗ trợ có thể khác nhau.

Hãy kiểm tra tài liệu SKU và bảng giá tại thời điểm triển khai, vì không phải tổ hợp provider, location, băng thông, SKU và hình thức tính phí nào cũng có sẵn ở mọi nơi.

### Global Reach và FastPath

- **ExpressRoute Global Reach** có thể hỗ trợ kết nối mạng tại chỗ ở những địa điểm khác nhau thông qua circuit tương ứng, khi đáp ứng điều kiện sản phẩm và phạm vi địa lý. Nó phục vụ kết nối giữa các site mạng, không thay thế thiết kế định tuyến hay phân đoạn mạng.
- **ExpressRoute FastPath** có thể tối ưu đường đi dữ liệu bằng cách bỏ qua ExpressRoute gateway trên data path cho những kịch bản/tài nguyên hỗ trợ. Gateway và connection vẫn có vai trò trong control plane, và FastPath có yêu cầu về SKU, cấu hình và dịch vụ. Không mặc định FastPath được bật cho mọi gateway.

## 6. BGP, CIDR và định tuyến trong ExpressRoute

Để lưu lượng đi đúng đường, cần lập kế hoạch địa chỉ và bảng tuyến trước khi đặt circuit.

### 6.1. Quy hoạch địa chỉ không chồng lấn

Ví dụ một doanh nghiệp có:

| Thành phần | CIDR | Vai trò |
|---|---|---|
| Trung tâm dữ liệu | 172.20.0.0/16 | Workload tại chỗ |
| VNet hub Azure | 10.40.0.0/16 | Gateway, firewall, dịch vụ mạng dùng chung |
| VNet sản xuất | 10.41.0.0/16 | API và dữ liệu ứng dụng |
| VNet phát triển | 10.42.0.0/16 | Workload phát triển |

Các dải này không chồng lấn. Khi thiết kế kết nối hub-and-spoke, cần xác định phương án peering, gateway transit, route table và firewall. Không nên giả định rằng cứ kết nối các VNet với một hub thì mọi VNet tự động quảng bá hoặc nhận đầy đủ tuyến qua ExpressRoute.

Nếu dữ liệu tại chỗ và Azure dùng những dải trùng nhau, định tuyến có thể mơ hồ hoặc bị giới hạn bởi quy tắc của dịch vụ. Nên giải quyết thiết kế địa chỉ trước khi kết nối hoặc dùng chiến lược chuyển đổi địa chỉ có kiểm soát trong những trường hợp được hỗ trợ.

### 6.2. BGP ASN, peering subnet và VLAN

Trong quá trình thiết lập private peering, các bên trao đổi và cấu hình:

- **ASN (Autonomous System Number)** của phía khách hàng/nhà cung cấp, theo yêu cầu dịch vụ.
- **VLAN ID** để phân biệt kênh peering trên kết nối mạng.
- **Peering address prefixes** dùng cho các phiên BGP; với IPv4, thiết kế thường cần hai dải /30 riêng cho đường primary và secondary.
- **Các prefix mạng cần quảng bá**, ví dụ mạng tại chỗ và các tuyến Azure được gateway truyền về.
- **Chính sách BGP**, bao gồm lọc tuyến, ưu tiên đường đi, điều kiện failover và giới hạn tuyến theo hỗ trợ thực tế.

Địa chỉ dùng cho **BGP peering** khác với không gian địa chỉ ứng dụng trong VNet. Không lấy một dải CIDR bất kỳ rồi dùng đồng thời cho peering và workload. Hãy phối hợp chính xác với provider và hướng dẫn thông số của circuit.

### 6.3. Đường tuyến đi và đường tuyến về

Giả sử ứng dụng tại chỗ **172.20.10.25** gọi API ở Azure **10.41.2.10**. Cả hai phía đều cần biết đường đến mạng đối diện:

1. Router tại chỗ có route tới **10.41.0.0/16** qua ExpressRoute.
2. Azure biết đường trở về **172.20.0.0/16** thông qua BGP/gateway và cấu hình định tuyến phù hợp.
3. NSG, firewall, security appliance và hệ điều hành cho phép kết nối được yêu cầu.
4. Ứng dụng sử dụng đúng địa chỉ hoặc tên DNS và có quyền xác thực ở tầng ứng dụng.

**Circuit hoạt động không đảm bảo luồng ứng dụng thành công.** Một lỗi cấu hình ở bất kỳ thành phần nào trong bốn bước cũng có thể gây timeout hoặc kết nối bị từ chối.

### 6.4. Default route và đường Internet

Nếu mạng tại chỗ quảng bá tuyến mặc định **0.0.0.0/0** và Azure chấp nhận theo kiến trúc, luồng outbound từ workload Azure có thể bị đưa về mạng tại chỗ. Điều này có thể hợp lệ trong mô hình kiểm soát Internet tập trung (*forced tunneling*), nhưng cũng có thể làm hỏng đường truy cập dịch vụ, tăng độ trễ hoặc tạo kết nối bất đối xứng.

Trước khi triển khai default route hoặc UDR thay đổi next hop, phải đánh giá đường trả về, firewall, DNS, truy cập endpoint nền tảng và khả năng phục hồi. Chỉ áp dụng khi topology/gateway hỗ trợ và đã kiểm thử.

## 7. Từ circuit tới VNet: cách luồng kết nối được thiết lập

Với thiết kế VNet truyền thống, kết nối hoạt động sau khi nhiều bước độc lập hoàn thành:

~~~mermaid
flowchart TD
  A["Chọn provider, peering location, SKU, bandwidth"] --> B["Tạo ExpressRoute circuit"]
  B --> C["Phối hợp service key để provision kết nối"]
  C --> D["Cấu hình Azure private peering và BGP"]
  D --> E["Tạo GatewaySubnet và ExpressRoute gateway"]
  E --> F["Tạo connection từ gateway tới circuit"]
  F --> G["Kiểm tra BGP routes, DNS và luồng ứng dụng"]
  G --> H["Giám sát, diễn tập failover, quản lý chi phí"]
~~~

Trong thực tế, một số công việc có thể chuẩn bị song song. Tuy nhiên, việc kết nối circuit tới VNet cần các thành phần và điều kiện tương thích sẵn sàng.

### GatewaySubnet

Azure yêu cầu subnet có tên **GatewaySubnet** để đặt Virtual Network Gateway của VNet. Subnet này cần đủ dải địa chỉ để triển khai gateway và mở rộng theo yêu cầu dịch vụ; nhiều kiến trúc dùng kích thước **/27 hoặc lớn hơn về số địa chỉ** cho khả năng phát triển. Luôn xác nhận kích thước tối thiểu và hướng dẫn mới nhất cho SKU dự định.

GatewaySubnet dành cho gateway, **không đặt VM hoặc dịch vụ ứng dụng thông thường vào subnet này**. Không gắn NSG hoặc cấu hình UDR tùy tiện có thể làm gián đoạn hoạt động gateway. Những quy tắc định tuyến, bảo mật được Microsoft cho phép cho gateway cần được kiểm tra riêng trước khi áp dụng.

### ExpressRoute gateway

Gateway có loại ExpressRoute xử lý kết nối giữa VNet và circuit, đồng thời tham gia phân phối thông tin định tuyến. Cần chọn loại và SKU hỗ trợ thông lượng, zone và tính năng cần thiết. Một gateway không phải bản thân circuit và không thể thay thế bước provisioning với nhà cung cấp.

### Hub-and-spoke

Trong kiến trúc nhiều workload, ExpressRoute gateway thường được đặt ở **hub VNet**. Các **spoke VNet** có thể dùng VNet peering cùng cấu hình **gateway transit/remote gateway** để truy cập mạng tại chỗ khi điều kiện topology cho phép.

Việc dùng chung gateway không làm mọi spoke tự động kết nối theo ý muốn. Cần rà soát các route, NSG, firewall, định tuyến giữa spoke và kết nối tới tài nguyên dùng chung.

## 8. Quy trình triển khai ExpressRoute an toàn

Phần này hướng dẫn trình tự thực hiện. Vì ExpressRoute liên quan tới nhà cung cấp mạng và có thể phát sinh phí đáng kể, ví dụ không yêu cầu người học tự đặt circuit thực trên subscription cá nhân.

### Bước 1: xác định yêu cầu nghiệp vụ và phạm vi

Ghi rõ:

- Các site tại chỗ và các Azure region/VNet cần kết nối.
- Lưu lượng dự kiến, băng thông giờ cao điểm, hướng truyền dữ liệu và yêu cầu về độ trễ.
- Workload quan trọng, dữ liệu nhạy cảm, thời gian gián đoạn chấp nhận được và yêu cầu về dự phòng.
- Cấu trúc tenant, subscription, resource group, quyền quản trị và trách nhiệm mỗi nhóm.
- Những private endpoint, DNS zone, firewall, route table, VNet peering đã có.
- Cấu hình gateway hoặc Virtual WAN hiện tại, để tránh trùng lặp kiến trúc.

### Bước 2: lựa chọn hình thức kết nối

Làm việc với provider hoặc đội kết nối Direct để xác định **peering location, bandwidth, SKU, loại dữ liệu, đường dẫn vật lý, thời gian cung cấp và chi phí**. Xác nhận khả năng phục vụ các Azure region mong muốn và cách bố trí đường primary/secondary. Nếu cần tránh phụ thuộc cùng một nhà cung cấp hoặc địa điểm, đánh giá phương án có nhiều circuit độc lập.

### Bước 3: tạo ExpressRoute circuit

Trong Azure portal:

1. Chọn đúng **subscription** và **resource group** quản lý kết nối.
2. Tìm **ExpressRoute circuits**, chọn thao tác tạo circuit.
3. Cấu hình tên, region tài nguyên quản lý, provider, peering location, băng thông và SKU/phương án tính phí được hỗ trợ.
4. Kiểm tra lựa chọn trước khi tạo, vì một số thông số và cam kết có giới hạn thay đổi.
5. Ghi lại **service key** qua kênh làm việc được kiểm soát để gửi cho nhà cung cấp phục vụ provisioning.

Việc tạo circuit có thể phát sinh chi phí ngay cả khi chưa chạy lưu lượng. Cần có phê duyệt kỹ thuật và chi phí trước khi thực hiện.

### Bước 4: provider provision kết nối

Phối hợp với provider để kết nối hạ tầng tới peering location và cập nhật trạng thái dịch vụ. Theo dõi **provider provisioning status** và **circuit provisioning state** trong portal. Trạng thái resource ARM thành công chưa đủ để kết luận provider đã hoàn thành đường truyền.

Kiểm tra địa chỉ peering, VLAN, ASN, băng thông và hai hướng kết nối. Ghi nhận đầu mối hỗ trợ của provider, nhà mạng trung gian và Microsoft.

### Bước 5: cấu hình private peering/BGP

Cấu hình **Azure private peering** nếu mục tiêu là truy cập các IP riêng trong VNet. Hai phía phải thống nhất ASN, peering prefix, VLAN và định tuyến. Xác minh các phiên BGP dự phòng được thiết lập và các prefix công bố đúng với kế hoạch.

Không quảng bá các prefix không được phép hoặc tuyến mặc định ngoài kế hoạch; sai sót có thể làm lưu lượng của hệ thống khác bị định tuyến qua ExpressRoute.

### Bước 6: tạo gateway và kết nối tới circuit

Tạo **GatewaySubnet** trong VNet hub; triển khai **ExpressRoute virtual network gateway** với SKU phù hợp. Sau đó tạo connection từ gateway tới circuit. Nếu circuit và VNet thuộc các subscription khác nhau, có thể cần **authorization** và các bước liên kết tương ứng theo mô hình quản trị được hỗ trợ.

Sau khi kết nối, xác nhận BGP route được trao đổi, gateway khỏe mạnh và VNet có đường về các prefix tại chỗ. Với spoke VNet, kiểm tra peering và gateway transit nếu có.

### Bước 7: kiểm tra luồng ứng dụng

Kiểm tra có mục tiêu thay vì chỉ ping:

1. Từ máy tại chỗ, phân giải DNS của API hoặc tài nguyên Azure.
2. Xem route tới private IP đích có đi qua đường dự kiến hay không.
3. Kiểm tra kết nối TCP/TLS tới cổng dịch vụ được cấp phép.
4. Từ Azure, xác minh đường trả về tới mạng tại chỗ.
5. Kiểm tra NSG, firewall, rule ứng dụng và quyền truy cập dữ liệu.
6. Đo độ trễ/throughput phù hợp với workload và so sánh với mức baseline.

Một số dịch vụ chặn ICMP, nên **ping thất bại không tự động chứng minh ExpressRoute bị lỗi**. Dùng kiểm tra ở cổng ứng dụng và dữ liệu route để có kết luận đáng tin cậy.

### Bước 8: giám sát và bàn giao vận hành

Thiết lập metric/cảnh báo cho circuit, peering, gateway và các thành phần mạng liên quan. Lưu sơ đồ topology, danh sách CIDR, ASN, VLAN, gateway, chủ sở hữu, hợp đồng provider, trình tự xử lý sự cố và quy trình failover. Thiết lập ngân sách theo subscription, đối chiếu phí circuit, gateway, đường truyền provider và các dịch vụ bảo mật.

## 9. Kiểm tra kết nối bằng Azure CLI (chế độ đọc)

Các lệnh dưới đây dùng để **xem trạng thái**, không tạo hay thay đổi tài nguyên. Cần đăng nhập vào Azure và có quyền đọc tại subscription chứa circuit hoặc gateway.

### Xác nhận subscription

~~~bash
az login
az account show --query "{name:name,id:id}" --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### Liệt kê circuit trong resource group

~~~bash
az network express-route list \
  --resource-group "rg-network-hub" \
  --output table
~~~

### Xem tình trạng một circuit

~~~bash
az network express-route show \
  --resource-group "rg-network-hub" \
  --name "er-circuit-prod" \
  --query "{name:name,provisioningState:provisioningState,providerState:serviceProviderProvisioningState,peeringLocation:serviceProviderProperties.peeringLocation,bandwidthMbps:serviceProviderProperties.bandwidthInMbps}" \
  --output json
~~~

Các thuộc tính trong output có thể khác theo hình thức cung cấp và phiên bản API. Quan sát cả tình trạng Azure Resource Manager và trạng thái provision của provider.

### Xem cấu hình peering

~~~bash
az network express-route peering list \
  --resource-group "rg-network-hub" \
  --circuit-name "er-circuit-prod" \
  --output table
~~~

### Xem ExpressRoute gateway trong hub VNet

~~~bash
az network vnet-gateway show \
  --resource-group "rg-network-hub" \
  --name "ergw-hub-prod" \
  --query "{name:name,gatewayType:gatewayType,provisioningState:provisioningState,sku:sku.name}" \
  --output json
~~~

**Lưu ý:** tên resource group, circuit và gateway là dữ liệu minh họa. Trong Azure Virtual WAN, gateway có loại tài nguyên và lệnh quản lý khác với virtual network gateway. Khi kiểm tra phải xác nhận đang dùng kiến trúc nào.

Những lệnh trên **không thay thế** việc kiểm tra trạng thái BGP session, tuyến nhận/quảng bá và kết nối ứng dụng từ mạng tại chỗ. Khi cần chẩn đoán sâu, kết hợp portal, metric, route inspection, công cụ của provider và mạng nội bộ.

## 10. Bảo mật ExpressRoute và kiểm soát truy cập

### Đường riêng không phải mã hóa mặc định

ExpressRoute dùng kết nối riêng thay cho đường Internet công cộng, nhưng lưu lượng **không tự động được mã hóa đầu cuối**. Với dữ liệu nhạy cảm, hãy triển khai TLS và các biện pháp bảo vệ ở lớp ứng dụng, hoặc xem xét thêm IPsec/MACsec khi mô hình và dịch vụ hỗ trợ.

Mạng riêng vẫn có thể bị ảnh hưởng nếu tài khoản quản trị bị chiếm quyền, firewall cho phép quá rộng hoặc ứng dụng có lỗ hổng. Vì vậy cần kết hợp các lớp:

| Lớp kiểm soát | Ví dụ |
|---|---|
| Danh tính và phân quyền | Microsoft Entra ID, Azure RBAC, quyền tối thiểu |
| Mạng | Azure Firewall, NSG, UDR, phân đoạn hub/spoke |
| Kết nối ứng dụng | TLS, xác thực API, quản lý chứng chỉ |
| Bí mật và khóa | Azure Key Vault, chính sách truy cập phù hợp |
| Dữ liệu | Mã hóa khi lưu, quyền cơ sở dữ liệu, sao lưu |
| Theo dõi | Azure Monitor, log firewall, metric gateway/circuit |

### Private Endpoint và DNS

Khi ứng dụng tại chỗ dùng ExpressRoute để truy cập một dịch vụ PaaS qua **Private Endpoint**, đường mạng phải đi tới IP riêng trong VNet và tên dịch vụ cần phân giải về IP đúng. Azure Private DNS Zone, DNS resolver và cơ chế conditional forwarding có thể được sử dụng tùy thiết kế.

Ví dụ, nếu ứng dụng tại chỗ truy cập tài khoản lưu trữ bằng FQDN nhưng DNS vẫn trả về public IP, kết nối có thể đi sai đường hoặc bị chặn do chính sách firewall. Phải kiểm tra DNS từ **máy khách thực tế**, không chỉ từ một máy trong VNet.

### Tối thiểu hóa quyền và phạm vi route

Chỉ quảng bá prefix cần thiết, lọc tuyến theo chính sách mạng và kiểm soát quyền tới từng subnet/tài nguyên. Không tạo tuyến cho mọi mạng nội bộ nếu workload chỉ cần truy cập một nhóm dịch vụ nhỏ. Đối với hub-and-spoke, xác định rõ firewall nào nhận lưu lượng và đường trả về phải đi cùng quy tắc định tuyến mong muốn.

## 11. Thiết kế tính sẵn sàng và dự phòng

ExpressRoute hỗ trợ cấu trúc đường truyền dự phòng tới mạng Microsoft. Mỗi circuit có cơ chế kết nối và phiên peering dự phòng theo thiết kế của dịch vụ và provider. Tuy nhiên, **một circuit không loại bỏ mọi điểm lỗi**, đặc biệt nếu hai kết nối cùng phụ thuộc một địa điểm, tuyến cáp hoặc nhà cung cấp.

Các cấp độ dự phòng cần xem xét:

1. **Dự phòng bên trong một circuit:** hai đường/phiên BGP theo cấu trúc ExpressRoute; nhà cung cấp phải triển khai đúng yêu cầu.
2. **Dự phòng kết nối độc lập:** cân nhắc hai circuit qua đường truyền, provider hoặc peering location khác nhau nếu mục tiêu sẵn sàng yêu cầu.
3. **Dự phòng gateway và VNet:** chọn SKU, zone và topology phù hợp với khả năng sẵn sàng.
4. **Dự phòng VPN:** có thể thiết kế VPN Gateway như đường thay thế trong những topology hỗ trợ coexistence, với chính sách định tuyến và BGP đã kiểm tra.
5. **Dự phòng ứng dụng:** nhiều instance, cơ sở dữ liệu phù hợp, retry có giới hạn, circuit breaker và kế hoạch khôi phục.

### Cần kiểm thử failover thực sự

Kịch bản diễn tập có thể bao gồm mất một liên kết, ngắt một phiên BGP hoặc hỏng một đường provider dưới sự phối hợp của nhóm mạng. Ghi lại tuyến nào được chọn, thời gian chuyển đổi, ảnh hưởng tới kết nối đang mở và việc lưu lượng có quay trở lại đường chính hay không.

Không thực hiện mô phỏng ngắt tuyến trên production nếu chưa có kế hoạch và quyền phê duyệt. BGP failover có thể có thời gian hội tụ và gây gián đoạn kết nối đang hoạt động. Một kiến trúc có hai circuit chỉ đạt mục tiêu dự phòng khi đã kiểm tra **cả hướng đi lẫn hướng về**, tránh định tuyến bất đối xứng qua firewall stateful.

## 12. Theo dõi và xử lý sự cố

Khi người dùng báo không kết nối được ERP tại chỗ tới Azure, cần phân tách vấn đề thành các lớp:

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Circuit chưa sẵn sàng | Provider chưa provision hoặc circuit có trạng thái lỗi | Xem circuit provisioning state, provider state và liên hệ provider |
| BGP session không established | ASN, VLAN, peering prefix, cổng vật lý hoặc cấu hình router sai | So sánh tham số hai phía, kiểm tra trạng thái BGP primary/secondary |
| BGP up nhưng không có tuyến Azure | Private peering, gateway connection hoặc route propagation chưa đúng | Kiểm tra prefix được quảng bá/nhận, connection, gateway và topology VNet |
| Azure không có đường về on-premises | Prefix tại chỗ bị lọc hoặc chưa được quảng bá | Xem BGP advertised/learned routes và effective routes |
| Kết nối tới VM bị timeout | NSG, UDR, firewall hoặc hệ điều hành chặn | Kiểm tra route, cổng đích, firewall và Network Watcher |
| PaaS dùng private endpoint không truy cập được | DNS phân giải ra public IP hoặc đường tới private IP không hợp lệ | Kiểm tra DNS từ on-premises, private DNS và tuyến tới subnet endpoint |
| Chậm hoặc mất gói | Nghẽn đường provider, gateway/circuit, ứng dụng hoặc thiết bị bảo mật | Đối chiếu metric lưu lượng, lỗi, độ trễ, utilization và log |
| Chỉ lỗi khi failover | Ưu tiên BGP, tuyến trả về hoặc dự phòng chưa hoàn chỉnh | Kiểm tra đường trước/sau failover và cấu hình hai phía |
| Không kết nối được spoke | Gateway transit, peering hoặc firewall/UDR chưa đúng | Rà soát topology hub-spoke và tuyến effective của spoke |

### Trình tự điều tra đề xuất

1. **Khoanh vùng:** site nào, VNet nào, dịch vụ nào, bắt đầu từ khi nào, toàn bộ hay một phần lưu lượng?
2. **Kiểm tra provisioning:** circuit, provider, peering và connection/gateway có trạng thái bình thường không?
3. **Kiểm tra BGP:** có đủ các phiên, đúng prefix, đúng hướng đi/về?
4. **Kiểm tra DNS:** FQDN đang trả về IP nào từ máy nguồn thực tế?
5. **Kiểm tra data path:** NSG, UDR, firewall, routing appliance, port và ứng dụng.
6. **Kiểm tra tải và dự phòng:** metric, log, packet loss và thay đổi gần đây.
7. **Đối chiếu trách nhiệm:** lỗi thuộc Azure, provider, mạng nội bộ hay ứng dụng để chuyển đúng nhóm hỗ trợ.

Azure Monitor và các công cụ giám sát mạng giúp phát hiện biến động lưu lượng, trạng thái và sức khỏe tài nguyên. Trong sự cố provider, cần lưu circuit identifier, peering location, thời điểm lỗi, trạng thái BGP và thông tin liên hệ nhà mạng để đối chiếu.

## 13. Chi phí và những điều cần kiểm soát

ExpressRoute là quyết định kiến trúc kèm cam kết vận hành và chi phí, không chỉ là một cấu hình kỹ thuật. Những khoản chi có thể bao gồm:

- **Circuit hoặc port:** tính phí theo loại ExpressRoute, băng thông, SKU, khu vực và hình thức thanh toán.
- **Connectivity provider:** đường truyền WAN, cross-connect, phí thiết lập và hợp đồng mạng riêng.
- **ExpressRoute gateway:** tài nguyên gateway có phí riêng theo SKU/thời gian sử dụng, kể cả khi lưu lượng thấp.
- **Truyền dữ liệu:** khác nhau theo lựa chọn metered/unlimited, phạm vi định tuyến và hướng truyền được tính phí.
- **Dịch vụ mạng đi kèm:** Azure Firewall, Private Endpoint, DNS, VNet peering, monitoring và các thành phần cần thiết khác.
- **Vận hành:** quản trị router/BGP, kiểm thử failover, bảo trì, hỗ trợ và thay đổi kiến trúc.

Trước khi tạo circuit, nhóm kiến trúc cần ước tính lưu lượng hai chiều, phân tích traffic burst, kiểm tra bandwidth phù hợp, so sánh với VPN và hiểu chi phí provider ngoài hóa đơn Azure. Theo dõi bằng **Azure Cost Management**, ngân sách và tag gắn chủ sở hữu, nhưng lưu ý hóa đơn của provider có thể nằm ngoài Azure.

Không khẳng định hình thức trả phí nào luôn rẻ hơn. Giá, phạm vi kết nối và giới hạn thay đổi theo SKU, địa điểm và thời điểm, nên phải đối chiếu bảng giá và hợp đồng hiện hành.

## 14. Tình huống thực tế: kết nối ERP tại chỗ với hệ thống bán hàng trên Azure

Một doanh nghiệp có hệ thống ERP tại trung tâm dữ liệu và một ứng dụng đặt hàng triển khai trên Azure:

- **Mạng tại chỗ:** 172.20.0.0/16, chứa ERP và cơ sở dữ liệu nghiệp vụ.
- **Hub VNet:** 10.40.0.0/16, chứa ExpressRoute gateway và firewall khi được thiết kế.
- **Spoke VNet sản xuất:** 10.41.0.0/16, chứa API ứng dụng.
- **Dịch vụ dữ liệu:** Azure SQL Database và Storage dùng Private Endpoint nơi phù hợp.
- **Kết nối:** ExpressRoute private peering tới hub, định tuyến có kiểm soát tới spoke.

Mục tiêu là cho phép API trên Azure gọi dịch vụ ERP tại chỗ, đồng thời nhân viên nội bộ truy cập một số endpoint ứng dụng riêng trong Azure.

### Thiết kế đề xuất

1. Kiểm kê mọi CIDR hiện có và bảo đảm **172.20.0.0/16**, **10.40.0.0/16**, **10.41.0.0/16** không chồng lấn với các mạng cần kết nối.
2. Chọn provider, địa điểm peering, bandwidth, SKU và kế hoạch đường dự phòng.
3. Thiết lập private peering BGP, cấu hình gateway/connection cho hub và gateway transit cho spoke nếu topology hỗ trợ.
4. Chỉ quảng bá các prefix cần thiết; dùng firewall và NSG để giới hạn hướng/cổng giữa API với ERP.
5. Dùng DNS phù hợp để tên ERP tại chỗ và tên Private Endpoint trong Azure phân giải ra địa chỉ chính xác.
6. Cấp quyền truy cập dữ liệu ở tầng ứng dụng, sử dụng TLS cho kết nối nhạy cảm và quản lý bí mật bằng công cụ phù hợp.
7. Kiểm thử hai chiều: API gọi ERP, ứng dụng tại chỗ truy cập Private Endpoint được phép, lưu lượng khác bị chặn.
8. Giám sát circuit/gateway/provider; diễn tập tình huống lỗi đường truyền và đo tác động nghiệp vụ.

### Bảng kiểm tra nghiệm thu

| Tiêu chí | Bằng chứng mong đợi |
|---|---|
| Circuit và provider | Provisioning hoàn tất, thông số đúng hợp đồng |
| Peering BGP | Các phiên yêu cầu established, tuyến hai chiều đúng kế hoạch |
| Gateway và connection | Trạng thái hoạt động, liên kết VNet đúng circuit |
| DNS | FQDN ERP và Private Endpoint phân giải đúng từ máy nguồn |
| Kiểm soát truy cập | Chỉ những kết nối được phép đi qua firewall/NSG và ứng dụng |
| Tải và độ trễ | Kết quả kiểm thử phù hợp SLO nghiệp vụ |
| Dự phòng | Kịch bản mất một đường có phương án duy trì/khôi phục được kiểm chứng |
| Giám sát và chi phí | Metric, alert, chủ sở hữu, ngân sách và hợp đồng provider đã được ghi nhận |

## 15. Những hiểu lầm thường gặp

**“ExpressRoute tự mã hóa toàn bộ dữ liệu.”** Không. Đây là đường kết nối riêng; cần cân nhắc TLS/IPsec hoặc MACsec theo cấu hình hỗ trợ để bảo vệ dữ liệu trên đường truyền.

**“Tạo circuit là VNet đã kết nối tới mạng tại chỗ.”** Chưa. Cần provider provision đường truyền, peering/BGP, gateway hoặc kiến trúc kết nối phù hợp và connection tới VNet/hub.

**“Peering location chính là Azure region của ứng dụng.”** Không. Địa điểm peering là nơi kết nối mạng Microsoft; region là vị trí triển khai tài nguyên Azure.

**“Microsoft peering dùng để truy cập mọi private IP của VNet.”** Không. Private IP VNet là trường hợp điển hình của Azure private peering; Microsoft peering áp dụng cho các dịch vụ/endpoint công cộng được hỗ trợ.

**“Circuit up nghĩa là ứng dụng sẽ hoạt động.”** Cần tuyến đi và về, DNS, firewall, NSG và ứng dụng hoạt động. Một phiên BGP healthy không bảo đảm tầng ứng dụng thành công.

**“Có hai phiên BGP thì không cần kế hoạch dự phòng.”** Dự phòng nội bộ một circuit không giải quyết mọi lỗi của provider, địa điểm hoặc tuyến vật lý.

**“ExpressRoute lúc nào cũng rẻ hơn VPN.”** Chi phí ExpressRoute gồm nhiều thành phần và thường phụ thuộc hợp đồng provider. Phải đánh giá dựa trên lưu lượng, yêu cầu SLO và chi phí vận hành.

**“Có ExpressRoute thì không cần Private Endpoint hoặc DNS nội bộ.”** ExpressRoute cung cấp tuyến kết nối; muốn đi tới PaaS qua private IP vẫn phải thiết kế endpoint, DNS và quyền truy cập.

## 16. Câu hỏi tự kiểm tra

1. ExpressRoute giúp giải quyết vấn đề gì khi kết nối trung tâm dữ liệu với Azure? Nêu hai tình huống nên cân nhắc sử dụng.
2. Khác biệt chính giữa ExpressRoute và VPN site-to-site về đường truyền, mã hóa và chi phí là gì?
3. Circuit, peering và ExpressRoute gateway đảm nhiệm những vai trò riêng nào?
4. Vì sao cần phân biệt peering location với Azure region?
5. Khi nào dùng Azure private peering? Microsoft peering dành cho loại endpoint nào?
6. Điều gì xảy ra nếu router tại chỗ không nhận được prefix Azure hoặc Azure không có tuyến quay lại mạng tại chỗ?
7. Vì sao **Private Endpoint** cần cấu hình **DNS** đúng dù ExpressRoute private peering đã hoạt động?
8. Nếu circuit healthy nhưng VM tại chỗ không gọi được API tại Azure qua HTTPS, bạn sẽ kiểm tra các lớp nào theo thứ tự?
9. Vì sao một circuit có đường primary/secondary vẫn có thể chưa đáp ứng yêu cầu sẵn sàng cao?
10. Những thành phần chi phí nào phải được tính khi so sánh ExpressRoute và VPN?
11. Khi dùng hub-and-spoke, cần kiểm tra gì để spoke kết nối được mạng tại chỗ mà vẫn giới hạn luồng truy cập?
12. Hãy thiết kế một checklist nghiệm thu ExpressRoute cho workload ERP và API bán hàng trước khi đưa vào production.

## Tài liệu tham khảo

- Microsoft Learn — *What is Azure ExpressRoute?*: https://learn.microsoft.com/azure/expressroute/expressroute-introduction
- Microsoft Learn — *ExpressRoute circuits and peerings*: https://learn.microsoft.com/azure/expressroute/expressroute-circuit-peering
- Microsoft Learn — *Connect a virtual network to an ExpressRoute circuit*: https://learn.microsoft.com/azure/expressroute/expressroute-howto-linkvnet-portal-resource-manager
- Microsoft Learn — *ExpressRoute routing requirements*: https://learn.microsoft.com/azure/expressroute/expressroute-routing
- Microsoft Learn — *ExpressRoute frequently asked questions*: https://learn.microsoft.com/azure/expressroute/expressroute-faqs
- Microsoft Learn — *ExpressRoute documentation*: https://learn.microsoft.com/azure/expressroute/
