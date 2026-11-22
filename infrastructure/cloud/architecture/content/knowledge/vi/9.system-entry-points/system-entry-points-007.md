# Health check, loại bỏ đích lỗi và điều phối lưu lượng dự phòng

> **Chương:** Điểm vào hệ thống  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt health check ở cấp process, instance, ứng dụng, dependency và toàn dịch vụ; chọn kiểm tra phù hợp với mục đích.
2. Giải thích vai trò của startup, liveness, readiness và health check của load balancer/orchestrator.
3. Thiết kế ngưỡng kiểm tra để phát hiện đích không khỏe, loại khỏi phân phối lưu lượng và tránh dao động trạng thái.
4. Mô tả connection draining, graceful shutdown và cách xử lý request đang chạy khi một đích bị loại.
5. Phân biệt failover trong một zone/region với điều phối lưu lượng giữa region; lựa chọn health probe, routing policy, TTL và cơ chế phục hồi.
6. Kiểm chứng hành vi khi lỗi, tránh tạo sự cố dây chuyền do probe quá sâu, retry hoặc chuyển hướng không kiểm soát.

## 1. Vì sao hệ thống cần health check và điều phối lưu lượng?

Một điểm vào như load balancer, API gateway, reverse proxy hoặc DNS router thường phân phối request tới nhiều đích: VM, container, pod, ứng dụng hoặc region. Danh sách đích chỉ hữu ích khi hệ thống biết đích nào có khả năng nhận và xử lý request.

Nếu một instance đã dừng nhưng vẫn nhận traffic, người dùng sẽ thấy lỗi. Nếu một instance còn sống ở mức process nhưng ứng dụng chưa nạp cấu hình hoặc chưa kết nối được database, request vẫn thất bại. Nếu probe đánh dấu cả cụm là lỗi chỉ vì một dependency không thiết yếu đang chậm, hệ thống có thể tự loại bỏ toàn bộ năng lực đang còn hoạt động.

**Health check** là một phép kiểm tra định kỳ hoặc theo sự kiện nhằm đánh giá một trạng thái sức khỏe cụ thể. Kết quả có thể được dùng để:

- Quyết định một process/container có cần khởi động lại hay không.
- Cho phép hoặc ngăn một instance nhận request mới.
- Loại một target khỏi pool của load balancer.
- Chuyển traffic sang zone hoặc region dự phòng.
- Cảnh báo đội vận hành và cung cấp tín hiệu cho autoscaling/automation.

Điểm quan trọng là phải biết **ai thực hiện phép kiểm tra, kiểm tra điều gì và kết quả được dùng để hành động nào**. Một endpoint trả HTTP 200 không tự chứng minh mọi nghiệp vụ hoạt động tốt; một lần timeout cũng chưa đủ kết luận cả region đã hỏng.

### 1.1. Những khái niệm cần phân biệt

| Khái niệm | Câu hỏi | Hành động thường liên quan |
|---|---|---|
| **Process health** | Tiến trình còn chạy và phản hồi được không? | Giám sát process hoặc runtime |
| **Startup check** | Ứng dụng đã hoàn tất khởi tạo chưa? | Chờ trước khi đánh giá liveness/readiness |
| **Liveness** | Process có còn tiến triển hay đã deadlock/hỏng không? | Có thể khởi động lại instance/container |
| **Readiness** | Ứng dụng hiện có thể nhận loại request này không? | Thêm/loại target khỏi endpoint phục vụ |
| **Load balancer target health** | Target có đạt điều kiện được nhận traffic theo cấu hình của LB không? | Chọn hoặc bỏ target khỏi pool |
| **Dependency health** | Database, cache, queue hoặc provider có dùng được không? | Giới hạn chức năng, retry có kiểm soát, cảnh báo |
| **Service health/SLO** | Người dùng có thực hiện được hành động quan trọng với chất lượng cam kết không? | Đánh giá dịch vụ và điều phối ở cấp cao hơn |

Các trạng thái này có liên quan nhưng **không thể thay thế lẫn nhau**. Một process sống chưa chắc sẵn sàng; một database khỏe chưa chắc API đúng nghiệp vụ; DNS health không nhất thiết phản ánh từng request của mọi người dùng.

## 2. Các loại health check và nơi nên thực hiện

### 2.1. Startup, liveness và readiness

Trong môi trường container/orchestrator, ba loại probe thường có ý nghĩa riêng:

- **Startup probe:** xác định ứng dụng đã khởi tạo đủ để bắt đầu được giám sát bình thường. Probe này hữu ích khi ứng dụng khởi động chậm, chạy migration an toàn hoặc nạp cache ban đầu. Khi startup chưa đạt, hệ thống có thể trì hoãn đánh giá các probe khác theo cơ chế nền tảng.
- **Liveness probe:** xác định tiến trình có còn hoạt động theo kỳ vọng hay bị treo. Khi thất bại đủ ngưỡng, orchestrator có thể khởi động lại container.
- **Readiness probe:** xác định instance có thể nhận request mới không. Khi không đạt, orchestrator hoặc endpoint controller có thể bỏ instance khỏi danh sách endpoint phục vụ; process vẫn có thể tiếp tục chạy và phục hồi.

Không đặt một lệnh gọi database dài làm liveness một cách tùy tiện. Khi database chậm, tất cả container có thể fail liveness rồi restart đồng loạt; điều này làm mất connection pool/cache vừa xây và tăng áp lực lên database. Liveness nên phát hiện tình trạng process không thể tự hồi phục; readiness có thể phản ánh khả năng nhận traffic với phạm vi dependency đã được lựa chọn.

Ví dụ mô tả endpoint:

~~~text
GET /health/startup
  200: bootstrap hoàn tất
  503: ứng dụng còn đang khởi tạo

GET /health/live
  200: event loop/thread chính vẫn tiến triển
  500/503: process rơi vào trạng thái cần khởi động lại

GET /health/ready
  200: instance có thể nhận request mới theo policy
  503: instance tạm thời chưa sẵn sàng
~~~

Các đường dẫn và mã phản hồi trên là ví dụ. Cách triển khai thực tế phụ thuộc framework và nền tảng. Endpoint health thường cần được giới hạn quyền truy cập và không trả secret, connection string, stack trace hoặc chi tiết topology nhạy cảm.

### 2.2. Health check của load balancer

Load balancer thường gửi probe theo giao thức và cấu hình đã chọn: TCP connect, HTTP/HTTPS request, gRPC health protocol hoặc phương thức do nền tảng hỗ trợ. Một target chỉ được xem là healthy khi đáp ứng điều kiện của health check theo ngưỡng.

| Loại probe | Chứng minh được điều gì? | Không chứng minh được điều gì? |
|---|---|---|
| **TCP connect** | Cổng có thể thiết lập kết nối | Ứng dụng có xử lý request đúng hay database khả dụng |
| **HTTP path** | Server trả response phù hợp với path/mã dự kiến | Luồng nghiệp vụ đầy đủ có thành công không |
| **HTTPS** | Kết nối TLS và phản hồi ứng dụng theo cấu hình | Mọi client/route khác đều có chứng chỉ và policy hợp lệ |
| **gRPC health service** | Service công bố trạng thái theo giao thức health | Tất cả request cụ thể hoặc dependency tùy chọn đều thành công |
| **Synthetic transaction** | Một hành trình thử từ góc nhìn client đạt kết quả | Mọi tenant, region, request path đều không có lỗi |

Probe nên kiểm tra vừa đủ để quyết định đích có nhận traffic mới được không. Nếu probe quá nông, đích hỏng vẫn nhận request; nếu quá sâu và gọi nhiều dependency, nó có thể tạo tải phụ, lộ dữ liệu hoặc tạo false negative.

### 2.3. Dependency health và chức năng giảm cấp

Ứng dụng thường có nhiều dependency với mức quan trọng khác nhau. Ví dụ:

| Dependency | Ảnh hưởng khi lỗi | Ứng xử hợp lý có thể chọn |
|---|---|---|
| Database giao dịch chính | Không thể xác nhận booking | Readiness của API tạo booking không đạt hoặc API trả lỗi có kiểm soát; không báo thành công giả |
| Cache | Có thể làm chậm truy vấn nhưng dữ liệu chuẩn còn trong DB | Tiếp tục với DB nếu còn capacity; cảnh báo, giới hạn tải |
| Queue thông báo | Booking có thể commit nhưng thông báo chậm | Cho phép booking nếu outbox ghi bền; theo dõi backlog/publish lag |
| Search index | Tìm kiếm có thể không dùng được hoặc chuyển sang cách đọc đơn giản | Giảm cấp hoặc tạm ngừng endpoint tìm kiếm |
| Email provider | Không gửi được email tức thời | Queue, retry có giới hạn; không làm hỏng booking đã commit |
| Identity provider | Có thể không xác thực được phiên mới | Hành vi phụ thuộc token/session policy; không tự bỏ xác thực |

Readiness không nên trả unhealthy chỉ vì **mọi chức năng phụ** đều không hoạt động. Cần xác định endpoint hoặc workload mà target phục vụ. Nếu một deployment cùng phục vụ cả API đặt booking và API báo cáo, readiness toàn instance phải lựa chọn chính sách rõ; đôi khi tách workload hoặc route theo capability là cách đơn giản hơn.

### 2.4. External synthetic monitoring

Health probe từ bên trong cùng network có thể bỏ sót sự cố mà người dùng gặp: DNS công khai, chứng chỉ edge, route Internet, WAF, CDN, identity provider hoặc sai cấu hình ở một điểm vào. **Synthetic monitoring** chạy một giao dịch kiểm tra từ vị trí gần người dùng hoặc bên ngoài biên cloud:

1. Phân giải DNS và thiết lập kết nối TLS.
2. Gọi endpoint công khai với danh tính kiểm tra có quyền giới hạn.
3. Thực hiện một thao tác không phá hoại hoặc thao tác trên dữ liệu thử.
4. Xác nhận kết quả nghiệp vụ, độ trễ và request ID.
5. Gửi metric/cảnh báo khi lỗi lặp lại theo ngưỡng.

Không chạy synthetic test tạo booking thật hoặc gửi SMS/email thật mỗi vài giây nếu chưa kiểm soát dữ liệu, chi phí và side effect. Cần tài khoản thử, dữ liệu cô lập, hạn mức và cleanup.

## 3. Thiết kế probe: tần suất, timeout và ngưỡng

### 3.1. Các tham số cơ bản

Một health check thường có các tham số:

| Tham số | Ý nghĩa | Tác động khi chọn sai |
|---|---|---|
| **Interval** | Khoảng thời gian giữa các lần kiểm tra | Quá thưa phát hiện muộn; quá dày tăng request phụ |
| **Timeout** | Thời gian chờ một probe | Quá ngắn tạo false negative; quá dài phát hiện chậm và giữ tài nguyên |
| **Healthy threshold** | Số lần thành công liên tiếp trước khi xem đích khỏe | Quá cao làm chậm đưa đích mới trở lại pool |
| **Unhealthy threshold** | Số lần thất bại liên tiếp trước khi loại đích | Quá thấp loại nhầm khi mạng chập chờn; quá cao để đích lỗi tiếp tục nhận traffic |
| **Initial delay/grace** | Khoảng chờ trước probe hoặc trước khi coi lỗi khởi động là bất thường | Quá ngắn gây restart loop lúc bootstrap |
| **Path/port/protocol** | Địa chỉ và giao thức được kiểm tra | Sai path, SNI hoặc port khiến target bị đánh lỗi dù ứng dụng đang chạy |
| **Expected status/body** | Điều kiện response được xem là thành công | Điều kiện quá rộng chấp nhận lỗi; quá hẹp loại target hợp lệ |

Ví dụ cấu hình minh họa:

~~~text
Protocol: HTTP
Path: /health/ready
Interval: 10 giây
Timeout: 2 giây
Unhealthy threshold: 3 lần liên tiếp
Healthy threshold: 2 lần liên tiếp
Grace period sau khi khởi động: 30 giây
~~~

Không sao chép nguyên các con số này vào production. Hãy lấy thời gian khởi động thực tế, latency phân vị cao, độ ổn định mạng, mục tiêu phát hiện lỗi và khả năng chịu tải làm đầu vào. Một probe timeout 2 giây có thể hợp lý với endpoint nội bộ đơn giản nhưng không hợp lý nếu path thực hiện truy vấn lớn.

### 3.2. Ước lượng thời gian phát hiện

Nếu health check chạy mỗi \(I\) giây, timeout là \(T\), cần \(N\) lần thất bại liên tiếp và lỗi xảy ra ngay sau lần probe thành công trước đó, thời gian từ lúc lỗi đến quyết định loại target gần đúng nằm trong khoảng:

\[
(N-1)I+T \quad \text{đến} \quad NI+T
\]

Đây chỉ là ước lượng đơn giản; nền tảng có thể có lịch probe lệch pha, nhiều node kiểm tra song song, jitter và thời gian cập nhật trạng thái.

Ví dụ interval 10 giây, timeout 2 giây, unhealthy threshold 3:

- Nếu lỗi xuất hiện ngay trước lần probe tiếp theo, có thể cần xấp xỉ \(2\times10+2=22\) giây.
- Nếu lỗi xuất hiện ngay trước một lần probe vừa bắt đầu, ba lần probe có thể kết thúc sau khoảng \(3\times10+2=32\) giây tùy cách tính lịch.

Vì vậy phải đo thời gian phát hiện thực tế trên nền tảng triển khai. **Phát hiện target lỗi không đồng nghĩa traffic đã chuyển xong**; còn thời gian cập nhật pool, deregistration, DNS cache hoặc routing convergence.

### 3.3. False positive và false negative

- **False positive:** target khỏe bị đánh dấu unhealthy. Hậu quả là giảm capacity, tạo tải dồn lên các target còn lại và có thể làm toàn cụm thất bại.
- **False negative:** target lỗi nhưng vẫn bị đánh dấu healthy. Request của người dùng tiếp tục thất bại và thời gian phục hồi dài.

Để giảm false positive:

- Dùng threshold đủ chống nhiễu, timeout theo latency thực và tránh probe phụ thuộc mạng/DB không cần thiết.
- Theo dõi trạng thái theo nhiều target và nhiều nguồn đo; tránh một probe duy nhất quyết định failover toàn hệ thống.
- Xem xét hysteresis: ngưỡng đưa target trở lại healthy có thể khác ngưỡng loại ra.
- Giữ capacity dự phòng để một target bị loại không đẩy các target còn lại vượt giới hạn.

Để giảm false negative:

- Không chỉ kiểm tra TCP nếu ứng dụng có thể mở cổng nhưng deadlock.
- Kiểm tra endpoint readiness thực sự được gắn với listener/route phục vụ.
- Có synthetic monitoring ngoài mạng và metric nghiệp vụ.
- Kiểm thử các lỗi như pool cạn, thread/event loop đứng, dependency thiết yếu không hoạt động.

### 3.4. Tránh health check storm và flapping

**Flapping** là trạng thái target liên tục chuyển healthy ↔ unhealthy. Nếu nhiều probe cùng gọi database hoặc endpoint cần nhiều CPU, lúc hệ thống yếu probe càng làm nặng thêm tải.

Biện pháp:

1. Endpoint probe phải nhẹ, nhanh và có giới hạn tài nguyên.
2. Dùng interval, timeout và threshold có hysteresis.
3. Tránh tất cả health checker chạy đồng pha; dùng jitter hoặc cơ chế scheduling phù hợp khi tự vận hành.
4. Không tự động restart mọi instance cùng lúc do một dependency bên ngoài.
5. Cảnh báo số lượng target unhealthy, số lần trạng thái đổi, capacity còn lại và error rate người dùng.
6. Xác định chính sách khi **mọi target cùng unhealthy**: fail closed, fail open, giữ target hay chuyển vùng là quyết định riêng, phải được kiểm chứng.

Mặc định fail open hay fail closed đều có thể nguy hiểm. Ví dụ giữ target unhealthy có thể tiếp tục trả lỗi; loại toàn bộ target có thể khiến dịch vụ không còn endpoint. Phải xác định theo độ an toàn nghiệp vụ, khả năng phục vụ một phần và chính sách nhà cung cấp.
## 4. Loại target lỗi và đưa target trở lại pool

### 4.1. Health state và vòng đời target

Load balancer thường duy trì trạng thái cho từng target, chẳng hạn initial, healthy, unhealthy, draining hoặc unused. Tên trạng thái và thuật toán chuyển đổi phụ thuộc nhà cung cấp; không nên giả định cùng một tên có cùng ngữ nghĩa ở mọi dịch vụ.

~~~mermaid
stateDiagram-v2
    [*] --> Initial
    Initial --> Healthy: probe thành công đủ ngưỡng
    Initial --> Unhealthy: probe thất bại theo policy
    Healthy --> Unhealthy: thất bại đủ ngưỡng
    Unhealthy --> Healthy: thành công đủ ngưỡng
    Healthy --> Draining: deregistration / scale-in / deployment
    Draining --> Removed: hết thời gian drain
    Removed --> [*]
~~~

Khi target unhealthy, load balancer thường ngừng gửi request mới sau khi trạng thái được cập nhật. Điều đó **không có nghĩa mọi kết nối đang tồn tại bị ngắt ngay lập tức**, và cũng không bảo đảm request đã gửi tới target lỗi được tự động gửi lại target khác. Hành vi retry phụ thuộc giao thức, thời điểm lỗi và semantics của request.

### 4.2. Deregistration và connection draining

Khi scale-in hoặc deploy phiên bản mới, target có thể đang xử lý request, streaming response, WebSocket hoặc giao dịch kéo dài. **Deregistration delay/connection draining** cho phép ngừng nhận kết nối/request mới và cho các kết nối đang chạy cơ hội kết thúc trong khoảng thời gian giới hạn.

Quy trình graceful shutdown thường gồm:

1. Đánh dấu instance không còn nhận việc mới (readiness false hoặc deregister).
2. Chờ load balancer/orchestrator ngừng gửi request mới và cập nhật endpoint.
3. Tiếp tục xử lý request hiện tại trong thời gian drain.
4. Ngừng nhận job mới từ queue; hoàn tất hoặc release lease/visibility timeout đúng cách.
5. Flush log/telemetry, đóng kết nối và giải phóng tài nguyên.
6. Thoát trong termination grace period; nếu quá hạn, orchestrator có thể buộc kết thúc process.

Thời gian drain phải dựa trên thời lượng request thực tế, giao thức và giới hạn nền tảng. Đặt quá ngắn làm đứt request đang chạy; đặt quá dài làm scale-in chậm hoặc giữ tài nguyên không cần thiết.

| Loại workload | Cách rút đích nên cân nhắc |
|---|---|
| HTTP API ngắn | Ngừng nhận request mới, để request hiện tại hoàn tất trong deadline |
| Streaming/SSE/WebSocket | Thông báo reconnect, hỗ trợ client kết nối lại và xác định cách giữ session/state |
| Worker queue | Dừng poll message mới; hoàn tất hoặc release message có kiểm soát; tránh ack trước xử lý xong |
| Batch job dài | Không kill tùy tiện; checkpoint hoặc chờ job kết thúc theo window |
| Consumer event | Quản lý offset/ack và xử lý message đang chạy để tránh mất hoặc lặp ngoài chính sách |

Không dựa vào việc load balancer báo unhealthy để giả định process đã dừng an toàn. Cần cơ chế shutdown trong ứng dụng, grace period của orchestration và kiểm thử deployment/scale-in.

### 4.3. Đưa target phục hồi trở lại pool

Sau khi target lỗi hồi phục, đưa lại vào pool quá nhanh có thể gây flapping. Cần xác nhận startup hoàn tất, cấu hình/secret hợp lệ, listener nhận kết nối, readiness đạt, connection pool và cache sẵn sàng. Nếu target có cache lạnh hoặc tải khởi tạo cao, cân nhắc warm-up trước khi tăng traffic. Một số nền tảng hỗ trợ slow start hoặc gradual traffic ramp; cần kiểm tra tính năng thực tế của load balancer đã chọn.

### 4.4. Khi tất cả target đều unhealthy

Đây là tình huống phải có quyết định trước:

| Chính sách | Ưu điểm | Rủi ro |
|---|---|---|
| Không gửi traffic tới target unhealthy | Tránh gửi request tới đích đã biết là lỗi | Pool rỗng dù một phần target có thể còn phục vụ được |
| Fail open/giữ target theo khả năng nền tảng | Có thể duy trì dịch vụ một phần | Traffic có thể tới target thật sự hỏng |
| Chuyển sang pool/zone/region khác | Duy trì điểm vào nếu dự phòng đủ năng lực | Probe sai có thể chuyển nhầm; dữ liệu dự phòng chưa sẵn sàng |
| Trả lỗi có kiểm soát và bảo toàn dữ liệu | Không tạo trạng thái nghiệp vụ sai | Người dùng không thực hiện được chức năng trong thời gian sự cố |

Không cấu hình bỏ qua health check vô điều kiện khi cả cụm lỗi. Với hệ thống đặt chỗ, trả 503 có thể an toàn hơn xác nhận booking sai; với nội dung công khai có thể chấp nhận phục vụ cache tĩnh. Fallback phải được quyết định ở cấp nghiệp vụ và thử nghiệm.

## 5. Điều phối lưu lượng dự phòng trong một region

### 5.1. Phân tán qua availability zone

Một mẫu triển khai phổ biến là nhiều target ở nhiều availability zone dùng một điểm vào ổn định:

~~~mermaid
flowchart TB
    U[Clients] --> DNS[DNS]
    DNS --> LB[Regional Load Balancer]
    subgraph Region[Cloud Region]
        subgraph AZA[Availability Zone A]
            A1[API target A1]
            A2[API target A2]
        end
        subgraph AZB[Availability Zone B]
            B1[API target B1]
            B2[API target B2]
        end
        LB --> A1
        LB --> A2
        LB --> B1
        LB --> B2
        A1 --> DB[(Database HA)]
        A2 --> DB
        B1 --> DB
        B2 --> DB
    end
~~~

Khi một target unhealthy, LB có thể bỏ target đó và phân phối request tới target khỏe khác. Khi cả AZ lỗi, hệ thống chỉ tiếp tục qua AZ còn lại nếu các thành phần cần thiết cũng có capacity và topology chịu lỗi phù hợp.

Cần xét load balancer có cross-zone routing phù hợp không; mỗi zone có đủ compute capacity sau lỗi không; database, cache, queue, secret endpoint, network egress và DNS có chịu lỗi tương ứng không; traffic khi zone khôi phục có tăng lại dần không.

Ví dụ tải đỉnh 600 request/giây chia đều cho hai zone, mỗi zone bình thường nhận khoảng 300. Khi một zone mất, zone còn lại phải chịu 600. Cần thiết kế capacity sau lỗi hoặc cơ chế giảm tải/rate limit và mức dịch vụ suy giảm đã thống nhất. Chạy hai zone không tự bảo đảm tải sau failover.

### 5.2. Regional load balancing và DNS failover

~~~mermaid
flowchart TB
    U[Global users] --> G[Global DNS / Traffic Manager]
    G -->|Primary healthy| P[Region A endpoint]
    G -.->|Failover| S[Region B endpoint]
    subgraph RA[Region A - Primary]
        P --> PA[Regional LB]
        PA --> AP[Application targets]
        AP --> DP[(Primary data)]
    end
    subgraph RB[Region B - Standby]
        S --> PB[Regional LB]
        PB --> AS[Standby / scaled application]
        AS --> DS[(Replicated / recoverable data)]
    end
    DP -.->|Replication / backup path| DS
~~~

DNS failover thường dựa trên health check endpoint và thay đổi câu trả lời DNS. Tuy nhiên:

- Client, resolver và thiết bị trung gian có thể cache kết quả theo TTL hoặc chính sách riêng.
- Không phải mọi client lập tức truy vấn DNS lại khi endpoint chính lỗi.
- Ứng dụng giữ kết nối lâu hoặc pin IP có thể tiếp tục dùng endpoint cũ.
- TTL thấp có thể tăng truy vấn DNS nhưng không loại bỏ cache cưỡng bức của client/resolver.
- DNS failover không đồng bộ database và không giải quyết conflict khi hai region cùng nhận ghi.

Vì vậy DNS failover **không phải chuyển đổi tức thì** và không nên là cơ chế duy nhất cho mọi loại kết nối. Cần phối hợp global load balancer/traffic manager hoặc khả năng client retry/re-resolve phù hợp.

### 5.3. Các chiến lược routing đa region

| Chiến lược | Cách hoạt động | Dùng khi | Đánh đổi |
|---|---|---|---|
| Active-passive | Region chính nhận traffic; region dự phòng chờ hoặc scale thấp | Muốn đơn giản hóa mô hình ghi | Capacity dự phòng, warm-up và replica lag |
| Active-active | Nhiều region cùng phục vụ | Cần latency địa lý và có thiết kế dữ liệu phù hợp | Conflict dữ liệu, định tuyến, quan sát và vận hành phức tạp |
| Weighted | Chia tỷ lệ theo trọng số | Canary, migration hoặc phân phối tải | Trọng số không phản ánh health/latency nếu không kết hợp metric |
| Latency-based | Chọn endpoint theo latency ước lượng | Người dùng phân tán địa lý | DNS latency không đại diện toàn bộ response ứng dụng |
| Geolocation/geoproximity | Định tuyến theo vị trí hoặc chính sách địa lý | Yêu cầu vùng dữ liệu/địa lý | GeoIP không tuyệt đối chính xác |
| Failover | Dùng endpoint dự phòng khi health policy kích hoạt | Disaster recovery | Cần fencing để ngăn split-brain |

Chọn chiến lược theo RTO/RPO, topology dữ liệu, vị trí người dùng, yêu cầu pháp lý, ngân sách và năng lực vận hành. **Multi-region không mặc định tốt hơn multi-AZ**; active-active có thể làm tăng độ phức tạp lớn nếu dữ liệu ghi tập trung hoặc không có cách giải quyết xung đột.

### 5.4. Điều kiện failover không chỉ là endpoint trả lời

Trước khi chuyển traffic sang region dự phòng, cần biết endpoint đó có đủ instance, quota, chứng chỉ, secret và cấu hình mới nhất không; database đã phục hồi/replica hay chưa; có nguy cơ split-brain không; queue, scheduler và job nền có chạy hai lần không; monitoring và on-call có hoạt động từ ngoài region lỗi không; ai được quyền tuyên bố failover và fencing.

Health check có thể nói region B đang trả response, nhưng không chứng minh database B có dữ liệu mới nhất hoặc được phép nhận ghi. Cần readiness ở cấp dịch vụ và quy trình failover dữ liệu riêng; đừng bật traffic ghi chỉ vì TCP/HTTP probe đạt.

### 5.5. Failback — quay về primary

Sau khi primary phục hồi, không chuyển traffic ngay chỉ vì probe xanh. Cần xác định nguyên nhân đã xử lý; đối soát dữ liệu trong thời gian failover; chọn hướng đồng bộ lại và xác nhận replication lag; xác nhận fencing ngăn hai nơi cùng nhận ghi; chuyển traffic từng bước và quan sát SLI.

Failback đôi khi cần migration dữ liệu hoặc maintenance riêng. Endpoint healthy chưa đủ để đảo vai trò database.

## 6. Thiết kế endpoint health an toàn

### 6.1. Readiness tổng hợp nhưng không gọi mọi dependency

Một readiness check có thể kết hợp trạng thái cục bộ:

~~~text
isReady =
    startupComplete
    AND configurationValid
    AND listenerAcceptingRequests
    AND criticalLocalResourcesAvailable
    AND requiredDataPathAcceptingWork
~~~

Nếu cần biết database còn khả dụng, ưu tiên probe nhẹ có timeout ngắn hoặc trạng thái connection/operation gần đây thay vì chạy truy vấn nặng mỗi lần health check. Với database là dependency thiết yếu, readiness có thể phản ánh khả năng xử lý endpoint cốt lõi; nhưng cần tránh DB chậm làm mọi instance đồng loạt bị loại rồi không còn instance nào xử lý request phục hồi.

Dependency tùy chọn như email/search nên được đo bằng metric riêng và làm endpoint tương ứng giảm cấp; không cần làm liveness toàn process thất bại.

### 6.2. Tách health endpoints khỏi kiểm tra quản trị

Endpoint cho load balancer chỉ nên trả thông tin tối thiểu:

~~~json
{
  "status": "ready"
}
~~~

Endpoint nội bộ dành cho vận hành có thể có detail hơn nhưng phải xác thực và kiểm soát truy cập:

~~~json
{
  "status": "degraded",
  "checks": {
    "database": "available",
    "cache": "unavailable",
    "notificationQueue": "available"
  },
  "checkedAt": "2026-11-18T05:00:00Z"
}
~~~

Không để endpoint công khai tiết lộ host nội bộ, địa chỉ database, cluster, tài khoản, secret, stack trace hoặc lỗi chứa query. Health endpoint cũng không nên chạy migration, sửa dữ liệu hay tạo message gây side effect.

### 6.3. Bảo vệ health check khỏi lạm dụng

- Chỉ cho phép nguồn probe được xác định truy cập endpoint nội bộ khi nền tảng hỗ trợ.
- Giới hạn tốc độ và tài nguyên; endpoint phải nhẹ và không trở thành vector DoS.
- Dùng TLS/xác thực phù hợp cho probe xuyên mạng hoặc giữa region.
- Không trả thông tin nhạy cảm; lưu log/metric đủ chẩn đoán mà không tạo log storm.
- Phân biệt traffic probe với traffic khách hàng khi phân tích SLI, nhưng vẫn giữ synthetic test cho toàn đường đi.

## 7. Quan sát và vận hành health/failover

### 7.1. Không chỉ giám sát trạng thái xanh/đỏ

| Nhóm metric | Ví dụ | Ý nghĩa |
|---|---|---|
| Target state | Số healthy/unhealthy/initial/draining | Năng lực nhận traffic hiện tại |
| Probe behavior | Success rate, timeout, latency, status code | Probe sai hoặc target dao động |
| User impact | 5xx, timeout, request success, p95/p99 | Người dùng thực sự bị ảnh hưởng? |
| Capacity | CPU, memory, DB connections, queue lag | Target còn lại có chịu tải không? |
| Traffic distribution | Request/byte theo zone/region/target | Xác nhận load balancing/failover |
| Recovery | Detection time, drain, failover/failback time | Đối chiếu RTO và runbook |
| Data health | Replication lag, consistency check | Endpoint dự phòng có dữ liệu đủ mới? |
| DNS/routing | Health state, answer, TTL, resolution latency | Client có nhận route mới? |

Cảnh báo theo tác động: tỷ lệ target unhealthy vượt ngưỡng, tất cả target mất healthy, capacity còn lại dưới mức dự phòng, error budget bị tiêu nhanh hoặc failover không hội tụ. Một target unhealthy đơn lẻ có thể là hành vi bình thường trong deployment; cả zone đỏ hoặc latency tăng đồng thời là tình huống ưu tiên cao.

### 7.2. Runbook khi target bị loại

1. Xác nhận phạm vi: một target, nhiều target cùng AZ, toàn region hay chỉ một health checker?
2. Đối chiếu user impact: error rate, latency, request success và chức năng nghiệp vụ.
3. Kiểm tra nguyên nhân: process, startup, readiness, mạng, certificate, cấu hình, quota hoặc dependency.
4. Xem capacity còn lại: target khỏe có chịu tải mà không vượt DB/connection/queue limit không?
5. Quyết định giảm tải/failover dựa trên runbook, rủi ro dữ liệu và quyền phê duyệt.
6. Phục hồi target: sửa lỗi, warm-up, kiểm tra readiness, đưa vào pool dần.
7. Đối soát request dở dang, message, dữ liệu, routing, SLI và chi phí.
8. Ghi thời điểm phát hiện/loại/phục hồi, false positive/negative, nguyên nhân và cải tiến.

Tự động hóa có thể xử lý lỗi instance đơn giản; quyết định chuyển database writer hoặc failover region thường cần guardrail và quy trình rõ hơn vì tác động tới dữ liệu.

### 7.3. Kiểm thử health check và điều phối lưu lượng

| Bài kiểm thử | Cách thực hiện trong môi trường kiểm soát | Kết quả cần xác nhận |
|---|---|---|
| Startup chậm | Tăng thời gian bootstrap/cache warm-up | Không restart loop; chỉ nhận traffic khi sẵn sàng |
| Process treo | Mô phỏng deadlock/không tiến triển | Liveness phát hiện và phục hồi đúng |
| Readiness false | Đánh dấu instance tạm không nhận request | LB/orchestrator loại target khỏi traffic mới |
| Dependency chậm | Làm DB/cache/provider chậm | Timeout, readiness và giảm cấp đúng; không loại toàn cụm sai |
| Target bị kill | Dừng instance đang nhận tải | Detection, drain, user impact và capacity |
| Drain dài | Tạo request/stream dài hoặc worker đang xử lý | Không mất request/job ngoài chính sách |
| Target flapping | Làm probe xen kẽ thành công/timeout | Hysteresis ổn định, không đổi trạng thái liên tục |
| Mất zone | Fault injection được phê duyệt | Traffic sang zone còn lại, capacity và data path đạt |
| DNS failover | Thay health state endpoint chính trong thử nghiệm | Resolver/client cập nhật trong khoảng đo |
| Region failover/failback | Diễn tập quy trình DR | RTO/RPO, fencing, writer, routing và dữ liệu đúng |

Mỗi phép thử cần baseline, phạm vi được phép, điều kiện dừng, người điều phối và cách rollback. Không thử dừng production hoặc thay DNS thật nếu chưa có kế hoạch/ủy quyền vận hành.

## 8. Ví dụ tổng hợp cho ứng dụng đặt lịch

### 8.1. Yêu cầu minh họa

Một dịch vụ đặt lịch hoạt động trong một region với hai availability zone. API stateless chạy nhiều instance; database managed có HA. Yêu cầu giả định:

- Một instance lỗi không làm mất toàn bộ API.
- Mất một zone không làm mất giao dịch đặt lịch nếu capacity và database failover đáp ứng thiết kế.
- Email chậm không làm health của Booking API fail.
- Deploy/scale-in không cắt request đang chạy ngoài chính sách.
- Đội vận hành xác định được target nào bị loại và vì sao.

Các yêu cầu này cần chuyển thành SLO/RTO/RPO cụ thể và kiểm thử theo provider trước khi triển khai.

### 8.2. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant LB as Regional Load Balancer
    participant A as API Instance A
    participant B as API Instance B
    participant DB as Managed DB HA
    LB->>A: Probe /health/ready
    A-->>LB: 200 ready
    LB->>B: Probe /health/ready
    B-->>LB: 200 ready
    LB->>A: POST /v1/bookings
    A->>DB: Commit booking + outbox
    DB-->>A: Commit success
    A-->>LB: 201 Created
    LB-->>A: Deregister / drain
    Note over LB,A: Ngừng request mới; request đang chạy drain theo policy
    LB->>B: Route request mới
    B->>DB: Xử lý request tiếp theo
    A-->>LB: Shutdown sau drain
    Note over DB: Notification queue xử lý bất đồng bộ, độc lập health API
~~~

### 8.3. Ma trận quyết định

| Câu hỏi | Quyết định minh họa | Lý do và giới hạn |
|---|---|---|
| Process còn sống? | Liveness kiểm tra tiến trình/event loop nhẹ | Phát hiện deadlock; không gọi DB nặng |
| Instance nhận request được? | Readiness kết hợp startup, cấu hình và dependency thiết yếu | Tách liveness khỏi khả năng nhận traffic |
| LB kiểm tra thế nào? | HTTP endpoint nhẹ, timeout/threshold được đo | Phát hiện ứng dụng; vẫn cần synthetic monitoring |
| Target lỗi xử lý ra sao? | Loại khỏi pool, drain theo policy | Request dở dang không mặc nhiên được replay |
| Một zone lỗi? | Regional LB phân phối tới zone còn lại, capacity tính cho tải sau lỗi | Chỉ đạt nếu DB/network/dịch vụ thiết yếu chịu lỗi |
| Email provider lỗi? | Queue giữ công việc, retry/DLQ; API booking vẫn hoạt động | Backlog cần alert; không đưa email vào readiness API |
| Region chính lỗi? | Failover chỉ khi DR data path và writer fencing sẵn sàng | DNS/global routing không bảo đảm dữ liệu |

## 9. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Một endpoint dùng cho startup, liveness và readiness | Restart loop hoặc đích chưa sẵn sàng vẫn nhận traffic | Tách probe theo hành động |
| Liveness gọi database/cache bên ngoài | Dependency chậm làm restart toàn cụm | Liveness nhẹ; readiness/dependency policy riêng |
| Probe chỉ kiểm tra TCP | Process mở cổng nhưng app deadlock vẫn healthy | HTTP/gRPC readiness phù hợp |
| Probe chạy nghiệp vụ nặng | Tăng tải và side effect | Probe ngắn, synthetic test tách riêng |
| Unhealthy threshold quá thấp | Instance bị loại bởi nhiễu | Đo latency, timeout, interval và hysteresis |
| Threshold quá cao | Đích lỗi tiếp tục nhận traffic lâu | Đặt detection objective và kiểm chứng |
| Restart mọi target khi DB lỗi | Cụm mất capacity, DB càng khó hồi phục | Tránh liveness dependency-based |
| Không cấu hình drain | Request dài bị cắt khi deploy/scale-in | Graceful shutdown và test drain |
| Tin LB retry mọi request lỗi | Giao dịch trùng hoặc mất request | Client retry có idempotency; semantics rõ |
| Failover theo một probe lỗi | Chuyển traffic nhầm vùng | Nhiều tín hiệu và xác nhận user impact |
| DNS TTL thấp được coi là tức thời | Client vẫn giữ cache/kết nối cũ | Test resolver/client, routing phù hợp |
| Multi-AZ được coi là DR đa region | Không phục hồi khi mất region | DR, replication, backup, runbook riêng |
| Failback ngay khi probe xanh | Dữ liệu lệch hoặc split-brain | Fencing, đối soát, warm-up, chuyển dần |
| Không đo traffic sau loại target | Target còn lại quá tải nhưng probe xanh | Theo dõi saturation/capacity và SLI |

## 10. Bài thực hành: thiết kế health check và failover

**Tình huống:** Ứng dụng đặt lịch chạy trong hai availability zone, mỗi zone có nhiều API instance. Regional load balancer kiểm tra target. Database chính là managed relational database; notification queue và cache là dependency bổ trợ. Sản phẩm muốn duy trì API khi một instance lỗi, giảm tác động khi một zone mất và có kế hoạch DR khi region không khả dụng. Đội chưa đo thời gian startup, p95, thời gian drain hoặc capacity sau lỗi.

Hãy xây dựng tài liệu thiết kế:

1. **Phân loại health:** định nghĩa startup, liveness, readiness, target health, synthetic check và dependency health; nêu hành động tương ứng.
2. **Thiết kế probe:** chọn path/port/protocol, interval, timeout, threshold, initial delay và expected status; nêu cách lấy giá trị từ quan sát và thử nghiệm.
3. **Ma trận dependency:** DB, cache, queue, email provider; xác định dependency nào làm API mất readiness và dependency nào chỉ làm chức năng giảm cấp.
4. **Loại target:** mô tả unhealthy, deregistration, connection draining, graceful shutdown và hành vi request đang chạy.
5. **Trong region:** vẽ deployment hai zone, tính capacity khi mất một zone, nêu phụ thuộc chung và hành vi khi mọi target unhealthy.
6. **Giữa region:** chọn active-passive hoặc phương án khác; mô tả health signal, DNS/global routing, replication, fencing, RTO/RPO và failback.
7. **Observability:** thiết kế dashboard target state, probe latency/error, user error rate, traffic distribution, capacity, replication lag và recovery time.
8. **Thử nghiệm:** process treo, DB chậm, target drain, zone failure, DNS failover và phục hồi; ghi baseline, điều kiện dừng và tiêu chí đạt.

| Chủ đề | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Readiness | Target có thể nhận request nghiệp vụ nào? | Test endpoint/dependency failure |
| Liveness | Tình trạng nào thực sự cần restart? | Test process deadlock/startup |
| Threshold | Bao lâu phát hiện và loại target? | Thời gian đo được |
| Draining | Request/stream/job đang chạy xử lý thế nào? | Test deploy/scale-in |
| Capacity | Sau khi loại target/zone, năng lực còn lại đủ không? | Load test và saturation |
| Failover | Tín hiệu nào đủ để chuyển traffic? | DR drill và decision log |
| Data safety | Region dự phòng có dữ liệu và writer state đúng không? | Replication lag, fencing, reconciliation |
| Failback | Ai phê duyệt, chuyển dữ liệu và traffic ra sao? | Runbook, RTO/RPO thực đo |

**Tiêu chí hoàn thành:** Người đọc theo dõi được từ probe thất bại đến quyết định loại đích, hiểu request đang chạy được xử lý thế nào, thấy lưu lượng đi đâu và biết phép thử nào chứng minh hệ thống chịu lỗi trong phạm vi cam kết.

## 11. Khung ghi nhớ

- **Health check gắn với hành động:** startup trì hoãn probe, liveness phục hồi process, readiness quyết định nhận request và load balancer chọn target.
- **Probe phải đại diện nhưng nhẹ:** kiểm tra đủ để ra quyết định; không gọi mọi dependency và không tạo tải/side effect ngoài ý muốn.
- **Loại target cần quản lý vòng đời:** unhealthy, deregistration, drain, shutdown, warm-up và đưa trở lại pool.
- **Điều phối lưu lượng tính cả capacity và dữ liệu:** Multi-AZ, regional failover và DNS failover giải quyết phạm vi khác nhau.
- **Failover không chỉ là routing:** region dự phòng cần data path, quyền, fencing, quota, quan sát, runbook và failback.
- **Mọi cam kết phải được thử:** detection time, user impact, capacity sau lỗi, RTO/RPO và thời gian hội tụ phải có số liệu.

Điểm vào hệ thống cần đưa lưu lượng tới thành phần có khả năng phục vụ, nhưng health state chỉ là tín hiệu ước lượng. Thiết kế tốt kết hợp probe đúng mục đích, ngưỡng ổn định, loại target có kiểm soát, điều phối qua miền lỗi, bảo vệ tính đúng đắn dữ liệu và quan sát từ góc nhìn người dùng. Nhờ đó hệ thống phản ứng trước lỗi mà không tự biến một thành phần suy giảm thành sự cố diện rộng.
