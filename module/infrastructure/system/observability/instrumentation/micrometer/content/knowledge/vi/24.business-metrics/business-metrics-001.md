# Chọn câu hỏi nghiệp vụ có thể trả lời bằng số liệu tổng hợp

Micrometer không chỉ dùng để theo dõi CPU, bộ nhớ, request latency hoặc connection pool. Ứng dụng cũng có thể công bố metrics phản ánh hoạt động kinh doanh: số đơn hàng đã thanh toán, tốc độ xử lý thanh toán, tỷ lệ thanh toán thất bại, giá trị đơn hàng hoặc số tác vụ đang chờ hoàn tất.

Một business metric có ích khi nó trả lời một câu hỏi cụ thể và hỗ trợ một quyết định vận hành. Ví dụ, “Có bao nhiêu đơn hàng được thanh toán mỗi phút theo kênh bán?” có thể trả lời bằng Counter. “Giá trị đơn hàng thường nằm trong khoảng nào?” có thể dùng DistributionSummary. “Có bao nhiêu đơn hàng đang chờ giao?” có thể dùng Gauge nếu ứng dụng có trạng thái hiện tại đáng tin cậy.

Không phải mọi câu hỏi kinh doanh đều phù hợp với metrics. Metrics là dữ liệu tổng hợp theo thời gian và một số chiều có giới hạn. Chúng không thay thế sổ cái tài chính, kho dữ liệu phân tích, lịch sử giao dịch hoặc dữ liệu định danh từng khách hàng.

## 1. Bắt đầu từ quyết định, không bắt đầu từ tên metric

Trước khi tạo meter, hãy xác định ai sẽ sử dụng số liệu và họ cần quyết định điều gì.

Ví dụ:

| Câu hỏi nghiệp vụ | Quyết định có thể hỗ trợ | Dạng số liệu phù hợp |
|---|---|---|
| Số đơn hàng thanh toán thành công mỗi phút là bao nhiêu? | Theo dõi nhu cầu và phát hiện lưu lượng bán giảm bất thường | Counter và rate |
| Tỷ lệ thanh toán thất bại có tăng không? | Điều tra cổng thanh toán hoặc thay đổi quy trình checkout | Counter theo kết quả |
| Giá trị đơn hàng thường là bao nhiêu? | Theo dõi xu hướng giá trị giỏ hàng và thay đổi theo kênh | DistributionSummary |
| Checkout mất bao lâu? | Phát hiện quy trình mua hàng chậm | Timer và percentile |
| Có bao nhiêu đơn đang chờ đóng gói? | Điều phối nhân lực hoặc xử lý backlog | Gauge |
| Khách hàng cụ thể nào bị tính tiền hai lần? | Điều tra một giao dịch | Log, trace và dữ liệu giao dịch |

Một câu hỏi phù hợp với metrics thường có các đặc điểm:

- Có thể diễn đạt bằng một đại lượng hoặc tỷ lệ rõ ràng.
- Dữ liệu có thể tổng hợp theo thời gian.
- Các chiều phân tích có tập giá trị hữu hạn.
- Có người hoặc hệ thống sẽ hành động khi số liệu thay đổi.
- Không cần truy xuất từng bản ghi để hiểu kết quả.

Nếu câu hỏi cần tìm một đơn hàng, khách hàng hoặc sự kiện cụ thể, hãy dùng ID trong log, trace hoặc hệ thống dữ liệu nghiệp vụ. Không đưa ID đó vào tag của metric.

## 2. Chuyển câu hỏi thành định nghĩa có thể đo

Một business metric cần có định nghĩa thống nhất để các nhóm không diễn giải khác nhau. Trước khi viết code, hãy mô tả:

1. **Đối tượng được đếm:** đơn hàng, lần thử thanh toán, lần giao hàng hay phiên checkout?
2. **Sự kiện bắt đầu:** lúc tạo đơn, gửi yêu cầu thanh toán hay khi trạng thái được xác nhận?
3. **Sự kiện kết thúc:** lúc thanh toán thành công, thất bại hay hết thời gian chờ?
4. **Đơn vị:** đơn hàng, lần thử, VND, giây hoặc số tác vụ.
5. **Tử số và mẫu số:** nếu là tỷ lệ, mỗi bên đại diện cho tập sự kiện nào?
6. **Cửa sổ thời gian hoặc cohort:** 5 phút gần nhất, một ngày hay nhóm phiên bắt đầu trong cùng ngày?
7. **Chiều phân tích:** kênh bán, nhà cung cấp thanh toán, vùng hoặc loại sản phẩm có giới hạn.
8. **Nguồn sự thật:** trạng thái đã commit trong cơ sở dữ liệu, event đã được xác nhận hay bộ đếm tạm thời?
9. **Người sở hữu:** ai chịu trách nhiệm giải thích và hành động khi số liệu bất thường?

Ví dụ, định nghĩa “đơn hàng đã thanh toán” cần nói rõ chỉ đếm một lần khi đơn chuyển sang trạng thái PAID. Nếu hệ thống phát lại event hoặc retry consumer, cùng một đơn hàng không được tính thành nhiều đơn đã thanh toán.

## 3. Chọn meter theo bản chất câu hỏi

| Loại meter | Phù hợp với câu hỏi | Ví dụ nghiệp vụ |
|---|---|---|
| **Counter** | Có bao nhiêu sự kiện đã xảy ra? Tốc độ sự kiện đang tăng hay giảm? | Đơn đã thanh toán, lần thử thanh toán, số lượt hoàn tiền |
| **Timer** | Một quy trình mất bao lâu? | Thời gian checkout, thời gian xác nhận thanh toán, thời gian xử lý đơn |
| **DistributionSummary** | Các giá trị số phân bố như thế nào? | Giá trị đơn hàng, số mặt hàng trong giỏ, khối lượng lô nhập |
| **Gauge** | Trạng thái hiện tại đang có giá trị bao nhiêu? | Số đơn đang chờ đóng gói, số phiên xử lý đang hoạt động |
| **LongTaskTimer** | Các tác vụ nghiệp vụ dài nào vẫn đang chạy và đã kéo dài bao lâu? | Báo cáo doanh thu đang chạy, batch đối soát đang hoạt động |

Không chọn Gauge để đếm số sự kiện tích lũy. Gauge chỉ đọc giá trị hiện tại và có thể giảm khi trạng thái thay đổi. Không chọn Counter cho một đại lượng cần tăng giảm theo trạng thái hiện tại. Hãy dùng meter có ngữ nghĩa phù hợp với câu hỏi.

## 4. Đếm đơn hàng đã thanh toán bằng Counter

Giả sử câu hỏi là: “Mỗi phút có bao nhiêu đơn hàng được thanh toán thành công theo kênh bán?”

Định nghĩa sự kiện là một đơn hàng chuyển sang trạng thái PAID sau khi giao dịch được xác nhận. Mỗi đơn hàng chỉ được tính một lần. Tag `channel` chỉ nhận các giá trị hữu hạn như `web`, `mobile` và `store`.

Có thể tạo Counter theo kênh:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void orderPaid(String channel) {
        registry.counter(
            "business.orders.paid",
            "channel", channel
        ).increment();
    }
}
```

Trong code production, `channel` phải đến từ enum hoặc danh sách giá trị đã kiểm soát. Không nhận một chuỗi tùy ý từ request rồi dùng trực tiếp làm tag.

Counter là số tích lũy trong vòng đời meter. Khi xem tốc độ đơn hàng, dùng `rate` hoặc `increase` trên backend thay vì đọc raw count như thể nó là số đơn trong phút hiện tại.

Ví dụ PromQL nếu series Prometheus được export với hậu tố counter thông thường:

```promql
sum by (channel) (
  rate(business_orders_paid_total[5m])
)
```

Kết quả là tốc độ đơn hàng thanh toán mỗi giây trong cửa sổ 5 phút, phân tách theo kênh. Nhân với 60 nếu dashboard muốn hiển thị đơn hàng mỗi phút.

Tên series thực tế phụ thuộc naming convention và phiên bản registry; hãy kiểm tra endpoint export trước khi dùng truy vấn.

## 5. Đo doanh thu và giá trị đơn hàng

Hai câu hỏi sau có vẻ giống nhau nhưng cần cách đo khác nhau:

- Tổng giá trị tiền của các đơn hàng đã thanh toán là bao nhiêu?
- Giá trị của một đơn hàng thường nằm ở mức nào?

Để theo dõi tổng tiền đã thanh toán theo thời gian, có thể dùng Counter tăng theo số tiền dương của từng đơn hàng. Để xem phân bố và tính giá trị đơn hàng trung bình hoặc percentile, dùng DistributionSummary.

Ví dụ sử dụng VND:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public class RevenueMetrics {

    private final MeterRegistry registry;

    public RevenueMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void orderPaid(String channel, long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException(
                "Paid order amount must be positive"
            );
        }

        registry.counter(
            "business.revenue.vnd",
            "channel", channel
        ).increment(amountVnd);

        DistributionSummary.builder("business.order.value.vnd")
            .tag("channel", channel)
            .register(registry)
            .record(amountVnd);
    }
}
```

Counter `business.revenue.vnd` cộng số tiền đã thanh toán. DistributionSummary `business.order.value.vnd` ghi từng giá trị đơn hàng để theo dõi count, sum và phân bố. Các tag channel phải có tập giá trị giới hạn.

Ví dụ PromQL tính tốc độ ghi nhận doanh thu:

```promql
sum by (channel) (
  rate(business_revenue_vnd_total[5m])
)
```

Tốc độ này có đơn vị VND mỗi giây. Có thể nhân 60 để hiển thị VND mỗi phút.

Giá trị đơn hàng trung bình trên cửa sổ 5 phút có thể được tính từ sum và count của DistributionSummary:

```promql
sum by (channel) (
  rate(business_order_value_vnd_sum[5m])
)
/
sum by (channel) (
  rate(business_order_value_vnd_count[5m])
)
```

Nếu cần p95 giá trị đơn hàng, bật histogram cho DistributionSummary và dùng `histogram_quantile()` trên các bucket tương thích. Không tính p95 bằng cách lấy trung bình p95 của từng instance.

Metrics dùng số dấu phẩy động và có thể reset khi tiến trình khởi động lại. Vì vậy, Counter doanh thu chỉ là tín hiệu vận hành để theo dõi xu hướng. Sổ cái hoặc hệ thống giao dịch đã commit mới là nguồn sự thật cho báo cáo tài chính, đối soát và kiểm toán. Không dùng metrics để quyết toán tiền.

Nếu hệ thống hỗ trợ nhiều tiền tệ, không cộng các loại tiền khác nhau vào một meter như thể chúng cùng đơn vị. Có thể tách metric theo currency với tập mã tiền tệ hữu hạn hoặc quy đổi theo chính sách báo cáo đã xác định. Hoàn tiền và chargeback nên được ghi nhận thành meter riêng; net revenue có thể được tính từ gross paid trừ refunds, nhưng báo cáo chính thức vẫn phải lấy từ ledger.

## 6. Tính tỷ lệ thanh toán thất bại

Câu hỏi: “Trong các lần thử thanh toán, bao nhiêu phần trăm thất bại?”

Trước hết phải định nghĩa đơn vị là *payment attempt* hay *payment intent*. Nếu một khách hàng thử thanh toán ba lần cho cùng một đơn, có thể đó là ba attempts nhưng chỉ là một intent. Hai cách đếm trả lời hai câu hỏi khác nhau.

Có thể dùng một Counter với tag kết quả:

```java
public void paymentAttemptFinished(
        String provider,
        boolean successful
) {
    String result = successful ? "success" : "failure";

    registry.counter(
        "business.payment.attempts",
        "provider", provider,
        "result", result
    ).increment();
}
```

Tag `provider` cần lấy từ danh sách nhà cung cấp có kiểm soát; `result` chỉ có hai giá trị. Truy vấn tỷ lệ thất bại:

```promql
sum(
  rate(business_payment_attempts_total{result="failure"}[5m])
)
/
sum(
  rate(business_payment_attempts_total[5m])
)
```

Nhân kết quả với 100 để hiển thị phần trăm. Khi không có attempts trong cửa sổ, mẫu số bằng 0 và dashboard cần thể hiện “không có dữ liệu” hoặc xử lý riêng thay vì diễn giải thành tỷ lệ lỗi bằng 0%.

Nếu muốn phân tích theo nhà cung cấp:

```promql
sum by (provider) (
  rate(business_payment_attempts_total{result="failure"}[5m])
)
/
sum by (provider) (
  rate(business_payment_attempts_total[5m])
)
```

Mẫu số phải chứa cả success và failure theo cùng định nghĩa attempt. Nếu một nhánh retry được tính vào tử số nhưng không được tính vào mẫu số, tỷ lệ sẽ sai.

## 7. Tỷ lệ chuyển đổi checkout và vấn đề cohort

Một câu hỏi phổ biến là: “Bao nhiêu checkout dẫn đến thanh toán thành công?”

Có thể ghi nhận hai Counter:

- `business.checkout.started`: số checkout bắt đầu.
- `business.checkout.completed`: số checkout hoàn tất bằng thanh toán.

Tỷ lệ giữa tốc độ hoàn tất và tốc độ bắt đầu trong cùng cửa sổ có thể dùng như một chỉ báo vận hành:

```promql
sum(rate(business_checkout_completed_total[15m]))
/
sum(rate(business_checkout_started_total[15m]))
```

Tuy nhiên, tỷ lệ này không nhất thiết là conversion rate theo cohort. Một checkout bắt đầu trước cửa sổ có thể hoàn tất bên trong cửa sổ; một checkout bắt đầu trong cửa sổ có thể chỉ hoàn tất sau đó. Vì vậy, numerator và denominator không chắc thuộc cùng một nhóm phiên.

Nếu câu hỏi chính xác là “Trong số checkout bắt đầu hôm qua, bao nhiêu phần trăm thanh toán thành công trong vòng 24 giờ?”, cần liên kết các sự kiện theo checkout/session và thời điểm bắt đầu. Đây là phân tích cohort, thường cần event store, warehouse hoặc hệ thống analytics có khả năng giữ khóa liên kết và xử lý sự kiện đến trễ. Counter tổng hợp đơn thuần không thể tái tạo cohort đó.

Khi dùng metrics cho dashboard vận hành, hãy đặt tên và mô tả rõ đây là *rolling throughput ratio* hoặc tỷ lệ hoàn tất theo cửa sổ, tránh gọi nó là cohort conversion nếu không có phép liên kết cohort thực sự.

## 8. Đo thời gian của quy trình nghiệp vụ bằng Timer

Một câu hỏi khác: “Từ lúc khách bắt đầu checkout đến lúc nhận được kết quả mất bao lâu?”

Nếu toàn bộ thao tác diễn ra đồng bộ trong một lời gọi, có thể dùng Timer quanh khối xử lý. Với quy trình kéo dài qua nhiều request hoặc nhiều service, thời gian cần được tính từ các mốc nghiệp vụ đã lưu và chỉ record khi có kết quả.

Ví dụ đo thời gian từ lúc đơn được tạo đến khi thanh toán hoàn tất:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public class CheckoutDurationMetrics {

    private final Timer checkoutCompletion;

    public CheckoutDurationMetrics(MeterRegistry registry) {
        this.checkoutCompletion = Timer.builder(
                "business.checkout.duration"
            )
            .description("Elapsed time from checkout start to completion")
            .register(registry);
    }

    public void recordCompleted(Duration elapsed) {
        if (elapsed.isNegative()) {
            throw new IllegalArgumentException(
                "Checkout duration cannot be negative"
            );
        }

        checkoutCompletion.record(elapsed);
    }
}
```

Khi checkout hoàn tất, lớp nghiệp vụ tính `Duration` từ hai timestamp đáng tin cậy rồi gọi `recordCompleted`. Nếu cần percentile, bật histogram theo yêu cầu vận hành và chọn bucket quanh các ngưỡng quan trọng.

Với tác vụ chạy trong cùng tiến trình và cần đo elapsed time chính xác, `System.nanoTime()` phù hợp hơn đồng hồ lịch. Với workflow kéo dài qua nhiều instance hoặc qua thời gian restart, cần dùng timestamp nghiệp vụ đã lưu và xác định rõ cách xử lý clock skew, sự kiện đến trễ và retry.

## 9. Theo dõi backlog hiện tại bằng Gauge

Câu hỏi: “Hiện có bao nhiêu đơn hàng đang chờ đóng gói?”

Đây là trạng thái hiện tại, không phải số đơn từng được tạo. Gauge phù hợp nếu ứng dụng có nguồn trạng thái đáng tin cậy và cập nhật giá trị khi đơn vào hoặc rời hàng đợi.

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicInteger;

public class FulfillmentQueueMetrics {

    private final AtomicInteger waitingOrders = new AtomicInteger();

    public FulfillmentQueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "business.fulfillment.waiting",
                waitingOrders,
                AtomicInteger::get
            )
            .description("Orders currently waiting for packing")
            .register(registry);
    }

    public void orderEnteredQueue() {
        waitingOrders.incrementAndGet();
    }

    public void orderLeftQueue() {
        waitingOrders.updateAndGet(value -> Math.max(0, value - 1));
    }
}
```

Giữ đối tượng `AtomicInteger` trong field để Gauge có thể đọc giá trị suốt vòng đời meter. Trong ứng dụng phân tán, mỗi instance có thể chỉ biết queue cục bộ; nếu cần backlog toàn hệ thống, hãy lấy giá trị từ broker hoặc nguồn trạng thái tập trung và xác định rõ cách tổng hợp.

Không tăng Gauge mỗi khi có đơn hàng mà không giảm khi đơn rời queue. Nếu mục tiêu là tổng số đơn đã vào queue, hãy dùng Counter riêng. Gauge biểu diễn số đang chờ tại thời điểm quan sát.

## 10. Chọn tag để phân tích mà không làm cardinality tăng cao

Tag cho phép phân tích business metric theo những chiều có ý nghĩa, nhưng mỗi tổ hợp tag tạo một meter/time series riêng.

Các chiều thường có thể kiểm soát:

- `channel`: web, mobile, store.
- `payment_provider`: các nhà cung cấp đã tích hợp.
- `result`: success, failure, timeout.
- `region`: tập vùng triển khai đã định nghĩa.
- `order_type`: standard, express, subscription.

Các giá trị cần tránh làm tag:

- `order_id`, `customer_id`, `checkout_id`.
- Email, số điện thoại hoặc dữ liệu cá nhân.
- URL chứa mã đơn hàng hoặc mã người dùng.
- Nội dung lỗi, tên file hoặc chuỗi tự do.
- SKU nếu danh mục có thể rất lớn và thay đổi thường xuyên.

Nếu cần điều tra một đơn hàng cụ thể, hãy ghi ID vào log hoặc trace với chính sách bảo vệ dữ liệu phù hợp. Metrics nên giữ các chiều tổng hợp có tập giá trị nhỏ, ổn định và có người sử dụng.

## 11. Chọn cửa sổ thời gian và cách tổng hợp

Business metric cần được đọc trong ngữ cảnh thời gian. Cùng một Counter có thể trả lời các câu hỏi khác nhau tùy cửa sổ:

- `rate(...[5m])`: tốc độ ngắn hạn để phát hiện thay đổi gần đây.
- `increase(...[1h])`: số tăng ước tính trong một giờ.
- `rate(...[1d])`: xu hướng dài hơn, nếu scrape interval và retention phù hợp.

Ví dụ số đơn đã thanh toán trong một giờ:

```promql
sum by (channel) (
  increase(business_orders_paid_total[1h])
)
```

Số liệu theo ngày có thể chịu ảnh hưởng của múi giờ, lịch bán hàng, ngày nghỉ và mùa vụ. Nếu dashboard cần ngày nghiệp vụ theo múi giờ địa phương, hãy xác định điều đó ở lớp truy vấn hoặc analytics; Prometheus lưu timestamp theo thời gian chuẩn UTC.

Khi tổng hợp nhiều instance, thường dùng `sum` cho Counter throughput và các bucket histogram tương thích. Với Gauge, chọn phép tổng hợp theo ý nghĩa: `sum` nếu mỗi instance sở hữu một phần backlog không trùng lặp; `max` nếu muốn thấy instance có queue lớn nhất. Không dùng cùng một phép tổng hợp cho mọi meter.

## 12. Ghi metrics đúng thời điểm của event

Business metric chỉ có ý nghĩa nếu được tăng ở đúng thời điểm nghiệp vụ được xác nhận.

Ví dụ, nếu tăng `orders.paid` trước khi transaction lưu trạng thái PAID commit, transaction có thể rollback nhưng Counter vẫn tăng. Một cách tiếp cận trong Spring là phát domain event trong transaction và xử lý metric sau commit:

```java
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

record OrderPaidEvent(String channel) {}

@Component
public class PaidOrderMetricsListener {

    private final MeterRegistry registry;

    public PaidOrderMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaidEvent event) {
        registry.counter(
            "business.orders.paid",
            "channel", event.channel()
        ).increment();
    }
}
```

Listener chỉ xử lý event khi transaction chứa event đã commit. Giá trị `channel` vẫn phải được chuẩn hóa về tập giá trị hữu hạn trước khi dùng làm tag.

Publisher phải phát `OrderPaidEvent` trong một transaction đang hoạt động, sau khi xác định chuyển trạng thái PAID. Nếu event được phát ngoài transaction, listener `@TransactionalEventListener` mặc định sẽ không xử lý event đó.

Cách này tránh đếm một đơn bị rollback. Tuy nhiên, metric không phải sổ cái bền vững: tiến trình có thể dừng sau commit nhưng trước khi listener cập nhật Counter; hoặc event có thể được giao lại và bị đếm lặp. Nếu số liệu cần đầy đủ để đối soát, dùng transactional outbox hoặc pipeline sự kiện có idempotency và kho dữ liệu bền vững. Metrics chỉ nên là tín hiệu tổng hợp phục vụ quan sát.

## 13. Xử lý retry, duplicate và event đến trễ

Một event nghiệp vụ có thể được phát lại khi consumer retry, broker giao ít nhất một lần hoặc dịch vụ phục hồi sau sự cố. Counter không biết event đã được xử lý trước đó hay chưa.

Cần xác định rõ:

- Đếm mỗi lần giao event hay mỗi chuyển trạng thái nghiệp vụ?
- Retry thanh toán là một attempt mới hay tiếp tục cùng một attempt?
- Duplicate event có được loại bằng event ID hoặc business key ở tầng xử lý không?
- Metric ghi ở nơi phát event hay nơi consumer xác nhận kết quả?
- Sự kiện đến trễ được tính vào thời điểm xảy ra hay thời điểm xử lý?

Nếu mục tiêu là đếm payment attempts, mỗi lần thử hợp lệ nên được ghi nhận một lần. Nếu mục tiêu là đếm đơn đã thanh toán, nhiều event retry cho cùng một order không được làm tăng số đơn. Cần idempotency ở tầng nghiệp vụ hoặc consumer trước khi cập nhật metric.

Counter được cập nhật trong bộ nhớ và có thể reset khi process restart. Prometheus có thể xử lý counter reset khi dùng `rate` hoặc `increase`, nhưng không thể khôi phục một event chưa từng được scrape hoặc đã bị mất trước khi export. Vì vậy, không dùng raw Counter làm dữ liệu kiểm toán.

## 14. Business metrics khác gì technical metrics?

Hai nhóm metrics bổ sung cho nhau:

| Business metrics | Technical metrics |
|---|---|
| Đơn đã thanh toán | HTTP request rate |
| Tỷ lệ payment failure | HTTP 5xx rate |
| Giá trị đơn hàng | CPU và memory |
| Thời gian checkout | Server request latency |
| Đơn đang chờ đóng gói | Executor queue và thread pool |
| Doanh thu vận hành theo thời gian | Database connection pool |

Ví dụ, nếu số đơn thanh toán giảm, technical metrics giúp tìm nguyên nhân:

- HTTP request rate có giảm theo không?
- Tỷ lệ 5xx có tăng không?
- Payment provider latency có tăng không?
- Database pool có pending connection không?
- Checkout latency có vượt ngưỡng không?

Business metrics cho biết tác động lên hoạt động kinh doanh; technical metrics giúp xác định tình trạng hệ thống có thể gây ra tác động đó.

## 15. Những câu hỏi không nên giải quyết chỉ bằng metrics

| Câu hỏi | Vì sao metrics tổng hợp chưa đủ | Nguồn phù hợp |
|---|---|---|
| Khách hàng nào bị charge hai lần? | Cần định danh và lịch sử giao dịch cụ thể | Ledger, payment record, log/trace |
| Doanh thu ròng chính xác theo kỳ kế toán là bao nhiêu? | Cần xử lý hoàn tiền, điều chỉnh, thuế, đối soát và quy tắc kế toán | Sổ cái và hệ thống tài chính |
| Bao nhiêu khách hàng duy nhất đã mua trong tháng? | Counter đếm sự kiện, không tự khử trùng người dùng theo cohort | Warehouse hoặc analytics có identity resolution |
| Vì sao một nhóm khách hàng rời bỏ checkout? | Cần liên kết hành trình và ngữ cảnh người dùng | Event analytics, nghiên cứu người dùng |
| Đơn hàng nào đang bị treo? | Gauge chỉ cho biết số lượng tổng hợp | Database, queue inspection, trace |
| Một khách hàng đã trải qua những bước nào? | Metrics không lưu chuỗi sự kiện cá nhân | Event store hoặc audit log |

Metrics vẫn có thể cung cấp chỉ báo tổng quan cho những lĩnh vực này, nhưng không chứa đủ dữ liệu để trả lời câu hỏi ở cấp bản ghi hoặc cohort.

## 16. Thiết kế dashboard business metrics có thể hành động

Một dashboard hữu ích nên nhóm các panel theo quyết định vận hành:

- **Nhu cầu:** đơn đã thanh toán mỗi phút, checkout bắt đầu, số đơn theo kênh.
- **Chất lượng giao dịch:** tỷ lệ payment failure, timeout và refund.
- **Giá trị:** giá trị đơn hàng trung bình, p95 order value, tốc độ ghi nhận doanh thu.
- **Hiệu suất quy trình:** checkout duration p50/p95/p99.
- **Backlog:** đơn đang chờ đóng gói, tuổi của backlog hoặc số tác vụ fulfillment đang hoạt động.

Mỗi panel nên có mô tả metric, đơn vị, cửa sổ thời gian và tag đang dùng. Alert chỉ nên tạo khi có hành động cụ thể, ví dụ payment failure rate tăng vượt ngưỡng trong khi traffic đủ lớn. Không tạo cảnh báo cho mọi biến động nhỏ của doanh thu hoặc số đơn vì hoạt động kinh doanh có thể có chu kỳ theo giờ và ngày.

## 17. Kiểm thử định nghĩa và instrumentation

Kiểm thử business metrics cần xác minh cả số đếm lẫn ngữ nghĩa event.

Ví dụ với Counter:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMetricsTest {

    @Test
    void countsPaidOrdersByChannel() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.orderPaid("web");
        metrics.orderPaid("web");
        metrics.orderPaid("mobile");

        assertThat(
            registry.get("business.orders.paid")
                .tag("channel", "web")
                .counter()
                .count()
        ).isEqualTo(2.0);

        assertThat(
            registry.get("business.orders.paid")
                .tag("channel", "mobile")
                .counter()
                .count()
        ).isEqualTo(1.0);

        registry.close();
    }
}
```

Test này xác nhận phép phân nhóm theo channel. Trong production code, nên dùng enum hoặc validation để bảo đảm giá trị tag hợp lệ.

Ngoài test meter, cần test luồng nghiệp vụ:

- Transaction rollback không làm tăng số đơn đã thanh toán.
- Một order chuyển sang PAID chỉ được đếm một lần.
- Duplicate event không làm tăng Counter lần nữa nếu định nghĩa là đơn duy nhất.
- Refund được ghi vào metric riêng.
- Checkout duration dùng đúng hai mốc bắt đầu và kết thúc.
- Gauge giảm khi đơn rời hàng đợi.
- Tag không chứa order ID hoặc customer ID.

Dùng `SimpleMeterRegistry` để kiểm tra instrumentation trong unit test; dùng integration test để xác nhận event lifecycle, transaction và export schema.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đếm order created thay cho order paid | Số liệu không phản ánh doanh thu đã xác nhận | Đặt tên và event theo trạng thái nghiệp vụ |
| Ghi Counter trước transaction commit | Rollback vẫn bị tính | Ghi sau commit hoặc qua event pipeline |
| Đếm mỗi lần delivery của event | Duplicate làm tăng số liệu | Idempotency trước khi ghi metric |
| Dùng Counter để biểu diễn backlog | Giá trị không giảm khi xử lý xong | Dùng Gauge cho trạng thái hiện tại |
| Dùng ID khách hàng làm tag | Cardinality tăng rất cao và có rủi ro dữ liệu cá nhân | Dùng log/trace hoặc analytics |
| Gọi rolling ratio là cohort conversion | Numerator và denominator có thể thuộc các nhóm khác nhau | Dùng cohort analytics có liên kết sự kiện |
| Cộng nhiều loại tiền vào một Counter | Đơn vị không còn ý nghĩa | Tách theo currency hoặc quy đổi theo chính sách |
| Dùng Counter làm sổ cái doanh thu | Có thể mất, reset hoặc đếm lặp | Dùng ledger làm nguồn sự thật |
| Alert khi traffic quá thấp | Một vài event làm tỷ lệ dao động mạnh | Kết hợp điều kiện về số lượng mẫu |
| Tổng hợp Gauge bằng sum không đúng | Có thể đếm trùng trạng thái giữa instance | Xác định quyền sở hữu và semantics trước khi aggregate |

## 19. Checklist chọn business metric

- [ ] Câu hỏi hỗ trợ quyết định cụ thể nào?
- [ ] Đơn vị được đếm là event, entity, attempt hay trạng thái?
- [ ] Đã định nghĩa thời điểm event được xác nhận?
- [ ] Nếu là tỷ lệ, tử số và mẫu số có cùng semantics không?
- [ ] Đây là rolling ratio hay cohort conversion?
- [ ] Đã chọn đúng Counter, Timer, DistributionSummary, Gauge hoặc LongTaskTimer?
- [ ] Đơn vị và currency có nhất quán không?
- [ ] Tag có tập giá trị hữu hạn và không chứa dữ liệu định danh không?
- [ ] Duplicate, retry, rollback và event đến trễ được xử lý thế nào?
- [ ] Cửa sổ thời gian có phù hợp với chu kỳ nghiệp vụ không?
- [ ] Có nguồn dữ liệu bền vững để đối soát khi cần không?
- [ ] Có người sở hữu dashboard và hành động khi metric bất thường không?
- [ ] Đã kiểm thử cả meter lẫn luồng nghiệp vụ tạo event chưa?

Một business metric tốt bắt đầu từ câu hỏi và định nghĩa nghiệp vụ rõ ràng. Counter trả lời số sự kiện và tốc độ; Timer đo thời lượng quy trình; DistributionSummary mô tả phân bố giá trị; Gauge phản ánh trạng thái hiện tại. Hãy giữ tag ở mức tổng hợp, ghi nhận đúng thời điểm nghiệp vụ được xác nhận và dùng hệ thống dữ liệu bền vững cho đối soát hoặc phân tích cohort. Khi kết hợp business metrics với technical metrics, đội ngũ có thể thấy cả tác động lên hoạt động kinh doanh lẫn nguyên nhân kỹ thuật đứng phía sau.

## Tài liệu tham khảo

- [Micrometer Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) — đếm sự kiện và cách diễn giải counter.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — đo thời lượng và phân phối thời gian.
- [Micrometer Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html) — ghi nhận phân bố các giá trị số.
- [Micrometer Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html) — đo trạng thái hiện tại.
- [Prometheus Metric Types](https://prometheus.io/docs/concepts/metric_types/) — semantics của counter, gauge, histogram và summary.

