# Control plane và data plane

> **Chương:** Mô hình mạng  
> **Học phần:** SECURITY_NETWORK_SECURITY — An ninh mạng  
> **Trọng tâm:** Phân biệt nơi mạng hình thành quyết định và nơi mạng thực thi quyết định; vận dụng sự phân biệt đó để thiết kế phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây và hạ tầng cloud an toàn.

Khi một gói tin đi từ máy người dùng tới dịch vụ API, thiết bị mạng phải trả lời ít nhất hai câu hỏi khác nhau: **Nên chuyển gói này đi đâu?** và **Phải thực hiện hành động gì với gói này ngay lúc nó đến?** Câu hỏi thứ nhất thường do **control plane** xây dựng câu trả lời thông qua giao thức, trạng thái mạng và chính sách. Câu hỏi thứ hai được **data plane** thực thi với từng gói hoặc từng luồng lưu lượng.

Sự tách biệt này giúp chúng ta hiểu vì sao một router vẫn có thể tiếp tục chuyển tiếp lưu lượng khi một tiến trình định tuyến tạm thời gặp sự cố; vì sao có đường đi hợp lệ nhưng firewall vẫn chặn truy cập; và vì sao xâm nhập vào hệ thống điều khiển mạng có thể gây hậu quả trên nhiều thiết bị cùng lúc. Đây là nền tảng để phân tích lưu lượng, giám sát xâm nhập, mô hình hóa mối đe dọa và thiết kế phòng vệ nhiều lớp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chức năng, đầu vào, đầu ra và quan hệ giữa **control plane**, **data plane** và **management plane**.
2. Phân biệt **routing/route selection** với **forwarding**, **RIB** với **FIB**, và chính sách bảo mật được cấu hình với chính sách được thực thi.
3. Theo dõi cách thông tin định tuyến, trạng thái láng giềng và quy tắc ACL/firewall ảnh hưởng đến một gói tin cụ thể.
4. So sánh hai mặt phẳng trên router/switch truyền thống, thiết bị phần mềm, SDN và mạng cloud.
5. Xác định các mối đe dọa đối với từng mặt phẳng, biện pháp giảm thiểu và tín hiệu giám sát phù hợp.
6. Chẩn đoán sơ bộ sự cố bằng cách xác định lỗi nằm ở đường điều khiển, đường chuyển tiếp, hay đường quản trị.

## 2. Một mạng, nhiều mặt phẳng chức năng

Trong kiến trúc mạng, *plane* (mặt phẳng) chỉ **nhóm trách nhiệm logic**, không nhất thiết là một máy chủ, một tiến trình hay một bo mạch riêng.

| Mặt phẳng | Câu hỏi trung tâm | Hoạt động điển hình | Kết quả tạo ra |
|---|---|---|---|
| **Control plane — mặt phẳng điều khiển** | Mạng biết những đích nào, đường đi nào nên được chọn và chính sách vận hành nào đang áp dụng? | Giao thức định tuyến, khám phá láng giềng, tính toán đường đi, xử lý một số sự kiện/topology, phân phối chính sách | Thông tin định tuyến, trạng thái điều khiển, chỉ dẫn để lập trình bảng chuyển tiếp |
| **Data plane — mặt phẳng dữ liệu/chuyển tiếp** | Gói tin vừa đến phải được chuyển, chặn, biến đổi, xếp hàng hay chuyển tới nơi xử lý khác? | Tra bảng chuyển tiếp, switching, routing packet, ACL, NAT, QoS, tunnel, xử lý lưu lượng | Gói tin được chuyển tiếp, bị loại bỏ hoặc được xử lý theo hành động đã lập trình |
| **Management plane — mặt phẳng quản trị** | Con người và hệ thống vận hành thay đổi, kiểm tra và giám sát thiết bị bằng cách nào? | SSH, giao diện quản lý, API cấu hình, AAA/RBAC, automation, giám sát cấu hình | Cấu hình, thao tác quản trị, nhật ký thay đổi, dữ liệu vận hành |

### 2.1. Hình dung bằng một hệ thống giao thông

- **Control plane** tương tự bộ phận tính toán các tuyến đường và cập nhật biển chỉ dẫn dựa trên bản đồ, sự cố hoặc quy định.
- **Data plane** tương tự luồng xe đang di chuyển theo chỉ dẫn tại từng nút giao; các chốt kiểm soát có thể cho đi, đổi hướng hoặc chặn.
- **Management plane** tương tự phòng điều hành, nơi người vận hành thay đổi quy tắc và kiểm tra trạng thái.

Ẩn dụ chỉ giúp hình dung. Trong hệ thống thật, một router có thể chạy cả ba mặt phẳng trên cùng một thiết bị; một nền tảng SDN có thể đặt logic điều khiển tập trung ở controller và thực thi chuyển tiếp trên nhiều switch; một số thiết bị còn xử lý cả gói tin ngoại lệ bằng CPU.

### 2.2. Mô hình khái niệm

~~~mermaid
flowchart TB
    OP["Người vận hành / hệ thống quản trị"]
    MP["Management plane<br/>Cấu hình, AAA, API, giám sát"]
    CP["Control plane<br/>Routing, topology, policy"]
    RIB["RIB / trạng thái điều khiển"]
    FIB["FIB + bảng adjacency + quy tắc xử lý"]
    DP["Data plane<br/>Match → Action → Forward / Drop"]
    NET["Lưu lượng từ người dùng và dịch vụ"]
    OUT["Lưu lượng tới next hop / đích"]
    OP --> MP
    MP -->|"Thay đổi cấu hình / chính sách"| CP
    MP -. "Triển khai chính sách" .-> DP
    CP --> RIB
    RIB -->|"Chọn và lập trình đường đi"| FIB
    FIB --> DP
    NET --> DP
    DP --> OUT
    DP -. "Counters / sự kiện / exception" .-> CP
    DP -. "Telemetry" .-> MP
~~~

Sơ đồ mô tả **quan hệ chức năng**: việc lập trình FIB và cập nhật chính sách có thể có thêm tầng trung gian, driver, agent, controller hoặc phần cứng tùy hệ thống. Mũi tên phản hồi từ data plane không có nghĩa mọi gói tin đều phải đi qua control plane.

**Điểm cần nhớ:** data plane thường xử lý lưu lượng theo bảng đã được cài đặt sẵn để đạt tốc độ cao; control plane cập nhật các bảng ấy khi topology, đường đi hoặc chính sách thay đổi.

## 3. Control plane: mạng học đường đi và ra quyết định như thế nào?

Control plane duy trì **nhận thức về mạng**. Với một router, nhiệm vụ điển hình là tìm được các mạng đích, đánh giá các đường đi khả dụng, chọn đường thích hợp và cung cấp thông tin cần thiết cho quá trình chuyển tiếp.

### 3.1. Nguồn thông tin cho quyết định

Một router có thể biết mạng đích thông qua:

| Nguồn | Ví dụ | Đặc điểm |
|---|---|---|
| **Connected route** | Mạng 10.10.10.0/24 gắn trực tiếp vào interface | Hình thành từ cấu hình/trạng thái interface phù hợp |
| **Static route** | Đến 10.20.30.0/24 qua next hop 10.10.20.2 | Do người quản trị/automation khai báo; cần quản lý khi mạng thay đổi |
| **Dynamic routing** | OSPF, IS-IS, BGP học thông tin từ láng giềng | Thích nghi với thay đổi theo thuật toán và chính sách của giao thức |
| **Chính sách từ hệ thống điều khiển** | SDN controller cấp route hoặc rule cho thiết bị | Phụ thuộc kiến trúc, API và cơ chế đồng bộ của nền tảng |

Control plane còn xử lý các hoạt động như thiết lập quan hệ láng giềng định tuyến, lựa chọn đường tốt nhất theo tiêu chí của giao thức, phân phối và rút lại route. **OSPF**, **IS-IS** và **BGP** không chọn đường theo cùng một thuật toán; không nên đồng nhất mọi “best path” với “đường ít hop nhất”.

Không phải trạng thái nào liên quan tới gói tin cũng đến từ giao thức routing. Chẳng hạn **ARP** (IPv4) và **Neighbor Discovery, ND** (IPv6) giúp xác định thông tin láng giềng ở đường kết nối cục bộ; quá trình này cung cấp dữ liệu cho bảng adjacency/neighbor mà data plane cần khi truyền gói tới next hop.

### 3.2. RIB khác FIB ở đâu?

**RIB (Routing Information Base)** là cơ sở thông tin định tuyến do hệ thống điều khiển duy trì. Nó phản ánh các đường đi đã biết và những đường đi được lựa chọn theo cơ chế của thiết bị/hệ điều hành mạng. Trong một số hệ thống, có nhiều bảng RIB theo VRF, giao thức hoặc ngữ cảnh.

**FIB (Forwarding Information Base)** là cơ sở tra cứu được tối ưu để xử lý lưu lượng: với địa chỉ đích hoặc một tập trường tương ứng, data plane xác định hành động chuyển tiếp hoặc loại bỏ. FIB thường được xây dựng từ các route đã chọn và có thể chứa thông tin về next hop, cổng ra, xử lý đặc biệt. Bảng neighbor/adjacency bổ sung thông tin cần thiết để đóng gói frame ở liên kết tiếp theo.

| Khía cạnh | RIB | FIB |
|---|---|---|
| Chức năng chính | Duy trì và lựa chọn thông tin về các đường đi | Tra cứu nhanh để chuyển tiếp gói tin |
| Mặt phẳng gắn với | Chủ yếu control plane | Chủ yếu data plane |
| Hình thức xử lý | Cập nhật khi topology/chính sách thay đổi | Tra cứu rất thường xuyên khi có lưu lượng |
| Tối ưu ưu tiên | Độ chính xác của trạng thái và quyết định tuyến | Tốc độ, khả năng mở rộng và hành động chuyển tiếp |
| Ví dụ kiểm tra | Xem route được học từ giao thức nào, metric và next hop | Xem đích khớp entry nào, cổng ra và kiểu xử lý |

**RIB và FIB không phải hai bản sao bắt buộc giống hệt nhau.** Một route xuất hiện trong bảng điều khiển nhưng có thể chưa được lập trình thành công xuống phần cứng, hoặc bị ảnh hưởng bởi giới hạn tài nguyên/chính sách. Ngược lại, một số thiết bị có entry chuyển tiếp do cấu hình đặc biệt, tunnel, ACL hoặc cơ chế fast path không được biểu diễn đơn giản như một route RIB.

### 3.3. Từ routing decision tới forwarding decision

Quá trình điển hình gồm:

1. Interface và giao thức cung cấp trạng thái kết nối, thông tin mạng đích và láng giềng.
2. Control plane chọn route phù hợp dựa trên chính sách, administrative preference, metric và thuật toán liên quan.
3. Hệ thống lập trình FIB hoặc các bảng chuyển tiếp tương đương.
4. Khi gói tin đến, data plane tra cứu FIB và quy tắc xử lý để quyết định cổng ra, next hop, tunnel hoặc drop.
5. Khi route, policy hoặc láng giềng thay đổi, control plane cập nhật trạng thái và đẩy kết quả mới xuống data plane.

Trong nhiều thiết bị, xử lý gói tin thông thường ở **fast path** (ASIC, NPU, kernel forwarding hay datapath phần mềm) và không cần CPU điều khiển đánh giá lại routing protocol cho mỗi gói.

### 3.4. Sự kiện ngoại lệ và gói dành cho chính thiết bị

Không phải mọi gói đều chỉ được chuyển tiếp. Một số gói cần đến chức năng của control plane hoặc tiến trình ở CPU, chẳng hạn thông điệp định tuyến gửi cho router, thông điệp điều khiển nhất định, lưu lượng truy cập trực tiếp địa chỉ quản trị, hoặc gói không xử lý được ở fast path. Thiết bị có thể thực hiện **punt** (chuyển gói lên CPU/slow path), xử lý bằng phần cứng hoặc bỏ gói tùy loại thiết bị và cấu hình.

Do đó, hệ thống an toàn cần bảo vệ **khả năng xử lý control plane** trước lưu lượng không cần thiết hoặc độc hại. Đây là lý do các kỹ thuật như **Control Plane Policing (CoPP)**, giới hạn lưu lượng vào CPU và chỉ cho phép các giao thức điều khiển cần thiết xuất hiện trong thiết kế.

## 4. Data plane: gói tin thực sự đi qua mạng như thế nào?

Data plane thực hiện các hành động trực tiếp lên lưu lượng. Những hành động này không chỉ là chuyển tiếp: có thể bao gồm kiểm tra điều kiện, loại bỏ, gắn nhãn, dịch địa chỉ, mã hóa/giải mã tunnel, ghi bộ đếm hoặc đưa gói vào hàng đợi.

### 4.1. Các bước xử lý khái niệm

~~~mermaid
flowchart TD
    IN["Gói / frame đi vào interface"]
    PARSE["Đọc header / metadata<br/>VLAN, IP, port, tunnel"]
    MATCH["Tra bảng<br/>MAC / FIB / ACL / state / policy"]
    DEC{"Có được phép và có đường xử lý?"}
    ACT["Chọn hành động<br/>NAT, QoS, next hop, tunnel..."]
    TX["Đóng gói phù hợp và gửi ra cổng"]
    DROP["Drop / Reject / Ghi counter"]
    EXC["Exception / punt nếu được thiết kế"]
    IN --> PARSE --> MATCH --> DEC
    DEC -->|"Có"| ACT --> TX
    DEC -->|"Không"| DROP
    MATCH -. "Một số trường hợp đặc biệt" .-> EXC
~~~

Sơ đồ chỉ là mô hình logic. **Thứ tự thực thi thực tế** giữa ACL, NAT, routing, stateful inspection, tunnel và QoS khác nhau theo thiết bị, hướng lưu lượng, tính năng và nền tảng. Khi phân tích bảo mật, phải kiểm tra thứ tự xử lý cụ thể được nhà cung cấp công bố.

### 4.2. Chuyển mạch và định tuyến

- **Switching ở lớp 2:** dùng thông tin như MAC đích và VLAN để chọn cổng ra trong miền L2, dựa trên bảng MAC/forwarding. Học MAC có thể được thực hiện bằng cơ chế của data plane, với các sự kiện điều khiển liên quan tới topology như STP tùy thiết bị.
- **Routing ở lớp 3:** dùng địa chỉ IP đích và bảng chuyển tiếp để chọn next hop hoặc interface. Khi có nhiều tiền tố khớp, hành vi phổ biến là **longest prefix match** — chọn tiền tố cụ thể nhất trong bảng tra cứu phù hợp.
- **Đóng gói ở mỗi hop:** khi chuyển qua liên kết Ethernet khác, router thường thay địa chỉ MAC nguồn/đích của frame. Địa chỉ IP nguồn/đích thường được giữ nguyên nếu không có NAT hoặc thao tác tương tự; TTL IPv4 hoặc Hop Limit IPv6 giảm ở mỗi hop L3. Một số cơ chế tunnel thay đổi cách header ngoài được xử lý.

### 4.3. Các hành động bảo mật trong data plane

| Biện pháp | Điều data plane thường thực hiện | Giới hạn cần nhớ |
|---|---|---|
| **ACL / firewall rule** | Match địa chỉ, protocol, port và điều kiện khác; allow, drop hoặc reject | Rule L3/L4 không biết toàn bộ quyền nghiệp vụ của người dùng |
| **Stateful firewall** | Theo dõi trạng thái luồng/kết nối và quyết định xử lý gói phù hợp | Cần tài nguyên state; không thay thế xác thực, phân quyền của API |
| **Segmentation / network policy** | Giới hạn luồng giữa VLAN, subnet, VRF, workload hoặc vùng mạng | Phân đoạn hiệu lực phụ thuộc vị trí thực thi, phạm vi và cấu hình |
| **NAT** | Dịch địa chỉ/port theo rule và trạng thái cần thiết | NAT không mặc nhiên là chính sách bảo mật đầy đủ |
| **QoS** | Phân loại, xếp hàng, ưu tiên/giới hạn băng thông hoặc drop khi nghẽn | QoS quản lý tài nguyên; không xác minh người dùng được truy cập dữ liệu nào |
| **VPN/IPsec/tunnel** | Đóng gói, chuyển tiếp và có thể mã hóa/giải mã lưu lượng qua tunnel | Truy cập qua tunnel vẫn cần kiểm tra quyền ở đích |
| **IDS/IPS** | Sensor quan sát bản sao lưu lượng; IPS đặt inline có thể chặn theo chính sách | Mức nhìn thấy payload phụ thuộc vị trí, mã hóa TLS và cách triển khai |

Một firewall hiện đại có thể thực hiện nhiều công đoạn ở data plane, trong khi control plane/management plane chịu trách nhiệm tính toán, phân phối và quản lý rule. Đừng đồng nhất **nơi lưu rule** với **nơi gói bị chặn**.

### 4.4. Đường truyền mã hóa ảnh hưởng khả năng quan sát

Với HTTPS, router/firewall L3/L4 trung gian thường nhìn thấy metadata như IP, cổng, thời điểm và kích thước lưu lượng, nhưng **không mặc nhiên xem được nội dung HTTP** được bảo vệ bởi TLS. Muốn áp dụng chính sách tầng ứng dụng dựa trên nội dung, hệ thống cần điểm kết thúc TLS hợp lệ (ví dụ reverse proxy/API gateway) hoặc cơ chế khác được thiết kế và quản trị phù hợp.

Tương tự, một sensor IDS/NDR đặt ngoài tunnel VPN thường không quan sát được nội dung bên trong nếu nó chỉ nhìn thấy gói đã mã hóa. **Vị trí kiểm soát trên đường đi** quyết định sensor có thể thấy gì và làm gì.

## 5. Management plane: mặt phẳng thứ ba phải bảo vệ

Management plane bao gồm giao diện để cấu hình, kiểm tra, cập nhật và vận hành thiết bị: SSH, web UI, API, automation, hệ thống quản lý thiết bị, cơ chế AAA và lưu nhật ký thay đổi.

Sự khác biệt quan trọng:

- **Cấu hình route hoặc firewall policy** qua API/CLI thường là thao tác **management plane**.
- **Tính toán hoặc phân phối trạng thái định tuyến** dựa trên cấu hình và giao thức thường là chức năng **control plane**.
- **Chuyển tiếp hoặc chặn gói** theo bảng/rule đã được cài đặt là chức năng **data plane**.

Ranh giới triển khai không phải lúc nào cũng tuyệt đối. Một SDN controller có thể cung cấp cả giao diện quản trị, chức năng điều khiển và dịch vụ chính sách. Cần phân tích theo **trách nhiệm**, quyền truy cập và đường truyền, không chỉ theo tên phần mềm.

Đối với an ninh mạng, management plane cần **danh tính quản trị tách biệt**, MFA khi phù hợp, RBAC, ghi log, giới hạn IP/mạng nguồn, bảo vệ API/secret, cập nhật bản vá và lý tưởng có kênh quản trị độc lập hoặc được cô lập. Nếu một kẻ tấn công chiếm quyền quản trị, họ có thể sửa rule và route rồi làm thay đổi hoạt động của cả hai mặt phẳng còn lại.

## 6. Ví dụ xuyên suốt: truy cập HTTPS qua hai router

Xét mạng giả định:

~~~mermaid
flowchart LR
    PC["Máy khách<br/>10.10.10.25/24"]
    R1["R1<br/>LAN: 10.10.10.1<br/>Transit: 10.10.20.1/30"]
    R2["R2 + ACL<br/>Transit: 10.10.20.2/30<br/>LAN: 10.20.30.1"]
    API["API HTTPS<br/>10.20.30.50/24"]
    PC -->|"Gateway 10.10.10.1"| R1
    R1 -->|"10.10.20.0/30"| R2
    R2 -->|"10.20.30.0/24"| API
~~~

Máy khách cần gọi **https://api.example.test** ở địa chỉ 10.20.30.50, cổng TCP 443. Giả sử DNS đã phân giải tên miền thành địa chỉ này, các interface đều hoạt động, đường về được cấu hình và thiết bị được phép xử lý yêu cầu. Địa chỉ và tên miền ở đây chỉ là ví dụ dành cho học tập.

### 6.1. Trước khi có gói tin: control plane chuẩn bị đường đi

Giả sử R1 có đường tĩnh hoặc học được mạng 10.20.30.0/24 qua R2. R2 biết mạng API là mạng kết nối trực tiếp và có tuyến về mạng máy khách.

| Thiết bị | Prefix đích | Next hop / cổng ra dự kiến | Nguồn thông tin |
|---|---|---|---|
| R1 | 10.10.10.0/24 | Interface LAN | Connected |
| R1 | 10.20.30.0/24 | 10.10.20.2 qua transit | Static hoặc giao thức routing |
| R2 | 10.20.30.0/24 | Interface LAN API | Connected |
| R2 | 10.10.10.0/24 | 10.10.20.1 qua transit | Static hoặc giao thức routing |

Các entry trên mô tả quan hệ dự kiến. Nếu hai router chạy OSPF, chúng cần hình thành quan hệ thích hợp và trao đổi thông tin topology trước khi học route; nếu sử dụng static route, không có bước học route động tương ứng.

Sau khi route được chọn, FIB được lập trình để chuyển tiếp tới cổng/next hop. Thiết bị còn cần xác định địa chỉ lớp 2 của next hop thông qua cơ chế neighbor tương ứng (ví dụ ARP trên Ethernet IPv4).

### 6.2. Khi gói tin tới: data plane thực thi

1. Máy khách nhận thấy 10.20.30.50 không cùng mạng /24 nên gửi frame tới MAC của gateway R1, thông qua kết quả ARP nếu cần.
2. R1 kiểm tra header, rule áp dụng và bảng chuyển tiếp; IP đích 10.20.30.50 khớp route 10.20.30.0/24. R1 chọn next hop 10.10.20.2.
3. R1 giảm TTL của gói IPv4, cập nhật các trường/checksum phù hợp và đóng gói frame mới trên liên kết transit tới R2.
4. R2 tiếp nhận gói, áp dụng ACL/firewall theo vị trí và thứ tự xử lý được cấu hình; nếu rule cho phép, R2 chuyển tới mạng 10.20.30.0/24.
5. API nhận kết nối TCP/TLS và thực hiện xác thực/phân quyền ở lớp ứng dụng. **Cho phép qua router/ACL không đồng nghĩa cho phép đọc dữ liệu API.**
6. Gói phản hồi cần có tuyến về và được mọi rule hoặc trạng thái firewall liên quan cho phép. Với một số firewall stateful, cơ chế xử lý chiều về phụ thuộc vào trạng thái luồng đã được thiết lập.

Ví dụ một chính sách kết nối có thể phát biểu:

~~~text
Nguồn: 10.10.10.0/24
Đích: 10.20.30.50/32
Giao thức: TCP
Cổng đích: 443
Hành động: ALLOW

Các kết nối khác: chỉ cho phép nếu có quy tắc hợp lệ khác
~~~

Đây là biểu diễn **logic**, không phải cú pháp ACL có thể copy trực tiếp vào một thiết bị. Cách đặt rule, chiều áp dụng, thứ tự match, implicit deny và cách xử lý kết nối phản hồi khác nhau giữa các hệ thống. Hệ thống thật cần quy tắc cụ thể cho lưu lượng được mong đợi và khả năng ghi log phù hợp.

### 6.3. Một route hợp lệ vẫn có thể không truy cập được

Giả sử R1 có FIB đúng tới 10.20.30.0/24 và R2 biết đường về, nhưng ACL trên R2 **deny TCP/443** từ 10.10.10.0/24. Lúc này:

- **Control plane:** route vẫn có thể được học và lựa chọn chính xác.
- **Data plane:** lưu lượng HTTPS bị chặn theo chính sách.
- **Ứng dụng:** không thấy request vì gói không đến được API.

Ngược lại, nếu ACL cho phép nhưng route về bị thiếu, luồng có thể thất bại do bất đối xứng hoặc không có đường phản hồi. Chẩn đoán cần kiểm tra **cả route hai chiều, FIB, ACL/state, neighbor và trạng thái dịch vụ**, thay vì cho rằng “có route thì phải ping hoặc truy cập được”.

### 6.4. Khi tuyến mạng thay đổi

Nếu R1 có hai đường tới 10.20.30.0/24 qua các next hop khác nhau, một giao thức định tuyến động có thể cập nhật lựa chọn sau khi phát hiện sự cố. Control plane cần thời gian phát hiện, tính toán và lập trình lại FIB; khoảng này được gọi chung là quá trình **hội tụ** (convergence).

Tại thời điểm chuyển đổi, có thể xảy ra mất gói, loop tạm thời hoặc đường đi không nhất quán tùy topology và thiết kế. Khi FIB mới được cài đặt, data plane bắt đầu dùng đường chuyển tiếp mới. **Khả năng hồi phục phụ thuộc cả tốc độ hội tụ lẫn khả năng cập nhật FIB và trạng thái liên quan.**

## 7. So sánh thiết bị truyền thống, phần mềm, SDN và cloud

Cặp khái niệm control/data plane được áp dụng rộng hơn router vật lý.

| Kiến trúc | Control plane thường đặt ở đâu? | Data plane ở đâu? | Điểm cần lưu ý về bảo mật |
|---|---|---|---|
| **Router/switch vật lý truyền thống** | Tiến trình định tuyến và điều khiển trên thiết bị | ASIC/NPU hoặc cơ chế forwarding của thiết bị; một số xử lý bằng CPU | Phân quyền quản trị, bảo vệ giao thức routing, giới hạn lưu lượng đến CPU, kiểm soát ACL |
| **Linux router / virtual switch** | Routing daemon, network stack, agent hoặc controller | Kernel forwarding, bridge, vSwitch, eBPF/XDP hay user-space datapath | Cô lập tiến trình, quyền host, cấu hình firewall, kiểm soát truy cập tới agent |
| **SDN** | Một hoặc nhiều controller logic quản lý topology/chính sách và phân phối flow/rule | Switch/router/virtual switch thực thi flow table hoặc chính sách | Bảo vệ controller và API, xác thực kênh controller–device, kiểm soát rollout, tính sẵn sàng |
| **Cloud VPC / mạng ảo** | Dịch vụ điều khiển của nền tảng kết hợp cấu hình route, security group, policy người dùng cung cấp | Hạ tầng mạng ảo hóa phân tán, hypervisor, NIC/offload và các thành phần nhà cung cấp | Cloud IAM, cấu hình security group/route, phân đoạn workload, flow logs và shared responsibility |

### 7.1. SDN: tách biệt điều khiển và chuyển tiếp rõ hơn

Trong Software-Defined Networking (**SDN**), logic điều khiển có thể được tập trung về mặt logic tại controller. Controller lập trình chính sách hoặc entry chuyển tiếp xuống thiết bị bằng giao diện tương ứng. Các giao thức cụ thể khác nhau theo nền tảng; **OpenFlow** là một ví dụ về giao thức dùng để lập trình flow table, không phải cơ chế duy nhất của SDN.

~~~mermaid
flowchart TB
    ADM["Quản trị / Policy API"]
    CTRL["SDN controller / cụm controller"]
    SW1["Switch / datapath A"]
    SW2["Switch / datapath B"]
    SW3["Switch / datapath C"]
    H1["Host / workload A"]
    H2["Host / workload B"]
    ADM --> CTRL
    CTRL -. "Cập nhật flow/policy an toàn" .-> SW1
    CTRL -. "Cập nhật flow/policy an toàn" .-> SW2
    CTRL -. "Cập nhật flow/policy an toàn" .-> SW3
    H1 --> SW1 --> SW2 --> SW3 --> H2
~~~

Tách logic có thể giúp triển khai chính sách nhất quán và tự động hóa thay đổi. Đồng thời controller trở thành thành phần **có quyền ảnh hưởng rộng**; cần bảo vệ API, quyền quản trị, chứng thực giữa controller và thiết bị, kiểm tra cấu hình trước khi áp dụng và cơ chế khôi phục khi controller mất kết nối.

**Mất kết nối với controller không có một kết quả cố định:** datapath có thể tiếp tục chuyển tiếp theo rule đã cài, hết hạn rule, không xử lý flow mới, fail-open hay fail-closed tùy cấu hình và nền tảng. Cần xác định hành vi mong muốn khi thiết kế mạng an toàn.

### 7.2. Cloud: một thay đổi policy có thể lan tới nhiều datapath

Trong cloud, người quản trị cập nhật route table hoặc security group qua control/management API. Nền tảng sau đó phân phối trạng thái cần thiết đến các điểm thực thi trong hạ tầng ảo hóa. Một instance có thể chuyển tiếp qua các thành phần phần mềm/hardware mà người dùng không trực tiếp nhìn thấy.

**Ví dụ:** sửa security group để chỉ cho phép cổng 443 từ subnet ứng dụng là thay đổi chính sách; các datapath tương ứng phải thực thi chính sách đó khi gói đến. IAM kiểm soát **ai được phép sửa security group**, còn security group kiểm soát **lưu lượng nào được phép đi qua**. API của ứng dụng vẫn kiểm tra danh tính và quyền nghiệp vụ.

Điều này giải thích vì sao quản lý thay đổi, rà soát quyền cloud, phát hiện cấu hình trôi (configuration drift) và kiểm thử đường lưu lượng đều rất quan trọng.

### 7.3. Kubernetes và mạng workload

Trong Kubernetes, các thành phần điều khiển tạo và phân phối trạng thái cho pods, services và chính sách; CNI/agent hoặc công nghệ datapath (iptables/nftables, eBPF, vSwitch...) có thể thực thi mạng tùy plugin. **Kubernetes NetworkPolicy** mô tả ý định giới hạn lưu lượng tới/từ pods, nhưng hiệu lực và tính năng phụ thuộc implementation CNI thực tế.

Không thể suy ra một NetworkPolicy đang bảo vệ workload chỉ từ việc manifest đã được lưu. Cần kiểm tra plugin có hỗ trợ chính sách, rule được triển khai và lưu lượng thực tế bị chặn/cho phép như dự kiến.

## 8. Mối đe dọa theo từng mặt phẳng

Phân biệt mặt phẳng giúp nhận biết **kẻ tấn công muốn điều khiển quyết định** hay **muốn lợi dụng đường chuyển tiếp**, cũng như cách họ có thể can thiệp vào cấu hình quản trị.

| Mặt phẳng | Kịch bản rủi ro | Hậu quả có thể xảy ra | Lớp phòng vệ điển hình |
|---|---|---|---|
| Control | Thông tin định tuyến giả, route leak/hijack, policy/controller bị thay đổi | Lưu lượng đi sai đường, mất kết nối, bị thu hút về vùng không mong muốn | Lọc prefix/neighbor, xác thực định tuyến khi hỗ trợ, kiểm tra origin BGP bằng RPKI/ROV khi phù hợp, quản trị thay đổi |
| Control | Lưu lượng điều khiển quá lớn hoặc bất thường làm quá tải CPU | Tiến trình định tuyến bị ảnh hưởng, cập nhật tuyến chậm hoặc mất neighbor | CoPP, giới hạn protocol, ACL bảo vệ địa chỉ thiết bị, giám sát CPU/control traffic |
| Data | ACL/segmentation thiếu hoặc sai thứ tự rule | Truy cập trái phép giữa vùng, lateral movement, lộ dữ liệu | Default deny hợp lý, least privilege mạng, kiểm tra luồng thực tế, rule review |
| Data | Lưu lượng DDoS hoặc số lượng state vượt khả năng thiết bị | Nghẽn băng thông, cạn bảng trạng thái, giảm hiệu năng | Rate limiting, chống DDoS, capacity planning, giám sát và điều phối |
| Data | Thiếu lọc IP giả mạo hoặc sai cấu hình đường đi | Lạm dụng địa chỉ nguồn, khó truy vết, vượt qua một số quy tắc tin cậy theo IP | Ingress/egress filtering, anti-spoofing, uRPF nếu phù hợp với topology |
| Management | Lộ tài khoản quản trị, API token, giao diện quản lý công khai | Kẻ xâm nhập sửa route, ACL, cấu hình VPN/IDS và giám sát | MFA, RBAC, tách vùng quản trị, secret rotation, audit và kiểm soát thay đổi |

Các cột mô tả ví dụ điển hình, không phải phân loại tuyệt đối. Một sự cố thường băng qua nhiều mặt phẳng: tài khoản quản trị bị đánh cắp (**management**) → route/policy bị sửa (**control**) → gói tin đi qua vùng trái phép (**data**) → dữ liệu ứng dụng bị lộ.

### 8.1. Bảo vệ control plane

**Các biện pháp quan trọng:**

1. **Giới hạn láng giềng và kênh giao thức định tuyến.** Chỉ thiết lập phiên routing với đối tác được phép; sử dụng cơ chế xác thực, lọc và bảo vệ phiên mà giao thức/nền tảng hỗ trợ.
2. **Kiểm tra những route được chấp nhận và công bố.** Với BGP, dùng prefix filter, max-prefix, chính sách import/export, giám sát bất thường và RPKI Route Origin Validation (**ROV**) khi phù hợp. ROV giúp kiểm tra tính hợp lệ của AS nguồn so với ROA, **không xác thực toàn bộ AS path hay đảm bảo route luôn an toàn**.
3. **Bảo vệ CPU và địa chỉ của thiết bị.** Dùng CoPP/control-plane ACL, giới hạn truy cập các giao thức điều khiển/địa chỉ loopback và tách quản trị khỏi mạng người dùng.
4. **Giám sát tính nhất quán.** Theo dõi neighbor state, số route, thay đổi next hop, biến động topology, CPU/control traffic và độ trễ lập trình FIB.
5. **Bảo vệ controller nếu dùng SDN.** Giới hạn quyền thay đổi chính sách, xác thực và mã hóa kết nối với datapath, thử kế hoạch xử lý khi mất controller.

Không nên áp dụng cấu hình hạn chế control plane một cách mù quáng: giới hạn quá chặt có thể chặn chính các gói cần để routing hoạt động hoặc phục hồi sau sự cố. Cần dựa trên lưu lượng bình thường và kiểm chứng tác động.

### 8.2. Bảo vệ data plane

**Các biện pháp quan trọng:**

1. **Phân đoạn theo nhu cầu thực tế.** Chỉ cho phép luồng giữa người dùng, ứng dụng, cơ sở dữ liệu, dịch vụ hạ tầng và mạng quản trị khi có nhu cầu xác định.
2. **Thực thi chính sách ở đúng vị trí.** ACL, stateful firewall, network policy, IPS hoặc egress control phải nằm trên tuyến lưu lượng liên quan; đường vòng hoặc route bất đối xứng có thể làm chính sách mất hiệu lực.
3. **Chống giả mạo địa chỉ.** Kiểm tra nguồn tại ranh giới phù hợp; cân nhắc uRPF theo chế độ phù hợp khi có nhiều đường đi và routing bất đối xứng.
4. **Quản lý năng lực thiết bị.** Theo dõi băng thông, packet drops, TCAM/flow table, conntrack/state table, queue, tunnel và khả năng xử lý mã hóa khi dùng VPN.
5. **Xác minh kết quả.** Kiểm tra traffic được phép và bị chặn trong phạm vi cho phép; đừng chỉ đối chiếu file cấu hình mà bỏ qua trạng thái rule đã được lập trình.

### 8.3. Bảo vệ management plane

Quyền cấu hình route, ACL, firewall, VPN và cloud policy cần được cấp theo **nguyên tắc quyền tối thiểu**. Thiết kế nên có danh tính cá nhân cho thao tác quản trị, quy trình phê duyệt thay đổi cần thiết, cấu hình được quản lý phiên bản, kênh quản lý riêng và log phục vụ truy vết. Đối với automation, credential ngắn hạn và phân quyền theo phạm vi công việc giúp giảm hậu quả khi token bị lộ.

## 9. Khi hai mặt phẳng không đồng bộ

Một điều dễ bỏ sót là trạng thái mong muốn ở control plane/management plane và trạng thái **được thực thi thực tế** ở data plane có thể khác nhau tạm thời hoặc kéo dài do lỗi.

| Tình huống | Dấu hiệu | Điều cần kiểm tra |
|---|---|---|
| Route xuất hiện trong RIB nhưng không được cài vào FIB | Ping/traffic thất bại dù bảng route có đường phù hợp | Khả năng lập trình FIB, next hop resolution, giới hạn tài nguyên và lỗi platform |
| FIB có route nhưng ACL từ chối | Kết nối bị drop; route trông vẫn bình thường | Counter/rule thực thi, hướng policy, nguồn/đích/port và thứ tự xử lý |
| Control plane vừa đổi route nhưng FIB còn giá trị cũ | Lưu lượng đi đường cũ hoặc mất gói ngắn hạn | Trạng thái convergence, đồng bộ thiết bị, thời gian cập nhật phần cứng |
| SDN/controller mất liên kết với switch | Flow đã có vẫn hoạt động nhưng lưu lượng mới có thể lỗi | Thời hạn flow, fail-open/fail-closed, hành vi khi controller unreachable |
| Quá tải CPU/control plane | Routing neighbor mất hoặc cập nhật chậm; luồng cũ có thể còn chạy | CPU, CoPP drop, exception traffic, protocol logs |
| Nút mạng chuyển tiếp nhưng ứng dụng không hoạt động | Kết nối TCP/TLS hoặc request HTTP thất bại ở các mức khác nhau | Listener, DNS, TLS, API gateway, authz và health của dịch vụ |

**Không thể suy luận data plane hoạt động bình thường chỉ vì control plane báo “up”.** Cũng không thể kết luận control plane hoàn toàn lành mạnh chỉ vì một số luồng đã tồn tại vẫn đang chạy.

### 9.1. Một chuỗi kiểm tra có thể lặp lại

Khi người dùng không truy cập được một dịch vụ, hãy khoanh vùng theo thứ tự:

1. **Xác định 5-tuple và hướng lưu lượng:** IP nguồn, IP đích, protocol, cổng nguồn/đích; thêm VLAN, VRF, tunnel, workload và thời điểm nếu có.
2. **Kiểm tra giải tên và trạng thái đích:** DNS có trả đúng địa chỉ dự kiến không, dịch vụ có đang lắng nghe đúng cổng không?
3. **Kiểm tra control plane:** route hai chiều, next hop, trạng thái neighbor/adjacency, BGP/OSPF nếu có, sự thay đổi topology và policy.
4. **Kiểm tra data plane:** FIB/forwarding lookup, ACL và firewall state, NAT, security group, counters, drops, capture phù hợp tại từng điểm.
5. **Kiểm tra management/config:** có thay đổi policy, rollout, quyền, cấu hình hay lỗi đồng bộ trong khoảng thời gian sự cố không?
6. **Liên hệ lớp ứng dụng và danh tính:** bắt tay TLS, phản hồi HTTP, xác thực/authorization và log API nếu gói đã đến nơi.

Đừng dùng một kết quả ping/traceroute đơn lẻ để kết luận chắc chắn. ICMP có thể bị chặn, traceroute có thể bị ảnh hưởng bởi chính sách trả lời của router, ECMP và đường đi bất đối xứng; khả năng trả lời ICMP cũng không chứng minh API đã sẵn sàng.

### 9.2. Ví dụ quan sát trên Linux

Các lệnh sau chỉ nhằm minh họa cách xem bảng tuyến và láng giềng trên một máy Linux có công cụ tương ứng. Chúng không chỉnh sửa hệ thống:

~~~bash
ip route show
ip route get 10.20.30.50
ip neigh show
~~~

- **ip route show** hiển thị thông tin định tuyến của kernel ở ngữ cảnh đang dùng.
- **ip route get** yêu cầu hệ điều hành tính kết quả tra route cho đích cụ thể, có thể cần thêm nguồn/interface/VRF khi topology phức tạp. Nó **không chứng minh** mọi gói sẽ tới đích thành công.
- **ip neigh show** cung cấp trạng thái láng giềng ARP/ND mà việc chuyển tiếp có thể sử dụng.

Đối với thiết bị có ASIC, cần thêm công cụ kiểm tra **hardware FIB/ACL counters** tương ứng từ nhà cung cấp: chỉ xem route ở mặt điều khiển đôi khi chưa đủ.

## 10. Quan hệ với DNS, Wi-Fi, VPN, IDS/IPS và bảo mật đám mây

Hai mặt phẳng là cách phân tích hữu ích đối với những công nghệ sẽ gặp trong học phần bảo mật mạng.

### DNS

DNS trả lời câu hỏi *tên miền nào ánh xạ tới địa chỉ/tài nguyên nào*. Việc phân giải tên có thể diễn ra **trước khi** một kết nối IP tới máy chủ được thiết lập. DNS là một hệ thống điều khiển ở **tầng ứng dụng/dịch vụ tên**, nhưng **không phải RIB/FIB của router**. Router chuyển tiếp các gói DNS như những gói IP khác, trừ khi thiết bị đóng vai trò DNS service hoặc có chính sách đặc biệt. Khi phân tích sự cố, cần tách lỗi DNS khỏi lỗi định tuyến và lỗi firewall.

### Wi-Fi

Control plane của mạng không dây có thể xử lý khám phá, association, authentication, quản lý radio/roaming theo kiến trúc; data plane chuyển frame lưu lượng của client sau khi các điều kiện kết nối cần thiết được đáp ứng. Việc kết nối được access point chấp nhận **không** tự trao quyền vào mọi dịch vụ doanh nghiệp. VLAN, NAC/802.1X, firewall và danh tính ứng dụng vẫn cần phối hợp.

### VPN và tunnel

Control plane của công nghệ tunnel có thể thiết lập phiên, thương lượng khóa/chính sách hoặc phân phối tuyến tới mạng bên kia. Data plane đóng gói và chuyển gói, đồng thời mã hóa/giải mã nếu giao thức và triển khai yêu cầu. Ví dụ, IKE thường tham gia thương lượng các thông số IPsec; đường truyền IPsec bảo vệ lưu lượng thực tế theo chính sách SA được cài đặt. **Đường tunnel up không bảo đảm ứng dụng phía sau có quyền hoặc còn hoạt động.**

### IDS/IPS

Một IDS nhận traffic qua SPAN/TAP hoặc sensor phù hợp có thể phát hiện hành vi nhưng thường không trực tiếp chặn gói đang đi qua nếu hoạt động thụ động. IPS inline có thể đưa ra hành động chặn ở đường lưu lượng. Chính sách và chữ ký được cấu hình/phân phối qua các thành phần điều khiển/quản trị; kết quả phụ thuộc vào **data plane có nhìn thấy lưu lượng cần kiểm tra** và khả năng xử lý của sensor.

### Cloud và môi trường đa vùng

VPC routing, cloud IAM, firewall/security group, workload identity và KMS bảo vệ những khía cạnh khác nhau. Thay đổi cloud route hoặc security group là một thao tác về cấu hình/trạng thái điều khiển, trong khi hạ tầng xử lý gói mạng phải thi hành kết quả. Danh tính workload giúp hạn chế **ai được gọi API hoặc tài nguyên cloud**, còn network policy giảm **đường nào có thể kết nối**.

## 11. Mô hình hóa mối đe dọa theo mặt phẳng

Khi dựng sơ đồ mối đe dọa, đừng chỉ vẽ dữ liệu từ client tới server. Hãy vẽ thêm **đường điều khiển và quản trị** vì chúng quyết định đường đi của dữ liệu.

~~~mermaid
flowchart LR
    USER["Người dùng"]
    EDGE["Gateway / firewall"]
    APP["Ứng dụng"]
    DB["Cơ sở dữ liệu"]
    ROUTE["Routing / SDN control"]
    ADMIN["Quản trị viên / CI"]
    USER -->|"Data traffic"| EDGE -->|"Allowed flows"| APP -->|"DB requests"| DB
    ADMIN -. "Config / policy" .-> ROUTE
    ADMIN -. "Firewall policy" .-> EDGE
    ROUTE -. "FIB / forwarding updates" .-> EDGE
~~~

Đối với mỗi ranh giới, hãy hỏi:

- **Chủ thể nào có quyền thay đổi quyết định?** Một người quản trị, routing neighbor, SDN controller, cloud API hay agent tự động?
- **Họ chứng minh danh tính bằng gì?** SSH key, MFA, certificate, token API hay protocol authentication?
- **Thông tin nào có thể bị làm giả hoặc bị lỗi?** Route, prefix, next hop, policy rule, neighbor entry, lệnh cấu hình.
- **Quyết định được thực thi ở đâu?** ASIC, kernel, virtual switch, firewall appliance, cloud datapath hay proxy?
- **Nếu thành phần đó bị xâm nhập thì bán kính ảnh hưởng là gì?** Một VLAN, nhiều tenant, tất cả VPC, toàn bộ cụm controller hay một nhóm endpoint?
- **Bằng chứng nào sẽ chỉ ra sự khác biệt?** Audit cấu hình, route change log, FIB counters, flow logs, telemetry IDS/IPS và log ứng dụng.

### Phân biệt ba kiểu thất bại

| Kiểu thất bại | Ví dụ | Cách tiếp cận |
|---|---|---|
| **Sai quyết định** | Routing policy công bố nhầm prefix và thu hút lưu lượng | Xem control plane, nguồn route, quyền thay đổi và chính sách lọc |
| **Sai thực thi** | ACL dự kiến deny nhưng rule chưa được áp dụng ở datapath | Kiểm tra bảng thực thi, thứ tự rule, traffic test và counter |
| **Sai quyền thay đổi** | Tài khoản automation có quyền sửa mọi route table | Giới hạn management/API permission, xác thực, audit và quy trình cấp quyền |

Ba kiểu có thể xảy ra đồng thời. Một cuộc kiểm tra kiến trúc tốt cần xác minh **ai được đặt chính sách**, **chính sách có đúng không** và **gói tin có bị xử lý theo chính sách không**.

## 12. Thực hành phân tích tình huống

Giả sử một doanh nghiệp có mạng nhân viên, mạng ứng dụng, mạng cơ sở dữ liệu và mạng quản trị. Trước đây, chỉ máy ứng dụng được phép truy cập CSDL. Sau một đợt triển khai tự động, nhân viên không truy cập được ứng dụng, còn dashboard router vẫn cho biết các neighbor OSPF đang ở trạng thái bình thường.

**Nhiệm vụ 1 — Vẽ hai đường:** vẽ đường dữ liệu nhân viên → gateway → API → CSDL, và đường điều khiển/quản trị automation → policy → thiết bị thực thi. Đánh dấu nơi ACL/security group được lập trình.

**Nhiệm vụ 2 — Liệt kê giả thuyết:** ít nhất một giả thuyết thuộc control plane (ví dụ route không được cài xuống FIB), một giả thuyết thuộc data plane (ACL chặn nhầm), một giả thuyết thuộc management plane (automation vừa triển khai policy sai) và một giả thuyết ngoài mạng (dịch vụ API bị lỗi).

**Nhiệm vụ 3 — Chỉ định bằng chứng:** cho mỗi giả thuyết, ghi nguồn kiểm tra: RIB, FIB, neighbor, ACL counter, flow log, nhật ký cấu hình hoặc log ứng dụng.

**Nhiệm vụ 4 — Lựa chọn sửa chữa:** ưu tiên thay đổi nhỏ có thể kiểm chứng và có phương án quay lại cấu hình cũ; xác minh cả kết nối được phép và kết nối phải bị chặn sau sửa chữa.

Một bài giải hợp lý cần tránh kết luận “OSPF up thì mạng chắc chắn tốt”. OSPF neighbor bình thường chỉ là **một phần trạng thái điều khiển**; kết nối ứng dụng còn phụ thuộc FIB, policy, đường về, TLS và dịch vụ.

### Ví dụ ma trận kiểm chứng

| Luồng mong muốn | Quyết định policy | Kết quả cần xác minh |
|---|---|---|
| Client → API TCP/443 | Allow tại biên ứng dụng nếu thuộc phạm vi truy cập | TCP/TLS/HTTP tới đúng dịch vụ, log tương ứng |
| Client → Database TCP/cổng DB | Deny | Không thể tạo phiên trực tiếp; có drop/counter phù hợp |
| API workload → Database TCP/cổng DB | Allow cho danh tính/nguồn phù hợp | Truy cập dữ liệu chỉ theo quyền DB của workload |
| Client → thiết bị mạng qua SSH quản trị | Deny ngoài mạng quản trị | Gói bị chặn ở vị trí thích hợp |
| Management workstation → thiết bị quản trị | Allow với xác thực và quyền phù hợp | Đăng nhập được ghi audit; quyền hạn đúng vai trò |

Sự khác biệt giữa **chính sách dự kiến** và **kết quả quan sát** chính là mục tiêu của phép kiểm thử. Cần thực hiện trên hệ thống được phép và theo quy trình thay đổi của môi trường.

## 13. Thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Control plane** | Nơi duy trì trạng thái, trao đổi thông tin mạng, lựa chọn và phân phối quyết định chuyển tiếp |
| **Data plane / forwarding plane** | Nơi xử lý gói/luồng lưu lượng theo bảng và policy đã lập trình |
| **Management plane** | Nơi quản trị, cấu hình, kiểm toán và vận hành thiết bị/hạ tầng |
| **RIB** | Cơ sở thông tin định tuyến do control plane/hệ thống routing duy trì |
| **FIB** | Cơ sở thông tin tối ưu cho tra cứu và hành động chuyển tiếp gói |
| **Next hop / adjacency** | Điểm chuyển tiếp kế tiếp và thông tin cần thiết để gửi gói trên liên kết tương ứng |
| **Longest prefix match** | Chọn entry khớp với tiền tố IP cụ thể nhất trong bảng phù hợp |
| **Convergence** | Quá trình mạng nhận ra thay đổi và cập nhật tới trạng thái định tuyến/chuyển tiếp mới |
| **Punt / slow path** | Đưa một số gói ngoại lệ đến CPU/đường xử lý chuyên biệt |
| **CoPP** | Cơ chế kiểm soát/giới hạn lưu lượng đến control plane của thiết bị |
| **SDN controller** | Thành phần điều khiển logic có thể tính toán và lập trình chính sách/flow |
| **TCAM / flow table** | Một số cấu trúc phần cứng/bảng quy tắc dùng để xử lý match/action tốc độ cao |
| **Ingress / egress** | Hướng lưu lượng đi vào / đi ra một interface, thiết bị hoặc vùng bảo vệ |
| **Fail-open / fail-closed** | Hành vi cho phép tiếp tục / mặc định từ chối khi cơ chế kiểm soát không sẵn sàng, tùy chính sách |

## 14. Tổng kết

**Control plane xây dựng và cập nhật quyết định; data plane thực thi quyết định trên lưu lượng; management plane cho phép con người và hệ thống vận hành quản lý các quyết định đó.** Sự phân chia này hiện diện trên router/switch, Linux, SDN, Kubernetes và cloud, dù cách triển khai thực tế có thể rất khác nhau.

Để xây dựng mạng an toàn, cần bảo vệ đồng thời **quyền thay đổi chính sách**, **độ tin cậy của thông tin định tuyến**, **tính đúng đắn của bảng chuyển tiếp**, **vị trí thực thi ACL/firewall/IDS/IPS**, và **khả năng quan sát kết quả thật trên lưu lượng**. Khi gặp sự cố, hãy đặt ba câu hỏi theo đúng thứ tự: *quyết định được tạo ra ở đâu, nó đã được triển khai ở đâu, và gói tin thực tế được xử lý ra sao?*
