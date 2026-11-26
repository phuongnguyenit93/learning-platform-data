# Metric độ trễ handler

Metric độ trễ handler cho biết một event mất bao lâu để được xử lý tại listener hoặc handler. Đây là chỉ số quan trọng trong hệ thống hướng sự kiện vì publisher có thể đã phát event thành công trong khi listener vẫn đang chờ, xử lý chậm hoặc retry nhiều lần.

Một con số latency duy nhất thường không đủ để giải thích vấn đề. Cần phân biệt thời gian handler thực thi, thời gian event chờ trước khi được xử lý, tuổi của event khi hoàn tất và thời gian của toàn bộ quy trình nghiệp vụ. Đo đúng từng khoảng giúp xác định độ trễ nằm ở listener, executor, broker, database hay một dịch vụ bên ngoài.

Trong Spring Modulith, application events giúp các module giao tiếp qua ranh giới nghiệp vụ. Event Publication Registry theo dõi publication tới listener và hỗ trợ phục hồi publication chưa hoàn tất. Registry không tự thay thế bộ metric của handler. Ứng dụng cần chủ động instrument listener hoặc service xử lý để ghi nhận thời gian, kết quả, retry và các chiều quan sát phù hợp.

## 1. Độ trễ handler có những loại nào?

Trước khi tạo metric, hãy thống nhất điểm bắt đầu và kết thúc. Những khoảng thời gian dưới đây trả lời các câu hỏi khác nhau:

| Loại độ trễ | Điểm bắt đầu | Điểm kết thúc | Ý nghĩa |
|---|---|---|---|
| Handler execution duration | Handler bắt đầu chạy | Handler hoàn tất hoặc ném lỗi | Thời gian code xử lý một lần giao |
| Queue wait | Broker nhận hoặc enqueue message | Consumer bắt đầu xử lý | Thời gian message chờ trước khi được xử lý |
| Event age | Event xảy ra hoặc được tạo | Handler hoàn tất | Event đã cũ bao lâu khi công việc kết thúc |
| Dispatch delay | Publication sẵn sàng được giao | Listener bắt đầu chạy | Thời gian chờ executor hoặc cơ chế dispatch |
| End-to-end workflow duration | Quy trình nghiệp vụ bắt đầu | Quy trình đạt trạng thái cuối | Thời gian hoàn thành toàn bộ nghiệp vụ |

Handler execution duration là metric cơ bản nhất. Nó đo khoảng thời gian từ lúc listener bắt đầu thực thi đến lúc listener kết thúc. Nếu listener gọi database và dịch vụ ngoài theo kiểu đồng bộ, thời gian chờ các lời gọi đó cũng nằm trong duration.

Queue wait và event age cần timestamp ở các mốc trước khi handler chạy. Nếu không có timestamp broker enqueue hoặc event occurredAt, không thể suy ra chính xác các khoảng này chỉ từ thời gian chạy listener.

End-to-end workflow duration thường dài hơn handler duration vì một quy trình có thể gồm nhiều event, nhiều listener, retry và bước chờ bên ngoài. Với saga, nên đo riêng thời gian từ lúc saga bắt đầu đến khi hoàn tất hoặc bị hủy.

## 2. Xác định ranh giới đo

Một metric có ý nghĩa khi mọi thành phần dùng cùng định nghĩa. Ví dụ với handler ghi nhận thanh toán:

~~~text
event occurredAt
       |
       v
publisher commit
       |
       v
publication được dispatch
       |
       v
handler bắt đầu  --------------------+
       |                             |
       | validate                    |
       | database write              | handler execution duration
       | gọi service ngoài           |
       |                             |
handler kết thúc hoặc ném exception-+
       |
       v
publication được cập nhật trạng thái
~~~

Khi đo handler execution duration, bắt đầu ngay trước phần công việc cần theo dõi và dừng khi phần đó hoàn tất hoặc thất bại. Không đặt timer ở một lớp chỉ enqueue tác vụ vào executor rồi coi đó là thời gian xử lý thực tế. Nếu listener chuyển việc sang một background worker khác và trả về ngay, timer của listener chỉ đo thời gian enqueue; worker cần metric riêng.

Nên xác định rõ handler được đo là listener method, application service hay toàn bộ chuỗi xử lý đồng bộ. Đo cùng một công việc ở nhiều lớp có thể hữu ích để phân rã thời gian, nhưng cần đặt tên metric khác nhau và tránh cộng các khoảng thời gian chồng lấn.

Với listener được chạy sau commit, thời gian chờ đến khi transaction phát event commit không nằm trong handler execution duration nếu timer chỉ bắt đầu khi listener được gọi. Muốn đo khoảng chờ đó, cần một timestamp ở thời điểm event/publication được tạo và một timestamp ở thời điểm listener bắt đầu.

## 3. Dùng Micrometer Timer để đo thời gian xử lý

Spring Boot thường tích hợp Micrometer để ghi metric vào MeterRegistry và xuất sang hệ thống quan sát. Timer là loại meter phù hợp để đo thời lượng của một thao tác. Timer ghi nhận số lần thực hiện và tổng thời gian; khi bật histogram, hệ thống còn có thể tính phân vị và tỷ lệ đáp ứng các ngưỡng.

Ví dụ instrument một listener bằng Timer.Sample:

~~~java
@Component
class AccountingEventListener {

    private final AccountingService accountingService;
    private final MeterRegistry meterRegistry;
    private final Timer successTimer;
    private final Timer errorTimer;

    AccountingEventListener(
            AccountingService accountingService,
            MeterRegistry meterRegistry) {
        this.accountingService = accountingService;
        this.meterRegistry = meterRegistry;
        this.successTimer = buildTimer(meterRegistry, "success");
        this.errorTimer = buildTimer(meterRegistry, "error");
    }

    private static Timer buildTimer(
            MeterRegistry registry,
            String outcome) {
        return Timer.builder("application.events.handler.duration")
            .description("Time spent processing an application event")
            .tag("handler", "accounting")
            .tag("event_type", "order_paid")
            .tag("outcome", outcome)
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(50),
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofSeconds(1)
            )
            .register(registry);
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        Timer.Sample sample = Timer.start(meterRegistry);
        Timer result = successTimer;

        try {
            accountingService.recordPayment(event);
        } catch (RuntimeException | Error ex) {
            result = errorTimer;
            throw ex;
        } finally {
            sample.stop(result);
        }
    }
}
~~~

Hai Timer được đăng ký một lần trong constructor, với cùng tên và các tag có tập giá trị cố định. Listener chỉ chọn meter tương ứng rồi dừng sample trong finally. Cách này ghi duration cho cả thành công và thất bại mà vẫn giữ nguyên exception để cơ chế publication/retry xử lý. Nếu muốn dùng một Timer chung không phân biệt outcome, có thể dùng một meter cho toàn bộ lần chạy và ghi lỗi bằng Counter riêng.

Timer.Sample sử dụng clock của Micrometer để đo elapsed time. Với khoảng thời gian trong cùng tiến trình, nên dựa trên đồng hồ monotonic do thư viện quản lý thay vì lấy hai timestamp wall-clock rồi trừ trực tiếp. Cách này tránh sai số khi đồng hồ hệ thống được đồng bộ hoặc điều chỉnh trong lúc handler đang chạy.

## 4. Đo duration, event age và queue wait riêng biệt

Không nên gộp mọi độ trễ vào một Timer duy nhất. Mỗi loại metric cần một nguồn thời gian phù hợp.

### Handler execution duration

Đo thời gian handler thực thi trong một lần giao. Timer bắt đầu ngay khi handler nhận quyền xử lý và dừng trong finally để cả lần thành công lẫn thất bại đều được ghi nhận.

### Event age

Event age là khoảng từ lúc event được tạo hoặc xảy ra đến lúc handler hoàn tất. Event cần mang occurredAt hoặc timestamp tương đương. Có thể ghi nhận khi handler hoàn tất:

~~~java
Duration age = Duration.between(
    event.occurredAt(),
    clock.instant()
);

if (!age.isNegative()) {
    eventAgeTimer.record(age);
}
~~~

Đây là phép đo dùng wall-clock ở hai thời điểm. Nếu event đi qua nhiều máy, đồng hồ của producer và consumer có thể lệch nhau. Cần đồng bộ NTP, chuẩn hóa timestamp UTC và theo dõi giá trị âm hoặc bất thường. Không âm thầm chuyển một event age âm thành 0 rồi coi dữ liệu hợp lệ.

### Queue wait

Queue wait là khoảng từ khi broker nhận message đến lúc consumer bắt đầu xử lý. Nếu broker hoặc message header cung cấp timestamp enqueue, consumer có thể tính khoảng này. Với broker không cung cấp timestamp phù hợp, producer có thể gắn publishedAt theo contract, nhưng cần hiểu đó là thời điểm producer gửi chứ không nhất thiết là thời điểm broker lưu message.

### Dispatch delay trong ứng dụng

Với listener bất đồng bộ, event có thể phải chờ executor trước khi listener bắt đầu. Để đo dispatch delay, cần timestamp được lưu ở thời điểm publication sẵn sàng dispatch và timestamp ở đầu listener. Không lấy thời gian event xảy ra thay cho thời gian dispatch nếu event đã được tạo từ trước.

Một bảng metric gợi ý:

| Metric | Loại | Đơn vị | Dùng để trả lời |
|---|---|---|---|
| application.events.handler.duration | Timer | giây | Handler mất bao lâu mỗi lần chạy? |
| application.events.handler.event.age | Timer | giây | Event cũ bao lâu khi được xử lý xong? |
| application.events.handler.queue.wait | Timer | giây | Message chờ bao lâu trước khi handler bắt đầu? |
| application.events.handler.failures | Counter | lần | Có bao nhiêu lần handler thất bại? |
| application.events.handler.retries | Counter | lần | Có bao nhiêu lần xử lý lại được thực hiện? |

Các tên trên là quy ước metric của ứng dụng, không phải tên metric mặc định được bảo đảm có sẵn trong Spring Modulith.

## 5. Đo cả thành công và thất bại

Chỉ đo duration của các lần thành công sẽ che mất tình trạng handler thất bại nhanh hoặc timeout kéo dài. Hãy ghi duration cho mọi lần thực thi và phân loại outcome bằng một tập giá trị nhỏ, ví dụ success, error, rejected hoặc timeout.

Một lần xử lý thất bại vẫn cần dừng Timer trong finally trước khi exception được truyền ra. Việc ghi metric không được làm thay đổi luồng exception:

~~~java
try {
    handler.process(event);
} catch (RuntimeException ex) {
    failureCounter.increment();
    throw ex;
} finally {
    sample.stop(handlerTimer);
}
~~~

Nếu lỗi nghiệp vụ là kết quả hợp lệ, chẳng hạn PaymentDeclined, có thể ghi outcome là rejected và lưu event kết quả tương ứng. Đừng phân loại một lần thanh toán bị từ chối như lỗi kỹ thuật nếu đó là kết quả được contract định nghĩa.

Nên tách các chỉ số:

- Duration: thời gian của từng lần thử.
- Failure counter: số lần handler thất bại.
- Retry counter: số lần retry thực sự được lên lịch hoặc thực hiện.
- Completion counter: số event đạt trạng thái kết thúc nghiệp vụ.
- In-flight: số handler đang chạy tại thời điểm quan sát, nếu cần.

Một event được retry ba lần sẽ tạo ba lần đo handler duration. Nếu cần biết tổng thời gian từ lúc event được tạo đến lúc cuối cùng thành công, hãy ghi một metric event age hoặc logical processing duration riêng khi event đạt trạng thái terminal. Không lấy tổng duration của ba lần thử làm thời gian event age vì nó bỏ qua thời gian chờ giữa các lần retry.

## 6. Histogram, percentile và SLO

Latency thường có phân phối lệch: phần lớn event xử lý nhanh nhưng một số ít bị chậm rất lâu. Trung bình (average) có thể che giấu tail latency. Vì vậy, nên theo dõi p50, p95 và p99 cùng histogram.

- **p50** cho biết một handler điển hình mất bao lâu.
- **p95** cho biết 95% lần xử lý hoàn tất trong hoặc dưới ngưỡng đó.
- **p99** giúp nhìn thấy phần đuôi chậm và những lần xử lý hiếm nhưng ảnh hưởng lớn.
- **Histogram** cho phép hệ thống quan sát tổng hợp bucket trên nhiều instance.

Không nên chỉ bật percentile tính riêng trong từng instance rồi cộng hoặc lấy trung bình giữa các instance để ra percentile toàn hệ thống. Với Prometheus, histogram bucket có thể được tổng hợp rồi tính percentile trên toàn bộ series.

SLO latency cần gắn với yêu cầu nghiệp vụ. Ví dụ, handler cập nhật trạng thái đơn hàng có thể đặt mục tiêu 95% lần xử lý dưới 250 ms; handler tạo báo cáo nền có thể có ngưỡng vài giây. Các con số phải dựa trên ngân sách độ trễ, tải thực tế và phụ thuộc downstream.

Micrometer Timer có thể bật percentile histogram và khai báo service level objectives. Ví dụ ngưỡng 50 ms, 100 ms, 250 ms và 1 giây giúp histogram có bucket phục vụ truy vấn và đánh giá SLO. Không chọn bucket quá dày nếu số lượng meter và series làm tăng chi phí lưu trữ đáng kể.

## 7. Metric name và tag có cardinality thấp

Metric có tag giúp so sánh handler, event type và kết quả. Nhưng mỗi tổ hợp tag tạo ra một time series. Nếu tag có giá trị gần như duy nhất cho từng event, số series có thể tăng rất nhanh.

Các tag thường phù hợp:

- handler: tên logic ổn định của listener, ví dụ accounting hoặc shipping.
- event_type: một trong các loại event được công bố.
- module: module nhận event.
- outcome: success, error, rejected hoặc timeout.
- transport: local, rabbitmq hoặc kafka nếu cùng dashboard cần so sánh.

Không đưa các giá trị sau vào metric tag:

- eventId, orderId, customerId hoặc correlationId.
- Email, username hoặc dữ liệu định danh.
- Exception message hoặc stack trace.
- URL có path động hoặc tên tenant không giới hạn.
- Timestamp, request ID hoặc delivery tag.

Các giá trị có độ phân biệt cao nên nằm trong log hoặc trace. Có thể ghi eventId và correlationId trong structured log để tìm một lần xử lý cụ thể mà không tạo hàng triệu series metric.

Tên handler và event type nên được kiểm soát từ code hoặc registry cấu hình, không lấy nguyên văn từ payload bên ngoài. Nếu event type có thể do nguồn không tin cậy tự đặt, hãy chuẩn hóa hoặc ánh xạ sang tập tên được phép trước khi dùng làm tag.

## 8. Tích hợp với Spring Modulith và Micrometer

Spring Modulith quản lý application event và publication; Micrometer đo thời lượng xử lý. Có thể instrument trực tiếp trong listener hoặc trong application service được listener gọi.

Ví dụ listener:

~~~java
@Component
class ShippingEventListener {

    private final ShippingService shippingService;
    private final MeterRegistry registry;

    ShippingEventListener(
            ShippingService shippingService,
            MeterRegistry registry) {
        this.shippingService = shippingService;
        this.registry = registry;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            shippingService.prepareShipment(event);
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("application.events.handler.duration")
                    .tag("handler", "shipping")
                    .tag("event_type", "order_paid")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
~~~

Ví dụ này ghi một Timer theo từng lần listener chạy. Nếu code production có nhiều handler, hãy trích xuất một component dùng chung để tránh lặp lại logic instrumentation và bảo đảm tên/tag thống nhất. Component đó không được bắt exception rồi trả về bình thường; phải giữ nguyên hành vi lỗi của listener.

Có thể dùng Micrometer Observation để kết hợp metric và tracing:

~~~java
Observation.createNotStarted(
        "application.events.handler",
        observationRegistry)
    .lowCardinalityKeyValue("handler", "shipping")
    .lowCardinalityKeyValue("event.type", "order_paid")
    .observe(() -> shippingService.prepareShipment(event));
~~~

Observation có thể được kết nối với meter và tracing handler đã cấu hình trong ứng dụng. Việc có metric hoặc span cụ thể phụ thuộc các ObservationHandler, registry và tracing exporter đang hoạt động. Chỉ tạo Observation trong code không tự bảo đảm mọi backend đã nhận dữ liệu.

Không giả định Spring Modulith tự cung cấp sẵn metric duration cho từng listener theo một tên cố định. Hãy instrument ở ranh giới handler và kiểm tra endpoint Actuator hoặc registry thực tế để xác nhận meter đã được đăng ký và xuất ra.

## 9. Dùng histogram với Prometheus và Grafana

Khi Micrometer xuất Timer sang Prometheus với histogram, metric thường có các series bucket, count và sum. Tên metric được chuyển đổi theo quy ước của Prometheus; dấu chấm trong tên Micrometer thường trở thành dấu gạch dưới và Timer dùng đơn vị giây.

Ví dụ truy vấn p95 theo handler:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, handler) (
    rate(application_events_handler_duration_seconds_bucket[5m])
  )
)
~~~

Truy vấn p99 theo event type:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, event_type) (
    rate(application_events_handler_duration_seconds_bucket[5m])
  )
)
~~~

Tỷ lệ lần xử lý thất bại có thể theo dõi bằng Counter riêng:

~~~promql
sum by (handler) (
  rate(application_events_handler_failures_total[5m])
)
~~~

Các tên series ở trên là ví dụ theo quy ước Micrometer Prometheus. Hãy xem metric thực tế tại endpoint scrape vì tên có thể thay đổi theo naming convention, cấu hình registry hoặc phiên bản.

Dashboard nên hiển thị ít nhất p50/p95/p99, throughput, số lỗi, số retry và số publication incomplete. Khi p95 tăng, so sánh cùng thời điểm với queue wait, event age, database latency và downstream latency để tìm đúng nút thắt.

## 10. Đặt cảnh báo theo ngân sách độ trễ

Một cảnh báo latency hữu ích cần có ngưỡng, cửa sổ thời gian và điều kiện tải tối thiểu. Nếu chỉ có một event chậm trong một khoảng dài, p99 có thể dao động mạnh. Hãy kết hợp percentile với số lượng request và tỷ lệ lỗi.

Ví dụ, một cảnh báo có thể kích hoạt khi p95 handler duration vượt 250 ms liên tục 10 phút và có đủ số lần xử lý trong cửa sổ. Ngưỡng thực tế phụ thuộc SLO của từng handler.

Nên có cảnh báo riêng cho:

- p95 hoặc p99 vượt ngân sách trong một khoảng liên tục.
- Queue wait tăng dù handler execution duration vẫn bình thường.
- Event age tăng, cho thấy event bị chậm từ trước khi handler chạy.
- Tỷ lệ lỗi hoặc retry tăng đột biến.
- Publication incomplete tồn tại quá lâu.
- Handler in-flight tăng liên tục hoặc không giảm sau khi tải hạ.

Không cảnh báo chỉ dựa trên một giá trị max đơn lẻ. Max rất nhạy với một outlier. Dùng percentile, tỷ lệ vượt SLO, error rate và backlog để đánh giá xu hướng.

## 11. Phân tích nguyên nhân khi latency tăng

Kết hợp nhiều metric giúp xác định thành phần gây chậm:

| Quan sát | Khả năng nguyên nhân | Hướng điều tra |
|---|---|---|
| Handler duration tăng, queue wait ổn định | Code handler hoặc downstream chậm | Trace, database query, HTTP client |
| Queue wait tăng, handler duration ổn định | Consumer thiếu năng lực hoặc executor bị nghẽn | Concurrency, thread pool, prefetch |
| Event age tăng nhưng handler duration thấp | Event được tạo hoặc dispatch từ lâu mới đến handler | Publication backlog, broker queue, retry delay |
| p99 tăng, p50 ổn định | Một số request gặp tail latency | Lock contention, GC pause, slow query, network |
| Duration và error rate cùng tăng | Downstream lỗi hoặc timeout | Dependency health, timeout, circuit breaker |
| Retry tăng, publication incomplete tăng | Listener thất bại liên tục | Exception type, cấu hình retry, dữ liệu lỗi |

Một handler có duration thấp không nhất thiết có trải nghiệm tốt. Nếu event chờ 30 giây trong queue rồi được xử lý trong 10 ms, handler metric đẹp nhưng nghiệp vụ vẫn trễ. Đây là lý do cần đo cả event age hoặc queue wait.

Trace có thể cho thấy thời gian chia cho các span như deserialize, validate, database và HTTP call. Metric cho thấy xu hướng tổng thể; trace giúp tìm một lần xử lý cụ thể; log cung cấp ngữ cảnh lỗi và định danh để đối chiếu.

## 12. Retry ảnh hưởng đến cách đọc latency

Khi handler retry, cần phân biệt thời gian của một attempt với thời gian hoàn thành logic event.

Ví dụ một event có ba lần thử:

~~~text
Attempt 1: 120 ms, thất bại
Retry wait: 5 s
Attempt 2: 180 ms, thất bại
Retry wait: 30 s
Attempt 3: 90 ms, thành công
~~~

Handler execution duration của các attempt lần lượt là 120 ms, 180 ms và 90 ms. Tổng thời gian event age từ lúc được tạo đến khi hoàn tất gần 35 giây cộng thời gian dispatch và các khoảng xử lý khác.

Nếu chỉ báo cáo trung bình handler duration, hệ thống có thể không nhận ra event đã chờ gần nửa phút mới hoàn tất. Nên theo dõi riêng:

- Duration mỗi attempt.
- Số lần retry trên mỗi handler.
- Thời gian chờ retry nếu có thể đo.
- Event age tại thời điểm terminal.
- Số event đang ở trạng thái incomplete hoặc retry pending.

Khi resubmit publication qua Event Publication Registry, lần thực thi lại cũng là một attempt mới. Hãy giữ event ID ổn định để có thể liên kết các lần thử trong log và trace. Không đưa event ID thành metric tag; dùng trace hoặc log để truy vết.

## 13. Đồng hồ, độ chính xác và dữ liệu bất thường

Duration trong cùng một process nên đo bằng timer monotonic. Không dùng LocalDateTime hoặc hai lần Instant.now() để đo handler execution vì đồng hồ wall-clock có thể được điều chỉnh.

Timestamp event và broker có thể đến từ máy khác. Để tính event age hoặc queue wait:

- Dùng UTC và định dạng timestamp có timezone rõ ràng.
- Đồng bộ đồng hồ các máy bằng NTP hoặc cơ chế tương đương.
- Theo dõi timestamp âm hoặc vượt xa giới hạn nghiệp vụ.
- Không trộn epoch seconds với epoch milliseconds.
- Xác định timestamp biểu diễn event occurredAt, publish time hay broker enqueue time.

Độ chính xác của timer cũng cần phù hợp. Không cần đo microsecond cho một handler có SLO tính bằng giây nếu chi phí instrumentation không đem lại giá trị. Nên dùng cùng đơn vị chuẩn và để Micrometer xuất đơn vị phù hợp với backend.

Nếu event không có occurredAt, vẫn có thể đo handler duration và queue wait khi có timestamp broker. Không tự gán thời điểm consumer nhận làm thời điểm event xảy ra rồi đặt tên metric là event age; cách đó sẽ làm metric đánh giá thấp độ trễ thực tế.

## 14. Kiểm thử metric độ trễ handler

Kiểm thử instrumentation cần xác nhận Timer được ghi cho cả thành công và thất bại, exception vẫn được truyền ra và tag có cardinality giới hạn.

Có thể dùng SimpleMeterRegistry trong unit test:

~~~java
@Test
void recordsHandlerDurationWhenProcessingSucceeds() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    AccountingEventListener listener =
        new AccountingEventListener(service, registry);

    listener.on(orderPaidEvent);

    Timer timer = registry.find("application.events.handler.duration")
        .tag("handler", "accounting")
        .tag("event_type", "order_paid")
        .tag("outcome", "success")
        .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
    assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
        .isGreaterThanOrEqualTo(0);
}
~~~

Các tình huống nên kiểm tra:

- Handler thành công tạo một lần ghi Timer với outcome success.
- Handler ném exception vẫn ghi duration với outcome error.
- Exception tiếp tục truyền ra để publication/retry xử lý.
- Handler được gọi nhiều lần tạo count tương ứng số attempt.
- Timer dùng đúng handler, event type và outcome.
- Metric không chứa eventId, orderId hoặc correlationId làm tag.
- Event age không bị ghi nhận âm khi timestamp không hợp lệ.
- Queue wait chỉ được ghi khi có timestamp nguồn phù hợp.
- Histogram có bucket/SLO đã cấu hình trong registry xuất dữ liệu.
- Listener enqueue tác vụ bất đồng bộ không bị nhầm với thời gian worker thực thi.

Unit test với SimpleMeterRegistry kiểm tra logic ghi meter. Integration test với registry/exporter thực tế mới xác nhận naming convention, histogram và endpoint scrape. Không cần dùng sleep dài để tạo latency; có thể kiểm tra count và sự hiện diện của meter, hoặc dùng clock/abstraction có thể kiểm soát trong test.

## 15. Những lỗi thường gặp

**Chỉ đo thời gian publisher phát event.** Điều đó không phản ánh thời gian listener xử lý. Hãy đo tại ranh giới handler.

**Gộp queue wait với handler duration.** Hai khoảng có nguyên nhân khác nhau. Hãy đặt metric riêng để tìm đúng nút thắt.

**Chỉ theo dõi average.** Average có thể che tail latency. Hãy dùng histogram và p95/p99.

**Chỉ đo lần thành công.** Lần thất bại có thể chậm và tạo backlog. Hãy ghi duration cho cả error và success.

**Nuốt exception để ghi metric.** Instrumentation không được làm thay đổi hành vi lỗi. Hãy ghi metric trong finally rồi ném lại exception.

**Dùng event ID hoặc order ID làm tag.** Cardinality tăng nhanh và làm hệ thống metric quá tải. Hãy giữ tag ở các chiều có tập giá trị nhỏ.

**Tính duration bằng wall-clock.** Đồng hồ bị điều chỉnh có thể tạo duration âm hoặc sai. Hãy dùng Timer hoặc monotonic clock.

**Coi một attempt là toàn bộ event.** Retry wait có thể chiếm phần lớn event age. Hãy đo attempt duration và event age riêng.

**Giả định Spring Modulith có sẵn metric handler theo tên cố định.** Cần instrument listener hoặc service và xác minh registry thực tế.

**Coi metric là công cụ truy vết từng event.** Metric dùng cho xu hướng tổng hợp. Hãy dùng log và trace có event ID/correlation ID để điều tra một lần xử lý.

## Kết luận

Metric độ trễ handler cần xác định ranh giới đo rõ ràng và tách handler execution duration khỏi queue wait, event age, dispatch delay và end-to-end workflow duration. Micrometer Timer phù hợp để đo từng lần thực thi; histogram và percentile giúp nhận biết tail latency, còn Counter và metric backlog bổ sung bức tranh về lỗi và retry.

Trong Spring Modulith, hãy instrument tại listener hoặc service thực sự thực hiện công việc. Ghi nhận cả lần thành công lẫn thất bại, giữ exception propagation, dùng tag có cardinality thấp và kết hợp metric với log, trace cùng Event Publication Registry. Khi các khoảng thời gian được đo riêng, đội phát triển có thể xác định event chậm vì handler, executor, broker hay bước chờ retry và cải thiện đúng thành phần.

