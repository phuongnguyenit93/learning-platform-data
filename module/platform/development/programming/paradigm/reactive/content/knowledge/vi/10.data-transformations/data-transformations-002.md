# Lọc phần tử theo điều kiện và theo kiểu dữ liệu

Một luồng reactive thường chứa nhiều phần tử hơn một bước xử lý cần dùng. Ví dụ, luồng sự kiện của hệ thống đơn hàng có thể chứa nhiều loại sự kiện; một pipeline tính tồn kho chỉ quan tâm đến sự kiện tạo đơn hợp lệ. Project Reactor cung cấp các toán tử lọc để chọn phần tử phù hợp trước khi tiếp tục biến đổi hoặc gọi dịch vụ.

Ba toán tử thường gặp là:

- **`filter(predicate)`:** giữ phần tử khi điều kiện đồng bộ trả về `true`.
- **`filterWhen(asyncPredicate)`:** giữ phần tử khi Publisher kết quả của điều kiện bất đồng bộ phát ra `true`.
- **`ofType(Class<R>)`:** giữ phần tử tương thích với kiểu được chỉ định và chuyển kiểu đầu ra sang `R`.

Chọn đúng toán tử giúp pipeline thể hiện rõ quy tắc nghiệp vụ, giữ kiểu dữ liệu an toàn và kiểm soát cách các bước bất đồng bộ tương tác với backpressure.

Các kiểu `Order`, `OrderCreated`, `PaymentReceived` và những dịch vụ trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa.

## 1. Lọc phần tử bằng filter

`filter` nhận một predicate có kiểu `Predicate<T>`. Với mỗi phần tử `T` từ upstream, predicate được đánh giá:

- Trả về `true`: phần tử được chuyển tiếp xuống downstream.
- Trả về `false`: phần tử bị loại khỏi luồng đầu ra.

Ví dụ, chỉ giữ các đơn hàng có tổng tiền dương:

~~~java
import reactor.core.publisher.Flux;

Flux<Order> orders = orderRepository.findAll();

Flux<Order> payableOrders = orders
    .filter(order -> order.total().signum() > 0);
~~~

Nếu đầu vào lần lượt có đơn hàng trị giá 120.000, 0 và 85.000 đồng, đầu ra chỉ chứa hai đơn hàng có tổng tiền dương. Kiểu dữ liệu vẫn là `Flux<Order>` vì filter chỉ quyết định giữ hay loại phần tử, không biến đổi phần tử.

Một pipeline có thể kết hợp nhiều điều kiện:

~~~java
import java.math.BigDecimal;
import reactor.core.publisher.Flux;

Flux<Order> eligibleOrders = orders
    .filter(order -> order.status() == OrderStatus.PENDING)
    .filter(order -> order.total().compareTo(new BigDecimal("50000")) >= 0)
    .filter(order -> !order.customerId().isBlank());
~~~

Các toán tử filter được áp dụng theo thứ tự từ trên xuống. Phần tử bị loại ở một bước sẽ không đi qua các bước phía sau. Vì vậy, có thể đặt điều kiện rẻ và loại được nhiều phần tử ở đầu pipeline để giảm công việc tiếp theo.

Predicate nên là một phép kiểm tra nhanh, dễ dự đoán và không có side effect. Không nên gửi HTTP request, ghi cơ sở dữ liệu hoặc thay đổi trạng thái dùng chung bên trong predicate đồng bộ. Những công việc đó có thể chặn thread đang phát tín hiệu hoặc tạo hành vi khó kiểm thử.

## 2. Lọc bất đồng bộ bằng filterWhen

Một số điều kiện lọc cần gọi dịch vụ hoặc truy cập dữ liệu bất đồng bộ. Ví dụ, muốn giữ đơn hàng khi dịch vụ kiểm tra gian lận xác nhận đơn hợp lệ. Không thể đặt một lời gọi bất đồng bộ vào predicate của `filter` vì `filter` cần kết quả boolean ngay trong lần đánh giá.

`filterWhen` nhận một hàm trả về Publisher<Boolean>. Phần tử được giữ khi Publisher của điều kiện phát ra `true`:

~~~java
import reactor.core.publisher.Flux;

Flux<Order> approvedOrders = orderRepository.findAll()
    .filterWhen(order ->
        fraudService.isAllowed(order.id())
    );
~~~

Giả sử `fraudService.isAllowed(id)` trả về `Mono<Boolean>`. Mỗi đơn hàng được kiểm tra bằng một thao tác bất đồng bộ; pipeline giữ đơn hàng khi kết quả là true. Giá trị đầu ra vẫn là `Order`, không phải Boolean, vì filterWhen dùng boolean để quyết định giữ phần tử gốc.

Có thể kết hợp điều kiện đồng bộ và bất đồng bộ:

~~~java
import reactor.core.publisher.Flux;

Flux<Order> readyOrders = orderRepository.findAll()
    .filter(order -> order.total().signum() > 0)
    .filterWhen(order -> inventoryService.hasStock(order.productId()));
~~~

Ở đây, đơn hàng có tổng tiền không dương bị loại trước khi gọi dịch vụ tồn kho. Cách sắp xếp này tránh thực hiện kiểm tra bất đồng bộ cho các phần tử chắc chắn không phù hợp.

Publisher kiểm tra trong `filterWhen` cần có kết quả boolean để quyết định. Nếu Publisher kiểm tra hoàn tất mà không phát giá trị, phần tử tương ứng không được giữ lại. Nếu Publisher kiểm tra phát lỗi, lỗi được truyền vào pipeline và kết thúc nhánh đó, trừ khi có toán tử xử lý lỗi ở vị trí thích hợp.

`filterWhen` không tự biến một lời gọi chặn thành bất đồng bộ. Hàm predicate cần trả về Publisher dựa trên API reactive hoặc một tác vụ đã được chuyển sang scheduler phù hợp. Nếu bọc một API chặn, cần cô lập nó bằng scheduler dành cho công việc chặn thay vì gọi trực tiếp trên event loop.

## 3. Lọc theo kiểu dữ liệu bằng ofType

Khi một Publisher mang nhiều kiểu phần tử, có thể cần chọn một loại cụ thể. `ofType(Class<R>)` vừa kiểm tra kiểu tương thích vừa chuyển kiểu phần tử đầu ra sang `R`.

~~~java
import java.math.BigDecimal;
import reactor.core.publisher.Flux;

record OrderCreated(String orderId) {}
record PaymentReceived(String orderId, BigDecimal amount) {}

Flux<Object> messages = Flux.<Object>just(
    new OrderCreated("ORD-101"),
    new PaymentReceived("ORD-101", new BigDecimal("120000")),
    "heartbeat",
    new OrderCreated("ORD-102")
);

Flux<OrderCreated> createdOrders =
    messages.ofType(OrderCreated.class);
~~~

Đầu ra chỉ chứa các đối tượng `OrderCreated`. Kiểu của luồng đầu ra là `Flux<OrderCreated>`, do đó các toán tử phía sau có thể truy cập trực tiếp `orderId()` mà không cần ép kiểu thủ công.

`ofType` kiểm tra khả năng tương thích kiểu, tương tự `Class.isInstance`. Vì thế, đối tượng thuộc lớp con hoặc triển khai interface được chỉ định cũng phù hợp. Nếu chỉ muốn lọc theo điều kiện nghiệp vụ, dùng `filter`; nếu muốn lọc và thu hẹp kiểu, dùng `ofType`.

Có thể viết logic tương đương bằng `filter` và `cast`:

~~~java
Flux<OrderCreated> createdOrders = messages
    .filter(OrderCreated.class::isInstance)
    .cast(OrderCreated.class);
~~~

`ofType(OrderCreated.class)` gọn hơn và thể hiện trực tiếp ý định. Không nên dùng `map(value -> (OrderCreated) value)` trên một luồng hỗn hợp mà chưa lọc kiểu, vì một phần tử không tương thích sẽ gây `ClassCastException` và làm luồng kết thúc bằng lỗi.

## 4. Kết hợp filter, filterWhen và ofType

Trong hệ thống sự kiện, ba toán tử có thể được kết hợp để lọc theo kiểu, loại dữ liệu không hợp lệ và xác minh điều kiện từ xa:

~~~java
Flux<OrderCreated> acceptedOrders = messageBus.events()
    .ofType(OrderCreated.class)
    .filter(event -> !event.orderId().isBlank())
    .filterWhen(event ->
        fraudService.isAllowed(event.orderId())
    );
~~~

Pipeline có ba giai đoạn:

1. `ofType` chỉ giữ sự kiện tạo đơn và thu hẹp kiểu đầu ra thành `OrderCreated`.
2. `filter` loại sự kiện có mã đơn hàng rỗng.
3. `filterWhen` kiểm tra chính sách gian lận bất đồng bộ và chỉ giữ sự kiện được chấp thuận.

Thứ tự các bước có ý nghĩa về hiệu năng. Nếu gọi kiểm tra từ xa trước khi lọc kiểu hoặc kiểm tra dữ liệu cơ bản, hệ thống có thể thực hiện nhiều yêu cầu không cần thiết. Hãy đưa các điều kiện rẻ và có tính loại trừ cao lên trước, miễn là việc đổi thứ tự không làm thay đổi quy tắc nghiệp vụ.

Lọc không biến đổi phần tử. Nếu cần sửa dữ liệu sau khi chọn, hãy nối thêm `map`:

~~~java
import java.util.Locale;
import reactor.core.publisher.Flux;

Flux<EnrichedOrder> enriched = acceptedOrders
    .map(event -> new EnrichedOrder(
        event.orderId(),
        event.orderId().toUpperCase(Locale.ROOT)
    ));
~~~

Nếu cần gọi một dịch vụ bất đồng bộ để tạo dữ liệu mới, hãy dùng `flatMap` sau bước lọc:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderSummary> summaries = acceptedOrders
    .flatMap(orderService::loadSummary);
~~~

Có thể ghi nhớ sự khác nhau:

| Toán tử | Mục đích | Kiểu phần tử đầu ra |
|---|---|---|
| `filter` | Chọn phần tử theo điều kiện đồng bộ | Giữ nguyên `T` |
| `filterWhen` | Chọn phần tử theo điều kiện bất đồng bộ | Giữ nguyên `T` |
| `ofType` | Chọn phần tử theo kiểu và thu hẹp kiểu | Chuyển từ `T` sang `R` |
| `map` | Biến đổi từng phần tử | Chuyển `T` sang `R` |
| `flatMap` | Biến đổi mỗi phần tử thành Publisher và hợp nhất kết quả | Kiểu phần tử do Publisher con phát ra |

## 5. Điều gì xảy ra khi phần tử bị loại?

Một phần tử không thỏa điều kiện sẽ không được phát xuống downstream. Tuy nhiên, nó vẫn đã được đọc từ upstream để đánh giá predicate.

Điều này có ý nghĩa với backpressure. Demand của downstream đếm số phần tử được phát qua ranh giới subscription. Nếu downstream yêu cầu một phần tử nhưng filter loại phần tử đầu tiên, toán tử có thể cần yêu cầu thêm dữ liệu upstream để tìm một phần tử phù hợp. Nguồn có thể phải phát nhiều phần tử hơn số phần tử cuối cùng downstream nhận được.

Ví dụ:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> evenNumbers = Flux.range(1, 100)
    .filter(number -> number % 2 == 0);
~~~

Nếu downstream yêu cầu một phần tử, filter có thể cần đọc 1 rồi loại, đọc 2 rồi phát. Một yêu cầu ở downstream vì thế không nhất thiết tương ứng với đúng một lần phát từ nguồn.

Các hệ quả thực tế:

- Điều kiện lọc càng chặt, nguồn có thể phải phát càng nhiều phần tử để đáp ứng cùng một demand downstream.
- Nếu phần lớn phần tử bị loại, chi phí đọc và đánh giá predicate vẫn tồn tại.
- Lọc sau một nguồn rất tốn kém không giúp giảm chi phí mà nguồn đã phải trả để tạo phần tử.
- Backpressure vẫn được duy trì qua toán tử; filter không cho phép downstream nhận vượt quá demand.

Với `filterWhen`, việc kiểm tra bất đồng bộ cũng cần tài nguyên và có thể tạo độ trễ. Cần theo dõi số lần gọi dịch vụ, thời gian phản hồi và số phần tử đang chờ kiểm tra. Không nên mặc định rằng tăng số lượng kiểm tra đồng thời luôn làm pipeline nhanh hơn; điều đó có thể gây quá tải cho dịch vụ được gọi.

## 6. Xử lý trường hợp không có phần tử phù hợp

Sau một hoặc nhiều toán tử lọc, luồng có thể không còn phần tử nào. Đây không phải lỗi. Publisher có thể hoàn tất bình thường mà không phát `onNext`.

Ví dụ:

~~~java
import reactor.core.publisher.Mono;

Mono<Order> selectedOrder = orderRepository.findById(orderId)
    .filter(order -> order.status() == OrderStatus.PENDING);
~~~

Nếu đơn hàng không tồn tại hoặc trạng thái không phải PENDING, `Mono<Order>` hoàn tất rỗng. Có thể dùng `switchIfEmpty` để cung cấp hành vi dự phòng:

~~~java
import reactor.core.publisher.Mono;

Mono<Order> selectedOrder = orderRepository.findById(orderId)
    .filter(order -> order.status() == OrderStatus.PENDING)
    .switchIfEmpty(Mono.error(
        new OrderNotEligibleException(orderId)
    ));
~~~

Cần phân biệt ba trường hợp:

- Không có bản ghi từ nguồn.
- Có bản ghi nhưng bị điều kiện lọc loại.
- Có lỗi trong quá trình đọc hoặc đánh giá điều kiện.

Nếu nghiệp vụ cần phân biệt “không tìm thấy” với “không đủ điều kiện”, hãy biểu diễn hai trường hợp bằng trạng thái hoặc lỗi riêng trước khi gộp chúng thành một kết quả rỗng.

## 7. Lỗi trong predicate và điều kiện bất đồng bộ

Nếu predicate của `filter` ném exception, pipeline kết thúc bằng `onError`. Tương tự, nếu Publisher do `filterWhen` trả về phát lỗi, lỗi được truyền xuống downstream.

~~~java
import reactor.core.publisher.Flux;

Flux<Order> safeOrders = orderRepository.findAll()
    .filter(order -> {
        if (order.total() == null) {
            throw new IllegalStateException("Đơn hàng thiếu tổng tiền");
        }
        return order.total().signum() > 0;
    })
    .onErrorResume(error -> {
        log.error("Không thể lọc luồng đơn hàng", error);
        return Flux.empty();
    });
~~~

Đây chỉ là ví dụ minh họa vị trí xử lý lỗi. Trong hệ thống thực tế, cần quyết định lỗi dữ liệu của một phần tử có nên làm hỏng toàn bộ luồng hay được chuyển thành kết quả lỗi riêng cho phần tử đó. Dùng `onErrorResume` ở cuối pipeline để thay toàn bộ luồng bằng rỗng có thể che giấu lỗi dữ liệu quan trọng.

Với kiểm tra bất đồng bộ, có thể xử lý lỗi ở ngay Publisher kiểm tra nếu nghiệp vụ có chính sách dự phòng rõ ràng:

~~~java
import reactor.core.publisher.Flux;

Flux<Order> allowedOrders = orders
    .filterWhen(order ->
        fraudService.isAllowed(order.id())
            .onErrorReturn(false)
    );
~~~

Ví dụ này coi lỗi kiểm tra là không được chấp thuận. Đây là quyết định nghiệp vụ mang tính fail-closed; chỉ dùng khi chính sách yêu cầu như vậy. Nếu lỗi dịch vụ cần được báo ra ngoài hoặc thử lại, hãy xử lý theo chính sách tương ứng thay vì tự động chuyển lỗi thành false.

## 8. Kiểm thử các toán tử lọc bằng StepVerifier

`StepVerifier` giúp kiểm tra chính xác phần tử nào được phát và cách luồng kết thúc.

Kiểm thử `filter`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void filterChiGiuSoChan() {
    StepVerifier.create(
            Flux.range(1, 6).filter(number -> number % 2 == 0)
        )
        .expectNext(2, 4, 6)
        .verifyComplete();
}
~~~

Kiểm thử `ofType`:

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void ofTypeChiGiuSuKienTaoDon() {
    Flux<Object> messages = Flux.<Object>just(
        new OrderCreated("ORD-101"),
        "heartbeat",
        new PaymentReceived("ORD-101", new BigDecimal("120000"))
    );

    StepVerifier.create(messages.ofType(OrderCreated.class))
        .expectNext(new OrderCreated("ORD-101"))
        .verifyComplete();
}
~~~

Kiểm thử `filterWhen` với thời gian ảo:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void filterWhenChoKetQuaKiemTraBatDongBo() {
    StepVerifier.withVirtualTime(() ->
            Flux.range(1, 5)
                .filterWhen(number ->
                    Mono.delay(Duration.ofMillis(100))
                        .map(ignored -> number % 2 == 0)
                )
        )
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(2, 4)
        .verifyComplete();
}
~~~

Supplier truyền vào `withVirtualTime` tạo pipeline sau khi virtual scheduler được cài đặt. Nhờ đó, phép thử không cần chờ đồng hồ thực cho các Publisher thời gian.

Nên bổ sung các trường hợp:

- Predicate luôn false khiến luồng hoàn tất rỗng.
- Predicate ném lỗi khiến luồng phát `onError`.
- Publisher kiểm tra trong `filterWhen` hoàn tất rỗng hoặc phát lỗi.
- `ofType` nhận đối tượng thuộc lớp con hoặc triển khai interface.
- `filter` và `filterWhen` được kết hợp nhưng vẫn giữ thứ tự phần tử đầu vào.
- Downstream yêu cầu ít phần tử; filter phải không phát vượt quá demand.

## 9. Lựa chọn toán tử khi thiết kế pipeline

Hãy xác định loại điều kiện trước khi chọn toán tử:

| Tình huống | Toán tử phù hợp |
|---|---|
| Kiểm tra trường dữ liệu có sẵn trong object | `filter` |
| Kiểm tra quyền, tồn kho hoặc trạng thái qua API reactive | `filterWhen` |
| Luồng chứa nhiều lớp sự kiện và chỉ cần một loại | `ofType` |
| Cần thay đổi object sau khi lọc | `map` |
| Cần gọi Publisher bất đồng bộ để tạo kết quả mới | `flatMap` |
| Không còn phần tử phù hợp và cần hành vi thay thế | `switchIfEmpty` |

Khi xây dựng pipeline, nên ưu tiên điều kiện đồng bộ, rẻ và có khả năng loại phần tử sớm. Chỉ gọi điều kiện bất đồng bộ khi cần thiết, và kiểm soát tải của dịch vụ được gọi. Dùng `ofType` để thu hẹp kiểu một cách rõ ràng, tránh ép kiểu thủ công trên luồng hỗn hợp.

Các toán tử lọc là bước chọn dữ liệu trong pipeline reactive. `filter` và `filterWhen` quyết định phần tử nào được đi tiếp; `ofType` chọn phần tử theo kiểu và cung cấp kiểu đầu ra cụ thể. Khi kết hợp đúng với `map`, `flatMap`, xử lý lỗi và backpressure, chúng giúp pipeline Mono và Flux giữ được luồng dữ liệu rõ ràng, an toàn kiểu và phù hợp với yêu cầu nghiệp vụ.

