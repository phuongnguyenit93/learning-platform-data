# Định tuyến, kết nối ngang hàng và transit trong hệ thống nhiều mạng

Khi một ứng dụng đám mây phát triển từ một mạng riêng thành nhiều mạng cho từng môi trường, sản phẩm hoặc tài khoản, câu hỏi không còn đơn giản là “có mở cổng kết nối hay chưa?”. Kiến trúc sư phải xác định **mạng nào được phép đi tới mạng nào, gói tin đi qua đâu, đường trả về là gì, ai quản lý kết nối và điều gì xảy ra khi một tuyến lỗi**. Nếu bỏ qua những câu hỏi đó, hệ thống dễ xuất hiện kết nối không đối xứng, mạng thử nghiệm truy cập nhầm sản xuất, địa chỉ IP chồng lấn, chi phí truyền dữ liệu tăng hoặc một hub trở thành điểm lỗi chung.

Bài học này thuộc chương **Kiến trúc mạng** của module **CLOUD_ARCHITECTURE**. Mục tiêu là hiểu nguyên lý **định tuyến (routing)**, **kết nối ngang hàng (peering)** và **mạng trung chuyển (transit)**; biết dùng chúng khi triển khai nhiều VPC/VNet, tài khoản, subscription hay project, và đánh giá các lựa chọn theo độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành của tư duy Well-Architected.

> **Nguyên tắc nền tảng:** Kết nối mạng là sự kết hợp của **địa chỉ không xung đột, định tuyến hai chiều, khả năng chuyển tiếp của các thành phần trung gian và chính sách bảo mật cho phép**. Một đường được vẽ trên sơ đồ hoặc một peering có trạng thái “active” không tự chứng minh ứng dụng đã liên lạc thành công.

## 1. Vì sao kiến trúc nhiều mạng cần được thiết kế riêng?

Giả sử một nền tảng đặt chỗ có các vùng chức năng:

- **Booking-prod:** API, worker và dữ liệu đặt chỗ trong mạng sản xuất của nhóm Booking.
- **Payments-prod:** dịch vụ thanh toán và những phụ thuộc bảo mật nhạy cảm hơn.
- **Shared-services:** DNS, hệ thống quan sát, công cụ triển khai hoặc dịch vụ nền tảng dùng chung.
- **Non-production:** môi trường dev, staging với quyền và chính sách khác prod.
- **On-premises:** hệ thống doanh nghiệp nội bộ kết nối qua VPN hoặc đường truyền chuyên dụng.

Tách mạng giúp quản trị tài nguyên theo nhóm, giảm phạm vi ảnh hưởng của thay đổi, giới hạn đường truy cập và định rõ ngân sách. Nhưng sau khi tách, các nhóm phải quyết định những luồng nào vẫn cần kết nối:

| Nguồn → Đích | Ví dụ nghiệp vụ | Yêu cầu kết nối |
|---|---|---|
| Booking-prod → Payments-prod | Xác nhận một khoản thanh toán | Chỉ được tới API/port cần thiết, có xác thực dịch vụ |
| Booking-prod → Shared-services | Gửi logs/traces, tra cứu DNS | Có đường đi và quyền phù hợp, không tự cấp quyền tới mọi dịch vụ chung |
| Staging → Môi trường thử nghiệm khác | Kiểm thử tích hợp | Có thể cho phép có điều kiện, tránh nối trực tiếp vào database prod |
| Prod → On-premises | Tra cứu hệ thống doanh nghiệp | Kết nối hybrid, định tuyến và phân giải tên nhất quán |
| Internet → API công khai | Người dùng đặt chỗ | Đi qua lớp công khai được bảo vệ, không mở trực tiếp kho dữ liệu |

**Ranh giới mạng không trùng hoàn toàn với ranh giới quản trị**. Hai VPC khác tài khoản có thể được kết nối; hai subnet trong cùng VPC vẫn có thể bị chặn bởi firewall hoặc security group. Việc tách account/subscription/project là quyết định quản trị; đường truyền thực tế phải được thiết kế, cấp quyền và kiểm chứng riêng.

## 2. Nền tảng định tuyến: CIDR, route table và next hop

### 2.1. Mỗi route mô tả điều gì?

**Route (tuyến)** là quy tắc lựa chọn nơi chuyển tiếp lưu lượng tới một đích IP. Một mục route thường có:

- **Destination prefix:** Dải đích dưới dạng CIDR, ví dụ 10.20.0.0/16.
- **Target/next hop:** Nơi chuyển tiếp tiếp theo, như giao diện nội bộ, peering connection, transit attachment, VPN gateway hoặc thiết bị ảo định tuyến.
- **Nguồn và phạm vi áp dụng:** Route cục bộ, cấu hình thủ công, học qua giao thức động, hoặc được dịch vụ cloud cung cấp; chịu các quy tắc ưu tiên của từng nền tảng.
- **Trạng thái khả dụng:** Một route có thể còn trong bảng nhưng next hop không sẵn sàng hoặc đường phía sau đã lỗi.

Một subnet, VPC, VNet hoặc router có thể có nhiều bảng định tuyến tại những lớp khác nhau. Khi một gói đi qua **nhiều miền định tuyến**, mỗi miền lại đưa ra quyết định chuyển tiếp dựa trên thông tin mà nó nhìn thấy. Vì vậy không thể chỉ kiểm tra bảng route của máy nguồn rồi kết luận cả hành trình đã đúng.

### 2.2. Longest-prefix match

Với nhiều tuyến khớp cùng địa chỉ đích, nguyên tắc cơ bản của định tuyến IP là chọn **tiền tố cụ thể nhất (longest-prefix match)**. Ví dụ:

| Đích trong route table | Next hop minh họa | Có khớp đích 10.20.8.50 không? |
|---|---|---|
| 0.0.0.0/0 | Internet/NAT gateway | Có, nhưng ít cụ thể nhất |
| 10.0.0.0/8 | Router nội bộ | Có |
| 10.20.0.0/16 | Transit attachment | Có |
| 10.20.8.0/24 | Thiết bị kiểm tra bảo mật | Có, cụ thể nhất |

Nếu các tuyến đều hợp lệ và thuộc cùng một quá trình lựa chọn theo tiền tố, đích **10.20.8.50** sẽ khớp tuyến **10.20.8.0/24**. Trong thực tế, khi cùng độ cụ thể, route tĩnh, route động hoặc các loại target cạnh tranh, **quy tắc ưu tiên do nền tảng quy định**; không suy ra chỉ từ bảng minh họa này.

Các prefix thường gặp:

- **10.10.0.0/16:** khoảng 65 nghìn địa chỉ IPv4 trên lý thuyết; số địa chỉ dùng được trong subnet cloud còn tùy nhà cung cấp và subnet.
- **10.10.4.0/24:** một dải con của 10.10.0.0/16.
- **0.0.0.0/0:** tuyến mặc định cho IPv4 khi không có tuyến cụ thể hơn; **không đồng nghĩa** lưu lượng chắc chắn ra Internet, vì next hop có thể là firewall hoặc transit.
- **::/0:** tuyến mặc định cho IPv6, phải xem xét riêng với các tuyến IPv4.

**Địa chỉ đích không xác định quyền truy cập.** Route tới Payments chỉ giúp tìm đường; Security Group, firewall, Network ACL, IAM và ứng dụng vẫn phải quyết định gói tin/yêu cầu có được phép hay không.

### 2.3. Đường đi và đường về

Một request API giữa hai mạng cần ít nhất hai chiều phù hợp:

~~~text
Booking API (10.10.5.10)                        Payments API (10.20.7.20)
          |                                                ^
          v                                                |
     Route đi tới 10.20.0.0/16 --> Transit --> Route tới Payments
          ^                                                |
          |                                                v
     Route trả về Booking    <-- Transit <-- Route tới 10.10.0.0/16
~~~

Nếu Booking có route tới Payments nhưng Payments không có route trả về 10.10.0.0/16, phiên TCP thường không thể hoàn tất. Tương tự, nếu lưu lượng qua một **stateful firewall**, cả hai chiều thường phải đi qua đường kiểm tra phù hợp để thiết bị duy trì trạng thái kết nối. Định tuyến bất đối xứng có thể khiến firewall loại gói hợp lệ, ngay cả khi từng bên có vẻ đều có đường tới nhau.

## 3. Kết nối ngang hàng (peering) là gì?

**Peering** kết nối trực tiếp hai mạng riêng, cho phép trao đổi lưu lượng qua hạ tầng mạng cloud theo cơ chế được nhà cung cấp hỗ trợ. Các ví dụ thường gặp là **AWS VPC Peering**, **Azure Virtual Network Peering** và **Google Cloud VPC Network Peering**.

~~~mermaid
flowchart LR
    subgraph A["Mạng A — Booking (10.10.0.0/16)"]
        APP["Booking API"]
        RTA["Route tới 10.20.0.0/16"]
        APP --> RTA
    end
    subgraph B["Mạng B — Payments (10.20.0.0/16)"]
        RTB["Route tới 10.10.0.0/16"]
        PAY["Payments API"]
        RTB --> PAY
    end
    RTA <-->|"Peering: kết nối trực tiếp hai mạng"| RTB
~~~

Trong kịch bản này, để Booking API gọi Payments API qua địa chỉ riêng, cần kiểm tra:

1. Hai dải IP không chồng lấn theo ràng buộc peering của nền tảng.
2. Kết nối peering được tạo và chấp thuận theo quy trình liên tài khoản/project/tenant nếu có.
3. Route hai chiều đã được cấu hình hoặc trao đổi đúng cách tùy nền tảng.
4. Firewall, security group, network ACL và các chính sách khác cho phép nguồn, đích và port cần thiết.
5. DNS và ứng dụng dùng đúng địa chỉ; không nhầm endpoint công khai với endpoint riêng.

### Peering không tự tạo transit

Trong các mô hình VPC/VNet peering thông dụng, peering **không có tính chuyển tiếp tự động (non-transitive)**:

~~~mermaid
flowchart LR
    A["VPC/VNet A"] <-->|"Peering A–B"| B["VPC/VNet B"]
    B <-->|"Peering B–C"| C["VPC/VNet C"]
    A -. "Không tự có đường A–C qua B" .- C
~~~

Tức là **A peering với B** và **B peering với C** không đồng nghĩa **A được dùng B như router trung chuyển để tới C**. Nếu cần lưu lượng A–C, phải thiết kế kết nối trực tiếp hoặc một cơ chế transit hợp lệ. Một số nền tảng cho phép kết hợp thiết bị ảo chuyển tiếp và cấu hình gateway transit theo điều kiện cụ thể; không được suy diễn rằng bản thân peering đã hỗ trợ chuyển tiếp tùy ý.

### Khi peering phù hợp

Peering thường là phương án đơn giản khi:

- Chỉ có **một vài cặp mạng** cần giao tiếp trực tiếp.
- Mối quan hệ kết nối khá ổn định và phạm vi các cặp có thể quản lý.
- Muốn tránh tự vận hành router ảo hoặc hub chỉ để nối hai mạng.
- Có thể đáp ứng các giới hạn CIDR, quota, phân quyền và cấu hình mạng của nhà cung cấp.

Nhược điểm xuất hiện khi số mạng tăng: nhiều kết nối cần tạo, nhiều route cần cập nhật, dễ nhầm đường được phép. Phí truyền dữ liệu qua peering, nhất là xuyên Region, cũng cần kiểm tra theo nhà cung cấp và hướng lưu lượng.

## 4. Transit: kết nối nhiều mạng thông qua trung tâm định tuyến

**Transit** là mô hình đưa lưu lượng qua một thành phần chuyển tiếp trung tâm thay vì thiết lập tất cả cặp peering. Trung tâm có thể là dịch vụ routing managed, gateway/hub hoặc thiết bị ảo mạng (*network virtual appliance — NVA*) có khả năng forwarding.

~~~mermaid
flowchart TB
    BK["Booking-prod<br/>10.10.0.0/16"] <-->|"Attachment + routes"| HUB["Transit hub<br/>Routing và segmentation"]
    PAY["Payments-prod<br/>10.20.0.0/16"] <-->|"Attachment + routes"| HUB
    SHR["Shared-services<br/>10.30.0.0/16"] <-->|"Attachment + routes"| HUB
    DEV["Non-production<br/>10.40.0.0/16"] <-->|"Attachment + routes"| HUB
    CORP["On-premises<br/>172.16.0.0/16"] <-->|"VPN / dedicated connection"| HUB
~~~

Trong sơ đồ, **có attachment không có nghĩa mọi mạng đều được phép giao tiếp với nhau**. Transit hub chỉ chuyển tiếp tới đích khi có tuyến phù hợp và không bị hạn chế bởi cơ chế phân đoạn. Đây chính là điểm cho phép tổ chức tạo nhóm mạng prod, non-prod, shared và hybrid với chính sách khác nhau.

### Các cách hiện thực hóa trên cloud

| Nền tảng | Phương án kết nối nhiều mạng | Lưu ý kiến trúc |
|---|---|---|
| **AWS** | **AWS Transit Gateway**, hoặc **AWS Cloud WAN** cho mô hình mạng rộng hơn; kết hợp kết nối VPN/Direct Connect khi cần hybrid | Transit Gateway có attachment và route table riêng; association/propagation cần thiết kế rõ. Cơ chế, chi phí và giới hạn của Cloud WAN khác Transit Gateway |
| **Azure** | **Hub-spoke với Azure Virtual Network** và NVA/Azure Firewall theo nhu cầu; **Azure Virtual WAN** với virtual hub cho kịch bản phù hợp | VNet peering không tự transitive. Forwarding, gateway transit, user-defined routes và chính sách Azure Virtual WAN phụ thuộc cấu hình và ràng buộc của từng mô hình |
| **Google Cloud** | **Network Connectivity Center (NCC)** và các mô hình hub/spoke hoặc thiết bị router/gateway phù hợp; có thể phối hợp Cloud Router, Cloud VPN, Interconnect | Không coi VPC Network Peering là transit. Loại spoke, trao đổi route, khả năng kết nối site-to-site và giới hạn NCC phải kiểm tra theo dịch vụ/cấu hình |

**Không ánh xạ ba sản phẩm thành một thực thể hoàn toàn tương đương.** Khác biệt có thể nằm ở việc học và quảng bá route, segment, kết nối qua Region, giới hạn attachment, tính năng inspection, khả năng kết nối hybrid và cách tính phí. Kiến trúc logic “các spoke nối qua transit” cần được kiểm chứng với sản phẩm thực tế.

### Transit routing: hai quyết định riêng

Một mô hình transit cần giải quyết:

1. **Spoke đưa gói vào hub bằng cách nào?** Route ở subnet/VPC/VNet hoặc cơ chế mạng tương ứng phải hướng đúng prefix về transit attachment/gateway.
2. **Hub sẽ chuyển gói tới attachment nào?** Bảng route/segment của hub phải chọn đúng next hop, và đường về phải tồn tại.

Nếu chỉ thêm route ở spoke mà hub chưa có route tới đích, gói vẫn bị drop. Nếu hub có route nhưng spoke không biết đưa gói vào hub, kết quả cũng không khác.

## 5. So sánh mesh peering, hub-and-spoke và kiến trúc kết hợp

### 5.1. Mesh peering

Khi **mọi cặp** trong N mạng đều cần kết nối trực tiếp, số kết nối peering tối đa theo mô hình full mesh là:

\[
\frac{N(N-1)}{2}
\]

Ví dụ, **6 mạng cần 15 kết nối** trong full mesh, còn **10 mạng cần 45 kết nối**. Công thức mô tả số cạnh giữa các cặp mạng, không phải số lượng route thực tế; mỗi kết nối có thể kéo theo nhiều bảng route, quyền và thay đổi vận hành.

**Ưu điểm:** Đường kết nối trực tiếp, phù hợp số ít cặp; ít phụ thuộc hub logic. **Hạn chế:** Số kết nối tăng nhanh, route và chính sách phân tán, khó chuẩn hóa khi nhiều nhóm.

### 5.2. Hub-and-spoke

Các mạng đầu cuối (**spoke**) nối vào một hub trung chuyển. Với N spoke, về mặt sơ đồ cơ bản chỉ cần **N liên kết spoke–hub**, nhưng cần thêm cấu hình route, phân đoạn, dự phòng hub và có thể các thành phần inspection.

**Ưu điểm:** Dễ chuẩn hóa kết nối, quản trị policy và mở rộng số lượng mạng; thuận tiện tích hợp mạng nội bộ. **Hạn chế:** Hub có thể trở thành điểm phụ thuộc chung về hiệu năng, cấu hình, bảo mật và chi phí; đường đi qua hub có thể dài hơn.

### 5.3. Mô hình kết hợp

Nhiều hệ thống dùng hub-and-spoke cho các kết nối xuyên nhóm, đồng thời tạo kết nối trực tiếp cho một số cặp cần độ trễ thấp hoặc lưu lượng rất lớn nếu nền tảng và chính sách cho phép. Ví dụ: Booking-prod gọi Payments-prod qua transit có kiểm soát, còn một liên kết truyền dữ liệu lớn giữa hai mạng cùng chủ sở hữu được thiết kế riêng.

Không nên thêm đường trực tiếp chỉ vì hub “có vẻ chậm”. Trước tiên phải đo **độ trễ, thông lượng, chi phí xử lý mỗi GB, chi phí xuyên vùng và yêu cầu inspection**, sau đó kiểm tra việc tạo đường mới có phá vỡ chính sách phân đoạn hoặc gây định tuyến bất đối xứng không.

| Tiêu chí | Peering trực tiếp | Transit hub | Kết hợp |
|---|---|---|---|
| Quy mô kết nối | Tốt khi ít cặp | Phù hợp khi nhiều mạng và cần quản trị trung tâm | Phù hợp khi có ngoại lệ được kiểm soát |
| Định tuyến | Chủ yếu quản lý theo từng cặp và các bảng route liên quan | Quản lý tại spoke và tại hub/segment | Cần quản lý cả hai hướng, tránh tuyến cạnh tranh |
| Phân đoạn | Dựa vào chọn cặp peering và chính sách mạng | Có thể tổ chức segment/route table và inspection tập trung | Linh hoạt nhưng dễ có đường vượt chính sách |
| Độ tin cậy | Tránh phụ thuộc một hub cho các cặp trực tiếp | Phải xem khả năng HA/failover và blast radius của hub | Nhiều đường hơn, cần xác định ưu tiên/failover |
| Chi phí | Chi phí kết nối, data transfer tùy cloud | Thường có phí hub, attachment, xử lý dữ liệu và truyền tải tùy dịch vụ | Cần đo để chứng minh lợi ích ngoại lệ |
| Vận hành | Đơn giản lúc nhỏ, phức tạp khi tăng cặp | Có thiết kế ban đầu nhiều hơn, dễ chuẩn hóa về lâu dài | Cần quy trình và tự động hóa chặt chẽ |

## 6. Thiết kế CIDR và phân đoạn trước khi tạo route

**Kế hoạch địa chỉ IP (IP address plan)** là điều kiện tiên quyết của kiến trúc nhiều mạng. Hai dải CIDR chồng lấn có thể khiến route mơ hồ và ngăn một số kiểu peering; với transit hoặc hybrid, xử lý overlapping CIDR thường đòi hỏi NAT, tái đánh địa chỉ hoặc giải pháp tích hợp khác có đánh đổi lớn.

Một quy hoạch minh họa cho doanh nghiệp:

| Mạng | CIDR IPv4 | Vai trò | Cho phép kết nối cần thiết |
|---|---|---|---|
| Booking-prod | 10.10.0.0/16 | API, ứng dụng và dịch vụ nghiệp vụ | Payments API, shared monitoring, một số on-prem |
| Payments-prod | 10.20.0.0/16 | Xử lý thanh toán | Booking qua API được kiểm soát; dịch vụ bảo mật |
| Shared-services | 10.30.0.0/16 | DNS, logging, công cụ nền tảng | Chỉ endpoint chung được phê duyệt |
| Non-production | 10.40.0.0/16 | Dev, staging | Dịch vụ thử nghiệm; không có tuyến rộng tới prod |
| On-premises | 172.16.0.0/16 | Hệ thống doanh nghiệp | Các dịch vụ hybrid cụ thể |

Các dải trên là **ví dụ**, không phải địa chỉ nên sử dụng mặc định. Một công ty đã dùng 10.0.0.0/8 ở mạng nội bộ phải quy hoạch toàn bộ trước khi cấp phát subnet mới. Đồng thời cần dự trữ đủ khoảng địa chỉ cho subnet compute, database, endpoint, container và tăng trưởng trong nhiều năm.

### Cần phân biệt “không có route” và “có route nhưng bị chặn”

- **Không quảng bá hoặc không cấu hình tuyến** từ Non-production đến Payments-prod giúp giảm khả năng đi tới đích ở lớp mạng.
- **Firewall và các chính sách bảo mật** tiếp tục chặn những luồng không được phép ngay cả khi có đường đi.
- **IAM và xác thực ứng dụng** giới hạn thao tác lên API, dữ liệu và secret; kết nối TCP được không có nghĩa người gọi đã được ủy quyền.

Thiết kế tốt thường dùng các lớp kiểm soát này phối hợp. Tách mạng là một phần của nguyên tắc **giảm quyền và giới hạn phạm vi ảnh hưởng (blast radius)**, không phải thay thế xác thực hay phân quyền ở tầng ứng dụng.

## 7. Ví dụ xuyên suốt: Booking-prod gọi Payments-prod qua transit

Giả sử hệ thống đặt chỗ cần gọi API thanh toán qua địa chỉ riêng:

- Booking API có địa chỉ **10.10.5.10** thuộc Booking-prod.
- Payments API có địa chỉ **10.20.7.20** thuộc Payments-prod.
- Hai mạng được kết nối với transit hub thông qua attachment tương ứng.
- Dịch vụ thanh toán chỉ lắng nghe HTTPS ở port 443 và xác thực danh tính workload.

### 7.1. Các bảng route minh họa

**Route table cho subnet của Booking API:**

| Đích | Next hop | Ý nghĩa |
|---|---|---|
| 10.10.0.0/16 | Local | Kết nối trong Booking-prod |
| 10.20.0.0/16 | Transit attachment | Gửi tới Payments-prod qua hub |
| 10.30.0.0/16 | Transit attachment | Gửi tới dịch vụ chung được phép |
| 172.16.0.0/16 | Transit attachment | Tới các hệ thống nội bộ được phê duyệt |
| 0.0.0.0/0 | Theo thiết kế egress riêng | Không tự mặc định rằng mọi đích phải qua Internet |

**Route table cho subnet của Payments API:**

| Đích | Next hop | Ý nghĩa |
|---|---|---|
| 10.20.0.0/16 | Local | Kết nối trong Payments-prod |
| 10.10.0.0/16 | Transit attachment | Đường trả về Booking |
| 10.30.0.0/16 | Transit attachment | Dịch vụ bảo mật/quan sát cần thiết |

**Quy tắc định tuyến logic tại transit hub (chỉ là minh họa):**

| Nguồn ingress | Đích | Egress | Có cho phép? |
|---|---|---|---|
| Booking-prod | 10.20.0.0/16 | Attachment Payments-prod | Có |
| Payments-prod | 10.10.0.0/16 | Attachment Booking-prod | Có |
| Booking-prod | 10.30.0.0/16 | Attachment Shared-services | Có theo yêu cầu |
| Non-production | 10.20.0.0/16 | Không cấp tuyến, hoặc áp cơ chế chặn hỗ trợ | Không |
| On-premises | 10.20.0.0/16 | Theo chính sách mạng hybrid | Chỉ những luồng được phê duyệt |

Đây là **mô hình logic** cho việc phân đoạn. Trong AWS Transit Gateway, thiết kế sẽ dùng **association**, **route propagation**, static route và có thể blackhole route theo tính năng dịch vụ; việc ingress từ attachment nào được tra cứu qua bảng nào phụ thuộc association của attachment. Ở Azure/Google Cloud, phải dịch logic này thành route table, hub connection, segment hoặc chính sách phù hợp, chứ không sao chép cú pháp AWS.

### 7.2. Đường đi của một request HTTPS

~~~mermaid
sequenceDiagram
    participant B as Booking API 10.10.5.10
    participant BR as Route của Booking subnet
    participant T as Transit hub
    participant PR as Route của Payments subnet
    participant P as Payments API 10.20.7.20

    B->>BR: TCP SYN tới 10.20.7.20:443
    BR->>T: Next hop cho 10.20.0.0/16
    T->>PR: Định tuyến tới attachment Payments
    PR->>P: Kiểm tra policy và giao gói
    P-->>PR: TCP SYN-ACK tới 10.10.5.10
    PR-->>T: Route về 10.10.0.0/16
    T-->>BR: Định tuyến tới attachment Booking
    BR-->>B: Trả lời TCP
~~~

Sơ đồ rút gọn biểu diễn đường đi logic; route table không nhất thiết là một thiết bị vật lý riêng. Trong thực tế:

1. Booking phân giải tên private của Payments ra đúng địa chỉ.
2. Hệ điều hành gửi packet tới gateway mặc định của subnet; cơ chế route cloud chuyển tới transit attachment dựa trên prefix.
3. Transit sử dụng route/segment đúng cho nguồn ingress để chuyển tới Payments.
4. Các lớp security group, firewall, network ACL hoặc policy thích hợp kiểm tra lưu lượng theo khả năng của nền tảng.
5. Payments trả lời qua route ngược, qua các thiết bị kiểm tra được yêu cầu.
6. Sau khi thiết lập kết nối và TLS, **xác thực và phân quyền ứng dụng** vẫn quyết định Booking được gọi thao tác thanh toán nào.

**Lỗi thường gặp:** Đội Booking thêm route 10.20.0.0/16 và mở port 443 nhưng quên route 10.10.0.0/16 ở phía Payments, hoặc hub không có route cho egress tương ứng. Kết quả: request timeout, dù cấu hình peering/attachment hiển thị trạng thái hoạt động.

### 7.3. Kiểm tra hướng lưu lượng ngoài nghiệp vụ

Đường Booking → Payments không phải luồng duy nhất:

- **DNS:** Booking dùng resolver nào? Private DNS zone có được liên kết/forward đúng sang mạng khác không?
- **Observability:** Log/trace có gửi tới Shared-services không, và nếu dịch vụ này ngừng thì đường thanh toán có bị chặn không?
- **Khóa và secret:** Các endpoint quản lý secret/kms có phải đi qua hub hay dùng private endpoint tại từng mạng?
- **Callback/webhook:** Nếu Payments cần gọi ngược, đó là một luồng ứng dụng mới cần được định tuyến, xác thực và xét quyền riêng.
- **Bảo trì:** Đường cập nhật package/image, đồng bộ thời gian, kiểm tra sức khỏe hoặc truy cập nền tảng managed service có thể cần những endpoint khác.

Vì vậy, thiết kế chỉ vẽ một mũi tên “Booking ↔ Payments” cần được bổ sung **ma trận luồng** thể hiện nguồn, đích, port/giao thức, chủ sở hữu, mục đích và cách kiểm chứng.

## 8. Kết nối hybrid, BGP và route propagation

Khi cloud phải trao đổi với mạng nội bộ hoặc một nhà cung cấp mạng khác, kiến trúc thường dùng:

- **Site-to-site VPN:** Tạo đường hầm được mã hóa trên hạ tầng mạng phù hợp. Khả dụng và thông lượng phụ thuộc dịch vụ, thiết bị, kết nối Internet và cấu hình HA.
- **Kết nối chuyên dụng:** Ví dụ AWS Direct Connect, Azure ExpressRoute hoặc Google Cloud Interconnect, dùng mô hình kết nối riêng theo điều kiện của nhà cung cấp. Kết nối chuyên dụng không tự đồng nghĩa lưu lượng đã mã hóa đầu-cuối; phải thiết kế bảo mật theo yêu cầu.
- **BGP (Border Gateway Protocol):** Trao đổi thông tin tuyến giữa các hệ thống định tuyến, phù hợp kịch bản học prefix động, failover nhiều đường hoặc kết nối nhiều miền mạng.

### Route tĩnh và route động

| Tiêu chí | Route tĩnh | Route học động/BGP |
|---|---|---|
| Cách cập nhật | Người quản trị hoặc IaC khai báo | Router/gateway quảng bá, học và rút tuyến theo phiên và chính sách |
| Dễ hiểu ban đầu | Tốt với ít prefix cố định | Cần hiểu peer, ASN, prefix filter và chính sách định tuyến |
| Phản ứng khi thay đổi mạng | Phải cập nhật cấu hình | Có thể tự hội tụ nếu thiết kế dịch vụ và đường dự phòng hỗ trợ |
| Rủi ro | Route quên cập nhật, sai next hop | Quảng bá nhầm prefix, học tuyến quá rộng, thay đổi ưu tiên khó phát hiện |
| Phạm vi dùng | Kết nối đơn giản, đường mặc định hoặc route đặc thù | Hybrid nhiều mạng, nhiều đường và cần trao đổi route ở quy mô lớn |

**BGP không tự cấp quyền truy cập.** BGP giúp quảng bá và lựa chọn đường đi giữa những neighbor phù hợp; firewall, chính sách phân đoạn, IAM và cơ chế truy cập ứng dụng vẫn quyết định luồng nào được phép. Route propagation cũng không có nghĩa mọi route đều nên được đưa vào mọi segment. Các prefix cần được **lọc, tổng hợp và giới hạn theo nhu cầu kết nối**.

### Ví dụ có hai đường hybrid

On-premises có mạng 172.16.0.0/16, kết nối tới cloud bằng hai đường (ví dụ primary là dedicated connection, backup là VPN). Muốn failover:

1. Xác định route nào được quảng bá qua mỗi đường và cách ưu tiên theo cơ chế thực tế.
2. Xác minh route trả về từ cloud đến on-premises.
3. Theo dõi trạng thái BGP peer/tunnel và điều kiện rút tuyến khi đường hỏng.
4. Kiểm tra thời gian hội tụ và tác động tới phiên TCP; **chuyển tuyến thành công không bảo đảm mọi kết nối đang mở được duy trì**.
5. Thử cả lỗi đường một chiều, lỗi gateway, sai chính sách và tình huống phục hồi đường chính.

Không nên đặt giả định “BGP luôn hội tụ trong vài giây” nếu chưa kiểm tra cấu hình, timers, nhà cung cấp và điều kiện mạng. Mục tiêu phục hồi cần dựa trên phép đo.

## 9. Routing và các lớp bảo mật: bảo vệ đường kết nối

Một hệ thống nhiều mạng thường cần **phân đoạn theo mức độ tin cậy**, nhất là giữa prod, non-prod và môi trường chứa dữ liệu thanh toán.

### 9.1. Phân lớp kiểm soát

| Lớp | Câu hỏi kiểm soát | Ví dụ |
|---|---|---|
| **Routing** | Có đường tới dải đích không? | Không quảng bá route Non-production → Payments-prod |
| **Network firewall / security group** | Nguồn nào được giao tiếp tới đích và port nào? | Chỉ Booking API gọi HTTPS tới Payments API |
| **DNS** | Tên dịch vụ có phân giải tới đúng endpoint không? | payments.internal trỏ vào IP private |
| **TLS / danh tính dịch vụ** | Hai đầu có xác minh danh tính và bảo vệ dữ liệu trên đường truyền không? | mTLS hoặc TLS và workload identity tùy yêu cầu |
| **Phân quyền ứng dụng** | Dịch vụ đã xác thực được thực hiện thao tác nào? | Booking được tạo yêu cầu thanh toán, không được đọc toàn bộ dữ liệu |
| **Giám sát / kiểm toán** | Có phát hiện đường đi bất thường, truy cập sai và thay đổi policy không? | Network flow logs, firewall logs, audit log và cảnh báo |

Không nên dùng định tuyến như cơ chế bảo mật duy nhất: router chủ yếu quyết định đường đi, còn việc ngăn lưu lượng trái phép cần các lớp chính sách rõ ràng. Ngược lại, việc mở firewall mà không có route hai chiều cũng không làm kết nối thành công.

### 9.2. Centralized inspection và rủi ro định tuyến bất đối xứng

Một số tổ chức buộc các luồng xuyên mạng đi qua **firewall hoặc NVA trung tâm** để thực thi chính sách, ghi log hoặc phát hiện tấn công.

~~~mermaid
flowchart LR
    A["Booking-prod"] --> HUB1["Transit ingress"]
    HUB1 --> FW["Central firewall / inspection"]
    FW --> HUB2["Transit egress"]
    HUB2 --> B["Payments-prod"]
    B -. "Đường trả về cũng cần qua inspection phù hợp" .-> FW
~~~

Với **stateful inspection**, đường đi và về thường phải đi qua cùng đường trạng thái hoặc qua cơ chế chia sẻ trạng thái được thiết kế cho HA. Nếu đường đi qua firewall A nhưng trả lời đi thẳng hoặc qua firewall B không chia sẻ trạng thái, kết nối có thể thất bại. Các dịch vụ như appliance mode, route symmetry support hay cơ chế HA khác phụ thuộc sản phẩm, vì vậy cần kiểm tra tài liệu và kiểm thử failover.

Các quyết định bổ sung:

- Firewall đặt ở **mạng trung tâm** hay mỗi spoke, và ai quản lý rule?
- Có yêu cầu **east-west inspection** (giữa các mạng) hay chỉ **north-south** (ra/vào Internet hoặc on-premises)?
- Có phải bắt buộc cả DNS, proxy, endpoint managed service hoặc lưu lượng xuyên Region đi qua inspection không?
- Nếu firewall/hub lỗi, hệ thống ưu tiên **fail-closed** hay có cơ chế đường dự phòng? Quy tắc phụ thuộc phân loại dữ liệu.
- Chi phí và độ trễ mỗi hop có vượt ngân sách hoặc SLO của nghiệp vụ không?

### 9.3. DNS và endpoint riêng

Route chỉ dựa trên địa chỉ IP; ứng dụng thường gọi **tên miền**. Khi nối nhiều mạng, cần kiểm tra private DNS zone, resolver inbound/outbound, DNS forwarding, tên miền trùng và phạm vi hiển thị record. Một private endpoint cho dịch vụ managed không tự có nghĩa DNS trên tất cả spoke biết sử dụng địa chỉ đó.

Nhiều sự cố “không tới được dịch vụ” thực ra là **DNS trả về địa chỉ public trong khi mạng chỉ cho phép đường private**, hoặc trả IP cũ sau khi endpoint thay đổi. Nên kiểm tra kết quả phân giải tên từ **đúng mạng nguồn** trước khi phân tích route.

## 10. Các lỗi định tuyến thường gặp và cách điều tra

Khi kết nối thất bại, đừng thay đổi đồng loạt nhiều bảng route. Dựa trên triệu chứng để kiểm tra từng lớp.

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
|---|---|---|
| Peering active nhưng không kết nối TCP | Thiếu route một chiều, firewall, sai subnet/port | Kiểm tra route nguồn/đích, chính sách hai phía, flow logs |
| A↔B và B↔C hoạt động nhưng A↔C không | Giả định peering transitive | Xác minh mô hình transit hoặc peering A–C được hỗ trợ |
| Chỉ một subnet không kết nối được | Subnet dùng bảng route hoặc chính sách khác | Xem route table/subnet association và security rule chính xác |
| Một chiều đến được, chiều trả lời thất bại | Thiếu route trả về, asymmetric routing, NAT không phù hợp | Truy vết hai chiều, trạng thái firewall, các bước SNAT/DNAT |
| Kết nối bằng IP được nhưng tên miền lỗi | DNS zone, resolver, forwarding hoặc cache sai | Truy vấn DNS từ chính workload nguồn và so với endpoint |
| Lỗi sau khi thêm mạng mới | CIDR overlapping, route cụ thể hơn, thay đổi propagation | Rà toàn bộ bảng prefix, route selection và chính sách quảng bá |
| Kết nối lỗi khi chuyển đường hybrid | BGP route chưa hội tụ, đường dự phòng thiếu tuyến, firewall state | Xem BGP peer/advertised-learned routes và thử failover |
| Chỉ lỗi với payload lớn | MTU/PMTU hoặc gói phân mảnh bị chặn | Kiểm tra Path MTU, MSS và khả năng truyền qua tunnel/appliance |
| Ping không trả lời nhưng HTTPS hoạt động | ICMP bị chặn hoặc dịch vụ không trả ICMP | Kiểm tra đúng giao thức ứng dụng, không kết luận từ ping đơn lẻ |
| Kết nối chậm bất thường | Route vòng qua hub/Region, inspection, NAT hoặc saturation | Đo latency từng chặng theo công cụ phù hợp và các metric thiết bị |

### Quy trình debug theo một luồng cụ thể

Ví dụ Booking (10.10.5.10) gọi Payments (10.20.7.20:443):

1. **Ghi rõ lưu lượng:** Source IP/subnet, destination IP/FQDN, protocol, port, thời điểm lỗi và hướng khởi tạo.
2. **Kiểm tra DNS:** Tên Payments có trả đúng IP private từ Booking không? Có TTL/forwarding/zone override?
3. **Kiểm tra routing phía nguồn:** Route cụ thể nhất cho 10.20.7.20 đi đâu? Bảng route có thực sự áp dụng cho subnet của Booking không?
4. **Kiểm tra thiết bị trung gian:** Peering/attachment/tunnel có khỏe không, transit segment có route đích không, có chỗ nào rơi vào blackhole hoặc route sai?
5. **Kiểm tra routing phía đích:** Payments có route về 10.10.5.10 và đường về có nhất quán với inspection không?
6. **Kiểm tra policy:** Security group, firewall, network ACL, rule ở NVA hoặc endpoint. Với stateful/stateLESS rule, xem cả hướng trả lời theo tính chất thực tế.
7. **Kiểm tra ứng dụng:** Dịch vụ có lắng nghe đúng port, TLS bắt tay được, chứng chỉ hợp lệ, auth/authorization trả lỗi gì?
8. **Dùng quan sát thực tế:** Flow log, firewall log, metric transit/tunnel, packet capture khi có quyền và công cụ phân tích đường đi của nhà cung cấp.

Ví dụ các công cụ kiểm tra mạng theo cloud có thể gồm **AWS VPC Reachability Analyzer**, **Azure Network Watcher** và **Google Cloud Connectivity Tests**. Khả năng mô phỏng hoặc xác minh tuyến, các loại tài nguyên hỗ trợ và mức độ bao quát khác nhau; một kết quả “reachable” ở tầng mạng không bảo đảm ứng dụng, chứng chỉ hoặc quy tắc nghiệp vụ hoạt động.

## 11. Độ tin cậy, khả năng mở rộng, chi phí và vận hành của transit

### Độ tin cậy

Một hub trung tâm giúp chuẩn hóa kết nối nhưng cũng làm tăng **phạm vi ảnh hưởng của sai cấu hình**. Cần phân biệt:

- **Dịch vụ managed có dự phòng nội bộ:** Giảm công vận hành hạ tầng, nhưng không bảo vệ khỏi route/policy bị cấu hình sai hoặc kết nối nhầm segment.
- **Kết nối hybrid:** Cần nhiều đường, thiết bị và vị trí phù hợp với mục tiêu phục hồi; hai tunnel trên cùng một điểm lỗi vật lý có thể không đủ.
- **Mạng và ứng dụng:** Một hub khỏe nhưng database ở mạng đích lỗi thì chức năng vẫn gián đoạn; SLO phải xét chuỗi phụ thuộc.
- **Khả năng phục hồi:** Kiểm thử sự cố route, attachment, hub, firewall, DNS và đường chuyên dụng theo RTO/RPO hoặc chỉ tiêu khôi phục kết nối đã định.

**RTO** mô tả thời gian khôi phục tối đa và **RPO** mô tả lượng dữ liệu có thể mất khi khôi phục. RPO chủ yếu liên quan tới dữ liệu; không nên dùng RPO để đánh giá riêng một bảng định tuyến. Với mạng, cần các chỉ tiêu bổ sung như thời gian hội tụ, tỉ lệ thành công của kết nối, latency và packet loss.

### Hiệu năng và mở rộng

Trung chuyển có thể thêm hop hoặc đường vòng. Những giới hạn phải đánh giá gồm số attachment, số route, băng thông, packet per second, kết nối NVA, session table, quota VPN và lượng lưu lượng kiểm tra bảo mật. **Tăng số API instance không giúp ích nếu bottleneck nằm ở hub/firewall/đường hybrid**.

Tại giai đoạn thiết kế, cần ước tính lưu lượng **east-west** giữa các ứng dụng, lưu lượng truy cập dữ liệu, tải vào giờ cao điểm, dự phòng lúc một đường chết và lưu lượng sao lưu/đồng bộ. Với ứng dụng yêu cầu độ trễ thấp, kiểm thử từ đúng Region, AZ và đường kết nối dự kiến.

### Chi phí

Các nhóm chi phí thường cần đưa vào dự toán:

| Nhóm | Nguồn phát sinh | Gợi ý giảm lãng phí |
|---|---|---|
| **Phạm vi kết nối** | Phí peering, hub, attachment hoặc gateway tùy nhà cung cấp | Chỉ tạo kết nối thật sự cần; xem có thể nhóm luồng phù hợp |
| **Dữ liệu qua hub** | Phí xử lý hoặc truyền dữ liệu theo chiều, GB, thời gian | Đo lưu lượng east-west; tránh đường vòng không cần thiết |
| **Cross-region/cross-zone** | Phí và độ trễ khi đi qua ranh giới vị trí | Chọn vị trí dịch vụ theo nhu cầu, cân bằng với HA và tuân thủ |
| **Inspection** | Firewall managed, NVA compute, license, log | Chọn tập luồng cần inspection, right-size và đặt quota |
| **Hybrid** | Kết nối chuyên dụng/VPN, cổng, nhà mạng, thiết bị | Đo nhu cầu băng thông và mức dự phòng thay vì chọn theo trực giác |
| **DNS/NAT/logging** | Resolver endpoint, NAT gateway, truy vấn, log lưu giữ | Thiết kế DNS/private endpoint, chính sách lưu log theo nhu cầu |

Chi phí cụ thể thay đổi theo sản phẩm, Region và chiều dữ liệu; không thể tính bằng một con số chung cho mọi cloud. Một phương án peering có thể rẻ hơn khi chỉ hai mạng trao đổi; transit có thể giảm chi phí vận hành ở quy mô lớn nhưng thêm phí hub và xử lý dữ liệu. Quyết định phải dựa trên **mô hình lưu lượng và tổng chi phí**, gồm cả thời gian vận hành.

### Vận hành

Nên quản lý route/attachment/policy bằng **infrastructure as code (IaC)** hoặc quy trình thay đổi được review, kiểm tra trước và sau triển khai. Với hệ thống lớn, cần có:

- Người sở hữu từng mạng, CIDR, attachment, prefix và route/segment.
- Danh sách các luồng được phê duyệt với lý do nghiệp vụ và người chịu trách nhiệm.
- Nhật ký thay đổi chính sách mạng, route, BGP và cơ chế truy cập chéo.
- Dashboard sức khỏe đường kết nối, lỗi tunnel, BGP session, latency, packet loss, byte/GB và chi phí.
- Quy trình rollback route và bài kiểm tra định tuyến hai chiều sau thay đổi.
- Tài liệu mạng logic và sơ đồ triển khai được cập nhật cùng thay đổi kiến trúc.

## 12. Đánh giá theo Well-Architected

Mục đích của đánh giá là xác định được **chứng cứ** cho mỗi quyết định, không chỉ nhìn một sơ đồ có đủ hub, spoke và biểu tượng firewall.

| Khía cạnh | Câu hỏi review | Bằng chứng nên có |
|---|---|---|
| **Operational Excellence** | Ai quản lý route, tạo kết nối và xử lý thay đổi sai? | IaC, owner, change review, runbook, diễn tập rollback |
| **Security** | Non-prod có thể tới prod không? Firewall/IAM có bảo vệ các endpoint nhạy cảm? | Ma trận luồng, segment, kiểm tra truy cập bị từ chối, flow log |
| **Reliability** | Lỗi transit attachment, DNS, firewall hoặc đường hybrid ảnh hưởng đến ai? | Bản đồ phụ thuộc, thử failover, thời gian hội tụ, cảnh báo |
| **Performance Efficiency** | Hub có đủ throughput và độ trễ ở tải đỉnh? | Load test, network metrics, quota, kiểm thử tuyến xuyên Region |
| **Cost Optimization** | Lưu lượng giữa các mạng đi đâu và bị tính phí ở những điểm nào? | Dự toán lưu lượng, billing/cost allocation, lưu lượng theo attachment |
| **Sustainability** | Có tài nguyên mạng/NVA dư thừa hoặc log lưu quá lâu không? | Right-sizing, vòng đời logging, xóa attachment và route không dùng |

### Tiêu chí chấp nhận minh họa

Với hệ thống Booking–Payments, nhóm có thể thống nhất các mục tiêu đo được:

1. **Booking-prod → Payments-prod:** Kết nối HTTPS thành công khi có tuyến đúng, và chỉ các nguồn/port được phê duyệt mới được truy cập.
2. **Non-production → Payments-prod:** Không có đường truy cập được phê duyệt; kiểm thử kết nối trái phép phải bị chặn.
3. **Lỗi một đường hybrid:** Đường dự phòng khôi phục trong thời gian mục tiêu đã thống nhất, đo bằng thử nghiệm định kỳ.
4. **Giờ cao điểm:** P95 thời gian thiết lập kết nối và latency mạng không vượt ngưỡng do ứng dụng đặt ra ở mức tải thiết kế.
5. **Dữ liệu chi phí:** Có thể phân bổ chi phí transit/attachment và lưu lượng giữa các mạng theo owner hoặc nhóm sản phẩm.

Các ngưỡng định lượng cụ thể (ví dụ thời gian hội tụ hoặc số GB/tháng) phải lấy từ yêu cầu thực tế và khả năng của dịch vụ; không nên giả định giá trị mặc định chỉ dựa trên hình vẽ.

## 13. Quy trình lựa chọn peering hay transit

Một quy trình quyết định thực tế:

1. **Liệt kê mạng và người sở hữu:** VPC/VNet, account/subscription/project, CIDR, Region, môi trường, phân loại dữ liệu.
2. **Xây ma trận kết nối:** Mạng nguồn, mạng đích, giao thức/port, tải dự kiến, luồng trả về, chủ sở hữu và lý do nghiệp vụ.
3. **Lập kế hoạch địa chỉ và DNS:** Tránh overlapping CIDR; xác định private DNS, resolver, endpoint và quyền quản lý.
4. **Chọn topology:** Dùng peering khi ít cặp; xem transit khi nhiều mạng cần kết nối, quản trị hoặc hybrid trung tâm; đánh giá phương án kết hợp nếu có yêu cầu đặc biệt.
5. **Thiết kế route hai chiều:** Source subnet, transit/hub segment, destination subnet và đường phản hồi; kiểm tra không có route không mong muốn.
6. **Thiết kế phân đoạn và bảo mật:** Route filter, firewall, inspection, IAM, TLS và chính sách cho các luồng xuyên ranh giới.
7. **Đánh giá giới hạn và chi phí:** Quota, attachments, băng thông, độ trễ, data processing, cross-region, dịch vụ managed và vận hành.
8. **Kiểm chứng:** Chạy bài test kết nối được phép/bị cấm, route failure, BGP failover, DNS, tải đỉnh và chi phí thực tế.
9. **Ghi lại quyết định:** Sơ đồ topology, ma trận luồng, route table/segment, ADR, giả định và điều kiện đánh giá lại.

Ví dụ một **Architecture Decision Record (ADR)** ngắn:

> **Bối cảnh:** Doanh nghiệp có hơn một chục mạng cho sản xuất, kiểm thử và dịch vụ chung; thường xuyên tạo mạng mới; cần kết nối hybrid và giới hạn luồng từ non-prod tới prod.
>
> **Phương án:** (A) Mở rộng mesh peering; (B) thiết lập transit hub với route/segment và chính sách được quản trị tập trung; (C) kết hợp transit cho kết nối chung và peering trực tiếp cho những cặp ngoại lệ.
>
> **Quyết định minh họa:** Chọn B làm topology mặc định, chỉ cho phép ngoại lệ có ADR và bài kiểm tra tuyến.
>
> **Lý do:** Giảm cấu hình theo từng cặp, chuẩn hóa onboarding mạng và kết nối hybrid, hỗ trợ phân đoạn tập trung.
>
> **Đánh đổi:** Phụ thuộc vào hub, chi phí attachment/data processing và yêu cầu quản lý route/inspection, dự phòng.
>
> **Kiểm chứng:** Thử kết nối hai chiều được phép, chặn non-prod → prod, đo tải/chi phí, mô phỏng lỗi đường hybrid và cập nhật runbook.

ADR ghi lại **lý do và hệ quả**; sơ đồ mạng và bảng route ghi lại **cấu trúc và đường đi**. Cần duy trì đồng bộ các tài liệu đó khi thêm mạng, đổi CIDR, chuyển Region hoặc thay nhà cung cấp.

## 14. Bài tập thực hành: phát hiện lỗi trong thiết kế đa mạng

Một công ty có bốn mạng:

| Mạng | CIDR | Nhu cầu |
|---|---|---|
| A — Booking-prod | 10.10.0.0/16 | Gọi API thanh toán B và gửi log tới C |
| B — Payments-prod | 10.20.0.0/16 | Nhận request từ A, trả lời về A |
| C — Shared-services | 10.30.0.0/16 | Cung cấp logging và DNS cho các mạng được phê duyệt |
| D — Non-production | 10.40.0.0/16 | Chỉ thử nghiệm, không được truy cập Payments-prod |

Hiện nhóm đã tạo **peering A–C, B–C và D–C**. Booking không gọi được Payments. Một thành viên đề nghị “cho traffic từ A đi vào C rồi tự chạy sang B vì cả hai đã peering với C”. Một người khác đề nghị thêm route 10.20.0.0/16 vào A mà không thay đổi cấu hình nào ở B.

### Yêu cầu

1. Giải thích vì sao thiết kế peering hiện tại không mặc nhiên cho A gọi B qua C.
2. Đề xuất hai phương án: kết nối A–B trực tiếp, hoặc dùng một hub/transit hợp lệ. Khi nào chọn mỗi phương án?
3. Với phương án transit, mô tả route cần có ở subnet A, hub, subnet B và đường trả về; nêu rõ cách chặn D → B.
4. Xác định cách kiểm tra DNS cho Payment API và luồng HTTPS trên port 443.
5. Nêu ít nhất ba rủi ro khi dùng một firewall trung tâm để kiểm tra A ↔ B.
6. Lập bảng test để kiểm tra các luồng A → B, A → C, D → B và khi một kết nối hybrid dự phòng bị lỗi.

### Gợi ý lời giải

**Phần 1 — Peering:** A peering C và B peering C chỉ thể hiện hai kết nối A–C, B–C. Theo mô hình peering không chuyển tiếp, C không phải router transit mặc định. Vì thế A không tự có đường tới B qua C.

**Phần 2 — Chọn kết nối:** Nếu chỉ A và B cần trao đổi trực tiếp với số ít mạng, thêm peering A–B và route/policy hai chiều có thể đơn giản. Nếu có nhiều mạng, nhu cầu hybrid và quản trị chung tăng, chọn transit hub với cơ chế định tuyến và phân đoạn phù hợp sẽ dễ mở rộng hơn. Quyết định còn phụ thuộc tính năng/giá dịch vụ của cloud cụ thể.

**Phần 3 — Route và phân đoạn:** A có route 10.20.0.0/16 tới transit; hub có route cho A ingress đi đến attachment B; B có route 10.10.0.0/16 tới transit; hub có route cho B ingress trở lại attachment A. D không được học hoặc có route tới B theo chính sách phù hợp, đồng thời firewall/policy chặn đường truy cập không mong muốn. Cần kiểm tra các route cụ thể hơn và default route có thể tạo đường vòng ngoài dự kiến.

**Phần 4 — DNS và HTTPS:** Từ A, phân giải FQDN của Payment API, xác nhận IP private thuộc B, thử kết nối TCP 443, TLS và xác thực ứng dụng. Sau đó dùng logs/metrics kiểm tra lưu lượng có đi đúng tuyến, đúng firewall và có trả lời về A.

**Phần 5 — Firewall tập trung:** Có thể là điểm phụ thuộc chung, tạo độ trễ/chi phí và gây mất phiên nếu định tuyến bất đối xứng hoặc chuyển firewall không đồng bộ trạng thái. Cần sizing, HA, route symmetry, quản trị rule và diễn tập.

**Phần 6 — Kiểm thử:** Ghi rõ từng luồng được phép/bị cấm, phương thức kiểm tra và bằng chứng, ví dụ:

| Test | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| A gọi B:443 | Kết nối được, API kiểm tra quyền đúng | Connection/TLS, application response, flow logs |
| B trả lời A | Gói về đúng tuyến, không bị firewall loại | Route table, flow log hai chiều |
| A gửi log C | Giao tiếp với endpoint logging đúng quyền | Log nhận được, network logs |
| D gọi B:443 | Bị chặn theo chính sách, không tạo đường truy cập trái phép | Policy/route review và kiểm tra kết nối bị từ chối |
| Ngắt một đường hybrid | Các luồng được thiết kế dự phòng chuyển tuyến trong mục tiêu | BGP/tunnel metrics, latency và kết quả kiểm tra ứng dụng |

**Bài học rút ra:** Khi hệ thống có nhiều mạng, hãy thiết kế **đường đi, đường về, giới hạn truyền tuyến và ranh giới tin cậy** như một phần của kiến trúc ứng dụng. Peering hữu ích cho ít cặp kết nối; transit giúp quản lý kết nối ở quy mô lớn; nhưng cả hai đều cần CIDR hợp lý, cấu hình route chính xác, kiểm soát truy cập, quan sát, đánh giá chi phí và thử sự cố để biến sơ đồ mạng thành hệ thống cloud đáng tin cậy.
