# Thiết kế ứng dụng

## Giữ logic nghiệp vụ dễ kiểm thử bằng hàm thuần

Trong ứng dụng reactive, dữ liệu đi qua nhiều toán tử trước khi tạo ra kết quả hoặc thực hiện một tác vụ bên ngoài. Nếu mỗi bước vừa tính toán nghiệp vụ, vừa đọc database, ghi log, lấy thời gian hệ thống và thay đổi trạng thái dùng chung, pipeline sẽ khó kiểm thử và khó dự đoán khi có retry, nhiều subscription hoặc cancellation.

Một cách thiết kế hiệu quả là giữ phần quyết định nghiệp vụ trong **hàm thuần** (pure function), sau đó để các thành phần reactive điều phối I/O và vòng đời tác vụ. Hàm thuần nhận đầu vào tường minh, trả kết quả xác định và không làm thay đổi trạng thái bên ngoài. Nhờ vậy, ta có thể kiểm thử logic trực tiếp bằng JUnit mà không cần khởi động Reactor, mock database hoặc chờ scheduler.

Trong module REACTIVE_PROGRAMMING, cách tổ chức này giúp pipeline **Mono** và **Flux** tập trung vào việc phối hợp các tác vụ bất đồng bộ. Các toán tử như `map` có thể áp dụng quy tắc nghiệp vụ thuần; `flatMap` nối các thao tác trả về Publisher; ranh giới I/O chịu trách nhiệm đọc, ghi và quản lý lỗi từ hệ thống bên ngoài.

### 1. Hàm thuần là gì?

Một hàm thuần có hai đặc điểm chính:

1. Với cùng đầu vào, hàm luôn trả về cùng kết quả.
2. Việc gọi hàm không tạo side effect quan sát được bên ngoài hàm.

Ví dụ:

~~~java
static BigDecimal lineTotal(int quantity, BigDecimal unitPrice) {
    return unitPrice.multiply(BigDecimal.valueOf(quantity));
}
~~~

Hàm trên chỉ tính toán từ hai tham số và trả về một giá trị mới. Nó không truy cập database, không đọc đồng hồ, không sửa biến toàn cục và không ghi dữ liệu ra ngoài.

Ngược lại, hàm sau không thuần:

~~~java
static BigDecimal calculateTotal(Order order) {
    BigDecimal rate = exchangeRateClient.currentRate();
    auditLog.write("Calculating order " + order.id());
    return order.total().multiply(rate);
}
~~~

Kết quả phụ thuộc vào tỷ giá tại thời điểm gọi, đồng thời hàm ghi log. Cùng một Order có thể cho kết quả khác nhau và việc gọi hàm làm thay đổi hệ thống bên ngoài. Ta khó kiểm thử phép tính mà không giả lập client và logger.

Hàm thuần không nhất thiết phải ngắn hoặc không được dùng vòng lặp. Một phép tính phức tạp vẫn có thể thuần nếu mọi dữ liệu cần thiết được truyền vào và không có side effect.

### 2. Tách quyết định nghiệp vụ khỏi tác động bên ngoài

Có thể tổ chức một thành phần theo mô hình **functional core, imperative shell**:

~~~text
       HTTP / Message / Scheduler
                  |
                  v
          Reactive orchestration
          đọc dữ liệu, phối hợp I/O
                  |
                  v
           Pure business logic
        quyết định và tính toán
                  |
                  v
          Reactive orchestration
          ghi kết quả, phát sự kiện
                  |
                  v
       Database / HTTP / Broker
~~~

Phần lõi nghiệp vụ nhận dữ liệu và trả quyết định. Phần điều phối reactive chịu trách nhiệm lấy dữ liệu cần thiết, gọi hàm thuần, rồi thực hiện side effect nếu quyết định yêu cầu. Ranh giới này làm rõ phần nào có thể kiểm thử độc lập và phần nào cần kiểm thử với dependency.

| Trách nhiệm | Nơi phù hợp | Ví dụ |
| --- | --- | --- |
| Tính giá, chiết khấu, thuế | Hàm thuần | calculateQuote(order, policy) |
| Kiểm tra điều kiện nghiệp vụ | Hàm thuần | isEligible(customer, offer) |
| Chọn trạng thái tiếp theo | Hàm thuần | decideNextState(current, event) |
| Đọc đơn hàng | Adapter reactive | orderRepository.findById(id) |
| Ghi đơn hàng | Adapter reactive | orderRepository.save(order) |
| Gọi dịch vụ thanh toán | Adapter reactive | paymentClient.authorize(command) |
| Điều phối các tác vụ bất đồng bộ | Service reactive | flatMap, zip, then |

Không phải mọi dòng code đều cần chuyển thành hàm thuần. Mục tiêu là cô lập quy tắc nghiệp vụ quan trọng khỏi những phụ thuộc có thời gian, trạng thái hoặc I/O.

### 3. Ví dụ: tính báo giá bằng hàm thuần

Giả sử ứng dụng cần tính báo giá dựa trên các dòng đơn hàng và hạng khách hàng. Ta mô hình hóa dữ liệu bằng các kiểu bất biến:

~~~java
import java.math.BigDecimal;
import java.util.List;

enum CustomerTier {
    STANDARD,
    GOLD
}

record OrderLine(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

record Quote(
    BigDecimal subtotal,
    BigDecimal discount,
    BigDecimal total
) {}

sealed interface QuoteResult
    permits AcceptedQuote, RejectedQuote {}

record AcceptedQuote(Quote quote) implements QuoteResult {}

record RejectedQuote(String reason) implements QuoteResult {}

record Order(
    String id,
    List<OrderLine> lines,
    CustomerTier customerTier
) {
    Order {
        lines = List.copyOf(lines);
    }
}
~~~

Quy tắc tính báo giá nhận toàn bộ dữ liệu cần thiết qua tham số:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

final class Pricing {
    private Pricing() {}

    static QuoteResult calculateQuote(
        List<OrderLine> lines,
        CustomerTier tier
    ) {
        if (lines == null || lines.isEmpty()) {
            return new RejectedQuote("Đơn hàng không có sản phẩm");
        }

        if (tier == null) {
            return new RejectedQuote("Thiếu hạng khách hàng");
        }

        boolean invalidLine = lines.stream().anyMatch(line ->
            line == null
                || line.quantity() <= 0
                || line.unitPrice() == null
                || line.unitPrice().signum() < 0
        );

        if (invalidLine) {
            return new RejectedQuote("Dòng sản phẩm không hợp lệ");
        }

        BigDecimal subtotal = lines.stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add)
            .setScale(2, RoundingMode.HALF_UP);

        BigDecimal rate = switch (tier) {
            case STANDARD -> new BigDecimal("0.00");
            case GOLD -> new BigDecimal("0.10");
        };

        BigDecimal discount = subtotal.multiply(rate)
            .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.subtract(discount)
            .setScale(2, RoundingMode.HALF_UP);

        return new AcceptedQuote(
            new Quote(subtotal, discount, total)
        );
    }
}
~~~

Hàm `calculateQuote` không truy cập dịch vụ nào và không sửa danh sách đầu vào. Với cùng danh sách dòng hàng và cùng hạng khách hàng, nó luôn trả cùng một `QuoteResult`. Các trường hợp không hợp lệ được biểu diễn thành `RejectedQuote`, nên caller có thể xử lý như một kết quả nghiệp vụ.

Ví dụ dùng `BigDecimal` tránh sai số nhị phân thường gặp khi dùng `double` cho tiền. Quy tắc scale và làm tròn trong ví dụ là chính sách minh họa; ứng dụng thực tế cần đưa quy tắc tiền tệ, thuế và làm tròn vào policy được truyền tường minh.

Nếu nhận một danh sách có thể bị thay đổi từ nơi khác, hãy tạo bản sao bất biến tại biên mô hình hoặc khi tiếp nhận dữ liệu. Hàm thuần không sửa input, nhưng một thread khác thay đổi danh sách trong lúc hàm đang đọc vẫn có thể làm kết quả không ổn định.

### 4. Kiểm thử hàm thuần trực tiếp

Vì hàm không phụ thuộc Reactor hoặc hệ thống bên ngoài, có thể kiểm thử bằng JUnit thông thường:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class PricingTest {
    @Test
    void appliesGoldDiscount() {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 2, new BigDecimal("20.00"))
        );

        QuoteResult result =
            Pricing.calculateQuote(lines, CustomerTier.GOLD);

        AcceptedQuote accepted =
            assertInstanceOf(AcceptedQuote.class, result);

        assertEquals(
            new Quote(
                new BigDecimal("40.00"),
                new BigDecimal("4.00"),
                new BigDecimal("36.00")
            ),
            accepted.quote()
        );
    }

    @Test
    void rejectsEmptyOrder() {
        QuoteResult result =
            Pricing.calculateQuote(List.of(), CustomerTier.STANDARD);

        assertEquals(
            new RejectedQuote("Đơn hàng không có sản phẩm"),
            result
        );
    }
}
~~~

Kiểm thử không cần mock repository, khởi tạo scheduler hoặc gọi `StepVerifier`. Mỗi test chỉ mô tả đầu vào và kết quả mong đợi. Khi quy tắc chiết khấu thay đổi, test chỉ ra chính xác phép tính hoặc trường hợp biên bị ảnh hưởng.

Nên bao phủ cả trường hợp biên như số lượng bằng không, giá âm, danh sách rỗng, mức chiết khấu tối đa và quy tắc làm tròn. Hàm thuần giúp các trường hợp này chạy nhanh và lặp lại ổn định.

### 5. Kết hợp hàm thuần trong Mono và Flux

Khi dữ liệu đã có trong Publisher, dùng `map` để áp dụng phép biến đổi đồng bộ và thuần:

~~~java
import reactor.core.publisher.Mono;

Mono<QuoteResult> previewQuote(String orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(
            Mono.error(new OrderNotFoundException(orderId))
        )
        .map(order ->
            Pricing.calculateQuote(order.lines(), order.customerTier())
        );
}
~~~

`findById` là tác động I/O và trả về `Mono<Order>`. `map` nhận Order đã có rồi gọi hàm tính báo giá thuần. Không cần tạo một subscription phụ hoặc block để lấy Order ra khỏi Mono.

Với nhiều đơn hàng, cùng quy tắc thuần có thể được áp dụng trên từng phần tử:

~~~java
import reactor.core.publisher.Flux;

Flux<QuoteResult> previews =
    orderRepository.findAll()
        .map(order ->
            Pricing.calculateQuote(
                order.lines(),
                order.customerTier()
            )
        );
~~~

Hàm thuần có thể được gọi mỗi khi phần tử đi qua `map`. Nếu nguồn cold được subscribe nhiều lần, phép tính cũng có thể chạy nhiều lần; vì không có side effect nên việc tính lại không làm thay đổi hệ thống.

### 6. Dùng flatMap cho tác động bất đồng bộ

`map` phù hợp khi hàm trả về một giá trị đồng bộ. Khi bước tiếp theo trả về Publisher, dùng `flatMap` để nối pipeline:

~~~java
import reactor.core.publisher.Mono;

Mono<Quote> createQuote(String orderId) {
    return previewQuote(orderId)
        .flatMap(result -> {
            if (result instanceof AcceptedQuote accepted) {
                return quoteRepository.save(accepted.quote());
            }

            RejectedQuote rejected = (RejectedQuote) result;
            return Mono.error(
                new QuoteRejectedException(rejected.reason())
            );
        });
}
~~~

Ở đây, hàm tính giá vẫn thuần và được gọi bằng `map`. Việc lưu báo giá là I/O, nên được biểu diễn bằng Publisher từ repository và nối bằng `flatMap`. Lỗi nghiệp vụ được chuyển thành `Mono.error` để caller xử lý theo hợp đồng của service.

Không đặt lệnh ghi database vào bên trong `map` rồi trả về một giá trị thông thường. Điều đó vừa che giấu side effect, vừa khiến pipeline không quản lý được completion, lỗi và cancellation của thao tác ghi.

### 7. Đưa thời gian, tỷ giá và cấu hình vào đầu vào

Một hàm sẽ không thuần nếu tự đọc dữ liệu thay đổi theo môi trường như:

- `Instant.now()` hoặc `LocalDate.now()`.
- Tỷ giá, giá thị trường hoặc cấu hình đang được cập nhật.
- Số ngẫu nhiên.
- Locale, timezone hoặc thông tin tenant lấy từ trạng thái toàn cục.
- Biến static mutable hoặc cache thay đổi mà hàm tự truy cập.

Hãy đọc các dữ liệu này ở lớp điều phối, sau đó truyền chúng vào hàm quyết định:

~~~java
import java.time.Instant;

record Subscription(
    Instant expiresAt,
    boolean paymentValid
) {}

enum RenewalDecision {
    RENEW,
    PAYMENT_REQUIRED,
    EXPIRED
}

static RenewalDecision decideRenewal(
    Subscription subscription,
    Instant now
) {
    if (!subscription.paymentValid()) {
        return RenewalDecision.PAYMENT_REQUIRED;
    }
    if (!subscription.expiresAt().isAfter(now)) {
        return RenewalDecision.EXPIRED;
    }
    return RenewalDecision.RENEW;
}
~~~

Lớp điều phối lấy thời gian một lần và truyền vào:

~~~java
import reactor.core.publisher.Mono;

Mono<RenewalDecision> renewalDecision(String subscriptionId) {
    return subscriptionRepository.findById(subscriptionId)
        .map(subscription ->
            decideRenewal(subscription, clock.instant())
        );
}
~~~

Trong ứng dụng, `Clock` được inject vào service và có thể thay bằng `Clock.fixed(...)` trong test. Hàm `decideRenewal` không biết đồng hồ hệ thống là gì; nó chỉ áp dụng quy tắc lên hai giá trị đầu vào.

Với tỷ giá, hãy đọc tỷ giá thành một object có phiên bản hoặc timestamp rồi truyền vào phép tính. Điều này giúp kết quả báo giá có thể được tái hiện sau này và tránh việc một phép tính đọc nhiều tỷ giá khác nhau giữa chừng.

### 8. Không đặt side effect trong map

Một lỗi thiết kế phổ biến là dùng `map` để cập nhật trạng thái hoặc ghi dữ liệu:

~~~java
// Tránh: side effect ẩn trong phép biến đổi.
Mono<Order> updated =
    orderRepository.findById(orderId)
        .map(order -> {
            auditRepository.write(order.id());
            return order.markProcessed();
        });
~~~

Lời gọi `auditRepository.write` có thể trả về Publisher nhưng bị bỏ qua. Khi đó pipeline không chờ thao tác audit hoàn tất, không kết hợp lỗi và không thể điều khiển cancellation của nó.

Hãy nối side effect thành một phần của pipeline:

~~~java
Mono<Order> updated =
    orderRepository.findById(orderId)
        .map(Order::markProcessed)
        .flatMap(order ->
            auditRepository.write(order.id())
                .thenReturn(order)
        );
~~~

Trong ví dụ này, `markProcessed` là phép biến đổi có thể giữ thuần nếu nó tạo một Order mới. Ghi audit là tác động bất đồng bộ và được nối bằng `flatMap` cùng `thenReturn`. Pipeline chỉ phát Order sau khi thao tác audit hoàn tất; lỗi audit được truyền theo luồng lỗi.

`doOnNext` phù hợp cho quan sát nhẹ như metrics hoặc logging, nhưng không nên dùng nó để thực hiện một bước nghiệp vụ bắt buộc mà pipeline cần chờ. Nếu tác động đó ảnh hưởng kết quả, hãy biểu diễn nó bằng Publisher và kết hợp bằng toán tử.

### 9. Hàm thuần giúp retry dễ dự đoán hơn

Khi pipeline được retry, các bước upstream có thể được thực thi lại. Nếu một lambda trong `map` chỉ tính toán thuần, chạy lại cùng dữ liệu vẫn cho cùng kết quả. Nếu lambda đó ghi database, gửi email hoặc tăng biến đếm, retry có thể lặp side effect.

~~~java
Mono<Quote> quote =
    orderRepository.findById(orderId)
        .map(order ->
            Pricing.calculateQuote(
                order.lines(),
                order.customerTier()
            )
        )
        .flatMap(this::persistAcceptedQuote)
        .retryWhen(retryPolicy);
~~~

Phép tính báo giá có thể chạy lại an toàn nếu đầu vào giống nhau. Tuy nhiên, thao tác `persistAcceptedQuote` có thể đã thành công ở database nhưng phản hồi bị mất trước khi pipeline nhận được kết quả. Retry khi đó có thể gửi lại thao tác ghi.

Với side effect có thể lặp, cần thiết kế idempotency key, unique constraint hoặc cơ chế deduplication phù hợp. Hàm thuần giảm rủi ro lặp tác động trong phần quyết định, nhưng không tự làm cho thao tác bên ngoài trở thành idempotent.

### 10. Hàm thuần không đồng nghĩa với công việc không tốn thời gian

Một hàm có thể thuần nhưng vẫn thực hiện phép tính CPU nặng. Purity nói về tính xác định và side effect; nó không nói về chi phí thời gian hoặc thread thực thi.

Với phép tính ngắn, `map` thường là đủ. Nếu phép tính CPU-bound kéo dài và cần tách khỏi event loop, có thể điều phối phần xử lý bằng `publishOn`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<Recommendation> recommendations =
    customerRepository.findActiveCustomers()
        .publishOn(Schedulers.parallel())
        .map(recommendationEngine::calculate);
~~~

`recommendationEngine.calculate` vẫn là hàm thuần; `publishOn` chỉ quyết định nơi thực hiện các bước downstream. Không dùng scheduler để che giấu một hàm blocking. Nếu hàm cần gọi database hoặc HTTP, hãy đưa I/O ra thành một dependency reactive riêng.

### 11. Kiểm thử service reactive riêng với kiểm thử hàm thuần

Hàm thuần nên được kiểm thử trực tiếp. Service reactive cần kiểm tra việc phối hợp nguồn, lỗi và repository. Ví dụ với Mockito:

~~~java
import java.math.BigDecimal;
import java.util.List;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Order order = new Order(
    "order-42",
    List.of(new OrderLine(
        "BOOK", 2, new BigDecimal("20.00")
    )),
    CustomerTier.GOLD
);

OrderRepository repository = mock(OrderRepository.class);
when(repository.findById("order-42"))
    .thenReturn(Mono.just(order));

OrderQueryService service = new OrderQueryService(repository);

StepVerifier.create(service.previewQuote("order-42"))
    .expectNextMatches(result ->
        result instanceof AcceptedQuote accepted
            && accepted.quote().total()
                .compareTo(new BigDecimal("36.00")) == 0
    )
    .verifyComplete();

verify(repository).findById("order-42");
~~~

Kiểm thử này không kiểm tra lại mọi phép tính chiết khấu; phần đó đã được kiểm tra trong `PricingTest`. Nó xác minh service lấy đúng đơn hàng và đưa kết quả tính toán vào Publisher.

Nên có thêm test cho `Mono.empty()`, lỗi repository và các kết quả từ chối nghiệp vụ. Dùng `StepVerifier` để xác minh cả phần tử lẫn terminal signal; đừng chỉ gọi `subscribe()` rồi kiểm tra ngay vì pipeline có thể chưa chạy xong.

### 12. Tránh trạng thái mutable dùng chung

Hàm thuần sẽ khó giữ tính xác định nếu nó đọc hoặc sửa trạng thái dùng chung:

~~~java
// Tránh trạng thái dùng chung trong logic nghiệp vụ.
static int processedCount = 0;

static Order markProcessed(Order order) {
    processedCount++;
    return order.withProcessed(true);
}
~~~

Khi có nhiều subscription hoặc scheduler, thứ tự cập nhật biến có thể thay đổi. Test chạy song song cũng có thể ảnh hưởng lẫn nhau. Thay vì tăng biến đếm trong logic nghiệp vụ, hãy trả dữ liệu cần thiết trong kết quả rồi để lớp quan sát cập nhật metric ở ranh giới phù hợp.

Ưu tiên record, collection bất biến và object value. Nếu cần accumulator trong pipeline, dùng toán tử có ngữ nghĩa rõ như `reduce` hoặc `scan`, và tránh chia sẻ accumulator mutable giữa các subscription.

~~~java
import java.math.BigDecimal;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<BigDecimal> total =
    Flux.fromIterable(lines)
        .map(line ->
            line.unitPrice().multiply(
                BigDecimal.valueOf(line.quantity())
            )
        )
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

`reduce` tạo kết quả tích lũy theo subscription. Phép cộng là hàm thuần, nên kết quả không phụ thuộc trạng thái bên ngoài.

### 13. Đưa quy tắc nghiệp vụ thành kiểu kết quả rõ ràng

Thay vì dùng exception cho mọi trường hợp từ chối nghiệp vụ, có thể biểu diễn các quyết định dự kiến bằng kiểu kết quả như `QuoteResult`. Điều này giúp phân biệt:

- **Từ chối nghiệp vụ:** dữ liệu hợp lệ về mặt kỹ thuật nhưng không đáp ứng quy tắc, ví dụ đơn hàng rỗng hoặc không đủ điều kiện.
- **Lỗi kỹ thuật:** database không truy cập được, timeout hoặc lỗi giao thức.

Từ chối nghiệp vụ có thể là một phần tử bình thường trong Publisher. Lỗi kỹ thuật thường được biểu diễn bằng `onError` để tầng gọi quyết định retry, fallback hoặc ánh xạ thành lỗi HTTP.

Không nên chuyển mọi exception thành `RejectedQuote`; việc đó có thể che giấu lỗi hạ tầng. Cũng không nên ném exception cho một kết quả từ chối đã được dự kiến trong nghiệp vụ nếu caller cần xử lý như một nhánh bình thường.

### 14. Các câu hỏi khi thiết kế hàm nghiệp vụ

Trước khi viết một quy tắc nghiệp vụ, hãy kiểm tra:

1. Hàm đã nhận đủ dữ liệu cần thiết qua tham số chưa?
2. Hàm có đọc thời gian, cấu hình, tỷ giá hoặc trạng thái toàn cục không?
3. Hàm có sửa object đầu vào, collection hoặc biến static không?
4. Cùng đầu vào có luôn cho cùng kết quả không?
5. Các trường hợp từ chối nghiệp vụ có được biểu diễn rõ ràng không?
6. Side effect có được tách ra thành Publisher riêng không?
7. Nếu pipeline retry hoặc có nhiều subscription, hàm có an toàn khi được gọi lại không?
8. Phép tính có tốn CPU đủ nhiều để cần điều phối scheduler không?

### 15. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Gọi repository trong hàm tính toán | Logic phụ thuộc database và khó test | Truyền dữ liệu đã đọc vào hàm thuần |
| Gọi `Instant.now()` bên trong quy tắc | Kết quả thay đổi theo thời điểm test | Truyền `Instant` hoặc `Clock` từ ngoài |
| Sửa object đầu vào | Kết quả phụ thuộc thứ tự gọi và chia sẻ dữ liệu | Dùng value object bất biến |
| Ghi dữ liệu trong `map` | Pipeline không quản lý completion/lỗi của side effect | Trả Publisher và nối bằng `flatMap` |
| Gọi `subscribe()` trong service để chạy việc phụ | Tạo subscription tách rời, khó cancellation | Trả Publisher cho caller điều phối |
| Dùng biến static để tích lũy kết quả | Race condition giữa subscription | Dùng `reduce`, `scan` hoặc kết quả bất biến |
| Retry quanh side effect không idempotent | Có thể ghi hoặc gửi tác động nhiều lần | Dùng idempotency key và thiết kế retry có chủ đích |
| Cho rằng hàm thuần luôn chạy nhanh | CPU-bound work vẫn có thể chặn event loop | Đo chi phí và điều phối scheduler phù hợp |

### 16. Quy trình áp dụng trong một service reactive

Khi xây dựng một chức năng mới, có thể đi theo trình tự:

1. Xác định dữ liệu đầu vào và quy tắc nghiệp vụ cần áp dụng.
2. Tạo value object bất biến để mô tả dữ liệu và kết quả.
3. Viết hàm thuần nhận đủ dữ liệu, trả quyết định hoặc kết quả rõ ràng.
4. Kiểm thử hàm bằng JUnit với các trường hợp thường và biên.
5. Viết service reactive để đọc dữ liệu bằng `Mono`/`Flux`.
6. Dùng `map` cho phép tính đồng bộ thuần và `flatMap` để nối I/O trả Publisher.
7. Xử lý lỗi kỹ thuật và từ chối nghiệp vụ theo hai hợp đồng riêng.
8. Kiểm thử service bằng `StepVerifier` và mock/fake dependency.
9. Nếu có retry, xác định side effect nào có thể lặp và bảo vệ bằng idempotency.
10. Đo tải để quyết định có cần đổi scheduler cho phần tính toán CPU-bound hay không.

Trong module REACTIVE_PROGRAMMING, hàm thuần giúp giữ quy tắc nghiệp vụ tách biệt khỏi thời gian, database, HTTP và trạng thái dùng chung. Khi phần lõi trả kết quả xác định còn lớp ngoài điều phối I/O bằng **Mono** và **Flux**, ta có thể kiểm thử từng quy tắc nhanh chóng, kiểm tra riêng vòng đời reactive và dự đoán hành vi tốt hơn khi retry, cancellation hoặc nhiều request chạy đồng thời.
