# Theo dõi hiệu năng và đánh giá ranh giới bằng một thay đổi nghiệp vụ mới

Trong chương **Thực hành hệ thống đơn hàng**, bài học này dùng một yêu cầu mới để kiểm tra đồng thời hai điều: hệ thống có đáp ứng hiệu năng sau khi thay đổi hay không, và các trách nhiệm có còn nằm đúng ranh giới kiến trúc hay không. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng, hiểu cách tầng trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu phối hợp trong một luồng có thể đo lường và kiểm thử.

Tình huống xuyên suốt là bổ sung **mã ưu đãi cho đơn hàng**. Client gửi mã ưu đãi khi đặt hàng; hệ thống phải xác định mã có áp dụng được cho khách hàng và các mặt hàng hay không, tính giảm giá, lưu đơn và phát sự kiện để các thành phần khác xử lý. Thay đổi này chạm đến API, ca sử dụng, quy tắc nghiệp vụ, dữ liệu và tích hợp. Nó cũng có thể làm tăng số truy vấn, thời gian xử lý và tải database.

Không thể đánh giá thay đổi chỉ bằng việc code chạy thành công. Cần đo trước và sau, quan sát từng bước trong luồng, xác định nơi quy tắc được thực thi, kiểm tra transaction và tính nhất quán, rồi quyết định có cần điều chỉnh ranh giới hay không. Mục tiêu là đưa ra kết luận dựa trên bằng chứng, thay vì bỏ tầng hoặc thêm lớp chỉ vì cảm giác.

Sau bài học, bạn có thể:

- Lập baseline và theo dõi hiệu năng của một ca sử dụng trước/sau thay đổi nghiệp vụ.
- Dùng metric, trace và log để tìm phần thời gian tăng thêm.
- Phân chia thay đổi mã ưu đãi theo trách nhiệm của từng tầng.
- Xác định transaction boundary, consistency và cách phát sự kiện an toàn.
- Đánh giá tác động của truy vấn, cache, khóa và lời gọi dịch vụ ngoài.
- Triển khai thay đổi theo giai đoạn và dùng kiểm thử kiến trúc để bảo vệ ranh giới.

## 1. Bắt đầu từ yêu cầu nghiệp vụ có thể kiểm chứng

Yêu cầu mới cần được mô tả bằng hành vi quan sát được, không chỉ bằng một trường mới trong request.

**Yêu cầu:** khách hàng có thể nhập mã ưu đãi khi đặt hàng. Mã chỉ được áp dụng khi còn hiệu lực, thuộc phạm vi sản phẩm/khách hàng được phép và đơn đạt điều kiện tối thiểu. Hệ thống phải tính tổng tiền sau giảm giá, ghi nhận mã đã dùng theo chính sách, lưu đơn và phát sự kiện `OrderPlaced` chứa kết quả cuối cùng.

Một số quy tắc cần được làm rõ trước khi thiết kế:

- Mã ưu đãi có thể áp dụng cho tất cả sản phẩm hay chỉ một tập sản phẩm?
- Có giới hạn số lần sử dụng tổng thể hoặc theo khách hàng không?
- Điều kiện giá trị đơn tối thiểu được tính trước hay sau thuế/phí vận chuyển?
- Mã hết hạn hoặc không hợp lệ làm request thất bại hay được bỏ qua?
- Một mã có được dùng lại khi client gửi lại cùng yêu cầu do timeout không?
- Khi hai request đồng thời dùng lượt ưu đãi cuối cùng, hệ thống bảo đảm điều gì?

Các câu hỏi này quyết định invariant, dữ liệu cần đọc/ghi và chiến lược đồng thời. Nếu chưa định nghĩa chúng, nhóm có thể tối ưu một luồng nhưng vô tình làm sai nghiệp vụ.

## 2. Xác định đường đi qua các tầng

Với một ứng dụng phân tầng, luồng đặt hàng có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    H[HTTP Controller] -->|Request DTO -> Command| A[Application: PlaceOrder]
    A --> C[Domain: Order và PromotionPolicy]
    A --> P[Data access ports]
    P --> R[Repository adapters]
    R --> DB[(Order database)]
    A -->|Lưu Outbox cùng transaction| DB
    DB --> O[Outbox Publisher]
    O --> B[Message Broker]
    B --> N[Notification / Analytics consumers]
~~~

Mỗi tầng có một vai trò:

| Tầng | Trách nhiệm trong thay đổi mã ưu đãi | Không nên sở hữu |
|---|---|---|
| Trình bày | Nhận `promotionCode`, kiểm tra định dạng, lấy danh tính đã xác thực, chuyển request thành command và ánh xạ response | Tự tính giảm giá hoặc truy vấn bảng promotion. |
| Ứng dụng | Điều phối đặt hàng, tải dữ liệu cần thiết, xác định transaction, gọi domain policy, lưu đơn và outbox | SQL cụ thể, quy tắc giao thức HTTP hoặc tự triển khai thuật toán giảm giá. |
| Nghiệp vụ | Kiểm tra điều kiện áp dụng, tính mức giảm và bảo vệ invariant của đơn hàng/ưu đãi | `HttpServletRequest`, JPA repository hoặc gửi message trực tiếp. |
| Truy cập dữ liệu | Đọc quy tắc ưu đãi, lưu đơn, ghi nhận lượt dùng và outbox qua adapter | Quyết định một request HTTP nên trả status nào hoặc tự điều phối toàn bộ ca sử dụng. |

Một thay đổi nghiệp vụ có thể chạm đến nhiều tầng mà vẫn có ranh giới tốt. Điều cần đánh giá là mỗi thay đổi có nằm trong đúng trách nhiệm không, các hợp đồng có rõ ràng không và có thành phần nào phải biết chi tiết nội bộ của tầng khác không.

## 3. Đặt baseline trước khi thêm tính năng

Trước khi sửa code, chọn một kịch bản đặt hàng đại diện và ghi nhận trạng thái hiện tại. Baseline phải dùng dữ liệu, tải và môi trường đủ gần với cách hệ thống vận hành.

Các chỉ số nên theo dõi:

| Nhóm | Chỉ số | Câu hỏi cần trả lời |
|---|---|---|
| Trải nghiệm | Latency p50, p95, p99 | Request thông thường và request chậm có thay đổi không? |
| Năng lực | Throughput, request đồng thời | Hệ thống xử lý được bao nhiêu đơn trong một đơn vị thời gian? |
| Độ tin cậy | Tỷ lệ lỗi, timeout, retry | Tính năng mới có làm tăng lỗi hoặc retry không? |
| Database | Số query, query duration, lock wait, connection pool | Có thêm truy vấn, tranh chấp khóa hoặc chờ connection không? |
| JVM | CPU, allocation, heap, GC pause, thread contention | Chi phí tính toán hoặc tạo object có tăng đáng kể không? |
| Message | Outbox backlog, publish delay, consumer lag | Sự kiện có được phát và xử lý đúng nhịp không? |

Ví dụ baseline minh họa cho endpoint `POST /orders`:

| Chỉ số | Trước thay đổi | Mục tiêu tham khảo |
|---|---:|---:|
| Throughput | 100 request/giây | Duy trì ít nhất 100 request/giây ở tải mục tiêu |
| Latency p50 | 95 ms | Không tăng đáng kể |
| Latency p95 | 210 ms | Dưới 280 ms |
| Latency p99 | 480 ms | Dưới 600 ms |
| Query trung bình/request | 5 | Không vượt quá mức cần thiết của tính năng |
| Tỷ lệ lỗi | 0,2% | Không tăng |

Đây là số liệu giả định để minh họa cách đặt baseline, không phải chuẩn chung. Mục tiêu thực tế phải lấy từ SLO, tải dự kiến và trải nghiệm người dùng của hệ thống.

Đo cùng một kịch bản trước và sau thay đổi: số dòng hàng, khách hàng, dữ liệu ưu đãi, cache state và mức đồng thời tương đương. Chỉ nhìn thời gian chạy một request trên máy phát triển không đủ để kết luận về hiệu năng production.

## 4. Instrumentation để biết thời gian nằm ở đâu

### Metric ở cấp endpoint và ca sử dụng

Theo dõi latency, throughput và lỗi của `POST /orders`, sau đó phân tách theo kết quả như thành công, mã ưu đãi không hợp lệ hoặc xung đột sử dụng mã. Dùng metric tag có số lượng giá trị hữu hạn, chẳng hạn `outcome=success|invalid_promotion|conflict`.

Không dùng `orderId`, `customerId`, email hoặc mã ưu đãi tự do làm metric label. Các giá trị có vô số khả năng sẽ tạo cardinality cao, làm tăng bộ nhớ và chi phí của hệ thống metrics. Nếu cần tra cứu một request cụ thể, dùng trace ID hoặc log có kiểm soát.

### Trace theo từng bước

Một trace có thể chia thời gian thành các span:

~~~mermaid
flowchart LR
    A[HTTP mapping<br/>4 ms] --> B[PlaceOrder use case<br/>12 ms]
    B --> C[Load customer/products<br/>18 ms]
    C --> D[Load promotion<br/>35 ms]
    D --> E[Persist order + outbox<br/>42 ms]
    E --> F[Commit transaction<br/>16 ms]
~~~

Các thời gian trong sơ đồ chỉ là ví dụ và không nhất thiết cộng chính xác thành latency endpoint vì còn overhead, span lồng nhau và thời gian chờ khác. Trace thực tế giúp biết thời gian tăng nằm ở truy vấn ưu đãi, tính toán, ghi dữ liệu hay chờ commit.

Trong Spring Boot, Micrometer Observation và tracing instrumentation có thể tạo metric/span cho HTTP server, client và các thành phần được instrument. Có thể bổ sung span cho các bước quan trọng như `promotion.lookup` hoặc `order.persist`. Đặt tên span theo thao tác ổn định, tránh đưa mã đơn hoặc mã khách hàng vào tên span.

### Log có ngữ cảnh

Log nên có trace/correlation ID, tên ca sử dụng, outcome và mã lỗi đã chuẩn hóa. Ví dụ:

~~~text
event=place_order outcome=success traceId=... durationMs=127
promotionApplied=true itemCount=3 transactionOutcome=committed
~~~

Đây là ví dụ cấu trúc, không phải định dạng bắt buộc. Không ghi token, thông tin thanh toán hoặc toàn bộ dữ liệu khách hàng. Không log cùng một exception ở mọi tầng; hãy ghi nhận ở nơi quyết định xử lý hoặc nơi có đủ ngữ cảnh, giữ cause chain để điều tra.

## 5. Thiết kế hợp đồng đầu vào và ca sử dụng

Tầng trình bày nhận dữ liệu theo giao thức, còn tầng ứng dụng nhận command theo ngôn ngữ ca sử dụng.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderRequest(
        @NotEmpty List<@Valid OrderLineRequest> lines,
        String promotionCode
) {
    public record OrderLineRequest(
            @NotBlank String productId,
            @Positive int quantity
    ) {}
}
~~~

Controller lấy `customerId` từ principal đã xác thực, không tin một trường định danh tùy ý trong body:

~~~java
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
class OrderController {
    private final PlaceOrder placeOrder;

    OrderController(PlaceOrder placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping("/orders")
    OrderResponse create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal,
            @RequestHeader(value = "Idempotency-Key", required = false)
                    String idempotencyKey) {

        var command = OrderCommandMapper.toCommand(
                request, principal.customerId(), idempotencyKey);
        var receipt = placeOrder.execute(command);
        return new OrderResponse(receipt.orderId(), receipt.total());
    }
}
~~~

`AppPrincipal`, mapper và response là kiểu do ứng dụng định nghĩa. Controller không tính giảm giá hoặc truy vấn repository. Nó chuyển giao thức thành command, gọi hợp đồng ca sử dụng và chuyển kết quả thành response.

Ví dụ response rút gọn:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderResponse(UUID orderId, BigDecimal total) {}
~~~

Command có thể gồm `customerId`, các dòng hàng, mã ưu đãi và idempotency key. Không đưa `HttpServletRequest`, `HttpHeaders` hoặc `ResponseEntity` vào command. Nếu nhiều adapter cùng gọi ca sử dụng, chúng có thể tạo command từ HTTP, CLI, batch hoặc message mà không phải mô phỏng một request HTTP.

Một hợp đồng ứng dụng rút gọn có thể được khai báo như sau:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record CustomerId(UUID value) {}
public record OrderLineInput(String productId, int quantity) {}

public record PlaceOrderCommand(
        CustomerId customerId,
        List<OrderLineInput> lines,
        String promotionCode,
        String idempotencyKey
) {}

public record OrderReceipt(UUID orderId, BigDecimal total) {}

public interface PlaceOrder {
    OrderReceipt execute(PlaceOrderCommand command);
}
~~~

## 6. Đặt quy tắc ưu đãi ở đúng nơi

Quy tắc như “mã còn hiệu lực”, “đơn đạt giá trị tối thiểu” hoặc “mỗi khách hàng chỉ dùng một lần” là quyết định nghiệp vụ. Tầng ứng dụng lấy dữ liệu cần thiết và điều phối; domain policy đánh giá điều kiện và tính kết quả.

Ví dụ một policy thuần:

~~~java
import java.time.Instant;

public final class PromotionPolicy {
    public Discount evaluate(
            Promotion promotion,
            CustomerId customerId,
            Money eligibleSubtotal,
            Instant now) {

        if (!promotion.isActiveAt(now)) {
            throw new PromotionNotActiveException();
        }
        if (!promotion.allows(customerId)) {
            throw new PromotionNotAllowedException();
        }
        if (eligibleSubtotal.isLessThan(promotion.minimumSpend())) {
            throw new PromotionMinimumNotReachedException();
        }

        return promotion.calculateDiscount(eligibleSubtotal);
    }
}
~~~

Các kiểu `Promotion`, `Money`, `CustomerId` và exception được rút gọn để làm rõ vị trí quy tắc. Policy không tự mở kết nối, đọc HTTP request hoặc gọi message broker. Nếu chính sách cần dữ liệu ngoài, tầng ứng dụng hoặc một domain service phù hợp nhận dữ liệu qua hợp đồng rồi truyền vào policy.

Không phải mọi phép kiểm tra đều phải nằm trong domain. Định dạng mã ưu đãi có ký tự hợp lệ có thể được kiểm tra ở tầng trình bày; việc mã đó có tồn tại, còn hiệu lực và phù hợp với đơn hàng là quyết định của ứng dụng/nghiệp vụ. Tách hai loại kiểm tra tránh controller tự quyết định quyền được giảm giá.

## 7. Transaction boundary và tính nhất quán khi đặt đơn

Giả sử đơn hàng, lượt sử dụng ưu đãi và outbox đều nằm trong cùng một cơ sở dữ liệu quan hệ và dùng cùng transaction manager. Một ranh giới transaction ở ca sử dụng có thể bảo đảm các thay đổi cục bộ cùng commit hoặc cùng rollback:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;

@Service
class PlaceOrderService implements PlaceOrder {
    private final CustomerRepository customers;
    private final ProductRepository products;
    private final PromotionRepository promotions;
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final PromotionPolicy promotionPolicy;
    private final Clock clock;

    PlaceOrderService(
            CustomerRepository customers,
            ProductRepository products,
            PromotionRepository promotions,
            OrderRepository orders,
            OutboxRepository outbox,
            PromotionPolicy promotionPolicy,
            Clock clock) {
        this.customers = customers;
        this.products = products;
        this.promotions = promotions;
        this.orders = orders;
        this.outbox = outbox;
        this.promotionPolicy = promotionPolicy;
        this.clock = clock;
    }

    @Override
    @Transactional
    public OrderReceipt execute(PlaceOrderCommand command) {
        var customer = customers.getById(command.customerId());
        var lines = products.loadOrderLines(command.lines());
        var order = Order.create(customer.id(), lines);

        if (command.promotionCode() != null) {
            var promotion = promotions.getByCode(command.promotionCode());
            var discount = promotionPolicy.evaluate(
                    promotion, customer.id(), order.eligibleSubtotal(),
                    clock.instant());
            order.apply(discount);
            promotions.reserveUse(promotion.id(), customer.id());
        }

        orders.save(order);
        outbox.append(OrderPlaced.from(order));
        return new OrderReceipt(order.id(), order.total());
    }
}
~~~

Đây là ví dụ minh họa; cần bổ sung kiểm tra tồn kho, idempotency, giới hạn ưu đãi và xử lý cạnh tranh theo chính sách của hệ thống. `reserveUse` phải là thao tác nguyên tử ở adapter, chẳng hạn cập nhật có điều kiện `remaining_uses > 0` và kiểm tra số dòng bị ảnh hưởng, hoặc dùng constraint/locking tương ứng. Các repository phải tham gia cùng transaction manager và cùng transaction resource thì các thay đổi mới có thể commit/rollback nguyên tử. Nếu `PromotionRepository` hoặc `OutboxRepository` dùng một database khác, `@Transactional` cục bộ không tự bảo đảm tính nguyên tử giữa hai nơi.

Với giới hạn theo khách hàng, có thể ghi một bản ghi sử dụng có unique constraint trên cặp `(promotion_id, customer_id)`. Với mã có thời hạn/trạng thái, thao tác reserve nên kiểm tra các điều kiện đó ngay trong câu cập nhật nguyên tử hoặc khóa/kiểm tra version phù hợp; chỉ đọc trạng thái trước đó rồi giả định nó không đổi là chưa đủ khi có cập nhật đồng thời.

Với cùng một database, nếu ghi đơn thành công nhưng ghi lượt sử dụng ưu đãi thất bại, transaction rollback sẽ hủy cả hai thay đổi. Nếu mọi thao tác thành công, đơn, lượt dùng và bản ghi outbox cùng commit. Cần có constraint hoặc cơ chế khóa/optimistic locking để hai request đồng thời không vượt quá giới hạn sử dụng. Chỉ đọc số lượt hiện tại rồi ghi tăng trong hai request song song là chưa đủ để bảo đảm giới hạn.

Trong Spring, `@Transactional` mặc định rollback khi phương thức kết thúc bằng `RuntimeException` hoặc `Error`; checked exception không tự động rollback nếu chưa cấu hình `rollbackFor` hoặc quy tắc tương ứng. Exception cần làm rollback phải được truyền ra khỏi ranh giới transaction hoặc transaction phải được đánh dấu rollback-only. Cấu hình proxy thông thường cũng có nghĩa lời gọi nội bộ từ một method sang method khác trong cùng instance không đi qua transaction proxy; đặt ranh giới ở method public được gọi từ bean khác giúp tránh hiểu nhầm này.

### Tránh giữ transaction mở khi gọi mạng

Không nên gọi dịch vụ ưu đãi bên ngoài trong khi đang giữ transaction database mở. Thời gian chờ mạng có thể kéo dài, giữ connection và khóa lâu, làm tăng contention. Nếu cần lấy báo giá từ dịch vụ ngoài, có thể thực hiện bước lấy quote trước transaction, sau đó truyền quote có phiên bản/thời hạn vào ca sử dụng. Trong transaction, xác minh quote còn hợp lệ và lưu snapshot điều kiện/giá đã chấp nhận.

Nếu hệ thống phải giữ chỗ ưu đãi ở dịch vụ ngoài và cập nhật đơn ở database, đây là quy trình phân tán. Một transaction JDBC thông thường không thể rollback tác dụng phụ đã xảy ra ở dịch vụ ngoài. Cần thiết kế workflow/Saga với thao tác bù, timeout, idempotency và trạng thái trung gian rõ ràng.

## 8. Phát sự kiện nhất quán bằng transactional outbox

Sau khi đơn được commit, các consumer có thể cần gửi email, cập nhật phân tích hoặc tạo notification. Gửi message trực tiếp trước khi transaction commit có thể tạo sự kiện cho đơn bị rollback. Gửi sau commit bằng một callback trong bộ nhớ vẫn có cửa sổ mất sự kiện nếu tiến trình dừng ngay sau commit.

Transactional outbox giải quyết khoảng trống này bằng cách ghi bản ghi sự kiện trong cùng transaction với đơn:

~~~mermaid
sequenceDiagram
    participant UseCase as PlaceOrder
    participant DB as Database
    participant Publisher as Outbox Publisher
    participant Broker as Message Broker
    participant Consumer
    UseCase->>DB: INSERT order
    UseCase->>DB: INSERT promotion usage
    UseCase->>DB: INSERT outbox event
    DB-->>UseCase: COMMIT cả ba thay đổi
    Publisher->>DB: Đọc outbox chưa publish
    Publisher->>Broker: Publish OrderPlaced
    Broker-->>Publisher: Acknowledge
    Publisher->>DB: Đánh dấu đã publish
    Broker->>Consumer: Deliver event
~~~

Outbox bảo đảm dữ liệu đơn và ý định phát sự kiện được lưu cùng nhau trong một transaction cục bộ. Publisher có thể chạy bất đồng bộ và thử lại khi broker tạm thời không sẵn sàng.

Outbox thường cung cấp ngữ nghĩa giao ít nhất một lần (at-least-once), không tự bảo đảm exactly-once ở mọi thành phần. Nếu publisher gửi thành công nhưng dừng trước khi đánh dấu bản ghi đã publish, nó có thể gửi lại. Consumer cần idempotent, ví dụ lưu event ID đã xử lý với constraint duy nhất hoặc cập nhật trạng thái theo phiên bản để một event lặp không tạo tác dụng phụ hai lần.

Không nên đánh dấu outbox đã publish trước khi broker xác nhận nhận message. Cũng cần có chính sách retry, dead-letter/đánh dấu lỗi, dọn bản ghi cũ và theo dõi tuổi của bản ghi chưa publish. Outbox giúp bảo đảm ý định phát sự kiện không bị mất cùng transaction; nó không tự bảo đảm thứ tự toàn cục giữa mọi event hoặc thứ tự xử lý ở tất cả consumer.

## 9. Đo tác động của thay đổi sau khi triển khai

Sau khi thêm mã ưu đãi, đo lại đúng kịch bản baseline và thêm các kịch bản riêng:

- Đặt hàng không có mã ưu đãi.
- Đặt hàng với mã hợp lệ.
- Mã hết hạn hoặc không đủ điều kiện.
- Nhiều dòng hàng và nhiều sản phẩm thuộc phạm vi ưu đãi khác nhau.
- Hai request đồng thời sử dụng lượt cuối cùng.
- Database chậm hoặc publisher/broker tạm thời không sẵn sàng.

Ví dụ bảng so sánh minh họa:

| Chỉ số | Trước | Sau | Diễn giải |
|---|---:|---:|---|
| p95 `POST /orders` | 210 ms | 248 ms | Tăng 38 ms; cần so với SLO và mức tăng kỳ vọng. |
| p99 `POST /orders` | 480 ms | 530 ms | Tail latency tăng; kiểm tra request có lookup ưu đãi chậm. |
| Query trung bình | 5 | 7 | Hai query mới có thể đến từ lookup và ghi lượt dùng. |
| Tỷ lệ lỗi | 0,2% | 0,22% | Phân loại lỗi mới, không chỉ nhìn tổng tỷ lệ. |
| Outbox publish delay p95 | Chưa áp dụng | 1,2 giây | Theo dõi riêng vì publish bất đồng bộ sau commit. |

Số liệu chỉ là ví dụ. Nếu p95 tăng nhưng vẫn trong SLO, tỷ lệ lỗi không tăng và độ chính xác nghiệp vụ được bảo đảm, thay đổi có thể chấp nhận. Nếu p99 tăng do lock contention khi nhiều request dùng cùng mã, cần kiểm tra chiến lược cập nhật lượt dùng thay vì bỏ qua tầng ứng dụng.

### Phân tích theo span

Nếu trace cho thấy thời gian tăng nằm ở `promotion.lookup`, kiểm tra index theo code/trạng thái/thời hạn, cache phù hợp hoặc cách lấy dữ liệu theo batch. Nếu thời gian nằm ở `promotion.recordUse`, kiểm tra constraint, lock wait và cách cập nhật bộ đếm. Nếu thời gian nằm ở commit, kiểm tra transaction có quá nhiều thao tác hoặc giữ khóa lâu không.

Nếu thời gian tăng chủ yếu do gọi dịch vụ ngoài, cân nhắc timeout, bulkhead, cache có chính sách rõ hoặc workflow bất đồng bộ. Không giải quyết bằng cách bỏ kiểm tra ưu đãi hoặc trả kết quả chưa được xác minh nếu hợp đồng yêu cầu quyết định đồng bộ.

## 10. Đánh giá ranh giới qua nơi mã thay đổi

Một thay đổi tốt có thể cần sửa nhiều tầng. Hãy đánh giá xem mỗi thay đổi có đúng trách nhiệm và hợp đồng không.

| Thành phần thay đổi | Hợp lý khi… | Dấu hiệu cần xem lại |
|---|---|---|
| Request DTO/controller | Nhận `promotionCode`, xác thực format và chuyển command | Controller tự tính discount hoặc đọc bảng promotion. |
| Application use case | Điều phối đọc dữ liệu, gọi policy, transaction và lưu outbox | Service tự viết SQL, xử lý HTTP status hoặc chứa toàn bộ quy tắc tính giảm giá. |
| Domain policy/model | Bảo vệ điều kiện ưu đãi, cách tính giảm và invariant | Domain gọi repository, đọc request context hoặc gửi message. |
| Repository adapter | Truy vấn promotion, ghi lượt dùng và lưu order | Repository tự quyết định toàn bộ ca sử dụng hoặc gửi email. |
| Outbox publisher | Chuyển event đã commit sang broker, retry và cập nhật trạng thái | Use case gửi message trực tiếp trong transaction mà không có bảo đảm phù hợp. |

Đừng đánh giá kiến trúc bằng số file thay đổi. Một thay đổi nghiệp vụ xuyên tầng là bình thường. Câu hỏi quan trọng là liệu một thay đổi về quy tắc ưu đãi có buộc controller biết SQL, hay một thay đổi về HTTP DTO có buộc domain model đổi theo không.

### Dấu hiệu ranh giới bị trộn

- Controller truy cập `PromotionRepository` và tự quyết định mã có hợp lệ không.
- Domain policy nhận `HttpServletRequest` để lấy customer ID.
- Repository vừa truy vấn, vừa gửi message hoặc quyết định response code.
- Nhiều adapter (HTTP, batch, scheduler) tự tính giảm giá theo cách khác nhau.
- Một transaction chứa lời gọi mạng dài và không có chiến lược phục hồi phân tán.
- Consumer nhận JPA entity hoặc phải biết tên bảng để đọc dữ liệu ưu đãi.

Khi thấy dấu hiệu, hãy lần theo một kịch bản cụ thể và kiểm tra test trước khi chuyển trách nhiệm. Không cần tạo thêm interface hoặc domain service nếu một lớp hiện có đã có hợp đồng và trách nhiệm phù hợp.

## 11. Xử lý cạnh tranh, idempotency và consistency

### Hai request cùng dùng lượt ưu đãi cuối

Giả sử mã `SAVE10` còn đúng một lượt. Hai request cùng đọc `remaining_uses = 1`, cả hai đều thấy đủ điều kiện rồi cùng tạo đơn. Nếu không có bảo vệ ở database hoặc cơ chế khóa thích hợp, giới hạn có thể bị vượt.

Một lựa chọn là cập nhật có điều kiện:

~~~sql
UPDATE promotion
SET remaining_uses = remaining_uses - 1
WHERE id = :promotion_id
  AND remaining_uses > 0;
~~~

Ứng dụng kiểm tra số dòng bị cập nhật. Nếu bằng 0, không còn lượt để áp dụng. Lệnh cập nhật và việc lưu đơn phải nằm trong cùng transaction trên cùng database nếu yêu cầu là hoặc cả hai cùng thành công hoặc cả hai cùng thất bại. Cú pháp placeholder và cách lấy affected row count tùy công nghệ truy cập dữ liệu.

Một lựa chọn khác là optimistic locking với version column hoặc khóa pessimistic trong phạm vi ngắn. Chọn phương án theo tải, mức tranh chấp và khả năng chấp nhận retry. Không giữ khóa trong khi gọi dịch vụ ngoài.

### Idempotency khi client retry

Client có thể timeout sau khi server đã commit đơn nhưng trước khi nhận response. Khi gửi lại cùng request, server cần nhận diện đây là cùng một ý định tạo đơn. Có thể lưu idempotency key cùng customer/operation và kết quả; tạo unique constraint trên phạm vi khóa phù hợp. Khi request lặp đến, trả lại kết quả đã lưu thay vì trừ thêm một lượt ưu đãi hoặc tạo đơn mới.

Idempotency key cần được kiểm tra phạm vi và thời hạn lưu. Không nên dùng một key toàn cục không gắn với actor hoặc loại thao tác nếu điều đó có thể gây va chạm giữa người dùng.

### Consistency của cache và dữ liệu ưu đãi

Cache có thể giảm thời gian đọc cấu hình ưu đãi, nhưng không nên để cache là nguồn duy nhất quyết định lượt dùng cuối cùng. Dữ liệu về trạng thái, thời hạn hoặc số lượt có thể thay đổi giữa lúc đọc cache và ghi đơn. Với điều kiện cần bảo đảm mạnh, transaction/database constraint phải là nơi quyết định cuối cùng. Cache có thể phục vụ dữ liệu ít thay đổi, còn bước reserve/use phải xác minh nguyên tử ở nơi sở hữu dữ liệu.

Nếu hệ thống chấp nhận eventual consistency cho báo cáo hoặc analytics, consumer có thể cập nhật read model sau khi nhận event. Không dùng read model bất đồng bộ để quyết định một invariant cần được bảo đảm đồng bộ trong giao dịch tạo đơn.

## 12. Kiểm thử hành vi, ranh giới và hiệu năng

Một bộ kiểm thử phù hợp nên có nhiều lớp:

| Loại kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Unit test domain | Quy tắc ưu đãi và invariant | Mã hết hạn bị từ chối; discount không vượt eligible subtotal. |
| Unit test application | Điều phối và kết quả use case | Command hợp lệ tạo đơn, ghi nhận lượt dùng và yêu cầu ghi outbox. |
| Repository integration test | SQL, constraint và cập nhật đồng thời | Hai transaction tranh lượt cuối không thể cùng reserve thành công. |
| Transaction test | Thay đổi cục bộ commit/rollback cùng nhau | Lỗi khi ghi outbox làm order và promotion usage rollback. |
| Outbox/consumer test | Phát lại event không gây tác dụng phụ trùng | Event ID được xử lý idempotent. |
| Controller test | DTO, xác thực và ánh xạ response | Mã ưu đãi được chuyển vào command; lỗi nghiệp vụ thành response đúng. |
| Architecture test | Phụ thuộc đúng hướng | Controller không phụ thuộc persistence adapter; domain không phụ thuộc Spring Web. |
| Load/performance test | Đáp ứng SLO dưới tải đại diện | So sánh p95/p99, throughput, query count và pool usage trước/sau. |

Test transaction cần xác minh trạng thái dữ liệu sau khi lỗi xảy ra, không chỉ kiểm tra exception được ném. Test concurrency cần tạo tranh chấp thực tế trên database hoặc engine tương thích; mock repository không chứng minh được khóa và constraint hoạt động đúng.

Load test nên có cả request có và không có mã ưu đãi, mã phổ biến gây tranh chấp và mã ít được dùng. Tải thử phải đủ dài để quan sát connection pool, GC, cache và outbox backlog; một burst ngắn có thể bỏ lỡ vấn đề tích lũy.

## 13. Triển khai thay đổi theo giai đoạn

Nếu tính năng cần cột mới hoặc bảng promotion usage, hãy dùng migration có phiên bản và kế hoạch tương thích:

1. **Expand:** thêm bảng/cột/index mới theo cách phiên bản ứng dụng hiện tại vẫn hoạt động.
2. **Deploy code tương thích:** triển khai code có thể đọc dữ liệu mới nhưng chưa bật tính năng cho toàn bộ người dùng.
3. **Backfill/configure:** nạp dữ liệu ưu đãi, kiểm tra constraint và xác nhận query plan.
4. **Enable gradually:** bật feature flag cho nhóm nhỏ, quan sát latency, lỗi, số lượt sử dụng và outbox lag.
5. **Contract:** chỉ xóa cấu trúc cũ hoặc code tương thích sau khi không còn consumer cần chúng.

Feature flag cần có owner, giá trị mặc định an toàn và cách tắt nhanh. Nếu tính năng tạo tác dụng phụ như trừ lượt ưu đãi, tắt flag không hoàn tác các đơn đã commit; cần có quy trình nghiệp vụ rõ cho dữ liệu đã phát sinh.

Triển khai canary hoặc theo nhóm khách hàng giúp so sánh nhóm bật/tắt trong điều kiện gần nhau. Theo dõi SLO, error budget, database load và backlog. Nếu vượt ngưỡng, dừng rollout hoặc tắt tính năng theo chính sách đã chuẩn bị. Không rollback schema một cách máy móc khi đã có dữ liệu mới; có thể cần forward fix hoặc giữ schema tương thích với phiên bản ứng dụng đang chạy.

## 14. Quy trình thực hành từ yêu cầu đến kết luận

~~~mermaid
flowchart TD
    A[Chốt quy tắc mã ưu đãi] --> B[Chọn kịch bản và baseline]
    B --> C[Map trách nhiệm theo tầng]
    C --> D[Thiết kế command, policy, repository và transaction]
    D --> E[Implement + unit/integration tests]
    E --> F[Đo trace, metrics và load test]
    F --> G{SLO và invariant đạt?}
    G -->|Có| H[Canary và theo dõi]
    G -->|Không| I[Tìm bottleneck / sửa ranh giới]
    I --> E
    H --> J[Đánh giá kết quả và ghi quyết định]
~~~

Trong mỗi vòng, hãy ghi lại:

- Quy tắc nghiệp vụ đã chốt và những giả định còn mở.
- Baseline, tải thử, phiên bản code và cấu hình.
- Dependency/sequence diagram cho luồng đặt hàng mới.
- Các thay đổi theo tầng và lý do đặt trách nhiệm ở đó.
- Transaction boundary, consistency model và cách phục hồi.
- Kết quả test, trace, metric và quyết định rollout.

## 15. Tự rà soát trước khi phát hành

1. Mã ưu đãi được kiểm tra và tính toán ở đúng tầng chưa?
2. Controller chỉ xử lý giao thức và chuyển command chưa?
3. Ca sử dụng có transaction boundary rõ và các repository có cùng tham gia transaction như giả định không?
4. Lượt dùng ưu đãi có được bảo vệ trước hai request đồng thời không?
5. Client retry có thể tạo đơn hoặc trừ lượt hai lần không?
6. Event được ghi cùng transaction qua outbox chưa; consumer có idempotent không?
7. Có lời gọi mạng nào đang giữ transaction hoặc database lock lâu không?
8. Metric có cardinality kiểm soát được, trace có span hữu ích và log không lộ dữ liệu nhạy cảm không?
9. p95/p99, throughput, error rate, query count và outbox lag có nằm trong ngưỡng không?
10. Feature flag, canary, rollback/forward-fix và chủ sở hữu vận hành đã rõ chưa?

## Kết luận

Một thay đổi nghiệp vụ mới là phép thử thực tế cho cả hiệu năng lẫn ranh giới kiến trúc. Với mã ưu đãi đơn hàng, tầng trình bày tiếp nhận dữ liệu, tầng ứng dụng điều phối transaction, domain policy bảo vệ quy tắc giảm giá và adapter dữ liệu quản lý truy vấn/ghi nhận lượt dùng. Hãy đo baseline, lần theo trace, kiểm tra concurrency và consistency, ghi event bằng outbox khi cần bảo đảm cùng commit với đơn, rồi so sánh lại dưới tải đại diện. Nếu hiệu năng chưa đạt, tối ưu đúng bottleneck và đánh giá từng trách nhiệm trước khi thay đổi đường đi giữa các tầng. Triển khai theo giai đoạn cùng metric, test và điều kiện dừng giúp tính năng mới đáp ứng nhu cầu mà hệ thống vẫn có thể hiểu, thay đổi và vận hành an toàn.
