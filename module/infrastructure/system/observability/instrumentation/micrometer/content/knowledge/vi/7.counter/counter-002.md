# Tăng một đơn vị hoặc một lượng dương có ý nghĩa

Counter là meter dùng để đếm các sự kiện tích lũy theo thời gian. Mỗi khi sự kiện được ghi nhận, ứng dụng tăng Counter thêm một đơn vị hoặc một lượng dương tương ứng với số sự kiện. Ví dụ, một đơn hàng được tạo thành công làm Counter tăng một; một lô nhập gồm 25 bản ghi hợp lệ có thể làm Counter tăng 25 nếu metric đó đếm số bản ghi.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, Counter là một trong những loại meter nền tảng bên cạnh Gauge, Timer và Distribution Summary. Khi dùng Counter, cần xác định chính xác sự kiện nào được đếm, thời điểm ghi nhận, ý nghĩa của một lần tăng và đơn vị của lượng tăng. Những quyết định này giúp số đo phản ánh đúng hoạt động nghiệp vụ và có thể diễn giải đáng tin cậy trong hệ thống giám sát.

## 1. Ngữ nghĩa của Counter

Counter biểu diễn một giá trị tích lũy chỉ tăng trong suốt vòng đời của meter. Ứng dụng có thể tăng một đơn vị bằng increment() hoặc tăng một lượng dương bằng increment(amount).

Ví dụ:

~~~java
Counter requests = registry.counter("checkout.requests");

requests.increment();       // Tăng một request
requests.increment(5.0);    // Tăng thêm năm request
~~~

Sau hai lệnh trên, giá trị tích lũy của Counter tăng thêm sáu. Giá trị Counter không được giảm để biểu diễn trạng thái hiện tại. Trong Micrometer, đối số của increment(amount) phải là số dương. Nếu không có sự kiện cần ghi nhận, không gọi increment; không truyền 0 hoặc số âm để biểu diễn không thay đổi hay giảm số đếm.

Counter phù hợp với các sự kiện có thể cộng dồn:

- Số đơn hàng được tạo.
- Số lần thanh toán thành công hoặc thất bại.
- Số message được xử lý.
- Số byte hoặc bản ghi đã xử lý, nếu mỗi lần tăng có đơn vị nhất quán.
- Số lần một thao tác nghiệp vụ được thực hiện.

Counter không phù hợp để biểu diễn số kết nối hiện đang mở, số request đang chạy hoặc số phần tử hiện có trong queue, vì các giá trị đó có thể tăng và giảm. Dùng Gauge cho trạng thái hiện tại và Counter cho số sự kiện đã xảy ra.

## 2. Tăng một đơn vị khi một sự kiện xảy ra

Với sự kiện đơn lẻ, cách dùng phổ biến nhất là gọi increment() đúng một lần tại thời điểm sự kiện được xác nhận.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final Counter ordersCreated;

    public OrderService(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("orders.created")
                .description("Number of orders successfully created")
                .baseUnit("orders")
                .register(registry);
    }

    public void createOrder(Order order) {
        orderRepository.save(order);
        ordersCreated.increment();
    }
}
~~~

Đoạn code minh họa ý tưởng: sau khi lưu đơn hàng thành công, Counter tăng một. Trong ứng dụng thực tế, orderRepository cần được inject và transaction phải được thiết kế sao cho thời điểm ghi nhận phù hợp với kết quả nghiệp vụ. Nếu việc lưu đơn hàng còn có thể rollback sau khi phương thức trả về, cần đặt instrumentation tại ranh giới xác nhận thành công phù hợp, chẳng hạn sau khi transaction commit hoặc thông qua sự kiện nghiệp vụ đã được xác nhận.

Tên metric nên mô tả sự kiện đã xảy ra, chẳng hạn orders.created hoặc payments.completed. Description giải thích ý nghĩa cụ thể của số đếm. Nếu Counter đo số đơn hàng, base unit có thể là orders; nếu đo số message, dùng messages. Đừng trộn nhiều loại đại lượng vào cùng một Counter.

Có thể lấy Counter bằng API tiện lợi:

~~~java
Counter ordersCreated = registry.counter("orders.created");
~~~

Hoặc dùng builder khi cần description, base unit và tag:

~~~java
Counter ordersCreated = Counter.builder("orders.created")
        .description("Number of successfully created orders")
        .baseUnit("orders")
        .tag("channel", "web")
        .register(registry);
~~~

Nên đăng ký meter một lần khi khởi tạo component rồi tái sử dụng. Không cần tạo và đăng ký lại Counter cho từng request. Registry quản lý meter theo tên và tập tag; việc dùng lại cùng một meter giúp tránh thao tác đăng ký lặp không cần thiết.

## 3. Tăng một lượng dương cho lô dữ liệu

increment(amount) hữu ích khi một thao tác đại diện cho nhiều sự kiện cùng loại. Ví dụ, một batch import có 25 bản ghi hợp lệ và metric cần đếm tổng số bản ghi đã nhập:

~~~java
int importedCount = batchResult.successfulRecords();

if (importedCount > 0) {
    importedRecords.increment(importedCount);
}
~~~

Điều kiện kiểm tra bảo đảm chỉ truyền lượng dương. Nếu batch rỗng, không có bản ghi nào được ghi nhận nên Counter không thay đổi.

Cần xác định metric đếm **số lần xử lý batch** hay **số bản ghi trong batch**. Đây là hai đại lượng khác nhau:

~~~java
// Đếm mỗi lần một batch được xử lý thành công.
processedBatches.increment();

// Đếm tổng số bản ghi hợp lệ trong batch.
if (successfulRecords > 0) {
    processedRecords.increment(successfulRecords);
}
~~~

Nếu một batch gồm 25 bản ghi, Counter batch tăng một còn Counter record tăng 25. Đặt tên metric và description thể hiện rõ đơn vị này để dashboard không diễn giải nhầm.

Lượng tăng phải có ý nghĩa nhất quán. Không dùng cùng một Counter lúc thì tăng theo số batch, lúc lại tăng theo số bản ghi. Nếu cần theo dõi cả hai, đăng ký hai meter riêng.

## 4. Chỉ tăng tại đúng thời điểm nghiệp vụ

Counter phản ánh sự kiện mà mã instrumentation ghi nhận. Vì vậy, vị trí gọi increment quyết định số liệu có ý nghĩa hay không.

Ví dụ ghi nhận kết quả thanh toán:

~~~java
public PaymentResult pay(PaymentRequest request) {
    try {
        PaymentResult result = paymentGateway.charge(request);
        paymentsSucceeded.increment();
        return result;
    } catch (PaymentException ex) {
        paymentsFailed.increment();
        throw ex;
    }
}
~~~

Ở đây hai Counter biểu diễn hai kết quả riêng biệt. Chỉ khi cổng thanh toán trả về thành công thì Counter thành công tăng; khi phát sinh PaymentException thì Counter thất bại tăng. Trong hệ thống thực tế, cần xác định rõ những lỗi nào được tính là thất bại nghiệp vụ và cách xử lý timeout khi kết quả từ hệ thống ngoài chưa xác định.

Một số sai lệch thường gặp:

- Tăng Counter trước khi thao tác hoàn tất, khiến số đếm thành công bao gồm cả thao tác thất bại.
- Gọi increment ở cả service và event listener cho cùng một sự kiện, làm đếm trùng.
- Retry một thao tác nhưng không phân biệt số lần thử với số nghiệp vụ hoàn tất.
- Tăng Counter khi nhận yêu cầu, sau đó lại dùng tên metric như thể yêu cầu đã thành công.

Hãy đặt tên theo sự kiện thực sự được đo. Ví dụ, requests.received đếm yêu cầu đã nhận; payment.attempts đếm lần thử thanh toán; payments.completed đếm thanh toán đã hoàn tất. Nếu muốn đo cả lần thử và kết quả cuối cùng, dùng các Counter riêng và tag outcome có tập giá trị hữu hạn.

Counter không tự loại bỏ sự kiện trùng lặp. Nếu cùng một message được giao lại nhiều lần và consumer xử lý lại, mỗi lần gọi increment sẽ được đếm. Muốn metric phản ánh số nghiệp vụ duy nhất, ứng dụng cần cơ chế idempotency hoặc phát sự kiện sau khi xác nhận rằng nghiệp vụ chỉ được ghi nhận một lần. Không đưa orderId hoặc messageId vào tag để cố gắng khử trùng lặp; các ID này làm cardinality tăng cao.

## 5. Phân loại Counter bằng tag có kiểm soát

Một Counter có thể được chia thành các chuỗi thời gian theo tag. Ví dụ đếm kết quả thanh toán:

~~~java
Counter success = Counter.builder("payments.completed")
        .description("Completed payments")
        .tag("outcome", "success")
        .register(registry);

Counter failure = Counter.builder("payments.completed")
        .description("Completed payments")
        .tag("outcome", "failure")
        .register(registry);
~~~

Hai meter có cùng tên nhưng khác giá trị outcome, nên backend có thể phân biệt số thanh toán thành công và thất bại. Trong thiết kế thực tế, có thể tạo meter bằng một factory hoặc helper để tránh lặp code.

Tag phù hợp cho Counter thường có tập giá trị nhỏ, như:

- outcome: success, failure.
- channel: web, mobile, partner.
- payment_method: card, bank_transfer, wallet.
- message_type: order_created, order_cancelled.

Tránh dùng userId, orderId, email, requestId, sessionId hoặc messageId làm tag. Mỗi giá trị mới có thể tạo một time series mới. Counter có số lượng tag không kiểm soát có thể làm tăng nhanh bộ nhớ, dung lượng lưu trữ và chi phí truy vấn.

Nếu muốn phân biệt theo dịch vụ, môi trường và vùng triển khai, hãy dùng common tags do cấu hình ứng dụng cung cấp. Giữ tên khóa và tập giá trị thống nhất giữa các instance để số liệu có thể tổng hợp đúng.

## 6. Counter và cách diễn giải theo thời gian

Giá trị Counter là tổng tích lũy trong vòng đời của meter. Khi ứng dụng khởi động lại, Counter trong tiến trình mới thường bắt đầu lại từ 0. Vì vậy, không nên nhìn giá trị thô của một instance rồi kết luận đó là tổng số sự kiện vĩnh viễn của toàn hệ thống.

Trong Prometheus, Counter thường được xuất dưới dạng tên metric có hậu tố _total theo quy ước đặt tên của registry. Ví dụ, meter orders.created có thể xuất hiện là orders_created_total. Hãy xác minh tên thực tế trên endpoint thay vì tự thêm hậu tố vào tên meter.

Để tính tốc độ sự kiện, dùng rate() trên một cửa sổ thời gian:

~~~promql
sum(rate(orders_created_total[5m]))
~~~

Truy vấn trên cộng tốc độ tạo đơn hàng mỗi giây của các chuỗi thời gian trong năm phút gần nhất. Có thể nhóm theo tag để so sánh dịch vụ hoặc môi trường:

~~~promql
sum by (service, environment) (
  rate(orders_created_total[5m])
)
~~~

Để ước lượng tổng số sự kiện tăng trong một khoảng thời gian, dùng increase():

~~~promql
sum(increase(orders_created_total[1h]))
~~~

rate() và increase() xử lý hiện tượng Counter reset khi tiến trình khởi động lại tốt hơn việc tự lấy hiệu hai giá trị thô. Cửa sổ truy vấn cần đủ mẫu scrape để tạo kết quả ổn định. Với dashboard vận hành, chọn cửa sổ phù hợp chu kỳ scrape và mức biến động của traffic.

Counter là số đếm tích lũy, còn rate là tốc độ sự kiện trong một khoảng thời gian. Dashboard cần ghi rõ đơn vị: số đơn mỗi giây, số message mỗi phút hoặc tổng số thanh toán trong một giờ. Tránh gắn nhãn "số request hiện tại" cho một truy vấn rate vì đó là hai khái niệm khác nhau.

## 7. Phân biệt Counter với Gauge

| Tiêu chí | Counter | Gauge |
|---|---|---|
| Đại lượng | Sự kiện tích lũy | Trạng thái hoặc giá trị tại thời điểm đọc |
| Chiều biến đổi | Chỉ tăng | Có thể tăng hoặc giảm |
| Ví dụ | Tổng đơn hàng đã tạo | Số đơn hàng đang chờ xử lý |
| Truy vấn thường dùng | rate(), increase() | Giá trị hiện tại, max_over_time(), avg_over_time() tùy nhu cầu |
| Khi nào dùng | Khi một sự kiện xảy ra | Khi muốn quan sát mức hiện tại |

Ví dụ, mỗi khi một message được xử lý, tăng Counter processedMessages. Để theo dõi số message đang chờ trong queue, dùng Gauge đọc độ sâu queue. Nếu queue giảm từ 100 xuống 20, Gauge cần phản ánh mức giảm; Counter không thể biểu diễn trạng thái này bằng cách decrement.

## 8. Kiểm thử Counter

Có thể dùng SimpleMeterRegistry trong unit test để kiểm tra số lần tăng mà không cần kết nối Prometheus hoặc backend bên ngoài:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderCounterTest {

    @Test
    void incrementsByOneAndByPositiveAmount() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter counter = Counter.builder("orders.created")
                .baseUnit("orders")
                .register(registry);

        assertThat(counter.count()).isZero();

        counter.increment();
        assertThat(counter.count()).isEqualTo(1.0);

        counter.increment(3.0);
        assertThat(counter.count()).isEqualTo(4.0);

        registry.close();
    }
}
~~~

Kiểm thử này xác nhận hai cách tăng tạo ra giá trị tích lũy như mong đợi. Có thể bổ sung test cho batch rỗng để bảo đảm code không gọi increment(0), và test nghiệp vụ để xác nhận chỉ kết quả thành công mới tăng Counter thành công.

Với code chạy đồng thời, nên tái sử dụng Counter do registry quản lý thay vì tự duy trì biến số đếm không đồng bộ. Các triển khai registry của Micrometer được thiết kế để ghi nhận meter trong môi trường đa luồng; tuy nhiên, logic nghiệp vụ vẫn phải tránh ghi nhận cùng một sự kiện hai lần.

Unit test với SimpleMeterRegistry chỉ kiểm tra logic instrumentation trong bộ nhớ. Để xác minh pipeline, cần kiểm tra endpoint export, trạng thái scrape hoặc log export, rồi truy vấn dữ liệu ở backend.

## 9. Những câu hỏi cần trả lời khi thiết kế Counter

Trước khi thêm một Counter, hãy xác định:

1. **Sự kiện nào được đếm?** Một yêu cầu được nhận, một lần thử, hay một nghiệp vụ hoàn tất?
2. **Thời điểm nào được xem là đã xảy ra?** Khi nhận message, khi xử lý xong, hay sau khi transaction commit?
3. **Một lần tăng đại diện cho bao nhiêu?** Một sự kiện, một batch, hay số bản ghi trong batch?
4. **Lượng tăng có luôn dương và cùng đơn vị không?** Nếu không có sự kiện, bỏ qua lần tăng; nếu cần giá trị giảm, hãy dùng Gauge.
5. **Tag nào cần để phân loại?** Chỉ chọn các chiều có tập giá trị giới hạn và có mục đích truy vấn.
6. **Dashboard cần hiển thị gì?** Tổng tích lũy, tốc độ theo giây hay số sự kiện trong một khoảng thời gian?

Khi sự kiện, thời điểm và đơn vị tăng được xác định rõ, Counter sẽ cung cấp số liệu tích lũy có ý nghĩa. Micrometer giúp ứng dụng ghi nhận sự kiện bằng increment() hoặc increment(amount); hệ thống giám sát có thể dùng rate và increase để diễn giải tốc độ hoặc lượng sự kiện theo thời gian, trong khi tag có kiểm soát giữ cho dữ liệu dễ truy vấn và vận hành.
