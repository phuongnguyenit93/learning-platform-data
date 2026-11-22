# Reachability Analyzer và chẩn đoán lỗi định tuyến trong AWS

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **Amazon VPC Reachability Analyzer** đánh giá khả năng kết nối mạng dựa trên cấu hình như thế nào và giới hạn của việc phân tích đó.
- Đọc được **network insights path**, **network insights analysis**, kết luận `NetworkPathFound`, các thành phần trên đường đi và những lời giải thích về lỗi.
- Tìm đúng tuyến đường, security group, network ACL, gateway hoặc điểm kết nối khi một ứng dụng không thể giao tiếp giữa các subnet, VPC hoặc mạng doanh nghiệp.
- Phân biệt vấn đề **định tuyến và lọc gói** với DNS, TLS, IAM, ứng dụng ngừng hoạt động hoặc database không nhận kết nối.
- Thực hiện quy trình điều tra bằng AWS Console, AWS CLI, VPC Flow Logs và kiểm thử từ workload, đồng thời sửa lỗi theo nguyên tắc ít thay đổi nhất.
- Đề xuất cách giám sát, kiểm chứng khả năng phục hồi và quản lý chi phí cho mạng AWS nhiều Availability Zone (AZ), nhiều tài khoản hoặc hybrid.

**Bối cảnh:** Bài thuộc chương **Kết nối mạng nâng cao**, trong module **CLOUD_PROVIDERS_AWS**. AWS cung cấp nhiều lớp hạ tầng mạng: Region/AZ, VPC/subnet, route table, Internet/NAT gateway, VPC peering, Transit Gateway, endpoints và kết nối on-premises. Khi ứng dụng chạy trên EC2, ECS, EKS hay Lambda cần truy cập RDS, S3, DynamoDB hoặc dịch vụ tích hợp, chỉ một route hoặc security group sai cũng có thể làm gián đoạn hệ thống. Reachability Analyzer giúp khoanh vùng vấn đề dựa trên **cấu hình mạng AWS** trước khi cần thử và đo lưu lượng thực.

## 1. Phân biệt ba câu hỏi khi điều tra mất kết nối

Một thông báo `connection timed out` có thể đến từ nhiều nguyên nhân. Hãy tách thành ba câu hỏi:

1. **Tên miền có phân giải thành đích hợp lệ không?** DNS client lấy IP nào, địa chỉ là private/public, IPv4/IPv6 và có đúng endpoint hiện tại không?
2. **Cấu hình mạng có cho gói tin đi từ nguồn đến đích không?** Route table có hướng phù hợp không, gateway có kết nối không, security group và NACL có cho phép lưu lượng không? Đây là phần **Reachability Analyzer** giúp phân tích.
3. **Đích có thực sự phục vụ yêu cầu không?** TCP listener có mở, firewall hệ điều hành có chặn, TLS/HTTP có đúng, IAM/application authentication có cho phép không?

~~~mermaid
flowchart TD
    A[Ứng dụng báo lỗi kết nối] --> B{Tên DNS có phân giải?}
    B -->|Không| C[Kiểm tra DNS / Resolver / private hosted zone]
    B -->|Có| D{Mạng AWS cho phép đường đi?}
    D -->|Không| E[Route table / gateway / SG / NACL / endpoint]
    D -->|Có theo cấu hình| F[Kiểm thử thực: TCP / TLS / ứng dụng]
    F --> G[Listener / OS firewall / IAM / DB / app / timeout]
~~~

Ví dụ EC2 trong subnet private truy cập RDS qua hostname:

- Nếu DNS trả sai địa chỉ: xử lý phân giải tên hoặc endpoint.
- Nếu thiếu route trên đường đi hoặc security group chặn cổng TCP 5432: xử lý mạng.
- Nếu đường mạng được cho phép nhưng PostgreSQL từ chối đăng nhập: xem database authentication và người dùng; thêm route hay mở cổng sẽ không sửa được lỗi này.

**Nguyên tắc:** “DNS trả lời”, “Reachability Analyzer tìm thấy đường đi” và “yêu cầu của ứng dụng thành công” là **ba kết luận khác nhau**.

## 2. Reachability Analyzer là gì?

**Amazon VPC Reachability Analyzer** là khả năng phân tích cấu hình kết nối của AWS. Bạn khai báo **nguồn**, **đích** và đặc tính lưu lượng như protocol/port; dịch vụ phân tích các thành phần mạng được hỗ trợ để xác định liệu có một đường đi hợp lệ theo cấu hình hay không. Kết quả hỗ trợ xác định lớp nào làm lưu lượng bị chặn.

Reachability Analyzer **không gửi các gói tin thử từ ứng dụng sang đích**. Đây là **phân tích tĩnh dựa trên cấu hình**, nên có thể hữu ích ngay cả khi endpoint chưa chạy ứng dụng hoặc chưa có gói tin thực, miễn tài nguyên và cấu hình được hỗ trợ để phân tích.

### Thuật ngữ cần biết

| Khái niệm | Ý nghĩa | Điều cần ghi nhớ |
| --- | --- | --- |
| **Network insights path** | Khai báo giả định nguồn → đích, protocol, port và tham số đường đi | Có thể lưu lại để chạy phân tích nhiều lần |
| **Network insights analysis** | Một lần chạy Reachability Analyzer cho path đã tạo | Phản ánh cấu hình tại lần phân tích |
| **Source / Destination** | Tài nguyên hoặc endpoint mà công cụ hỗ trợ, ví dụ EC2 instance/network interface | Loại tài nguyên được hỗ trợ và khả năng chọn IP/port tùy ngữ cảnh |
| **NetworkPathFound** | Kết luận có tìm thấy đường đi hợp lệ theo mô hình cấu hình hay không | Không chứng minh ứng dụng hoạt động |
| **Forward path components** | Các tài nguyên/hops được phân tích trên đường đi từ nguồn đến đích | Hữu ích để hiểu route và thành phần trung gian |
| **Return path components** | Thành phần đường về nếu loại phân tích hỗ trợ và trả thông tin | Không được mặc định luôn có ở mọi phân tích |
| **Explanations** | Giải thích lý do không thể đi qua đường đã yêu cầu hoặc thông tin liên quan | Cần xem resource ID và chi tiết để sửa đúng nơi |
| **Reachability** | Khả năng đi tới đích theo quy tắc mạng được mô hình hóa | Không xác nhận DNS, TLS, IAM hoặc tiến trình đang nghe cổng |

### Công cụ có thể làm và không thể làm

| Reachability Analyzer hữu ích để | Không nên dùng như bằng chứng rằng |
| --- | --- |
| Kiểm tra cấu hình đường đi từ một nguồn đến một đích được hỗ trợ | Gói tin đã đi qua mạng thực tế |
| Phát hiện route table hoặc bộ lọc mạng làm chặn đường đi | Server đang lắng nghe trên port và phản hồi khỏe mạnh |
| Đọc các thành phần mạng trung gian đã được mô hình hóa | Tên DNS luôn trỏ đúng đích mà ứng dụng thực sự dùng |
| So sánh kết quả trước/sau một thay đổi mạng | TLS handshake, IAM, quyền DB hoặc logic ứng dụng đã đúng |
| Hỗ trợ kiểm tra một số đường đi qua VPC peering, Transit Gateway, gateway và endpoint theo phạm vi hỗ trợ | Mọi thiết bị bên ngoài AWS hoặc mọi appliance/đường hầm đều được mô phỏng đầy đủ |

Khả năng hỗ trợ từng loại resource, giao thức và kiến trúc đa tài khoản có thể thay đổi. Trước khi dựa vào kết quả cho thiết kế đặc biệt như GWLB, firewall appliance, Direct Connect hoặc đường Internet, hãy xem **supported resources / limitations** ở tài liệu AWS hiện hành. Nếu một đoạn đường không được công cụ mô hình hóa, cần bổ sung kiểm thử thực và log ở các thiết bị liên quan.

### Vì sao cần khai báo đúng port và hướng?

Đường từ **EC2-A → EC2-B TCP/443** có thể hợp lệ, trong khi đường từ **EC2-A → EC2-B TCP/5432** không hợp lệ do security group. Hướng **A → B** và **B → A** cũng là hai yêu cầu khác nhau khi xét lưu lượng chủ động kết nối. Vì vậy:

- Chọn **nguồn chính xác** (instance/ENI/đối tượng được hỗ trợ), **đích chính xác**, protocol và **destination port**.
- Với địa chỉ IP đích thay đổi sau failover, kiểm tra thực thể/địa chỉ đúng tại thời điểm điều tra.
- Chạy phân tích riêng cho các luồng ứng dụng quan trọng; không suy luận tất cả cổng đều mở chỉ vì một path đã có `NetworkPathFound=true`.

## 3. Mô hình định tuyến AWS cần thuộc trước khi xem kết quả

Một gói từ EC2-A đến EC2-B có thể phải qua các thành phần sau:

~~~mermaid
flowchart LR
    A[EC2-A / ENI] --> SG1[Security group nguồn]
    SG1 --> NA[Network ACL subnet A]
    NA --> RT[Route table subnet A]
    RT --> GW{Đích / next hop}
    GW --> NB[Network ACL subnet B]
    NB --> SG2[Security group đích]
    SG2 --> B[EC2-B / ENI]
~~~

Sơ đồ trên là **mô hình logic để điều tra**, không phải thứ tự xử lý gói chính xác của mọi thiết bị AWS. Trong trường hợp cùng VPC, route có thể đi qua `local`; qua peering, Transit Gateway, Internet Gateway, NAT Gateway hoặc endpoints, chuỗi thành phần sẽ khác.

### 3.1. CIDR, subnet và route table

**CIDR** xác định dải địa chỉ, ví dụ VPC `10.20.0.0/16`, subnet `10.20.1.0/24`. Mỗi subnet dùng **một route table được liên kết**, hoặc dùng **main route table** của VPC nếu chưa có liên kết rõ ràng.

Route table gồm **destination** và **target** (next hop). Ví dụ:

| Destination | Target | Cách hiểu |
| --- | --- | --- |
| `10.20.0.0/16` | `local` | Gói tới dải địa chỉ trong VPC theo tuyến nội bộ mặc định |
| `0.0.0.0/0` | `igw-...` | Tuyến IPv4 mặc định tới Internet Gateway khi được thiết kế hợp lệ |
| `0.0.0.0/0` | `nat-...` | Tuyến IPv4 mặc định ra NAT Gateway, thường cho subnet private |
| `10.30.0.0/16` | `pcx-...` | Tuyến tới VPC khác qua VPC peering |
| `10.40.0.0/16` | `tgw-...` | Tuyến tới mạng gắn Transit Gateway |
| `pl-...` | `vpce-...` | Tuyến theo prefix list tới gateway endpoint tương ứng, khi dùng dịch vụ hỗ trợ |

Với IPv6, tuyến và đích có dạng `::/0`, `ipv6 CIDR`; cần dùng target hỗ trợ IPv6 phù hợp, ví dụ Internet Gateway hoặc egress-only Internet Gateway tùy yêu cầu. Không thể lấy chính route `0.0.0.0/0` để suy ra IPv6 hoạt động.

**Longest-prefix match:** Về cơ bản, route đến dải **cụ thể nhất** phù hợp địa chỉ đích được ưu tiên. Tuy nhiên khi tồn tại route tĩnh, route được propagate hoặc prefix list chồng lấp có các quy tắc ưu tiên riêng của AWS; cần đọc route table thực và tài liệu cho trường hợp đó.

### 3.2. Security group và network ACL

| Thuộc tính | Security group (SG) | Network ACL (NACL) |
| --- | --- | --- |
| Gắn ở đâu | Elastic network interface / tài nguyên có ENI tương ứng | Subnet |
| Trạng thái | **Stateful** | **Stateless** |
| Quy tắc | Cho phép theo inbound/outbound; không có Deny rule thông thường | Allow/Deny theo rule number |
| Chiều phản hồi | Lưu lượng đáp lại kết nối đã được cho phép thường được tự động chấp nhận | Cần rule cho **cả chiều đi và chiều về** |
| Cách đối chiếu | Protocol, port, CIDR hoặc SG reference phù hợp | Protocol, port, CIDR, số thứ tự rule |
| Dễ nhầm | Source SG không phải IP cụ thể, và SG reference có điều kiện hỗ trợ | Quên ephemeral ports cho traffic trả về |

Ví dụ: EC2-A ở subnet `10.20.1.0/24` gọi EC2-B ở `10.20.2.0/24` qua TCP/443.

- SG của A cần **egress** cho kết nối tới B theo cấu hình.
- SG của B cần **ingress TCP/443** từ A hoặc SG nguồn khi kiểu tham chiếu được hỗ trợ.
- NACL subnet A và B phải cho phép đúng lưu lượng đi/về; do NACL không trạng thái, **ephemeral ports** của client cần được tính đến theo hệ điều hành/luồng.
- Route của hai subnet cần dẫn tới nhau; cùng VPC thường có local route nhưng route có thể đã được tùy chỉnh qua appliance theo một kiến trúc đặc biệt.

Đừng thêm `0.0.0.0/0` ở tất cả SG để “xử lý nhanh”. Một kết luận AccessDenied/blocking nên dẫn tới **rule tối thiểu theo luồng thực tế**, còn giới hạn quyền IAM/API và firewall hệ điều hành vẫn phải được xem riêng.

## 4. Những lỗi định tuyến phổ biến theo loại kết nối

### 4.1. Cùng VPC, khác subnet hoặc khác AZ

Trong VPC thông thường, route `local` cho phép subnet liên lạc theo CIDR VPC. Nhưng việc liên lạc còn chịu ràng buộc bởi SG/NACL, instance firewall và listener.

Các nguyên nhân hay gặp:

- SG đích chưa cho cổng TCP cần thiết hoặc egress SG nguồn quá chặt.
- NACL từ chối chiều đi hoặc traffic hồi đáp.
- Đích không ở IP/ENI dự kiến, ứng dụng không bind vào địa chỉ cần thiết.
- Route `local` đã được thay đổi trong kiến trúc chèn middlebox/inspection và appliance không chuyển tiếp đúng.
- Địa chỉ IP đã thay đổi do thay ENI, autoscaling hoặc failover.

### 4.2. Public subnet và Internet Gateway

Một EC2 được coi là “có public IPv4” vẫn có thể không nhận kết nối từ Internet nếu:

- Subnet chưa có route ra **Internet Gateway (IGW)** phù hợp;
- SG không cho phép ingress port đích;
- NACL hoặc firewall hệ điều hành chặn;
- Instance không có public IP/Elastic IP đúng vào thời điểm truy cập;
- Ứng dụng không lắng nghe hoặc tên DNS trỏ tới IP cũ.

Route `0.0.0.0/0 → igw-...` chỉ là một điều kiện mạng. Bản thân route không tự biến một private IP thành IP Internet có thể truy cập.

### 4.3. Private subnet và NAT Gateway

Private instance muốn **khởi tạo kết nối IPv4 ra Internet** thường có:

- Route `0.0.0.0/0 → NAT Gateway` ở route table subnet private;
- Public NAT Gateway trong public subnet phù hợp, có Elastic IP và route ra IGW;
- SG/NACL và phương án đường về hợp lệ.

**NAT Gateway không phải cổng để Internet chủ động gọi vào instance private.** Với dữ liệu AWS, có thể chọn **VPC endpoint** thay cho đường ra Internet nếu dịch vụ và trường hợp sử dụng hỗ trợ; ví dụ gateway endpoint cho S3/DynamoDB hoặc interface endpoint cho nhiều dịch vụ AWS.

### 4.4. VPC peering

Peering nối **hai VPC** theo cơ chế được hỗ trợ, nhưng không tự tạo route hoàn chỉnh. Cần:

1. Peering connection ở trạng thái `active`.
2. Route **từ subnet nguồn** đến CIDR đích qua peering.
3. Route **chiều ngược** từ subnet đích về CIDR nguồn.
4. SG/NACL ở hai VPC cho phép luồng.
5. Dải CIDR không xung đột theo yêu cầu VPC peering.

**Peering không định tuyến transit:** VPC A peering B và B peering C không làm A tự động đi đến C qua B. Cần mô hình kết nối phù hợp khác nếu cần hub nhiều mạng.

### 4.5. Transit Gateway (TGW)

TGW hoạt động như hub nối nhiều VPC và mạng được hỗ trợ. Lỗi có thể phát sinh tại **hai lớp route**:

- Route table của **subnet VPC** chỉ đến TGW cho CIDR đích.
- **TGW route table** có association/propagation hoặc static route cho attachment đích.
- VPC ở đầu bên kia cũng có route phản hồi từ subnet về TGW khi cần.

Một attachment hiển thị available không chứng minh rằng route table của TGW chọn đúng attachment. Với nhiều TGW route tables, cần kiểm tra **attachment nào associate với bảng nào** và route nào đang được propagate. Blackhole route, CIDR chồng lấp hoặc thiếu đường về đều có thể làm hỏng luồng.

### 4.6. Kết nối hybrid: VPN/Direct Connect

VPC đi tới on-premises còn cần:

- VPC/TGW route tới mạng nội bộ;
- cấu hình gateway/attachment/VPN hoặc Direct Connect phù hợp;
- route/BGP và chính sách firewall phía on-premises cho **cả hai chiều**;
- DNS hybrid nếu gọi bằng hostname;
- kiểm soát MTU/MSS và thiết bị mạng ngoài AWS khi triệu chứng là gói nhỏ chạy, gói lớn lỗi.

Reachability Analyzer có thể đánh giá các phần AWS **được hỗ trợ**, nhưng **không kiểm chứng đầy đủ router/firewall tại trung tâm dữ liệu**. Sau khi xác định đoạn AWS phù hợp, cần thử lưu lượng thực và đối chiếu log network appliance phía ngoài.

## 5. Quy trình dùng Reachability Analyzer trên AWS Console

> **Chuẩn bị:** Có account và Region được cấp quyền; biết chính xác VPC, source, destination, giao thức và cổng dịch vụ. Bài thực hành nên sử dụng EC2/ENI lab; Reachability Analyzer có thể phát sinh phí theo lượt phân tích. Không chỉnh sửa hạ tầng sản xuất chỉ để thử nếu chưa đánh giá tác động.

### Bước 1 — Chọn luồng cần kiểm tra

Ví dụ:

- **Nguồn:** EC2 `app-a`, private IP `10.20.1.10`, ở AZ A.
- **Đích:** EC2 `api-b`, private IP `10.20.2.20`, ở AZ B.
- **Luồng:** TCP cổng **8080**.
- **Mong đợi:** A được gọi API ở B, nhưng B không nhất thiết được khởi tạo một kết nối mới tới A.

Đặt rõ luồng trước khi mở Console. Nếu ứng dụng dùng DNS, xác nhận DNS trỏ đến tài nguyên nào ở thời điểm lỗi; tránh phân tích đúng một instance nhưng ứng dụng thực tế gọi một load balancer khác.

### Bước 2 — Tạo Network Insights Path

Trong **VPC Console → Reachability Analyzer → Create and analyze path** (tên màn hình có thể thay đổi theo giao diện):

1. Chọn **source** từ loại tài nguyên được hỗ trợ; ví dụ EC2 instance hoặc ENI tương ứng.
2. Chọn **destination**; ví dụ EC2 hoặc ENI của API.
3. Chọn **protocol TCP** và **destination port 8080**.
4. Nếu giao diện hỗ trợ, cấu hình source/destination IP hoặc thông số khác để khớp đúng yêu cầu.
5. Đặt tên/tag dễ tìm như `lab-app-to-api-8080`, rồi tạo path và chạy analysis.

### Bước 3 — Đọc kết quả

Khi analysis hoàn tất, cần đọc **cả kết luận lẫn lời giải thích**:

| Kết quả | Cách diễn giải | Bước xử lý |
| --- | --- | --- |
| `NetworkPathFound = true` | Có đường mạng phù hợp theo cấu hình được mô hình hóa | Nếu app còn lỗi, thử từ OS/runtime và xem DNS, listener, firewall hệ điều hành, TLS, IAM |
| `NetworkPathFound = false` | Không tìm thấy đường đi theo các điều kiện đã khai báo | Mở Explanations và xem thành phần chặn |
| `Status = failed` hoặc lỗi chạy analysis | Bản thân quá trình phân tích thất bại hoặc không được hỗ trợ theo ngữ cảnh | Xem status message, quyền IAM, nguồn/đích, quotas và supported resources |
| Phân tích đang chạy | Chưa có kết luận | Chờ kết quả phân tích theo quy trình Console; không đọc một trạng thái tạm như bằng chứng cuối |

Ví dụ giả định trong một kết quả không tìm được đường đi: công cụ trỏ đến **inbound security group rule** thiếu TCP/8080 trên ENI đích. Hành động đúng là kiểm tra và bổ sung một rule **TCP/8080 từ đúng SG nguồn** khi cấu trúc SG reference cho phép, hoặc từ CIDR nguồn tối thiểu; sau đó phân tích lại.

### Bước 4 — Kiểm thử thực và lưu bằng chứng

Một lần phân tích lại cho `NetworkPathFound=true` là dấu hiệu tốt, nhưng vẫn cần kiểm thử thực:

- Từ EC2-A: `curl -v --connect-timeout 5 http://10.20.2.20:8080/health` (nếu ứng dụng thực sự hỗ trợ HTTP).
- Trên EC2-B: kiểm tra process/listening port bằng công cụ OS như `ss -lnt`, rồi log dịch vụ.
- Đối chiếu thời điểm, VPC Flow Logs, CloudWatch metrics và deployment gần nhất.
- Ghi ngắn **trước/sau**, resource ID, rules đã đổi, kết quả thực và người chịu trách nhiệm.

## 6. Thực hành với AWS CLI

AWS CLI giúp lưu được thông số path, chạy lại có kiểm soát và đưa kết quả vào runbook. Những ID bên dưới **chỉ là ví dụ**; không chạy nguyên văn trên production.

### 6.1. Kiểm tra danh tính và Region

~~~bash
aws sts get-caller-identity --profile lab
aws configure get region --profile lab
~~~

Tài khoản/role cần quyền IAM tối thiểu cho các API Reachability Analyzer và quyền đọc thông tin tài nguyên liên quan; việc tạo/sửa route hoặc SG là quyền khác và chỉ cấp khi thực sự cần.

### 6.2. Tạo Network Insights Path giữa hai ENI

~~~bash
aws ec2 create-network-insights-path \
  --source eni-0123456789abcdef0 \
  --destination eni-0fedcba9876543210 \
  --protocol tcp \
  --destination-port 8080 \
  --region ap-southeast-1 \
  --profile lab
~~~

Dùng các **ENI thực tế được Reachability Analyzer hỗ trợ** làm nguồn và đích; điều tra có thể dùng EC2 instance ID hoặc những loại tài nguyên khác nếu API hỗ trợ. Kết quả tạo path có trường `NetworkInsightsPathId` dạng `nip-...`.

### 6.3. Bắt đầu phân tích

~~~bash
aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh trả về analysis ID dạng `nia-...`. Chỉ sau khi analysis hoàn tất, đọc `NetworkPathFound`, `Explanations` và các thành phần đường đi.

### 6.4. Đọc kết quả

~~~bash
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Nếu chỉ muốn tóm tắt:

~~~bash
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-0123456789abcdef0 \
  --query 'NetworkInsightsAnalyses[0].{Status:Status,PathFound:NetworkPathFound,Explanations:Explanations}' \
  --region ap-southeast-1 \
  --profile lab
~~~

**Cách đọc:** `Status` phản ánh tiến trình của analysis; `NetworkPathFound` mới là trường cho biết có đường đi theo cấu hình hay không. Nếu không có đường, mở chi tiết `Explanations` và đối chiếu resource ID với VPC, subnet, route table, SG, NACL, gateway hoặc attachment thực tế.

### 6.5. Đọc route table và security group để xác nhận

~~~bash
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

**Cạm bẫy:** Nếu lệnh lọc route table theo `association.subnet-id` không trả kết quả, subnet có thể đang **kế thừa main route table**; không thể kết luận subnet không có route. Xem subnet association và main route table của VPC. Với NACL, kiểm tra NACL đang liên kết với **subnet**, không chỉ xem danh sách NACL bất kỳ của VPC.

### 6.6. Dọn tài nguyên thử nghiệm

Nếu policy lab cho phép, kết thúc bằng việc xóa **analysis/path thử nghiệm** khi không còn cần cho báo cáo. Lưu lại bằng chứng tối thiểu trước khi dọn. Tránh xóa các path/analysis thuộc quy trình vận hành của nhóm khác. Phí phân tích và bản ghi log có thể đã phát sinh dù tài nguyên path sau đó được dọn.

## 7. Bảng chẩn đoán theo thành phần mạng

| Thành phần | Lỗi thường gặp | Kiểm tra trọng tâm |
| --- | --- | --- |
| **Subnet route table** | Sai table association, không có route, chọn target sai, route bị blackhole | CIDR đích, longest-prefix, route state, next hop |
| **Security group** | Thiếu ingress port đích, egress nguồn quá chặt, CIDR/SG reference không khớp | Đúng ENI nào gắn SG nào, TCP/UDP, port, source/dest |
| **Network ACL** | Rule Deny ưu tiên, thiếu ephemeral port chiều về | Rule number, inbound/outbound, CIDR, ephemeral range |
| **Internet Gateway** | Chưa attach hoặc subnet thiếu route; instance thiếu public IP | IGW attachment, route `0.0.0.0/0`, public IP và SG |
| **NAT Gateway** | Sai route, NAT không available, NAT public nằm ở subnet thiếu IGW | Private route, NAT subnet và đường về; NAT chỉ cho kết nối khởi tạo từ bên trong |
| **VPC peering** | Peering chưa active, route thiếu một phía, CIDR xung đột | Peering state, route tables của cả hai VPC |
| **Transit Gateway** | Attachment thiếu/nhầm association, propagation thiếu, static/blackhole route | TGW route table, attachment state, VPC routes hai phía |
| **VPC endpoint** | Sai endpoint type, route/prefix list, endpoint SG hoặc private DNS | Gateway endpoint vs interface endpoint; DNS và SG/route đúng loại |
| **VPN/Direct Connect** | Thiếu route/BGP, firewall bên ngoài, tunnel mất kết nối | TGW/VGW + trạng thái tunnel/link + thiết bị on-premises |
| **Load Balancer** | SG/listener/target group/health check không đúng | Kiểm tra riêng luồng client→LB và LB→targets |
| **DNS** | Trỏ nhầm IP/vùng, private zone chưa liên kết, cache cũ | `dig`/`nslookup`, Route 53 Resolver và endpoint |
| **Hệ điều hành / ứng dụng** | Không listen port, host firewall, TLS hoặc authentication sai | `ss`, `curl`, logs, metrics, DB/auth |

**Lưu ý:** Không phải mọi mục trong bảng đều được Reachability Analyzer kiểm tra đầy đủ. Bảng này là **phạm vi điều tra end-to-end**, trong đó Reachability Analyzer là một công cụ quan trọng cho phần mạng AWS.

## 8. Ví dụ A: Hai EC2 cùng VPC nhưng ứng dụng không gọi được API

### Mô hình

- VPC `10.20.0.0/16` tại một Region.
- EC2-A trong subnet `10.20.1.0/24`, SG `sg-client`.
- EC2-B trong subnet `10.20.2.0/24`, SG `sg-api`.
- Ứng dụng A gọi `http://10.20.2.20:8080/health`.

~~~mermaid
flowchart LR
    subgraph VPC["VPC 10.20.0.0/16"]
      subgraph AZA["AZ A"]
        A[EC2-A / 10.20.1.10 / SG client]
      end
      subgraph AZB["AZ B"]
        B[EC2-B / 10.20.2.20 / SG API]
      end
      A -->|TCP 8080| B
    end
~~~

**Triệu chứng:** `curl` từ A bị timeout. Trong Reachability Analyzer, path từ ENI-A đến ENI-B cho TCP/8080 trả **không tìm thấy đường đi**, lời giải thích chỉ vào SG đích.

**Chẩn đoán:**

1. Xác nhận các subnet dùng route table có route `10.20.0.0/16 → local`.
2. Xác nhận SG A cho egress phù hợp.
3. Xem SG B: nếu chỉ mở TCP/443 thì TCP/8080 bị chặn.
4. Bổ sung inbound TCP/8080 giới hạn vào SG A (nếu loại tham chiếu được hỗ trợ), hoặc dải IP nguồn thích hợp.
5. Phân tích lại; nếu path được tìm thấy, thử `curl` thực.
6. Nếu `curl` vẫn timeout, xem EC2-B có ứng dụng listen TCP/8080, local firewall, đúng IP và log không.

**Bài học:** SG là bộ lọc, không phải route table. Một tuyến `local` tồn tại không chứng minh cổng ứng dụng mở.

## 9. Ví dụ B: VPC peering đang active nhưng không liên lạc được

### Mô hình

- **VPC A**: CIDR `10.10.0.0/16`, EC2 nguồn `10.10.1.10`.
- **VPC B**: CIDR `10.30.0.0/16`, EC2 đích `10.30.2.20`.
- Peering `pcx-demo` đã ở trạng thái `active`.
- Mục tiêu: A gọi B trên TCP/443.

~~~mermaid
flowchart LR
    A[EC2-A / 10.10.1.10] --> RA[Route table subnet A]
    RA --> PCX[VPC peering]
    PCX --> RB[Route table subnet B]
    RB --> B[EC2-B / 10.30.2.20]
~~~

**Tình trạng ví dụ:** Route phía A có `10.30.0.0/16 → pcx-demo`, nhưng phía B chưa có `10.10.0.0/16 → pcx-demo`. Một luồng trao đổi có thể không hoàn tất vì thiếu đường về; cần kiểm tra cả hai hướng bằng thông tin RA và cấu hình route.

**Cách xử lý:**

1. Kiểm tra VPC A/B có CIDR phù hợp, peering active và các subnet dùng route table nào.
2. Đối chiếu **route ở cả hai VPC** đến CIDR của đối phương.
3. Kiểm tra SG B cho TCP/443 từ nguồn; SG A có egress tương ứng.
4. Kiểm tra NACL hai phía và các đường hồi đáp.
5. Đánh giá bằng Reachability Analyzer theo phạm vi hỗ trợ của peering, rồi thử kết nối thực và ghi kết quả.

**Bài học:** Peering active mới là quan hệ kết nối giữa VPC; **route hai phía và bộ lọc mạng** quyết định luồng ứng dụng có hoàn tất được hay không. Đối với một luồng có SG stateful, việc phản hồi không yêu cầu mở thêm inbound rule ở SG của máy khởi tạo, nhưng NACL vẫn phải xét chiều về.

## 10. Ví dụ C: Private instance truy cập dịch vụ AWS hoặc Internet

### Tình huống

API trong private subnet cần tải dữ liệu từ một dịch vụ AWS qua HTTPS; nhóm vận hành nhận lỗi kết nối hoặc timeout.

**Không nên lập tức mở NAT Gateway:** trước hết xác định **dịch vụ đích và cách truy cập**.

- Nếu cần **S3/DynamoDB** và dùng endpoint được hỗ trợ: cân nhắc **gateway VPC endpoint** với route table phù hợp.
- Nếu cần API của một dịch vụ có **interface VPC endpoint**: cân nhắc endpoint ENI, security group và private DNS đúng.
- Nếu cần truy cập Internet IPv4 tổng quát: thường khảo sát **public NAT Gateway** cho private subnet và đường ra IGW.
- Nếu là IPv6: đánh giá tuyến IPv6 và egress-only IGW/đường ra thích hợp, không suy luận từ IPv4.

### Quy trình

1. Xác nhận DNS trả tên dịch vụ tới private endpoint hay public IP.
2. Kiểm tra route table thực của subnet nguồn; gateway endpoint route/prefix list hay default route qua NAT.
3. Kiểm tra private DNS của **interface endpoint** và SG của endpoint ENI nếu sử dụng.
4. Dùng Reachability Analyzer nếu cặp endpoint và kiến trúc thuộc loại hỗ trợ; không ép công cụ đánh giá một resource không hỗ trợ.
5. Kiểm thử HTTPS và IAM permission thực tế; API AWS có thể từ chối **AccessDenied** ngay cả khi mạng hoàn toàn ổn.

**Bài học:** Lỗi mạng tới endpoint và lỗi quyền IAM là hai lớp độc lập. Thay route không giải quyết được `AccessDenied` từ S3/KMS khi request đã đến dịch vụ.

## 11. Các công cụ bổ trợ: chọn đúng loại bằng chứng

Reachability Analyzer nên nằm trong bộ công cụ điều tra, không đứng một mình.

| Công cụ | Bằng chứng chính | Giới hạn cần nhớ |
| --- | --- | --- |
| **Reachability Analyzer** | Có/không có đường theo cấu hình mạng AWS được hỗ trợ và lời giải thích | Không phải packet probe, không bảo đảm listener/TLS/IAM |
| **VPC Flow Logs** | Bản ghi metadata lưu lượng tại ENI, subnet hoặc VPC; ACCEPT/REJECT theo mô hình log | Có độ trễ, không chứa payload, không đại diện cho mọi tình huống; ACCEPT không đồng nghĩa ứng dụng thành công |
| **CloudWatch Logs/Metrics** | Log ứng dụng, metric lưu lượng, error rate, latency, timeout | Cần cấu hình thu thập/giữ log và đánh dấu thời gian |
| **Route 53 Resolver query logging** | Truy vấn DNS mà Resolver xử lý/ghi nhận | Cache và phạm vi logging ảnh hưởng bản ghi |
| **VPC Traffic Mirroring** | Bản sao gói mạng trong các trường hợp được hỗ trợ, dùng phân tích sâu | Tốn tài nguyên, yêu cầu cấu hình, lưu trữ và bảo vệ dữ liệu |
| **AWS Network Manager / Route Analyzer** | Phân tích một số đường định tuyến/hub ở phạm vi dịch vụ được hỗ trợ | Khác Reachability Analyzer; chọn theo công nghệ TGW/Cloud WAN thực tế |
| **VPC Network Access Analyzer** | Kiểm tra đường truy cập mạng so với scope/quy tắc kiểm soát bạn khai báo | Dành cho kiểm tra tuân thủ phạm vi truy cập, không thay đo kết nối ứng dụng |
| **curl, nc, dig, traceroute, ss** | Kiểm chứng DNS, TCP/TLS, listener hoặc quan sát đường đi trên OS | Kết quả tùy ICMP/UDP/TCP, firewall, endpoint và quyền hệ điều hành |
| **AWS CloudTrail** | Ai đã thay đổi route, SG, NACL, endpoint; API control plane | Không phải log payload packet; cần cấu hình tra cứu sự kiện phù hợp |

### VPC Flow Logs: ACCEPT và REJECT nghĩa là gì?

Giả sử Flow Logs cho ENI nguồn ghi TCP/8080 với action `REJECT`: đây là tín hiệu cần đối chiếu với SG/NACL. Nếu `ACCEPT`, có thể gói đã qua lớp kiểm soát được log ghi nhận, nhưng **không chứng minh TCP handshake hoàn tất**, service nhận được request hay trả mã 200.

Một bước quan trọng là lọc log đúng:

- **ENI/subnet/VPC**, nguồn, đích, cổng, protocol;
- khoảng thời gian lỗi và timezone;
- network interface của **tài nguyên thực**, nhất là khi đi qua load balancer, NAT hoặc endpoint;
- cấu hình Flow Logs, loại bản ghi và trường `log-status` nếu có.

Khi có NAT hoặc load balancer, IP/port hiển thị ở các điểm quan sát có thể khác nhau do dịch địa chỉ hoặc proxy. Đừng kỳ vọng mọi log đều xuất hiện ở một ENI nguồn với cùng tuple ban đầu.

### Phân biệt network path với endpoint health

Ví dụ kết quả Reachability Analyzer cho client → ALB là reachable. Điều này **không chứng minh** rằng ALB có listener hợp lệ hoặc target group có healthy target. Cần kiểm tra riêng:

1. Client → ALB trên port thực;
2. ALB → target trên port cấu hình;
3. health check, target status và response code;
4. TLS certificate/listener rule và log của ứng dụng.

Có thể chạy phân tích mạng riêng cho luồng LB → target khi tài nguyên và kiểu đường đi được Reachability Analyzer hỗ trợ.

## 12. Quy trình chẩn đoán có thứ tự, tránh sửa mò

### Bước 1 — Xác định yêu cầu và chiều kết nối

Ghi lại theo một dòng:

~~~text
Nguồn: EC2 app-a / eni-A / 10.20.1.10 / VPC-A / subnet-A
Đích:  EC2 api-b / eni-B / 10.20.2.20 / VPC-A / subnet-B
Luồng: TCP 8080, app-a là bên mở kết nối
Lỗi:   Connection timed out sau 5 giây
Thời điểm: ngày/giờ quan sát thực tế và Region
~~~

Nếu có load balancer, NAT hoặc DNS thay đổi, ghi cả **hostname**, IP tại thời điểm lỗi và tài nguyên trung gian.

### Bước 2 — Kiểm tra cấu hình nguồn/đích

- EC2/ENI thuộc VPC/subnet/SG nào?
- Địa chỉ IP đích thuộc CIDR/IPv4/IPv6 nào?
- Route table của subnet nguồn là bảng cụ thể hay main route table?
- SG ingress/egress và NACL có rule phù hợp không?
- Các gateway/attachment/endpoint ở trạng thái gì?

### Bước 3 — Dùng Reachability Analyzer cô lập nút nghẽn

Tạo path đúng protocol/port và chạy analysis. Nếu không tìm thấy đường, đọc **Explanations + resource ID**, xác nhận bằng route table/SG/NACL/attachment. Không tự thêm `0.0.0.0/0` hoặc `::/0` chỉ vì cần có một route trông hợp lệ.

### Bước 4 — Thực hiện thay đổi nhỏ nhất

Ví dụ:

- Thiếu route trả về từ VPC B: thêm đúng CIDR nguồn qua peering/TGW có sẵn, sau khi được phê duyệt.
- SG đích thiếu TCP/443 từ SG app: thêm đúng rule thay vì cho toàn Internet.
- NACL thiếu ephemeral return ports: sửa rule theo OS/client và giới hạn CIDR chính xác.
- TGW thiếu association/propagation: điều chỉnh **đúng** TGW route table/attachment theo sơ đồ.
- Route đến NAT bị blackhole: khôi phục target/đường egress phù hợp, xem lại tình trạng NAT trước khi thay route.

Thay đổi network control trong production phải tính tới ảnh hưởng ngoài luồng đang lỗi, đặc biệt route table/SG được nhiều workload dùng chung.

### Bước 5 — Kiểm chứng sau thay đổi

1. Chạy lại **Reachability Analyzer** với cùng source/destination/protocol/port.
2. Chạy **TCP/HTTP test thực** từ workload.
3. Xác nhận **ứng dụng** và metric latency/error hoạt động đúng.
4. Kiểm tra luồng không được phép vẫn bị chặn; không mở rộng access ngoài ý định.
5. Ghi bằng chứng, change ID, thời gian, nguyên nhân gốc và rollback.

### Bước 6 — Nếu phân tích báo reachable nhưng ứng dụng vẫn lỗi

Kiểm tra lần lượt:

- DNS cache/trả IP khác với path;
- process không listen, host firewall hoặc container networking;
- listener/target group/health check của load balancer;
- TLS SNI/certificate, proxy, HTTP host header;
- database connection limit, authentication hoặc IAM;
- latency/throttle, DNS TTL, packet size/MTU, resource saturation;
- lỗi gián đoạn theo thời gian, trong khi Reachability Analyzer chỉ nhìn vào **cấu hình tại thời điểm phân tích**.

### Cây quyết định tham khảo

~~~mermaid
flowchart TD
  A[Không kết nối được] --> B[Kiểm tra DNS và IP đích]
  B --> C[Chọn nguồn, đích, protocol, port]
  C --> D[Chạy Reachability Analyzer]
  D --> E{NetworkPathFound?}
  E -->|Không| F[Explanations: route / SG / NACL / GW / endpoint]
  F --> G[Sửa đúng cấu hình + phân tích lại]
  E -->|Có| H[Thử TCP / TLS / app từ nguồn thật]
  G --> H
  H --> I{Request thực thành công?}
  I -->|Không| J[Flow Logs / OS / LB / TLS / IAM / app]
  I -->|Có| K[Ghi bằng chứng và giám sát]
~~~

## 13. Tư duy đa AZ, đa tài khoản và khả năng phục hồi

### Nhiều Availability Zone

Nếu ứng dụng có service ở AZ A và AZ B, kiểm tra các luồng quan trọng từ **cả hai AZ**, chẳng hạn:

- App task AZ A → RDS endpoint;
- App task AZ B → RDS endpoint;
- ALB subnet AZ A/B → targets AZ A/B;
- Workload ở từng AZ → NAT gateway hoặc VPC endpoint tương ứng.

Một path duy nhất thành công không bảo đảm **mọi AZ, ENI và target** đã được cấu hình đúng. NACL có thể khác theo subnet; route table có thể khác; dịch vụ có thể chỉ lỗi khi failover sang AZ khác.

**Failover:** Reachability Analyzer xác nhận đường theo cấu hình tĩnh, không tạo giả lập outage/failover thật. Để kiểm chứng RTO/RPO và khả năng phục hồi, cần diễn tập có kiểm soát kết hợp health check, ứng dụng, DNS, database replication/backup và dịch vụ thay thế.

### Nhiều tài khoản, nhiều VPC

Trong môi trường AWS Organizations, một luồng có thể đi qua route tables và TGW/VPC attachments thuộc nhiều tài khoản. Quyền xem/chạy phân tích cho tài nguyên nhiều account và mức hỗ trợ phụ thuộc cấu hình/tính năng đang dùng; cần tổ chức tài khoản quản trị mạng, chia sẻ thông tin, IAM role phù hợp.

Checklist:

- Có sơ đồ CIDR không chồng lấp và bảng ánh xạ VPC/account/Region.
- Có tài liệu **owner** của từng route table, TGW table, SG, endpoint và firewall.
- Chỉ rõ **return path**, không kiểm tra riêng chiều đi.
- Kiểm tra khả năng hỗ trợ phân tích cross-account với loại tài nguyên thực tế; nếu không đủ, dùng flow logs và kiểm thử từ mỗi phía.

### Tính nhất quán và thay đổi hạ tầng

Nhiều lỗi do cấu hình drift: một môi trường có rule đúng, môi trường còn lại thiếu. Nên quản lý route, SG, endpoint, TGW attachment và VPC bằng **Infrastructure as Code (CloudFormation, CDK hoặc công cụ tương đương)**, review thay đổi và kết hợp phân tích định tuyến trong giai đoạn kiểm thử.

Đối với network route có ảnh hưởng lớn, ghi rõ **assumptions, tests, metrics, rollback** trong pull request/change request. Reachability Analyzer là một nguồn bằng chứng đầu vào hữu ích, nhưng vẫn cần kiểm thử thực khi rollout.

## 14. Bảo mật, chi phí và observability

### Bảo mật

- **Least privilege:** IAM role của người điều tra chỉ nên có quyền đọc/phân tích cần thiết; quyền sửa SG/route phải được cấp theo vai trò và quy trình phù hợp.
- **Defense in depth:** Route hợp lệ không thay SG/NACL; SG cho phép không thay host firewall/TLS; DNS thành công không thay authentication/authorization.
- **Mạng private:** Ưu tiên private endpoint/đường nội bộ cho workload nhạy cảm khi khả thi; tránh mở cổng public chỉ để làm bài test.
- **Ghi log an toàn:** VPC Flow Logs, CloudWatch, CloudTrail và tài liệu kết nối có thể chứa IP, hostname và thông tin hạ tầng; áp dụng retention, encryption và quyền đọc phù hợp.
- **Giảm rủi ro change:** Chỉ điều chỉnh đúng rule, route, CIDR và cổng cần thiết; kiểm tra những đường **không được phép** sau thay đổi.

### Chi phí

- Reachability Analyzer có thể tính phí theo **lượt phân tích**. Đừng chạy phân tích lặp liên tục với các path giống nhau nếu không có mục tiêu kiểm tra mới.
- VPC Flow Logs, CloudWatch Logs/S3 và thời gian lưu dữ liệu có chi phí riêng.
- NAT Gateway, Transit Gateway, endpoints, truyền dữ liệu giữa AZ/Region và kết nối hybrid có thể là phần đáng kể của hóa đơn mạng.
- Dùng **AWS Pricing Calculator, AWS Cost Explorer và AWS Budgets** để ước tính theo Region/cấu hình hiện hành, gắn tags theo ứng dụng, môi trường, chủ sở hữu.

Một route `0.0.0.0/0` qua NAT Gateway có thể làm lưu lượng giữa các dịch vụ đi vòng và tốn chi phí hơn một endpoint/đường riêng phù hợp. Tuy nhiên lựa chọn endpoint phải dựa vào **loại dịch vụ, yêu cầu bảo mật và thực tế lưu lượng**, không chỉ vào một khoản phí đơn lẻ.

### Giám sát sau khi sửa lỗi

Các chỉ số có ích:

- tỷ lệ kết nối thành công, TCP connect time, HTTP 5xx và application error;
- target health của ALB/NLB, trạng thái các gateway/attachment/tunnel;
- lưu lượng VPC Flow Logs ACCEPT/REJECT và mẫu lỗi thay đổi;
- độ trễ DNS/endpoint và connection timeout từ các AZ;
- thời điểm thay đổi route/SG theo CloudTrail và change log;
- chi phí NAT/TGW/endpoint/logs theo ứng dụng hoặc môi trường.

## 15. Những nhầm lẫn thường gặp

| Phát biểu sai | Cách hiểu đúng |
| --- | --- |
| “Reachability Analyzer dùng ping từ AWS tới máy.” | Đây là phân tích tĩnh cấu hình, không tạo packet probe thực. |
| “Path found nghĩa là HTTPS sẽ trả 200.” | Cần kiểm tra listener, TLS, DNS, IAM và ứng dụng. |
| “Peering active là hai VPC tự thông nhau.” | Vẫn cần routes, SG/NACL, đường về và CIDR phù hợp. |
| “VPC route table có 0.0.0.0/0 là Internet dùng được.” | Cần target và địa chỉ IP/đường mạng hợp lệ, SG/NACL và dịch vụ đang hoạt động. |
| “Private subnet muốn gọi AWS API bắt buộc cần NAT.” | Có thể sử dụng gateway/interface VPC endpoints khi phù hợp. |
| “Security group stateless nên phải mở ephemeral inbound cho phản hồi.” | SG là stateful; **NACL** stateless mới thường cần xét port phản hồi. |
| “VPC Flow Logs ACCEPT chứng minh ứng dụng thành công.” | Chỉ là tín hiệu tại lớp mạng được log, không chứng minh TLS/HTTP hay logic ứng dụng. |
| “Một AZ có path tốt thì Multi-AZ chắc chắn hoạt động.” | Phải xác minh từng subnet/ENI/route và diễn tập failover. |
| “Chỉ cần mở hết 0.0.0.0/0 để biết lỗi.” | Cách này tạo rủi ro bảo mật và che giấu nguyên nhân; nên dùng phân tích theo luồng. |
| “Mọi thiết bị on-premises đều nằm trong mô hình Reachability Analyzer.” | Cần xác nhận giới hạn hỗ trợ và bổ sung kiểm thử/log của mạng bên ngoài AWS. |

## 16. Checklist trước khi kết luận sự cố được xử lý

- [ ] Xác định đúng nguồn, đích, protocol, destination port và thời điểm lỗi.
- [ ] Biết tên DNS phân giải thành IP nào khi lỗi xảy ra; không phân tích nhầm endpoint.
- [ ] Đọc đúng route table của mỗi subnet, gồm **main table** nếu không có association riêng.
- [ ] Kiểm tra SG inbound/egress theo ENI và NACL cả hai chiều.
- [ ] Với peering/TGW/hybrid: kiểm tra route và state **cả hai phía**; tránh CIDR trùng và blackhole.
- [ ] Với Internet/NAT/VPC endpoint: kiểm tra đúng target, public/private address, endpoint type và DNS.
- [ ] Đã chạy Reachability Analyzer với thông số hợp lệ và hiểu `NetworkPathFound` cùng `Explanations`.
- [ ] Đã đối chiếu các thành phần bị chặn với cấu hình thực, không mở quyền mạng quá rộng.
- [ ] Đã thử kết nối TCP/TLS/ứng dụng từ nơi phát sinh lỗi, không chỉ xem phân tích tĩnh.
- [ ] Có log/metric chứng minh lỗi đã giảm, đường không được phép vẫn bị chặn.
- [ ] Đã xem khả năng hoạt động từ nhiều AZ và sau failover nếu hệ thống cần HA.
- [ ] Ghi lại thay đổi, resource IDs, nguyên nhân, kiểm thử, phương án rollback và chi phí phát sinh.

## 17. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1: Chẩn đoán SG bị thiếu rule

**Đề bài:** EC2 trong hai subnet cùng VPC không giao tiếp TCP/8443. Route local đã có, SG nguồn cho egress, SG đích chỉ cho TCP/443. Hãy:

1. Tạo path từ ENI nguồn sang ENI đích với TCP/8443.
2. Giải thích vì sao analyzer có thể trả `NetworkPathFound=false`.
3. Đề xuất rule ingress tối thiểu cho SG đích; dự đoán khác biệt nếu thay port trong path thành 443.
4. Sau thay đổi, chạy lại và thử TCP/8443 thật; nêu nguyên nhân có thể khiến kết nối vẫn không thành công dù path tìm thấy.

**Kỳ vọng:** Phân biệt SG rule và route, dùng đúng destination port, hiểu giới hạn phân tích tĩnh.

### Bài tập 2: VPC peering có đường đi nhưng thiếu đường về

**Đề bài:** VPC A có CIDR `10.1.0.0/16`, VPC B có `10.2.0.0/16`; peering active. Route A → B có, B → A chưa có. Hãy vẽ đường đi/đường về, liệt kê route table cần sửa và những kiểm tra SG/NACL còn thiếu. So sánh kết quả kiểm tra chiều A→B với kết nối ứng dụng thành công thực tế.

**Kỳ vọng:** Nhận biết route phải phù hợp ở hai phía, ngoài các bộ lọc và thiết lập ứng dụng.

### Bài tập 3: Kiến trúc doanh nghiệp nhiều VPC

**Đề bài:** Các VPC ứng dụng trong nhiều account cùng kết nối về một TGW, có mạng on-premises qua VPN. Một service ở VPC A cần gọi service ở VPC C qua TCP/443. Thiết kế runbook gồm:

- bảng VPC CIDRs, subnet route tables và attachments;
- TGW route table association/propagation;
- nguyên tắc kiểm tra đường về và firewall;
- nơi Reachability Analyzer giúp tìm điểm chặn;
- công cụ bổ sung khi đường qua on-premises nằm ngoài phạm vi phân tích;
- metric/log và cảnh báo sau khi hoàn tất.

### Câu hỏi tự kiểm tra

**1. Reachability Analyzer báo reachable nhưng TCP handshake timeout, bước tiếp theo là gì?**  
Kiểm tra kết nối thực từ đúng ENI/host, IP DNS, listener, host firewall, load balancer, điều kiện runtime, đường về và Flow Logs; không suy luận ứng dụng đã hoạt động chỉ từ một kết luận tĩnh.

**2. SG cho phép inbound 5432 nhưng NACL chặn ephemeral port chiều về. Liệu một kết nối TCP có hoàn tất không?**  
Có thể không. SG stateful và NACL stateless có hành vi khác nhau; cần xét đường về và cổng phản hồi phù hợp.

**3. Vì sao subnet private không thể được truy cập từ Internet chỉ vì có NAT Gateway?**  
NAT Gateway thông thường cho phép luồng do phía private khởi tạo đi ra, không nhận kết nối mới từ Internet tới private instance.

**4. Trong TGW, chỉ xem route table VPC đã đủ chưa?**  
Chưa. Phải kiểm tra TGW route table, association, propagation/static routes, trạng thái attachments và đường về.

**5. Một thay đổi route hôm qua làm cả AZ B lỗi nhưng AZ A vẫn tốt. Nên kiểm tra gì trước?**  
So sánh route table associations, SG/NACL/endpoint và tài nguyên khác nhau giữa AZ; chạy những network insights path tương ứng từ cả hai AZ, rồi kiểm thử thực.

## 18. Kết luận

Reachability Analyzer giúp trả lời một câu hỏi quan trọng: **“Theo cấu hình mạng AWS hiện tại và luồng được khai báo, có đường đi hợp lệ từ nguồn tới đích không?”** Khi kết hợp với phân tích route table, security group, NACL, gateway, peering và TGW, công cụ rút ngắn thời gian tìm nguyên nhân mất kết nối.

Quy trình vững chắc là **xác định luồng thực → kiểm tra DNS và địa chỉ → phân tích đường đi → đọc điểm chặn → thay đổi tối thiểu → kiểm thử TCP/TLS/ứng dụng → giám sát và ghi nhận**. Khi thiết kế hệ thống AWS an toàn, có khả năng phục hồi và kiểm soát chi phí, phải nhìn đồng thời Region/AZ, IAM, VPC, compute, storage/database, endpoint, logging và ngân sách. Khả năng kết nối theo cấu hình chỉ là một lớp của chất lượng hệ thống.

### Tài liệu AWS nên tra cứu khi triển khai

- **Amazon VPC Reachability Analyzer User Guide**: khái niệm Network Insights Path, analysis, explanations, supported resources và limitations. <https://docs.aws.amazon.com/vpc/latest/reachability/>
- **Amazon VPC User Guide**: Route tables, security groups, network ACLs, Internet Gateway, NAT Gateway, VPC endpoints, VPC peering. <https://docs.aws.amazon.com/vpc/latest/userguide/>
- **AWS CLI Command Reference — EC2**: `create-network-insights-path`, `start-network-insights-analysis`, `describe-network-insights-analyses`. <https://docs.aws.amazon.com/cli/latest/reference/ec2/>
- **Amazon VPC Flow Logs**: phạm vi dữ liệu, filter và ý nghĩa ACCEPT/REJECT. <https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html>
- **AWS Transit Gateway documentation**: attachments, route tables, association, propagation và static routes. <https://docs.aws.amazon.com/vpc/latest/tgw/>

Tính năng được hỗ trợ, giới hạn, chính sách quyền và biểu giá có thể thay đổi theo dịch vụ, account và Region; hãy đối chiếu tài liệu AWS hiện hành trước khi áp dụng cho môi trường production.
