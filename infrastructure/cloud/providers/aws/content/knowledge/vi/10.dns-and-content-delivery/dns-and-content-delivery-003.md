# Routing policy theo trọng số, độ trễ và vị trí

> **Chương:** DNS và phân phối nội dung  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hạ tầng AWS từ Region/Availability Zone (AZ), IAM, VPC, compute, storage, database, tích hợp và serverless; thực hành chọn dịch vụ, thiết kế ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả cách **Amazon Route 53** chọn câu trả lời DNS thông qua routing policy, phân biệt định tuyến DNS với việc truyền các HTTP request.
2. Giải thích **Weighted routing**, tính tỷ trọng tương đối, chọn cách canary/blue-green rollout và hiểu ngoại lệ của **weight = 0**.
3. Giải thích **Latency-based routing** theo dữ liệu độ trễ đến các AWS Region, phân biệt với chọn Region gần nhất theo bản đồ.
4. Giải thích **Geolocation routing** theo châu lục, quốc gia, bang của Hoa Kỳ và **default record**; phân biệt với **Geoproximity routing** và bias.
5. Phân tích tác động của **health checks**, alias records, Evaluate Target Health, TTL, recursive DNS caching và EDNS Client Subnet.
6. Thiết kế chính sách DNS cho hệ thống nhiều Region, kết hợp Route 53 với ALB, CloudFront, IAM, VPC và giám sát để cải thiện tính sẵn sàng.
7. Đọc cấu hình, mô phỏng câu trả lời DNS bằng AWS CLI ở chế độ **chỉ đọc** và khắc phục các lỗi chọn nhầm endpoint.

## 1. Route 53 định tuyến ở cấp DNS như thế nào?

**Amazon Route 53** là dịch vụ DNS và quản lý tên miền của AWS. Khi một client muốn truy cập **api.example.com**, client thường hỏi recursive DNS resolver để chuyển tên miền thành thông tin DNS như địa chỉ IPv4 (**A**), IPv6 (**AAAA**) hoặc tên đích khác. Nếu cần trả lời từ authoritative DNS server của Route 53, dịch vụ chọn bản ghi phù hợp với routing policy đã cấu hình.

Ví dụ ứng dụng có hai backend:

- Endpoint A tại Singapore, đại diện cho một ALB hoặc backend ứng dụng trong AWS Region **ap-southeast-1**.
- Endpoint B tại Tokyo, đại diện cho một backend tại Region **ap-northeast-1**.

Cả hai cung cấp cùng một API. Route 53 có thể được cấu hình để trả lời theo:

- **Trọng số**: chủ động phân phối phần lớn các câu trả lời DNS về A, một phần nhỏ về B.
- **Độ trễ**: ưu tiên AWS Region được dự đoán có độ trễ mạng thấp nhất với nguồn truy vấn.
- **Vị trí địa lý**: ưu tiên endpoint theo quốc gia, châu lục hoặc vùng địa lý được chỉ định.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt / ứng dụng
    participant R as Recursive DNS resolver
    participant D as Route 53 authoritative DNS
    participant E as Endpoint được chọn
    U->>R: Hỏi api.example.com
    R->>D: Truy vấn khi cần, nếu chưa có cache
    Note over D: Chọn RRset theo routing policy và health
    D-->>R: Trả lời DNS, TTL
    R-->>U: Câu trả lời, có thể được cache
    U->>E: Kết nối HTTPS đến endpoint đã nhận
~~~

**Route 53 routing policy không phải một HTTP load balancer nằm giữa client và ứng dụng.** Route 53 trả lời **truy vấn DNS**, còn client sau đó kết nối tới endpoint được trả về. Nếu client đã cache DNS, đang giữ TCP/HTTP connection cũ hoặc DNS resolver chưa hết TTL, thay đổi policy có thể chưa tác động ngay tới lưu lượng thực tế.

### 1.1. Routing policy không thay thế tầng ứng dụng

Bốn điều kiện cần phân biệt:

1. **DNS:** tên miền trả về endpoint nào?
2. **Network:** client có thể đến endpoint qua Internet/VPC và qua Security Group/NACL không?
3. **Transport:** HTTPS/TLS và certificate có hợp lệ với hostname không?
4. **Application:** endpoint có khỏe, phiên làm việc có hợp lệ và dữ liệu có sẵn ở Region được chọn không?

Một DNS answer đúng không thể tự sửa lỗi kết nối VPC, một database chưa được replicate hoặc certificate không khớp hostname.

### 1.2. Public hosted zone và private hosted zone

- **Public hosted zone** quản lý DNS công khai khi domain/subdomain được ủy quyền tới name servers phù hợp.
- **Private hosted zone** cung cấp DNS cho các VPC được associate, với cơ chế resolver và routing có đặc điểm riêng.

Weighted, latency và geolocation có thể dùng trong private hosted zone theo điều kiện dịch vụ hỗ trợ. Tuy nhiên **cách xác định vị trí** trong private hosted zone có thể khác public zone. Không dùng kết quả DNS public để suy mọi hành vi của DNS riêng trong VPC.

## 2. Những khái niệm cần biết trước khi chọn policy

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Hosted zone** | Tập các DNS resource record sets thuộc một domain/subdomain. | example.com |
| **Record name** | Tên đầy đủ được hỏi. | api.example.com |
| **Record type** | Loại dữ liệu DNS. | A, AAAA, CNAME |
| **Record set (RRset)** | Nhóm giá trị cấu thành một bản ghi logic theo các trường của Route 53. | Một bản ghi A dùng Weighted policy. |
| **Routing policy** | Cách Route 53 chọn câu trả lời khi có nhiều record cùng tên/loại. | Weighted, latency, geolocation. |
| **SetIdentifier** | ID phân biệt các record cùng tên và loại thuộc nhóm routing có nhiều bản ghi. | stable-95, canary-5 |
| **TTL** | Khoảng thời gian để recursive resolver có thể cache câu trả lời DNS. | 60 giây |
| **Alias record** | Record đặc thù của Route 53 trỏ đến các tài nguyên/record được hỗ trợ. | api.example.com → ALB |
| **Health check** | Kiểm tra sức khỏe một endpoint hoặc đối tượng giám sát theo cấu hình. | HTTP /health |
| **EvaluateTargetHealth** | Tùy chọn alias để xét sức khỏe của target trong các trường hợp AWS hỗ trợ. | Alias đến ALB |

Khi dùng weighted/latency/geolocation, bạn thường có nhiều records **cùng Name và Type**, nhưng được phân biệt qua **SetIdentifier** và thuộc tính riêng của routing policy. Không được kết hợp tùy ý một weighted record và một geolocation record có **cùng name + type** như thể Route 53 sẽ tự biết áp policy nào trước.

Muốn phối hợp nhiều policy, thường cần **cấu trúc record/alias phân tầng** hoặc **Route 53 Traffic Flow**, thay vì trộn các dạng record cùng một cấp không hợp lệ.

## 3. Weighted routing — phân phối theo tỷ trọng tương đối

**Weighted routing** cho phép chỉ định trọng số cho nhiều record có cùng tên và loại. Route 53 chọn record theo **tỷ lệ trọng số so với tổng trọng số của nhóm record đủ điều kiện**. Đây là lựa chọn phù hợp để canary release, phân chia traffic tương đối hoặc di chuyển từng bước giữa phiên bản dịch vụ.

### 3.1. Công thức

Với những records có trọng số dương và cùng được xem là có thể chọn:

\[
P(i) = \frac{w_i}{\sum_{j=1}^{n} w_j}
\]

Trong đó:

- \(w_i\) là weight của record thứ \(i\).
- Mẫu số là tổng weight của các record đang được xét trong nhóm.
- \(P(i)\) là tỷ trọng **dự kiến của câu trả lời DNS**, không phải bảo đảm chính xác tỷ lệ HTTP requests hay số người dùng.

Ví dụ:

| Record | SetIdentifier | Weight | Tỷ lệ DNS dự kiến nếu đều được xét |
| --- | --- | ---: | ---: |
| Backend stable | stable | 90 | 90% |
| Backend canary | canary | 10 | 10% |
| **Tổng** | | **100** | **100%** |

Với 9.000 câu trả lời DNS độc lập, có thể kỳ vọng xấp xỉ 8.100 câu về stable, 900 câu về canary trong những điều kiện thống kê phù hợp. **Không nên hứa chắc 8.100/900**: DNS caching, health checks, số truy vấn thực tế và phân phối client khiến tỷ lệ đo ở tầng application khác nhiều.

### 3.2. Ví dụ JSON record sets

Hai records minh họa cho **api.example.com**, mỗi record có một IP thuộc dải địa chỉ **TEST-NET** dành cho tài liệu, không phải endpoint AWS thật.

~~~json
[
  {
    "Name": "api.example.com.",
    "Type": "A",
    "SetIdentifier": "stable-90",
    "Weight": 90,
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "api.example.com.",
    "Type": "A",
    "SetIdentifier": "canary-10",
    "Weight": 10,
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

Đây là ví dụ **ResourceRecordSet objects** để đọc hiểu cấu trúc, **không** phải toàn bộ payload **ChangeResourceRecordSets**. Với ALB thực tế, thường dùng **AliasTarget** thay cho IP A record tự quản lý, đồng thời phải lấy đúng DNS name và hosted zone ID của ALB.

### 3.3. Canary release với weighted policy

Một kế hoạch rollout có kiểm soát:

1. Deploy phiên bản **v2** ở backend độc lập, kiểm tra health, TLS, database compatibility và rollback.
2. Giữ traffic stable 100%, canary 0% hoặc chưa đưa canary vào tuyến theo thiết kế.
3. Chuyển trọng số thành **99:1**, quan sát tỉ lệ lỗi, latency, request logs và metric nghiệp vụ.
4. Nâng dần thành **95:5 → 90:10 → 50:50 → 0:100** khi có đủ bằng chứng ổn định.
5. Khi cần rollback, chuyển trọng số về phiên bản stable, kiểm tra DNS caching và xử lý phiên đang kết nối.

Một vấn đề quan trọng: nếu một recursive DNS resolver có nhiều client phía sau và cache câu trả lời, **nhiều người dùng có thể cùng sử dụng một backend** dù weight chỉ 1%. Vì vậy canary bằng DNS không phải bộ chia người dùng chính xác tuyệt đối hoặc cơ chế gắn phiên/canary theo customer ID.

Nếu cần kiểm soát rollout theo user, cookie, header hoặc session, có thể dùng **ALB routing rules**, feature flags hoặc hệ thống release control ở tầng ứng dụng thay vì chỉ dựa vào DNS.

### 3.4. Weight = 0 không phải nút vô hiệu hóa tuyệt đối

Hành vi cần nhớ theo tài liệu AWS:

- Nếu một số record có **weight > 0** đang đủ điều kiện/healthy, Route 53 thường ưu tiên xét những record đó và không chọn record **weight = 0**.
- Nếu **tất cả record đều có weight = 0**, Route 53 chọn giữa chúng với xác suất **bằng nhau**, để nhóm vẫn có câu trả lời.
- Khi cấu hình health checks và **tất cả record có weight dương** trở thành unhealthy, Route 53 có thể xét **record weight = 0** như phương án dự phòng.
- Nếu các record có health checks **đều unhealthy**, Route 53 có hành vi **fail-open** theo nhóm policy: dịch vụ vẫn có thể trả lời bằng các record mà thông thường bị loại, thay vì mặc định không trả câu trả lời.

**Hệ quả:** Không coi weight 0 là cách cô lập bảo mật hoặc ngắt hoàn toàn endpoint. Nếu một phiên bản tuyệt đối không được nhận traffic, cần xử lý ở **deployment, routing group, network/app access** hoặc gỡ record theo kế hoạch, không chỉ đặt weight 0.

### 3.5. Những lỗi dùng weighted phổ biến

- Nhầm **weight = 10** thành “10%” ngay cả khi tổng weight không phải 100.
- Coi tỷ trọng DNS answers là tỷ trọng HTTP requests thực tế.
- Coi weight 0 là disable tuyệt đối ngay cả khi mọi record khác unhealthy.
- Không gắn health check cho một target yếu nhưng vẫn kỳ vọng Route 53 tự biết trạng thái.
- Dùng weighted DNS để làm sticky sessions hoặc load balancing theo từng request.
- Quên lưu **SetIdentifier** riêng cho mỗi record cùng tên/loại.

## 4. Latency-based routing — tối ưu độ trễ theo AWS Region

**Latency routing** cho phép tạo records đại diện cho những endpoint phục vụ ứng dụng từ **nhiều AWS Region**. Route 53 sử dụng dữ liệu mạng của AWS để xác định **Region** được dự đoán cung cấp độ trễ thấp nhất cho nguồn truy vấn DNS, rồi chọn record của Region đó.

~~~mermaid
flowchart TD
    C["Client / DNS resolver"] --> R53["Route 53 latency policy"]
    R53 --> SGP["ap-southeast-1 — Singapore"]
    R53 --> TYO["ap-northeast-1 — Tokyo"]
    SGP --> A["ALB / ứng dụng Region Singapore"]
    TYO --> B["ALB / ứng dụng Region Tokyo"]
~~~

### 4.1. Không đồng nhất latency với khoảng cách địa lý

Một khách ở miền Bắc Việt Nam không mặc định được định tuyến tới Singapore, Tokyo hay Region nào chỉ vì Region đó gần trên bản đồ. Latency routing dựa trên **dữ liệu độ trễ mạng quan sát được và thay đổi theo thời gian**.

- Định tuyến BGP, ISP peering và network conditions có thể làm tuyến đến Region xa về khoảng cách địa lý nhưng có latency tốt hơn.
- Trình duyệt có thể dùng recursive resolver ở vị trí khác với người dùng.
- Thông tin **EDNS Client Subnet (ECS)** có thể giúp Route 53 ước lượng vị trí client chính xác hơn nếu resolver hỗ trợ.
- Dữ liệu latency của AWS không đo trực tiếp mọi đường đến các endpoint **nằm ngoài AWS**; khi dùng endpoint ngoài AWS, kết quả thực tế có thể khác.

**Latency routing không phải bài toán geo-fencing**. Nếu luật nghiệp vụ yêu cầu người dùng ở Việt Nam phải được xử lý bởi hệ thống nhất định, latency policy không bảo đảm điều đó.

### 4.2. Ví dụ record sets cho latency routing

~~~json
[
  {
    "Name": "api-latency.example.com.",
    "Type": "A",
    "SetIdentifier": "sg-region",
    "Region": "ap-southeast-1",
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "api-latency.example.com.",
    "Type": "A",
    "SetIdentifier": "tokyo-region",
    "Region": "ap-northeast-1",
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

Đây là ví dụ đọc hiểu, sử dụng IP thử nghiệm. Thuộc tính **Region** của record thể hiện Region phục vụ resource theo chính sách latency, **không phải vị trí đặt hosted zone**. Route 53 là dịch vụ DNS toàn cục; không cần tạo một hosted zone riêng cho mỗi Region chỉ để chạy latency routing.

### 4.3. Khi latency routing hữu ích

- Ứng dụng triển khai **active-active multi-Region** và muốn giảm thời gian round trip ban đầu.
- Mỗi Region có đủ backend, data store/replica và năng lực phục vụ các request được gửi tới nó.
- Có thể kết hợp health check/Evaluate Target Health để không ưu tiên endpoint đang lỗi trong điều kiện hỗ trợ.
- Hệ thống cần quan sát **p95/p99 latency** ở tầng ứng dụng và dữ liệu thực tế theo Region.

Không nên triển khai latency routing cho một API ở Singapore và một backend ở Tokyo **nếu Tokyo không có dữ liệu cần thiết**, không hỗ trợ nhất quán nghiệp vụ hoặc chỉ là hệ thống dự phòng chưa sẵn sàng nhận traffic.

### 4.4. Latency routing trong private hosted zone

Với private hosted zone, Route 53 có thể chọn endpoint theo **AWS Region liên quan tới VPC/resolver xuất phát truy vấn** và khoảng cách tới Region khác theo cơ chế AWS mô tả. Không suy rằng nó đang định vị **địa chỉ vật lý của nhân viên** như một public DNS query.

Nếu dùng Route 53 Resolver inbound/outbound endpoints, nơi request được nhận bởi resolver có thể ảnh hưởng quyết định. Phải kiểm thử tại chính VPC và con đường DNS thực tế.

## 5. Geolocation routing — chủ động chọn theo vị trí người dùng

**Geolocation routing** cho phép chỉ định endpoint dựa trên **vị trí mà Route 53 xác định cho nguồn DNS query**, theo:

- **Continent** (châu lục).
- **Country** (quốc gia, ví dụ mã ISO cho Việt Nam là **VN**).
- **Subdivision** (bang của Hoa Kỳ, theo phạm vi hỗ trợ).
- **Default** cho những vị trí không có record phù hợp hoặc không xác định được.

Ví dụ:

| Vị trí áp dụng | Endpoint mục tiêu | Mục đích |
| --- | --- | --- |
| Country = **VN** | Ứng dụng dành cho thị trường Việt Nam. | Ngôn ngữ/chính sách nội dung địa phương. |
| Continent = **EU** | Ứng dụng phiên bản châu Âu. | Nội dung phù hợp thị trường EU. |
| **Default** | Ứng dụng chung toàn cầu. | Tránh DNS không có câu trả lời cho vị trí chưa được khai báo. |

### 5.1. Vùng nhỏ hơn có độ ưu tiên cao hơn

Giả sử có ba geolocation records cùng tên/loại:

- Continent = **AS** (châu Á) → backend A.
- Country = **VN** → backend B.
- Default → backend C.

Khi Route 53 xác định query đến từ Việt Nam, record **VN** được chọn vì cụ thể hơn **AS**. Một query khác từ quốc gia châu Á không có record riêng có thể vào backend A. Một query thuộc khu vực chưa có rule khớp hoặc không định vị được dùng **Default**.

~~~mermaid
flowchart TD
    Q["DNS query"] --> V{"Khớp quốc gia VN?"}
    V -->|"Có"| VN["Endpoint Việt Nam"]
    V -->|"Không"| A{"Khớp châu Á AS?"}
    A -->|"Có"| AS["Endpoint châu Á"]
    A -->|"Không/không xác định"| D["Default endpoint"]
~~~

Sơ đồ chỉ minh họa hai rule địa lý và default; trong cấu hình đầy đủ, Route 53 xét **vị trí cụ thể nhất** (ví dụ bang Hoa Kỳ, quốc gia, châu lục) có record hợp lệ, cùng sức khỏe endpoint nếu đã cấu hình.

### 5.2. Ví dụ GeoLocation records

~~~json
[
  {
    "Name": "site-geo.example.com.",
    "Type": "A",
    "SetIdentifier": "vietnam",
    "GeoLocation": {"CountryCode": "VN"},
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "site-geo.example.com.",
    "Type": "A",
    "SetIdentifier": "default",
    "GeoLocation": {"CountryCode": "*"},
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

Đây là ví dụ dùng các IP reserved cho tài liệu. **CountryCode = "\*"** trong trường GeoLocation đại diện cho **Default** trong cấu trúc record API, không phải IP wildcard.

### 5.3. Vì sao phải có default record?

Một số IP không ánh xạ được chính xác tới vị trí địa lý hoặc thuộc các khu vực bạn chưa tạo record. **Nếu không có default**, Route 53 có thể trả lời DNS **không có answer** cho những query không tìm được geolocation match phù hợp.

Default record giúp:

- Tránh vô tình không phục vụ khách hợp lệ từ vị trí chưa cấu hình.
- Có fallback khi dữ liệu địa lý không rõ ràng.
- Cung cấp endpoint/nội dung chung cho thị trường khác.

**Default không có nghĩa “đúng mọi trường hợp”**. Nếu hệ thống bắt buộc không phục vụ một thị trường vì lý do pháp lý, cần có chính sách ứng dụng/lớp kiểm soát phù hợp, không dựa đơn độc vào dự đoán vị trí IP tại DNS.

### 5.4. Geolocation không xác định chính xác vị trí từng người

Quyết định thường phụ thuộc địa chỉ IP của **recursive DNS resolver** hoặc phần thông tin client do resolver gửi bằng **EDNS Client Subnet**.

- VPN, public DNS resolver, NAT, carrier network và ECS support có thể làm vị trí DNS khác vị trí vật lý.
- Geolocation theo DNS **không phải cơ chế chứng minh nơi cư trú hay quốc tịch**.
- Nếu cần áp chính sách dữ liệu, quyền nội dung và kiểm soát tuân thủ, ứng dụng vẫn phải xác thực/đánh giá quy tắc nghiệp vụ và dữ liệu phù hợp.

### 5.5. Geolocation kết hợp health check

Khi record cho vùng cụ thể bị đánh giá unhealthy và bạn có health checks phù hợp, Route 53 có thể xét **vùng địa lý rộng hơn** như country → continent → default để tìm endpoint healthy. Ví dụ record riêng cho một bang Hoa Kỳ có thể fallback sang record nước Mỹ hoặc châu lục trước khi tới default.

Tuy nhiên nếu toàn bộ endpoints được xét đều unhealthy, có thể có **fail-open behavior**: Route 53 vẫn trả về một record theo cơ chế của policy. Không coi DNS health check là giải pháp đảm bảo loại bỏ hoàn toàn endpoint hỏng.

## 6. Geoproximity khác geolocation như thế nào?

Trong nhóm **routing theo vị trí**, một lựa chọn khác là **Geoproximity routing**.

| Tiêu chí | **Geolocation** | **Geoproximity** |
| --- | --- | --- |
| Câu hỏi | “Người dùng thuộc quốc gia/châu lục/bang nào?” | “Người dùng gần tài nguyên nào hơn xét theo vị trí và bias?” |
| Rule | Country, continent, bang Mỹ và default. | AWS Region/Local Zone group hoặc tọa độ tài nguyên ngoài AWS theo phạm vi hỗ trợ. |
| Phân vùng | Theo ranh giới địa lý được chọn rõ ràng. | Theo vùng ảnh hưởng xung quanh từng tài nguyên. |
| Điều chỉnh tỷ trọng | Thay đổi rule/vị trí được gán; không có bias distance theo kiểu geoproximity. | **Bias** dương/mang giá trị âm để mở rộng/thu hẹp vùng ảnh hưởng. |
| Phù hợp | Nội dung theo thị trường, ngôn ngữ hoặc ranh giới quốc gia. | Điều phối lưu lượng theo khoảng cách địa lý và sức tải của tài nguyên. |
| Có giống latency routing? | Không. | Không: khoảng cách/vùng ảnh hưởng khác dữ liệu độ trễ đo được. |

### 6.1. Bias trong geoproximity

Bias cho phép **mở rộng hoặc thu hẹp vùng địa lý** mà một record thu hút. Khi bias **dương**, vùng ảnh hưởng của endpoint tăng; bias **âm** thu hẹp vùng ảnh hưởng.

AWS mô tả mô hình ước lượng khoảng cách đã điều chỉnh theo bias:

\[
\text{biased distance}=\text{actual distance}\times\left(1-\frac{\text{bias}}{100}\right)
\]

Ví dụ một endpoint cách resolver 150 km, bias **+50** khiến khoảng cách tính cho quyết định geoproximity trở thành 75 km. Đó là minh họa cơ chế chọn record, **không biến đường mạng vật lý ngắn đi 75 km**.

Không thay đổi bias quá lớn một lần khi đang phục vụ production: ranh giới vùng địa lý có thể thay đổi đáng kể, làm một backend bất ngờ nhận nhiều traffic hơn năng lực dự kiến.

### 6.2. Khi nào nên chọn geolocation thay vì geoproximity?

- Muốn người dùng ở Việt Nam dùng nội dung tiếng Việt theo rule rõ ràng → **Geolocation**.
- Muốn người dùng được gán cho endpoint gần về địa lý và điều chỉnh vùng ảnh hưởng theo capacity → **Geoproximity**.
- Muốn tối ưu thời gian truyền mạng dự đoán giữa người dùng và các AWS Region → **Latency**.

Đừng nhầm **“gần”** trong geoproximity với **“độ trễ thấp nhất”**: khoảng cách địa lý chỉ là một trong các yếu tố ảnh hưởng tới network latency.

## 7. Bảng quyết định: weighted, latency và location

| Tiêu chí | **Weighted** | **Latency-based** | **Geolocation** | **Geoproximity** |
| --- | --- | --- | --- | --- |
| Quy tắc chính | Tỷ trọng record. | Region dự đoán có latency thấp nhất. | Vị trí DNS query theo vùng định nghĩa. | Vùng ảnh hưởng dựa trên vị trí tài nguyên và bias. |
| Trường record quan trọng | **Weight**. | **Region**. | **GeoLocation**. | **GeoProximityLocation/Bias** theo API. |
| Đầu vào cần | Weight và các endpoint. | Endpoint theo nhiều AWS Region. | Quốc gia/châu lục/bang/default. | Vị trí tài nguyên/bias. |
| Canary rollout | **Rất phù hợp** ở cấp DNS. | Không trực tiếp quyết định % rollout. | Không trực tiếp quyết định %. | Không đặt tỷ trọng % trực tiếp. |
| Tối ưu độ trễ | Không tự tối ưu. | **Mục tiêu chính**. | Không tự đo latency. | Dựa vị trí, không phải đo latency trực tiếp. |
| Quy tắc theo thị trường | Không có. | Không chắc chắn. | **Phù hợp**. | Không chính xác theo ranh giới hành chính. |
| Kết quả chắc chắn theo từng user/request | Không. | Không. | Không xác định vị trí cá nhân tuyệt đối. | Không. |
| Health integration | Có. | Có. | Có. | Có theo cơ chế hỗ trợ. |
| TTL/cache vẫn áp dụng | Có. | Có. | Có. | Có. |

**Một nguyên tắc chọn nhanh:** Cần tỷ trọng rollout → Weighted; cần tối ưu độ trễ multi-Region → Latency; cần phân phối theo quốc gia/địa lý được chỉ định → Geolocation; cần điều chỉnh vùng ảnh hưởng quanh điểm phục vụ → Geoproximity.

Khi nhu cầu là active-passive disaster recovery, hãy đánh giá **Failover routing policy** thay vì cố mô phỏng hoàn toàn bằng Weighted 100:0. Khi cần trả lời nhiều IP health-check-aware, **Multivalue answer** có cơ chế khác với Weighted. Khi doanh nghiệp biết dải IP của từng ISP/client, **IP-based routing** có thể phù hợp hơn suy vị trí IP.

## 8. Health check: routing policy không tự biết ứng dụng đã hỏng

Nếu Route 53 không có tín hiệu health tương ứng, nó **không tự suy rằng endpoint hỏng** chỉ vì website bắt đầu trả HTTP 500 hoặc database không kết nối được.

### 8.1. Health check cho endpoint

Route 53 có thể kiểm tra endpoint HTTP/HTTPS/TCP hoặc dùng các cơ chế health check khác được AWS hỗ trợ. Bạn cần thiết kế tín hiệu health phản ánh mục tiêu vận hành:

- Kiểm tra endpoint **/health** hoặc **/ready** đúng protocol/port.
- Endpoint kiểm tra phải trả trạng thái theo điều kiện ứng dụng có thể phục vụ traffic.
- Tách liveness và readiness nếu workload có dependency chưa sẵn sàng.
- Tránh health check quá nặng làm tăng tải hoặc sai kết luận.
- Thiết kế nguồn health check, Security Group và network path phù hợp để AWS health checker thực sự truy cập được endpoint cần kiểm tra.

Một endpoint ALB đứng trước ứng dụng có thể tự health check targets; Route 53 alias đến ELB có tùy chọn **EvaluateTargetHealth** trong những trường hợp hỗ trợ. Nhưng Route 53 health check và ALB target group health check là **hai lớp khác nhau**.

### 8.2. Alias và EvaluateTargetHealth

**Alias record** có thể trỏ tới ELB, CloudFront, S3 website endpoint hoặc một record khác theo các mục tiêu AWS hỗ trợ. Với các alias target có cơ chế đánh giá sức khỏe, **EvaluateTargetHealth = true** giúp Route 53 xem xét sức khỏe target theo khả năng tương ứng.

Không phải mọi loại alias target đều hỗ trợ chọn EvaluateTargetHealth tùy ý. Ví dụ CloudFront distribution có những giới hạn khác ALB; khi thiết kế phải xem tài liệu cho loại alias target đó.

Nếu alias trỏ tới **record khác trong cùng hosted zone**, việc đánh giá có thể lan xuống nhóm record bên dưới theo các điều kiện của Route 53. Điều này cho phép tạo mô hình kết hợp nhiều routing policies (ví dụ latency chọn Region rồi weighted chọn phiên bản trong Region).

### 8.3. All-unhealthy và fail-open

Theo logic AWS, khi tất cả records trong một nhóm có health check đều bị đánh giá unhealthy, Route 53 cần vẫn đưa ra một câu trả lời và có thể **coi các record như có thể chọn** theo routing policy. Đây là hành vi **fail-open** nhằm tránh trạng thái không có câu trả lời chỉ vì health check.

**Vì vậy:**

- Đừng khẳng định “bật health check là DNS luôn loại bỏ mọi endpoint hỏng”.
- Cần upstream app/load balancer có khả năng xử lý lỗi, retry và circuit breaker phù hợp.
- Thực hiện diễn tập **mất một endpoint** và **mất toàn bộ endpoints**, đo thời gian DNS update theo TTL và hành vi client.

### 8.4. Health check cần đúng thực thể

Một sai lầm là dùng health check trỏ tới chính tên **api.example.com** có nhiều weighted/latency/geolocation records. Kết quả có thể vòng qua routing policy và kiểm tra endpoint **khác** với record bạn định bảo vệ.

Nên dùng endpoint health riêng cho từng backend, ví dụ:

- **sg-health.example.com** → Region Singapore.
- **jp-health.example.com** → Region Tokyo.

Health check phải kiểm tra đúng backend và path mong muốn, không phụ thuộc vào chính policy DNS đang được điều khiển.

## 9. TTL, DNS caching và EDNS Client Subnet

### 9.1. TTL không phải thời gian tuyệt đối để cắt traffic

**TTL** (Time To Live) cho biết thời gian resolver có thể cache DNS answer. Ví dụ TTL 60 giây nghĩa là recursive resolver có thể phục vụ câu trả lời đã cache trong khoảng được cho phép mà **không hỏi lại Route 53 cho mỗi request của client**.

Sau khi thay đổi policy:

- Authoritative Route 53 records cần thời gian lan truyền cập nhật.
- Recursive resolvers có thể vẫn cache câu trả lời trước đó.
- Trình duyệt/OS/app có thể có cache khác.
- Kết nối HTTP/TCP đang mở có thể được tái sử dụng ngay cả khi DNS đã đổi.

Vì vậy đổi 90:10 sang 100:0 **không bảo đảm mọi HTTP request chuyển sang stable trong 60 giây**.

### 9.2. TTL ngắn và TTL dài

| TTL | Ưu điểm | Đổi lại |
| --- | --- | --- |
| Ngắn, ví dụ 60 giây | Resolver thường hỏi lại sớm hơn, giúp chuyển traffic/failover linh hoạt. | Tăng DNS queries, chi phí có thể cao hơn; nhiều client không tuân TTL chính xác. |
| Dài, ví dụ 300–3600 giây | Ít truy vấn tới authoritative DNS, giảm tần suất lookup. | Có thể kéo dài thời gian client còn dùng endpoint cũ. |

AWS thường khuyến nghị TTL **60 giây hoặc thấp hơn khi dùng health checks** trong những cấu hình record không phải alias có TTL do bạn đặt. TTL hợp lý phụ thuộc RTO, tần suất rollout, lưu lượng DNS và hệ thống cache thực tế.

Đối với alias đến một số tài nguyên AWS, TTL của câu trả lời có thể do **target alias** quy định thay vì nhập một TTL độc lập như A record thông thường.

### 9.3. Recursive resolver và EDNS Client Subnet

Route 53 có thể quyết định dựa trên:

- **IP của recursive DNS resolver** nếu resolver không cung cấp EDNS Client Subnet.
- **Thông tin địa chỉ client được rút gọn** mà resolver gửi qua EDNS Client Subnet (ECS), khi tính năng được hỗ trợ.

~~~mermaid
flowchart TD
    U["Người dùng tại Việt Nam"] --> R{"Resolver có gửi ECS?"}
    R -->|"Không"| I["Route 53 ước lượng từ IP resolver"]
    R -->|"Có"| E["Route 53 dùng client subnet được gửi"]
    I --> S["Chọn record theo policy và health"]
    E --> S
~~~

Cùng một người dùng có thể nhận câu trả lời khác khi thay đổi DNS resolver, VPN hoặc đường mạng, ngay cả khi website và Route 53 records không đổi. Không diễn giải kết quả **nslookup/dig từ một mạng** như bằng chứng toàn bộ thị trường nhận đúng endpoint.

### 9.4. Private hosted zone có vị trí khác public DNS

Với private hosted zone, Route 53 có logic dựa trên **VPC/Resolver trong AWS Region** thay vì thông tin EDNS0 client subnet ngoài Internet; ECS không áp dụng theo cách tương tự ở private zone. Khi kiểm thử phải truy vấn qua resolver của chính VPC mục tiêu.

## 10. Ví dụ kiến trúc: ứng dụng đa Region và rollout có kiểm soát

Giả sử ứng dụng API hoạt động ở:

- **Singapore (ap-southeast-1)** với ALB và một nhóm EC2/ECS backend.
- **Tokyo (ap-northeast-1)** với ALB và một nhóm backend khác.
- Dữ liệu nghiệp vụ được thiết kế replication/consistency phù hợp; log, IAM, secrets và giám sát được cấu hình cho hai Region.

~~~mermaid
flowchart TD
    C["Người dùng ở nhiều vị trí"] --> R53["Route 53: api.example.com"]
    R53 -->|"Latency chọn Region"| S["sg.api.example.com"]
    R53 -->|"Latency chọn Region"| T["jp.api.example.com"]
    S -->|"Weighted chọn stable/canary"| SG1["Singapore ALB stable"]
    S -->|"Weighted"| SG2["Singapore ALB canary"]
    T -->|"Weighted chọn stable/canary"| JP1["Tokyo ALB stable"]
    T -->|"Weighted"| JP2["Tokyo ALB canary"]
~~~

### 10.1. Thiết kế nhiều lớp policy

**Lớp 1 — chọn Region:** Tạo latency alias records cho **api.example.com**, một record đại diện **Singapore** và một record đại diện **Tokyo**, cùng SetIdentifier và Region riêng.

**Lớp 2 — chọn phiên bản tại Region:** Trong từng nhánh, tạo nhóm weighted records tại tên trung gian khác nhau như **sg.api.example.com** và **jp.api.example.com**.

**Lớp 3 — health checks:** Gắn health check hoặc EvaluateTargetHealth phù hợp ở từng cấp, để Route 53 có thể chọn nhánh khác khi Region/tập backend không còn khỏe theo các điều kiện hỗ trợ.

**Lớp 4 — bảo vệ ứng dụng:** ALB listeners/target groups, HTTPS certificates, Security Group, IAM/VPC, WAF khi cần, data replication và monitoring.

Phần trình bày này là **kiến trúc logic**; alias tree cần được tạo hợp lệ với record names, DNS type, alias target hosted zone ID và health settings chính xác. Đừng copy trực tiếp mũi tên trên sơ đồ thành cấu hình DNS khi chưa kiểm tra giới hạn record.

### 10.2. Không dùng cùng Name/Type để trộn policy trực tiếp

Không tạo **một nhóm api.example.com A records** vừa có **Weight**, vừa có **Region**, vừa có **GeoLocation** tùy tiện trên các record ngang hàng. Route 53 yêu cầu các record cùng Name/Type trong một nhóm routing phải tuân kiểu policy tương ứng.

Nếu cần **địa lý → weighted → endpoint**, thiết kế bằng **tên trung gian và alias records** hoặc **Traffic Flow** được hỗ trợ. Bắt đầu từ policy đơn giản, đo trước khi thêm nhiều lớp.

### 10.3. Data plane không được xem nhẹ

Multi-Region DNS chỉ có giá trị nếu từng Region **tự phục vụ ứng dụng**:

- Các backend có trạng thái đủ khỏe và khả năng mở rộng phù hợp.
- Database có replication/backup và xử lý nhất quán theo nghiệp vụ.
- Ứng dụng hiểu chuyện một người dùng có thể chuyển Region giữa các request.
- Session storage, object S3, secret/credential, IAM/KMS và DNS name phải được thiết kế đúng.
- Có kế hoạch RPO/RTO, sao lưu, failover và khôi phục khi toàn bộ Region gặp sự cố.

Route 53 **không tự sao chép RDS, S3 objects, EBS volumes hoặc session state** giữa các Region. Những phần đó là trách nhiệm kiến trúc của hệ thống ứng dụng.

### 10.4. Khi nào dùng CloudFront thay vì chỉ Route 53?

Nếu mục tiêu là phân phối ảnh, CSS, JavaScript hoặc video với độ trễ thấp cho người dùng ở nhiều địa điểm, **Amazon CloudFront** cung cấp CDN edge caching, cơ chế bảo vệ/định tuyến origin và các tính năng phân phối nội dung phù hợp.

Route 53 có thể trỏ **Alias** tới CloudFront distribution, nhưng Route 53 routing policy **không tự cache nội dung web ở edge**. Hai dịch vụ bổ sung nhau:

- Route 53: trả lời DNS.
- CloudFront: phân phối và cache nội dung qua mạng edge, kết nối đến origins theo cấu hình.
- ALB/API Gateway: tiếp nhận HTTP(S), routing và nhiều chức năng ở tầng request theo khả năng dịch vụ.
- Ứng dụng: authentication, authorization, nội dung và consistency nghiệp vụ.

## 11. Bảo mật và quản trị thay đổi DNS

### 11.1. IAM least privilege

Không phải ai cũng cần quyền sửa public DNS records. Một thay đổi DNS nhầm có thể khiến toàn bộ người dùng kết nối sai endpoint hoặc làm gián đoạn dịch vụ.

Tách quyền:

- **Viewer/Support:** đọc hosted zones, records, health checks.
- **Deployment automation:** chỉ sửa record names/types được duyệt theo quy trình và IAM conditions hỗ trợ.
- **DNS administrator:** quản trị zone/delegation, IAM, DNSSEC khi cần; quyền cao có review.

Các IAM actions liên quan gồm **route53:ListHostedZones**, **route53:ListResourceRecordSets**, **route53:GetHostedZone**, **route53:ChangeResourceRecordSets**, **route53:GetChange**, **route53:GetHealthCheck** và những action khác theo chức năng. Khi dùng IaC, kiểm tra quyền apply và audit trong CloudTrail.

### 11.2. DNS không phải cơ chế xác thực người dùng

Weighted hoặc geolocation records không chứng minh caller có quyền truy cập hệ thống:

- Website phải sử dụng **TLS certificate** đúng hostname.
- Các private APIs cần authentication/authorization ở ứng dụng, API Gateway, ALB hoặc lớp thích hợp.
- Security Groups, VPC network path và WAF (khi hỗ trợ) vẫn cần cấu hình.
- Route 53 không chặn hoàn toàn truy cập trực tiếp endpoint nếu endpoint công khai và ứng dụng thiếu kiểm soát thích hợp.

### 11.3. DNSSEC và bảo vệ domain

**DNSSEC** giúp xác minh tính toàn vẹn/xác thực dữ liệu DNS trong chuỗi trust phù hợp khi cấu hình được hỗ trợ; nó không thay TLS, IAM hoặc ngăn mọi tấn công ứng dụng. DNS delegation, registrar lock, MFA, CloudTrail và quyền thay đổi hosted zone cũng cần được quản trị.

### 11.4. Kế hoạch rollback khi thay policy

1. Lưu phiên bản record sets hiện tại trong IaC/backup cấu hình được kiểm soát.
2. Kiểm tra endpoint đích, SSL certificate, health check và data consistency.
3. Thay đổi theo lô nhỏ/chiều thích hợp, ghi change ID.
4. Dùng **GetChange** kiểm tra trạng thái **INSYNC**.
5. Theo dõi tỷ lệ lỗi, request volumes, latency, business KPIs.
6. Nếu rollback, áp dụng cấu hình cũ và nhớ TTL/connection reuse sẽ khiến chuyển đổi traffic không tức thì.

Trong ứng dụng có tải cao, cần tránh hiểu **INSYNC** là “mọi client trên Internet đã quên cache DNS cũ”. INSYNC chỉ nói về việc thay đổi đã được triển khai đến Route 53 name servers theo cơ chế AWS.

## 12. AWS CLI: quan sát và mô phỏng routing (chỉ đọc)

Các lệnh sau **không tạo, sửa hay xóa** hosted zone/record. Thay ID và domain minh họa bằng tài nguyên của môi trường được phép truy cập. AWS Route 53 là dịch vụ DNS toàn cục; không cần gắn một Region CLI cho mỗi thao tác quản lý hosted zone giống EC2.

### 12.1. Xác định account và hosted zone

~~~bash
aws sts get-caller-identity

aws route53 list-hosted-zones \
  --query "HostedZones[].{Name:Name,Id:Id,Private:Config.PrivateZone}"

aws route53 get-hosted-zone \
  --id ZEXAMPLE123456
~~~

Một domain có thể xuất hiện trong **nhiều hosted zone** khác nhau (ví dụ public/private hoặc các zone độc lập). Kiểm tra **zone ID**, **PrivateZone**, name servers và delegation thực sự sử dụng, không chỉ nhìn tên.

### 12.2. Xem weighted, latency và geolocation records

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='api.example.com.']"

aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='api-latency.example.com.']"

aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='site-geo.example.com.']"
~~~

Trong JSON đầu ra, đọc:

| Trường | Cách diễn giải |
| --- | --- |
| **Name / Type** | Các records đang phục vụ tên và loại DNS nào. |
| **SetIdentifier** | Record nào trong nhóm. |
| **Weight** | Routing theo trọng số. |
| **Region** | Latency routing. |
| **GeoLocation** | Geolocation routing. |
| **GeoProximityLocation** | Geoproximity routing nếu record áp dụng. |
| **TTL** | Cache duration của record thường. |
| **ResourceRecords** | Các giá trị trực tiếp như IP. |
| **AliasTarget** | Record trỏ tới resource/record theo Alias. |
| **HealthCheckId** | Health check gắn vào record nếu có. |
| **EvaluateTargetHealth** | Trong AliasTarget, quyết định xem target health có được xét không. |

Với kết quả CLI phân trang, nhớ xử lý đủ pages nếu danh sách lớn. Kết quả chỉ cho biết **cấu hình AWS**; không chứng minh tất cả recursive resolvers/client đang trả về cùng IP tại thời điểm đó.

### 12.3. Mô phỏng câu trả lời DNS

~~~bash
aws route53 test-dns-answer \
  --hosted-zone-id ZEXAMPLE123456 \
  --record-name api.example.com \
  --record-type A
~~~

**TestDnsAnswer chỉ hỗ trợ public hosted zones.** Công cụ trả về thông tin về câu trả lời Route 53 dự kiến cho một DNS query giả định. Nó có tùy chọn để mô phỏng resolver IP hoặc EDNS Client Subnet:

~~~bash
# Chỉ minh họa cú pháp. Thay địa chỉ bằng IP thực của resolver
# hoặc client subnet được phép thử; không dùng TEST-NET IP
# để suy ra chính xác vị trí địa lý của người dùng.
aws route53 test-dns-answer \
  --hosted-zone-id ZEXAMPLE123456 \
  --record-name site-geo.example.com \
  --record-type A \
  --resolver-ip 8.8.8.8
~~~

Các flag có thể dùng theo nhu cầu: **--resolver-ip**, **--edns0-client-subnet-ip** và **--edns0-client-subnet-mask**. Với public resolver anycast, IP bạn nhìn thấy không luôn đại diện chính xác cho vị trí người dùng. Đừng coi một test từ một IP là kiểm thử đầy đủ mọi quốc gia.

**Kiểm tra khác biệt khi dùng weighted:** Gọi test một lần chỉ cho biết một câu trả lời giả định; không thể từ một lần test chứng minh tỷ lệ 90:10. Muốn đánh giá phân phối thực, cần số mẫu đủ lớn, các resolver độc lập và telemetry thực tế ở backend.

### 12.4. Kiểm tra health checks

~~~bash
aws route53 list-health-checks

aws route53 get-health-check \
  --health-check-id EXAMPLEHEALTHCHECKID

aws route53 get-health-check-status \
  --health-check-id EXAMPLEHEALTHCHECKID
~~~

Đọc cấu hình target HTTP/HTTPS/TCP, path, expected response, threshold và trạng thái health. Trạng thái Route 53 health check chỉ phản ánh tiêu chí nó được cấu hình để đo; không đảm bảo mọi nghiệp vụ ứng dụng đều hoạt động.

### 12.5. Kiểm tra tiến độ một DNS change

~~~bash
aws route53 get-change \
  --id /change/EXAMPLECHANGEID
~~~

Một change được xem là **INSYNC** khi Route 53 đã áp dụng tới name servers theo mô hình của dịch vụ. Resolver/client vẫn có thể cache câu trả lời cũ đến khi hết TTL hoặc do hành vi cache thực tế.

### 12.6. Kiểm tra DNS từ hệ điều hành

~~~bash
# Với hệ thống có dig:
dig api.example.com A
dig api.example.com AAAA
dig site-geo.example.com A

# Truy vấn resolver đã lựa chọn, nếu được phép:
dig @1.1.1.1 api.example.com A
~~~

Lệnh **dig** kiểm tra những DNS answers mà resolver cung cấp tại thời điểm truy vấn; kết quả có thể đến từ cache. Khi cần phân biệt recursive và authoritative, kiểm tra name servers của zone thực sự được ủy quyền. Không chạy một truy vấn rồi kết luận chính sách địa lý hay weighted cho toàn cầu là đúng.

## 13. Hướng dẫn chọn policy cho ứng dụng AWS

### 13.1. Tình huống A — Canary 5% người dùng cho API mới

**Bối cảnh:** Stable đã hoạt động, v2 chưa được kiểm thử đủ tải. Muốn đưa một phần nhỏ DNS answers về v2.

**Lựa chọn ban đầu:** **Weighted routing** (ví dụ 95:5).

**Kiểm tra bắt buộc:**

- Cả stable và canary có health checks phù hợp.
- v2 tương thích database schema và không gây lỗi khi user chuyển giữa phiên bản.
- Metrices và logs tách theo phiên bản/target.
- Không hiểu 5% weighted answers thành chính xác 5% active sessions hay HTTP requests.
- Kịch bản rollback không dựa vào “weight 0 chắc chắn cắt toàn bộ traffic”.

**Khi không phù hợp:** Nếu canary phải gắn cố định theo user ID, account tenant hoặc cookie, cân nhắc routing ở tầng ứng dụng.

### 13.2. Tình huống B — Ứng dụng API phục vụ châu Á và châu Âu

**Bối cảnh:** Backend ở Singapore và Frankfurt đều sẵn sàng, dữ liệu và authorization tương thích.

**Lựa chọn ban đầu:** **Latency-based routing**, nếu mục tiêu chính là trải nghiệm tốc độ.

**Kiểm tra:**

- Đo p95/p99 latency và error rate theo Region.
- Kiểm thử failover khi backend ở Region gần nhất gặp lỗi.
- Đánh giá replication/consistency của dữ liệu và ảnh hưởng cross-Region.
- Kiểm tra kết quả DNS từ nhiều resolver/country chứ không chọn Region bằng khoảng cách bản đồ.

Nếu có **yêu cầu lưu trữ/xử lý dữ liệu theo biên giới pháp lý**, phải thiết kế policy dữ liệu và kiểm soát ứng dụng riêng; latency routing tự nó không đáp ứng ràng buộc đó.

### 13.3. Tình huống C — Website trả nội dung riêng cho Việt Nam

**Bối cảnh:** Người dùng từ Việt Nam nên thấy giao diện hoặc điểm đến nội dung Việt Nam; khách khác nhận website quốc tế.

**Lựa chọn ban đầu:** **Geolocation**, country VN và **Default**.

**Kiểm tra:**

- Test từ nhiều resolver/ISP/VPN.
- Không nhầm địa chỉ resolver với địa chỉ vật lý.
- Có default cho quốc gia không cấu hình và IP không phân loại được.
- Ứng dụng có cơ chế chọn ngôn ngữ thủ công hoặc account preferences để tránh phụ thuộc tuyệt đối vào geo-IP.

### 13.4. Tình huống D — Điều chỉnh tải giữa hai trung tâm dữ liệu

**Bối cảnh:** Hai endpoint ở các vị trí khác nhau có capacity chênh lệch; muốn mở rộng vùng ảnh hưởng của endpoint nhiều capacity.

**Ứng viên:** **Geoproximity** với **bias** nhỏ và kiểm thử từng bước. Nếu mục tiêu là tỷ lệ tổng thể cụ thể không theo khoảng cách, chọn **Weighted** sẽ dễ diễn đạt hơn.

**Kiểm tra:** Quan sát traffic và latency thực tế. Bias không có nghĩa trực tiếp tăng 10% traffic khi tăng bias 10.

### 13.5. Tình huống E — Dự phòng 100% khi Region chính hỏng

**Bối cảnh:** Region phụ không nhận traffic trong vận hành bình thường, chỉ nhận khi Region chính lỗi.

**Ứng viên:** **Failover routing policy** với primary/secondary và health checks phù hợp; hoặc mô hình DNS nhiều lớp đã được kiểm chứng.

**Không nên:** Chỉ đặt weighted 100:0 rồi mặc định đáp ứng RTO vì TTL, cache và health check/fail-open behavior còn tác động.

## 14. Khắc phục sự cố định tuyến DNS

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| 90:10 nhưng backend canary nhận 30% requests. | Cache ở recursive resolver, lượng truy vấn nhỏ, session/connection reuse, client hoặc retry khác nhau. | DNS answers theo mẫu và request logs/metrics theo backend. |
| Người dùng Việt Nam nhận endpoint Default. | Query đến qua DNS resolver ở nơi khác, ECS không có, IP không định vị được, record VN sai. | TestDnsAnswer với nguồn phù hợp, GeoLocation và DNS resolver thực tế. |
| Latency routing chọn Tokyo thay vì Singapore. | Độ trễ mạng AWS đo được tốt hơn tới Tokyo; vị trí resolver/ECS khác dự kiến. | Xem Region field, DNS test, đo latency thực và resolver. |
| Ứng dụng đã down nhưng DNS vẫn trả về record cũ. | Chưa có health check, health check sai target/path hoặc tất cả record unhealthy rồi fail-open. | get-health-check-status, EvaluateTargetHealth, health config. |
| Đã rollback nhưng một số client vẫn tới canary. | TTL/cache, kết nối dài hạn hoặc weight 0 fallback khi các endpoint còn lại unhealthy. | GetChange INSYNC, TTL, connection pooling, kiểm tra backend health. |
| DNS trả “no answer” ở một số quốc gia. | Thiếu geolocation Default hoặc record phù hợp. | Xem GeoLocation records và mô phỏng vị trí. |
| Alias đến ALB không hoạt động. | Sai AliasTarget DNSName/HostedZoneId, policy/zone, ALB health hoặc routing/network. | list-resource-record-sets, ELB/target health, DNS và TLS. |
| Một môi trường trả endpoint khác dù cùng domain. | Public/private hosted zone trùng tên, VPC association hoặc resolver forwarding khác. | get-hosted-zone, VPC Resolver path, delegation, query từ đúng môi trường. |
| Record mới không có hiệu lực với công chúng. | Domain chưa delegate đúng name servers, thay đổi chưa INSYNC, cache cũ. | NS records tại registrar/parent zone, GetChange, TTL. |

### 14.1. Cây chẩn đoán gợi ý

~~~mermaid
flowchart TD
    A["Client đến sai endpoint"] --> B{"Đúng hosted zone và delegation?"}
    B -->|"Không"| B1["Sửa hosted zone / NS delegation"]
    B -->|"Có"| C{"Record Name, Type, SetIdentifier đúng?"}
    C -->|"Không"| C1["Kiểm tra RRset và policy"]
    C -->|"Có"| D{"Nguồn resolver/ECS được hiểu đúng?"}
    D -->|"Không"| D1["Thử qua resolver và vị trí khác"]
    D -->|"Có"| E{"Health checks / alias target đúng?"}
    E -->|"Không"| E1["Kiểm tra health và fallback"]
    E -->|"Có"| F{"Có cache TTL hoặc connection cũ?"}
    F -->|"Có"| F1["Chờ cache hợp lệ / đánh giá session"]
    F -->|"Không"| G["Đối chiếu logs/metrics tầng app và network"]
~~~

**Không** giải quyết mọi lỗi bằng cách giảm TTL về 0 hoặc mở rộng quyền truy cập endpoint. Cần biết vấn đề xảy ra ở **DNS routing, DNS cache, network hay ứng dụng**.

## 15. Giám sát, chi phí và khả năng phục hồi

### 15.1. Metrics và log cần theo dõi

- **Route 53 health checks:** tình trạng từng endpoint và alarm tương ứng.
- **CloudWatch metrics:** lượng DNS query theo loại hình có thể theo dõi qua các nguồn được AWS hỗ trợ, cùng metric sức khỏe endpoint và tài nguyên ứng dụng.
- **Route 53 query logging:** cấu hình theo loại hosted zone/public/private và điểm nhận log phù hợp.
- **CloudTrail:** ghi nhận hoạt động quản trị Route 53 như thay đổi record/zone trong phạm vi đã cấu hình.
- **ALB/API/CloudFront/application metrics:** request counts, status codes, p95/p99 latency, errors, target health.
- **Chi phí:** phí hosted zone, DNS queries, health checks và logging, cộng chi phí ALB/EC2/ECS/CloudFront/transfer/cross-Region/backend.

Route 53 query logs có thể giúp phân tích truy vấn DNS nhưng **không cho biết chính xác tất cả các HTTP requests mà browser gửi tới backend**. DNS caching khiến một lookup có thể phục vụ nhiều request.

### 15.2. Cân bằng chi phí và thời gian phục hồi

TTL ngắn hơn có thể giúp resolver hỏi lại sớm hơn khi endpoint thay đổi, nhưng số DNS queries và chi phí có thể tăng. DNS health checks có phí theo loại/tính năng. Multi-Region active-active còn có chi phí:

- Tài nguyên compute/database ở nhiều Region.
- Replication và data transfer liên vùng.
- Monitoring, backup, logs và bài kiểm tra failover.
- Chi phí vận hành, certificate/secret, hạ tầng triển khai riêng từng Region.

Không đánh giá lợi ích của Latency routing chỉ bằng response DNS: **độ trễ xử lý request end-to-end, consistency, error rate, RPO/RTO và chi phí toàn hệ thống** mới quyết định hiệu quả thực sự.

### 15.3. Khả năng phục hồi ở hai tầng

**Tầng DNS:** policy, health checks, TTL, alias tree và zone delegation hoạt động đúng.

**Tầng dịch vụ:** backend, dữ liệu, network, certificates, IAM/KMS, session và failover đã được thiết kế/diễn tập.

Nếu ứng dụng chỉ có một database đặt trong Region A nhưng DNS chuyển users sang Region B, dịch vụ Region B có thể vẫn lỗi nghiệp vụ. DNS failover không tự động replicate hoặc phục hồi dữ liệu.

## 16. Bài tập thực hành

### Bài tập 1 — Tính weight

Một nhóm weighted records có trọng số:

- **v1 = 180**
- **v2 = 20**
- **v3 = 0**

Giả sử v1/v2 healthy và đều đủ điều kiện, ước tính tỷ lệ DNS answers thế nào?

**Đáp án:** v1 ≈ 90%, v2 ≈ 10%, v3 ≈ 0%. Tuy nhiên v3 weight 0 không tuyệt đối bị vô hiệu nếu tất cả record có weight dương đều bị đánh giá unhealthy và Route 53 áp dụng fallback.

Nếu đổi toàn bộ weight thành 0, Route 53 không làm nhóm tắt hoàn toàn mà chọn giữa các records với xác suất bằng nhau theo behavior tài liệu.

### Bài tập 2 — Canary không đúng tỷ lệ request

Một tổ chức dùng Weighted 99:1 cho API nhưng canary ghi nhận gần 15% HTTP requests trong một khoảng thời gian ngắn. Hãy nêu ít nhất ba nguyên nhân có thể.

**Gợi ý:** DNS recursive caching tập trung nhiều client, số DNS queries ít, long-lived connections, retry, client không phân phối đồng đều, khác biệt traffic theo resolver, health check thay đổi tập endpoint. Thu thập nhiều mẫu và log ở backend trước khi kết luận policy sai.

### Bài tập 3 — Chọn latency hay geography?

Ứng dụng chạy Singapore và Tokyo. Mục tiêu chính là giảm độ trễ cảm nhận của users ở nhiều nước châu Á, **không có ràng buộc nội dung theo quốc gia**.

**Đáp án:** Bắt đầu với **Latency routing** và đo kết quả. Không chọn Geolocation chỉ dựa trên bản đồ. Nếu từng thị trường có chính sách nội dung cụ thể, xem xét Geolocation cùng cơ chế ứng dụng.

### Bài tập 4 — Default cho geolocation

Một hosted zone có record cho VN và EU nhưng không có Default. Khách ở Canada không nhận answer. Bạn nên làm gì?

**Đáp án:** Cấu hình **Default geolocation record** nếu mong muốn phục vụ các khu vực còn lại; kiểm tra zone/record type, DNS cache, health checks và behavior thực tế. Nếu doanh nghiệp cố ý không phục vụ Canada, cần thực thi quyết định bằng lớp bảo mật/nghiệp vụ thích hợp, không chỉ coi thiếu DNS answer là cơ chế pháp lý đầy đủ.

### Bài tập 5 — Health check trỏ về chính hostname cần điều khiển

Bạn gắn health check của endpoint Singapore tới **api.example.com**, trong khi api.example.com có latency records cho Singapore và Tokyo. Vì sao nguy hiểm?

**Đáp án:** Health check có thể đi qua chính routing policy và được trả về backend khác, khiến tình trạng health không đại diện chính xác endpoint Singapore. Nên kiểm tra hostname/IP/endpoint riêng cho từng backend.

### Bài tập 6 — Multi-Region nhưng không có dữ liệu

Route 53 Latency policy chuyển users từ Singapore sang Tokyo khi Singapore lỗi. Tokyo ALB healthy nhưng truy vấn nghiệp vụ vẫn lỗi vì Tokyo chưa có dữ liệu mới nhất.

**Đáp án:** Health check tầng load balancer không chứng minh dữ liệu/ứng dụng sẵn sàng. Cần thiết kế data replication, consistency, readiness/health checks đủ điều kiện, xử lý RPO/RTO và diễn tập failover trước khi công bố multi-Region.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Route 53 Weighted routing đảm bảo chính xác 10% HTTP requests vào canary không?  
**Đáp án:** Không. Trọng số định hướng phân phối câu trả lời DNS; cache, phiên kết nối và hành vi client có thể khiến tỷ lệ requests khác.

**Câu 2.** Hai weighted records có weight 30 và 70 thì record đầu có tỷ lệ bao nhiêu?  
**Đáp án:** Xấp xỉ 30% DNS answers khi cả hai đều đủ điều kiện/healthy và không có record khác trong nhóm.

**Câu 3.** Nếu tất cả weighted records đều weight 0 thì Route 53 trả no answer?  
**Đáp án:** Không. Chúng có thể được chọn với xác suất bằng nhau theo quy tắc của AWS.

**Câu 4.** Weight 0 có thể vẫn được chọn khi nào?  
**Đáp án:** Khi tất cả record có weight dương được đánh giá unhealthy trong cấu hình health checks thích hợp, hoặc khi toàn nhóm weight 0.

**Câu 5.** Latency routing chọn endpoint gần nhất về km hay theo dữ liệu AWS?  
**Đáp án:** Theo dữ liệu ước lượng network latency tới các AWS Region được cấu hình, không đơn thuần khoảng cách địa lý.

**Câu 6.** Geolocation định tuyến theo loại vị trí nào?  
**Đáp án:** Châu lục, quốc gia, bang Hoa Kỳ trong phạm vi hỗ trợ và Default.

**Câu 7.** Trong các records cho châu Á, Việt Nam và Default, query định vị ở Việt Nam ưu tiên record nào?  
**Đáp án:** Việt Nam, vì có vị trí khớp cụ thể hơn.

**Câu 8.** Vì sao cần Default record?  
**Đáp án:** Phục vụ các vị trí không có match hoặc IP không xác định được; thiếu Default có thể gây không có DNS answer cho những query đó.

**Câu 9.** Geoproximity khác geolocation và latency thế nào?  
**Đáp án:** Geoproximity tính vùng ảnh hưởng dựa trên vị trí tài nguyên/client và bias, khác quy tắc country/continent của geolocation và dữ liệu latency thực tế của latency routing.

**Câu 10.** Có health check nhưng mọi endpoints unhealthy thì Route 53 luôn trả no answer?  
**Đáp án:** Không. Route 53 có behavior fail-open theo nhóm policy để vẫn cung cấp câu trả lời trong một số cấu hình.

**Câu 11.** TTL 60 giây có bảo đảm mọi client chuyển endpoint đúng 60 giây sau khi update?  
**Đáp án:** Không. Cache, resolver, application behavior, kết nối đang mở và DNS propagation đều ảnh hưởng.

**Câu 12.** EDNS Client Subnet giúp gì?  
**Đáp án:** Khi DNS resolver hỗ trợ, nó gửi một phần subnet của client giúp Route 53 ước lượng vị trí thay vì chỉ dùng IP của resolver.

**Câu 13.** TestDnsAnswer dùng kiểm tra private hosted zone được không?  
**Đáp án:** Không. API **test-dns-answer** chỉ hỗ trợ **public hosted zones**.

**Câu 14.** Route 53 Latency routing có tự sao chép database giữa AWS Regions không?  
**Đáp án:** Không. Replication/failover dữ liệu cần được thiết kế riêng.

**Câu 15.** Nếu cần thử tính năng mới với đúng 5% user ID, weighted DNS có phù hợp tuyệt đối không?  
**Đáp án:** Không. Feature flag hoặc routing theo session/user ở tầng ứng dụng phù hợp hơn để kiểm soát chính xác nhóm người dùng.

**Câu 16.** Route 53 có thay CloudFront về khả năng cache ảnh tĩnh ở edge không?  
**Đáp án:** Không. Route 53 trả DNS answers; CloudFront là CDN phân phối và cache nội dung.

## 18. Tổng kết

**Ba chính sách chính cần phân biệt:**

- **Weighted routing:** chọn record theo **trọng số tương đối**. Phù hợp canary, chuyển traffic từng phần, phân bổ chủ động; không đảm bảo tỷ trọng HTTP request hoặc cắt endpoint tuyệt đối chỉ bằng weight 0.
- **Latency-based routing:** chọn **AWS Region với network latency được dự đoán tốt nhất** cho nguồn DNS query. Phù hợp active-active multi-Region; không bảo đảm vùng xử lý dữ liệu theo quy định pháp lý.
- **Geolocation routing:** chọn endpoint theo **châu lục/quốc gia/bang Hoa Kỳ**, ưu tiên vùng cụ thể nhất và nên có **Default**. Phù hợp điều phối nội dung theo thị trường; không xác định chắc vị trí thật của từng người.
- **Geoproximity routing:** chọn theo **vị trí và bias** để mở rộng/thu hẹp vùng ảnh hưởng của tài nguyên; không đồng nghĩa thuật toán đo latency.

**Mẫu tư duy triển khai an toàn:** Chọn policy theo mục tiêu → thiết kế record/alias đúng cấu trúc → gắn health phù hợp → tính TTL/cache/resolver/ECS → kiểm tra ứng dụng và dữ liệu ở từng Region → quan sát hiệu năng/tỉ lệ lỗi → diễn tập rollback/failover → quản trị IAM, DNS delegation và tổng chi phí.

Route 53 quyết định **DNS answer**, nhưng tính sẵn sàng của sản phẩm còn phụ thuộc **ALB, VPC, compute, database, IAM, TLS, giám sát và khả năng khôi phục**. Thiết kế cả hai tầng sẽ giúp doanh nghiệp dùng AWS hiệu quả, an toàn và có khả năng phục hồi.

### Tài liệu AWS chính thức

- [Choosing a routing policy](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html) — các chính sách định tuyến Route 53.
- [Weighted routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-weighted.html) — tỷ trọng và behavior khi weight bằng 0.
- [Latency-based routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-latency.html) — chọn Region theo latency.
- [Geolocation routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-geo.html) — vị trí cụ thể, vùng ưu tiên và Default.
- [Geoproximity routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-geoproximity.html) — bias và vùng ảnh hưởng.
- [EDNS0 and client location](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-edns0.html) — sử dụng resolver IP và EDNS Client Subnet.
- [How Route 53 chooses records with health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — healthy, unhealthy và fail-open.
- [Best practices for Route 53 DNS](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html) — TTL, routing, propagation và thiết kế DNS.
- [AWS CLI: test-dns-answer](https://docs.aws.amazon.com/cli/latest/reference/route53/test-dns-answer.html) — mô phỏng câu trả lời từ public hosted zone.

