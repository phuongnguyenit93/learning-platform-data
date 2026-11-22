# Đánh đổi tài nguyên cam kết, theo nhu cầu và có thể bị thu hồi

Khi triển khai workload trên cloud, tổ chức thường có nhiều cách mua hoặc cấp phát cùng một loại compute: trả theo mức sử dụng thực tế, cam kết sử dụng trong một thời hạn để nhận mức giá ưu đãi, hoặc dùng năng lực dư thừa có thể bị nhà cung cấp thu hồi. Mỗi mô hình đổi một thứ khác nhau: mức linh hoạt, độ chắc chắn của capacity, khả năng bị gián đoạn và chi phí đơn vị.

**Tài nguyên cam kết (committed/reserved capacity)** phù hợp với workload nền ổn định và có thể dự báo. **On-demand** cung cấp tính linh hoạt khi cần tăng/giảm nhanh hoặc tải chưa chắc chắn. **Spot/preemptible** tận dụng capacity dư thừa với giá thấp hơn nhưng workload phải chịu được việc tài nguyên bị thu hồi. Không có mô hình nào luôn rẻ nhất nếu chỉ nhìn giá theo giờ; phải tính cả mức sử dụng, thời gian nhàn rỗi, phí truyền dữ liệu, công sức vận hành, gián đoạn và capacity dự phòng.

Một chiến lược cost-aware thường kết hợp các mô hình. Tải nền có thể được đáp ứng bằng cam kết; tải biến động dùng on-demand; batch, CI job hoặc worker có thể retry dùng spot. Tuy nhiên, tỷ lệ kết hợp phải dựa vào SLO, thời gian chạy, khả năng checkpoint, độ trễ khởi động và hành vi khi capacity biến mất. Mục tiêu là giảm tổng chi phí mà vẫn duy trì năng lực phục vụ nghiệp vụ.

Bài học thuộc phần **Chi phí và bền vững** trong học phần thiết kế kiến trúc cloud. Trọng tâm là đánh đổi tài nguyên cam kết, theo nhu cầu và có thể bị thu hồi, từ đó lựa chọn mô hình phù hợp với workload, độ tin cậy, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt commitment/reservation, on-demand và spot/preemptible capacity.
- Đánh giá workload theo độ ổn định, khả năng gián đoạn và thời gian phục hồi.
- Tính chi phí hiệu dụng, utilization, break-even và mức cam kết hợp lý.
- Kết hợp nhiều loại capacity trong một kiến trúc autoscaling.
- Thiết kế checkpoint, retry, draining và xử lý interruption cho spot workload.
- Tránh overcommit, underutilization, capacity shortage và hidden cost.
- Xây dựng cost governance, dashboard, budget và quy trình review commitment.

## 1. Ba mô hình cấp phát tài nguyên

Tên gọi và điều khoản thương mại có thể khác giữa các cloud provider và từng dịch vụ. Cần phân biệt **cam kết chi tiêu/discount** với **reservation capacity thực sự**: một cam kết giá không phải lúc nào cũng bảo đảm một instance hoặc một slot compute có thể được cấp phát ngay. Trước khi mua, đọc đúng điều khoản sản phẩm, phạm vi áp dụng, tính linh hoạt và điều kiện hủy/thay đổi.

| Mô hình | Cách tính chi phí | Capacity/availability | Phù hợp |
| --- | --- | --- | --- |
| **Committed / Reserved** | Cam kết thời hạn hoặc mức chi tiêu/capacity để nhận discount | Tùy sản phẩm; có reservation bảo đảm capacity, có commitment chỉ áp dụng discount | Baseline ổn định, workload chạy liên tục hoặc có thể dự báo |
| **On-demand** | Trả theo mức sử dụng, không cần cam kết dài hạn | Linh hoạt nhưng vẫn chịu quota, regional capacity và service limits | Tải không chắc chắn, ứng dụng mới, peak ngắn, workload quan trọng cần capacity linh hoạt |
| **Spot / Preemptible** | Giá thấp hơn cho capacity dư thừa, có thể biến động theo cơ chế provider | Có thể bị thu hồi khi provider cần capacity; không nên xem là capacity bảo đảm | Batch, queue worker, CI, render, analytics và workload có thể retry/checkpoint |

### 1.1. Cam kết và reservation

Committed-use discount hoặc savings commitment thường đổi lấy một cam kết chi tiêu, loại tài nguyên, region hoặc thời hạn. Một số sản phẩm reservation còn gắn với capacity cụ thể hoặc bảo đảm khả năng khởi chạy trong phạm vi nhất định. Các mô hình không tương đương:

- Commitment có thể giảm đơn giá cho usage đủ điều kiện nhưng không bảo đảm capacity tại thời điểm cần.
- Capacity reservation có thể giữ chỗ capacity trong một zone/region nhưng bản thân reservation không nhất thiết là một discount.
- Reserved instance hoặc sản phẩm tương tự có thể kết hợp quyền lợi giá và điều kiện capacity tùy dịch vụ.
- Cam kết có thể có phạm vi family, platform, region, account hoặc loại usage cụ thể.

Hãy kiểm tra điều khoản về size flexibility, exchange, cancellation, payment option, unused commitment và sharing giữa account trước khi ra quyết định.

### 1.2. On-demand

On-demand giúp bắt đầu và dừng tài nguyên theo nhu cầu mà không cần cam kết dài. Đây thường là lựa chọn phù hợp cho giai đoạn thử nghiệm, workload chưa có baseline, peak ngắn và capacity dự phòng.

On-demand không đồng nghĩa “luôn có capacity vô hạn”. Vẫn có quota, service limit, regional capacity constraint, rate limit API và thời gian provisioning. Kiến trúc cần theo dõi quota và có kế hoạch cho tình huống không thể scale ngay.

### 1.3. Spot hoặc preemptible

Provider cung cấp capacity dư thừa với giá hấp dẫn nhưng có quyền thu hồi theo điều khoản của dịch vụ. Thời gian cảnh báo, cách gửi interruption signal và loại workload được phép chạy khác nhau theo provider/dịch vụ. Không giả định mọi sản phẩm đều báo trước cùng một khoảng thời gian.

Workload phải thiết kế để:

- Có thể bị dừng bất kỳ lúc nào theo semantics của dịch vụ.
- Lưu tiến độ hoặc thực hiện phần việc idempotent.
- Phát hiện interruption và ngừng nhận công việc mới.
- Hoàn tất/flush phần có thể trong khoảng cảnh báo nếu được cung cấp.
- Để job được retry hoặc tiếp tục ở một capacity khác.

Spot phù hợp nhất khi hệ thống có thể chấp nhận một worker mất đi mà không làm mất dữ liệu hoặc kết quả cuối.

## 2. Đánh giá workload trước khi chọn mô hình

Đừng chọn spot chỉ vì giá thấp, hoặc mua commitment chỉ vì mức discount hấp dẫn. Bắt đầu bằng workload profile.

### Các thuộc tính cần đo

| Thuộc tính | Câu hỏi |
| --- | --- |
| Baseline utilization | Năng lực tối thiểu cần thiết trong giờ thấp điểm là bao nhiêu? |
| Peak profile | Peak cao hơn baseline bao nhiêu, kéo dài bao lâu và xảy ra khi nào? |
| Predictability | Có thể dự báo theo giờ, ngày, mùa hoặc lịch business không? |
| Criticality | Mất capacity có gây mất doanh thu, dữ liệu hoặc vi phạm SLO không? |
| Interruption tolerance | Có thể pause, retry, checkpoint hoặc chuyển host không? |
| Startup time | Provisioning, image pull, warm-up và readiness mất bao lâu? |
| Statefulness | Workload giữ state trên local disk hoặc memory hay lưu state bên ngoài? |
| Runtime duration | Job chạy vài giây, vài phút hay nhiều giờ? |
| Scaling response | Có thể scale nhanh theo demand hay cần capacity luôn sẵn? |
| Portability | Workload có thể chạy trên nhiều instance type, zone hoặc region không? |
| Dependencies | Có bị ràng buộc bởi license, GPU, local storage, network locality không? |
| Cost of delay | Nếu job chậm 15 phút hoặc một giờ thì ảnh hưởng bao nhiêu? |

### Ma trận suitability

| Workload | Cam kết | On-demand | Spot/preemptible |
| --- | --- | --- | --- |
| API production với tải nền ổn định | Tốt cho baseline nếu cam kết đúng scope | Tốt cho burst/headroom | Chỉ dùng nếu có redundancy và workload chịu interruption |
| Database primary/stateful | Có thể phù hợp với baseline/discount theo sản phẩm | Có thể dùng cho capacity linh hoạt có kiểm soát | Thường không phù hợp nếu interruption gây gián đoạn hoặc mất state |
| Read replica có thể thay thế | Phù hợp nếu tải ổn định | Phù hợp cho tăng/giảm linh hoạt | Có thể cân nhắc nếu failover/rebuild được kiểm chứng |
| Batch analytics | Dùng cho pipeline chạy đều | Dùng cho deadline gần và job không thể chậm | Rất phù hợp nếu checkpoint/retry tốt |
| CI build/test | Thường không cần cam kết toàn bộ | Tốt cho pipeline cần kết quả đúng hạn | Phù hợp với job retryable và cache/artifact bên ngoài |
| Video/render/encoding | Có thể cho queue nền ổn định | Dùng cho deadline gấp | Phù hợp nếu job chia nhỏ và lưu checkpoint |
| Queue consumer | Có thể dùng cho baseline throughput | Dùng khi backlog tăng | Phù hợp nếu consumer có ack/retry/idempotency |
| Interactive low-latency | Có thể cho baseline | Phù hợp cho peak và capacity quan trọng | Chỉ dùng như phần capacity phụ có thể mất ngay |

Ma trận là hướng dẫn khởi đầu. Một workload có thể dùng nhiều loại capacity cùng lúc; quyết định cần xem SLO và cơ chế phục hồi thực tế.

## 3. Tách baseline, burst và interruptible work

Một chiến lược thực dụng là phân nhóm capacity theo vai trò:

- **Baseline:** mức công suất luôn cần để phục vụ tải nền và yêu cầu tối thiểu.
- **Burst/headroom:** năng lực thêm để xử lý peak, tăng trưởng hoặc node/zone failure.
- **Interruptible pool:** capacity có thể mất mà không làm hỏng nghiệp vụ.

~~~mermaid
flowchart TD
    DEMAND["Observed demand"] --> BASE["Stable baseline"]
    DEMAND --> BURST["Variable burst"]
    DEMAND --> FLEX["Deferrable / retryable work"]
    BASE --> COMMIT["Committed or reserved capacity"]
    BURST --> OD["On-demand capacity"]
    FLEX --> SPOT["Spot / preemptible pool"]
    COMMIT --> SERVICE["Application / workers"]
    OD --> SERVICE
    SPOT --> WORKER["Interruptible workers"]
~~~

### Không đặt toàn bộ baseline lên spot

Nếu toàn bộ năng lực phục vụ API được đặt trên spot, một đợt thu hồi có thể làm capacity giảm đột ngột đúng lúc tải cao. Autoscaler cần thời gian khởi tạo thay thế và không thể bảo đảm có capacity dự phòng ngay lập tức.

Baseline nên dựa trên mức tải cần phục vụ trong điều kiện bình thường và failure scenario. Burst có thể dùng on-demand hoặc capacity đã reserve. Spot nên được dùng cho phần có thể bị gián đoạn mà vẫn giữ SLO cốt lõi.

### Headroom phải tính cả failure

Không chỉ tính capacity cho peak bình thường. Hãy mô phỏng:

- Một zone mất capacity.
- Một nhóm spot instance bị thu hồi cùng lúc.
- Một instance family không còn capacity.
- Autoscaler hoặc quota không cấp thêm tài nguyên kịp.
- Queue backlog tăng nhanh hơn tốc độ xử lý.

Nếu phần còn lại không đủ phục vụ tải cốt lõi, cần admission control, load shedding hoặc capacity dự phòng thuộc mô hình đáng tin cậy hơn.

## 4. Tính chi phí hiệu dụng và break-even

Giá niêm yết theo giờ không phản ánh toàn bộ chi phí. Hãy tính mức sử dụng, phần capacity nhàn rỗi, commitment chưa dùng hết và chi phí vận hành.

### 4.1. Chi phí on-demand

Mô hình đơn giản:

\[
C_{OD}=H \times P_{OD} \times U
\]

Trong đó:

- \(H\): số giờ trong kỳ.
- \(P_{OD}\): giá đơn vị on-demand.
- \(U\): số đơn vị capacity trung bình được dùng; nếu tính theo một đơn vị luôn chạy thì \(U=1\).

Với autoscaling, nên tính theo tổng resource-hours thực tế thay vì lấy peak capacity nhân toàn bộ kỳ.

### 4.2. Commitment và utilization

Giả sử một commitment tương đương một đơn vị capacity mỗi giờ có chi phí cố định \(P_C\). Workload sử dụng trung bình \(u\) đơn vị trong \(H\) giờ, với usage đủ điều kiện áp dụng discount.

Chi phí cam kết và phần on-demand vượt cam kết có thể mô hình hóa:

\[
C_C=H \times P_C + \max(0,U-u)\times H \times P_{OD}
\]

Trong thực tế, cơ chế billing có thể theo spend/hour, family, instance normalization, account sharing hoặc usage coverage; công thức chỉ là mô hình đơn giản để hiểu utilization và unused commitment.

Tỷ lệ sử dụng commitment:

\[
Utilization=\frac{\text{Eligible usage covered}}{\text{Committed amount}}
\]

Tỷ lệ coverage khác utilization: coverage cho biết phần usage đủ điều kiện được commitment bao phủ; utilization cho biết phần cam kết đã được dùng. Cần xem cả hai để tránh mua quá nhiều hoặc cam kết sai scope.

### 4.3. Break-even

Với một đơn vị capacity chạy \(H\) giờ, nếu commitment có giá hiệu dụng \(P_C\) mỗi giờ và on-demand là \(P_{OD}\), commitment có lợi về giá trực tiếp khi:

\[
U \times H \times P_{OD} > H \times P_C
\]

Trong đó \(U\) là phần thời gian capacity có usage đủ điều kiện và có thể sử dụng discount. Ngưỡng sử dụng đơn giản:

\[
U_{BE}=\frac{P_C}{P_{OD}}
\]

Nếu commitment không có phí capacity cố định theo đơn vị hoặc có điều khoản khác, cần thay công thức theo pricing model thật. Phải thêm chi phí cơ hội do không thể giảm commitment khi workload giảm.

### 4.4. Ví dụ minh họa

Giả sử một workload có nhu cầu một đơn vị compute ổn định trong 730 giờ/tháng. On-demand giá 1.00 đơn vị tiền/giờ; commitment tương đương 0.65 đơn vị/giờ, không bao gồm phí phụ trợ.

| Phương án | Chi phí tháng giả định |
| --- | ---: |
| On-demand, chạy đủ 730 giờ | 730 |
| Commitment, chạy đủ và được cover | 474.5 |
| Commitment nhưng workload chỉ dùng 60% | 474.5 cho cam kết, cộng phần không được cover theo usage model tương ứng |

Ví dụ cuối cần phân biệt commitment theo capacity cố định với discount trên usage thực tế: nếu workload chỉ chạy 60% thời gian nhưng vẫn phải trả commitment toàn kỳ, phần nhàn rỗi không tự biến mất. Khi đó commitment chỉ có lợi nếu các workload khác có thể sử dụng cùng quyền lợi hoặc tổng eligible usage đủ lớn. Cần đọc billing model trước khi áp dụng số.

### Total Cost of Ownership (TCO)

TCO nên tính:

- Compute/storage/network usage.
- Commitment chưa sử dụng và phí trả trước.
- Data transfer, egress và cross-zone/cross-region.
- Image registry, artifact/cache và backup.
- Monitoring, scheduler, autoscaler và orchestration.
- Retry, duplicate work và thời gian job chạy lại.
- License, support và reservation management.
- Công sức của đội ngũ xử lý interruption, migration và capacity planning.
- Chi phí downtime, trễ deadline và mất cơ hội kinh doanh.

Một spot instance rẻ hơn đáng kể vẫn có thể làm tổng chi phí cao hơn nếu job bị thu hồi nhiều lần, phải recompute từ đầu hoặc cần vận hành phức tạp.

## 5. Mua commitment đúng mức

Commitment giúp giảm đơn giá khi workload đủ ổn định, nhưng mua quá nhiều làm tổ chức trả tiền cho capacity không dùng được.

### Quy trình sizing

1. Thu thập usage theo giờ/ngày trong một khoảng đủ đại diện, bao gồm mùa cao điểm.
2. Phân loại baseline ổn định và workload biến động.
3. Loại bỏ spike ngắn hoặc thử nghiệm không phản ánh demand lâu dài.
4. Kiểm tra growth forecast, migration và kế hoạch retire.
5. Xác định usage đủ điều kiện theo region/family/service/account.
6. Bắt đầu bằng mức commitment thận trọng.
7. Theo dõi utilization, coverage, unused commitment và forecast.
8. Review trước khi gia hạn hoặc mua thêm.

### Chọn term và payment option

Thời hạn dài thường có thể có discount cao hơn nhưng tăng rủi ro nếu kiến trúc hoặc nhu cầu thay đổi. Payment option trả trước, một phần hoặc theo kỳ ảnh hưởng cash flow và mức tiết kiệm. Đánh giá theo NPV/cash flow và khả năng thay đổi, không chỉ tỷ lệ discount.

### Avoid overcommit

Không mua commitment dựa trên:

- Peak demand ngắn hạn.
- Forecast tăng trưởng chưa được kiểm chứng.
- Workload sắp retire/migrate.
- Instance family/region có thể thay đổi.
- Usage đã được coverage bởi commitment hiện có.

Tránh đếm cùng một usage vào nhiều kế hoạch discount. Cost allocation và ownership cần làm rõ workload nào được tính vào commitment.

### Flexibility và portability

Cam kết theo family/region rộng hơn có thể giảm rủi ro thay đổi size hoặc account, nhưng discount, phạm vi và capacity guarantee có thể khác. Kiến trúc portability giúp đổi instance type hoặc region, nhưng không được giả định mọi license, storage, accelerator và network locality đều tương thích.

## 6. Quản lý spot/preemptible interruption

Spot chỉ phù hợp khi interruption là một trạng thái được thiết kế trước, không phải một tình huống bất ngờ hiếm gặp.

### Interruption lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> INTERRUPT_NOTICE: Provider signal or capacity reclaim
    INTERRUPT_NOTICE --> DRAINING: Stop new work
    DRAINING --> CHECKPOINT: Save progress and flush state
    CHECKPOINT --> TERMINATED: Instance reclaimed
    RUNNING --> TERMINATED: Abrupt loss / no usable notice
    TERMINATED --> REQUEUED: Work lease expires
    REQUEUED --> RUNNING: Replacement worker starts
~~~

Signal thời gian trước interruption là best-effort theo từng dịch vụ. Thiết kế phải chịu được cả trường hợp không có thời gian checkpoint.

### 6.1. Phát hiện interruption

- Theo dõi interruption notice/event theo cơ chế provider.
- Dùng lifecycle hook hoặc instance metadata phù hợp.
- Agent/worker phải kiểm tra signal trong thời gian chạy.
- Gửi event tới control plane bằng kênh có timeout ngắn.
- Nếu signal không đến, lease timeout hoặc heartbeat vẫn phải phát hiện worker biến mất.

### 6.2. Stop work và draining

Khi nhận signal:

1. Dừng nhận job mới.
2. Đánh dấu worker là draining/unavailable trong scheduler.
3. Hoàn tất phần việc ngắn nếu còn đủ thời gian và an toàn.
4. Lưu checkpoint hoặc kết quả trung gian bền vững.
5. Release lease/lock đúng cách nếu còn khả năng.
6. Dừng process và để orchestration thay capacity.

Không cố hoàn tất công việc vượt quá thời gian notice. Nếu job không kịp, để lease hết hạn và retry từ checkpoint gần nhất.

### 6.3. Checkpoint và idempotency

Checkpoint phải lưu ngoài instance, ví dụ durable object storage hoặc database, có version và checksum. Worker cần:

- Ghi checkpoint theo unit of work nhỏ.
- Commit output trước khi đánh dấu checkpoint hoàn thành.
- Sử dụng idempotency key/job ID.
- Phát hiện checkpoint cũ hoặc bị ghi đè.
- Reconcile output nếu worker chết sau khi ghi kết quả nhưng trước khi ack.
- Có retention và cleanup cho checkpoint.

Không lưu tiến độ duy nhất trên ephemeral disk của spot node. Instance bị thu hồi có thể làm mất disk/local cache.

### 6.4. Retry và duplicate

At-least-once processing có thể chạy lại một job. Consumer phải idempotent hoặc dùng deduplication/transactional commit. Dùng backoff và retry limit; poison job chuyển DLQ hoặc manual review. Không để một job liên tục fail và tiêu hao capacity không giới hạn.

## 7. Thiết kế workload phù hợp với capacity có thể bị thu hồi

Spot hoạt động tốt hơn khi workload được phân nhỏ, stateless và có thể chạy trên nhiều loại máy.

### Job decomposition

- Chia batch lớn thành các task độc lập hoặc partition.
- Giữ mỗi task đủ ngắn để giảm lượng công việc bị mất.
- Lưu input/output trên durable storage.
- Dùng scheduler phân phối lại task khi heartbeat mất.
- Có thể chạy cùng task trên nhiều worker nhưng chỉ commit một kết quả hợp lệ.

### Stateless worker

Đưa session, job state và metadata ra ngoài instance. Worker chỉ giữ working state tạm và có thể thay thế. Cache local chỉ là optimization; cache miss không được làm hỏng correctness.

### Instance flexibility

Cho phép nhiều instance size/family có khả năng đáp ứng yêu cầu CPU, memory, network, storage và architecture. Kiểm tra:

- Binary/container hỗ trợ CPU architecture nào.
- RAM và ephemeral storage tối thiểu.
- Network throughput và ENI/device limits.
- GPU/accelerator dependency.
- License hoặc host binding.
- Startup/warm-up và image availability.

Một pool đa dạng giảm phụ thuộc một capacity pool nhưng phải được benchmark để tránh chọn instance không đạt throughput hoặc cost-per-work-unit.

### Queue-based worker pool

~~~mermaid
flowchart TD
    PRODUCER["Job producer"] --> Q[("Durable queue")]
    Q --> SCHED["Scheduler / capacity controller"]
    SCHED --> OD["On-demand workers"]
    SCHED --> SPOT["Spot worker pool"]
    OD --> RESULT[("Durable result store")]
    SPOT --> RESULT
    SPOT -. "Interruption / lost heartbeat" .-> RETRY["Lease expiry / retry policy"]
    RETRY --> Q
    RESULT --> CONSUMER["Result consumer"]
~~~

Scheduler có thể ưu tiên spot cho backlog không có deadline gấp, nhưng phải giữ một mức on-demand capacity cho công việc quan trọng hoặc khi spot supply thấp.

## 8. Autoscaling với nhiều loại capacity

Autoscaling cần quyết định khi nào tăng/giảm capacity và loại capacity nào được phép nhận workload.

### Scaling signals

- Queue depth và oldest job age.
- Request concurrency và latency.
- CPU/memory/network utilization.
- Worker throughput và job duration.
- Spot interruption rate và capacity availability.
- On-demand quota và provisioning time.

CPU thấp không nhất thiết nghĩa là workload rảnh; worker có thể đang chờ I/O hoặc downstream quota. Dùng metric phản ánh demand thực.

### Mixed capacity policy

Một policy minh họa:

1. Giữ baseline on-demand hoặc reserved đủ cho SLA tối thiểu.
2. Khi queue tăng, ưu tiên thêm spot cho job retryable.
3. Nếu spot không cấp được và backlog đe dọa deadline, mở rộng on-demand trong budget.
4. Khi demand giảm, drain spot trước hoặc scale-in theo cost/risk policy.
5. Không giảm baseline dưới mức đủ chịu failure scenario.

### Scale-out lag

Autoscaler cần thời gian phát hiện, gọi API, chờ capacity, boot instance, pull image, tải secret và pass readiness. Nếu job cần xử lý ngay, chỉ dựa vào spot/on-demand scale-out có thể không đủ. Giữ warm pool hoặc headroom có thể cần thiết cho latency SLO.

### Scale-in

Scale-in phải tôn trọng active job, lease, draining, checkpoint và consumer group. Không terminate worker đang commit side effect mà không có idempotency/recovery.

## 9. Độ tin cậy và SLO khi dùng capacity linh hoạt

Giá rẻ không được đánh đổi bằng việc âm thầm làm hỏng SLO. Cần định nghĩa rõ điều gì xảy ra khi spot bị thu hồi.

### Tách SLO theo workload

| Workload | SLO gợi ý | Có thể dùng spot? |
| --- | --- | --- |
| Public API request | Latency/availability nghiêm ngặt | Chỉ như capacity phụ có redundancy và fallback |
| Batch data processing | Job completion trong cửa sổ thời gian | Có nếu checkpoint/retry đáp ứng deadline |
| CI test | Kết quả hoàn thành trong pipeline SLA | Có nếu job có thể retry và artifact được lưu bền vững |
| Video render | Tổng job hoàn tất trước deadline | Có nếu render chia chunk và checkpoint |
| Offline ML training | Training hoàn tất theo budget/time | Có nếu checkpoint model/optimizer và resume được |
| Stateful database primary | RPO/RTO và consistency | Thường không dùng spot cho writer chính |

### Capacity reserve cho failure

Khi tính baseline, phải tính cả khi:

- Một node hoặc zone mất.
- Một pool spot bị thu hồi cùng lúc.
- On-demand provisioning bị giới hạn.
- Worker retry làm tăng workload.
- Queue backlog cần xử lý sau outage.

Nếu không có đủ headroom, có thể cần giảm admission, ưu tiên job quan trọng, giãn deadline hoặc dùng capacity dự phòng đắt hơn.

### Budget interruption

Theo dõi interruption rate, retry rate, lost work, job completion time và cost per successful job. Một pool có giá đơn vị rẻ nhưng interruption cao có thể không hiệu quả. Đánh giá theo **chi phí cho kết quả hoàn thành**, không chỉ cost per instance-hour.

## 10. Chi phí ẩn của spot và commitment

### Spot hidden cost

- Work bị mất và phải chạy lại.
- Checkpoint write/read và storage.
- Queue, scheduler và orchestration.
- Thời gian kỹ sư xây resilience.
- On-demand fallback khi spot supply giảm.
- Provisioning churn, image pull và cache warm-up.
- Duplicate result, idempotency store và reconciliation.

### Commitment hidden cost

- Unused commitment khi demand giảm.
- Cam kết không khớp region/family/account/usage type.
- Mất flexibility trong migration hoặc đổi kiến trúc.
- Prepayment và chi phí vốn.
- Phải giữ một loại resource dù loại khác hiệu quả hơn.
- Phí hoặc giới hạn điều chỉnh/hủy theo hợp đồng.

### On-demand hidden cost

- Đơn giá có thể cao hơn trong thời gian dài.
- Chi phí thiếu kỷ luật nếu không có budget/autoscaling bound.
- Quota và capacity constraint có thể gây thiếu capacity vào peak.
- Tạo resource tạm nhưng quên cleanup.

### Unit economics

Chọn metric phản ánh giá trị:

- Cost per successful request.
- Cost per processed record.
- Cost per completed job.
- Cost per GB transformed.
- Cost per training run/converged model.
- Cost per tenant hoặc business transaction.

Khi so sánh on-demand với spot, tính cả số lần retry và phần công việc bị làm lại. Một worker spot nhanh nhưng hay bị thu hồi có thể tốn kém hơn worker on-demand ổn định.

## 11. Capacity planning và forecasting

Commitment nên dựa trên baseline có bằng chứng, không phải cảm giác. Spot nên dựa trên workload có flexibility và supply đa dạng.

### Data cần thu thập

- Resource-hours theo service, region, family và environment.
- p50/p95/p99 utilization theo giờ/ngày.
- Peak/burst pattern và seasonality.
- Queue throughput, backlog và job age.
- Spot interruption và replacement time.
- On-demand provisioning success/latency.
- Commitment utilization/coverage và unused spend.
- Growth forecast và roadmap migration.

### Forecast scenarios

Lập ít nhất ba kịch bản:

| Kịch bản | Demand | Quyết định |
| --- | --- | --- |
| Conservative | Demand thấp hơn forecast | Giữ commitment thận trọng, tránh lock-in |
| Expected | Demand dự kiến | Commit một phần baseline |
| Growth/peak | Demand tăng nhanh hoặc mùa cao điểm | Dùng on-demand/headroom, review commitment sau khi pattern ổn định |

Không commit toàn bộ forecast tăng trưởng chưa được kiểm chứng. Commitment có thể được mua dần khi usage thực tế chứng minh baseline mới.

### Forecast error

Đo chênh lệch forecast với actual. Nếu forecast thường xuyên cao hơn actual, tổ chức có thể đang overcommit; nếu thấp hơn nhiều, có thể bỏ lỡ discount hoặc thiếu capacity. Đưa forecast accuracy vào review hàng tháng/quý.

## 12. Cost governance và FinOps controls

Lựa chọn capacity phải gắn với trách nhiệm tài chính và kỹ thuật.

### Ownership và allocation

- Mỗi workload có owner và cost center.
- Tag theo service, environment, team, product và data classification khi phù hợp.
- Phân bổ shared commitment theo usage hoặc rule minh bạch.
- Phân biệt production, staging, dev/test và sandbox.
- Gắn budget và alert với owner có quyền xử lý.

### Guardrails

- Autoscaling minimum/maximum rõ ràng.
- Quota và instance family allowlist.
- Spot percentage cap theo workload criticality.
- Commitment purchase approval theo mức tiền và term.
- Budget alert khi utilization/coverage lệch.
- Cleanup cho ephemeral environment.
- Cost anomaly detection theo service/team/region.

### Showback và chargeback

Showback cung cấp chi phí cho team để họ hiểu usage; chargeback phân bổ chi phí vào ngân sách hoặc cost center. Cả hai cần quy tắc nhất quán, gồm shared platform, commitment discount, idle capacity và chi phí network.

Không đánh giá team chỉ bằng chi phí thấp. Phải xem cost cùng SLO, throughput, reliability và business value.

## 13. Sustainability và hiệu quả sử dụng tài nguyên

Sử dụng capacity hiệu quả có thể giảm chi phí và tác động môi trường, nhưng không nên giảm capacity đến mức liên tục retry hoặc làm workload chạy lâu hơn đáng kể.

### Các thực hành

- Right-size dựa trên profile CPU, memory, network và I/O.
- Tăng utilization có kiểm soát, tránh overprovision.
- Scale down tài nguyên nhàn rỗi theo giờ làm việc hoặc lịch batch.
- Chọn instance generation/architecture hiệu quả nếu workload tương thích.
- Đặt compute gần data để giảm network transfer.
- Giảm duplicate compute do retry hoặc pipeline chạy lại không cần thiết.
- Dùng spot cho workload interruptible nếu tổng energy/time-to-completion hợp lý.
- Archive hoặc expire tài nguyên và dữ liệu tạm đúng lifecycle.

### Hiệu quả trên mỗi đơn vị công việc

Theo dõi energy/carbon metric nếu provider và công cụ cung cấp dữ liệu đáng tin cậy. Nếu không, sử dụng proxy như compute-hours, CPU utilization, GB transferred và số lần retry. Tránh tuyên bố giảm carbon cụ thể chỉ từ việc chuyển sang spot nếu chưa có phương pháp đo.

### Trade-off

Một worker quá nhỏ có thể chạy lâu, tăng overhead và làm nhiều lần khởi tạo; worker lớn có thể xử lý nhanh nhưng để nhiều capacity nhàn rỗi. Cần benchmark cost/time/energy cho một đơn vị output.

## 14. Ví dụ thiết kế: nền tảng thương mại điện tử

**Bối cảnh giả định:** Một nền tảng có public API, database giao dịch, search indexing, image processing, recommendation training và nightly analytics. API cần latency ổn định; database giữ state quan trọng; image processing và analytics có thể chậm trong một khoảng thời gian; recommendation training có checkpoint. Đây là bài toán mô phỏng.

### Phân nhóm capacity

| Workload | Capacity chính | Capacity bổ sung | Lý do |
| --- | --- | --- | --- |
| API production | Reserved/committed baseline và on-demand headroom | Không dùng spot làm phần phục vụ bắt buộc | SLO latency/availability |
| Database primary | Capacity ổn định theo service tier | Reservation nếu semantics phù hợp | Stateful và cần writer availability |
| Search read nodes | Commitment cho baseline | On-demand hoặc spot replica có thể rebuild | Replica có thể tái tạo, nhưng query SLO phải giữ |
| Image processing | Spot workers | On-demand khi deadline backlog tăng | Job độc lập, output lưu bền vững |
| Nightly analytics | Spot pool | On-demand cho deadline quan trọng | Batch có thể retry/checkpoint |
| Model training | Spot đa dạng instance | On-demand fallback nếu deadline gần | Checkpoint model/optimizer |

### Kiến trúc

~~~mermaid
flowchart TD
    USER["Customer traffic"] --> API["API baseline pool"]
    API --> DB[("Transactional database")]
    API --> Q[("Durable work queues")]
    Q --> CTRL["Scheduler / autoscaler"]
    CTRL --> BASE["Committed baseline workers"]
    CTRL --> OD["On-demand burst workers"]
    CTRL --> SPOT["Spot interruptible workers"]
    BASE --> STORE[("Object / result store")]
    OD --> STORE
    SPOT --> STORE
    SPOT -. "Interruption" .-> CP["Checkpoint / retry / requeue"]
    CP --> Q
    STORE --> SEARCH["Search indexing / analytics / ML"]
~~~

### Quy tắc vận hành

- API không phụ thuộc vào spot worker để phản hồi request.
- Transaction database không được đặt trên capacity có thể bị thu hồi.
- Queue giữ công việc bền vững; worker mất thì lease hết hạn và job được requeue.
- Image processing lưu output theo job ID để retry không tạo bản trùng.
- Analytics có deadline; khi backlog vượt ngưỡng, mở on-demand capacity trong budget.
- Model training lưu checkpoint định kỳ và kiểm thử resume sau interruption.
- Dashboard hiển thị cost per completed image/job và interruption cost.

### Acceptance criteria

- API vẫn đạt SLO khi spot pool bị thu hồi.
- Không mất job đã được queue xác nhận.
- Duplicate worker không làm ghi output trùng hoặc sai.
- Batch hoàn thành trong deadline ngay cả khi spot supply giảm theo policy dự phòng.
- Commitment utilization đủ cao theo mục tiêu đã duyệt.
- Chi phí mỗi output tính cả retry, storage và orchestration.

## 15. Bài thực hành: chọn commitment, on-demand và spot cho workload cloud

**Tình huống:** Một công ty SaaS có API với tải nền ổn định và peak theo giờ, một nhóm worker xử lý export, pipeline CI, batch analytics ban đêm và database stateful. Worker export và analytics có thể retry; API cần SLO ổn định; CI job phải hoàn thành trước giờ release; database không được mất writer bất ngờ. Đây là dữ kiện mô phỏng.

### Nhiệm vụ

1. **Workload inventory:** lập profile theo baseline, peak, predictability, runtime, criticality và interruption tolerance.
2. **Capacity strategy:** xác định phần baseline committed/reserved, phần burst on-demand và phần interruptible spot.
3. **Financial model:** tính resource-hours, utilization, coverage, unused commitment, break-even và cost per successful job.
4. **Commitment decision:** đề xuất term, scope, payment option và mức mua ban đầu; nêu assumptions và sensitivity.
5. **Spot design:** thiết kế interruption signal, drain, checkpoint, lease, retry, idempotency, DLQ và replacement.
6. **Autoscaling:** định nghĩa queue/latency/concurrency signals, warm pool, min/max và fallback khi spot không có.
7. **Reliability:** mô phỏng spot pool bị thu hồi, zone failure, quota limit và queue backlog.
8. **Governance:** tạo owner/tag/budget/alert, commitment review và exception approval.
9. **Sustainability:** so sánh compute-hours và cost per unit output; đánh giá công việc bị chạy lại.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Stable baseline | Demand nền chạy liên tục | Commitment utilization/coverage đạt mục tiêu |
| Low demand | Demand giảm lâu hơn dự kiến | Unused commitment được phát hiện và forecast điều chỉnh |
| Peak burst | Traffic tăng đột ngột | On-demand/headroom đáp ứng hoặc admission policy rõ |
| Spot reclaim | Một nhóm worker nhận interruption | Drain/checkpoint/requeue không làm mất job |
| Abrupt loss | Spot node biến mất không có notice hữu ích | Lease timeout và retry phục hồi |
| Duplicate execution | Job được chạy đồng thời hai worker | Idempotency/dedup giữ output đúng |
| Spot shortage | Không cấp thêm spot capacity | On-demand fallback hoặc deadline/degradation policy kích hoạt |
| Quota limit | On-demand scale bị chặn | Alert, capacity plan và admission control hoạt động |
| Queue backlog | Consumer không theo kịp producer | Oldest age alert và scaling không quá tải downstream |
| Commitment mismatch | Resource family/region đổi | Cost coverage giảm và owner nhận alert |
| Database failure | Primary cần failover | Writer không phụ thuộc spot; RTO/RPO đáp ứng thiết kế |
| Cost anomaly | Retry làm cost per job tăng | Dashboard/anomaly alert phát hiện |

### Deliverables

- Workload suitability matrix.
- Baseline/burst/interruptible capacity plan.
- Commitment sizing và financial model.
- Spot interruption/checkpoint/retry architecture.
- Autoscaling policy và quota/headroom strategy.
- SLO, cost per unit output và sustainability metrics.
- Budget/tag/owner/approval governance.
- Load/failure test plan và ADR ghi trade-off.

## 16. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho capacity purchasing strategy |
| --- | --- |
| **Operational Excellence** | Usage, commitment, interruption, forecast và workload owner có dashboard/runbook/review không? |
| **Security** | Spot worker có identity, secret, network và data access ngắn hạn, giới hạn scope không? |
| **Reliability** | Baseline/headroom có chịu failure? Checkpoint, idempotency, queue, retry và deadline có được thử? |
| **Performance Efficiency** | Instance family/size, startup time, scaling lag và locality có đáp ứng workload không? |
| **Cost Optimization** | Commitment utilization, on-demand burst, spot retry, hidden cost và unit economics có được tính? |
| **Sustainability** | Có giảm idle capacity và duplicate work mà không kéo dài job hoặc tăng retry vô ích không? |

## 17. Những sai lầm thường gặp

**Mua commitment theo peak.** Peak ngắn làm tổ chức trả tiền cho capacity nhàn rỗi trong phần lớn thời gian.

**Nhầm discount commitment với capacity guarantee.** Giá ưu đãi không nhất thiết bảo đảm có instance ở zone mong muốn.

**Commit quá dài khi roadmap chưa ổn định.** Migration, đổi family hoặc giảm demand có thể làm cam kết không còn phù hợp.

**Đưa API hoặc database primary lên spot.** Interruption có thể trực tiếp ảnh hưởng availability hoặc consistency.

**Giả định spot luôn có warning.** Thiết kế phải chịu được instance loss đột ngột.

**Checkpoint chỉ trên local disk.** Dữ liệu tiến độ mất khi instance biến mất.

**Retry không idempotent.** Job chạy lại có thể tạo charge, record hoặc output trùng.

**Dùng spot cho mọi batch mà không có deadline policy.** Supply thấp có thể làm backlog vượt cửa sổ xử lý.

**Không giữ on-demand fallback.** Khi spot capacity không có, hệ thống không xử lý được công việc quan trọng.

**Không tính cost của retry và orchestration.** Giá instance thấp không phản ánh chi phí mỗi output.

**Autoscale vượt database capacity.** Tăng worker có thể làm downstream nghẽn hơn.

**Không theo dõi commitment coverage/utilization.** Có thể tiếp tục trả tiền cho cam kết không dùng.

**Đánh giá sustainability chỉ bằng giá.** Công việc chạy lại, thời gian hoàn tất và data transfer cũng ảnh hưởng hiệu quả tài nguyên.

## 18. Checklist trước khi triển khai chiến lược capacity

- [ ] Workload profile có baseline, peak, seasonality, criticality và interruption tolerance.
- [ ] Commitment/reservation được phân biệt đúng theo điều khoản dịch vụ.
- [ ] Phần baseline được xác định từ usage thực tế và failure headroom.
- [ ] Commitment scope, term, payment option, sharing và unused commitment được kiểm tra.
- [ ] Forecast có conservative/expected/growth scenario và đo forecast error.
- [ ] On-demand có quota, max scaling và budget guardrail.
- [ ] Spot chỉ chạy workload có thể retry/checkpoint hoặc được thay thế an toàn.
- [ ] Interruption notice, abrupt loss, draining và lease recovery được kiểm thử.
- [ ] Checkpoint/output nằm trên durable storage và có version/integrity.
- [ ] Job có idempotency, deduplication, retry limit và DLQ.
- [ ] Mixed capacity policy giữ đủ baseline khi spot shortage hoặc zone failure.
- [ ] Autoscaling tính provisioning lag, warm-up, downstream quota và scale-in drain.
- [ ] Cost tính compute, storage, network, retry, orchestration, idle và engineering overhead.
- [ ] Cost per successful request/job/output được theo dõi.
- [ ] Owner, tag, showback/chargeback, budget alert và purchase approval được thiết lập.
- [ ] Commitment utilization, coverage và spot interruption được review định kỳ.
- [ ] Security identity/secret/network của worker được giới hạn theo workload.
- [ ] Sustainability đánh giá resource-hours, idle capacity và duplicate work.
- [ ] Có ADR ghi assumptions, trade-off, owner và trigger xem lại chiến lược.

Đánh đổi giữa tài nguyên cam kết, theo nhu cầu và có thể bị thu hồi là quyết định về cả tài chính lẫn kiến trúc. Hãy dùng commitment cho baseline đủ ổn định và đúng phạm vi điều khoản, on-demand cho phần linh hoạt và nhu cầu chưa chắc chắn, spot cho workload được thiết kế để sống sót qua interruption. Đo utilization, coverage, cost per completed work và failure behavior thay vì chỉ so giá theo giờ. Một chiến lược tốt giữ capacity cốt lõi đủ tin cậy, biến công việc có thể trì hoãn thành tải linh hoạt và cho phép tổ chức thay đổi quy mô mà không bị mắc kẹt trong cam kết hoặc phụ thuộc vào capacity có thể biến mất.
