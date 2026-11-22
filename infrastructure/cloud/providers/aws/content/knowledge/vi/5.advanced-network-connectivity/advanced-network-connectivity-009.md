# VPC Lattice và kết nối dịch vụ giữa nhiều VPC

> **Chương:** Kết nối mạng nâng cao  
> **Module:** CLOUD_PROVIDERS_AWS — tìm hiểu hệ sinh thái AWS từ Region/Availability Zone (AZ), IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp, serverless; rèn luyện kỹ năng chọn dịch vụ, thiết kế ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Amazon VPC Lattice** giải quyết vấn đề kết nối giữa các ứng dụng và dịch vụ phân tán trong nhiều VPC hoặc nhiều AWS account như thế nào.
2. Phân biệt **service network**, **service**, **listener**, **rule**, **target group**, **VPC association** và **service-network VPC endpoint**.
3. Mô tả đường đi của một request từ ứng dụng ở VPC A tới dịch vụ ở VPC B qua VPC Lattice.
4. Thiết kế kiến trúc kết nối đa VPC và đa account với **AWS Resource Access Manager (AWS RAM)**, IAM, chính sách xác thực/phân quyền và Security Group.
5. Phân biệt cơ chế **VPC Lattice service** với **resource configuration/resource gateway** và biết tình huống sử dụng thích hợp.
6. Hiểu cách dùng tên miền, HTTPS/TLS, metric, access log, health check và công cụ AWS để quan sát và khắc phục lỗi.
7. Đánh giá khi nào chọn VPC Lattice thay cho VPC peering, Transit Gateway, PrivateLink hoặc những giải pháp kết nối khác, dựa trên yêu cầu kỹ thuật và chi phí.

## 1. Bài toán: nhiều VPC, nhiều dịch vụ, nhiều nhóm phát triển

Giả sử một hệ thống thương mại điện tử trên AWS được chia thành các ứng dụng:

- **Orders API** xử lý đơn hàng, chạy trên EC2 hoặc ECS trong **VPC Orders**.
- **Payments API** xử lý thanh toán, chạy trên ECS hoặc EKS trong **VPC Payments**.
- **Notifications API** gửi thông báo, chạy trên AWS Lambda trong tài khoản vận hành khác.
- Mỗi ứng dụng có thể được triển khai trong một AWS account riêng để tách quyền, chi phí và vòng đời phát hành.

Orders API cần gọi Payments API qua HTTPS, nhưng hai nhóm không muốn phải duy trì cấu hình truy cập trực tiếp tới toàn bộ các dải IP của nhau. Khi số dịch vụ tăng, mô hình tự quản lý nhiều kết nối VPC, các route và chính sách mạng có thể phức tạp.

**Amazon VPC Lattice** là một dịch vụ kết nối ứng dụng được AWS quản lý. Nó cung cấp một cách tổ chức, định tuyến, bảo vệ và quan sát giao tiếp giữa **các dịch vụ** được triển khai trong nhiều VPC hoặc AWS account, mà ứng dụng gọi dịch vụ không nhất thiết phải có đường kết nối mạng trực tiếp kiểu VPC peering tới toàn bộ mạng bên phía dịch vụ.

VPC Lattice đặc biệt phù hợp khi nhóm cần quản lý kết nối ở **ranh giới dịch vụ**: ứng dụng nào có thể gọi API nào, theo cổng/giao thức nào, với quyền gì và cách quan sát request ra sao.

### 1.1. Điểm khác biệt về mô hình tư duy

Với mạng truyền thống, câu hỏi thường là:

> “Làm sao máy trong VPC A đi tới địa chỉ IP của máy trong VPC B?”

Với VPC Lattice service, câu hỏi trở thành:

> “Làm sao client trong VPC A được phép gọi **Payments Service** đã đăng ký, và request đó được chuyển đến các target hợp lệ?”

VPC Lattice trừu tượng hóa lớp định danh/điểm truy cập dịch vụ, đồng thời cung cấp cơ chế routing, xác thực và quan sát thích hợp. Tuy vậy, khách hàng vẫn phải bảo đảm **các association, DNS, chính sách, Security Group, khả năng hoạt động của target và điều kiện mạng liên quan** được cấu hình chính xác.

### 1.2. VPC Lattice không phải mạng VPC kết nối mọi thứ

VPC Lattice không mặc nhiên biến hai VPC thành một mạng có thể định tuyến tự do giữa mọi địa chỉ IP. Khả năng truy cập phụ thuộc vào dịch vụ hoặc resource configuration được **công bố**, service network mà các bên tham gia, và các lớp bảo mật.

Ví dụ, Orders API được phép truy cập Payments Service qua VPC Lattice **không** đồng nghĩa Orders API có thể SSH vào tất cả EC2 instance trong VPC Payments hoặc truy vấn tùy ý database bên trong VPC đó.

## 2. Các thành phần cốt lõi của VPC Lattice

Hãy phân biệt hai khái niệm lớn:

- **VPC Lattice service:** điểm truy cập logic đại diện cho một ứng dụng/endpoint, có listener, routing rule và target group.
- **Service network:** ranh giới logic nhóm nhiều service (và resource configuration trong những kịch bản áp dụng), cho phép các VPC được kết nối sử dụng những thành phần mà chúng có quyền.

### 2.1. Sơ đồ khái niệm

~~~mermaid
flowchart LR
    subgraph A["VPC A — Clients"]
        ORD["Orders API"]
    end
    subgraph C["VPC C — Clients"]
        BATCH["Batch / Backoffice"]
    end
    subgraph SN["VPC Lattice — Service network"]
        S1["Payments Service"]
        S2["Notifications Service"]
    end
    subgraph B["VPC B — Targets"]
        P1["Payments target 1"]
        P2["Payments target 2"]
    end
    L["AWS Lambda function"]
    ORD -->|"VPC association hoặc service-network endpoint"| SN
    BATCH -->|"VPC association hoặc service-network endpoint"| SN
    S1 -->|"Listener / rules / target group"| P1
    S1 -->|"Listener / rules / target group"| P2
    S2 --> L
~~~

Đây là **sơ đồ logic**, không phải bản đồ gói tin chi tiết. Request từ client phải đi tới endpoint của VPC Lattice rồi được Lattice chuyển tiếp đến target; mỗi chiều phải thỏa các điều kiện mạng và phân quyền.

### 2.2. Bảng thành phần

| Thành phần | Vai trò | Câu hỏi thiết kế |
| --- | --- | --- |
| **Service network** | Tập hợp logic các service và resource configuration có thể được liên kết, cùng ranh giới truy cập/quan sát. | Những ứng dụng nào cùng thuộc miền kết nối? |
| **Service** | Đại diện cho một ứng dụng được cung cấp qua Lattice, có tên miền và các listener. | Cần công bố API nào cho client? |
| **Listener** | Tiếp nhận kết nối theo giao thức/cổng, sau đó áp dụng rule. | Sử dụng HTTPS/443, HTTP hay TLS passthrough? |
| **Rule** | Chọn hành động/target group theo điều kiện được hỗ trợ và thứ tự ưu tiên. | Request được chuyển đến backend nào? |
| **Target group** | Tập các compute target thực thi service; có cấu hình protocol, port và health check khi hỗ trợ. | Dịch vụ chạy trên EC2, IP, ALB hay Lambda? |
| **Service-network service association** | Kết nối một service với service network. | Service nào xuất hiện trong mạng dịch vụ? |
| **Service-network VPC association** | Kết nối một VPC vào service network cho các client trong VPC sử dụng service phù hợp. | VPC nào được tham gia làm client? |
| **Service-network VPC endpoint** | Cách khác để kết nối một VPC tới service network qua VPC endpoint loại service network. | Muốn dùng endpoint riêng, subnet và SG được chọn hay không? |
| **Auth policy** | Chính sách ở cấp service network và/hoặc service để kiểm soát quyền gọi service. | Principal nào được phép invoke? |
| **AWS RAM** | Chia sẻ các tài nguyên Lattice được hỗ trợ giữa những AWS account. | Account nào sở hữu/tiêu thụ service network? |

**Mấu chốt:** Một service được tạo nhưng chưa **associate** với service network sẽ chưa thể được những client trong mạng dịch vụ đó gọi theo kiến trúc này. Tương tự, một client VPC chưa được kết nối với service network sẽ không truy cập được service chỉ vì đã biết tên service.

### 2.3. Service network: biên giới kết nối

Service network có thể đại diện cho một miền nghiệp vụ, một môi trường hoặc một ranh giới chia sẻ có chủ đích.

Ví dụ:

- **commerce-prod-network** chứa Payments, Orders Backend và Notifications thuộc production.
- **commerce-dev-network** chứa các service tương ứng trong development.
- **analytics-network** dành cho các ứng dụng dữ liệu và báo cáo có yêu cầu truy cập khác.

Service network owner thường chịu trách nhiệm quyết định VPC nào và service nào được associate, chia sẻ network cho account cần thiết, và thiết lập chính sách chung ở phạm vi phù hợp. Service owner chịu trách nhiệm listener, routing, target group và kiểm soát riêng của service.

Không nhất thiết phải dùng một service network khổng lồ cho mọi ứng dụng. Phân chia theo môi trường và ranh giới tin cậy giúp quản lý quyền và tác động của thay đổi.

### 2.4. Service, listener và rule

Giả sử Payments Service có endpoint HTTPS:

- Listener nhận **HTTPS/443**.
- Rule xử lý request theo điều kiện path/header/method được hỗ trợ tương ứng với giao thức và cấu hình.
- Request tới **/payments/** được forward vào target group của Payments.
- Default action phục vụ các request không khớp rule cụ thể, theo cấu hình listener.

VPC Lattice hỗ trợ listener **HTTP**, **HTTPS** và **TLS**. HTTPS listener thường cho khả năng xử lý request ở lớp HTTP, còn **TLS passthrough** cho ứng dụng đích tự kết thúc TLS và có các hạn chế khác với routing HTTP. Không nên xem tất cả protocol là tương đương về khả năng kiểm tra header, auth hoặc routing.

### 2.5. Target group: nơi request được thực thi

Một target group định nghĩa backend cho một service. Những loại target group phổ biến gồm:

| Target type | Định danh backend | Ví dụ |
| --- | --- | --- |
| **INSTANCE** | EC2 instance ID. | Dịch vụ API chạy trực tiếp trên EC2. |
| **IP** | IP của target trong VPC được cấu hình cho target group, theo giới hạn của dịch vụ. | ECS task hoặc EKS Pod sau khi được đăng ký qua cơ chế phù hợp. |
| **LAMBDA** | AWS Lambda function. | Notification API dạng serverless. |
| **ALB** | Application Load Balancer nội bộ, theo những điều kiện hỗ trợ. | Ứng dụng đã có ALB riêng phía trước. |

ECS task và Kubernetes Pod thường được đưa vào target group thông qua cơ chế tích hợp/đăng ký dựa trên **IP**, thay vì coi tên “ECS” hay “Pod” là một loại target-group API riêng. Đối với EKS, có thể dùng **AWS Gateway API Controller** khi kiến trúc và phiên bản hỗ trợ. Với backend loại ALB, cần kiểm tra giới hạn listener, cổng, loại ALB và các điều kiện áp dụng.

Đối với traffic cần gRPC/HTTP/2 hoặc TCP/TLS passthrough, hãy kiểm tra **tính tương thích giữa listener, target protocol version và target type**. Ví dụ TCP target group gắn với TLS listener có hạn chế khác so với HTTPS listener thông thường.

## 3. Một request đi qua VPC Lattice như thế nào?

Xét luồng gọi từ **Orders API ở VPC A** tới **Payments Service** có backend tại **VPC B**.

~~~mermaid
sequenceDiagram
    participant O as Orders API (VPC A)
    participant D as DNS của service
    participant L as VPC Lattice
    participant P as Payments target (VPC B)
    O->>D: Resolve Payments Service domain
    D-->>O: Địa chỉ endpoint VPC Lattice phù hợp
    O->>L: HTTPS request tới Payments Service
    Note over L: Kiểm tra network association, auth và routing phù hợp
    L->>P: Chuyển tiếp request tới target
    P-->>L: Response từ backend
    L-->>O: HTTPS response tới client
~~~

Các bước logic:

1. **Service owner** tạo Payments Service, cấu hình listener và target group.
2. Service được **associate** với service network. VPC A được kết nối với service network bằng **VPC association hoặc service-network VPC endpoint**.
3. Orders API dùng **DNS của service** (do Lattice cấp hoặc custom domain đã cấu hình đúng) để xác định endpoint.
4. Client tạo kết nối tới Lattice. Security Group, tuyến mạng, endpoint và chính sách áp dụng phải cho phép luồng.
5. Nếu sử dụng IAM authorization, request cần đáp ứng yêu cầu **SigV4** và các policy có liên quan.
6. Lattice chọn listener/rule/target group, sau đó chuyển request đến target đang phục vụ theo cơ chế routing.
7. Target xử lý nghiệp vụ; response quay lại qua Lattice.

Điều này giúp nhóm phát triển gọi theo **tên dịch vụ** thay vì quản lý trực tiếp danh sách IP EC2/ECS thay đổi theo Auto Scaling. Tuy nhiên, VPC Lattice **không tự sửa lỗi ứng dụng, giới hạn truy cập dữ liệu ở tầng nghiệp vụ hay bảo đảm tất cả target luôn healthy**.

### 3.1. VPC association và VPC endpoint khác nhau thế nào?

| Tiêu chí | VPC association với service network | Service-network VPC endpoint |
| --- | --- | --- |
| Cách kết nối | Tạo association giữa VPC và service network. | Tạo VPC endpoint loại **service network** trong VPC và trỏ tới network. |
| Kiểm soát mạng | Có thể chỉ định Security Group cho association theo khả năng dịch vụ hỗ trợ. | Chọn subnet và Security Group của endpoint theo cấu hình. |
| Tình huống | Truy cập service trong mạng dịch vụ từ client thuộc VPC được associate. | Muốn kết nối qua các endpoint ENI được đặt trong subnet cụ thể hoặc phù hợp mô hình kết nối PrivateLink/VPC endpoint. |
| DNS và triển khai | Dùng cơ chế DNS/association của Lattice, kiểm tra private DNS theo loại tài nguyên. | Kiểm tra tùy chọn DNS endpoint và các điều kiện truy cập. |

Trong cả hai mô hình, **client vẫn phải có đường tới endpoint và được phép truy cập**. Các chi tiết về DNS và resource configuration có thể khác nhau giữa hai cơ chế, nên cần kiểm tra thông số thực tế của association.

### 3.2. Client chỉ cần mạng tới service được công bố

Nếu VPC A kết nối service network chứa Payments, điều đó không đòi hỏi thiết lập VPC peering để VPC A nhìn thấy mọi subnet trong VPC B. Mục tiêu của Lattice là cung cấp đường truy cập tới service đã được công bố và được cấp quyền.

Đối với luồng **database dạng TCP**, cần phân biệt hai lựa chọn:

- Dùng **VPC Lattice service với TLS listener/TCP target group** khi protocol và yêu cầu hệ thống nằm trong phạm vi hỗ trợ.
- Dùng **VPC Lattice resource configuration/resource gateway** khi mục tiêu là cung cấp truy cập đến một tài nguyên như RDS, một IP hoặc domain theo mô hình resource connectivity.

Không được mặc định áp dụng toàn bộ tính năng HTTP routing/auth của VPC Lattice service lên luồng resource configuration.

## 4. Hai lớp công bố: VPC Lattice service và resource configuration

Amazon VPC Lattice còn hỗ trợ cơ chế **resource configuration**. Thành phần này phục vụ việc cho client truy cập tài nguyên như RDS, endpoint dựa trên IP hoặc tên miền trong những trường hợp dịch vụ hỗ trợ, thông qua **resource gateway** và các association thích hợp.

### 4.1. Khác biệt về mục tiêu

| Câu hỏi | VPC Lattice service | Resource configuration / resource gateway |
| --- | --- | --- |
| Đang công bố điều gì? | Một **dịch vụ ứng dụng** với listener, rule và target group. | Một **tài nguyên** hoặc endpoint theo cấu hình resource connectivity. |
| Có HTTP routing theo rule không? | Có, với listener và protocol hỗ trợ. | Không sử dụng mô hình listener/rule/target group của service theo cùng cách. |
| Tính năng auth policy cấp service/service network? | Có thể áp dụng với **VPC Lattice services**. | **Auth policy của service network không áp dụng cho resource configuration**; resource configuration có cơ chế kiểm soát khác theo tài liệu. |
| Ứng dụng điển hình | API orders/payments, microservices, Lambda. | Cho phép client sử dụng tài nguyên ở VPC khác như endpoint database hoặc IP. |
| Cấu hình phía cung cấp | Service, listener, target group, target và association. | Resource gateway, resource configuration, association/share theo kiến trúc. |

**Resource gateway** là điểm vào trong VPC chứa tài nguyên được cung cấp. **Resource configuration** mô tả tài nguyên được phép công bố, còn các thành phần association và quyền quyết định client nào truy cập được.

Ở kiến trúc truy cập RDS, **mạng được thông** chưa đủ để query thành công: ứng dụng vẫn cần thông tin xác thực DB, TLS và quyền database phù hợp. IAM/Lattice network access không tự động trao quyền đọc bảng dữ liệu.

### 4.2. Không dùng chung giả định bảo mật

Một nhầm lẫn nguy hiểm là đặt auth policy cho service network rồi cho rằng mọi resource configuration cũng được chính sách đó bảo vệ. Theo tài liệu AWS, **service-network auth policy không áp dụng cho resource configurations**. Vì vậy khi công bố một database hoặc resource khác, phải rà soát các cơ chế kiểm soát thực sự hỗ trợ đối tượng đó: resource sharing/association, resource policy, Security Group, database credentials và các lớp bảo vệ liên quan.

Bài học này tập trung vào **kết nối dịch vụ giữa nhiều VPC**; phần resource configuration giúp tránh áp dụng sai mô hình khi yêu cầu thực tế là kết nối tài nguyên thay vì gọi API ứng dụng.

## 5. Thiết kế nhiều VPC và nhiều AWS account

Giả sử một doanh nghiệp chia ứng dụng theo account:

- **Account A — 111122223333:** VPC Orders, chứa client Orders API.
- **Account B — 444455556666:** VPC Payments, chứa target Payments API.
- **Service network:** commerce-prod-network, được đội hạ tầng quản trị và chia sẻ cho các bên cần tham gia.

Hai dãy account ID chỉ là **giá trị minh họa**. Bạn cần thay chúng bằng ID phù hợp trong môi trường thực tế.

### 5.1. Sơ đồ tổng thể

~~~mermaid
flowchart LR
    subgraph ACCA["Account A — VPC Orders"]
        O1["Orders API / ECS task"]
    end
    subgraph NETWORK["commerce-prod-network"]
        S["Payments Service HTTPS/443"]
    end
    subgraph ACCB["Account B — VPC Payments"]
        TG["Payments target group"]
        P1["Payments EC2/ECS 1"]
        P2["Payments EC2/ECS 2"]
    end
    RAM["AWS RAM: chia sẻ quyền dùng network/service phù hợp"]
    O1 -->|"VPC association + request hợp lệ"| S
    S --> TG
    TG --> P1
    TG --> P2
    RAM -.-> NETWORK
~~~

### 5.2. Các bước triển khai theo quyền sở hữu

**Bước 1 — Chọn phạm vi network.** Xác định môi trường, AWS Region, account owner, service owners và VPC consumers. Đặt tên rõ ràng theo nghiệp vụ/môi trường.

**Bước 2 — Chuẩn bị Payments backend.** Bảo đảm target có khả năng xử lý request, đáp ứng health check, dùng đúng protocol/port và Security Group phù hợp.

**Bước 3 — Tạo target group, service và listener.** Service owner tạo target group hỗ trợ loại workload, tạo Payments Service, cấu hình HTTPS/443 và routing.

**Bước 4 — Tạo hoặc chọn service network.** Network owner xây dựng ranh giới logic cho môi trường production và quyết định chính sách truy cập chung.

**Bước 5 — Chia sẻ tài nguyên cross-account khi cần.** Dùng **AWS RAM** chia sẻ service network và/hoặc các tài nguyên Lattice hỗ trợ cho account khác, kiểm tra quyền IAM của principal quản trị và trạng thái chấp nhận share nếu áp dụng.

**Bước 6 — Associate service và VPC.** Payments Service được kết nối với service network; VPC Orders được associate hoặc kết nối bằng service-network VPC endpoint. Các association phải ở trạng thái phù hợp trước khi kiểm thử.

**Bước 7 — Thiết lập security/auth.** Kiểm tra IAM permissions cho các thao tác quản trị, auth policy của service network/service, Security Group ở phía client/association/target, TLS và tên miền.

**Bước 8 — Kiểm thử đường đi và quan sát.** Gọi Payments từ Orders bằng một principal có quyền, xác minh response, health, log, metrics và hành vi khi quyền bị từ chối hoặc target lỗi.

Thứ tự thực hiện thực tế có thể thay đổi theo công cụ IaC và quyền sở hữu, nhưng cuối cùng **phải đủ cả liên kết mạng dịch vụ, liên kết service, nguồn gọi, quyền, listener, target và DNS**.

### 5.3. Vì sao cross-account cần thêm bước chia sẻ?

Một VPC trong account A không tự nhiên thấy và có quyền associate với service network thuộc account B. AWS RAM giúp chia sẻ các tài nguyên được AWS hỗ trợ, nhưng **quyền nhận share** và **quyền truy cập data-plane** là hai vấn đề khác nhau:

- **AWS RAM + IAM quản trị:** principal nào được tạo association, quản lý hoặc sử dụng tài nguyên Lattice.
- **VPC Lattice network association:** client VPC nào được kết nối với network.
- **Auth policy + identity permissions (khi bật AWS_IAM):** workload nào có thể gửi request tới service.
- **Application authorization:** người dùng cuối có được phép thực hiện nghiệp vụ như hoàn tiền hay xem dữ liệu không.

Nếu đã share service network nhưng quên tạo VPC association, client vẫn không có đường truy cập. Nếu đường mạng đã hoạt động nhưng service yêu cầu SigV4 và client không ký request, request vẫn có thể bị từ chối.

### 5.4. CIDR trùng lặp và giới hạn địa lý

VPC Lattice giúp giảm nhu cầu phải thiết lập định tuyến IP trực tiếp giữa mọi VPC để gọi những service đã công bố; điều này có lợi cho các tổ chức có dải CIDR khó phối hợp. Tuy nhiên **không nên tự động kết luận mọi mô hình IP chồng lấn đều được hỗ trợ cho mọi kiểu target, resource connectivity, protocol, endpoint và mạng trung gian**.

Trong môi trường production, cần xác minh các hạn chế của kiểu kết nối được chọn, phạm vi Region, VPC, account, địa chỉ IPv4/IPv6 và quota hiện hành. Ví dụ trong bài này sử dụng các VPC cùng Region để làm rõ nguyên lý.

## 6. Bảo mật theo nhiều lớp

VPC Lattice cung cấp các lớp kiểm soát bổ sung nhau. Không lớp nào nên được coi là thay thế hoàn toàn cho các lớp còn lại.

| Lớp | Câu hỏi cần trả lời | Kiểm soát điển hình |
| --- | --- | --- |
| **Membership** | VPC có đường tham gia service network chưa? Service có được công bố vào network chưa? | Service/VPC associations, service-network endpoint, AWS RAM. |
| **Network** | Client và Lattice có thể kết nối tới service target qua protocol/port thích hợp không? | Security Group ở client, association/endpoint, target; route và NACL liên quan. |
| **VPC Lattice auth** | Principal nào được phép gọi service? | Auth type **AWS_IAM**, auth policy của service network/service, SigV4, identity policy. |
| **Transport** | Dữ liệu có cần mã hóa và xác thực điểm cuối không? | HTTPS/TLS, certificate, custom domain, backend protocol. |
| **Application** | Caller có được phép xem/sửa dữ liệu nghiệp vụ này không? | Access token, session, RBAC/ABAC, validation và audit ở ứng dụng. |
| **Observability** | Có phát hiện lỗi, request bị từ chối và thay đổi cấu hình không? | Metrics, access logs, CloudTrail, tracing/log backend. |

### 6.1. Auth type NONE và AWS_IAM

VPC Lattice service/service network hỗ trợ lựa chọn cơ chế auth phù hợp, thường gặp:

- **NONE:** không bật lớp xác thực/phân quyền IAM của VPC Lattice tại thành phần đó. Khả năng truy cập vẫn bị chi phối bởi membership, network, auth ở lớp khác nếu có và ứng dụng.
- **AWS_IAM:** yêu cầu đánh giá **VPC Lattice auth policy**. Request được xác thực theo AWS Signature Version 4 (**SigV4**) khi chính sách yêu cầu principal đã xác thực.

Bật AWS_IAM nhưng **không có Allow phù hợp** trong các chính sách liên quan khiến request bị từ chối theo mặc định. Với một request đã ký, bên gọi cũng phải có **IAM identity-based permissions** tương ứng; các auth policy ở service network và service nếu được bật đều cần cho phép. **Explicit Deny** có ưu tiên theo quy tắc đánh giá chính sách.

### 6.2. Phân biệt hai họ IAM action

Một người triển khai thường gặp hai nhóm action có mục đích khác nhau:

1. **vpc-lattice:*** — API **control plane** để tạo, đọc, sửa service network, service, association, target group hoặc chính sách (tùy action).
2. **vpc-lattice-svcs:Invoke** — action **data plane** dùng trong auth policy/identity policy để cho phép gọi dịch vụ qua VPC Lattice. Ngoài Invoke còn có action liên quan được tài liệu IAM của dịch vụ liệt kê.

Ví dụ, cấp **vpc-lattice:GetService** để người vận hành xem cấu hình một service **không đồng nghĩa** cấp quyền **vpc-lattice-svcs:Invoke** cho ứng dụng gọi service ấy. Ngược lại, workload chỉ cần invoke API không nên được cấp quyền quản trị toàn bộ service network.

### 6.3. Ví dụ auth policy ở cấp service

Giả sử service Payments thuộc account B, chỉ role **OrdersClientRole** của account A được invoke:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersClientInvokePayments",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/OrdersClientRole"
      },
      "Action": "vpc-lattice-svcs:Invoke",
      "Resource": "arn:aws:vpc-lattice:ap-southeast-1:444455556666:service/svc-0123456789abcdef0/*"
    }
  ]
}
~~~

Đoạn trên minh họa **auth policy gắn vào Payments Service** có auth type **AWS_IAM**. Đây chưa phải cấu hình hoàn chỉnh: cần đối chiếu ARN thực, cấu trúc tài nguyên theo IAM Service Authorization Reference, policy ở service network nếu bật, và các điều kiện truy cập khác.

Role nguồn cũng cần **identity-based policy** cho phép invoke service phù hợp:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokePaymentsService",
      "Effect": "Allow",
      "Action": "vpc-lattice-svcs:Invoke",
      "Resource": "arn:aws:vpc-lattice:ap-southeast-1:444455556666:service/svc-0123456789abcdef0/*"
    }
  ]
}
~~~

**Không dùng Principal trong identity-based policy** của role. Principal xuất hiện trong auth policy vì đó là dạng resource-based policy.

Một auth policy ở **service-network level** có thể dùng để cấp quyền phạm vi rộng theo tổ chức/nhóm, trong khi service owner dùng auth policy riêng để giới hạn một API nhạy cảm hơn. Khi cả hai có auth type AWS_IAM, quyền cần phù hợp ở các lớp liên quan.

### 6.4. Ký request bằng SigV4

Khi IAM auth yêu cầu caller được xác thực, một request HTTP/HTTPS thông thường từ ứng dụng phải được ký bằng **AWS Signature Version 4** theo yêu cầu VPC Lattice. Có thể dùng AWS SDK hoặc bộ ký SigV4 tương thích với service để tránh tự xử lý khóa/chuỗi ký không đúng.

Ứng dụng nên nhận **temporary credentials từ role** gắn với EC2/ECS/EKS/Lambda hoặc cơ chế liên kết danh tính phù hợp. Tránh hard-code access key và secret key trong source code, environment không được kiểm soát hay pipeline logs.

**Lưu ý:** Auth policy của VPC Lattice không thay thế xác thực/ủy quyền người dùng cuối. Nếu Orders API gọi Payments thay mặt khách hàng, Payments vẫn cần kiểm tra quyền nghiệp vụ, chống thao tác lặp và audit nghiệp vụ phù hợp.

### 6.5. Security Group trong VPC Lattice

Security Group kiểm soát network traffic, còn auth policy kiểm soát quyền invoke ở lớp ứng dụng IAM.

Với **VPC association**, có thể gắn Security Group để giới hạn những client trong VPC được kết nối tới service network. Với **service-network VPC endpoint**, Security Group của endpoint kiểm soát traffic qua endpoint. Ở phía backend, **Security Group của target** phải cho phép traffic đến từ hạ tầng VPC Lattice theo mô hình nguồn được AWS hỗ trợ.

Đặc biệt, **không giả định target có thể đặt source = Security Group của client trong VPC khác**. Đường đi của traffic thông qua Lattice có nguồn theo cơ chế data plane của Lattice; đối với một số target như EC2, AWS cung cấp **AWS-managed prefix list** cho VPC Lattice, ví dụ:

- **com.amazonaws.ap-southeast-1.vpc-lattice**
- **com.amazonaws.ap-southeast-1.ipv6.vpc-lattice** khi tính năng IPv6 áp dụng.

Khi cần, dùng managed prefix list làm **source của inbound target SG** cho cổng backend và health check phù hợp, hoặc làm **destination** trong outbound SG của client nếu bị giới hạn egress và cách kết nối sử dụng VPC association. Cần chọn đúng prefix list ID/Region và kiểm tra hướng dẫn SG cho loại endpoint/target đang dùng.

Ví dụ quy tắc logic:

| Vị trí | Hướng | Rule minh họa |
| --- | --- | --- |
| Client SG | Outbound | TCP/443 tới đường đi Lattice phù hợp (prefix list hoặc endpoint theo mô hình kết nối). |
| VPC association / endpoint SG | Inbound | Chỉ cho phép nguồn client và cổng listener cần thiết, theo mô hình association. |
| Target SG | Inbound | Cho phép cổng target/health check từ nguồn Lattice do AWS tài liệu hóa. |
| Ứng dụng Payments | Authorization | Chỉ Orders service có quyền gọi nghiệp vụ phù hợp. |

Nếu client trả về **403** từ Lattice, cần kiểm tra **auth type, chữ ký và policy**, không chỉ mở thêm inbound SG. Nếu kết nối **timeout**, hãy kiểm tra DNS, association, endpoint, SG, network path và trạng thái backend.

## 7. DNS, HTTP/HTTPS và TLS

### 7.1. Tên miền do VPC Lattice cấp

Khi tạo VPC Lattice service, AWS cung cấp một **DNS name** riêng của service. Tên miền dịch vụ có thể theo dạng minh họa:

~~~text
payments-svc-0123456789abcdef0.<generated-id>.vpc-lattice-svcs.ap-southeast-1.on.aws
~~~

Chuỗi thực tế phải lấy từ thuộc tính DNS của service do AWS trả về; không nên tự suy ra chuỗi DNS chính xác từ tên/ID minh họa.

Client trong VPC được kết nối với service network có thể dùng DNS này để gọi service, nếu mạng và quyền truy cập hợp lệ.

### 7.2. Custom domain

Doanh nghiệp có thể muốn ứng dụng gọi **payments.internal.example.com**. VPC Lattice cho phép cấu hình **custom domain name** cho service theo điều kiện hỗ trợ, kết hợp bản ghi DNS trỏ đến tên miền của service.

Với **HTTPS trên custom domain**, phải cung cấp certificate phù hợp trong **AWS Certificate Manager (ACM)**. VPC Lattice không tự cung cấp certificate mặc định hợp lệ cho mọi custom domain; nếu thiếu certificate tương ứng, HTTPS qua tên miền tự chọn có thể không hoạt động.

Ví dụ:

~~~text
Client Orders API
    -> https://payments.internal.example.com
    -> DNS trỏ đến Lattice service
    -> listener HTTPS/443
    -> Payments target
~~~

Bạn phải cấu hình DNS zone/record để client phân giải được tên, đúng certificate và lựa chọn network association. Không được coi việc thêm một bản ghi DNS là đủ để cấp quyền truy cập.

### 7.3. HTTPS listener và TLS passthrough

| Cách tiếp nhận | Điều xảy ra ở Lattice | Tình huống |
| --- | --- | --- |
| **HTTP listener** | Nhận HTTP, định tuyến theo các khả năng được hỗ trợ. | Nội bộ/kiểm thử hoặc trường hợp có bảo vệ phù hợp và yêu cầu mã hóa được đánh giá. |
| **HTTPS listener** | Lattice xử lý TLS của kết nối client bằng certificate được quản lý/cung cấp phù hợp, có thể định tuyến HTTP. | API HTTPS giữa các dịch vụ. |
| **TLS listener (passthrough)** | Lattice chuyển luồng TLS tới target để ứng dụng đích xử lý TLS; các chức năng phân tích HTTP/routing có hạn chế. | Ứng dụng cần tự kết thúc TLS hoặc protocol phù hợp với TLS passthrough. |

**TLS đầu vào và TLS từ Lattice đến target là hai đoạn cần xem riêng.** Mã hóa đến Lattice không mặc nhiên bảo đảm target luôn được kết nối bằng HTTPS; target group có protocol/cấu hình riêng. Khi dữ liệu nhạy cảm hoặc có yêu cầu compliance, hãy xác minh toàn bộ đường truyền.

### 7.4. DNS không phải là cơ chế xác thực

Khi client biết hostname của Payments Service, nó **chưa được tự động cấp quyền invoke**. Ngược lại, IAM policy đúng nhưng DNS không phân giải hoặc client chưa kết nối service network thì ứng dụng vẫn không gọi được service.

Đánh giá DNS, mạng, IAM và ứng dụng theo từng lớp giúp tránh xử lý sai nguyên nhân.

## 8. Định tuyến, sức khỏe target và khả năng phục hồi

### 8.1. Listener rule

Listener rule quyết định request đến target group nào, dựa trên rule/condition có hỗ trợ cho giao thức đang dùng. Có thể có default action và các rule có độ ưu tiên.

Ví dụ tại Payments Service:

| Điều kiện minh họa | Target group | Ý nghĩa |
| --- | --- | --- |
| Path khớp **/payments/v1/*** | **payments-v1-tg** | API v1. |
| Path khớp **/payments/v2/*** | **payments-v2-tg** | API v2. |
| Default | **fallback-tg** hoặc response phù hợp theo cấu hình hỗ trợ. | Xử lý request còn lại. |

Cần kiểm tra cú pháp path matching và giới hạn action/rule của listener trước khi áp dụng IaC. Một số loại listener (đặc biệt TLS passthrough) có những giới hạn mạnh hơn HTTPS listener.

### 8.2. Health checks và target availability

VPC Lattice có thể kiểm tra sức khỏe target theo các giao thức, cổng và health check được hỗ trợ. Khi thiết kế:

1. Tạo endpoint health check thể hiện khả năng phục vụ phù hợp (không chỉ process còn chạy).
2. Bảo đảm SG và các lớp mạng cho phép traffic health check cần thiết.
3. Đăng ký nhiều target và phân tán AZ nếu SLA/RTO yêu cầu.
4. Theo dõi tình trạng target, tỷ lệ lỗi, latency và thử nghiệm các kịch bản target bị lỗi.

**Chi tiết cần nhớ:** Với mô hình target group nhất định, nếu **tất cả target đều unhealthy**, VPC Lattice có thể **fail open** và tiếp tục phân phối request đến các target unhealthy theo cơ chế được tài liệu hóa. Vì vậy không nên mặc định rằng Lattice luôn dừng gửi traffic tới toàn bộ backend khi health check thất bại. Cần kiểm tra hành vi theo loại target/protocol và thiết kế timeout/retry/circuit breaker ở ứng dụng.

### 8.3. Region và AZ

AWS hỗ trợ cơ chế phục vụ ứng dụng trên hạ tầng nhiều AZ. Với VPC Lattice, khả năng **AZ affinity** và lựa chọn đường tới các endpoint/target phù hợp giúp cải thiện hiệu quả truy cập, nhưng **tính sẵn sàng của ứng dụng vẫn phụ thuộc target và kiến trúc**.

Không nên suy ra chỉ cần tạo service network là hệ thống có HA. Nếu Payments chỉ chạy trên một EC2 instance trong một AZ, Lattice không thể thay thế việc triển khai thêm target hoặc cơ chế phục hồi phù hợp.

### 8.4. Timeout, retry và idempotency

Kết nối mạng ổn định không bảo đảm từng request luôn thành công. Các ứng dụng phân tán vẫn phải xử lý:

- **Timeout** ở client và các lớp phía server.
- **Retry có backoff/jitter** và giới hạn số lần thử.
- **Idempotency key** khi thực hiện thanh toán hoặc nghiệp vụ không được nhân đôi.
- **Circuit breaker** hoặc giới hạn tải khi downstream lỗi.
- **Observability** để phân biệt lỗi từ chính Lattice, backend và nghiệp vụ.

Ví dụ nếu Orders API timeout ngay sau khi gọi Payments, Orders không thể biết chắc request đã được Payments xử lý hay chưa. Nếu retry mà không có idempotency, ứng dụng có thể tạo giao dịch trùng.

## 9. Giám sát và xử lý sự cố

### 9.1. Những tín hiệu cần quan sát

| Tầng | Tín hiệu | Công cụ/nguồn quan sát |
| --- | --- | --- |
| Client | DNS lookup, TLS handshake, timeout, HTTP status, retry. | Log/tracing ứng dụng. |
| VPC Lattice | Số request, lỗi, latency và tình trạng service/target khi áp dụng. | Amazon CloudWatch metrics và VPC Lattice console. |
| Request qua Lattice | Client VPC, service, path, response code, thời gian, lượng dữ liệu theo trường hỗ trợ. | **VPC Lattice access logs** (nếu đã bật). |
| Hạ tầng backend | CPU/memory, container restart, RDS status, app exceptions. | CloudWatch, application logs, service-specific metrics. |
| Thay đổi cấu hình | Ai tạo/xóa/sửa service, association, auth policy. | AWS CloudTrail và quy trình quản trị thay đổi. |

**Access logs của VPC Lattice là tính năng cần bật, mặc định không nên giả định đã được bật.** Tùy loại tài nguyên và cấu hình, log có thể gửi tới CloudWatch Logs, Amazon S3 hoặc Amazon Data Firehose. Việc thu thập/lưu trữ/phân tích log phát sinh chi phí.

Lưu ý VPC Lattice **service access logs** và **resource access logs** có thể có định dạng/trường dữ liệu khác nhau; không thể dùng parser của HTTP service log để mặc định giải nghĩa resource TCP log.

### 9.2. Chẩn đoán theo dấu hiệu

| Triệu chứng | Khả năng cần kiểm tra | Bước tiếp theo |
| --- | --- | --- |
| DNS không phân giải | DNS do Lattice cấp hay custom domain sai, VPC resolver, association/endpoint chưa phù hợp. | Xem thuộc tính DNS service, record, DNS resolver và trạng thái kết nối VPC. |
| Kết nối timeout | SG client/association/endpoint/target, đường mạng, listener/port, target không phản hồi. | Kiểm tra cả hai đầu, health check, NACL/route và endpoint. |
| HTTP **403** | SigV4 thiếu/sai, auth type AWS_IAM, policy ở service network/service hoặc identity deny. | Đọc auth policy, xác định role thực tế, đối chiếu chữ ký và action Invoke. |
| HTTP **404** | Sai hostname/path, service không tồn tại/không được associate đúng network, rule không khớp hoặc backend trả 404. | Phân biệt status phát sinh tại Lattice hay backend qua logs. |
| HTTP **5xx** | Backend lỗi, target unhealthy, kết nối tới target trục trặc hoặc lỗi từ service network. | Kiểm tra metrics, access logs, target status và app logs. |
| Chỉ account A gọi lỗi | RAM share, VPC association, auth principal/role, SG hoặc DNS riêng của account A. | So sánh những association/permissions của account hoạt động với account gặp lỗi. |
| Service chạy nhưng chi phí tăng | Service tồn tại nhiều giờ, traffic/request tăng, data processing hoặc log tăng. | Xem service inventory, CloudWatch, billing/Cost Explorer và bảng giá theo Region. |

### 9.3. Cây chẩn đoán

~~~mermaid
flowchart TD
    A["Client không gọi được VPC Lattice service"] --> B{"Service đã associate với network?"}
    B -->|"Chưa"| B1["Tạo/sửa service association phù hợp"]
    B -->|"Rồi"| C{"VPC client đã kết nối network?"}
    C -->|"Chưa"| C1["Kiểm tra VPC association hoặc service-network endpoint"]
    C -->|"Rồi"| D{"DNS và HTTPS/TLS có hoạt động?"}
    D -->|"Không"| D1["Kiểm tra hostname, record, certificate, listener, SG và đường mạng"]
    D -->|"Có"| E{"Request bị 403?"}
    E -->|"Có"| E1["Kiểm tra AWS_IAM, SigV4, identity policy và auth policy"]
    E -->|"Không"| F{"Target healthy và ứng dụng phản hồi?"}
    F -->|"Không"| F1["Kiểm tra target group, health check, backend SG, app logs"]
    F -->|"Có"| G["Đối chiếu response/status, logs và nghiệp vụ"]
~~~

Đây là thứ tự đánh giá gợi ý, không phải quy tắc bắt buộc. Nhiều lỗi có thể tồn tại đồng thời; luôn ghi nhận **source VPC, target service, hostname, Region, role, request ID và thời điểm lỗi** để điều tra.

## 10. Thực hành đọc cấu hình bằng AWS CLI

Ví dụ sử dụng AWS CLI v2 và **chỉ đọc**, không tạo hay thay đổi tài nguyên. Thay ID minh họa bằng giá trị thật từ môi trường đã được phép truy cập. Các lệnh cần IAM permissions tương ứng và phải chạy với đúng AWS account/Region.

### 10.1. Xác định account và Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Nếu tài nguyên được tạo ở Region khác với profile CLI, câu lệnh có thể trả danh sách rỗng dù service vẫn tồn tại ở đúng Region.

### 10.2. Liệt kê service network và service

~~~bash
aws vpc-lattice list-service-networks \
  --region ap-southeast-1

aws vpc-lattice list-services \
  --region ap-southeast-1
~~~

Xác định service network ID dạng **sn-...** và service ID dạng **svc-...**, phân biệt với VPC ID dạng **vpc-...**. Đối với tài nguyên được chia sẻ qua RAM, kiểm tra quyền visibility và account đang đăng nhập.

### 10.3. Xem service nào nằm trong network

~~~bash
aws vpc-lattice list-service-network-service-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Nếu Payments Service không được associate vào network mà Orders dùng, request từ Orders sẽ không thể sử dụng service ấy theo thiết kế mong muốn.

### 10.4. Xem VPC được kết nối với network

~~~bash
aws vpc-lattice list-service-network-vpc-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-service-network-vpc-endpoint-associations \
  --service-network-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Hai danh sách tương ứng **VPC associations** và **service-network VPC endpoints**; trường hợp môi trường chỉ dùng một loại thì danh sách còn lại có thể trống. Kiểm tra trạng thái association cùng VPC ID, SG và account liên quan.

### 10.5. Xem listener, target group và target

~~~bash
aws vpc-lattice get-service \
  --service-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-listeners \
  --service-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice list-target-groups \
  --region ap-southeast-1

aws vpc-lattice list-targets \
  --target-group-identifier tg-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Kiểm tra **service DNS**, listener protocol/port, target group type/protocol, số lượng target và trạng thái health. Lệnh **list-target-groups** có thể cần xử lý phân trang và quyền ở account sở hữu target group, đặc biệt với tài nguyên chia sẻ.

### 10.6. Xem auth policy và access log subscriptions

~~~bash
# Có thể áp dụng cho service network hoặc service đã bật IAM auth.
aws vpc-lattice get-auth-policy \
  --resource-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1

aws vpc-lattice get-auth-policy \
  --resource-identifier sn-0123456789abcdef0 \
  --region ap-southeast-1

# Kiểm tra cấu hình gửi access logs của service.
aws vpc-lattice list-access-log-subscriptions \
  --resource-identifier svc-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Không có auth policy được cấu hình hoặc auth type **NONE** không có nghĩa ứng dụng tự động an toàn. Ngược lại, với **AWS_IAM**, thiếu Allow từ một policy bắt buộc có thể dẫn đến 403.

### 10.7. Kiểm tra managed prefix list của VPC Lattice

~~~bash
aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.ap-southeast-1.vpc-lattice \
  --region ap-southeast-1
~~~

Nếu client SG giới hạn outbound hoặc target SG cần Allow từ Lattice, đối chiếu **managed prefix list ID** từ Region đang dùng với những rule trong **describe-security-groups** hoặc **describe-security-group-rules**. Không tự sao chép một dãy IP tìm được trên Internet thành rule tồn tại lâu dài nếu AWS có cơ chế prefix list được quản lý phù hợp.

### 10.8. Kiểm thử request từ đúng môi trường

Để kiểm tra connectivity, gọi hostname Payments từ **chính container/EC2/Lambda** nằm trong VPC client, theo policy phù hợp. Ví dụ với service không bật AWS_IAM ở các lớp liên quan, một yêu cầu HTTPS có thể được thử như sau:

~~~bash
curl --verbose --max-time 10 \
  https://payments.internal.example.com/health
~~~

**Chỉ dùng lệnh mẫu nếu domain đã được tạo và bạn có quyền kiểm thử.** Khi service yêu cầu AWS_IAM, request phải được **ký SigV4**; lệnh curl thông thường không thực hiện việc đó và có thể nhận **403**. Không “khắc phục” bằng cách vô hiệu hóa IAM auth nếu thiết kế yêu cầu xác thực. Hãy sử dụng client/SDK hỗ trợ ký request và giữ credentials an toàn.

Kiểm thử thành công nên bao gồm cả **trường hợp bị từ chối có chủ đích**: principal không được cấp quyền, VPC không nằm trong network và endpoint không hợp lệ phải được xử lý theo thiết kế.

## 11. So sánh VPC Lattice với các lựa chọn kết nối AWS

Lựa chọn công cụ theo **bài toán**, không theo tiêu chí một dịch vụ luôn tốt hơn mọi giải pháp khác.

| Tiêu chí | **VPC Lattice service** | **VPC peering** | **Transit Gateway** | **AWS PrivateLink** |
| --- | --- | --- | --- | --- |
| Trọng tâm | Kết nối, định tuyến, bảo vệ và quan sát **service/application**. | Kết nối mạng IP giữa **hai VPC** theo định tuyến. | Kết nối và quản lý **nhiều VPC/mạng** theo mô hình hub. | Công bố và truy cập **dịch vụ/tài nguyên cụ thể** qua endpoint theo tính năng hỗ trợ. |
| Mức trừu tượng | Service, listener, rules, target groups, network association. | CIDR, route tables, SG/NACL. | Attachments, route tables, CIDR và chính sách mạng. | Endpoint service, interface endpoint, endpoint policies/SG khi áp dụng. |
| Khả năng kết nối rộng giữa VPC | Chỉ service/resource được công bố theo mô hình Lattice. | Kết nối mạng theo route và quyền. | Kết nối mạng theo route và attachments. | Điểm truy cập tới service/resource được công bố. |
| Điều khiển ở lớp ứng dụng | HTTP/HTTPS routing và IAM auth policy khi hỗ trợ. | Không tích hợp ở lớp VPC peering. | Không tích hợp ở lớp Transit Gateway. | Tùy loại endpoint và dịch vụ cung cấp, không mặc định có HTTP routing kiểu Lattice. |
| Trường hợp điển hình | Microservices nhiều team/account, API east-west. | Ít VPC, kết nối IP đơn giản. | Nhiều VPC/on-prem, cần định tuyến mạng tổng thể. | Truy cập private tới dịch vụ AWS, SaaS hoặc endpoint cụ thể. |
| Chi phí cần đánh giá | Giờ service, dữ liệu xử lý, request/kết nối và log theo bảng giá. | Data transfer và những khoản liên quan. | Attachment, data processing và những khoản liên quan. | Endpoint hours, data processing và những khoản liên quan. |

VPC Lattice có thể kết hợp với các giải pháp khác. Chẳng hạn doanh nghiệp vẫn dùng Transit Gateway để kết nối tới mạng on-prem, nhưng dùng Lattice cho giao tiếp giữa các service nội bộ có phạm vi rõ ràng.

**Không nên chọn Lattice chỉ để kết nối tùy ý mọi private IP của hai VPC** khi nhu cầu là định tuyến mạng tổng quát. Ngược lại, dùng một mạng peering/Transit Gateway phức tạp để quản lý hàng trăm API độc lập có thể khiến bài toán bảo mật ở cấp service khó kiểm soát nếu thiếu các lớp khác.

### 11.1. Khi nào VPC Lattice có lợi thế rõ ràng?

- Có nhiều ứng dụng phân tán qua **VPC/account**, cần gọi API theo định danh service.
- Muốn tách nhóm quản trị **service network** khỏi nhóm sở hữu backend.
- Muốn định tuyến đến EC2/ECS/EKS/Lambda target theo cơ chế được quản lý.
- Cần **auth policy** theo IAM principal cho kết nối API, cùng metrics và access logs.
- Không muốn yêu cầu mọi đội phát triển phối hợp trực tiếp từng tuyến VPC-to-VPC chỉ để gọi những API nội bộ.

### 11.2. Khi nào cân nhắc công cụ khác?

- Cần định tuyến IP thông dụng giữa cả hai mạng hoặc truy cập nhiều protocol/cổng bất kỳ → đánh giá **peering/Transit Gateway**.
- Chỉ cần tiêu thụ một dịch vụ qua endpoint private với mô hình publisher/consumer tương ứng → đánh giá **PrivateLink**.
- Cần kết nối hybrid on-prem với AWS qua VPN/Direct Connect → phải thiết kế các thành phần kết nối hybrid phù hợp.
- Cần API public cho người dùng Internet, authentication/throttling ở biên và quản lý API product → đánh giá **Amazon API Gateway**, ALB, CloudFront và WAF theo mục đích.

## 12. Chi phí và vận hành

VPC Lattice không chỉ mang chi phí của các EC2/ECS/Lambda target, mà còn có chi phí riêng cho service và data plane.

Các nhóm chi phí dịch vụ cần đánh giá theo bảng giá hiện hành và Region:

1. **Service provisioning:** phí theo số lượng/thời gian service được cấp phát.
2. **Data processing:** lượng dữ liệu request/response được xử lý qua Lattice.
3. **HTTP requests hoặc TCP connections:** tùy loại listener/traffic được tính phí.
4. **Access log delivery/storage/analysis:** phụ thuộc hệ thống nhận log như CloudWatch Logs, S3, Firehose.
5. **Hạ tầng backend và mạng liên quan:** EC2, ECS, Lambda, NAT, endpoint, database, các luồng dữ liệu khác theo kiến trúc.

Nếu chỉ có rất ít dịch vụ ít traffic nhưng được để ở trạng thái provisioned cả tháng, chi phí theo giờ service vẫn là yếu tố cần tính. Nếu traffic lớn, data processing và request/connection charges có thể quan trọng hơn.

Không ghi cứng một đơn giá USD cho mọi môi trường: giá, Region, tính năng và điều kiện tính phí có thể thay đổi. Khi tính toán ngân sách, dùng **trang Pricing chính thức** và AWS Pricing Calculator nếu phù hợp; xác nhận riêng phí của mô hình **resource configuration/resource endpoint** vì cách tính có thể khác với VPC Lattice services.

### 12.1. Vận hành theo vòng đời

- Chỉ associate service/VPC vào đúng network cần thiết.
- Review IAM/RAM share khi nhân sự hoặc ứng dụng thay đổi.
- Quản lý listener/rule/target group và chính sách bằng IaC nếu có thể.
- Gắn tag theo team, môi trường, cost center và service owner.
- Kiểm tra stale association, service không dùng, target unhealthy, log retention và quota.
- Theo dõi request count, error rate và latency theo từng service.
- Định kỳ diễn tập trường hợp mất target/AZ hoặc mất một thành phần phụ thuộc.

Quản trị tập trung service network giúp tạo tiêu chuẩn kết nối chung, nhưng không làm mất trách nhiệm của đội phát triển với lỗi ứng dụng và dữ liệu nghiệp vụ.

## 13. Tình huống ứng dụng

### Tình huống A — Orders gọi Payments ở AWS account khác

**Yêu cầu:** Orders ở account A cần gọi Payments ở account B, chỉ chấp nhận principal runtime được cấp quyền.

**Thiết kế:**

1. Payments Service có listener HTTPS/443, target group tới backend khỏe mạnh.
2. Network owner chia sẻ service network và thiết lập các association cho service/VPC theo quyền phù hợp.
3. VPC Orders kết nối với service network; client có DNS và egress phù hợp.
4. Service áp dụng auth type AWS_IAM và policy chỉ cho phép **OrdersClientRole**.
5. OrdersClientRole có identity-based Allow Invoke; ứng dụng ký request SigV4.
6. Payments tự kiểm tra quyền nghiệp vụ, idempotency và ghi audit.

**Kiểm chứng:** OrdersClientRole gọi thành công, role khác nhận từ chối theo policy, VPC không kết nối network không truy cập được dịch vụ. Xác nhận access logs, target health và dữ liệu giao dịch không bị nhân đôi khi retry.

### Tình huống B — Thêm Notifications Lambda

**Yêu cầu:** Sau khi thanh toán, Orders cần gửi thông báo qua một Lambda được quản lý ở account khác.

**Thiết kế:** Công bố Notification Service qua VPC Lattice với Lambda target theo cơ chế hỗ trợ, có chính sách invoke giới hạn caller. Đảm bảo Lambda execution role chỉ được gọi dịch vụ hoặc đọc dữ liệu thật sự cần. Không nhầm **quyền gọi Notification Service qua Lattice** với **quyền trực tiếp lambda:InvokeFunction** của mọi client.

**Kiểm chứng:** Những client chỉ có quyền với Payments không tự động có quyền gọi Notifications nếu auth policy được phân chia phù hợp.

### Tình huống C — Ứng dụng trong nhiều VPC cần truy cập RDS

**Yêu cầu:** Một số hệ thống cần kết nối tới cùng một database được quản lý tập trung.

**Phân tích:** Đây là bài toán **truy cập tài nguyên** có giao thức SQL/TCP, không giống hẳn API HTTPS có routing theo path. Cân nhắc resource configuration/resource gateway hoặc giải pháp mạng khác theo điều kiện hỗ trợ. Đánh giá cô lập dữ liệu, credential, Security Group, TLS, connection pooling, tác động tải và audit database.

**Kiểm chứng:** Kết nối mạng và xác thực database đều hợp lệ; không giả định auth policy của service network tự bảo vệ resource configuration.

### Tình huống D — 403 sau khi bật AWS_IAM

**Hiện tượng:** Request HTTPS chạy trước đây giờ trả 403.

**Khả năng thường gặp:** Client chưa ký SigV4, dùng nhầm IAM role, identity policy chưa cho Invoke hoặc auth policy ở service/service network thiếu Allow.

**Xử lý:** Đọc auth type từng lớp, xem identity thực trong runtime, kiểm tra Resource ARN của action Invoke, policy và log. Không tắt AWS_IAM chỉ để che lỗi khi hệ thống cần kiểm soát principal.

### Tình huống E — Kết nối được nhưng lỗi tăng khi một AZ có sự cố

**Hiện tượng:** Một AZ có target mất khả dụng, nhiều request timeout.

**Phân tích:** Kiểm tra target distribution và health, khả năng fail-open trong điều kiện tất cả target unhealthy, client timeout/retry, có bao nhiêu target khỏe ở AZ khác, và app có phụ thuộc một database hoặc service đơn điểm lỗi không.

**Xử lý:** Bổ sung HA theo RTO/RPO, health check phù hợp, load test/failover test và giới hạn retry để không gây tải thứ cấp.

## 14. Sai lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Gắn VPC vào service network là VPC nhìn thấy mọi private IP của nhau.” | Lattice cung cấp truy cập tới **service/resource được công bố**, không tự tạo mạng định tuyến tất cả địa chỉ. |
| “Tạo service rồi client account khác gọi ngay được.” | Cần đúng service-network association, kết nối client VPC/endpoint, quyền/share và cấu hình service. |
| “Biết DNS name thì có quyền gọi service.” | DNS chỉ giúp tìm endpoint; IAM auth, network và ứng dụng vẫn có thể từ chối. |
| “AWS RAM share tự động cấp quyền Invoke.” | Share quản lý quyền dùng/chia sẻ tài nguyên; data-plane Invoke còn có các lớp quyền và kết nối riêng. |
| “Gắn source SG của client vào target SG là luôn được.” | Traffic đi qua Lattice; nhiều trường hợp cần AWS-managed prefix list hoặc điều kiện khác theo loại target/endpoint. |
| “Policy vpc-lattice:GetService đủ cho ứng dụng gọi API.” | Control-plane permission khác **vpc-lattice-svcs:Invoke**. |
| “Bật AWS_IAM ở service rồi client có thể gửi curl bình thường.” | Request có thể cần được ký SigV4 và được phép từ cả các policy liên quan. |
| “Auth policy trên service network bảo vệ mọi resource configuration.” | Service-network auth policy **không áp dụng** cho resource configurations. |
| “HTTPS trên custom domain không cần cấu hình certificate.” | Cần certificate ACM phù hợp để HTTPS hoạt động trên custom domain. |
| “Một service network tự bảo đảm high availability.” | Còn cần target khỏe, nhiều AZ, failover và thiết kế phục hồi ứng dụng. |
| “Health check fail thì Lattice luôn ngưng gửi request đến mọi target lỗi.” | Một số target group có hành vi **fail-open** khi mọi target unhealthy. |
| “Lattice miễn phí khi cùng một Region.” | Cần tính service hours, data processing, request/connection và các chi phí liên quan. |
| “Lattice thay thế mọi nhu cầu Transit Gateway hoặc peering.” | Lattice tối ưu các tình huống service/resource connectivity; kết nối mạng IP tổng quát có mô hình khác. |

## 15. Bài tập và câu hỏi tự kiểm tra

### Bài tập thiết kế 1 — Chọn thành phần

Hệ thống có **Inventory API** chạy trong ECS ở VPC B và hai client ở VPC A, VPC C. Cả hai client cần gọi **GET /inventory/** qua HTTPS.

**Yêu cầu:** Phác thảo các thành phần tối thiểu và lớp bảo vệ.

**Gợi ý đáp án:** Một Inventory Service với HTTPS listener, target group phù hợp với ECS task, liên kết service với service network, liên kết hai client VPC qua association/endpoint, DNS, SG, IAM auth nếu cần, logging và health checks. Kiểm tra chính sách giữa consumer và service, giới hạn quyền nghiệp vụ trong ứng dụng.

### Bài tập thiết kế 2 — Khoanh vùng lỗi

Inventory Service chạy tốt khi gọi từ VPC A nhưng không thể truy cập từ VPC C. Điều gì nên kiểm tra đầu tiên?

**Gợi ý đáp án:** Xem VPC C đã được kết nối đúng service network chưa, trạng thái association/endpoint và SG/route/DNS. Nếu tới được Lattice nhưng trả 403, đối chiếu role và auth policy của request từ VPC C. Tránh sửa backend khi VPC A vẫn gọi thành công mà chưa có bằng chứng backend lỗi.

### Bài tập thiết kế 3 — Quyền của pipeline và runtime

Một pipeline triển khai Payments cần tạo target group và sửa listener, còn Orders runtime chỉ được gọi Payments API.

**Gợi ý đáp án:** Pipeline role có quyền **control plane** chính xác, qua quy trình kiểm soát thay đổi. Orders runtime role chỉ nhận quyền **vpc-lattice-svcs:Invoke** cần thiết và gửi request SigV4 nếu bật IAM auth. Không cấp quyền sửa service network cho Orders runtime.

### Câu hỏi nhanh

**Câu 1.** Service network và service khác nhau ở đâu?  
**Đáp án:** Service network là miền kết nối/quan sát logic chứa các service và resource configuration; service đại diện cho một ứng dụng với listener, rule và target group.

**Câu 2.** Một VPC có thể truy cập service trong service network bằng những hình thức kết nối nào?  
**Đáp án:** Qua **VPC association** hoặc **VPC endpoint loại service network**, theo điều kiện hỗ trợ và cấu hình.

**Câu 3.** Có bắt buộc dùng VPC peering giữa VPC client và VPC target khi gọi service bằng Lattice không?  
**Đáp án:** Không, không cần thiết lập VPC peering trực tiếp chỉ để gọi service đã được công bố qua VPC Lattice trong mô hình được hỗ trợ.

**Câu 4.** Auth type AWS_IAM thường đòi hỏi những gì?  
**Đáp án:** Caller có danh tính/temporary credentials phù hợp và ký SigV4; identity permissions và các auth policy được bật phải cho phép request, không có explicit Deny áp dụng.

**Câu 5.** Tại sao mở SG phía target cho CIDR của VPC client có thể chưa đủ?  
**Đáp án:** Traffic đi qua VPC Lattice và có nguồn theo data plane của Lattice; cần rule theo nguồn mà AWS hướng dẫn, như managed prefix list cho trường hợp áp dụng.

**Câu 6.** Lattice service auth policy có tự động áp dụng cho resource configuration không?  
**Đáp án:** Không. Đặc biệt, auth policy của service network không áp dụng cho resource configuration; cần kiểm tra mô hình quyền riêng.

**Câu 7.** Khi dùng custom domain với HTTPS cần thêm thành phần quan trọng nào?  
**Đáp án:** DNS mapping phù hợp và certificate **ACM** khớp tên miền.

**Câu 8.** Backend ECS tự scale thì client có cần biết IP từng task không?  
**Đáp án:** Thông thường không; client gọi tên service, còn VPC Lattice target group/tích hợp ECS xử lý registry/routing tới các target theo cơ chế hỗ trợ.

**Câu 9.** Tại sao access logs và metrics không thể thay thế application logs?  
**Đáp án:** Lattice mô tả request/response ở lớp service networking; application logs cần để hiểu lỗi nghiệp vụ, dữ liệu và quyết định authorization của chính ứng dụng.

**Câu 10.** Hai chi phí chính dễ bỏ sót khi dùng VPC Lattice là gì?  
**Đáp án:** Giờ service được provisioned và dữ liệu được xử lý; thêm phí request/connection và logging tùy loại traffic/cấu hình.

## 16. Tổng kết

**Amazon VPC Lattice** giúp liên kết các dịch vụ ứng dụng phân tán qua nhiều VPC và AWS account theo mô hình **service network → service → listener/rule → target group → backend**. Client kết nối service network qua **VPC association** hoặc **service-network VPC endpoint**, rồi gọi service bằng DNS và quyền thích hợp.

Khi triển khai production, cần kiểm tra đủ các yếu tố:

- **Connectivity:** service association, client VPC association/endpoint, DNS và Security Group.
- **Authorization:** quyền quản trị IAM/RAM, IAM identity permissions và VPC Lattice auth policy/SigV4 khi bật.
- **Application:** listener, routing, target health, xác thực nghiệp vụ, timeout/retry và dữ liệu.
- **Operations:** metrics, access logs, CloudTrail, nhiều AZ, thử failover và dự toán chi phí.

Lattice mang lại lợi ích lớn khi doanh nghiệp muốn quản trị giao tiếp **giữa các service** theo ranh giới có chủ đích. Tuy nhiên nó không thay thế mọi kết nối IP giữa VPC, không tự cung cấp quyền truy cập tài nguyên tùy ý và không thay trách nhiệm bảo vệ/giám sát ứng dụng của khách hàng.

### Tài liệu AWS tham khảo

- [What is Amazon VPC Lattice?](https://docs.aws.amazon.com/vpc-lattice/latest/ug/what-is-vpc-lattice.html) — tổng quan và các thành phần.
- [How VPC Lattice works](https://docs.aws.amazon.com/vpc-lattice/latest/ug/how-it-works.html) — service networks, association và đường kết nối.
- [Service networks in VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/service-networks.html) — tổ chức service network.
- [Target groups](https://docs.aws.amazon.com/vpc-lattice/latest/ug/target-groups.html) — kiểu target và routing.
- [Listeners for your VPC Lattice service](https://docs.aws.amazon.com/vpc-lattice/latest/ug/listeners.html) — HTTP, HTTPS và TLS.
- [Manage access to VPC Lattice services](https://docs.aws.amazon.com/vpc-lattice/latest/ug/access-management-overview.html) — các lớp kiểm soát truy cập.
- [VPC Lattice auth policies](https://docs.aws.amazon.com/vpc-lattice/latest/ug/auth-policies.html) — chính sách IAM cấp service/network.
- [Security groups for VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/security-groups.html) — các nguồn traffic và managed prefix list.
- [Access logs for VPC Lattice](https://docs.aws.amazon.com/vpc-lattice/latest/ug/monitoring-access-logs.html) — quan sát và phân tích request.
- [VPC Lattice pricing](https://aws.amazon.com/vpc/lattice/pricing/) — cách tính phí theo service/data/traffic.

