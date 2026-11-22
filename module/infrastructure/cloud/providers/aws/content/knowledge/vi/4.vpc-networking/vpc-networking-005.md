# Security Group và quy tắc stateful

> **Chương:** Mạng VPC  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/Availability Zone (AZ), IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành thiết kế ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Security Group (SG) bảo vệ lưu lượng ở đâu trong Amazon VPC và phân biệt với route table, Network ACL (NACL), IAM và AWS WAF.
2. Đọc và thiết kế **inbound rule**, **outbound rule** theo giao thức, cổng, địa chỉ CIDR, prefix list hoặc Security Group tham chiếu.
3. Giải thích cơ chế **stateful**: lưu lượng phản hồi của kết nối được cho phép có thể đi qua Security Group mà không cần một rule cho chiều ngược lại.
4. Phân biệt Security Group mặc định của VPC với Security Group mới tạo; hiểu quy tắc **allow-only**, **implicit deny**, và cách tổng hợp nhiều Security Group.
5. Thiết kế phân đoạn mạng cho hệ thống nhiều lớp **Internet → ALB → EC2/app → RDS**, có thể triển khai trên nhiều AZ.
6. Phân tích nguyên nhân kết nối thất bại, kiểm tra cấu hình bằng AWS CLI và dùng VPC Flow Logs cùng các công cụ quan sát khi cần.
7. Áp dụng nguyên tắc least privilege cho cả luồng inbound và outbound, đồng thời nhận diện ảnh hưởng của cấu hình mạng tới độ sẵn sàng và chi phí.

## 1. Security Group là gì?

**Security Group** là cơ chế kiểm soát lưu lượng mạng của AWS gắn với các **network interface** (thường là Elastic Network Interface — ENI) của những tài nguyên được hỗ trợ trong một VPC. Một Security Group gồm các quy tắc cho phép lưu lượng **đi vào (inbound)** và **đi ra (outbound)**.

Hãy hình dung một ứng dụng chạy trên EC2:

- Website cần nhận HTTPS ở cổng TCP **443**.
- Backend cần giao tiếp với database PostgreSQL ở cổng TCP **5432**.
- Database chỉ được nhận kết nối từ backend, không nên nhận trực tiếp từ Internet.

Security Group giúp diễn đạt những yêu cầu đó thành các rule mạng. Một rule có thể nói: “Cho phép TCP/5432 **từ các network interface có gắn Security Group của backend** đến database”, thay vì mở cổng database cho tất cả địa chỉ IP.

Security Group là lớp bảo vệ mạng. Nó **không thay thế** xác thực người dùng trong ứng dụng, phân quyền IAM, mã hóa TLS, vá lỗi hệ điều hành, bảo vệ dữ liệu hoặc thiết kế định tuyến VPC.

### 1.1. Security Group nằm ở đâu trong mô hình mạng?

~~~mermaid
flowchart LR
    C["Máy khách / hệ thống khác"] --> RT["Tuyến mạng qua route table và các thành phần kết nối"]
    RT --> NACL["NACL ở ranh giới subnet"]
    NACL --> ENI["ENI có gắn Security Group"]
    ENI --> APP["Ứng dụng trên EC2 / tài nguyên hỗ trợ"]
~~~

Sơ đồ là mô hình khái niệm về các lớp kiểm soát, không thể hiện chính xác thứ tự xử lý gói tin trong mọi kiến trúc. Điều quan trọng là:

- **Route table** quyết định gói tin có tuyến mạng phù hợp hay không.
- **NACL** đánh giá traffic ở cấp subnet theo rule cho phép/từ chối.
- **Security Group** kiểm soát traffic cho các interface/tài nguyên được gắn, theo các rule chỉ cho phép.
- **Ứng dụng hoặc hệ điều hành** vẫn phải thực sự lắng nghe trên cổng đó, cấu hình đúng và xử lý request hợp lệ.

**Kết luận:** Nếu một route không tồn tại, Security Group có Allow cũng không tạo ra được kết nối. Ngược lại, một route tồn tại nhưng Security Group không Allow thì traffic vẫn bị chặn ở lớp Security Group.

### 1.2. Phạm vi của Security Group

Security Group được tạo trong một **VPC**. Khi tạo tài nguyên như EC2, RDS hay một Application Load Balancer (ALB), bạn có thể gắn Security Group thích hợp vào network interface hoặc tài nguyên tương ứng, trong phạm vi và điều kiện dịch vụ hỗ trợ.

Một ENI có thể có **nhiều Security Group**. Các rule **Allow** từ những Security Group gắn vào cùng interface được xét tổng hợp. Ví dụ, SG-A cho phép inbound 443 từ Internet và SG-B cho phép inbound 22 từ mạng quản trị: cả hai luồng có thể được cho phép trên interface được gắn cả SG-A lẫn SG-B, nếu các lớp kiểm soát khác cũng cho phép.

Không có khái niệm “Security Group A ưu tiên hơn Security Group B” theo thứ tự gắn. **Không thể dùng một Security Group chứa Deny để ghi đè Allow từ Security Group khác**, vì Security Group thông thường chỉ có rule cho phép.

## 2. Thành phần của một Security Group rule

Security Group thường có hai tập rule:

| Loại | Đối tượng điều khiển | Ví dụ |
| --- | --- | --- |
| **Inbound rule** | Lưu lượng **bắt đầu đi vào** interface/tài nguyên. | Cho phép TCP/443 từ Internet vào ALB. |
| **Outbound rule** | Lưu lượng **bắt đầu đi ra** từ interface/tài nguyên. | Cho phép app gọi database qua TCP/5432. |

Mỗi rule có các phần thông dụng:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Direction** | Inbound hoặc outbound. | Inbound |
| **Protocol** | TCP, UDP, ICMP/ICMPv6 hoặc loại giao thức được hỗ trợ. | TCP |
| **Port / port range** | Cổng hoặc dải cổng, khi giao thức có khái niệm cổng. | 443; 8080; 5432 |
| **Source / destination** | Nguồn cho inbound, đích cho outbound. | 203.0.113.0/24; Security Group khác |
| **Description** | Mô tả lý do cấp quyền. | HTTPS từ khách truy cập |
| **Rule ID** | Định danh của một rule để xem, rà soát và quản lý. | sgr-… |

Các kiểu nguồn/đích thường gặp:

- **IPv4 CIDR:** ví dụ **10.0.0.0/16** cho mạng nội bộ hoặc **0.0.0.0/0** cho mọi địa chỉ IPv4.
- **IPv6 CIDR:** ví dụ **::/0** cho mọi địa chỉ IPv6; cần kiểm soát IPv6 riêng nếu VPC/tài nguyên dùng IPv6.
- **Security Group ID:** tham chiếu các network interface có gắn nhóm được chỉ định, khi mô hình mạng hỗ trợ kiểu tham chiếu ấy.
- **Managed prefix list:** tập CIDR được quản lý dưới dạng danh sách cho những trường hợp dịch vụ hỗ trợ; hữu ích khi cần quản lý nhiều dải địa chỉ.

**Security Group không dùng tên miền, đường dẫn URL hoặc nội dung HTTP làm điều kiện lọc.** Nếu cần phân quyền theo đường dẫn web, cơ chế xác thực ứng dụng hoặc lớp như AWS WAF/ALB phù hợp hơn.

### 2.1. Ví dụ đọc ba rule

| SG | Chiều | Giao thức/cổng | Nguồn hoặc đích | Ý nghĩa |
| --- | --- | --- | --- | --- |
| **alb-sg** | Inbound | TCP/443 | 0.0.0.0/0 | ALB nhận HTTPS từ mọi địa chỉ IPv4. |
| **app-sg** | Inbound | TCP/8080 | **alb-sg** | Chỉ các interface thuộc alb-sg được phép khởi tạo kết nối tới ứng dụng ở cổng 8080. |
| **db-sg** | Inbound | TCP/5432 | **app-sg** | Database PostgreSQL nhận kết nối từ ứng dụng, không từ mọi nguồn trong VPC. |

Ba rule inbound trên chưa đủ để chứng minh ứng dụng hoạt động. Cần kiểm tra **outbound rule ở bên khởi tạo kết nối**, route, NACL và cấu hình listener/port của từng dịch vụ.

## 3. Stateful là gì?

**Stateful** nghĩa là Security Group tính đến trạng thái của lưu lượng kết nối. Khi một request được cho phép theo rule ở chiều khởi tạo, **lưu lượng phản hồi tương ứng** được phép đi ngược lại qua Security Group mà không cần thêm rule cho chiều phản hồi đó.

### 3.1. Ví dụ inbound HTTPS

Giả sử khách hàng có IP **203.0.113.10** kết nối tới máy chủ web **10.0.2.20** qua HTTPS:

| Bước | Hướng | Cặp cổng minh họa | Kiểm tra SG |
| --- | --- | --- | --- |
| 1 | Client → Server | 203.0.113.10:**51524** → 10.0.2.20:**443** | Inbound của máy chủ cần Allow TCP/443 từ nguồn phù hợp. |
| 2 | Server → Client | 10.0.2.20:**443** → 203.0.113.10:**51524** | Phản hồi của kết nối đã được cho phép được SG xử lý **statefully**. |

Cổng **51524** là cổng tạm thời (**ephemeral port**) minh họa do client dùng; trong thực tế giá trị thay đổi theo hệ điều hành và kết nối.

~~~mermaid
sequenceDiagram
    participant C as Client 203.0.113.10
    participant S as SG của máy chủ
    participant W as Web server TCP/443
    C->>S: TCP source 51524 → destination 443
    Note over S: Kiểm tra inbound Allow TCP/443
    S->>W: Chuyển gói được cho phép
    W-->>S: Response source 443 → destination 51524
    Note over S: Cho phép phản hồi theo trạng thái kết nối
    S-->>C: Trả kết quả HTTPS
~~~

**Điểm cốt lõi:** Bạn không cần thêm một outbound rule “cho phép TCP/51524” chỉ để máy chủ trả lời kết nối HTTPS inbound đã được SG cho phép. Quy tắc outbound vẫn cần xem riêng khi **máy chủ chủ động mở kết nối mới**.

### 3.2. Ví dụ outbound HTTPS từ EC2

Một EC2 cần gọi API của một dịch vụ qua TCP/443:

1. Outbound của EC2 cho phép kết nối mới tới endpoint đích trên TCP/443.
2. EC2 khởi tạo kết nối.
3. Gói phản hồi từ endpoint bên ngoài có thể đi vào EC2 thông qua cơ chế stateful mà không cần tạo inbound rule cho ephemeral port.

Điều này có nghĩa **SG với inbound trống vẫn có thể nhận phản hồi cho những kết nối outbound được phép**. Inbound trống không đồng nghĩa máy chủ hoàn toàn không nhận bất kỳ packet nào; nó ngăn các luồng inbound mới không được cho phép.

### 3.3. Stateful không đồng nghĩa “cho phép mọi chiều”

Một số kết luận sai phổ biến:

- “Có inbound 443 thì server tự động được mở kết nối mới ra Internet ở 443.” → **Sai.** Kết nối mới do server khởi tạo phải được xét theo outbound rule.
- “Có outbound 5432 từ ứng dụng thì database tự động nhận kết nối ở 5432.” → **Sai.** Bên database vẫn phải có inbound rule phù hợp.
- “Đã kết nối thành công trước đó thì mọi gói tin từ địa chỉ kia đều được phép.” → **Sai.** SG xem xét lưu lượng thuộc kết nối/luồng phù hợp, không tự mở quyền vô hạn cho một IP.
- “Chỉ cần SG là đủ, không quan tâm NACL.” → **Sai.** NACL là stateless và cần xét riêng lưu lượng hai chiều nếu có rule hạn chế.

### 3.4. Connection tracking và những giới hạn thực tế

AWS sử dụng cơ chế theo dõi kết nối cho Security Group, với hành vi và ngoại lệ phụ thuộc giao thức, kiểu traffic và loại tài nguyên. Có những luồng traffic được **untracked** trong các cấu hình cho phép rất rộng; không nên xem SG như một hệ thống theo dõi phiên TCP đầy đủ theo nghĩa của application firewall.

Trong một số tình huống, **thay đổi rule không làm mọi kết nối đang hoạt động bị cắt ngay** vì trạng thái kết nối có thể còn tồn tại đến khi hết hạn hoặc bị đóng; một số loại flow không được track có thể chịu ảnh hưởng khác. Khi xử lý sự cố bảo mật, cần kiểm chứng hiệu ứng thực tế, chủ động đóng phiên/đổi đường kết nối nếu cần và tham khảo tài liệu *Security group connection tracking* của AWS.

**Ghi nhớ:** Stateful chủ yếu giảm số rule phải tạo cho **lưu lượng phản hồi**. Nó không thay thế việc giới hạn kết nối mới, quản lý phiên ứng dụng hoặc tường lửa mức ứng dụng.

## 4. Quy tắc mặc định, implicit deny và nhiều Security Group

### 4.1. Security Group mới tạo

Với một Security Group do bạn mới tạo trong VPC, cấu hình ban đầu thông thường là:

- **Inbound:** không có rule cho phép inbound mới.
- **Outbound:** có rule mặc định cho phép mọi outbound IPv4; nếu có IPv6 trong phạm vi hỗ trợ, có thể có rule outbound IPv6 tương ứng.

Bạn phải **kiểm tra cấu hình thực tế** trước khi kết luận, vì người triển khai, template hoặc công cụ IaC có thể thay đổi các rule ngay khi tạo.

Do SG sử dụng cơ chế **allow-only**, luồng mới không được bất kỳ rule phù hợp nào cho phép sẽ bị **implicit deny**. Security Group không có rule **Deny** tường minh hoặc thứ tự ưu tiên bằng số như NACL.

### 4.2. Default Security Group của VPC

Mỗi VPC có một **default Security Group**. Cấu hình ban đầu thường gồm:

- Inbound cho phép lưu lượng từ **các interface có gắn chính default Security Group đó** (self-reference).
- Outbound cho phép tất cả lưu lượng theo các rule mặc định hiện có.

Điểm cần lưu ý là “default” **không** có nghĩa cấu hình tối ưu cho production. Nếu nhiều tài nguyên cùng dùng default SG, rule inbound tự tham chiếu có thể cho phép chúng trao đổi trực tiếp trong phạm vi mạng phù hợp, dù ứng dụng không cần.

**Khuyến nghị:** Tạo SG theo vai trò ứng dụng như **alb-sg**, **app-sg**, **db-sg**; chỉ giữ những rule cần cho mỗi vai trò. Kiểm tra default SG đang được sử dụng và thu hẹp theo chính sách môi trường.

### 4.3. Nhiều Security Group được hợp nhất theo Allow

Giả sử EC2 có hai SG:

- SG-A: inbound TCP/443 từ **0.0.0.0/0**.
- SG-B: inbound TCP/22 từ **10.10.0.0/16**.

Khi gắn cả hai, EC2 có thể nhận **cả HTTPS 443 từ Internet** và **SSH 22 từ mạng quản trị**, nếu các lớp khác không chặn.

Nếu gỡ SG-A, nguồn Internet không còn quyền inbound 443 bắt nguồn từ SG-A; tuy nhiên có thể tồn tại Allow cho 443 ở một SG khác. Không thể gắn một SG “block-all” để phủ định quyền của SG-A. Muốn thu hẹp cần sửa/gỡ rule Allow hoặc SG đang mở rộng quyền.

### 4.4. Quy tắc inbound và outbound độc lập đối với kết nối mới

Cách diễn đạt thực tế khi review:

- **Inbound:** “Ai được phép **bắt đầu** kết nối tới tài nguyên này, bằng giao thức/cổng nào?”
- **Outbound:** “Tài nguyên này được phép **bắt đầu** kết nối tới đâu, bằng giao thức/cổng nào?”

Với luồng **client → server**, thông thường cả **outbound của client** và **inbound của server** phải cho phép luồng mới. Chiều phản hồi được stateful SG xử lý, nhưng vẫn phải đáp ứng các lớp mạng khác trên đường đi.

## 5. Security Group reference: cấp quyền theo vai trò mạng

Security Group có thể tham chiếu **ID của Security Group khác** thay vì danh sách địa chỉ IP cố định, trong phạm vi mạng và điều kiện tham chiếu AWS hỗ trợ.

Ví dụ:

- **app-sg** inbound TCP/8080 **source = alb-sg**.
- **db-sg** inbound TCP/5432 **source = app-sg**.

Khi một EC2 mới được gắn **app-sg**, nó có thể trở thành nguồn phù hợp của rule vào **db-sg** mà không cần thêm IP private của instance vào rule.

### 5.1. Điều gì xảy ra khi tham chiếu SG?

Khi rule inbound có **source = app-sg**, ý nghĩa là cho phép lưu lượng từ các interface có gắn **app-sg**, theo cơ chế của AWS ở phạm vi kết nối được hỗ trợ. Đây không phải việc “copy” toàn bộ rule của app-sg sang db-sg.

**SG reference không có tính bắc cầu:**

- **alb-sg → app-sg** cho phép ALB bắt đầu kết nối tới app theo rule đã định.
- **app-sg → db-sg** cho phép app bắt đầu kết nối tới DB theo rule đã định.
- Hai rule này **không** tự cấp quyền cho ALB truy cập trực tiếp DB.

Ngoài ra, inbound ở SG đích **không tự sinh** outbound ở SG nguồn; nếu SG nguồn hạn chế outbound, phải thêm rule tương ứng.

### 5.2. Tự tham chiếu (self-reference)

Nếu SG cho phép inbound TCP/9000 từ **chính nó**, các network interface dùng SG này có thể bắt đầu kết nối TCP/9000 với nhau trong điều kiện mạng hỗ trợ. Điều này hữu ích cho một số cluster cần trao đổi nội bộ nhưng cũng có thể làm rộng quyền truy cập giữa các node cùng SG.

Cần phân biệt:

- **Self-reference**: cho phép luồng từ các ENI cùng mang SG.
- **CIDR nội bộ**: cho phép mọi địa chỉ trong dải CIDR được chỉ định, kể cả các tài nguyên không mang SG đó nếu đường mạng phù hợp.

### 5.3. Giới hạn tham chiếu

Không giả định Security Group reference hoạt động qua **mọi** VPC peering, Transit Gateway, cross-account hay các mô hình trung gian NAT/proxy. Việc hỗ trợ phụ thuộc **loại rule, quan hệ VPC và cơ chế kết nối**. Khi lưu lượng đi qua một middlebox hoặc cơ chế chuyển tiếp làm thay đổi cách quan sát nguồn, cần xác minh liệu tham chiếu SG còn phù hợp hay nên dùng CIDR đúng phạm vi.

Với định tuyến phức tạp, đối chiếu tài liệu *Security group referencing* và kiểm thử đường đi thực tế trước khi chấp nhận thiết kế.

## 6. Thiết kế minh họa: Internet → ALB → ứng dụng → RDS

Giả sử hệ thống bán hàng dùng:

- **Application Load Balancer (ALB)** nhận HTTPS từ khách.
- **EC2** chạy API ở TCP/8080 trong private subnet.
- **Amazon RDS for PostgreSQL** nhận kết nối TCP/5432 trong các subnet dành cho database.
- Các thành phần ứng dụng được bố trí trên **nhiều AZ** để hỗ trợ tính sẵn sàng cao khi kiến trúc yêu cầu.

~~~mermaid
flowchart TB
    U["Internet / người dùng"] -->|"TCP 443"| ALB["ALB — alb-sg"]
    subgraph VPC["Amazon VPC"]
      subgraph AZA["Availability Zone A"]
        A["EC2 App A — app-sg, TCP 8080"]
      end
      subgraph AZB["Availability Zone B"]
        B["EC2 App B — app-sg, TCP 8080"]
      end
      DB[("Amazon RDS PostgreSQL — db-sg, TCP 5432")]
      ALB -->|"TCP 8080"| A
      ALB -->|"TCP 8080"| B
      A -->|"TCP 5432"| DB
      B -->|"TCP 5432"| DB
    end
~~~

Sơ đồ biểu diễn **luồng logic**: RDS Multi-AZ, subnet, route table, các interface và cơ chế failover thực tế cần được cấu hình riêng. Không thể suy ra Multi-AZ hay khả năng phục hồi chỉ từ việc đặt hai instance vào hai AZ.

### 6.1. Ma trận rule tối thiểu cho các kết nối chính

| Security Group | Chiều | Protocol/port | Source/Destination | Mục đích |
| --- | --- | --- | --- | --- |
| **alb-sg** | Inbound | TCP/443 | 0.0.0.0/0 | Nhận HTTPS từ khách IPv4. |
| **alb-sg** | Outbound | TCP/8080 | **app-sg** | ALB mở kết nối tới target và thực hiện health check trên cổng ứng dụng khi được cấu hình như vậy. |
| **app-sg** | Inbound | TCP/8080 | **alb-sg** | Chỉ ALB được truy cập endpoint ứng dụng trên port 8080. |
| **app-sg** | Outbound | TCP/5432 | **db-sg** | Ứng dụng khởi tạo kết nối tới PostgreSQL. |
| **db-sg** | Inbound | TCP/5432 | **app-sg** | Chỉ các app hợp lệ được kết nối database. |

**Các rule bổ sung tùy yêu cầu:** Nếu ứng dụng còn gọi AWS APIs, endpoint S3/STS, kho image, hệ thống giám sát, DNS, secret manager hoặc dịch vụ ngoài AWS, cần thiết kế các luồng outbound tương ứng và phương án kết nối (VPC endpoint, NAT hoặc đường đi khác). Bảng trên cố ý chỉ bao quát **hai luồng nghiệp vụ ALB → app và app → DB**; không phải bộ rule đầy đủ cho mọi workload.

Nếu ALB dùng IPv6 và website dự kiến phục vụ máy khách IPv6, cần thêm những rule IPv6 phù hợp, chẳng hạn **::/0** đối với cổng HTTPS công khai. Rule **0.0.0.0/0** chỉ nói tới IPv4.

### 6.2. Theo dấu một request thành công

1. Client bắt đầu kết nối HTTPS/443 đến ALB. **alb-sg inbound 443** cho phép request.
2. ALB bắt đầu một kết nối riêng đến target EC2 ở TCP/8080. **alb-sg outbound 8080** và **app-sg inbound 8080** cho phép.
3. App cần dữ liệu đơn hàng, bắt đầu kết nối đến RDS TCP/5432. **app-sg outbound 5432** và **db-sg inbound 5432** cho phép.
4. RDS trả kết quả; các SG trên đường của kết nối được phép phản hồi theo **stateful**.
5. App trả response cho ALB, ALB trả HTTPS response cho client theo các kết nối tương ứng.

Điều kiện đi kèm: ALB phải có listener, target group/health check được cấu hình đúng; EC2 phải lắng nghe port 8080; RDS phải chạy và cho phép kết nối hợp lệ; route/NACL/DNS/credentials phải phù hợp.

### 6.3. Tại sao không dùng một SG cho toàn bộ hệ thống?

Nếu ALB, app và RDS dùng chung SG với inbound quá rộng, rất khó chứng minh ai được quyền truy cập database. Khi chia SG theo **vai trò**, thay đổi số lượng app instance trong Auto Scaling Group không buộc phải liên tục chỉnh IP trong SG của RDS.

Thiết kế theo vai trò cũng giúp đánh giá thay đổi: nhóm vận hành có thể thấy chính xác việc thêm một rule TCP/5432 sẽ ảnh hưởng tới lớp database nào.

### 6.4. Hạn chế cổng quản trị

Tránh tạo inbound TCP/22 hoặc TCP/3389 từ **0.0.0.0/0** cho máy production. Nếu cần quản trị, cân nhắc **AWS Systems Manager Session Manager** cùng IAM, endpoint và cấu hình cần thiết, hoặc kết nối quản trị qua mạng/VPN được kiểm soát.

Lưu ý: Session Manager chỉ hoạt động khi instance/agent, IAM role, đường kết nối tới các dịch vụ SSM và những điều kiện liên quan được thiết lập đúng. Việc xóa rule SSH không tự động khiến Session Manager sử dụng được.

## 7. Security Group và Network ACL khác nhau thế nào?

**Security Group và NACL là hai lớp kiểm soát mạng bổ sung**, với các hành vi khác nhau:

| Tiêu chí | Security Group | Network ACL (NACL) |
| --- | --- | --- |
| Phạm vi | Network interface/tài nguyên được hỗ trợ. | Subnet. |
| Loại rule | **Allow**; các luồng không được Allow bị từ chối ngầm. | **Allow** và **Deny**. |
| Trạng thái | **Stateful** cho các luồng được theo dõi. | **Stateless**. |
| Thứ tự rule | Không xét thứ tự ưu tiên bằng số; tổng hợp các Allow. | Đánh giá rule theo **rule number**, từ số nhỏ tới số lớn, dừng khi khớp. |
| Chiều phản hồi | Phản hồi tương ứng của kết nối được Allow có thể đi qua mà không cần rule ngược. | Phải có rule phù hợp cho **cả hai chiều** traffic. |
| Liên kết | Gắn SG vào interface/tài nguyên; một interface có thể nhận nhiều SG. | Mỗi subnet liên kết với một NACL tại một thời điểm. |
| Nguồn/đích | CIDR IPv4/IPv6, SG reference, prefix list tùy rule/khả năng hỗ trợ. | Chủ yếu CIDR IPv4/IPv6, protocol và dải cổng. |
| Điển hình | Phân quyền theo vai trò ALB/app/DB. | Lớp lọc bổ sung ở ranh giới subnet. |

### 7.1. Ví dụ: inbound HTTPS với NACL stateless

Một website nhận TCP/443 từ client dùng source port **51524**:

- **Inbound NACL** của subnet phía server phải cho phép request tới destination port **443**.
- **Outbound NACL** của subnet phía server phải cho phép response đi tới **ephemeral port 51524** của client, trong phạm vi source/destination được thiết kế.
- Nếu NACL của subnet phía client cũng chịu tác động trong cùng môi trường định tuyến, phải xét rule tương ứng ở phía đó.

Không được kết luận rằng “SG đã stateful nên NACL cũng tự động cho response đi qua”. **NACL không theo dõi trạng thái kết nối.** Dải ephemeral port thay đổi theo hệ điều hành, client và dịch vụ; tránh ghi nhớ một dải duy nhất cho mọi hệ thống mà không xác minh môi trường.

### 7.2. Default NACL và custom NACL

Thông thường, **default NACL** của VPC có các rule cho phép toàn bộ lưu lượng vào/ra; **custom NACL** mới tạo có xu hướng từ chối các luồng nếu chưa được bổ sung rule phù hợp. Cần đọc rule thực tế vì chúng có thể đã được điều chỉnh.

Một subnet thuộc NACL nào là vấn đề **liên kết subnet**, không phải SG gắn trên instance. Nếu EC2 không kết nối được qua subnet, phải kiểm tra cả hai lớp.

## 8. Security Group không thay thế định tuyến hoặc dịch vụ mạng khác

### 8.1. Route table, Internet Gateway và NAT

Một EC2 trong subnet không có route ra Internet sẽ không thể trực tiếp truy cập Internet chỉ vì outbound SG Allow 0.0.0.0/0.

Ví dụ:

- **Public subnet** có route tới Internet Gateway, cùng các điều kiện cấp public address và kết nối khác phù hợp.
- **Private subnet** có thể dùng NAT Gateway cho một số luồng IPv4 outbound tới Internet hoặc VPC endpoint để đến dịch vụ AWS mà không cần đi qua Internet công cộng.
- **Internet Gateway** hay **NAT Gateway** không thay SG: các quyền mạng ở interface/tài nguyên vẫn phải hợp lệ.

Lưu ý loại endpoint:

- **Gateway endpoint** (ví dụ S3/DynamoDB khi được hỗ trợ) hoạt động thông qua định tuyến route table; không gắn SG trực tiếp giống interface endpoint.
- **Interface endpoint** được triển khai qua ENI trong VPC, có Security Group cần cho phép traffic phù hợp từ client.

Để kiểm soát truy cập đến AWS service một cách đầy đủ, có thể còn cần **endpoint policy**, IAM/resource policy và điều kiện của dịch vụ.

### 8.2. IAM, TLS và tường lửa ứng dụng

Security Group chỉ kiểm tra thông tin ở lớp mạng/transport theo khả năng hỗ trợ. Nó không biết người đang gọi API có quyền xem đơn hàng hay không.

- **IAM** kiểm soát hành động AWS API theo danh tính/quyền.
- **TLS** mã hóa và hỗ trợ xác thực điểm cuối khi được cấu hình đúng.
- **AWS WAF** có thể bổ sung quy tắc kiểm soát request web cho các loại tài nguyên hỗ trợ.
- **Application authorization** xác định người dùng cuối được xem/sửa dữ liệu nào.
- **OS firewall** trong EC2 (nếu cấu hình) có thể bổ sung lớp lọc, độc lập với SG.

Một request HTTPS được SG cho phép vẫn có thể bị ứng dụng trả **401**, **403** hoặc lỗi chứng chỉ. Những lỗi đó không tự động chứng tỏ SG sai.

### 8.3. Các dịch vụ tính toán khác EC2

Không phải mọi dịch vụ AWS dùng Security Group theo cách giống nhau. Ví dụ, EC2/ENI, RDS, ALB, interface VPC endpoint và những workload được kết nối vào VPC qua ENI có thể sử dụng SG theo tài liệu của dịch vụ. Với Lambda, việc cấu hình SG chỉ có ý nghĩa trong bối cảnh **VPC connectivity** của function; không nên suy rằng SG đó trực tiếp mở/đóng quyền gọi endpoint invoke Lambda.

Khi thiết kế ECS, EKS hoặc serverless, cần biết tài nguyên nào thực sự gắn ENI/SG và các hành vi điều khiển traffic riêng của dịch vụ. Quyền truy cập API của workload vẫn do IAM và các policy liên quan quyết định.

## 9. Các quy tắc triển khai an toàn

### 9.1. Giới hạn inbound theo nguồn thật sự cần thiết

| Nhu cầu | Quy tắc phù hợp | Tránh |
| --- | --- | --- |
| Website công khai | TCP/443 từ các nguồn Internet dự kiến tới SG của ALB. | Mở cổng database công khai chỉ để tiện kiểm thử. |
| App phía sau ALB | TCP/port app từ SG của ALB. | Inbound 0.0.0.0/0 vào EC2 app trong private subnet. |
| Database | TCP/port DB từ SG workload có quyền truy cập. | TCP/5432 hoặc 3306 từ mọi IPv4/IPv6. |
| Quản trị EC2 | Ưu tiên kênh quản trị được kiểm soát; nếu cần SSH, giới hạn IP/mạng quản trị. | SSH/RDP công khai với dải nguồn vô hạn. |
| Giao tiếp nội bộ cluster | SG self-reference hoặc tham chiếu nhóm đích đúng scope. | Mở toàn dải VPC cho mọi service nếu không có nhu cầu. |

Ngay cả khi server không gắn public IP, việc mở inbound rộng vẫn có thể tạo rủi ro từ bên trong VPC, mạng kết nối qua VPN/peering/Transit Gateway hoặc workload đã bị xâm nhập.

### 9.2. Thu hẹp outbound có kiểm soát

Rule outbound “Allow all” thuận tiện cho demo nhưng có thể mở rộng khả năng kết nối ngoài dự kiến. Khi đặt mục tiêu egress least privilege:

1. Liệt kê các đích thật sự cần: database, HTTPS APIs, S3 endpoint, dịch vụ cập nhật/giám sát, DNS và các thành phần phụ trợ.
2. Xác định đích theo **SG reference**, **prefix list** hoặc CIDR được duy trì phù hợp.
3. Bảo đảm kiến trúc định tuyến, NACL, endpoint policy và IAM tương thích.
4. Thử chức năng ứng dụng, health checks, khởi động lại instance, cập nhật dependency và tình huống phục hồi trước khi áp dụng production.

**Lưu ý:** Địa chỉ IP của dịch vụ bên ngoài có thể thay đổi. Việc tự gắn một IP cố định của endpoint SaaS vào SG thường gây hỏng kết nối về sau nếu nhà cung cấp thay đổi IP. Chọn giải pháp quản lý egress phù hợp với yêu cầu định danh/dải mạng.

### 9.3. Phân tách môi trường và trách nhiệm quản trị

- Dùng SG riêng cho **development**, **staging** và **production** theo mô hình account/VPC.
- Quản lý các rule bằng Infrastructure as Code (IaC) và review thay đổi có kiểm soát khi phù hợp.
- Đặt tên, **description** và tagging rõ mục đích; mô tả rule theo lý do nghiệp vụ.
- Hạn chế ai có quyền **ec2:AuthorizeSecurityGroupIngress**, **ec2:AuthorizeSecurityGroupEgress** hoặc sửa SG; ghi nhận các thay đổi qua CloudTrail.
- Rà soát SG không còn dùng, rule không còn cần và SG gắn vào tài nguyên ngoài dự kiến.
- Kiểm tra IPv4 và IPv6 độc lập, đặc biệt những VPC hoặc ALB dual-stack.

### 9.4. Stateful không loại bỏ nhu cầu theo dõi

**VPC Flow Logs** có thể ghi nhận metadata của traffic trong phạm vi được cấu hình, hỗ trợ kiểm tra ACCEPT/REJECT và phân tích đường đi; nhưng không giải mã payload, không ghi mọi packet như một công cụ packet capture đầy đủ, và tùy phạm vi/timing/format log.

AWS **Reachability Analyzer** có thể hỗ trợ phân tích khả năng kết nối theo cấu hình mạng giữa các điểm được hỗ trợ. Cần đối chiếu kết quả với ứng dụng thực tế, trạng thái dịch vụ và kiểm thử chức năng.

Bật log, lưu trữ CloudWatch Logs/S3 và phân tích có chi phí; hãy xác định phạm vi log và thời gian lưu theo yêu cầu điều tra, tuân thủ và ngân sách.

## 10. Thực hành với AWS CLI (chỉ đọc)

Các lệnh dưới đây dùng để quan sát cấu hình, **không tạo, sửa hoặc xóa rule**. Yêu cầu AWS CLI đã có credentials hợp lệ, quyền IAM đủ để đọc tài nguyên, và thay các ID minh họa bằng ID thật trong môi trường được phép truy cập.

### 10.1. Xác định principal đang sử dụng

~~~bash
aws sts get-caller-identity
~~~

Nếu command bị **AccessDenied** ở các bước tiếp theo, trước hết xác định đúng AWS account, Region và IAM role/user đang dùng. IAM có thể giới hạn quyền đọc cấu hình.

### 10.2. Xem cấu hình của một Security Group

~~~bash
aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Trong kết quả, chú ý:

- **VpcId:** SG thuộc VPC nào.
- **IpPermissions:** các inbound rule hiện có.
- **IpPermissionsEgress:** các outbound rule hiện có.
- Các dải CIDR/SG reference trong mỗi rule và protocol/port liên quan.

Đừng chỉ dựa vào tên SG; xem ID cụ thể và VPC để tránh nhầm môi trường.

### 10.3. Xem rule theo định dạng mới

~~~bash
aws ec2 describe-security-group-rules \
  --filters Name=group-id,Values=sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --output json
~~~

Một rule có thể có các thuộc tính như **SecurityGroupRuleId**, **IsEgress**, **IpProtocol**, **FromPort**, **ToPort**, **CidrIpv4**, **CidrIpv6** hoặc **ReferencedGroupInfo**. **IsEgress = true** nghĩa là outbound; **false** là inbound.

### 10.4. Tìm ENI đang gắn Security Group

~~~bash
aws ec2 describe-network-interfaces \
  --filters Name=group-id,Values=sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --output json
~~~

Xem **NetworkInterfaceId**, **SubnetId**, **PrivateIpAddress**, **Groups**, **Description** và các thông tin attachment có sẵn để biết SG đang bảo vệ interface của tài nguyên nào. Một số tài nguyên do dịch vụ quản lý sử dụng ENI do AWS tạo; cần đối chiếu tên/ID tài nguyên liên quan.

### 10.5. Kiểm tra SG của EC2, ALB và RDS

~~~bash
# EC2: kiểm tra instance, subnet và nhóm mạng gắn với instance.
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --region ap-southeast-1 \
  --query "Reservations[].Instances[].{Id:InstanceId,Subnet:SubnetId,SG:SecurityGroups}"

# ALB: kiểm tra scheme, VPC và Security Group.
aws elbv2 describe-load-balancers \
  --names example-public-alb \
  --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,VPC:VpcId,SG:SecurityGroups}"

# RDS: kiểm tra public access và những VPC SG được áp dụng.
aws rds describe-db-instances \
  --db-instance-identifier example-orders-db \
  --region ap-southeast-1 \
  --query "DBInstances[].{Name:DBInstanceIdentifier,Public:PubliclyAccessible,SG:VpcSecurityGroups}"
~~~

Một instance có thể dùng nhiều ENI và các SG gắn với ENI phải được kiểm tra theo đúng luồng, nên với sự cố phức tạp hãy kiểm tra **describe-network-interfaces** thay vì chỉ nhìn danh sách SG cấp instance.

### 10.6. Kiểm tra lớp mạng liên quan

~~~bash
# Xem NACL gắn với subnet minh họa.
aws ec2 describe-network-acls \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1

# Xem route table được liên kết tường minh với subnet (nếu có).
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1
~~~

**Quan trọng:** Nếu không tìm thấy route table liên kết **tường minh** cho subnet, subnet có thể đang sử dụng **main route table** của VPC. Cần xem thêm main association thay vì kết luận subnet không có route.

### 10.7. Đọc kết quả theo tình huống

- Nếu app **không tới được DB** trên 5432, kiểm tra **app-sg outbound 5432**, **db-sg inbound 5432**, IP/DNS DB, NACL/route và trạng thái DB listener.
- Nếu ALB báo target **unhealthy**, xem port health check, app listener, **alb-sg outbound** và **app-sg inbound**; kiểm tra thêm mã HTTP/HTTPS, đường health check và ứng dụng.
- Nếu một EC2 ở private subnet không truy cập được HTTPS Internet, kiểm tra **outbound SG**, route tới NAT/VPC endpoint và những lớp mạng khác. Không suy từ SG Allow ra kết luận chắc chắn có Internet.
- Nếu API AWS trả **AccessDenied**, kiểm tra IAM/resource policy; đây có thể là lỗi quyền API chứ không phải lỗi network timeout.
- Nếu lỗi xuất hiện sau khi sửa SG, xác minh rule có hiệu lực, ENI gắn đúng SG, trạng thái kết nối hiện có và thay đổi ở các lớp mạng khác.

## 11. Khắc phục sự cố bằng cây quyết định

Hãy xuất phát từ **luồng cụ thể**: nguồn, đích, protocol, port, Region/VPC và chiều bắt đầu kết nối.

~~~mermaid
flowchart TD
    A["Kết nối thất bại"] --> B{"Nguồn/đích/protocol/port đã chính xác?"}
    B -->|"Chưa"| B1["Xác minh DNS, IP, listener, cổng và target"]
    B -->|"Rồi"| C{"Nguồn cho phép kết nối mới qua outbound SG?"}
    C -->|"Không"| C1["Sửa phạm vi outbound theo yêu cầu"]
    C -->|"Có"| D{"Đích cho phép inbound SG?"}
    D -->|"Không"| D1["Sửa phạm vi inbound theo nguồn hợp lệ"]
    D -->|"Có"| E{"Route và NACL cho phép hai chiều?"}
    E -->|"Không"| E1["Kiểm tra route, subnet, NACL, gateway/endpoint"]
    E -->|"Có"| F["Kiểm tra OS firewall, app, TLS, IAM, database auth, health check và logs"]
~~~

**Cây quyết định là quy trình chẩn đoán khái quát.** Các dịch vụ hoặc phương thức mạng đặc biệt có thể có thêm điều kiện. Một lỗi cũng có thể do nhiều nguyên nhân cùng lúc.

### 11.1. Tình huống: TCP timeout tới RDS

**Hiện tượng:** EC2 trong VPC không kết nối PostgreSQL qua port 5432, dù database đang chạy.

Kiểm tra theo thứ tự:

1. Đang gọi **DB endpoint** đúng chưa? Endpoint DNS có trỏ tới địa chỉ cập nhật, nhất là sau failover?
2. Client EC2 có outbound rule cho TCP/5432 tới RDS phù hợp không?
3. RDS có inbound rule cho TCP/5432 từ **app-sg** hoặc nguồn phù hợp không?
4. Client/DB có nằm ở subnet/VPC có route hợp lệ? NACL có cho phép chiều request và response không?
5. Database có lắng nghe, đang healthy và có giới hạn kết nối hoặc vấn đề DNS/OS nào không?
6. Khi TCP đã thông nhưng login lỗi, mới tập trung kiểm tra **database credentials**, TLS và cơ chế DB authentication.

Không mở 5432 cho **0.0.0.0/0** như biện pháp “sửa nhanh”.

### 11.2. Tình huống: EC2 không cập nhật được package

**Hiện tượng:** EC2 ở private subnet có inbound rule phù hợp nhưng không gọi HTTPS đến kho package.

Giải thích: inbound SG không liên quan trực tiếp tới kết nối **do EC2 chủ động mở ra**. Cần kiểm tra outbound TCP/443, DNS, NACL và tuyến qua NAT/proxy/endpoint phù hợp. Một EC2 không có public IP và không có NAT/đường ra khác sẽ không truy cập được một repository Internet chỉ nhờ outbound Allow.

### 11.3. Tình huống: ALB nhận HTTPS nhưng trả 502/503

Việc người dùng kết nối đến ALB không đồng nghĩa ALB kết nối tốt tới target. Cần đối chiếu:

- ALB listener và target group đang hướng tới port nào.
- **alb-sg outbound** có cho phép port target/health check không.
- **app-sg inbound** có cho phép nguồn từ ALB không.
- EC2/ứng dụng có lắng nghe đúng port/protocol; endpoint health check có trả kết quả theo tiêu chí không.
- Target registration và trạng thái health của target.

Lỗi 502/503 có thể do nhiều nguyên nhân ở lớp ALB, target hoặc ứng dụng; **không** mặc định quy mọi lỗi cho SG.

## 12. Hiểu lầm và lỗi cấu hình thường gặp

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| “Security Group là stateless giống NACL.” | Security Group thường xử lý các luồng phản hồi theo trạng thái; NACL là stateless. |
| “Đã mở inbound 443 thì phải mở outbound ephemeral port mới trả HTTPS được.” | Phản hồi của kết nối được SG cho phép thường được cho phép statefully; không cần rule outbound riêng cho phản hồi. |
| “Không có inbound rule thì instance không thể nhận bất kỳ packet nào.” | Phản hồi của kết nối outbound được phép vẫn có thể vào theo stateful behavior. |
| “Gắn hai SG thì SG nghiêm ngặt hơn sẽ thắng.” | Các rule Allow được hợp nhất; SG không có Deny để phủ định Allow từ SG khác. |
| “Mở 10.0.0.0/8 là private nên an toàn tuyệt đối.” | Dải private có thể bao gồm nhiều hệ thống không đáng tin hoặc mạng kết nối; cần giới hạn theo vai trò. |
| “Có SG reference rồi không cần outbound ở client.” | SG đích có inbound Allow không tự tạo outbound Allow ở SG nguồn. |
| “Đã có route thì chắc chắn kết nối được.” | SG, NACL, gateway, listener và application layer đều có thể ngăn kết nối. |
| “Security Group lọc được URL /admin.” | SG không kiểm tra đường dẫn HTTP; dùng lớp ứng dụng/WAF/auth phù hợp. |
| “0.0.0.0/0 cũng cho phép mọi IPv6.” | 0.0.0.0/0 chỉ là IPv4; IPv6 dùng CIDR IPv6 như ::/0 khi áp dụng. |
| “Thay SG sẽ cắt ngay mọi connection.” | Connection tracking và các ngoại lệ khiến hành vi của phiên đang tồn tại cần được xác minh. |
| “RDS private nhưng mở inbound 0.0.0.0/0 thì không sao.” | Mở rộng quyền vẫn tăng rủi ro từ các mạng có đường kết nối tới DB. |

## 13. Bài tập thiết kế và đánh giá

### Bài tập 1 — Đánh giá quy tắc web public

Một EC2 vừa chạy nginx vừa chạy database, được gắn một SG với inbound:

- TCP/22 từ **0.0.0.0/0**.
- TCP/443 từ **0.0.0.0/0**.
- TCP/5432 từ **0.0.0.0/0**.

**Yêu cầu:** Xác định ba rủi ro và đề xuất kiến trúc cải tiến.

**Gợi ý lời giải:** HTTPS public có thể hợp lệ nếu đây là endpoint web công khai và bảo vệ tầng ứng dụng tốt; nhưng SSH và PostgreSQL mở cho mọi IPv4 là rủi ro cao. Tách web/database thành các thành phần/SG phù hợp, cân nhắc ALB, private subnet cho app/DB, dùng inbound từ SG theo vai trò; sử dụng kênh quản trị được kiểm soát thay SSH công khai. Giới hạn quyền outbound và đánh giá route/NACL.

### Bài tập 2 — App outbound bị chặn

Hệ thống có:

- **app-sg inbound 8080 từ alb-sg**.
- **db-sg inbound 5432 từ app-sg**.
- **app-sg outbound chỉ cho TCP/443 đến một endpoint xác định**.

Câu hỏi: App có mở được kết nối mới tới RDS TCP/5432 không?

**Đáp án:** Không, theo những rule nêu ra, **app-sg thiếu outbound TCP/5432** tới DB. **db-sg inbound 5432** là cần thiết nhưng chưa đủ. Phải bổ sung outbound phù hợp và kiểm tra các điều kiện mạng/DB khác.

### Bài tập 3 — Stateful và chiều phản hồi

Một EC2 chạy web server nhận TCP/443 từ client có source port 51620; EC2 có inbound 443 từ IP client và **không có outbound rule**. Liệu server có phản hồi được không?

**Đáp án:** Theo cơ chế stateful thông thường, phản hồi tương ứng của kết nối inbound đã được cho phép có thể đi qua SG dù không có outbound rule riêng. Tuy nhiên, NACL/route, listener và các điều kiện còn lại vẫn phải phù hợp. Server cũng **không** được tự ý mở một outbound connection mới chỉ vì inbound 443 đã mở.

### Bài tập 4 — Kết nối database không ổn định sau failover

RDS Multi-AZ chuyển đổi dự phòng; ứng dụng dùng địa chỉ IP DB cũ được ghi cứng vào cấu hình và đột nhiên timeout.

**Đáp án:** SG có thể không phải nguyên nhân. Kết nối tới IP cũ sau failover là rủi ro nếu không sử dụng DNS endpoint và retry/reconnect hợp lý. Cần xem endpoint, cấu hình DNS cache, kết nối ứng dụng, trạng thái database, sau đó mới đối chiếu SG/NACL/route và log.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Security Group được áp dụng chủ yếu ở cấp nào?  
**Đáp án:** Gắn với network interface/tài nguyên hỗ trợ bên trong VPC, không gắn trực tiếp vào subnet như NACL.

**Câu 2.** Security Group có hỗ trợ một rule Deny để ghi đè Allow không?  
**Đáp án:** Không. SG có rule Allow, và traffic không khớp Allow sẽ bị từ chối ngầm.

**Câu 3.** App có outbound TCP/5432 tới db-sg; DB có inbound TCP/5432 từ app-sg. Có cần mở inbound ephemeral trên app-sg chỉ để nhận phản hồi không?  
**Đáp án:** Thông thường không. SG là stateful cho phản hồi của kết nối đã được cho phép; nhưng NACL phải xét hai chiều.

**Câu 4.** Nếu EC2 gắn hai SG, một SG cho phép inbound 22 và SG còn lại cho phép 443, quyền hiệu lực thế nào?  
**Đáp án:** Tổng hợp các Allow từ cả hai SG. Không có thứ tự ưu tiên SG để hạn chế quyền của SG còn lại.

**Câu 5.** Vì sao rule **db-sg inbound 5432 source = app-sg** thường linh hoạt hơn đưa từng private IP EC2 vào rule?  
**Đáp án:** SG reference gắn quyền theo vai trò nhóm network interface, thuận tiện khi workload scale hoặc thay instance. Phải bảo đảm kết nối/kiểu tham chiếu được AWS hỗ trợ.

**Câu 6.** Có thể dùng 0.0.0.0/0 cho IPv6 không?  
**Đáp án:** Không. IPv6 có cú pháp riêng, ví dụ ::/0; phải review riêng các rule IPv6.

**Câu 7.** Khi EC2 có outbound Allow mọi đích nhưng không có route ra Internet, nó truy cập Internet được không?  
**Đáp án:** Không. SG chỉ là một lớp điều kiện; cần route, gateway/NAT/endpoint và các cấu hình mạng phù hợp.

**Câu 8.** Vì sao NACL phải có rule phản hồi dù SG là stateful?  
**Đáp án:** NACL hoạt động stateless, nên xử lý chiều request và response độc lập.

**Câu 9.** Nếu ALB tới app không được, tối thiểu cần kiểm tra hai rule SG nào?  
**Đáp án:** **alb-sg outbound** tới port ứng dụng và **app-sg inbound** từ alb-sg trên port đó, rồi kiểm tra listener/target, route, NACL và ứng dụng.

**Câu 10.** VPC Flow Logs giúp gì khi điều tra?  
**Đáp án:** Cung cấp metadata của luồng traffic trong phạm vi cấu hình để hỗ trợ chẩn đoán ACCEPT/REJECT và các đặc điểm kết nối; không thay thế kiểm thử ứng dụng hoặc việc xem tất cả các lớp mạng.

## 15. Tổng kết

Security Group là một trong những công cụ quan trọng nhất để **phân đoạn mạng và giới hạn đường kết nối** giữa các thành phần AWS. Có bốn nguyên tắc cần ghi nhớ:

1. **Allow-only và implicit deny:** chỉ những luồng được rule phù hợp cho phép mới có thể khởi tạo theo chiều tương ứng; nhiều SG gắn vào một interface sẽ cộng các quyền Allow.
2. **Stateful:** lưu lượng phản hồi của kết nối được phép có thể đi qua SG mà không cần rule độc lập cho chiều ngược lại. **NACL vẫn stateless**.
3. **Thiết kế theo vai trò:** dùng các nhóm như ALB, app và DB; ưu tiên SG reference phù hợp, hạn chế cổng quản trị/database và kiểm soát outbound theo nhu cầu.
4. **Bảo mật nhiều lớp:** SG cần được kết hợp với VPC route, NACL, IAM, TLS, logging, khả năng phục hồi qua AZ và các chính sách vận hành. Mở cổng không đồng nghĩa ứng dụng đã an toàn hoặc chắc chắn kết nối được.

Khi triển khai hệ thống an toàn, có giám sát và khả năng phục hồi trên AWS, hãy mô tả rõ từng **luồng khởi tạo** (nguồn → đích, protocol/port), kiểm tra rule ở **hai đầu**, xác nhận chiều phản hồi, kiểm thử route/NACL và giám sát thay đổi. Đây cũng là cách hạn chế sự cố kết nối, giảm bề mặt tấn công và tránh phát sinh chi phí điều tra/khắc phục không cần thiết.

### Tài liệu AWS tham khảo

- [Security groups for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — khái niệm và cách dùng Security Group.
- [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html) — inbound/outbound, nguồn/đích, SG reference.
- [Security group connection tracking](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html) — cơ chế stateful và những trường hợp đặc biệt của connection tracking.
- [Control subnet traffic with Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — so sánh lớp subnet stateless với SG.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — thu thập thông tin traffic để theo dõi và điều tra.

