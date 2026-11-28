# On-premises, cloud và hybrid network

Trong bảo mật mạng, lựa chọn hạ tầng **on-premises**, **cloud** hay **hybrid** không chỉ là quyết định nơi đặt máy chủ. Mỗi mô hình thay đổi cách thiết lập ranh giới tin cậy, cấp đường đi cho lưu lượng, phân đoạn hệ thống, xác thực kết nối, quản lý thiết bị bảo mật và xử lý sự cố. Một dịch vụ có thể dùng cùng giao thức HTTPS ở cả ba môi trường nhưng có **đường đi gói tin, quyền quản trị và điểm mất an toàn** rất khác nhau.

Bài học thuộc chương **Mô hình mạng** của module **SECURITY_NETWORK_SECURITY**, tập trung vào cách nhận diện cấu trúc mạng, phân tích luồng lưu lượng và mô hình hóa mối đe dọa để xây dựng kiến trúc an toàn. Những khái niệm như firewall, VPN, IDS/IPS, DNS, Wi-Fi, giám sát xâm nhập và bảo mật hạ tầng đám mây sẽ được liên hệ trực tiếp tới từng mô hình.

## 1. Khái niệm và ranh giới của ba mô hình

### 1.1. On-premises network

**On-premises** là mạng phục vụ các hệ thống do tổ chức triển khai, quản lý trong cơ sở hạ tầng riêng như phòng máy, trung tâm dữ liệu nội bộ hoặc vị trí thuê đặt thiết bị (colocation). Không nhất thiết mọi thiết bị phải nằm tại văn phòng; điều quyết định là **tổ chức chịu trách nhiệm đáng kể đối với thiết bị mạng và cách vận hành hạ tầng**.

Thành phần thường gặp:

- **LAN/VLAN/VRF:** tổ chức các miền mạng và phân đoạn người dùng, máy chủ, quản trị, khách truy cập.
- **Switch, router, firewall:** chuyển mạch, định tuyến và thực thi chính sách giữa các phân đoạn hoặc tới Internet/WAN.
- **DMZ:** khu vực riêng cho các dịch vụ có giao tiếp với bên ngoài như reverse proxy, VPN gateway hoặc máy chủ công khai.
- **DNS, DHCP, NAC/802.1X:** phân giải tên, cấp địa chỉ và kiểm soát thiết bị được phép kết nối.
- **IDS/IPS, SIEM, packet capture:** phát hiện bất thường và điều tra lưu lượng trên những vị trí quan sát được.
- **Máy chủ vật lý, máy ảo, hệ thống lưu trữ:** chạy ứng dụng và dữ liệu nghiệp vụ.

Ở mô hình này, tổ chức thường có khả năng tùy chỉnh topology, thiết bị và cách lấy gói tin sâu hơn. Đổi lại, đội vận hành phải quan tâm đến vòng đời phần cứng, nguồn điện, đường truyền, cập nhật firmware, dự phòng và bảo mật truy cập vật lý.

### 1.2. Cloud network

**Cloud network** là mạng được định nghĩa bằng các tài nguyên và dịch vụ của nền tảng đám mây. Trong public cloud, tổ chức thường tạo **mạng ảo** như VPC (Virtual Private Cloud) hoặc VNet (Virtual Network), subnet, route table, chính sách lọc lưu lượng, gateway và load balancer qua API hoặc giao diện quản trị.

Khả năng có sẵn phụ thuộc nhà cung cấp và loại dịch vụ đang dùng:

- **IaaS:** tổ chức quản lý phần lớn cấu hình hệ điều hành, ứng dụng, mạng ảo và quyền truy cập máy ảo; nhà cung cấp quản lý hạ tầng vật lý nền tảng.
- **PaaS/managed service:** nhiều lớp vận hành được nhà cung cấp quản lý; tổ chức vẫn phải cấu hình danh tính, truy cập mạng, dữ liệu và các tùy chọn bảo mật được cung cấp.
- **SaaS:** tổ chức thường kiểm soát ít thành phần mạng bên trong hơn, nhưng vẫn chịu trách nhiệm về danh tính người dùng, chính sách truy cập, cấu hình và dữ liệu theo hợp đồng dịch vụ.

Tên tính năng có thể khác nhau: **security group** thường là cơ chế lọc lưu lượng gắn với tài nguyên; **network ACL** là cơ chế lọc ở phạm vi subnet trong một số nền tảng; **cloud firewall** có thể kiểm soát lưu lượng tập trung hoặc ở biên. Đặc tính stateful/stateless và cách áp dụng cụ thể **không giống nhau ở mọi nhà cung cấp**, nên phải đối chiếu tài liệu nền tảng.

**Cloud không mặc định là công khai:** một máy chủ trong cloud có thể chỉ nhận kết nối từ mạng nội bộ hoặc qua private endpoint. Ngược lại, một cấu hình cloud sai có thể tạo đường truy cập Internet không mong muốn dù máy chủ nằm trong một VPC riêng.

### 1.3. Hybrid network

**Hybrid network** kết nối hạ tầng on-premises và cloud để các ứng dụng, dữ liệu hoặc người dùng có thể giao tiếp theo chính sách xác định. Hai môi trường có thể kết nối qua:

- **Site-to-site IPsec VPN:** đường hầm mã hóa qua mạng trung gian, thường là Internet.
- **Kết nối riêng của nhà cung cấp hoặc đối tác:** đường truyền riêng tới cloud; tính riêng tư về kết nối không đồng nghĩa lưu lượng tự động được mã hóa.
- **SD-WAN/WAN do doanh nghiệp quản lý:** chọn đường đi và chính sách giữa nhiều địa điểm và cloud.
- **Hub/transit network, gateway hoặc mạng trung gian:** tập trung định tuyến và kiểm soát nhiều mạng ảo, văn phòng, trung tâm dữ liệu.

Một hệ thống chỉ dùng public cloud hoặc chỉ dùng hạ tầng tại trung tâm dữ liệu là chưa phải hybrid. **Multi-cloud** nghĩa là sử dụng nhiều nền tảng cloud; môi trường multi-cloud có thể có hoặc không có kết nối on-premises, nên không được đồng nhất hai khái niệm.

## 2. So sánh theo góc nhìn bảo mật mạng

| Tiêu chí | On-premises | Cloud | Hybrid |
| --- | --- | --- | --- |
| Hạ tầng mạng | Thiết bị và kết nối vật lý do tổ chức hoặc bên thuê vận hành | Mạng ảo, gateway và dịch vụ do nền tảng cung cấp | Kết hợp hai miền quản trị và đường liên kết giữa chúng |
| Phân đoạn | VLAN, VRF, ACL, firewall, microsegmentation | VPC/VNet, subnet, security policy, firewall, microsegmentation | Chính sách nhất quán tại từng miền **và** điểm giao nhau |
| Kết nối ngoại vi | ISP, WAN, VPN, DMZ, reverse proxy | Internet gateway, load balancer, private endpoint, VPN | VPN/private circuit, transit gateway, bộ định tuyến biên |
| Danh tính & quyền | AD/LDAP, NAC, tài khoản thiết bị, hệ thống IAM nội bộ | Cloud IAM, vai trò dịch vụ, định danh workload, chính sách tài nguyên | Liên kết định danh và hạn chế quyền xuyên miền |
| Quan sát | SPAN/TAP, NetFlow, firewall/IDS logs, packet capture | Flow logs, audit API, load balancer logs, dịch vụ giám sát cloud | Kết hợp telemetry, đồng bộ thời gian và liên kết sự kiện |
| Khả năng mở rộng | Phụ thuộc khả năng phần cứng, đường truyền và dự phòng | Có thể cấp phát linh hoạt trong hạn mức và thiết kế nền tảng | Phụ thuộc cả hạ tầng riêng, cloud và đường liên kết |
| Rủi ro nổi bật | Điểm lỗi vật lý, cấu hình mạng cũ, thiếu cập nhật thiết bị | Sai cấu hình IAM/route/firewall, lộ dịch vụ và khóa truy cập | Route/DNS phức tạp, CIDR trùng, chính sách lệch, lỗi liên kết |

Không có mô hình nào tự động "an toàn hơn". Mức độ an toàn phụ thuộc vào **ranh giới tin cậy, tài sản, mối đe dọa, quyền quản trị, thiết kế dự phòng và chất lượng vận hành**.

## 3. Đường đi gói tin và các ranh giới tin cậy

### 3.1. Ví dụ mạng on-premises

~~~mermaid
flowchart LR
    I["Internet"] --> F["Edge firewall / IPS"]
    F --> D["DMZ: reverse proxy"]
    D --> A["App VLAN"]
    A --> B["Database VLAN"]
    U["User LAN"] --> C["Internal firewall / ACL"]
    C --> A
    M["Management VLAN"] --> X["Bastion / quản trị"]
    X --> A
~~~

Trong sơ đồ này, **DMZ không phải vùng hoàn toàn tin cậy**. Máy chủ có thể nhận yêu cầu từ Internet phải được giới hạn quyền đến lớp ứng dụng; lớp ứng dụng chỉ được kết nối tới đúng cổng cần thiết ở cơ sở dữ liệu. Mạng quản trị được tách ra để tránh truy cập quản trị trực tiếp từ máy người dùng thông thường.

**Lưu lượng north-south** là lưu lượng vào/ra một miền mạng, ví dụ Internet ↔ DMZ. **Lưu lượng east-west** là trao đổi giữa các máy chủ, subnet hoặc dịch vụ bên trong. Chặn tốt north-south vẫn để lại nguy cơ di chuyển ngang nếu east-west được cho phép quá rộng.

### 3.2. Ví dụ mạng cloud

~~~mermaid
flowchart LR
    U["Người dùng"] --> DNS["DNS"]
    DNS --> LB["Public load balancer / WAF"]
    LB --> APP["Private app subnet"]
    APP --> DB["Private database subnet"]
    APP --> NAT["Egress NAT / proxy"]
    NAT --> EXT["Dịch vụ ngoài được phép"]
    ADM["Quản trị viên"] --> ID["SSO / IAM + truy cập quản trị"]
    ID --> APP
~~~

Một triển khai ví dụ có:

- **VPC/VNet 10.20.0.0/16**; các subnet ở những vùng sẵn sàng (availability zone) được chọn khi nền tảng hỗ trợ.
- **Public subnet 10.20.1.0/24:** đặt thành phần cần tiếp xúc Internet theo thiết kế, chẳng hạn thành phần mạng của load balancer.
- **Private application subnet 10.20.10.0/24:** chạy ứng dụng, không cấp địa chỉ Internet công khai cho instance.
- **Private data subnet 10.20.20.0/24:** chạy database, chỉ nhận lưu lượng từ ứng dụng được cấp quyền.

Các địa chỉ trên chỉ mang tính minh họa; khi triển khai thật phải kiểm tra vùng địa chỉ, định tuyến, subnet ở nhiều zone và khả năng tránh trùng địa chỉ với các mạng khác.

**Lưu ý:** Một subnet được gọi là "private" thường có nghĩa không có tuyến nhận kết nối trực tiếp từ Internet theo thiết kế mạng cụ thể. Tên subnet **không phải bằng chứng** rằng mọi tài nguyên bên trong đều an toàn: phải kiểm tra địa chỉ public, route, rule lọc, public endpoint của dịch vụ quản lý và quyền gọi API.

**NAT cho đường ra** thường giúp tài nguyên có địa chỉ riêng mở kết nối ra ngoài mà không trực tiếp nhận kết nối khởi tạo từ Internet qua NAT đó. NAT không thay thế egress firewall, chính sách DNS, kiểm soát địa chỉ đích hoặc xác thực ứng dụng.

### 3.3. Ví dụ hybrid network

~~~mermaid
flowchart LR
    subgraph ON["On-premises / Data center"]
        ERP["ERP: 10.10.30.10"]
        OFW["On-prem firewall"]
        ERP --- OFW
    end
    subgraph LINK["Liên kết hybrid"]
        VPN["IPsec VPN hoặc kết nối riêng có bảo vệ phù hợp"]
    end
    subgraph CLOUD["Cloud: 10.20.0.0/16"]
        CGW["Cloud VPN / transit gateway"]
        API["Private API: 10.20.10.20"]
        DB["Database: 10.20.20.10"]
        CGW --- API
        API --> DB
    end
    OFW <-->|"Tuyến và chính sách cho luồng được phép"| VPN
    VPN <--> CGW
~~~

Để API trên cloud trao đổi với ERP tại on-premises, có **ít nhất hai chiều lưu lượng** cần xét: chiều yêu cầu và chiều phản hồi. Firewall stateful thường cho phép phản hồi của kết nối đã được cho phép, nhưng bảng định tuyến của cả hai miền vẫn phải có đường quay về phù hợp. Đường truyền bảo mật không tự tạo ra route hoặc quyền truy cập.

## 4. Những nguyên tắc chung khi bảo vệ cả ba mô hình

### 4.1. Phân đoạn theo chức năng và độ tin cậy

Không gom tất cả tài nguyên vào một miền mạng chỉ vì chúng thuộc cùng tổ chức. Nên tách tối thiểu các nhóm có rủi ro khác nhau như:

- **Biên/DMZ:** dịch vụ có giao tiếp với bên ngoài.
- **Ứng dụng:** thành phần xử lý nghiệp vụ, chỉ nhận kết nối từ lớp đã xác định.
- **Dữ liệu:** database, hệ thống lưu trữ và dịch vụ chứa thông tin nhạy cảm.
- **Quản trị:** bastion, hệ thống quản lý cấu hình, thiết bị điều khiển và công cụ bảo mật.
- **Người dùng/khách/thiết bị đặc thù:** vùng có mức độ tin cậy hoặc yêu cầu giám sát khác nhau.

Áp dụng **default deny** tại các điểm thực thi chính sách thích hợp: chỉ mở luồng có nhu cầu thực sự. Với cloud, phân đoạn có thể được thực thi bằng security group, policy workload hoặc dịch vụ firewall; với on-premises có thể dùng VLAN/VRF, ACL và firewall. Cần phân biệt **tách miền định tuyến** với **kiểm soát quyền truy cập**: VLAN hay subnet khác nhau không tự bảo đảm mọi giao tiếp đều bị lọc.

### 4.2. Xác thực danh tính kết nối và bảo mật dữ liệu

**Địa chỉ IP không đủ để chứng minh danh tính người gọi.** Ứng dụng cần xác thực người dùng hoặc workload bằng cơ chế thích hợp; kết nối giữa dịch vụ có thể dùng mTLS, danh tính workload hoặc token được bảo vệ và kiểm tra quyền.

- Dùng **TLS/HTTPS** ở các chặng cần bảo vệ nội dung và xác thực đầu mút; xác minh chứng chỉ và hostname.
- Dùng **IPsec** hoặc giải pháp tunnel phù hợp cho kênh truyền giữa các miền khi mô hình đe dọa yêu cầu mã hóa ở lớp mạng.
- Dùng **IAM, RBAC và cấp quyền tối thiểu** cho người quản trị cũng như định danh dịch vụ.
- Tách tài khoản quản trị khỏi tài khoản thường; dùng **MFA** và kiểm soát truy cập đặc quyền.
- Quản lý **khóa, bí mật, chứng chỉ** qua cơ chế có vòng đời, phân quyền và thu hồi rõ ràng.

Một đường riêng (private circuit) giảm sự phụ thuộc vào Internet công cộng ở một số khía cạnh, nhưng **không mặc nhiên mã hóa payload**. Ngược lại, VPN đã mã hóa dữ liệu vẫn cần kiểm soát định tuyến, phân quyền và bảo vệ tài nguyên ở hai đầu.

### 4.3. Quan sát lưu lượng và phát hiện xâm nhập

Vị trí đặt cảm biến quan trọng không kém bản thân công cụ:

| Loại dữ liệu | Trên on-premises | Trên cloud/hybrid | Mục đích |
| --- | --- | --- | --- |
| Network flow/connection logs | NetFlow/IPFIX, firewall logs, router logs | VPC/VNet flow logs, gateway/firewall logs | Tìm nguồn, đích, cổng, chiều truyền, chặn/cho phép, bất thường theo thời gian |
| DNS logs | DNS resolver nội bộ | Resolver, private DNS, DNS forwarding | Nhận diện truy vấn bất thường, tên miền sai hoặc vấn đề phân giải |
| IDS/IPS | TAP/SPAN hoặc inline sensor | Network sensor khả dụng, service IDS, NDR/host sensor | Phát hiện dấu hiệu tấn công trong phần lưu lượng có thể quan sát |
| Application/TLS logs | Reverse proxy, API gateway, ứng dụng | Load balancer, ingress, gateway, service mesh | Liên kết sự kiện mạng với request và danh tính ứng dụng |
| Control-plane audit | Nhật ký thay đổi firewall, VPN, switch | Cloud audit logs, IAM events, policy changes | Điều tra ai sửa route, rule hoặc quyền truy cập |

Packet capture và IDS/IPS không luôn nhìn thấy nội dung nằm trong TLS hay IPsec. Muốn phân tích payload cần chọn điểm quan sát thích hợp và tuân thủ chính sách xử lý dữ liệu; ở nhiều tình huống, **metadata cộng với log ứng dụng** là nguồn điều tra thực tế hơn. Hãy đồng bộ thời gian, có quy tắc giữ log và hạn chế truy cập log chứa dữ liệu nhạy cảm.

### 4.4. Bảo đảm sẵn sàng và khả năng phục hồi

Sự cố có thể đến từ **thiết bị**, **đường kết nối**, **chứng chỉ**, **DNS**, **route**, **quá tải**, **nhà cung cấp** hoặc **sai cấu hình**. Kiến trúc cần:

- Xác định các điểm lỗi đơn: firewall, VPN gateway, đường ISP, đường liên kết riêng, vùng triển khai, DNS resolver.
- Thiết kế **dự phòng phù hợp** và kiểm thử failover theo tình huống thật.
- Giới hạn tải bằng rate limit, timeout, quota, circuit breaker và các biện pháp giảm thiểu DDoS.
- Xác định chỉ tiêu vận hành theo **trải nghiệm end-to-end**, không chỉ trạng thái từng máy chủ.
- Kiểm tra cả **mất kết nối từng phần**: một phía không nhận được phản hồi, một tuyến mất nhưng tuyến khác vẫn báo hoạt động, hoặc DNS trả về địa chỉ cũ.

## 5. Trách nhiệm bảo mật thay đổi như thế nào?

**On-premises:** tổ chức phải tự bảo vệ phòng máy, cổng kết nối, thiết bị vật lý, firmware, hệ điều hành, cấu hình firewall, định tuyến, phân quyền và giám sát, trừ phần đã được ủy thác cho nhà cung cấp theo hợp đồng. Một thay đổi sai trên core switch có thể ảnh hưởng nhiều dịch vụ cùng lúc.

**Cloud:** nhà cung cấp bảo vệ phần hạ tầng thuộc phạm vi họ vận hành, còn khách hàng phải cấu hình và vận hành các phần trong quyền kiểm soát của mình. Ranh giới **shared responsibility** khác nhau giữa IaaS, PaaS và SaaS. Ví dụ nhà cung cấp quản lý phần cứng host nhưng không tự quyết định một ứng dụng của khách có được mở TCP/5432 tới Internet hay không.

**Hybrid:** trách nhiệm trải qua nhiều nhóm và nhiều miền. Nếu kết nối giữa ERP on-premises và API cloud lỗi, có thể cần phối hợp đội mạng, đội cloud, đội ứng dụng và nhà cung cấp đường truyền. Vì vậy phải ghi rõ **chủ sở hữu route, DNS, chính sách firewall, VPN, chứng chỉ, logging và quy trình xử lý sự cố**.

Các mô hình tin cậy đều cần tuân thủ nguyên tắc: **mỗi kết nối và hành động phải được xác thực, phân quyền và giám sát theo rủi ro**. Vị trí "ở trong LAN" hay "ở trong VPC" chỉ là một tín hiệu bối cảnh, không đủ để cấp quyền vô điều kiện.

## 6. Thiết kế kết nối hybrid an toàn

Hybrid mang lại khả năng tận dụng hệ thống hiện có và dịch vụ cloud, nhưng thường tạo ra rủi ro tích hợp lớn nhất. Cần giải quyết có hệ thống các vấn đề sau.

### 6.1. Quy hoạch địa chỉ, tuyến và miền định tuyến

Giả sử:

| Miền | Dải địa chỉ ví dụ | Vai trò |
| --- | --- | --- |
| Data center | 10.10.0.0/16 | Hạ tầng on-premises |
| ERP subnet | 10.10.30.0/24 | ERP được truy cập từ cloud |
| Cloud VPC | 10.20.0.0/16 | Mạng ảo ứng dụng cloud |
| Cloud API subnet | 10.20.10.0/24 | Dịch vụ gọi ERP |
| Cloud DB subnet | 10.20.20.0/24 | Database riêng của cloud |

Đây là các dải private IPv4 **không trùng nhau** trong ví dụ. Trong thực tế, cần dùng IPAM hoặc tài liệu địa chỉ để tránh trùng dải giữa văn phòng, VPN người dùng, các VPC và môi trường đối tác. Khi hai miền trùng CIDR, định tuyến trực tiếp có thể không xác định được đúng đích; NAT hoặc đánh lại địa chỉ chỉ là giải pháp thiết kế cần đánh giá kỹ.

Nếu API 10.20.10.20 cần gọi ERP 10.10.30.10, tối thiểu phải kiểm tra:

1. Bảng route ở phía cloud có đường đến **10.10.30.0/24** qua gateway hybrid phù hợp.
2. Phía on-premises có route phản hồi tới **10.20.10.0/24** qua liên kết tương ứng.
3. Firewall và policy hai phía cho phép **đúng nguồn, đích, giao thức và cổng**; không mở toàn bộ 10.0.0.0/8 vì tiện.
4. Địa chỉ có bị NAT ở một chặng không, và danh tính nguồn mà firewall nhìn thấy có đúng như thiết kế không.
5. Khi có nhiều tuyến hoặc gateway, cơ chế chọn tuyến và failover có tránh **asymmetric routing** gây lỗi với firewall stateful không.

**BGP** thường được dùng để trao đổi route động giữa router/gateway ở các kết nối hybrid có hỗ trợ. Tuy nhiên, việc route được quảng bá thành công không chứng minh dịch vụ đích có quyền truy cập hay còn hoạt động. Cần kiểm soát prefix được quảng bá/nhận, lựa chọn tuyến và ảnh hưởng của route rò rỉ.

### 6.2. DNS và khám phá dịch vụ

Tổ chức có thể dùng tên nội bộ như **erp.corp.example** ở on-premises và **api.internal.example** trên cloud. Khi đó cần quyết định:

- Resolver nào chịu trách nhiệm cho từng vùng tên; có dùng **conditional forwarding** hay private DNS zone không?
- Truy vấn DNS giữa hai phía đi qua đâu và có được firewall cho phép không?
- Khi dịch vụ đổi địa chỉ hoặc chuyển vùng, DNS cache/TTL có làm khách kết nối tới đích cũ không?
- Có nguy cơ **split-horizon DNS** cấu hình sai dẫn tới cùng một tên phân giải thành địa chỉ không mong muốn không?
- Có log để phân biệt sự cố DNS với sự cố route hay không?

DNSSEC giúp xác thực dữ liệu DNS được ký trong phạm vi triển khai; **không tự mã hóa truy vấn**. Mã hóa DNS cần cơ chế khác như DoT/DoH phù hợp, đồng thời cân nhắc khả năng quan sát và chính sách sử dụng DNS nội bộ.

### 6.3. Hiệu năng, MTU và xử lý lỗi

Kết nối on-premises ↔ cloud tạo thêm độ trễ và phụ thuộc đường WAN. Tunnel IPsec bổ sung overhead, có thể làm giảm **MTU hiệu dụng**. Một đường ping gói nhỏ thành công không đủ chứng minh yêu cầu TLS, truyền file hoặc giao dịch dài sẽ hoạt động ổn định.

Cần đánh giá:

- Round-trip time, packet loss, jitter, throughput và số kết nối đồng thời.
- MTU/PMTUD, nguy cơ phân mảnh hoặc chặn ICMP cần cho phát hiện đường đi.
- Timeout giữa ứng dụng, proxy, firewall, VPN và dịch vụ; thứ tự timeout phải phù hợp.
- Retry, idempotency, hàng đợi, cache và hành vi khi on-premises tạm mất kết nối.
- Dung lượng và tính sẵn sàng của **cả đường chính lẫn đường dự phòng**.

Không nên tự ý "sửa" lỗi kết nối bằng cách tắt kiểm tra TLS, mở firewall toàn bộ hoặc vô hiệu hóa logging. Những thao tác đó có thể che giấu nguyên nhân và mở rộng phạm vi tấn công.

### 6.4. Không biến liên kết hybrid thành một LAN phẳng

Một VPN site-to-site có thể tạo đường IP giữa hai bên, nhưng không có nghĩa mọi máy chủ đều nên tin cậy lẫn nhau. Giữ chính sách tại **điểm giao nhau** và **bên trong mỗi miền**:

- Chỉ định nhóm nguồn cloud được phép truy cập nhóm đích on-premises.
- Chỉ mở các cổng nghiệp vụ đã phê duyệt; cấm luồng quản trị không cần thiết.
- Ghi log các thay đổi route/policy và các kết nối bất thường.
- Tách đường truy cập quản trị khỏi đường dữ liệu ứng dụng.
- Khi cần, áp dụng xác thực workload và TLS/mTLS **bên trong đường hầm**.

Đây cũng là tư duy nền tảng của **Zero Trust**: cấp quyền theo danh tính và ngữ cảnh của yêu cầu cụ thể, đồng thời kiểm tra liên tục trong khả năng của hệ thống, thay vì tin toàn bộ miền vì đã nối VPN.

## 7. Mô hình hóa mối đe dọa theo từng môi trường

Một cách đơn giản là trả lời: **tài sản là gì, ai có thể tấn công, điểm vào ở đâu, dữ liệu đi qua đâu, và biện pháp nào ngăn/phát hiện/khôi phục?**

| Môi trường | Kịch bản tấn công/sự cố | Tác động CIA | Kiểm soát cần đánh giá |
| --- | --- | --- | --- |
| On-premises | Máy người dùng bị nhiễm mã độc quét và truy cập ngang sang database | Bí mật, toàn vẹn, sẵn sàng | Phân đoạn user/server, firewall east-west, EDR, giám sát |
| On-premises | Thiết bị firewall biên lỗi hoặc ISP mất kết nối | Sẵn sàng | HA, ISP dự phòng, giám sát failover, diễn tập sự cố |
| Cloud | Security policy/route mở cổng quản trị hoặc database ra Internet | Bí mật, toàn vẹn | Least privilege, kiểm tra cấu hình, asset inventory, cảnh báo thay đổi |
| Cloud | Định danh cloud có quyền quá lớn bị lộ khóa | Cả ba | IAM tối thiểu, secret rotation, MFA cho con người, audit API, phát hiện bất thường |
| Hybrid | Route quảng bá sai làm lưu lượng đi nhầm hoặc mất đường về | Sẵn sàng; có thể ảnh hưởng bí mật | Prefix filtering, route review, giám sát luồng và phân tích đường đi |
| Hybrid | Firewall mở rộng toàn bộ hai mạng khi triển khai VPN | Bí mật, toàn vẹn, sẵn sàng | Chỉ cấp luồng cần thiết, xác thực ứng dụng, rule review |
| Hybrid | VPN còn kết nối nhưng DNS ERP không phân giải được | Sẵn sàng | DNS forwarding, giám sát resolver, kiểm thử phân giải ở hai chiều |

**Kiểm soát phòng ngừa** (ví dụ phân đoạn) nên đi cùng **phát hiện** (log, IDS/IPS, giám sát bất thường) và **khôi phục** (backup cấu hình, runbook, dự phòng). Không một biện pháp riêng lẻ nào giải quyết mọi dạng tấn công hoặc sự cố.

## 8. Case study: đưa ứng dụng đặt hàng lên cloud, giữ ERP ở data center

### 8.1. Bối cảnh

Một công ty đang chạy ERP tại data center, muốn đưa frontend và API đặt hàng lên cloud để mở rộng theo lượng truy cập. Cơ sở dữ liệu ERP và một số quy trình nội bộ vẫn ở on-premises.

Yêu cầu:

1. Khách Internet chỉ được truy cập frontend/API công khai qua HTTPS.
2. Cloud API được phép gọi **đúng endpoint ERP** phục vụ kiểm tra tồn kho và ghi nhận đơn.
3. Người dùng Internet không được truy cập trực tiếp ERP, database hoặc mạng quản trị.
4. Khi đường hybrid gặp sự cố, hệ thống phải trả lỗi có kiểm soát hoặc xếp hàng xử lý phù hợp với nghiệp vụ; không ghi nhận đơn trùng.
5. Đội vận hành xác định được lỗi ở DNS, route, VPN, firewall, ứng dụng hay ERP.

### 8.2. Sơ đồ luồng

~~~mermaid
flowchart LR
    C["Khách hàng"] -->|"HTTPS 443"| W["Cloud WAF + Load Balancer"]
    W -->|"TLS 8443"| A["Cloud Order API"]
    A -->|"TLS 5432"| D[("Cloud Order DB")]
    A -->|"TLS 443 / VPN hoặc đường riêng"| H["Hybrid Gateway"]
    H --> F["On-prem Firewall"]
    F -->|"TLS 443"| E["ERP API"]
    O["Đội vận hành"] --> MON["Logs + Metrics + Traces"]
    MON -.-> A
    MON -.-> H
    MON -.-> F
~~~

Các cổng trên là **giả định cho bài học**, không phải mặc định của mọi sản phẩm. Khi triển khai, cổng và giao thức phải lấy từ thiết kế hệ thống thực tế.

### 8.3. Lập ma trận luồng trước khi cấu hình

| Nguồn | Đích | Giao thức/cổng ví dụ | Chính sách | Lý do |
| --- | --- | --- | --- | --- |
| Internet | Public load balancer | TCP/443 | Allow có giới hạn và bảo vệ WAF/DDoS | Khách sử dụng ứng dụng |
| Load balancer | Order API private | TCP/8443 (TLS) | Allow từ định danh/tập nguồn của LB | Chuyển yêu cầu vào ứng dụng |
| Order API | Cloud Order DB | TCP/5432 (TLS) | Allow từ ứng dụng được cấp quyền | Truy vấn dữ liệu đơn hàng |
| Order API 10.20.10.20 | ERP API 10.10.30.10 | TCP/443 (TLS) | Allow qua gateway hybrid | Đồng bộ nghiệp vụ |
| Internet | ERP API | Mọi cổng | Deny | Không công khai ERP |
| User LAN thông thường | Database/thiết bị quản trị | Mặc định deny | Deny trừ ngoại lệ có duyệt | Ngăn truy cập ngang |

Giới hạn quyền bằng nhóm tài nguyên, danh tính workload và chính sách ứng dụng khi công nghệ hỗ trợ. Bảng địa chỉ IP/cổng là lớp tối thiểu, không thay thế xác thực và phân quyền ở API.

### 8.4. Tình huống lỗi để diễn tập

**Tình huống A — VPN mất kết nối:** Cloud API không gọi được ERP. Ứng dụng phải có timeout, circuit breaker và cơ chế retry có giới hạn; chỉ xếp hàng xử lý bất đồng bộ nếu nghiệp vụ cho phép. Dùng idempotency key hoặc cơ chế tương đương để tránh tạo đơn trùng khi kết nối phục hồi.

**Tình huống B — Route chiều đi đúng, chiều về sai:** VPN báo trạng thái "up" nhưng kết nối TCP không hoàn tất. Kiểm tra route ở hai đầu, trạng thái firewall, NAT và khả năng asymmetric routing; không kết luận sự cố ứng dụng từ một triệu chứng timeout.

**Tình huống C — ERP đổi địa chỉ:** Cloud vẫn phân giải hostname cũ do forwarding/cache hoặc hồ sơ DNS chưa cập nhật. Kiểm tra resolver được dùng ở cloud và on-premises, TTL, phân giải private zone và cấu hình firewall tương ứng.

**Tình huống D — Một cloud instance bị xâm nhập:** Nếu network policy mở quá rộng, kẻ tấn công có thể tiếp cận ERP qua đường hybrid. Giới hạn nguồn, đích, cổng; xác thực danh tính của API gọi ERP; giám sát lưu lượng bất thường và có phương án vô hiệu hóa kết nối nhanh.

## 9. Quy trình kiểm tra khi mạng không thông hoặc nghi mất an toàn

Thực hiện các kiểm tra dưới đây **trong hệ thống bạn được phép quản trị**, từ đúng vị trí của máy khách, API hoặc gateway. Các lệnh chỉ là ví dụ; trên hệ điều hành và môi trường cloud khác nhau có công cụ tương đương.

### 9.1. Kiểm tra tên miền và tầng ứng dụng

~~~bash
# Kiểm tra tên miền mà máy đang sử dụng có phân giải được không
nslookup api.internal.example

# Kiểm tra bắt tay TLS và phản hồi HTTP của API
curl -Iv https://api.internal.example/
~~~

Nếu DNS không trả về địa chỉ dự kiến, hãy điều tra resolver, private zone và forwarding trước. Nếu có IP đúng nhưng TLS không thiết lập, kiểm tra đường đi, firewall, endpoint và chứng chỉ. HTTP 401/403 cho thấy đã nhận phản hồi ở tầng ứng dụng nhưng có vấn đề xác thực hoặc phân quyền; không đồng nghĩa "mạng bị đứt".

### 9.2. Kiểm tra kết nối, định tuyến và log

~~~bash
# Trên Linux: xem tuyến dự kiến tới đích
ip route get 10.10.30.10

# Trên Linux: kiểm tra cổng TCP từ máy nguồn được phép
nc -vz -w 5 10.10.30.10 443

# Trên Windows PowerShell: kiểm tra cổng TCP
Test-NetConnection 10.10.30.10 -Port 443
~~~

Những phép kiểm tra này **không tự chứng minh** lưu lượng ứng dụng thực tế đi đúng chính sách hoặc mã hóa. Để xác nhận, cần đối chiếu đường đi với route table, security policy, firewall/VPN logs, flow logs và kết quả xác thực TLS thực tế. Một lần ping thất bại không đủ kết luận TCP/443 không hoạt động vì ICMP có thể bị chặn.

### 9.3. Thứ tự chẩn đoán gợi ý

1. **Danh tính nguồn và đích:** nguồn thật là máy nào, đích đã phân giải ra IP gì, có NAT không?
2. **Tên miền:** DNS trả lời đúng từ từng miền mạng chưa?
3. **Định tuyến:** có đường đi và đường về? Có chồng lấn CIDR hay lệch chính sách quảng bá route không?
4. **Kiểm soát truy cập:** firewall, security group, ACL, network policy, gateway có cho phép đúng luồng?
5. **Kênh mã hóa và xác thực:** tunnel lên đúng peer? TLS certificate/hostname hợp lệ? Xác thực workload và quyền ứng dụng đúng?
6. **Khả năng đáp ứng:** service đang lắng nghe cổng, phụ thuộc sẵn sàng, latency/timeout và capacity có phù hợp?
7. **Bằng chứng:** đối chiếu log cùng thời điểm ở hai miền, cập nhật sơ đồ và ghi rõ thay đổi đã thực hiện.

Thứ tự này giúp phân biệt vấn đề **network reachability**, **security policy**, **TLS**, **application authorization** và **availability**.

## 10. Lựa chọn mô hình nào cho hệ thống?

Việc lựa chọn là kết quả của nhu cầu nghiệp vụ và rủi ro cụ thể:

| Câu hỏi thiết kế | Khi nào đáng cân nhắc | Cần làm rõ về bảo mật |
| --- | --- | --- |
| Có hệ thống chuyên dụng, thiết bị công nghiệp hoặc phụ thuộc mạng nội bộ khó di dời? | On-premises hoặc hybrid | Phân đoạn OT/IT, truy cập quản trị, kiểm soát liên kết ra ngoài |
| Cần mở rộng nhanh dịch vụ web và triển khai ở nhiều vùng? | Cloud hoặc hybrid | IAM, mạng ảo, WAF/DDoS, hạ tầng bằng mã, kiểm soát cấu hình |
| Có dữ liệu/phụ thuộc phải ở lại data center nhưng ứng dụng mới dùng cloud? | Hybrid | Kết nối an toàn, DNS, routing, phân quyền, độ trễ, phương án khi mất WAN |
| Có yêu cầu khả năng phục hồi cao? | Bất kỳ mô hình nào có thiết kế dự phòng phù hợp | Định nghĩa SLO, kiểm thử failover, giải pháp DR, tránh điểm lỗi đơn |
| Muốn đơn giản hóa vận hành mạng? | Xem xét dịch vụ quản lý và khả năng hiện tại của đội ngũ | Trách nhiệm nhà cung cấp/khách hàng, giám sát, giới hạn khả năng kiểm soát |
| Có yêu cầu lưu trữ dữ liệu và kiểm soát truy cập theo quy định? | Đánh giá theo quy định và rủi ro, không kết luận chỉ từ vị trí triển khai | Vị trí dữ liệu, hợp đồng, mã hóa, IAM, audit, sao lưu và khả năng chứng minh tuân thủ |

Không nên chọn on-premises chỉ vì nghĩ rằng "ở trong công ty sẽ an toàn", hoặc chọn cloud vì nghĩ "nhà cung cấp đã bảo mật mọi thứ". **Khả năng áp dụng đúng kiểm soát, vận hành và phục hồi** mới quyết định hiệu quả.

## 11. Các nhầm lẫn phổ biến

1. **"Mạng private thì tin cậy toàn bộ."** IP private/VLAN/VPC không chứng minh danh tính người dùng hay workload; vẫn cần xác thực, phân quyền và kiểm soát east-west.
2. **"VPN tạo ra một mạng an toàn hoàn chỉnh."** VPN bảo vệ phạm vi đường hầm theo cấu hình; lỗi ở hai đầu, route sai và quyền quá rộng vẫn gây rủi ro.
3. **"Đường truyền riêng luôn được mã hóa."** Kết nối riêng là đặc tính đường đi; yêu cầu bí mật và toàn vẹn cần xác định công nghệ mã hóa cụ thể.
4. **"Cloud firewall thay thế mọi kiểm soát ứng dụng."** Lọc IP/cổng không ngăn ứng dụng nhận dữ liệu nghiệp vụ sai hoặc danh tính hợp lệ nhưng thiếu quyền.
5. **"Có một VPC/VNet là mọi dịch vụ đều cách ly."** Phải xem subnet, route, endpoint công khai, policy và kết nối tới mạng khác.
6. **"Hybrid chỉ cần cấu hình VPN là xong."** Phải thiết kế CIDR, route hai chiều, DNS, lưu lượng cho phép, khả năng giám sát, hiệu năng và failover.
7. **"Thấy VPN up nghĩa là ứng dụng chạy."** Đường hầm có thể lên nhưng route, firewall, DNS, TLS hoặc ứng dụng vẫn lỗi.
8. **"Triển khai multi-region là tự có dự phòng."** Dự phòng chỉ có giá trị nếu dữ liệu, DNS, điều phối lưu lượng và kịch bản khôi phục thực sự hoạt động.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một database cloud không có public IP nhưng security policy cho phép mọi host trong VPC kết nối. Có thể xem database đã được phân đoạn theo nguyên tắc tối thiểu chưa?

**Gợi ý trả lời:** Chưa chắc. Database tránh được một số đường truy cập trực tiếp từ Internet, nhưng phạm vi bên trong VPC vẫn quá rộng nếu chỉ ứng dụng cụ thể cần kết nối. Nên giới hạn nguồn theo nhóm workload/danh tính và cổng cần thiết.

**Câu 2.** Công ty có VPC cloud dùng 10.10.0.0/16, trùng với mạng data center. Điều gì cần giải quyết trước khi nối VPN?

**Gợi ý trả lời:** Phải xử lý chồng lấn địa chỉ bằng tái quy hoạch CIDR hoặc thiết kế dịch địa chỉ/định tuyến có kiểm soát. Nếu không, các đích trùng dải có thể bị định tuyến sai; cần xác minh cả đường đi và đường về.

**Câu 3.** Một private circuit kết nối data center với cloud. Có thể bỏ TLS khi truyền dữ liệu khách hàng không?

**Gợi ý trả lời:** Không thể suy ra như vậy từ tên loại đường truyền. Hãy xác định yêu cầu bí mật, toàn vẹn, danh tính đầu mút, khả năng quan sát ở trung gian và cơ chế mã hóa thực tế. TLS hoặc kênh được bảo vệ tương đương vẫn thường cần thiết.

**Câu 4.** VPN đã kết nối, DNS trả IP đúng nhưng Order API vẫn timeout khi gọi ERP. Ba nhóm nguyên nhân cần kiểm tra tiếp là gì?

**Gợi ý trả lời:** (1) Route hai chiều/NAT/asymmetric routing; (2) firewall, security policy, cổng đích; (3) dịch vụ ERP, TLS, timeout và độ trễ. Dùng log tại các điểm giao nhau để xác định chặng lỗi.

**Câu 5.** Một nhân viên quản trị cloud có quyền sửa route và mở security group. Đây là rủi ro của data plane hay control plane?

**Gợi ý trả lời:** Quyền sửa tài nguyên là **control plane**. Thay đổi có thể tác động tới **data plane** bằng cách cho phép hoặc ngăn lưu lượng, nên cần IAM tối thiểu, MFA, audit và kiểm soát thay đổi.

## 13. Checklist kiến trúc mạng an toàn

Trước khi đưa một hệ thống on-premises, cloud hoặc hybrid vào vận hành, hãy xác minh:

- [ ] Có **sơ đồ các miền mạng, ranh giới tin cậy và luồng dữ liệu** thực tế.
- [ ] Có **inventory** các nguồn/đích, địa chỉ CIDR, dịch vụ và người chịu trách nhiệm.
- [ ] Mỗi luồng cần thiết có **ma trận source–destination–protocol–port** và quy tắc mặc định từ chối.
- [ ] Mạng người dùng, ứng dụng, dữ liệu và quản trị được **phân đoạn và kiểm soát giao tiếp** phù hợp.
- [ ] Kênh truyền nhạy cảm có **mã hóa, xác thực đầu mút, quản lý khóa/chứng chỉ** theo yêu cầu.
- [ ] Danh tính con người, dịch vụ và quyền thao tác dùng **least privilege**, có log audit.
- [ ] Hybrid đã kiểm tra **CIDR không trùng, route hai chiều, DNS, NAT, MTU, tunnel và failover**.
- [ ] Có đủ **flow logs, firewall/VPN logs, DNS logs và application traces** để truy lỗi xuyên miền.
- [ ] Có biện pháp phát hiện xâm nhập, giới hạn tải, bảo vệ biên và **quy trình ứng phó sự cố**.
- [ ] Đã kiểm tra từ góc nhìn người dùng/ứng dụng và diễn tập lỗi thực tế, không chỉ xem dashboard "healthy".

**Điểm cốt lõi:** On-premises, cloud và hybrid là ba cách tổ chức và kết nối hạ tầng với những ranh giới vận hành khác nhau. Để bảo mật mạng, hãy hiểu **đường đi gói tin**, **nơi thực thi chính sách**, **điểm kết thúc mã hóa**, **danh tính được phép truy cập** và **bằng chứng giám sát**. Khi chuyển workload hoặc kết nối hai môi trường, phải đánh giá lại các yếu tố đó ở từng chặng, thay vì mang nguyên giả định tin cậy của môi trường cũ sang môi trường mới.
