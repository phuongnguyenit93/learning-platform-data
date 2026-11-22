# Cảnh báo theo triệu chứng người dùng và ngưỡng bão hòa

Một hệ thống cơ sở dữ liệu có thể dùng CPU cao mà người dùng vẫn nhận phản hồi nhanh; ngược lại, CPU chỉ ở mức trung bình nhưng người dùng đã gặp timeout do connection pool cạn, lock wait, storage latency hoặc replica chậm. Vì vậy, cảnh báo vận hành hiệu năng không nên chỉ dựa trên một ngưỡng tài nguyên đơn lẻ. Cần bắt đầu từ điều người dùng đang trải nghiệm, sau đó dùng các tín hiệu tài nguyên để giải thích, dự báo và khoanh vùng nguyên nhân.

Trong vận hành DATABASE_PERFORMANCE, cảnh báo tốt phải trả lời được ba câu hỏi: người dùng đang bị ảnh hưởng ở mức nào, hệ thống đang tiến gần giới hạn nào, và người trực vận hành cần làm gì tiếp theo. Độ trễ p95/p99, tỷ lệ lỗi, throughput và độ mới dữ liệu mô tả tác động. CPU, I/O, memory, connection pool, lock, worker queue và replication lag mô tả mức bão hòa. Ngưỡng cần được hiệu chỉnh theo baseline và SLO, có thời gian duy trì, hysteresis và liên kết tới runbook để giảm cảnh báo nhiễu.

Bài học này trình bày cách chọn SLI/SLO hướng người dùng, thiết kế cảnh báo triệu chứng và cảnh báo nguyên nhân, xác định ngưỡng bão hòa, dùng nhiều cửa sổ thời gian và burn rate, phân nhóm mức độ nghiêm trọng, theo dõi các tài nguyên database, viết quy tắc cảnh báo có thể hành động và kiểm chứng chúng qua diễn tập.

## 1. Bắt đầu từ trải nghiệm người dùng

Một dashboard tài nguyên có thể cho biết database đang dùng 85% CPU, nhưng con số đó chưa nói được dịch vụ có đang gặp sự cố hay không. Nếu throughput ổn định và latency vẫn nằm trong mục tiêu, CPU cao có thể là trạng thái sử dụng hiệu quả. Ngược lại, CPU thấp không chứng minh hệ thống khỏe nếu request đang chờ connection, lock hoặc network.

Hãy định nghĩa các chỉ số thể hiện tác động trực tiếp:

- **Latency:** thời gian người dùng chờ một thao tác hoàn tất, thường theo p50, p95 và p99.
- **Error rate:** tỷ lệ request hoặc transaction thất bại, timeout hoặc trả kết quả không hợp lệ.
- **Throughput:** số request, transaction hoặc query nghiệp vụ hoàn tất trong một đơn vị thời gian.
- **Freshness:** độ trễ dữ liệu mà người dùng đọc được, đặc biệt khi đọc từ replica hoặc materialized view.
- **Availability:** tỷ lệ thao tác quan trọng có thể hoàn tất thành công trong khoảng thời gian đo.

Không phải ứng dụng nào cũng cần tất cả SLI trên. Chọn chỉ số gắn với hành trình nghiệp vụ quan trọng. Ví dụ, trang tra cứu đơn hàng cần latency và availability; dashboard phân tích cần freshness và thời gian hoàn tất báo cáo; dịch vụ ghi thanh toán cần tỷ lệ commit thành công và thời gian xác nhận.

### 1.1. SLI, SLO và SLA

- **SLI (Service Level Indicator):** phép đo chất lượng dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ request có latency dưới 300 ms.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một cửa sổ thời gian, ví dụ 99,9% request đọc đơn hàng hoàn tất trong 500 ms trong 30 ngày.
- **SLA (Service Level Agreement):** cam kết dịch vụ với khách hàng hoặc bên liên quan, có thể kèm điều khoản và hậu quả khi không đạt.

Alert nên được thiết kế chủ yếu quanh SLO và mức độ ảnh hưởng. Ngưỡng CPU, memory hoặc connection là tín hiệu hỗ trợ, không thay thế mục tiêu dịch vụ.

### 1.2. Chọn mẫu số đúng

Tỷ lệ lỗi phải có mẫu số rõ ràng:

\[
Error\ Rate=\frac{Failed\ Requests}{Total\ Requests}
\]

Không trộn health check, request nội bộ và thao tác nghiệp vụ nếu chúng có ý nghĩa khác nhau. Cũng cần phân biệt lỗi do client hủy request với lỗi server, timeout database và lỗi nghiệp vụ được dự kiến.

Nếu traffic gần bằng 0, tỷ lệ lỗi có thể dao động rất mạnh. Một request lỗi trên một request tạo ra 100% error rate nhưng chưa chắc cần page đội trực. Có thể kết hợp số lượng lỗi tuyệt đối, tỷ lệ lỗi và tín hiệu availability của thao tác quan trọng.

## 2. Cảnh báo theo triệu chứng và cảnh báo theo nguyên nhân

Hai nhóm cảnh báo có vai trò khác nhau:

| Loại | Ví dụ | Mục đích |
|---|---|---|
| Triệu chứng (symptom) | p99 vượt SLO, error rate tăng, freshness quá cũ | Xác nhận người dùng đang bị ảnh hưởng |
| Bão hòa (saturation) | Pool pending tăng, I/O latency cao, worker queue đầy | Phát hiện tài nguyên gần hoặc đã chạm giới hạn |
| Nguyên nhân (cause) | Blocking chain kéo dài, CPU quota throttling, storage volume lỗi | Hỗ trợ khoanh vùng và chọn hành động |
| Dự báo (capacity) | Dung lượng log còn 15%, backlog tăng liên tục | Cho thời gian xử lý trước khi sự cố xảy ra |

Một cảnh báo triệu chứng thường có mức ưu tiên cao vì phản ánh tác động. Cảnh báo nguyên nhân giúp người trực biết phải xem gì. Cảnh báo dự báo cần có lead time và hành động rõ, nếu không nó dễ trở thành thông báo nền bị bỏ qua.

### 2.1. Ví dụ: CPU cao nhưng người dùng chưa bị ảnh hưởng

Database duy trì CPU 90% trong giờ báo cáo, nhưng latency p95 của API vẫn đạt SLO, error rate thấp và throughput ổn định. Đây có thể là workload sử dụng CPU hiệu quả. Nên theo dõi và đánh giá headroom, nhưng chưa nhất thiết page người trực chỉ vì CPU vượt một con số cố định.

### 2.2. Ví dụ: CPU thấp nhưng request đã timeout

Pool ứng dụng có 40 connection và cả 40 đều đang được giữ. Một số transaction đang chờ dịch vụ ngoài; request mới chờ pool 2 giây rồi timeout. Database CPU chỉ 25% vì phần lớn session không thực thi SQL. Cảnh báo pool pending và request latency sẽ phát hiện vấn đề tốt hơn CPU threshold.

## 3. Thiết kế SLI hướng người dùng

SLI cần phản ánh đúng thao tác nghiệp vụ và được đo tại vị trí có thể nhìn thấy toàn bộ thời gian chờ.

### 3.1. Latency

Đo thời gian từ lúc request bắt đầu đến khi ứng dụng trả kết quả, không chỉ đo server-side SQL execution. Nếu đo riêng SQL, vẫn cần một SLI ở tầng ứng dụng để phát hiện pool wait, network và xử lý sau query.

Percentile hữu ích:

- p50: trải nghiệm của request ở giữa phân phối.
- p95: phần lớn request nằm dưới mức này, hữu ích để nhận biết suy giảm phổ biến.
- p99: tail latency, nhạy với các request chậm hoặc queue ngắn hạn.

Không lấy trung bình của percentile từ nhiều instance để tạo percentile toàn hệ thống. Cần tính percentile trên histogram/latency buckets đã tổng hợp đúng cách hoặc từ dữ liệu sự kiện phù hợp.

### 3.2. Error rate và timeout

Phân loại lỗi ít nhất theo:

- Timeout khi lấy connection.
- Query/statement timeout.
- Lock wait timeout hoặc deadlock victim.
- Connection reset/refused.
- Database unavailable/failover.
- Lỗi ứng dụng hoặc lỗi nghiệp vụ.

Một error rate tổng hợp cho biết tác động nhưng không đủ để chẩn đoán. Dùng error code hoặc label có cardinality được kiểm soát; không gắn raw SQL, user ID hoặc request ID làm label metric vì sẽ tạo cardinality bùng nổ.

### 3.3. Throughput

Theo dõi transaction nghiệp vụ hoàn tất mỗi giây, không chỉ số câu SQL được gửi. Một request có thể phát nhiều query; một query batch có thể xử lý hàng nghìn bản ghi. Chọn đơn vị phản ánh công việc hữu ích.

Throughput giảm cùng latency tăng thường là dấu hiệu bão hòa. Tuy nhiên, throughput giảm cũng có thể do traffic giảm; cần so với arrival rate hoặc số request đến.

### 3.4. Freshness

Với dữ liệu đọc từ replica hoặc summary, đo khoảng cách giữa thời điểm thay đổi nguồn được commit và thời điểm thay đổi đó có thể được đọc ở đích. Có thể dùng source watermark, log position hoặc timestamp nghiệp vụ.

Freshness alert nên dựa trên yêu cầu sản phẩm. Replica lag 5 giây có thể chấp nhận với dashboard tổng hợp nhưng không chấp nhận với màn hình cần read-after-write.

## 4. SLO và error budget

Giả sử SLO availability là 99,9% trong 30 ngày. Error budget là phần request có thể thất bại mà vẫn còn trong mục tiêu:

\[
Error\ Budget=1-SLO
\]

Với SLO 99,9%, error budget là 0,1% tổng request trong cửa sổ đánh giá. Nếu hệ thống tiêu thụ budget nhanh hơn tốc độ cho phép, cần ưu tiên độ tin cậy và giảm thay đổi rủi ro.

### 4.1. Burn rate

Burn rate cho biết tốc độ tiêu thụ error budget so với tốc độ được phép:

\[
Burn\ Rate=\frac{Observed\ Error\ Ratio}{Allowed\ Error\ Ratio}
\]

Nếu SLO cho phép error ratio 0,1% và quan sát thấy 1% lỗi trong cửa sổ, burn rate bằng 10. Nếu duy trì mức này, budget sẽ cạn nhanh hơn tốc độ mục tiêu 10 lần.

Burn rate hữu ích hơn một ngưỡng lỗi tuyệt đối khi traffic thay đổi, vì nó gắn với SLO. Cần chọn cửa sổ thời gian và lượng request tối thiểu để tránh alert từ mẫu quá nhỏ.

### 4.2. Multi-window alert

Một quy tắc có thể yêu cầu burn rate cao trong cửa sổ ngắn và vẫn cao trong cửa sổ dài. Cách này giúp phát hiện sự cố nhanh nhưng tránh page do một spike vài giây.

Ví dụ khái niệm:

~~~text
PAGE khi:
  burn_rate_5m > ngưỡng_cao
  VÀ burn_rate_1h > ngưỡng_xác_nhận
~~~

Các ngưỡng phải được tính từ SLO, thời gian phản ứng và lượng traffic. Không sao chép một con số từ hệ thống khác mà không hiểu cửa sổ và error budget.

## 5. Ngưỡng bão hòa là gì?

Bão hòa xảy ra khi một tài nguyên hoặc hàng đợi tiến gần giới hạn xử lý bền vững. Dấu hiệu thường không chỉ là utilization cao mà còn là queue, wait hoặc latency tăng.

Các tài nguyên database cần quan sát:

- CPU capacity và runnable queue.
- Connection pool và server session capacity.
- Data I/O và log I/O.
- Memory, buffer cache, memory grant và temporary spill.
- Lock/latch và transaction duration.
- Worker/process/thread capacity.
- Network throughput, RTT và connection establishment.
- Log storage, WAL/redo retention và replication backlog.
- Dung lượng đĩa và tốc độ tăng trưởng.

### 5.1. Utilization và queue

Utilization cho biết tỷ lệ sử dụng tài nguyên. Queue cho biết công việc đang chờ. Khi utilization tăng mà queue và latency chưa tăng, hệ thống có thể vẫn còn headroom. Khi utilization cao kéo dài cùng queue tăng, nguy cơ bão hòa rõ hơn.

Ví dụ:

- CPU 85% nhưng runnable queue thấp và latency ổn định: có thể vẫn hoạt động tốt.
- CPU 65% nhưng một core bị bão hòa và query latency tăng: tổng CPU che giấu hotspot.
- Storage throughput thấp nhưng read latency cao: có thể I/O ngẫu nhiên hoặc volume đang bị giới hạn IOPS.
- Pool utilization 100% và pending requests tăng: pool đã trở thành hàng đợi.

### 5.2. Ngưỡng phải phản ánh capacity thực tế

Ngưỡng 80% CPU không có ý nghĩa giống nhau trên mọi hệ thống. Một database có workload CPU-bound và burst ngắn có thể hoạt động bình thường ở 90%; hệ thống khác cần headroom lớn cho checkpoint hoặc peak traffic.

Hãy xác định saturation knee qua load test và lịch sử production: mức tải mà tăng concurrency không còn tăng throughput tương xứng, trong khi latency hoặc queue bắt đầu tăng nhanh.

## 6. Ngưỡng tĩnh, động và dựa trên baseline

### 6.1. Ngưỡng tĩnh

Ngưỡng tĩnh là giá trị cố định, ví dụ disk free dưới 10% hoặc connection pool pending lớn hơn 20 trong 5 phút.

Ưu điểm:

- Dễ hiểu và kiểm tra.
- Phù hợp giới hạn cứng như dung lượng, max connection hoặc replication retention.
- Dễ dùng trong runbook.

Hạn chế:

- Không phản ánh mùa vụ hoặc thay đổi quy mô.
- Có thể báo động trong giờ cao điểm bình thường.
- Có thể bỏ lỡ suy giảm tương đối khi baseline thay đổi.

### 6.2. Ngưỡng động

Ngưỡng động so sánh metric với baseline theo giờ, ngày trong tuần hoặc phân phối lịch sử. Ví dụ, số query mỗi phút cao hơn mức bình thường 3 độ lệch chuẩn trong cùng khung giờ.

Ưu điểm là thích ứng với seasonality. Hạn chế là baseline có thể học nhầm một giai đoạn đã suy giảm, dữ liệu ít làm mô hình không ổn định, hoặc sự kiện đặc biệt bị coi là bình thường nếu kéo dài.

### 6.3. Kết hợp ngưỡng

Trong thực tế có thể kết hợp:

- Hard limit cho giới hạn không thể vượt như disk full.
- Relative threshold cho thay đổi so với baseline.
- User-facing SLO alert cho tác động.
- Queue/latency threshold để xác nhận bão hòa.

Ví dụ, cảnh báo CPU chỉ page khi CPU cao kéo dài và request latency hoặc runnable queue đồng thời tăng. Nếu CPU cao nhưng SLO vẫn đạt, có thể tạo ticket capacity hoặc dashboard signal thay vì page.

## 7. Hysteresis, duration và chống cảnh báo chập chờn

Metric có thể dao động quanh ngưỡng. Nếu alert bật/tắt liên tục, người trực nhận nhiều thông báo nhưng không có hành động ổn định.

### 7.1. Pending duration

Yêu cầu điều kiện duy trì trong một khoảng thời gian trước khi firing. Ví dụ, pool pending phải vượt ngưỡng liên tục 3 phút mới page.

Duration quá ngắn gây false positive do spike; quá dài làm phát hiện muộn. Chọn theo tốc độ sự cố có thể gây hại và thời gian phản ứng.

### 7.2. Hysteresis

Hysteresis dùng ngưỡng kích hoạt và ngưỡng hồi phục khác nhau:

- Bật cảnh báo khi metric vượt 90%.
- Chỉ tắt khi metric giảm dưới 80% và giữ ổn định trong một khoảng thời gian.

Hai ngưỡng này chỉ là ví dụ. Mục tiêu là tránh trạng thái bật/tắt khi metric dao động sát ngưỡng.

### 7.3. Cooldown và deduplication

Cooldown hạn chế gửi lặp thông báo cho cùng một sự kiện trong khoảng thời gian ngắn. Deduplication gom nhiều alert có cùng nguyên nhân hoặc cùng service thành một incident.

Không dùng cooldown để che mất một sự cố mới. Cần phân biệt alert lặp của cùng incident với một lần tái phát sau khi hệ thống đã phục hồi.

## 8. Cảnh báo CPU và worker saturation

CPU cần được quan sát ở cả host, VM/container và DBMS.

Metric nên có:

- CPU utilization theo core và toàn host.
- Runnable queue hoặc scheduler queue.
- CPU throttled time trong container.
- VM CPU ready/steal nếu có.
- DB process CPU và top query CPU.
- Worker availability và số worker đang hoạt động.
- Parallel query worker planned/launched và imbalance.

### 8.1. Cảnh báo có ý nghĩa

Một cảnh báo CPU bền vững nên kết hợp:

- CPU hoặc quota utilization cao kéo dài.
- Runnable queue hoặc throttling tăng.
- User-facing latency/throughput suy giảm hoặc headroom dưới ngưỡng.

Nếu chỉ có CPU cao mà không có queue, throttling hay tác động, nên phân loại là capacity warning thay vì page khẩn cấp.

### 8.2. Ví dụ Prometheus alert rule

~~~yaml
groups:
  - name: database-capacity
    rules:
      - alert: DatabaseCpuSaturation
        expr: |
          avg by (cluster) (
            rate(node_cpu_seconds_total{mode="idle"}[5m])
          ) < 0.15
          and on (cluster)
          database_runnable_tasks > 4
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Database CPU capacity is saturated"
          description: "CPU idle is low and runnable work is queued."
~~~

Đây là ví dụ minh họa. Metric database_runnable_tasks và label cluster cần được exporter cung cấp; điều kiện node_cpu_seconds_total phải được diễn giải đúng theo số core và topology. Ngưỡng runnable cố định cần hiệu chỉnh theo số CPU khả dụng.

## 9. Cảnh báo connection pool và session capacity

Connection pool là hàng đợi quan trọng giữa ứng dụng và database. Các metric cần theo dõi:

- Total/max connections.
- Active/in-use connections.
- Idle connections.
- Pending/acquire queue.
- Acquire wait p95/p99.
- Acquire timeout count.
- Connection creation rate.
- Checkout duration.
- Leak detection và transaction age.

### 9.1. Cảnh báo pool saturation

Dấu hiệu mạnh:

- Active connections gần max.
- Pending requests lớn hơn 0 và kéo dài.
- Acquire wait vượt phần ngân sách latency của request.
- Timeout tăng.

Pool active 100% trong vài giây không nhất thiết cần page nếu không có pending và latency vẫn đạt SLO. Pool active 80% nhưng pending tăng liên tục có thể nghiêm trọng hơn nếu request bị queue.

### 9.2. Tổng pool qua nhiều replica

Không chỉ xem pool từng process. Tổng connection tiềm năng:

\[
C_{total}=\sum_{i=1}^{N}PoolMax_i+C_{jobs}+C_{ops}+C_{other}
\]

Autoscaling, rolling deployment và nhiều service dùng chung database có thể làm tổng pool vượt budget dù từng instance nằm dưới max. Cảnh báo nên so tổng server connections và tổng pool capacity với connection budget an toàn.

### 9.3. Ví dụ cảnh báo

~~~yaml
groups:
  - name: application-db-pool
    rules:
      - alert: DatabasePoolQueueGrowing
        expr: |
          sum by (service) (db_pool_pending_requests) > 5
          and
          histogram_quantile(
            0.95,
            sum by (service, le) (rate(db_pool_acquire_seconds_bucket[5m]))
          ) > 0.2
        for: 3m
        labels:
          severity: page
        annotations:
          summary: "Requests are waiting for database connections"
          description: "Pool queue and acquire latency exceed the service budget."
~~~

Tên metric là ví dụ. Cần xác minh histogram bucket, đơn vị giây, label và cách exporter ghi pending requests. Có thể thêm điều kiện error rate hoặc request latency để xác nhận tác động.

## 10. Cảnh báo data I/O và log I/O

Data I/O và log I/O có đặc tính khác nhau:

- Data I/O thường liên quan page read/write, checkpoint và buffer cache.
- Log I/O liên quan WAL/redo/transaction log, commit durability và replication.

Metric nên theo dõi:

- Read/write latency theo volume.
- IOPS, throughput và queue depth.
- Physical reads và bytes read theo query.
- Buffer/cache hit ratio cùng lượng đọc tuyệt đối.
- Log flush latency và log bytes/second.
- Checkpoint duration và write pressure.
- Log space hoặc WAL retention.

### 10.1. Không cảnh báo chỉ bằng cache hit ratio

Cache hit ratio cao có thể che giấu lượng I/O tuyệt đối lớn. Cache hit giảm cũng có thể bình thường khi workload chuyển sang scan. Hãy xem physical reads, latency và tác động query cùng lúc.

### 10.2. Cảnh báo log flush

Commit latency tăng cùng log flush latency và transaction throughput giảm có thể chỉ ra log device hoặc synchronous replication đang giới hạn. Nếu log generation tăng nhưng flush latency vẫn ổn định và replica theo kịp, đây có thể chỉ là tải ghi cao.

### 10.3. Disk capacity

Dung lượng còn lại là cảnh báo dự báo quan trọng:

- Free space thấp.
- Tốc độ tăng WAL/redo/temp/log.
- Thời gian dự kiến đến khi đầy.
- Replication slot hoặc archive giữ log lâu.

Ước lượng thời gian còn lại:

\[
TimeToFull\approx\frac{FreeSpace}{GrowthRate}
\]

Growth rate cần tính trên cửa sổ phù hợp và xét peak. Nếu log tăng 10 GB/giờ và còn 20 GB, thời gian lý thuyết đến đầy khoảng 2 giờ; nhưng cần chừa biên an toàn vì tốc độ tăng có thể thay đổi.

## 11. Cảnh báo memory pressure và temp spill

Không chỉ theo dõi memory utilization. Cần xem:

- Available memory và swap activity.
- Buffer pool/cache pressure.
- Memory grant pending hoặc query memory queue.
- Sort/hash spill.
- Tempdb/temp file usage.
- Per-query memory consumption.
- OOM kill hoặc DB process memory limit.

Một DBMS có thể dùng phần lớn RAM cho buffer cache theo thiết kế; memory utilization cao không tự động là sự cố. Cảnh báo nên dựa vào memory pressure, paging, grant wait, spill hoặc OOM risk.

Ví dụ:

~~~text
WARNING khi:
  memory grant queue tăng liên tục
  HOẶC temp spill bytes vượt baseline nhiều lần
  VÀ query latency có xu hướng tăng

PAGE khi:
  hệ thống gần OOM hoặc swap/thrashing gây ảnh hưởng dịch vụ
~~~

Đối với SQL Server, xem memory grants và tempdb spill; PostgreSQL xem temp files/temp_bytes; MySQL xem buffer pool và temporary table/disk activity; Oracle xem PGA workarea và TEMP usage. Tên metric và mức quan sát phụ thuộc phiên bản, cấu hình và quyền.

## 12. Cảnh báo lock, blocking và transaction dài

Lock wait là tín hiệu trực tiếp của tranh chấp. Metric cần:

- Số session đang bị block.
- Tổng và p95 lock wait duration.
- Blocking chain depth.
- Tuổi transaction blocker.
- Deadlock count/rate.
- Idle-in-transaction sessions.
- Long-running transaction count.
- Lock timeout và deadlock victim rate.

### 12.1. Cảnh báo theo tác động

Một deadlock đơn lẻ có thể được ứng dụng retry an toàn và không gây SLO breach. Nhưng deadlock rate tăng nhanh hoặc một blocker giữ lock nhiều phút có thể ảnh hưởng nhiều request.

Ưu tiên page khi:

- Nhiều request quan trọng bị block.
- Lock wait vượt latency budget.
- Blocking chain kéo dài.
- Deadlock/timeout tăng cùng error rate.
- Transaction lâu giữ snapshot hoặc gây áp lực cleanup.

### 12.2. Phân biệt blocker với nạn nhân

Alert cần kèm blocker session ID, database, application name, transaction age, object/resource và query sample nếu có thể. Đừng chỉ báo “50 session đang chờ lock” mà không chỉ ra blocker gốc.

Không tự động kill blocker chỉ dựa trên tuổi transaction. Một transaction dài có thể là migration hoặc công việc hợp lệ; cần runbook xác minh chủ sở hữu và rollback impact.

## 13. Cảnh báo replication lag và freshness

Với hệ thống có replica, cần tách:

- Send/transport lag: log chưa chuyển hết.
- Receive/flush lag: replica đã nhận nhưng chưa flush bền vững.
- Apply/replay lag: log đã nhận nhưng chưa áp dụng xong.
- User-visible freshness: thay đổi nghiệp vụ đã có thể đọc ở nơi ứng dụng truy vấn chưa.

Một con số “replication lag” tổng hợp có thể che giấu vị trí backlog. Alert cần biết queue tăng ở khâu nào.

### 13.1. Cảnh báo theo SLO freshness

Ví dụ:

- Dashboard chấp nhận dữ liệu trễ tối đa 5 phút.
- Tra cứu trạng thái đơn hàng chấp nhận trễ tối đa 2 giây.
- Read-after-write phải đọc từ primary hoặc dùng consistency token.

Đặt ngưỡng theo yêu cầu này. Không page chỉ vì lag 10 giây nếu mọi consumer chấp nhận 1 phút; cũng không coi lag 2 giây là nhỏ nếu nghiệp vụ cần phản ánh ngay.

### 13.2. Backlog tăng liên tục

Một replica có lag 30 giây nhưng backlog đang giảm có thể sắp bắt kịp. Một replica lag 10 giây nhưng backlog tăng nhanh có thể sớm vượt SLO. Hãy theo dõi cả giá trị hiện tại, tốc độ thay đổi và khả năng catch-up.

### 13.3. Disk/WAL retention

Replication slot, archive hoặc standby chậm có thể giữ WAL/redo và làm dung lượng log tăng. Cần cảnh báo cả lag và dung lượng bị giữ. Nếu chỉ cảnh báo lag, có thể bỏ lỡ nguy cơ disk full; nếu chỉ cảnh báo disk, khó biết consumer nào giữ log.

## 14. Ngưỡng theo thời gian và dự báo

Một ngưỡng tĩnh không phải lúc nào cũng đủ. Một số chỉ số cần nhìn xu hướng:

- Disk free giảm nhanh.
- WAL/redo backlog tăng liên tục.
- Queue length có slope dương.
- Connection usage tăng theo autoscaling.
- Query latency tăng theo số request đồng thời.
- Replica apply rate thấp hơn log generation rate.

### 14.1. Rate of change

Đo tốc độ thay đổi:

\[
Slope=\frac{Metric_{t2}-Metric_{t1}}{t2-t1}
\]

Nếu queue tăng 1.000 record/phút trong 10 phút liên tiếp, cảnh báo dự báo có thể được kích hoạt trước khi queue chạm giới hạn. Nhưng slope cần lọc nhiễu và kiểm tra xem tốc độ tiêu thụ có tăng tương ứng không.

### 14.2. Time-to-exhaustion

Với tài nguyên có giới hạn rõ như disk hoặc connection budget, có thể ước lượng thời gian tới ngưỡng:

\[
TTE=\frac{Capacity-CurrentUsage}{GrowthRate}
\]

Chỉ tính khi growth rate dương và tương đối ổn định. Nếu growth rate biến động mạnh, dùng percentile cao hoặc mô hình dự báo thận trọng và ghi rõ giả định.

## 15. Severity và routing

Không phải mọi alert đều cần đánh thức người trực.

| Mức | Ý nghĩa | Ví dụ | Hành động |
|---|---|---|---|
| Critical/Page | Người dùng đang bị ảnh hưởng nghiêm trọng hoặc nguy cơ mất dịch vụ tức thời | SLO burn nhanh, database unavailable, disk sắp đầy trong thời gian ngắn | Đánh thức on-call, mở incident |
| Warning | Bão hòa kéo dài hoặc headroom giảm, chưa có ảnh hưởng lớn | CPU/IO queue cao, pool gần max nhưng chưa timeout | Tạo cảnh báo cho đội phụ trách, điều tra trong giờ làm |
| Ticket/Info | Xu hướng hoặc cơ hội tối ưu | Query cost tăng nhẹ, dung lượng tăng theo dự báo dài hạn | Tạo ticket capacity/performance |

Severity phải gắn với tác động, thời gian còn lại và khả năng hành động. Một cảnh báo critical không nên chỉ chứa “CPU 95%”; nó cần nói dịch vụ nào bị ảnh hưởng, metric nào vượt SLO, trong bao lâu và runbook ở đâu.

### 15.1. Routing theo ownership

Route alert tới đội có thể xử lý:

- Application team: pool exhaustion, connection leak, request timeout.
- Database team: blocking, query regression, storage, checkpoint.
- Platform team: VM scheduling, CPU quota, disk/network.
- Data platform team: refresh backlog, replication/freshness, ETL.

Một incident có thể cần nhiều nhóm, nhưng phải có một incident owner điều phối để tránh nhiều nhóm cùng thay đổi cấu hình không phối hợp.

## 16. Alert phải có nội dung hành động

Một alert hữu ích nên chứa:

- Tên service/database và môi trường.
- Triệu chứng hoặc tài nguyên bị bão hòa.
- Giá trị hiện tại, ngưỡng, xu hướng và thời gian duy trì.
- SLI/SLO bị ảnh hưởng nếu có.
- Query fingerprint, pool hoặc node liên quan khi đã xác định.
- Link dashboard và runbook.
- Hành động an toàn đầu tiên.
- Owner/team và severity.

Ví dụ nội dung:

~~~text
Alert: Order API database pool saturation
Severity: Page
Impact: p99 request latency > 1.2 s for 8 minutes
Pool: 48/50 active; 17 requests pending
Acquire p95: 420 ms
Database: CPU 42%; active sessions 31
Likely direction: connections are being held longer than SQL execution
Next checks:
  1. Open request traces and checkout-duration panel
  2. Find long transactions / idle-in-transaction sessions
  3. Inspect remote dependency latency for affected endpoints
Runbook: database/pool-saturation
~~~

Ví dụ này cho thấy pool đang bão hòa trong khi CPU database không cao; hướng điều tra đầu tiên là connection hold duration và transaction, không phải tăng CPU.

## 17. Ví dụ quy tắc cảnh báo SLO

Một quy tắc Prometheus khái niệm:

~~~yaml
groups:
  - name: order-api-slo
    rules:
      - alert: OrderApiHighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{
              service="order-api",
              status=~"5.."
            }[5m]))
            /
            sum(rate(http_requests_total{
              service="order-api"
            }[5m]))
          ) > 0.01
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Order API error ratio is above 1%"
          description: "Check database, dependency and application errors."
~~~

Đây là ví dụ đơn giản. Trong production cần xử lý mẫu số bằng 0, loại trừ traffic không thuộc SLI, label grouping đúng service/region và kết hợp multi-window burn rate. Ngưỡng 1% không phải chuẩn chung; phải suy ra từ SLO.

Ví dụ cảnh báo latency theo histogram:

~~~yaml
- alert: OrderApiP95LatencyHigh
  expr: |
    histogram_quantile(
      0.95,
      sum by (le, service) (
        rate(http_request_duration_seconds_bucket{
          service="order-api"
        }[5m])
      )
    ) > 0.5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Order API p95 latency exceeds 500 ms"
~~~

Histogram phải được instrument nhất quán trên mọi instance. Nếu số request rất thấp, percentile có thể không ổn định; hãy kết hợp traffic threshold hoặc SLO event count.

## 18. Ví dụ cảnh báo theo ngưỡng bão hòa

### 18.1. Connection pool

~~~yaml
- alert: DbPoolAcquireTimeouts
  expr: sum by (service) (rate(db_pool_acquire_timeout_total[5m])) > 0
  for: 2m
  labels:
    severity: page
  annotations:
    summary: "Database pool acquire timeouts are occurring"
    description: "Inspect pool queue, checkout duration and database sessions."
~~~

Không page chỉ vì một counter cũ lớn hơn 0; dùng rate hoặc increase trong cửa sổ phù hợp. Nếu một timeout đơn lẻ được chấp nhận, cần ngưỡng số lượng/tỷ lệ và SLO impact.

### 18.2. Replication apply lag

~~~yaml
- alert: ReplicaApplyLagHigh
  expr: database_replica_apply_lag_seconds > 60
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Replica apply lag exceeds freshness budget"
    description: "Check log generation rate, apply throughput and replica resources."
~~~

Metric database_replica_apply_lag_seconds là metric exporter giả định. Phải xác minh nó đo apply lag chứ không phải send lag hoặc một giá trị ước lượng khác. Ngưỡng 60 giây chỉ phù hợp nếu freshness SLO cho phép.

### 18.3. Disk exhaustion

~~~yaml
- alert: DatabaseVolumeLowSpace
  expr: database_volume_free_bytes / database_volume_size_bytes < 0.10
  for: 5m
  labels:
    severity: page
  annotations:
    summary: "Database volume free space is below 10%"
    description: "Check data, log, temp and retained replication files."
~~~

Trong thực tế, nên cảnh báo theo cả phần trăm và dung lượng tuyệt đối, vì volume lớn có thể còn nhiều GB ở mức 5%, trong khi volume nhỏ có thể hết chỗ dù tỷ lệ còn 20%. Dự báo time-to-full hữu ích hơn nếu growth rate ổn định.

## 19. Metric và nguồn dữ liệu theo DBMS

Tên metric thực tế phụ thuộc exporter, phiên bản và cách triển khai. Bảng dưới đây nêu nhóm dữ liệu cần thu thập.

| DBMS | Session/query | Wait/lock | I/O/log/replication |
|---|---|---|---|
| PostgreSQL | pg_stat_activity, pg_stat_statements | pg_locks, wait_event | pg_stat_io (phiên bản hỗ trợ), pg_stat_wal, pg_stat_replication, replication slots |
| MySQL | Performance Schema statement digest, process list | InnoDB status, Performance Schema waits/locks | InnoDB metrics, redo/binlog status, replica applier status |
| SQL Server | Query Store, sys.dm_exec_requests, sessions | wait stats, lock DMVs, Extended Events | file I/O DMVs, transaction log, availability group queues |
| Oracle | V$SESSION, V$SQL, SQL Monitor | V$SESSION wait/blocking, system/session events | file statistics, redo/archive, Data Guard transport/apply views |

Không expose trực tiếp toàn bộ database catalog cho mọi dashboard hoặc người dùng. Dùng exporter/collector với quyền tối thiểu, giới hạn tần suất query và tránh metric label có cardinality quá cao.

## 20. Cảnh báo theo đặc thù PostgreSQL

Các tín hiệu đáng theo dõi:

- pg_stat_activity: active sessions, idle in transaction và wait events.
- pg_stat_statements: query calls, total/mean time và block reads/hits.
- pg_locks: lock waits và blocker.
- pg_stat_database: transaction, deadlock, temp files và block activity.
- pg_stat_io/pg_stat_wal: I/O và WAL metrics tùy phiên bản.
- pg_stat_replication: write/flush/replay position và lag.
- pg_replication_slots: WAL retention do slot.
- pg_database_size/pg_relation_size: tăng trưởng dung lượng.

Alert cần tính delta cho counter tích lũy và ghi nhận reset do restart. Với replication, theo dõi cả LSN distance và tốc độ WAL generation/apply, không chỉ một trường lag.

Một số trạng thái có thể bình thường trong thời gian ngắn. Ví dụ autovacuum chạy không nhất thiết là sự cố; cần cảnh báo khi transaction lâu, dead tuples/bloat, I/O hoặc latency cho thấy tác động thực tế.

## 21. Cảnh báo theo đặc thù MySQL

Các tín hiệu:

- Threads_connected và Threads_running.
- Connection errors và aborted connections.
- Performance Schema statement digest.
- InnoDB row lock waits, deadlocks và history list length.
- Buffer pool reads và page flushing.
- Redo log capacity/pressure và binlog growth.
- Replica receiver/applier status và queue.
- Temp table to disk và sort merge passes.

Threads_connected cao nhưng Threads_running thấp có thể là nhiều session idle. Threads_running cao cùng CPU/run queue hoặc lock waits tăng có thể chỉ ra concurrency quá lớn.

Seconds_Behind_Source không nên là tín hiệu duy nhất cho replication freshness. Cần đọc trạng thái applier, relay log và vị trí log theo phiên bản/cấu hình.

## 22. Cảnh báo theo đặc thù SQL Server

Các tín hiệu:

- Query Store runtime stats và plan changes.
- sys.dm_exec_requests, sessions và worker availability.
- Wait statistics theo delta.
- Blocking/deadlock từ Extended Events.
- Memory grants pending và query spill.
- Tempdb usage và contention.
- Transaction log usage, log reuse wait và log backup.
- Availability group log send queue và redo queue.

CXPACKET/CXCONSUMER, PAGEIOLATCH, WRITELOG, RESOURCE_SEMAPHORE hoặc LCK_M_* là ví dụ wait cần đặt trong ngữ cảnh. Không page chỉ vì một wait type xuất hiện; cần biết nó tăng trong cửa sổ nào và có liên quan SLO không.

## 23. Cảnh báo theo đặc thù Oracle

Các tín hiệu:

- Active sessions và wait class qua V$SESSION.
- SQL elapsed/CPU/buffer gets trong V$SQL.
- Blocking session và row lock.
- PGA workarea, TEMP usage và sort/hash spill.
- Redo generation và log switch frequency.
- Tablespace/datafile free space.
- Data Guard transport lag và apply lag.
- Resource Manager consumer group pressure.

ASH, AWR và SQL Monitor có thể cung cấp dữ liệu lịch sử/chi tiết nhưng quyền và điều kiện sử dụng phụ thuộc phiên bản, edition và licensing. Không giả định mọi môi trường đều có cùng tính năng.

## 24. Alert fatigue và quản lý chất lượng cảnh báo

Alert fatigue xảy ra khi người trực nhận quá nhiều cảnh báo không hành động được. Hệ quả là cảnh báo quan trọng có thể bị bỏ qua.

Giảm alert fatigue bằng cách:

- Mỗi alert phải có owner và hành động.
- Dùng symptom alert để xác định tác động, cause alert để hỗ trợ điều tra.
- Group alert cùng incident và deduplicate.
- Dùng pending duration, hysteresis và cooldown hợp lý.
- Chỉ page khi cần phản ứng ngoài giờ.
- Đưa xu hướng capacity dài hạn vào ticket thay vì page.
- Loại metric có cardinality cao và label không ổn định.
- Tạm silence có thời hạn khi bảo trì có kế hoạch, có owner và lý do.
- Rà soát alert không từng dẫn tới hành động hoặc không phát hiện sự cố thật.

Không silence một alert chỉ vì nó thường xuyên xuất hiện. Hãy sửa ngưỡng, metric hoặc hệ thống gây cảnh báo nhiễu.

## 25. Runbook gắn với từng loại cảnh báo

Một alert không có runbook khiến người trực phải tự tìm hiểu lại trong lúc sự cố. Runbook nên nêu:

1. Ý nghĩa metric và cách tính.
2. Service, database và workload bị ảnh hưởng.
3. Dashboard và truy vấn quan sát an toàn.
4. Ngưỡng bình thường và cách so baseline.
5. Các nguyên nhân thường gặp.
6. Bước phân biệt nguyên nhân.
7. Biện pháp giảm tác động có thể thực hiện.
8. Tác động/rủi ro của từng hành động.
9. Cách xác minh phục hồi.
10. Điều kiện escalations và owner.

Ví dụ runbook pool saturation:

~~~text
1. Xác nhận API p95/error rate có vượt SLO không.
2. Xem pool active/max, pending và acquire wait.
3. So sánh DB active sessions, CPU và I/O.
4. Tìm transaction lâu, idle-in-transaction và connection checkout duration.
5. Kiểm tra remote dependency latency và request traces.
6. Nếu DB bão hòa: giảm admission/concurrency theo policy.
7. Nếu app giữ connection lâu: giảm transaction scope hoặc xử lý leak theo owner.
8. Xác minh pending/acquire wait và API p95 giảm.
9. Theo dõi một chu kỳ peak trước khi đóng incident.
~~~

Runbook không nên yêu cầu tự động kill session, restart database hoặc tăng max_connections nếu chưa có điều kiện xác minh và phê duyệt vận hành phù hợp.

## 26. Kiểm thử cảnh báo trước khi production

Alert rule cần được kiểm thử như một phần của hệ thống:

- Replay metric lịch sử để xem alert firing/resolved có đúng thời điểm không.
- Tạo tải kiểm thử có kiểm soát để chạm ngưỡng CPU, pool, I/O hoặc lock.
- Tạo lỗi giả lập trong môi trường staging để xác minh SLO alert.
- Kiểm tra metric thiếu, exporter down và scrape gap.
- Kiểm tra label grouping, routing, deduplication và notification.
- Xác minh runbook, dashboard và owner link hoạt động.
- Kiểm tra alert không firing khi chỉ có spike ngắn nằm trong giới hạn cho phép.

### 26.1. Test alert theo kịch bản

| Kịch bản | Kết quả mong đợi |
|---|---|
| CPU cao ngắn, SLO bình thường | Không page; có thể ghi nhận metric |
| CPU cao kéo dài và p99 tăng | Cảnh báo theo mức ảnh hưởng |
| Pool đầy nhưng không pending | Không nhất thiết page |
| Pool pending và acquire wait tăng | Alert pool saturation |
| Replica lag tăng nhưng vẫn dưới freshness SLO | Warning hoặc không page theo policy |
| Replica lag vượt freshness SLO liên tục | Alert freshness |
| Disk time-to-full ngắn | Page trước khi hết dung lượng |
| Exporter mất metric | Alert telemetry missing |
| Deploy bảo trì đã khai báo | Silence có thời hạn theo quy trình |

## 27. Thiếu telemetry cũng là một rủi ro

Không có metric không đồng nghĩa hệ thống bình thường. Nếu exporter ngừng scrape, dashboard có thể hiển thị khoảng trống hoặc giá trị cũ.

Theo dõi:

- Scrape success và scrape duration.
- Last sample timestamp.
- Exporter process health.
- Metric freshness.
- Missing series của database/node/service.
- Clock skew giữa application, database và monitoring.

Đặt alert riêng cho monitoring pipeline. Nếu không có dữ liệu, cảnh báo cần nói rõ “không thể quan sát” thay vì hiển thị 0 và tạo cảm giác hệ thống khỏe.

## 28. Quy trình thiết kế cảnh báo từ đầu

1. **Chọn hành trình nghiệp vụ.** Xác định thao tác người dùng quan trọng và SLO.
2. **Định nghĩa SLI.** Chọn latency, error, throughput, availability hoặc freshness với mẫu số rõ.
3. **Xác định error budget.** Tính allowed error ratio và cửa sổ đánh giá.
4. **Tìm saturation knee.** Benchmark concurrency và tài nguyên để xác định vùng bắt đầu tăng queue/latency.
5. **Chọn metric nguyên nhân.** CPU, pool, I/O, memory, lock, worker, log, replication và disk.
6. **Đặt ngưỡng và duration.** Dùng hard limit, baseline, multi-window và hysteresis phù hợp.
7. **Chọn severity.** Page cho user impact nghiêm trọng hoặc nguy cơ tức thời; warning/ticket cho headroom và capacity.
8. **Thiết kế nội dung alert.** Thêm giá trị, ngưỡng, xu hướng, service, owner, dashboard và runbook.
9. **Cấu hình routing/dedup.** Gom cảnh báo cùng incident và tránh gửi lặp.
10. **Kiểm thử.** Replay lịch sử, fault injection và staging load test.
11. **Đánh giá sau triển khai.** Đo false positive, missed incident, thời gian phát hiện và thời gian khắc phục.
12. **Hiệu chỉnh định kỳ.** Cập nhật khi workload, topology, SLO hoặc capacity thay đổi.

## 29. Những sai lầm thường gặp

- **Page chỉ vì CPU cao.** CPU utilization không trực tiếp chứng minh người dùng bị ảnh hưởng.
- **Chỉ cảnh báo triệu chứng mà không có tín hiệu chẩn đoán.** Người trực biết hệ thống chậm nhưng không biết bắt đầu từ đâu.
- **Chỉ cảnh báo tài nguyên mà không theo dõi SLO.** Có thể bỏ lỡ pool wait, lock hoặc lỗi ứng dụng khi CPU thấp.
- **Dùng average thay percentile.** Tail latency có thể xấu nghiêm trọng nhưng average ít đổi.
- **Không xét traffic thấp.** Một lỗi trên một request có thể làm error rate 100%.
- **Ngưỡng cố định không có baseline.** Dễ báo động trong giờ cao điểm bình thường hoặc bỏ lỡ suy giảm tương đối.
- **Không có duration/hysteresis.** Alert chập chờn quanh ngưỡng.
- **Dùng counter tích lũy như rate.** Giá trị lớn có thể chỉ phản ánh lịch sử dài.
- **Dùng metric replica lag không rõ semantics.** Send lag, receive lag và apply lag không giống nhau.
- **Không tính tổng pool qua mọi replica.** Autoscaling có thể làm vượt connection budget.
- **Không cảnh báo telemetry missing.** Exporter chết có thể bị hiểu nhầm là metric bằng 0.
- **Alert không có owner/runbook.** Người trực không biết ai xử lý và bước tiếp theo.
- **Silence vô thời hạn.** Một cảnh báo quan trọng có thể bị che khuất lâu dài.
- **Không kiểm thử alert.** Rule có thể sai đơn vị, label hoặc không firing khi sự cố xảy ra.

## 30. Checklist cảnh báo production

- [ ] Đã xác định SLI/SLO theo hành trình người dùng quan trọng.
- [ ] Đã đo latency p50/p95/p99, error rate, throughput và freshness phù hợp.
- [ ] Mẫu số và cách loại trừ request của SLI được định nghĩa rõ.
- [ ] Có error budget và burn-rate alert cho SLO quan trọng.
- [ ] Cảnh báo triệu chứng được tách khỏi cảnh báo nguyên nhân và capacity.
- [ ] Ngưỡng bão hòa dựa trên benchmark/baseline và capacity thực tế.
- [ ] Có theo dõi queue, wait và latency cùng utilization.
- [ ] Có alert cho CPU, connection pool, data/log I/O, memory, lock, worker, disk và replication theo nhu cầu.
- [ ] Có phân biệt send/receive/apply lag và user-visible freshness.
- [ ] Ngưỡng có pending duration, hysteresis và deduplication hợp lý.
- [ ] Severity phản ánh tác động và thời gian cần phản ứng.
- [ ] Alert có owner, dashboard, giá trị hiện tại, ngưỡng và runbook.
- [ ] Metric counter được chuyển thành rate/delta đúng cách.
- [ ] Có cảnh báo khi exporter/scrape/telemetry bị mất.
- [ ] Label metric có cardinality được kiểm soát.
- [ ] Đã kiểm thử alert bằng dữ liệu lịch sử và kịch bản staging.
- [ ] Có quy trình silence có thời hạn và owner.
- [ ] Đã rà soát false positive, missed incident và alert fatigue.

Cảnh báo hiệu năng nên bắt đầu từ triệu chứng người dùng như latency, lỗi, throughput và freshness; ngưỡng CPU, connection, I/O, memory, lock và replication giúp giải thích mức bão hòa. Một ngưỡng có ý nghĩa phải dựa trên SLO, baseline và điểm saturation đã đo, đồng thời xét queue, thời gian duy trì và xu hướng. Hãy phân loại severity theo tác động, gắn alert với owner và runbook, kiểm thử cả điều kiện firing lẫn mất telemetry, rồi hiệu chỉnh theo workload thực tế. Mục tiêu là phát hiện đủ sớm để hành động, nhưng không làm đội vận hành mất tập trung bởi những cảnh báo không có ý nghĩa.
