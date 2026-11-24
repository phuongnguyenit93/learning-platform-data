# Số lần quan sát đã có trong Timer hoặc DistributionSummary

## Mục tiêu

Khi đo thời gian xử lý hoặc phân bố kích thước dữ liệu, Micrometer không chỉ lưu giá trị trung bình hay tổng cộng. Cả Timer và DistributionSummary đều ghi nhận số lần quan sát thông qua thuộc tính count. Điều này cho phép trả lời những câu hỏi như:

- Có bao nhiêu request đã được đo thời gian?
- Có bao nhiêu đơn hàng đã được ghi nhận kích thước?
- Trong năm phút gần nhất, tốc độ xử lý là bao nhiêu lần mỗi giây?
- Một giờ qua có bao nhiêu lần ghi nhận payload?

Điểm dễ nhầm là count không phải tổng thời gian và cũng không phải tổng giá trị được ghi. Count đếm số lần gọi phương thức record thành công để ghi nhận một observation. Giá trị của observation được tổng hợp riêng:

- Timer có count và total time.
- DistributionSummary có count và total amount.

Vì vậy, khi đã ghi nhận mỗi sự kiện bằng Timer hoặc DistributionSummary, ứng dụng thường đã có số lần quan sát mà không cần tạo thêm Counter chỉ để đếm lại chính những lần đó.

Sau bài này, bạn có thể giải thích count của hai meter, chọn đúng loại phép đo, đọc số liệu count ở registry/backend, tính tốc độ và tổng số lần quan sát theo khoảng thời gian, đồng thời kiểm thử để phát hiện việc đếm thiếu hoặc đếm trùng.

## Count là gì?

Trong Micrometer, một observation là một lần một meter nhận dữ liệu. Với Timer, mỗi lần ghi nhận một thời lượng là một observation. Với DistributionSummary, mỗi lần ghi nhận một giá trị số là một observation.

Ví dụ, ứng dụng xử lý ba đơn hàng với thời gian lần lượt là 120 ms, 180 ms và 250 ms. Nếu mỗi lần xử lý được ghi vào cùng một Timer:

| Lần ghi nhận | Thời lượng |
|---:|---:|
| 1 | 120 ms |
| 2 | 180 ms |
| 3 | 250 ms |

Timer có:

- count = 3 lần quan sát.
- total time = 550 ms.
- mean = 550 / 3, xấp xỉ 183,33 ms.

Count trả lời câu hỏi “đã ghi nhận bao nhiêu lần?”. Total time trả lời “tổng thời lượng được ghi nhận là bao nhiêu?”. Hai đại lượng có đơn vị và ý nghĩa khác nhau.

Tương tự, nếu ứng dụng ghi kích thước ba payload là 100, 200 và 300 bytes vào DistributionSummary:

- count = 3 payload.
- total amount = 600 bytes.
- mean amount = 200 bytes.

Count vẫn là 3, dù tổng kích thước là 600. Nếu một payload có kích thước 300 bytes, lời gọi record(300) chỉ thêm một observation, không làm count tăng 300 lần.

## Count có sẵn trong Timer

### Timer ghi nhận điều gì?

Timer được dùng để đo thời lượng của một thao tác. Ngoài phân bố thời gian, Timer còn theo dõi:

- Count: số lần ghi nhận thời lượng.
- Total time: tổng thời gian của các lần ghi nhận.
- Max: thời lượng lớn nhất trong cửa sổ thống kê được cấu hình.
- Percentile hoặc histogram: phân bố thời lượng nếu được bật và registry hỗ trợ.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class PaymentService {
    private final Timer paymentTimer;

    public PaymentService(MeterRegistry registry) {
        this.paymentTimer = Timer.builder("business.payment.processing")
                .description("Thời gian xử lý một lần thanh toán")
                .tag("provider", "primary")
                .register(registry);
    }

    public void charge(Payment payment) {
        paymentTimer.record(() -> callPaymentProvider(payment));
    }

    private void callPaymentProvider(Payment payment) {
        // Gọi hệ thống thanh toán.
    }

    public long recordedPayments() {
        return paymentTimer.count();
    }

    public double totalSeconds() {
        return paymentTimer.totalTime(TimeUnit.SECONDS);
    }
}
~~~

Mỗi lần gọi charge và đi qua paymentTimer.record(...) sẽ tạo một lần ghi nhận. Sau ba lần gọi, paymentTimer.count() trả về 3. Tổng thời gian được truy xuất bằng totalTime(TimeUnit.SECONDS), còn count không có đơn vị thời gian.

Đối với thao tác cần gắn tag kết quả sau khi hoàn tất, có thể dùng Timer.Sample:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    paymentGateway.charge(payment);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(registry.timer(
            "business.payment.processing",
            "outcome", outcome
    ));
}
~~~

Lệnh sample.stop(...) ghi thời lượng vào Timer được chọn và làm count của Timer đó tăng thêm một. Việc chọn Timer ở thời điểm kết thúc giúp tag outcome phản ánh kết quả cuối cùng. Tập giá trị outcome phải được kiểm soát, ví dụ success và error.

### Count của Timer không nhất thiết là số request toàn hệ thống

Count chỉ đếm những thao tác thực sự đi qua điểm instrumentation. Nó bằng số request chỉ khi mỗi request thuộc phạm vi cần đo đều tạo đúng một lần record.

Một số tình huống làm count khác số request:

- Một số request bị bỏ qua trước khi đến đoạn instrumentation.
- Một thao tác được retry và mỗi lần retry đều được đo riêng.
- Một request xử lý nhiều công việc con nhưng chỉ có một Timer bao quanh toàn bộ request.
- Một batch gồm 100 phần tử được đo bằng một Timer cho cả batch.
- Một thao tác có nhiều Timer ở các tầng khác nhau.

Hãy viết rõ định nghĩa của metric. Ví dụ, business.payment.processing đo số lần gọi provider, còn http.server.requests đo số request HTTP được server quan sát. Hai count có thể khác nhau và điều đó không nhất thiết là lỗi.

## Count có sẵn trong DistributionSummary

### DistributionSummary ghi nhận điều gì?

DistributionSummary được dùng để đo phân bố của một đại lượng số không phải thời gian. Ví dụ:

- Số item trong một đơn hàng.
- Kích thước payload.
- Số bản ghi trong một batch.
- Số byte đọc hoặc ghi trong một thao tác.

Mỗi lần gọi record(amount) là một observation. DistributionSummary cung cấp:

- Count: số giá trị đã được ghi nhận.
- Total amount: tổng các giá trị được ghi nhận.
- Max: giá trị lớn nhất theo cửa sổ thống kê.
- Percentile hoặc histogram: phân bố giá trị nếu được cấu hình.

Ví dụ:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final DistributionSummary itemsPerOrder;

    public OrderMetrics(MeterRegistry registry) {
        this.itemsPerOrder = DistributionSummary
                .builder("business.orders.items")
                .description("Số mặt hàng trong mỗi đơn hàng")
                .baseUnit("items")
                .register(registry);
    }

    public void recordOrder(int itemCount) {
        itemsPerOrder.record(itemCount);
    }

    public long observedOrders() {
        return itemsPerOrder.count();
    }

    public double totalItems() {
        return itemsPerOrder.totalAmount();
    }
}
~~~

Giả sử ba đơn hàng lần lượt có 2, 5 và 8 mặt hàng. Sau khi gọi recordOrder cho mỗi đơn:

| Đơn hàng | Số mặt hàng được ghi |
|---|---:|
| A | 2 |
| B | 5 |
| C | 8 |

DistributionSummary có count = 3 và totalAmount = 15. Count là số đơn hàng được quan sát; totalAmount là tổng số mặt hàng của các đơn đó. Trung bình số mặt hàng mỗi đơn có thể tính bằng totalAmount / count = 5.

Nếu ứng dụng ghi một batch chứa 100 bản ghi bằng summary.record(100), count tăng một và totalAmount tăng 100. Nếu câu hỏi cần trả lời là “đã xử lý bao nhiêu bản ghi”, tổng amount có thể phù hợp hơn count. Nếu cần “đã xử lý bao nhiêu batch”, count mới là đại lượng phù hợp. Nếu cần cả hai, hãy định nghĩa rõ hai câu hỏi và cách đo.

## So sánh count giữa Counter, Timer và DistributionSummary

Ba meter có thể đều cung cấp một giá trị tích lũy tăng dần, nhưng ngữ nghĩa khác nhau:

| Meter | Count hoặc giá trị chính | Mỗi lần ghi nhận có nghĩa là | Đại lượng bổ sung |
|---|---|---|---|
| Counter | Tổng sự kiện đã tăng | Một sự kiện được increment | Không có tổng amount hay thời lượng |
| Timer | Số lần đo thời gian | Một thao tác được ghi nhận thời lượng | Tổng thời gian, max, percentile/histogram |
| DistributionSummary | Số lần ghi nhận số liệu | Một giá trị số được record | Tổng amount, max, percentile/histogram |

Không nên tạo Counter riêng chỉ để đếm đúng những thao tác mà Timer hoặc DistributionSummary đã ghi nhận. Ví dụ, nếu mọi lần thanh toán đều đi qua paymentTimer.record(...), paymentTimer.count() đã là số lần thanh toán được đo.

Counter riêng vẫn có ích khi sự kiện cần đếm độc lập với phép đo thời gian hoặc phân bố. Ví dụ:

- Đếm số lần một thông điệp bị loại bỏ, trong khi chỉ các thông điệp được xử lý mới được đo Timer.
- Đếm số lần người dùng nhấn nút, dù không phải lần nào cũng tạo một thao tác cần đo thời lượng.
- Đếm số lần một điều kiện nghiệp vụ xảy ra ở nhiều nhánh code khác nhau.

Nếu cùng một sự kiện được ghi vào cả Counter và Timer, hãy xác định đó là chủ ý. Nếu hai meter được kỳ vọng có cùng phạm vi, cùng thời điểm và cùng tag nhưng số đếm khác nhau, cần kiểm tra đường code có bỏ sót hoặc ghi trùng.

## Đọc count từ registry

### Truy vấn trong ứng dụng

Timer và DistributionSummary đều cung cấp count() để truy vấn số lần quan sát:

~~~java
Timer timer = registry.get("business.payment.processing")
        .tag("provider", "primary")
        .timer();

long paymentCount = timer.count();

DistributionSummary summary = registry.get("business.orders.items")
        .summary();

long orderCount = summary.count();
double itemTotal = summary.totalAmount();
~~~

Các giá trị trên là số liệu tích lũy mà meter hiện đang giữ. Chúng hữu ích cho kiểm thử hoặc chẩn đoán nội bộ, nhưng không nên dùng việc đọc count từ request path để tự xây dựng dashboard. Hãy để registry export dữ liệu cho backend giám sát.

### Đọc count trong Prometheus

Với Prometheus registry, Timer được xuất dưới dạng metric có count và sum. Tên metric được chuyển theo quy tắc Prometheus và có thể thêm đơn vị, ví dụ Timer có tên http.server.requests thường xuất hiện với hậu tố seconds_count và seconds_sum. DistributionSummary cũng xuất count và sum; tên cuối cùng phụ thuộc tên metric, base unit và quy tắc đặt tên của registry.

Ví dụ minh họa:

~~~text
http_server_requests_seconds_count{uri="/orders/{orderId}",status="200"} 42
http_server_requests_seconds_sum{uri="/orders/{orderId}",status="200"} 3.8

business_orders_items_count{channel="web"} 10
business_orders_items_sum{channel="web"} 27
~~~

Trong ví dụ đầu, 42 là số lần request được ghi nhận vào Timer; 3.8 là tổng thời gian tính bằng giây. Trong ví dụ thứ hai, 10 là số đơn hàng được ghi nhận; 27 là tổng số mặt hàng của các đơn đó.

Tên thực tế cần được xác nhận tại endpoint metrics của ứng dụng hoặc trong Prometheus. Không giả định mọi registry đều dùng cùng hậu tố hoặc cùng cách biểu diễn.

### Count tích lũy, rate và increase

Giá trị count export thường là bộ đếm tích lũy từ khi tiến trình khởi động hoặc từ khi meter được tạo. Để phân tích trong một khoảng thời gian, cần dùng phép tính trên chuỗi counter:

- Rate: tốc độ số lần quan sát trên mỗi giây trong cửa sổ.
- Increase: số lần quan sát tăng thêm trong cửa sổ thời gian.

Ví dụ PromQL với metric Timer đã được Prometheus export:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Truy vấn này tính tốc độ request trung bình mỗi giây trong cửa sổ năm phút và cộng theo URI. Để xem số request tăng thêm trong một giờ:

~~~promql
sum by (uri) (
  increase(http_server_requests_seconds_count[1h])
)
~~~

Với DistributionSummary, có thể dùng count để đếm số observation:

~~~promql
sum by (channel) (
  increase(business_orders_items_count[1h])
)
~~~

Khi dùng Prometheus, rate và increase xử lý việc counter reset khi tiến trình khởi động lại. Nên áp dụng rate/increase cho từng chuỗi trước khi tổng hợp các instance để tránh che khuất reset của từng tiến trình. Tên metric và label trong ví dụ phải được thay bằng tên thực tế của hệ thống.

## Tránh đếm trùng hoặc đếm thiếu

### Đếm trùng do ghi ở nhiều lớp

Giả sử một request đi qua controller, service và repository. Nếu cả ba lớp đều ghi cùng một metric có cùng ý nghĩa “số request”, count sẽ tăng ba lần cho một request. Hãy chọn một ranh giới đo cho mỗi khái niệm:

- HTTP request count ở lớp server instrumentation.
- Business operation count ở lớp service nghiệp vụ.
- Database call count ở lớp client/repository instrumentation.

Các metric này có thể cùng tăng trong một luồng xử lý nhưng đo các loại thao tác khác nhau, nên tên và mô tả phải nói rõ phạm vi.

### Đếm retry

Nếu một lần thanh toán được thử lại ba lần, có hai câu hỏi hợp lệ:

- Số yêu cầu thanh toán của người dùng: đếm một lần cho một business operation.
- Số lần gọi payment provider: đếm ba lần cho ba lần attempt.

Không gộp hai định nghĩa vào cùng một metric. Có thể đặt metric riêng như business.payment.operations và business.payment.attempts, hoặc thêm tag attempt outcome với tập giá trị hữu hạn. Timer cũng cần được đặt đúng phạm vi: đo toàn bộ operation nếu muốn biết thời gian người dùng chờ, hoặc đo từng attempt nếu muốn biết latency của provider.

### Đếm batch

Với một batch gồm N phần tử, Timer bao quanh toàn batch có count tăng một lần và phản ánh thời lượng của cả batch. DistributionSummary.record(N) có count tăng một lần, totalAmount tăng N. Nếu cần biết tổng số phần tử, dùng totalAmount hoặc một Counter chuyên đếm phần tử đã xử lý. Hãy không diễn giải count của batch thành số phần tử.

### Đếm lỗi

Timer.record(...) có thể ghi nhận thời lượng ngay cả khi thao tác kết thúc bằng exception, miễn là đoạn code đo được kết thúc và dừng Timer. Nếu chỉ ghi Timer ở nhánh thành công, count sẽ không bao gồm thao tác thất bại. Hãy quyết định metric cần đo mọi lần thử hay chỉ những lần thành công, rồi đặt điểm ghi nhận và tag outcome nhất quán.

## Kiểm thử count

Kiểm thử nên xác minh cả số observation lẫn đại lượng được ghi. SimpleMeterRegistry phù hợp cho unit test vì giữ dữ liệu trong bộ nhớ:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class ObservationCountTest {
    @Test
    void timerCountsRecordedDurations() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Timer timer = registry.timer("test.operation.duration");

            timer.record(100, TimeUnit.MILLISECONDS);
            timer.record(200, TimeUnit.MILLISECONDS);
            timer.record(300, TimeUnit.MILLISECONDS);

            assertThat(timer.count()).isEqualTo(3);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(600.0);
        } finally {
            registry.close();
        }
    }

    @Test
    void summaryCountsSamplesSeparatelyFromTheirTotal() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            DistributionSummary summary =
                    registry.summary("test.batch.size");

            summary.record(2);
            summary.record(5);
            summary.record(8);

            assertThat(summary.count()).isEqualTo(3);
            assertThat(summary.totalAmount()).isEqualTo(15.0);
        } finally {
            registry.close();
        }
    }
}
~~~

Test đầu xác minh ba thời lượng tạo ra count bằng 3 và tổng thời gian bằng 600 ms. Test thứ hai xác minh ba giá trị mẫu tạo ra count bằng 3, còn tổng amount bằng 15. Hai assertion riêng biệt giúp tránh nhầm số lần ghi nhận với tổng giá trị.

Ngoài unit test, kiểm thử tích hợp nên xác nhận endpoint export có metric count tương ứng, tag được chuẩn hóa và mỗi request tạo đúng số observation theo định nghĩa. Với Prometheus, có thể scrape endpoint hai lần và kiểm tra count tăng theo số thao tác mới; trong môi trường có nhiều instance, cần phân biệt count từng instance với tổng count đã aggregate.

## Checklist thiết kế metric có count

1. Xác định một observation tương ứng với sự kiện hoặc thao tác nào.
2. Dùng Timer khi cần đo thời lượng; count của Timer là số lần đo.
3. Dùng DistributionSummary khi cần đo phân bố số; count là số mẫu, totalAmount là tổng các giá trị.
4. Không diễn giải count của batch thành số phần tử trong batch.
5. Không thêm Counter riêng nếu chỉ lặp lại count đã có cùng phạm vi trong Timer hoặc Summary.
6. Nếu cần cả số operation và số attempt, định nghĩa hai metric riêng.
7. Đặt ranh giới instrumentation để tránh ghi trùng ở controller, service và repository.
8. Xác định request thất bại có được ghi vào Timer hay không.
9. Dùng rate hoặc increase để phân tích khoảng thời gian; không so sánh trực tiếp hai giá trị count tích lũy ở thời điểm khác nhau.
10. Kiểm thử count cùng totalTime hoặc totalAmount và kiểm tra dữ liệu export.

## Kết luận

Timer và DistributionSummary đã tích hợp số lần quan sát qua count(). Timer.count() là số lần ghi nhận thời lượng; DistributionSummary.count() là số mẫu số học đã ghi. Tổng thời gian và tổng amount được theo dõi riêng, nên một lần ghi giá trị lớn vẫn chỉ là một observation. Hãy tận dụng count có sẵn khi nó khớp với định nghĩa sự kiện, dùng Counter riêng cho sự kiện độc lập và kiểm tra ranh giới instrumentation để tránh đếm trùng. Khi export sang Prometheus, dùng rate hoặc increase trên chuỗi _count để phân tích tốc độ và số lần quan sát trong một khoảng thời gian.
