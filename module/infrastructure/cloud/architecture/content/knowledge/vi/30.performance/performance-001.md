# Xây dựng ngân sách độ trễ cho luồng đầu cuối

Người dùng cảm nhận hiệu năng qua thời gian từ lúc thực hiện một hành động đến khi nhận được kết quả hữu ích. Một API có thể phản hồi nhanh ở từng service nhưng toàn bộ luồng vẫn chậm vì gateway, xác thực, network, database, cache, queue hoặc dịch vụ bên ngoài cộng dồn độ trễ. Tối ưu một endpoint riêng lẻ không đủ nếu chưa hiểu tổng thời gian của user journey và phần nào đang tiêu thụ ngân sách.

**Ngân sách độ trễ (latency budget)** là giới hạn thời gian được phân bổ cho toàn bộ request hoặc một luồng nghiệp vụ, sau đó chia thành mục tiêu cho từng thành phần và khoảng dự phòng. Nó biến yêu cầu như “trang checkout phải nhanh” thành những mục tiêu có thể đo: thời gian đầu cuối tối đa, deadline của mỗi dependency, queue wait, database work, serialization và response. Ngân sách cũng giúp quyết định có nên gọi một service phụ đồng bộ, chuyển tác vụ sang nền, dùng cache hay từ chối sớm khi đã hết thời gian.

Một ngân sách tốt phải dựa trên trải nghiệm người dùng, SLO và phân bố latency thực tế. Không nên cộng các số trung bình rồi kết luận request sẽ đạt p95; tail latency của từng hop, concurrency, retry và tương quan tải có thể làm luồng đầu cuối chậm hơn nhiều. Cần định nghĩa deadline, đo bằng trace, phân tích percentile và điều chỉnh theo bằng chứng.

Bài học thuộc phần **Hiệu năng** của học phần thiết kế kiến trúc cloud. Trọng tâm là xây dựng ngân sách độ trễ cho luồng đầu cuối, liên kết mục tiêu người dùng với kiến trúc network, compute, dữ liệu và vận hành, đồng thời cân bằng hiệu năng, độ tin cậy, bảo mật, khả năng mở rộng và chi phí theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Xác định user journey, SLI và latency SLO phù hợp.
- Phân rã thời gian đầu cuối thành các hop, queue và giai đoạn xử lý.
- Phân bổ deadline cho gateway, service, database và dependency bên ngoài.
- Phân biệt latency trung bình, percentile, tail latency và thời gian chờ.
- Truyền deadline qua các service và kiểm soát retry/concurrency.
- Đo latency bằng tracing, metrics, logs và load test.
- Tìm bottleneck, điều chỉnh ngân sách và thiết kế degraded path.

## 1. Bắt đầu từ trải nghiệm người dùng

Latency budget không nên bắt đầu bằng câu hỏi “database được bao nhiêu mili giây?”. Hãy bắt đầu bằng hành động người dùng cần hoàn tất và thời điểm kết quả trở nên hữu ích.

Ví dụ:

- Mở danh sách lịch hẹn và nhìn thấy dữ liệu.
- Tìm kiếm sản phẩm và nhận trang kết quả có thể tương tác.
- Xác nhận booking và biết booking đã được lưu hay chưa.
- Thanh toán và nhận trạng thái rõ ràng.
- Tải báo cáo và nhận file hoặc operation ID.

Các hành động có độ nhạy thời gian khác nhau. Trang tìm kiếm tương tác thường cần phản hồi nhanh hơn báo cáo lớn. Tác vụ bất đồng bộ có thể không cần hoàn thành trong request, nhưng phải có thời hạn xử lý và trạng thái để người dùng theo dõi.

### Định nghĩa latency SLI và SLO

- **SLI (Service Level Indicator):** chỉ số đo trải nghiệm, ví dụ tỷ lệ request kết thúc trong 400 ms.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI, ví dụ 99% request tìm kiếm hoàn tất trong 400 ms trong cửa sổ đo.
- **Deadline:** thời điểm muộn nhất mà một request hoặc bước xử lý còn có giá trị.
- **Latency budget:** giới hạn tổng và phần phân bổ cho từng bước để đạt mục tiêu đó.

Ví dụ SLO minh họa:

| User journey | Latency objective | Đo ở đâu |
| --- | --- | --- |
| Mở trang booking | p95 dưới 500 ms | API gateway đến response body hoàn chỉnh |
| Search catalog | p95 dưới 300 ms | Search API, không tính thời gian render phía client nếu SLO chỉ dành cho backend |
| Xác nhận booking | p99 dưới 1.2 giây | Từ lúc API nhận request đến khi ghi nhận kết quả commit hoặc trạng thái pending hợp lệ |
| Gửi email xác nhận | 95% trong 2 phút | Từ event được chấp nhận đến provider acknowledgement |
| Báo cáo ngày | Hoàn tất trước 08:00 | Từ lịch chạy đến dataset/report publish |

Các con số là ví dụ để thiết kế bài tập, không phải chuẩn chung. Tổ chức cần xác định SLO từ user research, business criticality, baseline và chi phí đạt mục tiêu.

### Chọn điểm bắt đầu và điểm kết thúc

Một phép đo phải có ranh giới rõ:

- Client-side latency bắt đầu khi người dùng tương tác, có thể gồm DNS, TLS, download và render.
- Server-side latency thường bắt đầu khi gateway nhận request và kết thúc khi response được gửi.
- Business completion có thể muộn hơn response nếu thao tác được chấp nhận để xử lý bất đồng bộ.

Không trộn các loại này trong cùng dashboard. Một API có p95 200 ms không có nghĩa người dùng thấy nội dung sau 200 ms nếu frontend phải tải thêm tài nguyên, gọi API khác và render.

## 2. Mô hình hóa luồng đầu cuối

Vẽ dependency graph trước khi chia ngân sách. Một request có thể gọi tuần tự, song song hoặc chuyển công việc qua queue. Cách phối hợp quyết định cách cộng latency.

~~~mermaid
flowchart LR
    CLIENT["Client"] --> EDGE["DNS / TLS / Edge"]
    EDGE --> GW["API Gateway"]
    GW --> AUTH["Authentication"]
    AUTH --> APP["Application service"]
    APP --> CACHE["Cache"]
    CACHE -->|Miss| DB["Database"]
    CACHE -->|Hit| RESP["Response assembly"]
    DB --> RESP
    APP --> OPT["Optional service"]
    OPT --> RESP
    RESP --> CLIENT
    APP --> Q[("Async queue")]
    Q --> WORKER["Background worker"]
~~~

### Các thành phần thường tiêu thụ latency

| Thành phần | Thời gian cần đo | Ví dụ nguyên nhân chậm |
| --- | --- | --- |
| Client/network | DNS, connect, TLS, RTT, transfer | Kết nối mới, khoảng cách region, payload lớn |
| Edge/gateway | Queue wait, auth, routing, rate limit | Quá tải, policy lookup, cold connection |
| Application | Queue/thread wait, CPU, lock, serialization | Thread pool cạn, GC, synchronous call chain |
| Cache | Network RTT, command latency, miss | Hot key, connection limit, eviction |
| Database | Pool wait, query, lock, commit | Scan, contention, slow storage, connection exhaustion |
| External API | Connect, server processing, response | Provider latency, quota, retry, cross-region call |
| Queue/worker | Publish, queue wait, consume, processing | Consumer lag, backlog, retry/DLQ |
| Response | Aggregation, compression, serialization, transfer | JSON lớn, CPU compression, client bandwidth |

Không phải thành phần nào cũng nằm trên critical path. Queue xử lý email sau khi response đã trả có latency riêng và không được cộng vào latency của API booking, nhưng nó cần SLO riêng.

### Xác định critical path

Critical path là chuỗi phụ thuộc quyết định thời điểm request có thể hoàn tất. Nếu hai dependency chạy song song, tổng thời gian của đoạn đó gần bằng nhánh chậm nhất cộng phần tổng hợp, không phải tổng thời gian của cả hai nhánh.

Ví dụ:

~~~mermaid
flowchart TD
    A["API starts"] --> B["Read booking: 90 ms"]
    B --> C["Parallel calls"]
    C --> D["Customer profile: 70 ms"]
    C --> E["Recommendation: 180 ms"]
    D --> F["Assemble: 35 ms"]
    E --> F
    F --> G["Return response"]
~~~

Sau bước đọc booking, hai nhánh chạy song song. Critical path là nhánh recommendation 180 ms, cộng thời gian điều phối và assembly. Nếu recommendation không quan trọng với use case, có thể đặt deadline ngắn hoặc bỏ nhánh khi chậm.

## 3. Phân rã ngân sách đầu cuối

Giả sử một API có latency objective p95 là 500 ms. Một bản phân bổ ban đầu có thể như sau:

| Giai đoạn | Budget | Ghi chú |
| --- | ---: | --- |
| Gateway, auth và routing | 45 ms | Bao gồm queue wait ở gateway |
| Application queue và xử lý | 60 ms | Không bao gồm thời gian gọi dependency |
| Cache/database access | 130 ms | Bao gồm pool wait và query |
| Dependency nghiệp vụ | 90 ms | Một hoặc nhiều call trên critical path |
| Response assembly/serialization | 45 ms | Mapping, JSON và compression |
| Network/response margin | 50 ms | Phần truyền còn lại và biến động |
| Safety reserve | 80 ms | Tail variation, scheduler, retry không mong đợi |
| **Tổng** | **500 ms** | Mục tiêu minh họa |

Không nhất thiết phải cấp budget cho từng bước theo tỷ lệ bằng nhau. Dependency nào có latency biến động lớn, khó kiểm soát hoặc nằm ngoài tổ chức cần timeout chặt hơn. Phần dự phòng bảo vệ request khỏi những thành phần không thể dự đoán hoàn toàn.

### Cách phân bổ

1. Đặt tổng deadline theo trải nghiệm và SLO.
2. Liệt kê critical path và các call chạy song song.
3. Ước lượng p50/p95/p99 hiện tại của từng hop.
4. Cấp budget cho phần có thể kiểm soát và đặt timeout cho dependency.
5. Dành reserve cho variance, scheduling và response transfer.
6. Kiểm tra tổng ngân sách theo cấu trúc tuần tự/song song.
7. Load test và tracing để xác minh; điều chỉnh từ số đo.

### Tránh cộng nhầm các nhánh song song

Với các bước tuần tự:

\[
T_{\mathrm{total}} \approx T_1 + T_2 + \cdots + T_n
\]

Với các nhánh song song bắt đầu gần cùng lúc:

\[
T_{\mathrm{parallel}} \approx \max(T_1,T_2,\ldots,T_n)+T_{\mathrm{join}}
\]

Đây là mô hình đơn giản. Thực tế còn có thời gian điều phối, queue, giới hạn concurrency và tương quan giữa các nhánh.

### Budget không phải quota để từng service tiêu hết

Nếu tất cả service đều dùng đúng maximum timeout được cấp, request có thể chạm deadline tổng. Mỗi bước cần giữ headroom và dừng khi remaining deadline không còn đủ cho operation có ích. Không tiếp tục thực hiện call mới chỉ vì timeout cục bộ vẫn chưa hết.

## 4. Hiểu p50, p95, p99 và tail latency

Latency không chỉ là một con số trung bình. Nếu phần lớn request nhanh nhưng một nhóm nhỏ rất chậm, người dùng bị ảnh hưởng và SLO percentile có thể thất bại.

| Thước đo | Diễn giải |
| --- | --- |
| p50 | Một nửa request hoàn tất nhanh hơn hoặc bằng giá trị này |
| p90 | 90% request hoàn tất nhanh hơn hoặc bằng |
| p95 | 95% request hoàn tất nhanh hơn hoặc bằng |
| p99 | 99% request hoàn tất nhanh hơn hoặc bằng |
| p99.9 | Tail rất chậm, hữu ích với luồng khối lượng lớn hoặc critical |
| Mean/average | Trung bình; có thể che giấu tail |
| Max | Giá trị lớn nhất quan sát trong tập đo; nhạy với sample size/outlier |

### Vì sao tail latency cộng dồn?

Giả sử một request đi qua 10 service tuần tự. Mỗi service có xác suất 99% hoàn thành trong 50 ms. Xác suất cả 10 service đều nằm trong khoảng 50 ms, nếu độc lập, là:

\[
0.99^{10} \approx 90.4\%
\]

Do đó, dù từng service đạt p99 ở 50 ms, chỉ khoảng 90.4% request có tất cả 10 hop cùng ở trong ngưỡng đó theo giả định độc lập. Request end-to-end có thể có percentile kém hơn từng component.

Đây là minh họa xác suất, không phải phép tính trực tiếp p95 đầu cuối từ p95 từng service. Latency giữa các service có thể tương quan do tải, network hoặc dependency chung.

### Tail amplification

Tail có thể tăng mạnh do:

- Một node hoặc partition chậm trong pool.
- Queue wait tăng khi concurrency vượt capacity.
- Lock contention hoặc noisy neighbor.
- Retries tạo thêm tải đúng lúc dependency đang chậm.
- Một nhánh song song có latency cao làm chậm toàn response.
- Cold start, autoscaling hoặc connection establishment.
- Garbage collection, CPU throttling và storage throttling.

Theo dõi percentile theo route, tenant tier, region và dependency. Không chỉ xem percentile toàn hệ thống vì nó có thể che một nhóm người dùng hoặc một partition đang gặp vấn đề.

## 5. Deadline propagation và timeout theo thời gian còn lại

Timeout độc lập ở mỗi service dễ làm tổng thời gian vượt mục tiêu. Một request có tổng deadline 800 ms nhưng ba dependency mỗi bên timeout 800 ms có thể kéo dài nhiều giây nếu lần lượt chờ.

### Truyền deadline

Khi request đi qua service, truyền deadline tuyệt đối hoặc remaining timeout có định dạng thống nhất. Mỗi service tính ngân sách còn lại, trừ thời gian đã tiêu thụ và phần overhead nội bộ.

~~~text
incoming deadline: 12:00:00.800
current time:      12:00:00.310
remaining:         490 ms

local response reserve: 60 ms
dependency call budget: 300 ms
unallocated safety:     130 ms
~~~

Ví dụ, service chỉ cấp 300 ms cho dependency vì cần giữ 60 ms để hoàn thiện response và 130 ms dự phòng. Nếu còn 50 ms thì không nên bắt đầu call có timeout 300 ms.

### Timeout theo hop

- Connect timeout: giới hạn thời gian thiết lập kết nối.
- Request/read timeout: giới hạn chờ response hoặc dữ liệu.
- Pool-acquisition timeout: giới hạn chờ connection/thread.
- Database statement timeout: giới hạn query.
- Overall deadline: giới hạn toàn request.

Phải cấu hình tổng hợp các timeout này; một timeout không thay thế timeout khác. Ví dụ HTTP read timeout 2 giây không giúp request đạt SLO 500 ms.

### Cancellation propagation

Khi caller hết deadline hoặc client hủy request, downstream work nên được cancel nếu an toàn. Nếu tiếp tục chạy query hoặc gọi provider sau khi caller đã bỏ cuộc, hệ thống tiêu tốn tài nguyên vô ích và làm giảm capacity cho request khác.

Không cancel side effect đã commit hoặc operation cần hoàn tất để giữ consistency. Các tác vụ như payment reconciliation hoặc durable workflow cần lifecycle độc lập với HTTP client.

### Clock và deadline format

Deadline tuyệt đối qua nhiều host cần chú ý clock skew. Ở từng process, dùng monotonic clock để đo thời lượng; truyền deadline theo protocol/runtime chuẩn của nền tảng và chuyển đổi cẩn thận. Không dùng timestamp client tùy ý như nguồn tin cậy cho authorization hoặc business expiry.

## 6. Retry, hedging và ngân sách thời gian

Retry có thể khắc phục lỗi tạm thời nhưng làm request chậm hơn và tăng tải. Chỉ retry khi còn deadline và có cơ chế đảm bảo an toàn.

### Retry budget

Với một call có budget 240 ms, có thể thử hai lần:

| Lần | Timeout | Backoff | Ghi chú |
| --- | ---: | ---: | --- |
| Attempt 1 | 100 ms | 20 ms | Chỉ retry lỗi transient |
| Attempt 2 | 100 ms | 0 ms | Dừng nếu remaining deadline không đủ |
| Reserve | 20 ms | — | Dành cho xử lý kết quả |

Các con số chỉ minh họa. Phải tính tổng timeout, backoff và serialization vào budget. Retry không được dùng hết thời gian còn lại của request.

### Quy tắc retry

- Chỉ retry lỗi tạm thời như connection reset hoặc một số 5xx/429 theo contract.
- Dùng exponential backoff và jitter để tránh đồng bộ retry.
- Giới hạn số lần và retry budget theo service.
- Idempotency key cho operation ghi.
- Không retry validation, authorization hoặc lỗi nghiệp vụ rõ ràng.
- Tránh retry lồng tầng: gateway retry service, service retry database, SDK lại retry.

### Hedged requests

Hedging gửi một bản request thứ hai tới replica khác khi request đầu vượt một ngưỡng latency, rồi dùng kết quả hợp lệ đầu tiên. Nó có thể giảm tail latency cho thao tác đọc idempotent nhưng làm tăng tải và dễ gây stampede. Chỉ dùng khi:

- Có replica capacity thực sự.
- Operation đọc không tạo side effect.
- Cancel request chậm khi có kết quả.
- Có giới hạn tỷ lệ hedge và theo dõi extra load.
- Consistency semantics giữa replica được chấp nhận.

Không hedging thao tác ghi thanh toán hoặc tạo booking nếu chưa có protocol idempotency/coordination phù hợp.

## 7. Queueing, concurrency và Little's Law

Một request không chỉ mất thời gian xử lý; nó còn có thể chờ trước khi được xử lý. Queueing delay thường tăng nhanh khi hệ thống tiến gần giới hạn capacity.

### Little's Law

Trong trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request trung bình đang ở trong hệ thống.
- \(\lambda\) là throughput trung bình (request/giây).
- \(W\) là thời gian trung bình trong hệ thống (giây).

Ví dụ 200 request/giây và trung bình 0.25 giây trong hệ thống tương ứng khoảng 50 request đang xử lý/chờ. Nếu thời gian tăng lên 1 giây ở cùng throughput, số request đang tồn tại trung bình tăng lên khoảng 200, làm tăng memory, connection và queue pressure.

Little's Law không tự xác định capacity tối đa; nó giúp liên hệ concurrency, throughput và latency trong điều kiện ổn định.

### Queue wait budget

Nếu request chờ 150 ms trong worker queue, thời gian đó đã tiêu thụ ngân sách dù CPU chưa làm gì. Cần đo:

- Queue depth và oldest item age.
- Queue wait p50/p95/p99.
- Active workers và saturation.
- Reject/drop/backpressure count.
- Downstream concurrency và connection pool wait.

### Admission control và load shedding

Khi queue hoặc connection pool vượt ngưỡng, có thể từ chối sớm, throttle hoặc hạ ưu tiên tác vụ không thiết yếu. Xếp hàng vô hạn chỉ đổi lỗi quá tải thành latency rất lớn và tiêu hao tài nguyên.

Một request chỉ nên được nhận nếu có đủ thời gian và capacity để hoàn tất có ích. Với tác vụ dài, chuyển sang durable async workflow và trả operation ID thay vì giữ HTTP connection.

## 8. Phân bổ ngân sách theo từng loại dependency

Mỗi dependency có đặc tính và mức kiểm soát khác nhau.

| Dependency | Điều cần tính trong budget | Chiến lược |
| --- | --- | --- |
| Internal service cùng region | Gateway/mesh, queue, serialization và downstream processing | Deadline propagation, connection reuse |
| Cross-region service | RTT, TLS, egress, replication và retry | Giảm synchronous hop, cache/read model |
| Database | Pool wait, query, lock, commit, network | Query timeout, index, pool sizing |
| Cache | Pool wait, network RTT, hit/miss | Short timeout, fallback có giới hạn |
| External API | Connect, provider processing, quota và retries | Timeout chặt, circuit breaker, async khi phù hợp |
| Message broker | Publish acknowledgement và queue wait | Durable publish, async processing SLO |
| Object storage | DNS/TLS, upload/download, multipart và transfer | Streaming, multipart, signed URL |
| Authentication | Token verification, introspection hoặc remote policy lookup | Local verification khi an toàn, cache policy có giới hạn |

### Internal call không miễn phí

Một service cùng VPC vẫn chịu network stack, service mesh, mTLS, load balancing, queueing và serialization. Gọi thêm nhiều service nhỏ có thể tăng latency và failure surface. Hãy cân nhắc gộp query, bulk endpoint hoặc read model nếu chúng cùng một transaction/use case và ranh giới domain cho phép.

### External dependency

Không đặt toàn bộ ngân sách vào SLA của provider. Tổ chức cần timeout ngắn hơn deadline tổng, circuit breaker, fallback hợp lý, retry policy và trạng thái nghiệp vụ khi kết quả không rõ. Với payment, timeout không chứng minh giao dịch thất bại; cần query status hoặc reconciliation.

## 9. Đo latency đúng cách

Không thể quản lý thứ không đo được. Cần phối hợp metrics, distributed tracing, logs và synthetic/load tests.

### Metrics

Các metric cơ bản:

- Request count và throughput theo route.
- Latency histogram p50/p90/p95/p99.
- Error rate và timeout rate.
- Queue wait và processing duration.
- Connection pool wait/active/idle.
- Cache hit/miss và command latency.
- Database query duration, lock wait và pool wait.
- CPU, memory, GC, throttling và network saturation.

Dùng histogram có bucket phù hợp với SLO. Trung bình không đủ để tính percentile; tránh tính percentile bằng cách lấy trung bình percentile của từng instance vì có thể sai khi traffic phân bố không đều.

### Distributed tracing

Trace cho thấy request đi qua service nào, call nào tuần tự/song song, thời gian ở từng span và nơi phát sinh tail. Span nên ghi:

- Service, operation, route template.
- Start/end/duration và status.
- Dependency name và peer region.
- Queue wait, pool wait hoặc query class khi có thể.
- Retry attempt và remaining deadline nếu an toàn.
- Correlation/request ID.

Không đưa secret hoặc payload nhạy cảm vào span attributes. Dùng trace sampling phù hợp; giữ sampling đại diện cho lỗi và slow request để điều tra tail.

### Client-side measurement

Nếu SLO là trải nghiệm người dùng, đo cả DNS, connection, TLS, TTFB, content download và render/interaction. Backend tracing không thấy thời gian thiết bị, mạng di động hoặc JavaScript bundle.

### Synthetic monitoring

Chạy journey thử từ region/điểm mạng được chọn, với dữ liệu thử an toàn. Synthetic test giúp phát hiện lỗi trước khi nhiều người dùng bị ảnh hưởng nhưng không thay thế real-user monitoring.

## 10. Phân tích bottleneck và tối ưu theo bằng chứng

Sau khi có trace và percentile, tìm phần chiếm thời gian hoặc làm tăng tail.

### Phân biệt latency source

- **Network-bound:** RTT cao, handshake nhiều, payload lớn, cross-region.
- **CPU-bound:** xử lý, serialization, compression hoặc cryptography tốn CPU.
- **I/O-bound:** database/storage chậm hoặc throughput hạn chế.
- **Lock/contention-bound:** nhiều request tranh chấp lock, row hoặc partition.
- **Queue-bound:** worker/thread/connection không đủ.
- **Dependency-bound:** provider hoặc service downstream chậm.

### Tối ưu theo tầng

**Network:** dùng connection pooling/keep-alive, giảm round trip, đặt compute gần dependency, truyền payload cần thiết và cân nhắc compression theo CPU/network tradeoff.

**Compute:** loại bỏ blocking call không cần thiết, tối ưu serialization, giảm allocation, tránh lock dài, cấu hình thread/worker pool theo downstream capacity và đo GC/throttling.

**Database:** kiểm tra query plan, index, N+1 queries, lock wait, connection pool, pagination và data access pattern. Không tăng pool vô hạn vì có thể đẩy database tới saturation.

**Cache:** cache dữ liệu lặp lại phù hợp freshness, kiểm soát stampede/hot key, đặt timeout và fallback; không cache quyết định giao dịch yêu cầu dữ liệu chuẩn mới nhất.

**Architecture:** giảm hop tuần tự, chạy song song phần độc lập, chuyển side effect không cần đồng bộ sang queue, dùng materialized view hoặc read model cho query tổng hợp.

**Payload:** giảm field không cần, pagination, streaming response hoặc compression; đo CPU và network trước/sau.

### Thay đổi một biến tại một thời điểm

Ghi baseline, thay một yếu tố, chạy cùng workload và so sánh p50/p95/p99, throughput, error và cost. Nếu thay đổi làm p50 tốt nhưng p99 xấu, cần hiểu nhóm request nào bị ảnh hưởng. Tránh tuyên bố tối ưu chỉ dựa trên một lần chạy nhỏ.

## 11. Capacity, autoscaling và latency budget

Autoscaling có thể giúp tăng capacity nhưng không phản ứng tức thời. Khởi tạo instance, container, JVM, cache warm-up hoặc mở connection có thể làm latency tăng trong giai đoạn scale out.

### Những điều cần đưa vào budget

- Queueing trong lúc capacity mới chưa sẵn sàng.
- Cold start hoặc image pull.
- Health/readiness gate trước khi nhận traffic.
- Connection pool warm-up và DNS resolution.
- Cache warm-up hoặc JIT compilation.
- Scale-in draining để không cắt request đang chạy.

### Scale theo tín hiệu phù hợp

CPU đơn lẻ có thể không phản ánh bottleneck. Một service có thể chậm vì database pool wait dù CPU thấp. Cân nhắc request concurrency, queue depth, oldest age, latency, downstream saturation và throughput.

### Headroom và overload

Capacity cần có headroom cho peak và failure scenario. Nếu một availability zone mất, các zone còn lại phải đủ capacity hoặc có admission control. Không đặt autoscaling max quá cao đến mức mở quá nhiều connection tới database/provider.

### Load test

Kiểm thử ở:

- Expected steady-state traffic.
- Peak/burst traffic.
- Ramp-up và ramp-down.
- Dependency slowdown.
- Một node/zone bị mất.
- Cache cold hoặc queue backlog.
- Tenant hot key/noisy neighbor.

Đo latency phân vị và error rate cùng throughput; một hệ thống có thể giữ latency thấp bằng cách silently dropping request, nên phải xem tất cả chỉ số.

## 12. Thiết kế graceful degradation dựa trên deadline

Khi thời gian còn lại ít, ứng dụng nên chọn hành vi có giá trị thay vì tiếp tục gọi mọi dependency.

Ví dụ trang booking có tổng deadline 500 ms:

- Booking data là bắt buộc, được ưu tiên.
- Customer display profile có thể dùng snapshot hợp lệ trong phạm vi policy.
- Recommendation là optional, timeout sau 80 ms.
- Analytics event được phát bất đồng bộ.

~~~mermaid
flowchart TD
    A["Request: 500 ms deadline"] --> B["Auth and booking read"]
    B --> C["Remaining budget check"]
    C --> D["Profile call"]
    C --> E["Optional recommendation"]
    E --> F{"Completed within 80 ms?"}
    F -- "Yes" --> G["Include suggestions"]
    F -- "No" --> H["Omit suggestions / degraded flag"]
    D --> I["Assemble response"]
    G --> I
    H --> I
    I --> J["Return before overall deadline"]
    B --> Q["Async analytics event"]
~~~

### Quy tắc degraded mode

- Không hy sinh authorization hoặc business invariant để giảm latency.
- Chỉ dùng stale data trong giới hạn được domain owner duyệt.
- Không xác nhận write khi source of truth chưa commit hoặc chưa có durable acceptance theo contract.
- Optional dependency có deadline nhỏ hơn tổng request.
- Queue/async path có SLO riêng và báo trạng thái pending.
- Theo dõi degraded response rate và business outcome.

### Khi nào fail fast?

Nếu remaining budget không đủ cho operation có ích hoặc dependency bắt buộc không thể trả lời trong deadline, fail fast với trạng thái rõ ràng. Trả lỗi nhanh có thể tốt hơn chờ timeout dài, nhưng cần retry guidance và idempotency để tránh tạo side effect trùng.

## 13. Ví dụ thực tế: ngân sách độ trễ cho checkout

**Bối cảnh giả định:** Một nền tảng thương mại điện tử muốn checkout backend đạt p95 dưới 800 ms và p99 dưới 1.2 giây trong điều kiện tải mục tiêu. Luồng gồm API gateway, authentication, cart, pricing, inventory, order database và payment provider. Email và analytics xử lý sau khi order được ghi nhận. Đây là mục tiêu mô phỏng.

### Luồng đồng bộ và bất đồng bộ

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Auth"]
    G --> CART["Cart and checkout"]
    CART --> PRICE["Pricing"]
    CART --> INV["Inventory validation/reservation"]
    PRICE --> ORDER["Order transaction"]
    INV --> ORDER
    ORDER --> RESP["Response"]
    ORDER --> OUT["Transactional outbox"]
    OUT --> Q[("Queue")]
    Q --> PAY["Payment workflow"]
    Q --> EMAIL["Notification"]
    Q --> ANA["Analytics"]
~~~

Sơ đồ là một lựa chọn thiết kế minh họa. Nếu payment cần được xác nhận đồng bộ trước khi order có trạng thái thành công, payment call phải nằm trên critical path và được cấp budget riêng; nếu workflow chấp nhận trạng thái pending, payment có thể tiếp tục bất đồng bộ theo contract.

### Phân bổ budget ban đầu

| Bước | Budget | Loại |
| --- | ---: | --- |
| Gateway, TLS/auth/routing | 70 ms | Tuần tự |
| Cart load và application processing | 90 ms | Tuần tự |
| Pricing lookup | 110 ms | Song song với inventory |
| Inventory validation/reservation | 160 ms | Song song với pricing, nhánh chậm hơn |
| Order database transaction | 180 ms | Tuần tự sau validation |
| Response assembly/serialization | 50 ms | Tuần tự |
| Network/safety reserve | 140 ms | Dự phòng |
| **Tổng critical path ước lượng** | **690 ms** | 70 + 90 + max(110,160) + 180 + 50 + 140 |

Phần còn lại tới mục tiêu p95 800 ms là headroom 110 ms cho variance chưa được mô hình hóa. Đây là bản phân bổ khởi đầu; phải xác minh bằng histogram và distributed traces. Không cộng pricing và inventory như hai bước tuần tự nếu thực tế chúng chạy song song.

### Payment workflow

Nếu payment được thực hiện sau response, API cần trả trạng thái phù hợp như order accepted/payment pending và operation ID. Payment worker có deadline/SLO riêng, idempotency key và reconciliation. Không được gọi provider bất đồng bộ rồi trả “paid” khi chưa có xác nhận.

### Đo lường

- Gateway duration và auth duration.
- Cart query/pool wait.
- Pricing p95/p99.
- Inventory lock/queue wait.
- Database commit duration.
- Outbox publish lag, payment queue age và provider processing time.
- Checkout end-to-end p50/p95/p99 và success rate.

### Tiêu chí chấp nhận

- Checkout API đạt SLO latency cùng success/error objective.
- Không tạo oversell hoặc order trùng do timeout/retry.
- Optional analytics/email không làm tăng critical path.
- Khi pricing/inventory chậm, timeout và degraded policy hoạt động đúng.
- Queue/payment backlog được quan sát và xử lý theo SLO riêng.
- Tải peak không làm connection pool hoặc database quá giới hạn.

## 14. Bài thực hành: xây dựng latency budget cho luồng đặt lịch

**Tình huống:** Một nền tảng đặt lịch có API xem lịch, search provider và xác nhận booking. Hệ thống chạy ở hai region; user có thể ở xa region chứa tenant. Luồng xác nhận cần auth, đọc availability, kiểm tra pricing, giữ slot trong database và phát notification event. Search có thể dùng cache/read model; notification không cần hoàn tất trước response. Mục tiêu giả định: p95 search dưới 350 ms, p95 booking confirmation dưới 900 ms và p99 dưới 1.5 giây.

### Nhiệm vụ

1. **Vẽ user journey:** xác định điểm bắt đầu/kết thúc, client/network/server và business completion.
2. **Vẽ dependency graph:** phân biệt tuần tự, song song, critical path và async side effect.
3. **Tạo ngân sách:** phân bổ gateway, auth, network, service queue, cache/database, lock, serialization, response và reserve.
4. **Định nghĩa deadline:** truyền remaining budget qua service; cấp connect/read/statement/pool timeout.
5. **Thiết kế retry:** xác định lỗi retryable, idempotency, backoff/jitter, attempt limit và retry budget.
6. **Thiết kế overload:** queue depth, worker concurrency, admission control, load shedding và autoscaling headroom.
7. **Đo lường:** xác định histogram, traces, span fields, dashboards, synthetic test và sampling policy.
8. **Graceful degradation:** quyết định dùng cache/stale, bỏ recommendation, queue notification hay fail fast cho từng dependency.
9. **Validation:** chạy load test, dependency slowdown, cold cache và zone failure; so sánh latency budget với kết quả.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Normal load | Tải dự kiến ổn định | p50/p95/p99 và throughput đạt SLO |
| Peak load | Burst traffic | Queue wait và tail không vượt giới hạn hoặc admission control kích hoạt |
| Slow dependency | Pricing tăng latency | Caller dừng theo deadline, không giữ request vô hạn |
| Parallel branch | Availability và pricing chạy song song | Critical path dùng nhánh chậm hơn, không cộng nhầm hai thời gian |
| Retry storm | Dependency trả 503/429 | Retry budget/backoff/jitter giới hạn extra load |
| Connection saturation | Pool gần cạn | Pool wait được đo, timeout và backpressure rõ |
| Cold cache | Cache miss hàng loạt | Database không bị stampede vượt capacity |
| Queue backlog | Notification worker chậm | API vẫn giữ SLO; queue age có alert |
| Region latency | User xa home region | RTT được đo; placement/edge/read path có phương án |
| Zone failure | Một zone mất | Headroom/failover giữ mức SLO được xác định |
| Cancellation | Client hủy request | Downstream read được cancel; side effect bền vững vẫn được xử lý đúng |
| Payload growth | Response lớn hơn bình thường | Serialization/transfer không vượt budget |

### Deliverables

- User journey và dependency graph.
- Latency SLI/SLO và measurement boundary.
- Budget table cho critical path và async workflow.
- Deadline/timeout/retry/concurrency policy.
- Observability dashboard và trace specification.
- Load/fault test plan và kết quả.
- Bottleneck analysis cùng đề xuất tối ưu.
- ADR ghi giả định, trade-off, owner và review trigger.

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho latency budget |
| --- | --- |
| **Operational Excellence** | Có SLO owner, dashboard, trace, runbook, load test cadence và review khi workload đổi không? |
| **Security** | TLS, auth, policy lookup, encryption và redaction có được tính vào budget mà không bị bỏ qua để tăng tốc? |
| **Reliability** | Deadline propagation, timeout, cancellation, retry budget, circuit breaker và degraded mode có được thử? |
| **Performance Efficiency** | Critical path, queueing, cache, query, network, payload và capacity được tối ưu theo số đo không? |
| **Cost Optimization** | Có cân bằng latency với replica, overprovision, cache, region placement và autoscaling cost không? |
| **Sustainability** | Có tránh retry storm, polling dư thừa, payload lớn và capacity nhàn rỗi chỉ để đạt latency không cần thiết? |

## 16. Những sai lầm thường gặp

**Chỉ đo thời gian của một service.** Người dùng trải nghiệm cả luồng, gồm network, gateway, dependency và client.

**Cộng trung bình để suy ra p95.** Percentile không cộng tuyến tính; cần đo end-to-end và hiểu phân bố từng hop.

**Cấp timeout bằng nhau cho mọi dependency.** Một service phụ không nên được giữ request lâu bằng toàn bộ deadline.

**Không truyền deadline.** Mỗi tầng có timeout riêng có thể khiến tổng request vượt SLO.

**Retry ở nhiều tầng.** Retry lồng nhau làm số call tăng theo cấp số nhân trong outage.

**Không tính queue wait.** Worker có thể chờ lâu dù processing time thấp.

**Dùng CPU làm tín hiệu autoscaling duy nhất.** Database pool wait hoặc external dependency có thể là bottleneck khi CPU thấp.

**Chạy mọi call tuần tự.** Dependency độc lập có thể chạy song song, nhưng cần kiểm soát fan-out và concurrency.

**Chạy mọi call song song không giới hạn.** Fan-out lớn có thể làm downstream quá tải.

**Hedging mọi request.** Request nhân đôi có thể làm tail nặng hơn khi hệ thống đang bão hòa.

**Không reserve thời gian response.** Service dùng hết deadline vào dependency và không còn thời gian serialize/trả kết quả.

**Coi async là hoàn tất ngay.** Queue acceptance khác với business completion; API phải thể hiện trạng thái chính xác.

**Không đo client-side latency.** Backend nhanh nhưng DNS, TLS, transfer hoặc render vẫn chậm.

**Tối ưu p50 mà bỏ qua p99.** Một nhóm người dùng hoặc partition vẫn có trải nghiệm rất kém.

## 17. Checklist trước khi công bố latency SLO

- [ ] User journey và measurement boundary được định nghĩa rõ.
- [ ] SLI/SLO dùng percentile phù hợp và có owner.
- [ ] Dependency graph xác định critical path, nhánh song song và async side effect.
- [ ] Budget bao gồm gateway, auth, queue, pool wait, compute, data, network và response.
- [ ] Mỗi hop có timeout phù hợp với remaining deadline.
- [ ] Có cancellation propagation cho work không còn hữu ích.
- [ ] Retry có backoff/jitter, attempt limit, idempotency và retry budget.
- [ ] Hedging chỉ dùng cho thao tác phù hợp và có concurrency cap.
- [ ] Queue depth, wait time, oldest age và backpressure được quan sát.
- [ ] Percentile được đo bằng histogram/tracing đủ đại diện; không suy ra từ average.
- [ ] Dashboard phân tách route, region, tenant tier và dependency cần thiết.
- [ ] Client-side measurement được dùng khi SLO phản ánh trải nghiệm người dùng.
- [ ] Load test bao gồm steady, peak, burst, cold start và dependency degradation.
- [ ] Capacity/autoscaling có headroom và không tạo tải quá mức cho downstream.
- [ ] Graceful degradation không phá authorization hoặc business invariant.
- [ ] Async acceptance và business completion có semantics riêng.
- [ ] Kết quả tối ưu được so sánh cùng workload và có cost/error trade-off.
- [ ] Budget được review khi code path, dependency, region hoặc traffic profile thay đổi.

Ngân sách độ trễ biến hiệu năng đầu cuối thành một mục tiêu có thể thiết kế và kiểm chứng. Hãy bắt đầu từ hành trình người dùng và SLO, xác định critical path, phân bổ thời gian cho từng hop cùng phần dự phòng, rồi truyền deadline xuyên suốt để các service dừng đúng lúc. Percentile, queueing, retry và tail latency phải được đo bằng trace và workload đại diện; các lựa chọn cache, song song hóa, async workflow, autoscaling và degraded mode cần giữ đúng semantics nghiệp vụ. Một ngân sách tốt không chỉ làm request nhanh hơn mà còn giúp hệ thống sử dụng capacity có trách nhiệm và duy trì hiệu năng khi tải hoặc dependency thay đổi.
