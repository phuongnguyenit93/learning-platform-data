# Kết nối trung tâm dữ liệu qua VPN và đường truyền riêng

## Mục tiêu học tập

Khi thiết kế **Cloud Architecture**, không phải mọi ứng dụng đều có thể chuyển toàn bộ lên public cloud trong một lần. Một số hệ thống vẫn đặt cơ sở dữ liệu, thiết bị chuyên dụng, phần mềm kế toán hoặc kho dữ liệu trong trung tâm dữ liệu (*on-premises data center*). Ứng dụng trên đám mây cần trao đổi dữ liệu an toàn và ổn định với các hệ thống đó. Kiến trúc này thường được gọi là **kết nối hybrid**.

Bài học thuộc phần **Kiến trúc mạng**, tập trung vào hai cách kết nối phổ biến: **VPN site-to-site dựa trên IPsec** và **đường truyền riêng** đến nhà cung cấp cloud. Việc lựa chọn phải xét đồng thời mạng, compute, dữ liệu, mô hình triển khai, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo nguyên tắc **Well-Architected**.

Sau bài học, bạn có thể:

- Giải thích đường đi của lưu lượng giữa trung tâm dữ liệu và mạng riêng trên cloud.
- Phân biệt VPN site-to-site qua Internet với kết nối riêng qua nhà mạng và cổng kết nối của nhà cung cấp cloud.
- Thiết kế địa chỉ IP, định tuyến, DNS, firewall và cơ chế mã hóa cho kết nối hybrid.
- Phân tích trade-off về thông lượng, độ trễ, dự phòng, bảo mật, chi phí và độ phức tạp.
- Xác định khi nào nên dùng VPN, đường truyền riêng hoặc **đường truyền riêng kết hợp VPN dự phòng**.
- Viết kịch bản chất lượng đo được và thiết kế bài kiểm thử failover, hiệu năng và khôi phục.
- Ghi nhận quyết định kiến trúc bằng ADR và đánh giá theo Well-Architected.

## 1. Bối cảnh: vì sao cần kết nối trung tâm dữ liệu với cloud?

Giả sử một công ty có ba nhóm hệ thống:

1. **Trong trung tâm dữ liệu:** database ERP, hệ thống quản lý kho, dịch vụ định danh nội bộ và các ứng dụng chưa thể di chuyển.
2. **Trên cloud:** API Java/Spring Boot, dịch vụ xử lý đơn hàng, worker đồng bộ dữ liệu và hệ thống phân tích.
3. **Người dùng và đối tác:** truy cập qua Internet hoặc mạng doanh nghiệp bằng các kênh được kiểm soát.

Một API đặt hàng trên cloud có thể cần hỏi tình trạng tồn kho ở trung tâm dữ liệu. Nếu đường kết nối đứt, API có thể chậm hoặc không thể xác nhận đơn. Một kênh kết nối hybrid vì vậy trở thành **phụ thuộc quan trọng của luồng nghiệp vụ**, chứ không chỉ là vấn đề kéo dây mạng.

Khi thu thập yêu cầu, cần làm rõ:

| Câu hỏi nghiệp vụ | Điều ảnh hưởng tới kiến trúc |
| --- | --- |
| Những ứng dụng nào cần trao đổi dữ liệu? | Các nguồn/đích được phép đi qua kênh kết nối. |
| Dữ liệu có nhạy cảm hoặc chịu quy định cư trú dữ liệu không? | Mã hóa, quyền truy cập, vùng đặt dữ liệu và audit. |
| Tốc độ thay đổi và lưu lượng dự kiến? | Băng thông, cơ chế đồng bộ, kích thước gói và chi phí dữ liệu. |
| Kết nối cần hoạt động vào thời điểm nào? | SLO, lịch bảo trì, kênh dự phòng và trực vận hành. |
| Chậm hoặc mất kết nối gây hậu quả gì? | Timeout, cache, hàng đợi, chế độ suy giảm và RTO. |
| Khi mất kết nối, có thể tạm dừng ghi hoặc đồng bộ sau không? | Tính nhất quán dữ liệu và chiến lược phục hồi. |

**Điểm quan trọng:** Một tuyến mạng tốt chưa đảm bảo ứng dụng tốt. Cần đo cả hành trình giao dịch, bao gồm DNS, xác thực, service trên cloud, firewall, kết nối về trung tâm dữ liệu và hệ thống dữ liệu cuối cùng.

## 2. Bức tranh kiến trúc hybrid cơ bản

~~~mermaid
flowchart LR
    U["Người dùng"] --> EDGE["HTTPS / Load balancer"]
    subgraph CLOUD["Cloud: mạng riêng 10.40.0.0/16"]
        EDGE --> APP["Ứng dụng Spring Boot"]
        APP --> GW["Cloud VPN hoặc private gateway"]
        APP --> DATA[("Database trên cloud")]
    end
    GW <-->|"Kênh hybrid được kiểm soát"| ONGW
    subgraph DC["Trung tâm dữ liệu: 10.20.0.0/16"]
        ONGW["Edge router / firewall"]
        ONGW --> ERP["ERP / Inventory API"]
        ONGW --> LEGACY[("Database nội bộ")]
    end
~~~

Đây là sơ đồ logic, không hàm ý mọi database trong trung tâm dữ liệu có thể được truy cập trực tiếp. Trong thiết kế tốt, nên cân nhắc một **API hoặc lớp tích hợp có kiểm soát** trước dữ liệu quan trọng, thay vì mở kết nối database từ nhiều workload cloud.

Các thành phần cơ bản gồm:

- **Mạng cloud riêng:** VPC, VNet hoặc mô hình tương đương, có subnet và route table.
- **Đầu mạng tại trung tâm dữ liệu:** Router/firewall hỗ trợ IPsec, BGP, phân vùng và HA.
- **Đầu kết nối cloud:** VPN gateway, virtual gateway, transit/hub gateway hoặc điểm kết nối riêng theo nhà cung cấp.
- **Đường dẫn dữ liệu:** Internet được mã hóa đối với VPN; đường truyền qua nhà mạng/cổng riêng đối với private connection.
- **Điều khiển:** Routing, DNS, firewall/ACL, danh tính, certificate/secret và giám sát.
- **Ứng dụng:** Timeout, retry, circuit breaker, cache và xử lý khi một hệ thống phụ thuộc không sẵn sàng.

Phải tách **data plane** (các gói dữ liệu thực đi qua) khỏi **control plane** (cấu hình, định tuyến, quản lý tài nguyên). Một sự cố control plane không nhất thiết khiến mọi lưu lượng hiện hữu dừng ngay, nhưng có thể ngăn thay đổi route hoặc tạo tài nguyên khi cần khôi phục.

## 3. VPN site-to-site: kết nối được mã hóa qua mạng công cộng

### 3.1. Cơ chế hoạt động

**Site-to-site VPN** tạo đường hầm giữa thiết bị mạng tại trung tâm dữ liệu và gateway cloud. Cách triển khai phổ biến sử dụng **IPsec** để xác thực các đầu cuối và bảo vệ gói IP đi qua mạng không đáng tin cậy như Internet.

~~~mermaid
flowchart LR
    subgraph DC["Trung tâm dữ liệu"]
        DCNET["Mạng 10.20.0.0/16"] --> ROUTER["Router / Firewall"]
    end
    ROUTER --> TUNNEL["IPsec Tunnel qua Internet"]
    TUNNEL --> VPNGW["Cloud VPN Gateway"]
    subgraph CLOUD["Cloud"]
        VPNGW --> PRIVATE["Private subnet 10.40.0.0/16"]
    end
~~~

Ở mức khái niệm, một kết nối thường trải qua:

1. Hai đầu cuối xác nhận khả năng kết nối và thông số bảo mật tương thích.
2. **IKE** thiết lập/thương lượng các security association; có thể sử dụng IKEv2 khi hai bên cùng hỗ trợ và chính sách cho phép.
3. **IPsec ESP** bảo vệ traffic theo tập chính sách/route đã chọn. Thuật toán, khóa, lifetime và tính năng PFS cần tương thích và đáp ứng chính sách bảo mật.
4. Hệ thống định tuyến đưa traffic giữa các mạng đã được cho phép qua tunnel.
5. Gateway và thiết bị đầu cuối liên tục theo dõi trạng thái tunnel; cấu hình route phải có cơ chế phản ứng phù hợp khi tunnel mất.

Lưu ý rằng IPsec bảo vệ một đoạn đường truyền ở tầng mạng. Các ứng dụng có dữ liệu nhạy cảm vẫn nên dùng **TLS, xác thực dịch vụ và phân quyền ở tầng ứng dụng**; không coi VPN là cơ chế xác thực người dùng cuối.

### 3.2. VPN phù hợp khi nào?

VPN thường phù hợp cho:

- Kết nối ban đầu khi triển khai hybrid hoặc di chuyển dữ liệu từng giai đoạn.
- Lưu lượng vừa phải, có thể chịu biến động độ trễ từ Internet.
- Chi nhánh hoặc trung tâm dữ liệu cần kết nối nhanh khi chưa có sẵn đường truyền riêng.
- **Kênh dự phòng** khi kết nối chính qua private circuit bị gián đoạn.
- Môi trường thử nghiệm, quản trị được giới hạn quyền, hoặc đồng bộ không bắt buộc thời gian thực.

Ưu điểm của VPN là có thể triển khai tương đối nhanh nếu đã có kết nối Internet, thường không cần đặt circuit riêng trước, và tạo được cơ chế mã hóa lưu lượng ở tầng mạng.

Các giới hạn:

- Throughput có thể bị giới hạn bởi thiết bị mã hóa/giải mã, dịch vụ gateway, số tunnel và khả năng định tuyến.
- Độ trễ, jitter và mất gói phụ thuộc tuyến Internet, nhà mạng và thời điểm.
- Phụ thuộc nguồn Internet và thiết bị biên; chỉ tạo hai tunnel qua cùng một modem/nhà mạng chưa đạt độc lập vật lý.
- Gói IPsec có overhead nên ảnh hưởng MTU và có thể gây phân mảnh nếu xử lý không đúng.
- Tunnel “UP” không đồng nghĩa API nội bộ hoạt động, route đúng hoặc dữ liệu đã đồng bộ.

**Không đồng nhất VPN site-to-site với VPN truy cập từ xa.** Remote-access VPN phục vụ thiết bị/người dùng; site-to-site nối các mạng/điểm mạng. Chính sách IAM và phân quyền người dùng cần được thiết kế độc lập.

### 3.3. Tunnel, route và địa chỉ

Ví dụ kế hoạch địa chỉ:

| Vùng | CIDR minh họa | Vai trò |
| --- | --- | --- |
| Trung tâm dữ liệu | 10.20.0.0/16 | ERP, ứng dụng nội bộ, DNS |
| Cloud production | 10.40.0.0/16 | App, worker, database |
| Cloud staging | 10.50.0.0/16 | Thử nghiệm, không mặc định được truy cập production |
| Mạng quản trị | 10.60.0.0/24 | Quản trị qua bastion/kiểm soát riêng |

Các dải CIDR chỉ là ví dụ dùng địa chỉ riêng. **Hai miền định tuyến cần tránh chồng lấn CIDR**; nếu cả hai cùng dùng 10.20.0.0/16, route sẽ mơ hồ và có thể buộc dùng NAT hoặc thiết kế lại địa chỉ. NAT chéo mạng tăng độ phức tạp logging, policy, DNS và xử lý kết nối hai chiều; nên ưu tiên quy hoạch không chồng lấn từ đầu.

Tại hai đầu, route cần chỉ rõ:

- Từ cloud đến 10.20.0.0/16: đi qua gateway hybrid.
- Từ trung tâm dữ liệu đến 10.40.0.0/16: đi qua tunnel/circuit phù hợp.
- Chỉ subnet và port thực sự cần thiết mới được firewall cho phép.
- Mạng staging 10.50.0.0/16 không tự động được quyền tới database production.

Nếu chỉ cấu hình route một chiều, gói đến đích nhưng gói trả lời không quay về đúng nơi. Đây là lỗi phổ biến trong môi trường có nhiều bảng định tuyến, firewall stateful hoặc kết nối dự phòng.

## 4. Đường truyền riêng: kết nối qua hạ tầng mạng chuyên biệt

### 4.1. Đường truyền riêng nghĩa là gì?

Ở đây, “đường truyền riêng” là kết nối giữa trung tâm dữ liệu và điểm kết nối riêng của nhà cung cấp cloud hoặc qua đối tác kết nối. Tùy nhà cung cấp, dịch vụ thường được gọi là **AWS Direct Connect**, **Azure ExpressRoute**, **Google Cloud Interconnect** hoặc các lựa chọn tương đương.

Điều cần phân biệt:

- **Kênh cloud private connectivity:** Lưu lượng từ trung tâm dữ liệu đi vào cloud qua một điểm kết nối riêng hoặc đối tác, không nhất thiết đi qua đường Internet công cộng như VPN site-to-site truyền thống.
- **Leased line/Metro Ethernet/MPLS của nhà mạng:** Dịch vụ vận chuyển traffic từ địa điểm doanh nghiệp tới điểm kết nối. Có thể vẫn cần circuit, cross-connect và cổng dịch vụ cloud riêng.
- **Đường truyền vật lý độc lập:** Hai đường logic chạy cùng một bó cáp hoặc cùng một điểm giao tiếp vẫn có thể bị ảnh hưởng bởi một lỗi chung.

~~~mermaid
flowchart LR
    subgraph DC["Trung tâm dữ liệu"]
        LAN["Mạng nội bộ"] --> ER["Edge router"]
    end
    ER --> TELCO["Nhà mạng / Đối tác kết nối"]
    TELCO --> CROSS["Điểm kết nối / Cross-connect"]
    CROSS --> CLOUDGW["Private connectivity gateway"]
    subgraph CLOUD["Mạng riêng Cloud"]
        CLOUDGW --> APP["Ứng dụng / Dữ liệu"]
    end
~~~

Các dịch vụ có những loại giao diện, mô hình routing, yêu cầu BGP, băng thông cổng, thời gian cung cấp và phạm vi khu vực khác nhau. Khi thực hiện dự án, phải xem thông số và điều kiện hỗ trợ **của nhà cung cấp đang sử dụng**, không suy diễn rằng mọi dịch vụ private connection có cùng đặc tính.

### 4.2. Lợi ích

**Tính dự báo:** Một kết nối riêng có thể đem lại thông lượng được đặt trước và chất lượng ổn định hơn so với việc đi qua Internet công cộng, tùy tuyến và cam kết của nhà mạng. Điều này có giá trị với luồng dữ liệu lớn hoặc nhạy cảm độ trễ.

**Kiểm soát kết nối:** Đường đi mạng và đối tác kết nối được xác định rõ; doanh nghiệp có thể xây policy và quan sát phù hợp.

**Băng thông cho tải lớn:** Một số phương án hỗ trợ mức băng thông lớn, thích hợp truyền dữ liệu định kỳ, phân tích, sao lưu hoặc đồng bộ giữa data center và cloud.

**Thiết kế hybrid dài hạn:** Khi nhiều dịch vụ cần kết nối và có đội vận hành mạng chuyên trách, private connectivity có thể là nền tảng hạ tầng lâu dài.

### 4.3. Giới hạn và hiểu nhầm

- **Riêng không có nghĩa được mã hóa.** Nhiều hình thức kết nối riêng không tự mã hóa payload end-to-end. Cần TLS, IPsec overlay hoặc cơ chế mã hóa phù hợp với yêu cầu và khả năng hỗ trợ.
- **Không mặc nhiên nhanh hơn mọi VPN.** Kết quả phụ thuộc khoảng cách, tuyến, cổng, ứng dụng, kích thước gói và cách xử lý lưu lượng.
- **Không mặc nhiên có HA.** Một circuit, một port, một router hoặc một nhà mạng vẫn là điểm lỗi đơn.
- **Không mặc nhiên bỏ qua kiểm soát an ninh.** Private path vẫn cần IAM, firewall, định danh dịch vụ, least privilege và audit.
- **Chi phí và thời gian triển khai có thể cao:** Bao gồm phí cloud port/connection, nhà mạng, cross-connect, thiết bị biên, lắp đặt, bảo trì và nhân lực.
- **Có thể không cấp sẵn Internet access.** Private connection hướng tới các mạng/dịch vụ theo cấu hình và loại gateway; không được coi là một tuyến Internet tổng quát.

Private circuit không bảo đảm ứng dụng chịu được lỗi logic, hỏng database hoặc sự cố cấp region; các cơ chế backup, failover và DR vẫn phải được thiết kế riêng.

## 5. So sánh VPN và đường truyền riêng theo yêu cầu thực tế

| Tiêu chí | VPN site-to-site qua Internet | Đường truyền riêng |
| --- | --- | --- |
| Nền tảng truyền tải | Kết nối Internet sẵn có ở hai đầu | Mạng/circuit của nhà mạng và điểm kết nối private tới cloud |
| Mã hóa | Thường dùng IPsec cho đường hầm | Cần xác nhận riêng; private không đồng nghĩa encrypted |
| Thời gian khởi tạo | Có thể nhanh nếu hạ tầng mạng sẵn sàng | Có thể cần đặt circuit, khảo sát, cross-connect |
| Thông lượng | Phụ thuộc gateway, thiết bị và Internet; có thể phải dùng nhiều tunnel | Có thể đặt băng thông phù hợp tùy dịch vụ/circuit |
| Độ trễ, jitter | Có thể biến động theo đường Internet | Có thể ổn định hơn trên tuyến được quản lý; vẫn phải đo |
| Mức dự phòng | Cần nhiều tunnel, endpoint và đường Internet độc lập | Cần đa port, điểm kết nối, router/nhà mạng hoặc site khi yêu cầu |
| Khả năng thay đổi nhanh | Phù hợp triển khai/thử nghiệm, đổi cấu hình tương đối nhanh | Thay đổi tốc độ/circuit có thể kéo theo điều chỉnh nhà mạng |
| Chi phí | Gateway, Internet, thiết bị, egress, vận hành | Port, circuit, cross-connect, thiết bị, egress, dự phòng, vận hành |
| Rủi ro chính | Biến động Internet, giới hạn mã hóa/thiết bị | Cáp/circuit/port/nhà mạng, thời gian cung cấp, lock-in kết nối |
| Tình huống thường gặp | Kết nối nhanh, tải vừa, dự phòng | Workload hybrid dài hạn, tải lớn hoặc yêu cầu kết nối riêng |

Bảng là **khung đánh giá**, không phải sự bảo đảm hiệu năng của bất kỳ sản phẩm cụ thể nào. Cần so những phương án đáp ứng **cùng** phạm vi rủi ro và SLO; nếu phương án VPN chỉ có một Internet uplink còn private có hai circuit độc lập, chi phí và độ tin cậy không tương đương.

## 6. Mô hình kết hợp: private là chính, VPN là dự phòng

Với workload quan trọng, một phương án đáng đánh giá là đường truyền riêng phục vụ traffic thường xuyên và VPN làm kênh dự phòng. Lựa chọn này chỉ có ích nếu **định tuyến, năng lực dự phòng và quy trình chuyển tuyến** được kiểm chứng.

~~~mermaid
flowchart LR
    DC["DC Core Network"] --> R["HA Router / Firewall"]
    R --> P["Đường truyền riêng - primary"]
    R --> V["VPN IPsec - backup"]
    P --> HUB["Cloud hybrid gateway / hub"]
    V --> HUB
    HUB --> APP["Private App Subnets"]
    HUB --> DB["Dịch vụ dữ liệu"]
~~~

Khi lập thiết kế, cần kiểm tra:

1. **Ưu tiên route:** Đường nào được chọn khi cả hai còn hoạt động? Cơ chế static route, metric, BGP local preference hay thuộc tính tương đương được hỗ trợ ra sao?
2. **Phát hiện lỗi:** BFD/BGP session, tunnel health, probe ứng dụng hay cơ chế khác; mất route và mất ứng dụng là hai loại lỗi khác nhau.
3. **Thời gian hội tụ:** Sau khi circuit mất, bao lâu lưu lượng thực sự chuyển sang VPN và ứng dụng xử lý request thành công?
4. **Dung lượng backup:** VPN có đủ băng thông cho **tải tối thiểu thiết yếu** không, hay cần chế độ suy giảm chức năng?
5. **Đường về:** Route từ cloud về data center có chuyển tương ứng không? Firewall stateful hoặc NAT có làm rơi phiên đang mở?
6. **Hành vi khôi phục:** Khi private link hoạt động trở lại, failback có gây chuyển tuyến liên tục (*flapping*) hoặc đứt phiên không?

Không mặc định rằng các tuyến tự chuyển đổi chỉ vì đã cấu hình hai kết nối. Chính sách route cụ thể phụ thuộc gateway và nhà cung cấp. Một số cơ chế route preference và ECMP có giới hạn; phải kiểm chứng bằng tài liệu kỹ thuật tương ứng và diễn tập trên môi trường thực.

### 6.1. Dự phòng logic và dự phòng vật lý

Hai tunnel IPsec trên cùng một thiết bị cùng ISP có thể chịu lỗi của một tunnel nhưng vẫn hỏng khi ISP mất. Hai private circuit đi cùng một tuyến cáp vẫn có thể cùng mất khi cáp bị đào đứt.

Phân tích nên xem các **miền lỗi**:

| Thành phần | Câu hỏi về điểm lỗi chung |
| --- | --- |
| Thiết bị đầu data center | Có hai router/firewall độc lập, nguồn điện và đường uplink không? |
| Nhà mạng | Có phụ thuộc cùng ISP, PoP hoặc tuyến cáp không? |
| Điểm kết nối cloud | Hai circuit có đi qua cùng thiết bị hoặc cùng địa điểm không? |
| Cloud gateway/hub | Gateway có được triển khai theo kiến trúc HA phù hợp dịch vụ không? |
| DNS/danh tính | Chuyển tuyến có giữ được DNS nội bộ, định danh và chứng thư không? |
| Application/data | Phía cloud và on-prem có thực sự xử lý được giao dịch sau chuyển tuyến không? |
| Đội vận hành | Có cùng tài khoản quản trị, bí mật và runbook chỉ tồn tại tại một địa điểm không? |

Muốn giảm rủi ro một điểm kết nối chung, cần đa dạng hóa các thành phần thật sự có thể cùng gặp sự cố; số lượng đường logic chỉ là bước đầu.

## 7. Quy hoạch địa chỉ IP và định tuyến hybrid

### 7.1. CIDR, chồng lấn và phân đoạn mạng

Lập **IP address plan** trước khi triển khai. Dự trù địa chỉ cho cloud production, staging, DR region, mạng on-prem, VPN/tunnel và vùng mở rộng. Một thiết kế dễ vận hành thường ưu tiên các CIDR riêng không chồng lấn giữa các miền kết nối.

Ví dụ:

~~~text
On-prem datacenter:    10.20.0.0/16
On-prem management:    10.21.0.0/20
Cloud production:      10.40.0.0/16
Cloud staging:         10.50.0.0/16
Cloud DR:              10.60.0.0/16
~~~

Đường truyền riêng hay VPN **không tự làm các subnet nhìn thấy nhau**. Mỗi tuyến cần có route ở cả hai đầu, firewall chính xác và đường trả lời hợp lệ.

Nếu có nhiều VPC/VNet, transit gateway hoặc hub-and-spoke có thể giúp tập trung định tuyến và bảo mật. Tuy nhiên, một hub tập trung cũng có thể trở thành điểm quá tải hoặc lỗi nếu không có HA và capacity planning.

### 7.2. Static routing và BGP

- **Static routes:** Tương đối dễ hiểu với mạng nhỏ, ít thay đổi. Phải quản lý cập nhật thủ công hoặc tự động hóa failover khi đường mất; không giả định route tĩnh luôn phát hiện lỗi ở cấp ứng dụng.
- **BGP (Border Gateway Protocol):** Hai hệ thống mạng có thể quảng bá/thu hồi prefix và hội tụ khi kết nối có thay đổi. Thường phù hợp với nhiều đường kết nối hoặc môi trường lớn.
- **BGP ASN:** Dùng số hệ tự trị phù hợp theo quy định của tổ chức và nhà cung cấp; ASN private có thể được dùng khi đáp ứng điều kiện kết nối.
- **Route filtering:** Chỉ quảng bá các prefix đã cho phép; tránh phát tán toàn bộ bảng định tuyến nội bộ hoặc default route ngoài dự định.
- **Route priority:** Chọn primary/backup bằng policy được hỗ trợ; thử cả chiều data center → cloud và cloud → data center.

**BGP session đang UP không bảo đảm API hoạt động.** Cần thêm probe ở cấp ứng dụng và monitor những tuyến quan trọng. Đồng thời, health probe không thay thế cơ chế định tuyến thực.

### 7.3. Định tuyến bất đối xứng và firewall stateful

Trong hệ thống có nhiều circuit, gói đi có thể qua private link nhưng gói trả lời qua VPN. Thiết bị firewall stateful không nhìn thấy trạng thái của phiên có thể chặn gói trả lời. Do đó, thiết kế phải xem:

- Forward path và return path.
- Các firewall và NAT state có được chia sẻ/đồng bộ không.
- Khi route thay đổi, phiên TCP hiện tại phải reconnect hay có thể tiếp tục.
- Chính sách chọn tuyến cho traffic khác nhau có tạo bất đối xứng không.

Không chỉ thử ping. Cần thử các kết nối ứng dụng thực, request dài, nhiều phiên đồng thời và trường hợp chuyển tuyến giữa phiên.

## 8. DNS và nhận diện dịch vụ giữa hai môi trường

Ứng dụng thường dùng hostname như **inventory.internal.example** thay vì địa chỉ IP tĩnh. Để hostname nội bộ hoạt động xuyên hybrid, có thể dùng DNS resolver/forwarder có kiểm soát giữa cloud và on-prem, với các zone và chính sách truy cập rõ ràng.

Một số vấn đề cần xử lý:

- **Split-horizon DNS:** Cùng tên có thể trả địa chỉ khác nhau tùy môi trường; phải đảm bảo người gọi nhận đúng đáp án.
- **Conditional forwarding:** Chỉ chuyển tiếp các zone cần thiết; tránh vòng lặp resolver A ↔ B.
- **DNS over hybrid:** Khi VPN/circuit lỗi, câu truy vấn DNS có timeout dài không? Có resolver dự phòng ở mỗi phía không?
- **Cache và TTL:** TTL thấp không bảo đảm toàn bộ client làm mới tức thì, đặc biệt với ứng dụng giữ kết nối dài.
- **Không lộ thông tin nội bộ:** Private hostnames và IP không nên tự động bị xuất sang resolver công cộng.

Với ứng dụng Java, việc cache DNS, connection pooling và thời hạn kết nối cần được xét khi chuyển đổi endpoint. Một hệ thống có tuyến mạng dự phòng tốt vẫn có thể gặp thời gian lỗi dài vì DNS hoặc pool kết nối giữ địa chỉ cũ.

## 9. Bảo mật: VPN và private link chỉ là một phần của hệ thống

### 9.1. Phân tầng kiểm soát bảo mật

| Lớp kiểm soát | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Network segmentation | Subnet nào được phép nói chuyện với subnet nào? | Chỉ worker sync gọi Inventory API qua cổng cần thiết |
| Transport protection | Dữ liệu được bảo vệ khi truyền bằng gì? | IPsec qua Internet, TLS giữa các dịch vụ; mã hóa private circuit nếu yêu cầu |
| Identity | Bên nào đang gọi API và được xác thực ra sao? | mTLS, OAuth2/client identity hoặc giải pháp được phê duyệt |
| Authorization | Caller được phép thực hiện thao tác nào? | Chỉ tài khoản dịch vụ sync được đọc một tập tồn kho |
| Data protection | Dữ liệu cá nhân/bí mật có được giới hạn và mã hóa không? | Phân loại dữ liệu, quản lý khóa, không log plaintext nhạy cảm |
| Audit và incident response | Có phát hiện cấu hình trái phép hoặc truy cập bất thường không? | Flow logs, gateway logs, audit events, cảnh báo |

Việc “đặt database trên private subnet” giúp thu hẹp đường truy cập nhưng không chứng minh DB có policy đúng; vẫn cần kiểm tra quyền, patch, secret, backup, mã hóa và audit.

### 9.2. Quản lý khóa VPN và thiết bị biên

- Ưu tiên cơ chế xác thực và thuật toán được tổ chức phê duyệt; xem khả năng hỗ trợ từ cả thiết bị và cloud gateway.
- Bảo vệ khóa/PSK, certificate và quyền cấu hình gateway; có lịch rotation và phương án khôi phục.
- Tách quyền đọc log khỏi quyền thay đổi route hoặc security policy khi có thể.
- Giới hạn địa chỉ IP đầu cuối được phép kết nối; kiểm tra chống thay đổi cấu hình không có phê duyệt.
- Đảm bảo các thiết bị mạng được cập nhật bản vá và backup cấu hình.
- Trong nhật ký, che dữ liệu nhạy cảm và bí mật xác thực.

Không đưa khóa thật hoặc PSK vào source code, tài liệu học hoặc hệ thống ticket. Những ví dụ cấu hình trong bài này chỉ dùng địa chỉ và tham số minh họa.

### 9.3. Shared responsibility và tuân thủ

Nhà cung cấp cloud bảo vệ phần hạ tầng theo phạm vi dịch vụ, còn doanh nghiệp thường phải quản lý chính sách kết nối, IAM, firewall rules, dữ liệu, đầu kết nối on-prem và quy trình vận hành tương ứng. Trách nhiệm cụ thể cần dựa vào dịch vụ và hợp đồng.

**Data residency:** Việc chuyển dữ liệu từ data center lên cloud để phân tích, backup hoặc đồng bộ phải xét vùng lưu trữ và chính sách tuân thủ. Kênh private không tự làm hoạt động truyền dữ liệu trở nên hợp pháp hoặc phù hợp chính sách.

## 10. Hiệu năng: bandwidth, latency, jitter, MTU và nút thắt

### 10.1. Không nhầm băng thông với tốc độ phản hồi

- **Bandwidth/throughput:** lượng dữ liệu có thể chuyển trong một đơn vị thời gian.
- **Latency:** thời gian một gói hoặc một request đi qua mạng và được xử lý.
- **Jitter:** độ biến thiên của delay giữa các gói, đáng chú ý với thoại/video hoặc ứng dụng nhạy cảm thời gian.
- **Packet loss:** gói tin mất làm TCP truyền lại, kéo dài thời gian giao dịch.
- **p95/p99:** các percentile độ trễ, quan trọng để đánh giá trải nghiệm khi tải cao.

Một đường truyền 1 Gbps không bảo đảm API mất 10 ms, vì request còn phụ thuộc database, application processing, round trip, queue, TLS và các dependency khác.

### 10.2. Ước tính lưu lượng cần thiết

Giả sử ứng dụng đồng bộ **200 giao dịch/giây**, mỗi giao dịch truyền trung bình **150 KiB** qua kênh hybrid (tính tổng dữ liệu request/response):

~~~text
Tải hữu ích = 200 giao dịch/s × 150 KiB/giao dịch
            = 30.000 KiB/s
            = 30.000 × 1.024 × 8 bit/s
            = 245.760.000 bit/s
            ≈ 245,76 Mbps
~~~

Nếu dự trù thêm **30% headroom trên tải hữu ích**, mức mục tiêu tham khảo là khoảng:

~~~text
245,76 Mbps × 1,30 ≈ 319,49 Mbps
~~~

Đây là bài toán minh họa; không phải cứ mua đường 320 Mbps là chắc đủ. Cần thêm overhead truyền tải/IPsec, peak burst, các luồng khác, retransmission, QoS, lưu lượng backup và cách tính băng thông của nhà cung cấp. Đặc biệt, nếu response gấp nhiều lần request hoặc có tải đồng bộ định kỳ, phải tính theo **chiều truyền dữ liệu** riêng.

### 10.3. MTU/MSS và phân mảnh

IPsec đóng gói thêm header/overhead làm giảm kích thước payload có thể truyền an toàn trên một path. Nếu một đầu gửi gói lớn hơn path MTU, hiện tượng phân mảnh hoặc drop có thể gây timeout khó hiểu. Những lỗi này đôi khi chỉ xuất hiện với phản hồi lớn, trong khi ping kích thước nhỏ vẫn thành công.

Các biện pháp cần kiểm tra:

- Path MTU discovery và chính sách ICMP phù hợp.
- Thiết lập MSS clamp hoặc MTU trên giao diện/tunnel theo cấu hình được hỗ trợ.
- Test payload lớn, request thực và lưu lượng đồng thời, không chỉ gói kiểm tra nhỏ.
- Theo dõi retransmission, fragmentation/drop và lỗi tunnel.

Giá trị MTU tối ưu không có một con số đúng cho mọi tuyến; phải đo và đối chiếu thông số thiết bị/dịch vụ.

### 10.4. Ứng dụng và database: giảm sự phụ thuộc vào round trip

Nếu một request đặt hàng trên cloud liên tiếp gọi on-prem API năm lần để lấy dữ liệu nhỏ, độ trễ mạng sẽ bị nhân lên. Có thể cân nhắc:

1. **Batch API** thay vì nhiều request lẻ.
2. **Cache hoặc read model trên cloud** đối với dữ liệu có thể chấp nhận độ trễ cập nhật.
3. **Đồng bộ bất đồng bộ qua queue/event** đối với luồng không cần câu trả lời tức thì.
4. **Đặt logic gần dữ liệu** nếu chính sách và mục tiêu nghiệp vụ cho phép.
5. **Timeout, retry có giới hạn và circuit breaker** để tránh khuếch đại sự cố mạng.

Đổi sang đồng bộ bất đồng bộ tạo bài toán **tính nhất quán cuối cùng**; phải xác định độ trễ dữ liệu cho phép và cách đối soát khi kết nối mất lâu. Không bỏ qua vấn đề đúng đắn nghiệp vụ chỉ để giảm độ trễ.

## 11. Chiến lược sẵn sàng cao và phục hồi khi đường kết nối lỗi

### 11.1. Phân tích miền lỗi

Không dùng một kịch bản “VPN hỏng” để đại diện cho mọi sự cố. Cần phân biệt:

- Một IPsec tunnel hết hạn/đứt nhưng Internet vẫn còn.
- Một thiết bị router/firewall on-prem chết.
- Một nhà mạng hoặc tuyến cáp mất kết nối.
- Cloud gateway hoặc khu vực kết nối bị ảnh hưởng.
- DNS nội bộ không thể phân giải.
- Routing sai hoặc chồng lấn prefix, gây blackhole.
- Kết nối hoạt động nhưng latency/packet loss vượt ngưỡng.
- Kết nối ổn nhưng API ERP/database ở trung tâm dữ liệu bị lỗi.
- Control plane gặp lỗi khiến việc thay đổi cấu hình khôi phục bị ngăn.

Mỗi loại có hành vi khác nhau, nên phải có **kịch bản chất lượng** và phép kiểm thử phù hợp.

### 11.2. RTO và RPO trong kiến trúc mạng

**RTO** là giới hạn thời gian chấp nhận để phục hồi chức năng nghiệp vụ sau sự cố đã định nghĩa. Với lỗi hybrid network, RTO phải đo đến lúc **người dùng hoàn tất hành trình được yêu cầu**, không chỉ đến lúc BGP session quay lại trạng thái established.

**RPO** là khoảng mất dữ liệu tính theo thời gian tối đa được chấp nhận. RPO liên quan đến mô hình sao chép/ghi dữ liệu; thay VPN bằng đường truyền riêng **không tự khiến RPO bằng 0**. Nếu sự kiện đang nằm trong queue khi mất mạng, phải kiểm tra không mất, không trùng và khôi phục đúng thứ tự cần thiết.

### 11.3. Chế độ suy giảm khi mất kết nối

Một số tính năng có thể tiếp tục phục vụ khi mất kết nối on-prem:

| Chức năng | Hành vi suy giảm có thể lựa chọn | Điều kiện cần kiểm chứng |
| --- | --- | --- |
| Đọc catalog | Trả từ cache/read model gần nhất | Độ tươi dữ liệu và thông báo trạng thái |
| Tạo đặt chỗ | Tạm khóa hoặc nhận ở trạng thái pending | Không bán quá số lượng, kiểm soát idempotency |
| Đồng bộ báo cáo | Tạm giữ sự kiện trong queue để xử lý sau | Queue có đủ dung lượng và retention |
| Đăng nhập | Dùng token phiên đã xác thực nếu chính sách cho phép | Thời hạn token, quyền bị thu hồi và kiểm soát rủi ro |
| Quản trị dữ liệu nhạy cảm | Từ chối cho đến khi kênh được phục hồi | Thông báo lỗi rõ, không mở bypass trái phép |

Các lựa chọn này cần nghiệp vụ chấp thuận. Ví dụ, cho phép booking khi dữ liệu tồn kho bị trễ có thể gây đặt trùng; nếu không có cơ chế reservation nhất quán, tạm dừng bước ghi quan trọng có thể an toàn hơn.

## 12. Thiết kế giám sát và SLO cho kết nối hybrid

Đừng dựa duy nhất vào trạng thái tunnel **UP/DOWN**. Một thiết kế quan sát tốt gồm nhiều mức:

| Mức | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Circuit/Internet | Link state, lỗi interface, bandwidth, drop | Tình trạng kết nối vật lý và bão hòa |
| Tunnel/IPsec | Tình trạng IKE/IPsec SA, thời gian rekey, lỗi thương lượng | Tình trạng đường hầm mã hóa |
| Routing | BGP neighbor, số prefix, thay đổi route, convergence | Khả năng trao đổi và chọn đường |
| Network quality | RTT, loss, jitter, throughput, retransmission | Chất lượng đường truyền thực tế |
| DNS | Tỷ lệ phân giải thành công và thời gian resolve | Phụ thuộc tên dịch vụ xuyên môi trường |
| Application | p95/p99 API, tỷ lệ lỗi, transaction success, timeout | Tác động đến người dùng |
| Data integration | Replication lag, queue age, số lỗi xử lý/sự kiện trùng | Chất lượng và tính nhất quán dữ liệu |
| Cost | Dữ liệu truyền, port/circuit/egress và chi phí mỗi giao dịch | Khả năng vận hành trong ngân sách |

### 12.1. SLI, SLO và error budget

Một ví dụ **minh họa** cho luồng đồng bộ tồn kho:

- **SLI:** Tỷ lệ yêu cầu Inventory API hợp lệ từ ứng dụng cloud được trả kết quả đúng trong thời gian 2 giây.
- **SLO:** Ít nhất 99,9% yêu cầu hợp lệ đáp ứng SLI trong cửa sổ 30 ngày.
- **Error budget:** Với SLO 99,9%, có 0,1% tổng yêu cầu thuộc phạm vi đo được phép không đạt mục tiêu trong kỳ; cách tính loại trừ/bao gồm lỗi phải được chốt từ trước.

SLO của **kết nối mạng** và SLO của **Inventory API end-to-end** là hai tiêu chí khác nhau. Mạng có thể đạt mục tiêu packet loss nhưng API vẫn thất bại vì database hoặc ứng dụng.

### 12.2. Kịch bản chất lượng sáu phần

Một kịch bản đầy đủ nên xác định **nguồn tác động, tác động, môi trường, thành phần, phản hồi và thước đo**.

**Kịch bản QA-NET-01 — Chuyển tuyến từ private circuit sang VPN:**

| Thành phần | Mô tả |
| --- | --- |
| Nguồn tác động | Sự cố nhà mạng làm mất tuyến private chính |
| Tác động | Kết nối primary không còn truyền dữ liệu |
| Môi trường | Giờ cao điểm, Inventory API đang có 100 req/s |
| Thành phần | Router/firewall on-prem, cloud gateway, route, Inventory API |
| Phản hồi | Phát hiện lỗi, chuyển tuyến sang VPN, giảm tải chức năng phụ nếu cần |
| Thước đo | Trong 5 phút kể từ khi tiêm lỗi, ≥ 99% yêu cầu nghiệp vụ hợp lệ thành công trong cửa sổ 10 phút sau khôi phục; không có sự kiện ghi trùng trong bộ kiểm thử |

Ngưỡng ở đây là **mục tiêu giả định để học**, cần thương lượng từ tác động nghiệp vụ. Nên bổ sung cách đo khoảng gián đoạn thực tế giữa thời điểm failover bắt đầu và lúc hoàn tất giao dịch, số request bị lỗi và mức tải mà VPN dự phòng chịu được.

**Kịch bản QA-NET-02 — Chịu tải đồng bộ dữ liệu:**

Khi worker cần trao đổi trung bình 250 Mbps dữ liệu hữu ích liên tục 30 phút giữa cloud và trung tâm dữ liệu trong điều kiện hệ thống bình thường, đường kết nối phải duy trì throughput yêu cầu, packet loss trong ngưỡng đã chốt và queue lag không vượt mục tiêu. Đo cả hai chiều, overhead và các tải cạnh tranh.

**Kịch bản QA-NET-03 — Hạn chế truy cập:**

Khi workload staging gửi yêu cầu tới database ERP production qua mạng hybrid, firewall và cơ chế authorization phải từ chối toàn bộ ca truy cập trái phép thuộc bộ kiểm thử đã xác định, không để lộ dữ liệu và ghi audit event có thể truy vết.

### 12.3. Cảnh báo phù hợp

- Cảnh báo link/tunnel down và route thay đổi, có gắn ngữ cảnh tuyến nào bị ảnh hưởng.
- Cảnh báo độ trễ cao, packet loss và bão hòa kéo dài, tránh báo động chỉ vì một spike rất ngắn.
- Cảnh báo Inventory API thực sự không đạt SLO, dù tunnel vẫn UP.
- Cảnh báo khi hệ thống đang chạy trên VPN backup lâu hơn giới hạn vận hành hoặc dự phòng gần đầy tải.
- Liên kết mỗi cảnh báo với dashboard, runbook và người chịu trách nhiệm.

## 13. TCO: chi phí VPN, đường truyền riêng và phương án kết hợp

Giá máy chủ cloud không đủ để quyết định mạng hybrid. **Tổng chi phí sở hữu (TCO)** cần xét:

- Cloud gateway, VPN tunnel, private connection port và hub/transit processing.
- Đường Internet/leased line, nhà mạng, cross-connect, thiết bị biên và bảo trì.
- Phí truyền dữ liệu từ cloud ra ngoài (*egress*) và phí xử lý theo dịch vụ.
- Kết nối dự phòng: router, port, ISP, circuit, địa điểm khác nhau.
- Mã hóa, giám sát, log, security, DNS và năng lực nhân sự.
- Phí khởi tạo, khảo sát, thiết lập và thời gian chờ cung cấp.
- Diễn tập failover, kiểm thử hiệu năng, support, thay đổi hợp đồng.

### 13.1. Ví dụ so sánh chi phí giả định

Bảng dưới đây là **số liệu minh họa do bài học đặt ra**, không phải báo giá hay cam kết của nhà cung cấp. Đơn vị: **triệu VND/tháng**. Giả định các phương án dùng cùng workload và khối lượng dữ liệu, nhưng vẫn cần kiểm chứng có đáp ứng SLO tương đương hay không.

| Khoản mục | VPN-only | Hai private circuits | Private + VPN dự phòng |
| --- | ---: | ---: | ---: |
| Cloud VPN gateway/tunnels | 8 | 0 | 8 |
| Private port/circuit cloud | 0 | 45 | 45 |
| Nhà mạng, cross-connect | 0 | 35 | 35 |
| Đường private dự phòng thứ hai | 0 | 45 | 45 |
| Data transfer/egress giả định | 12 | 12 | 12 |
| Giám sát và vận hành phân bổ | 18 | 22 | 24 |
| **Tổng mỗi tháng** | **38** | **159** | **169** |

Ví dụ, TCO thường xuyên của phương án private + VPN ở bảng trên là:

~~~text
8 + 45 + 35 + 45 + 12 + 24 = 169 triệu VND/tháng
~~~

Nếu có **240 triệu VND** phí lắp đặt ban đầu phân bổ trong 24 tháng:

~~~text
240 / 24 = 10 triệu VND/tháng
TCO phân bổ của private + VPN = 169 + 10 = 179 triệu VND/tháng
~~~

**Lưu ý để so sánh công bằng:** Phương án hai private circuits trong bảng đã có hai tuyến riêng, trong khi VPN-only chưa được mô tả là hai ISP vật lý độc lập. Bảng thể hiện cấu phần chi phí giả định, không khẳng định cả ba có độ tin cậy tương đương. Để chọn kiến trúc, cần thiết kế cùng các miền lỗi, tải dự phòng và SLO, rồi cập nhật lại chi phí.

### 13.2. Chi phí nghiệp vụ

Có thể bổ sung:

~~~text
Chi phí kết nối hybrid mỗi giao dịch thành công
    = Tổng chi phí kết nối trong kỳ / Số giao dịch nghiệp vụ thành công trong kỳ
~~~

Nếu TCO phân bổ là 179 triệu VND/tháng và hệ thống hoàn thành 500.000 giao dịch hợp lệ, chi phí phân bổ của kết nối hybrid là **358 VND/giao dịch**. Con số này không bao gồm tổng compute/database của ứng dụng nếu chúng nằm ngoài phạm vi tính.

Mô hình ra quyết định cần xét **chi phí của gián đoạn** (mất doanh thu, chậm giao dịch, rủi ro dữ liệu và nghĩa vụ hợp đồng) cùng với TCO. Một đường rẻ hơn nhưng không đáp ứng SLO không phải phương án tương đương.

## 14. Case study: đưa ứng dụng đặt hàng lên cloud, giữ ERP ở data center

### 14.1. Yêu cầu đầu vào

Một doanh nghiệp triển khai Spring Boot API đặt hàng trên cloud nhưng ERP và cơ sở dữ liệu tồn kho vẫn nằm ở trung tâm dữ liệu. Trong giai đoạn 1:

- API trên cloud phục vụ người dùng bên ngoài, xác thực tại cloud.
- Khi tạo đơn, cần kiểm tra tồn kho ERP; một số trường hợp cần ghi reservation vào ERP.
- Lưu lượng trung bình 100 req/s, cao điểm 300 req/s; mỗi giao dịch trao đổi dữ liệu ít nhưng phải đúng.
- Bản đồng bộ báo cáo đẩy dữ liệu theo lô, có thể trì hoãn vài phút.
- ERP chỉ cho phép kết nối từ các subnet ứng dụng đã đăng ký.
- Doanh nghiệp mong muốn phục hồi giao tiếp ứng dụng trong vòng 5 phút sau lỗi đường chính, với khả năng duy trì giao dịch quan trọng ở mức đã thống nhất.

Các thông số là ví dụ học tập; chúng không phải tiêu chuẩn chung cho cloud.

### 14.2. So sánh phương án

**Phương án A — Site-to-site VPN:** Có thể triển khai sớm, thuận tiện kiểm thử luồng nghiệp vụ và chuyển đổi dần. Cần kiểm tra băng thông tối đa trong giờ cao điểm, biến động Internet, cơ chế failover và cấu hình tunnel. Nếu chỉ dùng một ISP, lỗi ISP có thể làm mất toàn bộ kết nối.

**Phương án B — Private connection:** Có thể ổn định và phù hợp cho đồng bộ dài hạn. Cần đánh giá thời gian cung cấp, phí circuit/port, HA và cơ chế mã hóa. Một đường private duy nhất vẫn có thể là single point of failure.

**Phương án C — Private primary + VPN backup:** Cho phép sử dụng private ở trạng thái bình thường và VPN khi sự cố. Phải kiểm chứng rằng backup đủ sức xử lý ít nhất luồng tạo đơn quan trọng; các luồng báo cáo nặng có thể tạm dừng khi failover.

**Quyết định minh họa:** Giai đoạn đầu dùng VPN để tích hợp và kiểm thử. Khi lưu lượng, ngân sách và cam kết vận hành được xác nhận, triển khai private connection phục vụ chính, giữ VPN làm dự phòng. Việc chuyển pha cần có ADR và không được mặc định vì “private tốt hơn”; phải dùng kết quả đo thực tế.

### 14.3. Kiến trúc đề xuất

~~~mermaid
flowchart TB
    USERS["Người dùng Internet"] --> WAF["WAF / Public API"]
    WAF --> APP["Order API cloud - multi AZ"]
    APP --> CLOUDGW["Hybrid gateway"]
    CLOUDGW --> PRIVATE["Private circuit"]
    CLOUDGW --> VPN["VPN backup"]
    PRIVATE --> DCEDGE["DC HA edge routers"]
    VPN --> DCEDGE
    DCEDGE --> FW["Firewall segment ERP"]
    FW --> ERP["Inventory service / ERP"]
    APP --> QUEUE[("Queue báo cáo")]
    QUEUE --> SYNC["Async worker"]
    SYNC --> CLOUDGW
~~~

Các nguyên tắc:

1. **Không mở database ERP trực tiếp** cho các client Internet hoặc tất cả subnet cloud.
2. Service-to-service dùng danh tính/ủy quyền riêng, mã hóa và audit phù hợp.
3. Đặt timeout cho Inventory API; tránh retry vô hạn khi đường kết nối lỗi.
4. Các lệnh thay đổi tồn kho phải có ID giao dịch/idempotency và đối soát khi client timeout.
5. Batch báo cáo có thể chờ queue khi kết nối backup đang hạn chế.
6. Định tuyến phải được thử cả hai chiều và cả lúc trở lại primary.

### 14.4. Kiểm thử chấp nhận

- **Kiểm thử kết nối:** ping và TCP/TLS tới endpoint hợp lệ; kiểm tra route và DNS; xác minh staging không vào production.
- **Kiểm thử tải:** tạo workload 100/300 req/s với dữ liệu đại diện, đo p95/p99 của luồng tạo đơn, bandwidth hai chiều và error rate.
- **Kiểm thử failover:** ngắt private path trong môi trường kiểm soát; đo thời gian tới lúc API đặt đơn thành công qua VPN, số request lỗi và độ trễ tăng.
- **Kiểm thử tính đúng đắn:** cố tình làm mất response sau khi ERP đã giữ tồn kho; client retry phải không tạo reservation trùng.
- **Kiểm thử backup đủ tải:** trên VPN, tạm dừng batch báo cáo và xác nhận luồng đặt đơn quan trọng đạt tiêu chí tối thiểu.
- **Kiểm thử DNS/security:** kiểm tra resolver dự phòng, certificate/secret rotation, quyền truy cập và log audit.
- **Kiểm thử failback:** khôi phục private, quan sát route ổn định, session, throughput và backlog được xử lý theo thứ tự phù hợp.

Báo cáo phải giữ được cấu hình, thời điểm thử, mức tải, số liệu đo và kết quả đạt/trượt. Việc tunnel đã lên không đủ để ký nghiệm thu.

## 15. Quy trình triển khai từng bước

Một dự án thật có thể đi theo trình tự:

1. **Thu thập yêu cầu:** Danh sách luồng nghiệp vụ, dữ liệu, throughput hai chiều, latency, bảo mật, SLO và RTO/RPO.
2. **Khảo sát mạng hiện trạng:** CIDR, tuyến WAN, firewall, ISP, thiết bị HA, DNS và phụ thuộc ứng dụng on-prem.
3. **Vẽ data flow:** Xác định cụ thể nguồn, đích, port, protocol, identity và chủ sở hữu.
4. **Chọn mô hình kết nối:** VPN, private hoặc kết hợp; lập ma trận miền lỗi và phương án dự phòng.
5. **Quy hoạch địa chỉ/routing:** CIDR không chồng lấn, BGP/static route, route filtering, quy tắc ưu tiên và failback.
6. **Thiết kế bảo mật:** IPsec/TLS, firewall, IAM, quản lý khóa, dữ liệu nhạy cảm, logging và phân quyền.
7. **Triển khai trong môi trường kiểm soát:** Kiểm tra từng kết nối, DNS, route và đường trả lời trước khi mở traffic nghiệp vụ.
8. **Thử tải và tiêm lỗi:** Đo throughput, p95/p99, packet loss, MTU, failover, queue lag và tính đúng đắn dữ liệu.
9. **Bàn giao vận hành:** Dashboard, alerts, runbook, liên hệ nhà mạng/cloud support, quy trình thay đổi và diễn tập định kỳ.
10. **Ghi ADR và xem lại:** Đánh giá khi lưu lượng, giá dịch vụ, vị trí dữ liệu hoặc mức độ rủi ro thay đổi.

### 15.1. Mẫu kế hoạch kết nối dạng YAML khái niệm

Ví dụ này chỉ là **mẫu tài liệu kiến trúc**, không phải cấu hình có thể áp dụng trực tiếp lên thiết bị hoặc cloud API.

~~~yaml
id: HYBRID-NET-008
owner: Network_and_Platform_Team
on_prem_cidr: 10.20.0.0/16
cloud_prod_cidr: 10.40.0.0/16
connectivity:
  primary: dedicated_private_circuit
  backup: site_to_site_ipsec_vpn
routing:
  method: bgp
  allowed_prefixes:
    - 10.20.0.0/16
    - 10.40.0.0/16
security:
  network_policy: least_privilege
  service_to_service: tls_with_identity
  encryption_on_private_link: validate_requirement
observability:
  - circuit_state
  - tunnel_state
  - bgp_route_state
  - latency_p95
  - packet_loss
  - inventory_api_success_rate
failover_validation:
  drill_id: TEST-NET-FAILOVER-01
  service_rto_target_minutes: 5
  backup_capacity: critical_workload_only
status: proposed
~~~

Trong hệ thống thật, thêm danh sách subnet, thiết bị, đầu nối, ASNs, route advertisements, điều kiện rollback, chủ sở hữu SLO và phương pháp kiểm thử cụ thể. Không ghi khóa VPN vào tệp mô tả này.

## 16. Những lỗi thiết kế thường gặp

| Nhận định hoặc lỗi | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| “Private link thì dữ liệu tự được mã hóa.” | Private path không nhất thiết mã hóa nội dung. | Xác định nhu cầu và dùng TLS/IPsec hoặc cơ chế phù hợp. |
| “Đã có hai tunnel VPN nên chắc chắn HA.” | Hai tunnel có thể chung router, ISP hoặc nguồn điện. | Đánh giá độc lập theo failure domain vật lý. |
| “BGP UP tức ứng dụng tốt.” | Route có thể đúng nhưng DNS, DB, app hoặc firewall lỗi. | Monitor synthetic transaction và SLO toàn tuyến. |
| “VPN đủ băng thông vì kiểm tra ping nhanh.” | Ping nhỏ không phản ánh throughput, MTU và tải thực tế. | Load test, đo hai chiều và packet loss. |
| “Có circuit riêng thì không cần VPN backup.” | Một circuit vẫn có thể mất do cáp, port hoặc provider. | Thiết kế dự phòng dựa trên rủi ro và RTO. |
| “Mọi CIDR private đều kết nối được.” | CIDR chồng lấn gây ambiguity và lỗi định tuyến. | Quy hoạch địa chỉ, giới hạn prefix, xem lại NAT. |
| “Chỉ cần route từ cloud về data center.” | Thiếu return path làm request timeout. | Kiểm tra cả hai chiều, firewall state và NAT. |
| “Mở toàn bộ port nội bộ cho dễ tích hợp.” | Làm tăng khả năng lan truyền sự cố/xâm nhập. | Segmentation, allowlist và least privilege. |
| “Đường truyền 1 Gbps thì API chắc nhanh.” | Latency và application/database processing vẫn có thể chậm. | Đo p95/p99 end-to-end, tối ưu các lời gọi chéo mạng. |
| “Failover xong là dữ liệu nhất quán.” | Retry và giao dịch đang xử lý có thể gây trùng/mất. | Idempotency, queue/outbox và đối soát. |
| “Đổi sang private link sẽ tự giảm mọi chi phí.” | Có port, ISP, cross-connect và vận hành mới. | Tính TCO cùng phạm vi chất lượng và rủi ro. |

## 17. Bài tập thực hành

**Bối cảnh:** Một ngân hàng giả định có hệ thống quản lý khách hàng và database giao dịch tại hai trung tâm dữ liệu. Cloud chạy ứng dụng web và dịch vụ báo cáo. Có 150 req/s liên quan tới dữ liệu nội bộ, trong giờ cao điểm lên 500 req/s. Dữ liệu rất nhạy cảm; mọi giao dịch ghi phải xác minh quyền và không được xử lý trùng. Ngân sách có giới hạn và yêu cầu phục hồi kết nối quan trọng trong 5 phút.

Thực hiện:

1. **Thiết kế luồng:** Vẽ mạng on-prem và cloud gồm CIDR, DNS, firewall, application subnet, data subnet và điểm kết nối hybrid.
2. **So sánh lựa chọn:** Đề xuất VPN-only, hai private circuits và private + VPN backup; lập bảng ưu/nhược về bảo mật, throughput, latency, HA, vận hành và TCO.
3. **Xây ba kịch bản chất lượng sáu phần:** Một kịch bản lỗi link, một kịch bản tải cao, một kịch bản truy cập trái phép; đặt ngưỡng minh họa, nêu cách đo.
4. **Quy hoạch IP:** Chọn CIDR cho các môi trường mà không chồng lấn; mô tả forward/return route và BGP hoặc static routing.
5. **Ước lượng băng thông:** Với 500 req/s và 120 KiB dữ liệu trao đổi mỗi request, tính throughput hữu ích, cộng headroom 25%, rồi giải thích các yếu tố khiến băng thông thực tế còn khác.
6. **Kiểm tra failover:** Mô tả cách giả lập mất tuyến private và kiểm chứng VPN thực sự phục vụ đủ giao dịch quan trọng; nêu chính sách đối với báo cáo không ưu tiên.
7. **Đối soát dữ liệu:** Nêu cách xử lý khi client timeout sau khi hệ thống on-prem đã ghi giao dịch.
8. **Tính TCO:** Dùng giả định hợp lý về circuit, egress, gateway, thiết bị, nhân lực và diễn tập; so các phương án đáp ứng cùng mục tiêu.
9. **Viết ADR:** Chọn phương án và nêu rủi ro còn lại, số liệu cần thu thập và điều kiện xem lại.

**Gợi ý tự kiểm tra:** Không đánh giá kênh kết nối chỉ bằng việc tunnel hoạt động. Bài làm đạt khi có **ứng dụng cụ thể, chỉ số đo được, đường mạng hai chiều, giải pháp bảo mật, phương án lỗi và kết quả kiểm thử end-to-end**.

## 18. Checklist trước khi thông qua thiết kế

- [ ] Đã mô tả rõ hệ thống và dữ liệu nào trao đổi giữa data center và cloud.
- [ ] Chọn VPN, private connection hoặc phương án kết hợp dựa trên workload và rủi ro thực tế.
- [ ] Có CIDR plan không chồng lấn, IPAM và quy định mở rộng mạng.
- [ ] Đã xác định route, BGP/static routing, prefix filter, primary/backup và return path.
- [ ] Có sơ đồ tất cả thiết bị, circuit, ISP, PoP và điểm lỗi chung.
- [ ] Có thiết kế TLS/IPsec và chính sách kiểm soát truy cập phù hợp dữ liệu.
- [ ] DNS nội bộ, timeout và behavior khi mất kết nối được kiểm chứng.
- [ ] Đã đo MTU/MSS, packet loss, latency, jitter, throughput và tải đỉnh hai chiều.
- [ ] Có SLI/SLO cho giao dịch nghiệp vụ, không chỉ trạng thái tunnel.
- [ ] Có diễn tập failover và failback với RTO/RPO, queue lag và idempotency.
- [ ] VPN backup hoặc kênh dự phòng đủ năng lực xử lý luồng ưu tiên.
- [ ] TCO tính cả circuit, gateway, egress, thiết bị, giám sát, support và nhân lực.
- [ ] Có runbook, alerts, owner, quy trình thay đổi và ADR với điều kiện xem lại.
- [ ] Đã đánh giá độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành và tính bền vững theo Well-Architected.

## 19. Liên hệ với Well-Architected

| Trụ cột | Câu hỏi khi review kết nối hybrid |
| --- | --- |
| **Operational Excellence** | Có chủ sở hữu, giám sát xuyên on-prem/cloud, IaC, runbook và diễn tập không? |
| **Security** | Có mã hóa, phân đoạn mạng, danh tính, quyền tối thiểu và audit xuyên cả hai môi trường không? |
| **Reliability** | Các failure domain có độc lập, failover đạt RTO và dữ liệu đúng sau lỗi không? |
| **Performance Efficiency** | Băng thông, p95/p99, packet loss, MTU và hành trình ứng dụng có đáp ứng tải thực không? |
| **Cost Optimization** | TCO của VPN/private/hybrid so với giá trị giảm rủi ro và tải nghiệp vụ như thế nào? |
| **Sustainability** | Có tránh truyền dữ liệu lặp lại, tài nguyên dự phòng quá mức và xử lý không cần thiết không? |

**Kết luận:** VPN site-to-site và đường truyền riêng là hai công cụ để kết nối trung tâm dữ liệu với cloud, mỗi công cụ có ưu điểm và giới hạn riêng. Chất lượng kiến trúc được xác định bởi **tính đúng đắn của dữ liệu, bảo mật, khả năng chịu lỗi, hiệu năng thực đo, chi phí toàn vòng đời và năng lực vận hành**. Một quyết định hợp lý cần bắt đầu từ kịch bản nghiệp vụ, kiểm chứng bằng load test/failover và được xem lại khi yêu cầu thay đổi.
