# Xây dựng baseline hiệu năng và capacity plan

Một hệ thống có thể chạy nhanh trong ngày thử nghiệm nhưng trở nên chậm khi lượng người dùng tăng, xảy ra chiến dịch khuyến mãi hoặc một Availability Zone gặp sự cố. Nếu chỉ chọn cấu hình máy chủ theo cảm giác, đội vận hành dễ rơi vào hai tình huống: cấp quá ít tài nguyên khiến ứng dụng nghẽn, hoặc cấp quá nhiều tài nguyên làm chi phí Azure tăng mà hiệu năng không cải thiện tương ứng.

Trong chương **Hiệu năng và vận hành** của lộ trình **CLOUD_PROVIDERS_AZURE**, bài học này trình bày cách đo **baseline hiệu năng** và xây dựng **capacity plan** có thể kiểm chứng. Phương pháp áp dụng cho kiến trúc trên Microsoft Azure, từ subscription, resource group, mạng, dịch vụ tính toán đến lưu trữ, dữ liệu, giám sát, bảo mật và kiểm soát chi phí. Ví dụ sử dụng một ứng dụng đặt hàng chạy trên Azure Kubernetes Service (AKS), Azure Container Apps hoặc Azure App Service, kết nối Azure SQL Database/Storage và các dịch vụ phụ thuộc.

Baseline phải trả lời: **hiện hệ thống xử lý lưu lượng bao nhiêu, với độ trễ, lỗi và mức sử dụng tài nguyên nào, trong điều kiện gì?** Capacity plan phải trả lời: **khi lưu lượng thay đổi, cần bao nhiêu tài nguyên, mất bao lâu để cấp thêm, chi phí dự kiến là bao nhiêu, và hệ thống còn hoạt động được khi có sự cố hay không?**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt baseline, benchmark, SLI, SLO, capacity, headroom, forecast và capacity plan.
2. Thu thập throughput, latency, error rate, saturation, concurrency cùng tín hiệu nghiệp vụ từ Azure Monitor, Application Insights và telemetry ứng dụng.
3. Xác định workload thực tế, xây dựng kịch bản kiểm thử tải có thể tái lập và nhận diện điểm bão hòa.
4. Tính capacity sơ bộ bằng throughput đã đo, Little's Law, headroom, mức tăng trưởng và yêu cầu chịu lỗi.
5. Lập kế hoạch tài nguyên cho compute, database, cache, message queue, storage và mạng thay vì chỉ tăng số instance.
6. Liên kết capacity plan với autoscale, quota Azure, SLO, ngân sách chi phí và quy trình thay đổi hạ tầng.
7. Trình bày một bản kế hoạch có giả định, số liệu nguồn, ngưỡng hành động, người chịu trách nhiệm và lịch kiểm tra lại.

## 2. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa | Câu hỏi minh họa |
| --- | --- | --- |
| **Performance baseline** | Mốc số liệu hiệu năng của một cấu hình và workload đã xác định | Ở 120 request/giây, p95 và CPU là bao nhiêu? |
| **Benchmark** | Phép đo có quy trình, điều kiện và mục tiêu so sánh | Bản phát hành mới xử lý cùng workload nhanh hơn hay chậm hơn? |
| **Capacity** | Mức tải có thể phục vụ trong các ràng buộc về hiệu năng và tính đúng đắn | Tối đa bao nhiêu request/giây khi p95 vẫn đạt SLO? |
| **Headroom** | Phần công suất dự phòng có thể dùng khi tải tăng hoặc tài nguyên mất đi | Còn đủ chỗ xử lý burst trước khi scale thêm không? |
| **Capacity forecast** | Dự báo nhu cầu tải và tài nguyên theo thời gian | Quý tới peak RPS tăng 30% sẽ cần bao nhiêu replica? |
| **Capacity plan** | Quyết định về tài nguyên, giới hạn, thời điểm cấp thêm, chi phí, rủi ro và kiểm chứng | Cần tăng quota, node pool và RU/s khi nào? |
| **SLI** | Chỉ số định lượng mức dịch vụ, ví dụ tỷ lệ request thành công | Tỷ lệ request hợp lệ thành công trong 30 ngày? |
| **SLO** | Mục tiêu đặt cho SLI, ví dụ 99,9% request hợp lệ thành công | Mức dịch vụ nào phải được bảo đảm? |

Baseline không đồng nghĩa với **đỉnh công suất**. Baseline là ảnh chụp có bối cảnh về hành vi thông thường hoặc một mức tải được lựa chọn. Đỉnh công suất cần được tìm bằng benchmark/load test có tiêu chí dừng và đối chiếu SLO.

**Ví dụ:** p95 của API là 300 ms trong ngày thường, nhưng khi traffic tăng gấp đôi, p95 lên 1,8 giây và lỗi 503 tăng. Không thể kết luận hệ thống có capacity gấp đôi chỉ từ CPU trung bình còn 40%, vì nghẽn có thể nằm ở database connection pool, storage IOPS, network hoặc một dependency khác.

## 3. Xác định workload trước khi đo

### 3.1. Phân loại hành trình người dùng

Một ứng dụng thương mại điện tử có các hành trình chịu tải khác nhau:

| Hành trình | Endpoint minh họa | Tài nguyên chính | Rủi ro khi tải tăng |
| --- | --- | --- | --- |
| Xem sản phẩm | GET /products | Cache, database read, outbound HTTP | Cache miss, hot key, read latency |
| Tìm kiếm | GET /search | Search/index, CPU, network | Query đắt, fan-out |
| Xem giỏ | GET /cart | Session store, cache, database | Hot partition, lock |
| Đặt hàng | POST /orders | Database write, transaction, queue | Lock contention, ghi trùng, backlog |
| Xử lý thanh toán | Webhook/worker | Queue, payment API, database | Rate limit, retry storm, pending jobs |
| Chạy báo cáo | Background job | CPU, database, storage | Tranh chấp với giao dịch trực tuyến |

Đo cùng một số **RPS tổng** chưa đủ. Ví dụ, 1.000 request đọc cache có thể nhẹ hơn 100 request tạo đơn có nhiều giao dịch dữ liệu. Mỗi lần benchmark nên ghi **tỷ lệ từng loại nghiệp vụ**, kích thước payload, cache hit rate, tỉ lệ đọc/ghi, số lời gọi downstream và tỉ lệ người dùng đồng thời.

### 3.2. Nhận diện hình dạng lưu lượng

Phân tích tối thiểu:

- **Mức bình thường:** lưu lượng theo phút/giờ và ngày trong tuần.
- **Giờ cao điểm:** peak theo các cửa sổ 1, 5 hoặc 15 phút; nếu cần phải xem burst theo giây.
- **Mùa vụ/sự kiện:** ngày lương, đợt sale, đóng sổ, chạy batch, triển khai chiến dịch.
- **Tốc độ tăng:** xu hướng tuần/tháng/quý, tách tăng trưởng thật với sự kiện một lần.
- **Biến thiên địa lý:** vùng đặt người dùng, độ trễ qua Internet và giữa các Azure region.
- **Thay đổi phiên bản:** feature flag, bản build, cache policy hoặc database schema mới.

Nếu hệ thống chưa có lưu lượng production, dùng dự báo từ sản phẩm và load test để xây baseline ban đầu, rồi cập nhật sau khi có traffic thật. Ghi rõ mức độ tin cậy thấp hơn của baseline được suy ra từ giả định.

### 3.3. Khung mô tả workload

Ví dụ minh họa, **không phải số liệu được đo từ một hệ thống Azure thực**:

~~~yaml
workload: orders-api
environment: production
region: southeastasia
release: 2026.11.example
measurementWindow: "14 ngay dai dien"
traffic:
  normalRps: 70
  peak15mRps: 220
  burstRps: 350
  readPercent: 75
  writePercent: 25
dependencies:
  inventoryCallsPerRequest: 0.8
  paymentCallsPerRequest: 0.12
  cacheHitRate: 0.82
objectives:
  availabilitySloPercent: 99.9
  latencyP95TargetMs: 500
~~~

Tài liệu đo phải chỉ rõ **RPS ở đâu**: request tại ingress, request hợp lệ sau xác thực, transaction nghiệp vụ hay số attempt thực tế đến downstream. Chúng không nhất thiết bằng nhau do retry, cache, polling và fan-out.

## 4. Bộ chỉ số tối thiểu của baseline

### 4.1. Traffic, latency, errors, saturation

Bốn nhóm tín hiệu thường dùng trong vận hành dịch vụ là **traffic**, **latency**, **errors** và **saturation**:

| Nhóm | Chỉ số cần lưu | Cách đọc |
| --- | --- | --- |
| **Traffic** | Requests/second, transactions/second, bytes/s, messages/s | Lượng công việc thực sự đến hệ thống |
| **Latency** | p50, p95, p99; thời gian theo từng dependency | Tỷ lệ lớn người dùng có trải nghiệm chậm đến mức nào |
| **Errors** | 5xx, timeout, lỗi nghiệp vụ, request bị throttle, failed dependencies | Phân biệt lỗi ứng dụng với hành vi từ chối có chủ đích |
| **Saturation** | CPU, memory, GC, thread pool, connection pool, queue depth, IOPS, RU/s | Tài nguyên nào tiến gần giới hạn |

Nên bổ sung **số request đồng thời**, throughput hoàn tất, backlog tăng/giảm, tỷ lệ retry, cache hit/miss và số công việc thành công trên mỗi đơn vị tài nguyên. Chỉ số nghiệp vụ như **đơn hàng hoàn tất/phút** có thể quan trọng hơn tổng số HTTP 200.

**Không kết luận từ CPU đơn lẻ.** CPU 30% vẫn có thể đi kèm p99 5 giây nếu ứng dụng chờ cơ sở dữ liệu hoặc kết nối bên ngoài. Ngược lại, CPU tăng trong khi throughput và latency vẫn ổn định có thể chấp nhận được nếu còn headroom và ứng dụng chưa vượt SLO.

### 4.2. Percentile khác trung bình

Giả sử trong 100 request, có 95 request phản hồi dưới 200 ms và 5 request mất gần 3 giây. Thời gian trung bình có thể nhìn tương đối tốt, nhưng nhóm người dùng gặp tail latency vẫn có trải nghiệm rất kém.

- **p50** là latency mà khoảng một nửa request không vượt quá.
- **p95** là latency mà khoảng 95% request không vượt quá.
- **p99** cho biết vùng đuôi chậm nhất, đặc biệt hữu ích với dịch vụ nhạy latency.

Phải ghi rõ **cửa sổ tính percentile** và tập request. **Không lấy trung bình p95 của từng instance hoặc từng giờ rồi gọi đó là p95 toàn hệ thống**. Percentile chung cần được tính từ phân phối latency hoặc histogram có thể hợp nhất phù hợp; nếu chỉ có log đã lấy mẫu, phải xem chính sách sampling trước khi suy ra percentile chính xác.

### 4.3. Định nghĩa request thành công

HTTP 200 không luôn đồng nghĩa một giao dịch nghiệp vụ đã hoàn tất. Một API có thể trả 202 Accepted trong khi đơn hàng còn nằm trong queue. Baseline nghiệp vụ cần có các trạng thái **đã xử lý, đang chờ, đã thất bại, được hoàn tiền/đối soát**. Với hệ thống hàng đợi, throughput nên đo cả số message được nhận và **số message thực sự hoàn tất**, cùng độ tuổi của message lâu nhất.

## 5. Gắn telemetry trong kiến trúc Azure

Một kiến trúc quan sát thông thường:

~~~mermaid
flowchart LR
    C["Client"] --> G["Front Door / API Management / Ingress"]
    G --> A["Ứng dụng trên App Service, AKS hoặc Container Apps"]
    A --> D["Database / Cache / Storage"]
    A --> Q["Service Bus / background workers"]
    G -. "Request metrics" .-> M["Azure Monitor"]
    A -. "OpenTelemetry / Application Insights" .-> M
    D -. "Resource metrics / logs" .-> M
    Q -. "Queue metrics / logs" .-> M
    M --> L["Log Analytics, dashboards và alerts"]
~~~

**Azure Monitor** thu nhận metrics và logs tùy dịch vụ/tính năng được bật. **Application Insights** theo dõi request, dependency, exception, trace và telemetry ứng dụng; trong nhiều hệ thống có thể tích hợp **OpenTelemetry** để thống nhất trace context. **Log Analytics workspace** cho phép truy vấn telemetry theo Kusto Query Language (KQL). AKS có thể dùng các công cụ quan sát container và node phù hợp, cùng metrics từ nền tảng/ứng dụng.

### 5.1. Những chiều dữ liệu cần gắn

Một phép đo có ý nghĩa khi đi kèm metadata:

| Chiều | Ví dụ | Lợi ích |
| --- | --- | --- |
| Environment | dev, staging, prod | Không trộn tải thử với tải thật |
| Service/operation | orders-api / POST /orders | Xác định luồng gây nghẽn |
| Region/zone | southeastasia / zone phân bổ | Phân tích độ trễ và sự cố cục bộ |
| Deployment version | commit SHA hoặc release ID | So sánh trước/sau triển khai |
| Instance/replica | Pod, container, App Service instance | Xác định tải phân phối không đều |
| Dependency | Azure SQL, Redis, Inventory API | Phân biệt lỗi ứng dụng và downstream |
| Response class | 2xx, 4xx, 5xx, timeout | Thống kê lỗi đúng hợp đồng |

Không gắn user ID, token, email, dữ liệu thanh toán hoặc giá trị có cardinality cực lớn vào **metric label** chỉ để phân tích hiệu năng. Dùng trace/log có chính sách bảo vệ dữ liệu khi cần truy vết từng request.

### 5.2. Tần suất và chất lượng số liệu

Đặt độ phân giải tùy mục tiêu: dữ liệu theo giờ phù hợp phân tích xu hướng, nhưng có thể che một burst 30 giây làm dịch vụ bị lỗi. Vì thế cần song song **tổng hợp dài hạn** và **cửa sổ ngắn** cho peak, lỗi, autoscale.

Kiểm tra:

1. Đồng bộ thời gian và cấu hình timezone khi dựng báo cáo.
2. Telemetry có bị sampling hoặc mất dữ liệu khi hệ thống quá tải không.
3. Các lần deploy, scale, failover và thay đổi cấu hình có được đánh dấu không.
4. Các metric ứng dụng và metric Azure có cùng đơn vị thời gian và cửa sổ tính không.
5. Chi phí ingest/retention telemetry có phù hợp ngân sách không.

## 6. Thu thập baseline bằng Azure Monitor và KQL

### 6.1. Ví dụ truy vấn request

Trong một **workspace-based Application Insights** có bảng **AppRequests**, có thể bắt đầu bằng truy vấn sau:

~~~kusto
AppRequests
| where TimeGenerated >= ago(14d)
| where Name has "/orders"
| summarize
    rawRows = count(),
    estimatedRequests = sum(ItemCount),
    failedRows = countif(Success == false),
    avgDurationMs = avg(DurationMs),
    p95DurationMs = percentile(DurationMs, 95),
    p99DurationMs = percentile(DurationMs, 99)
  by bin(TimeGenerated, 1h), Name
| extend approxRps = estimatedRequests / 3600.0
| order by TimeGenerated asc
~~~

**Lưu ý khi sử dụng:**

- Tên bảng và cột tùy chế độ Application Insights, workspace và schema. Chế độ/classic query có thể dùng bảng **requests** với **timestamp**, **duration**, **name**. Kiểm tra schema trước khi chạy.
- **ItemCount** phản ánh số lượng được đại diện bởi bản ghi trong những cấu hình có sampling; cách ước lượng lưu lượng và lỗi phải phù hợp chính sách sampling.
- Percentile tính trực tiếp trên những bản ghi còn lại **không tự động là percentile chính xác của toàn bộ request** khi sampling có trọng số hoặc không đồng đều. Dùng histogram/metrics thích hợp hoặc dữ liệu test đầy đủ cho baseline quan trọng.
- Truy vấn theo nhóm một giờ có thể che peak 1 phút. Thêm một báo cáo **bin(TimeGenerated, 1m)** khi cần đánh giá burst, đồng thời tránh suy luận percentile từ nhóm quá ít mẫu.
- Điều kiện **Name has "/orders"** chỉ là ví dụ. Hãy lọc endpoint/operation thật và loại trừ probe, bot hoặc synthetic requests nếu chúng không thuộc SLI.

### 6.2. Truy vấn độ trễ downstream

~~~kusto
AppDependencies
| where TimeGenerated >= ago(7d)
| summarize
    calls = count(),
    failures = countif(Success == false),
    p95Ms = percentile(DurationMs, 95)
  by Target, Type, bin(TimeGenerated, 1h)
| order by failures desc
~~~

Đối chiếu p95 dependency với p95 end-to-end: nếu độ trễ tổng tăng nhưng dependency không đổi, kiểm tra CPU, thread pool, serialization hoặc queue nội bộ. Nếu Azure SQL/Storage tăng thời gian xử lý đúng giờ cao điểm, xem database resource metrics, throughput, throttling và khả năng contention.

### 6.3. Baseline cần lưu thành tài liệu

Ví dụ **bảng baseline minh họa** sau một đợt đo:

| Chỉ số | Giờ bình thường | Giờ cao điểm | Mục tiêu / diễn giải |
| --- | ---: | ---: | --- |
| Ingress RPS | 70 | 220 | Kiểm tra đúng khoảng lấy mẫu |
| Request p50 | 95 ms | 140 ms | Quan sát trải nghiệm thông thường |
| Request p95 | 260 ms | 430 ms | Mục tiêu p95 không quá 500 ms |
| Request p99 | 580 ms | 960 ms | Theo dõi tail latency |
| Tỷ lệ lỗi kỹ thuật | 0,1% | 0,3% | Cần định nghĩa rõ mẫu số |
| CPU trung bình mỗi replica | 36% | 62% | Chưa kết luận capacity chỉ từ CPU |
| Memory working set | 690 MiB | 880 MiB | So với limit và xu hướng rò rỉ |
| Inventory API p95 | 90 ms | 210 ms | Có thể trở thành dependency bottleneck |
| Queue backlog | Gần 0 | Tăng ngắn hạn | Kiểm tra thời gian tiêu backlog |

Phải ghi **nguồn dữ liệu, ngày đo, phiên bản ứng dụng, loại VM/node/plan, cấu hình database, số replica, region, cache state và mix request**. Nếu các yếu tố này thay đổi, không so sánh hai con số p95 như thể điều kiện giống hệt nhau.

## 7. Thiết kế benchmark và kiểm thử tải

### 7.1. Những loại kiểm thử cần phân biệt

| Loại kiểm thử | Cách tạo tải | Mục đích |
| --- | --- | --- |
| **Baseline load test** | Tải ổn định ở mức thường | Đo mốc p95, error rate và resource usage |
| **Capacity/step test** | Tăng RPS theo từng nấc có khoảng giữ tải | Tìm điểm throughput không còn tăng tương ứng hoặc SLO bị vi phạm |
| **Stress test** | Vượt tải dự kiến có kiểm soát | Xem hệ thống từ chối, degrade và phục hồi |
| **Spike test** | Tăng đột ngột trong thời gian ngắn | Kiểm tra headroom, autoscale lag, connection pools |
| **Soak/endurance test** | Tải dài đủ để quan sát tích lũy | Tìm memory leak, GC, pool leak, tăng backlog |
| **Scale/failover test** | Tăng/giảm replica, làm mất một thành phần trong môi trường test | Đo thời gian scale, khả năng chịu lỗi và capacity sau sự cố |

**Azure Load Testing** là một lựa chọn để tổ chức kiểm thử tải trên Azure; tùy tính năng và phiên bản dịch vụ, có thể sử dụng kịch bản dựa trên Apache JMeter và quan sát metrics của các tài nguyên Azure. Ngoài ra có thể dùng công cụ kiểm thử tải phù hợp khác. Việc chọn công cụ phải dựa trên loại giao thức, hỗ trợ xác thực, khả năng tạo lưu lượng, chi phí và nhu cầu báo cáo.

### 7.2. Trình tự một buổi benchmark

1. **Khóa điều kiện:** ghi commit, image digest, CPU/memory request/limit, node SKU, database tier, số replica, region và feature flags.
2. **Chuẩn bị dữ liệu:** kích thước dataset và phân phối khóa sát production, dữ liệu giả hoặc dữ liệu đã được cho phép; tránh dùng bí mật hoặc dữ liệu khách hàng thật.
3. **Chuẩn bị test generator:** chắc chắn máy phát tải không phải bottleneck; quan sát CPU/network của generator.
4. **Warm-up:** để JIT, pool kết nối, cache và quá trình scale đạt trạng thái phù hợp với mục tiêu test.
5. **Đo baseline:** giữ tải đủ lâu ở mức ổn định, ghi số mẫu và metric cùng mốc thời gian.
6. **Tăng từng nấc:** chẳng hạn 50 → 100 → 150 → 200 → 250 RPS, nhưng điều chỉnh theo capacity thật.
7. **Dừng khi đạt guardrail:** p95 vượt SLO, lỗi tăng, hệ thống có nguy cơ làm hỏng dữ liệu hoặc sử dụng tài nguyên vượt mức được phép.
8. **Giảm tải và quan sát phục hồi:** đo backlog, pool, GC, health check và thời gian trở về bình thường.
9. **Lặp lại:** kiểm tra biến động giữa các lần thử và đối chiếu nguyên nhân.

### 7.3. Phân biệt mô hình phát tải

**Closed-loop** thường mô phỏng một số người dùng ảo: mỗi người chờ phản hồi rồi gửi yêu cầu mới. Khi hệ thống chậm, tổng request rate tự giảm, có nguy cơ che mức tải mà production sẽ tiếp tục gửi.

**Open-loop** phát request theo arrival rate đã định, hữu ích để đánh giá hệ thống dưới lưu lượng đến không phụ thuộc tốc độ trả lời. Nếu mục tiêu là 220 RPS, phải đo **RPS thực gửi được**, không chỉ cấu hình mục tiêu trong tool.

Cả hai mô hình đều có ích, nhưng không được so sánh số liệu khi không ghi rõ cách tạo tải, thời gian think time, mô hình session và tỷ lệ hành trình nghiệp vụ. Với test tạo dữ liệu, phải xử lý idempotency/cleanup để tránh làm bẩn trạng thái.

## 8. Tìm điểm capacity hữu dụng

Khả năng chịu tải không phải con số CPU đạt 100%. Một hệ thống có **usable capacity** tại mức cao nhất mà vẫn thỏa các mục tiêu về lỗi, latency, tính đúng đắn và khả năng vận hành.

Ví dụ đo trên một replica ứng dụng, trong cùng cấu hình và mix request:

| Tải vào/replica | CPU trung bình | p95 | Tỷ lệ lỗi | Nhận xét |
| ---: | ---: | ---: | ---: | --- |
| 18 RPS | 35% | 190 ms | 0,0% | Còn nhiều headroom |
| 28 RPS | 48% | 260 ms | 0,1% | Đáp ứng mục tiêu |
| 35 RPS | 61% | 340 ms | 0,1% | Mức được chọn để lập kế hoạch |
| 42 RPS | 76% | 530 ms | 0,4% | p95 vượt mục tiêu 500 ms |
| 50 RPS | 90% | 1.200 ms | 2,1% | Tiến gần bão hòa |

**Kết luận cho ví dụ:** chọn **35 RPS/replica** làm capacity vận hành ban đầu vì mức tải này đã được kiểm thử, nằm dưới mục tiêu p95 500 ms và còn dư địa cho biến động. Không suy ra 100% CPU tương ứng bao nhiêu RPS theo phép nhân tuyến tính: bottleneck, GC, lock, connection pool và queue thường khiến hiệu năng phi tuyến khi gần bão hòa.

Con số **35 RPS/replica** chỉ có ý nghĩa với cấu hình được đo. Nếu thay VM size, CPU request, runtime, database tier, phiên bản ứng dụng hoặc tỷ lệ nghiệp vụ thì phải đánh giá lại.

### 8.1. Throughput, arrival rate và thời gian chờ

Khi hệ thống ổn định, throughput hoàn tất xấp xỉ arrival rate. Nếu arrival rate vượt khả năng xử lý trong thời gian dài, backlog sẽ tăng. Các chỉ số cần quan sát đồng thời:

- Số request gửi đến.
- Số request hoàn tất thành công/thất bại.
- Số request đang chờ hoặc bị từ chối.
- Độ dài queue và tuổi request lâu nhất.
- Độ trễ từng tầng: ingress, ứng dụng, database, queue consumer.

Một throughput bằng 200 RPS không phải kết quả tốt nếu có thêm 100 RPS đang tích lũy trong queue. Ngược lại, cơ chế backpressure trả 429/503 có kiểm soát có thể bảo vệ tính sẵn sàng của phần hệ thống còn lại.

### 8.2. Little's Law để ước lượng concurrency

Với hệ thống ổn định, trong cùng ranh giới đo:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống.
- \(\lambda\): tốc độ request hoàn tất trung bình, tính bằng request/giây.
- \(W\): thời gian trung bình một request tồn tại trong hệ thống, tính bằng giây.

Nếu mỗi replica xử lý **35 RPS**, thời gian trung bình **180 ms = 0,18 giây**:

\[
L = 35 \times 0{,}18 = 6{,}3
\]

Trung bình mỗi replica có khoảng **6–7 request đang xử lý hoặc chờ trong ranh giới đã đo**. Con số này không bằng p95 latency nhân RPS, vì Little's Law dùng **thời gian trung bình**, và không có nghĩa thread pool chỉ cần 7 thread: phải xét burst, fan-out, blocking I/O, pool limits và backlog.

Không áp dụng công thức một cách tùy tiện khi queue liên tục tăng, workload không ổn định hoặc đơn vị thời gian không nhất quán.

## 9. Tính số replica và dự phòng chịu lỗi

Sử dụng bộ số liệu minh họa:

- Peak đã quan sát: **220 RPS**.
- Safe capacity đã kiểm thử: **35 RPS/replica**.
- Forecast tăng trưởng peak: **30%**.
- Mục tiêu: p95 không quá 500 ms ở workload được kiểm thử.

### 9.1. Capacity tối thiểu ở peak hiện tại

\[
N_{peak} = \left\lceil \frac{220}{35} \right\rceil = 7
\]

Cần ít nhất **7 replica có khả năng xử lý tương đương** trong điều kiện lý tưởng, nếu lưu lượng phân phối đều và dependency vẫn đủ capacity.

Để có một replica dự phòng theo giả định **mất một replica**:

\[
N_{N+1} = 7 + 1 = 8
\]

Tuy nhiên **8 replica không tự bảo đảm chịu được mất cả Availability Zone**. Nếu nhiều replica cùng nằm ở zone bị lỗi, số còn lại có thể thấp hơn 7.

### 9.2. Capacity sau 30% tăng trưởng

\[
RPS_{forecast} = 220 \times 1{,}30 = 286
\]

\[
N_{forecast} = \left\lceil \frac{286}{35} \right\rceil = 9
\]

Với dự phòng mất một replica, cần xem xét ít nhất **10 replica** ở peak mới, chưa tính mất zone, giới hạn platform, startup time và các rủi ro khác.

### 9.3. Mất cả một Availability Zone

Giả sử workload và dịch vụ hỗ trợ triển khai trên **3 zone**, tải chia đều và tất cả replica có cùng safe capacity:

| Kịch bản | Phân bổ ví dụ | Số còn lại nếu mất zone có nhiều replica nhất | Đủ capacity theo giả định? |
| --- | --- | ---: | --- |
| 8 replica, peak 220 RPS | 3 / 3 / 2 | 5 | **Không**, cần 7 |
| 12 replica, peak 220 RPS | 4 / 4 / 4 | 8 | **Có**, 8 ≥ 7 |
| 10 replica, peak 286 RPS | 4 / 3 / 3 | 6 | **Không**, cần 9 |
| 15 replica, peak 286 RPS | 5 / 5 / 5 | 10 | **Có**, 10 ≥ 9 |

Đây là bài toán **capacity số học**, chưa chứng minh hệ thống thực sẽ chịu được mất zone. Còn phải kiểm tra khả năng bố trí Pod/instance đúng zone, node availability, quota, database failover, kết nối, DNS, health probe, thời gian chuyển lưu lượng và khả năng khởi động replica bổ sung.

**N+1 replica** và **zone resilience** là hai mức dự phòng khác nhau. Nếu yêu cầu phục hồi sau sự cố cấp vùng, cần một bài toán capacity riêng cho **multi-region**, replication và RTO/RPO.

## 10. Capacity là chuỗi các điểm nghẽn, không chỉ compute

Một request đi qua nhiều tầng. Nếu compute đủ 300 RPS nhưng database chỉ giữ SLO ở 180 RPS thì **capacity thực tế của toàn luồng vẫn bị giới hạn bởi database**.

~~~mermaid
flowchart LR
    C["220 RPS từ client"] --> G["Gateway / ingress"]
    G --> A["Compute replicas"]
    A --> D["Azure SQL / Cosmos DB"]
    A --> K["Cache"]
    A --> Q["Service Bus"]
    D --> S["Storage / network / IO"]
~~~

### 10.1. Azure SQL Database

Quan sát CPU/vCore hoặc DTU tùy mô hình, memory/IO nếu khả dụng, số kết nối, độ trễ query, deadlock, lock wait, log write và truy vấn tốn tài nguyên. Capacity có thể tăng bằng tối ưu index, giảm số query, cache phù hợp, pooling, read scale theo kiến trúc hoặc chọn tier/compute thích hợp.

Không tăng SQL tier chỉ vì request latency tăng. Trước hết xác định query plan, index, lock contention, lỗi ứng dụng hoặc pattern truy vấn N+1. Khi database tier thay đổi, cần benchmark lại ở đúng dữ liệu và mix request.

### 10.2. Azure Cosmos DB

Capacity cần tính theo **request units per second (RU/s)** và **phân phối tải theo partition**. Một phép ước lượng sơ bộ:

\[
RU/s_{estimate} = \sum_i (operationRate_i \times averageRU_i)
\]

Ví dụ **150 reads/s × 3 RU/read** và **50 writes/s × 8 RU/write**:

\[
RU/s = 150 \times 3 + 50 \times 8 = 850
\]

**850 RU/s là nhu cầu tính toán trung bình theo giả định**, chưa bao gồm burst, chênh lệch kích thước document/query, indexing, background load, partition imbalance hoặc hiệu ứng hot partition. Hãy đo **RequestCharge**, throttling **429**, normalized RU consumption và latency thực tế trước khi chọn manual/autoscale throughput, đồng thời kiểm tra giới hạn/tính năng của tài khoản và partition.

### 10.3. Azure Cache for Redis hoặc dịch vụ cache được chọn

Quan sát cache hit ratio, memory pressure, eviction, network throughput, CPU, connection count và p95 latency. Tăng cache hit có thể giảm nhu cầu database, nhưng cache warming và cache stampede sau restart/failover có thể tạo đỉnh tải lớn.

Phân biệt **cache capacity theo dung lượng dữ liệu** với **capacity theo số operation/giây**. Một cache đủ RAM vẫn có thể nghẽn network hoặc CPU.

### 10.4. Azure Service Bus, Event Hubs và background workers

Với pipeline bất đồng bộ, đo:

- Message arrival rate và completion rate.
- Queue depth, message age, dead-letter count.
- Số consumer và concurrency mỗi consumer.
- Thời gian xử lý trung bình/p95, tỷ lệ retry, lock timeout hoặc throttling.
- Giới hạn throughput và quota của tier/namespace được chọn.

Nếu message vào **500/s** nhưng worker xử lý được **400/s**, backlog tăng khoảng **100 message/s** khi tốc độ đó duy trì. Sau 10 phút:

\[
backlog \approx 100 \times 600 = 60.000 \text{ messages}
\]

Ngay cả khi traffic giảm, phải tính **thời gian tiêu backlog**. Nếu worker xử lý 600/s và vẫn có 500/s đến, năng lực tiêu tồn là 100/s; cần khoảng 600 giây để dọn 60.000 message, giả định tốc độ ổn định và không phát sinh lỗi.

### 10.5. Storage và mạng

Quan sát Azure Storage transactions, ingress/egress, latency, throttling, dung lượng, throughput và IOPS phù hợp loại storage. Với kiến trúc phân vùng, kiểm tra hot partition hoặc các giới hạn theo tài khoản/tài nguyên.

Mạng cần tính cả bandwidth, số kết nối, SNAT port consumption khi outbound qua thành phần NAT, số connection mới/giây, round-trip time, dịch vụ gateway và lưu lượng liên vùng. Một trường hợp thiếu SNAT có thể xuất hiện như lỗi connection timeout trong khi CPU còn thấp.

### 10.6. Quota và subscription

**Autoscale không vượt qua quota và giới hạn nền tảng.** Kiểm tra vCPU quota theo family/region, số IP, node/Pod limit, subnet IP capacity, tài nguyên database/queue và quota riêng từng dịch vụ. Cần dự trù thời gian yêu cầu tăng quota và capacity availability của region; không chờ đến đúng ngày chiến dịch mới xin quota.

## 11. Xây capacity forecast theo kịch bản

Forecast phải tách **dự báo nhu cầu** khỏi **khả năng cấp tài nguyên**. Một mô hình ban đầu có thể dùng:

\[
Demand_{future} = BaselinePeak \times (1 + growthRate) \times eventFactor
\]

Ví dụ peak hiện tại **220 RPS**, tăng trưởng 30% và ngày sự kiện có đỉnh bằng **1,5 lần** mức peak đã tăng:

\[
Demand = 220 \times 1{,}30 \times 1{,}5 = 429 \text{ RPS}
\]

Nếu safe capacity vẫn là 35 RPS/replica thì số replica lý thuyết:

\[
\left\lceil 429 / 35 \right\rceil = 13
\]

Con số 13 chưa bao gồm dự phòng mất replica/zone, cũng chưa chứng minh database hoặc queue đáp ứng 429 RPS. Sự kiện ngắn cần kiểm tra **thời gian autoscale tăng công suất**: nếu traffic tăng trong 30 giây nhưng cấp node và warm-up mất vài phút, cần **pre-scale** hoặc đủ headroom ngay trước sự kiện.

### 11.1. Ba kịch bản để trình bày với đội vận hành

| Kịch bản | Đầu vào lưu lượng | Hành động cần xác minh |
| --- | --- | --- |
| **Base** | Peak đã đo 220 RPS | Duy trì SLO, quan sát giá trị bình thường |
| **Growth** | Peak tăng 30% lên 286 RPS | Điều chỉnh min/max replica, compute, database, quota |
| **Event / stress** | Peak ngắn 429 RPS | Pre-scale, rate limit, cache, queue, chính sách giảm tải |

Để tránh đánh giá thấp rủi ro, cần thêm kịch bản **mất một instance, zone hoặc dependency** trong khi tải đang cao. Dự báo nên bao gồm bất định: ví dụ growth 20–40% hoặc dải traffic dự kiến, không trình bày một giá trị duy nhất như cam kết chắc chắn.

### 11.2. Headroom và thời gian phản ứng

Có hai loại headroom cần quan tâm:

- **Headroom hiệu năng:** capacity còn dư so với tải đã kiểm chứng, dưới giới hạn SLO.
- **Headroom cấp phát:** quota, node, địa chỉ IP, database throughput và budget để scale thêm.

Nếu autoscale mất 5 phút mới thêm đủ replica nhưng spike bắt đầu trong 20 giây, headroom phải đủ hấp thụ traffic trong thời gian chờ. Với queue, cũng phải tính giới hạn backlog và thời gian chờ tối đa chấp nhận được.

## 12. Kết hợp capacity plan với autoscale trên Azure

### 12.1. Chọn tín hiệu scaling đúng bottleneck

| Nền tảng | Cơ chế thường dùng | Chỉ số cần cân nhắc |
| --- | --- | --- |
| **AKS** | Horizontal Pod Autoscaler (HPA), node autoscaling, cơ chế event-driven phù hợp | CPU, memory, custom/external metrics, pending Pods |
| **Azure Container Apps** | Scale rules theo HTTP, event/queue hoặc custom scaler khi hỗ trợ | Concurrent HTTP requests, queue depth, độ trễ |
| **Azure App Service** | App Service autoscale/automatic scaling tùy plan và tính năng | CPU, memory, HTTP queue, schedule, metric phù hợp |
| **Azure Functions** | Scale theo plan/trigger và cấu hình concurrency | Queue backlog, trigger throughput, execution duration |
| **Azure SQL/Cosmos DB** | Thay đổi compute/tier hoặc throughput theo cơ chế được hỗ trợ | Query latency, CPU/DTU, RU consumption, throttling |

Không có một autoscale policy duy nhất đúng cho toàn hệ thống. Ví dụ CPU-based scaling không phát hiện tốt khi ứng dụng nghẽn vì I/O hoặc đợi database. Scaling theo queue depth có thể hợp lý cho worker nhưng phải tính tốc độ xử lý và giới hạn downstream.

### 12.2. Ví dụ HPA cho AKS

Đoạn cấu hình sau minh họa HPA dựa trên CPU:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 4
  maxReplicas: 15
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

**Điều kiện:** deployment **orders-api** tồn tại, container có **CPU requests** phù hợp, hệ thống có resource metrics và node pool có khả năng cấp thêm Pod. HPA CPU utilization được hiểu tương đối với CPU **request**, không phải phần trăm CPU vật lý của toàn node. Ví dụ container request **500m** thì mức target 65% tương ứng trung bình khoảng **325m** CPU sử dụng trên mỗi Pod được tính, theo logic metric của HPA.

**minReplicas: 4** và **maxReplicas: 15** chỉ minh họa cú pháp. Với peak 220 RPS và yêu cầu chịu mất zone ở phần 9, **4 replica khởi đầu có thể thiếu capacity trước khi scale**. Production cần tính lại minimum replicas, zone distribution, PodDisruptionBudget/topology spread constraints, thời gian khởi động, cluster autoscaler và quota.

HPA không tự tạo node mới nếu node pool hết chỗ; node autoscaler cũng phải đáp ứng quota, tài nguyên và giới hạn mạng. CPU HPA có thể không giải quyết được tình trạng SQL bị throttling, và tăng Pod đôi khi còn tăng áp lực lên database.

### 12.3. Kịch bản kiểm thử scale

Một kế hoạch kiểm thử autoscale nên ghi:

1. Mức load khiến metric vượt ngưỡng và thời điểm bắt đầu.
2. Thời gian HPA quyết định replica mới.
3. Thời gian node mới sẵn sàng nếu cần.
4. Thời gian image pull, khởi động app, warm-up cache và readiness.
5. p95/error rate trong toàn bộ quá trình chuyển tiếp.
6. Thời gian giảm tải và khả năng scale down không làm gián đoạn giao dịch.

**Scale-to-zero**, cold start và min replicas cần được đánh giá đặc biệt với workload tương tác. Không nên chỉ nhìn số replica cuối cùng mà bỏ qua trải nghiệm trong khoảng scale chưa kịp.

## 13. SLO, error budget và guardrail cho capacity

Một capacity plan cần các tiêu chí **chấp nhận/từ chối** cụ thể. Ví dụ SLO minh họa:

- Trong 30 ngày, **99,9% request hợp lệ được phục vụ thành công**, theo định nghĩa SLI.
- Ở peak 220 RPS với mix nghiệp vụ đã định, **p95 end-to-end không quá 500 ms**.
- Tỷ lệ timeout hoặc 5xx ở workload thử nghiệm không vượt ngưỡng do đội vận hành quy định.
- Khi một replica bị loại khỏi dịch vụ, hệ thống vẫn phục vụ trong giới hạn đã thống nhất.

Nếu chọn SLO availability **99,9%** trên tổng số request hợp lệ, error budget danh nghĩa là **0,1% số request trong cửa sổ đo**. Không tự quy đổi trực tiếp thành “43,2 phút downtime/tháng” cho mọi hệ thống, vì SLI theo request và SLI theo thời gian là hai cách định nghĩa khác nhau.

### 13.1. Guardrail trong load test

Một bộ guardrail minh họa:

| Điều kiện | Hành động |
| --- | --- |
| p95 vượt 500 ms trong cửa sổ đo ổn định | Ghi nhận mức tải là vượt tiêu chí capacity |
| Tỷ lệ 5xx/timeout tăng đột biến | Dừng tăng tải, kiểm tra dependency |
| Queue oldest-message age vượt giới hạn nghiệp vụ | Dừng tăng tải và kiểm tra worker/capacity |
| Memory tăng không hồi phục khi giảm tải | Chạy soak/profiling để tìm leak |
| Database throttling tăng mạnh | Không tự tăng replica ứng dụng; kiểm tra database throughput |
| Dữ liệu test có nguy cơ ảnh hưởng hệ thống ngoài phạm vi | Ngừng test và cô lập workload |

SLO nên đo theo hành trình quan trọng, region và môi trường. Không dùng một p95 tổng hợp để che sự cố chỉ ảnh hưởng nhóm người dùng nhất định.

## 14. Kế hoạch chi phí và hiệu quả tài nguyên

Capacity plan cần chỉ rõ **khả năng chi trả**. Chi phí Azure có thể bao gồm compute, storage, database, caching, networking/egress, log ingestion, monitoring, load testing và các cơ chế dự phòng.

### 14.1. Công thức tính chi phí minh họa

Giả định **một đơn vị compute tương đương với một replica có chi phí 0,12 USD/giờ**, chạy **730 giờ/tháng**. Đây là **giá giả định để học tính toán**, không phải báo giá Azure và không áp dụng nguyên trạng cho AKS/App Service/Container Apps.

~~~text
monthlyComputeCost = capacityUnits × unitCostPerHour × hoursPerMonth
~~~

| Kịch bản | Đơn vị compute | Tính toán | Chi phí giả định/tháng |
| --- | ---: | --- | ---: |
| Peak 220 RPS, N+1 | 8 | 8 × 0,12 × 730 | 700,80 USD |
| Peak 220 RPS, chịu mất một zone (giả định) | 12 | 12 × 0,12 × 730 | 1.051,20 USD |
| Peak 286 RPS, chịu mất một zone (giả định) | 15 | 15 × 0,12 × 730 | 1.314,00 USD |

**Lưu ý quan trọng:** Chi phí thực trên AKS thường phụ thuộc VM/node, disk, network, load balancer và các thành phần khác; một Pod/replica không có mức giá cố định tách biệt khi dùng chung node. Container Apps và App Service có mô hình tính phí khác. Dùng **Azure Pricing Calculator, Azure Cost Management** và báo giá áp dụng cho subscription/region của dự án để thay các giả định trên bằng giá thực.

### 14.2. Hiệu quả và dự phòng

Không thể tối ưu chi phí chỉ bằng cách giảm số replica. Phải cân đối:

- Chi phí thường trực của min replicas so với thời gian scale lên khi có spike.
- Số node/zone để chịu lỗi so với mức dịch vụ yêu cầu.
- Database reserved capacity/tier và mức dư thừa cần thiết.
- Tỷ lệ cache hit, cách dùng connection pool và tối ưu query.
- Chi phí log/trace và sampling tương ứng nhu cầu điều tra.
- Chi phí egress giữa region hoặc cross-zone khi thay đổi kiến trúc.

Một chỉ số hiệu quả có thể là **chi phí trên 1.000 giao dịch nghiệp vụ hoàn tất**. Nhưng phải đi kèm SLO: chi phí giảm không có ý nghĩa nếu số giao dịch thành công giảm mạnh hoặc độ trễ tăng quá ngưỡng.

## 15. Mẫu capacity plan có thể kiểm chứng

Capacity plan nên được quản lý như một quyết định kỹ thuật có người chịu trách nhiệm. Mẫu tối thiểu:

| Thành phần | Nội dung cần điền |
| --- | --- |
| Workload và scope | Tên dịch vụ, hành trình, region, môi trường, ranh giới đo |
| Baseline evidence | Link dashboard/run test, ngày đo, release, cấu hình |
| SLO/guardrail | Availability, p95/p99, error, backlog và ngưỡng dừng |
| Current demand | RPS bình thường, peak, burst, tỷ lệ nghiệp vụ |
| Forecast | Growth, mùa vụ, kịch bản event, mức độ tin cậy |
| Measured safe capacity | RPS/replica hoặc transactions/tier trong điều kiện đã test |
| Dependency constraints | SQL/Cosmos/queue/cache/storage/network, quotas |
| Resilience requirement | Mất replica/zone/region, RTO/RPO khi liên quan |
| Scaling design | Min/max, trigger, cooldown, lag, pre-scale |
| Resource change | Node/instance count, tier, quota request, deadline |
| Cost estimate | Giả định giá, biên độ, phần chi phí không tính vào |
| Owner và review date | Người quyết định, ngày kiểm tra lại, sự kiện kích hoạt |

Ví dụ một phần kế hoạch:

~~~yaml
service: orders-api
region: southeastasia
scope: "production / ingress / user checkout"
baseline:
  peakRps: 220
  measuredSafeRpsPerReplica: 35
  p95LimitMs: 500
  sampleStatus: "hypothetical-teaching-example"
forecast:
  peakGrowthPercent: 30
  forecastPeakRps: 286
availability:
  zones: 3
  lossScenario: "mot zone mat capacity"
capacity:
  peakNowReplicasForZoneLoss: 12
  forecastReplicasForZoneLoss: 15
  verifiedByFailoverTest: false
actions:
  - "kiem tra zone placement va node capacity"
  - "kiem tra SQL/queue/network tai 286 RPS"
  - "mo rong quota truoc dot cao diem"
  - "chay load va failover test"
owner: "platform-operations"
nextReview: "truoc dot phat hanh hoac su kien tai lon"
~~~

File YAML trên là **mẫu kế hoạch quản trị**, không phải cấu hình Azure Deployment, Bicep hay HPA để áp dụng trực tiếp.

## 16. Tích hợp capacity planning vào quy trình vận hành

### 16.1. Chu kỳ định kỳ

Một chu kỳ hợp lý có thể là:

1. **Hằng ngày:** theo dõi SLO, lỗi, p95/p99, resource saturation, backlog và chi phí bất thường.
2. **Hằng tuần:** so sánh baseline hiện tại với tuần trước ở các điều kiện tương đương, ghi lại drift.
3. **Trước phát hành lớn:** benchmark regression với commit/cấu hình mới, so sánh p95 và safe RPS.
4. **Hằng tháng hoặc mỗi chu kỳ planning:** cập nhật forecast, kiểm tra quota và kế hoạch chi phí.
5. **Trước sự kiện lớn:** xác nhận pre-scale, capacity của database, quota, diễn tập giảm tải.
6. **Sau sự cố hoặc thay đổi kiến trúc:** tạo baseline mới và sửa giả định bị chứng minh sai.

Chu kỳ trên chỉ là gợi ý; cần điều chỉnh theo lưu lượng và mức độ quan trọng. Một hệ thống biến động nhanh có thể cần đánh giá nhiều lần trong tuần.

### 16.2. Kết nối CI/CD với performance regression

Trong pipeline, có thể chạy smoke/performance test ở staging để so sánh phiên bản hiện tại với baseline gần nhất. Điều kiện so sánh phải cùng loại tài nguyên, dữ liệu và mix workload; nếu khác thì kết quả chỉ là tín hiệu tham khảo.

Một quy tắc review minh họa:

~~~text
Nếu p95 tăng > 20% so với baseline cùng điều kiện
  hoặc safe throughput giảm > 15%
  hoặc memory tăng liên tục trong soak test:
    yêu cầu kiểm tra thay đổi trước khi promote production
~~~

Các ngưỡng 20%/15% là **ví dụ giả định**, không phải tiêu chuẩn của Azure. Để tránh false positive, cần xét số lần test, phương sai đo, kích thước mẫu, độ tin cậy thống kê và ảnh hưởng của phụ thuộc ngoài.

### 16.3. Ngưỡng kích hoạt hành động

Thay vì chỉ ghi “theo dõi CPU”, kế hoạch nên ghi **điều kiện → hành động → người phụ trách**:

| Điều kiện | Hành động | Chủ thể |
| --- | --- | --- |
| Peak forecast vượt 80% capacity đã kiểm chứng | Đặt lịch load test và capacity review | SRE/Platform |
| Thời gian scale lên dài hơn thời gian xảy ra spike | Pre-scale hoặc tăng headroom | Operations |
| SQL p95 tăng trước khi app CPU tăng | Profiling/tối ưu SQL và đánh giá tier | Database owner |
| Queue age vượt mục tiêu dù CPU worker thấp | Kiểm tra throttling, concurrency, locks, downstream | Backend team |
| Quota còn thấp hơn mức scale max mong muốn | Yêu cầu tăng quota và kiểm tra region availability | Cloud admin |
| Chi phí/giao dịch tăng sau release | Phân tích cache hit, retry, fan-out, resource allocation | Engineering + FinOps |

## 17. Tình huống thực tế: capacity ứng dụng đủ nhưng vẫn chậm

Đội phát triển thấy orders-api ở peak 220 RPS có CPU 55%, 8 replica và p95 tăng lên 1,6 giây. Họ dự định tăng lên 16 replica. Telemetry cho thấy:

- CPU của ứng dụng vẫn dưới 65%.
- 70% thời gian của request nằm ở truy vấn Azure SQL.
- Database xuất hiện lock wait và một truy vấn có nhiều lần đọc.
- HTTP pool bắt đầu chờ kết nối, nhưng memory của app còn dư.

Phân tích:

1. Compute chưa được chứng minh là bottleneck. Tăng replica có thể tăng số kết nối/query xuống SQL và làm lock contention nặng thêm.
2. Cần tìm slow query, execution plan, index, transaction scope và connection pool.
3. Benchmark lại sau khi tối ưu SQL, giữ nguyên workload và cấu hình đo.
4. Nếu database vẫn đạt giới hạn theo tier, cân nhắc thay đổi tier/capacity và chạy kiểm thử trước khi thay đổi production.
5. Cập nhật baseline và capacity plan sau khi tìm được điểm bão hòa mới.

**Một thay đổi hạ tầng chỉ đúng khi giải quyết bottleneck đã đo.** Tăng số instance không nhất thiết tăng khả năng xử lý nghiệp vụ cuối cùng.

## 18. Bài thực hành: baseline và dự báo cho orders-api

**Bối cảnh:** Dịch vụ orders-api chạy ở môi trường Azure thử nghiệm được phép sử dụng. Người học có quyền đọc metrics, chạy load test không phá hủy và không sử dụng dữ liệu khách hàng thật.

### Bài A — Xây baseline đo được

1. Chọn 2–3 hành trình nghiệp vụ (xem sản phẩm, xem giỏ, tạo đơn thử nghiệm).
2. Ghi tỉ lệ traffic từng hành trình, region, phiên bản, số replica, CPU/memory requests, database tier.
3. Thu request/dependency latency (p50/p95/p99), lỗi, throughput, concurrent requests và resource saturation.
4. Tạo đồ thị RPS theo phút và latency theo phút; đánh dấu thời điểm thay đổi tải.
5. Tổng hợp kết quả vào bảng baseline có nguồn số liệu và thời gian đo.

**Tiêu chí đạt:** Có đủ bối cảnh để người khác lặp lại phép đo; không chỉ chụp một screenshot CPU hoặc một giá trị p95.

### Bài B — Kiểm thử tìm safe capacity

1. Khởi động ở tải thấp, chạy warm-up.
2. Tăng từng nấc tải và ghi metric cùng cửa sổ ổn định.
3. Dừng ở ngưỡng lỗi/latency hoặc guardrail đã chọn.
4. Xác định mức tải lớn nhất vẫn đáp ứng mục tiêu.
5. Lặp lại để xem kết quả có nhất quán hay không.

**Tiêu chí đạt:** Xác định được **safe RPS/capacity unit** và ghi rõ hạn chế về database, network, cache và mô hình phát tải.

### Bài C — Lập forecast và capacity plan

Dùng giả định **220 RPS peak**, **35 RPS/replica**, **30% tăng trưởng**:

1. Tính số replica cho peak hiện tại và sau tăng trưởng.
2. Bổ sung N+1 rồi đánh giá yêu cầu mất một zone trong 3 zone.
3. Giả sử traffic sự kiện cao gấp 1,5 lần peak đã tăng; ước lượng demand và đánh giá autoscale lag.
4. Kiểm tra database, queue, IP và quota có đủ cho số replica mới không.
5. Tính chi phí bằng báo giá cụ thể của môi trường hoặc nêu rõ giá giả định.
6. Viết tài liệu capacity plan có owner, action, deadline và điều kiện cần kiểm chứng.

**Tiêu chí đạt:** Không chỉ trả một con số replica; phải có SLO, dependency, thời gian scale, yêu cầu chịu lỗi và chi phí.

### Bài D — Diễn tập một bottleneck

Trong môi trường test, tạo kịch bản dependency SQL chậm hoặc queue xử lý không kịp, có guardrail. Quan sát ứng dụng có thể tăng replica nhưng latency/backlog vẫn xấu. Đề xuất hành động giải quyết nguyên nhân và đo lại.

**Tiêu chí đạt:** Bản báo cáo phân biệt được “thiếu compute” và “nghẽn dependency”; không tăng cấu hình tùy tiện để làm đẹp một chỉ số.

## 19. Sự cố thường gặp khi dựng baseline

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Hai lần benchmark khác nhau nhiều | Khác workload mix, cache, dữ liệu, cấu hình hoặc nguồn tải | Khóa điều kiện và lặp nhiều lần |
| p95 trên dashboard khác p95 truy vấn log | Khác cửa sổ, sampling, histogram hoặc tập request | Đồng nhất ranh giới đo và cách tính percentile |
| CPU thấp nhưng ứng dụng chậm | Đợi database, pool, queue, network hoặc lock | Dùng tracing, dependency metrics, profiler |
| RPS không tăng dù tăng virtual users | Generator nghẽn hoặc closed-loop chậm theo phản hồi | Đo arrival RPS thực và generator utilization |
| Scale nhiều Pod nhưng Pod Pending | Node/IP/quota/placement không đủ | Kiểm tra scheduler events, node autoscaler, subnet |
| Autoscale không bắt kịp spike | Startup, image pull, metrics lag hoặc cooldown | Pre-scale, tăng headroom, tối ưu startup |
| Cosmos DB 429 khi app CPU thấp | Thiếu RU/s hoặc hot partition | Kiểm tra RequestCharge, partition, throughput |
| Queue depth giảm nhưng nghiệp vụ chưa xong | Consumer lấy message nhưng xử lý thất bại/chậm | Đo successful completion và message age |
| Chi phí tăng mà p95 không giảm | Bottleneck ở tầng khác, overprovisioning | So sánh bottleneck trước/sau, cost per transaction |
| Ứng dụng đạt SLO ngày thường nhưng lỗi khi mất zone | Capacity không đủ ở các zone còn lại | Kiểm thử failover và placement thực |
| Baseline nhanh bị lỗi thời | Release, traffic, dữ liệu hoặc tier thay đổi | Gắn version và lịch cập nhật baseline |
| Chỉ lưu số trung bình | Che tail latency và burst | Thu p95/p99 và peak theo cửa sổ ngắn |

## 20. Tự kiểm tra kiến thức

**Câu 1.** Baseline hiệu năng và capacity plan khác nhau ở điểm nào?  
**Đáp án:** Baseline là phép đo có điều kiện xác định; capacity plan dựa trên baseline, test và dự báo để quyết định tài nguyên, khả năng chịu lỗi, autoscale, chi phí và hành động.

**Câu 2.** Vì sao CPU trung bình 40% không chứng minh còn 60% capacity ứng dụng?  
**Đáp án:** Hiệu năng không tăng tuyến tính với CPU, và bottleneck có thể là database, lock, queue, network hoặc memory.

**Câu 3.** Khi 35 RPS/replica là mức đã kiểm thử đạt SLO, peak 220 RPS cần ít nhất bao nhiêu replica trong điều kiện lý tưởng?  
**Đáp án:** \(\lceil 220/35 \rceil = 7\) replica, chưa tính dự phòng.

**Câu 4.** Nếu forecast peak là 286 RPS và hệ thống có ba zone, 10 replica tổng có bảo đảm chịu mất một zone không?  
**Đáp án:** Không. Với phân bổ 4/3/3, mất zone có 4 replica chỉ còn 6, trong khi theo phép tính cần 9 replica phục vụ peak forecast. Cần đánh giá placement và dự phòng cao hơn, ví dụ 15 replica phân bổ 5/5/5 theo giả định minh họa.

**Câu 5.** Little's Law sử dụng p95 latency hay latency trung bình?  
**Đáp án:** Dùng thời gian tồn tại **trung bình** của request trong hệ thống ổn định; p95 không thể thay trực tiếp cho \(W\).

**Câu 6.** Vì sao không thể lấy trung bình p95 theo giờ để có p95 theo ngày?  
**Đáp án:** Percentile là thuộc tính của phân phối, không cộng tuyến tính; cần hợp nhất phân phối/histogram hoặc tính trên tập dữ liệu phù hợp.

**Câu 7.** Vì sao HPA tăng Pod chưa chắc giúp một API đang chậm?  
**Đáp án:** HPA chỉ tăng số Pod khi điều kiện scaling đạt; có thể thiếu node/quota hoặc bottleneck ở database, queue hay network.

**Câu 8.** Khi nào nên pre-scale thay vì chờ autoscale?  
**Đáp án:** Khi spike có thể dự đoán và xuất hiện nhanh hơn thời gian cần để metrics kích hoạt, cấp node, kéo image và khởi động đủ replica.

**Câu 9.** RU/s ước lượng của Cosmos DB có thể dùng làm throughput provisioned ngay không?  
**Đáp án:** Chưa. Cần đo RequestCharge, phân bổ partition, 429, burst, indexing và các giới hạn tài khoản trước khi quyết định.

**Câu 10.** Chi phí 1.314 USD/tháng trong bài có phải báo giá Azure cho 15 replica không?  
**Đáp án:** Không. Đó là phép tính với giá và đơn vị compute giả định; chi phí thực phụ thuộc gói dịch vụ, node/VM, storage, network, region và các thành phần khác.

## 21. Checklist áp dụng cho dự án Azure

- [ ] Đã mô tả workload mix, peak, burst, mùa vụ, tỷ lệ đọc/ghi, dependencies và số người dùng đồng thời.
- [ ] Có SLI/SLO rõ cho latency, availability và kết quả nghiệp vụ.
- [ ] Có telemetry request, dependency, lỗi, CPU, memory, pool, queue, storage, database và networking.
- [ ] Baseline lưu thời gian, phiên bản, cấu hình, nguồn dữ liệu, vùng triển khai và tình trạng sampling.
- [ ] Đã thực hiện benchmark đủ warm-up, nhiều mức tải, guardrail và kiểm tra phục hồi.
- [ ] Safe capacity được chọn theo SLO và kết quả đo thực, không suy tuyến tính từ CPU.
- [ ] Capacity plan đã tính tăng trưởng, event traffic, headroom và autoscale lag.
- [ ] Đã phân biệt N+1 với yêu cầu mất zone/region.
- [ ] Đã kiểm tra capacity database, cache, queue, storage, network, IP và quota Azure.
- [ ] Autoscale min/max, chỉ số kích hoạt, thời gian phản ứng và khả năng scale-down đã được kiểm chứng.
- [ ] Chi phí dự kiến có nguồn giá/giả định, ngân sách và người chịu trách nhiệm.
- [ ] Có ngưỡng kích hoạt hành động, lịch rà soát, kế hoạch kiểm tra lại sau release hoặc sự cố.

**Điều cốt lõi:** Baseline đáng tin phải gắn với workload và môi trường đo cụ thể. Capacity plan tốt dùng baseline đó cùng load test, dự báo, SLO, ràng buộc dependency và yêu cầu chịu lỗi để đưa ra quyết định có thể kiểm chứng. Trong Microsoft Azure, việc duy trì vòng đo lường → dự báo → cấp phát → kiểm thử → tối ưu giúp hệ thống phục vụ ổn định hơn và chi phí hạ tầng có cơ sở rõ ràng.
