# Thiết kế thử nghiệm tải thường, tải đỉnh và tải kéo dài

> **Chương:** Hiệu năng  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thử nghiệm tải (load test), tải đỉnh (peak test), tải kéo dài (soak/endurance test), stress test và spike test.
2. Chuyển dữ liệu sử dụng và yêu cầu nghiệp vụ thành workload model có arrival rate, concurrency, mix request, dữ liệu và thời gian chạy.
3. Thiết lập baseline, mục tiêu SLI/SLO, tiêu chí đạt/trượt và ngưỡng dừng trước khi chạy thử nghiệm.
4. Chọn workload profile và loại thử nghiệm phù hợp với câu hỏi capacity, autoscaling, stability hoặc failure.
5. Chuẩn bị môi trường, dữ liệu, traffic generator và dependency để kết quả đại diện nhưng không gây rủi ro production.
6. Đo latency percentile, throughput, error rate, saturation, queue age, resource utilization và chi phí.
7. Phân tích kết quả để tìm bottleneck, kiểm tra scaling behavior và ước lượng headroom/capacity.
8. Phát hiện các sai lệch thường gặp như coordinated omission, generator bottleneck, cache warm-up, dữ liệu quá nhỏ và tải không giống thực tế.
9. Tổ chức báo cáo, lưu kịch bản và tái chạy thử nghiệm để so sánh phiên bản kiến trúc theo thời gian.

## 1. Vì sao phải thử nghiệm hiệu năng?

Một kiến trúc có thể hoạt động tốt với vài người dùng thử nhưng suy giảm khi traffic tăng, dữ liệu lớn lên hoặc nhiều request đồng thời tranh chấp cùng dependency. Autoscaling, cache, database tier và queue thường được chọn dựa trên giả định. Nếu không kiểm chứng, những giả định đó có thể tạo chi phí quá cao hoặc khiến hệ thống không đáp ứng được giờ cao điểm.

Thử nghiệm hiệu năng (performance testing) tạo tải có kiểm soát để trả lời những câu hỏi cụ thể:

- Hệ thống đáp ứng bao nhiêu request hoặc giao dịch mỗi giây ở mức chất lượng đã cam kết?
- Latency p95/p99 thay đổi ra sao khi concurrency tăng?
- Đỉnh traffic ngắn có làm queue, database hoặc autoscaler mất ổn định không?
- Hệ thống có thể duy trì tải nhiều giờ mà không rò rỉ memory, tăng backlog hoặc suy giảm dần không?
- Khi một dependency chậm hoặc capacity bị giới hạn, hệ thống suy giảm như thế nào?
- Bao nhiêu headroom còn lại khi peak load xảy ra cùng một sự cố zone/instance?
- Chi phí trên một giao dịch hoặc một đơn vị throughput là bao nhiêu?

Không có một bài test duy nhất trả lời tất cả. Tải thường giúp xác lập baseline, tải đỉnh kiểm tra năng lực tại thời điểm bận nhất, tải kéo dài tìm vấn đề tích lũy. Stress/spike test trả lời các câu hỏi khác về giới hạn và khả năng phục hồi.

### 1.1. Bắt đầu từ nghiệp vụ, không bắt đầu từ công cụ

Giả sử nền tảng đặt lịch có các luồng:

- Tìm kiếm slot trống.
- Xem chi tiết dịch vụ và địa điểm.
- Tạo booking và xác nhận.
- Hủy hoặc đổi lịch.
- Gửi email/SMS thông báo.
- Nhân viên vận hành xem dashboard.

Các luồng có chi phí rất khác nhau. Search có thể đọc cache hoặc query nhiều bảng; tạo booking cần transaction, kiểm tra slot và phát event; notification có thể xử lý bất đồng bộ. Tạo 1.000 request/giây với toàn bộ là GET cached không tương đương 1.000 booking write/giây.

Vì vậy, workload model phải mô tả **người dùng làm gì, với tần suất nào, trên loại dữ liệu nào và trong khoảng thời gian nào**.

## 2. Các loại thử nghiệm cần phân biệt

### 2.1. Load test — tải theo mục tiêu dự kiến

Load test chạy một workload đại diện ở mức tải đã xác định để đo hệ thống hoạt động như thế nào trong điều kiện bình thường hoặc gần mức mục tiêu vận hành.

Mục tiêu:

- Xác nhận SLO về latency, throughput và error rate.
- Tạo baseline trước khi thay đổi kiến trúc.
- Tìm bottleneck ở tải được dự báo.
- Định lượng capacity và headroom.

Ví dụ: mô phỏng 2.000 người dùng hoạt động với khoảng 350 request/giây trong 30 phút, theo mix search, detail, booking và cancellation được quan sát từ hệ thống thật.

### 2.2. Peak load test — tải đỉnh

Peak load test mô phỏng mức bận nhất dự kiến trong một khoảng thời gian, thường theo pattern giờ cao điểm, campaign, kỳ nghỉ hoặc thời điểm mở bán.

Nó cần phản ánh cả tổng arrival rate hoặc concurrency cực đại; tỷ lệ request read/write trong giai đoạn đỉnh; tenant/region skew và dữ liệu nóng; burst ở đầu cửa sổ; khả năng scale-up và thời gian autoscaler phản ứng.

Peak test không chỉ tăng số user. Nếu peak thật có 60% traffic trong 10 phút đầu, việc chạy đều tải trong một giờ có thể bỏ qua vấn đề queue và autoscaling khi traffic dồn tới.

### 2.3. Soak/endurance test — tải kéo dài

Soak test duy trì một workload đại diện trong thời gian dài để phát hiện vấn đề không dễ thấy ở test ngắn:

- Memory leak, file descriptor/connection leak.
- Thread pool, connection pool hoặc cache tăng dần.
- Queue backlog tích lũy vì consumer chậm hơn producer.
- Log, metrics hoặc temporary storage tăng không kiểm soát.
- Token/certificate hết hạn, connection stale hoặc batch job va chạm.
- Database bloat, checkpoint, compaction và maintenance ảnh hưởng latency.
- Autoscaler oscillation hoặc capacity không scale down.

Ví dụ: duy trì tải 70% peak trong 8 giờ hoặc một ngày, gồm workload nền, batch định kỳ và chu kỳ cache. Thời gian cụ thể phụ thuộc hệ thống; mục đích là bao phủ chu kỳ vận hành có ý nghĩa, không phải chạy lâu theo một con số cố định.

### 2.4. Stress test — vượt giới hạn dự kiến

Stress test tăng tải vượt mức bình thường/peak để xác định giới hạn và cách hệ thống thất bại:

- Khi nào latency hoặc error vượt SLO?
- Điểm nghẽn đầu tiên nằm ở API, database, broker hay external dependency?
- Hệ thống trả lỗi có kiểm soát, queue hay sập dây chuyền?
- Rate limit, backpressure, circuit breaker và load shedding có hoạt động?
- Sau khi giảm tải, hệ thống có phục hồi hay cần restart/can thiệp?

Stress test không nhằm chứng minh hệ thống chịu được tải vô hạn. Kết quả quan trọng là biết boundary, failure mode và cách bảo vệ phần còn lại của hệ thống.

### 2.5. Spike test — thay đổi tải đột ngột

Spike test tạo bước nhảy traffic nhanh, ví dụ từ 100 lên 1.500 request/giây trong 20 giây rồi giảm xuống.

Nó giúp kiểm tra:

- Autoscaler có phản ứng kịp tốc độ traffic?
- Connection pool, thread pool và cache có chịu burst?
- Queue có hấp thụ spike và consumer có bắt kịp?
- Cold start, image pull và initialization có làm tăng latency?
- Hệ thống có overload protection khi capacity chưa tăng?

Spike test khác peak test: peak mô tả mức cao cần phục vụ, spike nhấn mạnh tốc độ và độ đột ngột của sự thay đổi.

### 2.6. So sánh nhanh

| Loại test | Câu hỏi chính | Hình dạng tải | Kết quả mong đợi |
|---|---|---|---|
| Load | Ở tải mục tiêu, chất lượng có đạt không? | Tăng dần tới target rồi giữ ổn định | Baseline SLI/capacity |
| Peak | Hệ thống chịu được giờ bận nhất không? | Pattern peak theo thời gian | Headroom và SLO ở peak |
| Soak | Chạy lâu có suy giảm không? | Tải ổn định hoặc biến thiên theo chu kỳ | Tính ổn định dài hạn |
| Stress | Giới hạn và failure mode là gì? | Tăng vượt capacity dự kiến | Saturation point, graceful degradation |
| Spike | Burst nhanh có gây mất ổn định không? | Tăng/giảm rất nhanh | Autoscaling, queue và recovery behavior |

Các bài test có thể kết hợp nhưng cần giữ câu hỏi và tiêu chí riêng. Không gọi một bài chạy 5 phút ở tải cao là soak test.

## 3. Xác định mục tiêu và tiêu chí thành công

### 3.1. SLI, SLO và workload target

Trước thử nghiệm, xác định:

- **Latency:** p50, p95, p99 theo operation hoặc endpoint.
- **Throughput:** request/s, transaction/s hoặc business operation/s.
- **Error rate:** tỷ lệ lỗi kỹ thuật, timeout và business rejection được phân loại rõ.
- **Saturation:** CPU, memory, connection pool, IOPS, queue capacity và network.
- **Freshness/queue age:** độ trễ dữ liệu, oldest message age hoặc replication lag nếu có.
- **Cost:** chi phí trên đơn vị throughput/giao dịch và chi phí khi autoscaling.

Ví dụ tiêu chí giả định cho Booking API:

| Chỉ số | Mục tiêu minh họa |
|---|---|
| Arrival rate | 500 request/s sustained |
| Booking write throughput | 80 booking/s |
| p95 latency cho search | ≤ 250 ms |
| p99 latency cho booking | ≤ 800 ms |
| Technical error rate | < 0,5% |
| Queue oldest age | < 60 giây |
| Database CPU | < 70% ở tải mục tiêu |
| Data correctness | Không có booking trùng slot; mọi kết quả được đối soát |

Các số trên chỉ là ví dụ. SLO thực tế phải theo business requirement, baseline và measurement point. Không chọn CPU 70% như mục tiêu phổ quát; database có thể bottleneck ở IOPS, locks hoặc connections dù CPU còn thấp.

### 3.2. Định nghĩa điều kiện đạt/trượt

Một test đạt khi đồng thời:

1. Duy trì target load đủ lâu sau warm-up.
2. Latency percentile nằm trong threshold.
3. Error rate và business correctness nằm trong giới hạn.
4. Dependency và resource saturation còn headroom đã định.
5. Backlog không tăng liên tục hoặc có thể drain trong cửa sổ mục tiêu.
6. Autoscaling và failure handling không tạo oscillation hoặc cascading failure.
7. Không có dấu hiệu suy giảm dài hạn.

Đừng chỉ kết luận pass vì average latency thấp. Average có thể che giấu một nhóm request p99 rất chậm; cũng không thể coi error rate thấp là thành công nếu giao dịch bị xử lý trùng.

### 3.3. Measurement point

Xác định latency được đo ở đâu:

- Client-side end-to-end, gồm DNS, TLS, network và gateway.
- Load balancer hoặc API gateway.
- Application handler.
- Database query/transaction.
- Queue publish/consume.

Client-side measurement thường gần trải nghiệm người dùng hơn. Server-side trace giúp tìm nguyên nhân. Cần giữ correlation ID hoặc trace ID để nối hai góc nhìn; không lấy server processing time thay cho end-to-end latency nếu có network/cold start đáng kể.

## 4. Xây dựng workload model

### 4.1. Arrival rate và concurrency

Hai cách mô tả tải phổ biến:

- **Arrival-rate model:** số request/operation bắt đầu trong một đơn vị thời gian, ví dụ 500 request/giây.
- **Concurrency model:** số request/session đang hoạt động đồng thời, ví dụ 1.000 virtual users.

Quan hệ gần đúng theo định luật Little:

~~~text
Concurrency (L) ≈ Arrival rate (λ) × Average time in system (W)
~~~

Ví dụ 200 request/giây với thời gian xử lý trung bình 0,4 giây tạo khoảng 80 request đang ở trong hệ thống tại một thời điểm, nếu workload ổn định và các giả định phù hợp.

Đây là quan hệ theo trung bình trong hệ thống ổn định. Khi tải vượt capacity, thời gian chờ tăng, concurrency có thể tăng mạnh dù arrival rate không đổi. Vì vậy, test cần theo dõi cả offered load và achieved throughput.

### 4.2. Closed workload và open workload

**Closed workload** thường duy trì số virtual users; mỗi user gửi request tiếp theo sau khi request trước hoàn thành hoặc sau think time. Khi hệ thống chậm, số request mới có thể tự giảm vì user ảo đang chờ.

**Open workload** tạo arrival theo lịch độc lập với thời gian phản hồi; nếu server chậm, request vẫn tiếp tục đến theo tốc độ đã đặt. Đây thường là mô hình tốt để kiểm tra hệ thống trước offered load cố định.

Khác biệt này quan trọng. Closed test có thể vô tình giảm tải ngay khi server chậm, làm kết quả latency trông tốt hơn thực tế. Hiện tượng coordinated omission xảy ra khi load generator chỉ đo latency của request đã được gửi, bỏ qua khoảng thời gian request đáng lẽ đến nhưng bị trì hoãn vì generator đang chờ.

Chọn model theo hành vi thật:

- Người dùng click rồi chờ kết quả: session/closed model có thể phù hợp.
- Event, webhook, scheduled job hoặc API client gửi theo rate độc lập: open/arrival-rate model thường phù hợp hơn.
- Hệ thống có cả hai: mô phỏng riêng từng nguồn và tổng hợp.

### 4.3. Request mix

Một workload thực tế có thể gồm:

| Operation | Tỷ lệ giả định | Đặc tính |
|---|---:|---|
| Search available slots | 45% | Read-heavy, nhiều filter |
| View service details | 25% | Cache-friendly |
| Create booking | 15% | Transaction/write, kiểm tra xung đột |
| Cancel/reschedule | 5% | Update và event |
| Read booking history | 7% | Read theo tenant/time |
| Admin dashboard | 3% | Query tổng hợp, quyền riêng |

Tỷ lệ phải dựa trên telemetry, product analytics hoặc forecast được xác nhận. Dùng mix toàn GET có thể đánh giá sai database write capacity và queue throughput. Đồng thời, tỷ lệ request không tương đương tỷ lệ tài nguyên: một dashboard query có thể tốn CPU hơn nhiều search request.

### 4.4. User journey và think time

Một người dùng có thể:

1. Mở trang và tải danh sách dịch vụ.
2. Tìm slot.
3. Xem chi tiết.
4. Chọn slot và xác nhận booking.
5. Xem trang xác nhận.

Mô phỏng user journey giúp giữ tương quan session, cookie, token, cache và dữ liệu. Think time giữa thao tác tránh tạo workload phi thực tế nếu người dùng thật cần đọc/chọn trước khi click tiếp.

Không để think time quá lớn khiến test tạo ít tải hơn dự kiến. Cũng không loại bỏ think time nếu mục tiêu là kiểm tra journey và session behavior.

### 4.5. Workload theo tenant và phân bố dữ liệu

Cloud SaaS thường có tenant size rất khác nhau. Cần mô hình hóa tenant nhỏ/vừa/lớn; tenant có dữ liệu nóng hoặc lịch sử dài; region, locale và time zone khác nhau; tenant burst cao theo campaign; tenant có cấu hình đặc biệt, quota hoặc key riêng.

Không phân phối đều dữ liệu nếu hệ thống thật có hot tenant/hot key. Một bài test với 10 tenant có lượng dữ liệu giống nhau có thể bỏ qua contention khi một tenant chiếm phần lớn traffic.

## 5. Mô hình tải thường, tải đỉnh và tải kéo dài

### 5.1. Normal load

Tải thường nên đại diện mức sử dụng phổ biến trong thời gian hoạt động bình thường:

- Arrival rate theo giờ/ngày.
- Request mix và user journey.
- Background jobs, batch, refresh và telemetry.
- Data size, hot/cold cache và tenant distribution.
- External dependency ở mức có thể mô phỏng.

Dùng normal load để xác nhận baseline và chi phí vận hành thường ngày. Không dùng mức trung bình ngày nếu nó bỏ qua peak theo phút hoặc theo tenant.

### 5.2. Peak load

Peak model nên dựa trên dữ liệu đo được hoặc forecast có lý do:

~~~text
Peak offered load =
  forecast active users
  × actions per user per time window
  × request fan-out per action
~~~

Ví dụ giả định:

- 12.000 người dùng hoạt động trong cửa sổ 10 phút.
- Bình quân 2 hành động/phút/người dùng trong cửa sổ đó.
- Mỗi hành động tạo trung bình 1,4 request tới API.

~~~text
12.000 × 2 × 1,4 / 60 = 560 request/second
~~~

Kết quả gần 560 request/giây là ước lượng offered load từ giả định. Cần hiệu chỉnh theo concurrency, think time, request fan-out, retries, cache hit và traffic từ background jobs. Không lấy con số này làm capacity yêu cầu cuối cùng nếu dữ liệu đầu vào chưa được xác minh.

Peak test cần thêm headroom để xét forecast uncertainty và failure scenario. Ví dụ, nếu một region phải tiếp nhận traffic sau khi vùng khác mất, test capacity của region còn lại ở mức traffic failover chứ không chỉ peak bình thường.

### 5.3. Sustained/soak load

Soak workload nên bao phủ một chu kỳ vận hành có ý nghĩa:

- Duy trì base load trong nhiều giờ.
- Có các đợt peak ngắn định kỳ.
- Chạy batch, backup, cleanup, compaction hoặc report job như production.
- Có cache turnover và session lifecycle.
- Bao phủ token/certificate refresh nếu thời lượng test phù hợp.
- Theo dõi storage growth, memory, connection và queue backlog.

Ví dụ profile 8 giờ:

| Giai đoạn | Thời lượng | Tải |
|---|---:|---|
| Warm-up | 20 phút | 20% normal |
| Normal | 2 giờ | 55% target |
| Peak windows | 4 × 10 phút | 100% peak |
| Inter-peak | 2 giờ | 60% target |
| Drain/observe | 30 phút | Giảm tải, theo dõi queue/cleanup |

Đây là profile minh họa. Tạo profile theo lịch sử traffic và chu kỳ batch thực tế; nếu job backup chạy mỗi đêm, test 8 giờ ban ngày có thể chưa đủ để phát hiện contention.

### 5.4. Test matrix

| Scenario | Offered load | Duration | Mục tiêu |
|---|---:|---:|---|
| Baseline normal | 50–60% target | 30 phút | Baseline latency/resource |
| Expected load | 100% target | 30–60 phút | Đạt SLO |
| Peak | 100% forecast peak | 20–30 phút | Capacity ở peak |
| Headroom | 120–130% peak | 10–15 phút | Biên an toàn và failure mode |
| Spike | 20% → 100% peak nhanh | Nhiều lần | Autoscaling/burst behavior |
| Soak | 60–70% normal/peak profile | 8–24 giờ hoặc chu kỳ phù hợp | Memory/queue/storage drift |
| Stress | Tăng từng bậc tới quá tải có kiểm soát | Theo từng bước | Saturation và graceful degradation |

Tỷ lệ và thời lượng chỉ là ví dụ. Cần chọn dựa trên production profile, SLO, safety boundary và câu hỏi đo lường.

## 6. Thiết kế kịch bản thử nghiệm và dữ liệu

### 6.1. Workload script phải mô phỏng hành vi hợp lệ

Kịch bản cần xử lý authentication và token refresh; cookie/session; header, tenant ID và permission; correlation ID; data setup/cleanup; retry/timeout giống client hoặc theo policy test; response validation, không chỉ kiểm tra HTTP status.

Nếu script chỉ gửi request mà không kiểm tra kết quả, test có thể đạt throughput cao trong khi server trả lỗi nghiệp vụ hoặc dữ liệu không đúng.

### 6.2. Test data

Dataset phải đại diện về kích thước và phân bố:

- Số tenant và số record mỗi tenant.
- Lịch sử booking, index cardinality và quan hệ.
- Hot/cold key, partition skew và dữ liệu có độ chọn lọc khác nhau.
- Kích thước object/request payload.
- Cache key hit ratio.
- Giao dịch cạnh tranh cùng slot để kiểm tra lock/unique constraint.

Dùng dữ liệu tổng hợp hoặc đã ẩn danh. Không sao chép PII production vào load environment nếu chưa có cơ sở pháp lý, kiểm soát truy cập và quy trình masking. Dữ liệu test cũng cần retention và cleanup.

### 6.3. Data isolation và side effects

Không để test vô tình gửi email/SMS thật tới khách hàng, thu tiền hoặc gọi payment provider production, tạo booking nghiệp vụ thật, gửi webhook tới partner, xóa dữ liệu của tenant đang hoạt động hoặc làm tăng chi phí cloud/egress ngoài budget.

Tách account/project/network và credentials; dùng sandbox/mock cho provider ngoài khi phù hợp. Nếu cần kiểm thử production-like dependency, có test tenant, allowlist, quota và stop switch được phê duyệt.

### 6.4. State cleanup và repeatability

Một test có thể làm dữ liệu tăng nhanh, unique constraint conflict hoặc cache state khác giữa lần chạy. Cần xác định seed dataset version, unique namespace/run ID, setup/teardown scripts có idempotency, TTL/cleanup schedule, snapshot/restore khi cần giữ môi trường baseline và cách reset queue/cache/database an toàn.

Test repeatable cho phép so sánh commit/instance family/configuration khác nhau mà không bị khác biệt dataset chi phối.

## 7. Môi trường thử nghiệm và traffic generator

### 7.1. Mức độ production likeness

Môi trường test nên giống production ở những yếu tố ảnh hưởng kết quả:

- Service topology và network path.
- Instance/container size, autoscaling policy và quotas.
- Database engine/version/tier, storage/IOPS, index và parameter.
- Cache, queue partition, broker configuration.
- TLS, IAM, secret retrieval và encryption overhead.
- Region, availability zones và latency giữa service.
- Observability agent, log/trace sampling và sidecar overhead.

Không nhất thiết sao chép mọi thứ 1:1 nếu chi phí cao. Nhưng cần ghi lại khác biệt và giải thích giới hạn suy luận. Ví dụ test database nhỏ hơn production không thể kết luận trực tiếp về capacity write khi storage throughput khác.

### 7.2. Load generator không được trở thành bottleneck

Theo dõi CPU/memory và network của generator; offered arrival rate so với achieved request rate; số connection, socket, ephemeral port và TLS handshake; client-side queue, timeout và error; phân bố generator theo vùng địa lý.

Phân tán load generator khi cần, nhưng tổng hợp metric và clock phải đủ đồng bộ. Không lấy CPU của server làm số duy nhất; generator bottleneck có thể khiến server trông nhàn rỗi.

### 7.3. Cache state và warm-up

Một test có cache nóng có thể đạt throughput cao hơn nhiều so với cold start. Cần chạy riêng cold cache/cold start khi đó là tình huống cần đo, warm cache đại diện steady-state, cache eviction/refresh pattern và cache miss burst hoặc dependency chậm.

Ghi rõ test bắt đầu khi nào được coi là warm. Không so sánh một build chạy warm cache với build khác chạy cold cache rồi kết luận optimization.

### 7.4. NTP và thời gian

Các máy generator và service cần clock đồng bộ đủ chính xác để nối timeline, trace và latency. Chênh lệch đồng hồ có thể làm negative span hoặc metric sai. Dùng timestamp monotonic ở client/load tool cho duration nếu thư viện hỗ trợ; wall-clock phục vụ correlation.

## 8. Chỉ số cần thu thập

### 8.1. Latency percentile

Latency thường có phân bố lệch: nhiều request nhanh, một số ít rất chậm. Vì vậy:

- **p50:** một nửa request có latency không vượt quá giá trị này.
- **p95:** 95% request có latency không vượt quá giá trị này.
- **p99:** 99% request có latency không vượt quá giá trị này.

Ví dụ p50 = 80 ms, p95 = 220 ms, p99 = 1.200 ms cho thấy tail latency lớn; một nhóm request có thể bị chậm vì lock, cache miss, GC, retry hoặc dependency. Không dùng average làm chỉ số duy nhất.

Khi tổng hợp nhiều instance, không lấy trung bình p95 của từng instance để suy ra p95 toàn hệ thống. Cần histogram/bucket hoặc raw sample phù hợp để tính percentile hợp lệ trên tổng tập quan sát.

### 8.2. Throughput và offered load

Phân biệt:

- **Offered load:** số request mà generator dự định gửi.
- **Started requests:** số request thực sự được khởi tạo.
- **Completed throughput:** số request hoàn thành trong một đơn vị thời gian.
- **Successful business throughput:** số thao tác nghiệp vụ thành công và hợp lệ.

Nếu offered load 1.000 request/s nhưng completed throughput chỉ 650 request/s, phần còn lại có thể đang chờ, timeout hoặc chưa gửi được. Cần đối chiếu client-side queue và lỗi.

### 8.3. Error rate

Phân loại HTTP 4xx do input/auth/business rule; HTTP 5xx do lỗi server; timeout/connection reset/TLS handshake failure; retry exhaustion/circuit breaker open; business outcome sai, duplicate hoặc mất event.

Không gộp 409 “slot đã được đặt” vào cùng loại với 500 database unavailable nếu đó là kết quả nghiệp vụ có chủ đích. Nhưng trong contention test, cần đo xem xung đột hợp lệ có tăng bất thường và có bảo đảm không tạo booking trùng.

### 8.4. Saturation và dependency metrics

| Thành phần | Metric |
|---|---|
| API/compute | CPU, memory, GC pause, thread pool, worker count, request queue |
| Network | Throughput, retransmit, connection count, packet drop, TLS handshake |
| Database | CPU, IOPS, storage latency, connection, lock wait, slow query, replica lag |
| Cache | Hit/miss, eviction, memory, command latency, hot key |
| Broker/queue | Publish/consume rate, backlog, oldest age, partition lag, DLQ |
| Autoscaler | Desired/current replica, scale event, pending pod, cold start |
| Platform | Quota, API throttling, NAT/connection tracking, storage request limit |
| Business | Booking success, duplicate prevention, payment success, notification lag |

Metric phải gắn với thời gian và phiên bản triển khai để đối chiếu với bước thay đổi tải.

### 8.5. Queueing behavior

Khi arrival rate lớn hơn service rate trong một khoảng đủ dài, backlog tăng. Khi tải giảm, hệ thống cần thời gian drain queue. Chỉ nhìn API latency có thể bỏ qua việc event đang tồn đọng.

Đo queue depth/backlog, oldest message age, producer rate và consumer rate, retry/DLQ, processing time từng message và thời gian drain sau peak.

Một peak test đạt ở API nhưng queue age tăng từ 10 giây lên 40 phút là dấu hiệu hệ thống chưa xử lý được tải end-to-end.

## 9. Tìm bottleneck và diễn giải kết quả

### 9.1. Bottleneck đầu tiên quyết định throughput

Một request có thể đi qua gateway → API → cache → database → broker. Nếu database connection pool bão hòa, tăng API replica có thể làm nhiều connection tranh chấp hơn. Nếu broker consumer chậm, tăng producer chỉ làm backlog lớn hơn.

Quy trình phân tích:

1. So sánh offered load và completed/successful throughput.
2. Xác định thời điểm latency/error bắt đầu tăng.
3. Xem saturation tại từng dependency cùng thời điểm.
4. Theo trace/slow query/profile để tìm phần thời gian chiếm ưu thế.
5. Thay đổi một yếu tố có kiểm soát (query, pool, cache, replica, partition).
6. Chạy lại cùng workload/dataset và so sánh kết quả.

Không tối ưu theo một metric riêng. Giảm latency bằng cách tăng cache có thể tạo stale data; tăng connection pool có thể làm database quá tải; scale worker có thể tăng external API throttling.

### 9.2. Các dạng bottleneck thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| CPU API cao, DB thấp | Serialization, business logic, crypto, compression | CPU profile, allocation, GC, hot path |
| API CPU thấp, DB latency cao | Slow query, lock, IOPS, connection saturation | Query plan, locks, connection pool, storage |
| Queue age tăng | Consumer throughput thấp, poison message, partition skew | Consumer lag, retry/DLQ, partition key |
| p99 tăng nhưng p50 ổn | Tail dependency, hot key, GC pause, retry | Trace percentile, outlier instance, GC/lock |
| Scale event nhiều nhưng throughput không tăng | Downstream bottleneck hoặc autoscaler lag | Dependency saturation, scaling signal |
| Error tăng khi burst | Connection exhaustion, quota, cold start | Generator/client, quota, startup timeline |
| Latency tăng dần qua nhiều giờ | Leak, cache churn, bloat, background work | Memory/FD/connection trend, storage, job overlap |

### 9.3. Capacity curve

~~~mermaid
flowchart LR
    L[Increase offered load] --> A[Throughput rises]
    A --> B{First saturation reached?}
    B -->|No| A
    B -->|Yes| C[Queueing and tail latency grow]
    C --> D[Errors / timeouts increase]
    D --> E[Graceful degradation or cascading failure]
~~~

Trong một khoảng tải, throughput tăng gần tuyến tính. Khi một dependency bão hòa, throughput có thể chững trong khi latency tăng mạnh; sau đó lỗi xuất hiện. Điểm capacity có ích là mức tải cao nhất vẫn đạt SLO và giữ headroom theo policy, không đơn thuần là mức tải ngay trước khi process crash.

### 9.4. Headroom và capacity planning

Giả sử test cho thấy một cell phục vụ 700 request/s ở SLO, với database CPU 65%, queue age ổn định và còn khả năng chịu tải. Nếu forecast peak là 500 request/s, headroom danh nghĩa là 40% so với forecast theo công thức:

~~~text
Headroom ratio = (tested safe capacity - forecast peak) / forecast peak
               = (700 - 500) / 500
               = 40%
~~~

Con số chỉ có ý nghĩa nếu test dùng đúng request mix, dataset, region và failure scenario. Nếu 700 request/s chỉ đạt khi cache nóng và không có batch job, headroom thực tế thấp hơn.

Capacity planning cần xét tăng trưởng traffic/dữ liệu, skew theo tenant/region, khả năng mất zone hoặc replica, thời gian autoscaling/provision, quota provider, batch/backup/compaction và mức độ thay đổi giữa ngày thường/campaign.

## 10. Autoscaling và thử nghiệm tải

### 10.1. Scale-out không phải phản ứng tức thì

Autoscaler thường cần thời gian để thu thập metric, đánh giá threshold/window, yêu cầu replica mới, scheduler tìm node/capacity, pull image và khởi động process, readiness check rồi đưa instance vào load balancer.

Nếu spike xảy ra trong 10 giây nhưng thời gian scale-out là 90 giây, hệ thống cần đủ headroom hoặc cơ chế hấp thụ burst trong khoảng đó. Peak test có thể pass sau khi scale xong nhưng spike test vẫn fail.

### 10.2. Kiểm tra scaling policy

Đo trigger metric và thời gian phát hiện; desired replica so với ready replica; pending/failed pod hoặc VM; scale-up/scale-down duration; throughput/latency trước và sau scale; connection/queue/network ở dependency; oscillation và cooldown.

Scale API replica nhưng database connection pool tăng theo có thể làm database quá tải. Cần giới hạn tổng connection theo số replica và capacity database.

### 10.3. Test scale-down và idle cost

Sau peak, kiểm tra replica giảm về baseline mà không cắt request đang xử lý; queue consumer không giảm quá nhanh khi backlog còn; cache không mất nóng gây thundering herd; connection pool và DB không bị reconnect storm; chi phí trở lại mức dự kiến.

Test hiệu năng cần xem cả khả năng mở rộng và khả năng thu hẹp an toàn.

## 11. Thực hiện thử nghiệm an toàn

### 11.1. Ranh giới môi trường

Ưu tiên isolated account/project/cluster. Nếu dùng production:

- Có phê duyệt, change window và owner giám sát.
- Dùng test tenant và dữ liệu được cho phép.
- Giới hạn RPS/concurrency, budget, region và thời lượng.
- Có kill switch và điều kiện tự dừng.
- Không gọi đối tác hoặc hệ thống thanh toán thật ngoài phạm vi đã duyệt.
- Theo dõi user impact và có người quyết định dừng.

Không chạy stress test hoặc spike test tùy tiện vào production. Một bài test có thể gây mất dịch vụ, tăng hóa đơn, làm cạn quota hoặc ảnh hưởng dữ liệu thật.

### 11.2. Ngưỡng dừng

Đặt stop condition trước khi chạy, ví dụ error rate vượt ngưỡng nghiêm trọng trong nhiều cửa sổ liên tiếp; p99 vượt mức gây user impact; database CPU/IOPS/connection đạt vùng nguy hiểm; queue age tăng nhanh hoặc DLQ tăng; external dependency rate limit; cost/budget vượt giới hạn; hoặc có cảnh báo từ production/customer support.

Ngưỡng phải cụ thể cho hệ thống. Người chạy test cần biết cách dừng generator, drain queue, rollback config và báo incident owner.

### 11.3. Khôi phục sau test

- Dừng generator và xác nhận offered load về 0.
- Theo dõi queue drain hoặc xóa dữ liệu test theo đúng scope.
- Khôi phục feature flag, quota, scaling policy hoặc config tạm.
- Kiểm tra external provider không còn job/test session.
- Xác nhận production baseline và SLI bình thường.
- Thu thập report, log và trace trước khi hết retention.
- Ghi incident/near miss nếu test vượt ranh giới hoặc gây ảnh hưởng.

## 12. Công cụ và cách triển khai kịch bản

### 12.1. Chọn công cụ theo mô hình tải

| Công cụ | Đặc điểm | Khi cân nhắc |
|---|---|---|
| k6 | Script JavaScript, hỗ trợ virtual users và arrival-rate executors | API load test, kịch bản CI |
| Apache JMeter | GUI/CLI, nhiều protocol/plugin và distributed mode | Workload đa dạng, test plan có sẵn |
| Gatling | DSL code, scenario và reporting | Kịch bản phức tạp, automation |
| Locust | Python user behavior và distributed workers | User journey tùy biến |
| wrk/wrk2 | HTTP benchmark nhẹ; wrk2 nhấn mạnh constant throughput | Benchmark endpoint và latency dưới rate |
| Cloud provider load testing | Dịch vụ tạo/điều phối generator | Test phân tán, tích hợp cloud |

Không công cụ nào tự bảo đảm workload đại diện. Kịch bản, data, generator capacity và metric mới quyết định độ tin cậy của kết quả.

### 12.2. Ví dụ k6 với arrival rate

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    booking_peak: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 600,
      stages: [
        { target: 200, duration: '2m' },
        { target: 500, duration: '5m' },
        { target: 500, duration: '10m' },
        { target: 100, duration: '2m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
  },
};

export default function () {
  const response = http.get(__ENV.BASE_URL + '/api/slots', {
    headers: {
      Authorization: 'Bearer ' + __ENV.TEST_TOKEN,
      'X-Test-Run': __ENV.RUN_ID,
    },
    tags: { operation: 'search_slots' },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response has slots': (r) => {
      try {
        return Array.isArray(r.json('slots'));
      } catch (_) {
        return false;
      }
    },
  });

  sleep(0.2);
}
~~~

Ví dụ minh họa cách đặt arrival-rate stages và thresholds; cần điều chỉnh theo version k6, generator capacity, endpoint, authentication và test data. Với arrival-rate executor, cấu hình VU phải đủ để duy trì rate; nếu thiếu VU, k6 có thể không phát đủ offered load và báo dropped iterations. Cần theo dõi chỉ số đó.

Không hard-code token thật trong script. Cấp test credential qua secret mechanism của pipeline, tránh in environment variable hoặc token vào log.

### 12.3. Ví dụ kịch bản soak

~~~javascript
export const options = {
  scenarios: {
    sustained_workload: {
      executor: 'constant-arrival-rate',
      rate: 180,
      timeUnit: '1s',
      duration: '8h',
      preAllocatedVUs: 120,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
  },
};
~~~

Đây chỉ là một ví dụ tải liên tục; soak thực tế có thể cần nhiều scenario, batch job, peak windows, cache cycle và test data lifecycle. Chạy 8 giờ một endpoint duy nhất chưa đủ kiểm tra toàn bộ hệ thống.

## 13. Phân tích và báo cáo kết quả

### 13.1. Báo cáo cần có gì?

Một performance report hữu ích gồm:

1. **Câu hỏi và phạm vi:** mục tiêu test, environment, service/region và phiên bản.
2. **Workload model:** arrival/concurrency, request mix, dataset, tenant skew, think time và thời lượng.
3. **Điều kiện môi trường:** instance size, autoscaling, database tier, cache, network, provider quota và config.
4. **Kết quả:** latency percentile, throughput, errors, business success, saturation, queue và cost.
5. **Timeline:** warm-up, ramp, plateau, spike, scale event và failure.
6. **Bottleneck:** thành phần/metric, bằng chứng trace/query/profile và giả thuyết đã loại trừ.
7. **Kết luận:** pass/fail theo tiêu chí, safe capacity và giới hạn suy luận.
8. **Action:** thay đổi, owner, priority và test lại.

### 13.2. Bảng kết quả minh họa

| Offered load | Completed throughput | p95 | p99 | Error rate | DB CPU | Queue age |
|---:|---:|---:|---:|---:|---:|---:|
| 200 req/s | 199 req/s | 140 ms | 280 ms | 0,05% | 35% | 2 s |
| 400 req/s | 398 req/s | 210 ms | 510 ms | 0,10% | 55% | 8 s |
| 600 req/s | 590 req/s | 390 ms | 1.100 ms | 0,80% | 82% | 45 s |
| 800 req/s | 620 req/s | 1.400 ms | 4.800 ms | 6,5% | 95% | 8 min |

Số liệu là giả định. Nó gợi ý hệ thống bắt đầu không đạt mục tiêu gần 600 req/s: throughput không theo kịp offered load, latency/error/queue tăng và DB saturation cao. Mức safe capacity phải được xác nhận lại bằng workload mix, data correctness, headroom và repeated runs.

### 13.3. So sánh trước và sau tối ưu

So sánh cần giữ cố định workload/request mix, dataset version và cache state, environment size/config, test duration và warm-up, generator capacity, region và dependency behavior.

Nếu thay đổi nhiều biến cùng lúc, rất khó biết cải tiến đến từ đâu. Dùng một giả thuyết mỗi vòng: ví dụ thêm index cho query X, thay connection pool hoặc tăng worker concurrency; chạy lại cùng test.

### 13.4. Reproducibility và versioning

Lưu kịch bản test và commit hash; tool/version và dependency; dataset seed/version, data shape và cleanup; infrastructure revision/provider version; metric/report và timestamp; approval, stop event hoặc deviation.

Khi một bài test không lặp lại được, chênh lệch có thể đến từ shared environment, noisy neighbor, cache hoặc data drift. Ghi nhận điều kiện chạy giúp tránh kết luận sai về code.

## 14. Tối ưu kiến trúc theo kết quả thử nghiệm

### 14.1. Từ symptom tới thay đổi

| Symptom | Hướng tối ưu có thể thử | Điều phải kiểm tra lại |
|---|---|---|
| Query DB chậm | Index, query rewrite, partition, read replica | Write amplification, lock, storage |
| API CPU cao | Profile, algorithm, serialization, compression | Memory/GC và correctness |
| Connection saturation | Pool sizing, proxy, backpressure | Tổng connection khi scale-out |
| Cache miss cao | Key design, TTL, prewarm, cache size | Staleness, thundering herd |
| Queue backlog | Consumer concurrency, partition, batch size | Ordering, duplicate, downstream limit |
| Scale-up chậm | Pre-provision, min replicas, startup optimization | Idle cost, quota |
| Peak cost quá cao | Autoscale, caching, workload isolation | Tail latency và scale-down behavior |
| p99 tăng bất thường | Tail dependency, retry, hot key, GC | p50/p95, error và fairness |

Không tăng tài nguyên chỉ vì một biểu đồ CPU cao nếu nguyên nhân là lock contention, I/O hoặc query plan. Scale-up có thể che triệu chứng trong ngắn hạn nhưng không giải quyết giới hạn kiến trúc.

### 14.2. Test lại sau tối ưu

Sau mỗi thay đổi:

1. Chạy smoke/functional test.
2. Chạy baseline load với cùng test profile.
3. Chạy peak để xác nhận capacity mục tiêu.
4. Chạy stress có kiểm soát nếu thay đổi ảnh hưởng saturation/failure.
5. Chạy soak khi thay đổi cache, pool, worker hoặc lifecycle.
6. Đối chiếu cost, business correctness và security.

Performance improvement chỉ có ý nghĩa khi không làm sai giao dịch, giảm bảo mật hoặc tăng chi phí không được chấp nhận.

## 15. Các lỗi thường gặp trong performance testing

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng virtual user count | Không biết offered request rate thật | Đo arrival rate, concurrency và achieved throughput |
| Chỉ đo average latency | Che giấu tail latency | Theo dõi p50/p95/p99 và histogram |
| Dùng closed workload cho traffic open | Server chậm khiến generator tự giảm tải | Dùng arrival-rate/open model khi phù hợp |
| Load generator thiếu capacity | Test không đạt target nhưng server bị kết luận yếu | Theo dõi generator CPU/network/dropped iterations |
| Dữ liệu test quá nhỏ | Cache/index behavior không giống production | Dùng dataset và cardinality đại diện |
| Chỉ test happy path | Bỏ qua write, retry, lock và error path | Mô phỏng request mix và business outcome |
| Không warm-up hoặc không ghi cache state | So sánh thiếu công bằng | Chuẩn hóa warm-up/cold-cache scenario |
| Test quá ngắn | Không thấy leak, queue buildup và batch contention | Soak theo chu kỳ vận hành |
| Chỉ nhìn API latency | Queue/backlog có thể tích lũy | Đo end-to-end và oldest message age |
| Không tính autoscaling delay | Peak spike gây timeout trước khi replica sẵn sàng | Spike test và đo scale timeline |
| Retry test vô hạn | Làm tăng tải và che lỗi gốc | Retry budget, backoff, idempotency |
| Thử trực tiếp production không guardrail | Gây outage hoặc phát sinh giao dịch thật | Isolated env hoặc approved test window/kill switch |
| Thay nhiều tham số cùng lúc | Không biết thay đổi nào tạo hiệu quả | Một giả thuyết/biến chính mỗi vòng |
| Không đối soát business data | Throughput cao nhưng giao dịch sai/trùng | Validate invariants và reconciliation |
| Không lưu config/commit hash | Không tái lập được kết quả | Versioning script, data và infrastructure |

## 16. Bài thực hành: xây dựng test plan cho nền tảng đặt lịch

**Tình huống:** Một SaaS đặt lịch chạy trên cloud gồm API Gateway, Booking Service, relational database, cache, event broker và Notification Worker. Ngày thường có khoảng 150 request/giây, peak gần nhất là 450 request/giây trong 15 phút. Nhóm dự kiến campaign tiếp theo có thể đạt 700 request/giây. Hiện chưa biết database safe capacity và consumer có drain được notification backlog sau peak hay không.

Hãy xây dựng test plan:

1. **Business workload:** xác định operation mix cho search, detail, create, cancel, history và notification.
2. **Model traffic:** chuyển lịch sử normal/peak thành arrival-rate profile; ghi giả định về concurrency, think time, retry và tenant skew.
3. **SLO:** chọn latency percentile, error rate, booking correctness, queue age, freshness và capacity headroom.
4. **Test matrix:** thiết kế load, peak, spike, stress và soak; định nghĩa duration/warm-up/ramp/plateau.
5. **Test data:** tạo tenant/data volume đại diện, hot key và booking conflict; bảo đảm không dùng PII thật.
6. **Environment:** mô tả instance/database/IOPS/cache/broker/region/autoscaler và khác biệt với production.
7. **Generator:** chọn tool, phân tán generator, xác định max VU/arrival rate và giám sát dropped iteration.
8. **Instrumentation:** dashboard latency p50/p95/p99, throughput, error, DB, cache, queue, autoscaler và business metric.
9. **Safety:** budget, scope, test credential, sandbox, kill switch, stop condition và cleanup.
10. **Analysis:** dùng kết quả để xác định safe capacity, bottleneck, headroom và đề xuất tối ưu.
11. **Repeatability:** version test script, dataset, config, commit hash và báo cáo trước/sau.

### Test matrix mẫu

| Scenario | Profile minh họa | Thời lượng | Câu hỏi |
|---|---|---:|---|
| Normal | 150 req/s, mix production-like | 30 phút | Baseline có đạt SLO? |
| Peak hiện tại | 450 req/s | 20 phút | Có tái hiện được traffic giờ cao điểm? |
| Forecast campaign | 700 req/s | 20 phút | Có đạt target và còn headroom? |
| Spike | 150 → 700 req/s trong 15 giây | 5 lần | Autoscaler/queue có chịu burst? |
| Stress | Tăng 700 → 900 → 1.100 req/s theo bậc | Từng bậc 5 phút | Bottleneck và graceful degradation ở đâu? |
| Soak | 300 req/s, kèm peak window và batch job | 8 giờ | Memory/queue/storage có ổn định? |

Các profile là giả định ban đầu, cần hiệu chỉnh bằng analytics thực tế và giới hạn an toàn của môi trường.

### Bảng tiêu chí pass/fail mẫu

| Chỉ số | Điều kiện đạt minh họa |
|---|---|
| Booking API p95 | ≤ 300 ms ở 700 req/s |
| Booking API p99 | ≤ 800 ms ở 700 req/s |
| Technical error rate | < 0,5% |
| Successful booking | Đạt business target và không có booking trùng slot |
| Queue oldest age | < 60 giây ở peak; drain về baseline trong 10 phút |
| DB saturation | Không vượt safety limit đã xác định từ load test |
| Autoscaling | Scale hoàn tất trước khi error budget bị tiêu thụ vượt policy |
| Soak stability | Memory/connection/backlog không tăng không giới hạn |

**Tiêu chí hoàn thành:** Một reviewer có thể hiểu tải nào được mô phỏng, vì sao đại diện cho nghiệp vụ, mục tiêu đạt/trượt, cách thu thập bằng chứng, điều kiện dừng và cách rút ra safe capacity. Mọi số liệu giả định phải được phân biệt với số liệu đo thực tế.

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi về thử nghiệm hiệu năng | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Kịch bản, dữ liệu, môi trường, report và quy trình chạy lại có được version hóa? | Test plan, script revision, repeatable report |
| **Security** | Test data/credential được bảo vệ; scope và stop switch có an toàn? | Data masking, IAM, approval, cleanup evidence |
| **Reliability** | Peak/spike/soak có chứng minh graceful degradation và recovery? | Queue drain, error budget, soak trend, failure test |
| **Performance Efficiency** | Capacity, bottleneck, latency tail và autoscaling có được đo? | p95/p99, throughput, saturation, capacity curve |
| **Cost Optimization** | Có đo cost per transaction, idle headroom và chi phí peak? | Cost dashboard, cost/load curve, scale-down result |
| **Sustainability** | Compute/storage/network có được dùng hiệu quả theo tải? | Utilization, data lifecycle, resource efficiency |

Thử nghiệm hiệu năng không chỉ tạo ra một con số request/giây. Nó cung cấp bằng chứng để chọn kiến trúc, capacity và scaling policy; khi được chạy lặp lại với workload đại diện, nó giúp tổ chức hiểu rõ giới hạn, rủi ro và chi phí trước khi traffic thật chạm tới giới hạn đó.

## 18. Khung ghi nhớ

- **Load test** xác nhận hệ thống ở tải mục tiêu; **peak test** kiểm tra giờ bận; **soak test** tìm suy giảm tích lũy.
- **Stress test** xác định giới hạn/failure mode; **spike test** kiểm tra tải tăng đột ngột và tốc độ autoscaling.
- **Workload model** phải mô tả arrival/concurrency, request mix, journey, think time, tenant skew và dữ liệu.
- **Offered load khác completed throughput.** Theo dõi dropped iterations và khả năng của load generator.
- **Latency cần percentile:** average không đủ để hiểu tail behavior; kết hợp p50/p95/p99, errors và business correctness.
- **Bottleneck nằm ở toàn luồng:** API, database, cache, queue, network, quota và external dependency.
- **Soak cần quan sát xu hướng:** memory, connection, storage, queue age, cache và background jobs.
- **Test phải an toàn và tái lập:** data đã kiểm soát, stop condition, cleanup, version script/config và báo cáo.
- **Capacity là mức tải đạt SLO với headroom**, không phải con số tối đa trước khi hệ thống sập.

Thiết kế thử nghiệm tải tốt bắt đầu từ cách người dùng và hệ thống tạo traffic, chuyển thành workload có thể tái lập, rồi đo chất lượng ở cả tầng kỹ thuật lẫn nghiệp vụ. Tải thường, tải đỉnh và tải kéo dài trả lời các câu hỏi khác nhau; kết hợp chúng với stress/spike test giúp kiến trúc sư hiểu capacity, giới hạn và cách hệ thống phục hồi trước khi đưa ra quyết định đầu tư hoặc mở rộng.
