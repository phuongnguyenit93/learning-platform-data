# Chọn tên, đơn vị và tag cho bộ đếm

Counter là meter dùng để đếm số lần một sự kiện xảy ra hoặc tổng lượng một đại lượng chỉ tăng. Một bộ đếm tốt phải có ngữ nghĩa rõ ràng: người đọc nhìn vào tên, mô tả, đơn vị và tag có thể hiểu chính xác điều gì đang được cộng thêm, khi nào việc cộng xảy ra và có thể phân tích theo những chiều nào.

Thiết kế Counter không bắt đầu từ việc đặt một cái tên nghe có vẻ hợp lý. Trước hết cần xác định sự kiện được tính, điểm ghi nhận sự kiện, câu hỏi vận hành cần trả lời và các chiều phân nhóm có tập giá trị được kiểm soát. Sau đó mới chọn tên meter, đơn vị và tag để dữ liệu nhất quán giữa mã ứng dụng, backend và dashboard.

## 1. Xác định chính xác điều Counter đếm

Counter trong Micrometer biểu diễn một giá trị tích lũy chỉ tăng. Mỗi lần gọi increment, giá trị tăng thêm một; có thể tăng một lượng dương nếu mỗi lần ghi nhận đại diện cho nhiều đơn vị.

Các ví dụ phù hợp:

- Số đơn hàng được tạo thành công.
- Số lần thanh toán được thử.
- Số request bị từ chối.
- Tổng số byte đã gửi.
- Số thông điệp đã xử lý.

Counter phù hợp khi câu hỏi là “đã xảy ra bao nhiêu lần?” hoặc “tổng lượng đã tích lũy là bao nhiêu?”. Nó không phù hợp để biểu diễn trạng thái hiện tại có thể tăng và giảm, chẳng hạn số request đang chạy, số kết nối đang mở hoặc độ dài hàng đợi. Những giá trị đó thường cần Gauge.

### Chọn đúng điểm tăng bộ đếm

Tên metric chỉ có ý nghĩa nếu thời điểm tăng được định nghĩa nhất quán:

| Sự kiện cần đếm | Thời điểm tăng phù hợp | Điều cần phân biệt |
| --- | --- | --- |
| Đơn hàng được tạo | Sau khi thao tác tạo đơn được xác nhận thành công | Không tăng chỉ vì request đã đến controller nếu giao dịch còn có thể rollback. |
| Lần thử thanh toán | Khi một lần gọi cổng thanh toán thực sự được gửi đi | Retry là một lần thử mới và có thể được tính riêng. |
| Thanh toán hoàn tất | Khi hệ thống xác nhận thanh toán thành công | Không đồng nhất với số lần thử thanh toán. |
| Request bị từ chối | Tại điểm quyết định từ chối request | Cần thống nhất có tính cả lỗi xác thực, giới hạn tốc độ và lỗi nghiệp vụ hay không. |
| Message được xử lý | Khi xử lý đạt trạng thái được định nghĩa là hoàn tất | Cần phân biệt message nhận được, bắt đầu xử lý và xử lý thành công. |

Một request có thể tạo ra nhiều sự kiện khác nhau. Ví dụ, một khách hàng thanh toán một lần nhưng hệ thống thử gọi cổng thanh toán ba lần do timeout. Nếu metric là payment attempts, kết quả cần tăng ba; nếu metric là payments completed, chỉ tăng khi thanh toán hoàn tất theo định nghĩa nghiệp vụ. Không nên dùng một tên metric chung khiến hai khái niệm này bị trộn lẫn.

Counter thường được lưu trong bộ nhớ của tiến trình và có thể bắt đầu lại khi ứng dụng khởi động lại. Backend như Prometheus xử lý việc counter reset khi tính rate hoặc increase. Vì vậy, không dùng giá trị Counter thô làm số lượng tích lũy vĩnh viễn của nghiệp vụ; dữ liệu giao dịch chuẩn vẫn phải nằm trong hệ thống lưu trữ nghiệp vụ.

## 2. Đặt tên Counter theo sự kiện và đại lượng

Tên meter nên mô tả đại lượng hoặc sự kiện được đếm, ổn định theo thời gian và không chứa giá trị tag. Với Micrometer, nên dùng tên chữ thường, phân tách các phần bằng dấu chấm. Registry sẽ chuyển tên sang quy ước của backend đích.

Ví dụ:

| Tên Micrometer | Ý nghĩa |
| --- | --- |
| orders.created | Số đơn hàng được tạo thành công. |
| payments.attempted | Số lần thử thanh toán. |
| payments.completed | Số thanh toán hoàn tất. |
| messages.processed | Số message được xử lý theo định nghĩa đã thống nhất. |
| http.server.rejected | Số request bị từ chối. |
| bytes.transmitted | Tổng số byte đã truyền. |

Tên nên trả lời được “đang đếm cái gì?” mà không cần mở mã nguồn. Phần mô tả bổ sung điều kiện cụ thể để tránh cách hiểu khác nhau.

### Các cách đặt tên nên tránh

| Tên không rõ hoặc dễ gây nhầm | Vấn đề | Cách đặt rõ hơn |
| --- | --- | --- |
| counter1 | Không thể hiện sự kiện. | orders.created |
| total | Không cho biết tổng của đại lượng nào. | payments.completed |
| order_counter | Nhấn mạnh cách cài đặt thay vì ý nghĩa. | orders.created |
| orders.created.web | Nhúng một giá trị phân nhóm vào tên, làm phát sinh nhiều tên metric. | orders.created với tag channel=web |
| orders.success và orders.failure | Có thể tạo hai metric cho cùng một khái niệm kết quả. | orders.processed với tag outcome=success/failure, nếu hai kết quả cần so sánh cùng nhau. |
| requests.per.second | Rate là phép tính từ counter theo thời gian, không phải giá trị tích lũy được đếm. | http.server.requests và truy vấn rate() ở Prometheus. |

Không đưa tên môi trường, tên pod, ID người dùng hoặc ID đơn hàng vào tên meter. Những chiều cần phân tích nên được biểu diễn bằng tag có miền giá trị kiểm soát.

## 3. Chọn đơn vị phù hợp

Đơn vị trả lời câu hỏi “mỗi lần tăng đại diện cho bao nhiêu?”. Với Counter đếm sự kiện, đơn vị tự nhiên thường là thực thể hoặc sự kiện được đếm, chẳng hạn orders, requests, messages hoặc attempts. Với Counter cộng dồn đại lượng, đơn vị có thể là bytes hoặc records.

Micrometer cho phép khai báo base unit khi tạo meter. Base unit giúp mô tả đại lượng mà meter ghi nhận; đây là thông tin ngữ nghĩa, không phải tốc độ theo thời gian.

Ví dụ:

~~~java
Counter.builder("orders.created")
        .description("Number of orders successfully created")
        .baseUnit("orders")
        .register(registry);
~~~

~~~java
Counter.builder("bytes.transmitted")
        .description("Total number of bytes transmitted")
        .baseUnit("bytes")
        .register(registry);
~~~

Đối với bộ đếm sự kiện, việc khai báo base unit có thể giúp người đọc hiểu đại lượng đang được đếm; nếu quy ước dự án không khai báo đơn vị cho số lần xảy ra, hãy mô tả rõ trong description. Không gắn đơn vị thời gian như seconds hoặc requests_per_second cho một Counter chỉ đếm số sự kiện. Tốc độ sự kiện được tính bằng cách lấy độ thay đổi của counter chia cho thời gian.

### Đơn vị và phép tính rate

Giả sử Counter orders.created đếm số đơn hàng. Giá trị tích lũy là số đơn hàng được tạo kể từ khi tiến trình bắt đầu. Khi dùng Prometheus:

- rate(orders_created_total[5m]) biểu diễn tốc độ đơn hàng mỗi giây trong cửa sổ năm phút.
- increase(orders_created_total[1h]) ước lượng số đơn hàng được tạo trong một giờ.

Rate có đơn vị “orders mỗi giây” dù base unit của Counter là orders. Không cần tạo một Counter khác có tên orders.per.second để lưu rate. Cũng không nên đổi base unit của Counter thành orders/second vì như vậy sẽ mô tả sai dữ liệu được ghi.

Với byte, nếu mỗi lần gọi increment(bytesSent) cộng số byte vừa gửi, Counter bytes.transmitted biểu diễn tổng byte. Có thể tính byte/giây từ rate ở backend. Nếu cần phân bố kích thước của từng payload hoặc từng lần gửi, DistributionSummary thường phù hợp hơn vì nó giữ thông tin phân bố, không chỉ tổng lượng.

## 4. Chọn tag theo câu hỏi cần phân tích

Tag tạo các chiều lọc và nhóm cho Counter. Chỉ thêm tag khi có câu hỏi vận hành hoặc nghiệp vụ cụ thể cần trả lời.

Ví dụ với orders.created:

| Tag | Giá trị mẫu | Câu hỏi có thể trả lời |
| --- | --- | --- |
| channel | web, mobile, partner | Kênh nào tạo ra đơn hàng? |
| region | ap-southeast-1, ap-northeast-1 | Số đơn hàng theo khu vực triển khai thay đổi ra sao? |
| outcome | success, failure | Kết quả xử lý được phân bố thế nào? |

Không cần thêm tất cả các tag này nếu dashboard không dùng chúng. Mỗi tag bổ sung làm tăng số tổ hợp series. Chọn số chiều nhỏ nhất vẫn trả lời được câu hỏi.

### Ưu tiên miền giá trị hữu hạn

Tag phù hợp thường lấy từ enum, danh mục cấu hình được quản lý hoặc route template:

- channel: web, mobile, partner.
- outcome: success, failure, rejected.
- payment_method: card, bank_transfer, wallet.
- method: GET, POST, PUT, DELETE.
- status: nhóm mã trạng thái đã chuẩn hóa.

Tránh dùng các giá trị biến thiên cao như user_id, order_id, request_id, session_id, email, token, exception message hoặc URL đầy đủ có UUID. Các giá trị này có thể tạo ra một series mới cho gần như mỗi request hoặc thực thể, làm cardinality tăng mạnh và có thể làm lộ dữ liệu nhạy cảm.

Nếu cần tra cứu một giao dịch hoặc request cụ thể, hãy dùng log hoặc trace với chính sách truy cập phù hợp. Metrics nên giữ các nhóm tổng hợp.

### Ước lượng cardinality

Giả sử Counter có ba tag:

- channel có 3 giá trị;
- outcome có 2 giá trị;
- region có 4 giá trị.

Số tổ hợp tối đa của các tag là:

\[
3 \times 2 \times 4 = 24
\]

Đây là mức tối đa cho một metric trước khi tính các label do hạ tầng hoặc backend thêm vào. Nếu một tag có 100.000 user ID, mức tổ hợp sẽ tăng từ 24 lên đến 2.400.000. Vì vậy, không dùng định danh cá nhân làm tag cho Counter.

## 5. Ví dụ thiết kế Counter hoàn chỉnh

Giả sử nhóm đơn hàng cần biết số đơn được tạo thành công theo kênh. Sự kiện được tính là đơn hàng đã được chấp nhận và lưu thành công. Miền giá trị channel được giới hạn bằng enum.

~~~java
public enum OrderChannel {
    WEB("web"),
    MOBILE("mobile"),
    PARTNER("partner");

    private final String tagValue;

    OrderChannel(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Đăng ký Counter một lần cho mỗi channel:

~~~java
import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {

    private final Map<OrderChannel, Counter> createdByChannel;

    public OrderMetrics(MeterRegistry registry) {
        Map<OrderChannel, Counter> counters = new EnumMap<>(OrderChannel.class);
        for (OrderChannel channel : OrderChannel.values()) {
            Counter counter = Counter.builder("orders.created")
                    .description("Number of orders successfully created")
                    .baseUnit("orders")
                    .tag("channel", channel.tagValue())
                    .register(registry);
            counters.put(channel, counter);
        }
        this.createdByChannel = Collections.unmodifiableMap(counters);
    }

    public void recordCreated(OrderChannel channel) {
        createdByChannel.get(channel).increment();
    }
}
~~~

Mã ứng dụng chỉ cần gọi recordCreated sau khi đơn hàng được tạo thành công theo định nghĩa nghiệp vụ. Counter đã được đăng ký khi bean được khởi tạo; mỗi lần ghi nhận chỉ tra cứu meter tương ứng và tăng giá trị. Số series do tag channel tạo ra được giới hạn ở ba giá trị enum.

Nếu một thao tác tạo nhiều đơn hàng cùng lúc và mỗi đơn đều được tính là một sự kiện, có thể tăng theo số lượng dương:

~~~java
counter.increment(numberOfOrders);
~~~

Chỉ làm như vậy khi numberOfOrders là số đơn hàng đã thực sự được tạo thành công. Không truyền giá trị âm để giảm Counter. Nếu cần cập nhật một số lượng hiện tại có thể tăng hoặc giảm, hãy dùng Gauge.

## 6. Phân biệt attempts, successes và failures

Một tên Counter phải thể hiện chính xác sự kiện được đếm. Đối với một quy trình có nhiều trạng thái, có thể chọn một trong hai cách thiết kế:

**Cách 1: một metric chung với tag outcome**

~~~java
Counter.builder("payments.processed")
        .description("Number of payment processing outcomes")
        .tag("outcome", "success")
        .register(registry);
~~~

Đăng ký meter cho các giá trị outcome được phép, chẳng hạn success, failure và rejected. Cách này thuận tiện khi cần so sánh kết quả trong cùng một nhóm metric.

**Cách 2: metric riêng cho các sự kiện có ngữ nghĩa khác nhau**

- payments.attempted: mỗi lần gửi yêu cầu thanh toán đến cổng thanh toán.
- payments.completed: mỗi lần hệ thống xác nhận thanh toán hoàn tất.
- payments.failed: mỗi lần một lần xử lý kết thúc với lỗi theo định nghĩa nghiệp vụ.

Không có một cách duy nhất phù hợp cho mọi hệ thống. Hãy chọn cách làm cho truy vấn và dashboard dễ hiểu. Nếu hai metric là các sự kiện khác nhau về thời điểm và ngữ nghĩa, tên riêng có thể rõ hơn. Nếu chúng là các kết quả loại trừ nhau của cùng một thao tác và cần so sánh, tag outcome có thể phù hợp.

Đặc biệt, đừng dùng success/failure để phân loại cả lỗi kỹ thuật, lỗi nghiệp vụ và timeout nếu nhóm vận hành cần phân biệt các loại này. Có thể dùng một tag error_type với danh mục nhỏ đã chuẩn hóa, nhưng chỉ khi chiều đó có câu hỏi phân tích rõ ràng và cardinality được kiểm soát.

## 7. Kiểm tra tên và tag trong Prometheus

Micrometer dùng tên meter độc lập với quy ước đặt tên của từng backend. Khi xuất sang Prometheus, tên thường được chuyển từ dạng phân tách bằng dấu chấm sang dấu gạch dưới và Counter được biểu diễn theo quy ước hậu tố _total. Ví dụ orders.created có thể xuất thành orders_created_total.

Luôn kiểm tra endpoint exposition thực tế của ứng dụng vì cách chuẩn hóa có thể phụ thuộc phiên bản registry và cấu hình.

Ví dụ PromQL:

~~~promql
sum by (channel) (
  rate(orders_created_total[5m])
)
~~~

Truy vấn này tính tốc độ tạo đơn hàng mỗi giây trong cửa sổ năm phút và nhóm theo channel.

Để xem số đơn hàng được tạo trong một giờ:

~~~promql
sum by (channel) (
  increase(orders_created_total[1h])
)
~~~

rate và increase được thiết kế cho counter và xử lý việc counter reset tốt hơn so với tự lấy hiệu hai mẫu. Tránh dùng phép trừ thủ công giữa hai giá trị khi tiến trình có thể khởi động lại.

## 8. Kiểm thử Counter

Có thể dùng SimpleMeterRegistry để kiểm tra ngữ nghĩa Counter mà không cần kết nối Prometheus:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderMetricsTest {

    @Test
    void counterCountsCreatedOrdersForTheSelectedChannel() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter counter = Counter.builder("orders.created")
                .description("Number of orders successfully created")
                .baseUnit("orders")
                .tag("channel", "web")
                .register(registry);

        counter.increment();
        counter.increment(2.0);

        assertThat(registry.get("orders.created")
                .tag("channel", "web")
                .counter()
                .count()).isEqualTo(3.0);
    }
}
~~~

Ngoài việc kiểm tra số đếm, nên kiểm tra:

1. Tên meter và description diễn đạt đúng sự kiện.
2. Tag chỉ nhận giá trị thuộc danh mục được phép.
3. Một sự kiện chỉ làm tăng counter đúng một lần theo điểm ghi nhận đã chọn.
4. Retry được tính đúng theo định nghĩa attempts hoặc completed.
5. Meter không tạo tag mới từ ID, URL hoặc dữ liệu đầu vào tự do.
6. Counter không bị dùng để biểu diễn trạng thái có thể giảm.

Kiểm thử đơn vị xác minh hành vi của mã instrumentation. Kiểm thử tích hợp có thể xác minh registry thực tế xuất đúng tên metric và label mà Prometheus sẽ scrape.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tên metric không mô tả sự kiện | Người đọc không biết số liệu đang đếm gì. | Dùng tên ổn định như orders.created hoặc payments.attempted. |
| Tăng counter trước khi giao dịch thành công | Số liệu cao hơn số sự kiện nghiệp vụ thực tế. | Tăng tại điểm sự kiện được xác nhận theo định nghĩa. |
| Gộp attempt và success vào một Counter | Không phân biệt được retry và kết quả cuối cùng. | Tạo metric riêng hoặc dùng outcome tag với ngữ nghĩa rõ ràng. |
| Đặt đơn vị là per-second | Nhầm đại lượng tích lũy với tốc độ. | Counter lưu tổng; dùng rate() để tính tốc độ. |
| Dùng ID làm tag | Cardinality tăng theo số thực thể. | Dùng nhóm giá trị hữu hạn; tra cứu chi tiết qua log/trace. |
| Đưa channel vào tên metric | Phát sinh nhiều metric name và khó tổng hợp. | Giữ một tên, dùng tag channel. |
| Dùng Counter cho số kết nối đang mở | Giá trị không thể giảm đúng theo trạng thái. | Dùng Gauge hoặc meter phù hợp với trạng thái hiện tại. |
| Tạo meter với tag-value tự do ở mỗi request | Có thể tạo lượng series không kiểm soát. | Chuẩn hóa enum và đăng ký meter cho tập giá trị hợp lệ. |

## 10. Checklist trước khi phát hành Counter

- [ ] Sự kiện hoặc đại lượng được đếm có định nghĩa rõ ràng.
- [ ] Thời điểm tăng Counter khớp với định nghĩa nghiệp vụ.
- [ ] Tên meter mô tả sự kiện, ổn định và không chứa tag-value.
- [ ] Description giải thích điều kiện ghi nhận.
- [ ] Base unit mô tả đúng đại lượng; không ghi tốc độ vào đơn vị của Counter.
- [ ] Tag có câu hỏi phân tích cụ thể và tập giá trị hữu hạn.
- [ ] Không có ID, dữ liệu cá nhân, token hoặc chuỗi tự do trong tag.
- [ ] Cardinality được ước lượng theo số chiều và số target.
- [ ] Dashboard dùng rate hoặc increase khi cần phân tích theo thời gian.
- [ ] Kiểm thử xác nhận Counter tăng đúng số lần và đúng tag.

Một Counter hữu ích khi tên, đơn vị và tag cùng mô tả một hợp đồng đo lường rõ ràng. Tên cho biết sự kiện nào được đếm, đơn vị cho biết đại lượng tích lũy, còn tag cung cấp những chiều phân tích có giới hạn và có chủ đích.
