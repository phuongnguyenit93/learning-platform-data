# Mức đồng thời, tốc độ tạo instance và giới hạn mở rộng

Một hàm serverless có thể tự tăng số execution environment khi lượng request tăng. Khả năng này giúp ứng dụng xử lý tải biến động mà không phải quản lý máy chủ, nhưng không có nghĩa năng lực mở rộng là vô hạn hoặc tức thời. Nền tảng có thể giới hạn số lần thực thi đồng thời, tốc độ tạo môi trường mới, số request/giây, số instance tối đa, số lần polling event source hoặc quota theo tài khoản và region.

Nếu không thiết kế các giới hạn này, một đợt traffic tăng có thể làm request bị throttle, cold start kéo dài, queue backlog tăng hoặc database và API downstream bị quá tải. Tăng concurrency quá cao đôi khi làm hệ thống chậm hơn vì mọi execution environment cùng mở kết nối và tranh chấp tài nguyên.

Bài học này thuộc chương **Mô hình hàm serverless** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong bối cảnh đó, hiểu mức đồng thời, tốc độ tạo instance và giới hạn mở rộng giúp thiết kế hàm serverless đáp ứng tải, bảo vệ dependency và kiểm soát chi phí.

## 1. Hiểu concurrency trong serverless

### 1.1. Execution environment và invocation

Nền tảng serverless thường tạo một execution environment để tải runtime, mã ứng dụng và phần khởi tạo cần thiết. Mỗi lần hàm được gọi là một invocation hoặc execution.

Một số nền tảng có thể tái sử dụng execution environment cho nhiều invocation nối tiếp hoặc đồng thời tùy mô hình runtime và cấu hình. Một số mô hình xử lý đồng thời nhiều request trong cùng environment; mô hình khác chỉ xử lý một invocation tại một thời điểm trên mỗi environment. Vì vậy, không thể áp dụng một con số concurrency per-instance chung cho mọi dịch vụ.

Khi tải tăng, nền tảng có thể tạo thêm environment. Khi tải giảm, environment có thể được giữ ấm trong một thời gian hoặc bị thu hồi. Vòng đời này do nền tảng quản lý và không nên được xem là trạng thái lưu trữ bền vững.

### 1.2. Concurrency là số công việc đang chạy cùng lúc

Concurrency là số invocation đang được xử lý tại cùng một thời điểm. Nó khác với request rate:

- **Request rate / arrival rate:** số request đến trong một giây.
- **Concurrency:** số request hoặc invocation đang chạy cùng lúc.
- **Throughput:** số request hoàn tất trong một đơn vị thời gian.
- **Duration:** thời gian một invocation chạy.
- **Scaling rate:** tốc độ nền tảng tăng hoặc giảm execution environment.
- **Maximum instances:** giới hạn số environment có thể được cấp cho một function hoặc workload.

Ví dụ, 100 request mỗi giây không nhất thiết cần 100 execution environment. Nếu mỗi request chỉ mất 100 ms và hệ thống phân phối đều, số request trung bình đang chạy cùng lúc có thể khoảng 10. Nếu mỗi request mất 2 giây, concurrency trung bình có thể khoảng 200.

### 1.3. Định luật Little để ước lượng concurrency

Với hệ thống ổn định, một cách ước lượng cơ bản là:

**Concurrency trung bình ≈ Arrival rate × Average duration**

Trong đó:
- Arrival rate là số invocation bắt đầu mỗi giây.
- Average duration là thời gian xử lý trung bình tính bằng giây.

Ví dụ:

- 120 request/giây.
- Thời gian xử lý trung bình 250 ms, tương đương 0,25 giây.
- Concurrency trung bình ước tính: 120 × 0,25 = 30 invocation.

Đây là mức trung bình, không phải giới hạn an toàn. Khi thiết kế cần tính đến burst, thời gian xử lý ở percentile cao, retry, cold start và headroom.

Nếu duration tăng gấp đôi do database chậm, concurrency cũng có thể tăng gần gấp đôi dù request rate không đổi. Vì vậy, concurrency cao có thể là hệ quả của dependency chậm, không chỉ do traffic tăng.

### 1.4. Concurrency toàn hệ thống và per-instance

Cần phân biệt hai phạm vi:

- **Function/account concurrency:** tổng số invocation đang chạy của một function hoặc một phạm vi quota trong tài khoản/region.
- **Per-instance concurrency:** số invocation một execution environment xử lý đồng thời.

Ví dụ minh họa: nếu một environment được cấu hình xử lý 5 request cùng lúc và function cần 40 invocation đồng thời, số environment lý thuyết tối thiểu là 8. Nếu mỗi environment chỉ xử lý một invocation tại một thời điểm, cần khoảng 40 environment.

Con số thực tế có thể lớn hơn do phân phối tải, thời gian khởi tạo, giới hạn scaling và các ràng buộc của runtime.

## 2. Mô hình tính toán capacity

### 2.1. Ước lượng số environment cần thiết

Với mô hình mỗi environment có concurrency giới hạn C, có thể ước lượng:

**Số environment cần ≈ ceil(Tổng concurrency mục tiêu / C)**

Ví dụ:
- Concurrency mục tiêu: 150.
- Mỗi environment xử lý tối đa 5 invocation đồng thời.
- Nhu cầu lý thuyết: ceil(150 / 5) = 30 environment.

Cần cộng headroom cho burst và environment đang khởi tạo. Đồng thời kiểm tra giới hạn tối đa của function, account, region và dependency.

### 2.2. Tính capacity theo throughput

Nếu mỗi environment xử lý tối đa C invocation đồng thời và duration trung bình là D giây, throughput lý thuyết gần đúng là:

**Throughput mỗi environment ≈ C / D**

Ví dụ:
- C = 4 invocation.
- D = 0,2 giây.
- Throughput lý thuyết ≈ 20 invocation/giây/environment.

Đây là phép ước lượng trong điều kiện request phân bố đều và không có bottleneck khác. CPU, memory, network, runtime scheduling, connection pool và dependency có thể làm throughput thấp hơn.

### 2.3. Ví dụ sizing end-to-end

Một API serverless nhận 300 request/giây. Duration trung bình là 400 ms.

- Concurrency trung bình ước tính: 300 × 0,4 = 120.
- Nếu một environment xử lý 4 invocation đồng thời: cần khoảng 30 environment ở mức trung bình.
- Nếu thiết kế headroom 50%: capacity mục tiêu khoảng 180 concurrency, tương đương 45 environment ở concurrency 4.

Sau đó phải kiểm tra:
- Function có quota concurrency đủ cho 180 không?
- Nền tảng có thể tạo 45 environment đủ nhanh không?
- Database chịu được số kết nối tăng thêm không?
- API downstream có rate limit không?
- Network, subnet và IP capacity có đáp ứng không?
- Cost ở mức tải này có nằm trong ngân sách không?

Headroom 50% chỉ là ví dụ. Chọn mức dự phòng theo burst, SLO, độ biến động duration và chi phí.

### 2.4. Dùng percentile thay vì chỉ average

Average duration có thể che giấu request chậm. Nếu phần lớn request mất 100 ms nhưng một số request mất 5 giây, concurrency và tail latency sẽ bị ảnh hưởng.

Theo dõi:
- p50 duration.
- p90/p95 duration.
- p99 duration.
- Maximum duration.
- Timeout rate.
- Duration theo loại request hoặc dependency.

Có thể dùng p95 để sizing bảo thủ hơn, nhưng cần tránh coi một percentile đơn lẻ là dự báo hoàn hảo. Phân bố request và tương quan giữa duration với tải cần được đo thực tế.

## 3. Tốc độ tạo execution environment

### 3.1. Scaling rate là gì?

Khi concurrency tăng, nền tảng cần cấp thêm execution environment. Quá trình này có tốc độ giới hạn, có thể được mô tả bằng:
- Số environment mới tối đa được tạo trong một khoảng thời gian.
- Tốc độ tăng concurrency theo chu kỳ.
- Số instance được cấp đồng thời.
- Giới hạn burst ban đầu và tốc độ tăng tiếp theo.
- Quota riêng cho function, account, region hoặc event source.

Các nền tảng có thuật toán và con số khác nhau. Không giả định một mức ramp-up cố định cho mọi nhà cung cấp hoặc mọi loại trigger. Cần xem tài liệu quota hiện hành và đo trong môi trường mục tiêu.

### 3.2. Burst traffic và gradual traffic

**Gradual traffic:** tải tăng từ từ, cho autoscaler thời gian tạo environment và phân phối invocation.

**Burst traffic:** một lượng lớn request đến trong thời gian rất ngắn, ví dụ sau email campaign, thông báo đẩy, sự kiện bán hàng hoặc một hệ thống upstream retry đồng loạt.

Với burst, nhu cầu concurrency có thể vượt tốc độ tạo environment. Request có thể phải chờ, bị throttle hoặc trả lỗi trước khi capacity mới sẵn sàng.

### 3.3. Tốc độ scale-out không đồng nghĩa maximum capacity

Một function có thể có quota concurrency tối đa rất cao nhưng vẫn không thể tăng từ 0 lên mức đó ngay lập tức. Cần xem cả:
- Maximum concurrency.
- Scaling rate.
- Startup duration.
- Warm capacity hiện có.
- Event source polling rate.
- Downstream capacity.

Đây là bốn câu hỏi khác nhau: hệ thống có thể đạt tới bao nhiêu, tăng nhanh tới đâu, mất bao lâu để một environment sẵn sàng và dependency có chịu được tải đó hay không.

### 3.4. Scale-to-zero và cold start

Một số mô hình serverless có thể giảm về zero environment khi không có tải. Khi request tiếp theo đến, nền tảng phải khởi tạo environment mới. Điều này tiết kiệm chi phí idle nhưng tạo cold start.

Cold start có thể bao gồm:
- Cấp compute sandbox hoặc container.
- Chuẩn bị network interface hoặc runtime isolation.
- Pull image hoặc tải artifact.
- Khởi tạo runtime.
- Nạp module và dependency.
- Chạy initialization code.
- Lấy secret hoặc token.
- Tạo connection pool tới dependency.

Không phải mọi cold start đều thực hiện tất cả bước trên; trình tự phụ thuộc nền tảng và cấu hình.

### 3.5. Cold start và duration của request

Cold start làm tăng latency của invocation đầu tiên trên environment mới. Khi tải tăng đột ngột, nhiều environment mới có thể được tạo cùng lúc, khiến một phần lớn request gặp cold start.

Một function có average duration 100 ms trong trạng thái warm có thể có p95 cao hơn nhiều khi cold start. Do đó, cần đo riêng:
- Initialization duration.
- Invocation duration.
- End-to-end latency.
- Tỷ lệ invocation trên environment mới.
- Tỷ lệ cold start theo phiên bản runtime và kích thước artifact.

### 3.6. Giảm cold start

Các biện pháp có thể gồm:
- Giảm kích thước package hoặc container image.
- Chỉ nạp dependency cần thiết.
- Tránh thực hiện truy vấn mạng hoặc công việc nặng trong initialization.
- Tái sử dụng client và connection pool khi environment được reuse.
- Chọn runtime và memory phù hợp.
- Dùng provisioned/warm capacity khi latency yêu cầu.
- Giữ initialization idempotent và có timeout.
- Tránh tải quá nhiều model hoặc thư viện khi chưa cần.

Không tối ưu bằng cách bỏ kiểm tra bảo mật, TLS hoặc xác thực. Cần đo trước và sau để biết bước nào thực sự chiếm thời gian.

## 4. Giới hạn mở rộng ở nhiều tầng

### 4.1. Account và region quota

Quota concurrency có thể áp dụng theo account, project, subscription, region hoặc dịch vụ. Nhiều function cùng chia sẻ quota nên một workload tăng tải có thể chiếm capacity của workload khác.

Cần lập inventory:
- Quota tổng.
- Quota dành riêng hoặc phân bổ cho function.
- Số concurrency đang dùng.
- Mức peak theo ngày/tuần.
- Quota cho deployment, VPC networking hoặc event source.
- Thời gian yêu cầu tăng quota và quy trình phê duyệt.

Không đợi đến khi production bị throttle mới gửi yêu cầu tăng quota. Quota phải được kiểm tra trước khi launch hoặc trước chiến dịch dự kiến có burst.

### 4.2. Function-level maximum concurrency

Một số nền tảng cho phép đặt giới hạn concurrency tối đa cho từng function hoặc từng alias/version. Giới hạn này giúp ngăn một function chiếm hết quota chung.

Tác động:
- Nếu đặt quá thấp, request bị throttle hoặc queue backlog tăng.
- Nếu đặt quá cao, function có thể làm quá tải database hoặc downstream.
- Nếu không đặt, một function có thể tiêu thụ phần lớn quota dùng chung.

Giới hạn nên dựa trên capacity của dependency, SLO và ngân sách. Cần phân biệt reserved concurrency, maximum concurrency, provisioned concurrency và concurrency thực tế; tên gọi và semantics khác nhau theo nhà cung cấp.

### 4.3. Giới hạn theo event source

Với queue hoặc stream, có thể có giới hạn:
- Số poller hoặc consumer.
- Maximum concurrent batches.
- Batch size.
- Maximum concurrency của event source mapping.
- Partition count hoặc shard count.
- Số message in-flight.
- Visibility timeout hoặc lease duration.

Tăng concurrency của function không nhất thiết tăng tốc độ đọc queue nếu event source hoặc partition là bottleneck.

### 4.4. Networking và IP capacity

Khi function kết nối vào private network, việc mở rộng có thể phụ thuộc:
- Số địa chỉ IP khả dụng trong subnet.
- Network interface hoặc attachment quota.
- NAT gateway và SNAT capacity.
- DNS resolver capacity.
- Firewall connection tracking.
- Số kết nối đồng thời tới private endpoint.

Một function có quota concurrency cao nhưng subnet cạn IP hoặc network attachment quota có thể không scale-out được. Cần kiểm tra network capacity như một phần của serverless capacity planning.

### 4.5. Dependency quota

Function có thể scale nhanh hơn database, cache hoặc API mà nó gọi. Các giới hạn thường gặp:
- Maximum database connections.
- Query throughput hoặc transaction rate.
- API requests per second.
- Queue publish/consume rate.
- Object storage request rate hoặc account quota.
- Rate limit của hệ thống đối tác.
- Connection limit của proxy.

Đừng chỉ tăng concurrency để xử lý queue backlog. Nếu downstream đã bão hòa, tăng số invocation chỉ làm tăng timeout, retry và chi phí.

## 5. Bảo vệ dependency khi concurrency tăng

### 5.1. Tính giới hạn connection pool

Giả sử mỗi execution environment mở một pool gồm P connection tới database. Nếu có N environment, số connection tiềm năng là:

**Tổng connection ≈ N × P**

Ví dụ:
- Database cho phép tối đa 500 connection.
- Dành 100 connection cho admin, migration và workload khác.
- Còn 400 connection cho function.
- Mỗi environment giữ pool 8 connection.

Số environment tối đa theo giới hạn connection là 400 / 8 = 50.

Nếu function có thể tạo 100 environment, database có thể bị quá tải dù function quota cho phép. Cần giảm pool size, dùng connection proxy, giới hạn concurrency hoặc thay đổi kiến trúc truy cập dữ liệu.

### 5.2. Connection reuse và proxy

Có thể giảm connection churn bằng:
- Tái sử dụng client trong execution environment.
- Dùng connection pool có giới hạn.
- Dùng database proxy hoặc pooling service nếu phù hợp.
- Đặt idle timeout và max lifetime.
- Đóng connection đúng cách.
- Tránh mở connection mới cho từng request nếu runtime hỗ trợ reuse an toàn.

Execution environment có thể bị freeze hoặc terminate bất kỳ lúc nào theo semantics của nền tảng. Không coi connection local là bền vững; xử lý reconnect và stale connection.

### 5.3. Backpressure

Backpressure là cơ chế điều tiết tốc độ nhận việc khi downstream không đủ capacity.

Ví dụ:
- Giới hạn concurrency của function.
- Giới hạn poller hoặc consumer của queue.
- Đưa request vào queue thay vì xử lý đồng bộ.
- Giảm batch size hoặc tốc độ phát message.
- Trả 429/503 có Retry-After khi phù hợp.
- Dùng circuit breaker khi dependency lỗi.
- Giới hạn số request đang chờ.

Backpressure giúp hệ thống giữ ổn định thay vì nhận nhiều việc hơn khả năng xử lý.

### 5.4. Retry và retry storm

Khi invocation timeout, nền tảng hoặc client có thể retry. Nếu nhiều request cùng thất bại, retry có thể làm tải tăng thêm đúng lúc hệ thống yếu nhất.

Cần:
- Giới hạn số lần retry.
- Exponential backoff và jitter.
- Phân biệt lỗi tạm thời với lỗi vĩnh viễn.
- Dùng idempotency key cho thao tác có side effect.
- Có dead-letter queue hoặc nơi lưu lỗi cuối cùng.
- Không retry vô hạn các request chắc chắn thất bại.
- Đặt timeout tổng và timeout dependency phù hợp.

Retry policy phụ thuộc trigger. Synchronous invocation, asynchronous invocation và event source polling có semantics retry khác nhau. Phải kiểm tra rõ nền tảng đang dùng.

### 5.5. Giới hạn đồng thời theo downstream

Nếu database chịu được 200 query đồng thời, function không nên mở 1.000 invocation cùng lúc rồi để database tự từ chối.

Có thể đặt concurrency cap thấp hơn giới hạn downstream và giữ headroom cho workload khác. Nếu nhiều function dùng chung database, cần tính tổng concurrency của tất cả function, không chỉ một function riêng lẻ.

## 6. Synchronous và asynchronous scaling

### 6.1. Synchronous invocation

Với HTTP/API hoặc synchronous invocation, caller chờ kết quả. Khi function không có capacity:
- Request có thể bị throttle.
- Gateway hoặc client có thể timeout.
- Caller có thể retry.
- Latency tăng khi cold start hoặc dependency chậm.

Cần xác định timeout của từng lớp: client, API gateway, function platform và dependency. Timeout tổng phải đủ để các bước có thể hoàn tất nhưng không giữ request vô hạn.

### 6.2. Asynchronous invocation

Với asynchronous invocation, sự kiện có thể được lưu trong hàng đợi nội bộ của nền tảng trước khi function xử lý.

Ưu điểm:
- Tách tốc độ gửi sự kiện khỏi tốc độ xử lý.
- Có thể hấp thụ burst trong giới hạn retention và queue capacity.
- Cho phép retry và xử lý lỗi riêng.

Rủi ro:
- Backlog có thể tăng nhanh.
- Event age tăng và vi phạm mục tiêu thời gian.
- Retry có thể tạo duplicate.
- Queue retention có thể hết hạn trước khi xử lý.
- Function có thể scale quá nhanh và làm quá tải downstream.

Theo dõi tuổi event, queue depth, retry, throttle và dead-letter count.

### 6.3. Queue-based load leveling

Queue có thể làm bộ đệm giữa producer và function:

~~~mermaid
flowchart LR
    P["Producers"] --> Q["Queue / Event buffer"]
    Q --> C["Pollers / Event source"]
    C --> F["Serverless functions"]
    F --> D["Database / Downstream"]
    F --> DLQ["Dead-letter queue"]
~~~

Producer có thể tiếp tục gửi trong khi worker xử lý theo capacity đã giới hạn. Tuy nhiên, queue không tạo capacity vô hạn; phải đặt retention, quota, giới hạn message, DLQ và cảnh báo backlog.

### 6.4. Batch size và concurrency

Event source có thể gom nhiều message vào một batch. Batch lớn:
- Giảm overhead invocation.
- Có thể tăng throughput.
- Làm tăng thời gian xử lý và memory cần thiết.
- Khi batch lỗi, có thể khiến nhiều message phải retry nếu không hỗ trợ partial batch response.

Batch nhỏ:
- Giảm phạm vi retry.
- Có thể tăng số invocation và overhead.
- Có thể làm tăng chi phí hoặc áp lực scheduler.

Chọn batch size theo thời gian xử lý, kích thước message, memory, timeout, ordering và semantics của queue.

### 6.5. Partial batch failure

Một số event source hỗ trợ phản hồi chỉ ra message thất bại trong batch để nền tảng retry phần đó. Nếu không cấu hình đúng, một message lỗi có thể khiến cả batch được giao lại.

Cần:
- Dùng partial batch response khi nền tảng và trigger hỗ trợ.
- Thiết kế xử lý idempotent.
- Theo dõi message retry count.
- Có poison-message handling và DLQ.
- Tránh để một message lỗi chặn cả partition hoặc queue vô thời hạn.

## 7. Quota, throttling và hành vi khi vượt giới hạn

### 7.1. Throttling là gì?

Throttling xảy ra khi nền tảng từ chối hoặc trì hoãn request do vượt một giới hạn concurrency, rate, quota hoặc capacity.

Triệu chứng:
- Lỗi throttling hoặc too many requests.
- HTTP 429 hoặc lỗi tương đương.
- Invocation không bắt đầu.
- Queue backlog tăng.
- Event age tăng.
- Caller timeout hoặc retry.
- Metric concurrent execution chạm giới hạn.

Cần phân biệt throttling ở function platform với rate limit của API gateway, downstream service hoặc identity provider.

### 7.2. Reserved concurrency và provisioned concurrency

Tên gọi cụ thể khác nhau giữa nền tảng, nhưng thường có hai khái niệm cần phân biệt:

- **Reserved concurrency:** dành riêng hoặc giới hạn phần concurrency cho function, giúp cô lập capacity hoặc giới hạn mức tiêu thụ.
- **Provisioned concurrency / pre-warmed capacity:** chuẩn bị sẵn execution environment để giảm cold start, thường có chi phí duy trì ngay cả khi ít request.

Một cấu hình dành riêng concurrency không nhất thiết làm environment ấm sẵn. Ngược lại, warm capacity không nhất thiết tăng quota tổng của account. Đọc đúng semantics của nhà cung cấp trước khi cấu hình.

### 7.3. Per-function cap

Đặt max concurrency có thể bảo vệ downstream nhưng tạo backlog hoặc throttling khi traffic vượt cap.

Ví dụ:
- Function nhận 500 request/giây.
- Dependency chỉ cho phép 100 request/giây.
- Giới hạn function để không vượt capacity dependency.
- Phần việc dư được queue hoặc từ chối có kiểm soát.

Nếu synchronous API không có queue, cần trả lỗi retryable hoặc response phù hợp để caller xử lý. Không nên để request chờ đến timeout ở nhiều tầng.

### 7.4. Quota increase

Khi cần tăng quota:
1. Đo peak và forecast traffic.
2. Xác định quota nào đang giới hạn.
3. Kiểm tra dependency và network capacity.
4. Yêu cầu tăng quota trước ngày triển khai.
5. Xác minh quota đã áp dụng đúng region/account.
6. Chạy load test có kiểm soát.
7. Theo dõi throttling và downstream sau khi tăng.

Tăng quota không có nghĩa phải dùng hết quota. Giới hạn function và downstream vẫn cần thiết.

## 8. Cold start, warm capacity và tối ưu khởi tạo

### 8.1. Những thành phần ảnh hưởng cold start

Cold start có thể chịu ảnh hưởng bởi:
- Runtime và phiên bản runtime.
- Kích thước package/image.
- Số dependency được import.
- Mã initialization.
- Network attachment.
- Secret retrieval và token exchange.
- TLS handshake và connection setup.
- Runtime compilation hoặc JIT.
- Nạp model hoặc dữ liệu cấu hình.

Cần phân tích initialization duration riêng với thời gian xử lý request.

### 8.2. Provisioned hoặc pre-warmed capacity

Khi cần latency ổn định, có thể giữ một số environment đã khởi tạo trước. Điều này phù hợp:
- API có SLO latency nghiêm ngặt.
- Traffic có mẫu dự đoán được.
- Các đợt campaign hoặc giờ cao điểm.
- Workload có cold start initialization nặng.

Hạn chế:
- Chi phí duy trì warm capacity.
- Có thể không bao phủ burst vượt mức đã chuẩn bị.
- Cần cập nhật warm environment khi deploy version mới.
- Có thể tạo nhiều capacity idle nếu forecast sai.

Warm capacity cần được sizing theo concurrency nền và mẫu burst; không thay thế autoscaling hoặc quota planning.

### 8.3. Initialization code phải an toàn

Initialization có thể chạy lại trên environment mới và có thể thất bại. Nên:
- Không tạo side effect không idempotent trong initialization.
- Không chạy migration database tự động ở mọi environment.
- Đặt timeout cho việc đọc secret và tạo connection.
- Xử lý credential refresh.
- Tái sử dụng client khi environment được reuse.
- Đóng hoặc tái tạo connection khi stale.
- Không lưu trạng thái nghiệp vụ duy nhất trong memory của environment.

### 8.4. Deploy mới và cold start

Một phiên bản mới có thể cần environment mới. Trong thời gian rollout, một phần request có thể gặp cold start hoặc chạy song song trên hai version.

Cần:
- Warm đúng version/alias đang nhận traffic nếu nền tảng hỗ trợ.
- Canary traffic trước khi chuyển toàn bộ.
- Kiểm tra tương thích schema và message.
- Theo dõi init duration và error rate sau deploy.
- Có rollback khi version mới tăng cold start hoặc timeout.

## 9. Autoscaling policy và điều khiển tải

### 9.1. Dựa trên metric phù hợp

Không chỉ dùng CPU hoặc request count. Với function serverless, có thể theo dõi:
- Concurrent executions.
- Invocation rate.
- Duration p50/p95/p99.
- Throttle count.
- Error rate.
- Init/cold-start duration.
- Queue depth và oldest event age.
- Event source poller concurrency.
- Downstream connection count và latency.
- Cost per request hoặc cost per successful job.

Chọn metric gắn với mục tiêu dịch vụ. Ví dụ, queue worker cần quan tâm tuổi message và backlog, còn API đồng bộ cần latency và tỷ lệ throttle.

### 9.2. Scale-out nhanh, scale-in thận trọng

Khi tải tăng, hệ thống cần thêm capacity kịp thời. Khi tải giảm, giảm capacity quá nhanh có thể khiến cold start lặp lại ngay khi traffic bật lại.

Có thể dùng:
- Stabilization window.
- Minimum warm capacity.
- Hysteresis giữa scale-out và scale-in.
- Scheduled capacity cho traffic dự đoán được.
- Giới hạn số environment thay đổi mỗi chu kỳ.
- Queue buffer để hấp thụ dao động.

### 9.3. Bảo vệ dependency bằng concurrency budget

Tạo một concurrency budget cho mỗi downstream.

Ví dụ:
- Database dành 250 connection cho API function.
- Mỗi environment mở tối đa 5 connection.
- Concurrency environment cap khoảng 50 theo giới hạn connection, trước khi trừ thêm headroom và nhu cầu khác.
- Nếu function xử lý nhiều request trong cùng environment, pool và concurrency phải được tính theo mô hình runtime thật.

Budget cần tính cả các function khác, scheduled job, migration và operator. Cần có một owner chịu trách nhiệm tổng hợp.

### 9.4. Circuit breaker và load shedding

Khi downstream chậm hoặc lỗi:
- Circuit breaker tạm ngừng gọi dependency.
- Load shedding từ chối request ít quan trọng hoặc quá tải.
- Queue hóa tác vụ có thể trì hoãn.
- Ưu tiên request quan trọng.
- Giới hạn retry và concurrency.
- Trả lỗi có thể xử lý được cho caller.

Mục tiêu là giữ phần hệ thống còn khỏe tiếp tục hoạt động, tránh một dependency kéo sập toàn bộ workload.

## 10. Ví dụ: API serverless có burst traffic

Một API xử lý yêu cầu đặt hàng có:
- Baseline 80 request/giây.
- Burst lên 600 request/giây trong 30 giây.
- Duration warm trung bình 200 ms.
- p95 duration 500 ms.
- Database chịu được tối đa 180 connection dành cho API.
- Mỗi environment có pool tối đa 3 connection.

Ước lượng ở baseline:
- Concurrency trung bình: 80 × 0,2 = 16.
- Với p95 duration 0,5 giây, phép tính bảo thủ hơn: 80 × 0,5 = 40.

Ước lượng ở burst:
- Concurrency trung bình theo duration warm: 600 × 0,2 = 120.
- Theo p95 duration: 600 × 0,5 = 300.

Giới hạn database:
- 180 connection / 3 connection mỗi environment = 60 environment tối đa theo pool.
- Nếu tạo 100 environment, pool có thể mở tới 300 connection, vượt budget.

Thiết kế cần cân nhắc:
1. Giới hạn pool nhỏ hơn nếu workload không cần nhiều connection.
2. Dùng database proxy hoặc connection multiplexing nếu phù hợp.
3. Giới hạn concurrency để bảo vệ database.
4. Dùng queue cho tác vụ không cần phản hồi ngay.
5. Kiểm tra tốc độ scale-out và warm capacity cho burst.
6. Load test với duration p95 và dependency chậm.
7. Đặt retry có backoff và idempotency cho thao tác đặt hàng.
8. Theo dõi throttle, latency, DB connections và queue age.

Không nên lấy phép tính 60 environment làm giới hạn cấu hình cuối cùng mà chưa tính connection của workload khác, headroom và concurrency thực tế bên trong environment.

## 11. Kiểm thử khả năng mở rộng

### 11.1. Test các dạng tải

Cần kiểm thử nhiều mẫu:
- Constant load: tải ổn định trong thời gian dài.
- Ramp-up: tăng dần request rate.
- Burst/spike: tăng đột ngột trong thời gian ngắn.
- Step load: chuyển giữa các mức tải cố định.
- Soak test: duy trì tải lâu để tìm leak hoặc quota tích lũy.
- Recovery test: giảm tải rồi tăng lại để quan sát scale-in/scale-out.
- Dependency degradation: làm database hoặc API chậm có kiểm soát.

### 11.2. Đo từ đầu đến cuối

Thu thập:
- Request rate gửi vào.
- Invocation accepted/started/completed.
- Concurrent execution.
- Environment creation và init duration.
- End-to-end latency.
- Throttle và error rate.
- Queue backlog và oldest event age.
- Downstream connection/throughput/latency.
- Chi phí theo request hoặc theo đợt test.

Chỉ đo function duration có thể bỏ qua thời gian chờ ở API gateway, queue, scheduler hoặc cold start.

### 11.3. Test vượt ngưỡng

Cần xác định hệ thống phản ứng thế nào khi:
- Chạm function concurrency cap.
- Chạm account/region quota.
- Event source không poll kịp.
- Database đạt connection limit.
- Network/IP capacity không đủ.
- Provisioned capacity thấp hơn burst.
- Secret manager hoặc identity provider chậm.
- Một dependency timeout và retry bắt đầu.

Mục tiêu không phải chỉ chứng minh function có thể scale cao, mà còn xác nhận hệ thống degrade có kiểm soát.

### 11.4. Không tạo tải gây ảnh hưởng production

Load test nên chạy trong môi trường được kiểm soát hoặc có phê duyệt rõ ràng. Dùng dữ liệu thử, giới hạn chi phí, đặt ngưỡng dừng và thông báo owner của dependency. Không chạy spike test tùy tiện lên database hoặc API đối tác production.

## 12. Quan sát và cảnh báo

| Chỉ số | Ý nghĩa | Khi cần cảnh báo |
|---|---|---|
| Concurrent executions | Số invocation đang chạy | Tiến gần cap hoặc quota |
| Throttles | Invocation bị từ chối do giới hạn | Tăng đột biến hoặc vượt SLO |
| Invocation duration | Thời gian xử lý | p95/p99 tăng liên tục |
| Init duration | Thời gian khởi tạo environment | Cold start tăng sau deploy hoặc burst |
| Invocation errors | Tỷ lệ lỗi trong function | Vượt ngưỡng theo workload |
| Queue depth | Số message chờ | Tăng liên tục |
| Oldest event age | Tuổi event chưa xử lý | Tiến gần retention hoặc SLO |
| Downstream connections | Kết nối tới DB/API | Gần connection limit |
| Dependency latency | Độ trễ dịch vụ phụ thuộc | Tăng đồng thời với concurrency |
| Scale-out rate | Tốc độ cấp environment | Nhu cầu tăng nhanh hơn khả năng cấp |
| Provisioned capacity utilization | Mức dùng warm capacity | Thiếu warm capacity hoặc dư thừa kéo dài |
| Cost per successful invocation | Chi phí cho kết quả thành công | Tăng bất thường |

Cảnh báo nên dựa trên xu hướng và thời gian kéo dài, tránh báo động chỉ vì một spike ngắn không ảnh hưởng SLO.

## 13. Tối ưu chi phí và hiệu năng

### 13.1. Concurrency cao không đồng nghĩa hiệu quả cao

Tăng concurrency có thể tăng throughput, nhưng cũng có thể:
- Tăng số environment và chi phí.
- Tạo nhiều connection tới database.
- Tăng contention và retry.
- Làm latency p99 xấu đi.
- Tăng số request bị downstream từ chối.

Tối ưu cần dựa trên chi phí cho một request thành công và SLO, không chỉ số invocation tối đa.

### 13.2. Memory và CPU ảnh hưởng duration

Ở nhiều nền tảng, cấu hình memory có thể ảnh hưởng lượng CPU hoặc network capacity được cấp. Tăng memory đôi khi làm function chạy nhanh hơn và tổng thời gian tính phí thấp hơn, dù mức giá mỗi đơn vị thời gian cao hơn.

Cần benchmark nhiều mức memory với workload thật và đo:
- Duration.
- CPU saturation.
- Memory peak.
- Cold start.
- Error/timeout.
- Cost per successful invocation.

### 13.3. Tối ưu batch và concurrency

Với queue worker, batch lớn hơn có thể giảm overhead invocation nhưng tăng thời gian xử lý và phạm vi retry. Với API đồng bộ, concurrency cao có thể giảm wait nhưng gây tải lên database.

Chọn batch size, concurrency và memory cùng nhau. Thay một tham số mỗi lần trong benchmark để hiểu tác động.

### 13.4. Chọn warm capacity theo lịch tải

Provisioned/warm capacity có thể hữu ích cho giờ cao điểm có thể dự đoán. Có thể:
- Tăng trước chiến dịch.
- Giảm sau giờ cao điểm.
- Dùng minimum warm capacity cho baseline.
- Để autoscaler xử lý phần burst vượt mức.

Cần so sánh chi phí warm capacity với tổn thất do cold start và yêu cầu latency.

## 14. Những sai lầm thường gặp

**Đồng nhất request rate với concurrency.** Concurrency phụ thuộc cả tốc độ đến và thời gian xử lý. Duration tăng có thể làm concurrency tăng dù request rate không đổi.

**Giả định serverless scale vô hạn.** Account quota, function cap, scaling rate, network và downstream đều có giới hạn.

**Chỉ kiểm tra maximum concurrency.** Scaling rate và cold start có thể khiến hệ thống không đạt mức tối đa đủ nhanh.

**Tăng concurrency mà không tính database connection.** Mỗi environment có thể tạo pool riêng, làm database cạn connection.

**Dùng provisioned concurrency như quota increase.** Warm capacity và giới hạn concurrency có semantics khác nhau; cần xác minh theo nhà cung cấp.

**Đặt concurrency cap quá thấp.** Request có thể bị throttle hoặc queue age tăng dù downstream còn capacity.

**Retry ngay lập tức.** Retry storm làm tải tăng và kéo dài sự cố. Dùng backoff, jitter và giới hạn số lần.

**Không phân biệt synchronous và asynchronous.** Hai mô hình có hành vi throttle, retry và buffering khác nhau.

**Không đo cold start riêng.** Average duration có thể che giấu initialization latency của environment mới.

**Scale-out function nhưng quên network quota.** Subnet IP, NAT, network interface và DNS có thể trở thành bottleneck.

**Không test dependency degradation.** Function có thể đạt concurrency mục tiêu nhưng làm database hoặc API đối tác quá tải.

**Chỉ tối ưu chi phí mỗi invocation.** Một invocation rẻ nhưng thất bại, retry nhiều hoặc làm tăng latency có thể khiến tổng chi phí cao hơn.

## 15. Checklist thiết kế concurrency và scaling

### Nhu cầu và capacity

- [ ] Đo arrival rate, duration trung bình và p95/p99.
- [ ] Ước lượng concurrency bằng arrival rate × duration.
- [ ] Xác định concurrency per-instance theo runtime/platform.
- [ ] Tính số environment cần và headroom.
- [ ] Phân biệt maximum capacity với scaling rate.
- [ ] Xác minh quota account, region, function và event source.

### Cold start và scaling

- [ ] Đo init duration và tỷ lệ cold start.
- [ ] Kiểm tra startup code, package/image và dependency.
- [ ] Xác định nhu cầu scale-to-zero hay warm capacity.
- [ ] Cấu hình provisioned/warm capacity nếu latency yêu cầu.
- [ ] Kiểm thử burst, ramp-up và deployment version mới.
- [ ] Đặt stabilization và scale-in policy phù hợp.

### Bảo vệ dependency

- [ ] Tính tổng connection từ mọi environment.
- [ ] Giới hạn pool và concurrency theo capacity database.
- [ ] Kiểm tra API rate limit, queue, NAT và subnet IP.
- [ ] Dùng backpressure và circuit breaker.
- [ ] Đặt retry có backoff, jitter và idempotency.
- [ ] Có queue/DLQ cho công việc có thể xử lý bất đồng bộ.

### Vận hành và kiểm thử

- [ ] Theo dõi concurrency, throttle, duration và init duration.
- [ ] Theo dõi queue depth và oldest event age.
- [ ] Theo dõi downstream latency và connection usage.
- [ ] Kiểm thử vượt quota và dependency chậm trong môi trường kiểm soát.
- [ ] Đặt ngưỡng dừng load test và ngân sách chi phí.
- [ ] Đo cost per successful invocation.
- [ ] Có runbook khi throttle, backlog hoặc quota bị chạm.

## 16. Ghi nhớ

- Concurrency là số invocation đang chạy đồng thời; request rate là số invocation đến trong một giây.
- Ước lượng cơ bản: concurrency trung bình bằng arrival rate nhân duration trung bình.
- Concurrency per-instance và concurrency toàn function/account là hai giới hạn khác nhau.
- Maximum capacity không cho biết tốc độ tạo environment; cần xem scaling rate và cold start.
- Burst traffic có thể vượt khả năng scale-out tức thời dù quota tổng còn đủ.
- Cold start gồm nhiều bước khởi tạo; cần đo riêng init duration và invocation duration.
- Reserved concurrency, maximum concurrency và provisioned concurrency có semantics khác nhau theo nền tảng.
- Concurrency phải được giới hạn theo capacity của database, API và network dependency.
- Queue, backpressure, retry có backoff và idempotency giúp xử lý tải đột biến an toàn hơn.
- Load test phải kiểm tra cả throttle, cold start, quota, dependency và chi phí.
- Mục tiêu là đáp ứng SLO với capacity và chi phí có thể kiểm soát.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Invocation | Một lần thực thi hàm serverless. |
| Execution environment | Môi trường runtime được nền tảng cấp để chạy function. |
| Concurrency | Số invocation đang được xử lý đồng thời. |
| Per-instance concurrency | Số invocation một execution environment có thể xử lý cùng lúc. |
| Arrival rate | Tốc độ request hoặc event đến hệ thống. |
| Throughput | Số request hoặc job hoàn tất trong một đơn vị thời gian. |
| Duration | Thời gian một invocation xử lý. |
| Little's Law | Quan hệ giữa số công việc trung bình, tốc độ đến và thời gian ở trong hệ thống. |
| Scaling rate | Tốc độ nền tảng có thể tăng hoặc giảm capacity. |
| Cold start | Thời gian khởi tạo environment mới trước khi xử lý invocation. |
| Warm capacity | Execution environment được chuẩn bị sẵn để giảm thời gian khởi tạo. |
| Scale-to-zero | Giảm số environment đang chạy về 0 khi không có tải. |
| Throttling | Từ chối hoặc trì hoãn request khi vượt giới hạn. |
| Quota | Giới hạn tài nguyên hoặc tốc độ do nền tảng áp dụng. |
| Reserved concurrency | Phần concurrency được dành riêng hoặc giới hạn cho function theo semantics của nền tảng. |
| Provisioned concurrency | Capacity được khởi tạo trước để giảm cold start. |
| Backpressure | Cơ chế điều tiết tốc độ nhận việc theo capacity xử lý. |
| Retry storm | Nhiều client retry đồng loạt làm tăng tải khi hệ thống đang lỗi. |
| Exponential backoff | Tăng dần thời gian chờ giữa các lần retry. |
| Jitter | Thành phần ngẫu nhiên thêm vào thời gian retry để tránh đồng bộ. |
| Idempotency key | Khóa giúp nhận diện và ngăn xử lý lặp gây tác động trùng. |
| Event source mapping | Cấu hình liên kết event source với function để polling và chuyển event. |
| Dead-letter queue (DLQ) | Queue lưu message không xử lý thành công sau các lần thử theo policy. |
| Connection pool | Nhóm kết nối được tái sử dụng tới database hoặc dịch vụ khác. |
| Circuit breaker | Cơ chế tạm ngừng gọi dependency đang lỗi để bảo vệ hệ thống. |
