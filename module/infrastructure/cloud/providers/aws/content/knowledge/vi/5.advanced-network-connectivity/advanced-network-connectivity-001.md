# VPC Peering và giới hạn định tuyến bắc cầu

Trong AWS, một ứng dụng có thể được tách thành nhiều **Virtual Private Cloud (VPC)** để cô lập môi trường phát triển, production, hệ thống dữ liệu và dịch vụ dùng chung. Khi một ứng dụng trong VPC A phải gọi private API hoặc truy cập cơ sở dữ liệu trong VPC B, có thể kết nối hai VPC bằng **VPC Peering**. Công nghệ này tạo đường trao đổi lưu lượng qua địa chỉ IP của hai VPC, không cần đi qua public internet.

Tuy nhiên, VPC Peering có giới hạn thiết kế đặc biệt quan trọng: **không hỗ trợ định tuyến bắc cầu (non-transitive routing)**. Nếu VPC A peering với B và A cũng peering với C, B **không thể** dùng A làm mạng trung chuyển để giao tiếp với C. Nhầm lẫn điều này dễ dẫn đến route table sai, triển khai không hoạt động và kiến trúc nhiều VPC khó mở rộng.

Bài học thuộc chương **Kết nối mạng nâng cao** của mô-đun **CLOUD_PROVIDERS_AWS**. Kiến thức được áp dụng khi thiết kế mạng cho EC2, ECS/EKS, Lambda trong VPC, RDS, lưu trữ và dịch vụ tích hợp giữa account/Region; lựa chọn phương án kết nối, thiết lập bảo mật, giám sát, khả năng phục hồi và kiểm soát chi phí.

> **Nguyên tắc cần nhớ:** VPC Peering là kết nối **một cặp VPC với một cặp VPC**. Route table, Security Group, NACL và DNS phải được cấu hình phù hợp ở cả hai bên. Không thể biến một VPC ở giữa thành router bắc cầu giữa các peering connections.

## 1. Kết quả học tập

Sau khi học, bạn có thể:

1. Diễn giải VPC Peering, điều kiện cùng/khác account và Region, IPv4/IPv6.
2. Đọc sơ đồ A–B–C và chứng minh vì sao B không đi được đến C qua A.
3. Lập route table **hai chiều** cho cặp VPC đã peer mà không nhầm tuyến `local`, `pcx-...`, Internet Gateway, NAT Gateway hoặc Transit Gateway.
4. Nhận diện các giới hạn CIDR chồng lấn, DNS, tham chiếu Security Group, edge-to-edge routing và quota.
5. Mô tả quy trình yêu cầu, chấp nhận, kích hoạt peering và cấp quyền lưu lượng thực tế.
6. Sử dụng AWS Console và AWS CLI **chỉ đọc** để kiểm tra kết nối, route tables, Security Groups, NACL và VPC Flow Logs.
7. Chọn giữa VPC Peering, AWS Transit Gateway, AWS Cloud WAN và AWS PrivateLink theo nhu cầu thực sự.
8. Đánh giá tác động tới bảo mật, độ sẵn sàng, khả năng mở rộng và phí data transfer.

## 2. Khái niệm VPC Peering

**VPC Peering connection** là kết nối mạng giữa **hai VPC** cho phép tài nguyên trong chúng trao đổi dữ liệu bằng private IPv4 hoặc IPv6. Có thể tạo kết nối giữa:

- Hai VPC cùng AWS account, cùng Region.
- Hai VPC khác AWS account, cùng Region.
- Hai VPC cùng AWS account, khác Region.
- Hai VPC khác account, khác Region.

Ví dụ công ty có VPC chạy API Java/Spring Boot trong account ứng dụng và VPC chứa dịch vụ dữ liệu riêng trong account dữ liệu. Khi IP CIDR không chồng lấn, hai account được cấp quyền cấu hình kết nối, route table và chính sách mạng phù hợp, ứng dụng có thể kết nối tới private endpoint của cơ sở dữ liệu. Peering tạo **khả năng định tuyến**; nó không tự động cấp quyền đăng nhập vào database hoặc AWS API.

### 2.1. Peering là kết nối mạng lớp IP, không phải “gộp VPC”

Sau khi peer, hai VPC vẫn độc lập về:

- Chủ sở hữu account, ranh giới IAM và SCP của tổ chức.
- Subnet, route table, Security Group, NACL và DNS của từng VPC.
- Dải CIDR, thiết lập DNS, tài nguyên triển khai và vòng đời của chúng.
- Chính sách ứng dụng, database authentication, TLS, secrets và phân quyền dịch vụ.

Peering không tạo một VPC mới, không nhập CIDR, không đồng bộ route và không tạo một VPN gateway hoặc thiết bị router cần vận hành. Lưu lượng đi trong hạ tầng mạng AWS; inter-Region peering đi trên AWS backbone và được mã hóa trên đường truyền giữa các Region. Với dữ liệu nhạy cảm, ứng dụng vẫn nên dùng TLS và xác thực riêng.

### 2.2. Điều kiện trước khi tạo peering

| Điều kiện | Ý nghĩa |
|---|---|
| **CIDR không chồng lấn** | Không thể peer trực tiếp hai VPC nếu bất kỳ dải IPv4 hoặc IPv6 của chúng bị overlap; bao gồm primary/secondary CIDRs |
| Hai đầu là VPC hợp lệ | Có VPC ID, account ID và Region chính xác |
| Có quyền thao tác | Principal được phép tạo/accept peering; với cross-account bên nhận phải chấp thuận |
| Phải có route hai chiều | Chỉ tạo peering chưa làm traffic hoạt động |
| Network access rules | SG/NACL và firewall ứng dụng phải cho phép luồng cần thiết |
| DNS | Nếu dùng hostname, phải giải quyết DNS độc lập với việc mở tuyến IP |
| Quota và dữ liệu truyền | Kiểm tra giới hạn peering/route table và chi phí data transfer theo AZ/Region |

**Ví dụ CIDR:** VPC A là `10.10.0.0/16` và VPC B là `10.20.0.0/16` thì hai dải không chồng lấn. Nếu B có CIDR `10.10.128.0/17`, nó nằm trong dải của A, nên không thể tạo peering dù chỉ muốn dùng một subnet không overlap. Việc hai VPC đều có IPv6 CIDR riêng cũng **không cho phép bỏ qua** IPv4 overlap.

## 3. Bài toán trung tâm: A peer B, A peer C, nhưng B không đến được C

Giả sử cả ba VPC cùng Region `ap-southeast-1`:

| VPC | IPv4 CIDR | Chức năng |
|---|---|---|
| **A – Shared Services** | `10.10.0.0/16` | API hoặc dịch vụ dùng chung |
| **B – Application** | `10.20.0.0/16` | Ứng dụng backend |
| **C – Data** | `10.30.0.0/16` | Hệ thống dữ liệu |

Có hai peering connections:

- `pcx-ab`: A ↔ B.
- `pcx-ac`: A ↔ C.

~~~mermaid
flowchart TD
    B["VPC B • Application<br/>10.20.0.0/16"]
    A["VPC A • Shared Services<br/>10.10.0.0/16"]
    C["VPC C • Data<br/>10.30.0.0/16"]
    B <-->|"pcx-ab: trực tiếp"| A
    A <-->|"pcx-ac: trực tiếp"| C
    B -.-|"KHÔNG có peering trực tiếp<br/>B → A → C không được hỗ trợ"| C
~~~

**Đường hợp lệ:** EC2 ở B có thể gọi private service ở A qua `pcx-ab` nếu tuyến, Security Group, NACL, firewall và ứng dụng đều hợp lệ. EC2 ở C cũng có thể gọi A qua `pcx-ac`.

**Đường không hợp lệ:** EC2 ở B muốn kết nối tới private IP của RDS ở C bằng tuyến `B → pcx-ab → A → pcx-ac → C`. **AWS không chuyển tiếp traffic từ một peering connection sang peering connection khác.** Thêm tuyến đến CIDR C ở route table B và cho target là `pcx-ab` không làm quan hệ bắc cầu xuất hiện.

### 3.1. Vì sao không thể bật định tuyến bắc cầu bằng static routes?

Ở mạng truyền thống, nếu router A biết tuyến tới B và C, A có thể chuyển tiếp giữa hai mạng. Nhưng **VPC Peering không phải một router giữa các VPC**. Peering chỉ cho phép traffic từ một VPC tới **VPC đối tác trực tiếp của connection đó**. Mối quan hệ A↔B độc lập với A↔C; AWS không coi A là “transit network” cho traffic B↔C.

Các thao tác **không giải quyết** giới hạn này:

1. Thêm default route `0.0.0.0/0` của B hướng về `pcx-ab` để đi tiếp C.
2. Thêm route cho `10.30.0.0/16` trên B với target `pcx-ab` dù A không phải endpoint của CIDR C.
3. Chỉ mở mọi cổng ở Security Group của A.
4. Bật IP forwarding trên EC2 trong A để giả lập router nối hai peering connections.
5. Bổ sung route C→B trên route table C nhưng vẫn thiếu một peering B–C trực tiếp.

Kể cả khi control plane chấp nhận một cấu hình route nào đó, **data plane không hỗ trợ bắc cầu qua peering**. Khắc phục đúng là có **peering B–C riêng** nếu cần kết nối điểm-điểm, hoặc dùng công cụ thiết kế cho transitive routing như **AWS Transit Gateway** hoặc **AWS Cloud WAN**.

### 3.2. Thêm peering trực tiếp B–C

Để ba VPC đều trao đổi với nhau, có thể tạo thêm:

- `pcx-bc`: B ↔ C.
- Route ở các subnet cần thiết trong B tới `10.30.0.0/16` qua `pcx-bc`.
- Route ngược trong C tới `10.20.0.0/16` qua `pcx-bc`.
- Security Groups, NACLs và quyền ứng dụng cho đúng luồng giao tiếp.

~~~mermaid
flowchart TD
    A["VPC A"]
    B["VPC B"]
    C["VPC C"]
    A <-->|"pcx-ab"| B
    A <-->|"pcx-ac"| C
    B <-->|"pcx-bc"| C
~~~

**Bây giờ** B↔C có đường peering trực tiếp. Kết nối B–C không cần đi qua A. Đây là mô hình **full mesh** cho ba VPC.

### 3.3. Công thức mở rộng

Nếu có `n` VPC và mọi VPC phải peer trực tiếp với mọi VPC khác, số peering connections là:

\[
P = \frac{n(n-1)}{2}
\]

| Số VPC | Số peering của full mesh | Nhận xét |
|---:|---:|---|
| 2 | 1 | Rất đơn giản |
| 3 | 3 | A–B, A–C, B–C |
| 5 | 10 | Route và SG nhiều hơn |
| 10 | 45 | Tăng gánh nặng vận hành |
| 20 | 190 | Cần đánh giá lại kiến trúc kết nối |

Mỗi VPC trong full mesh có `n − 1` kết nối; số kết nối tổng thể tăng theo `O(n²)`. AWS áp dụng quota peering connections trên mỗi VPC và quota route entries trong route table. Vì vậy, với hàng chục/hàng trăm VPC thường nên đánh giá **Transit Gateway** hoặc **Cloud WAN** thay vì duy trì full mesh.

## 4. Route table: cấu hình điều kiện để hai VPC liên lạc

**VPC Peering connection có trạng thái `active` vẫn chưa bảo đảm lưu lượng chạy được.** Route table gắn với các subnet nguồn và subnet đích phải có tuyến đến CIDR của bên kia, bao gồm **đường đi và đường trả về**.

### 4.1. Trường hợp A ↔ B

Cho A `10.10.0.0/16`, B `10.20.0.0/16`, peering ID minh họa `pcx-ab`. Route table của các subnet cần liên lạc:

| Route table của subnet | Destination | Target |
|---|---|---|
| Subnet thuộc A | `10.10.0.0/16` | `local` |
| Subnet thuộc A | `10.20.0.0/16` | `pcx-ab` |
| Subnet thuộc B | `10.20.0.0/16` | `local` |
| Subnet thuộc B | `10.10.0.0/16` | `pcx-ab` |

**Tuyến `local`** do AWS thêm cho phạm vi VPC, xử lý traffic nội bộ. Tuyến tới peer phải trỏ vào **VPC peering connection ID**, không trỏ vào EC2 instance, Internet Gateway, NAT Gateway hoặc VPC ID.

Cần chọn **đúng route table gắn với subnet** đang chạy resource. Một VPC có thể có nhiều route table và mỗi subnet dùng một route table (được liên kết rõ ràng hoặc kế thừa main route table). Thêm tuyến vào main route table không có tác dụng nếu subnet thực tế đang dùng một custom route table khác.

### 4.2. Trường hợp A ↔ B và A ↔ C

Để B có thể gọi A, và C có thể gọi A:

| Route table | Destination | Target |
|---|---|---|
| A | `10.20.0.0/16` | `pcx-ab` |
| A | `10.30.0.0/16` | `pcx-ac` |
| B | `10.10.0.0/16` | `pcx-ab` |
| C | `10.10.0.0/16` | `pcx-ac` |

Các local routes luôn tồn tại nhưng được lược khỏi bảng này để dễ quan sát. Những route trên **không tạo đường B→C**. A có các route đến B, C cho **traffic xuất phát từ tài nguyên A** và traffic trả về ứng dụng ở A. Nó không trở thành router bắc cầu cho traffic từ B đến C.

### 4.3. Chọn CIDR tuyến hẹp hơn

Không bắt buộc thêm route đến toàn bộ peer VPC. Nếu ứng dụng chỉ cần kết nối tới subnet dữ liệu `10.30.10.0/24`, có thể tạo route hẹp hơn `10.30.10.0/24 → pcx-ac` ở subnet tương ứng của A. Trong một số tình huống, có thể route đến riêng IP host `/32`. AWS dùng quy tắc **longest prefix match** để chọn tuyến cụ thể nhất.

Giới hạn bằng route table giúp giảm phạm vi có tuyến, nhưng **route table không thay thế cho security policy**: Security Group, NACL và xác thực ứng dụng vẫn cần cấu hình đúng.

### 4.4. Kết nối `pending-acceptance` và route `blackhole`

AWS cho phép khai báo route trỏ tới một peering connection còn `pending-acceptance`, nhưng route có thể ở trạng thái **`blackhole`** (chưa hoạt động) cho tới khi peering được chấp nhận thành `active`. Nếu connection bị xóa/mất hiệu lực, route trỏ tới nó cũng không tạo được luồng truyền dữ liệu hợp lệ. Luôn kiểm tra **cả `Status.Code` của connection và `State` của route**.

## 5. Vòng đời tạo và kích hoạt peering

Quy trình thiết lập kết nối thực tế gồm nhiều bước độc lập:

1. **Lập địa chỉ IP:** kiểm tra primary/secondary IPv4 và IPv6 CIDR của hai VPC không overlap.
2. **Xác định hai đầu:** account, Region, VPC ID của requester và accepter.
3. **Requester tạo yêu cầu peering:** qua Console hoặc API `CreateVpcPeeringConnection`.
4. **Accepter chấp thuận:** owner của VPC nhận phải `AcceptVpcPeeringConnection` để connection chuyển sang `active`. Trong cùng account, bên vận hành có thể thực hiện cả hai vai trò nếu có quyền.
5. **Cập nhật route tables của subnet cần liên lạc:** ở cả hai VPC.
6. **Cấu hình SG/NACL/DNS:** theo luồng truy cập và yêu cầu tên miền.
7. **Kiểm tra giao tiếp thực tế và observability:** đối chiếu route, flow logs và ứng dụng.
8. **Lưu thay đổi vào IaC/runbook:** quản trị vòng đời, quyền, chi phí và dọn dẹp nếu ngừng sử dụng.

Một request `pending-acceptance` có thể **hết hạn sau 7 ngày** nếu không được chấp thuận. Khi peering giữa hai Region, requester tạo request ở Region của VPC nguồn và accepter nhận/accept tại Region của VPC đích. Tên tag của peering là metadata theo phạm vi account/Region và không nên mặc định được chia sẻ đồng bộ.

### 5.1. Thao tác qua AWS Management Console

Đi đến **VPC Console → Peering connections → Create peering connection**. Chọn requester VPC, account và Region của accepter rồi chọn accepter VPC. Sau khi tạo request, ở đúng account/Region của accepter chọn **Actions → Accept request**. Tiếp đó mở **VPC → Route tables** ở từng phía, xác định route table theo subnet association và thêm tuyến đến CIDR của peer với target là peering connection.

Để cấu hình kết nối trong môi trường production, nhóm phụ trách mỗi account phải duyệt luồng ứng dụng, thay đổi SG/NACL và ghi nhận kết quả kiểm tra. **Không tự accept request từ account không quen biết**; việc tạo peering chỉ mới mở khả năng định tuyến nhưng có thể là bước khởi đầu cho truy cập ngoài mong muốn.

### 5.2. AWS CLI minh họa các thao tác thay đổi

Các lệnh bên dưới là **minh họa cú pháp quản trị** và sẽ thay đổi cấu hình AWS nếu thực thi với ID/credentials thật. Chỉ chạy trong lab có quyền thay đổi, VPC/cidr đã được quy hoạch và quy trình phê duyệt phù hợp.

~~~bash
# Bên requester: tạo yêu cầu kết nối giữa VPC trong cùng Region
aws ec2 create-vpc-peering-connection \
  --vpc-id vpc-REQUESTER \
  --peer-vpc-id vpc-ACCEPTER \
  --region ap-southeast-1

# Bên accepter: chấp thuận ID của kết nối sau khi xác minh
aws ec2 accept-vpc-peering-connection \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1

# Route ở subnet của VPC requester, đến CIDR peer
aws ec2 create-route \
  --route-table-id rtb-REQUESTER \
  --destination-cidr-block 10.20.0.0/16 \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1

# Route ngược cần được thực hiện tại bên accepter
aws ec2 create-route \
  --route-table-id rtb-ACCEPTER \
  --destination-cidr-block 10.10.0.0/16 \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1
~~~

Các ID chứa `REQUESTER`, `ACCEPTER`, `EXAMPLE` là placeholder và **không thể dùng nguyên văn**. Với cross-account, lệnh accept và route ở accepter chạy bằng IAM principal của account đó; với inter-Region, cần đặt `--region` đúng cho từng phía. Không chạy trùng `create-route` khi route đã tồn tại; cần kiểm tra trước và chọn API sửa phù hợp nếu cần.

### 5.3. Các trạng thái cần phân biệt

| Trạng thái | Ý nghĩa vận hành |
|---|---|
| `initiating-request` | AWS đang khởi tạo yêu cầu |
| `pending-acceptance` | Chờ owner của VPC bên nhận đồng ý |
| `active` | Peering đã được kích hoạt; vẫn phải có routes/security hợp lệ |
| `failed` | Không tạo được connection, ví dụ overlap CIDR |
| `rejected` | Accepter từ chối |
| `expired` | Request không được accept trước thời hạn |
| `deleted` | Connection đã bị xóa/không còn hiệu lực |

Không sử dụng mỗi trạng thái `active` để kết luận ứng dụng đã có network reachability. Kết luận đó cần route hai chiều, SG/NACL và kiểm tra theo đúng protocol/port.

## 6. Giới hạn CIDR: không được overlap giữa hai VPC peer trực tiếp

AWS từ chối peering giữa hai VPC khi các CIDR IPv4 hoặc IPv6 tương ứng bị **chồng lấn**. Quy tắc này bao gồm tất cả CIDR được gắn với VPC, kể cả secondary CIDR.

### 6.1. Ví dụ

| Cặp VPC | CIDR | Peer trực tiếp được không? | Giải thích |
|---|---|---|---|
| A và B | A: `10.10.0.0/16`; B: `10.20.0.0/16` | Có, nếu thỏa điều kiện khác | Không overlap |
| A và D | A: `10.10.0.0/16`; D: `10.10.128.0/17` | Không | D nằm trong CIDR A |
| A và E | A primary: `10.10.0.0/16`, secondary: `172.20.0.0/16`; E: `172.20.8.0/21` | Không | Overlap với CIDR phụ của A |
| A và F | IPv4 không overlap; IPv6 hai bên overlap | Không | Overlap IPv6 vẫn là hạn chế |

Nếu B và C có cùng CIDR nhưng **không peer trực tiếp với nhau**, A vẫn có thể có hai kết nối A–B và A–C nếu CIDR A không overlap với từng bên. Đây là tình huống phức tạp: route của A phải đủ cụ thể để chọn đúng peer, và không có unicast reverse path forwarding bảo đảm gói trả về đi đúng nơi. Tránh thiết kế này cho hệ thống mới nếu có thể; hãy phân bổ CIDR không overlap trên toàn bộ miền kết nối để giảm rủi ro.

### 6.2. Xử lý khi đã có mạng chồng lấn

Đừng cố chuyển đường qua VPC thứ ba bằng peering. Các lựa chọn tùy yêu cầu gồm:

- **Đổi/re-IP CIDR hoặc xây VPC mới:** giải pháp kiến trúc mạng sạch khi cần kết nối layer 3 toàn diện và có thể di chuyển dịch vụ.
- **AWS PrivateLink:** xuất bản một dịch vụ đích để các VPC tiêu thụ qua interface endpoint; thường phù hợp khi chỉ cần một API/dịch vụ và các mạng overlap.
- **Mô hình NAT/routing được hỗ trợ qua giải pháp khác:** khi thực sự cần dịch địa chỉ ở quy mô mạng, phải thiết kế và kiểm thử kỹ qua Transit Gateway hoặc thiết bị mạng được hỗ trợ; tránh cho rằng peering tự xử lý NAT/transit.

PrivateLink không phải kết nối full mesh hai chiều giữa mọi địa chỉ trong hai VPC; nó cung cấp truy cập theo **dịch vụ**. Cần đánh giá interface endpoint, load balancer, DNS, phép xác thực và chi phí riêng.

## 7. Giới hạn edge-to-edge routing

**Edge-to-edge routing** là ý định dùng VPC peer làm đường trung chuyển đến một gateway hoặc kết nối mạng khác.

AWS không hỗ trợ các luồng sau **qua VPC peering**:

| Ý định | Có dùng VPC peering để đi bắc cầu được không? |
|---|---|
| VPC B đi ra internet thông qua Internet Gateway trong VPC A | **Không** |
| VPC B dùng NAT Gateway/NAT device của VPC A để đi internet | **Không** |
| VPC B dùng VPN của VPC A để đến on-premises | **Không** |
| VPC B đi on-premises qua Direct Connect/Virtual Private Gateway của VPC A | **Không** |
| VPC B sử dụng gateway endpoint S3 trong VPC A | **Không** |
| VPC B đi VPC C qua `pcx-ab` rồi `pcx-ac` | **Không** |

Ví dụ công ty có VPC “network hub” A với một NAT Gateway để kiểm soát internet egress. Nếu chỉ peer B với A rồi đặt `0.0.0.0/0 → pcx-ab` trong B, **không thể** dùng NAT Gateway của A làm lối ra internet cho B. Mạng egress tập trung phải dùng kiến trúc transit được hỗ trợ (ví dụ Transit Gateway kết hợp inspection/egress VPC) và cấu hình đúng route tables, NAT, firewall, khả năng phục hồi.

Lưu ý phân biệt: dịch vụ NAT Gateway có một số cơ chế traffic đi *từ NAT trong VPC của nó tới peer* được AWS hỗ trợ ở trường hợp riêng. Điều đó **không cho phép client từ VPC peer dùng NAT của VPC kia làm gateway internet**.

## 8. Bảo mật: route tồn tại chưa đồng nghĩa port được mở

Luồng kết nối ứng dụng đi từ VPC B đến VPC A cần đồng thời:

1. **Peering `active`** và route hai chiều giữa các subnet cần thiết.
2. **Security Group** gắn với client/server cho phép egress/inbound đúng protocol/port.
3. **Network ACL** của cả hai subnet không chặn traffic đi và traffic trả về.
4. Host firewall, load balancer listener, ứng dụng và database thực sự lắng nghe cổng.
5. DNS, TLS và xác thực ứng dụng đúng nếu dùng hostname/HTTPS/database user.

### 8.1. Security Group stateful

Giả sử client Java ở B `10.20.1.10` cần gọi private API ở A `10.10.10.20:443`:

- SG client B: outbound TCP 443 tới IP/CIDR của API hoặc SG peer nếu được hỗ trợ.
- SG server A: inbound TCP 443 từ IP/CIDR của B hoặc SG B nếu được hỗ trợ.
- SG là **stateful** nên thông thường traffic trả về của connection hợp lệ được cho phép, không cần mở một rule riêng cho ephemeral return port.

**Tham chiếu Security Group của VPC peer:** AWS hỗ trợ SG reference nếu hai VPC peer ở **cùng Region**, kể cả khác account (cần dùng account ID cùng SG ID khi phù hợp). Không thể tham chiếu SG của VPC peer ở **khác Region**; dùng IP CIDR và quản trị thay đổi địa chỉ thay thế.

Không mở `0.0.0.0/0` inbound chỉ để “thử cho chạy” một kết nối private; điều đó có thể mở phạm vi vượt yêu cầu nếu tài nguyên có đường tiếp cận khác.

### 8.2. Network ACL stateless

NACL áp dụng tại subnet boundary và là **stateless**. Ngoài rule inbound/outbound đúng port dịch vụ, cần cho phép chiều phản hồi qua dải ephemeral ports phù hợp với hệ điều hành/client. Ví dụ một client tạo TCP connection đến server cổng 443: response có source port 443 nhưng destination là ephemeral port của client. Nếu NACL chặn chiều trả về, SYN có thể đi được nhưng handshake vẫn thất bại.

NACL khác SG ở chỗ có allow/deny rules và xét theo thứ tự số rule. Khi troubleshoot, cần kiểm tra **cả bốn chiều inbound/outbound ở hai subnet**, không chỉ inbound rule của server.

### 8.3. IAM và lớp ứng dụng

IAM policy cấp quyền **tạo/accept/modify peering** là control-plane authorization; IAM không phải một firewall IP cho toàn bộ traffic qua peering. Quyền của ứng dụng vẫn do SG, NACL, host firewall và authentication/authorization ở dịch vụ đích quyết định. Ví dụ nối VPC thành công không cho phép truy cập bảng RDS nếu thiếu database credentials hoặc security group DB chưa mở cổng phù hợp.

Trong môi trường nhiều account, nguyên tắc **least privilege** cần áp dụng cả người quản trị networking và workload. Nên có phê duyệt hai phía cho thay đổi tạo tuyến xuyên ranh giới account.

## 9. DNS khi dùng VPC Peering

Bật kết nối IP không tự động giải quyết mọi hostname ở peer.

### 9.1. DNS resolution option của peering

Mặc định, **public IPv4 DNS hostname** của EC2 ở peer có thể phân giải thành public IPv4 của instance. Khi bật tùy chọn DNS resolution trên peering và đáp ứng điều kiện VPC DNS, hostname public IPv4 EC2 trong peer có thể phân giải về **private IPv4** khi truy cập từ VPC đối tác.

Cần lưu ý:

- Peering connection phải ở trạng thái `active`.
- Cả hai VPC phải đáp ứng thiết lập `enableDnsSupport` và `enableDnsHostnames`.
- Tùy chọn requester/accepter DNS resolution được quản lý ở từng phía tương ứng.
- DNS resolution option không tự động cấp quyền dùng mọi private hosted zone ở peer.

### 9.2. Private hosted zones và DNS server

**Route 53 private hosted zone (PHZ)** không tự được chia sẻ chỉ vì hai VPC peer. Nếu ứng dụng B cần phân giải `db.internal.example` thuộc PHZ được cấu hình riêng tại A, cần lập phương án như liên kết PHZ với VPC B (kể cả quy trình cross-account phù hợp), Route 53 Resolver endpoints/rules hoặc thiết kế DNS khác.

Không thể trực tiếp truy vấn **Amazon-provided DNS server của VPC peer** theo cách gửi DNS traffic xuyên peering để nhờ resolver của peer xử lý. Vì vậy cần phân biệt ba việc:

1. IP connectivity A↔B đã hoạt động chưa?
2. Hostname có phân giải ra **đúng private IP** không?
3. Sau khi phân giải, SG/NACL/application port có mở không?

Khi `curl https://service.internal` lỗi nhưng gọi private IP trực tiếp thành công, hướng điều tra thường là DNS/TLS hostname thay vì route table. Việc gọi IP trực tiếp chỉ là một phép chẩn đoán phù hợp; với TLS certificate có thể cần hostname/SNI chính xác.

## 10. Peering inter-Region, IPv6, quota và chi phí

### 10.1. Khác Region

VPC Peering hỗ trợ inter-Region, không cần sử dụng Internet Gateway, VPN hoặc Direct Connect để truyền traffic giữa hai VPC. Lưu lượng inter-Region đi trên backbone AWS và được AWS mã hóa trên đường truyền. Mặc dù vậy, độ trễ giữa hai khu vực địa lý vẫn có thể ảnh hưởng ứng dụng đồng bộ, database replication và timeout. Thiết kế ứng dụng cũng cần đảm bảo retry, idempotency và phương án failover phù hợp.

Với inter-Region, các thao tác quản lý peering và route cần thực hiện trong **Region tương ứng của mỗi phía**. Security Group reference sang peer khác Region không được hỗ trợ. DNS resolution option giữa Regions phải được cấu hình phù hợp nếu cần hostname EC2 trả private IP.

### 10.2. IPv6

Peering có thể truyền IPv6 nếu cả hai VPC có IPv6 CIDRs không overlap, tài nguyên/subnet được cấu hình IPv6 và route tables hai phía có tuyến IPv6 tới peering connection. Security Group/NACL phải cho phép các luồng IPv6 tương ứng. Đừng cho rằng đã mở IPv4 CIDR thì IPv6 tự mở.

### 10.3. Quota

Mỗi VPC có quota cho số peering active/pending và route table có quota entry. Theo tài liệu AWS, quota mặc định active peering connections trên mỗi VPC hiện ở mức **50**, có thể đề nghị tăng trong phạm vi AWS hỗ trợ; các quota cụ thể còn phụ thuộc account/Region và có thể được cập nhật. Trước khi quyết định full mesh, cần kiểm tra **Service Quotas** và bài toán số route theo subnet thay vì mặc định quota sẽ đủ.

### 10.4. Chi phí

AWS không tính phí riêng cho việc **tạo peering connection**. Chi phí phát sinh chủ yếu từ lưu lượng truyền dữ liệu qua peering:

- Data transfer qua peering trong **cùng Availability Zone** theo điều kiện dịch vụ được AWS miễn phí, kể cả qua account khác.
- Lưu lượng **qua các AZ khác nhau** trong Region có thể chịu phí transfer theo biểu phí liên quan.
- **Inter-Region peering** có phí data transfer inter-Region.
- Tài nguyên nguồn/đích như EC2, RDS, load balancer, CloudWatch và các dịch vụ khác có phí riêng.

Tên AZ như `ap-southeast-1a` có thể ánh xạ tới AZ vật lý khác giữa các account; dùng **AZ ID** khi cần đối chiếu cùng physical AZ. Kiểm tra **Amazon VPC/EC2 Pricing** mới nhất trước khi chốt ngân sách. Quản trị theo dữ liệu thực tế: lượng GB truyền, hướng traffic, số cặp VPC, Region, placement và kế hoạch tăng trưởng.

## 11. Peering, Transit Gateway, Cloud WAN hay PrivateLink?

| Tiêu chí | VPC Peering | AWS Transit Gateway | AWS Cloud WAN | AWS PrivateLink |
|---|---|---|---|---|
| Ý tưởng | Kết nối trực tiếp hai VPC | Hub trung chuyển giữa nhiều VPC và mạng kết nối | Quản trị mạng toàn cục theo chính sách và segments | Xuất bản/tiêu thụ dịch vụ riêng qua endpoint |
| Transitive routing | **Không** | **Có**, khi attachments/route tables cho phép | Có, theo thiết kế segments/chính sách | Không phải full network routing |
| Phù hợp | Ít VPC, cặp kết nối ổn định | Nhiều VPC, hub-and-spoke, hybrid networking | Mạng nhiều Region, nhiều account quy mô lớn | Cho phép một dịch vụ/endpoint được truy cập có kiểm soát |
| Overlapping CIDR | Không cho cặp peering trực tiếp overlap | Cần giải quyết/thiết kế hạn chế overlap đối với routing giữa attachments | Cần quy hoạch địa chỉ và chính sách phù hợp | Có thể phục vụ bài toán truy cập dịch vụ khi mạng overlap |
| Vận hành | Quản lý từng cặp + route hai bên | Quản lý attachments, TGW route tables và VPC routes | Quản lý core network, policies, segments | Quản lý endpoint/service, DNS và phân quyền ứng dụng |
| Chi phí | Truyền dữ liệu; không phí tạo connection | Attachment-hour, data processing, transfer theo biểu phí | Phí core network/attachment/data theo biểu phí | Endpoint-hour và data processing theo dịch vụ |

### 11.1. Chọn Peering khi nào?

- Có hai hoặc một số ít VPC với CIDR không overlap, cần trao đổi private IP hai chiều.
- Không cần VPC thứ ba làm transit.
- Muốn quản lý rõ ràng từng kết nối và route trong số lượng nhỏ.
- Cross-account hoặc inter-Region direct connectivity cần đơn giản, có quyền quản trị hai đầu.

### 11.2. Chọn Transit Gateway khi nào?

- Nhiều VPC cần giao tiếp lẫn nhau hoặc đi tới mạng on-premises theo một mô hình hub.
- Cần **transitive routing** có kiểm soát bằng TGW route tables, propagation và associations.
- Muốn giảm số kết nối point-to-point và áp dụng phân đoạn mạng, kiểm tra bảo mật ở vị trí phù hợp.

Tuy nhiên, **gắn mọi VPC vào một Transit Gateway không đồng nghĩa mọi VPC tự được phép thấy nhau**. Reachability vẫn do VPC route tables, TGW route tables, SG/NACL, policy và các cấu hình khác quyết định. Việc gắn kết nối có chi phí và quota riêng.

### 11.3. Chọn Cloud WAN hoặc PrivateLink khi nào?

**AWS Cloud WAN** phù hợp khi cần quản lý mạng lớn xuyên Region/account với network policy, segmentation và quản trị tập trung. **AWS PrivateLink** phù hợp khi bên cung cấp chỉ cần cho bên tiêu thụ truy cập một dịch vụ cụ thể qua private endpoint mà không muốn mở kết nối IP tổng quát giữa hai VPC; thích hợp với nhiều mô hình chia sẻ dịch vụ qua ranh giới account, kể cả khi dải CIDR overlap.

Nếu B chỉ cần gọi một API của C, **PrivateLink** có thể hợp lý hơn cho quyền truy cập hẹp. Nếu B cần giao tiếp với hàng chục subnet/tài nguyên ở C và nhiều VPC khác, **Transit Gateway/Cloud WAN** có thể thích hợp hơn.

## 12. Bài lab chỉ đọc: quan sát peering và kiểm tra đường A↔B

### 12.1. Điều kiện

- Có AWS account/lab với ít nhất một VPC; nếu không có peering thì có thể dùng mô hình giả định và phân tích output mẫu.
- AWS CLI v2 đã cấu hình profile SSO/role được quyền đọc `ec2:DescribeVpcs`, `ec2:DescribeVpcPeeringConnections`, `ec2:DescribeRouteTables`, `ec2:DescribeSecurityGroups` và `ec2:DescribeNetworkAcls` khi cần.
- Region ví dụ: `ap-southeast-1`. Nếu khác Region, thay bằng Region của VPC đích.
- Lab **không tạo, accept, xóa peering hay thay đổi route/SG/NACL**; chỉ truy vấn metadata.

### 12.2. Bước A – Xác nhận identity và VPC CIDRs

~~~bash
# Đảm bảo đang dùng đúng account/role
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

# Liệt kê VPC ID, primary/secondary IPv4 và IPv6 associations
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,PrimaryIpv4:CidrBlock,AllIpv4:CidrBlockAssociationSet[].CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock}' \
  --output json
~~~

Ghi lại VPC ID, CIDR, owner account và Region đúng; so sánh các dải CIDR. Nếu output rỗng, có thể không có VPC trong Region đó hoặc tài khoản không đúng; nếu `AccessDenied`, kiểm tra quyền được cấp.

### 12.3. Bước B – Liệt kê peering connections

~~~bash
aws ec2 describe-vpc-peering-connections \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcPeeringConnections[].{PeeringId:VpcPeeringConnectionId,Status:Status.Code,Requester:RequesterVpcInfo.VpcId,RequesterOwner:RequesterVpcInfo.OwnerId,RequesterRegion:RequesterVpcInfo.Region,Accepter:AccepterVpcInfo.VpcId,AccepterOwner:AccepterVpcInfo.OwnerId,AccepterRegion:AccepterVpcInfo.Region}' \
  --output table
~~~

Ghi nhận mỗi `VpcPeeringConnectionId`, `Status.Code`, requester/accepter VPC ID, owner và Region. Nếu thấy `pending-acceptance`, đọc mục kiểm tra quyền/quy trình của tổ chức; không tự accept request từ account lạ. Đối với inter-Region, cần kiểm tra đúng vị trí quản lý và metadata Region của hai đầu.

### 12.4. Bước C – Đọc route table theo VPC/subnet

Thay `vpc-EXAMPLE-A` bằng VPC ID đã được phép xem:

~~~bash
aws ec2 describe-route-tables \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'RouteTables[].{TableId:RouteTableId,Associations:Associations[].SubnetId,Routes:Routes[].{Ipv4:DestinationCidrBlock,Ipv6:DestinationIpv6CidrBlock,Target:VpcPeeringConnectionId,State:State}}' \
  --output json
~~~

Tìm tuyến có `VpcPeeringConnectionId = pcx-...`, so sánh với CIDR của VPC peer. Xác định subnet của ứng dụng dùng route table nào; nếu không có association explicit thì nó dùng **main route table**. Kiểm tra phía ngược lại tại account/Region peer để chắc chắn có return route.

### 12.5. Bước D – Kiểm tra Security Group và NACL

~~~bash
aws ec2 describe-security-groups \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'SecurityGroups[].{Id:GroupId,Name:GroupName,Inbound:IpPermissions,Outbound:IpPermissionsEgress}' \
  --output json

aws ec2 describe-network-acls \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'NetworkAcls[].{Id:NetworkAclId,Entries:Entries,Associations:Associations}' \
  --output json
~~~

Đối chiếu cổng dịch vụ, CIDR hoặc SG source hợp lệ và chiều outbound/return. Đừng mở mọi cổng chỉ vì ping không thành công: ICMP có thể bị chặn trong khi HTTPS 443 vẫn hoạt động.

### 12.6. Bước E – Đối chiếu Console và kiến trúc

Trong VPC Console, xem **Peering connections**, **Route tables**, **Security Groups** và các tài nguyên đích. Vẽ sơ đồ đúng các cặp kết nối thực sự. Trả lời:

1. Có peering trực tiếp từ B đến C không?
2. Nếu không, vì sao route `B → pcx-ba → A → pcx-ac → C` không hoạt động?
3. Route table gắn với subnet nguồn và subnet đích là bảng nào?
4. Route `blackhole` báo hiệu điều gì?
5. Có quy tắc SG/NACL nào chặn protocol/port mong muốn không?
6. Nếu DNS hostname phân giải sai IP, bạn sẽ kiểm tra những thuộc tính nào?

Chỉ khi đã có quyền vận hành và môi trường lab cho phép, có thể thực hiện một bài thực hành nâng cao tạo peering A–B, accept và cấu hình route hai chiều. Với account dùng chung/production, cần review và lên kế hoạch hoàn tác trước khi thay đổi.

## 13. Troubleshooting: tìm đúng nguyên nhân kết nối thất bại

Một chương trình Java ở B gọi service A qua HTTPS có thể gặp timeout dù peering `active`. Hãy chẩn đoán theo thứ tự:

| Triệu chứng | Kiểm tra trước |
|---|---|
| Không tìm thấy peering | Đúng account/Region? Requester/accepter VPC IDs? |
| `pending-acceptance` hoặc `expired` | Bên nhận đã accept trước thời hạn chưa? |
| Peering `failed` | IPv4/IPv6 CIDR có overlap không? |
| Peering `active` nhưng không đi được | Route table của **đúng subnet** ở cả hai đầu; đúng target `pcx-...`? |
| Route `blackhole` | Peering chưa active, đã xóa hoặc không còn hợp lệ? |
| TCP timeout dù có route | SG inbound/outbound, NACL chiều đi/về, host firewall, port/listener |
| DNS hostname về public IP | Đã bật DNS resolution option và VPC DNS attributes chưa? |
| Private hostname không phân giải | PHZ association, Route 53 Resolver rules/endpoints |
| B↔A hoạt động, A↔C hoạt động, B↔C không hoạt động | **Đây là non-transitive peering**; cần B–C trực tiếp hoặc mô hình transit |
| Lưu lượng bị chuyển sai giữa hai peers | CIDR peers overlap nhau, route specificity/longest-prefix-match, thiếu return route đúng |
| Chỉ lỗi khi liên vùng hoặc tăng tải | Kiểm tra latency, MTU/PMTUD, throughput ứng dụng, data transfer, DNS và timeout |

### 13.1. Dùng observability đúng chỗ

- **VPC Flow Logs:** ghi metadata của IP traffic trên ENI/subnet/VPC theo cấu hình; hỗ trợ tra cứu `ACCEPT`/`REJECT`, IP/port/protocol, nhưng `ACCEPT` không đảm bảo ứng dụng xử lý thành công.
- **Reachability Analyzer:** phân tích đường reachability và thành phần networking có thể ngăn kết nối; dùng để tìm sai route, SG/NACL và các hạn chế đường đi được công cụ hỗ trợ.
- **CloudWatch metrics/logs và application logs:** giúp kiểm tra TCP timeout, database connection pool, DNS errors, retries.
- **CloudTrail:** phục vụ điều tra ai tạo/accept peering, sửa route hoặc SG/NACL ở control plane khi các event đó được ghi nhận.
- **VPC IP Address Manager (IPAM):** hỗ trợ quy hoạch, cấp phát và theo dõi CIDR để giảm overlap trong kiến trúc nhiều VPC.

Không kết luận một luồng là an toàn chỉ vì đã chạy qua private peering; vẫn cần mã hóa ở tầng ứng dụng, IAM/credentials đúng và các biện pháp bảo mật cơ sở dữ liệu.

## 14. Tình huống kiến trúc: ứng dụng Java/Spring Boot nhiều VPC

Một doanh nghiệp thiết kế ba miền:

- **VPC App (B):** chứa ECS services chạy Java/Spring Boot, gửi request tới API chung.
- **VPC Shared (A):** chứa authentication proxy và một số API nội bộ.
- **VPC Data (C):** chứa private RDS/Aurora và dịch vụ quản trị dữ liệu.

Ban đầu, App B chỉ gọi API ở A, Data C cũng gọi API ở A. Hai peering B–A và C–A đủ cho **những luồng trực tiếp đó**. Sau này một developer thêm chức năng App B truy cập DB trong C bằng private IP; request thất bại dù A giao tiếp được với cả hai bên.

Lý do là B **không thể đi qua A** để sang C. Hướng xử lý:

1. **Nếu chỉ cần B truy cập một dịch vụ ở C:** cân nhắc PrivateLink hoặc API được cung cấp qua A theo mô hình **ứng dụng nhận request rồi tự gọi dịch vụ C** (hai kết nối ứng dụng riêng biệt B→A, A→C, không phải chuyển tiếp gói IP qua A). Cần đánh giá bảo mật, auth, latency và chi phí.
2. **Nếu B và C cần kết nối IP hai chiều trực tiếp, quy mô nhỏ:** thêm peering B–C và route hai chiều, SG/NACL theo port.
3. **Nếu tương lai có hàng chục VPC và kết nối hybrid:** thiết kế Transit Gateway/Cloud WAN cùng routing domains, segmentation, inspection và quy hoạch CIDR, chi phí.

**Phân biệt tầng mạng và tầng ứng dụng:** VPC A có thể chạy một API proxy nhận request từ B, rồi ứng dụng proxy khởi tạo **request mới** tới C. Đây là logic application-layer, không tạo khả năng chuyển tiếp bất kỳ gói TCP/IP nào từ B qua A tới C. Việc dùng proxy chỉ phù hợp nếu kiến trúc và chính sách ứng dụng chủ đích yêu cầu nó.

## 15. Câu hỏi tự đánh giá

1. Nếu A peer B và B peer C, A có thể gửi gói đến C qua B không? Vì sao?
2. Ba VPC A, B, C cần kết nối đôi một bằng Peering: cần bao nhiêu connections và route hai chiều cơ bản?
3. Một peering đang `active`, nhưng không có return route phía peer. Lỗi gì thường xảy ra?
4. VPC A và B có IPv4 primary khác nhau nhưng secondary IPv4 CIDR bị overlap. Có thể peer trực tiếp không?
5. Vì sao mở inbound Security Group cho cổng 443 không sửa được giới hạn non-transitive routing?
6. Một client trong VPC B có thể dùng NAT Gateway của VPC A qua peering để đi internet không?
7. VPC peering inter-Region có thể reference Security Group của peer ở Region khác không?
8. VPC B cần phân giải private hostname từ Route 53 private hosted zone ở A. Peering alone có đủ không?
9. Trường hợp nào PrivateLink phù hợp hơn Peering?
10. Trong môi trường 10 VPC kết nối full mesh, số peering connections là bao nhiêu?
11. Nếu flow logs ở cả hai đầu ghi `ACCEPT` nhưng ứng dụng vẫn lỗi, cần kiểm tra thêm những lớp nào?
12. Vì sao cần kiểm soát data transfer xuyên AZ/Region, ngay cả khi thao tác tạo peering không thu phí?

### Đáp án định hướng

- **Non-transitive:** không có transit mặc định hoặc cấu hình bật transit qua peering; phải có peering trực tiếp hoặc kiến trúc TGW/Cloud WAN.
- **Route hai chiều:** cả subnet nguồn và subnet đích đều phải có route đến CIDR peer qua đúng `pcx-...`; đánh giá SG/NACL, DNS và ứng dụng độc lập.
- **CIDR overlap:** không thể peer trực tiếp nếu có bất kỳ dải IPv4/IPv6 chồng lấn trong cặp VPC.
- **Tăng trưởng:** với `n` VPC full mesh cần `n(n-1)/2` connections; 10 VPC cần 45 connections.
- **Lựa chọn dịch vụ:** Peering kết nối trực tiếp ít VPC; Transit Gateway/Cloud WAN phục vụ transit network; PrivateLink phục vụ truy cập một dịch vụ riêng.

## 16. Tài liệu AWS chính thức

1. [What is VPC Peering?](https://docs.aws.amazon.com/vpc/latest/peering/what-is-vpc-peering.html) — Khái niệm, phạm vi account/Region và traffic.
2. [How VPC peering connections work](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-basics.html) — Non-transitive peering, overlap CIDR, edge-to-edge routing và giới hạn khác.
3. [Create a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/create-vpc-peering-connection.html) — Requester và accepter.
4. [Accept or reject a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/accept-vpc-peering-connection.html) — Phê duyệt và an toàn với account đối tác.
5. [Update your route tables](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-routing.html) — Route hai chiều, `blackhole` và `pcx-...` target.
6. [VPC Peering common configurations](https://docs.aws.amazon.com/vpc/latest/peering/peering-configurations-full-access.html) — Sơ đồ star/full mesh.
7. [Peering configurations with specific routes](https://docs.aws.amazon.com/vpc/latest/peering/peering-configurations-partial-access.html) — Longest prefix match và đặc điểm CIDR peers chồng lấn.
8. [Reference peer security groups](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-security-groups.html) — Giới hạn SG reference theo Region.
9. [Enable DNS resolution for peering](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-dns.html) — DNS hostname khi peering.
10. [Troubleshoot a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/troubleshoot-vpc-peering-connections.html) — Route, SG/NACL và Reachability Analyzer.
11. [VPC Peering quotas](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-connection-quotas.html) — Hạn mức số kết nối.
12. [AWS: Network connectivity between VPCs and Regions](https://docs.aws.amazon.com/prescriptive-guidance/latest/secure-outbound-network-traffic/vpc-region-communication.html) — So sánh Peering và Transit Gateway.

> **Ghi nhớ:** **A–B và A–C không suy ra B–C.** VPC Peering chỉ mang lưu lượng giữa hai VPC **được peer trực tiếp**. Trước triển khai hãy xác minh CIDR không overlap, request đã active, route hai chiều, SG/NACL/DNS, chính sách IAM và yêu cầu bảo mật. Nếu thiết kế đòi hỏi trung chuyển giữa nhiều mạng, hãy dùng dịch vụ hỗ trợ transitive routing thay vì cố gắng thêm static routes vào peering.

