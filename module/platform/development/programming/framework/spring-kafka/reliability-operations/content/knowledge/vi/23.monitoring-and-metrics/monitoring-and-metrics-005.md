# Consumer lag và tốc độ tiêu thụ

Trong một hệ thống Spring Kafka, việc consumer vẫn đang chạy chưa đủ để kết luận pipeline khỏe mạnh. Một listener có thể liên tục xử lý record nhưng không theo kịp tốc độ producer, làm **consumer lag** tăng dần. Ngược lại, lag bằng 0 cũng không bảo đảm mọi side effect nghiệp vụ đã hoàn tất: record có thể được chuyển sang retry topic, xử lý bất đồng bộ, hoặc offset bị commit trước khi công việc thực sự bền vững.

Hai đại lượng cần quan sát cùng nhau là **consumer lag** — lượng vị trí dữ liệu mà consumer group còn chưa bắt kịp — và **tốc độ tiêu thụ/xử lý** — số record consumer nhận hoặc hoàn tất trong một đơn vị thời gian. Kết hợp chúng với độ tuổi record, lỗi, retry, tốc độ publish và trạng thái offset commit mới cho phép đánh giá hệ thống đang bắt kịp, tích tụ backlog hay bị kẹt.

Bài học này trình bày cách hiểu offset và lag theo partition, sự khác nhau giữa records consumed và records processed, các phép tính backlog, metrics Kafka client và Spring Kafka, công cụ lệnh kiểm tra consumer group, thiết kế dashboard/alert, ảnh hưởng của retry và transaction, cách capacity planning và các runbook vận hành.

## 1. Consumer lag là gì?

Kafka chia mỗi topic thành các partition, mỗi partition là một log có thứ tự offset tăng dần. Một **consumer group** lưu committed offset cho từng topic-partition mà group tiêu thụ. Committed offset thông thường biểu thị **vị trí kế tiếp** mà group sẽ đọc khi tiếp tục từ trạng thái đã xác nhận, không phải offset cuối cùng vừa xử lý trừ một.

Một cách tính thường dùng khi đối chiếu group offsets và end offsets:

~~~text
lag(group, topic, partition)
    = logEndOffset(topic, partition)
      - committedOffset(group, topic, partition)
~~~

Ví dụ:

~~~text
Partition orders.events-0

Các vị trí log:
... 4997 | 4998 | 4999 | 5000 | 5001 | 5002 | 5003 | ...

Group committed offset = 5000
Log end offset         = 5004  (vị trí kế tiếp sau record cuối)

Lag theo offset = 5004 - 5000 = 4
~~~

Kết quả này phản ánh khoảng cách giữa hai vị trí offset. Trong Kafka thông thường nó gần với số record còn phải tiến qua, nhưng **không luôn đúng bằng số event nghiệp vụ chưa xử lý** vì log có thể có transaction markers, aborted records, các khoảng trống do compaction và những khác biệt giữa semantics của công cụ đo.

### 1.1. Lag là đại lượng theo group và partition

Lag không phải thuộc tính duy nhất của topic. Cùng một topic, hai consumer groups có thể đang ở những vị trí hoàn toàn khác nhau:

| Consumer group | Committed offset | End offset | Lag |
|---|---:|---:|---:|
| `billing-group` | 8.900 | 10.000 | 1.100 |
| `analytics-group` | 9.950 | 10.000 | 50 |
| `audit-group` | 10.000 | 10.000 | 0 |

Muốn xác định một service đang chậm, phải lọc **đúng consumer group**, topic và partition. Không dùng lag của một group để kết luận tình trạng của group khác.

### 1.2. Topic có nhiều partitions

Giả sử `orders.events` có ba partitions:

| Partition | Committed offset | Log end offset | Lag |
|---|---:|---:|---:|
| 0 | 13.000 | 13.100 | 100 |
| 1 | 6.200 | 7.200 | 1.000 |
| 2 | 4.500 | 4.520 | 20 |
| **Tổng** | | | **1.120** |

**Total group lag** của tập partitions là tổng các lag, ở đây bằng 1.120 vị trí offset. Nhưng **maximum partition lag** là 1.000 tại partition 1; đây có thể là partition nóng cần điều tra. Một dashboard chỉ hiển thị số tổng dễ che mất sự mất cân bằng giữa partitions.

## 2. Các vị trí offset thường bị nhầm

Khi vận hành cần phân biệt tối thiểu:

| Khái niệm | Ý nghĩa |
|---|---|
| Log start offset | Vị trí đầu tiên còn được Kafka giữ lại theo retention/compaction |
| Log end offset (LEO) | Vị trí kế tiếp sau dữ liệu cuối đã ghi vào log theo cách Kafka xác định |
| Consumer position | Vị trí kế tiếp KafkaConsumer dự kiến fetch khi tiếp tục |
| Committed offset | Vị trí đã được consumer group xác nhận bền vững |
| Last stable offset (LSO) | Giới hạn đọc an toàn với consumer `read_committed` khi có transaction đang mở |

Chúng không nhất thiết bằng nhau.

### 2.1. Position có thể tiến trước xử lý thành công

Kafka `poll()` lấy về một tập records và cập nhật vị trí fetch của consumer. Nếu listener nhận batch rồi xử lý chậm, **consumer position có thể đã tiến** trong khi committed offset còn ở vị trí cũ.

~~~text
Log end offset:  1.100
Consumer poll() đã nhận đến offset 1.049
Consumer position: 1.050
Group committed offset: 1.000

Fetch-position lag  ≈ 1.100 - 1.050 = 50
Committed-offset lag   = 1.100 - 1.000 = 100
~~~

Hai đại lượng cùng hợp lệ nhưng trả lời hai câu hỏi khác nhau:

- **Fetch lag:** consumer đã fetch tới đâu?
- **Committed lag:** group đã xác nhận bền vững tới đâu?

Nếu ứng dụng xử lý bất đồng bộ hoặc commit theo batch, khác biệt có thể lớn. Đừng xem `records-lag-max` của Kafka client và lag do exporter tính từ group committed offsets là luôn bằng nhau.

### 2.2. Committed offset không chứng minh side effect đã xong

Nếu listener enqueue một task bất đồng bộ rồi trả về thành công, container có thể commit offset trước khi worker hoàn tất. Dashboard khi đó có thể hiển thị lag giảm rất đẹp, nhưng database vẫn chưa cập nhật.

Do đó, cần metric **business processing completed rate** hoặc số task pending nếu có async workflow. Một số Kafka consumer có thể đọc nhanh hơn khả năng xử lý thật, làm lag ở Kafka thấp nhưng backlog dịch chuyển sang queue nội bộ.

### 2.3. Retention và dữ liệu đã biến mất

Nếu consumer group tụt quá xa và Kafka retention xóa một số record trước khi group tiêu thụ, committed offset có thể đứng sau log start offset. Khi đó một phép tính lag đơn giản không nói được **bao nhiêu event đã mất khả năng đọc**.

Kiểm tra cả log start offset, committed offset, retention và chính sách `auto.offset.reset`. Không đặt lại group offset sang latest chỉ để lag về 0 nếu nghiệp vụ chưa phê duyệt việc bỏ qua dữ liệu.

## 3. Lag khi sử dụng Kafka transactions

Consumer dùng `isolation.level=read_committed` không đọc các record thuộc transaction đã abort; việc đọc còn chịu giới hạn bởi **last stable offset (LSO)** nếu có transaction đang mở.

Vì vậy, tùy hệ thống exporter và cách lấy end offset, lag có thể được đo với mốc:

- Log end offset / high watermark, gần bức tranh dữ liệu broker có.
- Last stable offset đối với read-committed visibility.

Hai cách có thể tạo số lag khác nhau khi có transaction mở lâu.

~~~text
LEO = 5.500
LSO = 5.400  (transaction đang mở)
Committed offset = 5.350

Theo LEO: 5.500 - 5.350 = 150
Theo LSO: 5.400 - 5.350 = 50
~~~

Không có phép đo nào tự động “sai” nếu định nghĩa rõ. Khi so sánh dashboards của hai exporters, phải biết chúng dùng **end-offset reference** nào.

### 3.1. Open transaction có thể làm lag có vẻ không giảm

Một transaction mở lâu có thể ngăn consumer `read_committed` đọc record nằm phía sau LSO, dù network, thread và consumer group vẫn hoạt động.

Khi nghi ngờ, kiểm tra:

1. Các transactional producer có transaction quá dài không?
2. Producer có commit/abort lỗi không?
3. Downstream đang dùng `read_committed` hay `read_uncommitted`?
4. Lag metric dùng LEO hay LSO?
5. Consumer có xử lý record sẵn có đến LSO không?

Không đổi ngay sang `read_uncommitted` để “giảm lag” vì consumer có thể đọc output từ transaction đã abort.

## 4. Tốc độ tiêu thụ gồm những tốc độ nào?

Trong một Kafka pipeline, có ít nhất bốn tốc độ khác nhau:

| Tốc độ | Đơn vị thường dùng | Điều nó thực sự đo |
|---|---|---|
| Producer arrival rate | records/s, bytes/s | Records được ghi vào Kafka từ upstream |
| Consumer fetched/consumed rate | records/s, bytes/s | Records Kafka consumer đọc được qua poll/fetch |
| Listener invocation rate | calls/s | Số lần hàm listener được gọi |
| Business success throughput | events/s | Số event hoàn tất xử lý nghiệp vụ theo định nghĩa ứng dụng |

Một listener có thể nhận 1.000 records/s nhưng chỉ xử lý nghiệp vụ thành công 700 records/s; phần còn lại có thể lỗi, chuyển retry topic hoặc được enqueue.

### 4.1. records-consumed-rate của Kafka client

Kafka consumer có metrics như `records-consumed-rate`, `bytes-consumed-rate`, `records-lag-max` và các fetch metrics, tùy Kafka client version. Chúng cho biết hoạt động ở tầng consumer, nhưng không nhất thiết phản ánh số lần **database commit thành công** hay **business event hoàn tất**.

Đừng đặt tên metric tùy chỉnh `business_success_rate` cho Kafka client records-consumed-rate. Hai ngữ nghĩa khác nhau và cần hiển thị ở hai series riêng.

### 4.2. Listener invocation rate khác record count trong batch

Với record listener, một lời gọi thường tương ứng một record được đưa vào adapter. Với batch listener, một lời gọi có thể chứa hàng trăm records:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "batchFactory")
public void consume(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Nếu method được gọi 10 lần/s với batch size trung bình 200, invocation rate là 10 calls/s nhưng record delivery rate có thể là khoảng 2.000 records/s. Không tính throughput records chỉ bằng số method calls của batch listener.

### 4.3. Error và retry làm tăng attempt rate

Một event có thể được listener xử lý nhiều lần khi xảy ra retry. Nếu đo số lần gọi listener, metric có thể tăng dù số unique business events hoàn tất không tăng.

Để đánh giá thực tế, có thể đo riêng:

- Processing attempts count.
- Business successes count.
- Business permanent failures count.
- Retry/DLT rate.
- Số unique event IDs hoàn tất nếu hệ thống có store phù hợp.

Không dùng event ID làm metric tag vì số lượng giá trị quá lớn; nếu cần deduplication hãy dùng database/inbox hoặc workflow state.

## 5. Quan hệ giữa input, throughput và lag

Một mô hình đơn giản:

~~~text
L(t + Δt) ≈ max(0, L(t) + A(Δt) - C(Δt))

L = backlog theo đơn vị record/offset tương ứng
A = lượng dữ liệu mới đến
C = lượng dữ liệu consumer hoàn tất/commit tương ứng
~~~

Khi tính theo records/s trong một cửa sổ thời gian:

~~~text
Net backlog growth rate ≈ producer arrival rate
                          - effective consumer completion rate
~~~

Giả sử:

- Producer phát 500 records/s.
- Consumer hoàn tất và commit hiệu quả 400 records/s.

Trong điều kiện tốc độ ổn định, backlog có thể tăng khoảng 100 records/s. Sau 10 phút, lượng tồn đọng tăng gần 60.000 records. Đây là ước lượng: số liệu thực có thể chịu ảnh hưởng batch commit, transaction, compaction, filtering, retry và sự thay đổi của traffic.

### 5.1. Tốc độ tiêu thụ cao chưa chắc tốt

Nếu producer đưa vào 2.000 records/s và consumer xử lý 1.500 records/s, throughput 1.500 records/s nghe có vẻ lớn nhưng lag **vẫn tăng**.

Ngược lại, nếu producer chỉ đưa vào 100 records/s và consumer xử lý 150 records/s, backlog cũ có thể đang giảm.

Vì vậy, không đánh giá consumer chỉ bằng một con số records/s; phải đặt cạnh **upstream rate** và **lag trend**.

### 5.2. Lag giảm chưa chắc business đã hoàn tất

Nếu lỗi được publish sang retry topic, offset topic chính có thể commit và lag ở topic chính giảm. Nhưng event chưa hoàn tất nghiệp vụ, chỉ chuyển sang hàng đợi khác. Tương tự, DLT có thể chứa những event cần điều tra.

Với workflow có retry topics/outbox/worker queue, cần tổng hợp trạng thái toàn đường xử lý chứ không chỉ nhìn lag của main topic.

## 6. Tính thời gian bắt kịp backlog

Khi consumer có năng lực xử lý hiệu quả cao hơn tốc độ producer, có thể ước lượng thời gian tiêu hết backlog:

~~~text
Time to catch up ≈ Current backlog
                   / (Consumer capacity - Producer arrival rate)

Điều kiện: Consumer capacity > Producer arrival rate.
~~~

Ví dụ:

- Backlog hiện tại: 10.000 records.
- Producer tiếp tục gửi 200 records/s.
- Consumer xử lý hiệu quả 250 records/s.
- Năng lực giảm backlog ròng: 50 records/s.

Khi đó, thời gian bắt kịp ước lượng:

~~~text
10.000 / (250 - 200) = 200 giây
~~~

Khoảng 3 phút 20 giây là ước lượng khi input rate và throughput đủ ổn định. Trong production, tốc độ thường thay đổi theo giờ, kích thước record, partition distribution và dependency health.

### 6.1. Nếu năng lực bằng hoặc thấp hơn input rate

Nếu:

~~~text
Consumer capacity <= Producer arrival rate
~~~

backlog **không thể giảm ổn định** trong mô hình đơn giản. Tăng timeout hoặc restart consumer không chữa được vấn đề capacity. Cần cải thiện xử lý, giảm lượng công việc, điều chỉnh partition/concurrency hoặc mở rộng nguồn lực phù hợp.

### 6.2. Không dùng tổng throughput để che một partition nóng

Giả sử mỗi partition có arrival và completion rate:

| Partition | Incoming | Completed | Thay đổi backlog |
|---|---:|---:|---:|
| 0 | 80/s | 100/s | Giảm 20/s |
| 1 | 200/s | 140/s | **Tăng 60/s** |
| 2 | 20/s | 50/s | Giảm 30/s |

Tổng backlog có thể chỉ tăng ròng 10/s, nhưng partition 1 vẫn tăng 60/s. Nếu event cần thứ tự theo key và partition 1 bị hot key, chỉ thêm consumer trong cùng group không giúp một partition được xử lý đồng thời bởi nhiều consumers.

Cần kiểm tra key distribution, partition count, processing cost theo key và stateful ordering contract.

## 7. Lag theo số record và lag theo thời gian

Một backlog 10.000 records có thể là:

- Khoảng 10 giây dữ liệu ở pipeline xử lý 1.000 records/s.
- Khoảng 3 giờ dữ liệu ở pipeline xử lý dưới 1 record/s.

Số lượng record không trực tiếp thể hiện độ trễ nghiệp vụ. Vì vậy nên đo thêm:

- **Oldest unprocessed record age:** tuổi event lâu nhất còn đang chờ.
- **End-to-end processing latency:** thời gian từ lúc sự kiện xuất hiện đến khi business side effect hoàn tất.
- **Event-time delay:** khác biệt giữa thời gian sự kiện xảy ra ở nguồn và thời gian xử lý, nếu có timestamp nghiệp vụ đáng tin.
- **Time to first success after incident:** thời gian phục hồi khi có sự cố.

### 7.1. Kafka timestamp không luôn là business event time

Kafka record timestamp có thể là create time do producer cung cấp hoặc log append time do broker xác định, tùy topic configuration. Business event timestamp trong payload có thể còn khác vì event được tạo trước khi gửi Kafka.

Khi tính end-to-end latency, hãy ghi rõ dùng timestamp nào. Không dùng thời gian của máy producer không đồng bộ clock làm nguồn sự thật mà không kiểm tra clock skew.

### 7.2. Consumer group lag bằng 0 nhưng event vẫn cũ

Một record đến Kafka muộn sau khi bị giữ ở upstream outbox 30 phút có thể được consumer xử lý ngay, khiến Kafka lag gần 0. Tuy nhiên độ trễ nghiệp vụ tính từ thời điểm tạo event vẫn là 30 phút.

Do đó, cần phối hợp Kafka lag với upstream outbox age và business event age nếu SLO yêu cầu dữ liệu “fresh”.

## 8. Kiểm tra lag bằng Kafka CLI

Kafka cung cấp công cụ `kafka-consumer-groups.sh` để xem trạng thái consumer groups. Ví dụ:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-group
~~~

Trong Windows, dùng script tương ứng với bản Kafka cài đặt hoặc chạy từ môi trường shell có Kafka CLI. Tên folder và đường dẫn có thể khác tùy gói phân phối.

Kết quả minh họa:

~~~text
GROUP         TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
billing-group orders.events  0          13000           13100           100  consumer-a
billing-group orders.events  1          6200            7200           1000  consumer-b
billing-group orders.events  2          4500            4520             20  consumer-c
~~~

Các số trên là ví dụ, không phải dữ liệu của cluster thực tế.

### 8.1. Đọc đúng các cột

- `GROUP`: consumer group ID.
- `TOPIC` và `PARTITION`: log cụ thể.
- `CURRENT-OFFSET`: committed offset mà group đang lưu.
- `LOG-END-OFFSET`: end offset do công cụ lấy tại thời điểm đo.
- `LAG`: khoảng cách được công cụ tính từ end offset và group offset.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID` (nếu có): member/instance đang được assign.

Nếu `CURRENT-OFFSET` hoặc consumer ID hiển thị `-`, đừng diễn giải như số 0. Có thể group chưa có committed offset, không có member active hoặc partition chưa được assign theo cách công cụ trình bày. Cần xem group state và offset reset policy.

### 8.2. Kiểm tra group state

Trong các phiên bản Kafka CLI hỗ trợ:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-group \
  --state
~~~

Group có thể đang Stable, PreparingRebalance, CompletingRebalance hoặc không có member, tùy phiên bản group protocol. Không kết luận chỉ từ lag rằng group có consumer sống; nên xem membership/assignments và log của service.

### 8.3. Cần nhiều mẫu theo thời gian

Một lệnh CLI chụp tại một thời điểm chỉ cho **lag hiện tại**. Để biết backlog đang tăng hay giảm, cần nhiều mẫu có timestamp và độ dài interval rõ. Với production, tốt hơn sử dụng exporter/metrics system thay vì chạy lệnh CLI liên tục với tần suất rất cao.

### 8.4. Không reset offsets để làm dashboard đẹp

Các chức năng thay đổi group offsets có thể làm bỏ qua record hoặc gây replay rất lớn. Nếu lag cao, điều tra nguyên nhân và capacity trước. Việc reset offsets cần runbook, xác nhận dữ liệu cần xử lý và phê duyệt phù hợp.

## 9. Kafka client metrics liên quan

Kafka consumer Java client xuất nhiều metrics qua JMX và metrics APIs. Tên MBean hoặc field cụ thể có thể khác theo phiên bản Kafka client, nhưng những nhóm metrics sau thường rất hữu ích.

| Metric thường gặp | Tầng | Diễn giải |
|---|---|---|
| `records-consumed-rate` | Kafka consumer fetch manager | Tốc độ records consumer nhận |
| `bytes-consumed-rate` | Consumer fetch manager | Throughput bytes |
| `records-lag-max` | Consumer fetch manager | Độ lệch fetch lag cao nhất consumer quan sát theo partition |
| `records-lag` hoặc metrics per-partition | Consumer fetch manager | Thông tin lag theo partition trong phạm vi client |
| `fetch-rate` | Consumer fetch manager | Tần suất fetch requests |
| `fetch-latency-avg` / `fetch-latency-max` | Consumer fetch manager | Độ trễ fetch |
| `poll-idle-ratio-avg` | Consumer metrics ở các phiên bản hỗ trợ | Tỷ lệ thời gian poll thread không xử lý giữa polls |
| `commit-rate` và commit latency | Consumer coordinator | Hoạt động và độ trễ offset commits |
| Rebalance-related metrics | Consumer coordinator | Tần suất/thời gian group rebalances |

### 9.1. Client lag và group committed lag khác nhau

Metric `records-lag-max` của Kafka client liên quan vị trí fetch/consumer, trong khi Kafka consumer group lag từ exporter thường tính dựa trên committed group offsets. Đặc biệt với batch/manual ack/transactions, chúng không nhất thiết đồng nhất.

Nên đặt tên panel khác nhau, ví dụ:

- “**Fetch lag max per consumer**”.
- “**Committed offset lag by group/partition**”.

Không gộp hai metric vào cùng series có nhãn “lag” mà không ghi định nghĩa.

### 9.2. Đọc số liệu khi nhiều consumers

Một group có nhiều consumers, mỗi consumer có `client.id` riêng và chỉ được assign một tập partitions. Nếu cộng mọi `records-lag-max`, kết quả không tương đương tổng lag group.

Muốn tổng backlog, cần dữ liệu committed offsets theo partition. Muốn phát hiện consumer nào đang bị kẹt fetch, dùng client lag max và client ID/assigned partitions.

## 10. Metrics của Spring Kafka listener

Kafka client metrics chưa đủ để xác định listener có xử lý business thành công không. Spring Kafka có hỗ trợ Micrometer metrics/observation cho listener containers ở các phiên bản phù hợp, và ứng dụng có thể thêm custom metrics.

Những tín hiệu nên có:

1. Listener invocation duration.
2. Listener processing attempt count.
3. Business success count.
4. Business failure count phân loại theo nhóm exception ổn định.
5. Retry count và recovery/DLT rate.
6. Số record đang in-flight hoặc đang chờ trong queue nội bộ.
7. Thời gian commit database hoặc downstream dependency.

### 10.1. Không đồng nhất listener invocation với success

Ví dụ:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing-group")
public void consume(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Số lần method được gọi bao gồm cả lần retry. Một method trả thành công có thể là xử lý mới hoặc deduplicate record đã xử lý. Vì vậy định nghĩa “success” nên được thống nhất:

- Success = listener không ném exception.
- Success = database transaction commit.
- Success = unique business event hoàn tất lần đầu.

Mỗi loại metric dùng cho câu hỏi khác nhau. Trong dashboard reliability, nên có **tốc độ xử lý thực sự bền vững** theo hợp đồng nghiệp vụ, không chỉ invocation.

## 11. Ví dụ instrument business success/failure bằng Micrometer

Ví dụ dùng `MeterRegistry` để phân biệt số event hoàn tất và số lần xử lý lỗi:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;
    private final Counter successes;
    private final Counter failures;
    private final Timer processingTimer;

    public OrdersListener(
            OrderService orderService,
            MeterRegistry meterRegistry) {
        this.orderService = orderService;

        this.successes = Counter.builder(
                "app.kafka.orders.processing.success")
                .description("Successfully processed Kafka orders")
                .register(meterRegistry);

        this.failures = Counter.builder(
                "app.kafka.orders.processing.failure")
                .description("Failed Kafka order processing attempts")
                .register(meterRegistry);

        this.processingTimer = Timer.builder(
                "app.kafka.orders.processing.duration")
                .description("Order listener processing duration")
                .register(meterRegistry);
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "billing-group")
    public void consume(OrderEvent event) {
        long started = System.nanoTime();

        try {
            orderService.processIdempotently(event);
            successes.increment();
        }
        catch (RuntimeException ex) {
            failures.increment();
            throw ex; // Giữ exception cho Spring Kafka error handler.
        }
        finally {
            processingTimer.record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Đoạn code giả định `OrderService`, Micrometer và các imports đã được cấu hình. Counter `successes` ở đây đếm **listener invocations hoàn tất bình thường**, không tự deduplicate unique event IDs. Nếu `processIdempotently` trả thành công vì record đã xử lý từ trước, counter vẫn tăng. Muốn thống kê unique completed events, cần API nghiệp vụ trả kết quả phù hợp hoặc lưu event state trong database.

### 11.1. Đừng nuốt lỗi chỉ để metric failure tăng

Nếu listener catch exception rồi trả về bình thường, Spring Kafka có thể commit/ack record theo policy dù nghiệp vụ chưa hoàn tất. Đo failure không được phá error-handling semantics. Ghi metric rồi **rethrow** exception khi chưa có một recovery bền vững.

### 11.2. Đo batch listener chính xác

Nếu listener nhận một `List<ConsumerRecord<K,V>>`, counter cần tăng theo **số records đã xử lý thành công**, không tăng 1 theo batch trừ khi metric được đặt tên là batch count. Khi batch xử lý thất bại giữa chừng, phải xác định số thành công thực tế và commit semantics trước khi tăng success count.

## 12. Commit rate có thể thấp dù consumer khỏe

Offset commits phụ thuộc `AckMode`, batch boundaries, transactions và cơ chế manual ack. Trong một số cấu hình, listener xử lý hàng trăm records nhưng chỉ commit một lần ở cuối batch.

Ví dụ:

~~~text
Poll trả 500 records.
Listener xử lý đủ 500 records.
Container commit offset sau batch.

Business throughput: 500 records được xử lý.
Commit count: 1 lần.
~~~

Không lấy `commit-rate × 1 record` làm throughput.

### 12.1. Committed lag có dạng răng cưa

Trong các ứng dụng commit theo batch:

~~~text
Lag
 ^
 |         /|         /|
 |        / |        / |
 |       /  |       /  |
 |______/   |______/   |____
 +--------------------------> time
           commit     commit
~~~

Giữa các commits, producer tiếp tục ghi record khiến committed lag tăng; khi batch commit, lag giảm mạnh. Đừng page chỉ vì một spike rất ngắn nếu đó là nhịp bình thường của ack policy.

Tuy nhiên, nếu khoảng cách giữa commits dài bất thường hoặc offset đứng yên trong khi processing success không tăng, cần điều tra listener/downstream.

### 12.2. Manual ack và asyncAcks

Với manual acknowledgment, ứng dụng chịu trách nhiệm ack đúng thời điểm. Với những chế độ ack bất đồng bộ được Spring Kafka hỗ trợ, container có thể giữ records hoặc pause delivery khi còn ack gaps chưa được hoàn tất.

Tình huống thường gặp:

- Kafka client records consumed tăng do poll.
- Business tasks đang in-flight.
- Committed offset đứng yên vì có một ack còn thiếu.
- Group lag tăng dù một số tasks đã hoàn tất.

Cần dashboard in-flight count, oldest in-flight age và ack gaps nếu ứng dụng dùng mô hình này.

## 13. Retry, DLT và những lag “ẩn”

Spring Kafka hỗ trợ blocking retry và non-blocking retry topics. Hai cơ chế tạo ra đường đi backlog khác nhau.

### 13.1. Blocking retry

Khi error handler giữ record để retry với backoff, consumer có thể chậm tiến trên partition. Committed lag tăng nếu upstream vẫn publish. Đồng thời listener processing attempts có thể tăng mạnh nhưng business success rate bằng 0.

Quan sát:

- Exception classes.
- Retry attempt count.
- Backoff duration.
- Consumer group lag theo partition.
- Record age và DLT recovery.

### 13.2. Non-blocking retry

Khi record lỗi được publish sang retry topic:

~~~text
orders.events (main)
      |
      | xử lý lỗi
      v
orders.events-retry-... (delayed)
      |
      | hết retry
      v
orders.events-dlt
~~~

Main topic offset có thể được xác nhận sau khi record được chuyển sang retry topic, vì vậy **main topic lag có thể về 0 trong khi sự kiện vẫn chưa hoàn tất**.

Để biết hệ thống còn bao nhiêu công việc:

1. Theo dõi lag của các retry consumer groups.
2. Theo dõi số record trên retry topics và thời điểm đủ điều kiện xử lý.
3. Theo dõi DLT publish rate và số case chưa giải quyết.
4. Theo dõi business event completion age nếu có.

Không cộng bừa tất cả group lags trên nhiều topics để tuyên bố chính xác số unique events đang chờ: một event có thể xuất hiện qua nhiều bước, có replay hoặc duplicate.

### 13.3. DLT lag không bằng dữ liệu mất

DLT thường chứa record đã hết retry cần xử lý riêng. Nếu DLT consumer tắt theo quy trình review thủ công, DLT lag có thể tăng có chủ đích. Điều quan trọng là có owner, retention, SLA điều tra và replay, không nhất thiết phải kéo DLT lag về 0 bằng mọi giá.

## 14. Pause và backpressure ảnh hưởng lag

Spring Kafka có `MessageListenerContainer.pause()` và `resume()` để điều khiển delivery khi downstream quá tải. Khi container paused, nó vẫn có thể poll để duy trì group membership nhưng không giao thêm records mới theo cơ chế pause của container.

Trong khoảng pause:

- Producer vẫn có thể ghi dữ liệu mới.
- Committed lag thường tăng.
- Consumer records consumed rate có thể thấp hoặc bằng 0.
- Downstream queue có thời gian thoát tải.

Sau resume, backlog có thể giảm nhưng chỉ khi năng lực xử lý ròng vượt tốc độ arrival.

### 14.1. Đừng page khi planned maintenance

Lag tăng khi paused có chủ đích là hệ quả dự kiến. Dashboard nên hiển thị pause state và reason. Alert có thể đổi từ “lag đang tăng” sang “maintenance vượt thời gian cho phép” để tránh báo sai, nhưng không được mất khả năng quan sát backlog tiến gần giới hạn retention.

### 14.2. Resume đồng loạt có thể tạo burst

Nếu nhiều pods cùng resume sau một sự cố downstream, việc tiêu thụ backlog có thể tạo connection storm và retry storm mới.

Cân nhắc:

- Staggered resume.
- Giới hạn concurrency, queue capacity.
- Rate limiter hoặc adaptive backpressure.
- Theo dõi DB pool, HTTP 429/503, processing latency.
- Hysteresis high/low watermarks.

Resume là nút bật lại delivery, không phải bộ rate limiter tự động.

## 15. Rebalance làm thay đổi hình dạng metric

Khi scale out, scale in, deploy hoặc lỗi consumer group, Kafka có thể rebalance partition assignments.

Tác động:

- Client ID/instance đang báo lag của một partition có thể đổi.
- `records-consumed-rate` của consumer cũ về 0 sau khi mất assignment.
- Consumer mới cần thời gian khởi động và nhận partition.
- Committed lag có thể tăng trong khoảng ngừng xử lý.
- Một số record chưa commit có thể được giao lại.

### 15.1. Không cộng metrics của consumer cũ và mới tùy tiện

Khi rolling deploy, exporters có thể giữ stale time series trong một khoảng thời gian. Nếu cộng lag per-client của consumer cũ và mới, dashboard có thể đếm trùng cùng partition.

Đối với **consumer group lag**, ưu tiên một nguồn đo theo committed offsets của group/partition có định danh ổn định. Dùng client-specific metrics để phân tích local behavior và assignment.

### 15.2. Concurrency không vượt giới hạn partition

Trong một consumer group, mỗi partition chỉ được assign cho một consumer tại một thời điểm. Nếu topic có 4 partitions, nâng tổng active consumers từ 4 lên 12 không làm một partition được chia cho 3 consumers.

Nếu lag tập trung ở một partition, phải xử lý key skew hoặc tăng partitions theo thiết kế ordering thích hợp. Chỉ tăng concurrency có thể tạo consumers không có partition assignment.

## 16. Sự khác nhau giữa records/s và bytes/s

Hai workload cùng 1.000 records/s có thể tiêu tốn tài nguyên rất khác:

- Record trung bình 500 bytes: khoảng 500 KB/s payload.
- Record trung bình 100 KB: khoảng 100 MB/s payload.

Do đó throughput records/s phải đi kèm bytes/s, CPU, memory, network và downstream cost.

### 16.1. Một record có thể tốn CPU hơn record khác

Ví dụ một `OrderEvent` chỉ cập nhật một row database, trong khi `InvoiceEvent` có thể phải đối soát hàng trăm lines. Hai event cùng được tính là 1 record nhưng processing time khác đáng kể.

Nên theo dõi duration histogram theo **event class thuộc tập hữu hạn** nếu hợp đồng có event type; tránh đưa event id hoặc order id vào metric tags.

### 16.2. Batch size và hiệu suất

Batch processing có thể tăng throughput nhờ giảm số transaction/round trips, nhưng cũng có thể làm:

- Thời gian một poll xử lý kéo dài.
- Commit delay lớn.
- Poison-pill ảnh hưởng cả batch.
- Memory pressure tăng.
- Khó phân biệt record hoàn tất và record thất bại.

Tối ưu batch cần đi cùng kiểm tra correctness và latency, không chỉ records/s.

## 17. Dung lượng tiêu thụ và capacity planning

Để xử lý lag lâu dài, cần xác định bottleneck chính:

| Bottleneck | Biểu hiện thường gặp | Hướng xử lý |
|---|---|---|
| CPU parse/decompress | CPU cao, processing latency tăng | Tối ưu codec, scale partition/consumers nếu có ích |
| Database pool | Chờ connection, p95 latency tăng | Tối ưu SQL/transaction, capacity pool có kiểm soát |
| HTTP downstream | Timeout/429/503 tăng | Backoff, circuit breaker, giảm concurrency, cache |
| Single hot partition | Một partition lag tăng mạnh | Phân phối key, xem lại partitioning/ordering |
| Consumer fetch/network | Fetch latency cao, bytes rate thấp | Kiểm tra broker/network/client config |
| Blocking retry | Exception rate cao, committed offset đứng | Phân loại exception, DLT, backoff |
| Large batches | Commit dạng răng cưa, latency cao | Giảm batch, tune processing |
| GC/memory | Pause dài, throughput dao động | Heap profiling, bounded queues, allocation |

### 17.1. Scale consumer group đúng cách

Muốn tăng throughput bằng cách thêm consumers:

1. Xác nhận topic có đủ partitions.
2. Xác nhận workload có thể xử lý song song theo partition.
3. Xác nhận bottleneck nằm ở consumer chứ không phải shared downstream.
4. Tính tổng concurrency của các pods.
5. Test rebalance/rolling-deploy.
6. Đo effective business completion rate sau scale.

Nếu database đã hết connections, tăng consumers có thể làm throughput giảm thêm.

### 17.2. Scale partition và ordering

Tăng số partition có thể cho phép nhiều consumer xử lý song song, nhưng có ảnh hưởng:

- Mappings key → partition có thể thay đổi.
- Các event cùng key trong tương lai có thể đi tới partition mới.
- Khó bảo toàn ordering xuyên thay đổi partition count nếu không thiết kế.
- Số partition lớn hơn làm tăng chi phí quản lý broker.

Không tăng partitions chỉ để làm số lag trung bình nhỏ; cần đánh giá hợp đồng thứ tự và khối lượng thực tế.

## 18. Thiết kế dashboard tối thiểu

Một dashboard giúp xử lý sự cố nên trả lời được: **backlog ở đâu, tăng nhanh đến mức nào, tại sao tăng, và khi nào có thể bắt kịp?**

### 18.1. Nhóm trạng thái tổng quan

- Total committed lag của consumer group.
- Max partition lag.
- Number of partitions with increasing lag.
- Producer arrival rate và consumer success rate.
- Oldest unprocessed event age.
- Count của active group members và assigned partitions.
- Consumer group state/rebalance.

### 18.2. Nhóm hiệu năng

- Records consumed/s và bytes consumed/s.
- Listener successful records/s.
- Listener processing duration p50/p95/p99.
- Database query/transaction latency.
- HTTP downstream error rate.
- CPU, memory và GC pauses.

### 18.3. Nhóm reliability

- Error/retry/DLT rate.
- Last successful processing timestamp.
- Commit failure rate.
- Transaction abort/producer fencing nếu dùng Kafka transactions.
- Pause/resume state và backpressure reason.
- Worker queue depth nếu có async processing.

### 18.4. Phân tầng theo partition

Đặt bảng hoặc heatmap cho các partition lag cao nhất thay vì chỉ hiển thị total lag. Với consumer groups lớn, có thể ưu tiên top N partitions theo lag và theo lag growth rate.

## 19. Prometheus/Grafana: hiểu schema trước khi viết query

Tên metric phụ thuộc exporter (Kafka exporter, JMX exporter, Micrometer, OpenTelemetry collector...), nên các ví dụ PromQL dưới đây **chỉ áp dụng nếu exporter thực sự xuất đúng tên và labels**. Đừng copy trực tiếp vào dashboard production mà không kiểm tra metrics endpoint.

### 19.1. Total lag theo group và topic

Ví dụ nếu exporter có `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{consumergroup="billing-group"}
)
~~~

### 19.2. Partition lag lớn nhất

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{consumergroup="billing-group"}
)
~~~

### 19.3. Tốc độ business success

Giả sử ứng dụng xuất counter `app_kafka_orders_processing_success_total` từ Micrometer/Prometheus:

~~~promql
sum(rate(app_kafka_orders_processing_success_total[5m]))
~~~

Nếu metric có labels service/listener, nên lọc phù hợp để không cộng nhầm các pipeline khác nhau.

### 19.4. Tốc độ tăng lag

Với metric lag dạng gauge, có thể so chênh lệch trong một khoảng thời gian. Ví dụ:

~~~promql
delta(
  kafka_consumergroup_lag{
    consumergroup="billing-group",
    topic="orders.events"
  }[5m]
)
~~~

`delta` trên gauge cho biết chênh lệch trong cửa sổ 5 phút, không phải counter rate. Trước khi diễn giải, cần nhóm đúng partition và tính đến rebalance, reset offset hoặc metric samples thiếu. Nếu muốn tăng lag mỗi giây, chia mức thay đổi cho thời gian tương ứng hoặc dùng phương pháp phù hợp với time series của hệ thống.

### 19.5. Những sai lầm khi dùng query

- Dùng `rate()` trên lag gauge như thể lag là counter.
- Cộng lag per-client metric có assignment trùng sau rebalance.
- Quên filter consumer group.
- Trộn main topic và retry topic mà gọi là số unique business events.
- Dùng một sample tức thời để kết luận tăng lag kéo dài.
- Áp alert bằng tuyệt đối 1.000 records cho mọi topic dù traffic khác nhau.

## 20. Thiết kế alert: trend, duration và SLO

Không có một ngưỡng consumer lag tuyệt đối phù hợp cho mọi ứng dụng. Một số alert hữu ích:

| Alert | Điều kiện tham khảo | Ý nghĩa |
|---|---|---|
| Sustained growing lag | Lag tăng liên tục trong một cửa sổ đủ dài | Capacity thấp hơn input rate hoặc consumer bị lỗi |
| Lag age exceeds SLO | Oldest event age vượt ngân sách | Dữ liệu đến muộn với nghiệp vụ |
| No progress | Committed offset không tiến, input đang có | Consumer stop, retry, block, commit issue |
| Hot partition | Max partition lag vượt baseline | Skew hoặc xử lý chậm theo key |
| Processing throughput drop | Success rate giảm mạnh so với baseline | Dependency/CPU/error regression |
| Retry/DLT spike | Error/recovery rate tăng | Lỗi dữ liệu hoặc downstream |
| Consumer group unstable | Rebalance/active member churn cao | Partition reassignment làm gián đoạn |
| Backpressure duration | Container paused quá lâu | Dependency chưa phục hồi |

### 20.1. Đừng page khi topic im lặng hợp lệ

Một topic giao dịch thưa dữ liệu có thể không nhận record nhiều giờ. Lag 0 và throughput 0 là bình thường nếu producer không có event. Alert “consumer throughput = 0” chỉ hợp lý khi có **expected input** hoặc backlog đang chờ.

### 20.2. Tách warning và critical

Ví dụ:

- Warning: lag tăng 15 phút nhưng business freshness chưa vượt SLO.
- Critical: oldest unprocessed event age vượt SLA, hoặc committed offset đứng yên trong khi producer liên tục phát record quan trọng.

Các con số phải điều chỉnh theo service; chỉ dùng ví dụ để thể hiện nguyên tắc kết hợp số lượng, thời gian và tác động.

### 20.3. Tránh alert flapping

Commit theo batch và các đợt traffic có thể làm lag tăng rồi giảm ngắn hạn. Sử dụng evaluation window, thời gian duy trì điều kiện và hysteresis. Không cần page cho một spike ngắn của lag nếu pipeline bắt kịp bình thường.

## 21. Runbook: lag tăng dù records-consumed-rate cao

1. Xác định consumer group/topic/partition đang tăng lag.
2. So sánh incoming records/s với consumed records/s.
3. So sánh consumed records/s với **business success rate**.
4. Kiểm tra record processing duration, error/retry rate.
5. Kiểm tra commit frequency và ack mode.
6. Kiểm tra backlog đang chuyển vào worker queue hay retry topics.
7. Xem partition key skew và hot partitions.
8. Kiểm tra database/HTTP dependency saturation.
9. Nếu bottleneck là consumer và partitions đủ, cân nhắc tăng concurrency/replicas.
10. Theo dõi max lag, total lag và oldest age sau thay đổi.

**Không kết luận consumer đủ khỏe vì số records consumed/s lớn.** Nó vẫn có thể chậm hơn tốc độ upstream.

## 22. Runbook: lag cao nhưng records-consumed-rate gần 0

1. Kiểm tra group có active members không.
2. Xác nhận listener container running hay stopped.
3. Kiểm tra consumer group rebalance hoặc partition assignment.
4. Kiểm tra pause/backpressure state.
5. Kiểm tra logs broker/authentication/authorization/network.
6. Kiểm tra deserialization/conversion errors trước listener.
7. Kiểm tra blocking retry hoặc error handler đang giữ record.
8. Kiểm tra thread dump để tìm listener bị block hoặc deadlock.
9. Kiểm tra `max.poll.interval.ms` và `NonResponsiveConsumerEvent`.
10. Khắc phục nguyên nhân, rồi xác nhận committed offset tiến và lag giảm.

Không reset offsets sang latest để biến lag thành 0. Điều đó có thể bỏ qua dữ liệu chưa xử lý.

## 23. Runbook: lag thấp nhưng nghiệp vụ hoàn tất chậm

Đây là tình huống nguy hiểm vì dashboard Kafka nhìn có vẻ tốt.

1. Xác định listener có enqueue công việc async rồi trả thành công không.
2. Kiểm tra task queue depth và oldest in-flight task age.
3. Kiểm tra database transaction commit thành công hay chưa.
4. Kiểm tra retry topic/DLT backlog.
5. Kiểm tra upstream outbox age và business event timestamp.
6. Xác định commit offset có xảy ra trước side effect bền vững không.
7. Bổ sung business completion metric và đối soát event IDs.
8. Sửa acknowledgment policy nếu Kafka offset đang bị xác nhận quá sớm.

Lag Kafka thấp không bù được việc dữ liệu bị kẹt ở một queue nội bộ chưa có durability.

## 24. Runbook: lag tăng ở đúng một partition

1. Xác định topic-partition có lag tăng nhanh nhất.
2. So sánh incoming rate giữa các partitions.
3. Kiểm tra key distribution và hot key.
4. Kiểm tra consumer được assign partition đó đang chạy ở pod nào.
5. Đo processing duration và exception rate chỉ cho partition liên quan.
6. Xác nhận có một record lỗi chặn tiến độ không.
7. Kiểm tra downstream workload của key/tenant tương ứng.
8. Cân nhắc thay đổi partition strategy nếu hợp đồng ordering cho phép.
9. Không chỉ tăng consumer replicas vượt partition count.

Nếu cùng aggregate cần xử lý tuần tự, phá ordering để tăng throughput có thể gây lỗi dữ liệu nghiêm trọng hơn lag.

## 25. Runbook: committed lag không giảm sau resume

1. Xác nhận container đã thực sự resume, không chỉ nhận request.
2. Kiểm tra còn partition-level pause requests không.
3. Kiểm tra framework giữ pause vì ack gaps/error handling không.
4. Kiểm tra consumer group assignment và state.
5. Xác định listener processing đang chạy hay bị block.
6. Kiểm tra producer arrival rate có đang cao hơn processing capacity không.
7. Đối chiếu committed lag với fetch lag và success rate.
8. Nếu commit theo batch, chờ một chu kỳ commit phù hợp trước khi kết luận.

Resume không bảo đảm backlog giảm nếu downstream vẫn chậm hoặc lỗi liên tục.

## 26. Runbook: lag spike sau deploy/rebalance

1. Kiểm tra mốc deploy và logs consumer group rebalance.
2. Xác nhận số active consumers trước/sau rollout.
3. Kiểm tra partitions đã được assign đầy đủ chưa.
4. Xác định producer rate có tăng cùng thời điểm không.
5. Kiểm tra startup time, consumer start failures và executor threads.
6. Kiểm tra schema/deserializer compatibility với records mới.
7. Đo lại success throughput sau rollout.
8. Nếu spike ngắn rồi giảm, có thể là hệ quả bình thường của rebalance.
9. Nếu spike kéo dài, rollback hoặc sửa regression theo quy trình.

Đừng chẩn đoán chỉ bằng biểu đồ lag tức thời; cần kết hợp deployment annotations và group events.

## 27. Runbook: exporter báo lag âm, thiếu hoặc không nhất quán

1. Kiểm tra metric được tính từ committed offset, consumer position, LSO hay LEO.
2. Kiểm tra có stale partition/member series không.
3. Kiểm tra group chưa từng commit offset hay consumer mới khởi tạo.
4. Kiểm tra retention/compaction và log start offset.
5. Kiểm tra offset reset hoặc seek thủ công gần đây.
6. Kiểm tra các transaction đang mở nếu dùng `read_committed`.
7. So sánh CLI, AdminClient và exporter cùng thời điểm.
8. Xem scrape interval, missing data và duplicate targets.

Nếu công cụ báo giá trị âm do snapshot end/commit khác thời điểm hoặc cách chuẩn hóa, không tự biến số âm thành “backlog âm” trong báo cáo nghiệp vụ. Hãy xác định định nghĩa và cách tính của nguồn dữ liệu, rồi điều chỉnh query/dashboard cho nhất quán.

## 28. Kiểm thử lag và throughput trong môi trường tích hợp

Một bộ test tốt cần xác nhận cả metrics và kết quả thực.

### 28.1. Consumer bình thường bắt kịp

1. Tạo topic có nhiều partitions.
2. Gửi một lượng records có event IDs ổn định.
3. Khởi động group test từ offset phù hợp.
4. Xác nhận listener xử lý thành công.
5. Xác nhận committed offset tiến.
6. Xác nhận group lag giảm về mức dự kiến.

### 28.2. Processing chậm hơn producer

1. Gửi records với input rate cao hơn processing capacity có kiểm soát.
2. Đo records-consumed-rate và success rate riêng.
3. Quan sát lag trend tăng.
4. Ngừng producer hoặc tăng capacity.
5. Xác nhận backlog dần giảm.

### 28.3. Manual acknowledgment và batch commit

1. Cấu hình ack mode phù hợp.
2. Xử lý nhiều records trước khi commit.
3. Quan sát committed lag tăng rồi giảm theo chu kỳ commit.
4. Xác nhận metrics không tính commit count thành record throughput.

### 28.4. Retry/DLT

1. Gửi event gây exception retryable.
2. Xác nhận blocking retry hoặc retry-topic routing đúng policy.
3. Đo main-topic lag và retry-topic lag riêng.
4. Xác nhận business success chưa được tính khi event mới chỉ được chuyển retry topic.
5. Nếu hết retry, xác nhận DLT và recovery metrics.

### 28.5. Crash trước commit

1. Xử lý một record nhưng mô phỏng crash trước offset commit.
2. Restart consumer cùng group.
3. Xác nhận record có thể được giao lại.
4. Xác nhận business handler idempotent.
5. Đối chiếu consumed count, business success và committed lag.

### 28.6. Partition skew

1. Gửi nhiều events vào một key/partition hơn các partitions khác.
2. Xác nhận max partition lag tăng dù group total throughput vẫn cao.
3. Tăng consumer count vượt partition count, kiểm tra hiệu quả thực tế.
4. Đánh giá phân phối key/ordering trước khi thay đổi partitions.

## 29. Các lỗi hiểu sai phổ biến

**Lag bằng 0 nghĩa mọi nghiệp vụ hoàn tất.** Sai nếu offset đã commit nhưng record chuyển sang retry topic, worker queue hoặc xử lý bất đồng bộ.

**records-consumed-rate là business success rate.** Client nhận record không đồng nghĩa database commit.

**Một records-consumed-rate cao là consumer đủ nhanh.** Cần so với arrival rate và lag trend.

**Cộng records-lag-max của các client để ra total group lag.** Max per-client không phải phép cộng committed lag theo partitions.

**Chỉ theo dõi total lag.** Một partition nóng có thể che khuất trong tổng trung bình.

**Đặt alert lag > 1.000 cho mọi topic.** Ý nghĩa 1.000 records phụ thuộc tốc độ, kích thước, SLO và workload.

**Rate trên lag gauge như counter.** Lag tăng giảm; dùng phép toán cho gauge và nhận biết resets/stale data.

**Lấy commit rate làm record rate.** Một commit có thể xác nhận cả batch.

**Tăng concurrency vô hạn.** Throughput vẫn bị giới hạn bởi partitions hoặc downstream bottleneck.

**Xem mọi lag spike sau rebalance là lỗi.** Cần xem xu hướng hồi phục.

**Bỏ qua LSO khi đọc transactional topics.** LEO và LSO có thể khác khi transaction đang mở.

**Reset offsets để xóa lag.** Có thể bỏ qua dữ liệu chưa xử lý.

**Bỏ qua retry/DLT backlog.** Main-topic lag thấp không có nghĩa workflow thành công.

**Không đo tuổi record.** Lag tính theo số lượng không tự thể hiện độ trễ nghiệp vụ.

## 30. Checklist giám sát và vận hành

### Định nghĩa số liệu

- [ ] Đã phân biệt fetch lag và committed consumer group lag.
- [ ] Đã thống nhất end-offset reference khi dùng `read_committed`.
- [ ] Dashboard xác định rõ group/topic/partition.
- [ ] Có total lag và max partition lag.
- [ ] Đã phân biệt records fetched, listener invocations và business success.
- [ ] Có record age hoặc end-to-end latency theo SLO.

### Cấu hình ứng dụng

- [ ] Ack/commit mode phù hợp với durability của side effects.
- [ ] Listener không trả thành công trước khi công việc quan trọng hoàn tất hoặc lưu bền vững.
- [ ] Có idempotency khi record được redeliver.
- [ ] Retry/backoff/DLT được quan sát riêng.
- [ ] Có metric queue/in-flight nếu dùng worker async.
- [ ] Concurrency phù hợp partition count và downstream capacity.

### Dashboard và alerts

- [ ] Đã đặt input rate bên cạnh completion rate.
- [ ] Có lag trend, không chỉ snapshot tức thời.
- [ ] Có top hot partitions.
- [ ] Có alerts theo duration/SLO thay vì một ngưỡng tuyệt đối chung.
- [ ] Có pause/rebalance/maintenance annotations.
- [ ] Không dùng event IDs/offsets làm metric tags.
- [ ] Kiểm tra metric schema và label names của exporter thực tế.

### Khôi phục

- [ ] Có runbook consumer lag tăng liên tục.
- [ ] Có runbook lag đứng yên và consumer không xử lý.
- [ ] Có runbook lag thấp nhưng business hoàn tất chậm.
- [ ] Có runbook retry-topic/DLT backlog.
- [ ] Có runbook hot partition và key skew.
- [ ] Không reset group offsets khi chưa đánh giá nguy cơ bỏ dữ liệu.
- [ ] Có capacity plan khi throughput đầu vào tăng.

## Kết luận

**Consumer lag** phản ánh khoảng cách giữa vị trí dữ liệu hiện có trong Kafka và tiến độ của consumer group, nhưng phải chỉ rõ đang dùng **committed offset**, **consumer position**, **LEO** hay **LSO**. **Tốc độ tiêu thụ** cũng cần phân biệt số record Kafka client fetch, số lần listener được gọi và số business events thật sự hoàn tất. Một consumer có throughput cao vẫn có thể tụt hậu nếu producer gửi nhanh hơn; một group có lag 0 vẫn có thể đang giữ backlog ở retry topic hoặc queue nội bộ.

Để vận hành Spring Kafka đáng tin cậy, hãy đo lag theo partition, theo dõi input rate cạnh processing success rate, bổ sung tuổi record, lỗi/retry/DLT, trạng thái pause và rebalance. Dùng các phép tính backlog/catch-up để đánh giá capacity nhưng không bỏ qua hot partitions, transaction visibility và commit semantics. Quan trọng nhất, **lag chỉ là một chỉ báo tiến độ Kafka**; kết luận về độ tin cậy phải dựa trên cả việc record đã được xử lý bền vững và pipeline đáp ứng SLO nghiệp vụ.
