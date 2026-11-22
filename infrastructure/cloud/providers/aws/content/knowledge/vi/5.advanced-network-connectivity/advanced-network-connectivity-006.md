# AWS Direct Connect, virtual interface và dự phòng kết nối

Khi ứng dụng AWS cần trao đổi dữ liệu thường xuyên với trung tâm dữ liệu tại chỗ (*on-premises*), kết nối Internet thông thường có thể không đáp ứng tốt yêu cầu về đường truyền ổn định, băng thông dự báo được hoặc quản trị tuyến mạng. **AWS Direct Connect (DX)** cung cấp đường kết nối mạng chuyên dụng giữa mạng doanh nghiệp và một **AWS Direct Connect location**. Trên kết nối vật lý, doanh nghiệp cấu hình **virtual interface (VIF)** và định tuyến **BGP** để đến đúng tài nguyên AWS.

Tuy nhiên, một đường Direct Connect duy nhất cũng có thể trở thành điểm lỗi đơn (*single point of failure*). Thiết kế thực tế phải xét đồng thời **đường truyền, thiết bị, Direct Connect location, BGP, gateway, route table, bảo mật, băng thông và cơ chế chuyển tuyến khi sự cố**.

Bài học thuộc chương **Kết nối mạng nâng cao** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung đặt Direct Connect trong hệ sinh thái AWS gồm Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless, giúp người học chọn dịch vụ, thiết kế ứng dụng an toàn, giám sát được, có khả năng phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả Direct Connect, sự khác nhau giữa **dedicated connection**, **hosted connection**, **virtual interface**, **Direct Connect gateway** và **Transit Gateway**.
2. Chọn đúng **private VIF**, **public VIF** hoặc **transit VIF** cho các tình huống kết nối.
3. Giải thích vai trò của **802.1Q VLAN**, **BGP ASN**, BGP peer, tiền tố định tuyến và sự khác biệt giữa kết nối vật lý với luồng dữ liệu ứng dụng.
4. Thiết kế dự phòng theo các lớp thiết bị, nhà mạng, đường cáp, Direct Connect location và có thể bổ sung **Site-to-Site VPN** khi phù hợp.
5. So sánh **active/active** với **active/passive**, nêu cách tác động đến chiều đi/chiều về và kiểm thử failover.
6. Giám sát trạng thái đường truyền, phiên BGP, băng thông, lỗi mạng và đánh giá tổng chi phí của kết nối hybrid.

## 2. Direct Connect hoạt động ở đâu trong kiến trúc hybrid?

Direct Connect là dịch vụ kết nối mạng có điểm bàn giao tại một **Direct Connect location**, thường là cơ sở *colocation* hoặc địa điểm kết nối của đối tác. Doanh nghiệp cần một đường vật lý hoặc dịch vụ của nhà cung cấp để đi từ router của mình đến địa điểm đó. Direct Connect location **không phải** là một Availability Zone hay địa điểm chạy EC2/RDS; địa điểm này liên kết mạng doanh nghiệp với mạng AWS.

Luồng cơ bản:

~~~mermaid
flowchart LR
    subgraph DC["Trung tâm dữ liệu doanh nghiệp"]
        LAN["Mạng nội bộ / ứng dụng"]
        CR["Customer router"]
        LAN --> CR
    end
    CR -->|"Đường truyền / đối tác"| LOC["AWS Direct Connect location"]
    LOC -->|"Dedicated / hosted connection"| VIF["Virtual interface + BGP"]
    VIF --> GW["VGW hoặc Direct Connect gateway"]
    GW --> VPC["VPC: EC2, ECS, RDS, dịch vụ nội bộ"]
~~~

Tùy loại VIF, đích có thể là **VPC sử dụng private IP**, **địa chỉ public của dịch vụ AWS** hoặc **nhiều VPC kết nối qua Transit Gateway**. Mỗi bước đều có cấu hình và quyền truy cập riêng; việc phiên BGP lên (*Established*) chưa đủ chứng minh ứng dụng có thể kết nối.

### 2.1. So sánh các phương án mạng

| Phương án | Đường truyền | Trường hợp phù hợp | Giới hạn quan trọng |
|---|---|---|---|
| **AWS Site-to-Site VPN qua Internet** | IPsec qua kết nối Internet | Kết nối nhanh, đường dự phòng, lưu lượng vừa phải | Chịu ảnh hưởng Internet, hiệu năng biến thiên theo đường truyền |
| **AWS Direct Connect** | Kết nối vật lý chuyên dụng đến DX location | Hybrid dài hạn, băng thông ổn định, truyền dữ liệu thường xuyên | Cần provisioning vật lý/đối tác; phải thiết kế dự phòng, không tự mã hóa lưu lượng |
| **VPN kết hợp Direct Connect** | IPsec kết hợp hạ tầng DX tùy kiến trúc được hỗ trợ | Cần đường DX và mã hóa lớp mạng | Cấu hình phức tạp hơn; phải phân biệt VPN dùng DX làm transport hay VPN độc lập qua Internet |
| **Kết nối Internet/public API** | Internet và endpoint public | Ứng dụng chỉ cần gọi API công khai | Không thay thế kết nối riêng đến private subnet |

Đường Direct Connect có thể mang lưu lượng đến các tài nguyên AWS ở nhiều Region thông qua cấu hình gateway phù hợp; không nên suy rằng địa điểm vật lý của DX luôn trùng Region có VPC.

## 3. Dedicated connection, hosted connection và VIF

### 3.1. Dedicated connection

**Dedicated connection** là đường Ethernet vật lý dành riêng cho một khách hàng tại Direct Connect location. Khách hàng đặt kết nối qua AWS và sắp xếp kết nối vật lý với cơ sở colocation hoặc nhà mạng theo quy trình cung cấp. Khi cần tự quản lý số VIF, thiết bị, cấu hình đường truyền và thiết kế dự phòng, đây thường là một lựa chọn phù hợp.

### 3.2. Hosted connection

**Hosted connection** được một **AWS Direct Connect Partner** cung cấp trên hạ tầng kết nối của đối tác. Doanh nghiệp làm việc với đối tác để có dung lượng và triển khai phù hợp. Hỗ trợ băng thông và hình thức bàn giao phụ thuộc đối tác và cấu hình.

**Không nên nhầm:** *hosted connection* là dịch vụ kết nối do đối tác cấp; *hosted virtual interface* là VIF được cấp cho một tài khoản AWS khác và cần được tài khoản nhận chấp thuận theo quy trình. Đây là hai khái niệm riêng.

| Tiêu chí | Dedicated connection | Hosted connection |
|---|---|---|
| Đơn vị cấp kết nối | Khách hàng yêu cầu trực tiếp từ AWS | AWS Direct Connect Partner cung cấp |
| Cách quản lý | Khách hàng quản lý đường DX và các VIF trong phạm vi được hỗ trợ | Khách hàng/đối tác chia sẻ trách nhiệm theo dịch vụ đã mua |
| Thiết bị và kết nối cuối | Cần đáp ứng điều kiện cross-connect và thiết bị mạng | Đường đi phụ thuộc hạ tầng và hợp đồng đối tác |
| Dự phòng | Có thể đặt các kết nối riêng ở nhiều DX location | Cần làm rõ tính độc lập của đường đi, vị trí và thiết bị do đối tác cung cấp |
| Lựa chọn | Theo dung lượng, quyền kiểm soát và hạ tầng hiện có | Theo năng lực của đối tác, nhu cầu cung cấp và vận hành |

### 3.3. Virtual interface nằm ở đâu?

**VIF** là giao diện logic cấu hình trên một kết nối Direct Connect, dùng **VLAN 802.1Q** và một hoặc nhiều phiên **BGP peering** theo địa chỉ IP được thiết lập. VIF quy định **kiểu tài nguyên AWS có thể tiếp cận** và điểm kết nối logic thích hợp, còn đường DX là phương tiện truyền tải bên dưới.

Các thông số thường phải chuẩn bị gồm:

- **Connection ID** của đường vật lý hoặc hosted connection, và loại VIF sẽ tạo.
- **VLAN ID** hợp lệ/không trùng trong phạm vi kết nối theo yêu cầu AWS.
- **Customer BGP ASN** và ASN ở phía AWS/Direct Connect gateway.
- **Địa chỉ BGP peer IPv4 hoặc IPv6**, cấu hình xác thực phiên BGP nếu sử dụng.
- **Gateway đích**, tài khoản sở hữu VIF, tuyến mạng sẽ quảng bá/nhận.
- **MTU** và loại khung truyền tải phù hợp với thiết bị và loại VIF; cấu hình jumbo frame chỉ khi các thành phần hỗ trợ.

Không dùng VLAN hoặc BGP để thay thế cho **security group, NACL, firewall, route table hoặc IAM** của ứng dụng. Chúng giải quyết các lớp kiểm soát khác nhau.

## 4. Ba loại virtual interface và cách chọn

| Loại VIF | Đích truy cập chính | Kết nối logic | Trường hợp điển hình | Không dùng cho |
|---|---|---|---|---|
| **Private VIF** | Địa chỉ **private** trong một hoặc nhiều VPC phù hợp | **Virtual Private Gateway (VGW)** hoặc **Direct Connect gateway (DXGW)** với VGW associations | On-premises truy cập EC2/RDS private trong VPC | Gắn trực tiếp vào Transit Gateway |
| **Public VIF** | Địa chỉ **public** thuộc mạng AWS và dịch vụ public AWS | Public BGP peering đến AWS public prefixes | On-premises gọi endpoint public AWS, ví dụ dịch vụ có public API | Internet transit tổng quát hoặc truy cập private IP trong VPC |
| **Transit VIF** | Nhiều VPC hoặc các attachment kết nối qua **Transit Gateway (TGW)** | **DXGW**, rồi **TGW association** | Mạng hybrid lớn, nhiều VPC/tài khoản, định tuyến tập trung | Gắn trực tiếp vào VGW |

### 4.1. Private VIF: truy cập private IP trong VPC

Với một VPC có **VGW**, private VIF có thể được liên kết trực tiếp đến VGW khi kiến trúc phù hợp. Nếu cần kết nối với **nhiều VPC ở các Region hoặc tài khoản được hỗ trợ**, private VIF có thể kết thúc tại **DXGW**, rồi DXGW liên kết đến các **VGW**.

~~~mermaid
flowchart LR
    R["On-prem router"] --> DX["Direct Connect connection"]
    DX --> PV["Private VIF"]
    PV --> DG["Direct Connect gateway"]
    DG --> VG1["VGW của VPC A"]
    DG --> VG2["VGW của VPC B"]
    VG1 --> V1["VPC A: private workload"]
    VG2 --> V2["VPC B: private workload"]
~~~

**Giới hạn cần nhớ:** DXGW liên kết các VGW không tự trở thành router **VPC-to-VPC** hay đường **hairpin qua on-premises** để hai VPC nói chuyện trực tiếp với nhau. Muốn VPC-to-VPC cần kiến trúc định tuyến đúng, chẳng hạn Transit Gateway hoặc các lựa chọn kết nối VPC khác phù hợp.

### 4.2. Public VIF: gọi endpoint public thuộc AWS

Public VIF đưa lưu lượng từ mạng doanh nghiệp đến **AWS public IP prefixes**; AWS quảng bá các prefix thích hợp qua BGP. Đây có thể là đường đi cho những API hoặc tài nguyên AWS sử dụng địa chỉ public, nhưng **không phải dịch vụ Internet transit** để truy cập mọi địa chỉ public trên Internet.

Public VIF có yêu cầu riêng đối với **public IP prefixes** doanh nghiệp quảng bá, đăng ký quyền sử dụng và xác minh định tuyến. Cần kiểm tra cùng nhà mạng và AWS trước khi đặt cấu hình quảng bá prefix. Dữ liệu vẫn phải được bảo vệ ở lớp ứng dụng/truyền tải theo yêu cầu: gọi HTTPS tới endpoint public không đồng nghĩa đường vật lý DX tự mã hóa.

Khi muốn truy cập dịch vụ AWS **qua private IP/endpoint trong VPC**, hãy xem xét private/transit VIF và **VPC endpoint/PrivateLink** nếu dịch vụ hỗ trợ; public VIF không thay thế việc thiết kế đường private tương ứng.

### 4.3. Transit VIF: kết nối nhiều VPC qua TGW

Với hệ thống có nhiều ứng dụng, VPC, account và cần định tuyến trung tâm, **Transit VIF → DXGW → TGW → VPC attachments** là mô hình tiêu biểu:

~~~mermaid
flowchart LR
    ONP["On-premises networks"] --> DX["Direct Connect connection"]
    DX --> TV["Transit VIF + BGP"]
    TV --> DG["Direct Connect gateway"]
    DG --> TG["Transit Gateway"]
    TG --> VA["VPC A attachment"]
    TG --> VB["VPC B attachment"]
    TG --> VC["Shared services VPC"]
~~~

Trong thiết kế này:

1. Tạo **DXGW** với ASN thích hợp.
2. Tạo **Transit VIF** trên kết nối DX và chỉ định DXGW.
3. Liên kết **TGW** với DXGW; hoàn tất chấp thuận proposal khi các tài khoản liên quan yêu cầu.
4. Thiết lập **VPC attachments**, TGW route tables, propagation/association, VPC route tables, firewall và các prefix được phép.
5. Kiểm tra BGP, đường đi cả chiều đi lẫn chiều về và quyền truy cập ứng dụng.

**Không gắn private VIF trực tiếp vào TGW** và **không gắn transit VIF trực tiếp vào VGW**. Một DXGW dành cho cấu hình VGW/private VIF không thể tùy ý dùng đồng thời để gắn TGW/transit VIF; cần tuân thủ quy tắc liên kết và quota hiện hành. Các ASN của TGW và DXGW khi liên kết phải khác nhau theo yêu cầu dịch vụ.

## 5. Vai trò của DXGW, VGW, TGW và bảng định tuyến

| Thành phần | Vai trò | Sai lầm thường gặp |
|---|---|---|
| **DXGW** | Kết nối logic giữa VIF và các gateway AWS theo cấu hình được hỗ trợ | Coi DXGW là một router trung gian dùng để tự động kết nối mọi VPC |
| **VGW** | Virtual private gateway của VPC cho một số kiến trúc DX/VPN | Quên route propagation hoặc chỉ cấu hình một chiều |
| **TGW** | Trung tâm định tuyến giữa VPCs/VPN và kết nối hybrid | Thiếu TGW route-table association/propagation hoặc route đến attachment |
| **VPC route table** | Quy định hướng chuyển gói ra khỏi subnet | Chỉ thêm đường phía on-premises mà quên route ngược từ VPC |
| **Security group/NACL** | Kiểm soát lưu lượng ở lớp mạng/tài nguyên | BGP lên nhưng TCP kết nối bị chặn do thiếu rule |
| **Customer router/firewall** | BGP, route filtering, kết nối đến LAN và chính sách bảo vệ | Quảng bá nhầm prefix hoặc dùng đường về không đối xứng |

**Tuyến hai chiều là điều kiện bắt buộc.** Khi gói từ LAN đến một private IP ở VPC, phải có tuyến đi **LAN → DX → VPC** và tuyến về **VPC → DX → LAN**. Còn phải cho phép lưu lượng ở security group, NACL và firewall; DNS phải trả địa chỉ đúng, nhất là khi dùng private hosted zone hoặc hybrid DNS resolver.

**Ví dụ CIDR minh họa:**

- Mạng on-premises: **10.40.0.0/16**.
- VPC ứng dụng: **10.80.0.0/16**.
- VPC dữ liệu: **10.90.0.0/16**.

Các CIDR không được chồng lấn nếu kiến trúc định tuyến không xử lý được trùng địa chỉ. Trước khi kết nối nhiều VPC hoặc tài khoản, lập danh mục CIDR, route propagation và dải prefix được quảng bá. Với DXGW/TGW, đặc biệt chú ý **allowed prefixes**: đây là cơ chế kiểm soát tuyến được phép theo thiết kế liên kết, không phải thay thế firewall.

## 6. BGP peering và lựa chọn tuyến

Direct Connect dùng **Border Gateway Protocol (BGP)** để trao đổi thông tin định tuyến giữa router khách hàng và AWS. Thông thường mỗi VIF cần cấu hình đúng **ASN**, địa chỉ peering và BGP neighbor. Một VIF có thể cấu hình IPv4/IPv6 peering theo khả năng và nhu cầu.

### 6.1. BGP up chưa đồng nghĩa đường ứng dụng hoạt động

Cần phân biệt trạng thái:

| Tầng kiểm tra | Dấu hiệu đạt | Ví dụ lỗi dù tầng dưới hoạt động |
|---|---|---|
| Kết nối vật lý | Cổng và đường DX active | Không có VIF hoặc VLAN sai |
| VLAN và BGP | Phiên BGP **Established** | Không quảng bá/nhận prefix cần dùng |
| Routing | Có prefix và next hop hợp lệ hai chiều | TGW/VPC route table thiếu đường đi |
| Network policy | Firewall, SG, NACL cho phép | TCP bị chặn, DNS phân giải sai |
| Ứng dụng | API/DB trả lời theo SLO | IAM, TLS, xác thực database hoặc service endpoint sai |

Nếu BGP không lên, kiểm tra lần lượt **interface state → VLAN → địa chỉ peer → ASN → BGP authentication → ACL/firewall tại router → thông số phiên**. Nếu BGP lên nhưng không thấy route, kiểm tra chính sách **import/export**, prefix filtering, **allowed prefixes**, tình trạng gateway association và route propagation.

### 6.2. Active/active và active/passive

Hai đường DX có thể được cấu hình để:

- **Active/active:** cả hai đường xử lý lưu lượng; AWS hỗ trợ **ECMP (Equal-Cost Multi-Path)** trong những điều kiện BGP và topology phù hợp. Có thể cải thiện tận dụng băng thông và vẫn còn một đường khi sự cố.
- **Active/passive:** một đường ưu tiên, đường còn lại chờ tiếp nhận lưu lượng sau khi BGP và routing chuyển tuyến. Phù hợp khi muốn dự đoán đường chính hoặc tuyến dự phòng, nhưng cần đo thời gian chuyển và năng lực tuyến phụ.

**Quan trọng:** BGP là định tuyến giữa nhiều thiết bị. Chiều **on-premises → AWS** chịu tác động bởi chính sách BGP trên router của bạn; chiều **AWS → on-premises** phụ thuộc chính sách AWS, thông tin prefix được quảng bá và các thuộc tính đường đi. Hai chiều **không tự động đối xứng**.

Với private/transit VIF, AWS hỗ trợ **BGP local preference communities** để điều chỉnh mức ưu tiên khi lưu lượng từ AWS quay về on-premises:

| Community | Ý nghĩa |
|---|---|
| **7224:7100** | Ưu tiên thấp (*low*) |
| **7224:7200** | Ưu tiên trung bình (*medium*) |
| **7224:7300** | Ưu tiên cao (*high*) |

Khi các điều kiện phù hợp, có thể quảng bá cùng prefix từ VIF chính với community ưu tiên cao, từ VIF dự phòng với community thấp. Với active/active, hai tuyến có thể dùng cùng community và các thuộc tính phù hợp để đủ điều kiện ECMP. AWS xét **longest prefix match**, **local preference**, **AS_PATH** và các đặc điểm routing khác; không chỉ dựa vào một BGP community.

Không sao chép community từ **private/transit VIF** sang **public VIF**: public VIF có quy tắc prefix và BGP communities riêng. Trước khi thay đổi ưu tiên trên mạng production, cần thử failover và quan sát cả **đường đi** lẫn **đường về**.

### 6.3. Phát hiện lỗi BGP nhanh hơn

Direct Connect hỗ trợ **Bidirectional Forwarding Detection (BFD)** để phát hiện lỗi kết nối nhanh hơn trong những cấu hình phù hợp. AWS có thể tự bật hỗ trợ BFD trên VIF, nhưng **router phía khách hàng vẫn phải cấu hình đúng** thì cơ chế mới có tác dụng. Thời gian hội tụ phụ thuộc timer, thiết bị, topology và đường dự phòng; không được hứa một RTO cố định chỉ nhờ BFD.

## 7. Thiết kế dự phòng kết nối theo từng miền lỗi

Sự cố có thể xảy ra tại nhiều tầng:

1. **Cổng/router tại doanh nghiệp**: cổng quang, module, router hoặc nguồn điện.
2. **Đường local loop / last mile**: cáp bị đứt, tuyến cáp cùng ống dẫn hoặc lỗi nhà mạng.
3. **DX location**: thiết bị AWS tại điểm kết nối hoặc sự cố toàn địa điểm.
4. **Định tuyến**: BGP down, route filtering sai, thay đổi prefix hoặc route table.
5. **Ứng dụng và hạ tầng AWS**: lỗi VPC, dịch vụ trong AZ/Region, DNS hoặc backend.

Một đường kết nối thứ hai **chỉ thực sự tăng độ bền** khi tránh dùng chung điểm lỗi cần bảo vệ. Hai circuit từ hai nhà mạng khác tên vẫn có thể đi cùng một tuyến cáp vật lý; cần yêu cầu sơ đồ đa dạng đường đi và xác nhận với đối tác.

### 7.1. AWS Direct Connect Resiliency Toolkit

AWS cung cấp **Direct Connect Resiliency Toolkit** và *Connection wizard* để giúp chọn mô hình kết nối dedicated với mức dự phòng phù hợp. Các mô hình thường dùng:

| Mô hình | Thiết kế điển hình | Rủi ro được giảm | Ý nghĩa |
|---|---|---|---|
| **Development and test** | Kết nối tách biệt tới các thiết bị khác nhau tại **cùng một DX location** | Lỗi thiết bị riêng lẻ | Không chống được sự cố toàn DX location |
| **High resiliency** | Hai kết nối riêng đến **nhiều DX location** | Lỗi đường kết nối hoặc thiết bị; giảm ảnh hưởng sự cố location | Phù hợp nhiều hệ thống production; vẫn cần kiểm tra các điều kiện SLA |
| **Maximum resiliency** | Các kết nối tách biệt trên thiết bị riêng tại **hơn một DX location**, thường kết hợp nhiều đường ở mỗi địa điểm | Lỗi thiết bị, kết nối và toàn location ở mức cao hơn | Phù hợp hệ thống trọng yếu, cần ngân sách và vận hành tương ứng |

Tài liệu Toolkit công bố mục tiêu thiết kế liên quan SLA **99,9%** đối với *High resiliency* và **99,99%** đối với *Maximum resiliency*, nhưng **không phải bảo đảm tự động** khi chỉ đặt tên kiến trúc. Khả năng hưởng SLA phụ thuộc tất cả điều kiện trong SLA AWS Direct Connect, cấu hình thực tế và trách nhiệm của khách hàng/đối tác.

### 7.2. Ví dụ topology có dự phòng hai địa điểm

~~~mermaid
flowchart LR
    subgraph ON["Doanh nghiệp / on-premises"]
        LAN["LAN / workloads"]
        R1["Router 1"]
        R2["Router 2"]
        LAN --> R1
        LAN --> R2
    end
    R1 -->|"Carrier / path A"| LA["DX Location A"]
    R2 -->|"Carrier / path B"| LB["DX Location B"]
    LA -->|"VIF A / BGP A"| DG["Direct Connect gateway"]
    LB -->|"VIF B / BGP B"| DG
    DG --> TG["Transit Gateway"]
    TG --> VPC["VPC applications / data"]
~~~

Sơ đồ là **minh họa hai đường ở hai DX location**, không tự chứng minh đạt *Maximum resiliency*. Với mục tiêu đó cần thiết kế đầy đủ số kết nối, thiết bị riêng, vị trí và kiểm tra điều kiện SLA. Nên lập sơ đồ cụ thể của **router, thiết bị vật lý, cặp circuit, đối tác mạng và vị trí DX** thay vì chỉ vẽ hai đường trên sơ đồ logic.

### 7.3. Tại sao LAG chưa đủ cho HA cấp địa điểm?

**Link Aggregation Group (LAG)** dùng **LACP** để gộp nhiều dedicated connections thành một giao diện logic, thường nhằm mở rộng băng thông và đơn giản hóa quản lý. Các member của LAG trên AWS kết thúc tại **cùng DX location và cùng thiết bị AWS**; AWS không hỗ trợ **multi-chassis LAG** cho cấu hình DX này.

Vì vậy:

- LAG có thể giúp chịu lỗi **một member link** trong giới hạn cấu hình.
- **Một LAG duy nhất không loại bỏ lỗi thiết bị AWS hoặc lỗi DX location**.
- Muốn HA cấp location cần thiết kế **các kết nối/LAG độc lập ở nhiều location** và routing/BGP chuyển tuyến phù hợp.

### 7.4. VPN làm đường dự phòng

**AWS Site-to-Site VPN qua Internet** có thể là đường thay thế khi DX gặp sự cố, phù hợp nếu lưu lượng và SLA cho phép. Dùng hai VPN tunnels theo khuyến nghị của dịch vụ, cấu hình route và cơ chế kiểm tra sức khỏe. Không nhầm với phương án **IPsec VPN chạy qua Direct Connect**: nếu VPN chạy trên cùng đường DX bị hỏng thì nó cũng mất đường vận chuyển.

Một đường dự phòng đúng nghĩa cần có **miền lỗi độc lập**, đủ băng thông cho tải thiết yếu, cấu hình route tương thích và kịch bản DNS/tường lửa đã kiểm thử.

| Kịch bản hỏng | Có DX thứ hai cùng location | Có DX ở location khác | Có VPN độc lập qua Internet |
|---|---|---|---|
| Một cổng hoặc một link DX lỗi | Có thể tiếp tục nếu không chia sẻ thiết bị/đường | Có thể tiếp tục | Có thể tiếp tục |
| Một DX location gặp sự cố | Không bảo đảm | Có thể tiếp tục nếu đường và routing độc lập | Có thể tiếp tục nếu Internet/VPN không cùng miền lỗi |
| Nhà mạng/last-mile dùng chung bị đứt | Có thể cùng hỏng | Chỉ tốt nếu last-mile thực sự đa dạng | Phụ thuộc đường Internet còn hoạt động |
| Một AZ/VPC route table cấu hình sai | Thường không giải quyết | Thường không giải quyết | Thường không giải quyết |
| Toàn Region AWS gặp sự cố | Không tự khôi phục ứng dụng | Không tự khôi phục ứng dụng | Không tự khôi phục ứng dụng |

**Dự phòng mạng và dự phòng ứng dụng khác nhau.** Nếu yêu cầu chịu được mất toàn AZ/Region, cần thiết kế **Multi-AZ/DR**, database replication, DNS/routing và runbook ở lớp ứng dụng, không chỉ thêm Direct Connect.

## 8. Mã hóa và bảo mật đường Direct Connect

**Direct Connect không mặc định mã hóa dữ liệu đang truyền**. Kết nối chuyên dụng có tuyến vật lý riêng, nhưng không đồng nghĩa dữ liệu có mã hóa đầu cuối.

Các lựa chọn bảo vệ:

| Giải pháp | Phạm vi bảo vệ | Lưu ý |
|---|---|---|
| **TLS/HTTPS** | Bảo vệ kết nối lớp ứng dụng đến endpoint hỗ trợ | Nên dùng cho API, truy cập dịch vụ và các ứng dụng nhạy cảm |
| **IPsec / Site-to-Site VPN kết hợp DX** | Mã hóa ở lớp mạng theo kiến trúc VPN phù hợp | Cần kiểm tra thông lượng tunnel, endpoint, MTU, route và khả năng dự phòng |
| **MACsec** | Mã hóa điểm-điểm ở lớp 2 trên các đường DX hỗ trợ | Phạm vi link MACsec, khả năng thiết bị, connection type và location phải được xác nhận; không thay thế TLS/IPsec đầu-cuối |
| **Firewall, SG, NACL, IAM** | Kiểm soát đường đi, cổng, danh tính và hành động | Không trực tiếp mã hóa dữ liệu; cần cấu hình kèm |

Nếu dùng **MACsec**, cần kiểm tra thiết bị tương thích, loại kết nối hỗ trợ và chế độ mã hóa. Tùy chế độ, khi không đàm phán được MACsec, kết nối có thể **ngừng chuyển lưu lượng** hoặc **chuyển không mã hóa**; lựa chọn này phải theo yêu cầu bảo mật của doanh nghiệp. Không giả định hosted connection nào cũng hỗ trợ MACsec.

Với hệ thống chứa dữ liệu nhạy cảm, cần kết hợp phân quyền IAM, quy tắc mạng, mã hóa lưu trữ (S3/EBS/RDS), mã hóa truyền tải và log. Direct Connect **không tự giải quyết yêu cầu lưu trú dữ liệu theo quốc gia/Region**; phải xem luồng đi và nơi dữ liệu được xử lý/lưu.

## 9. Quy trình triển khai mẫu

### Bước 1 — Thu thập yêu cầu

Lập bảng gồm: VPC/Region và tài khoản AWS cần kết nối, ứng dụng, CIDR on-premises, băng thông giờ cao điểm, độ trễ, yêu cầu bảo mật, RTO/RPO, mô hình active/active hoặc active/passive, loại dự phòng, thời gian lắp đặt và ngân sách.

Nếu mạng doanh nghiệp có nhiều địa điểm, hãy đánh giá khả năng **điểm lỗi chung** tại core network và các carrier trước khi quyết định số circuit.

### Bước 2 — Chọn điểm kết nối, loại connection và mô hình dự phòng

Chọn DX location và nhà cung cấp có tuyến mạng phù hợp. Xác nhận khả năng provisioning, *cross-connect*, thiết bị của hai đầu, loại dedicated/hosted và phương án dự phòng. Với workload trọng yếu, cân nhắc Connection wizard của **Resiliency Toolkit**.

### Bước 3 — Chọn mô hình VIF/gateway

- **Một VPC, private IP:** cân nhắc private VIF → VGW.
- **Nhiều VPC dùng VGW ở nhiều Region/tài khoản:** cân nhắc private VIF → DXGW → các VGW.
- **Nhiều VPC qua mạng trung tâm:** transit VIF → DXGW → TGW.
- **Public endpoint thuộc AWS:** public VIF; xác minh yêu cầu public prefix.

Thiết kế cần xét **giới hạn associate/gateway**, khả năng định tuyến, băng thông và quản trị giữa các tài khoản.

### Bước 4 — Quy hoạch BGP và route

Thiết lập ASN, VLAN, peer addresses, BGP authentication, danh sách prefix được phép, route filter, default-route policy và tuyến về. Với nhiều DX locations, xác định BGP preference/communities cho active/active hoặc active/passive. Lập sơ đồ đầy đủ chiều **on-prem → AWS** và **AWS → on-prem**.

### Bước 5 — Thiết lập kết nối và chính sách bảo mật

Sau khi port/hosted connection được cấp và đối tác hoàn tất đường vật lý, cấu hình VIF, DXGW/VGW/TGW, VPC route tables, TGW route tables nếu có, SG/NACL, DNS resolver và các kết nối mã hóa phù hợp. Thêm IAM quyền quản trị Direct Connect theo least privilege; lưu hồ sơ cấu hình mạng và người phê duyệt.

### Bước 6 — Kiểm tra chức năng và tải

Kiểm tra **link/VLAN/BGP → learned prefixes → bidirectional routing → ứng dụng**, rồi chạy thử lưu lượng thực tế và theo dõi thông số. Xác nhận băng thông, jitter, packet loss, MTU, chi phí và đặc điểm failover.

### Bước 7 — Kiểm thử dự phòng có kế hoạch

Thử mất từng đường, mất một phiên BGP, giả lập lỗi một địa điểm theo quy trình phù hợp, kiểm tra cảnh báo và đo:

- Thời gian phát hiện và hội tụ BGP.
- Tổng thời gian ứng dụng bị gián đoạn hoặc giảm chất lượng.
- Thông lượng của tuyến còn lại khi toàn bộ tải dồn sang.
- Đường đi/đường về có thay đổi như dự kiến không.
- Khả năng trở về đường chính, tránh flapping hoặc phân bố tải ngoài dự kiến.

**AWS Direct Connect Failover Test** trong Resiliency Toolkit có thể hỗ trợ thử chuyển tuyến BGP theo phạm vi được hỗ trợ. Chỉ thực hiện trong cửa sổ thay đổi đã thông báo và có phương án khôi phục vì thử lỗi có thể gây gián đoạn lưu lượng thật.

## 10. Kiểm tra trạng thái bằng AWS CLI

Các lệnh sau **chỉ đọc thông tin** và yêu cầu profile AWS có quyền phù hợp; thay các ID minh họa bằng tài nguyên lab thực tế. AWS CLI và endpoint Direct Connect phải dùng Region được cấu hình tương ứng.

~~~bash
# Liệt kê các kết nối Direct Connect mà tài khoản có thể xem.
aws directconnect describe-connections \
  --query 'connections[].{Id:connectionId,Name:connectionName,State:connectionState,Location:location,Bandwidth:bandwidth}' \
  --output table

# Liệt kê các virtual interface, loại VIF, trạng thái và connection ID.
aws directconnect describe-virtual-interfaces \
  --query 'virtualInterfaces[].{Id:virtualInterfaceId,Type:virtualInterfaceType,State:virtualInterfaceState,Connection:connectionId,Vlan:vlan}' \
  --output table

# Xem các Direct Connect gateway trong phạm vi được hỗ trợ.
aws directconnect describe-direct-connect-gateways \
  --query 'directConnectGateways[].{Id:directConnectGatewayId,Name:directConnectGatewayName,ASN:amazonSideAsn}' \
  --output table

# Liệt kê metric Direct Connect trên CloudWatch.
aws cloudwatch list-metrics --namespace AWS/DX
~~~

Kết quả cần đối chiếu với **BGP session state** trên router doanh nghiệp và trạng thái **BGPPeers** của VIF; nếu có DXGW/TGW, cần kiểm tra thêm gateway association, attachment và route table thực tế.

### 10.1. Metric nên theo dõi

| Metric (CloudWatch, namespace AWS/DX) | Ý nghĩa vận hành | Tình huống cần cảnh báo |
|---|---|---|
| **ConnectionState** | Đường kết nối up/down | Mất một trong các kết nối cần thiết |
| **ConnectionBpsIngress / ConnectionBpsEgress** | Lưu lượng vào/ra theo góc nhìn AWS | Tiệm cận công suất hoặc thay đổi đột ngột |
| **ConnectionErrorCount** | Lỗi tầng mạng ở đầu thiết bị | Tăng bất thường, nghi vấn cáp/quang |
| **VirtualInterfaceBgpStatus** | Trạng thái phiên BGP của VIF | BGP down, flap thường xuyên |
| **VirtualInterfaceBgpPrefixesAccepted / Advertised** | Số prefix nhận/quảng bá | Số lượng giảm bất ngờ hoặc route thiếu |
| **VirtualInterfaceBpsIngress / Egress** | Lưu lượng của VIF | VIF bão hòa hoặc mất lưu lượng bất thường |
| **ConnectionEncryptionState** | Trạng thái mã hóa kết nối khi có cấu hình liên quan | Mất mã hóa trong kiến trúc yêu cầu MACsec |

Thông số **ConnectionState = up** không chứng minh ứng dụng đang phục vụ bình thường. Cần kết hợp **synthetic monitoring**, phép đo RTT/packet loss, log firewall, truy vấn API/database và SLO của ứng dụng. CloudWatch thường tổng hợp dữ liệu theo khoảng thời gian; cảnh báo cần thiết kế phù hợp để không bỏ sót lỗi ngắn hoặc gây quá nhiều cảnh báo giả.

### 10.2. Runbook xử lý sự cố

| Dấu hiệu | Kiểm tra theo thứ tự | Hướng xử lý ban đầu |
|---|---|---|
| **ConnectionState down** | Carrier, optics, cross-connect, router interface, thông báo DX | Chuyển tuyến dự phòng, phối hợp AWS/nhà mạng |
| **Connection up, BGP down** | VLAN, peer IP, ASN, authentication, thiết bị/router | Kiểm tra peering/config trước khi thay đổi routing rộng |
| **BGP up, không có route mong đợi** | Route filter, prefix quảng bá, allowed prefixes, DXGW/TGW association | Sửa chính sách định tuyến tương ứng |
| **Có route nhưng TCP không tới EC2/RDS** | VPC/TGW route tables, SG, NACL, firewall, DNS | Xác minh hai chiều và cổng dịch vụ |
| **DX chính mất, đường dự phòng không nhận tải** | BGP preference, community, AS_PATH, số prefix, năng lực đường dự phòng | Khắc phục điều kiện failover và kiểm thử lại |
| **Băng thông thấp, packet loss cao** | Utilization, MTU, queuing, interface drops, ISP/carrier | Đo đoạn gây nghẽn, cân tải/điều chỉnh công suất |
| **MACsec trạng thái không đạt** | Thiết bị, key/mode, port hỗ trợ, CloudWatch encryption state | Áp dụng runbook khôi phục mã hóa, tránh tự hạ chuẩn bảo mật |

## 11. Chi phí và trách nhiệm vận hành

Tổng chi phí Direct Connect cần xét ngoài phần đường truyền đến AWS:

| Hạng mục | Ví dụ phát sinh | Chủ thể cần đối chiếu |
|---|---|---|
| **Phí Direct Connect** | Cổng/công suất, dữ liệu truyền ra theo hình thức định giá và Region | Bảng giá AWS, điều khoản pricing hiện hành |
| **Cross-connect/colocation** | Cổng vật lý tại điểm đặt thiết bị, dây nối, chi phí chỗ đặt | Colocation facility |
| **Đường last-mile và nhà mạng** | Tuyến quang từ văn phòng/data center đến DX location | Carrier hoặc Direct Connect Partner |
| **Đường dự phòng** | Circuit, thiết bị, nhân sự vận hành, VPN backup | AWS + đối tác + doanh nghiệp |
| **Gateway và dịch vụ AWS đi kèm** | TGW attachment/data processing, VPN, monitoring, traffic giữa dịch vụ/Region | AWS theo thiết kế cụ thể |
| **Bảo trì và kiểm thử** | Thời gian triển khai, cửa sổ change, hỗ trợ sự cố, diễn tập failover | Nhóm vận hành và đối tác |

AWS có thể có nhiều hình thức định giá Direct Connect tùy điều kiện và thời điểm; không nên lấy một mức phí theo giờ hoặc giả định phí truyền dữ liệu cố định cho mọi trường hợp. Dùng **AWS Pricing Calculator** và bảng giá chính thức, tính cả lưu lượng một chiều/two-way, dự phòng và công suất trong tình huống **một đường phải gánh toàn bộ tải**.

Chi phí tối ưu phải được đánh giá cùng độ sẵn sàng: cắt bớt một DX location có thể giảm phí nhưng tạo rủi ro gián đoạn sản xuất lớn hơn khoản tiết kiệm.

## 12. Tình huống thiết kế và bài tập

### Tình huống A — Một VPC và yêu cầu kết nối cơ bản

Doanh nghiệp có ứng dụng kế toán tại on-premises, cần truy cập private RDS trong một VPC AWS. Băng thông tương đối ổn định, dữ liệu nhạy cảm, nhưng hệ thống vẫn có thể chịu được một khoảng gián đoạn ngắn đã định.

**Câu hỏi:** chọn VIF nào và cần kiểm tra gì?

**Gợi ý:** dùng **private VIF** với VGW hoặc DXGW theo topology phù hợp. Đảm bảo private CIDR không chồng lấn, route hai chiều, security group chỉ mở port DB từ mạng doanh nghiệp và mã hóa ở lớp ứng dụng. Chuẩn bị kết nối dự phòng hoặc VPN độc lập với đường DX chính và kiểm thử ứng dụng sau failover.

### Tình huống B — Nhiều VPC qua nhiều tài khoản

Một tổ chức có mạng ứng dụng, dữ liệu và dịch vụ dùng chung nằm ở nhiều VPC thuộc các tài khoản khác nhau. Mục tiêu là tập trung quản trị mạng hybrid và không tạo VIF riêng cho mọi VPC.

**Câu hỏi:** private VIF với nhiều VGW hay transit VIF + TGW?

**Gợi ý:** xác định có cần định tuyến tập trung VPC-to-VPC hoặc nhiều attachments hay chỉ cần on-premises-to-VPC. Nếu cần mạng tập trung, xem xét **transit VIF → DXGW → TGW**, rồi thiết kế TGW route tables và quyền chia sẻ tài nguyên giữa tài khoản. Nếu chỉ cần kết nối private đến một số VPC, **private VIF → DXGW → VGW associations** có thể phù hợp. Hai mô hình có quota, routing, chi phí và giới hạn khác nhau.

### Tình huống C — Đường DX chính hỏng

Hệ thống đã có hai kết nối vật lý nhưng cả hai terminate trên **cùng thiết bị trong cùng DX location**, được gộp thành một LAG. Khi DX location gặp sự cố, cả hai kết nối ngừng phục vụ.

**Câu hỏi:** vì sao hai kết nối không giúp hệ thống duy trì truy cập? Cần thay đổi gì?

**Gợi ý:** số lượng cáp không quyết định độc lập miền lỗi. Thiết kế hai location thực sự khác nhau, router/đường last-mile khác, có BGP và phương án failover. Với tải trọng yếu, tham khảo **High/Maximum resiliency** của Toolkit, kiểm tra điều kiện SLA và diễn tập mất location. VPN dự phòng chỉ hữu ích nếu đường transport còn hoạt động.

### Tình huống D — Định tuyến không đối xứng

Router on-premises gửi lưu lượng qua VIF A, nhưng AWS trả về VIF B do cấu hình BGP preference khác. Firewall trạng thái (*stateful*) của doanh nghiệp từ chối nhiều phiên TCP.

**Câu hỏi:** cần xác minh và điều chỉnh gì?

**Gợi ý:** đối chiếu cả hai chiều lưu lượng, BGP local preference trên router on-premises, community/AS_PATH quảng bá đến AWS, bảng route và vị trí firewall. Sau khi chọn chính sách cân tải phù hợp, kiểm thử các phiên dài/nhạy cảm trong lúc chuyển đường, kiểm tra timeout và trạng thái kết nối.

## 13. Checklist trước khi đưa Direct Connect vào production

- [ ] Đã xác định ứng dụng, tài khoản, Region, VPC, CIDR và nhu cầu băng thông thực tế.
- [ ] Đã phân biệt **dedicated** với **hosted connection**, hợp đồng carrier và đường vật lý đến DX location.
- [ ] Đã chọn đúng **private/public/transit VIF** và kiến trúc **VGW/DXGW/TGW**.
- [ ] Đã kiểm tra VLAN, peer IP, ASN, BGP auth, route filters, allowed prefixes và MTU.
- [ ] Đã xác minh route **hai chiều** qua on-premises, DX, TGW/VPC và policy firewall/SG/NACL.
- [ ] Đã xác định các miền lỗi vật lý thực sự độc lập; LAG không bị hiểu nhầm là HA cấp DX location.
- [ ] Đã lựa chọn mô hình dự phòng, kiểm tra điều kiện SLA và có runbook failover.
- [ ] Đã xem xét **mã hóa truyền tải** bằng TLS, IPsec hoặc MACsec phù hợp; DX không mặc định mã hóa.
- [ ] Đã thiết lập CloudWatch alerts cho **ConnectionState**, BGP, lưu lượng và lỗi đường truyền.
- [ ] Đã thử mất đường, hội tụ BGP, tải trên đường dự phòng và ảnh hưởng với ứng dụng.
- [ ] Đã dự toán chi phí DX, data transfer, carrier, cross-connect, TGW/VPN và vận hành.
- [ ] Đã lưu sơ đồ mạng, chủ sở hữu, hỗ trợ liên hệ và lịch rà soát thiết kế.

## 14. Ghi nhớ

**Direct Connect** cung cấp lớp kết nối mạng chuyên dụng giữa mạng doanh nghiệp và AWS, còn **VIF** quyết định cách tiếp cận tài nguyên. **Private VIF** hướng tới private IP trong VPC; **public VIF** tới AWS public prefixes; **transit VIF** nối qua DXGW và TGW để phục vụ mạng nhiều VPC. **BGP và route table** quyết định khả năng đi lại hai chiều. **Dự phòng chỉ hiệu quả khi tránh các miền lỗi chung**, có phương án chuyển tuyến và diễn tập đủ sát với tải ứng dụng. Cuối cùng, Direct Connect không tự thay thế mã hóa, IAM, bảo vệ mạng, giám sát hoặc kiến trúc phục hồi Multi-AZ/Multi-Region.

### Tài liệu AWS chính thức nên đối chiếu khi triển khai

- [AWS Direct Connect — User Guide](https://docs.aws.amazon.com/directconnect/latest/UserGuide/) — khái niệm, mô hình kết nối và phạm vi dịch vụ.
- [Direct Connect virtual interfaces](https://docs.aws.amazon.com/directconnect/latest/UserGuide/create-vif.html) — private, public và transit VIF.
- [Direct Connect gateways](https://docs.aws.amazon.com/directconnect/latest/UserGuide/direct-connect-gateways.html) — các kiểu liên kết gateway.
- [Virtual private gateway associations](https://docs.aws.amazon.com/directconnect/latest/UserGuide/virtualgateways.html) — giới hạn kết nối private VIF/DXGW/VGW.
- [Transit Gateway associations](https://docs.aws.amazon.com/directconnect/latest/UserGuide/direct-connect-transit-gateways.html) — transit VIF và DXGW/TGW.
- [Routing policies and BGP communities](https://docs.aws.amazon.com/directconnect/latest/UserGuide/routing-and-bgp.html) — active/active, active/passive và route preference.
- [Direct Connect Resiliency Toolkit](https://docs.aws.amazon.com/directconnect/latest/UserGuide/resiliency_toolkit.html) — mô hình dự phòng, SLA và kiểm thử failover.
- [Link aggregation groups](https://docs.aws.amazon.com/directconnect/latest/UserGuide/lags.html) — LACP, cùng thiết bị và giới hạn LAG.
- [Encryption in AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/encryption-in-transit.html) — VPN, MACsec và mã hóa dữ liệu.
- [Monitor with Amazon CloudWatch](https://docs.aws.amazon.com/directconnect/latest/UserGuide/monitoring-cloudwatch.html) — ConnectionState, BGP, throughput và các metric.
- [AWS Direct Connect Pricing](https://aws.amazon.com/directconnect/pricing/) — cách tính giá và các yếu tố chi phí.
