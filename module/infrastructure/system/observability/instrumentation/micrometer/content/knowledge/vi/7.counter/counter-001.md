# Counter dùng để đếm sự kiện tích lũy như thế nào

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `Counter` là meter dùng để đếm số lần một sự kiện xảy ra. Mỗi lần ghi nhận làm giá trị tăng lên; giá trị không giảm trong vòng đời của counter. Ví dụ, ứng dụng có thể đếm số đơn hàng được tạo, số lần gửi email thành công hoặc số thông điệp được nhận.

Counter trả lời câu hỏi “đã có bao nhiêu sự kiện xảy ra kể từ khi bộ đếm bắt đầu?”. Khi đưa số liệu vào hệ giám sát, ta thường quan tâm thêm tốc độ sự kiện trong một khoảng thời gian. Bài này giải thích cách ghi nhận đúng ranh giới sự kiện, cách đọc số đếm tích lũy, cách tính tốc độ và những giới hạn cần hiểu khi dùng counter trong ứng dụng Java.

## 1. Đặc tính tích lũy của Counter

Một counter chỉ tăng. Nếu giá trị hiện tại là 12 và ứng dụng ghi nhận thêm một sự kiện, giá trị thành 13. Counter không có thao tác giảm hoặc đặt lại về một giá trị tùy ý trong quá trình sử dụng thông thường.

```java
Counter ordersCreated = registry.counter("orders.created");

ordersCreated.increment();
ordersCreated.increment();
ordersCreated.increment(3);

System.out.println(ordersCreated.count()); // 5.0
```

`increment()` tăng một đơn vị. `increment(amount)` tăng theo số lượng dương được truyền vào, hữu ích khi một lần xử lý đại diện cho nhiều sự kiện, chẳng hạn nhận một batch gồm 20 bản ghi hợp lệ. Nếu một request chỉ tạo một đơn hàng, hãy tăng một đơn vị cho đơn hàng đó.

Counter phù hợp với các sự kiện có thể đếm được và không thể “hoàn tác” bằng cách trừ đi giá trị đã ghi. Ví dụ:

- Số đơn hàng được tạo thành công.
- Số lần xác thực thất bại.
- Số message được consumer nhận.
- Số lần gọi một API bên ngoài.
- Số job được đưa vào hàng đợi.

Counter không biểu diễn trạng thái hiện tại. Số request đang chạy, số kết nối đang mở hoặc độ dài queue có thể tăng và giảm; các giá trị này phù hợp với `Gauge`.

## 2. Tạo và đăng ký Counter

Với trường hợp đơn giản, có thể lấy counter trực tiếp từ `MeterRegistry`:

```java
Counter ordersCreated = registry.counter("orders.created");
```

Nếu cần mô tả hoặc tag, dùng builder:

```java
Counter ordersCreated = Counter.builder("orders.created")
    .description("Number of orders successfully created")
    .tag("channel", "web")
    .register(registry);
```

Hai cách đều đăng ký counter trong registry. Khi cùng registry đã có meter cùng tên và tag, lời gọi sau tái sử dụng meter đó. Vì vậy, ứng dụng nên đăng ký counter một lần khi khởi tạo bean và giữ tham chiếu để ghi nhận trong các phương thức nghiệp vụ.

Trong Spring Boot, nhận registry qua constructor injection:

```java
@Component
public class OrderMetrics {
    private final Counter ordersCreated;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("orders.created")
            .description("Number of orders successfully created")
            .register(registry);
    }

    public void orderCreated() {
        ordersCreated.increment();
    }
}
```

Không tạo `SimpleMeterRegistry` hoặc registry mới cho mỗi request. Nếu meter được đăng ký vào một registry riêng, exporter của ứng dụng có thể không đọc được số liệu đó.

## 3. Chọn đúng thời điểm tăng counter

Ý nghĩa của counter phụ thuộc vào thời điểm gọi `increment()`. Trước khi viết instrumentation, hãy xác định chính xác sự kiện cần đếm: request bắt đầu, thao tác được chấp nhận, hay nghiệp vụ đã hoàn tất thành công. Các ranh giới này trả lời những câu hỏi khác nhau và không nên dùng chung một tên metric.

Ví dụ, với nghiệp vụ tạo đơn hàng, có thể phân biệt ba số liệu:

| Sự kiện | Thời điểm tăng | Câu hỏi được trả lời |
| --- | --- | --- |
| `attempted` | Khi bắt đầu xử lý yêu cầu tạo đơn | Có bao nhiêu lần thử? |
| `created` | Sau khi lưu đơn thành công | Có bao nhiêu đơn đã được tạo? |
| `failed` | Khi thao tác thất bại theo định nghĩa của ứng dụng | Có bao nhiêu lần tạo đơn lỗi? |

Ví dụ triển khai:

```java
@Component
public class OrderMetrics {
    private final Counter attempts;
    private final Counter created;
    private final Counter failures;

    public OrderMetrics(MeterRegistry registry) {
        this.attempts = Counter.builder("orders.create")
            .description("Number of order creation attempts")
            .tag("result", "attempted")
            .register(registry);

        this.created = Counter.builder("orders.create")
            .description("Number of order creation attempts")
            .tag("result", "success")
            .register(registry);

        this.failures = Counter.builder("orders.create")
            .description("Number of order creation attempts")
            .tag("result", "failure")
            .register(registry);
    }

    public void attempted() {
        attempts.increment();
    }

    public void succeeded() {
        created.increment();
    }

    public void failed() {
        failures.increment();
    }
}
```

Service gọi các phương thức ở đúng ranh giới:

```java
public Order createOrder(CreateOrderCommand command) {
    metrics.attempted();
    try {
        Order saved = repository.save(Order.from(command));
        metrics.succeeded();
        return saved;
    } catch (RuntimeException exception) {
        metrics.failed();
        throw exception;
    }
}
```

Trong ví dụ này, `attempted` tăng trước thao tác lưu; `success` chỉ tăng sau khi repository trả về thành công; `failure` tăng khi phát sinh `RuntimeException` trong đoạn được bọc. Nếu ứng dụng có các trường hợp từ chối nghiệp vụ, timeout, retry hoặc hủy riêng, hãy quyết định chúng thuộc nhóm nào và dùng tập tag hữu hạn để thể hiện rõ ý nghĩa.

Không nên tăng counter thành công trước khi thao tác thực sự đạt trạng thái thành công. Ngược lại, nếu mục tiêu là đếm số lần thử, hãy tăng ở đầu luồng xử lý, kể cả khi lần thử sau đó thất bại.

Nếu service chạy trong transaction, thời điểm `repository.save()` trả về có thể vẫn nằm trước lúc transaction được commit. Khi metric cần biểu diễn số giao dịch đã commit, hãy ghi nhận sau khi transaction commit thành công, chẳng hạn qua callback after-commit hoặc sự kiện phát ra sau commit. `Counter` không tham gia transaction của database nên không tự rollback khi transaction nghiệp vụ bị hủy.

## 4. Counter và tính đồng thời

Một ứng dụng web thường xử lý nhiều request cùng lúc. Counter của Micrometer được thiết kế để nhận cập nhật từ nhiều luồng; ứng dụng có thể gọi `increment()` từ các request hoặc worker khác nhau mà không cần tự đồng bộ quanh từng lần tăng.

```java
public void messageConsumed() {
    consumedMessages.increment();
}
```

Mỗi lần consumer xử lý một message, gọi phương thức trên một lần tại đúng ranh giới đã chọn. Nếu một batch có 50 message và tất cả đều được nhận thành công, có thể ghi nhận bằng `increment(50)` thay vì gọi 50 lần. Chỉ dùng cách tăng theo batch khi con số đó thực sự là số sự kiện đã xảy ra; không dùng nó để ghi kích thước batch trung bình hoặc giá trị queue hiện tại.

Counter là số liệu quan sát phục vụ vận hành. Nó không thay thế cơ chế lưu trữ giao dịch hoặc bảo đảm xử lý đúng một lần. Nếu tiến trình dừng sau khi database commit nhưng trước khi gọi `increment()`, sự kiện có thể không xuất hiện trong metric. Nếu ứng dụng retry và cùng một nghiệp vụ được ghi nhận ở nhiều lần thử, counter có thể phản ánh số lần xử lý chứ không phải số thực thể duy nhất. Với số liệu kế toán hoặc kiểm kê chính xác, hãy dùng dữ liệu nghiệp vụ bền vững làm nguồn sự thật.

## 5. Đọc giá trị tích lũy và tốc độ sự kiện

`count()` trả về tổng số đã được counter ghi nhận trong registry hiện tại:

```java
double total = ordersCreated.count();
```

Giá trị này hữu ích để kiểm tra trong unit test hoặc debug cục bộ. Khi quan sát một service đang chạy, tổng tích lũy đơn lẻ thường không cho biết tải hiện tại. Một counter có giá trị 100.000 có thể tăng rất chậm hoặc tăng hàng nghìn lần mỗi phút.

Hệ giám sát thường lấy mẫu counter theo chu kỳ rồi tính tốc độ tăng trong một cửa sổ thời gian. Với Prometheus, hàm `rate()` tính tốc độ trung bình mỗi giây:

```promql
rate(orders_create_total{result="success"}[5m])
```

Truy vấn trên giả định Prometheus exporter xuất counter thành metric `orders_create_total` và có label `result`. Tên thực tế có thể được chuẩn hóa theo registry, phiên bản exporter và quy tắc đặt tên; hãy kiểm tra endpoint exposition để dùng đúng tên.

Để tính số sự kiện ước tính xảy ra trong một giờ:

```promql
increase(orders_create_total{result="success"}[1h])
```

`rate()` phù hợp để vẽ thông lượng theo thời gian, còn `increase()` hữu ích khi muốn biết tổng số sự kiện trong cửa sổ. Cả hai hàm đều xử lý việc counter reset theo quy tắc của Prometheus. Khi tổng hợp nhiều instance, hãy áp dụng `rate()` cho từng time series trước rồi mới cộng:

```promql
sum by (result) (
  rate(orders_create_total[5m])
)
```

Cách viết này cho phép Prometheus xử lý reset của từng instance trước khi các tốc độ được cộng lại. Nếu cộng counter thô của nhiều instance trước rồi mới tính rate, một instance khởi động lại có thể làm sai kết quả tổng hợp.

Có thể tính tỷ lệ tạo đơn thành công trên số lần thử khi cả hai loại sự kiện được ghi nhận nhất quán:

```promql
sum(rate(orders_create_total{result="success"}[5m]))
/
sum(rate(orders_create_total{result="attempted"}[5m]))
```

Nếu mẫu số bằng 0 trong cửa sổ quan sát, truy vấn có thể không trả về tỷ lệ hữu ích. Dashboard nên xử lý trường hợp không có request thay vì diễn giải nó thành lỗi hoặc thành công tuyệt đối.

## 6. Counter reset khi tiến trình khởi động lại

Counter trong ứng dụng thường bắt đầu từ 0 khi registry được tạo. Khi JVM hoặc container khởi động lại, giá trị trong bộ nhớ bắt đầu lại từ đầu. Điều đó không có nghĩa tổng số sự kiện lịch sử của hệ thống bị giảm; đó là một lần reset của bộ đếm thuộc tiến trình.

Hệ giám sát cần nhận diện time series theo các nhãn như service, instance hoặc pod. Khi một instance khởi động lại và counter giảm từ giá trị cũ về 0, Prometheus `rate()` và `increase()` có cơ chế điều chỉnh counter reset để ước lượng tốc độ hoặc lượng tăng trong cửa sổ.

Vì vậy:

- Không lưu giá trị `count()` vào biến rồi tự tính hiệu số giữa hai lần đọc nếu chưa xử lý trường hợp reset.
- Không cộng trực tiếp các giá trị tích lũy của những instance có vòng đời khác nhau để suy ra thông lượng tức thời.
- Giữ nhãn nhận diện instance ổn định và có ý nghĩa trong cấu hình scrape.
- Dùng `rate()` hoặc `increase()` cho counter trong Prometheus thay vì tự trừ hai snapshot ở tầng ứng dụng.

Counter mô tả số sự kiện kể từ khi tiến trình/registry bắt đầu ghi nhận. Hệ thống time series mới cung cấp lịch sử qua nhiều lần scrape và nhiều vòng đời instance.

## 7. Tag và cardinality khi đếm sự kiện

Tag cho phép chia counter thành các nhóm để trả lời câu hỏi như số đơn theo kênh hoặc số lỗi theo loại thao tác. Ví dụ:

```java
Counter webOrders = registry.counter(
    "orders.created", "channel", "web");
Counter mobileOrders = registry.counter(
    "orders.created", "channel", "mobile");
```

Hai counter có cùng tên nhưng khác tag value nên được theo dõi riêng. Đây là cách phù hợp nếu số kênh là một tập nhỏ, được định nghĩa trước.

Các tag thường có cardinality thấp:

- `channel`: `web`, `mobile`, `partner`.
- `result`: `success`, `failure`, `rejected`.
- `operation`: một tập tên thao tác cố định.
- `region`: một tập vùng triển khai đã xác định.

Không đưa `orderId`, `userId`, email, số điện thoại, request ID, trace ID hoặc nội dung exception vào tag. Mỗi giá trị mới có thể tạo một time series riêng. Với metric đếm sự kiện có lưu lượng cao, cardinality tăng nhanh làm Prometheus và các backend khác tốn bộ nhớ, dung lượng và chi phí truy vấn.

Nếu cần xem số liệu theo từng khách hàng hoặc từng đơn hàng, hãy dùng log, trace hoặc kho dữ liệu nghiệp vụ. Metrics nên trả lời câu hỏi tổng hợp ở cấp service, endpoint, loại thao tác hoặc nhóm kết quả.

## 8. Phân biệt Counter, Gauge và Timer

Ba meter này có thể cùng xuất hiện quanh một nghiệp vụ nhưng biểu diễn những điều khác nhau:

| Meter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Counter` | Tổng số sự kiện tích lũy | Số đơn đã tạo |
| `Gauge` | Giá trị hiện tại có thể tăng hoặc giảm | Số đơn đang chờ trong queue |
| `Timer` | Số lần thao tác và phân phối thời lượng | Số lần tạo đơn cùng thời gian xử lý |

Nếu muốn biết có bao nhiêu đơn đã được tạo kể từ khi ứng dụng chạy, dùng counter. Nếu muốn biết hiện có bao nhiêu đơn đang chờ, dùng gauge. Nếu muốn biết thao tác tạo đơn mất bao lâu và có bao nhiêu lần hoàn tất, dùng timer.

Không tạo counter rồi giảm nó khi một đơn rời khỏi queue để biểu diễn queue depth. Cách đó làm mất ý nghĩa tích lũy của counter và có thể không tương thích với backend. Hãy dùng gauge cho trạng thái hiện tại và counter riêng cho số lần enqueue/dequeue nếu cần đếm sự kiện.

Tương tự, timer đã có số lần ghi nhận trong `count`. Nếu mục tiêu chỉ là đếm số lần thao tác được đo thời gian, hãy dùng trường count của timer thay vì tạo counter trùng lặp. Chỉ tạo counter riêng nếu nó mô tả một sự kiện hoặc ranh giới khác.

## 9. Kiểm thử Counter

`SimpleMeterRegistry` cho phép kiểm tra counter mà không cần kết nối backend. Test nên xác minh số lần tăng, mức tăng theo batch và việc các lần đăng ký cùng định danh dùng chung số liệu:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

class OrderCounterTest {
    @Test
    void accumulatesEventCounts() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Counter first = registry.counter("orders.created", "channel", "web");
        Counter second = registry.counter("orders.created", "channel", "web");

        assertSame(first, second);

        first.increment();
        second.increment(4);

        assertEquals(5.0, first.count());
    }
}
```

Test xác nhận hành vi tích lũy trong một registry. Nó không kiểm tra scrape, lưu trữ lịch sử hoặc xử lý reset của Prometheus. Những phần đó cần được kiểm tra ở mức tích hợp với registry/exporter và cấu hình scrape thực tế.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Counter tăng gấp đôi | Cùng sự kiện được ghi ở nhiều lớp, retry được tính như nhiều lần thử hoặc consumer xử lý lặp |
| Counter thành công tăng dù giao dịch lỗi | Gọi `increment()` trước khi xác định thao tác đã thành công |
| Giá trị counter giảm sau deploy | JVM/container khởi động lại và counter trong bộ nhớ bắt đầu lại |
| Dashboard hiển thị tổng tích lũy thay vì tốc độ | Đang truy vấn raw counter thay vì `rate()` hoặc `increase()` |
| Tổng nhiều instance bất thường | Cộng counter thô trước khi xử lý reset; cần tính rate theo từng series rồi mới tổng hợp |
| Số time series tăng liên tục | Tag chứa ID hoặc giá trị không giới hạn |
| Counter được cập nhật nhưng exporter không thấy | Meter được đăng ký vào registry khác hoặc bị `MeterFilter` từ chối |

Khi điều tra counter tăng sai, hãy kiểm tra định nghĩa sự kiện trước, sau đó lần theo mọi vị trí gọi `increment()`, xác định retry và hành vi xử lý lặp, rồi đối chiếu label giữa các instance. Một counter chỉ hữu ích khi mọi nơi ghi nhận cùng tuân theo một định nghĩa sự kiện.

## 11. Nguyên tắc áp dụng

Hãy dùng `Counter` cho sự kiện tích lũy, xác định rõ ranh giới ghi nhận và chỉ tăng khi sự kiện theo định nghĩa đã xảy ra. Đăng ký meter một lần trong registry dùng chung, chọn tag có tập giá trị hữu hạn và giữ tên metric phản ánh đúng ý nghĩa nghiệp vụ. Với Prometheus, đọc tốc độ bằng `rate()` và lượng tăng trong cửa sổ bằng `increase()`, đồng thời tính theo từng time series trước khi tổng hợp nhiều instance.

Counter là tín hiệu vận hành giúp quan sát thông lượng và xu hướng. Dữ liệu giao dịch bền vững vẫn là nguồn sự thật cho kiểm kê hoặc đối soát; metrics cung cấp góc nhìn tổng hợp nhanh để phát hiện thay đổi và sự cố trong hệ thống.
