# Tránh gateway thành điểm nghẽn hoặc điểm lỗi đơn

## Mục tiêu bài học

Trong kiến trúc Microservices, API Gateway là cửa vào chung cho web, mobile, đối tác hoặc các client bên ngoài. Gateway thường thực hiện định tuyến, kết thúc TLS, xác thực ở biên, giới hạn tốc độ, kiểm tra kích thước request, quan sát và một số chuyển đổi giao thức. Đây là vị trí có giá trị lớn vì cung cấp **một điểm kiểm soát thống nhất**. Nhưng nếu triển khai không đúng, gateway cũng có thể trở thành **điểm nghẽn hiệu năng (bottleneck)** hoặc **điểm lỗi đơn (single point of failure, SPOF)**.

Hai rủi ro cần phân biệt:

- **Điểm nghẽn:** Gateway hoặc một phụ thuộc của nó không xử lý kịp tải, làm tăng latency, queue, timeout và tỷ lệ lỗi, dù hệ thống downstream vẫn còn tài nguyên.
- **Điểm lỗi đơn:** Chỉ một instance, một thành phần hạ tầng, một cấu hình hoặc một phụ thuộc có thể làm toàn bộ luồng truy cập bị gián đoạn khi nó lỗi.

Một gateway có thể **vừa là điểm nghẽn vừa là điểm lỗi đơn**. Ngược lại, ba replica gateway vẫn có thể cùng chết do cấu hình sai, Redis dùng chung bị lỗi hoặc một Load Balancer duy nhất không hoạt động. Vì vậy không thể kết luận hệ thống đã sẵn sàng cao chỉ từ số pod.

Sau bài học, bạn có thể:

1. Xác định nơi gateway nằm trên critical path và nhận diện các failure domain.
2. Thiết kế nhiều replica, cân bằng tải, phân tán theo vùng lỗi và health check phù hợp.
3. Hiểu cách scale gateway dựa vào độ trễ, connection, CPU, băng thông và lượng request.
4. Dùng timeout, rate limit, bulkhead, circuit breaker và retry budget để tránh nghẽn dây chuyền.
5. Giảm phụ thuộc đồng bộ và loại business logic không cần thiết khỏi gateway.
6. Thiết kế deployment, cập nhật cấu hình, quan sát và kiểm thử lỗi để tránh gateway thành SPOF.

## 1. Gateway nằm trên đường đi quan trọng

Ví dụ:

~~~text
Browser / Mobile / Partners
             |
             v
         API Gateway
         /    |     \
        v     v      v
    Catalog  Orders  Payments
       |        |       |
      DB       DB      PSP
~~~

Một lỗi ở Catalog chỉ nên làm ảnh hưởng khả năng lấy danh mục trong phạm vi phù hợp. Nhưng nếu **gateway bị mất hoàn toàn**, những API còn khỏe mạnh cũng không được client truy cập. Tác động lan rộng theo vị trí trên đường đi, không chỉ theo kích thước source code.

Điều này đúng cả khi gateway là:
- Reverse proxy như NGINX/Envoy.
- Managed API Gateway trên cloud.
- Spring Cloud Gateway hoặc service tự xây.
- Ingress controller/Kubernetes Gateway.
- API management platform có authentication, policy và analytics.

Tên sản phẩm không tự bảo đảm availability. Điều quan trọng là **cấu trúc deployment, failure isolation, chính sách xử lý tải và phụ thuộc runtime**.

### 1.1. Gateway không phải nơi duy nhất có thể trở thành SPOF

Các điểm chung cần kiểm tra:

- DNS và cơ chế phân giải tên.
- Global/regional Load Balancer.
- TLS certificate và secret store.
- Service discovery hoặc cấu hình route.
- Identity provider và JWKS endpoint.
- Redis hoặc database dùng chung cho rate limiting/session.
- Logging/tracing collector nếu đường request đợi chúng.
- Network egress, NAT gateway hoặc proxy outbound.
- Control plane cấu hình và quy trình rollout.
- Cluster/node/zone nơi tất cả replica cùng chạy.

Nhiều gateway instance đặt chung một node có thể cùng chết khi node đó lỗi. Nhiều gateway instance đặt khác node nhưng cùng một Availability Zone vẫn có thể bị gián đoạn do lỗi ở mức zone.

### 1.2. Bottleneck không nhất thiết là CPU đạt 100%

Gateway có thể nghẽn vì:
- Chạm giới hạn số kết nối hoặc file descriptor.
- Connection pool tới một upstream quá nhỏ.
- Worker thread bị chặn bởi thư viện blocking.
- TLS handshake và certificate verification tốn CPU.
- Proxy buffer chứa quá nhiều request/response lớn.
- Network bandwidth hoặc packets-per-second bị giới hạn.
- Rate-limit store, DNS hoặc identity provider trả chậm.
- Queue chờ lâu dù CPU chưa cao.
- Retry từ gateway làm downstream quá tải.
- Một route chậm giữ tài nguyên dùng chung và làm hỏng route khác.

Vì vậy chỉ xem biểu đồ CPU của gateway là chưa đủ.

## 2. Thiết kế mục tiêu: không một instance duy nhất

Một topology cơ bản:

~~~text
                    External clients
                           |
                           v
                   Load Balancer
                           |
           +---------------+---------------+
           |               |               |
           v               v               v
      Gateway A        Gateway B        Gateway C
        Zone 1           Zone 2           Zone 3
           |               |               |
           +---------------+---------------+
                           |
                    Service discovery
                           |
                     Internal services
~~~

Mục tiêu:
- Một gateway pod/process lỗi thì request mới được chuyển sang instance khác.
- Một node lỗi không làm mọi gateway instance biến mất.
- Một zone lỗi không làm mất hết khả năng phục vụ, nếu hạ tầng hỗ trợ đa zone.
- Các instance không phụ thuộc vào state cục bộ không thể chuyển giao.
- Load Balancer nhận diện instance sẵn sàng và đưa khỏi vòng định tuyến khi cần.

Điều kiện kỹ thuật thực sự phụ thuộc môi trường. Managed cloud Load Balancer thường có cơ chế HA của nhà cung cấp, nhưng cần xác minh phạm vi region/zone, quota và giới hạn dịch vụ thay vì mặc định nó không bao giờ lỗi.

### 2.1. Active-active khác active-passive

**Active-active:** Nhiều gateway instance cùng nhận traffic. Nó phân tán tải và sử dụng tài nguyên, nhưng đòi hỏi route/config/policy đồng nhất và cơ chế cân bằng tải phù hợp.

**Active-passive:** Một instance hoặc một site làm việc; một hệ thống dự phòng nhận traffic khi primary lỗi. Cách này có thể đơn giản trong một số bối cảnh nhưng phụ thuộc vào phát hiện lỗi và chuyển đổi. Thời gian failover và rủi ro cấu hình ở standby cần được đo.

Ở mức instance gateway stateless, active-active thường phù hợp để vừa scale vừa chịu lỗi. Ở mức region, active-active có thể đòi hỏi dữ liệu, định tuyến toàn cầu và chính sách vận hành phức tạp hơn; active-passive đôi khi dễ quản lý hơn.

### 2.2. Không đặt session hoặc routing state chỉ trong RAM của một gateway

Nếu gateway lưu login session, mapping request hoặc quota quan trọng trong bộ nhớ riêng một replica, request kế tiếp đi qua replica khác có thể cho kết quả khác.

Những lựa chọn:
- Token stateless có xác minh chữ ký và thời hạn hợp lý, khi thích hợp.
- Shared session store được thiết kế HA.
- Idempotency/business state thuộc service sở hữu nghiệp vụ, không chỉ nằm trong gateway.
- Cookie/session affinity nếu thực sự cần, nhưng không coi sticky session là phương án HA thay cho state sharing.

Giữ gateway stateless giúp thay replica, scale và failover dễ hơn. Tuy nhiên token stateless vẫn phải xử lý key rotation, revocation và authorization theo yêu cầu bảo mật.

## 3. Phân biệt health check và availability thực

Một pod chạy và trả 200 cho /health chưa chắc phục vụ request tốt. Có thể:
- Event loop hoặc thread pool nghẽn.
- Gateway không tải được route config.
- Connection pool tới upstream cạn.
- Bộ phận xác thực bị timeout.
- Proxy đang trả 502 cho phần lớn client.

Nên phân biệt:

- **Liveness:** process có còn hoạt động đủ để không cần restart không?
- **Readiness:** instance có sẵn sàng nhận request mới không?
- **Startup:** ứng dụng đã khởi tạo đủ trước khi kiểm tra liveness/readiness chưa?
- **End-to-end synthetic check:** người dùng có đi qua gateway và một API đại diện thành công không?
- **Dependency health:** thông tin phụ thuộc nào đang lỗi hoặc chậm?

### 3.1. Không để readiness bị phụ thuộc quá mức

Nếu readiness gateway trả lỗi chỉ vì một service ít quan trọng đang down, Load Balancer có thể rút **tất cả gateway instance** khỏi traffic. Khi đó sự cố một downstream trở thành outage toàn hệ thống.

Readiness thường nên phản ánh năng lực cốt lõi của **chính gateway** để nhận và route request. Health của downstream có thể được quan sát riêng, dùng circuit breaker/fallback theo từng route. Nếu một dependency là điều kiện bắt buộc thực sự để gateway phục vụ an toàn, chính sách readiness cần được nêu rõ và kiểm chứng trong tình huống lỗi diện rộng.

### 3.2. Liveness quá nhạy tạo restart storm

Nếu liveness probe phụ thuộc vào một service ngoài đang chậm, mọi replica gateway có thể liên tục restart, làm tăng tải startup và khiến recovery khó hơn. Liveness không nên bị đồng nhất với mọi downstream health.

### 3.3. Cân bằng tải khi instance mất readiness

Load Balancer cần:
- Ngừng gửi **request mới** tới instance không sẵn sàng.
- Cho request đang xử lý thời gian hoàn tất khi rolling update hoặc shutdown, nếu contract cho phép.
- Hỗ trợ connection draining hoặc graceful termination phù hợp.
- Không gửi lại command có side effect một cách mù quáng chỉ vì connection bị cắt.

Graceful shutdown không thể cam kết mọi in-flight request đều hoàn tất: vẫn cần idempotency và khả năng phục hồi ở service nghiệp vụ.

## 4. Scale ngang theo năng lực xử lý thực

Một replica gateway không có một giá trị RPS cố định trong mọi trường hợp. Capacity phụ thuộc:

- Kích thước request và response.
- TLS, HTTP/2, WebSocket/SSE hoặc gRPC.
- Tỷ lệ request cần xác thực/chuyển đổi.
- Số connection mới so với keep-alive.
- Workload parse JSON, validate schema hoặc transform headers.
- Latency của upstream và timeout.
- Network throughput, CPU/memory, connection pool và runtime.
- Số tenant, policy và độ phức tạp route.
- Tỷ lệ request bị giới hạn hoặc cache hit.

Ví dụ một gateway xử lý tốt 20.000 request/giây khi response nhỏ không có nghĩa cũng đạt mức đó khi proxy file 10 MB hoặc stream sống hàng phút.

### 4.1. Capacity planning theo ngân sách

Một phương pháp:
1. Thu thập RPS ở giờ cao điểm và peak burst.
2. Đo phân phối kích thước request/response, không chỉ giá trị trung bình.
3. Đo concurrent connections và thời gian tồn tại connection.
4. Benchmark mỗi replica với cấu hình thật.
5. Xác định vùng vận hành an toàn theo latency SLO và error budget.
6. Giữ headroom để một instance hoặc zone có thể mất mà không quá tải instance còn lại.
7. Test autoscaling và phục hồi trong khi traffic đang tăng.

Có thể ước lượng năng lực tối thiểu theo:
- Peak requests per second / safe RPS per replica.
- Connection concurrency / safe connections per replica.
- Network bytes per second / safe bandwidth per replica.
- CPU, memory, queue hoặc event-loop saturation.

Số replica cần đáp ứng **đồng thời các ràng buộc**, không chỉ phép chia RPS.

### 4.2. Hiệu ứng khi mất một replica

Giả sử ba gateway chia tải gần đều. Khi một instance mất, hai instance còn lại phải nhận lại phần tải của instance đó. Nếu trước sự cố cả ba đã chạy sát công suất tối đa, lỗi một instance có thể kéo theo timeout và quá tải cho hai instance còn lại.

Do đó thiết kế HA cần **headroom** và khả năng load shedding, không chỉ có nhiều instance.

### 4.3. Autoscaling không phải cơ chế chống sự cố tức thời

HPA/KEDA hoặc các cơ chế scale khác có độ trễ đo chỉ số, ra quyết định, khởi tạo pod, warm-up và nhận traffic. Nếu traffic tăng đột ngột trong vài giây, autoscaler chưa chắc phản ứng kịp.

Nên:
- Duy trì số replica tối thiểu và dự phòng đủ.
- Scale theo tín hiệu liên quan đến bottleneck, có thể kết hợp CPU, request rate, connection và latency nếu hạ tầng hỗ trợ.
- Cân nhắc tốc độ scale up/down và ngưỡng chống dao động.
- Đo thời gian startup, warm-up route cache và TLS.
- Không scale down quá nhanh khi còn stream hoặc connection dài.

## 5. Ranh giới mạng và connection pool

Gateway có hai phía kết nối:
- Client → Gateway.
- Gateway → Upstream service.

Một nghẽn có thể phát sinh ở bất kỳ phía nào.

Ví dụ:

~~~text
10.000 clients
       |
       v
     Gateway
       |
       | connection pool max = 50
       v
   Orders service
~~~

Nếu gateway có 50 upstream connections nhưng request chờ lâu, queue phía gateway có thể tăng mạnh dù Orders còn khả năng xử lý. Ngược lại, tăng connection pool vô hạn có thể làm Orders cạn connection và database.

Các cấu hình cần đo:
- Số upstream connections tối đa.
- Connect timeout và response timeout.
- Idle/keep-alive lifetime.
- HTTP/2 multiplexing nếu được hỗ trợ.
- Pending acquisition queue và queue timeout.
- Số connection per host/route và global.
- DNS caching và refresh khi service discovery đổi địa chỉ.
- Khả năng xử lý half-open connection hoặc network reset.

### 5.1. Không chặn event-loop bằng công việc blocking

Với các gateway dùng non-blocking I/O như Spring Cloud Gateway WebFlux, nếu gọi SDK blocking, JDBC query hoặc thực hiện CPU-heavy JSON transformation ngay trên event-loop, một số ít request chậm có thể cản trở rất nhiều request khác.

Không nên:
- Gọi Thread.sleep trong filter.
- Thực hiện network call blocking mà không có giới hạn.
- Serialize payload lớn trên event-loop không kiểm soát.
- Đọc toàn bộ request body vào bộ nhớ chỉ để kiểm tra một header.

Nếu một tác vụ bắt buộc blocking, có thể cô lập nó vào executor phù hợp với giới hạn concurrency, nhưng cần đánh giá có nên để tác vụ đó ở gateway hay chuyển vào service chuyên trách.

## 6. Không biến gateway thành nơi chứa business logic

Gateway nên tập trung vào **edge concerns** như:
- Định tuyến và load balancing.
- TLS termination và các chính sách giao thức.
- Authentication ở biên và xác minh token.
- Rate limiting, quota hoặc request size limit.
- Header normalization và correlation ID.
- Logging/metrics/tracing.
- Chính sách CORS, một số bảo vệ edge và version routing.

Nghiệp vụ nên thuộc các service sở hữu domain:
- Tính giá và khuyến mại.
- Điều kiện chấp nhận đơn.
- Giữ tồn kho.
- Quy tắc thanh toán hoặc hoàn tiền.
- Quản lý trạng thái giao hàng.

Nếu gateway phải gọi ba service để tính tổng tiền, giữ tồn và chọn chương trình khuyến mại cho mọi request, nó trở thành một orchestrator nghiệp vụ bất đắc dĩ, vừa tăng latency vừa làm mọi release phụ thuộc vào gateway.

### 6.1. API composition và Backend for Frontend (BFF)

Một số giao diện cần một endpoint tổng hợp dữ liệu từ nhiều service. Có thể dùng BFF hoặc API composition service có ownership rõ, thay vì nhét toàn bộ logic tổng hợp vào một gateway toàn cục.

~~~text
Mobile/Web Clients
        |
        v
     Gateway
       /   \
      v     v
   BFF-A   BFF-B
    / \      / \
Catalog Orders Payments Profile
~~~

Điều này không tự loại bỏ rủi ro ở BFF. Nhưng nó giúp **cô lập tải và trách nhiệm** theo client/use case. Một thay đổi ở trải nghiệm mobile không bắt buộc làm thay đổi filter chung trên đường đi của mọi API.

### 6.2. Hạn chế synchronous fan-out tại gateway

Nếu một request gateway đồng thời gọi 10 backend, latency có thể bị chi phối bởi backend chậm nhất, và một request người dùng có thể tạo 10 request downstream. Khi fan-out kết hợp retry, hệ thống dễ gây request amplification.

Nếu cần fan-out:
- Đặt deadline tổng và timeout riêng cho từng dependency.
- Có giới hạn concurrency.
- Phân loại dữ liệu bắt buộc so với optional.
- Có fallback hợp lệ cho phần optional.
- Trả partial result rõ trong API contract nếu nghiệp vụ cho phép.
- Quan sát số downstream calls mỗi request.

## 7. Timeout và deadline: tránh giữ request quá lâu

Một request có thể đi qua:

~~~text
Client -> Gateway -> BFF -> Orders -> Inventory
~~~

Nếu mỗi hop tự dùng timeout 10 giây mà không tôn trọng deadline của caller, request downstream có thể tiếp tục lâu sau khi người dùng ngừng chờ.

Thiết kế tốt nên có:
- Connect timeout phù hợp.
- Response/idle timeout.
- Total deadline cho toàn bộ request.
- Propagation của correlation ID và deadline khi khả thi.
- Thời gian dành cho từng hop đủ nhỏ trong tổng budget.
- Giới hạn request body processing time và thời gian stream.

Không dùng một timeout cho mọi loại traffic. GET danh mục nhỏ, SSE connection dài và file download có đặc điểm khác nhau.

### 7.1. Timeout không chứng minh side effect thất bại

Nếu gateway timeout sau khi gửi POST /payments, Payments có thể đã xử lý thành công. Gateway không được tự động phát lại request với idempotency key mới. Những API có side effect cần stable operation ID và cơ chế retry/tra cứu trạng thái do service nghiệp vụ sở hữu.

Gateway có thể chuyển timeout thành lỗi chuẩn hoặc trạng thái chưa xác định theo contract, nhưng không được tự suy diễn nghiệp vụ bị từ chối.

## 8. Retry budget: gateway không nên nhân tải vô hạn

Retry có ích khi lỗi ngắn hạn, nhưng là nguồn của retry storm nếu dùng thiếu kiểm soát.

Ví dụ:
- Client retry 3 lần.
- Gateway retry 3 lần.
- BFF retry 3 lần.

Một request gốc có thể dẫn tới nhiều attempts ở backend. Nếu backend đã quá tải, việc nhân request càng làm nó khó phục hồi.

### 8.1. Quy tắc thiết kế retry

- Quy định **tầng chịu trách nhiệm retry** cho từng loại thao tác.
- Chỉ retry lỗi/operation có semantics an toàn, đặc biệt GET idempotent hoặc POST có idempotency được bảo vệ.
- Dùng exponential backoff và jitter, giới hạn số attempts.
- Giữ tổng deadline và retry budget.
- Không retry khi client đã hết deadline mà nghiệp vụ không cần xử lý tiếp.
- Tôn trọng Retry-After hoặc gợi ý từ backend khi phù hợp.
- Theo dõi số retries mỗi request gốc.
- Không retry đồng thời nhiều route nếu điều đó làm quá tải dependency dùng chung.

Circuit breaker giúp tạm ngừng gọi một upstream đang lỗi để giảm tải và fail nhanh. Nó không thể thay thế idempotency hoặc trả lời liệu command trước đã thực hiện side effect chưa.

### 8.2. Hedged requests

Một số hệ thống gửi một yêu cầu đọc tới nhiều replica để giảm tail latency. Nhưng hedging làm tăng tải và có thể gây tác dụng phụ nếu dùng cho command. Chỉ cân nhắc với operation read-only an toàn, deadline rõ, quota chặt và bằng chứng đo được; không dùng mặc định cho tạo đơn hoặc thanh toán.

## 9. Rate limiting và load shedding

Rate limit giúp ngăn một client/tenant hoặc một burst gây nghẽn tài nguyên chung.

Các chiều giới hạn:
- Theo API key/user/tenant/IP đáng tin.
- Theo route, HTTP method hoặc nhóm dịch vụ.
- Theo RPS và burst.
- Theo concurrent in-flight requests.
- Theo số bytes upload/download.
- Theo cost của thao tác, ví dụ export hoặc query nặng.
- Theo tổng workload khi hệ thống tiến gần capacity.

Ví dụ một chính sách minh họa:

| Nhóm API | Chiến lược |
| --- | --- |
| GET public catalog | Giới hạn RPS/burst, hỗ trợ cache |
| POST /orders | Giới hạn concurrency và idempotency |
| POST /payments | Quota chặt, xác thực, không retry mù |
| GET /reports/export | Ít job đồng thời, có hàng đợi |
| SSE/WebSocket | Giới hạn số connection và lifetime |
| Upload file lớn | Quota bytes, giới hạn concurrency và thời gian |

### 9.1. Local vs distributed rate limiter

**Local limiter:** Mỗi gateway replica tự đếm quota. Dễ vận hành và ít phụ thuộc, nhưng nếu một tenant gửi request phân tán trên nhiều replica, quota toàn cụm có thể vượt ngưỡng dự kiến.

**Distributed limiter:** Dùng shared store/service để áp quota nhất quán hơn trên toàn cụm. Nhưng chính store đó có thể thành bottleneck hoặc SPOF.

Cần cân nhắc:
- Độ chính xác quota cần tới mức nào.
- Tác động khi shared limiter bị lỗi.
- Có cache/lease quota cục bộ để giảm round trip không.
- Khi không thể xác minh quota, **fail open** hay **fail closed** theo mức độ rủi ro.
- Sự khác biệt giữa giới hạn bảo vệ tài nguyên và giới hạn bảo mật/tài chính.

Với API có yêu cầu ngăn gian lận hoặc giới hạn tài chính, không nên tự chuyển sang fail open chỉ để giữ availability. Với một số endpoint public ít nhạy cảm, degraded limiter có thể chấp nhận được nếu có guardrail khác. Chính sách phải được xác nhận bởi nghiệp vụ và security.

### 9.2. Load shedding trước khi queue vô hạn

Nếu gateway đã vượt capacity, việc tiếp tục nhận rồi xếp hàng không giới hạn làm latency và memory tăng, khiến tất cả client chịu ảnh hưởng. Có thể:
- Trả 429 khi client vượt quota.
- Trả 503 khi toàn hệ thống không còn capacity.
- Giới hạn hàng đợi và in-flight requests.
- Ưu tiên đường xử lý trọng yếu có chính sách công bằng.
- Cung cấp Retry-After khi đúng ngữ nghĩa.
- Bảo vệ endpoint quan trọng khỏi batch export và request lớn.

Trả lỗi sớm, nhất quán và có thể phục hồi thường tốt hơn cho toàn hệ thống so với timeout dây chuyền.

## 10. Bulkhead: một route chậm không được kéo sập mọi route

Bulkhead là cách tách ngân sách tài nguyên theo luồng hoặc nhóm phụ thuộc. Nếu một backend xử lý chậm, không để nó chiếm hết connection/queue/thread dùng cho các backend khác.

Ví dụ:

~~~text
                    API Gateway
                /       |        \
               v        v         v
         Orders pool Catalog pool Reports pool
            max A       max B       max C
               |          |           |
               v          v           v
            Orders      Catalog     Reporting
~~~

Những tài nguyên có thể cô lập:
- Connection pool theo upstream.
- Số request đồng thời theo route.
- Queue limit và thời gian chờ lấy connection.
- Thread/executor nếu có công việc blocking.
- Memory buffer.
- Circuit breaker và timeout policy theo upstream.

Điều này giúp khi Reporting chậm hoặc export tốn bandwidth, API đặt hàng vẫn có cơ hội phục vụ trong ngân sách riêng. Mỗi pool phải được sizing theo tải thực và sự phụ thuộc hạ tầng bên dưới.

### 10.1. Tránh shared state không cần thiết

Một filter chung dùng lock toàn cục, một event-loop bị blocking hoặc một connection pool chung quá nhỏ có thể vô tình gắn mọi route lại với nhau. Bulkhead cần được kiểm chứng bằng load test: làm chậm một upstream và đo độ trễ của route không liên quan.

## 11. Caching: giảm tải có chủ đích

Cache có thể giảm số request phải tới backend:
- CDN cache cho nội dung tĩnh/public.
- Gateway cache cho GET có semantics an toàn.
- Client cache với ETag/Cache-Control.
- Application/service cache cho dữ liệu được sở hữu đúng nơi.

Nhưng cache ở gateway cũng mang rủi ro:
- Cache key thiếu tenant/user làm rò rỉ dữ liệu.
- TTL quá dài gây stale business data.
- Thêm cache store dùng chung tạo phụ thuộc mới.
- Cache miss đồng loạt sau deploy hoặc expiry tạo traffic spike.
- Cache stampede khi nhiều request cùng nạp một key.
- Không thể cache mọi command có side effect.

Nên xác định cache key theo đủ tham số công khai, quyền truy cập và variation cần thiết; dùng TTL/invalidation có contract, cache bypass cho dữ liệu nhạy cảm nếu cần.

### 11.1. Cache không thay cho scale

Nếu 90% GET được cache nhưng 10% miss đều đi tới một backend đã quá tải, gateway vẫn có thể nghẽn khi cache lạnh. Capacity plan cần thử cả cache-warm và cache-cold, khi store cache lỗi và khi có invalidation lớn.

## 12. Kiểm soát request/response lớn và streaming

Gateway có thể proxy file, JSON lớn, SSE, WebSocket và gRPC. Mỗi loại có rủi ro khác.

- Upload file: giới hạn body bytes, multipart size, timeout và concurrency.
- Download lớn: tránh buffer toàn bộ file trong heap.
- SSE/WebSocket: connection sống lâu, cần giới hạn kết nối và idle policy.
- gRPC streaming: flow control, message size, deadline và max concurrent streams.
- JSON lớn: tránh parse/serialize lại chỉ để đọc một trường nhỏ.
- Nén: kiểm soát chi phí CPU và kích thước sau giải nén nếu gateway xử lý body.

Một gateway non-blocking có thể vẫn hết bộ nhớ nếu filter gom toàn bộ request body vào buffer.

### 12.1. Không nên truyền file cực lớn qua gateway nếu không cần

Một giải pháp:
1. Client yêu cầu tạo upload/download intent qua gateway.
2. Service nghiệp vụ xác thực, kiểm tra quyền và cấp signed URL giới hạn thời hạn.
3. Client tải trực tiếp lên/xuống object storage.
4. Service xác minh file hoàn tất, checksum, quota và trạng thái.

Mô hình này giảm băng thông và thời gian giữ kết nối qua gateway, nhưng signed URL, quyền truy cập, expiry và audit cần được thiết kế an toàn.

## 13. Authentication và những phụ thuộc dễ làm gateway thành SPOF

Gateway thường xác minh JWT hoặc gọi identity provider. Nếu mỗi request phải gọi một remote identity service và service đó chậm, toàn gateway có thể bị ảnh hưởng.

Các chiến lược phù hợp tùy bảo mật:
- Xác minh JWT ký số cục bộ dựa trên public keys được phân phối an toàn.
- Cache JWKS/public key với TTL, rotation và fallback được thiết kế rõ.
- Dùng bounded connection pool/timeout nếu cần introspection token.
- Cô lập resource của đường authentication khỏi route khác khi khả thi.
- Giám sát lỗi xác thực, key refresh và độ trễ identity provider.

**Không được bỏ kiểm tra chữ ký hoặc quyền truy cập để tránh outage.** Nếu cần fail closed khi không thể xác minh token, đó là một quyết định bảo mật hợp lệ dù ảnh hưởng availability. Có thể cải thiện HA của identity provider hoặc key distribution thay vì bỏ bảo vệ.

### 13.1. Gateway xác thực không thay authorization nghiệp vụ

Gateway có thể xác minh token và các quyền coarse-grained, nhưng service sở hữu resource vẫn phải thực thi authorization liên quan owner/tenant và business state. Không biến một lỗi gateway thành cơ hội truy cập thẳng service nội bộ không có bảo vệ.

### 13.2. External dependencies phải có failure policy

Những phụ thuộc như Redis, service discovery, config server, JWKS, audit collector hoặc tracing collector cần câu trả lời:

- Nếu nó chậm 5 giây, request có phải chờ 5 giây không?
- Nếu nó down, gateway còn route được không?
- Có cache last-known-good configuration an toàn không?
- Có dữ liệu nào không được phép dùng cũ vì rủi ro bảo mật không?
- Có giới hạn retry và circuit breaker không?
- Có alert và runbook phục hồi không?

Không nên để gửi log/trace đồng bộ là điều kiện để trả response cho mọi API, trừ khi đó là một yêu cầu nghiệp vụ/compliance được xác định rõ.

## 14. Triển khai gateway trong Kubernetes: ví dụ minh họa

Một triển khai có thể dùng nhiều replica và phân tán theo zone/node. Ví dụ YAML rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: api-gateway
      containers:
        - name: gateway
          image: example.invalid/api-gateway:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
~~~

Đây là **mẫu cấu trúc để đọc hiểu**, không phải manifest production dùng nguyên bản. Các health endpoints phụ thuộc cấu hình Spring Boot Actuator; image là placeholder. Cần cân nhắc:
- Cluster có đủ zone và node thật không.
- Với ScheduleAnyway, Kubernetes **cố gắng** phân tán nhưng không đảm bảo cứng ở mọi tình huống.
- Nếu muốn ràng buộc cứng, cần hiểu hậu quả khi thiếu capacity và pod không schedule được.
- Bổ sung PodDisruptionBudget, rolling update, autoscaling, security context và graceful shutdown phù hợp.
- Resource requests/limits cần đo theo workload.
- Readiness/liveness phải kiểm tra đúng loại sức khỏe, không phụ thuộc toàn bộ backend.

### 14.1. PodDisruptionBudget và rollout

PDB giúp hạn chế số pod đồng thời bị gián đoạn trong các **voluntary disruptions** được Kubernetes hỗ trợ. Nó không ngăn được crash, mất node hoặc outage của cả zone.

Rolling update cần:
- Số replica tối thiểu đủ.
- maxUnavailable/maxSurge thích hợp.
- Readiness đúng và startup time được tính.
- Graceful termination/draining cho request đang chạy.
- Quy trình rollback khi error rate tăng.

Không nên tuyên bố PDB là bằng chứng hệ thống chịu được mất một Availability Zone. Điều đó cần kiểm thử độc lập.

### 14.2. HPA và metrics

HPA có thể scale theo CPU hoặc các custom metrics nếu hệ thống hỗ trợ. CPU một mình chưa thể phản ánh network saturation, số connection dài hoặc queue pending. Nên đo và chọn tín hiệu scale phù hợp, tránh dao động liên tục khi request spike ngắn.

Nếu có ba replica nhưng tất cả thường xuyên dùng 95% capacity, hệ thống chưa có nhiều dư địa chịu lỗi. Chính sách scale phải gắn với SLO và khả năng chịu mất instance/zone.

## 15. Cấu hình route và rollout an toàn

Gateway có thể gặp sự cố toàn diện chỉ vì một cấu hình route sai được phân phối đồng loạt. Ví dụ:
- Route catch-all đè lên route cụ thể.
- RewritePath làm mọi request thành 404.
- Global filter mới ném exception.
- Token validation config sai làm mọi request bị 401.
- Certificate hoặc secret hết hạn.
- Thay đổi timeout/rate limit quá chặt.
- Config server cung cấp file thiếu hoặc không tương thích với phiên bản app.

Các biện pháp:
1. Lưu cấu hình theo version và có review.
2. Validate schema và route conflicts trước rollout.
3. Test synthetic requests với các endpoint trọng yếu.
4. Canary rollout trên một phần nhỏ traffic nếu hạ tầng hỗ trợ.
5. So sánh 4xx/5xx, p95/p99 và throughput giữa bản mới/cũ.
6. Tự động dừng hoặc rollback khi vượt ngưỡng đã định.
7. Giữ last-known-good config khi phù hợp và an toàn.
8. Có kế hoạch rotate TLS certificates/keys trước khi hết hạn.

### 15.1. Blue-green, canary và backward compatibility

Gateway có thể cùng lúc phục vụ các API/client với nhiều phiên bản. Một deployment mới cần tương thích với backend đang chạy, và backend mới cần tương thích với gateway cũ trong giai đoạn rolling update.

Nếu đổi header, path, authentication hoặc request transformation, hãy kiểm thử cả tổ hợp version trong khoảng deploy lệch, không yêu cầu tất cả service release đồng thời nếu mục tiêu là deploy độc lập.

### 15.2. Một control plane lỗi không nên làm data plane ngừng ngay

Ở các hệ thống có control plane quản lý route/policy, cần biết:
- Gateway có tiếp tục route theo cấu hình đã nhận khi control plane tạm thời down không?
- Cấu hình đó có đủ mới và an toàn không?
- Secret/certificate rotation hoạt động thế nào khi control plane lỗi?
- Khi control plane phục hồi, các replica có nhận cùng version không?

Một data plane có khả năng tiếp tục với cấu hình đã được xác minh giúp giảm SPOF, nhưng các chính sách security có thể yêu cầu fail closed cho những trường hợp nhất định. Phải cân bằng theo risk model, không dùng fail-open bừa bãi.

## 16. Multi-region và disaster recovery

Nhiều replica trong một region chưa xử lý outage toàn region. Với yêu cầu availability cao, có thể cần multi-region:

~~~text
                  Global traffic routing
                      /            \
                     v              v
                 Region A        Region B
                 LB + Gateways   LB + Gateways
                    |                |
                 Services A       Services B
~~~

Những vấn đề cần quyết định:
- RTO (thời gian phục hồi mục tiêu) và RPO (mất dữ liệu chấp nhận).
- Active-active hay active-passive ở cấp region.
- DNS/global load balancer và health routing có thời gian chuyển đổi bao lâu.
- TLS certificates, secrets và config có đồng bộ hợp lệ không.
- Các service và database có sẵn sàng ở region dự phòng không.
- Session/token có dùng được ở region khác không.
- Dữ liệu có yêu cầu cư trú theo địa lý không.
- Nếu region B còn gateway nhưng Payments chỉ tồn tại ở region A, failover có thực sự phục vụ checkout được không?

**Multi-region chỉ ở gateway không tạo availability end-to-end nếu các dependency thiết yếu vẫn nằm ở một region.** Cần xác định độ sẵn sàng của toàn bộ business path.

### 16.1. DNS failover có độ trễ

DNS TTL, resolver caching và connection đang mở có thể làm traffic chuyển chậm hơn kỳ vọng. Không nên hứa chuyển region “ngay lập tức” nếu chưa thử thực tế. Với một số hệ thống, global load balancing có health routing và failover được quản lý phù hợp hơn DNS đơn giản.

## 17. Graceful degradation và cô lập dịch vụ lỗi

Gateway không thể tự làm một service lỗi trở lại khỏe mạnh, nhưng có thể **hạn chế ảnh hưởng sang các route khác**.

Ví dụ:
- Catalog đang lỗi: các API đặt hàng dựa trên dữ liệu đã được xác minh có thể vẫn hoạt động theo policy.
- Reporting chậm: giới hạn concurrency/route này để Orders không bị nghẽn.
- Recommendation service lỗi: BFF có thể bỏ qua gợi ý tùy chọn nếu API contract cho phép.
- Payments không rõ kết quả: checkout phải giữ trạng thái PENDING/UNKNOWN phù hợp, không tự báo thành công.

Các nguyên tắc:
- Fallback chỉ dùng khi semantics hợp lệ và có quyền sử dụng dữ liệu.
- Một route không được chiếm hết connection/queue của route khác.
- Error response nên chuẩn hóa nhưng giữ nguyên business error code.
- Khi upstream lỗi diện rộng, hạn chế retries để tránh làm hồi phục khó hơn.
- Giữ các luồng read-only hoặc ít phụ thuộc nếu nghiệp vụ cho phép.
- Không bỏ authentication/authorization chỉ vì muốn dịch vụ tiếp tục trả 200.

Graceful degradation phải được thiết kế ở cả gateway, BFF và các service sở hữu nghiệp vụ; gateway một mình không thể quyết định mọi fallback.

## 18. Observability: tìm điểm nghẽn thật

Những nhóm chỉ số quan trọng:

| Nhóm | Ví dụ |
| --- | --- |
| Traffic | RPS, concurrent requests, new connections/s |
| Latency | p50/p95/p99 gateway latency, upstream latency, queue wait |
| Errors | 4xx/5xx theo route và nguyên nhân, 502/503/504 |
| Resource | CPU, memory, GC, event-loop delay, thread usage |
| Network | Throughput bytes/s, retransmits, TLS handshake time |
| Pool | Upstream active/idle connections, pending acquisition |
| Protection | 429, rate-limit decisions, circuit breaker state, retries |
| Availability | Ready replicas, LB unhealthy targets, zone distribution |
| Streaming | Active long-lived streams, bytes buffered, write stalls |
| Dependencies | Auth/JWKS, Redis, config server, DNS latency/error rate |
| Deployments | Config version, canary error-rate delta, rollback events |

Nên gắn labels theo service, route template, upstream, region/zone và status class. Tránh dùng path có user ID hoặc order ID làm metric label vì cardinality có thể tăng không kiểm soát.

### 18.1. Tách độ trễ gateway và backend

Nếu request mất 900 ms:
- Gateway xử lý 20 ms?
- Chờ lấy connection 300 ms?
- Backend xử lý 550 ms?
- Network 30 ms?

Chỉ nhìn tổng latency không cho biết điểm cần cải thiện. Distributed tracing và metrics về upstream timing, queue wait giúp xác định bottleneck.

### 18.2. SLI và SLO

Có thể đặt mục tiêu dựa trên:
- Success rate của request hợp lệ trên critical routes.
- p95/p99 latency qua gateway và toàn end-to-end path.
- Tỷ lệ request bị gateway tự tạo lỗi 5xx.
- Tỷ lệ route phục vụ sau khi mất một instance/zone.
- Thời gian phát hiện và phục hồi lỗi.
- Error budget để quyết định tốc độ rollout/thay đổi.

Mục tiêu phải phân biệt lỗi gateway với business rejection hợp lệ (ví dụ 409 do đơn không thể hủy). Không gộp toàn bộ 4xx thành outage.

### 18.3. Synthetic monitoring

Có thể gửi request định kỳ qua cùng đường client thật: DNS → LB → Gateway → một route đại diện. Điều này giúp phát hiện certificate hết hạn, route config sai hoặc LB lỗi mà dashboard CPU chưa báo.

Probe cần đủ nhẹ, không tạo side effect nghiệp vụ hoặc tải không cần thiết. Với các tuyến có yêu cầu bảo mật, synthetic identity và secret phải được quản lý an toàn.

## 19. Kiểm thử tải và lỗi ở nhiều cấp

Không nên chỉ thử gateway với một endpoint Hello World. Test phải phản ánh:
- Kích thước request/response.
- TLS và authentication.
- Phân phối endpoint (Catalog, Orders, Payments, Export).
- Burst và sustained traffic.
- Long-lived connections/streams.
- Slow clients và slow upstream.
- Retry/backoff của client thật.
- Number of replicas, autoscaling và LB topology.

### 19.1. Kịch bản load test

1. **Baseline:** tăng RPS tới khi latency SLO bắt đầu bị vi phạm.
2. **Burst:** traffic tăng mạnh trong vài giây; theo dõi queue và load shedding.
3. **Large bodies:** upload/download lớn và kiểm tra memory buffer.
4. **Slow upstream:** một route trả chậm; đo ảnh hưởng lên route khác.
5. **Retry storm:** upstream trả 503; bảo đảm gateway/client không nhân tải vô hạn.
6. **Long-lived streams:** nhiều SSE/WebSocket/gRPC connections đồng thời.
7. **Cold cache:** giảm cache hit để xem backend chịu tải không.
8. **Uneven load balancing:** một vài replica nhận nhiều connection hơn các replica khác.

### 19.2. Kịch bản failure injection

| Sự cố giả lập | Kỳ vọng |
| --- | --- |
| Kill một gateway pod | LB loại target lỗi, các pod còn lại đáp ứng được tải |
| Restart/rollout liên tiếp | Graceful drain, không rớt phần lớn traffic |
| Mất một node | Replica còn trên node khác phục vụ |
| Mất một zone | Phục vụ trong phạm vi HA cam kết nếu hạ tầng hỗ trợ |
| Redis rate limiter timeout | Áp chính sách fail mode đã thiết kế |
| Identity/JWKS endpoint chậm | Không làm event-loop bị block vô hạn; giữ security |
| Config server down | Data plane xử lý theo policy phù hợp |
| Một upstream trả 5xx | Circuit/bulkhead bảo vệ route khác |
| Gateway CPU hoặc memory cao | Scale/load shedding thay vì queue vô hạn |
| Certificate lỗi/hết hạn | Alert sớm và có quy trình rotation/rollback |
| Client đóng stream giữa chừng | Resource được cleanup và không giữ connection rò rỉ |
| DNS/global LB failover | Traffic chuyển theo RTO đã được kiểm chứng |

Sau mỗi test phải ghi nhận **tác động thực**, thời gian phục hồi, error rate, dữ liệu bị ảnh hưởng và bài học cấu hình. Không coi test đạt chỉ vì có ba replica được khai báo.

## 20. Quy trình xử lý khi gateway là điểm nghẽn

Khi thấy p99 gateway tăng hoặc 502/503 nhiều, nên tiếp cận theo dữ liệu:

1. **Xác định phạm vi:** tất cả routes hay một route? Một region hay toàn hệ thống?
2. **Tìm vị trí chờ:** event-loop, queue, TLS, connection acquisition, upstream hoặc authentication?
3. **Kiểm tra các ngưỡng:** in-flight, CPU, memory, file descriptor, network, pool, bytes buffered.
4. **Phân biệt nguyên nhân với hậu quả:** backend chậm có thể làm gateway queue đầy; không phải cứ tăng gateway replicas là giải quyết.
5. **Giảm tải an toàn:** rate limit, load shedding, tắt/bớt export không thiết yếu, hạn chế retries.
6. **Khôi phục capacity:** scale thêm nếu bottleneck nằm ở gateway và upstream còn khả năng chịu tải.
7. **Cô lập route lỗi:** bulkhead hoặc circuit breaker theo dependency.
8. **Rà soát cấu hình vừa thay:** route, filter, timeout, cert, pool, rate limit.
9. **Đo sau khắc phục:** success rate, latency, số connection, retry và error budget.
10. **Ghi bài học:** capacity headroom, alert, runbook và test regression tương ứng.

Không nên mặc định restart toàn bộ gateway nếu chưa biết nguyên nhân; restart hàng loạt có thể khiến connection đứt, cache lạnh và traffic dồn lên instance còn lại.

## 21. Các sai lầm thiết kế thường gặp

### “Đặt gateway trước mọi service là có HA”

Không đúng. Một instance gateway duy nhất là SPOF rõ ràng. Nhiều instance chưa đủ nếu cùng node/zone, dùng chung phụ thuộc bắt buộc hoặc cùng lỗi cấu hình.

### “Có ba pod thì không thể outage”

Lỗi cùng nguyên nhân có thể làm cả ba pod chết: secret sai, route config sai, dependency dùng chung down hoặc memory leak xuất hiện khi traffic tăng. Cần phân tán failure domain và kiểm thử.

### “Gateway CPU thấp nên không thể nghẽn”

Connection pool, event-loop blocking, network quota, queue và auth provider latency có thể là bottleneck khi CPU thấp.

### “Retry càng nhiều càng tốt”

Retry có thể làm downstream đang yếu quá tải hơn. Retry cần budget, idempotency và backoff; tránh nhiều tầng retry chồng nhau.

### “Circuit breaker sẽ bảo đảm mọi request thành công”

Circuit breaker giúp fail nhanh và tránh gọi upstream đang lỗi, không làm backend khỏe lại; cũng không xác nhận trạng thái side effect của request đã gửi.

### “Global filter có thể chứa mọi business rule”

Đưa logic tính giá, đặt hàng, thanh toán vào gateway làm tăng coupling và blast radius. Giữ domain rules tại service sở hữu nghiệp vụ, dùng BFF/application composition có chủ đích khi cần.

### “Gateway có thể cache mọi response GET”

Không đúng với dữ liệu nhạy cảm, trạng thái theo user hoặc GET phụ thuộc authorization. Cache key và policy phải xét tenant/user và freshness.

### “Khi Redis limiter down thì bỏ hết rate limit”

Có thể gây overload hoặc vi phạm security policy. Fail-open/fail-closed phải quyết định theo loại endpoint và threat model.

### “Tăng timeout giải quyết hết 504”

Nếu backend hoặc pool đã nghẽn, tăng timeout có thể giữ connection lâu hơn và làm queue tăng. Cần tìm nơi bị chậm và kiểm soát tài nguyên.

### “Liveness phải kiểm tra tất cả downstream”

Một downstream lỗi có thể khiến toàn bộ gateway restart. Tách readiness, liveness và dependency health theo trách nhiệm.

### “Mất một gateway instance thì LB sẽ retry POST an toàn”

Không thể suy ra. POST có thể đã tạo side effect, nên phải có idempotency và status recovery theo nghiệp vụ.

### “Multi-region gateway đủ để checkout không gián đoạn”

Nếu Payments, Inventory hoặc dữ liệu thiết yếu chỉ nằm ở region đã lỗi, multi-region ở gateway chưa mang lại availability end-to-end.

## 22. Architecture Decision Record mẫu

~~~text
Title:
  Triển khai API Gateway active-active, phân tán multi-zone.

Context:
  Gateway xử lý toàn bộ HTTP API của website và mobile.
  Tăng traffic theo giờ cao điểm; một instance lỗi có thể làm gián đoạn hệ thống.

Decision:
  - Tối thiểu ba replica, trải trên các node/zone phù hợp.
  - Gateway stateless với route config được version và rollout theo canary.
  - Load Balancer dùng readiness và connection draining.
  - Route-level concurrency limits, upstream pool limits và timeouts.
  - Rate limit theo tenant/route; policy rõ khi limiter store lỗi.
  - Không đưa business orchestration vào global gateway filter.
  - Observability và synthetic monitoring qua đường vào thật.

Trade-offs:
  - Chi phí runtime và giám sát cao hơn một instance.
  - Distributed rate limit và route config phức tạp hơn.
  - Có thể cần dự phòng capacity khi mất một zone.
  - Gateway HA không thay thế HA của auth, DNS, LB và backend.

Evidence / Revisit:
  - Theo dõi p99, 5xx, RPS, active connections và zone health.
  - Test mất instance, mất zone và dependency outage.
  - Rà soát khi traffic/route/workload thay đổi đáng kể.
~~~

Mẫu này chỉ minh họa cách ghi lý do kiến trúc; không áp đặt con số replica hoặc chính sách fail mode cho mọi hệ thống.

## 23. Checklist thực hành

Trước khi đưa Gateway vào production hoặc nâng mức chịu lỗi:

- [ ] Có sơ đồ đầy đủ client → DNS/LB → gateway → services?
- [ ] Đã xác định mọi dependency đồng bộ trên critical path?
- [ ] Có ít nhất hơn một instance ở các failure domain phù hợp với mục tiêu HA?
- [ ] Load Balancer định tuyến bằng readiness và có graceful drain?
- [ ] Liveness không phụ thuộc vô điều kiện vào mọi downstream?
- [ ] Gateway có state cục bộ nào khiến failover bị sai?
- [ ] Route/config/secret/certificate được version, validate và rollback?
- [ ] Số replica và headroom được tính theo tải khi mất một instance/zone?
- [ ] Autoscaling dựa trên chỉ số thật và không scale down quá nhanh?
- [ ] Connection pool, pending queue và concurrency giới hạn theo route/upstream?
- [ ] Có timeout/deadline phù hợp và retry budget thống nhất?
- [ ] Circuit breaker, bulkhead và load shedding được áp dụng nơi cần?
- [ ] Có quota theo tenant, bytes và long-lived connections?
- [ ] Shared Redis/config/JWKS/DNS có HA và failure policy rõ?
- [ ] Không chứa domain logic phức tạp trong global gateway filters?
- [ ] Có tránh buffer payload lớn và hỗ trợ streaming an toàn?
- [ ] Authentication/authorization không bị bỏ qua khi dependency lỗi?
- [ ] Có p95/p99, 5xx, pool/queue, retry, saturation và synthetic monitoring?
- [ ] Đã thử kill pod, mất node/zone, slow upstream, Redis lỗi, config sai?
- [ ] Có runbook và owner xử lý gateway outage/rollout failure?

## 24. Bài tập tình huống

### Bài tập 1 — Gateway có ba replica nhưng cùng node

Ba gateway pod đều chạy trên một worker node. Khi node chết, API ngừng hoạt động dù các service còn khỏe mạnh.

**Câu hỏi:** Tại sao số replica không đủ? Cách khắc phục?

**Gợi ý:** Cần anti-affinity/topology spread theo node/zone, capacity ở các node khác và test failover thực tế. Replicas chỉ bảo vệ lỗi riêng lẻ nếu failure domains thực sự tách biệt.

### Bài tập 2 — CPU thấp nhưng p99 cao

Gateway CPU 30%, nhưng latency p99 tới vài giây và queue pending connections tăng. Orders service CPU vẫn thấp.

**Câu hỏi:** Bạn sẽ đo gì trước khi tăng replicas?

**Gợi ý:** Upstream connection pool, connection acquisition time, event-loop delay, pending queue, network throughput và timeout policy. Một pool max quá nhỏ có thể gây nghẽn khi CPU thấp.

### Bài tập 3 — Identity provider bị timeout

Mỗi request vào Gateway đều gọi remote introspection API. Khi identity provider chậm, tất cả route tăng latency.

**Câu hỏi:** Các cách cải thiện có thể là gì?

**Gợi ý:** Xem token validation offline qua keys được phân phối an toàn, introspection pool/timeouts, JWKS cache/rotation, HA của identity provider. Không bỏ xác thực để đạt uptime.

### Bài tập 4 — Reporting làm Orders chậm

Một báo cáo lớn tạo nhiều streaming connections. Sau đó endpoint POST /orders tăng 503 dù Orders backend còn tài nguyên.

**Câu hỏi:** Cần bảo vệ ở đâu?

**Gợi ý:** Route-level connection/concurrency budgets, bytes quota, backpressure, separate export job và bulkhead. Đo network/pool usage theo route.

### Bài tập 5 — Retry storm

Client, gateway và BFF đều retry POST /payments khi response bị timeout.

**Câu hỏi:** Rủi ro và kế hoạch sửa?

**Gợi ý:** Retry amplification và duplicate side effect. Dùng stable idempotency key ở Payments, một retry owner, query status, retry budget, backoff và deadline tổng.

### Bài tập 6 — Readiness phụ thuộc Catalog

Readiness gateway gọi Catalog. Catalog outage làm mọi gateway pod thành NotReady, nên cả Payments API cũng không truy cập được.

**Câu hỏi:** Vì sao xảy ra outage diện rộng?

**Gợi ý:** Readiness đang kiểm tra sức khỏe downstream không thiết yếu. Cần tách gateway readiness khỏi dependency health và dùng route-level protection.

### Bài tập 7 — Rollout cấu hình sai

Một global filter mới gây lỗi 401 cho mọi route. Hệ thống có nhiều replica nhưng tất cả nhận cấu hình mới cùng lúc.

**Câu hỏi:** Vì sao multi-replica không cứu được?

**Gợi ý:** Đây là correlated failure qua config. Cần version, synthetic test, canary/blue-green, rollout control và rollback nhanh.

### Bài tập 8 — Mất cả region

Gateway đã multi-region nhưng Inventory chỉ có ở region A. Region A mất, traffic chuyển sang region B; checkout vẫn lỗi.

**Câu hỏi:** Bạn sẽ thay đổi kiến trúc ra sao?

**Gợi ý:** Xác định end-to-end business path và RTO/RPO. Thiết kế data/service failover phù hợp với consistency, region và compliance; không chỉ nhân bản gateway.

## 25. Kết luận

API Gateway tạo một điểm vào thống nhất nhưng cũng tập trung traffic và các phụ thuộc vào cùng vị trí. Để tránh gateway thành **điểm nghẽn**, cần kiểm soát connection, queue, event-loop, byte size, retry, concurrency và capacity bằng số liệu đo được. Để tránh nó thành **điểm lỗi đơn**, cần nhiều instance ở các failure domain phù hợp, Load Balancer/health check chính xác, state có thể chia sẻ, rollout an toàn và kế hoạch cho các phụ thuộc như auth, DNS, config, certificate và rate-limit store.

Các biện pháp phải làm việc cùng nhau: **replicas mà không có headroom vẫn quá tải khi mất một instance; autoscaling mà không có load shedding vẫn có thể thua traffic burst; circuit breaker mà không có idempotency vẫn không giải quyết side effect chưa rõ; multi-region gateway mà backend không sẵn sàng vẫn không tạo availability end-to-end**.

Nguyên tắc quan trọng nhất: **Gateway nên là lớp truy cập và bảo vệ có thể thay thế, mở rộng và phục hồi, không phải nơi duy nhất nắm quy tắc nghiệp vụ hoặc tài nguyên không thể dự phòng.**
