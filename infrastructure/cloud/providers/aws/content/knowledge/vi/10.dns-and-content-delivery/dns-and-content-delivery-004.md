# Health check, failover DNS và thời gian TTL

> **Chương:** DNS và phân phối nội dung  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — tìm hiểu hệ sinh thái AWS từ Region/AZ, IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn kỹ năng thiết kế hệ thống an toàn, giám sát được, có khả năng phục hồi và kiểm soát chi phí.

Khi hệ thống phục vụ khách hàng bằng tên miền `app.example.com`, người dùng không cần biết chính xác máy chủ ở Availability Zone (AZ) hay AWS Region nào. **DNS** giúp tìm địa chỉ/đích dịch vụ, còn **health check** giúp xác định đích nào vẫn đáp ứng tiêu chí sức khỏe. **DNS failover** của Amazon Route 53 kết hợp hai yếu tố đó: nếu đích chính được đánh giá không khỏe, Route 53 có thể trả về đích dự phòng cho các truy vấn DNS mới.

Nhưng có một giới hạn quan trọng: **Route 53 không điều khiển được ngay lập tức mọi kết nối đang mở hoặc mọi bản ghi DNS đã nằm trong cache của client**. Do đó, thiết kế failover phải hiểu **TTL (Time to Live)**, thời gian phát hiện lỗi, sự sẵn sàng của hệ thống dự phòng và hành vi retry/reconnect của ứng dụng.

Các tên miền, địa chỉ IP, Region và cấu hình trong bài là ví dụ. Nội dung tập trung vào **public DNS/Route 53** với những ghi chú cần thiết cho private endpoint; khi triển khai thật phải kiểm tra loại hosted zone, dịch vụ đích, quyền IAM, quota và tính năng đang hỗ trợ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả đường đi của một truy vấn DNS từ ứng dụng tới recursive resolver và authoritative DNS.
2. Phân biệt **Route 53 health check**, **ALB target-group health check**, **CloudWatch-alarm-based health check** và **Evaluate Target Health** của alias record.
3. Cấu hình logic **primary/secondary failover**, giải thích kết quả khi một hoặc cả hai đích không khỏe.
4. Phân tích ảnh hưởng của **TTL**, recursive caching, ứng dụng giữ kết nối lâu và thời gian phát hiện lỗi tới RTO.
5. Thiết kế failover hai Region với readiness endpoint, dữ liệu, xác thực, điều kiện chuyển lại và kế hoạch quan sát.
6. Dùng AWS CLI hoặc công cụ DNS để kiểm tra records, health status và câu trả lời DNS mà không thay đổi tài nguyên.

## 2. DNS làm gì, và không làm gì?

DNS (Domain Name System) biến tên như `app.example.com` thành dữ liệu DNS phù hợp, chẳng hạn bản ghi `A`/`AAAA` hoặc chuỗi tham chiếu khác. **Amazon Route 53** có thể đóng vai trò **authoritative DNS** cho một public hosted zone, tức là dịch vụ có thẩm quyền trả lời về bản ghi của tên miền được ủy quyền cho nó.

### 2.1. Dòng đi của một truy vấn

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng / trình duyệt
    participant Resolver as Recursive DNS resolver
    participant R53 as Route 53 authoritative DNS
    participant API as Endpoint ứng dụng
    App->>Resolver: Hỏi A app.example.com
    alt Resolver còn bản ghi hợp lệ trong cache
        Resolver-->>App: Trả bản ghi đã cache
    else Cache hết hạn hoặc chưa có
        Resolver->>R53: Truy vấn authoritative DNS
        R53-->>Resolver: Câu trả lời theo routing và health hiện tại
        Resolver-->>App: Trả câu trả lời và cache theo TTL
    end
    App->>API: Kết nối HTTPS đến địa chỉ/đích đã nhận
~~~

Sơ đồ rút gọn quá trình phân giải DNS; thực tế có root/TLD/name servers, DNS cache ở hệ điều hành/ứng dụng và có thể có CNAME hoặc nhiều bước truy vấn. Điều quan trọng là **Route 53 không nhận mọi truy vấn của từng client**: nhiều client có thể dùng chung một recursive resolver, và resolver có thể trả từ cache mà không hỏi lại authoritative DNS.

### 2.2. DNS không phải mạng truyền dữ liệu ứng dụng

- Route 53 trả lời câu hỏi **“nên đi tới đâu?”**, không phải proxy truyền toàn bộ HTTP request từ client tới server.
- Sau khi đã có IP, client mở TCP/TLS/HTTP theo cách của ứng dụng. Việc DNS thay đổi **không tự kết thúc TCP connection đang sống**.
- Route 53 không tự thay thế ALB, Auto Scaling, Security Group, WAF, cơ sở dữ liệu hoặc cơ chế phục hồi dữ liệu.
- Nếu DNS trả một endpoint khỏe nhưng endpoint đó không có dữ liệu mới, không đủ capacity hoặc bị lỗi phân quyền, nghiệp vụ vẫn có thể thất bại.

### 2.3. Các loại bản ghi liên quan

| Record | Vai trò | Liên quan failover |
| --- | --- | --- |
| `A` | Trả địa chỉ IPv4 | Có thể dùng với routing policy failover |
| `AAAA` | Trả địa chỉ IPv6 | Nếu hỗ trợ IPv6, cần tính cả đường failover IPv6 |
| `CNAME` | Tên này trỏ sang một tên DNS khác | Không dùng CNAME tại zone apex theo quy tắc DNS thông thường |
| **Route 53 alias A/AAAA** | Trỏ đến tài nguyên AWS được hỗ trợ hoặc record trong hosted zone | Có thể dùng failover và `Evaluate Target Health` khi đối tượng đích hỗ trợ |
| `NS`, `SOA` | Ủy quyền và thông tin zone | Quan trọng cho DNS hosting, không phải hai đích primary/secondary |

**Alias không đồng nghĩa CNAME**. Alias là tính năng Route 53, cho phép trỏ `A`/`AAAA` vào những tài nguyên hỗ trợ như Elastic Load Balancing và có thể dùng ở zone apex. Chọn record type và đối tượng đích dựa theo tài liệu của tài nguyên, không tùy ý gán CNAME cho toàn bộ record.

## 3. Health check trong Route 53

**Health check** là cơ chế đánh giá một tài nguyên hoặc tín hiệu vận hành có đáp ứng điều kiện đã cấu hình không. Route 53 dùng trạng thái đó để quyết định record nào có thể được trả về trong những routing policy được hỗ trợ.

### 3.1. Các cách đánh giá sức khỏe

| Cách đánh giá | Dữ liệu đầu vào | Dùng khi |
| --- | --- | --- |
| **Endpoint health check** | Kiểm tra TCP, HTTP hoặc HTTPS tới endpoint | Có URL/port kiểm tra phản ánh khả năng phục vụ |
| **CloudWatch alarm health check** | Trạng thái alarm và cách xử lý thiếu dữ liệu theo cấu hình | Sức khỏe không thể đo chỉ bằng một HTTP URL, cần metric nghiệp vụ |
| **Calculated health check** | Kết hợp trạng thái các health check con | Muốn mô tả quy tắc tổng hợp điều kiện hệ thống |
| **Private endpoint health check** (khi khả dụng) | Health check source trong VPC truy cập private endpoint | Endpoint nội bộ, khác với public health checker |
| **Alias Evaluate Target Health** | Trạng thái do AWS cung cấp cho alias target được hỗ trợ | Record alias tới ALB hoặc tài nguyên hỗ trợ đánh giá sức khỏe |

Không phải mọi lựa chọn đều áp dụng được cho mọi loại alias record và tài nguyên. Ví dụ không được mặc định `Evaluate Target Health` hỗ trợ giống nhau cho ALB, CloudFront, S3 website và mọi dịch vụ AWS. Trước khi dùng, kiểm tra tài liệu đích và cơ chế health được hỗ trợ.

### 3.2. Endpoint health check: HTTP/HTTPS hay TCP?

- **TCP**: chỉ kiểm tra có thiết lập được kết nối TCP với port mong muốn hay không. Cổng mở **không chứng minh ứng dụng xử lý giao dịch được**.
- **HTTP/HTTPS**: gửi request đến endpoint đã cấu hình (host/port/path), xem phản hồi; thông thường mã **2xx/3xx** đáp ứng điều kiện status, có thể thêm **string matching** với nội dung body khi được hỗ trợ.
- **HTTPS**: kiểm tra đường truyền HTTPS, nhưng đừng mặc định điều đó thay thế việc giám sát **chứng chỉ, ngày hết hạn, tên miền, cấu hình TLS** theo yêu cầu bảo mật riêng.
- **CloudWatch alarm**: thích hợp khi trạng thái phụ thuộc vào metric như số giao dịch thành công, queue backlog hoặc lỗi nghiệp vụ không phản ánh đầy đủ bằng một HTTP request.

Một endpoint đơn giản:

~~~http
GET /health/ready HTTP/1.1
Host: primary.example.net
~~~

Ví dụ response khỏe:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

READY
~~~

Response thất bại khi ứng dụng không thể phục vụ:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

NOT_READY
~~~

**Phân biệt liveness và readiness:**

- **Liveness:** process còn chạy hay đang treo; thường dùng để restart container/process.
- **Readiness:** instance/Region có đủ điều kiện nhận request thật hay chưa; thích hợp hơn cho điều hướng traffic.

Endpoint trả `200` chỉ vì web server còn sống có thể khiến Route 53 tiếp tục trả về một Region đã mất database hoặc dịch vụ phụ thuộc bắt buộc. Nhưng health check **quá phụ thuộc** vào nhiều hệ thống không quan trọng cũng có thể tạo failover giả và vòng chuyển đổi liên tục. Hãy định nghĩa một tín hiệu gần với khả năng phục vụ nghiệp vụ, đồng thời tránh check nặng gây quá tải.

### 3.3. Interval và failure threshold

Với health check endpoint Route 53 theo cách phổ biến, có thể chọn chu kỳ như **30 giây (standard)** hoặc **10 giây (fast)**, tùy loại/tính năng được hỗ trợ. **Failure threshold** là số lần kiểm tra lỗi liên tiếp cần thiết trước khi checker đánh giá endpoint không khỏe; mặc định thường là **3**.

Ví dụ cấu hình minh họa:

| Thuộc tính | Giá trị |
| --- | --- |
| Type | HTTPS |
| Domain name | `primary.example.net` |
| Port/path | `443` / `/health/ready` |
| Request interval | 30 giây |
| Failure threshold | 3 |
| Health-checker regions | Các vùng kiểm tra được chọn theo hỗ trợ |

**Không tính “thời gian phát hiện = 30 × 3 = đúng 90 giây”**. Route 53 sử dụng nhiều health checker ở những vị trí khác nhau, mỗi checker kiểm tra theo lịch riêng; còn thời gian chờ response, việc tổng hợp trạng thái và DNS resolver caching. 90 giây chỉ có thể là con số trực giác để hiểu ngưỡng, không phải SLA hay RTO chính xác.

Chu kỳ 10 giây giúp phản ứng nhanh hơn trong một số tình huống nhưng thường **có chi phí cao hơn** và vẫn không bảo đảm tất cả client chuyển ngay tức thì.

### 3.4. Public endpoint và private endpoint

Health check endpoint **công khai** truyền thống dùng các Route 53 health checkers có khả năng truy cập công cộng. Nó không thể tự nhiên kết nối tới một IP private `10.0.1.10` chỉ vì IP đó tồn tại trong VPC. Phải xác định đường truy cập thật sự:

- Với ALB internet-facing hoặc public API, dùng health check phù hợp với host/path/port, đảm bảo Security Group/WAF không chặn nhầm các checker.
- Với dịch vụ chỉ dùng private IP, có thể dùng **private endpoint health checks** khi Region/tính năng đáp ứng, hoặc giám sát từ trong VPC và đưa trạng thái qua CloudWatch alarm/giải pháp thích hợp.
- Private endpoint health check sử dụng health-check source trong VPC, có yêu cầu subnet/AZ/DNS riêng và miền lỗi của nguồn kiểm tra; nó **không** giống việc cho public health checker truy cập trực tiếp private IP.

Đối với ứng dụng private, cũng cần cân nhắc **private hosted zone** và Route 53 Resolver theo phạm vi DNS. Public DNS failover không tự tạo đường VPC nội bộ qua nhiều Region.

### 3.5. Khi host kiểm tra trùng với DNS failover name

Nếu primary và secondary đều được cung cấp qua `app.example.com`, **không** nên tạo health check theo domain `app.example.com` rồi gắn chính health check đó vào record đang quyết định câu trả lời cho `app.example.com`. Việc health check phụ thuộc vào DNS record mà nó đang điều khiển dễ dẫn đến vòng lặp quan sát và kết quả không dự đoán được.

Thay vào đó, có endpoint độc lập:

~~~text
app.example.com               ← DNS failover người dùng truy cập
primary.example.net            ← health check primary (không failover vòng lại)
secondary.example.net          ← health check secondary
~~~

Nếu kiểm tra HTTPS bằng hostname, xác nhận `Host` header, TLS SNI, chứng chỉ, path và WAF rule để check đi đúng vhost. Địa chỉ kiểm tra phải phản ánh dịch vụ cụ thể ở Region tương ứng, không đi qua một cache/proxy chung có thể che giấu lỗi origin.

## 4. Health check của Route 53 khác health check ALB ra sao?

Ứng dụng production thường có nhiều lớp điều hướng:

~~~mermaid
flowchart TB
    C["Client / recursive DNS resolver"] --> R53["Route 53 failover\nchọn endpoint/Region"]
    R53 --> P["ALB ở Region chính\nnhiều AZ"]
    R53 --> S["ALB ở Region phụ\nnhiều AZ"]
    P --> PT["Target group chính\nEC2/ECS trong nhiều AZ"]
    S --> ST["Target group phụ\nEC2/ECS trong nhiều AZ"]
    PT --> DBP["Cơ sở dữ liệu chính"]
    ST --> DBS["Dữ liệu dự phòng\nđúng mục tiêu RPO"]
~~~

- **ALB target-group health check** đánh giá target EC2/ECS/địa chỉ IP phía sau ALB để phân phối request đến những target khỏe theo cơ chế của Elastic Load Balancing.
- **Route 53 health check** thường dùng để quyết định **endpoint cấp cao** nào được trả về trong DNS (ví dụ Region chính hay Region dự phòng).
- **Alias Evaluate Target Health** có thể dùng tín hiệu sức khỏe do dịch vụ đích hỗ trợ (chẳng hạn ALB), thay vì phải duy trì một Route 53 endpoint health check độc lập cho alias đó.

ALB có thể khỏe về mặt target group trong khi workflow đặt hàng không hoạt động do lỗi phụ thuộc khác. Ngược lại, một target lỗi không đồng nghĩa cả Region thất bại: ALB/Auto Scaling có thể thay target để phục vụ bình thường mà không cần DNS failover.

**Nguyên tắc:** giải quyết lỗi hẹp bằng cơ chế hẹp nhất — khôi phục target tại ALB/ASG trước, chỉ chuyển Route 53 sang Region khác khi sự cố hoặc mục tiêu availability thật sự cần.

## 5. Failover DNS: primary và secondary

Route 53 có **Failover routing policy** cho mô hình **active–passive**:

- **Primary:** endpoint mặc định, nhận DNS queries khi Route 53 coi primary là khỏe.
- **Secondary:** endpoint dự phòng, được chọn khi primary không khỏe và secondary đủ điều kiện.
- Cặp failover records có **cùng Record name và Record type**, khác `SetIdentifier`/vai trò `PRIMARY` và `SECONDARY`.
- Cả hai có thể là non-alias hoặc alias record theo các quy tắc hỗ trợ.
- Nếu secondary không có health check, Route 53 có thể coi nó là đích dự phòng khả dụng để trả DNS mà **không chứng minh secondary thực sự khỏe**.

### 5.1. Bảng quyết định khi có health check cho cả hai

| Primary | Secondary | Route 53 trả lời các DNS query mới |
| --- | --- | --- |
| **Healthy** | Healthy | **Primary** |
| **Healthy** | Unhealthy | **Primary** |
| **Unhealthy** | Healthy | **Secondary** |
| **Unhealthy** | Unhealthy | **Primary** theo quy tắc failover này |

Hàng cuối rất dễ bị bỏ qua: **Route 53 không tự tạo một đích khỏe khi cả hai đều hỏng.** Với cặp failover records được kiểm tra sức khỏe, nếu không còn đích khỏe, nó có thể trả primary thay vì trả lời “không có dịch vụ”. Vì vậy, **chỉ nhìn DNS record được trả về không phải là bằng chứng endpoint khỏe**.

Nếu không thiết lập health check cho secondary, Route 53 không thể xác minh trạng thái thực của nó qua health check đó. Kết quả có thể bị đẩy sang một secondary đang hỏng, dù primary cũng không phục vụ được.

### 5.2. Sơ đồ failover hai Region

~~~mermaid
sequenceDiagram
    participant HC as Health checkers
    participant P as Primary Region
    participant R53 as Route 53
    participant DNS as Recursive resolver
    participant C as Client
    participant S as Secondary Region
    HC->>P: HTTPS /health/ready
    P-->>HC: 503 / timeout liên tiếp
    HC->>R53: Trạng thái primary = unhealthy
    C->>DNS: Hỏi app.example.com
    alt Resolver đã hết cache
        DNS->>R53: Query record failover
        R53-->>DNS: Secondary record
        DNS-->>C: Secondary (theo TTL)
        C->>S: Tạo kết nối mới
    else Resolver còn cache primary
        DNS-->>C: Primary vẫn trong cache
        C->>P: Có thể tiếp tục lỗi
    end
~~~

**DNS failover không chuyển các request đang xử lý dở.** HTTP client có thể cần retry; TCP connection pool có thể vẫn giữ IP/connection cũ; phiên đăng nhập hoặc state lưu cục bộ ở Region chính có thể không tồn tại ở Region phụ.

### 5.3. Failback: khi primary khỏe trở lại

Mặc định, khi primary được coi là khỏe, Route 53 có thể tiếp tục trả primary cho DNS queries mới. Tuy nhiên, **tự động quay lại** không phải lúc nào cũng an toàn:

- Primary có thể còn **data lag** sau sự cố.
- Các thao tác ghi đã chuyển sang secondary có thể chưa được đồng bộ ngược.
- Service mới hồi phục có thể chưa đủ capacity.
- Health endpoint có thể “flap” (đổi healthy/unhealthy liên tục).

Trong những hệ thống cần kiểm soát, dùng tín hiệu readiness phản ánh dữ liệu, cơ chế failback có phê duyệt, hoặc thay đổi routing thủ công/Route 53 ARC theo quy trình DR phù hợp. Đừng để DNS chuyển đổi qua lại trong khi tầng dữ liệu chưa rõ vai trò ghi.

## 6. TTL — vì sao failover không tức thì?

**TTL (Time to Live)** là thời gian DNS record được phép nằm trong **cache của resolver** trước khi cần truy vấn lại authoritative DNS. TTL thường được biểu diễn bằng **giây**, nhưng hành vi cache thực tế còn phụ thuộc hệ điều hành, DNS resolver và thư viện của client.

Ví dụ non-alias record:

~~~text
app.example.com.  60  IN  A  192.0.2.10
                  ^^
                  TTL = 60 giây
~~~

`192.0.2.10` là địa chỉ IPv4 **chỉ dùng làm ví dụ tài liệu**; không phải endpoint Internet đang hoạt động.

### 6.1. Trường hợp resolver còn cache

Giả sử resolver hỏi Route 53 lúc `10:00:00`, nhận primary với TTL 300 giây. Primary bị lỗi lúc `10:00:20`; Route 53 đánh giá primary unhealthy và bắt đầu trả secondary lúc `10:01:00`. Resolver vẫn có thể trả primary theo cache tới khoảng `10:05:00` nếu tuân theo TTL 300 giây mà không có cơ chế refresh sớm.

~~~text
10:00:00   Resolver lấy primary, TTL = 300s
10:00:20   Primary gặp sự cố
10:01:00   Route 53 đã trả secondary cho các query mới
10:02:00   Resolver cũ có thể vẫn trả primary từ cache
10:05:00   Cache cũ hết hạn; resolver hỏi lại và nhận secondary
~~~

Các mốc chỉ để minh họa. Một số resolver có cơ chế giữ cache lâu hơn, làm mới sớm hoặc TTL tối thiểu/tối đa; ứng dụng Java/JVM, HTTP client, proxy hoặc mobile app cũng có thể cache DNS độc lập.

### 6.2. TTL ngắn và TTL dài

| TTL mẫu | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **30–60 giây** | Các resolver tuân TTL có cơ hội nhận đích mới sớm hơn | Tăng DNS query khi cache hết hạn thường xuyên hơn; không loại bỏ độ trễ health detection |
| **300 giây** | Giảm số lần cần hỏi authoritative DNS | Câu trả lời cũ có thể tồn tại nhiều phút |
| **3.600 giây** | Cache lâu, ít truy vấn hơn | Không phù hợp với mục tiêu failover nhanh của nhiều ứng dụng |

Đối với non-alias record gắn Route 53 health check, AWS khuyến nghị TTL **60 giây hoặc ít hơn** để client phản ứng tương đối nhanh với thay đổi sức khỏe. Đây là **khuyến nghị**, không phải cam kết chuyển vùng trong 60 giây.

**TTL không phải thời gian Route 53 phải đợi trước khi đổi câu trả lời.** Khi health check đổi trạng thái, Route 53 cập nhật lựa chọn cho truy vấn mới; TTL chi phối việc recursive resolver/client còn tiếp tục dùng câu trả lời cũ bao lâu.

### 6.3. TTL với alias record

Nếu Route 53 **alias** trỏ trực tiếp tới AWS resource được hỗ trợ, bạn thường **không tự đặt TTL trên alias record**; Route 53 sử dụng TTL của **alias target**. Ví dụ ALB/ELB thường dùng TTL khoảng **60 giây** theo đặc tính dịch vụ. Nếu alias trỏ tới một record khác trong cùng hosted zone, TTL được quyết định theo record đích.

**Không nhầm** việc không có ô TTL khi tạo alias record với “DNS không cache”. Alias vẫn có hành vi TTL trong câu trả lời được authoritative DNS trả về.

### 6.4. TTL và RTO

Một mô hình tư duy đơn giản:

~~~text
Thời gian client thực sự sử dụng được secondary
  ≈ thời gian phát hiện primary unhealthy
  + thời gian cập nhật trạng thái/routing
  + thời gian còn cache DNS ở resolver/client
  + thời gian reconnect/retry
  + thời gian secondary đủ capacity và dữ liệu sẵn sàng
~~~

Đây **không phải công thức SLA**: một số bước có thể chồng lấn, và mỗi client có đường đi/cache khác nhau. Nó giúp đặt câu hỏi đúng khi thiết kế **RTO**.

Ví dụ, chọn TTL 30 giây không giải quyết sự cố nếu:

- Health check cần nhiều thời gian để xác nhận lỗi.
- Application giữ kết nối cũ trong nhiều phút và không reconnect.
- Secondary chưa được warm up hoặc thiếu database.
- Resolver không tuân TTL như dự kiến.

## 7. Thiết kế một kịch bản: ứng dụng nhiều AZ, dự phòng khác Region

### 7.1. Bối cảnh

Giả sử ứng dụng thương mại điện tử hoạt động ở **Region Singapore** (`ap-southeast-1`) và có phương án dự phòng ở **Region Sydney** (`ap-southeast-2`). Cấu trúc minh họa:

~~~text
app.example.com           -> Route 53 Failover DNS

Primary, Singapore:
  ALB (2+ AZ) -> EC2/ECS application (2+ AZ) -> database chính
  Health endpoint: primary.example.net/health/ready

Secondary, Sydney:
  ALB (2+ AZ) -> ứng dụng dự phòng và dữ liệu sẵn sàng phục vụ
  Health endpoint: secondary.example.net/health/ready
~~~

Lựa chọn hai Region có **đánh đổi giữa độ trễ, địa lý dữ liệu, khả năng replication và chi phí**. Chọn Region theo nhu cầu thật, không coi cặp ví dụ là khuyến nghị mặc định cho mọi doanh nghiệp.

### 7.2. Active–passive khác active–active

| Phương án | Luồng bình thường | Khi Region chính mất | Độ phức tạp dữ liệu |
| --- | --- | --- | --- |
| **Active–passive** | Chỉ primary nhận traffic người dùng | Route 53 chuyển DNS queries mới sang secondary | Phải bảo đảm secondary đủ sẵn sàng, đồng bộ và vai trò ghi rõ ràng |
| **Active–active** | Nhiều Region cùng phục vụ | Traffic có thể được chuyển sang Region còn khỏe theo routing policy | Phải giải quyết ghi đa Region, conflict, session và tính nhất quán |

Failover routing policy primary/secondary phù hợp với **active–passive**. Đối với active–active có thể cân nhắc weighted, latency-based hoặc những chiến lược routing khác kèm health phù hợp, nhưng không dùng chúng như cách “tự giải quyết” dữ liệu nhiều Region.

### 7.3. Kiến trúc network và bảo mật

Ở mỗi Region:

- ALB internet-facing nằm ở subnet thuộc nhiều AZ, listener HTTPS với chứng chỉ hợp lệ.
- Ứng dụng nằm trong private subnet, Auto Scaling/ECS có đủ capacity theo kế hoạch.
- Security Group của app chỉ cho phép traffic từ ALB, không public trực tiếp port backend.
- Health endpoint accessible qua đường check dự kiến, tránh lộ thông tin nhạy cảm trong response.
- IAM roles và secrets được thiết kế cho Region/tài khoản tương ứng; không dùng khóa truy cập nhúng vào AMI/image.
- WAF/CDN, Route 53 records và certificate có chính sách phù hợp khi failover; tránh endpoint phụ có TLS hostname không khớp.

**Rủi ro phổ biến:** primary dùng ALB nhiều AZ, nhưng secondary chỉ có một EC2 duy nhất và database chưa đồng bộ. DNS chuyển thành công mà ứng dụng vẫn lỗi — đây không phải vấn đề “TTL quá dài”.

### 7.4. Đảm bảo dữ liệu và RPO

Trước khi bật tự động chuyển người dùng sang secondary, phải trả lời:

1. **Đơn hàng đã ghi tại primary** được sao chép sang secondary bằng cách nào?
2. **RPO** cho phép mất tối đa bao nhiêu dữ liệu?
3. Có cho phép secondary **ghi** không, hay chỉ phục vụ màn hình thông báo/bản đọc?
4. Nếu primary trở lại, dữ liệu ghi tại secondary có cần đồng bộ ngược không?
5. Từng phụ thuộc như S3, database, queue, cache, Secrets Manager có tồn tại ở secondary và có quyền truy cập chưa?

RDS Multi-AZ chỉ giải quyết dự phòng ở mức AZ trong phạm vi Region cho kiểu triển khai tương ứng; nó không tự tạo kế hoạch **cross-Region disaster recovery**. S3 replication thường bất đồng bộ và có độ trễ. DNS failover là **điều hướng lưu lượng**, không phải sao chép dữ liệu.

## 8. Tạo cặp failover records đúng nguyên tắc

Giả sử dùng hai **ALB**, mỗi ALB thuộc một Region. Với Route 53 **alias A records**, có thể tạo cặp:

| Trường | Primary record | Secondary record |
| --- | --- | --- |
| Name | `app.example.com` | `app.example.com` |
| Type | `A` | `A` |
| Routing policy | Failover | Failover |
| Set identifier | `app-primary` | `app-secondary` |
| Failover role | **PRIMARY** | **SECONDARY** |
| Alias target | DNS name của ALB Singapore | DNS name của ALB Sydney |
| Evaluate Target Health | **Yes** nếu được hỗ trợ và phù hợp | **Yes** nếu được hỗ trợ và phù hợp |
| TTL | Theo alias target | Theo alias target |

Khi gắn health check riêng cho **non-alias** failover records, chọn health check tương ứng và TTL ngắn. Với alias record, Route 53 có thể dùng **Evaluate Target Health** thay cho endpoint health check riêng khi tài nguyên hỗ trợ; nếu kết hợp cả health check và Evaluate Target Health, phải hiểu điều kiện đánh giá tổng hợp.

### 8.1. Ví dụ CloudFormation YAML (minh họa, chưa triển khai)

Đoạn dưới đây chỉ thể hiện hai **Route 53 alias failover recordsets**. Các tham số bucket/Region/ALB/zone phải lấy từ hạ tầng thật. Đặc biệt, **HostedZoneId bên trong AliasTarget là canonical hosted zone ID của từng load balancer**, không phải ID hosted zone của tên miền.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Route 53 DNS failover records (example)

Parameters:
  PublicHostedZoneId:
    Type: String
  PrimaryAlbDnsName:
    Type: String
  PrimaryAlbCanonicalZoneId:
    Type: String
  SecondaryAlbDnsName:
    Type: String
  SecondaryAlbCanonicalZoneId:
    Type: String

Resources:
  PrimaryRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref PublicHostedZoneId
      Name: app.example.com.
      Type: A
      SetIdentifier: app-primary
      Failover: PRIMARY
      AliasTarget:
        DNSName: !Ref PrimaryAlbDnsName
        HostedZoneId: !Ref PrimaryAlbCanonicalZoneId
        EvaluateTargetHealth: true

  SecondaryRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref PublicHostedZoneId
      Name: app.example.com.
      Type: A
      SetIdentifier: app-secondary
      Failover: SECONDARY
      AliasTarget:
        DNSName: !Ref SecondaryAlbDnsName
        HostedZoneId: !Ref SecondaryAlbCanonicalZoneId
        EvaluateTargetHealth: true
~~~

**Giới hạn của ví dụ:**

- CloudFormation trên **không tạo** ALB, target groups, cơ sở dữ liệu, health endpoint hoặc ACM certificates.
- `EvaluateTargetHealth` dựa trên sức khỏe của alias target được AWS hỗ trợ. Nếu nghiệp vụ cần giám sát tính sẵn sàng **end-to-end** (ví dụ database), cần thiết kế tín hiệu health khác tương ứng và tích hợp hợp lệ.
- Nếu phân phối qua CloudFront, đừng sao chép nguyên cấu hình health cho ALB và giả định Evaluate Target Health giống nhau với CloudFront. Kiểm tra những lựa chọn failover ở tầng CDN/origin hoặc health check tương ứng.
- Phải thêm `AAAA` tương ứng nếu yêu cầu IPv6 và cấu hình của các tài nguyên hỗ trợ.
- Không chạy stack chỉ để thử trên một hosted zone production: thay đổi DNS có thể ảnh hưởng toàn bộ người dùng.

### 8.2. Non-alias record là phương án khác

Nếu đích là **IP tĩnh có thể truy cập công khai**, có thể tạo failover non-alias `A` records và gắn `HealthCheckId` cho từng đích. Khi đó bạn **tự chọn TTL**, ví dụ `60`. Nhưng với ALB, **không hardcode IP đang resolve từ ALB** vào `A` record: IP của load balancer có thể thay đổi; dùng alias vào ALB để Route 53 theo dõi địa chỉ phù hợp.

### 8.3. Tránh vòng lặp trong health check

Không cấu hình health check của primary bằng `app.example.com` rồi gắn nó vào chính failover record `app.example.com`. Health checker có thể nhận secondary khi primary lỗi, thấy secondary khỏe rồi đánh giá sai primary là khỏe. Dùng hostname/địa chỉ **riêng cho từng endpoint** hoặc tín hiệu được dịch vụ cung cấp.

## 9. Kiểm tra bằng AWS CLI và công cụ DNS (chỉ đọc)

Các lệnh sau chỉ xem trạng thái, không tạo/sửa/xóa record. Thay hosted zone ID và health check ID bằng dữ liệu thật được phép xem.

### 9.1. Xem những failover records trong hosted zone

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id Z0123456789EXAMPLE \
  --query "ResourceRecordSets[?Name=='app.example.com.'].[Name,Type,SetIdentifier,Failover,TTL,HealthCheckId,AliasTarget.DNSName,AliasTarget.EvaluateTargetHealth]" \
  --output table
~~~

Đối chiếu:

- Cùng **Name** và **Type**.
- Có một PRIMARY và một SECONDARY, `SetIdentifier` duy nhất trong bộ records.
- Đích alias hoặc non-alias đúng với Region và endpoint dự kiến.
- HealthCheckId/`EvaluateTargetHealth` được cấu hình nhất quán với thiết kế.
- Với alias, trường TTL có thể không hiện vì Route 53 lấy từ alias target.

### 9.2. Xem health check và kết quả mới nhất

~~~bash
aws route53 get-health-check \
  --health-check-id 00000000-1111-2222-3333-444444444444

aws route53 get-health-check-status \
  --health-check-id 00000000-1111-2222-3333-444444444444
~~~

`get-health-check-status` trả trạng thái theo các health checker cùng thông tin thời điểm/chi tiết được hỗ trợ; không nên xem đây là chuỗi log request hoàn chỉnh. Với alias dựa trên `EvaluateTargetHealth` của ALB mà **không tạo Route 53 health check riêng**, sẽ không có health-check ID tương ứng để gọi `get-health-check-status`.

### 9.3. Kiểm tra Route 53 sẽ trả lời gì

~~~bash
aws route53 test-dns-answer \
  --hosted-zone-id Z0123456789EXAMPLE \
  --record-name app.example.com \
  --record-type A
~~~

Lệnh `test-dns-answer` hỗ trợ kiểm tra cách Route 53 authoritative DNS trả lời truy vấn theo cấu hình; nó **không mô phỏng** hoàn toàn resolver caching, browser DNS cache, HTTP/TLS hoặc client thật.

### 9.4. Đọc DNS như một client (có công cụ `dig`)

~~~bash
dig app.example.com A
dig app.example.com AAAA
dig +short app.example.com A
~~~

Quan sát phần **TTL còn lại** của record khi dùng đầu ra đầy đủ; nếu resolver đã cache, giá trị TTL nhìn thấy có thể **nhỏ hơn TTL cấu hình gốc**. Dùng DNS resolver được phép trong môi trường vận hành; không cần thay đổi DNS hệ thống chỉ để kiểm tra. Nếu đang làm việc trong mạng doanh nghiệp với split-horizon/private DNS, kết quả có thể khác truy vấn ngoài Internet.

### 9.5. Không lấy một câu trả lời DNS làm kết luận cuối cùng

Khi kiểm tra failover:

1. **Route 53 health status** cho thấy hệ thống đang đánh giá đích nào khỏe.
2. **Authoritative DNS answer** cho thấy Route 53 chọn record nào ở thời điểm kiểm thử.
3. **Recursive resolver answer** cho biết cache từ góc nhìn client đang trả gì.
4. **HTTP/TLS test** tới endpoint sau khi resolve mới xác nhận thực tế có phục vụ request hay không.
5. **Business metrics** xác định ứng dụng có xử lý giao dịch thành công hay chỉ trả 200 từ health endpoint.

## 10. Quan sát và cảnh báo failover

Một kế hoạch theo dõi nên có **cả tín hiệu health** và **tín hiệu nghiệp vụ**:

| Lớp | Điều cần theo dõi | Vì sao |
| --- | --- | --- |
| **Route 53 health checks** | Trạng thái healthy/unhealthy và thay đổi theo thời gian | Biết khi nào điều kiện DNS failover được kích hoạt |
| **CloudWatch alarms** | Health check status, tỷ lệ lỗi, độ trễ, alarm thiếu dữ liệu | Cảnh báo đội vận hành khi trạng thái bất thường |
| **ALB** | HealthyHostCount, HTTP 5xx, TargetResponseTime, target health | Phân biệt lỗi target với lỗi toàn Region |
| **Ứng dụng** | Request rate, p95/p99 latency, checkout success, retry và reconnect | Đánh giá tác động lên người dùng |
| **Cơ sở dữ liệu** | Replication lag, DB connections, failover events, lỗi ghi | Xác định secondary có thể xử lý giao dịch hay không |
| **DNS queries** | Mô hình query logs nếu đã cấu hình, resolver behavior | Xem xu hướng tra cứu, không coi là đầy đủ mọi lần client dùng cache |
| **Chi phí** | Hosted zones, DNS queries, health check types, alarm/logging, hạ tầng secondary | Dự toán DR tổng thể |

Một số CloudWatch metrics của health check Route 53 xuất hiện trong một Region dành cho metrics của tính năng tương ứng; kiểm tra tài liệu và Region dashboard trước khi kết luận không có số liệu. Nếu dùng private endpoint health check, metric/alarm có thể thuộc Region của nguồn kiểm tra.

**Không dựa hoàn toàn vào DNS query logs để đếm người dùng.** Cùng một DNS answer có thể được cache và phục vụ nhiều kết nối mà không sinh thêm authoritative DNS query.

## 11. Chi phí và đánh đổi thiết kế

| Quyết định | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| TTL ngắn trên non-alias failover record | Resolver được hỏi lại thường xuyên hơn, có cơ hội cập nhật failover sớm | Tăng số authoritative DNS queries; vẫn có cache ngoài kiểm soát |
| Fast health check | Phát hiện lỗi nhanh hơn trong một số tình huống | Có thể phát sinh phí cao hơn và nhạy với lỗi chập chờn |
| Health check HTTPS/string match | Kiểm tra sâu hơn port TCP | Có chi phí và tải kiểm tra, cần cấu hình host/path/cert/WAF đúng |
| Secondary warm/hot | RTO tốt hơn, ít chờ khởi động | Compute, ALB, database, replication và giám sát phát sinh phí |
| Secondary cold/backup-only | Chi phí chạy thường trực có thể thấp | RTO dài hơn; không phù hợp với failover tự động quá nhanh |
| Giám sát cả primary và secondary | Tránh chuyển sang đích dự phòng không khỏe | Thêm health check/metrics và vận hành |
| Tự động failback | Có thể giảm thao tác thủ công | Rủi ro flapping, split-brain, dữ liệu chưa đồng bộ |

Không có một TTL hoặc failure threshold phù hợp cho mọi ứng dụng. Chọn dựa trên **RTO/SLO đã đo**, mức chịu lỗi trong thời gian cache cũ, chi phí và hành vi của client thực tế.

## 12. Sự cố thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| Route 53 vẫn trả primary dù app đang lỗi | Health check đang kiểm tra nhầm hostname, hoặc chỉ kiểm TCP, hoặc ALB health chưa phản ánh lỗi DB | Endpoint/check type, state, dependencies, alias target health |
| Health check báo unhealthy nhưng browser vẫn vào được | Health checker bị WAF/SG chặn, Host/SNI/path khác client, status không thuộc 2xx/3xx | Logs của endpoint, whitelist nguồn kiểm tra phù hợp, request cấu hình |
| Primary đã unhealthy nhưng một số client vẫn tới primary | Recursive/application DNS cache còn hiệu lực, connection pool giữ IP cũ | TTL trả về, resolver, JVM/cache, keep-alive/retry |
| Cả primary và secondary unhealthy nhưng DNS vẫn trả primary | Quy tắc khi hai failover records đều unhealthy | Kiểm tra sức khỏe cả hai, không coi DNS trả là dấu hiệu khỏe |
| Route 53 chuyển sang secondary nhưng ứng dụng báo lỗi ghi | Secondary chưa có dữ liệu, chưa nhận vai trò ghi hoặc IAM/KMS/secret khác | RPO, replication, DB topology, endpoint/role của ứng dụng |
| Failover xong liên tục chuyển qua lại | Readiness quá nhạy, dependency chập chờn, không có quy trình failback | Phân tích health history và tiêu chí ổn định trước khi nhận tải |
| Chỉ IPv4 hoạt động sau failover | `A` và `AAAA` chưa có chiến lược tương ứng | Kiểm tra cả hai record types và kết nối IPv6 |
| Sử dụng alias ALB nhưng không thấy TTL cấu hình | Alias kế thừa TTL target | Đọc tài liệu AliasTarget và DNS answer |
| Health check hostname tự phụ thuộc record failover | Vòng lặp DNS giữa record và health checker | Dùng hostname độc lập cho từng Region |
| Bản ghi thay đổi nhưng khách chưa thấy | DNS ủy quyền sai, TTL cache hoặc CNAME chuỗi trung gian | Kiểm tra NS, authoritative answer, resolver chain |

**Cách xử lý timeout:** khi một request tới secondary bị timeout, đừng chỉ tăng timeout hoặc giảm TTL. Hãy kiểm tra DNS trả về, TCP/TLS, Security Group/NACL/WAF, ALB target, logs và trạng thái database để xác định đúng lớp lỗi.

## 13. Diễn tập failover trước production

Chuyển DNS thật có thể ảnh hưởng khách hàng. Thực hành an toàn nên dùng **sandbox/staging** hoặc tên miền kiểm thử, tạo sự cố có chủ đích trong phạm vi được phê duyệt.

### 13.1. Kịch bản thử nghiệm

1. **Chuẩn bị:** có primary và secondary riêng, health endpoints không vòng lặp DNS, dữ liệu giả và cơ chế quan sát.
2. **Ghi đường chuẩn:** truy vấn DNS từ vài resolver, đo TTL còn lại, health status và tỷ lệ request thành công tới primary.
3. **Làm primary thất bại ở staging:** thay đổi response readiness thành `503` hoặc tắt một endpoint test, không cắt Internet của môi trường thật.
4. **Theo dõi detection:** ghi thời điểm health checker nhận lỗi, Route 53 coi primary unhealthy và authoritative answer chuyển sang secondary.
5. **Kiểm tra client:** dùng client đã cache trước lỗi và client mới; so sánh khi nào mỗi bên thực sự kết nối tới secondary.
6. **Đo nghiệp vụ:** số request lỗi, thời gian phục hồi, retry, trạng thái session và độ nhất quán dữ liệu.
7. **Khôi phục primary:** kiểm tra failback theo chiến lược đã phê duyệt; không tự động bật lại ghi ở hai Region nếu chưa điều phối dữ liệu.
8. **Lập báo cáo:** đối chiếu RTO/RPO thực tế với mục tiêu, ghi vấn đề về TTL, client DNS cache và capacity.

### 13.2. Mẫu bảng đo

| Mốc | Thời điểm giả định | Cần ghi nhận |
| --- | --- | --- |
| Primary bắt đầu không sẵn sàng | `t0` | Lỗi ứng dụng/health endpoint |
| Route 53 đánh giá unhealthy | `t1` | Health status/metrics |
| Authoritative DNS trả secondary | `t2` | `test-dns-answer` hoặc truy vấn authoritative |
| Resolver A hết cache primary | `t3` | DNS answer và TTL từ client A |
| Client A giao dịch thành công ở secondary | `t4` | Logs, metrics, request ID |
| Dữ liệu secondary đạt trạng thái cho phép ghi | `t5` | Replication lag, quyết định vai trò |

**RTO thực tế** cần đo theo điều kiện nghiệp vụ được chấp nhận, không đơn giản bằng `t2 - t0`. Nếu secondary DNS đã được trả nhưng khách vẫn không đặt hàng được, mục tiêu khôi phục chưa đạt.

## 14. Bài tập củng cố

### Bài tập 1 — tính ảnh hưởng của cache

Một resolver lấy bản ghi primary lúc 10:00 với TTL 300 giây. Primary lỗi lúc 10:01, Route 53 chuyển câu trả lời cho truy vấn mới sang secondary lúc 10:02. Resolver tuân TTL và không refresh sớm.

**Hỏi:** khi nào resolver đó có thể bắt đầu hỏi lại và nhận secondary?

**Gợi ý:** khoảng **10:05** sau khi cache hết hạn. TTL không phải thời gian Route 53 chờ; nó là thời gian cache từ lúc resolver nhận câu trả lời.

### Bài tập 2 — chọn record health

Bạn có hai ALB ở hai Region; mỗi ALB có target groups và health check riêng. Hãy đề xuất Route 53 failover alias records, giải thích lợi ích của `EvaluateTargetHealth=true`, và trường hợp nào cần một tín hiệu readiness ngoài trạng thái ALB target.

**Gợi ý:** cặp alias `A` cùng Name/Type, SetIdentifier khác nhau, PRIMARY/SECONDARY, alias tới từng ALB, bật đánh giá sức khỏe target khi hỗ trợ. Nếu target healthy nhưng mọi giao dịch ghi thất bại do DB, cần bổ sung kiểm tra nghiệp vụ/CloudWatch alarm thay vì mặc định ALB health là toàn bộ dịch vụ.

### Bài tập 3 — cả hai đích đều unhealthy

Primary và secondary cùng có health check, cả hai bị đánh giá unhealthy. Route 53 trả record nào theo mô hình failover?

**Đáp án:** **primary**. Điều đó không phải bằng chứng primary đã hồi phục; cần cảnh báo và xử lý tình huống hết đích khỏe.

### Bài tập 4 — phân biệt ba health check

Một EC2 target bị lỗi nhưng ALB còn nhiều target khỏe. Một Region khác có ALB target healthy nhưng DB bị lỗi. Hãy chọn xem ALB target health, Route 53 endpoint health và CloudWatch alarm giúp ích ở đâu.

**Gợi ý:** ALB xử lý lỗi một target; Route 53 chỉ nên chuyển Region khi endpoint/Region không đạt readiness; CloudWatch alarm có thể đưa metric nghiệp vụ hoặc DB vào quyết định khi HTTP check không phản ánh đủ.

### Bài tập 5 — vì sao DNS không sửa được dữ liệu?

S3 Cross-Region Replication và cơ sở dữ liệu replica đang chậm vài phút. Primary lỗi, DNS chuyển sang secondary trong thời gian ngắn. Ứng dụng không tìm thấy một số đơn hàng mới.

**Gợi ý:** DNS chỉ thay đường tới endpoint; replication dữ liệu có RPO riêng. Cần chính sách chịu mất dữ liệu, cơ chế phục hồi giao dịch và quyết định có cho secondary ghi ngay không.

### Bài tập 6 — đề xuất SLO và diễn tập

Hệ thống cần RTO 5 phút sau lỗi Region, cho phép tối đa 1 phút RPO. Hãy liệt kê phép đo phải thực hiện trong staging, bao gồm health detection, DNS TTL, application cache, secondary capacity và replication lag. Đề xuất cách quyết định failover/failback an toàn khi primary chập chờn.

**Gợi ý:** đặt tiêu chí pass bằng **giao dịch thành công và dữ liệu đúng**, đo từ `t0` tới request thành công, không chỉ xem authoritative DNS đổi câu trả lời. Không mặc định đổi TTL sang 30 giây sẽ đạt RTO 5 phút nếu những yếu tố khác chưa sẵn sàng.

## 15. Ghi nhớ

Ba ý chính khi thiết kế Route 53 failover:

1. **Health check** quyết định endpoint/record được coi là khỏe dựa trên tín hiệu được cấu hình; phải chọn tín hiệu phản ánh đúng khả năng phục vụ và không tạo vòng lặp DNS.
2. **Failover DNS** trả primary khi primary khỏe, chuyển secondary khi primary unhealthy và secondary khỏe theo routing policy. Nếu **cả hai** unhealthy, vẫn có trường hợp Route 53 trả **primary**; không phải một phương án chữa mọi sự cố.
3. **TTL và client caching** quyết định một phần độ trễ mà từng người dùng quan sát. Một câu trả lời authoritative mới không tự thay đổi mọi cache và TCP connection đang tồn tại.

Để đạt mục tiêu **RTO/RPO**, hệ thống cần đồng thời có **secondary thực sự sẵn sàng**, chiến lược dữ liệu phù hợp, health signals đáng tin, retry/reconnect của client, monitor và kế hoạch diễn tập. DNS là thành phần điều phối quan trọng, nhưng **không thay thế tính sẵn sàng của ứng dụng và dữ liệu**.

### Tài liệu AWS chính thức

- [Amazon Route 53 health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/welcome-health-checks.html) — cơ chế health check, alarm và kết quả.
- [How Route 53 determines health](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-determining-health-of-endpoints.html) — request interval, checker, HTTP/TCP status và private checks.
- [Creating and updating health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-creating-values.html) — cấu hình endpoint, Host, SNI, threshold và string matching.
- [Private endpoint health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-private-endpoints.html) — health check sources trong VPC và yêu cầu mạng.
- [Active-active and active-passive failover](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-types.html) — các mô hình failover.
- [How Route 53 chooses records when health checking is configured](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — quyết định primary/secondary và trường hợp cả hai unhealthy.
- [Values specific for failover records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-values-failover.html) — Record Name, TTL, HealthCheckId và các giới hạn.
- [Values specific for failover alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-values-failover-alias.html) — alias và Evaluate Target Health.
- [Choosing between alias and non-alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html) — TTL alias và hỗ trợ với AWS resources.
- [Route 53 DNS failover configuration task list](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-how-to.html) — quy trình cấu hình từ health check đến records.
- [Amazon Route 53 pricing](https://aws.amazon.com/route53/pricing/) — hosted zones, queries, loại health check và các khoản phí liên quan.
