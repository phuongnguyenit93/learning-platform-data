# Đếm một sự kiện theo kết quả được xác nhận

Business metrics giúp trả lời các câu hỏi về kết quả hoạt động của sản phẩm: có bao nhiêu đơn hàng được xác nhận, bao nhiêu khoản thanh toán được chấp nhận, bao nhiêu đăng ký hoàn tất hoặc bao nhiêu yêu cầu bị từ chối theo quy tắc nghiệp vụ. Để những con số này có ý nghĩa, ứng dụng phải xác định chính xác thời điểm một sự kiện được xem là đã xảy ra.

Một request được gửi đến không đồng nghĩa một kết quả nghiệp vụ đã được tạo. Một lệnh có thể thất bại ở bước kiểm tra, bị rollback, được thử lại hoặc được xử lý lặp do client gửi lại. Nếu tăng Counter quá sớm, dashboard sẽ đếm cả những kết quả chưa được xác nhận. Nếu tăng Counter nhiều lần cho cùng một chuyển đổi trạng thái, số liệu sẽ bị phóng đại.

Bài này dùng sự kiện đơn hàng được xác nhận làm ví dụ. Quy tắc cốt lõi là chỉ ghi nhận sự kiện sau khi kết quả nghiệp vụ đã được xác nhận theo ranh giới mà hệ thống chọn, thường là sau khi transaction commit thành công.

## 1. Xác định sự kiện trước khi tạo Counter

Trước khi viết instrumentation, hãy định nghĩa một sự kiện nghiệp vụ bằng một câu có thể kiểm chứng:

> Một đơn hàng được tính là đã xác nhận khi trạng thái của nó chuyển từ trạng thái chưa xác nhận sang CONFIRMED và thay đổi đó được commit thành công.

Định nghĩa này trả lời bốn câu hỏi:

- **Đối tượng nào?** Một đơn hàng.
- **Sự kiện nào?** Chuyển trạng thái sang CONFIRMED.
- **Điều kiện nào?** Chuyển đổi hợp lệ theo quy tắc nghiệp vụ.
- **Khi nào được tính?** Sau khi transaction lưu chuyển đổi đã commit.

Nếu không thống nhất định nghĩa, các thành phần khác nhau có thể đếm những thứ khác nhau. Ví dụ, API gateway đếm request, service đếm lần thử xử lý, còn hệ thống báo cáo đếm đơn hàng đã commit. Cả ba số đều có thể đúng theo cách định nghĩa riêng, nhưng không thể thay thế cho nhau.

### Phân biệt các loại số đếm

| Số đo | Thời điểm ghi nhận | Câu hỏi được trả lời |
| --- | --- | --- |
| Request received | Khi hệ thống nhận request. | Có bao nhiêu yêu cầu đi vào? |
| Attempted confirmation | Khi bắt đầu xử lý lệnh xác nhận. | Có bao nhiêu lần thử? |
| Confirmed order | Khi chuyển trạng thái được commit. | Có bao nhiêu đơn hàng thực sự được xác nhận? |
| Rejected order | Khi kết quả từ chối nghiệp vụ được xác định và lưu thành công nếu cần lưu lịch sử. | Có bao nhiêu đơn hàng bị từ chối theo quy tắc? |
| Technical failure | Khi thao tác thất bại do lỗi kỹ thuật. | Có bao nhiêu lần xử lý gặp lỗi hệ thống? |

Không gộp lỗi kỹ thuật với kết quả từ chối nghiệp vụ. Ví dụ, thẻ bị từ chối theo kết quả từ cổng thanh toán có thể là một outcome nghiệp vụ; timeout khi gọi cổng thanh toán là lỗi kỹ thuật. Hai trường hợp cần được đếm và cảnh báo riêng.

## 2. Chọn Counter cho sự kiện tích lũy

Counter phù hợp khi cần đếm số lần một sự kiện xảy ra và giá trị chỉ tăng. Mỗi lần sự kiện được xác nhận, gọi increment một lần.

Ví dụ đăng ký Counter:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderBusinessMetrics {

    private final Counter confirmedOrders;

    public OrderBusinessMetrics(MeterRegistry registry) {
        this.confirmedOrders = Counter.builder("orders.events")
                .description("Number of confirmed order business events")
                .tag("outcome", "confirmed")
                .register(registry);
    }

    public void orderConfirmed() {
        confirmedOrders.increment();
    }
}
~~~

Tên meter mô tả nhóm sự kiện, còn tag outcome phân biệt kết quả. Nếu chỉ có một loại outcome, cũng có thể dùng tên cụ thể như orders.confirmed. Hãy chọn quy ước tên nhất quán trong module và giữ nguyên ngữ nghĩa của meter qua các phiên bản.

Counter không nên được dùng để biểu diễn số đơn hàng hiện đang chờ xác nhận. Đó là trạng thái hiện tại, phù hợp với Gauge lấy số lượng từ nguồn dữ liệu hiện hành. Counter biểu diễn số sự kiện đã xảy ra trong vòng đời meter.

## 3. Không tăng Counter khi mới nhận request

Ví dụ sau dễ tạo số liệu sai:

~~~java
public void confirmOrder(UUID orderId) {
    confirmedOrders.increment();
    orderService.confirm(orderId);
}
~~~

Counter tăng trước khi nghiệp vụ hoàn tất. Nếu confirm thất bại, transaction rollback hoặc database không lưu được trạng thái mới, metric vẫn ghi nhận một đơn hàng đã xác nhận dù điều đó chưa xảy ra.

Một biến thể khác là tăng Counter ngay sau khi gọi repository nhưng trước khi transaction commit:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = repository.findById(orderId).orElseThrow();
    order.confirm();
    repository.save(order);
    confirmedOrders.increment();
}
~~~

Phương thức có thể kết thúc bình thường nhưng transaction vẫn rollback ở bước commit do constraint, lỗi flush hoặc lỗi kết nối. Vì vậy, tăng Counter bên trong phương thức transactional chưa chắc có nghĩa dữ liệu đã được commit.

Với metric đếm kết quả đã lưu bền vững, hãy đặt điểm ghi nhận sau commit hoặc dùng một cơ chế sự kiện bền vững gắn với transaction.

## 4. Ghi nhận sau transaction commit với Spring

Spring cung cấp TransactionalEventListener để xử lý sự kiện theo phase của transaction. Có thể phát application event khi domain state thay đổi, sau đó chỉ tăng Counter khi transaction commit thành công.

Định nghĩa sự kiện bất biến:

~~~java
import java.util.UUID;

public record OrderConfirmed(UUID orderId) {
}
~~~

Service thay đổi trạng thái và phát sự kiện trong transaction:

~~~java
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = repository.findById(orderId).orElseThrow();

        boolean changed = order.confirm();
        if (changed) {
            events.publishEvent(new OrderConfirmed(order.getId()));
        }
    }
}
~~~

Trong ví dụ, phương thức confirm của domain entity trả về true chỉ khi trạng thái thực sự chuyển sang CONFIRMED. Nếu đơn hàng đã được xác nhận trước đó, không phát lại sự kiện chuyển trạng thái.

Listener tăng Counter sau commit:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderConfirmedMetricsListener {

    private final Counter confirmedOrders;

    public OrderConfirmedMetricsListener(MeterRegistry registry) {
        this.confirmedOrders = Counter.builder("orders.events")
                .description("Number of confirmed order business events")
                .tag("outcome", "confirmed")
                .register(registry);
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        confirmedOrders.increment();
    }
}
~~~

Với cấu hình mặc định, listener này chỉ được gọi khi có transaction đang hoạt động và transaction hoàn tất commit. Nếu transaction rollback, callback AFTER_COMMIT không chạy nên Counter không tăng. Nếu cần xử lý event được phát bên ngoài transaction, phải quyết định rõ fallback behavior; không bật fallback chỉ để tránh bỏ sót mà chưa xác định ngữ nghĩa.

Đây là cách phù hợp cho telemetry trong tiến trình khi sự kiện được phát trong cùng transaction với thay đổi trạng thái. Nó giảm nguy cơ đếm một kết quả đã rollback, nhưng chưa tạo ra bảo đảm giao nhận sự kiện bền vững qua mọi sự cố tiến trình.

## 5. Bảo đảm một chuyển đổi trạng thái chỉ phát một sự kiện

Ngay cả khi listener chạy sau commit, lệnh nghiệp vụ vẫn có thể được gọi nhiều lần. Ví dụ client timeout sau khi server đã commit rồi gửi lại request. Nếu mỗi lần gọi đều phát OrderConfirmed, Counter có thể tăng nhiều lần cho cùng một đơn hàng.

Domain operation nên thể hiện chuyển đổi trạng thái:

~~~java
public boolean confirm() {
    if (status == OrderStatus.CONFIRMED) {
        return false;
    }

    if (status != OrderStatus.PENDING) {
        throw new IllegalStateException("Order cannot be confirmed");
    }

    status = OrderStatus.CONFIRMED;
    return true;
}
~~~

Chỉ phát event khi phương thức trả về true. Điều này giúp một lệnh gọi lặp trên cùng trạng thái không phát thêm event trong luồng tuần tự.

Tuy nhiên, kiểm tra trạng thái trong bộ nhớ của entity không tự giải quyết mọi race condition. Hai transaction đồng thời có thể cùng đọc PENDING rồi cùng cố xác nhận. Hãy bảo vệ invariant ở tầng dữ liệu bằng optimistic locking, pessimistic locking, điều kiện cập nhật nguyên tử hoặc constraint phù hợp.

Ví dụ với optimistic locking, entity có thể dùng version column. Nếu hai transaction cùng sửa một phiên bản, một transaction commit, transaction còn lại nhận conflict và phải đọc lại trạng thái trước khi quyết định có phát event hay không.

Nếu API hỗ trợ idempotency key, hãy lưu key và kết quả xử lý theo transaction. Request gửi lại với cùng key phải trả kết quả trước đó mà không tạo thêm chuyển đổi trạng thái hoặc event nghiệp vụ.

## 6. Retry và giao nhận event có thể làm đếm trùng

Một event listener hoặc consumer có thể được gọi nhiều lần nếu hệ thống dùng cơ chế retry hoặc message delivery at-least-once. Counter.increment() không biết hai lần gọi có cùng đại diện cho một event hay không.

Các tình huống cần phân biệt:

- Retry trước commit: transaction thất bại thì listener AFTER_COMMIT không chạy.
- Retry request sau khi commit: domain transition phải nhận ra trạng thái đã hoàn tất và không phát event mới.
- Message broker giao lại event: consumer có thể nhận cùng event nhiều lần.
- Consumer xử lý thành công nhưng mất acknowledgment: broker có thể gửi lại.
- Process dừng sau commit nhưng trước khi listener cập nhật Counter: event có thể không được đếm trong registry của tiến trình.

Với event có thể được giao lại, cần cơ chế idempotent consumer. Có thể lưu event ID đã xử lý trong bảng có unique constraint và chỉ thực hiện tác động nghiệp vụ khi event ID được ghi nhận lần đầu. Không đưa event ID vào tag metric; event ID có cardinality gần như không giới hạn.

Một Counter trong bộ nhớ không cung cấp exactly-once counting xuyên qua crash, restart hoặc retry phân tán. Nếu con số phải chính xác để đối soát doanh thu, tính hoa hồng hoặc báo cáo pháp lý, hãy truy vấn dữ liệu giao dịch bền vững hoặc bảng sự kiện đã được khử trùng lặp. Metrics chỉ là tín hiệu vận hành có thể mất hoặc sai lệch nhỏ trong các cửa sổ lỗi.

## 7. Transactional outbox khi cần giao event bền vững

Nếu hệ thống cần chuyển event sang broker sau khi commit, có thể dùng transactional outbox:

1. Trong cùng transaction, cập nhật đơn hàng và ghi một bản ghi outbox với event ID duy nhất.
2. Sau commit, một publisher đọc các bản ghi outbox chưa gửi và phát lên broker.
3. Consumer lưu event ID đã xử lý để khử trùng.
4. Consumer cập nhật business metrics khi event được chấp nhận theo chính sách idempotency.

~~~mermaid
flowchart TD
    A[Confirm order] --> B[Database transaction]
    B --> C[Update order state]
    B --> D[Insert outbox event]
    C --> E[Commit]
    D --> E
    E --> F[Outbox publisher]
    F --> G[Message broker]
    G --> H[Idempotent consumer]
    H --> I[Business processing]
    I --> J[Increment telemetry counter]
~~~

Outbox giúp tránh tình huống database commit thành công nhưng event chưa được ghi ở nơi nào khác. Tuy nhiên, outbox thường giao message ít nhất một lần; consumer vẫn cần idempotency. Việc tăng Counter vẫn không trở thành một giao dịch nguyên tử với database và backend metrics.

Nếu mục tiêu chỉ là dashboard vận hành gần thời gian thực, listener AFTER_COMMIT có thể đủ. Nếu mục tiêu là số liệu kinh doanh chính xác, hãy lấy số đếm từ nguồn bền vững và dùng Counter như một chỉ báo bổ sung.

## 8. Thiết kế outcome và tag có cardinality thấp

Một meter có thể dùng tag outcome để phân biệt các kết quả hữu hạn:

| outcome | Ý nghĩa |
| --- | --- |
| confirmed | Đơn hàng đã được xác nhận và commit. |
| rejected | Đơn hàng bị từ chối theo quy tắc nghiệp vụ. |
| cancelled | Đơn hàng được hủy thành công. |

Không dùng các giá trị như order_id, customer_id, email, idempotency_key hoặc exception_message làm tag. Mỗi giá trị mới có thể tạo một time series riêng; số lượng đơn hàng tăng sẽ làm cardinality tăng không giới hạn.

Nếu cần phân tích theo kênh, dùng danh mục đã chuẩn hóa như web, mobile, partner. Không lấy chuỗi tự do từ request làm tag. Có thể chuẩn hóa input thành một enum hoặc tập giá trị đã cho phép trước khi ghi nhận metric.

Ví dụ tạo Counter theo outcome:

~~~java
Counter confirmed = Counter.builder("orders.events")
        .tag("outcome", "confirmed")
        .register(registry);

Counter rejected = Counter.builder("orders.events")
        .tag("outcome", "rejected")
        .register(registry);
~~~

Hai Counter có cùng tên nhưng khác tag nên là hai meter identity. Nếu số outcome được định nghĩa cố định, cách này giúp dashboard nhóm theo outcome.

Không tạo một Counter mới cho từng đơn hàng. Meter nên được đăng ký một lần và tái sử dụng; mỗi sự kiện chỉ gọi increment trên meter tương ứng.

## 9. Không đếm nhầm lỗi kỹ thuật thành outcome nghiệp vụ

Một thao tác có thể kết thúc theo nhiều cách:

| Kết quả | Ví dụ | Cách ghi nhận |
| --- | --- | --- |
| Confirmed | Đơn hàng chuyển sang CONFIRMED và commit. | Tăng business counter confirmed. |
| Rejected | Quy tắc nghiệp vụ không cho phép xác nhận và kết quả được lưu nếu cần. | Tăng business counter rejected. |
| Validation failure | Thiếu thông tin hoặc dữ liệu không hợp lệ trước khi có chuyển đổi trạng thái. | Có thể ghi counter validation failure riêng nếu đây là câu hỏi vận hành cần theo dõi. |
| Technical failure | Database timeout, network error hoặc dependency unavailable. | Ghi metric lỗi kỹ thuật riêng; không tăng confirmed. |
| Retryable failure | Có thể thử lại sau lỗi tạm thời. | Đếm attempt/failure riêng, không đếm kết quả thành công. |

Nếu chỉ có Counter confirmed, dashboard không cho biết có bao nhiêu lần thử thất bại. Nếu cần theo dõi funnel, có thể có meter riêng cho attempt, confirmed và rejected. Hãy định nghĩa quan hệ giữa các số liệu và tránh suy ra số attempt bằng cách cộng các Counter có ngữ nghĩa khác nhau.

## 10. Đọc business Counter trong Prometheus

Micrometer Prometheus registry thường xuất Counter với hậu tố _total. Ví dụ meter orders.events có tag outcome=confirmed có thể được chuẩn hóa thành orders_events_total.

Tốc độ xác nhận đơn hàng mỗi giây:

~~~promql
rate(orders_events_total{outcome="confirmed"}[5m])
~~~

Số lượng tăng ước lượng trong một giờ:

~~~promql
increase(orders_events_total{outcome="confirmed"}[1h])
~~~

So sánh tốc độ theo outcome:

~~~promql
sum by (outcome) (
  rate(orders_events_total[5m])
)
~~~

Tổng hợp giữa nhiều instance:

~~~promql
sum by (outcome) (
  rate(orders_events_total{job="orders-api"}[5m])
)
~~~

Rate và increase xử lý Counter reset do process restart tốt hơn phép trừ mẫu thủ công. Tuy nhiên, chúng chỉ tính trên các mẫu Prometheus đã thu thập; nếu tiến trình mất sự kiện trước khi increment hoặc scrape bỏ lỡ thay đổi giữa hai lần lấy mẫu, truy vấn không thể khôi phục dữ liệu chưa từng được xuất.

Không dùng giá trị Counter hiện tại trên một pod làm tổng số đơn hàng của toàn hệ thống. Mỗi instance có Counter riêng và Counter có thể reset khi instance khởi động lại.

## 11. Đối chiếu metric với dữ liệu nghiệp vụ

Business Counter là telemetry trong bộ nhớ. Nó có thể bị reset khi restart, mất một lần tăng nếu process dừng ở thời điểm không thuận lợi, hoặc tăng trùng nếu event bị xử lý lại. Vì vậy, dashboard cần được đối chiếu với nguồn dữ liệu nghiệp vụ khi có yêu cầu chính xác.

Các nguồn đối chiếu có thể gồm:

- Bảng orders với trạng thái CONFIRMED và timestamp chuyển trạng thái.
- Bảng audit ghi nhận state transition.
- Bảng outbox chứa event ID duy nhất.
- Báo cáo tổng hợp theo khoảng thời gian từ kho dữ liệu.

Nếu cần so sánh metric với số liệu database, hãy thống nhất múi giờ, cửa sổ thời gian, trạng thái được tính và thời điểm commit. Một truy vấn database theo created_at có thể không tương đương với Counter ghi nhận confirmed_at.

Không cố làm cho Counter trở thành nguồn sự thật bằng cách gán lại giá trị từ database mỗi lần scrape. Counter là loại meter tăng dần; nếu cần hiển thị một số đếm hiện tại lấy từ truy vấn, hãy cân nhắc Gauge hoặc một quy trình tổng hợp riêng với ngữ nghĩa rõ ràng.

## 12. Kiểm thử Counter và ranh giới commit

Kiểm thử đơn vị có thể xác nhận listener tăng Counter đúng khi được gọi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderConfirmedMetricsListenerTest {

    @Test
    void incrementsConfirmedCounterForConfirmedEvent() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderConfirmedMetricsListener listener =
                new OrderConfirmedMetricsListener(registry);

        listener.on(new OrderConfirmed(java.util.UUID.randomUUID()));

        assertThat(registry.get("orders.events")
                .tag("outcome", "confirmed")
                .counter()
                .count()).isEqualTo(1.0);
    }
}
~~~

Kiểm thử trên xác minh hành vi listener khi nhận event; nó không kiểm tra transaction. Cần thêm integration test với Spring transaction để xác nhận:

1. Event được phát trong transaction commit thì listener AFTER_COMMIT chạy và Counter tăng.
2. Event được phát trong transaction rollback thì listener không chạy và Counter không tăng.
3. Lệnh xác nhận lặp lại không tạo thêm event nếu trạng thái đã CONFIRMED.
4. Retry hoặc event delivery lặp không làm tăng business count lần nữa nếu consumer có idempotency.
5. Technical failure không tăng Counter confirmed.

Trong test transaction, dùng TransactionTemplate hoặc cơ chế transaction test của Spring để chủ động commit/rollback. Không chỉ dựa vào một test method có annotation @Transactional vì test framework có thể rollback transaction ở cuối test và khiến listener AFTER_COMMIT không được gọi như kỳ vọng.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tăng Counter khi nhận request | Đếm cả request thất bại hoặc bị rollback. | Chỉ ghi nhận sau khi outcome được xác nhận. |
| Tăng Counter bên trong transaction trước commit | Transaction có thể rollback sau khi Counter đã tăng. | Dùng AFTER_COMMIT hoặc cơ chế bền vững phù hợp. |
| Phát event mỗi lần gọi confirm | Request retry có thể đếm cùng đơn hàng nhiều lần. | Chỉ phát event khi có state transition mới và dùng idempotency. |
| Cho rằng listener AFTER_COMMIT bảo đảm exactly-once | Process có thể dừng sau commit trước khi cập nhật Counter. | Dùng outbox/durable event nếu cần giao nhận bền vững; đối chiếu dữ liệu nguồn. |
| Dùng event ID làm tag | Tạo cardinality gần như không giới hạn. | Dùng ID để deduplicate trong storage, không dùng làm tag metric. |
| Gộp lỗi kỹ thuật và từ chối nghiệp vụ | Dashboard không phân biệt lỗi hệ thống với quyết định nghiệp vụ. | Tách outcome và technical failure. |
| Dùng Counter làm số liệu tài chính chính xác | Reset, mất event hoặc duplicate có thể làm lệch số. | Dùng ledger/database làm nguồn sự thật. |
| Tạo meter trong từng request | Tăng chi phí và có thể tạo nhiều series. | Đăng ký meter một lần, tái sử dụng. |
| Dùng Gauge cho số sự kiện tích lũy | Giá trị có thể giảm và không biểu diễn số lần xảy ra. | Dùng Counter cho event count. |

## 14. Checklist thiết kế business event counter

- [ ] Định nghĩa sự kiện bằng điều kiện nghiệp vụ có thể kiểm chứng.
- [ ] Phân biệt request, attempt, outcome và technical failure.
- [ ] Xác định ranh giới xác nhận, thường là sau transaction commit.
- [ ] Chỉ phát event khi có state transition mới.
- [ ] Có idempotency hoặc concurrency control cho lệnh có thể được gửi lại.
- [ ] Không giả định in-memory Counter bảo đảm exactly-once qua restart.
- [ ] Dùng outbox và idempotent consumer nếu cần giao event bền vững.
- [ ] Không dùng event ID, order ID hoặc customer ID làm tag.
- [ ] Tag outcome/channel có tập giá trị hữu hạn.
- [ ] Đăng ký Counter một lần và chỉ increment khi sự kiện đã được xác nhận.
- [ ] Dùng rate/increase để truy vấn Counter trong Prometheus.
- [ ] Đối chiếu với database hoặc audit/outbox khi cần số liệu chính xác.
- [ ] Kiểm thử cả commit, rollback, retry và duplicate delivery.

Một business Counter đáng tin cậy bắt đầu từ định nghĩa sự kiện rõ ràng. Hãy tăng nó khi kết quả nghiệp vụ đã được xác nhận, giữ tag trong tập giá trị hữu hạn và xử lý retry bằng idempotency ở tầng nghiệp vụ hoặc event consumer. Khi cần số đếm chính xác qua mọi lần restart và sự cố, dùng dữ liệu bền vững làm nguồn sự thật; Micrometer cung cấp góc nhìn vận hành nhanh và hữu ích.
