# Đo thời gian một thao tác ở ranh giới người dùng hoặc dịch vụ quan tâm

Một request HTTP có thể gọi nhiều use case, còn một use case có thể chạy qua nhiều thành phần nội bộ. Vì vậy, thời gian của request không phải lúc nào cũng thể hiện đúng thời gian mà người dùng hoặc một dịch vụ phụ thuộc đang chờ để hoàn thành một thao tác nghiệp vụ.

Micrometer Timer giúp đo thời gian tại ranh giới có ý nghĩa đó. Điều quan trọng nhất là xác định rõ lúc thao tác bắt đầu, điều kiện nào được xem là hoàn tất và phần công việc nào thuộc phạm vi đo. Khi ranh giới được định nghĩa đúng, số liệu có thể dùng để đánh giá trải nghiệm, phát hiện suy giảm và đặt SLO.

## 1. Business operation boundary là gì?

Business operation boundary là hai mốc bao quanh một hành động có ý nghĩa với người dùng hoặc dịch vụ gọi đến. Ví dụ:

- Người mua đặt hàng và nhận được kết quả xác nhận.
- Người dùng tìm kiếm và nhận được danh sách kết quả.
- Một dịch vụ yêu cầu giữ chỗ tồn kho và nhận được kết quả giữ chỗ.
- Người vận hành yêu cầu tạo báo cáo và nhận được báo cáo hoàn chỉnh.

Mỗi thao tác cần có một định nghĩa start và end nhất quán. Nếu các lần đo dùng ranh giới khác nhau, việc so sánh latency theo thời gian hoặc giữa các phiên bản sẽ không còn đáng tin cậy.

### Ví dụ chọn ranh giới

| Thao tác | Bắt đầu đo | Kết thúc đo |
| --- | --- | --- |
| Đặt hàng đồng bộ | Use case nhận lệnh đặt hàng | Đơn hàng được lưu và kết quả thanh toán cần thiết đã rõ |
| Tìm kiếm | Use case nhận tiêu chí tìm kiếm hợp lệ | Kết quả đã sẵn sàng trả về |
| Giữ tồn kho | Dịch vụ nhận yêu cầu giữ chỗ | Có kết quả giữ chỗ hoặc từ chối |
| Tạo báo cáo nền | Worker bắt đầu xử lý báo cáo | File/báo cáo đã được tạo hoặc tác vụ thất bại |

Ranh giới phụ thuộc cam kết của hệ thống. Nếu API chỉ cam kết tiếp nhận một yêu cầu tạo báo cáo, thao tác API kết thúc khi job đã được xếp hàng thành công. Thời gian tạo file là một operation khác, kết thúc khi worker hoàn thành.

## 2. Phân biệt business latency với HTTP request latency

HTTP server metrics như http.server.requests đo thời gian xử lý request tại lớp web. Business timer đo thời gian của use case cụ thể. Hai phép đo có thể bao phủ những phần công việc khác nhau.

~~~mermaid
flowchart TD
    A["HTTP request bắt đầu"] --> B["Authentication / routing"]
    B --> C["Business operation bắt đầu"]
    C --> D["Validate và xử lý nghiệp vụ"]
    D --> E["Database / dịch vụ phụ thuộc"]
    E --> F["Business operation hoàn tất"]
    F --> G["Serialize response"]
    G --> H["HTTP request kết thúc"]
~~~

Trong ví dụ này, HTTP latency bao gồm cả authentication, routing và serialize response. Business latency chỉ bao quanh use case. Nếu một request gọi nhiều use case, mỗi use case có thể có timer riêng trong khi HTTP server vẫn ghi một timer tổng.

Không cộng hoặc trừ các timer một cách máy móc để suy ra thời gian từng thành phần. Các khoảng đo có thể lồng nhau hoặc chạy đồng thời. Nếu cần biết thời gian của dependency, hãy đo dependency bằng meter riêng hoặc dùng tracing để thấy quan hệ cha/con.

## 3. Xác định rõ phạm vi công việc được tính

Trước khi viết code, hãy trả lời:

1. Người gọi đang chờ kết quả nào?
2. Thao tác bắt đầu khi lệnh được nhận, sau validation hay khi worker bắt đầu?
3. Có bao gồm thời gian chờ queue không?
4. Có bao gồm gọi database hoặc dịch vụ bên ngoài không?
5. Thành công, từ chối nghiệp vụ, timeout và lỗi kỹ thuật được kết thúc như thế nào?
6. Nếu thao tác bị hủy hoặc retry, một lần đo đại diện cho một lần thử hay toàn bộ hành trình?

Ví dụ với đặt hàng đồng bộ, nếu người dùng chờ kết quả xác nhận thanh toán thì business timer nên bao gồm cả thời gian gọi payment provider. Có thể đo thêm riêng thời gian provider để tìm nguyên nhân chậm, nhưng timer tổng vẫn phản ánh trải nghiệm của use case.

Nếu payment provider chạy bất đồng bộ và API chỉ trả về trạng thái accepted, timer của API nên dừng khi yêu cầu đã được tiếp nhận. Quá trình hoàn tất thanh toán sau đó cần metric riêng hoặc trace liên kết với workflow.

## 4. Dùng Timer cho một thao tác đồng bộ

Timer phù hợp với thao tác có điểm hoàn tất rõ ràng. Có thể dùng Timer.record(...) để bọc một đoạn code hoặc Timer.Sample khi cần chọn meter sau khi đã biết kết quả.

Ví dụ với Timer.record:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class SearchService {

    private final Timer searchDuration;
    private final SearchRepository repository;

    public SearchService(
        MeterRegistry registry,
        SearchRepository repository
    ) {
        this.searchDuration = Timer.builder("business.search.duration")
            .description("Thời gian hoàn thành use case tìm kiếm")
            .register(registry);
        this.repository = repository;
    }

    public SearchResult search(SearchCommand command) {
        return searchDuration.record(() -> repository.search(command));
    }
}
~~~

Timer đo toàn bộ phần code nằm trong lambda. Nếu cần đo validation, mapping, gọi nhiều repository và tổng hợp kết quả, hãy đặt tất cả phần đó trong operation được bọc. Nếu chỉ bọc repository, metric đang đo database access chứ chưa phải business search latency.

## 5. Dùng Timer.Sample để phân loại kết quả

Trong nhiều use case, kết quả cuối cùng quyết định tag outcome. Timer.Sample cho phép bắt đầu đo trước, sau đó chọn Timer phù hợp tại thời điểm kết thúc.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MeterRegistry registry;
    private final InventoryService inventory;
    private final OrderRepository orders;

    public OrderService(
        MeterRegistry registry,
        InventoryService inventory,
        OrderRepository orders
    ) {
        this.registry = registry;
        this.inventory = inventory;
        this.orders = orders;
    }

    public Order placeOrder(PlaceOrderCommand command) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "error";

        try {
            inventory.reserve(command.items());
            Order order = orders.save(command);
            outcome = "success";
            return order;
        } catch (InventoryUnavailableException ex) {
            outcome = "rejected";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("business.order.place.duration")
                    .description("Thời gian hoàn thành use case đặt hàng")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
~~~

Trong ví dụ:

- Timer bắt đầu ngay khi use case được gọi.
- Thời gian giữ chỗ tồn kho và lưu đơn hàng nằm trong cùng business operation.
- Thành công được gắn outcome=success.
- Từ chối do hết tồn kho được gắn outcome=rejected.
- Các lỗi runtime khác giữ giá trị mặc định outcome=error.
- finally bảo đảm sample được dừng cả khi có exception.

Hãy chỉ tạo các outcome có ý nghĩa và tập giá trị hữu hạn. Nếu cần phân biệt timeout, validation failure hoặc dependency failure, hãy chuẩn hóa thành các nhóm ổn định thay vì dùng exception message làm tag.

## 6. Chọn điểm bắt đầu và kết thúc cho đúng

Một phép đo chỉ hữu ích khi các mốc có cùng ý nghĩa qua các lần gọi.

**Điểm bắt đầu** thường là lúc service nhận một yêu cầu đã đủ điều kiện đi vào use case. Nếu validation là một phần của trải nghiệm mà người dùng quan tâm, có thể bắt đầu trước validation. Nếu validation ở gateway đã nằm ngoài phạm vi service, hãy ghi rõ điều đó.

**Điểm kết thúc** là lúc hệ thống đã có kết quả mà hợp đồng của operation cam kết. Không dừng timer ngay khi submit công việc nếu người gọi vẫn phải chờ công việc hoàn thành.

Ví dụ:

- placeOrder: kết thúc khi đơn hàng có trạng thái kết quả mà API trả về.
- reserveInventory: kết thúc khi có kết quả giữ chỗ.
- generateReport: nếu đồng bộ, kết thúc khi báo cáo sẵn sàng; nếu bất đồng bộ, API submit và worker execution là hai phép đo khác nhau.

Không thay đổi ranh giới giữa các phiên bản chỉ để làm số latency trông tốt hơn. Nếu định nghĩa thay đổi vì hợp đồng sản phẩm thay đổi, hãy ghi nhận thay đổi đó trong tài liệu metric và dashboard.

## 7. Đo thời gian chờ queue và thời gian xử lý riêng biệt

Với tác vụ nền, thời gian tổng từ lúc người dùng gửi yêu cầu đến lúc hoàn thành có thể gồm:

\[
T_{\text{end-to-end}} =
T_{\text{queue wait}} + T_{\text{execution}}
\]

Nếu worker bắt đầu đo khi lấy job khỏi queue, Timer execution không bao gồm thời gian chờ. Có thể đo riêng hai khoảng:

~~~java
// Khi đưa job vào queue
Timer.Sample queueWait = Timer.start(registry);
queue.enqueue(job);

// Khi worker lấy job ra
queueWait.stop(
    registry.timer("business.report.queue.wait")
);

Timer.Sample execution = Timer.start(registry);
try {
    reportWorker.generate(job);
} finally {
    execution.stop(
        registry.timer("business.report.execution")
    );
}
~~~

Đoạn code chỉ minh họa khi enqueue và dequeue cùng tiến trình, cùng vòng đời bộ nhớ. Trong hệ thống phân tán hoặc queue bền vững, không chuyển Timer.Sample qua message hoặc tiến trình khác. Hãy dùng tracing context để liên kết các span hoặc thiết kế event timestamp có semantics và đồng bộ clock rõ ràng.

Nếu người dùng quan tâm thời gian hoàn tất toàn bộ workflow, cần có một phép đo end-to-end phù hợp với ranh giới workflow. Không dùng riêng execution timer để đại diện cho thời gian người dùng đã chờ.

## 8. Đo thao tác bất đồng bộ đến khi hoàn tất

Khi một thao tác trả về CompletableFuture, lời gọi phương thức có thể chỉ submit công việc rồi trả về ngay. Nếu dừng Timer tại thời điểm future được tạo, số đo chỉ phản ánh thời gian submit.

Có thể dừng Timer.Sample khi future hoàn tất:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class AsyncReportService {

    private final MeterRegistry registry;
    private final ReportClient client;

    public AsyncReportService(
        MeterRegistry registry,
        ReportClient client
    ) {
        this.registry = registry;
        this.client = client;
    }

    public CompletableFuture<Report> generate(ReportRequest request) {
        Timer.Sample sample = Timer.start(registry);

        return client.generateAsync(request)
            .whenComplete((report, error) -> {
                String outcome;
                if (error == null) {
                    outcome = "success";
                } else if (error instanceof CancellationException) {
                    outcome = "cancelled";
                } else {
                    outcome = "error";
                }

                sample.stop(
                    Timer.builder("business.report.generate.duration")
                        .tag("outcome", outcome)
                        .register(registry)
                );
            });
    }
}
~~~

Sample được dừng khi future hoàn tất, dù hoàn tất bình thường hay exceptional. Nếu API chỉ cam kết nhận yêu cầu rồi trả về job ID, hãy dùng một timer khác cho thao tác submit và đo worker execution riêng; ví dụ trên phù hợp khi caller xem future completion là kết quả cuối cùng của operation.

Trong thiết kế thực tế, bảo đảm callback hoàn tất chỉ chịu trách nhiệm dừng sample một lần. Nếu timeout, cancellation và callback retry có thể cạnh tranh, cần một cơ chế điều phối trạng thái hoàn tất để tránh ghi nhận lặp.

## 9. Một thao tác có retry: đo từng lần thử hay toàn bộ operation?

Retry làm thay đổi cách diễn giải latency. Ví dụ, một use case gọi payment provider ba lần mới thành công:

- Timer cho từng lần thử phản ánh độ trễ và lỗi của dependency.
- Timer bao quanh toàn bộ use case phản ánh thời gian người dùng chờ, gồm cả backoff và retry.

Hai số đo trả lời hai câu hỏi khác nhau. Có thể đặt tên riêng như business.payment.attempt.duration và business.checkout.duration. Không ghi cả hai vào cùng một metric name với cùng tags nếu semantics khác nhau.

Khi đo toàn bộ operation, bắt đầu trước vòng retry và dừng sau kết quả cuối cùng. Khi đo attempt, bắt đầu và dừng trong mỗi lần gọi dependency. Nếu có backoff, tổng operation timer bao gồm thời gian chờ giữa các lần thử; attempt timer không bao gồm phần chờ đó.

## 10. Chọn tên meter và tags có cardinality thấp

Tên meter nên mô tả hành động nghiệp vụ, không mô tả một request cụ thể:

| Nên dùng | Ý nghĩa |
| --- | --- |
| business.order.place.duration | Thời gian use case đặt hàng |
| business.search.duration | Thời gian use case tìm kiếm |
| business.inventory.reserve.duration | Thời gian giữ chỗ tồn kho |
| business.report.generate.duration | Thời gian tạo báo cáo |

Tags thường hữu ích:

- outcome=success|rejected|error|cancelled
- channel=web|mobile|partner
- operation=create|update|cancel
- region=north|central|south nếu số vùng được giới hạn

Không dùng:

- order_id
- customer_id
- request_id
- email
- exception message hoặc URL có ID động

Mỗi tổ hợp tên và tag values có thể tạo một time series. Tags có cardinality cao làm tăng bộ nhớ registry, chi phí export, lưu trữ và truy vấn. Nếu cần điều tra một order cụ thể, dùng log hoặc trace với correlation ID thay vì metric tag.

## 11. Đọc Timer và đánh giá latency nghiệp vụ

Timer cung cấp số lần ghi nhận và thời gian tích lũy; registry có thể cung cấp max, histogram hoặc percentile theo cấu hình.

Các thống kê thường dùng:

- count: số lần operation hoàn tất đã được ghi nhận.
- totalTime: tổng thời gian của các operation.
- max: thời gian lớn nhất theo cửa sổ/implementation.
- Histogram: số quan sát nằm trong các bucket thời gian.
- Percentile: ước lượng vị trí trong phân phối nếu được cấu hình và registry hỗ trợ.

Không chỉ nhìn mean. Một thao tác có p50 tốt nhưng p99 rất cao vẫn có thể làm một nhóm người dùng chờ lâu. Với business operation quan trọng, hãy chọn histogram/SLO bucket theo ngưỡng mà sản phẩm quan tâm.

Ví dụ cấu hình ngưỡng:

~~~java
Timer checkout = Timer.builder("business.checkout.duration")
    .description("Thời gian hoàn thành checkout")
    .serviceLevelObjectives(
        java.time.Duration.ofMillis(300),
        java.time.Duration.ofMillis(800),
        java.time.Duration.ofSeconds(2)
    )
    .register(registry);
~~~

Ngưỡng 300 ms, 800 ms và 2 giây chỉ là ví dụ. Hãy chọn dựa trên hành trình người dùng, yêu cầu sản phẩm và baseline thực tế. SLO cần định nghĩa rõ tập operation đủ điều kiện và outcome nào được tính là good event.

## 12. Không đo cùng một ranh giới hai lần

Nếu cùng một operation vừa được đo bằng annotation/aspect vừa được đo thủ công bằng Timer.Sample, dashboard có thể có hai metric trùng ý nghĩa hoặc latency bị đếm hai lần trong báo cáo tổng hợp.

Trước khi thêm timer:

1. Kiểm tra HTTP server metrics đã đo phần nào.
2. Kiểm tra service method có Timed hoặc Observation instrumentation chưa.
3. Kiểm tra binder hoặc AOP có tạo timer cùng mục đích không.
4. Chọn một nơi sở hữu business boundary.
5. Đặt tên khác nhau nếu cố ý đo các lớp khác nhau.

Timed có thể tiện cho method-level timing khi TimedAspect/AOP đã được cấu hình. Nhưng method boundary chỉ tương đương business boundary nếu method đó thực sự đại diện cho operation cần đo. Đừng áp annotation rộng khắp rồi giả định mọi method đều là business action.

## 13. Kiểm thử ranh giới và kết quả đo

Có thể dùng SimpleMeterRegistry để kiểm tra count, tag outcome và thời gian được ghi nhận. Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMetricsTest {

    @Test
    void recordsOneSuccessfulBusinessOperation() {
        MeterRegistry registry = new SimpleMeterRegistry();
        Timer.Sample sample = Timer.start(registry);

        // Đại diện cho phần công việc của use case trong test.
        sample.stop(
            Timer.builder("business.order.place.duration")
                .tag("outcome", "success")
                .register(registry)
        );

        Timer timer = registry.find("business.order.place.duration")
            .tag("outcome", "success")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1L);

        registry.close();
    }
}
~~~

Test trên kiểm tra việc ghi nhận Timer. Test ở cấp service nên xác minh thêm:

- Operation thành công ghi đúng outcome.
- Từ chối nghiệp vụ và lỗi kỹ thuật ghi đúng nhóm outcome.
- Exception không làm mất lần ghi nhận.
- Thời gian bao gồm các bước thuộc business boundary.
- Thời gian không bao gồm công việc nằm ngoài hợp đồng operation.
- Async timer chỉ dừng khi future hoàn tất.
- Cancellation/timeout không làm sample bị dừng nhiều lần.
- Retry được đo riêng theo attempt và toàn bộ operation nếu cả hai số đo cần thiết.

Không dùng sleep dài để kiểm thử thời gian. Hãy kiểm tra count, tag và sự kiện dừng sample; nếu cần kiểm thử chính xác elapsed time, dùng clock có thể điều khiển hoặc abstraction thời gian phù hợp với phiên bản Micrometer đang dùng.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Đo toàn bộ HTTP request rồi gọi đó là business latency | Bao gồm routing/serialization và các phần ngoài use case | Đặt timer tại ranh giới use case |
| Chỉ đo repository call | Bỏ sót validation, orchestration và dependency khác | Bao quanh toàn bộ operation cần quan sát |
| Dừng timer ngay sau khi submit future | Chỉ đo thời gian submit | Dừng sample trong callback hoàn tất |
| Không tính queue wait trong workflow người dùng phải chờ | Latency báo cáo thấp hơn trải nghiệm thật | Đo queue wait hoặc end-to-end riêng |
| Dùng order ID làm tag | Cardinality tăng theo số giao dịch | Dùng log/trace cho định danh |
| Không phân loại outcome | Khó phân biệt chậm do thành công hay lỗi | Dùng outcome hữu hạn |
| Đo cả attempt và toàn operation vào cùng meter | Số liệu không còn cùng semantics | Dùng metric name riêng |
| Chỉ xem average | Che khuất đuôi latency | Dùng histogram/percentile và SLO |
| Dừng sample ở nhiều nhánh cạnh tranh | Một operation có thể bị ghi nhiều lần | Có một điểm kết thúc được điều phối |

## 15. Quy trình thiết kế business timer

Khi thêm phép đo cho một hành động nghiệp vụ:

1. Chọn hành động mà người dùng hoặc dịch vụ phụ thuộc thực sự quan tâm.
2. Viết rõ điều kiện bắt đầu và kết thúc.
3. Quyết định thời gian queue, dependency, retry và backoff có thuộc phạm vi không.
4. Phân biệt thời gian submit với thời gian xử lý nếu operation chạy nền.
5. Dùng Timer hoặc Timer.Sample để đo elapsed time bằng clock của Micrometer.
6. Chọn outcome và các tags có tập giá trị hữu hạn.
7. Đặt tên meter thể hiện rõ business operation và semantics.
8. Bật histogram/SLO buckets nếu cần đánh giá ngưỡng trải nghiệm.
9. Kiểm thử success, rejection, exception, timeout, cancellation và async completion.
10. Đối chiếu với HTTP metrics, dependency metrics và tracing để tránh diễn giải nhầm.

Business timer có giá trị khi nó phản ánh đúng thời gian mà người dùng hoặc dịch vụ gọi đến phải chờ. Ranh giới rõ ràng giúp phân biệt latency của use case với latency của HTTP server, queue hoặc dependency. Khi kết hợp Timer.Sample, outcome có kiểm soát và histogram phù hợp, đội ngũ có thể theo dõi chất lượng thao tác nghiệp vụ bằng những số liệu có thể so sánh và hành động được.
