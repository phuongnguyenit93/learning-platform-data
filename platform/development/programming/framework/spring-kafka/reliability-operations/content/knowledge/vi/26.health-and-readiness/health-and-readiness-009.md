# Lag vượt ngưỡng

Consumer group lag tăng là một tín hiệu cho biết consumer đang tụt lại so với dữ liệu đã được ghi vào Kafka. Tuy nhiên, một con số lag lớn không tự động có nghĩa service đã hỏng: topic có thể vừa trải qua một đợt traffic burst, consumer có thể đang chủ động pause để bảo trì, hoặc một retry workflow đang chuyển records sang topic khác. Ngược lại, lag chỉ vài trăm records vẫn có thể rất nghiêm trọng nếu mỗi record là một giao dịch quan trọng và đã chờ vượt SLA.

Trong chương **Health và readiness**, “lag vượt ngưỡng” là một điều kiện vận hành dùng để đánh giá liệu một consumer group còn đủ khả năng xử lý công việc theo mục tiêu của service hay không. Để đưa điều kiện này vào health/readiness một cách đáng tin cậy, cần xác định rõ **đang đo lag nào, ngưỡng thuộc group/topic/partition nào, breach kéo dài bao lâu, dữ liệu metrics có còn mới không, và trạng thái health sẽ tác động tới instance như thế nào**.

Bài học này giải thích cách xây threshold policy, phân biệt lag count với lag age, dùng sustained breach và hysteresis, tích hợp một lag health indicator với Spring Boot Actuator, tách readiness khỏi liveness, giám sát metrics, tránh false positives trong retry/transaction/pause và xây runbook phục hồi.

## 1. Lag vượt ngưỡng có nghĩa gì?

Kafka lưu record theo từng partition với offset tăng dần. Consumer group lưu committed offset cho từng topic-partition. Một phép tính lag thường dùng:

~~~text
committed-offset lag
    = log-end-offset
      - committed-offset
~~~

Ví dụ:

~~~text
Topic: orders.events
Group: orders-worker
Partition: 0

Committed offset = 8.000
Log end offset   = 8.750

Lag = 8.750 - 8.000 = 750
~~~

Trong ví dụ, group còn khoảng cách 750 vị trí offset so với cuối log. Đây là tín hiệu backlog, nhưng chưa đủ để kết luận 750 business events đang chờ: compaction, transaction markers, aborted records, offset gaps và cách exporter lấy end offset có thể ảnh hưởng cách diễn giải.

Một policy “lag vượt ngưỡng” thường gồm nhiều điều kiện:

- Lag vượt ngưỡng theo tổng group hoặc một partition.
- Điều kiện kéo dài đủ lâu, không chỉ một lần scrape.
- Consumer group có backlog thật sự và input đang tiếp tục đến.
- Record age hoặc business freshness vượt ngân sách cho phép.
- Trạng thái pause/maintenance được tính đến.
- Dữ liệu đo lag đủ mới để đưa ra quyết định.

### 1.1. Threshold là chính sách nghiệp vụ

Ngưỡng 1.000 records có thể phù hợp với một pipeline xử lý hàng nghìn records mỗi giây, nhưng rất nghiêm trọng với một pipeline chỉ xử lý vài records mỗi phút.

Ngưỡng phải được chọn dựa trên:

1. Tốc độ producer bình thường và peak.
2. Năng lực consumer đã đo trong điều kiện production-like.
3. SLA về thời gian xử lý event.
4. Kích thước và chi phí xử lý mỗi record.
5. Số partitions và độ lệch tải giữa partitions.
6. Thời gian pause/maintenance được phép.
7. Retention của topic và thời gian tối đa có thể phục hồi backlog.

Không copy một con số threshold từ service khác chỉ vì cùng sử dụng Kafka.

## 2. Xác định loại lag trước khi đặt ngưỡng

Các dashboard có thể hiển thị nhiều đại lượng cùng mang tên “lag”. Cần biết rõ từng đại lượng đo từ vị trí nào.

| Đại lượng | Cách hiểu | Câu hỏi trả lời |
|---|---|---|
| Committed group lag | End offset trừ committed offset | Group đã xác nhận tiến độ tới đâu? |
| Fetch/consumer position lag | End offset trừ vị trí consumer đã fetch | Consumer đã đọc tới đâu? |
| Lag theo LSO | Last stable offset trừ committed offset | Consumer `read_committed` còn cách vùng dữ liệu có thể đọc bao xa? |
| Partition lag | Khoảng cách cho từng topic-partition | Partition nào đang tụt lại? |
| Lag age / oldest record age | Tuổi của dữ liệu cũ nhất còn chờ | Người dùng phải chờ bao lâu? |
| Business completion backlog | Số nghiệp vụ chưa hoàn tất theo state của ứng dụng | Công việc thật sự còn tồn bao nhiêu? |

### 2.1. Committed lag và fetch lag khác nhau

Consumer có thể đã poll một batch records nhưng chưa commit offset:

~~~text
Log end offset        = 1.100
Consumer position     = 1.050
Committed offset      = 1.000

Fetch-position lag    = 50
Committed-offset lag  = 100
~~~

Đây là tình huống bình thường khi listener đang xử lý batch hoặc commit theo batch. Không nên dùng fetch lag và committed lag thay thế nhau trong cùng một threshold policy.

### 2.2. Transaction và last stable offset

Với consumer `isolation.level=read_committed`, consumer không đọc record thuộc transaction đã abort và việc đọc có thể bị giới hạn bởi last stable offset (LSO) khi có transaction chưa kết thúc.

Ví dụ:

~~~text
Log end offset       = 5.500
Last stable offset   = 5.400
Committed offset     = 5.350

Lag theo LEO         = 150
Lag theo LSO         = 50
~~~

Exporter dùng LEO và exporter dùng LSO có thể hiển thị lag khác nhau khi transaction đang mở. Khi đặt ngưỡng, phải ghi rõ nguồn lag và cách tính; nếu không, đội vận hành có thể so sánh những con số không cùng định nghĩa.

### 2.3. Lag âm, offset thiếu hoặc stale series

Group mới có thể chưa có committed offset; partition chưa được assign; exporter có thể scrape end offset và committed offset ở hai thời điểm khác nhau. Không tự coi giá trị thiếu là 0, cũng không diễn giải lag âm như “consumer nhanh hơn broker”.

Policy cần một trạng thái **unknown** khi không đủ dữ liệu để kết luận. Nếu exporter ngừng cập nhật, một số gauge có thể giữ giá trị cũ và tạo cảm giác lag vẫn ổn định.

## 3. Total lag không thay thế partition lag

Giả sử một topic có bốn partitions:

| Partition | Lag |
|---|---:|
| 0 | 20 |
| 1 | 30 |
| 2 | 1.800 |
| 3 | 25 |
| **Total** | **1.875** |

Tổng lag 1.875 có thể chưa vượt ngưỡng warning 2.000, nhưng partition 2 đã tích tụ 1.800 records. Nếu partition này chứa một key nóng hoặc một luồng nghiệp vụ quan trọng, chỉ nhìn total lag sẽ che mất vấn đề.

Nên theo dõi ít nhất:

- **Total lag** của consumer group theo topic.
- **Maximum partition lag**.
- Số partitions có lag tăng liên tục.
- Partition lag growth rate.
- Partition assignment/member hiện tại nếu cần điều tra ownership.

### 3.1. Không cộng max lag của từng consumer để tính total

Một consumer có thể được assign nhiều partitions. Metric `records-lag-max` thường là mức lag lớn nhất mà client quan sát, không phải tổng committed lag của group.

Muốn tính total group lag, lấy committed offsets và end offsets theo từng partition rồi tổng hợp với cùng định nghĩa. Dùng client-level max lag để tìm consumer có partition nóng hoặc fetch chậm.

### 3.2. Consumer count lớn hơn partition count

Trong một consumer group, mỗi partition chỉ được assign cho một consumer tại một thời điểm. Nếu topic có ba partitions nhưng group có sáu consumer instances, không phải cả sáu đều xử lý dữ liệu của topic đó.

Một consumer không có assignment không nhất thiết là lỗi liveness. Health policy nên xem assignment và group state thay vì đánh dấu DOWN chỉ vì một member không có record.

## 4. Lag count và lag age trả lời hai câu hỏi khác nhau

Lag count cho biết khoảng cách theo offset. Lag age cho biết một record đã chờ bao lâu.

Ví dụ:

- Pipeline A có lag 20.000 records nhưng xử lý 10.000 records/s.
- Pipeline B có lag 200 records nhưng chỉ xử lý 1 record/s.

Pipeline B có thể có độ trễ lớn hơn nhiều dù con số lag nhỏ.

Một health policy tốt nên kết hợp:

| Tín hiệu | Dùng khi |
|---|---|
| Total lag | Đo quy mô backlog |
| Max partition lag | Phát hiện partition nóng |
| Lag growth rate | Phân biệt backlog đang tăng hay giảm |
| Oldest unprocessed record age | Bảo vệ freshness/SLA |
| Business completion age | Đo độ trễ tới khi side effect thực sự hoàn tất |
| Consumer success rate | Xác nhận throughput nghiệp vụ |

### 4.1. Kafka record timestamp không luôn là business event time

Kafka timestamp có thể là CreateTime do producer gửi hoặc LogAppendTime do broker gán, tùy cấu hình topic. Payload có thể chứa event time từ hệ thống nguồn, khác với cả hai timestamp trên.

Khi tính lag age, cần xác định timestamp đáng tin cậy. Clock skew giữa producer và broker có thể làm age âm hoặc phóng đại. Nếu cần SLO nghiệp vụ, có thể instrument timestamp lúc tạo event và lúc hoàn tất xử lý trong application state.

### 4.2. Lag thấp nhưng event vẫn cũ

Một event nằm trong outbox upstream 30 phút rồi mới được publish sang Kafka có thể được consumer xử lý ngay. Kafka lag gần 0 nhưng end-to-end latency vẫn 30 phút.

Với pipeline có outbox, retry topics hoặc worker queues, cần đo tuổi dữ liệu ở toàn workflow. Không tuyên bố service healthy chỉ vì lag của main topic bằng 0.

## 5. Threshold nên có warning và critical

Một cách tiếp cận là định nghĩa nhiều mức:

| Mức | Ý nghĩa | Hành động gợi ý |
|---|---|---|
| Normal | Lag nằm trong baseline/SLO | Tiếp tục theo dõi |
| Warning | Backlog tăng hoặc vượt ngưỡng cảnh báo | Tạo cảnh báo, điều tra capacity |
| Critical | Lag/age vượt ngưỡng ảnh hưởng SLO | Đánh dấu readiness không đạt nếu policy yêu cầu, page owner |
| Unknown | Metrics thiếu, stale hoặc không đủ dữ liệu | Cảnh báo observability, không giả định lag = 0 |

Ví dụ minh họa:

~~~text
orders-worker:
  warning total lag  = 2,000 records
  critical total lag = 10,000 records
  critical oldest age = 60 seconds

  warning max partition lag  = 1,000
  critical max partition lag = 5,000
~~~

Những giá trị này chỉ minh họa cấu trúc policy, không phải khuyến nghị cho mọi workload.

### 5.1. Ngưỡng tuyệt đối

Ngưỡng tuyệt đối dễ giải thích và triển khai, ví dụ total lag vượt 10.000 records. Nhưng nó không tự thích nghi với producer rate theo giờ, topic có record size rất khác nhau, workload batch, số partitions và thời gian xử lý theo event type.

Hãy dùng ngưỡng tuyệt đối như một guardrail, kết hợp age và trend.

### 5.2. Ngưỡng theo tỷ lệ hoặc capacity

Có thể xem backlog so với năng lực xử lý dự kiến:

~~~text
backlog_ratio = current_lag / expected_processing_capacity_per_window
~~~

Ví dụ consumer thường xử lý 5.000 records trong 5 phút; lag 10.000 tương đương khoảng hai cửa sổ năng lực. Cách đo này hữu ích hơn một con số tĩnh khi throughput thay đổi.

Tuy nhiên, capacity phải được đo từ business success throughput bền vững, không chỉ từ số records poll được.

## 6. Sustained breach: đừng phản ứng với một lần scrape

Lag có thể tăng ngắn hạn do producer burst, consumer rebalance, rolling deployment, batch commit, garbage collection pause hoặc tạm thời pause để backpressure.

Nếu health indicator chuyển DOWN ngay khi một sample vượt threshold, readiness có thể flapping và làm orchestration liên tục thay đổi trạng thái.

Một policy phổ biến yêu cầu điều kiện vượt ngưỡng liên tục trong một khoảng thời gian:

~~~text
Critical breach:
  total lag > 10,000
  continuously for 2 minutes

or

oldest record age > 60 seconds
  continuously for 30 seconds
~~~

Thời gian cụ thể phải phù hợp SLO và tốc độ scrape. Có thể dùng rolling window hoặc yêu cầu N mẫu liên tiếp; cần xử lý missing samples rõ ràng.

### 6.1. Hysteresis tránh flapping

Dùng hai ngưỡng khác nhau khi vào và thoát trạng thái:

~~~text
Enter WARNING: lag >= 2,000
Clear WARNING: lag <= 1,000

Enter CRITICAL: lag >= 10,000
Clear CRITICAL: lag <= 5,000
~~~

Đây là ví dụ high/low watermarks. Khi lag dao động quanh 2.000, trạng thái warning không bật/tắt liên tục.

### 6.2. Cần xác định điều kiện clear

Không clear incident chỉ vì một sample lag giảm dưới threshold. Có thể yêu cầu:

- Lag dưới clear threshold trong một khoảng ổn định.
- Oldest record age trở lại trong SLA.
- Business success rate bình thường.
- Consumer poll progress và group assignment ổn định.

Readiness có thể hồi phục nhanh hơn hoặc chậm hơn alert tùy chính sách service; hai trạng thái nên được định nghĩa riêng.

## 7. Tính lag growth và thời gian bắt kịp

Mô hình đơn giản theo records:

~~~text
backlog(t + Δt)
  ≈ max(0, backlog(t) + incoming(Δt) - completed(Δt))
~~~

Tốc độ tăng backlog ròng:

~~~text
growth_rate ≈ producer_arrival_rate - consumer_completion_rate
~~~

Nếu producer phát 500 records/s và consumer hoàn tất 400 records/s, backlog có thể tăng khoảng 100 records/s. Trong 5 phút, backlog tăng 30.000 records nếu tốc độ ổn định.

### 7.1. Ước lượng time to catch up

Nếu consumer capacity lớn hơn input rate:

~~~text
time_to_catch_up
  ≈ current_backlog
    / (consumer_capacity - producer_arrival_rate)
~~~

Ví dụ:

- Backlog: 12.000 records.
- Producer rate: 200 records/s.
- Consumer completion capacity: 260 records/s.
- Net drain rate: 60 records/s.

Thời gian bắt kịp ước lượng là 12.000 / 60 = 200 giây.

Nếu consumer capacity nhỏ hơn hoặc bằng producer rate, backlog không thể giảm ổn định. Tăng timeout, restart hoặc hạ threshold không sửa được vấn đề capacity.

### 7.2. Ước lượng có giới hạn

Phép tính trên giả định producer rate và consumer capacity tương đối ổn định, không có hot partition làm nghẽn group, retry/DLT không làm backlog dịch chuyển sang workflow khác, và capacity đo theo business completion tương ứng với cách đếm backlog.

Trong production, hãy dùng forecast như một tín hiệu vận hành, không phải cam kết thời gian chính xác.

## 8. Lấy lag từ đâu?

Có nhiều cách thu thập:

| Nguồn | Dữ liệu | Lưu ý |
|---|---|---|
| Kafka consumer group exporter | Lag theo group/topic/partition | Cần xác nhận định nghĩa offset |
| Kafka AdminClient | Group committed offsets, group state, end offsets qua Admin APIs | Cần quyền và xử lý timeout |
| Kafka client metrics | Fetch lag, consumed rate, fetch behavior | Không nhất thiết là committed group lag |
| JMX exporter | Expose Kafka client/broker metrics | Tên MBean phụ thuộc version |
| Spring/Micrometer instrumentation | Listener processing và application metrics | Thường cần custom business metrics |
| Observability platform | Tổng hợp lag, age, throughput, health | Phải kiểm tra freshness và label cardinality |

### 8.1. AdminClient và committed offsets

Kafka AdminClient có thể truy vấn committed offsets của consumer group, group description/state và end offsets thông qua các API tương ứng. Về mặt khái niệm:

1. Lấy committed offsets cho group.
2. Xác định các topic-partitions cần theo dõi.
3. Lấy end offsets cùng định nghĩa đã chọn.
4. Tính lag theo partition.
5. Tổng hợp total/max và timestamp snapshot.

Việc lấy end offsets và committed offsets không phải một snapshot nguyên tử duy nhất. Producer và consumer có thể tiến trong lúc truy vấn. Vì vậy kết quả có thể dao động nhẹ; threshold policy cần chịu được sai khác đo lường.

### 8.2. Không truy vấn AdminClient trực tiếp trong mỗi health request

Một `/actuator/health` endpoint có thể được gọi thường xuyên bởi kubelet, load balancer và monitoring. Nếu mỗi request lại truy vấn nhiều consumer groups/partitions qua broker:

- Health endpoint có thể chậm.
- Broker nhận thêm load không cần thiết.
- Lỗi Kafka quản trị có thể làm health endpoint timeout.
- Nhiều probes đồng thời có thể tạo query storm.

Nên dùng một **lag sampler** chạy định kỳ với timeout, lưu snapshot gần nhất vào cache thread-safe. HealthIndicator chỉ đọc snapshot và đánh giá policy nhanh.

### 8.3. Metrics stale là một trạng thái riêng

Snapshot lag cũ không thể được coi là lag ổn định. Lưu timestamp của lần thu thập gần nhất:

~~~text
Lag snapshot:
  value = 8,500
  observedAt = 12:00:00
  now = 12:05:00
  maxAge = 30 seconds

Result = STALE / UNKNOWN
~~~

Không trả UP chỉ vì snapshot cũ vẫn nằm dưới threshold. Cũng không mặc định DOWN cho consumer group nếu lỗi chỉ nằm ở metrics exporter; cần phân biệt **consumer health unknown** và **consumer lag critical**.

## 9. Thiết kế LagSnapshot và policy

Một snapshot có thể chứa:

~~~text
groupId
topic
observedAt
totalLag
maxPartitionLag
partitionLagMap
oldestRecordAge
activeMemberCount
assignedPartitionCount
sourceDefinition (committed/LSO/...)
collectionStatus
~~~

Không phải mọi trường đều lấy được từ cùng một API. Chỉ lưu trường có nguồn dữ liệu đáng tin và định nghĩa rõ.

### 9.1. Policy cần có

~~~text
LagPolicy:
  warningTotalLag
  criticalTotalLag
  warningPartitionLag
  criticalPartitionLag
  criticalOldestAge
  sustainedBreachDuration
  clearThreshold
  clearDuration
  maxSnapshotAge
  startupGracePeriod
  maintenancePolicy
~~~

### 9.2. Policy theo group/topic

Một ứng dụng có thể consume nhiều topics:

| Group/topic | Tính chất | Health policy |
|---|---|---|
| `orders-worker / orders.events` | Critical, cần xử lý nhanh | Age + total + partition threshold |
| `audit-worker / audit.events` | Có thể xử lý chậm hơn | Threshold theo retention/SLA |
| `notifications / email.events` | Có thể có traffic burst | Lag trend và oldest age |
| `orders-dlt-review / orders.events.dlt` | Chờ review thủ công | DLT age/ownership, không dùng threshold main pipeline |

Không cộng lag của nhiều consumer groups để tạo một “total application lag” không có ý nghĩa. Một record có thể được đọc bởi nhiều groups độc lập; cộng các group lags có thể đếm cùng dữ liệu nhiều lần.

## 10. Hysteresis và sustained breach trong code

Có thể xây một policy evaluator độc lập với Spring HealthIndicator:

~~~java
public enum LagState {
    NORMAL,
    WARNING,
    CRITICAL,
    UNKNOWN
}

public record LagSnapshot(
        long totalLag,
        long maxPartitionLag,
        Duration oldestRecordAge,
        Instant observedAt) {
}
~~~

Một evaluator cần giữ trạng thái và thời điểm bắt đầu breach để kiểm tra điều kiện kéo dài:

~~~text
on each new snapshot:
  if snapshot missing or stale:
      state = UNKNOWN
  else if critical condition starts:
      record criticalSince
  else if critical condition persists:
      after sustained duration -> CRITICAL
  else if warning condition starts:
      record warningSince
  else if warning condition persists:
      after warning duration -> WARNING
  else if below clear threshold long enough:
      state = NORMAL
~~~

Đây là logic minh họa. Production implementation cần xử lý restart của process, nhiều snapshots cùng timestamp, đồng hồ thay đổi, stale data và đồng thời cập nhật trạng thái từ nhiều threads.

### 10.1. Trạng thái breach không nên chỉ là boolean

Một state hữu ích có thể chứa severity, since timestamp, last observed lag, trigger reason, group/topic/partition liên quan, last successful collection timestamp và last clear timestamp.

Nhờ vậy health endpoint và incident logs giải thích được **vì sao** service đang degraded.

## 11. Tích hợp với Spring Boot Actuator

Spring Boot Actuator cung cấp health infrastructure. Ứng dụng có thể tạo một custom `HealthIndicator` để đưa trạng thái lag policy vào health endpoint.

Ví dụ:

~~~java
@Component("kafkaConsumerLag")
public class KafkaConsumerLagHealthIndicator
        implements HealthIndicator {

    private final LagSnapshotProvider snapshots;
    private final LagPolicyEvaluator evaluator;

    public KafkaConsumerLagHealthIndicator(
            LagSnapshotProvider snapshots,
            LagPolicyEvaluator evaluator) {
        this.snapshots = snapshots;
        this.evaluator = evaluator;
    }

    @Override
    public Health health() {
        LagSnapshot snapshot = snapshots.latest();
        LagEvaluation evaluation = evaluator.evaluate(snapshot);

        if (evaluation.state() == LagState.UNKNOWN) {
            return Health.unknown()
                    .withDetail("reason", evaluation.reason())
                    .build();
        }

        if (evaluation.state() == LagState.CRITICAL) {
            return Health.outOfService()
                    .withDetail("reason", evaluation.reason())
                    .withDetail("totalLag", snapshot.totalLag())
                    .withDetail(
                            "maxPartitionLag",
                            snapshot.maxPartitionLag())
                    .build();
        }

        return Health.up()
                .withDetail("lagState", evaluation.state().name())
                .withDetail("totalLag", snapshot.totalLag())
                .withDetail(
                        "maxPartitionLag",
                        snapshot.maxPartitionLag())
                .build();
    }
}
~~~

`LagSnapshotProvider` và `LagPolicyEvaluator` là abstraction do ứng dụng định nghĩa. Code minh họa sử dụng `Health.unknown()`, `Health.outOfService()` và `Health.up()`; hãy xác nhận API và health status mapping của Spring Boot version thực tế.

### 11.1. HealthIndicator phải nhanh

`health()` nên chỉ đọc snapshot đã được thu thập trước đó. Không thực hiện AdminClient network calls, query database hoặc quét mọi partition đồng bộ trong health request.

Nếu health check chậm, chính probe có thể timeout và khiến orchestration đánh dấu instance unhealthy dù nguyên nhân chỉ là health endpoint bị block.

### 11.2. Warning không nhất thiết phải trả DOWN

Trong ví dụ, WARNING vẫn trả `UP` nhưng có detail `lagState=WARNING`. Có thể thay bằng custom status hoặc health group riêng nếu cần. Quan trọng là policy phải phân biệt:

- Warning: cần điều tra nhưng instance vẫn có thể xử lý.
- Critical: readiness không đạt nếu service không nên nhận thêm traffic/công việc.
- Unknown: không đủ dữ liệu để kết luận.

Không biến mọi warning thành DOWN nếu điều đó tạo ra scale/restart storm.

## 12. Đưa lag health vào readiness group

Với Spring Boot Actuator có hỗ trợ health groups/probes, có thể đưa custom indicator vào readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaConsumerLag
        liveness:
          exclude: kafkaConsumerLag
~~~

Ví dụ cấu hình theo các phiên bản Spring Boot hỗ trợ health probes/groups. Hãy kiểm tra property names và group mặc định của version dự án.

Khi lag indicator trả `OUT_OF_SERVICE`, readiness group có thể đánh dấu instance không sẵn sàng theo status mapping. Điều này chỉ có ý nghĩa nếu orchestrator thực sự gọi readiness probe tương ứng.

### 12.1. Readiness DOWN không tự pause Kafka listener

Readiness thường quyết định pod có nhận traffic qua Kubernetes Service hay không. Nó **không tự dừng Kafka consumer**. Nếu muốn khi critical lag thì ngừng nhận records mới, cần một cơ chế pause/backpressure riêng và phải hiểu rằng pause có thể làm lag tiếp tục tăng.

Với consumer group, việc loại pod khỏi HTTP Service cũng không tự thay đổi Kafka partition assignment.

### 12.2. Lag vượt ngưỡng không phải lúc nào cũng nên làm readiness DOWN

Ví dụ service đang xử lý backlog lớn nhưng vẫn có throughput tốt. Nếu mọi pod cùng chuyển NotReady, hệ thống có thể loại hết consumer khỏi service/orchestration policy, làm capacity giảm và lag tăng thêm.

Trước khi gắn lag vào readiness, trả lời:

- Pod NotReady có làm consumer dừng không?
- Deployment autoscaler có scale dựa trên readiness không?
- Nếu tất cả pods NotReady, hệ thống có tự phục hồi không?
- Lag có thể giảm bằng cách giữ consumers tiếp tục chạy không?

Với nhiều worker services, cách tốt hơn có thể là giữ readiness của process theo khả năng phục vụ, đồng thời page/alert khi consumer lag vượt SLO. Readiness chỉ nên fail khi instance thật sự không nên nhận thêm công việc hoặc không thể thực hiện vai trò của nó.

## 13. Không dùng consumer lag làm liveness probe trực tiếp

**Liveness** quyết định process có nên được restart. Lag là backlog của group, có thể tăng do producer burst hoặc downstream capacity thấp. Restart pod không làm biến mất backlog và có thể gây rebalance.

Không nên:

~~~text
if consumerLag > threshold:
    liveness = DOWN
    restart pod
~~~

Nếu tất cả replicas cùng có lag cao, restart đồng loạt có thể làm consumer group mất ổn định và tăng thời gian xử lý.

### 13.1. Liveness nên phản ánh process có thể tự tiếp tục không

Những tín hiệu phù hợp hơn cho liveness:

- JVM deadlock/unrecoverable internal state.
- Main application process không phản hồi.
- Một critical internal loop không thể tự phục hồi và đã được xác minh.

Consumer thread liveness có thể có health component riêng. Tuy nhiên, một consumer non-responsive do dependency tạm thời không nhất thiết cần restart ngay; timeout/circuit breaker/recovery có thể hiệu quả hơn.

### 13.2. Readiness, liveness và alert không giống nhau

| Cơ chế | Mục tiêu | Lag breach nên tác động thế nào? |
|---|---|---|
| Alert | Báo cho người vận hành | Có thể WARNING/CRITICAL theo SLO |
| Readiness | Quyết định instance có nhận thêm traffic/công việc không | Chỉ fail nếu policy cho thấy instance không sẵn sàng |
| Liveness | Quyết định có cần restart process không | Không fail chỉ vì backlog lớn |
| Autoscaling | Điều chỉnh capacity | Có thể dùng lag trend/age và throughput, có cooldown |
| Backpressure | Điều tiết input/delivery | Pause/resume theo resource state, không chỉ lag đơn lẻ |

## 14. Lag threshold với nhiều consumer instances

Một consumer group có thể chạy trên nhiều pods. Lag là trạng thái group/partition, không thuộc riêng một pod.

~~~text
                    orders-worker group
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
        pod A            pod B            pod C
      partitions 0      partitions 1      partitions 2
      and 3
~~~

Nếu mỗi pod tự query total group lag và đưa nó vào readiness, cùng một breach sẽ khiến tất cả pods đồng thời NotReady. Nếu orchestration hoặc deployment policy loại bỏ chúng, consumer capacity có thể giảm đúng lúc cần tăng.

### 14.1. Health local và health group

Phân biệt:

- **Local health:** consumer thread/container trong pod này có chạy đúng không?
- **Group health:** toàn group có bắt kịp dữ liệu và đáp ứng SLO không?

Lag threshold thường là **group health**. Consumer thread liveness và listener runtime là **local health**.

Không đưa group-level backlog vào local liveness của mọi pod một cách máy móc.

### 14.2. Một central signal có thể phù hợp hơn

Với group lớn, có thể tính group lag tập trung ở monitoring/health service, phát alert hoặc autoscaling signal. Mỗi pod vẫn theo dõi local container state. Điều này tránh việc mọi pod lặp lại cùng query group offsets và đưa ra quyết định trái ngược nhau.

## 15. Health theo startup grace period

Ngay sau khi deploy:

- Consumer có thể chưa hoàn tất assignment.
- Exporter chưa có sample đầu tiên.
- Group offsets chưa được tạo.
- Producer chưa phát dữ liệu.
- Consumer mới có thể chưa có committed offset.

Không coi snapshot thiếu ngay lúc startup là lag = 0 hoặc critical. Policy cần startup grace period:

~~~text
container starts
      |
      v
startup grace period
      |
      +--> lag sample not ready: STARTING / UNKNOWN
      |
      v
valid snapshots available
      |
      v
evaluate warning/critical thresholds
~~~

Grace period phải đủ để startup bình thường, nhưng không dài đến mức che lỗi cấu hình khiến consumer không bao giờ được assign partitions.

### 15.1. Consumer group mới

Group chưa có committed offset có thể được xử lý theo `auto.offset.reset` khi bắt đầu đọc. Lag calculation của exporter có thể hiển thị missing/unknown cho tới khi offset được xác lập.

Đừng mặc định group mới có lag bằng 0. Hãy phân biệt:

- Chưa có offset và chưa có assignment.
- Group bắt đầu từ earliest và còn backlog.
- Group bắt đầu từ latest và chưa có record mới.
- Exporter chưa thu thập được dữ liệu.

## 16. Retry, DLT và lag chuyển chỗ

Khi listener xử lý lỗi:

~~~text
orders.events
     |
     | retry/recover
     v
orders.events-retry
     |
     | hết retry
     v
orders.events-dlt
~~~

Main topic lag có thể giảm khi record được chuyển sang retry topic. Nhưng event vẫn chưa hoàn tất nghiệp vụ.

Nếu chỉ đưa `orders.events` vào health indicator, service có thể báo UP trong khi retry topic backlog tăng rất lớn.

### 16.1. Theo dõi các stages

Với workflow có retry/DLT, health policy nên xác định rõ:

- Main consumer group lag.
- Retry consumer group lag.
- Oldest retry event age.
- DLT count/age và thời gian xử lý thủ công.
- Business event completion age.

Không cộng mọi topic/group lags thành số unique events nếu cùng một event có thể xuất hiện ở nhiều stages.

### 16.2. DLT không phải lúc nào cũng critical backlog

Một DLT có thể được thiết kế để chờ người vận hành review. Nếu DLT không có record, đó là tín hiệu tốt; nếu có record, severity phụ thuộc loại nghiệp vụ và SLA. Một health threshold `DLT lag > 0 => DOWN` thường không phù hợp với quarantine workflow có chủ đích.

## 17. Lag threshold khi consumer đang pause

Spring Kafka pause/resume có thể dùng để bảo vệ downstream khi queue hoặc database quá tải. Khi container paused:

- Producer vẫn ghi vào Kafka.
- Consumer không giao thêm records mới cho listener theo cơ chế pause.
- Lag có thể tăng.
- Đây có thể là trạng thái được điều khiển có chủ đích.

Nếu health indicator đánh dấu DOWN chỉ vì lag tăng trong maintenance, readiness/alerts sẽ phản ánh sai policy.

### 17.1. Đưa pause reason vào evaluation

Snapshot hoặc policy context nên biết:

- Container đang pause hay không.
- Pause reason (maintenance, queue full, dependency unhealthy).
- Pause bắt đầu lúc nào.
- Thời gian pause tối đa được phép.
- Backlog có còn nằm trong retention/freshness budget không.

Pause có chủ đích không có nghĩa bỏ qua mọi ngưỡng. Nếu pause kéo dài vượt maintenance window hoặc oldest record age vượt SLA, vẫn cần alert.

### 17.2. Lag cao sau resume

Sau resume, backlog có thể còn lớn trong khi consumer đang bắt kịp. Không nên chuyển critical ngay chỉ vì snapshot đầu tiên vẫn cao; theo dõi lag growth rate và drain rate.

Nếu lag giảm đều và oldest age đang được xử lý, trạng thái có thể warning thay vì critical tùy SLO. Nếu lag tiếp tục tăng dù consumer đã resume, capacity hoặc downstream vẫn chưa đủ.

## 18. Prometheus và Grafana: ví dụ threshold queries

Tên metric phụ thuộc exporter. Các truy vấn dưới đây chỉ áp dụng nếu metrics endpoint thực sự xuất series có tên và labels tương ứng.

### 18.1. Total lag theo group/topic

Giả sử exporter có metric `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }
)
~~~

### 18.2. Maximum partition lag

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }
)
~~~

### 18.3. Lag growth trong cửa sổ

Lag là gauge, không phải counter. Có thể dùng delta trong một cửa sổ để đánh giá thay đổi:

~~~promql
delta(
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }[5m]
)
~~~

Delta dương cho biết lag cuối cửa sổ cao hơn đầu cửa sổ theo samples hiện có; cần xét rebalance, offset reset, missing samples và exporter restart.

### 18.4. Alert duy trì điều kiện

Ví dụ cấu trúc alert:

~~~yaml
groups:
  - name: kafka-consumer-health
    rules:
      - alert: KafkaConsumerLagCritical
        expr: |
          sum by (consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker"
            }
          ) > 10000
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Kafka consumer lag is above the critical threshold"
          description: "Check partition lag, input rate and processing throughput."
~~~

Tên metric, label và group syntax là ví dụ; xác minh với exporter thực tế trước khi deploy. Ngưỡng 10.000 và thời gian 2 phút chỉ minh họa.

### 18.5. Alert khi metrics stale

Một alert lag threshold không thể đáng tin nếu exporter đã ngừng scrape. Cần alert riêng cho target down, sample timestamp quá cũ, metric series biến mất và AdminClient collection failures.

Không diễn giải “không có metric lag” thành “lag = 0”.

## 19. HealthIndicator đọc snapshot thay vì query Kafka

Một kiến trúc phù hợp:

~~~text
Scheduled lag sampler
        |
        v
Kafka AdminClient / exporter metrics
        |
        v
LagSnapshotProvider (cache)
        |
        +--> lag policy evaluator
        |
        v
HealthIndicator
        |
        v
Actuator readiness group
~~~

Sampler có thể chạy mỗi vài giây hoặc theo chu kỳ phù hợp với volume và số partitions. Health endpoint chỉ đọc snapshot mới nhất và đánh giá trạng thái trong thời gian rất ngắn.

### 19.1. Tách collection khỏi evaluation

Hai trách nhiệm khác nhau:

- **Collection:** gọi AdminClient/metrics source, tính lag, gắn timestamp, xử lý timeout.
- **Evaluation:** áp threshold, sustained breach, hysteresis, startup grace và maintenance policy.

Điều này giúp test threshold logic mà không cần broker và test collector riêng với Kafka integration.

### 19.2. Snapshot phải nhất quán theo một lần thu thập

Không cập nhật từng partition vào shared map rải rác rồi để health check đọc một nửa snapshot cũ, một nửa snapshot mới. Tạo một immutable snapshot hoàn chỉnh và atomically replace reference sau khi collection thành công.

Nếu collection chỉ thành công một phần, đánh dấu snapshot partial/unknown hoặc lưu lỗi theo policy; không giả định những partitions thiếu có lag 0.

## 20. Ví dụ LagSnapshotProvider và HealthIndicator

Một interface do ứng dụng định nghĩa:

~~~java
public interface LagSnapshotProvider {
    LagSnapshot latest();
}
~~~

Snapshot:

~~~java
public record LagSnapshot(
        String groupId,
        String topic,
        long totalLag,
        long maxPartitionLag,
        Duration oldestRecordAge,
        Instant observedAt,
        boolean complete) {
}
~~~

Health indicator có thể kiểm tra freshness và critical breach:

~~~java
@Component("kafkaConsumerLag")
public class KafkaLagHealthIndicator implements HealthIndicator {

    private final LagSnapshotProvider snapshots;
    private final Duration maxSnapshotAge = Duration.ofSeconds(30);
    private final long criticalLag = 10_000;
    private final Duration criticalAge = Duration.ofSeconds(60);

    public KafkaLagHealthIndicator(LagSnapshotProvider snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public Health health() {
        LagSnapshot snapshot = snapshots.latest();

        if (snapshot == null || !snapshot.complete()) {
            return Health.unknown()
                    .withDetail("reason", "lag_snapshot_unavailable")
                    .build();
        }

        Duration snapshotAge =
                Duration.between(snapshot.observedAt(), Instant.now());

        if (snapshotAge.isNegative()
                || snapshotAge.compareTo(maxSnapshotAge) > 0) {
            return Health.unknown()
                    .withDetail("reason", "lag_snapshot_stale")
                    .withDetail("snapshotAge", snapshotAge.toString())
                    .build();
        }

        boolean critical =
                snapshot.totalLag() >= criticalLag
                || snapshot.oldestRecordAge()
                        .compareTo(criticalAge) >= 0;

        if (critical) {
            return Health.outOfService()
                    .withDetail("group", snapshot.groupId())
                    .withDetail("topic", snapshot.topic())
                    .withDetail("totalLag", snapshot.totalLag())
                    .withDetail(
                            "maxPartitionLag",
                            snapshot.maxPartitionLag())
                    .withDetail(
                            "oldestRecordAge",
                            snapshot.oldestRecordAge().toString())
                    .build();
        }

        return Health.up()
                .withDetail("totalLag", snapshot.totalLag())
                .withDetail(
                        "maxPartitionLag",
                        snapshot.maxPartitionLag())
                .build();
    }
}
~~~

Đây là ví dụ cấu trúc, chưa bao gồm sustained breach/hysteresis và dùng threshold minh họa. Trong production, các giá trị nên nằm trong cấu hình có validation; `Instant.now()` có thể được trừu tượng hóa bằng `Clock` để test ổn định. Cần xử lý trường hợp timestamp tương lai do clock skew.

### 20.1. Không dùng code mẫu này như threshold policy hoàn chỉnh

Một health check chỉ so sánh snapshot tức thời với ngưỡng có thể flapping. Để production-ready, cần thêm:

- Thời gian breach liên tục.
- Ngưỡng clear thấp hơn ngưỡng enter.
- Startup grace.
- Maintenance/pause reason.
- Snapshot stale/partial.
- Partition-specific threshold.
- Phân biệt warning và critical.

## 21. Tùy chỉnh status mapping

Spring Boot Health có những status phổ biến như `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. Khi health group được dùng cho readiness, cần kiểm tra status nào được map thành HTTP 200/503 theo cấu hình/version.

Nếu tạo custom status như `DEGRADED`, cần khai báo status order và mapping phù hợp. Nếu không, Actuator có thể xử lý custom status không như mong đợi.

Một lựa chọn đơn giản:

- `UP`: trong giới hạn.
- `OUT_OF_SERVICE`: critical, instance không nên nhận thêm traffic theo readiness policy.
- `UNKNOWN`: không đủ dữ liệu.

Nhưng UNKNOWN không tự động có cùng ý nghĩa với DOWN trong mọi probe. Hãy xác nhận orchestration behavior bằng integration test hoặc kiểm tra endpoint thực tế.

## 22. Autoscaling theo lag khác health readiness

Lag có thể là tín hiệu scale consumer group:

- Lag tăng liên tục.
- Producer rate lớn hơn consumer success rate.
- Có partitions chưa đạt capacity.
- Downstream còn headroom để nhận thêm load.

Nhưng scale không phải luôn có ích:

- Consumer count đã bằng hoặc vượt partition count.
- Database connection pool đã đầy.
- Downstream đang rate-limit.
- Hot partition giới hạn parallelism.
- Consumer tasks bị block cùng một dependency.

### 22.1. Scale theo lag và throughput

Một policy autoscaling tốt hơn có thể kết hợp:

~~~text
scale_out when:
  lag growth is sustained
  AND oldest record age is rising
  AND downstream has capacity
  AND additional partitions can be assigned
~~~

Scale in khi backlog ổn định dưới clear threshold, consumers không có task in-flight quan trọng và hệ thống đủ dư địa cho traffic burst.

### 22.2. Cooldown và rebalance cost

Mỗi lần scale có thể gây rebalance, làm gián đoạn processing và tăng lag ngắn hạn. Dùng cooldown, stabilization window và giới hạn scale step để tránh oscillation.

Đừng dùng readiness DOWN làm tín hiệu autoscaler duy nhất nếu tất cả pods cùng bị đánh dấu không sẵn sàng do group lag.

## 23. Lag vượt ngưỡng trong lúc deploy

Rolling deployment có thể làm consumer instances cũ stop và nhường partitions, consumer mới start và chờ assignment, rebalance tạm thời dừng một phần processing, lag tăng ngắn hạn và metric exporters thay đổi series theo instance.

Health policy nên nhận biết deployment/rollout state hoặc dùng sustained window đủ hợp lý để không page mỗi lần rebalance ngắn.

Tuy nhiên, nếu lag tiếp tục tăng sau khi group ổn định, cần điều tra regression về startup, concurrency, deserializer, database hoặc processing time.

### 23.1. Không bỏ qua mọi lag trong rollout

Một deployment kéo dài có thể làm backlog vượt freshness SLO. Startup grace không phải lý do bỏ qua vô hạn. Hãy đặt maximum rollout duration và maximum allowable lag age trong maintenance policy.

## 24. Lag threshold và retention

Kafka retention giới hạn thời gian hoặc dung lượng record được giữ. Nếu backlog tồn tại quá lâu, một phần dữ liệu có thể bị xóa trước khi consumer xử lý.

Khi đánh giá critical lag, cân nhắc:

- Retention time/size của topic.
- Oldest record age so với retention.
- Tốc độ drain dự kiến.
- Khả năng tăng capacity.
- Replay từ archive/object storage nếu có.

Một lag 100.000 records có thể chấp nhận nếu consumer có thể bắt kịp trong 2 phút và retention dài; một lag 5.000 records có thể critical nếu oldest record chỉ còn ít phút trước khi bị xóa.

### 24.1. Lag không phải bằng chứng dữ liệu còn tồn tại

Nếu log start offset đã vượt committed offset, consumer có thể không còn đọc được một số records cũ. Cần phát hiện retention gap và không báo “chỉ còn backlog 0” nếu group offset đã bị reset hoặc dữ liệu đã hết hạn.

Đừng tự động reset group offsets để làm health status xanh. Việc bỏ qua records cần quyết định nghiệp vụ rõ ràng và audit.

## 25. Observability: dashboard và alert

Dashboard lag health nên có:

| Panel | Mục đích |
|---|---|
| Total committed lag by group/topic | Tổng backlog |
| Max lag by partition | Phát hiện hot partition |
| Lag growth rate | Biết backlog đang tăng hay giảm |
| Oldest record age | Đo freshness/SLA |
| Producer arrival rate | Input pressure |
| Business success throughput | Capacity xử lý thực tế |
| Consumer active members/assignments | Group membership |
| Retry topic lag / DLT count | Backlog ở recovery path |
| Pause state and duration | Backpressure/maintenance |
| Snapshot age / collection errors | Độ tin cậy của metric |
| Readiness status | Tác động tới orchestration |

### 25.1. Alert theo điều kiện kết hợp

Một alert critical có thể cần lag vượt critical threshold, điều kiện kéo dài ít nhất một khoảng, oldest age vượt freshness SLO hoặc lag growth dương liên tục, không phải planned maintenance được phê duyệt và snapshot còn mới.

Đừng tạo alert chỉ từ một số liệu lag tức thời.

### 25.2. Alert metrics stale riêng

Nếu lag collector ngừng hoạt động, alert threshold có thể im lặng dù backlog đang tăng. Có alert riêng cho snapshot age quá lớn, AdminClient collection failures, exporter scrape failure và missing group/topic series.

Observability failure cần được phát hiện như một vấn đề riêng.

## 26. Runbook: lag vượt warning threshold

1. Xác định đúng consumer group và topic.
2. Kiểm tra total lag, max partition lag và xu hướng trong cửa sổ thời gian.
3. Xác nhận snapshot lag còn mới.
4. So sánh producer arrival rate với business completion throughput.
5. Kiểm tra oldest record age và freshness SLO.
6. Xem consumer group state, active members và partition assignment.
7. Kiểm tra pause/maintenance state.
8. Kiểm tra retry topic/DLT nếu main topic lag đang giảm bất thường.
9. Kiểm tra DB/HTTP latency và consumer errors.
10. Theo dõi drain rate; nâng severity nếu backlog tiếp tục tăng hoặc age vượt SLA.

Warning có thể chỉ là traffic burst bình thường. Không scale/restart trước khi xác định bottleneck.

## 27. Runbook: lag vượt critical threshold

1. Xác nhận threshold breach bằng nhiều samples hoặc metric source độc lập.
2. Xác định partition nào đóng góp nhiều nhất vào backlog.
3. Kiểm tra consumer group có active members và assignments không.
4. Kiểm tra records consumed rate và business success rate.
5. Kiểm tra listener exception/retry/DLT/transaction abort.
6. Kiểm tra consumer thread liveness và thread dumps nếu poll progress dừng.
7. Kiểm tra downstream capacity, connection pools và timeouts.
8. Ước lượng thời gian bắt kịp theo net drain rate.
9. Chọn hành động: khôi phục dependency, tăng capacity, giảm input hoặc pause theo policy.
10. Theo dõi lag age và completion throughput cho tới khi dưới clear threshold.

Không reset offsets để làm dashboard xanh và không restart toàn bộ group nếu chưa xác định nguyên nhân.

## 28. Runbook: lag cao nhưng đang giảm

1. Kiểm tra lag growth rate có âm ổn định không.
2. Xác nhận oldest record age đang giảm hoặc không tiếp tục tăng.
3. Kiểm tra business success rate.
4. Xác nhận consumer group không rebalance liên tục.
5. Kiểm tra estimated catch-up time có nằm trong recovery objective không.
6. Giữ warning/incident mở cho tới khi clear condition được thỏa.
7. Tránh scale in khi backlog chưa phục hồi.

Lag cao nhưng đang drain có thể là quá trình recovery bình thường. Severity nên phản ánh cả mức tồn đọng lẫn xu hướng.

## 29. Runbook: readiness DOWN vì lag

1. Xác định indicator nào làm readiness group không đạt.
2. Kiểm tra health detail: group, topic, total lag, max partition lag, oldest age.
3. Xác nhận lag snapshot không stale.
4. Xác nhận readiness DOWN có thực sự cần thiết cho service này.
5. Kiểm tra việc NotReady có làm giảm consumer capacity hoặc ảnh hưởng orchestration không.
6. Nếu consumer vẫn có thể xử lý backlog, cân nhắc policy readiness/alert phù hợp hơn.
7. Nếu instance thực sự không thể nhận công việc, khắc phục root cause và xác nhận clear threshold trước khi readiness UP.

Readiness là quyết định về khả năng nhận công việc, không phải một bản sao của dashboard lag.

## 30. Runbook: lag collector hoặc health indicator trả UNKNOWN

1. Kiểm tra thời điểm snapshot cuối cùng.
2. Kiểm tra AdminClient/exporter availability.
3. Kiểm tra timeout, ACL và quyền đọc group offsets.
4. Kiểm tra group/topic có tồn tại và có committed offsets chưa.
5. Kiểm tra partial partition results.
6. Xem clock skew hoặc timestamp tương lai.
7. Xác nhận health endpoint đọc đúng cache và không gọi broker đồng bộ.
8. Khôi phục metrics collection.
9. Đối chiếu bằng Kafka CLI/Admin tools nếu cần.

UNKNOWN không đồng nghĩa lag bằng 0. Trong critical service, observability unavailable có thể cần alert riêng nhưng không nhất thiết phải restart consumer process.

## 31. Runbook: lag tập trung ở một partition

1. Lấy top partition lag.
2. So sánh input rate theo partition.
3. Xác định consumer member được assign partition đó.
4. Kiểm tra hot keys và key distribution.
5. Đo processing time/error rate của các events liên quan.
6. Kiểm tra có poison pill/blocking retry ở đầu partition không.
7. Xác định ordering requirements trước khi thay đổi partition strategy.
8. Nếu tăng partitions, đánh giá key remapping và ordering cho events tương lai.
9. Theo dõi max lag partition sau thay đổi.

Tăng replicas không giúp một hot partition nếu downstream hoặc ordering chỉ cho phép xử lý tuần tự.

## 32. Kiểm thử lag threshold và readiness

Không cần chỉ test phép so sánh số học. Cần kiểm thử cả dữ liệu thiếu, snapshot stale, hysteresis và hành vi health endpoint.

### 32.1. Unit test policy evaluator

Các trường hợp:

1. Lag dưới warning: NORMAL.
2. Lag vượt warning một sample: chưa chuyển trạng thái nếu cần sustained breach.
3. Lag vượt warning đủ thời gian: WARNING.
4. Lag vượt critical đủ thời gian: CRITICAL.
5. Lag giảm dưới clear threshold một sample: vẫn giữ state nếu clear duration chưa đủ.
6. Lag giảm ổn định dưới clear threshold: NORMAL.
7. Snapshot stale/partial: UNKNOWN.
8. Oldest age vượt SLO dù total lag thấp: CRITICAL nếu policy quy định.
9. Partition lag vượt threshold dù total chưa vượt: state theo partition policy.
10. Pause/maintenance hợp lệ: state theo policy maintenance.

### 32.2. Test HealthIndicator

1. Inject snapshot NORMAL và xác nhận `UP`.
2. Inject snapshot WARNING và xác nhận health details phản ánh warning theo policy.
3. Inject CRITICAL và xác nhận status tương ứng.
4. Inject UNKNOWN/stale và xác nhận không bị diễn giải thành lag 0.
5. Xác nhận health method không gọi network/AdminClient.
6. Đo thời gian phản hồi của indicator với snapshot cache.

### 32.3. Test readiness group

1. Bật Actuator health probes.
2. Đưa `kafkaConsumerLag` vào readiness group theo cấu hình.
3. Xác nhận status UP/OUT_OF_SERVICE/UNKNOWN được map như mong đợi.
4. Xác nhận liveness group không bị lag indicator làm DOWN.
5. Kiểm tra endpoint path mà orchestrator thực sự gọi.

### 32.4. Integration test collector

1. Tạo topic và consumer group test.
2. Gửi records để tạo backlog có kiểm soát.
3. Thu committed offsets và end offsets.
4. Xác nhận lag snapshot theo partition.
5. Consume records và xác nhận lag giảm.
6. Mô phỏng AdminClient timeout hoặc missing offsets.
7. Xác nhận snapshot được đánh dấu stale/unknown, không thành 0.

### 32.5. Test burst và recovery

1. Gửi burst lớn hơn consumer capacity.
2. Xác nhận warning/critical theo sustained window.
3. Tăng capacity hoặc giảm producer input.
4. Xác nhận net drain rate dương.
5. Xác nhận state chỉ clear sau hysteresis duration.

## 33. Những sai lầm thường gặp

**Dùng một threshold cố định cho mọi topics.** Workload, SLO và record cost khác nhau.

**Chỉ nhìn total lag.** Một partition nóng có thể bị che trong tổng.

**Đánh dấu DOWN ngay khi một sample vượt ngưỡng.** Rebalance/batch commit/burst ngắn gây flapping.

**Không có clear threshold.** Health status bật/tắt liên tục quanh cùng một ranh giới.

**Coi lag thấp là business complete.** Backlog có thể nằm ở retry topics hoặc worker queue.

**Dùng lag làm liveness probe.** Restart không xóa backlog và có thể làm group rebalance.

**Đưa group lag vào readiness mọi pod mà không xét tác động.** Tất cả replicas có thể cùng NotReady và giảm capacity.

**Gọi AdminClient trong mỗi health request.** Health endpoint có thể chậm và tạo query storm.

**Coi metric thiếu là lag 0.** Observability failure bị che.

**Bỏ qua startup grace và group mới.** Offset/assignment có thể chưa sẵn sàng.

**Coi DLT lag bằng 0 là mục tiêu bắt buộc.** DLT có thể là hàng chờ review có chủ đích.

**Không xem retry lag.** Main topic có thể sạch nhưng event vẫn chưa hoàn tất.

**Scale consumer mà không kiểm tra downstream.** Có thể làm database/HTTP quá tải hơn.

**Reset offsets để health xanh.** Có thể bỏ qua dữ liệu chưa xử lý.

## 34. Checklist triển khai

### Định nghĩa lag và ngưỡng

- [ ] Đã ghi rõ committed lag, fetch lag hay LSO lag.
- [ ] Có total lag và max partition lag.
- [ ] Có lag growth rate và oldest record age.
- [ ] Threshold dựa trên arrival rate, capacity và SLO.
- [ ] Có warning/critical và enter/clear thresholds.
- [ ] Có sustained breach duration và hysteresis.
- [ ] Có startup grace và maintenance policy.

### Thu thập dữ liệu

- [ ] Lag source có timeout và quyền đọc offsets phù hợp.
- [ ] Snapshot có observed timestamp và trạng thái complete.
- [ ] Missing/stale data trở thành UNKNOWN, không phải 0.
- [ ] Health endpoint đọc cache, không query broker đồng bộ.
- [ ] Total lag được tổng hợp theo group/topic/partition nhất quán.

### Health và orchestration

- [ ] HealthIndicator chỉ đánh giá policy đã định nghĩa.
- [ ] Readiness group chỉ include lag khi có lý do nghiệp vụ.
- [ ] Liveness không fail chỉ vì lag cao.
- [ ] Đã kiểm tra status mapping của Spring Boot.
- [ ] Đã đánh giá tác động NotReady lên consumer capacity.
- [ ] Có alert riêng cho metrics collector stale.

### Recovery và kiểm thử

- [ ] Có dashboard lag, age, input rate và business success rate.
- [ ] Có retry/DLT và pause state trong quan sát.
- [ ] Có runbook warning, critical, stale metrics và hot partition.
- [ ] Test sustained breach/hysteresis/clear.
- [ ] Test readiness và liveness độc lập.
- [ ] Test AdminClient/exporter failure.
- [ ] Không reset offsets ngoài quy trình replay được phê duyệt.

## Kết luận

**Lag vượt ngưỡng** là một tín hiệu về khả năng consumer group đáp ứng tốc độ và độ trễ xử lý dữ liệu. Để biến nó thành health/readiness policy có ích, cần định nghĩa rõ loại lag, tính theo group và partition, kết hợp total/max lag với lag age và tốc độ tăng backlog. Ngưỡng phải dựa trên SLO và capacity thực tế; sustained breach, hysteresis, startup grace và freshness của snapshot giúp giảm cảnh báo sai.

Trong Spring Boot, có thể đưa policy vào một custom `HealthIndicator`, nhưng indicator nên đọc snapshot đã được thu thập định kỳ thay vì truy vấn Kafka trong mỗi health request. Readiness chỉ nên fail khi instance thực sự không nên nhận thêm công việc; lag cao không phải lý do tự động restart process hoặc làm mọi pod NotReady. Cuối cùng, phải theo dõi cả retry/DLT, pause, transaction và business completion, vì backlog có thể dịch chuyển khỏi main topic trong khi nghiệp vụ vẫn chưa hoàn tất. **Một threshold tốt dẫn tới hành động phục hồi đúng; một con số lag đơn lẻ không thể tự quyết định sức khỏe của cả pipeline.**
