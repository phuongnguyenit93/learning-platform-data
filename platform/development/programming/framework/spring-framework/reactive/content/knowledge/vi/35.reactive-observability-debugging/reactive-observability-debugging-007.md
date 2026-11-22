# Micrometer cho chuỗi Reactor và tránh nhãn có quá nhiều giá trị

Một chuỗi Reactor có thể xử lý hàng nghìn request và phát hàng triệu phần tử. Chỉ đo HTTP endpoint thường chưa đủ để biết đoạn pipeline nào chậm, có bao nhiêu subscription lỗi, stream kết thúc bình thường hay bị cancel, hoặc scheduler có hàng đợi tăng cao hay không. Micrometer cung cấp một mô hình đo lường độc lập backend; Reactor tích hợp Micrometer để quan sát publisher và scheduler mà không cần tự viết listener cho từng tín hiệu.

Một lỗi vận hành phổ biến khi thêm metrics là đưa giá trị thay đổi gần như mỗi request vào metric tag, chẳng hạn orderId, userId, sessionId, requestId hoặc URL đầy đủ. Mỗi tổ hợp tag tạo một meter/time series riêng. Số series có thể tăng mạnh, kéo theo RAM, chi phí ingest, dung lượng lưu trữ và thời gian truy vấn. Micrometer Observation phân biệt low-cardinality và high-cardinality key values để tách dữ liệu phù hợp cho metrics và tracing.

Bài học thuộc nhóm **Quan sát và gỡ lỗi** của module Spring Framework - reactive. Nội dung tập trung vào cách instrument Flux/Mono, đọc meter Reactor, đo Scheduler, sử dụng Observation, thiết kế tag có miền giá trị hữu hạn và giới hạn rủi ro cardinality trong Spring Boot 3.3.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Micrometer MeterRegistry và ObservationRegistry.
- Phân biệt metrics, logs và distributed traces.
- Biết vì sao Reactor metrics nằm trong module riêng reactor-core-micrometer.
- Dùng Micrometer.metrics(MeterRegistry) với tap() để đo publisher.
- Đặt tên chuỗi bằng name() và thêm tag bằng tag().
- Dùng Micrometer.observation(ObservationRegistry) để tạo observation cho chuỗi reactive.
- Phân biệt metrics-level instrumentation với observation-level instrumentation.
- Đo Scheduler bằng Micrometer.timedScheduler().
- Hiểu meter Reactor như flow duration, subscribed, requested, onNext delay và scheduler tasks.
- Định nghĩa cardinality, time series và sự bùng nổ số tổ hợp tag.
- Phân biệt low-cardinality và high-cardinality values.
- Biết vì sao tag trực tiếp trên Micrometer.metrics luôn là metric dimension.
- Dùng Observation.lowCardinalityKeyValue() và highCardinalityKeyValue() đúng mục đích.
- Thiết kế tên meter, tag, route template và common tags ổn định.
- Dùng MeterFilter như một lớp giới hạn bổ sung.
- Kiểm thử meter bằng SimpleMeterRegistry.
- Xem metrics qua Spring Boot Actuator và Prometheus endpoint.
- Tránh ghi dữ liệu cá nhân, secret hoặc định danh request vào metric labels.

## 2. Metrics, logs và traces có vai trò khác nhau

Ba tín hiệu quan sát bổ sung cho nhau:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Metrics | Hệ thống đang khỏe hay có xu hướng bất thường? | Tỷ lệ lỗi, throughput, latency p95, queue size |
| Logs | Sự kiện cụ thể đã xảy ra là gì? | Order O-1001 bị từ chối vì trạng thái không hợp lệ |
| Traces | Một request đi qua những service/span nào và tốn thời gian ở đâu? | Gateway → Order API → Inventory → Database |

Metrics thường được tổng hợp theo thời gian và chiều dữ liệu. Chúng phù hợp cho dashboard, alert và phân tích xu hướng. Logs chứa chi tiết từng sự kiện. Trace biểu diễn đường đi của một request qua nhiều thành phần, gồm span, thời gian và attributes.

Không nên biến metrics thành kho lưu trữ sự kiện. Một metric như orders.pipeline.flow.duration có thể cho biết phân bố thời gian xử lý; nó không cần một time series riêng cho từng order. Khi cần tìm order cụ thể, dùng trace/log có quyền truy cập và retention phù hợp.

### Micrometer là gì?

Micrometer là facade cho metrics. Ứng dụng ghi Counter, Timer, Gauge hoặc DistributionSummary qua MeterRegistry; registry tương ứng chuyển dữ liệu sang Prometheus, OTLP, Datadog, Graphite hoặc backend được hỗ trợ.

Micrometer Observation bổ sung abstraction chung cho một đơn vị công việc. Tùy ObservationHandler được cài đặt, một observation có thể tạo metrics, trace hoặc tín hiệu khác.

| Registry | Mục đích | API thường dùng |
| --- | --- | --- |
| MeterRegistry | Ghi và truy vấn meters | Counter, Timer, Gauge, DistributionSummary |
| ObservationRegistry | Bắt đầu/kết thúc observation và xử lý contextual key values | Observation.createNotStarted(), ObservationHandler |

Trong Spring Boot có Actuator, các registry và ObservationRegistry phù hợp thường được auto-configure. Hãy inject bean do Spring quản lý; không tạo global static registry riêng rồi kỳ vọng nó nhận mọi cấu hình của Boot.

## 3. Reactor tích hợp Micrometer qua module riêng

Với Reactor 3.5 trở lên, API instrumentation chính thức nằm trong artifact:

~~~xml
<dependency>
  <groupId>io.projectreactor</groupId>
  <artifactId>reactor-core-micrometer</artifactId>
</dependency>
~~~

Module này cung cấp các entry point:

- Micrometer.metrics(meterRegistry): thu thập metrics chi tiết của publisher.
- Micrometer.observation(observationRegistry): quan sát vòng đời của một chuỗi reactive.
- Micrometer.timedScheduler(...): bọc Scheduler để đo công việc được submit qua wrapper.

Các API nhận registry tường minh. Điều đó giúp code biết metrics/observation được ghi vào registry nào, thay vì dựa vào một registry global ẩn.

Các cách instrumentation Reactor cũ dựa trên reactor.util.Metrics và operator metrics legacy đã được thay thế bằng reactor-core-micrometer. Với code mới trên Reactor 3.6, ưu tiên Micrometer.metrics hoặc Micrometer.observation kết hợp tap(). Thêm micrometer-core vào classpath chưa đủ để gọi các API mới; cần dependency đúng module.

## 4. Đo một Flux hoặc Mono bằng Micrometer.metrics

Để bật metrics cho publisher:

~~~java
Flux<OrderEvent> measured = Flux.just(
        new OrderEvent("created"),
        new OrderEvent("validated"))
    .name("orders.pipeline")
    .tag("operation", "process")
    .tap(Micrometer.metrics(meterRegistry));
~~~

Ý nghĩa:

1. Flux.just tạo source.
2. name() đặt prefix ổn định cho meter.
3. tag() thêm chiều dữ liệu có miền giá trị nhỏ.
4. tap() cài SignalListener do Reactor Core Micrometer cung cấp.
5. Khi publisher được subscribe và kết thúc, các meter tương ứng được cập nhật.

Phải có subscription thì pipeline mới chạy và metrics mới được ghi. Tạo Flux nhưng không subscribe không tạo một lần xử lý thực tế.

~~~java
measured.subscribe(
    event -> log.info("event={}", event),
    error -> log.error("pipeline failed", error));
~~~

Trong ứng dụng WebFlux, thường không tự subscribe trong service/controller. Hãy trả Flux/Mono để framework quản lý subscription. subscribe() ở ví dụ trên chỉ minh họa consumer độc lập.

### Vì sao name() quan trọng?

~~~java
.name("orders.pipeline")
~~~

Các meter được tạo tại instrumentation point dùng prefix orders.pipeline. Nếu không đặt name(), Reactor dùng prefix mặc định reactor.

Tên meter nên mô tả một luồng nghiệp vụ ổn định. Không đưa order ID hoặc user ID vào tên:

~~~java
// Không nên: mỗi order tạo một tên meter khác nhau.
.name("orders." + orderId)
~~~

Dùng tên ổn định rồi phân tích theo tag hữu hạn.

## 5. Đặt instrumentation ở đúng vị trí trong pipeline

tap(Micrometer.metrics(...)) đo chuỗi tại điểm được gắn. Hãy đặt nó ở vị trí phản ánh đơn vị công việc muốn quan sát.

~~~java
Flux<OrderEvent> result = source
    .filter(this::isValid)
    .map(this::normalize)
    .name("orders.validation")
    .tag("operation", "validate")
    .tap(Micrometer.metrics(meterRegistry))
    .flatMap(this::persist);
~~~

Trong ví dụ này, instrumentation được đặt sau validate/normalize và trước persist. Nó quan sát publisher từ điểm đó theo lifecycle của sequence được tap. Nếu muốn đo cả persist, đặt tap sau persist hoặc tạo observation bao trọn operation.

~~~java
Flux<OrderEvent> result = source
    .filter(this::isValid)
    .map(this::normalize)
    .flatMap(this::persist)
    .name("orders.process")
    .tag("operation", "create")
    .tap(Micrometer.metrics(meterRegistry));
~~~

Đây là instrumentation cho pipeline tổng thể.

Không gắn metrics vào mọi operator một cách máy móc. Quá nhiều điểm instrumentation có thể tạo số meter lớn, tăng overhead và làm dashboard khó đọc. Chọn boundary có ý nghĩa: ingest, validation, persistence, outbound call hoặc một nghiệp vụ end-to-end.

Nếu pipeline có retry, metrics gắn trước/sau retry có thể mô tả số lần subscription hoặc lifecycle khác nhau. Hãy quyết định bạn muốn đo một request nghiệp vụ tổng thể hay từng attempt. Đặt tap theo mục tiêu rồi kiểm thử số subscription và error status.

## 6. Các meter Reactor thường gặp

Reactor Core Micrometer cung cấp nhiều meter theo prefix đã đặt.

| Meter suffix | Loại | Ý nghĩa |
| --- | --- | --- |
| .flow.duration | DistributionSummary | Thời gian từ subscription tới terminal signal hoặc cancellation |
| .malformed.source | Counter | Số tín hiệu sai từ source, ví dụ onNext sau onComplete |
| .onNext.delay | Timer | Khoảng cách giữa các onNext, hoặc từ onSubscribe tới onNext đầu |
| .requested | DistributionSummary | Tổng demand được yêu cầu bởi subscriber |
| .subscribed | Counter | Số subscription vào sequence |
| .scheduler.tasks.active | LongTaskTimer | Công việc scheduler đang hoạt động |
| .scheduler.tasks.completed | Timer | Thời gian hoàn thành task |
| .scheduler.tasks.pending | LongTaskTimer | Task đang chờ được thực thi |
| .scheduler.tasks.submitted | Counter | Số task được submit, phân biệt loại submission |

Các meter cụ thể phụ thuộc loại instrumentation và phiên bản Reactor. Với publisher metrics, prefix động lấy từ name(); nếu không có name thì thường là reactor.

### Flow duration và terminal status

Flow duration đo vòng đời từ subscribe tới khi chuỗi kết thúc hoặc bị cancel. Status có thể phân biệt:

- completed: có onNext rồi onComplete.
- completedEmpty: complete mà không có onNext.
- error: kết thúc bằng onError.
- cancelled: downstream hủy subscription.

Status hữu ích khi pipeline không hoàn tất theo cách dự kiến. Tỷ lệ cancellation cao có thể do client đóng kết nối, timeout, downstream không còn cần dữ liệu hoặc logic ứng dụng chủ động cancel.

### OnNext delay

OnNext delay đo khoảng cách giữa các tín hiệu dữ liệu. Nếu một stream vốn phát đều nhưng độ trễ tăng, có thể có tắc nghẽn downstream, source chậm, scheduler bận hoặc external dependency chậm.

Nó không tự giải thích nguyên nhân. Kết hợp với trace, scheduler metrics, queue metrics và log để xác định điểm nghẽn.

### Requested amount

Requested amount phản ánh demand của subscriber. Nó hữu ích khi phân tích backpressure. Nếu subscriber yêu cầu Long.MAX_VALUE, stream đã có demand không giới hạn ở phía đó; không nên suy luận rằng toàn hệ thống không có backpressure chỉ từ một meter.

## 7. Đo Observation của một chuỗi reactive

Micrometer.metrics tập trung vào các metrics chi tiết của publisher. Micrometer.observation tạo một observation cho lifecycle của chuỗi. Tùy ObservationRegistry handlers, observation có thể tạo timer, trace hoặc cả hai.

~~~java
Flux<OrderEvent> observed = source
    .name("orders.pipeline")
    .tap(Micrometer.observation(observationRegistry));
~~~

Đây là cách đơn giản để tạo observation cho chuỗi. ObservationRegistry phải được cung cấp rõ ràng.

### Observation với tên và key values tùy chỉnh

~~~java
Flux<OrderEvent> observed = source
    .tap(Micrometer.observation(
        observationRegistry,
        registry -> Observation.createNotStarted(
                "orders.process",
                registry)
            .lowCardinalityKeyValue("operation", "create")
            .lowCardinalityKeyValue("region", "ap-southeast-1")
            .highCardinalityKeyValue("order.id", orderId)
    ));
~~~

Ở đây:

- orders.process là tên observation ổn định.
- operation có tập giá trị nhỏ như create, update, cancel.
- region lấy từ danh sách region hữu hạn.
- order.id là định danh riêng cho một đơn hàng, có cardinality cao.

Theo quy tắc mặc định của Spring Boot Observation handlers, low-cardinality key values được thêm vào metrics và traces; high-cardinality key values chỉ được thêm vào traces. Muốn high-cardinality value xuất hiện ở trace, ứng dụng cần cấu hình tracing handler/bridge phù hợp. Nếu chỉ có metrics handler, giá trị high-cardinality không trở thành metric label.

Không đưa email, token, địa chỉ, thông tin thanh toán hoặc dữ liệu cá nhân vào trace chỉ vì API cho phép high-cardinality key. Tracing vẫn cần chính sách bảo mật, quyền truy cập và retention.

## 8. Micrometer.metrics và Micrometer.observation khác nhau thế nào?

| Tiêu chí | Micrometer.metrics | Micrometer.observation |
| --- | --- | --- |
| Entry point | MeterRegistry | ObservationRegistry |
| API Reactor | tap(Micrometer.metrics(registry)) | tap(Micrometer.observation(registry)) |
| Mục tiêu | Các meter chi tiết của publisher | Lifecycle của một đơn vị công việc |
| Tag | name() và tag() gắn vào meter dimensions | low/high cardinality key values |
| Trace | Không tự tạo span chỉ từ metrics API | Có thể tạo span nếu registry có tracing handler |
| Dùng khi | Cần demand, subscription, flow duration, onNext delay | Cần observation thống nhất metrics/tracing |

Không nhất thiết gắn cả hai API vào cùng một publisher. Nếu cả hai cùng tạo timer cho cùng một đoạn công việc, bạn có thể có dữ liệu chồng lặp. Chọn một loại instrumentation cho mỗi mục tiêu hoặc ghi rõ mục đích của từng loại.

## 9. Cardinality là gì?

Cardinality là số lượng giá trị phân biệt mà một chiều dữ liệu có thể nhận. Trong metrics, một time series được xác định bởi tên metric và tập hợp tag/label values.

~~~text
orders.pipeline.flow.duration{
  operation="create",
  region="ap-southeast-1",
  status="completed"
}
~~~

Một tổ hợp tag khác là một time series khác:

~~~text
orders.pipeline.flow.duration{
  operation="cancel",
  region="ap-northeast-1",
  status="error"
}
~~~

Nếu có operation 4 giá trị, region 5 giá trị và status 4 giá trị, số tổ hợp tối đa là 4 × 5 × 4 = 80 series cho một metric name, nếu mọi tổ hợp đều xuất hiện.

Nếu thêm orderId có 1.000.000 giá trị phân biệt, số tổ hợp lý thuyết tăng thành 80.000.000. Đây là worst-case theo tích số các miền giá trị; thực tế còn phụ thuộc tổ hợp nào phát sinh.

### Vì sao cardinality cao nguy hiểm?

Mỗi series có thể cần bộ nhớ, metadata, index, scrape/export work và lưu trữ. Cardinality tăng gây:

- RAM tăng ở ứng dụng hoặc metrics backend.
- Chi phí lưu trữ và ingest cao hơn.
- Prometheus scrape/query chậm.
- Dashboard tải lâu và alert khó ổn định.
- Nhiều series ngắn hạn liên tục được tạo.
- Quota của backend bị vượt.
- Khó giữ metric schema ổn định giữa các phiên bản.

Số sample lớn và số series lớn là hai vấn đề khác nhau. Một metric có ít series nhưng được cập nhật thường xuyên có thể có nhiều sample; một metric có hàng triệu label combinations có cardinality cao dù mỗi series chỉ có ít sample.

## 10. Low cardinality và high cardinality

Low-cardinality là giá trị có miền hữu hạn, nhỏ và ổn định. High-cardinality là giá trị có thể sinh ra rất nhiều biến thể, thường tăng theo số request hoặc entity.

| Low-cardinality thường phù hợp cho metrics | High-cardinality thường không phù hợp làm metric tag |
| --- | --- |
| operation=create/update/delete | orderId |
| outcome=success/error | userId |
| status=completed/error/cancelled | sessionId |
| region từ allowlist nhỏ | requestId |
| paymentMethod=card/bank | traceId |
| route=/orders/{id} | raw URL /orders/12345 |
| environment=dev/staging/prod | email hoặc IP |
| exceptionType từ tập class đã biết | exception message động |

Low cardinality không có một con số chung áp dụng cho mọi backend. Một tag có 20 giá trị có thể ổn ở một hệ thống nhưng quá lớn ở một metric rất nóng. Hãy đánh giá số series dự kiến, tần suất cập nhật, quota backend và nhu cầu truy vấn.

### Giá trị hữu hạn phải thật sự được giới hạn

Nếu tag region lấy trực tiếp từ query string, người dùng có thể gửi region=abc-1, region=abc-2 và vô số giá trị khác. Tên tag nghe có vẻ low-cardinality không đảm bảo value thực sự bị giới hạn.

~~~java
private static final Set<String> REGIONS = Set.of(
    "ap-southeast-1",
    "ap-northeast-1");

private String normalizeRegion(String input) {
    return input != null && REGIONS.contains(input)
        ? input
        : "other";
}
~~~

Tag chỉ nhận một trong ba giá trị: hai region đã định nghĩa hoặc other.

## 11. Lỗi nguy hiểm: đưa ID vào Reactor tag()

Ví dụ không nên:

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("orderId", orderId)
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Mỗi orderId khác nhau tạo một metric dimension mới. Với hàng triệu order, số series có thể tăng rất nhanh.

Một lỗi tương tự là đưa userId, requestId hoặc sessionId vào tag:

~~~java
.tag("userId", userId)
.tag("requestId", requestId)
.tag("sessionId", sessionId)
~~~

Micrometer.metrics không có cơ chế tự hiểu rằng tag này high-cardinality và chuyển nó sang trace. Mỗi tag từ Reactor tag() được dùng như một chiều dữ liệu của meter.

### Cách sửa

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("operation", "lookup")
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Nếu cần orderId để tìm request cụ thể, dùng log có structured field hoặc trace attribute có kiểm soát. Đừng hy sinh sức khỏe của metrics backend để có thể truy vấn một order bằng Prometheus.

## 12. Dùng high-cardinality values trong Observation đúng cách

Observation có API tách rõ hai nhóm:

~~~java
Observation.createNotStarted("orders.lookup", observationRegistry)
    .lowCardinalityKeyValue("operation", "lookup")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> repositoryLookup(orderId));
~~~

Khi dùng Spring Boot với Observation handlers mặc định:

- operation và outcome được đưa vào metrics và traces.
- order.id chỉ được đưa vào traces.
- order.id không làm phát sinh một metric series cho mỗi order.

Với reactive chain, có thể dùng Micrometer.observation trong tap() như phần trước để observation theo lifecycle của publisher.

### High-cardinality không có nghĩa dữ liệu nào cũng nên ghi

Trace hữu ích để điều tra một request cụ thể, nhưng có thể chứa dữ liệu nhạy cảm. Tránh lưu token, password, cookie, email hoặc payload đầy đủ. ID nội bộ cũng cần đánh giá retention, access control và chính sách dữ liệu.

### Nếu không có tracing handler thì sao?

ObservationRegistry có thể chỉ có meter handler. Khi đó high-cardinality key value không được chuyển thành metric theo semantics của Spring Boot, nhưng cũng có thể không được xuất đi đâu. Nếu cần trace, cấu hình Micrometer Tracing bridge và exporter tương ứng; không đổi high-cardinality value thành metric tag để bù cho việc chưa có tracing.

## 13. Tên metric và route template phải ổn định

Tên metric là một phần schema vận hành. Hãy đặt tên theo nghiệp vụ và không nhúng tham số request.

Nên:

~~~java
.name("orders.pipeline")
.name("inventory.reservation")
.name("payments.authorize")
~~~

Không nên:

~~~java
.name("orders." + orderId)
.name("users." + username)
.name("http." + request.getURI())
~~~

Với HTTP route, dùng route template thay vì raw path. Ví dụ /orders/{id} có miền route nhỏ; /orders/10001, /orders/10002, ... tạo nhiều giá trị khác nhau.

Một quy ước tốt:

- Tên meter ổn định và có namespace.
- Tag key nhất quán, không đổi tên giữa các release.
- Tag values lấy từ enum hoặc allowlist.
- Không gắn raw URL, query string hoặc exception message.
- Giữ cùng tập tag keys cho cùng metric name.
- Dùng common tags cho environment/region/instance khi chúng có miền giá trị phù hợp.

Một số backend, trong đó có Prometheus, kỳ vọng các series cùng metric name có schema label nhất quán. Đừng tùy tiện thêm tag key ở một nhánh pipeline nhưng bỏ nó ở nhánh khác.

## 14. MeterFilter: lớp bảo vệ bổ sung

Micrometer MeterFilter cho phép deny, transform hoặc giới hạn meter registration. Nó hữu ích để ngăn một tag bất ngờ tạo vô số series.

~~~java
@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter tenantTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "orders.pipeline",
            "tenant",
            20,
            MeterFilter.deny());
    }
}
~~~

Ý nghĩa:

- Chỉ áp dụng cho meter có tên bắt đầu bằng orders.pipeline.
- Xem giá trị tag tenant.
- Cho phép tối đa 20 giá trị phân biệt cho nhóm meter phù hợp.
- Khi vượt ngưỡng, filter cuối trả DENY cho meter mới tương ứng.

Spring Boot tự đăng ký các MeterFilter bean vào Spring-managed MeterRegistry.

### MeterFilter không thay thế thiết kế tag tốt

Nếu filter cho phép 20 tenant đầu tiên rồi từ chối phần còn lại, metrics của các tenant sau không được ghi như dự kiến. Nó không gom chúng thành other, không sửa lại tag và không tự báo cho đội vận hành rằng schema sai.

Vì vậy:

1. Thiết kế tag có miền hữu hạn ngay từ đầu.
2. Dùng MeterFilter làm giới hạn phòng vệ.
3. Theo dõi số meter và cảnh báo khi filter bắt đầu deny.
4. Kiểm tra prefix và tag key để filter chỉ ảnh hưởng meter mong muốn.
5. Không đặt ngưỡng quá thấp khiến dữ liệu hợp lệ bị loại bỏ.

Có thể dùng MeterFilter.ignoreTags("requestId", "userId") để bỏ một số tag khỏi meter IDs, nhưng đây là biện pháp xử lý hậu quả. Tốt hơn là không gắn những tag này ngay từ đầu.

## 15. Common tags trong Spring Boot

Common tags áp dụng cho nhiều meters. Ví dụ:

~~~properties
management.metrics.tags.application=order-service
management.metrics.tags.environment=staging
~~~

Các giá trị này nên ổn định trong từng deployment. Đừng đưa pod request ID hoặc build timestamp thay đổi liên tục vào common tags.

Với Observation, có thể cấu hình common low-cardinality key values:

~~~properties
management.observations.key-values.region=ap-southeast-1
management.observations.key-values.stack=production
~~~

Các giá trị này được thêm vào observations theo cấu hình Spring Boot. Nếu một property lấy giá trị tùy ý từ environment hoặc tenant mà có miền rất lớn, nó vẫn có thể tạo cardinality cao. Tên common không tự làm cho value trở thành low-cardinality.

## 16. Đo Scheduler bằng Micrometer.timedScheduler

Reactor thực hiện công việc bất đồng bộ thông qua Scheduler. Khi cần quan sát scheduler riêng, có thể bọc scheduler:

~~~java
Scheduler original = Schedulers.newParallel(
    "order-worker", 4);

Scheduler measured = Micrometer.timedScheduler(
    original,
    meterRegistry,
    "orders.scheduler");
~~~

Sau đó dùng wrapper cho tác vụ:

~~~java
Mono<Void> work = Mono.fromRunnable(
        () -> performCpuWork())
    .subscribeOn(measured)
    .then();
~~~

Chỉ những Runnable được submit qua wrapper measured mới được đo. Nếu cùng lúc có code submit trực tiếp qua original, các task đó không được wrapper instrument.

Khi tạo Scheduler riêng, cần dispose khi application shutdown:

~~~java
@Bean(destroyMethod = "dispose")
Scheduler orderWorkerScheduler(MeterRegistry registry) {
    Scheduler original = Schedulers.newParallel(
        "order-worker", 4);

    return Micrometer.timedScheduler(
        original, registry, "orders.scheduler");
}
~~~

Với scheduler do ứng dụng tạo riêng, cần quản lý cleanup. Không bọc cùng scheduler nhiều lần mà không có lý do, vì có thể đo trùng hoặc chỉ đo một đường submit.

### Đọc scheduler metrics

Scheduler meters có thể cho biết số task đã submit, số task đã hoàn tất, task đang hoạt động, task đang chờ và thời gian thực thi. Pending task tăng kéo dài có thể chỉ ra scheduler quá tải, blocking operation hoặc concurrency chưa hợp lý. Kết hợp CPU, thread pool, queue, GC và external dependency metrics để tìm nguyên nhân.

## 17. Metrics và Observation không tự động có nghĩa tracing đã bật

Spring Boot Actuator tự cấu hình Micrometer MeterRegistry và ObservationRegistry. Nhưng để xuất trace, ứng dụng cần tracing bridge và exporter tương ứng.

Một cấu hình metrics cơ bản có thể có:

- spring-boot-starter-actuator.
- micrometer-registry-prometheus.
- reactor-core-micrometer.

Để xuất trace, có thể bổ sung Micrometer Tracing bridge cho OpenTelemetry hoặc Brave và exporter phù hợp. Đừng giả định high-cardinality Observation key value đã xuất đi chỉ vì code gọi highCardinalityKeyValue().

Spring Boot có thể tự instrument HTTP server, WebClient hoặc các integration được hỗ trợ. Nếu bạn lại tạo một observation bao toàn bộ cùng operation mà không có ranh giới khác biệt, metrics có thể bị đếm hai lần. Hãy chọn boundary rõ ràng:

- HTTP server observation: thời gian request tổng thể.
- Reactor pipeline observation: thời gian một luồng nghiệp vụ bên trong.
- Scheduler metrics: hiệu năng thực thi task.
- Database observation: thời gian truy vấn.

## 18. Context propagation cho Observation trong Reactor

Observation context có thể cần được chuyển qua thread và reactive pipeline. Spring Boot 3.3 có property:

~~~properties
spring.reactor.context-propagation=auto
~~~

Mặc định là limited. Chế độ auto bật automatic context propagation cho các subscription mới, giúp ThreadLocal values được khôi phục từ Reactor Context ở các điểm thực thi phù hợp.

Cần nhớ:

- Context propagation không làm giảm cardinality.
- Nó không tự biến một tag động thành high-cardinality trace attribute.
- Nó không thay thế việc đặt đúng low/high key values.
- Hook áp dụng cho subscription mới; nên cấu hình từ startup.
- ThreadLocal vẫn phải được cleanup để tránh rò rỉ dữ liệu sang công việc dùng lại thread.
- Với executor tùy chỉnh hoặc @Async, có thể cần ContextPropagatingTaskDecorator.

Nếu chỉ dùng Reactor metrics với MeterRegistry, không cần bật auto context propagation chỉ để ghi meter. Bật khi ứng dụng cần truyền observation/tracing context qua các ranh giới thread theo thiết kế.

## 19. Ví dụ sai và đúng: theo dõi đơn hàng

### Sai: mỗi đơn hàng tạo một time series

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("orderId", orderId)
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Mỗi orderId khác nhau tạo một metric dimension mới. Với hàng triệu order, số series có thể tăng rất nhanh.

### Đúng: metric dùng chiều dữ liệu hữu hạn

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("operation", "lookup")
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Nếu cần phân biệt found, missing hoặc error, thiết kế status tag theo terminal signal hoặc Observation convention có miền giá trị nhỏ. Đừng gắn một giá trị cố định sai với mọi outcome.

### Đúng: ID riêng được giữ trong trace

~~~java
public Mono<Order> findOrderObserved(String orderId) {
    return repository.findById(orderId)
        .tap(Micrometer.observation(
            observationRegistry,
            registry -> Observation.createNotStarted(
                    "orders.lookup",
                    registry)
                .lowCardinalityKeyValue(
                    "operation", "lookup")
                .highCardinalityKeyValue(
                    "order.id", orderId)));
}
~~~

Order ID không trở thành metric dimension trong Spring Boot default Observation handler; nó có thể xuất hiện ở trace nếu tracing được cấu hình. Nếu trace có dữ liệu nhạy cảm, áp dụng chính sách redaction và access control.

## 20. Project thực hành Java 17+ với Spring Boot 3.3.5

Project dưới đây cung cấp một WebFlux endpoint phát OrderEvent, đo publisher bằng Micrometer.metrics, và một lookup operation tạo Observation với order ID là high-cardinality trace attribute.

### Cấu trúc thư mục

~~~text
reactor-micrometer-demo/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example/observability
    │   │   ├── ObservabilityApplication.java
    │   │   ├── OrderEvent.java
    │   │   ├── OrderMetricsService.java
    │   │   ├── OrderController.java
    │   │   └── MetricsConfiguration.java
    │   └── resources/application.properties
    └── test
        └── java/com/example/observability
            └── ReactorMetricsTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactor-micrometer-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core-micrometer</artifactId>
    </dependency>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot dependency management cung cấp các phiên bản tương thích cho Reactor, Micrometer và Prometheus registry. reactor-core-micrometer là dependency riêng để sử dụng API Micrometer của Reactor.

### application.properties

~~~properties
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactor-micrometer-demo
management.metrics.tags.environment=dev

management.observations.key-values.region=ap-southeast-1
management.observations.key-values.stack=local

spring.reactor.context-propagation=auto
~~~

Các common values application, environment, region và stack có miền giá trị được kiểm soát. Không thay chúng bằng request ID, timestamp hoặc tên user.

Endpoint Prometheus được expose qua /actuator/prometheus. Chỉ expose các actuator endpoints cần thiết trong môi trường triển khai; cấu hình authentication/network policy phù hợp.

### ObservabilityApplication.java

~~~java
package com.example.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ObservabilityApplication.class, args);
    }
}
~~~

### OrderEvent.java

~~~java
package com.example.observability;

public record OrderEvent(
    String orderId,
    String status) {
}
~~~

Record là DTO response. orderId xuất hiện trong JSON response vì đó là dữ liệu nghiệp vụ; việc trả ID cho API client không có nghĩa phải dùng ID làm metric tag.

### OrderMetricsService.java

~~~java
package com.example.observability;

import java.util.Set;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderMetricsService {

    private static final Set<String> ALLOWED_REGIONS =
        Set.of("ap-southeast-1", "ap-northeast-1");

    private final MeterRegistry meterRegistry;
    private final ObservationRegistry observationRegistry;

    public OrderMetricsService(
            MeterRegistry meterRegistry,
            ObservationRegistry observationRegistry) {
        this.meterRegistry = meterRegistry;
        this.observationRegistry = observationRegistry;
    }

    public Flux<OrderEvent> events(String region) {
        String safeRegion =
            region != null && ALLOWED_REGIONS.contains(region)
                ? region
                : "other";

        return Flux.just(
                new OrderEvent("ord-1001", "created"),
                new OrderEvent("ord-1002", "validated"),
                new OrderEvent("ord-1003", "completed"))
            .name("orders.pipeline")
            .tag("operation", "process")
            .tag("region", safeRegion)
            .tap(Micrometer.metrics(meterRegistry));
    }

    public Mono<OrderEvent> lookup(String orderId) {
        return Mono.fromSupplier(
                () -> new OrderEvent(orderId, "found"))
            .tap(Micrometer.observation(
                observationRegistry,
                registry -> Observation.createNotStarted(
                        "orders.lookup",
                        registry)
                    .lowCardinalityKeyValue(
                        "operation", "lookup")
                    .highCardinalityKeyValue(
                        "order.id", orderId)));
    }
}
~~~

Điểm cần quan sát:

1. orders.pipeline là tên meter ổn định.
2. operation chỉ có một tập hành động hữu hạn.
3. region được map qua allowlist; mọi giá trị khác thành other.
4. orderId nằm trong response payload, không nằm trong metrics tag.
5. lookup dùng Observation API; order.id được đánh dấu high-cardinality.
6. MeterRegistry và ObservationRegistry được inject từ Spring Boot.

Nếu không có tracing handler, high-cardinality order.id có thể không được export; hãy thêm Micrometer Tracing và exporter khi cần trace cụ thể. Không đổi order.id thành tag để buộc nó xuất hiện ở metrics.

### OrderController.java

~~~java
package com.example.observability;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class OrderController {

    private final OrderMetricsService service;

    public OrderController(OrderMetricsService service) {
        this.service = service;
    }

    @GetMapping("/orders/events")
    public Flux<OrderEvent> events(
            @RequestParam(defaultValue = "ap-southeast-1")
            String region) {
        return service.events(region);
    }

    @GetMapping("/orders/{id}")
    public Mono<OrderEvent> lookup(@PathVariable String id) {
        return service.lookup(id);
    }
}
~~~

Controller trả publisher cho WebFlux. Framework subscribe và serialize response. Không gọi subscribe() trong controller chỉ để metrics được ghi; tap() nằm trong chain và metrics được ghi khi HTTP request subscribe tới publisher.

### MetricsConfiguration.java

~~~java
package com.example.observability;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter tenantTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "orders.pipeline",
            "tenant",
            20,
            MeterFilter.deny());
    }
}
~~~

Filter là giới hạn dự phòng nếu ai đó vô tình thêm tenant tag vào orders.pipeline. Ví dụ hiện tại không gắn tenant ID; nếu cần phân tích theo tenant, cân nhắc một tier/segment có miền giá trị nhỏ và được kiểm soát.

### ReactorMetricsTest.java

~~~java
package com.example.observability;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;

class ReactorMetricsTest {

    @Test
    void publisherRecordsMetersWithBoundedTags() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        Flux.range(1, 3)
            .name("orders.pipeline")
            .tag("operation", "process")
            .tag("region", "ap-southeast-1")
            .tap(Micrometer.metrics(registry))
            .blockLast();

        Meter subscribed = registry.getMeters().stream()
            .filter(meter ->
                meter.getId().getName().equals(
                    "orders.pipeline.subscribed"))
            .findFirst()
            .orElseThrow();

        assertEquals(
            "process",
            subscribed.getId().getTag("operation"));

        assertEquals(
            "ap-southeast-1",
            subscribed.getId().getTag("region"));

        assertFalse(
            subscribed.getId().getTags().stream()
                .anyMatch(tag ->
                    tag.getKey().equals("orderId")));

        registry.close();
    }

    @Test
    void meterFilterCapsDistinctValuesForOneTag() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                "orders.pipeline",
                "customerId",
                2,
                MeterFilter.deny()));

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-a").increment();

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-b").increment();

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-c").increment();

        long matchingMeters = registry.getMeters().stream()
            .filter(meter ->
                meter.getId().getName().equals(
                    "orders.pipeline.calls"))
            .count();

        assertEquals(2, matchingMeters);
        registry.close();
    }
}
~~~

Test đầu subscribe publisher bằng blockLast() để kích hoạt instrumentation rồi kiểm tra meter subscribed và các tag ổn định. Test thứ hai minh họa MeterFilter deny meter vượt ngưỡng tag value. Đây là unit test cho registry in-memory; nó không thay thế kiểm thử Prometheus scrape hoặc trace exporter.

### Chạy test

~~~bash
mvn -q clean test
~~~

Khi cả hai test pass, Maven kết thúc với exit code 0. Ví dụ không cần database hoặc external service.

### Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl "http://localhost:8080/api/orders/events?region=ap-southeast-1"
~~~

Response JSON mong đợi:

~~~json
[
  {"orderId":"ord-1001","status":"created"},
  {"orderId":"ord-1002","status":"validated"},
  {"orderId":"ord-1003","status":"completed"}
]
~~~

Gọi lookup:

~~~bash
curl "http://localhost:8080/api/orders/ord-1001"
~~~

Response:

~~~json
{"orderId":"ord-1001","status":"found"}
~~~

### Xem meter qua Actuator

~~~bash
curl "http://localhost:8080/actuator/metrics/orders.pipeline.subscribed"
~~~

Xem metrics Prometheus đã expose:

~~~bash
curl "http://localhost:8080/actuator/prometheus"
~~~

Tên metric khi xuất Prometheus có thể được chuẩn hóa theo naming convention của registry. Dùng endpoint metrics để tra cứu meter ID gốc; dùng endpoint prometheus để xem format thực tế mà backend scrape.

## 21. Kiểm thử và xác minh cardinality

Một test cardinality nên kiểm tra ít nhất:

- Meter name không chứa ID động.
- Tag keys có tập ổn định.
- Tag values đến từ enum/allowlist.
- Hai request với hai orderId khác nhau không tạo hai metric series khác nhau nếu orderId không phải tag.
- MeterFilter từ chối giá trị vượt ngưỡng khi có cấu hình guard.
- Observation high-cardinality field không bị chuyển nhầm thành metric tag.
- Số meters tăng trong giới hạn dự kiến sau một bộ request đại diện.

Có thể dùng SimpleMeterRegistry để kiểm tra meter IDs trong unit test. Với integration test, dùng PrometheusMeterRegistry hoặc endpoint Actuator để kiểm tra naming/labels được export.

### Đo trước và sau

1. Gửi 100 request với 100 order IDs khác nhau.
2. Đếm số meter của orders.pipeline.
3. Xác nhận số meter không tăng 100 lần chỉ vì ID khác nhau.
4. Thay đổi operation từ create sang cancel.
5. Xác nhận chỉ có số series tương ứng với miền operation đã thiết kế.

Không chỉ đo registry.getMeters().size() một lần ở startup. Cardinality có thể chỉ xuất hiện khi traffic thật đi qua những nhánh code hiếm.

### Quan sát metric count trong production

Theo dõi tổng số active series, số series mới theo thời gian, số meter bị MeterFilter deny, số tag values mới cho các key quan trọng, tỷ lệ series churn, query latency và scrape duration của backend.

Một spike cardinality thường xuất hiện sau khi release thêm một tag hoặc thay route name. Hãy đưa schema tag vào review code và test, giống như thay đổi database schema.

## 22. Những lỗi thường gặp và cách khắc phục

1. **Chỉ thêm micrometer-core nhưng thiếu reactor-core-micrometer.** API Micrometer của Reactor không có; thêm module đúng.
2. **Dùng reactor.util.Metrics legacy cho code mới.** Ưu tiên Micrometer.metrics() hoặc Micrometer.observation().
3. **Tạo publisher nhưng không subscribe.** Pipeline chưa chạy nên không có meter event; để WebFlux quản lý subscription hoặc subscribe trong consumer độc lập.
4. **Quên name().** Meter dùng prefix mặc định reactor; đặt tên ổn định theo nghiệp vụ.
5. **Đặt name theo orderId.** Mỗi ID tạo meter name mới; giữ prefix tĩnh.
6. **Đưa userId/orderId/requestId vào tag().** Mỗi giá trị tạo metric dimension mới; chuyển định danh sang trace/log phù hợp.
7. **Cho rằng Micrometer.metrics tự nhận biết high-cardinality.** Mọi Reactor tag() đều là metric tag; API không tự chuyển tag động sang trace.
8. **Dùng Observation.highCardinalityKeyValue rồi kỳ vọng Prometheus có label đó.** Theo handler mặc định của Boot, high-cardinality chỉ dành cho trace.
9. **Không có tracing exporter nhưng kỳ vọng trace attribute được lưu.** Thêm bridge/exporter hoặc chấp nhận high-cardinality key không được xuất.
10. **Gắn raw URL làm tag.** ID path và query string có thể tạo vô số series; dùng route template.
11. **Dùng exception message làm tag.** Message thường chứa ID, input hoặc text động; dùng exception class hoặc outcome hữu hạn.
12. **Gắn IP/email/token vào metrics.** Cardinality và privacy đều có vấn đề; không đưa secret/PII vào label.
13. **Dùng region name nhưng không validate input.** Query parameter có thể nhận vô hạn giá trị; normalize bằng allowlist.
14. **Tạo tag key khác nhau cho cùng meter name.** Backend có thể gặp schema không nhất quán; giữ tag keys cố định.
15. **Dùng MeterFilter như giải pháp duy nhất.** Filter có thể deny dữ liệu hợp lệ sau ngưỡng; sửa thiết kế tag từ gốc.
16. **Đặt maximumAllowableTags quá thấp.** Meters mới bị loại và dashboard thiếu dữ liệu; chọn ngưỡng theo miền hợp lệ.
17. **Không kiểm tra tên metric sau normalization.** Prometheus có thể đổi dấu chấm thành underscore; tra cứu bằng endpoint thực tế.
18. **Gắn metrics và observation trùng lặp mà không có ranh giới.** Có thể đếm cùng một work hai lần; chọn instrumentation point rõ.
19. **Đo scheduler wrapper nhưng submit task qua scheduler gốc.** Những task đó không đi qua wrapper và không được đo; dùng wrapper ở nơi submit.
20. **Tạo Scheduler mới mà không dispose.** Thread/resource tồn tại sau test hoặc shutdown; quản lý lifecycle.
21. **Đặt tap quá sớm hoặc quá muộn so với nghiệp vụ muốn đo.** Meter phản ánh sai boundary; xác định rõ phần pipeline cần quan sát.
22. **Cho rằng Micrometer.metrics và Micrometer.observation tạo cùng meter.** Hai API có mục tiêu và tập dữ liệu khác nhau; chọn đúng.
23. **Bật automatic context propagation để giải quyết cardinality.** Context propagation không giới hạn số tag; thiết kế tag vẫn phải đúng.
24. **Chỉ test bằng SimpleMeterRegistry rồi kết luận Prometheus export đúng.** Registry in-memory không kiểm tra scrape format; thêm integration test nếu cần.
25. **Không đo series churn sau release.** Một tag động có thể chỉ bộc lộ khi traffic thực tăng; theo dõi số series và meter deny.

## 23. Checklist thiết kế metrics cho Reactor

Trước khi merge instrumentation:

- Publisher đã được đặt name ổn định chưa?
- Meter name có vô tình chứa ID hoặc URL động không?
- Mỗi tag key có miền giá trị rõ ràng không?
- Region, environment, operation và status có được giới hạn/normalize không?
- Có userId, orderId, requestId, sessionId hoặc traceId trong metric tag không?
- Có raw path, query string, IP hoặc email trong tag không?
- Nếu cần ID để điều tra, đã dùng trace/log có kiểm soát chưa?
- Có phân biệt Micrometer.metrics với Micrometer.observation không?
- High-cardinality Observation key có chỉ đi vào trace theo cấu hình dự định không?
- Registry có được inject từ Spring Boot không?
- reactor-core-micrometer có trong dependencies không?
- MeterFilter có prefix/tag key đúng và ngưỡng hợp lý không?
- Có test kiểm tra meter ID và tag set không?
- Có test request với nhiều IDs để xác minh series không tăng theo ID?
- Scheduler wrapper có đo đúng các task thực sự submit qua nó không?
- Scheduler tự tạo có cleanup không?
- Không có instrumentation trùng lặp ở cùng boundary?
- Actuator chỉ expose endpoint cần thiết và có bảo vệ phù hợp?
- Prometheus/metrics backend có alert cho cardinality hoặc series growth không?
- Logs/traces có chính sách redaction, access control và retention không?

## 24. Bài tập tự kiểm tra

**Câu 1.** Reactor dùng module nào để tích hợp Micrometer hiện đại?  
**Đáp án:** reactor-core-micrometer.

**Câu 2.** API nào ghi publisher metrics vào MeterRegistry?  
**Đáp án:** tap(Micrometer.metrics(meterRegistry)).

**Câu 3.** Vì sao nên đặt name() cho chuỗi?  
**Đáp án:** Để prefix meter ổn định và dễ tìm kiếm, tránh prefix mặc định chung.

**Câu 4.** tag() trên publisher dùng với Micrometer.metrics tạo gì?  
**Đáp án:** Một metric dimension/tag cho các meter của publisher.

**Câu 5.** orderId có nên là metric tag không?  
**Đáp án:** Thông thường không; nó có cardinality cao và tạo quá nhiều series.

**Câu 6.** Micrometer.observation nhận registry nào?  
**Đáp án:** ObservationRegistry.

**Câu 7.** Low-cardinality key values của Observation được xuất đi đâu theo handler mặc định của Spring Boot?  
**Đáp án:** Metrics và traces.

**Câu 8.** High-cardinality key values được xuất đi đâu theo handler mặc định của Spring Boot?  
**Đáp án:** Chỉ traces, không phải metric labels.

**Câu 9.** API nào đo Scheduler?  
**Đáp án:** Micrometer.timedScheduler().

**Câu 10.** Cardinality của một metric có nhiều tag phụ thuộc điều gì?  
**Đáp án:** Số tổ hợp giá trị phân biệt của các tag; worst-case là tích số cardinality của từng tag.

**Câu 11.** MeterFilter.maximumAllowableTags dùng làm gì?  
**Đáp án:** Giới hạn số giá trị phân biệt cho một tag key của các meter có tên khớp prefix.

**Câu 12.** MeterFilter có tự gom các giá trị vượt ngưỡng thành other không?  
**Đáp án:** Không; filter có thể deny meter vượt ngưỡng. Muốn gom nhóm phải normalize value trước khi tạo tag.

**Câu 13.** Có thể đưa raw URL làm tag không?  
**Đáp án:** Không nên; dùng route template ổn định như /orders/{id}.

**Câu 14.** Có cần subscribe thủ công trong controller WebFlux để metrics hoạt động không?  
**Đáp án:** Không; trả publisher để framework subscribe. Metrics được ghi khi subscription thực sự chạy.

**Câu 15.** SimpleMeterRegistry kiểm tra được điều gì?  
**Đáp án:** Xác minh meter IDs và tags trong bộ nhớ, nhưng không thay thế kiểm thử exporter/backend.

## 25. Ghi nhớ

Reactor tích hợp Micrometer qua reactor-core-micrometer. Dùng name() để đặt prefix meter ổn định, tag() để thêm các chiều dữ liệu có miền giá trị nhỏ, và tap(Micrometer.metrics(meterRegistry)) để ghi metrics của publisher. Micrometer.observation(observationRegistry) đo lifecycle của chuỗi reactive; Micrometer.timedScheduler() đo task đi qua một Scheduler wrapper.

Cardinality là số giá trị phân biệt của tag; mỗi tổ hợp tag có thể tạo một time series. Không đưa orderId, userId, requestId, sessionId, email, IP hoặc raw URL vào metric tag. Với Observation, lowCardinalityKeyValue được đưa vào metrics và traces theo handler mặc định của Spring Boot; highCardinalityKeyValue chỉ dành cho traces. Nếu tracing chưa được cấu hình, high-cardinality value có thể không được export ở đâu.

MeterFilter.maximumAllowableTags là lớp phòng vệ, không thay thế thiết kế tag có miền giá trị hữu hạn. Kiểm thử meter IDs, đo series growth và theo dõi cardinality sau mỗi release. Dùng metrics để quan sát xu hướng tổng thể, traces/logs để điều tra từng request, và bảo vệ dữ liệu nhạy cảm ở mọi tín hiệu.

### Tài liệu tham khảo

- Project Reactor 3.6, [Exposing Reactor Metrics](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.3/reference/html/#metrics).
- Project Reactor, [Micrometer.metrics and Micrometer.observation](https://projectreactor.io/docs/core/release/reference/metrics.html).
- Spring Boot 3.3, [Metrics and MeterRegistry](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).
- Spring Boot 3.3, [Observability and Cardinality](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).
- Micrometer, [Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- Micrometer, [Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html).
- Micrometer, [Concepts: Meters and Tags](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).
- Reactor Core Javadoc, [Micrometer entry point](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.11/api/reactor/core/observability/micrometer/Micrometer.html).
