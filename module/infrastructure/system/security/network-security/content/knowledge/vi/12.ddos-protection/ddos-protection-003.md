# Application-layer denial of service: bảo vệ ứng dụng trước DoS/DDoS tầng 7

**Application-layer denial of service (DoS tầng ứng dụng, thường gọi là L7 DoS)** là tình huống các yêu cầu tới ứng dụng khiến năng lực phục vụ bị suy giảm nghiêm trọng hoặc không còn đáp ứng nhu cầu hợp lệ. Khi nhiều nguồn cùng tham gia tạo tải bất lợi, tình huống có thể trở thành **Distributed Denial of Service (DDoS)**. Đối thủ có thể nhắm đến HTTP/HTTPS, API, đăng nhập, tìm kiếm, truy vấn dữ liệu hoặc những thao tác nghiệp vụ tiêu tốn tài nguyên; không nhất thiết cần làm nghẽn băng thông Internet.

Trong chương **DDoS** thuộc học phần **SECURITY_NETWORK_SECURITY**, mục tiêu của bài là hiểu **vì sao một request hợp lệ về cú pháp vẫn có thể gây quá tải**, cách đo ảnh hưởng tới người dùng thật và xây dựng phòng vệ từ CDN/WAF, giới hạn tần suất, phân quyền, cache, quản lý tài nguyên backend đến giám sát và ứng phó. Đây là chủ đề liên kết trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS, xác thực kết nối và hạ tầng đám mây.

Bài tập trung vào **thiết kế, quan sát và phòng vệ**. Các ví dụ sử dụng dữ liệu giả định hoặc thao tác đọc trạng thái trong môi trường được phép, không yêu cầu tạo lưu lượng tấn công.

## 1. Phân biệt DoS, DDoS và các tầng bị ảnh hưởng

**Denial of service** là sự suy giảm tính sẵn sàng do tài nguyên hoặc khả năng xử lý bị cạn kiệt, tắc nghẽn hay không thể phục vụ yêu cầu hợp lệ. Một nguồn cũng có thể gây DoS; chữ **distributed** trong DDoS nhấn mạnh nhiều nguồn cùng đóng góp vào tình huống.

| Khía cạnh | Tấn công khối lượng hoặc tầng mạng/giao vận | DoS/DDoS tầng ứng dụng |
|---|---|---|
| Đối tượng dễ bị ảnh hưởng | Đường truyền, thiết bị mạng, bảng trạng thái, khả năng xử lý gói | Web server, worker, runtime, API, DB, cache, queue, dịch vụ xác thực |
| Đơn vị thường phân tích | bit/s, packet/s, connection setup rate, state table | request/s theo endpoint, chi phí request, thời gian xử lý, số worker, độ trễ |
| Biểu hiện | Link/đường uplink bão hòa, packet loss, thiết lập kết nối thất bại | Request timeout, API tăng 5xx/429, CPU/DB pool cạn, p95/p99 tăng |
| Nơi phòng vệ chủ yếu | Nhà mạng, DDoS scrubbing, edge filtering, network firewall | CDN/WAF, API gateway, auth, rate/concurrency limits, cache, backend resilience |
| Tính khó phân biệt | Một số gói và mẫu giao vận có thể nhận diện ở L3/L4 | Traffic có thể giống những request web/API hợp lệ về cú pháp |
| Yếu tố cần bảo vệ | Đường mạng tới hệ thống | Toàn bộ đường xử lý nghiệp vụ từ edge tới data plane |

Các loại tải **có thể chồng lấp**: một sự kiện bắt đầu như kết nối TCP/TLS quá lớn rồi chuyển thành request gây tải backend. Không nên phân loại chỉ theo tên cổng; traffic TCP/443 có thể liên quan nhiều lớp, bao gồm TLS termination, HTTP parsing và xử lý dữ liệu.

### 1.1. Tính sẵn sàng khác tính bí mật và toàn vẹn

TLS/mTLS bảo vệ nội dung và xác thực các đầu kết nối trong phạm vi cấu hình, nhưng **một phiên HTTPS được mã hóa đúng vẫn có thể tiêu thụ tài nguyên**. Firewall cho phép TCP/443 theo nghiệp vụ cũng không bảo đảm backend đủ năng lực nhận số lượng request vượt kỳ vọng.

DDoS nhằm làm giảm **availability**; một cuộc tấn công có thể không đọc hoặc thay đổi dữ liệu. Tuy nhiên hệ thống bị quá tải dễ phát sinh lỗi dây chuyền, mất telemetry hoặc ảnh hưởng các chức năng an toàn khác, nên cần quản lý cả ba trục CIA (Confidentiality, Integrity, Availability) trong thiết kế tổng thể.

## 2. Vì sao tầng ứng dụng có điểm yếu về tài nguyên?

Một HTTP request ngắn có thể gây ra nhiều công việc phía sau:

~~~text
Client
   |
   v
HTTPS/TLS termination
   |
   v
WAF / API Gateway
   |
   v
Authentication / Session lookup
   |
   v
Application worker
   |------> Cache
   |------> Database queries
   |------> Search index
   |------> Third-party service
   |------> Queue / Background task
   |
   v
Response cho client
~~~

Một yêu cầu được nhận tại edge không nhất thiết tương đương một thao tác nhỏ. Một endpoint có thể phải truy vấn DB nhiều lần, đọc dữ liệu lớn, thực hiện tính toán, gọi dịch vụ ngoài hoặc chờ một hàng đợi. Khi số request đang xử lý vượt năng lực của **tài nguyên nghẽn nhất**, độ trễ tăng trước khi lỗi xuất hiện.

### 2.1. Bất đối xứng giữa chi phí request và chi phí xử lý

Đối với người gửi, tạo một request có thể rất rẻ; đối với server, request đó có thể làm tiêu tốn CPU, bộ nhớ, DB connections hoặc thời gian chờ. Ta gọi đây là **bất đối xứng tài nguyên**.

Ví dụ nghiệp vụ:

- Trang tĩnh được cache tốt thường rẻ hơn một truy vấn tạo báo cáo tức thời.
- API tìm kiếm thiếu giới hạn độ phức tạp có thể tiêu thụ CPU/DB đáng kể.
- Endpoint đăng nhập có thể phải xác minh mật khẩu và tham gia cơ chế chống gian lận.
- Trang danh sách phân trang không giới hạn có thể gây truy vấn dữ liệu lớn.
- Một hành động tạo background job có thể dùng ít thời gian tại API nhưng tạo tải kéo dài ở worker.
- Nhiều request hợp lệ cùng chờ một dịch vụ ngoài có thể làm cạn thread pool hoặc connection pool.

Điều cần đo là **chi phí theo từng loại request**, không chỉ tổng request/s của toàn website. Một lần gọi chức năng nặng có thể cần chính sách riêng với việc lấy favicon hoặc tài nguyên tĩnh.

### 2.2. Tài nguyên có thể nghẽn ở nhiều tầng

| Tài nguyên | Triệu chứng khi cạn | Telemetry nên xem |
|---|---|---|
| CDN/edge | Tăng lỗi từ edge, cache hit biến động | Edge request rate, status code, challenge/block, origin fetch |
| TLS/reverse proxy | Kết nối chờ, handshake timeout | Active connections, handshake latency, CPU, open file descriptors |
| API gateway | Queue tăng, request bị từ chối, rate limit kích hoạt | Per-route concurrency, 429, latency, rejected count |
| Application pool | Worker bận, thread starvation, timeout | In-flight requests, event loop lag, CPU/memory, saturation |
| Database | Connection pool cạn, truy vấn chậm, lock contention | Pool wait time, active connections, slow queries, query latency |
| Cache | Cache miss tăng, backend quá tải | Hit ratio, miss rate, eviction, backend fetch |
| Message queue | Job backlog, delayed processing | Queue depth, enqueue/dequeue rate, oldest-message age |
| Dịch vụ ngoài | Timeout dây chuyền, retry storm | Downstream latency, circuit breaker, retry rate |
| Hạ tầng cloud | Autoscaling chậm, quota/chi phí tăng | Scaling events, resource quotas, error budget, billing alerts |

**Kết luận vận hành:** nếu chỉ tăng số VM ở frontend mà DB hoặc một dịch vụ phụ vẫn là nút cổ chai, hệ thống có thể tiếp tục lỗi dù năng lực edge được nâng.

## 3. Các kiểu tải L7 DoS thường được thảo luận

Phân loại dưới đây giúp phòng thủ nhận diện **bề mặt cần bảo vệ**, không phải hướng dẫn thực hiện tấn công.

### 3.1. Request flood vào HTTP/API

Nhiều request nhắm tới web/API khiến gateway và backend phải xử lý liên tục. Chúng có thể dùng phương thức GET hoặc POST bình thường và trông hợp lệ ở mức giao thức.

Tín hiệu cần xem: request rate theo route, số nguồn khác nhau, tỷ lệ 2xx/4xx/5xx, độ trễ p95/p99 và sự thay đổi của in-flight requests. Một đợt tăng traffic hợp lệ cũng có thể tạo mẫu tương tự, vì vậy cần bối cảnh.

### 3.2. Tải nhắm vào endpoint tốn tài nguyên

Một nhóm endpoint có chi phí xử lý cao (báo cáo, tìm kiếm, export, các bước xác thực hoặc thao tác dữ liệu lớn) dễ tạo nút nghẽn hơn những tài nguyên tĩnh.

**Biện pháp phù hợp:** giới hạn công việc theo user/tenant và loại request, phân trang, giới hạn độ sâu/độ phức tạp truy vấn, cache theo quyền, chuyển job nặng vào queue có quota, đặt timeout và giới hạn concurrency.

### 3.3. Tải giữ kết nối hoặc giữ tài nguyên lâu

Một số tình huống DoS dựa trên việc làm nhiều kết nối hoặc request tồn tại lâu, khiến server phải giữ socket, buffer hoặc worker. Đây có thể là kết quả của client chậm, mạng yếu, tải cao hoặc hành vi cố ý.

**Biện pháp:** timeout hợp lý cho từng giai đoạn, giới hạn kết nối và concurrency, quản lý buffer, giới hạn kích thước request/header/body, cấp tài nguyên theo chính sách. Cần phân biệt **client trên mạng chậm hợp lệ** với hành vi bất thường để tránh chặn người dùng có kết nối yếu.

### 3.4. Cache miss và tải dồn vào origin

Khi tỷ lệ cache hit giảm, phần lớn request phải tới server gốc. Điều này có thể xảy ra do nội dung biến động, cấu hình cache key không phù hợp, tham số request không được chuẩn hóa hoặc một chiến dịch nội dung hợp lệ.

**Biện pháp:** thiết kế cache key cẩn thận, cache những response công khai phù hợp, sử dụng stale content đúng chính sách, request coalescing, bảo vệ origin và quan sát miss rate theo route. Không cache nhầm dữ liệu cá nhân hoặc nội dung cần phân quyền.

### 3.5. API phức tạp, GraphQL và truy vấn nhiều tầng

API có query hoặc thao tác lồng nhau có thể dẫn đến chi phí không tuyến tính với độ dài request. Với GraphQL hoặc tương tự, có thể giới hạn **query depth, complexity, pagination và tổng workload theo danh tính**.

Một giới hạn request/s chung đôi khi không đủ khi chi phí giữa các request rất khác nhau; cần **cost-based quotas** hoặc ngân sách tài nguyên ở tầng ứng dụng.

### 3.6. Tải phân tán trên nhiều nguồn

Trong DDoS, mỗi nguồn có thể tạo lưu lượng tương đối nhỏ nhưng tổng tải lớn. Lọc theo một IP đơn lẻ có thể không giải quyết toàn bộ vấn đề. Ngược lại, nhiều user hợp lệ dùng chung NAT hoặc mạng di động có thể chia một IP: chặn IP rộng làm tổn hại người dùng vô can.

Phòng thủ cần kết hợp **identity, phiên, loại endpoint, thiết bị, nguồn mạng, tín hiệu hành vi và năng lực edge/upstream**, tránh tin một trường địa chỉ đơn lẻ.

## 4. Phân biệt sự kiện tấn công với đợt tăng truy cập hợp lệ

Một website có thể nhận tăng trưởng đột biến do chương trình bán hàng, kết quả thi, ra mắt sản phẩm, cập nhật hệ thống hoặc lỗi retry từ client. Chỉ nhìn đồ thị request/s sẽ khó kết luận.

| Câu hỏi | Traffic tăng hợp lệ có thể có | DoS/DDoS nghi vấn có thể có |
|---|---|---|
| Nguồn của sự kiện | Chiến dịch, thông báo, giờ cao điểm đã biết | Không gắn được với nhu cầu rõ ràng hoặc có chỉ báo bất thường |
| Hành vi người dùng | Có luồng duyệt trang và hoàn thành tác vụ hợp lý | Nhiều request không tiến triển hoặc chỉ tập trung điểm tốn tài nguyên |
| Auth/session | Phiên/role phù hợp với nghiệp vụ | Tỷ lệ auth thất bại hoặc profile hành vi thay đổi, tùy trường hợp |
| Endpoint | Tăng đồng đều theo hành trình người dùng | Một số endpoint chịu tải chênh lệch bất thường |
| Chỉ số backend | Tải tăng tương ứng với nhu cầu | Chi phí mỗi request hoặc retry/concurrency tăng khác thường |
| Thay đổi vận hành | Có deployment hoặc chiến dịch liên quan | Có thể xảy ra cùng deployment; cần xác minh thay vì đoán |

Không có một dòng trong bảng có thể chứng minh ý định. Một tổ chức nên ghi **mức chắc chắn**, các giả thuyết còn mở và bằng chứng từ nhiều nguồn.

### 4.1. Cách tránh tự tạo retry storm

Khi backend trả lỗi hoặc timeout, nhiều client/microservice có thể tự retry đồng thời. Nếu mọi tầng đều retry nhiều lần, tải có thể khuếch đại dù không có đối thủ.

Nên dùng **retry budget, exponential backoff có jitter, timeout nhất quán, idempotency và circuit breaker**. Khi cần từ chối tải, response thích hợp và chỉ dẫn retry có giới hạn giúp giảm nguy cơ client liên tục gửi lại ngay.

## 5. Mô hình hóa rủi ro L7 theo tài sản và hành trình người dùng

Đối với application-layer DoS, cần mô tả rõ **đối tượng cần bảo đảm sẵn sàng** và **điều kiện mà đối thủ có thể gây tải**.

| Thành phần | Câu hỏi threat modeling | Ví dụ |
|---|---|---|
| Tài sản | Chức năng nào cần duy trì trong sự cố? | Login, thanh toán, tra cứu đơn hàng |
| Đối thủ | Có thể gửi request từ đâu, có danh tính không? | Nguồn Internet không auth; tài khoản API có quota thấp |
| Bề mặt | Những endpoint nào thực sự reachable? | Public API, CDN origin, cổng admin bị lộ |
| Chi phí | Mỗi request tốn CPU/DB/queue bao nhiêu? | Report đồng bộ chiếm DB connection |
| Ranh giới | Edge, API gateway, auth và DB chặn ở đâu? | WAF tại edge, quota theo tenant ở API |
| Điều kiện | Cần login, captcha hay token? Có thể tránh chỗ nào? | Một số endpoint public cần cho người dùng mới |
| Tác động | Availability SLO nào bị ảnh hưởng? | Người dùng hợp lệ không hoàn tất checkout |
| Quan sát | Dữ liệu nào chứng minh mức độ, nguồn và hành động? | CDN logs, APM, DB metrics, WAF decisions |
| Phản ứng | Ai có quyền bật mitigation, rollback và thông báo? | SRE/on-call cùng Security Operations |

**Năng lực đối thủ phải được giới hạn theo bằng chứng:** việc gửi được request không có nghĩa đối thủ có quyền truy cập tài khoản; việc truy cập được port 443 không có nghĩa họ đọc được HTTPS của người khác. Ngược lại, một kẻ đã có token hợp lệ có thể gây tải trên những endpoint mà token ấy được cấp.

### 5.1. Phân biệt north-south và east-west

- **North-south:** lưu lượng Internet → CDN/WAF → ứng dụng; khả năng chống tải phụ thuộc cả ISP, CDN, load balancer và origin.
- **East-west:** service → service và workload → DB/cache/queue; có thể xảy ra overload hoặc retry storm bên trong, không đi qua WAF Internet.
- **Control plane:** IAM, API quản trị, hệ thống cấu hình rate limit và cloud autoscaling; một thay đổi policy trái phép có thể làm mất tác dụng phòng vệ.

Chỉ triển khai WAF biên không đủ nếu có đường truy cập trực tiếp tới origin hoặc dịch vụ nội bộ không được giới hạn.

## 6. Kiến trúc phòng vệ L7 nhiều lớp

~~~mermaid
flowchart TD
    C[Người dùng và client Internet] --> U[Upstream chống DDoS mạng]
    U --> CDN[CDN / Edge cache]
    CDN --> WAF[WAF / Bot management]
    WAF --> GW[API Gateway / Auth / Rate limits]
    GW --> LB[Load balancer]
    LB --> APP[Application workers]
    APP --> CACHE[Cache]
    APP --> DB[(Database)]
    APP --> Q[Queue / Background workers]
    APP --> EXT[Downstream service]
    CDN -.Telemetry.-> OBS[Logs / Metrics / Tracing / SIEM]
    WAF -.Policy decisions.-> OBS
    GW -.Request outcomes.-> OBS
    APP -.Saturation / SLO.-> OBS
    DB -.Pool / query latency.-> OBS
~~~

**Điểm thiết kế:** mỗi lớp giải quyết một ràng buộc cụ thể.

| Lớp | Chức năng | Giới hạn cần biết |
|---|---|---|
| Upstream / ISP / scrubbing | Giảm nghẽn đường truyền và lưu lượng mạng lớn | Không phân biệt đầy đủ mọi thao tác ứng dụng |
| CDN | Phục vụ nội dung cache gần người dùng; hấp thụ nhiều request phổ biến | Nội dung cá nhân, API động và cache miss vẫn tới origin |
| WAF / bot management | Quy tắc HTTP và dấu hiệu hành vi, kiểm tra/challenge khi phù hợp | False positive, bot tinh vi, API không dùng trình duyệt |
| API gateway | Quota theo client/tenant/route, auth và giới hạn request | Không tự giảm chi phí backend nếu quota quá cao |
| Load balancer | Phân phối request tới backend khỏe mạnh | Không làm tăng năng lực DB, cache hoặc dịch vụ ngoài |
| Application | Giới hạn concurrency, input, workload và retry | Cần tối ưu logic nghiệp vụ và resource budgeting |
| Database/cache/queue | Cô lập pool, quota truy vấn, caching và backpressure | Một shared backend vẫn có thể là nút cổ chai |
| Observability/SOC | Phát hiện, xác minh, đánh giá mitigation | Thiếu dữ liệu nếu log/metrics pipeline bị quá tải |

**Nguyên tắc quan trọng:** các lớp phải đặt trên **đường đi bắt buộc**. Nếu tên DNS trỏ qua CDN nhưng origin vẫn nhận kết nối trực tiếp từ Internet ngoài các nguồn CDN được cấp quyền, một số chính sách edge có thể bị bỏ qua. Khi giới hạn origin theo nguồn, cần dùng cơ chế nhận dạng kết nối CDN phù hợp và quản lý thay đổi địa chỉ của nhà cung cấp.

## 7. Đo availability và nhận diện suy giảm dịch vụ

L7 DoS nên được đánh giá theo **trải nghiệm của user hợp lệ**, không chỉ theo số request nghi vấn.

### 7.1. Các nhóm chỉ số

| Nhóm | Chỉ số | Mục đích |
|---|---|---|
| Mức tải | Request/s theo route, tenant, client type | Biết tăng trưởng xảy ra ở đâu |
| Độ trễ | p50, p95, p99 theo endpoint và thành phần | Phát hiện request bị chậm |
| Chất lượng | Success rate, 5xx, timeout, 429, các business outcome | Đánh giá khả năng hoàn thành tác vụ |
| Saturation | In-flight requests, worker busy, queue depth, CPU, DB pool wait | Tìm tài nguyên nghẽn |
| Cache | Hit ratio, miss rate, origin fetch | Nhận biết tải dồn vào backend |
| Edge enforcement | Allow/challenge/block/rate-limited counts | Đánh giá chính sách và tác động ngoài ý muốn |
| Khả dụng | SLI/SLO, synthetic transactions từ vị trí được kiểm soát | Đánh giá người dùng thật có sử dụng được không |
| An toàn vận hành | Telemetry loss, collector lag, log sampling | Xác định độ tin cậy của kết luận |

**p95/p99** cần tính theo đúng khoảng thời gian, tập request và nhóm endpoint. Có thể p50 bình thường nhưng p99 tăng mạnh khi một số request chờ DB lock hoặc pool.

### 7.2. Request rate không đồng nghĩa offered load

Một biểu thức trực giác:

\[
\text{Tải công việc} \approx \sum_{i=1}^{n} \text{số request loại }i \times \text{chi phí xử lý loại }i
\]

Đây là mô hình khái niệm, không phải công thức tính công suất chính xác cho mọi hệ thống. **Chi phí** có thể đo bằng CPU time, database query cost, memory, thời gian giữ worker hay tổng tải downstream. Hai endpoint có cùng request/s nhưng tài nguyên dùng khác nhau.

Các thành phần hàng đợi có mối liên hệ giữa tốc độ đến, thời gian xử lý và số request đang xử lý (ví dụ định luật Little trong điều kiện hệ ổn định). Khi hệ thống vượt khả năng phục vụ bền vững, queue sẽ tăng và độ trễ có thể tăng rất nhanh.

### 7.3. SLI và SLO

- **SLI (Service Level Indicator):** phép đo như tỷ lệ checkout thành công hoặc request hợp lệ dưới ngưỡng latency.
- **SLO (Service Level Objective):** mục tiêu đối với SLI trong khoảng thời gian xác định.
- **Error budget:** phần sai lệch được chấp nhận so với mục tiêu, giúp ưu tiên ứng phó và thay đổi.

Ví dụ chính sách: mục tiêu chức năng checkout hoàn thành đủ nhanh với tỷ lệ kỳ vọng do nhóm sản phẩm/SRE xác định. Trong sự cố, đội phòng thủ ưu tiên duy trì hành trình checkout thay vì mọi endpoint phụ như báo cáo phân tích.

Không đưa ra một con số SLO chung cho mọi ứng dụng; ngân hàng, game, cổng thông tin và trang nội dung có mức độ chịu lỗi khác nhau.

## 8. Rate limiting và quota: khống chế lượng việc được nhận

**Rate limiting** giới hạn tần suất request hoặc tài nguyên tiêu thụ theo một khóa định danh, tuyến hoặc chính sách. Đây là một lớp phòng vệ quan trọng nhưng cần thiết kế đúng để tránh chặn lưu lượng hợp lệ.

### 8.1. Các phương pháp phổ biến

| Phương pháp | Cách tư duy | Ưu điểm | Điều cần thận trọng |
|---|---|---|---|
| Fixed window | Đếm request trong từng khoảng thời gian | Đơn giản | Có thể tạo burst ở ranh giới hai cửa sổ |
| Sliding window | Theo dõi tập request trong khoảng trượt | Phản ánh tải mượt hơn | Chi phí lưu trạng thái và độ chính xác |
| Token bucket | Token được bổ sung theo tốc độ, request tiêu token | Cho phép burst hữu hạn có kiểm soát | Bucket size/rate phải dựa vào năng lực backend |
| Leaky bucket / queue | Điều hòa tốc độ xử lý theo nhịp | Làm mượt tải | Queue quá dài vẫn làm người dùng chờ và dùng bộ nhớ |
| Concurrency limit | Giới hạn số request đang xử lý cùng lúc | Trực tiếp bảo vệ worker/pool | Cần timeout và cơ chế từ chối khi bão hòa |
| Cost-based quota | Request tiêu ngân sách theo chi phí ước tính | Hữu ích cho API nặng/GraphQL/report | Cần đo và cập nhật cost model |

### 8.2. Token bucket bằng ví dụ khái niệm

Giả sử policy tạo token theo tốc độ đã cấu hình và một request tiêu một token. Bucket có dung lượng hữu hạn cho phép một đợt truy cập ngắn, còn về dài hạn mức request được chấp nhận chịu giới hạn theo tốc độ bổ sung token.

~~~text
Bucket còn token?
    |
    +-- Có --> Trừ token --> Request được tiếp tục theo các rule khác
    |
    +-- Không --> Trả 429 / xếp hàng ngắn / challenge / quyết định khác
~~~

Tùy ứng dụng, việc **xếp hàng** có thể tăng độ trễ và bộ nhớ; khi queue dài, từ chối sớm đôi khi bảo vệ availability tốt hơn. Policy cần phân biệt **được phép vào tầng tiếp theo** với **ứng dụng hoàn tất request**.

### 8.3. Chọn khóa giới hạn (rate-limit key)

Không nên dùng duy nhất IP nguồn cho mọi trường hợp:

- Người dùng đi qua **carrier-grade NAT**, proxy công ty hoặc Wi-Fi đông có thể dùng chung một public IP.
- IPv6 có nhiều địa chỉ cho cùng một thiết bị; cần lựa chọn prefix hoặc identity phù hợp với quyền riêng tư và chuẩn vận hành.
- Nguồn phân tán có thể gửi ít request trên mỗi IP nhưng tổng tải lớn.
- Account/token có thể bị chia sẻ hoặc bị lộ; quota theo account cần kết hợp phát hiện lạm dụng.
- Gateway đặt sau CDN có thể nhìn thấy **IP của proxy** thay vì IP client nếu không cấu hình tin cậy đúng.

Khóa thường cần phối hợp: **user/tenant/API key đã xác thực + endpoint/operation + quyền và resource budget**, bổ sung network signals khi thích hợp. Header chứa IP client chỉ được tin nếu do proxy được tin cậy thiết lập và chuỗi proxy được cấu hình đúng; không tin trực tiếp giá trị header do client tùy ý gửi.

### 8.4. Rate limiting theo route và độ nhạy

Ví dụ ma trận **khái niệm**, chưa phải cấu hình của vendor:

| Nhóm endpoint | Đặc tính tải | Cơ chế chính |
|---|---|---|
| Nội dung tĩnh công khai | Cache được, chi phí origin thấp | CDN cache, policy chống burst ở edge |
| API đọc nhẹ | Nhiều request hợp lệ | Quota theo client/tenant + concurrency có giới hạn |
| Tìm kiếm nâng cao | Chi phí biến động | Cost budget, giới hạn độ phức tạp và trang |
| Đăng nhập/quên mật khẩu | Nhạy cảm với lạm dụng và người dùng thật | Quota theo account/network signals, bảo vệ xác thực, anti-automation phù hợp |
| Export/báo cáo | Chi phí DB/CPU lớn | Async job, quota theo user/tenant, hàng đợi và thời hạn |
| API nội bộ | Danh tính workload, SLO phụ thuộc downstream | Service-level quota, mTLS, circuit breaker |
| Health check | Phải ổn định khi sự cố | Policy riêng, nguồn/identity đáng tin, không bỏ toàn bộ bảo vệ |

Một con số request/s áp dụng đồng loạt có thể vừa **quá chặt** với API nhẹ, vừa **quá lỏng** với một thao tác tốn tài nguyên.

### 8.5. Phản hồi khi giới hạn

Một ứng dụng HTTP có thể dùng **429 Too Many Requests** khi giới hạn theo chính sách; **503 Service Unavailable** có thể phù hợp với tình trạng tạm thời không còn năng lực. Có thể kèm **Retry-After** khi biết thời gian phù hợp, nhưng không bảo đảm mọi client sẽ tuân thủ.

Không tạo hệ thống retry vô hạn chỉ vì server trả 429/503. Clients cần backoff, jitter và retry budget. Một số nghiệp vụ (ví dụ thanh toán) cần **idempotency key** để tránh thực thi nhiều lần khi client thử lại sau timeout.

## 9. WAF và bot management

**Web Application Firewall (WAF)** có thể kiểm tra thuộc tính HTTP, loại request, một số pattern khai thác, reputation, hành vi và chính sách ứng dụng. Tùy nhà cung cấp, WAF kết hợp rate limiting, bot classification hoặc challenge.

### 9.1. Các hành động có thể dùng

- **Observe/log only:** thu thập tín hiệu trước khi siết rule, phù hợp giai đoạn học baseline.
- **Rate limit:** giảm tốc độ của nhóm request có điều kiện.
- **Challenge:** kiểm tra khả năng tương tác theo cơ chế nhà cung cấp, cần cân nhắc tác động tới người dùng.
- **Block/deny:** từ chối request khớp tín hiệu đủ tin cậy.
- **Route/tier:** chuyển một số request sang đường xử lý có quota thấp hơn hoặc giữ nội dung tĩnh.
- **Allowlist có kiểm soát:** dành cho các dịch vụ giám sát và tích hợp được xác minh, có hạn phạm vi.

**WAF không luôn đọc được traffic sau khi request đã rời điểm kết thúc TLS**, và WAF ở Internet không kiểm soát mặc nhiên API nội bộ hay traffic east-west không đi qua nó.

### 9.2. Tránh gây hại cho người dùng hợp lệ

Các thử thách trình duyệt/captcha có thể làm hỏng **mobile app, API client, accessibility và thiết bị không tương tác**. Hệ thống cần luồng riêng cho client được cấp danh tính, API key, mTLS hoặc token theo chính sách. Một IP công cộng đại diện nhiều người dùng có thể gây false positive khi giới hạn quá chặt.

Nên thử nghiệm rule bằng **telemetry thật và traffic đã được cấp phép**, có công tắc rollback, nhóm owner và theo dõi tỷ lệ hoàn thành nghiệp vụ của người dùng hợp lệ.

### 9.3. WAF signature khác chống quá tải

Một rule WAF phát hiện payload khai thác đã biết không đồng nghĩa bảo vệ khỏi request flood hợp lệ về cú pháp. Ngược lại, quota và concurrency controls có thể giảm tải L7 dù không phát hiện một exploit cụ thể. Phải kết hợp **lọc theo rủi ro request** và **quản lý ngân sách tài nguyên backend**.

## 10. CDN, caching và bảo vệ origin

CDN giúp phục vụ nội dung có thể cache ở edge, giảm số request tới hệ thống gốc. Với ứng dụng có nhiều nội dung công khai, đây là lớp phòng vệ quan trọng trước đợt tăng tải.

### 10.1. Những câu hỏi cần giải quyết khi cache

- Response có công khai không? Có chứa dữ liệu theo user, token, giỏ hàng hay phiên?
- Cache key dựa vào path, query, header và cookie nào là cần thiết?
- Thời hạn cache có phù hợp với tính chính xác của dữ liệu không?
- Khi backend lỗi, có thể phục vụ nội dung cũ theo chính sách (stale) không?
- Có cơ chế request coalescing để tránh nhiều miss đồng thời cùng một object không?
- Origin có bị truy cập trực tiếp ngoài CDN không?
- Có thể nhận biết cache hit/miss theo route và cảnh báo khi miss rate tăng không?

**Không cache nhầm dữ liệu cá nhân giữa nhiều user.** Một rule cache sai có thể gây lộ dữ liệu, làm ảnh hưởng tính bí mật dù availability được cải thiện.

### 10.2. Bảo vệ origin

Một sơ đồ mong muốn:

~~~text
Client Internet --> CDN/WAF --> Origin
                           [Chỉ đường được cấp quyền từ edge tới origin]
Client Internet ----X------> Origin trực tiếp (nếu không cần)
~~~

Điểm **X** là mục tiêu chính sách, cần được thực thi bằng nguồn edge đáng tin, kết nối được xác thực hoặc private origin integration phù hợp. Khi nhà cung cấp CDN có thay đổi dải IP, rule origin phải được cập nhật có kiểm soát. Chỉ ẩn hostname/IP origin trong tài liệu không đủ thay thế ACL/firewall.

### 10.3. Không phải mọi API đều cache được

Các endpoint đặt hàng, tài khoản, thanh toán, dữ liệu thời gian thực hoặc response phân quyền thường cần xử lý tại origin. Với chúng, **rate limit, authentication, idempotency, circuit breaker, queue và cost controls** có thể quan trọng hơn cache.

## 11. Bảo vệ tài nguyên backend và ngăn sự cố dây chuyền

Khi traffic đi qua edge, hệ thống vẫn cần tự bảo vệ nếu tải vượt khả năng.

### 11.1. Bounded concurrency

Giới hạn số request/job đồng thời cho từng loại công việc, đặc biệt tại DB connection pool, search service và các endpoint nặng. Nếu đạt giới hạn, áp dụng **queue ngắn, từ chối sớm hoặc giảm chất lượng có kiểm soát**. Queue không giới hạn chỉ chuyển vấn đề từ CPU sang bộ nhớ và độ trễ.

### 11.2. Timeout, circuit breaker và retry budget

- **Timeout:** không giữ worker mãi để chờ dependency không phản hồi.
- **Circuit breaker:** tạm ngừng gọi dependency liên tục thất bại, tùy logic ứng dụng.
- **Retry budget:** hạn chế số lần thử lại ở mọi tầng để tránh khuếch đại.
- **Jitter:** phân tán thời điểm retry giữa các client.
- **Deadline propagation:** chuyển giới hạn thời gian của một request qua các lời gọi downstream.
- **Bulkhead:** tách pool tài nguyên của những chức năng khác nhau để sự cố tại một nhóm không chiếm hết năng lực của nhóm khác.

Ví dụ, nếu chức năng báo cáo đang bão hòa, **bulkhead** giúp giữ worker cho trang đăng nhập và thanh toán. Điều này thể hiện **ưu tiên tính sẵn sàng của nghiệp vụ quan trọng**, không chỉ giữ tổng CPU dưới ngưỡng.

### 11.3. Async job và phân bổ công việc

Đối với export, xử lý hình ảnh, báo cáo lớn hoặc tác vụ lâu, thay vì giữ một HTTP request chờ toàn bộ kết quả, ứng dụng có thể gửi job vào queue và trả ID để theo dõi trạng thái.

Nhưng queue cũng cần **quota theo user/tenant, giới hạn số job đang chờ, tuổi tối đa, idempotency và cơ chế hủy**. Nếu cho enqueue vô hạn, tải vẫn tích tụ và gây mất availability của worker hoặc kho lưu trữ.

### 11.4. Database và dịch vụ dữ liệu

- Giới hạn connection pool và thời gian chờ truy vấn theo nghiệp vụ.
- Theo dõi slow queries, lock contention, read/write hotspots.
- Đặt pagination và giới hạn số lượng bản ghi hợp lý.
- Cân nhắc precomputation, index phù hợp, cache và read replicas khi đúng nhu cầu.
- Phân quyền truy cập DB và nhóm workload để một backend không chiếm toàn bộ tài nguyên.
- Quan sát **query cost per route**, không chỉ request/s tại frontend.

Giải pháp mở rộng ngang application không tự khắc phục bottleneck tại DB. Autoscaling cần được đặt trong mô hình giới hạn công suất của toàn bộ chuỗi.

## 12. Kết hợp DDoS protection ở L3/L4 với bảo vệ L7

Một sự kiện L7 DDoS có thể đồng thời gây nhiều kết nối, TLS handshake hoặc nghẽn mạng. Nếu uplink đã bão hòa, WAF đặt sau uplink không nhận đủ packet để đưa ra quyết định; cần sự hỗ trợ của **ISP, CDN hoặc dịch vụ chống DDoS upstream**.

| Triệu chứng ưu thế | Điểm phòng thủ gần nguồn nghẽn | Các lớp tiếp theo |
|---|---|---|
| Đường truyền sắp bão hòa | ISP/upstream, scrubbing, CDN ingress | Firewall/edge sau khi traffic đã được giảm |
| SYN/connection saturation | Hạ tầng chống DDoS L3/L4 và quản lý kết nối | TLS termination, WAF |
| Nhiều HTTPS request hợp lệ về cú pháp | CDN/WAF, bot management, request quota | API gateway, app concurrency |
| DB chịu tải quá lớn | Cost/quota tại app, cache, queue, DB pool | Query optimization, autoscaling có giới hạn |
| DNS authoritative bị quá tải | DNS provider có năng lực phân tán/anycast và rate protection | Health checks, authoritative DNS architecture |
| Retry storm nội bộ | Client retry controls, circuit breaker, service quotas | Bulkhead, admission control, telemetry |

**Mỗi lớp có độ trễ phản ứng và trách nhiệm riêng.** Nhà mạng xử lý nghẽn upstream; nhóm bảo mật điều chỉnh edge/WAF; nhóm ứng dụng chịu trách nhiệm giới hạn chi phí endpoint; SRE đảm bảo SLO và vận hành khôi phục.

### 12.1. IP allowlist và rủi ro mở đường vòng

Chính sách chỉ tin một số dải IP có thể hữu ích cho origin/CDN hoặc dịch vụ private, nhưng không nên tin một header HTTP do client tự đặt để xác nhận nguồn. Quy tắc ở origin cần dựa trên kết nối đến từ proxy đáng tin theo hạ tầng thực tế và nên có **xác thực giữa các thành phần** khi phù hợp.

Trong môi trường cloud/Kubernetes, kiểm tra cả public LB, private LB, ingress, NodePort, security group, network ACL, host firewall, service mesh và các đường peering có thể bỏ qua edge.

## 13. Bảo vệ các endpoint nhạy cảm

### 13.1. Đăng nhập, OTP và khôi phục tài khoản

Những endpoint này có chi phí xử lý và yêu cầu bảo mật riêng. Một số vấn đề cần kết hợp:

- Chống thử mật khẩu liên tục, credential stuffing và lạm dụng OTP theo danh tính/account.
- Rate limit phù hợp theo account, thiết bị, tenant và tín hiệu mạng; tránh tạo khả năng gây khóa tài khoản hàng loạt cho người khác.
- Bảo vệ khả năng truy cập của người dùng thật khi hệ thống đang chịu tải.
- Thực thi MFA và authorization độc lập với rate limiting.
- Bảo vệ credential và không ghi mật khẩu/token vào access log.

**Lưu ý:** việc trả 429 liên tiếp tới user thật có thể trở thành một dạng denial of service do chính phòng vệ gây ra. Chính sách cần đánh giá tác động theo nhóm người dùng và độ tin cậy của tín hiệu bot.

### 13.2. API công khai và API theo khách hàng

Có thể phân chia **quota theo plan/tenant/client identity**, tách đọc và ghi, đồng thời giới hạn số kết nối hoặc in-flight requests. Một tenant gây tải cao không nên làm cạn tài nguyên của các tenant khác; đây là bài toán **fairness và noisy-neighbor isolation**.

Nếu token bị lộ, hệ thống cần có cơ chế thu hồi, đổi khóa, cảnh báo bất thường và giới hạn quyền. API key không chỉ là bộ đếm quota mà còn là thông tin nhạy cảm cần được bảo vệ.

### 13.3. GraphQL và tìm kiếm

Thay vì chỉ đếm request, có thể sử dụng **depth/complexity limits**, pagination, query cost và thời hạn xử lý. Cần đánh giá câu truy vấn hợp lệ có chi phí cao và chọn cách giảm tải phù hợp, tránh làm hỏng chức năng tìm kiếm thiết yếu.

### 13.4. Webhook và API của bên thứ ba

Webhook thường do dịch vụ ngoài gọi và có thể dùng chung IP hoặc thay đổi nguồn. Nên xác thực chữ ký/request theo cơ chế đối tác, giới hạn payload và concurrency, idempotency và có queue xử lý. IP allowlist chỉ nên là lớp bổ sung khi nguồn IP được đối tác quản lý rõ ràng.

Các tích hợp hợp lệ có thể retry khi nhận lỗi; ứng dụng cần phản hồi và cơ chế xử lý lại phù hợp để không tự tạo một cơn bão yêu cầu.

## 14. Giám sát, phát hiện và phân loại cảnh báo L7

Một hệ thống phát hiện tốt kết hợp **edge log + access log + APM + backend metrics + firewall/IDS/IPS + DNS + cloud audit**.

### 14.1. Những tín hiệu có thể tương quan

| Tín hiệu | Ý nghĩa tiềm năng | Cần xác minh thêm |
|---|---|---|
| RPS tăng mạnh ở một route | Đợt truy cập cao hoặc tập trung bất thường | Campaign, asset owner, traffic source, SLO |
| p99 tăng và worker saturation | Nút nghẽn trong chuỗi xử lý | CPU, DB pool, queue, downstream |
| WAF challenge/block tăng | Edge đang thực thi phòng vệ | Tỷ lệ client thật bị ảnh hưởng, rule version |
| 429 tăng | Quota/rate limit đang tác động | Rate-limit key, bot signals, hành trình hợp lệ |
| 503 tăng | Tải quá công suất hoặc dependency lỗi | Health check, LB, app/DB metrics |
| Cache hit giảm đột ngột | Tải tới origin tăng | Deployment, cache key, TTL, request mix |
| Retry count tăng | Có thể hình thành amplification nội bộ | Client behavior, backoff, timeout |
| Nhiều nguồn IP, ít request mỗi nguồn | Phân tán hoặc tăng trưởng user hợp lệ | Identity, geography, network diversity, behavior |
| Flow L3/L4 không tăng nhiều nhưng latency cao | Bottleneck tính toán hoặc lock/DB | APM traces, slow queries, job queue |

### 14.2. Thí dụ log tổng hợp giả định

~~~json
{
  "timestamp": "2026-11-28T05:00:00Z",
  "service": "order-api",
  "route": "/api/orders/search",
  "edge_request_count": 2400,
  "origin_request_count": 1850,
  "cache_hit_ratio": 0.23,
  "p95_latency_ms": 2100,
  "response_429_count": 410,
  "response_5xx_count": 175,
  "db_pool_utilization_ratio": 0.96,
  "classification": "needs-investigation"
}
~~~

Đây là **ví dụ minh họa** và các số đo chưa có baseline hoặc ngưỡng SLO, nên chưa kết luận rằng tấn công đang diễn ra. Tuy nhiên kết hợp request tăng, cache hit thấp, p95 cao, DB pool gần đầy và nhiều lỗi là tín hiệu đáng ưu tiên điều tra.

### 14.3. Những nguyên tắc giảm false positive

1. So sánh theo **route, tenant, loại client và giờ/ngày**; không lấy một ngưỡng từ toàn website.
2. Xem **thay đổi mới triển khai**, marketing campaign và lịch batch.
3. Tách request do **health check, monitoring hoặc crawler được phê duyệt**.
4. Kiểm tra hệ quả trên **người dùng thật** bằng synthetic transaction và business outcome.
5. Xác minh dữ liệu log có sampling/aggregation và thiết bị/collector có đang mất log.
6. Khi ghi kết luận, tách **đã xác minh**, **giả thuyết**, **chưa biết**.

NIDS/IPS có thể hỗ trợ phát hiện hành vi traffic bất thường, nhưng **L7 DoS qua HTTPS hợp lệ và đã mã hóa** có thể không có chữ ký nội dung rõ ràng. APM, WAF và backend metrics thường cần thiết để xác định chi phí thật.

## 15. Runbook ứng phó sự cố Application-layer DDoS

Một runbook hữu ích chỉ định trách nhiệm, cách ra quyết định và tiêu chí để đảo ngược mitigation. Trình tự dưới đây áp dụng cho các hệ thống do tổ chức quản lý hoặc được cấp quyền.

### Giai đoạn A — Trước sự cố

1. **Định nghĩa SLO và hành trình quan trọng:** login, checkout, tra cứu trạng thái, API của khách hàng.
2. **Lập sơ đồ đường mạng:** ISP, DNS, CDN, WAF, LB, origin, DB, cache, queue và các đường bypass.
3. **Xác định điểm nghẽn:** peak capacity, scaling lead time, DB pool, expensive endpoints.
4. **Chuẩn bị telemetry:** có dashboard latency, errors, RPS, 429, pool, cache miss, WAF decisions và business outcomes.
5. **Chuẩn bị policy:** rate-limit templates, emergency controls, trusted clients và phương án giảm tính năng phụ.
6. **Xác nhận liên hệ:** on-call SRE, Security Operations, CDN/DDoS provider, ứng dụng, DB, truyền thông/CSKH.
7. **Tập diễn tập:** dùng kiểm thử năng lực đã được phê duyệt trong staging hoặc môi trường lab, không tạo tải chưa kiểm soát trên production.

### Giai đoạn B — Phát hiện và phân loại

1. Xác minh người dùng thật có lỗi hay chỉ một dashboard bất thường.
2. Xác định **đường bị nghẽn**: network, edge, TLS, gateway, app, DB, cache, queue hay downstream.
3. Thu mẫu log/metrics đủ theo thời gian; ghi thay đổi gần nhất và mức độ chắc chắn của nhận định.
4. Phân biệt **tăng tải hợp lệ, deployment regression, retry storm, sự cố provider và DoS nghi vấn**.
5. Ước lượng mức ảnh hưởng theo SLO, nhóm người dùng, vùng địa lý và tài sản trọng yếu.

### Giai đoạn C — Giảm tác động

Các phương án nên được lựa chọn theo **điểm nghẽn đã xác minh**:

- **Nghẽn đường Internet:** liên hệ upstream/CDN/DDoS provider; policy tại origin thường quá muộn nếu uplink đã đầy.
- **Tải edge:** điều chỉnh WAF/rate limit có mục tiêu, tránh chặn rộng theo IP nếu traffic CGNAT.
- **Cache miss lớn:** kiểm tra cache key, TTL, stale policy, origin shielding và tính hợp lệ của nội dung cache.
- **Backend quá tải:** concurrency caps, request shedding, timeout, circuit breaker, tạm giảm tính năng không thiết yếu.
- **DB bão hòa:** hạn chế query tốn tài nguyên, bật/điều chỉnh queue, giảm parallelism và mở rộng có cân nhắc khả năng data tier.
- **Retry storm:** giảm retry, dùng backoff/jitter và hạn chế luồng từ các service gây khuếch đại.

**Không bật toàn bộ cơ chế một cách mù quáng.** Nhiều thay đổi đồng thời khiến khó biết biện pháp nào hiệu quả, dễ làm hỏng hành trình nghiệp vụ và tạo áp lực lên service phụ. Ghi rule version, thời điểm, phạm vi và người duyệt.

### Giai đoạn D — Xác minh giảm tác động

Kiểm tra cùng lúc:

- p95/p99 latency và success rate của nhóm request quan trọng.
- Error rate/timeout/429/5xx và business completion.
- Cache hit, origin RPS, worker/DB pool saturation.
- WAF block/challenge và **false positive với user hợp lệ**.
- Tình trạng queue/backpressure và downstream.
- Việc giảm tải ở một route có chuyển nghẽn sang route khác hay không.

Một biểu đồ request/s giảm sau khi bật block **không tự chứng minh thành công** nếu user hợp lệ cũng bị chặn. Tiêu chí thành công là **khôi phục khả năng phục vụ chính đáng**.

### Giai đoạn E — Phục hồi và rút kinh nghiệm

1. Hạ mitigation khẩn cấp theo từng bước, giữ monitoring.
2. Khôi phục các tính năng tạm giảm khi resource budget cho phép.
3. Đối chiếu timeline và evidence; loại bỏ suy đoán không được xác minh.
4. Kiểm tra phát sinh chi phí cloud, autoscaling, cache và queue backlog.
5. Viết postmortem nêu nguyên nhân, nút nghẽn, phạm vi ảnh hưởng, điều tốt/xấu và action owners.
6. Cập nhật SLO, dashboard, runbook, rule, kiến trúc origin và bài test phòng thủ.

## 16. Kiểm chứng phòng vệ trong lab và production

Đánh giá availability cần phương pháp kiểm thử được quản lý. **Không tự thực hiện stress test/traffic flood lên Internet, hệ thống của bên thứ ba hoặc production** khi chưa được phê duyệt cụ thể, vì việc kiểm thử có thể gây gián đoạn thật.

### 16.1. Những phép kiểm tra không gây tải

Có thể kiểm tra một số thông tin ở endpoint **do mình quản trị** bằng request đơn lẻ:

~~~bash
# Quan sát response header của một dịch vụ localhost
curl -I --max-time 5 http://127.0.0.1:8080/

# Kiểm tra tình trạng listener tại host Linux được cấp quyền
ss -lnt

# Xem số liệu giao diện theo quyền hệ thống
ip -s link
~~~

Dịch vụ localhost ở cổng 8080 phải được bật từ trước nếu muốn nhận phản hồi. Các lệnh trên không đo được năng lực chống DDoS; chúng minh họa việc **quan sát đường xử lý** mà không tạo traffic lớn.

### 16.2. Cần kiểm tra những điều gì trong staging/lab?

- Quota theo user/tenant/route có áp đúng không?
- Khi vượt quota giả định, response và Retry-After có nhất quán với client không?
- API hợp lệ dưới ngưỡng có hoạt động và trả kết quả đúng không?
- Worker/DB/queue có bounded concurrency và timeout không?
- Các cơ chế retry/backoff có tránh tải tích lũy không?
- Hệ thống có ưu tiên hành trình chính khi chức năng phụ quá tải không?
- Edge/WAF action và ứng dụng có ghi log đủ để giải thích quyết định không?
- Client mobile/API/thiết bị hỗ trợ accessibility có vượt challenge hợp lệ không?
- Khi tắt một chính sách khẩn cấp, có rollback nhanh và kiểm chứng được không?

Trong production, việc đánh giá thường dùng **observability, canary, synthetic transactions mức thấp và thay đổi policy có kiểm soát**. Capacity test cường độ cao cần kế hoạch riêng về giới hạn tải, thời điểm, quyền thử nghiệm và người giám sát.

## 17. Ví dụ một policy phòng thủ theo vai trò

Đây là mẫu **khái niệm**, không phải cú pháp của CDN/WAF/API gateway cụ thể:

~~~yaml
policy_id: "orders-search-protection"
owner: "application-team"
purpose: "Giữ tính sẵn sàng cho API tìm kiếm đơn hàng"
scope:
  service: "order-api"
  route: "/api/orders/search"
  methods:
    - "GET"
identity:
  primary_key: "authenticated-tenant-and-user"
  fallback: "trusted-edge-client-signals"
admission:
  strategy: "cost-and-concurrency-budget"
  max_query_complexity: "calibrated-from-staging"
  burst_policy: "bounded"
failure_behavior:
  when_over_budget: "respond-429-or-degrade"
  retry_guidance: "bounded-backoff"
monitoring:
  - "p95_and_p99_latency"
  - "successful_search_completion"
  - "rejected_requests_by_reason"
  - "database_pool_wait"
  - "false_positive_review"
change_control:
  approval: "security-and-sre"
  rollback: "documented"
~~~

Trong thực tế, cần điền **ngưỡng đã đo, schema cụ thể của nhà cung cấp, danh tính đáng tin và cách lưu trữ counters phân tán**. Chỉ viết cấu hình khái niệm không tự tạo một rate limiter hoạt động.

### 17.1. Những lựa chọn cần được review

**Lưu trạng thái giới hạn:** nếu có nhiều instance gateway, bộ đếm giới hạn theo user có đồng bộ không? Chọn local hay centralized rate limiting ảnh hưởng đến độ nhất quán, latency và khả năng chịu lỗi.

**Khi rate-limit service bị lỗi:** fail-open có thể khiến backend quá tải; fail-closed có thể chặn user hợp lệ. Chính sách cần được quyết định theo loại endpoint và điều kiện lỗi, tránh một lựa chọn chung cho toàn hệ thống.

**Phân quyền quản trị rule:** actor có quyền sửa WAF, bypass list hoặc quota có thể thay đổi khả năng phòng vệ. Cloud IAM, MFA, audit change và guardrail là những phần của thiết kế bảo mật, không chỉ của vận hành.

**Audit:** lưu action theo rule ID, policy version, source identity đã được xác minh, route, thời điểm và kết quả, tránh ghi secret, token hay dữ liệu cá nhân không cần thiết.

## 18. Tình huống thực hành và đáp án gợi ý

### Tình huống A — Nhiều request đến trang tĩnh

Traffic public tăng mạnh đến hình ảnh và CSS; CDN vẫn có cache hit cao, origin ổn định, người dùng hoàn thành tác vụ bình thường.

**Câu hỏi:** có cần kết luận L7 DDoS đang làm hỏng dịch vụ không?

**Gợi ý:** chưa. Request lớn nhưng không gây suy giảm availability tại origin có thể là traffic hợp lệ hoặc một sự kiện edge đã hấp thụ. Theo dõi CDN, băng thông và security signals nhưng đánh giá tác động bằng SLO/SLI, không chỉ RPS.

### Tình huống B — Trang tìm kiếm khiến DB pool cạn

p95 của search tăng, DB connection pool gần bão hòa trong khi tổng băng thông Internet thấp. Những trang khác vẫn tương đối bình thường.

**Câu hỏi:** nên ưu tiên lớp nào?

**Gợi ý:** điều tra **cost per search request, query plan, concurrency, pagination và timeout**, rồi áp quota theo route/identity, cache khi đúng và giảm tải backend. Chỉ lọc L3/L4 ở uplink không giải quyết nguyên nhân đang nằm ở DB.

### Tình huống C — Chặn IP làm ảnh hưởng người dùng thật

Rate limit theo source IP khiến nhiều người dùng mạng di động không đăng nhập được; traffic đến từ một dải NAT lớn.

**Câu hỏi:** vấn đề thiết kế ở đâu?

**Gợi ý:** một IP có thể đại diện nhiều người dùng qua CGNAT. Nên kết hợp account/session/tenant identity, hành vi và tín hiệu edge đáng tin, có giới hạn theo nghiệp vụ và giám sát false positive. Không bỏ toàn bộ phòng vệ chỉ vì một key không phù hợp.

### Tình huống D — Website bị chậm sau khi DB được mở rộng

Đội SRE tăng replica DB nhưng độ trễ vẫn cao; dashboard cho thấy worker pool ở API đã đầy và retry tăng.

**Câu hỏi:** vì sao chỉ mở rộng DB chưa đủ?

**Gợi ý:** bottleneck có thể nằm tại application concurrency, connection handling hoặc retry storm. Cần tìm đúng điểm nghẽn và điều chỉnh admission, timeout, queue, retry và bulkhead theo telemetry.

### Tình huống E — CDN đã bật nhưng origin vẫn chịu tải lớn

Origin nhận nhiều request trực tiếp qua một endpoint ngoài đường CDN; WAF edge không ghi nhận tương ứng.

**Câu hỏi:** lớp bảo vệ nào bị thiếu?

**Gợi ý:** điểm kiểm soát edge không nằm trên tất cả đường tới origin. Kiểm tra DNS/public exposure, firewall/security group, LB, đường peering và cơ chế chỉ cho phép nguồn CDN/proxy đáng tin; xác thực kết nối khi phù hợp.

### Tình huống F — API mobile gặp lỗi challenge

Sau khi bật bot challenge trên mọi request HTTP, trình duyệt web hoạt động nhưng ứng dụng mobile và webhook hợp lệ không qua được kiểm tra.

**Câu hỏi:** cần điều chỉnh thế nào?

**Gợi ý:** phân loại client theo identity và loại endpoint; dùng token/mTLS/chữ ký webhook và quota cho API không có giao diện người dùng. Chỉ áp challenge tương tác khi có khả năng hoàn tất; kiểm thử accessibility và business completion.

### Tình huống G — Cloud tự mở rộng nhưng chi phí tăng mạnh

Autoscaling liên tục tạo instance khi traffic tăng, nhưng báo cáo vẫn chậm và bill cloud tăng.

**Câu hỏi:** có nên chỉ tăng giới hạn autoscaling?

**Gợi ý:** chưa. Xem workload cost, DB bottleneck, queue, caching, per-tenant quota và unit economics. Autoscaling tăng năng lực nhưng không phải cách phòng ngừa chi phí vô hạn hoặc lạm dụng endpoint nặng.

### Tình huống H — Log WAF cho thấy block tăng, SLO vẫn giảm

Sau khi bật một rule chặn mới, số request tới origin giảm nhưng tỷ lệ checkout thành công cũng giảm.

**Câu hỏi:** rule có hiệu quả không?

**Gợi ý:** cần kiểm tra false positive và các hành trình nghiệp vụ, nhóm client, địa lý, user identity, challenge behavior. Mitigation chỉ đạt mục tiêu khi người dùng hợp lệ được phục vụ; có thể phải thu hẹp/rollback rule và dùng kiểm soát theo route chính xác hơn.

## 19. Những sai lầm thường gặp

1. **Coi DoS chỉ là băng thông lớn.** L7 có thể làm nghẽn DB, worker hay queue khi Mbps thấp.
2. **Tin rằng có firewall TCP/443 là đủ.** Firewall cho phép kết nối nghiệp vụ không kiểm soát toàn bộ chi phí API.
3. **Chỉ nhìn tổng RPS.** Endpoint khác nhau có resource cost rất khác nhau.
4. **Gán mọi traffic cao là tấn công.** Flash crowd, deployment, retry storm hoặc sự kiện kinh doanh có thể tạo mẫu tương tự.
5. **Chặn IP quá rộng.** NAT của mạng di động, doanh nghiệp và shared proxy làm nhiều người dùng vô can bị ảnh hưởng.
6. **Chỉ lọc ở origin khi uplink đã nghẽn.** Phải giải quyết tại upstream nếu điểm nghẽn nằm trước origin.
7. **Bật WAF challenge cho mọi API.** Client không có trình duyệt không thể hoàn thành thử thách.
8. **Cache sai nội dung phân quyền.** Có thể lộ dữ liệu giữa các user, làm mất tính bí mật.
9. **Autoscale không có budget.** Tăng tài nguyên không khắc phục workload bất đối xứng hoặc downstream bottleneck.
10. **Queue không giới hạn.** Giảm request fail trước mắt nhưng tích lũy độ trễ và bộ nhớ.
11. **Retry không giới hạn.** Khi lỗi, client tự khuếch đại tải.
12. **Quên đường trực tiếp tới origin.** WAF/CDN chỉ bảo vệ traffic đi qua chúng.
13. **Không xét traffic east-west.** Service nội bộ có thể tạo overload ngoài phạm vi WAF Internet.
14. **Không xem mức hoàn thành nghiệp vụ.** Giảm request không có ý nghĩa nếu user hợp lệ bị chặn.
15. **Không giám sát logging pipeline.** Trong tải cao, mất log làm sai kết luận về traffic.
16. **Không kiểm soát quyền sửa mitigation.** Một thay đổi IAM/rule có thể tắt bảo vệ hoặc mở đường bypass.
17. **Không kiểm thử rollback.** Emergency policy còn tồn tại lâu sau sự cố, gây lỗi cho user.
18. **Xem 429 là thất bại tuyệt đối.** Khi dùng đúng, từ chối có kiểm soát có thể duy trì SLO của người dùng ưu tiên và bảo vệ backend.

## 20. Checklist thiết kế và vận hành phòng vệ L7 DoS/DDoS

- [ ] Xác định SLO/SLI của các hành trình nghiệp vụ quan trọng.
- [ ] Ghi sơ đồ Internet/ISP/CDN/WAF/API gateway/origin/cache/DB/queue.
- [ ] Xác minh origin không có đường truy cập trực tiếp ngoài chính sách.
- [ ] Đánh giá request cost theo endpoint và điều kiện xác thực.
- [ ] Có baseline RPS, p95/p99, success/429/5xx, backend saturation và cache hit.
- [ ] Dùng rate limit/quota theo identity, tenant, route hoặc cost phù hợp.
- [ ] Hiểu hạn chế của source-IP filtering trong mạng NAT và IPv6.
- [ ] Áp concurrency limit, timeout, queue bound, circuit breaker và retry budget.
- [ ] Cân nhắc CDN caching, stale policy và bảo vệ dữ liệu phân quyền.
- [ ] Bảo vệ endpoint login, OTP, search, GraphQL, report và webhook theo chức năng.
- [ ] Thiết kế khác nhau cho web browser, mobile client và machine-to-machine API.
- [ ] Có upstream mitigation nếu đường truyền hoặc thiết bị biên có thể nghẽn.
- [ ] Có giám sát WAF decisions, false positives và business completion.
- [ ] Kết hợp firewall/IDS/IPS, DNS, VPN/NAC và cloud audit theo threat model.
- [ ] Bảo vệ quyền sửa WAF/rate limit/CDN/security group và ghi audit.
- [ ] Có dashboard, alert, owner và runbook ứng phó cho từng nút nghẽn chính.
- [ ] Dựng được timeline sự cố và có bằng chứng thay đổi/rollback.
- [ ] Kiểm thử trong lab/staging có giới hạn, kiểm chứng cả trường hợp allow và reject.
- [ ] Có kế hoạch xử lý backlog, chi phí cloud và phục hồi sau sự kiện.
- [ ] Review lại rule, limit, dependency và SLO khi kiến trúc hoặc traffic thay đổi.

## 21. Tổng kết

**Application-layer denial of service** khai thác khoảng chênh giữa công việc yêu cầu tạo ra và năng lực phục vụ thực tế của ứng dụng. L7 DDoS có thể đến từ nhiều nguồn và dùng các request HTTP/API bình thường về mặt cú pháp, nên **không thể chỉ dựa vào số IP, số request hoặc một chữ ký để kết luận**. Cần quan sát cả tải, chi phí theo endpoint, điểm nghẽn backend và ảnh hưởng đến người dùng hợp lệ.

Phòng vệ bền vững kết hợp **upstream/CDN, WAF, rate limiting theo danh tính và chức năng, bảo vệ origin, caching phù hợp, concurrency và backpressure, kiến trúc DB/queue có giới hạn, observability và runbook**. Trong phạm vi SECURITY_NETWORK_SECURITY, các lớp firewall, VPN/NAC, IDS/IPS, DNS và cloud hỗ trợ xác định đường đi, giới hạn truy cập và phát hiện bất thường. Khi thiết kế lấy **availability SLO của nghiệp vụ** làm tiêu chí, đội vận hành có thể giảm tác động của tải bất lợi mà vẫn duy trì quyền truy cập cho những người dùng được phép.
