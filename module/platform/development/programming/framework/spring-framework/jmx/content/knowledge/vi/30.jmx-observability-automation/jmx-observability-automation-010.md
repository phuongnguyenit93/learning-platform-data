# Thiết kế cảnh báo dựa trên ngưỡng và xu hướng trong Spring Framework JMX

## 1. Tổng quan

Trong ứng dụng Java/Spring, JMX (Java Management Extensions) cho phép công cụ vận hành đọc trạng thái MBeans như hàng đợi, bộ nhớ, thread pool, cache, connection pool và các bộ đếm do ứng dụng tự công bố. Khi kết hợp với một hệ thống thu thập metrics và đánh giá quy tắc, những dữ liệu đó có thể dùng để thiết kế **cảnh báo dựa trên ngưỡng và xu hướng**.

Một cảnh báo tốt không chỉ nói rằng một giá trị lớn hơn một con số. Nó phải trả lời:

- Dấu hiệu này có phản ánh vấn đề thật không?
- Mức độ ảnh hưởng tới người dùng và hoạt động kinh doanh là gì?
- Xu hướng đang xấu đi hay hệ thống đang tự hồi phục?
- Cần hành động ngay hay chỉ theo dõi?
- Người nhận cảnh báo cần kiểm tra gì tiếp theo?
- Có thể giảm cảnh báo trùng hoặc nhiễu mà không bỏ lỡ sự cố quan trọng không?

Trong Spring Framework JMX, MBean thường chỉ **công bố dữ liệu và operations**. Việc duy trì lịch sử, tính xu hướng, đánh giá ngưỡng, gửi thông báo và quản lý incident thường thuộc về monitoring/alerting system ở bên ngoài. JMX notification cũng có thể báo chuyển trạng thái, nhưng không thay thế hệ thống cảnh báo có lưu trữ, đánh giá cửa sổ thời gian và lịch sử.

### Mục tiêu

Sau bài học, bạn có thể:

1. Lựa chọn JMX attributes có ích để làm tín hiệu cảnh báo.
2. Phân biệt cảnh báo ngưỡng tuyệt đối, tỷ lệ, xu hướng và dự báo.
3. Thiết kế điều kiện \`for\`/duration, hysteresis và cooldown chống flapping.
4. Dùng counters, gauges, rates và rolling windows đúng ngữ nghĩa.
5. Thiết kế cấp độ warning/critical theo tác động và khả năng xử lý.
6. Kết hợp JMX metrics với hệ thống giám sát như Micrometer/Prometheus khi phù hợp.
7. Kiểm thử cảnh báo với dữ liệu bình thường, tăng tải, lỗi, thiếu dữ liệu và phục hồi.
8. Tạo thông điệp cảnh báo có ownership, ngữ cảnh, runbook và điều kiện kết thúc.

## 2. Mô hình dữ liệu và cảnh báo

\`\`\`text
Spring application
  |
  +-- MBeans / @ManagedResource
  |       |
  |       +-- QueueDepth
  |       +-- ActiveThreads
  |       +-- FailedJobsTotal
  |       +-- LastSuccessEpochMs
  |
  +-- JVM platform MXBeans
          |
          +-- HeapMemoryUsage
          +-- ThreadCount
          +-- GarbageCollector counts/times
          |
          v
   JMX collector / metrics bridge
          |
          v
   Time-series database
          |
          v
   Rule evaluation / alert manager
          |
          +-- Threshold checks
          +-- Trend / rate analysis
          +-- Missing-data handling
          +-- Dedup, grouping and routing
          |
          v
    Warning / Critical alerts
          |
          v
    Operator / incident response
\`\`\`

Cần phân biệt:

- **MBean:** nguồn dữ liệu quan sát được trong một JVM.
- **JMX attribute:** trạng thái hiện tại hoặc counter do MBean cung cấp.
- **JMX notification:** tín hiệu sự kiện tại thời điểm producer phát.
- **Collector:** chủ động thu thập dữ liệu qua JMX hoặc đọc từ hệ thống instrumentation.
- **Time-series store:** lưu samples theo thời gian.
- **Alert rule:** định nghĩa điều kiện cần cảnh báo.
- **Alert manager:** gửi, nhóm, khử trùng lặp, giới hạn và điều phối cảnh báo.
- **Runbook:** hướng dẫn người nhận đánh giá và xử lý.

Không mặc định \`MBeanServer\` lưu lịch sử đủ dài để tính xu hướng hoặc tự gửi email/Slack/PagerDuty. Những khả năng đó cần được triển khai ở tầng phù hợp.

## 3. Bắt đầu từ triệu chứng cần phát hiện

Đừng bắt đầu với câu hỏi “MBean nào có sẵn?” rồi tạo alert trên mọi attribute. Hãy xác định triệu chứng ảnh hưởng vận hành.

| Triệu chứng | Tín hiệu phù hợp | Điều cần kiểm tra |
|---|---|---|
| Công việc bị ùn ứ | QueueDepth, enqueue/dequeue rate | Backlog tăng liên tục hay chỉ spike |
| Worker ngừng tiến triển | LastSuccessTime, ProcessedTotal | Có công việc đầu vào không |
| Pool gần cạn | ActiveConnections / MaxConnections | Có giữ ở mức cao lâu không |
| JVM áp lực bộ nhớ | HeapUsed / HeapMax, GC pause | Heap max có xác định không; GC có đang tăng |
| Lỗi xử lý tăng | Failure counter rate / total rate | Có traffic hay không; mẫu số đủ lớn không |
| Scheduler bị trễ | LastExecutionAgeSeconds | Lịch chạy kỳ vọng là bao lâu |
| Cache hoạt động kém | Hit/Miss rate, latency | Có thay đổi traffic hoặc workload không |
| Thread pool nghẽn | ActiveThreadCount, QueueSize, rejected count | Queue có bounded không và tasks có timeout không |

Chỉ chọn một attribute khi nó có ngữ nghĩa rõ, chi phí đọc hợp lý và phản ánh một quyết định vận hành cụ thể.

## 4. Chọn đúng kiểu dữ liệu

### Gauge

Gauge biểu thị một giá trị đo tại thời điểm đọc:
- \`QueueDepth\`.
- \`ActiveConnections\`.
- \`HeapUsedBytes\`.
- \`CurrentWorkers\`.

Nó có thể tăng hoặc giảm và không nhất thiết có tính đơn điệu.

### Counter

Counter biểu thị tổng tích lũy theo một phạm vi:
- \`ProcessedJobsTotal\`.
- \`FailedJobsTotal\`.
- \`RejectedRequestsTotal\`.

Nếu counter reset khi restart, hệ thống tính rate cần nhận diện counter reset đúng cách. Không dùng “counter tăng 100” khi chưa biết khoảng thời gian.

### Timestamp

Ví dụ \`LastSuccessfulRunEpochMillis\`. Khi cảnh báo worker ngừng tiến triển, có thể tính:

\`\`\`text
lastSuccessAgeSeconds = (nowMillis - lastSuccessEpochMillis) / 1000
\`\`\`

Cần xử lý giá trị chưa có lần chạy thành công, clock skew và lịch xử lý có cố định không.

### Ratio

Ví dụ:

\`\`\`text
PoolUtilization = ActiveConnections / MaxConnections
\`\`\`

Chỉ áp dụng khi \`MaxConnections > 0\`; hiểu trường hợp kích thước tối đa dynamic và đo hai giá trị ở gần cùng thời điểm.

### Rate

Ví dụ:
\`\`\`text
ErrorRatePerSecond = increase(FailedJobsTotal in window) / windowSeconds
\`\`\`

Cần phân biệt rate lỗi tuyệt đối và tỷ lệ lỗi trên tổng request. Nếu traffic gần bằng 0, một lỗi đơn lẻ có thể tạo tỷ lệ 100% nhưng không đáng paging.

## 5. Ngưỡng tuyệt đối

Ngưỡng tuyệt đối đơn giản khi miền giá trị và năng lực hệ thống ổn định.

Ví dụ:
- QueueDepth lớn hơn 500 jobs.
- Worker paused trong giờ xử lý.
- Active connections vượt 90 trong pool có capacity 100.
- TimeSinceLastSuccess vượt 10 phút trong khi lịch kỳ vọng là 1 phút.

Một rule đơn giản:

\`\`\`text
if QueueDepth > 500:
    warning
\`\`\`

Nhưng nếu queue thường tăng lên 600 trong 15 giây sau một batch rồi tự xả, rule này dễ tạo alert nhiễu.

Nên bổ sung thời gian duy trì:

\`\`\`text
if QueueDepth > 500 for 5 minutes:
    warning
\`\`\`

Cửa sổ 5 phút chỉ là ví dụ, không phải ngưỡng chuẩn. Chọn dựa trên đặc điểm workload, tốc độ tiêu thụ và tác động người dùng.

### Khi nào ngưỡng tuyệt đối phù hợp?

- Có giới hạn capacity rõ ràng.
- Giá trị có ý nghĩa tuyệt đối.
- Ngưỡng được kiểm chứng bằng dữ liệu vận hành.
- Điều kiện vượt ngưỡng cần hành động nhất quán.

### Khi nào chưa đủ?

- Traffic có chu kỳ theo giờ/ngày.
- Mỗi cluster có capacity khác nhau.
- Queue tăng theo burst nhưng giảm nhanh.
- Hệ thống auto-scale, ngưỡng cố định nhanh lỗi thời.

## 6. Ngưỡng tương đối theo capacity

Một pool có 20 connections và pool có 200 connections không nên dùng cùng ngưỡng “18 connections đang dùng”.

Tính:
\`\`\`text
utilization = active / maximum
\`\`\`

Ví dụ:
- Warning nếu utilization trên 0.80 duy trì 10 phút.
- Critical nếu utilization trên 0.95 duy trì 3 phút.

Đây là điều kiện minh họa, không phải chuẩn cho mọi pool. Đối với pool có burst hợp lệ, dùng thêm waiters, timeout count hoặc queue depth để đánh giá khả năng người dùng bị ảnh hưởng.

Một tỷ lệ cao không luôn có nghĩa dịch vụ hỏng. Nếu pool có headroom thấp nhưng không có waiters/timeouts, có thể chỉ cần capacity planning thay vì paging.

## 7. Cảnh báo dựa trên xu hướng

Xu hướng trả lời “giá trị đang tăng hay giảm với tốc độ nào?”, không chỉ “giá trị đã vượt một mốc hay chưa?”.

Ví dụ:
\`\`\`text
Time       QueueDepth
10:00      100
10:05      180
10:10      280
10:15      400
10:20      560
\`\`\`

Giá trị 400 ở 10:15 có thể chưa vượt ngưỡng 500 nhưng backlog đang tăng. Nếu tốc độ tăng cao và không có dấu hiệu phục hồi, cảnh báo xu hướng sớm có ích.

### Độ dốc tuyến tính đơn giản

\`\`\`text
slope = (value_now - value_10min_ago) / 10
\`\`\`

Đơn vị là jobs/phút khi sample mỗi phút.

Trong thực tế, slope từ chỉ hai điểm dễ bị ảnh hưởng bởi spike hoặc missing data. Có thể dùng:
- Linear regression trên một cửa sổ.
- Rolling median/mean.
- EWMA để giảm nhiễu.
- Change-point/anomaly detection khi đã có dữ liệu nền.

Mỗi phương pháp cần kiểm chứng theo đặc tính tải. Không tạo alert vì một xu hướng nhỏ trong một cửa sổ ngắn có nhiều biến động ngẫu nhiên.

## 8. Kết hợp ngưỡng và xu hướng

Một cảnh báo hữu ích có thể yêu cầu cả hai:

\`\`\`text
Warning if:
  QueueDepth > 300
  AND slope over 10 minutes > 20 jobs/minute
  AND condition persists for 5 minutes
\`\`\`

Lợi ích:
- Không cảnh báo với queue cao nhưng đang giảm nhanh.
- Có thể cảnh báo trước khi chạm giới hạn quá lớn.
- Loại bớt một spike ngắn.

Tuy nhiên, nếu QueueDepth đã vượt một ngưỡng critical thật sự, không nên bắt buộc slope dương: queue rất cao và đứng yên vẫn là sự cố.

Một chiến lược:
- Warning: backlog vừa cao vừa đang tăng.
- Critical: backlog vượt ngưỡng ảnh hưởng người dùng, hoặc time-to-exhaustion rất ngắn.
- Recovery: backlog giảm và duy trì ở vùng an toàn.

## 9. Dự báo time-to-exhaustion

Khi queue có capacity giới hạn, có thể ước tính:

\`\`\`text
remainingCapacity = queueCapacity - currentDepth
netGrowthRate = enqueueRate - dequeueRate

if netGrowthRate > 0:
    timeToFull = remainingCapacity / netGrowthRate
\`\`\`

Ví dụ:
- Capacity: 10.000 jobs.
- Current depth: 8.000 jobs.
- Net growth: 100 jobs/phút.
- Time-to-full: 20 phút.

Đây là **ước tính** dựa trên giả định growth rate tiếp tục tương tự. Nếu auto-scaling hoặc rate thay đổi mạnh, dự báo có thể sai.

Nên:
- Dùng cửa sổ đủ dài.
- Kiểm tra netGrowthRate dương ổn định.
- Đặt confidence/freshness.
- Không đưa ra con số chính xác giả khi dữ liệu quá nhiễu.
- Kết hợp với absolute critical threshold.

## 10. Hysteresis chống flapping

Flapping xảy ra khi tín hiệu dao động quanh một ngưỡng khiến alert bật/tắt liên tục.

Ví dụ:
\`\`\`text
QueueDepth: 490 -> 510 -> 495 -> 520 -> 480 -> 505
threshold: 500
\`\`\`

Một ngưỡng duy nhất khiến hệ thống chuyển trạng thái liên tục.

**Hysteresis** dùng hai ngưỡng:
- Enter alert khi \`QueueDepth >= 500\`.
- Clear alert khi \`QueueDepth <= 350\`.

\`\`\`text
             QueueDepth
                 |
   Alert ON  >= 500
                 |
        350 .. 500   Keep previous alert state
                 |
   Alert OFF <= 350
\`\`\`

Đây là state machine. Trong khoảng giữa hai ngưỡng, giữ trạng thái trước đó. Có thể kết hợp thêm duration trước khi enter/clear.

### Ví dụ logic

\`\`\`java
public final class QueueAlertState {
    private boolean active;

    public boolean update(int queueDepth) {
        if (!active && queueDepth >= 500) {
            active = true;
        } else if (active && queueDepth <= 350) {
            active = false;
        }
        return active;
    }
}
\`\`\`

Đây là mô phỏng hysteresis đơn giản. Hệ thống alerting thực tế cần quản lý trạng thái qua nhiều samples và có thể cần \`for\` duration cùng missing-data semantics.

## 11. Cửa sổ thời gian và điều kiện duy trì

Một condition như “CPU > 90%” thường chưa đủ để paging. Một spike ngắn có thể bình thường.

Các cách:
- **Instantaneous:** đánh giá mỗi sample.
- **Rolling average:** trung bình trên cửa sổ.
- **Percentile:** biểu thị tail latency hoặc thời gian pause.
- **Sustained duration:** yêu cầu điều kiện liên tục trong N phút.
- **Count of violations:** ít nhất K trong N samples vượt ngưỡng.

Ví dụ:
\`\`\`text
Critical if:
  error_ratio_5min > 5%
  AND requests_5min >= 100
  sustained for 3 minutes
\`\`\`

Điều kiện request count giúp tránh cảnh báo 100% error rate khi chỉ có một request lỗi.

Cẩn thận chọn window quá dài: có thể giảm nhiễu nhưng làm chậm phát hiện sự cố. Lựa chọn phải dựa trên SLO và thời gian phản ứng cần thiết.

## 12. Warning và critical

Một mô hình hai cấp:

| Level | Mục đích | Hành động |
|---|---|---|
| Warning | Dấu hiệu xấu đang hình thành | Điều tra trong thời gian làm việc, chuẩn bị tăng capacity |
| Critical | Có khả năng ảnh hưởng nghiêm trọng hoặc đang vi phạm SLO | On-call paging hoặc incident response |

Không nên dùng:
- Warning khi chỉ số “khá cao” mà không biết tác động.
- Critical cho mọi trục trặc nội bộ không ảnh hưởng người dùng.
- Nhiều alerts khác nhau cùng paging cho một nguyên nhân.

Một hệ thống tốt cần gắn ngưỡng với capacity, SLO, thời gian chịu đựng và hành động thực tế.

## 13. Tín hiệu JMX cho queue và worker

Một Spring MBean có thể expose:

\`\`\`java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Import",
    description = "Import worker monitoring"
)
public class ImportWorkerMonitor {

    private final AtomicInteger pending = new AtomicInteger();
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicLong completed = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    @ManagedAttribute(description = "Current pending job count")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedAttribute(description = "Current active job count")
    public int getActiveCount() {
        return active.get();
    }

    @ManagedAttribute(description = "Completed jobs since restart")
    public long getCompletedTotal() {
        return completed.get();
    }

    @ManagedAttribute(description = "Failed jobs since restart")
    public long getFailedTotal() {
        return failed.get();
    }
}
\`\`\`

Đây là ví dụ management interface. Trong ứng dụng thật, dữ liệu phải được cập nhật từ worker/service thực tế, không phải một bộ counter độc lập không liên hệ với xử lý nghiệp vụ.

### Các alerts có thể thiết kế

- PendingCount cao và tăng liên tục.
- PendingCount cao, ActiveCount bằng 0 trong khi worker phải chạy.
- FailedTotal rate tăng theo khoảng thời gian.
- CompletedTotal không tăng trong lúc có PendingCount.
- Queue capacity gần cạn.

Chỉ đọc một snapshot không đủ để tính rate/trend. Collector cần lưu nhiều samples theo thời gian.

## 14. JMX platform MXBeans và cảnh báo JVM

Java cung cấp platform MBeans như:
- \`java.lang:type=Memory\`.
- \`java.lang:type=Threading\`.
- \`java.lang:type=GarbageCollector,name=...\`.
- \`java.lang:type=MemoryPool,name=...\`.

Có thể đọc heap:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();

long used = heap.getUsed();
long max = heap.getMax();

if (max > 0) {
    double utilization = (double) used / max;
    System.out.printf("Heap utilization: %.2f%n", utilization);
}
\`\`\`

Khi \`max\` không xác định (ví dụ -1 theo một số API), không tính tỷ lệ bằng phép chia. Phải xử lý trường hợp không có giới hạn rõ.

### Không chỉ cảnh báo “heap > 80%”

JVM có thể dùng heap cao trước GC rồi giảm, nên một snapshot 80% không tự chứng minh memory leak. Có thể cần:
- Heap used sau GC theo xu hướng.
- GC pause duration và frequency.
- Allocation rate.
- OutOfMemoryError indicators.
- JVM version, collector và heap sizing.
- Latency/error rate của ứng dụng.

Một alert đáng tin thường kết hợp tác động người dùng và dấu hiệu tài nguyên, không dựa hoàn toàn vào một ngưỡng chung.

## 15. Counter reset sau restart

Một bộ đếm \`FailedTotal\` có thể tăng:

\`\`\`text
100 -> 110 -> 130 -> process restart -> 0 -> 5
\`\`\`

Nếu collector lấy \`new - old\` theo cách ngây thơ, delta có thể âm, làm sai rate.

Cần:
- Biết counter reset khi nào.
- Dùng hàm increase/rate có hỗ trợ reset trong metrics engine.
- Gắn instance identity hợp lý.
- Kiểm tra missing samples trong thời gian restart.
- Tránh cộng chồng dữ liệu của hai process instances khi một pod thay thế pod khác.

Không gắn alert trực tiếp theo \`FailedTotal > 1000\` nếu counter chạy dài ngày, vì nó sẽ luôn vượt ngưỡng sau một khoảng thời gian. Alert thường nên dùng **tốc độ lỗi** hoặc tỷ lệ lỗi trong cửa sổ.

## 16. Missing data: không có dữ liệu cũng là một trạng thái

Nếu collector không đọc được JMX, hệ thống có thể:
- JVM chết.
- JMX connector mất kết nối.
- Firewall thay đổi.
- Credentials hết hạn.
- MBean bị unregister.
- ObjectName thay đổi do deploy.
- Scraper/collector lỗi.

Không nên mặc định missing data = zero. Giá trị zero biểu thị hệ thống báo đã đo được 0; missing biểu thị không có sample hợp lệ.

Một chính sách có thể:
- Alert riêng “JMX target unavailable” sau một thời gian thích hợp.
- Đánh dấu các cảnh báo phụ thuộc metrics là unknown, không tự clear sai.
- Phân biệt mất telemetry với worker hoạt động bình thường.
- Có runbook kiểm tra connector và service health.

Ví dụ:
\`\`\`text
QueueDepth = 0: đo được backlog bằng 0
QueueDepth = missing: không biết backlog là bao nhiêu
\`\`\`

Hai trạng thái không tương đương.

## 17. Notification và rule-based alerting

JMX notification có thể dùng để phát tín hiệu khi:
- Worker chuyển sang FAILED.
- Một resource chạm trạng thái DEGRADED.
- Configuration reload thất bại.
- Queue bị dừng ngoài dự kiến.

Nhưng JMX notification không mặc định lưu bền hoặc replay đầy đủ khi client offline. Một hệ thống cảnh báo cần độ tin cậy cao thường nên dùng **metrics polling + rule evaluation**, có thể bổ sung notifications để nhận tín hiệu sớm.

Ví dụ phối hợp:
1. Notification báo \`worker.failed\`.
2. Collector/alert engine đọc lại \`WorkerState\`.
3. Alert engine xác minh trạng thái kéo dài.
4. Gửi alert đến đúng owner.
5. Khi trạng thái trở lại RUNNING và ổn định, clear alert.

Điều này hạn chế phản ứng với notification đơn lẻ đã lỗi thời và cho phép phục hồi sau mất kết nối.

## 18. Tránh alert storm và duplicate alerts

Một sự cố database có thể làm:
- Connection pool saturation.
- Queue depth tăng.
- Error rate tăng.
- Latency tăng.
- Workers failed.

Nếu năm alert đều paging riêng cho cùng một nguyên nhân, on-call dễ bị quá tải.

Nên:
- Group alerts theo service, environment, cluster hoặc incident.
- Dùng inhibition/suppression có chủ đích.
- Chọn một primary symptom alert.
- Chuyển các secondary signals thành context.
- Có dedup key ổn định.
- Không dùng request ID hoặc session ID làm alert identity.
- Rate-limit notifications trong trường hợp flapping.

Không suppress quá rộng đến mức che nhiều sự cố độc lập. Rule grouping cần phản ánh ownership và failure domains thực sự.

## 19. Cảnh báo không chỉ dựa trên metric technical

Một JVM có thể có CPU/heap bình thường nhưng nghiệp vụ đang ngừng tiến triển. Ví dụ:
- QueueDepth cao.
- CompletedTotal không tăng.
- LastSuccessAt quá cũ.

Một cảnh báo “worker stalled” có thể hữu ích hơn “CPU cao” vì trực tiếp gắn với sự cố người dùng.

Điều kiện minh họa:

\`\`\`text
WorkerStalled if:
  PendingCount > 0
  AND increase(CompletedTotal over 10m) == 0
  AND WorkerState == RUNNING
\`\`\`

Cần lưu ý:
- Có batch dài hơn 10 phút hợp lệ không?
- Có độ trễ nhận việc theo lịch không?
- CompletedTotal reset/restart như thế nào?
- Có sự kiện retry kéo dài không?
- WorkerState stale hay mới?

Nếu không có throughput kỳ vọng và thời gian xử lý chuẩn, nên cân nhắc alert theo age của oldest pending job thay vì chỉ dựa vào CompletedTotal.

## 20. Đặt ngưỡng từ dữ liệu thực tế

Một quy trình chọn ngưỡng:
1. Thu thập baseline đủ dài (giờ cao điểm/thấp điểm, ngày thường/cuối tuần).
2. Xác định capacity, service SLO và điểm bắt đầu ảnh hưởng người dùng.
3. Đánh dấu các sự cố lịch sử và những mẫu bình thường.
4. Thử các candidate rules offline trên dữ liệu cũ.
5. Đo false positives, false negatives và detection delay.
6. Chọn warning/critical thresholds.
7. Đặt điều kiện duy trì, hysteresis và cooldown.
8. Review sau mỗi thay đổi lớn về workload hoặc capacity.

Không có “ngưỡng JMX chuẩn” cho mọi ứng dụng. Ngưỡng tốt là ngưỡng dựa trên tác động, năng lực thực tế và hành động rõ.

### Ngưỡng theo phân phối lịch sử

Nếu queue depth có chu kỳ, có thể dùng baseline theo thời gian trong ngày hoặc percentile. Nhưng anomaly detection cần quản lý:
- Seasonality.
- Cold start và ít dữ liệu.
- Thay đổi load hoặc deployment.
- Tránh coi sự cố kéo dài là baseline mới bình thường.
- Giới hạn tốc độ thay đổi threshold.

Một ngưỡng động quá linh hoạt có thể khiến alert không bao giờ bật khi hệ thống xấu đi chậm.

## 21. Một ví dụ cảnh báo với PromQL

Khi dữ liệu JMX được chuyển thành các time series có tên/labels phù hợp, có thể viết rules. Tên metrics ở đây **là ví dụ của collector**, không phải metric names được Spring/JMX chuẩn hóa mặc định.

### Queue backlog

\`\`\`promql
job_queue_pending{app="orders",env="prod"} > 500
\`\`\`

Cấu hình alert rule có thể đặt \`for: 5m\` để chỉ cảnh báo khi điều kiện duy trì liên tục. Việc này yêu cầu collector thực sự export metric \`job_queue_pending\`.

### Error rate

\`\`\`promql
rate(job_failed_total{app="orders",env="prod"}[5m]) > 2
\`\`\`

Đây là số failures/giây (trung bình 5 phút), không phải 2%. Muốn tính tỷ lệ phần trăm, cần mẫu số như processed/attempted request rate tương ứng.

### Tỷ lệ lỗi

\`\`\`promql
sum(rate(job_failed_total{app="orders",env="prod"}[5m]))
/
clamp_min(
  sum(rate(job_attempted_total{app="orders",env="prod"}[5m])),
  0.001
)
> 0.05
\`\`\`

Cần thêm điều kiện volume tối thiểu để tránh đánh giá sai khi ít traffic. \`clamp_min\` chỉ tránh chia cho 0, không tự chứng minh denominator đủ lớn.

### Xu hướng backlog

\`\`\`promql
deriv(job_queue_pending{app="orders",env="prod"}[15m]) > 0.5
\`\`\`

\`deriv()\` ước tính slope theo **đơn vị mỗi giây**. 0.5 jobs/giây tương đương khoảng 30 jobs/phút. Cần phối hợp backlog tuyệt đối để tránh alert khi queue rất nhỏ đang tăng nhẹ.

## 22. Alert rule YAML minh họa

Một ví dụ theo kiểu Prometheus rules:

\`\`\`yaml
groups:
  - name: orders-jobs
    rules:
      - alert: OrdersQueueBacklogHigh
        expr: job_queue_pending{app="orders",env="prod"} > 500
        for: 5m
        labels:
          severity: warning
          team: orders
        annotations:
          summary: "Orders queue backlog high"
          description: "Queue {{ $labels.queue }} has exceeded 500 pending jobs for 5m"
          runbook_url: "https://intranet.example/runbooks/orders-queue"
\`\`\`

Địa chỉ runbook trên là **placeholder**. Cần thay bằng URL nội bộ thật nếu triển khai. Điều kiện này chỉ hoạt động khi collector xuất metric và labels đúng với query.

Trong dự án thực, nên version-control alert rules, review qua pull request và kiểm thử bằng các công cụ của alerting stack đang dùng.

## 23. Thiết kế thông điệp cảnh báo

Một thông điệp cần thông tin đủ để điều tra:

\`\`\`text
[CRITICAL] Orders worker backlog may exhaust capacity

Environment: production
Service: orders
Instance: worker-03
Resource: ImportQueue
Current queue depth: 8,600 / 10,000
15m trend: +95 jobs/min
Estimated time to capacity: ~15 min
Started at: 2026-11-11 08:30 UTC
Suggested checks:
  - Verify dequeue rate and worker health
  - Inspect downstream database latency
  - Check recent deployment and rejection counts
Runbook: <internal URL>
\`\`\`

Một cảnh báo tốt nên có:
- Severity.
- Service/environment/instance.
- Tín hiệu và ngưỡng.
- Khoảng thời gian/cửa sổ.
- Trend hoặc mức độ thay đổi nếu liên quan.
- Trạng thái hiện tại và timestamp.
- Đội chịu trách nhiệm.
- Runbook và bước điều tra.
- Điều kiện clear/recovery.

Đừng tự đưa ra dự báo chính xác nếu số liệu thiếu hoặc slope không ổn định.

## 24. Chống flapping bằng state machine

Một rule có thể được mô hình hóa:

\`\`\`text
NORMAL
  |
  | QueueDepth >= 500 for 5m
  v
WARNING
  |
  | QueueDepth >= 800 for 3m
  v
CRITICAL
  |
  | QueueDepth <= 600 for 5m
  v
WARNING
  |
  | QueueDepth <= 350 for 10m
  v
NORMAL
\`\`\`

Các ngưỡng riêng cho enter/clear thể hiện hysteresis; durations giúp tránh transitions do dao động ngắn. Khi điều kiện critical giảm, có thể quay về warning trước khi về normal.

Thiết kế state machine cần trả lời:
- Có cần gửi alert khi severity tăng?
- Có cần gửi recovery notification?
- Nếu dữ liệu missing, giữ state hay chuyển unknown?
- Nếu collector restart, phục hồi state bằng cách nào?
- Nếu instance biến mất do scale-down hợp lệ, có nên alert không?

Không dùng một static state machine riêng trong từng MBean để thay thế alerting system trừ khi có lý do cụ thể; alert state thường nên do hệ thống monitoring quản lý trên dữ liệu lịch sử.

## 25. Kiểm thử alert rules

Không chỉ kiểm tra điều kiện trên một sample. Cần kiểm thử chuỗi thời gian.

### Case A — Spike ngắn

\`\`\`text
0m: 200
1m: 650
2m: 250
3m: 210
\`\`\`

Nếu rule yêu cầu >500 trong 5 phút, không nên cảnh báo.

### Case B — Tăng liên tục

\`\`\`text
0m: 200
5m: 360
10m: 540
15m: 700
\`\`\`

Rule backlog + trend có thể cảnh báo nếu đủ duration.

### Case C — Duy trì cao nhưng giảm

\`\`\`text
0m: 900
5m: 820
10m: 720
15m: 580
\`\`\`

Rule trend dương không nên bật, nhưng critical threshold tuyệt đối vẫn có thể phù hợp khi queue đang gây ảnh hưởng.

### Case D — Flapping

\`\`\`text
490, 510, 495, 520, 485, 515
\`\`\`

Hysteresis/duration giúp tránh gửi alert liên tục.

### Case E — Counter reset

\`\`\`text
FailedTotal: 100 -> 110 -> restart -> 0 -> 2
\`\`\`

Rate logic cần xử lý reset, không suy ra rate âm.

### Case F — Missing samples

\`\`\`text
QueueDepth: 500 -> missing -> missing
\`\`\`

Phải phát hiện mất telemetry hoặc áp dụng unknown state phù hợp, không mặc định queue=0 và tự clear cảnh báo.

### Case G — Tải ít

Một lỗi trong một request có thể tạo error ratio 100%; yêu cầu volume tối thiểu để tránh paging sai.

## 26. Kiểm thử JMX source và thu thập

Một rule tốt vẫn vô ích nếu dữ liệu JMX sai.

Có thể kiểm tra MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Import"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

Object pending = server.getAttribute(name, "PendingCount");
System.out.println("PendingCount=" + pending);
\`\`\`

Chỉ dùng platform server nếu exporter thực sự đăng ký vào đó. Trong môi trường nhiều MBeanServers, phải lấy đúng reference.

Kiểm thử đường end-to-end:
1. Tạo dữ liệu mô phỏng backlog.
2. Xác minh MBean attribute thay đổi.
3. Xác minh collector đọc được giá trị.
4. Kiểm tra metric label mapping.
5. Kiểm thử alert rule bằng test series.
6. Kiểm tra Alertmanager route đến đúng team.
7. Xác minh recovery khi giá trị về bình thường.

Không gọi operations gây hại hoặc tạo tải production quá mức để thử alert.

## 27. Metrics vs JMX notifications

| Tiêu chí | JMX attribute polling | JMX notification |
|---|---|---|
| Trạng thái hiện tại | Có | Thường cần đọc lại snapshot |
| Lưu lịch sử | Cần collector/time-series store | Không mặc định |
| Trend/rate | Có nếu lưu samples | Không trực tiếp |
| Phát hiện thay đổi nhanh | Phụ thuộc polling interval | Có thể gần thời điểm phát |
| Mất connection | Collector có thể phục hồi qua sample mới | Có thể bỏ lỡ events |
| Reconnect | Đọc lại snapshot | Đăng ký lại listener |
| Alert thresholds | Phù hợp với rule engine | Thường dùng làm tín hiệu bổ trợ |
| Durable exactly-once | Không tự bảo đảm | Không tự bảo đảm |

Kết hợp hai phương án khi cần:
- Notification báo bất thường ngay.
- Attribute polling xác nhận và theo dõi phục hồi.
- Alerting engine đánh giá thời gian duy trì và xu hướng.
- Log/event store giữ lịch sử khi nghiệp vụ yêu cầu.

## 28. Quy trình triển khai alert production

1. **Xác định mục tiêu:** phát hiện người dùng bị ảnh hưởng hoặc nguy cơ sắp ảnh hưởng.
2. **Chọn source metrics:** JMX attributes với semantics rõ.
3. **Đặt nhãn:** app, env, instance, resource, owner.
4. **Thu baseline:** hiểu normal variation.
5. **Chọn thresholds:** tuyệt đối/tỷ lệ/xu hướng.
6. **Đặt temporal logic:** window, duration, hysteresis.
7. **Xử lý missing data:** có rule cho mất telemetry.
8. **Định nghĩa severity và routing:** đúng nhóm on-call.
9. **Viết runbook:** bước kiểm tra nguyên nhân và cách xử lý an toàn.
10. **Test lịch sử và giả lập:** false positive/negative, reset, reconnect.
11. **Triển khai theo giai đoạn:** ban đầu có thể chỉ cảnh báo không paging để đánh giá.
12. **Review định kỳ:** khi capacity, workload hoặc kiến trúc đổi.

Một alert được duy trì tốt có owner, tài liệu, cách kiểm tra và lịch review. Rule không còn ý nghĩa cần được gỡ thay vì tích tụ.

## 29. Các anti-pattern

**1. Cảnh báo mọi attribute.**  
Gây nhiễu và không gắn với hành động cụ thể.

**2. Chỉ dùng một ngưỡng tức thời.**  
Dễ phản ứng với spike ngắn.

**3. Không phân biệt counter và gauge.**  
Tính rate sai hoặc tạo alert luôn bật theo tổng tích lũy.

**4. Không xử lý missing data.**  
Có thể coi mất telemetry là khỏe mạnh.

**5. Dùng ngưỡng CPU/heap chung cho mọi JVM.**  
Không xét GC, SLO, workload và memory sizing.

**6. Bỏ qua điều kiện traffic tối thiểu.**  
Một lỗi đơn lẻ gây tỷ lệ lỗi 100%.

**7. Chỉ cảnh báo theo trend.**  
Có thể bỏ qua trạng thái đã rất xấu nhưng không còn tăng.

**8. Alert storm do cùng một nguyên nhân.**  
Thiếu grouping và inhibition thích hợp.

**9. Thiếu owner hoặc runbook.**  
Người nhận không biết hành động gì.

**10. Dùng JMX notification làm event history.**  
Không có durable replay mặc định.

**11. Gắn nhãn cardinality quá cao.**  
Request IDs/session IDs không phù hợp làm alert identity.

**12. Auto-remediation không có giới hạn.**  
Hành động tự động như restart hoặc scale có thể làm sự cố nghiêm trọng hơn khi tín hiệu sai.

## 30. Tự động hóa phản ứng với cảnh báo

Không phải alert nào cũng nên tự động gọi JMX operation.

Một workflow có thể gồm:

\`\`\`text
Alert condition
      |
      v
Validate health + recent change + current state
      |
      v
Choose action
      |
      +-- Notify only
      +-- Create incident
      +-- Restart worker (under strict policy)
      +-- Scale capacity (with guardrails)
      +-- Pause intake (when safe)
\`\`\`

Nếu có auto-remediation, cần:
- Giới hạn số lần chạy.
- Chỉ xử lý khi trạng thái được xác minh.
- Có cooldown.
- Có audit và rollback.
- Tránh race giữa nhiều alert processors.
- Có kiểm soát quyền gọi operations.
- Có khả năng disable automation trong incident.
- Không retry thao tác không idempotent mù khi remote JMX timeout.

Một alerting rule không được quyền mặc định thao tác production chỉ vì nó phát hiện vượt ngưỡng.

## 31. Bài tập thực hành

### Bài A — Thiết kế backlog alert

1. Tạo MBean với PendingCount và CompletedTotal.
2. Giả lập queue tăng rồi giảm.
3. Thiết kế warning threshold + slope.
4. Thiết kế critical threshold độc lập với slope.
5. Thêm duration và hysteresis.
6. Viết điều kiện clear.

### Bài B — Counter rate

1. Tạo FailedTotal và AttemptedTotal.
2. Lưu samples theo từng phút.
3. Tính error rate theo window 5 phút.
4. Xử lý counter reset.
5. Bổ sung min traffic volume.
6. So sánh absolute failures/second với percentage.

### Bài C — Missing JMX connection

1. Tắt collector ở môi trường test.
2. Quan sát dữ liệu missing.
3. Cấu hình rule target unavailable.
4. Kiểm tra dependent alert không tự clear giả.
5. Bật lại collector và kiểm tra phục hồi.

### Bài D — Hysteresis

1. Tạo chuỗi values dao động quanh 500.
2. So sánh alert chỉ có threshold 500.
3. Thêm enter 500, clear 350.
4. Đếm số transitions.
5. Thêm duration để giảm flapping.

### Bài E — Ngưỡng theo capacity

1. Tạo pool size 20 và pool size 200.
2. So sánh ngưỡng absolute 18.
3. Chuyển sang utilization ratio.
4. Bổ sung waiters/timeouts.
5. Đề xuất warning/critical theo SLO.

### Bài F — Runbook

1. Chọn một cảnh báo critical.
2. Viết owner, scope và impact.
3. Xác định ba bước chẩn đoán đầu tiên.
4. Nêu thao tác an toàn và chống lặp.
5. Định nghĩa recovery condition.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** JMX tự tính trend và gửi alert không?  
**Trả lời:** Không mặc định. Cần collector, history store và alert evaluator hoặc triển khai riêng.

**Câu 2.** Vì sao một ngưỡng >500 tức thời dễ gây nhiễu?  
**Trả lời:** Có thể chỉ là burst ngắn tự hồi phục.

**Câu 3.** Hysteresis là gì?  
**Trả lời:** Dùng ngưỡng enter và clear khác nhau để tránh flapping.

**Câu 4.** Vì sao nên cảnh báo theo rate thay vì tổng FailedTotal?  
**Trả lời:** Counter tích lũy dài hạn có thể luôn vượt mốc; rate phản ánh tốc độ lỗi trong cửa sổ.

**Câu 5.** Missing data có bằng zero không?  
**Trả lời:** Không. Missing là không có phép đo hợp lệ.

**Câu 6.** Trend dương có luôn là critical không?  
**Trả lời:** Không. Cần xem giá trị tuyệt đối, capacity, tốc độ tăng và ảnh hưởng.

**Câu 7.** Notification có đảm bảo replay sau reconnect không?  
**Trả lời:** Không có durable replay mặc định; nên đọc snapshot và dùng monitoring history.

**Câu 8.** Vì sao cần volume tối thiểu cho tỷ lệ lỗi?  
**Trả lời:** Để tránh alert sai khi mẫu số rất nhỏ.

**Câu 9.** Một alert tốt cần những gì ngoài biểu thức?  
**Trả lời:** Owner, severity, context, runbook, routing, temporal logic và recovery condition.

**Câu 10.** Có nên tự động restart khi mọi JMX gauge vượt ngưỡng không?  
**Trả lời:** Không. Auto-remediation cần guardrails, validation, cooldown, audit và kiểm soát rủi ro.

## 33. Ghi nhớ

- Dữ liệu JMX là nguồn quan sát, không phải hệ thống alerting hoàn chỉnh.
- Bắt đầu từ tác động vận hành và câu hỏi cần giải quyết.
- Phân biệt gauge, counter, rate, ratio và timestamp.
- Ngưỡng tuyệt đối hữu ích khi capacity ổn định; ngưỡng tỷ lệ tốt hơn khi quy mô khác nhau.
- Xu hướng giúp phát hiện sự cố sớm, nhưng cần kết hợp giá trị tuyệt đối và quality của dữ liệu.
- Duration, rolling window, hysteresis và cooldown giảm cảnh báo nhiễu.
- Missing data cần policy riêng, không coi là zero.
- JVM metrics như heap/GC cần đặt trong ngữ cảnh workload và hiệu năng.
- Group alerts và gắn owner/runbook rõ ràng.
- Notifications hỗ trợ phát hiện tức thời nhưng không thay thế metric history hoặc event store.
- Mọi auto-remediation phải có quyền, idempotency/guardrails và rollback phù hợp.
- Kiểm thử rule bằng chuỗi dữ liệu bình thường, bất thường, reset, missing và recovery.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`@ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — Platform MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html
- Prometheus Documentation — Alerting Rules: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Prometheus Documentation — Query Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/
