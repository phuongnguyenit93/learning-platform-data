# Ngăn noisy neighbor bằng hạn mức và phân bổ tài nguyên

## 1. Noisy neighbor là vấn đề chia sẻ tài nguyên

Trong kiến trúc đa khách hàng (multi-tenant), nhiều tenant dùng chung compute, database, cache, network, queue, object storage hoặc search cluster. Mô hình chia sẻ giúp tăng mức sử dụng tài nguyên và giảm chi phí, nhưng một tenant có tải đột biến hoặc hành vi bất thường có thể tiêu thụ phần lớn năng lực dùng chung. Tenant khác khi đó thấy latency tăng, request timeout, queue backlog hoặc lỗi dù họ không tăng tải.

Hiện tượng này thường được gọi là **noisy neighbor**. Nguyên nhân không nhất thiết là tenant độc hại; một đợt import dữ liệu lớn, báo cáo nặng, vòng lặp retry sai hoặc chiến dịch kinh doanh thành công cũng có thể tạo tải vượt dự tính.

Mục tiêu kiến trúc là **chia sẻ có kiểm soát**: mỗi tenant có quyền sử dụng tài nguyên tương ứng với gói dịch vụ/chính sách; nền tảng bảo vệ năng lực chung; tenant có tải cao không làm tenant khác mất SLO; và công việc quan trọng vẫn có thể tiến hành khi hệ thống điều tiết tải.

Trong module **CLOUD_ARCHITECTURE**, vấn đề này gắn với compute, mạng, dữ liệu và mô hình triển khai. Thiết kế phải cân bằng **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng SaaS đặt chỗ có hàng nghìn tenant. Mỗi tenant quản lý property, booking, người dùng và báo cáo. Tenant A bắt đầu import hàng trăm nghìn bản ghi và chạy báo cáo toàn năm; nếu mọi request cùng dùng một connection pool và worker pool, tenant B có thể không đăng nhập hoặc tra cứu được booking.

## 2. Phân biệt quota, rate limit, concurrency và resource allocation

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Quota | Tổng mức sử dụng trong một kỳ/gói dịch vụ | 100.000 API calls/ngày, 500 GB lưu trữ |
| Rate limit | Tốc độ request/thao tác trong một cửa sổ | 20 request/giây mỗi tenant |
| Burst allowance | Lượng tải tăng ngắn hạn được chấp nhận | Burst 50 request trước khi điều tiết |
| Concurrency limit | Số thao tác đang chạy đồng thời | Tối đa 5 báo cáo nặng mỗi tenant |
| Resource reservation | Năng lực được bảo đảm hoặc dành riêng | 2 worker slot tối thiểu cho tenant ưu tiên |
| Resource cap | Mức tối đa tenant có thể tiêu thụ | Không quá 4 vCPU hoặc 8 job đang chạy |
| Fair scheduling | Quy tắc chia năng lực khi nhiều tenant tranh chấp | Weighted fair queueing theo trọng số tenant |
| Admission control | Quyết định nhận, trì hoãn hay từ chối công việc mới | Không nhận job khi database đã bão hòa |

Một tenant có thể chưa vượt quota tháng nhưng vẫn gây noisy neighbor bằng cách gửi lượng request lớn trong vài giây. Ngược lại, tenant dùng đều đặn có thể chạm quota tổng dù không gây tải tức thời. Vì vậy cần kết hợp **hạn mức tích lũy, hạn mức tốc độ, giới hạn đồng thời và phân bổ năng lực**.

## 3. Xác định tài nguyên cần bảo vệ

Không thể đặt hạn mức công bằng nếu chỉ đếm HTTP request. Một request đọc cache khác rất nhiều về chi phí so với request export báo cáo, tìm kiếm phức tạp hoặc import tệp lớn.

| Tài nguyên | Kiểu tranh chấp | Chỉ số đo phù hợp |
| --- | --- | --- |
| API gateway/compute | CPU, thread, connection, request burst | RPS, CPU time, active requests, p95/p99 |
| Database | Connection pool, IOPS, CPU, lock, transaction | Query time, active connection, rows scanned, lock wait |
| Cache | Memory, hot keys, network, eviction | Memory per tenant/keyspace, hit ratio, ops/s |
| Queue/worker | Consumer slot, backlog, execution time | Queue age, job count, worker seconds, retry |
| Search | Query complexity, shard, aggregation | Query latency, shard work, bytes/rows examined |
| Object storage | Dung lượng, request, listing, egress | GB, PUT/GET/LIST, bytes transferred |
| Network | Băng thông, kết nối liên vùng, egress | Bytes/s, connection count, transfer cost |
| External provider | API quota, concurrency, chi phí giao dịch | Calls, throttling, latency, provider quota |

Nên đo đơn vị tiêu thụ có ý nghĩa thay vì gán một request bằng một đơn vị chi phí. Ví dụ: tìm kiếm cơ bản bằng 1 search unit; aggregation nhiều chiều bằng 5 units; job export bằng worker-seconds; lưu trữ bằng GB-month; egress bằng GB truyền dữ liệu. Đây là mô hình metering nội bộ, phải hiệu chỉnh từ dữ liệu thực và không nhất thiết phản ánh chính xác hóa đơn cloud.

## 4. Xây dựng chính sách hạn mức theo tenant

Quota nên phản ánh thỏa thuận dịch vụ và năng lực nền tảng. Một policy thường có base allowance, burst allowance, hard cap, concurrency cap, priority, overage behavior và reset period.

| Hạn mức | Starter | Business | Enterprise |
| --- | ---: | ---: | ---: |
| API read calls/ngày | 20.000 | 200.000 | Theo hợp đồng |
| Burst read RPS | 5 | 30 | Được cấu hình |
| Concurrent export jobs | 1 | 3 | Theo pool/quota |
| Storage | 20 GB | 200 GB | Theo hợp đồng |
| Import job đồng thời | 1 | 2 | Có thể dành riêng |

Các số liệu chỉ minh họa. Không nên suy ra tenant Enterprise được tiêu thụ tài nguyên vô hạn; mọi gói vẫn cần guardrail toàn hệ thống. Một quota tổng dễ hiểu nhưng không thể hiện chi phí khác nhau giữa API read, export, import và webhook. Có thể kết hợp quota theo kỳ, rate limit theo route, concurrency cho job nặng, storage/egress quota và hard safety cap.

## 5. Rate limiting và burst control

| Thuật toán | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Fixed window | Đếm request trong cửa sổ cố định | Có thể burst ở ranh giới hai cửa sổ |
| Sliding window | Tính lưu lượng trong cửa sổ trượt | Chính xác hơn tùy triển khai nhưng tốn trạng thái |
| Token bucket | Token được nạp theo tốc độ; request tiêu thụ token | Cho phép burst có giới hạn |
| Leaky bucket | Đưa công việc ra theo tốc độ ổn định | Làm mượt tải nhưng có thể tăng thời gian chờ |

Ví dụ token bucket: refill rate 10 tokens/second, bucket capacity 30 tokens, mỗi request tiêu thụ 1 token. Tenant có thể gửi burst trong sức chứa bucket; về lâu dài tốc độ trung bình bị giới hạn bởi tốc độ nạp. Request đắt hơn có thể tiêu thụ nhiều token hơn nếu cost model được kiểm chứng.

Rate limit có thể áp dụng đồng thời theo tenant, user/API key, route, IP/source signal và toàn hệ thống. Các giới hạn phải phối hợp theo thứ tự rõ ràng. Với HTTP API, 429 Too Many Requests phù hợp khi caller vượt rate limit; có thể trả Retry-After hoặc reset time. Khi toàn hệ thống thiếu năng lực, 503 Service Unavailable có thể phù hợp hơn. Client cần backoff, jitter, giới hạn retry và idempotency cho thao tác ghi.

## 6. Concurrency limit, queue và admission control

Rate limit kiểm soát tốc độ bắt đầu thao tác; concurrency limit kiểm soát số công việc đang tiêu thụ tài nguyên cùng lúc. Tenant gửi 2 request/giây nhưng mỗi request chạy 60 giây có thể tạo 120 tác vụ đồng thời. Rate thấp vẫn có thể làm cạn connection pool nếu không có concurrency cap.

| Nhóm | Ví dụ | Hạn mức phù hợp |
| --- | --- | --- |
| Interactive API | Đọc booking, tra cứu profile | Rate và concurrency ngắn, latency-sensitive |
| Search | Tìm kiếm, filter, aggregation | Cost-weighted rate, timeout, giới hạn complexity |
| Batch import | Import danh sách property | Job concurrency, file size, worker-seconds |
| Export/report | Báo cáo, tạo file lớn | Số job đồng thời và queue capacity |
| Webhook | Sự kiện đối tác | Hạn mức riêng, retry policy và dead-letter |
| Admin operation | Bulk update, reindex tenant | Role-based admission và maintenance window |

Queue có thể hấp thụ burst nhưng không được vô hạn. Nếu tốc độ đến luôn lớn hơn tốc độ xử lý, backlog và tuổi công việc sẽ tăng. Đặt maximum queue depth/bytes, maximum queue age, pending-job cap theo tenant, tổng worker/concurrency và hành vi khi queue đầy.

Admission controller quyết định có nhận công việc dựa trên trạng thái hệ thống và policy tenant. Ví dụ chỉ nhận thêm export nếu worker active thấp hơn ngưỡng, database còn headroom và tenant chưa vượt concurrency cap. Khi không thể nhận, trả phản hồi rõ ràng và không tạo job record mồ côi.

## 7. Phân bổ tài nguyên công bằng

Quota quy định mức được phép tiêu thụ; scheduler/fair allocator quyết định ai được dùng tài nguyên khi nhiều tenant cùng tranh chấp.

| Chiến lược | Cách chia | Khi phù hợp | Hạn chế |
| --- | --- | --- | --- |
| First-come, first-served | Ai đến trước được xử lý trước | Tải nhỏ, yêu cầu đơn giản | Tenant gửi nhiều có thể chiếm hàng đợi |
| Equal share | Mỗi tenant hoạt động nhận phần bằng nhau | Tenant có nhu cầu tương đương | Không phản ánh gói dịch vụ |
| Weighted fair sharing | Chia theo trọng số tenant | Gói dịch vụ khác nhau | Cần kiểm soát trọng số và tránh starvation |
| Reserved capacity | Dành năng lực cho nhóm tenant/workload | SLO cao hoặc cam kết riêng | Có thể tạo idle capacity |
| Best effort pool | Dùng phần năng lực còn dư | Batch/report không nhạy thời gian | Có thể bị trì hoãn |
| Dedicated pool | Tách node/worker/database cho tenant | Cô lập mạnh | Tăng chi phí và phân mảnh capacity |

Giả sử tenant A có trọng số 1, B trọng số 2 và C trọng số 1 trong một worker pool. Khi cả ba có backlog, năng lực xử lý mục tiêu có thể theo tỷ lệ 1:2:1. Đây là mục tiêu phân phối, không phải bảo đảm chính xác từng giây; triển khai thực tế cần tính thời gian thực thi khác nhau giữa job. Nên đo worker-seconds hoặc cost units thay vì chỉ đếm message.

Để tránh starvation, có thể dùng weighted fair scheduling, deficit round robin, aging (tăng ưu tiên khi job chờ lâu), reserved minimum share, giới hạn job ưu tiên cao đồng thời và deadline-aware scheduling.

## 8. Phân vùng tài nguyên để giảm blast radius

~~~mermaid
flowchart TB
    T1["Tenant A"] --> G["Admission / Quota / Scheduler"]
    T2["Tenant B"] --> G
    T3["Tenant C"] --> G
    G --> S["Shared worker pool"]
    G --> P["Reserved pool: Premium"]
    G --> D["Dedicated pool: Large tenant"]
    S --> DB["Shared DB / Cache"]
    P --> DB
    D --> DDB["Isolated DB / Cache khi cần"]
~~~

- **Shared pool:** nhiều tenant chia sẻ compute/database/cache; tối ưu chi phí, cần quota và fairness mạnh.
- **Segmented pool:** tenant được phân vào nhóm pool theo khu vực, gói, workload hoặc rủi ro; giảm phạm vi ảnh hưởng.
- **Dedicated pool:** một tenant hoặc nhóm nhỏ có compute/data plane riêng; cô lập tốt hơn nhưng tăng chi phí, automation và capacity fragmentation.

Không nhất thiết dành riêng toàn bộ stack cho mọi tenant lớn. Có thể chỉ tách worker import, search shard hoặc connection pool đang gây tranh chấp.

### 8.1. Bảo vệ database, cache và queue

Một tenant chạy truy vấn chậm có thể giữ connection lâu. Hãy giới hạn query concurrency theo tenant/workload, connection pool có timeout, statement duration/rows scanned, tách analytics sang read replica/warehouse, và theo dõi connection/lock wait. Không tạo pool vật lý riêng cho mọi tenant nếu số tenant rất lớn; tổng connection có thể vượt giới hạn database.

Cache key phải có tenant context khi dữ liệu khác nhau; memory quota/eviction cần ngăn một tenant chiếm hết cache. Search query cần giới hạn aggregation, page size, wildcard và timeout. Queue nên có per-tenant backlog cap và fairness; worker dùng concurrency slot theo tenant.

## 9. Hạn mức mềm, cứng và adaptive

| Loại | Hành vi | Ví dụ |
| --- | --- | --- |
| Soft quota | Cảnh báo hoặc tính phí vượt, chưa từ chối ngay | Storage gần giới hạn |
| Hard quota | Từ chối hoặc ngăn thao tác vượt | Không nhận upload khi storage cap đạt |
| Burst quota | Cho vượt mức cơ sở trong thời gian ngắn | Token bucket |
| Adaptive limit | Điều chỉnh theo capacity và tình trạng hệ thống | Giảm concurrency export khi DB saturation tăng |
| Emergency system cap | Bảo vệ toàn nền tảng bất kể tenant plan | Dừng nhận job nặng khi hạ tầng bão hòa |

Adaptive limit không nên tùy tiện thay đổi cam kết dịch vụ mà tenant đã mua. Cần xác định giới hạn nào thuộc sản phẩm, giới hạn nào là biện pháp bảo vệ sự cố và cách thông báo khi hệ thống phải degraded.

## 10. Phát hiện noisy neighbor bằng telemetry

Muốn cô lập đúng tenant, hệ thống cần gắn tenant context đáng tin cậy vào telemetry. Không nên chỉ dùng tenant ID do client tự gửi; phải xác định từ identity đã xác thực và truyền context qua gateway, service, job và database instrumentation.

| Nhóm | Metric |
| --- | --- |
| Request | RPS, active request, 429/503, timeout, p95/p99 theo tenant và route |
| Compute | CPU time, memory, worker seconds, thread/connection occupancy |
| Database | Query count/duration, rows scanned, lock wait, connection wait |
| Queue | Pending jobs, oldest age, processing rate, retry, DLQ |
| Search | Query cost, shard work, aggregation buckets, timeout |
| Storage/network | Bytes stored, request count, egress, upload/download rate |
| Quota | Used, remaining, reset time, burst consumption, cap event |
| Fairness | Share thực tế so với trọng số/reservation và thời gian chờ |

Tenant A có RPS gấp 10 tenant trung vị chưa chắc là noisy neighbor nếu gói dịch vụ và năng lực phân bổ cho phép. Cần xem **tài nguyên thực tiêu thụ so với allowance, mức ảnh hưởng tới shared resource và SLO của tenant khác**.

~~~text
tenantUtilizationRatio = measuredResourceUnits / allocatedResourceUnits
sharedPoolPressure = observedDemand / safePoolCapacity
~~~

Đây là tỷ lệ khái niệm. Tránh gộp CPU, I/O, network và query cost thành một điểm duy nhất nếu không có trọng số có cơ sở. Nên giữ metric theo từng tài nguyên để tìm đúng bottleneck.

## 11. Công bằng không có nghĩa mọi tenant nhận kết quả giống nhau

Fairness phải gắn với hợp đồng dịch vụ và hành vi tiêu thụ. Tenant trả phí cho mức thông lượng cao hơn có thể nhận trọng số lớn hơn; tuy nhiên tenant lớn không được phép làm mất năng lực an toàn tối thiểu của nền tảng.

Chính sách nên phân biệt entitlement (quyền sử dụng đã cam kết), actual usage, system safety cap, priority, overage và isolation tier. Nếu khách hàng vượt usage do lỗi nền tảng như retry storm từ API, metering cần phân biệt retry do hệ thống, tác vụ nội bộ và thao tác người dùng khi chính sách tính phí yêu cầu.

## 12. Ví dụ policy quota và phân bổ

Policy minh họa sau diễn tả ý định, không phải schema cho một nhà cung cấp cụ thể:

~~~yaml
tenantPolicy:
  plan: business
  limits:
    apiRead:
      sustainedPerSecond: 20
      burst: 60
    export:
      concurrentJobs: 2
      maxRowsPerJob: 500000
    import:
      concurrentJobs: 1
      maxFileSizeMB: 250
    storage:
      softLimitGB: 180
      hardLimitGB: 200
  scheduling:
    workerWeight: 2
    minimumSharePercent: 5
    bestEffortBurst: true
  behavior:
    rateExceeded: reject_with_retry_after
    concurrencyExceeded: enqueue_if_capacity
    hardQuotaExceeded: reject_and_explain
~~~

Các con số và tên trường chỉ phục vụ học tập. Hệ thống thật phải xác định đơn vị, reset period, cách tính chi phí, concurrency nhiều region, nguồn policy có thẩm quyền và cách cập nhật quota để các instance không áp dụng policy khác nhau quá lâu.

## 13. Failure mode của hệ thống quota

Bộ giới hạn tài nguyên cũng là dependency quan trọng. Nếu limiter lỗi, hệ thống có thể mở cửa không giới hạn hoặc từ chối tất cả tenant.

| Failure mode | Nguy cơ | Hướng thiết kế |
| --- | --- | --- |
| Quota store unavailable | Không xác định được mức sử dụng | Local safety limit, cached policy có version và timeout |
| Counter mất dữ liệu | Tenant dùng vượt quota | Reconcile, durable counter hoặc giới hạn bổ sung |
| Counter double count | Tenant bị chặn oan | Idempotency key, atomic increment hoặc event dedup |
| Multi-region inconsistency | Các region cấp vượt tổng quota | Phân bổ quota theo region hoặc coordination phù hợp |
| Policy rollout lệch | Instance áp dụng ngưỡng khác nhau | Versioned policy, staged rollout và telemetry |
| Limiter latency tăng | Mỗi request chờ quota service | Local token bucket, batching hoặc async metering |
| Reset boundary race | Burst lúc đổi cửa sổ | Sliding window/token bucket và boundary test |
| Admin cấu hình sai | Tenant bị khóa hoặc dùng quá mức | Validation, audit, dry-run, rollback |

### 13.1. Fail-open hay fail-closed?

Không có lựa chọn chung. Với API read ít nhạy cảm, local safety cap và fail-open có giới hạn có thể giữ availability. Với thao tác có thể gây chi phí lớn hoặc rủi ro dữ liệu, fail-closed hoặc chỉ cho phép allowance bảo vệ có thể phù hợp hơn. Quyết định phải dựa trên loại tài nguyên, hậu quả kinh doanh và khả năng đo local.

## 14. Bảo mật và chống lạm dụng quota

Quota không phải cơ chế xác thực. Kẻ tấn công có thể tạo nhiều account/API key để phân tán usage hoặc giả tenant ID nếu hệ thống tin request header.

- Tenant context được xác minh từ identity và membership.
- API key/token gắn với tenant/client đúng scope, có rotation và revoke.
- Không cho client tự sửa plan, weight hoặc quota.
- Rate limit trước xác thực theo IP/risk signal và sau xác thực theo tenant/user.
- Audit việc nâng quota, đổi plan, grant burst và truy cập telemetry.
- Tách quyền admin platform khỏi quyền admin tenant.
- Không trả thông tin usage hoặc trạng thái quota của tenant khác.
- Service identity của batch job cũng phải mang tenant/actor context đáng tin cậy.

## 15. Quy trình xử lý khi phát hiện noisy neighbor

~~~mermaid
flowchart TD
    A["Phát hiện shared resource pressure / SLO regression"] --> B["Xác định tenant, route và resource tiêu thụ"]
    B --> C{"Vượt policy hay hệ thống thiếu capacity?"}
    C -->|Tenant vượt hạn mức| D["Rate/concurrency limit hoặc queue"]
    C -->|Capacity thiếu| E["Scale, tối ưu hoặc chuyển workload pool"]
    D --> F["Đo ảnh hưởng tới tenant khác và tenant bị điều tiết"]
    E --> F
    F --> G{"SLO phục hồi?"}
    G -->|Chưa| B
    G -->|Rồi| H["Ghi nhận, điều chỉnh quota và capacity plan"]
~~~

Runbook nên gồm: xác minh SLO và shared resource bão hòa; xác định tenant/workload bằng telemetry đã xác thực; kiểm tra tenant vượt allowance hay capacity nền tảng thiếu; áp biện pháp ít ảnh hưởng nhất; thông báo theo hợp đồng API; đo SLO của tenant bị điều tiết lẫn tenant khác; khôi phục policy bình thường sau sự cố; và rút kinh nghiệm về query, quota, pool, capacity hoặc retry.

Không tự động gắn nhãn tenant abusive chỉ dựa vào request rate; đó có thể là lỗi ứng dụng hoặc chiến dịch hợp lệ. Phân loại nguyên nhân trước khi áp chế tài theo hợp đồng.

## 16. Capacity planning và phân bổ dự phòng

Nếu hạ tầng có 100 worker slots, không nên phân bổ toàn bộ làm reservation cứng cho tenant. Cần dành năng lực cho system workload, sự cố, rollout, burst và phục hồi.

~~~text
Total worker capacity:       100 slots
Platform/system reserve:      10 slots
Premium reserved capacity:    20 slots
Shared fair-use pool:          60 slots
Best-effort burst headroom:    10 slots
~~~

Các pool có thể mượn phần rỗi theo policy; phần reserved không sử dụng có thể cho shared pool mượn nhưng phải thu hồi được khi tenant cần. Điều này cần preemption hoặc priority scheduling an toàn, không dừng tùy tiện job đã gây side effect.

Khi tenant lớn tăng trưởng, có thể điều chỉnh quota/trọng số sau khi đo nhu cầu; tối ưu query/import/export; chuyển workload nặng sang queue/pool phù hợp; tách shard/database/cache/search capacity nếu đó là bottleneck; hoặc dùng dedicated pool khi lợi ích cô lập xứng đáng chi phí. Không nâng quota vô hạn để che lấp query kém hiệu quả.

## 17. Bài thực hành: ngăn tenant gây noisy neighbor trên nền tảng SaaS

**Bối cảnh giả định:** nền tảng có 2.000 tenant, 30.000 request/giây cao điểm, shared PostgreSQL, Redis, search cluster và worker pool. Tenant A chạy import lớn và 10 báo cáo đồng thời; tenant B bị latency API tăng gấp năm lần. Các con số chỉ phục vụ bài tập, không phải benchmark mặc định.

### Nhiệm vụ

1. Xây dựng resource map cho API, DB, cache, search, queue, worker, storage và network.
2. Phân loại ít nhất năm workload theo chi phí và mức độ ưu tiên.
3. Thiết kế quota tổng, rate limit, burst, concurrency và hard system cap cho từng plan.
4. Chọn fair scheduling strategy cho worker pool; nêu cách tránh tenant có job dài chiếm hết slot.
5. Đề xuất giới hạn DB query/connection, search complexity, cache memory và queue backlog theo tenant.
6. Thiết kế shared, segmented và dedicated pool; xác định ngưỡng chuyển tenant lớn sang pool riêng.
7. Xây dashboard phát hiện noisy neighbor và phân biệt vượt quota với thiếu capacity nền tảng.
8. Thiết kế hành vi khi quota service lỗi, reset counter, multi-region và policy rollout lệch phiên bản.
9. Diễn tập tenant A tăng tải, DB bão hòa, queue backlog và limiter unavailable; đo SLO của tenant A/B.
10. Viết ADR giải thích đánh đổi fairness, isolation, performance, security, cost và operations.

### Mẫu ma trận chính sách

| Workload | Metering unit | Tenant limit | Shared system guardrail | Khi vượt |
| --- | --- | --- | --- | --- |
| Read API | Request/cost unit | Rate + burst | Global concurrency | 429 hoặc backoff |
| Search | Search cost unit | Query rate + complexity | Timeout/shard capacity | Reject query nặng |
| Import | Worker seconds/records | Concurrent jobs + file size | Worker pool capacity | Queue hoặc reject |
| Export | Worker seconds/rows | Concurrent jobs | DB read budget | Defer/throttle |
| Storage | GB-month/requests | Soft/hard quota | Account-level cap | Alert/deny new upload |
| Egress | Bytes transferred | Monthly allowance | Network capacity | Throttle/overage policy |

### Tiêu chí hoàn thành

- Hạn mức phản ánh chi phí tài nguyên, không chỉ số request.
- Tenant context và metering không thể giả mạo từ client.
- Có fairness policy và tránh starvation cho workload cấp thấp.
- Một tenant không thể chiếm hết worker, DB connection hoặc cache memory.
- Limiter lỗi không mở toàn bộ hệ thống hoặc từ chối oan mọi tenant.
- Có metric phân biệt noisy neighbor, tải cao hợp lệ và thiếu capacity.
- Có quy trình tăng quota, tách pool và xử lý sự cố với audit.
- Kiểm thử chứng minh tenant B vẫn đáp ứng SLO khi tenant A tăng tải trong phạm vi mô phỏng.

## 18. Checklist Well-Architected trước khi đưa quota và resource isolation vào production

- [ ] Đã lập bản đồ tài nguyên dùng chung và đo chi phí theo loại workload.
- [ ] Quota theo kỳ, rate limit, burst, concurrency và system cap được phân biệt rõ.
- [ ] Hạn mức phản ánh gói dịch vụ và có owner/reset/overage behavior.
- [ ] Có fair scheduling/weighted sharing cho pool tranh chấp; không chỉ dùng first-come first-served.
- [ ] Có minimum reserve cho system workload và headroom phục hồi.
- [ ] Queue hữu hạn, backlog age và per-tenant pending cap được kiểm soát.
- [ ] Database, cache, search, worker, storage và egress có guardrail phù hợp.
- [ ] Shared/segmented/dedicated pool được chọn theo nhu cầu cô lập và chi phí.
- [ ] Tenant identity được xác minh; client không thể tự nâng quota/priority hoặc giả tenant context.
- [ ] Telemetry theo tenant/workload có quyền truy cập, retention và masking phù hợp.
- [ ] Limiter có chiến lược timeout, fail-open/fail-closed, local cap và reconciliation.
- [ ] Multi-region quota/counter có semantics và xử lý oversubscription được xác định.
- [ ] Retry/backoff/idempotency ngăn quota và dependency bị khuếch đại tải.
- [ ] Có dashboard/cảnh báo phân biệt tenant vượt policy với capacity planning thiếu.
- [ ] Có runbook điều tiết, nâng quota, chuyển pool, rollback policy và audit.
- [ ] Đã kiểm thử noisy neighbor và chứng minh SLO của tenant khác được bảo vệ.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** quota nói tenant được dùng bao nhiêu; rate limit và concurrency kiểm soát tốc độ cùng số công việc đang chạy; fair scheduling và resource pool quyết định cách chia năng lực khi có tranh chấp. Muốn ngăn noisy neighbor bền vững, hệ thống phải **đo chi phí theo workload, xác minh tenant context, giới hạn nhiều tầng, phân bổ công bằng và có khả năng cô lập khi cần**. Hạn mức chỉ thực sự hiệu quả khi được kiểm chứng bằng SLO của cả tenant gây tải lẫn những tenant cùng chia sẻ nền tảng.
