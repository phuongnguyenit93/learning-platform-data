# Metric lỗi và retry

Metric lỗi và retry giúp nhóm vận hành biết application event đang được xử lý tốt đến đâu, listener nào thường thất bại, publication nào bị tồn đọng và cơ chế thử lại có đưa hệ thống trở về trạng thái bình thường hay không. Một dashboard chỉ đếm số exception là chưa đủ: cần đo cả số lần xử lý, tỷ lệ thành công, số lần lên lịch retry, retry đã cạn ngân sách, tuổi publication chưa hoàn tất và độ trễ từ lúc event được phát đến khi listener hoàn tất.

Trong Spring Modulith, `@ApplicationModuleListener` hỗ trợ giao event bất đồng bộ sau commit; Event Publication Registry theo dõi trạng thái publication đến transactional listener và giúp phát hiện publication chưa hoàn tất. Registry là nguồn thông tin quan trọng về trạng thái giao publication, còn metric ứng dụng mô tả sức khỏe, hiệu năng và chính sách retry. Cần phân biệt hai phần này để không nhầm một publication đang incomplete với một lần retry đã được lên lịch.

## 1. Metric trả lời câu hỏi vận hành nào?

Với mỗi luồng event, nhóm vận hành cần trả lời được:

- Có bao nhiêu lần listener được gọi và bao nhiêu lần thành công?
- Tỷ lệ lỗi đang tăng hay chỉ có một vài lỗi đơn lẻ?
- Lỗi tập trung ở listener, event type hay nhóm nguyên nhân nào?
- Bao nhiêu retry đã được lên lịch, đang chờ, đang chạy hoặc đã hết giới hạn?
- Publication incomplete lâu nhất đã tồn tại bao lâu?
- Backlog đang tăng nhanh hơn tốc độ xử lý hay không?
- Sau một đợt lỗi, event có được xử lý thành công khi retry không?
- Độ trễ xử lý có còn nằm trong SLO của nghiệp vụ không?

Metric nên đo trạng thái tổng hợp và xu hướng. Để điều tra một event cụ thể, dùng log và trace có `event_id`, `publication_id` hoặc correlation ID. Không đưa các định danh duy nhất này vào nhãn metric vì chúng làm cardinality tăng không giới hạn.

## 2. Phân biệt attempt, failure, retry và publication incomplete

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Metric thường dùng |
| --- | --- | --- |
| Attempt | Một lần listener thực sự bắt đầu xử lý publication. | Tổng attempt, thời lượng xử lý. |
| Success | Một attempt hoàn tất thành công theo transaction boundary đã chọn. | Tổng success, tỷ lệ success. |
| Failure | Một attempt kết thúc bằng lỗi. | Tổng failure theo nhóm lỗi. |
| Retry scheduled | Chính sách quyết định sẽ thử lại vào thời điểm sau. | Số retry được lên lịch, retry delay. |
| Retry executed | Một lần thử lại thực sự bắt đầu. | Số retry attempt, thời lượng retry. |
| Retry exhausted | Publication hoặc tác vụ đã hết ngân sách retry. | Số lần cạn retry, số event cần can thiệp. |
| Publication incomplete | Registry chưa ghi nhận listener hoàn tất publication. | Số publication incomplete, tuổi publication lâu nhất. |

Một failure không nhất thiết dẫn đến retry. Lỗi dữ liệu hoặc lỗi hợp đồng có thể bị phân loại là không retry được. Ngược lại, một publication incomplete có thể do tiến trình dừng giữa chừng, kể cả khi không có exception được ghi nhận. Một retry scheduled cũng chưa phải retry executed: tác vụ có thể vẫn đang chờ thời điểm tiếp theo.

Không dùng một counter chung tên `event_errors` để đại diện cho tất cả các trạng thái. Tách metric theo ý nghĩa giúp dashboard và alert không đưa ra kết luận sai.

## 3. Bộ metric cốt lõi

Một bộ metric tối thiểu nên bao gồm các nhóm sau:

| Nhóm | Metric gợi ý | Loại đo | Mục đích |
| --- | --- | --- | --- |
| Xử lý | `application.event.processing` | Timer | Thời gian mỗi attempt; có thể xem count, mean và percentile. |
| Xử lý | `application.event.failures` | Counter | Số attempt thất bại theo listener và nhóm lỗi. |
| Xử lý | `application.event.successes` | Counter | Số attempt thành công. |
| Retry | `application.event.retry.scheduled` | Counter | Số lần chính sách lên lịch retry. |
| Retry | `application.event.retry.executed` | Counter | Số lần retry thực sự bắt đầu. |
| Retry | `application.event.retry.exhausted` | Counter | Số tác vụ hết retry budget. |
| Retry | `application.event.retry.delay` | Timer/Distribution summary | Khoảng thời gian từ failure đến lần thử tiếp theo. |
| Registry | `application.event.publication.incomplete` | Gauge | Số publication chưa hoàn tất. |
| Registry | `application.event.publication.oldest.age` | Gauge | Tuổi của publication incomplete lâu nhất. |
| Queue | `application.event.retry.backlog` | Gauge | Số tác vụ đang chờ retry. |
| Queue | `application.event.dead_letter` | Counter/Gauge | Số event chuyển vào dead-letter hoặc số bản ghi đang tồn tại. |
| Năng lực | `application.event.in_flight` | Gauge | Số attempt đang xử lý. |

Tên metric trên là quy ước minh họa cho ứng dụng; hãy thống nhất naming convention với Micrometer, backend metrics và hệ thống dashboard đang dùng. Một số giá trị có thể được cung cấp bởi broker hoặc queue adapter, một số cần instrument ở listener/retry service.

## 4. Chọn counter, timer và gauge

**Counter** phù hợp với sự kiện chỉ tăng như failure, success, retry scheduled và retry exhausted. Khi hiển thị tốc độ, backend thường tính rate từ counter trong một cửa sổ thời gian; không cần tự reset counter mỗi phút.

**Timer** phù hợp với thời lượng xử lý và độ trễ retry. Timer thường cung cấp count và tổng thời gian, đồng thời có thể cấu hình histogram/percentile theo backend. Nên quan sát p50, p95, p99 cùng số lượng mẫu để tránh kết luận từ percentile khi traffic quá thấp.

**Gauge** phù hợp với trạng thái hiện tại như backlog, số publication incomplete, số worker active hoặc tuổi publication cũ nhất. Gauge cần phản ánh giá trị hiện tại, không tăng mãi theo thời gian.

Không tính tỷ lệ lỗi bằng cách lấy trung bình của các tỷ lệ từng instance. Hãy tính từ tổng số failure và tổng số attempt trong cùng cửa sổ:

\[
\text{failure rate} = \frac{\text{failed attempts}}{\text{all attempts}} \times 100\%
\]

Nếu cần tỷ lệ event thất bại cuối cùng, hãy đo riêng số publication kết thúc ở trạng thái exhausted hoặc dead-letter. Failure rate theo attempt có thể cao trong khi phần lớn event vẫn được retry thành công.

## 5. Thiết kế nhãn metric với cardinality thấp

Nhãn giúp lọc metric theo listener, event type hoặc nhóm lỗi. Tuy nhiên, mỗi tổ hợp nhãn tạo ra một time series riêng. Nếu thêm `event_id`, `order_id`, email, user ID hoặc exception message vào tag, số time series có thể tăng theo số event và làm backend metrics quá tải.

Nhãn thường phù hợp:

- `listener`: tên logic cố định của listener, ví dụ `inventory.order-confirmed`;
- `event_type`: một trong tập event type đã biết và có giới hạn;
- `outcome`: `success` hoặc `failure`;
- `failure_kind`: nhóm lỗi hữu hạn như `transient`, `business`, `contract`, `unknown`;
- `retryable`: `true` hoặc `false` nếu nhãn này thực sự hữu ích.

Không dùng các giá trị sau làm tag:

- event ID, publication ID, aggregate ID;
- tenant ID, customer ID, email hoặc số điện thoại;
- exception message, stack trace, URL có tham số;
- timestamp, retry timestamp hoặc giá trị tự do từ payload.

Đưa định danh cụ thể vào log hoặc trace thay vì metric. Nếu event type được tạo động từ dữ liệu, ánh xạ về một tập tên đã kiểm soát trước khi ghi metric.

## 6. Instrument listener bằng Micrometer

Micrometer có thể đo thời lượng và số lần xử lý ở ranh giới listener. Ví dụ sau minh họa cách giữ nhãn hữu hạn và để exception tiếp tục truyền ra ngoài:

```java
@Component
public class InventoryEventListener {

    private static final String LISTENER = "inventory.order-confirmed";
    private static final String EVENT_TYPE = "OrderConfirmed";

    private final InventoryService inventory;
    private final MeterRegistry meters;

    public InventoryEventListener(
            InventoryService inventory,
            MeterRegistry meters) {
        this.inventory = inventory;
        this.meters = meters;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        Timer.Sample sample = Timer.start(meters);
        String outcome = "success";

        try {
            inventory.reserveFor(event.orderId());
            Counter.builder("application.event.successes")
                    .tag("listener", LISTENER)
                    .tag("event_type", EVENT_TYPE)
                    .register(meters)
                    .increment();
        } catch (RuntimeException exception) {
            outcome = "failure";
            Counter.builder("application.event.failures")
                    .tag("listener", LISTENER)
                    .tag("event_type", EVENT_TYPE)
                    .tag("failure_kind", classify(exception))
                    .register(meters)
                    .increment();
            throw exception;
        } finally {
            sample.stop(Timer.builder("application.event.processing")
                    .tag("listener", LISTENER)
                    .tag("event_type", EVENT_TYPE)
                    .tag("outcome", outcome)
                    .register(meters));
        }
    }

    private String classify(RuntimeException exception) {
        if (exception instanceof DependencyUnavailableException) {
            return "transient";
        }
        if (exception instanceof InvalidEventException) {
            return "contract";
        }
        return "unknown";
    }
}
```

Đây là ví dụ instrument thủ công; `classify` phải ánh xạ exception vào tập nhãn hữu hạn. Trong ứng dụng thực tế nên tách metric recorder khỏi listener để tránh lặp code và thống nhất tên metric. Chỉ tăng success sau khi phần xử lý được xem là hoàn tất theo transaction boundary đã chọn. Nếu commit database có thể thất bại sau khi method trả về, hãy đặt instrumentation ở ranh giới có thể xác nhận commit hoặc kết hợp với metric trạng thái publication.

Không bắt exception rồi trả về bình thường chỉ để ghi metric. Với transactional listener, việc nuốt exception có thể khiến framework coi publication đã hoàn tất dù nghiệp vụ chưa thành công. Ghi metric rồi ném lại lỗi để cơ chế quản lý publication nhận biết failure.

## 7. Đo retry ở nơi quyết định retry

Metric retry nên được ghi tại thành phần thực sự đưa ra quyết định retry hoặc lên lịch retry. Không tăng `retry.scheduled` trong mọi catch block nếu chưa biết lỗi có được retry hay không.

Một luồng retry minh họa:

```java
public void handleFailure(
        EventEnvelope event,
        Failure failure,
        int attemptNumber) {

    RetryDecision decision = retryPolicy.decide(
            failure,
            attemptNumber,
            clock.instant()
    );

    if (decision.retry()) {
        retryScheduler.schedule(event, decision.nextAttemptAt());
        metrics.retryScheduled(failure.kind());
        return;
    }

    metrics.retryExhausted(failure.kind());
    deadLetterStore.store(event, failure);
}
```

`RetryDecision`, `RetryScheduler`, `DeadLetterStore` và `metrics` là abstraction của ứng dụng. Nếu dùng Event Publication Registry để phục hồi publication incomplete, không nhất thiết phải tự xây một scheduler cho cùng publication. Hãy xác định một nơi làm chủ retry cho mỗi chặng và instrument tại nơi đó.

Các trạng thái nên được đo riêng:

1. `failure`: attempt hiện tại thất bại.
2. `retry_scheduled`: đã lưu bền vững quyết định thử lại.
3. `retry_executed`: lần thử tiếp theo thực sự bắt đầu.
4. `retry_succeeded`: một lần retry hoàn tất thành công.
5. `retry_exhausted`: không còn được thử tự động theo policy.
6. `dead_lettered`: event đã được chuyển sang nơi chờ xử lý riêng.

Nếu listener lưu một retry task bền vững rồi kết thúc bình thường, ứng dụng đã nhận trách nhiệm giao tiếp cho retry worker. Chỉ làm vậy khi task được lưu an toàn, có idempotency và có cơ chế quan sát riêng. Nếu chưa có cơ chế thay thế bảo đảm phục hồi, hãy để exception truyền về cơ chế publication thay vì đánh dấu listener thành công.

## 8. Chính sách retry và metric cần đi kèm

Retry phù hợp với lỗi có khả năng tự hết như timeout, mất kết nối ngắn hạn hoặc dịch vụ phụ thuộc tạm thời không khả dụng. Lỗi hợp đồng, payload không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường không được giải quyết bằng cách thử lại liên tục.

Một retry policy cần xác định:

- nhóm lỗi được retry và nhóm lỗi không retry;
- số lần thử tối đa hoặc deadline tổng;
- khoảng chờ cơ sở và khoảng chờ tối đa;
- exponential backoff và jitter;
- điều kiện chuyển sang dead-letter/quarantine;
- cách redrive sau khi nguyên nhân đã được khắc phục.

Ví dụ exponential backoff có giới hạn:

\[
d_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

Sau đó thêm jitter trong khoảng được cấu hình để nhiều event không cùng retry tại một thời điểm. Đây là công thức khái niệm; triển khai cần tránh overflow, áp dụng giới hạn và dùng đồng hồ nhất quán.

Metric liên quan gồm retry count theo nhóm lỗi, retry delay, số tác vụ đang chờ, số tác vụ đến hạn nhưng chưa chạy, retry exhausted và tỷ lệ phục hồi thành công sau retry. Không dùng `attemptNumber` làm nhãn nếu số lần thử không có giới hạn nhỏ; ghi nó trong log hoặc histogram nếu cần phân tích.

## 9. Phân loại lỗi để retry đúng

Không phải mọi exception đều nên retry. Phân loại lỗi phải thống nhất giữa listener, retry policy và dashboard.

| Nhóm lỗi | Ví dụ | Retry | Nhãn metric gợi ý |
| --- | --- | --- | --- |
| Tạm thời | Timeout, connection reset, dependency tạm ngừng | Có giới hạn, có backoff | `transient` |
| Quá tải | Rate limit, thread pool đầy, broker throttling | Có thể retry sau thời gian chờ | `overload` |
| Hợp đồng | Payload sai schema, thiếu trường bắt buộc, event type không hỗ trợ | Thường không retry tự động | `contract` |
| Nghiệp vụ | Không đủ điều kiện, trạng thái không cho phép | Theo quy tắc nghiệp vụ; thường cần can thiệp hoặc event mới | `business` |
| Lập trình/cấu hình | Null bất ngờ, mapping sai, thiếu bean hoặc cấu hình | Không retry liên tục; cần sửa lỗi | `programming` |
| Không xác định | Chưa phân loại được nguyên nhân | Chính sách thận trọng, cảnh báo và giới hạn retry | `unknown` |

Metric theo nhóm lỗi giúp nhận ra xu hướng. Ví dụ, `transient` tăng đồng thời với dependency latency cao có thể chỉ ra sự cố dịch vụ ngoài; `contract` tăng sau một lần deploy có thể chỉ ra producer/consumer không tương thích.

Không dùng exception class đầy đủ hoặc exception message làm nhãn nếu chúng có thể sinh ra nhiều giá trị. Có thể ghi chi tiết exception vào log có kiểm soát, còn metric chỉ giữ nhóm lỗi ổn định.

## 10. Quan sát Event Publication Registry

Event Publication Registry theo dõi publication đến transactional listener. Publication chưa hoàn tất có thể cho biết listener đã thất bại, tiến trình dừng giữa chừng hoặc trạng thái hoàn tất chưa được ghi nhận. Đây là chỉ báo quan trọng cho giao event nội bộ trong Spring Modulith.

Có thể dùng API công khai `EventPublicationRegistry` để truy vấn publication incomplete theo phiên bản Spring Modulith đang sử dụng. Ví dụ về hướng quan sát:

```java
@Component
public class PublicationHealthCollector {

    private final EventPublicationRegistry publications;
    private final MeterRegistry meters;

    public PublicationHealthCollector(
            EventPublicationRegistry publications,
            MeterRegistry meters) {
        this.publications = publications;
        this.meters = meters;
    }

    public void collect() {
        int incomplete = publications.findIncompletePublications().size();
        Gauge.builder(
                "application.event.publication.incomplete",
                () -> incomplete
        ).register(meters);
    }
}
```

Đoạn mã chỉ minh họa việc lấy số lượng publication incomplete; không nên đăng ký một Gauge mới trong mỗi lần collect như ví dụ đơn giản này ở production. Hãy giữ một state object ổn định hoặc dùng binder/collector được quản lý vòng đời đúng cách. API và kiểu trả về cần đối chiếu với phiên bản Spring Modulith của ứng dụng.

Registry không phải bộ đếm retry. Nó cho biết publication còn incomplete, không tự cung cấp đầy đủ lịch sử attempt, nguyên nhân lỗi, thời gian backoff hoặc số lần retry theo policy nghiệp vụ. Muốn có các số liệu đó, instrument listener và retry coordinator của ứng dụng. Không truy cập trực tiếp bảng nội bộ hoặc sửa trạng thái registry bằng SQL để làm dashboard.

## 11. Đo backlog và tuổi publication

Số lượng publication incomplete là một tín hiệu, nhưng cần kết hợp với tuổi của publication cũ nhất. Một backlog gồm 500 event mới phát trong vài giây có thể bình thường; một publication tồn tại nhiều giờ có thể là sự cố dù backlog chỉ có một event.

Các metric hữu ích:

- `publication.incomplete`: số publication đang chờ hoàn tất;
- `publication.oldest.age`: tuổi của publication incomplete lâu nhất;
- `retry.backlog`: số retry task đang chờ;
- `retry.overdue`: số task đã đến hạn nhưng chưa được chạy;
- `listener.in_flight`: số attempt đang xử lý;
- `listener.processing`: thời lượng xử lý theo listener và outcome.

Nếu event được externalize qua broker, lấy backlog, consumer lag, unacknowledged messages và DLQ depth từ broker/client metrics. Không suy ra backlog broker chỉ từ trạng thái Event Publication Registry nội bộ: đây là các chặng khác nhau.

Khi đo tuổi, dùng timestamp UTC và đồng hồ hệ thống được đồng bộ. Nếu metric collector không thể truy vấn registry hoặc broker, ghi nhận lỗi collector riêng; không xuất số 0 giả vì dashboard sẽ hiểu nhầm hệ thống đang khỏe.

## 12. Cảnh báo dựa trên SLO và xu hướng

Alert tốt tập trung vào ảnh hưởng vận hành, không bắn cảnh báo cho mọi exception. Có thể xây dựng các cảnh báo sau:

| Cảnh báo | Điều kiện tham khảo | Ý nghĩa |
| --- | --- | --- |
| Failure rate tăng | Tỷ lệ failure vượt ngưỡng trong nhiều cửa sổ liên tiếp và có đủ số mẫu | Listener hoặc dependency đang gặp lỗi có tính hệ thống. |
| Publication quá cũ | Tuổi publication incomplete lâu nhất vượt thời gian xử lý cho phép | Một số event có thể đang bị kẹt. |
| Retry exhausted | Counter exhausted tăng hoặc có event mới vào DLQ | Cần điều tra hoặc can thiệp. |
| Retry backlog tăng | Backlog tăng liên tục, số task đến hạn vượt năng lực xử lý | Consumer không theo kịp tốc độ lỗi/phát sinh. |
| Processing latency cao | p95/p99 vượt SLO trong khoảng thời gian đủ dài | Listener chậm, contention hoặc dependency latency cao. |
| Không có success | Có traffic/attempt nhưng không có success trong cửa sổ quan sát | Luồng có thể đã ngừng hoạt động. |
| Collector mất dữ liệu | Không scrape được metrics hoặc registry/broker collector lỗi | Dashboard không còn đủ dữ liệu để kết luận. |

Ngưỡng cụ thể cần dựa trên SLO, lưu lượng bình thường và mức độ quan trọng của event. Dùng `for` duration hoặc nhiều cửa sổ liên tiếp để tránh cảnh báo do một spike ngắn. Với event quan trọng, có thể đặt ngưỡng tuổi publication thấp hơn các event phục vụ báo cáo.

Không chỉ cảnh báo theo tỷ lệ. Khi lưu lượng rất thấp, một failure tạo ra tỷ lệ 100% nhưng có thể chưa phải sự cố hệ thống; kết hợp tỷ lệ với số lượng tuyệt đối và tuổi event.

## 13. Dashboard theo luồng event

Một dashboard vận hành có thể chia thành bốn khu vực:

1. **Throughput:** attempt, success, failure theo thời gian và listener.
2. **Latency:** thời lượng xử lý p50/p95/p99, độ trễ từ event đến completion.
3. **Recovery:** retry scheduled/executed, retry delay, retry exhausted, DLQ và recovery success.
4. **Backlog:** publication incomplete, oldest age, retry queue depth, overdue task và broker lag.

Bộ lọc nên dùng listener, event type và failure kind có cardinality thấp. Khi người vận hành chọn một listener có lỗi, dashboard dẫn tới log/trace để tra event ID và correlation ID. Không cố hiển thị mọi event ID thành time series.

Nên có dashboard riêng cho các luồng có SLO khác nhau. Ví dụ, event cập nhật trạng thái thanh toán cần cảnh báo nhanh hơn event xây dựng báo cáo ngày. Tránh gộp tất cả listener thành một tỷ lệ trung bình khiến luồng quan trọng bị che khuất.

## 14. Log và trace bổ sung cho metric

Metric cho biết điều gì đang xảy ra trên diện rộng; log và trace giúp tìm nguyên nhân của một lần xử lý cụ thể.

Log có cấu trúc nên chứa:

- `event_id` và `publication_id` nếu có;
- event type và listener name;
- attempt number và retry policy version;
- failure kind và exception type đã chuẩn hóa;
- correlation ID/trace ID;
- thời điểm bắt đầu, kết thúc và retry scheduled time;
- outcome như `SUCCESS`, `RETRY_SCHEDULED`, `EXHAUSTED` hoặc `DEAD_LETTERED`.

Không đưa event ID, aggregate ID hoặc exception message thành metric tag. Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Trace có thể liên kết publisher với listener và dependency call; với retry diễn ra sau một khoảng chờ dài, dùng trace link hoặc correlation ID để nối các lần thực thi thay vì giữ một span mở vô thời hạn.

## 15. Tránh đếm metric sai

Một số lỗi instrumentation thường làm dashboard khó tin cậy:

- Tăng failure counter trong cả listener và retry coordinator cho cùng một failure, khiến một lỗi bị đếm hai lần.
- Tăng retry scheduled dù policy quyết định không retry.
- Tăng success ngay khi method trả về, trong khi transaction commit sau đó có thể rollback.
- Đếm publication incomplete như số retry attempt.
- Đếm redelivery từ broker như một event mới.
- Dùng metric collector không hoạt động nhưng vẫn xuất giá trị zero.
- Tạo tag động từ event ID hoặc exception message làm cardinality bùng nổ.
- Không phân biệt retry đã lên lịch với retry thực sự bắt đầu.

Hãy xác định một điểm sở hữu cho mỗi metric. Ví dụ listener sở hữu attempt duration và failure; retry coordinator sở hữu retry scheduled/exhausted; registry collector sở hữu incomplete publication; broker exporter sở hữu consumer lag và queue depth.

## 16. Kiểm thử metric và retry

Kiểm thử nên xác minh metric phản ánh đúng trạng thái và không làm thay đổi semantics của listener:

1. Listener thành công tăng success đúng một lần và ghi duration.
2. Listener thất bại tăng failure theo nhóm lỗi rồi truyền exception ra ngoài.
3. Lỗi không retry được không làm tăng retry scheduled.
4. Lỗi retry được tăng retry scheduled đúng một lần khi task đã được lưu.
5. Retry thực sự bắt đầu mới tăng retry executed.
6. Hết retry budget tăng retry exhausted và tạo trạng thái cần can thiệp.
7. Publication incomplete được đo riêng với retry backlog.
8. Metric tag không chứa event ID, aggregate ID hoặc exception message.
9. Transaction commit/rollback được phản ánh đúng trong success metric.
10. Collector lỗi không xuất số liệu zero giả và có metric sức khỏe riêng.

Với Micrometer, có thể dùng `SimpleMeterRegistry` trong unit test để kiểm tra counter, timer và tag. Kiểm thử tích hợp cần xác nhận metric được export qua registry/backend đang dùng và dashboard query đúng tên/label. Không cần chạy QA chuyên môn trong bước soạn bài này; các ví dụ cần được xác minh ở vòng QA riêng theo quy trình dự án.

## 17. Checklist triển khai metric lỗi và retry

- [ ] Phân biệt attempt, success, failure, retry scheduled, retry executed và retry exhausted.
- [ ] Có timer cho thời lượng xử lý và độ trễ retry.
- [ ] Có gauge cho publication incomplete, retry backlog và tuổi event cũ nhất.
- [ ] Nhãn metric là tập giá trị hữu hạn, cardinality thấp.
- [ ] Event ID, aggregate ID và exception message chỉ nằm trong log/trace có kiểm soát.
- [ ] Failure được phân loại thống nhất với retry policy.
- [ ] Retry có backoff, jitter, giới hạn số lần hoặc deadline.
- [ ] Metric retry được ghi tại nơi thực sự lên lịch và thực thi retry.
- [ ] Event Publication Registry được dùng để quan sát publication incomplete, không nhầm với retry counter.
- [ ] Broker lag và DLQ được đo riêng nếu event được externalize.
- [ ] Alert dựa trên SLO, tỷ lệ, số lượng tuyệt đối và tuổi backlog.
- [ ] Kiểm thử xác nhận metric không nuốt exception hoặc làm sai transaction semantics.

Metric lỗi và retry biến quá trình giao event thành một luồng có thể quan sát và điều hành. Trong Spring Modulith, Event Publication Registry cho biết publication nào chưa hoàn tất; Micrometer và metric của retry coordinator cho biết listener thất bại ra sao, retry có được lên lịch và backlog đang tăng hay giảm. Khi mỗi metric có một điểm sở hữu rõ ràng, nhãn có cardinality thấp và alert dựa trên SLO, nhóm vận hành có thể phát hiện sự cố sớm, phân biệt lỗi tạm thời với lỗi cần can thiệp và xác nhận hệ thống đã phục hồi sau retry.
