# Chia chuỗi dài thành phép biến đổi có tên và mục đích rõ

## Vì sao cần đặt tên cho từng giai đoạn của pipeline?

Một pipeline Reactor thường bắt đầu ngắn: lấy dữ liệu, lọc điều kiện, gọi dịch vụ phụ, biến đổi kết quả rồi trả về. Khi nghiệp vụ phát triển, chuỗi toán tử có thể dài với nhiều `map`, `filter`, `flatMap`, `onErrorResume`, `publishOn` và các hook quan sát. Nếu mọi bước nằm trong một biểu thức, người đọc phải hiểu toàn bộ chuỗi mới nhận ra từng đoạn đang thực hiện quy tắc nghiệp vụ nào.

Chia chuỗi thành các phép biến đổi có tên giúp thể hiện ý định ở cấp nghiệp vụ. Thay vì đọc một dãy lambda để đoán mục đích, người đọc có thể thấy các bước như `onlyEligibleOrders`, `enrichWithCustomer`, `calculateShipping` và `persistResult`. Tên tốt cũng giúp kiểm thử từng quy tắc riêng, tái sử dụng phép biến đổi và thay đổi một giai đoạn mà không làm rối phần còn lại.

Trong `REACTIVE_PROGRAMMING`, việc đặt tên cần giữ nguyên bản chất reactive của pipeline: phương thức trung gian nên trả về `Mono` hoặc `Flux`, không tự gọi `subscribe()` hay `block()`. Nhờ vậy, demand, cancellation, lỗi và context vẫn được điều khiển từ subscription ở ngoài cùng. Các giai đoạn có tên không chỉ làm mã dễ đọc; chúng tạo ra những ranh giới rõ để thiết kế và quan sát hành vi bất đồng bộ.

## Nhận diện một chuỗi đang quá dài hoặc khó đọc

Một pipeline cần được tách khi người đọc khó trả lời nhanh các câu hỏi sau:

- Bước này đang áp dụng quy tắc nghiệp vụ nào?
- Dữ liệu đi vào và đi ra của giai đoạn có kiểu gì?
- Giai đoạn có thể gọi I/O, phát lỗi, hoàn tất rỗng hoặc hủy công việc không?
- Nó có làm thay đổi thứ tự, concurrency hoặc scheduler không?
- Nó có side effect như ghi database, gửi message hoặc cập nhật metric không?
- Có thể kiểm thử giai đoạn này độc lập bằng dữ liệu đầu vào nhỏ không?

Không phải cứ có nhiều toán tử là phải tạo nhiều phương thức. Một chuỗi ngắn, tuyến tính và có mục đích rõ vẫn có thể để nguyên. Nên tách khi một đoạn có ý nghĩa nghiệp vụ độc lập, có chính sách lỗi riêng, có thể tái sử dụng hoặc cần được kiểm thử riêng. Tách quá nhỏ thành hàng chục phương thức chỉ bọc một `map` đơn giản có thể khiến người đọc phải nhảy qua nhiều file mà không hiểu thêm điều gì.

## Ví dụ: từ một chuỗi dài sang các bước có tên

Giả sử một API tạo danh sách đơn hàng đã thanh toán, lấy thông tin khách hàng và tồn kho, rồi tạo view trả về. Một chuỗi tất cả trong một biểu thức có thể trông như sau:

```java
Flux<OrderView> views = orderRepository.streamOrders()
    .filter(order -> order.status() == OrderStatus.PAID)
    .filter(order -> order.total().compareTo(minimumTotal) >= 0)
    .flatMap(order -> customerClient.findById(order.customerId())
        .zipWith(inventoryClient.findBySku(order.sku()))
        .map(tuple -> new OrderView(
            order,
            tuple.getT1(),
            tuple.getT2(),
            order.total().add(tuple.getT2().shippingCost())
        )), 12)
    .doOnNext(view -> metrics.recordCreatedView(view.order().id()));
```

Chuỗi này có thể đúng, nhưng đang trộn nhiều ý định: chọn đơn hàng hợp lệ, gọi hai dịch vụ phụ, tính phí và ghi metric. Khi thêm retry riêng cho inventory hoặc fallback cho customer, biểu thức sẽ càng khó đọc.

Có thể đặt tên cho từng giai đoạn và để phương thức điều phối chỉ thể hiện trình tự nghiệp vụ:

```java
Flux<OrderView> buildOrderViews(BigDecimal minimumTotal) {
    return orderRepository.streamOrders()
        .transform(OrderStages.paidOrders())
        .transform(OrderStages.atLeast(minimumTotal))
        .flatMap(this::enrichOrder, 12)
        .doOnNext(view -> metrics.recordCreatedView(view.order().id()));
}
```

Tên các bước cho biết pipeline đang làm gì. Phần chi tiết của từng phép biến đổi được đặt trong lớp hoặc module có trách nhiệm tương ứng:

```java
import java.math.BigDecimal;
import java.util.function.Function;
import reactor.core.publisher.Flux;

final class OrderStages {
    private OrderStages() {}

    static Function<Flux<Order>, Flux<Order>> paidOrders() {
        return orders -> orders.filter(
            order -> order.status() == OrderStatus.PAID);
    }

    static Function<Flux<Order>, Flux<Order>> atLeast(BigDecimal minimum) {
        return orders -> orders.filter(
            order -> order.total().compareTo(minimum) >= 0);
    }
}
```

`transform` nhận một hàm biến đổi publisher và áp dụng nó vào chuỗi. Ở đây, mỗi hàm trả về một `Function<Flux<Order>, Flux<Order>>`, nên phép lọc có thể được đặt tên, tái sử dụng và kiểm thử riêng. Các phương thức này không subscribe; chúng chỉ mô tả cách biến đổi nguồn.

## Đặt tên theo mục đích nghiệp vụ

Tên giai đoạn nên diễn đạt điều gì được đảm bảo sau khi bước đó chạy. Các động từ như `validate`, `select`, `enrich`, `calculate`, `authorize`, `persist`, `publish` và `mapToView` thường hữu ích nếu được kết hợp với đối tượng nghiệp vụ cụ thể.

| Tên khó hiểu | Tên diễn đạt ý định | Kết quả được kỳ vọng |
|---|---|---|
| `step1()` | `onlyPaidOrders()` | Chỉ giữ đơn hàng đã thanh toán |
| `processData()` | `enrichWithCustomer()` | Bổ sung thông tin khách hàng |
| `filter2()` | `withinCreditLimit()` | Giữ giao dịch trong hạn mức tín dụng |
| `callApi()` | `loadCurrentInventory()` | Tải tồn kho hiện tại cho SKU |
| `doWork()` | `persistOrderSummary()` | Lưu bản tóm tắt đơn hàng |
| `convert()` | `toOrderView()` | Chuyển mô hình lưu trữ thành view API |

Tên không nên hứa nhiều hơn hành vi thật. Ví dụ `validateOrder` thường gợi ý rằng dữ liệu sai sẽ phát lỗi; nếu phương thức chỉ bỏ phần tử không hợp lệ bằng `filter`, tên `onlyValidOrders` hoặc `excludeInvalidOrders` có thể chính xác hơn. Nếu một bước có thể trả `Mono.empty()`, tên và tài liệu cần làm rõ trường hợp không có kết quả.

### Một giai đoạn nên có một mục đích chính

Một phương thức có tên như `validateAndEnrichAndSave` thường cho thấy nhiều trách nhiệm đang bị gộp. Tách nó thành các giai đoạn nếu mỗi phần có chính sách lỗi, tác dụng phụ hoặc khả năng kiểm thử khác nhau. Ngược lại, không cần tách `trimAndNormalizeCode` thành hai publisher riêng nếu hai thao tác luôn tạo thành một phép biến đổi thuần, nhỏ và không có ranh giới nghiệp vụ độc lập.

Tên tốt làm lộ ra hợp đồng của giai đoạn: nó lọc, biến đổi, gọi I/O hay ghi dữ liệu; nó giữ thứ tự hay cho phép concurrency; nó có thể rỗng hay phát lỗi. Đó là thông tin hữu ích hơn một tên kỹ thuật chung như `handleFlux`.

## Dùng Function và transform để tái sử dụng chuỗi biến đổi

Khi một giai đoạn là phép biến đổi publisher thuần, có thể biểu diễn nó bằng `Function`. `transform` giúp đặt phép biến đổi vào đúng vị trí trong pipeline:

```java
import java.time.Instant;
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<Order>, Flux<Order>> paidOnly = orders ->
    orders.filter(order -> order.status() == OrderStatus.PAID);

Function<Flux<Order>, Flux<Order>> recentOnly = orders ->
    orders.filter(order -> order.createdAt().isAfter(cutoff));

Flux<Order> eligible = orderSource
    .transform(paidOnly)
    .transform(recentOnly);
```

Hai hàm có thể được đặt trong lớp `OrderStages` thay vì khai báo tại nơi sử dụng. Cách tổ chức phù hợp khi phép biến đổi được tái sử dụng ở nhiều use case hoặc cần được kiểm thử độc lập.

Có thể tạo hàm nhận tham số để cấu hình quy tắc:

```java
static Function<Flux<Order>, Flux<Order>> createdAfter(Instant cutoff) {
    return orders -> orders.filter(
        order -> order.createdAt().isAfter(cutoff));
}

Flux<Order> recentPaidOrders = orderSource
    .transform(OrderStages.paidOrders())
    .transform(OrderStages.createdAfter(cutoff));
```

Tham số như `cutoff` được capture trong hàm biến đổi. Hãy dùng giá trị bất biến hoặc bản sao an toàn; tránh capture một collection mutable dùng chung rồi sửa nó từ nhiều subscription.

## transform và transformDeferred khác nhau ở thời điểm áp dụng

`transform` áp dụng hàm biến đổi khi dựng pipeline. `transformDeferred` trì hoãn việc áp dụng hàm cho đến mỗi lần subscription. Khác biệt này quan trọng khi giai đoạn cần tạo state riêng, đọc dữ liệu theo subscription hoặc phụ thuộc vào Context.

Ví dụ sau tạo bộ đếm riêng cho mỗi subscription:

```java
import java.util.concurrent.atomic.AtomicLong;
import reactor.core.publisher.Flux;

Flux<SequencedEvent> sequenced = eventSource
    .transformDeferred(events -> {
        AtomicLong sequence = new AtomicLong();
        return events.map(event ->
            new SequencedEvent(sequence.incrementAndGet(), event));
    });
```

Mỗi subscriber đi qua `transformDeferred` sẽ tạo một `AtomicLong` mới. Nếu dùng `transform` và tạo counter trong lambda biến đổi, counter có thể được tạo một lần ở assembly rồi dùng chung qua các subscription. Điều đó chỉ phù hợp nếu bộ đếm thật sự có phạm vi chia sẻ.

Nếu cần đọc Reactor Context khi áp dụng phép biến đổi, dùng `transformDeferredContextual`:

```java
Flux<Event> visibleEvents = sharedEvents
    .transformDeferredContextual((events, context) -> {
        String tenantId = context.get("tenantId");
        return events.filter(event -> event.tenantId().equals(tenantId));
    });
```

Toán tử này tạo phép biến đổi cho từng subscriber và cung cấp `ContextView` tương ứng. Khi dùng với nguồn đã `share()`, cần đặt logic phụ thuộc subscriber ở phía downstream của ranh giới chia sẻ nếu mỗi subscriber phải áp dụng context riêng. Không đặt lựa chọn tenant ở upstream của một subscription dùng chung cho nhiều tenant.

## Chia pipeline theo kiểu dữ liệu và trách nhiệm

Một cách tách hiệu quả là đặt tên cho các giai đoạn chuyển đổi kiểu dữ liệu. Ví dụ, một đơn hàng thô có thể được xác thực, kết hợp với dữ liệu khách hàng rồi chuyển thành view:

```java
Mono<OrderView> findOrderView(String orderId) {
    return loadOrder(orderId)
        .flatMap(this::requireEligibleOrder)
        .flatMap(this::attachCustomer)
        .map(this::toOrderView);
}

Mono<Order> loadOrder(String orderId) {
    return orderRepository.findById(orderId);
}

Mono<Order> requireEligibleOrder(Order order) {
    if (order.status() != OrderStatus.PAID) {
        return Mono.error(new OrderNotEligibleException(order.id()));
    }
    return Mono.just(order);
}

Mono<OrderWithCustomer> attachCustomer(Order order) {
    return customerClient.findById(order.customerId())
        .map(customer -> new OrderWithCustomer(order, customer));
}

OrderView toOrderView(OrderWithCustomer value) {
    return new OrderView(value.order(), value.customer());
}
```

Mỗi phương thức có một hợp đồng đơn giản: `loadOrder` có thể rỗng nếu không tìm thấy; `requireEligibleOrder` phát lỗi nghiệp vụ nếu trạng thái không hợp lệ; `attachCustomer` có thể lỗi khi dịch vụ khách hàng không sẵn sàng; `toOrderView` là phép biến đổi đồng bộ thuần. Kiểu trả về làm rõ giai đoạn nào bất đồng bộ và giai đoạn nào chỉ biến đổi dữ liệu.

Nếu muốn giữ dữ liệu qua nhiều bước, dùng kiểu trung gian có tên như `OrderWithCustomer` thay vì `Tuple2` hoặc `Tuple3` ở nhiều tầng. Tuple phù hợp cho kết hợp ngắn cục bộ; kiểu domain cụ thể giúp các phương thức và thông báo lỗi dễ hiểu hơn khi pipeline lớn.

## Đặt ranh giới lỗi tại giai đoạn có chính sách rõ ràng

Việc tách chuỗi cũng giúp xác định lỗi nào được xử lý ở đâu. Một `onErrorResume` đặt cuối pipeline có thể bắt mọi lỗi từ tất cả giai đoạn trước đó. Nếu fallback chỉ có ý nghĩa với một dependency cụ thể, đặt nó ngay quanh giai đoạn gọi dependency đó.

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<Customer> loadCustomer(String customerId) {
    return customerClient.findById(customerId)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class, error ->
            customerCache.findById(customerId));
}

Mono<OrderView> buildView(Order order) {
    return loadCustomer(order.customerId())
        .flatMap(customer -> inventoryClient.findBySku(order.sku())
            .map(inventory -> toView(order, customer, inventory)));
}
```

Ở đây, cache chỉ thay thế lỗi timeout khi tải khách hàng. Lỗi tồn kho không bị biến thành lỗi cache khách hàng. Nếu đặt một `onErrorResume` chung ở cuối `buildView`, phạm vi fallback sẽ rộng hơn và có thể che giấu lỗi không liên quan.

Với `Flux`, cần phân biệt lỗi của toàn nguồn với lỗi của một phần tử. `onErrorResume` bên ngoài `flatMap` thường thay thế toàn bộ luồng sau lỗi. Nếu mỗi đơn hàng có thể thất bại độc lập và các đơn khác vẫn cần xử lý, hãy đặt phục hồi bên trong nhánh publisher con:

```java
Flux<OrderResult> results = orders.flatMap(order ->
    enrichOrder(order)
        .map(OrderResult::success)
        .onErrorResume(error -> Mono.just(OrderResult.failure(order.id(), error))),
    12
);
```

Chính sách này biến lỗi của một đơn thành kết quả lỗi có cấu trúc và cho phép các đơn khác tiếp tục. Chỉ dùng khi nghiệp vụ chấp nhận xử lý từng phần; với giao dịch cần tính nguyên tử, có thể phải để lỗi kết thúc toàn bộ pipeline.

## Side effect phải là một giai đoạn có thể kết hợp

Một pipeline dễ đọc cần làm rõ đâu là phép biến đổi thuần và đâu là side effect. `map` phù hợp để biến đổi một giá trị đồng bộ. Nếu một bước gọi database, gửi message hoặc gọi API và trả về publisher, hãy dùng `flatMap`, `concatMap` hoặc toán tử kết hợp phù hợp để giữ thao tác đó trong cùng subscription.

```java
Mono<Receipt> placeOrder(CreateOrder command) {
    return validate(command)
        .flatMap(orderRepository::save)
        .flatMap(saved -> paymentClient.authorize(saved)
            .map(payment -> new Receipt(saved, payment)))
        .flatMap(receipt -> auditClient.record(receipt)
            .thenReturn(receipt));
}
```

Các bước lưu đơn, xác thực thanh toán và ghi audit đều thuộc cùng pipeline. Nếu downstream hủy hoặc một bước phát lỗi, các bước tiếp theo không được chạy theo cách tách rời ngoài ý muốn. Tùy hợp đồng hệ thống, cần thêm transaction hoặc saga để xử lý trường hợp một side effect đã thành công trước khi bước sau thất bại.

Không viết helper kiểu sau:

```java
void saveLater(Order order) {
    orderRepository.save(order).subscribe();
}
```

`subscribe()` bên trong helper tạo một subscription độc lập. Caller không còn điều khiển được demand, lỗi hoặc cancellation của thao tác lưu. Thay vào đó, trả publisher:

```java
Mono<Order> saveOrder(Order order) {
    return orderRepository.save(order);
}
```

Tầng ứng dụng hoặc framework chịu trách nhiệm subscribe ở ranh giới ngoài cùng. Các tầng service nên trả publisher để caller quyết định cách ghép, xử lý lỗi và quản lý vòng đời.

## Đặt scheduler ở giai đoạn thực sự cần đổi cách thực thi

Tên giai đoạn cũng giúp chỉ ra đoạn nào là blocking, CPU-bound hoặc I/O non-blocking. Không nên rải `publishOn` và `subscribeOn` trong mọi helper mà không nêu rõ mục đích.

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<LegacyProfile> loadLegacyProfile(String id) {
    return Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
}

Mono<ProfileView> buildProfileView(String id) {
    return loadLegacyProfile(id)
        .map(this::normalizeProfile)
        .map(this::toProfileView);
}
```

`loadLegacyProfile` thể hiện rõ đây là nguồn blocking được cô lập trên `boundedElastic`. Những phép biến đổi thuần phía sau không cần tự thêm scheduler. Nếu một đoạn CPU nặng cần worker CPU riêng, có thể đặt `publishOn(Schedulers.parallel())` tại ranh giới trước đoạn đó và giới hạn concurrency phù hợp.

Client reactive non-blocking thường không cần đưa sang `boundedElastic`. Chuyển scheduler có chi phí và có thể làm mất lợi ích của event loop nếu dùng sai. Tên phương thức và vị trí boundary nên giúp reviewer hiểu vì sao việc chuyển thread là cần thiết.

## Tổ chức các phép biến đổi theo lớp và module

Không có một cách tổ chức duy nhất cho mọi dự án. Với ứng dụng nhỏ, các hàm thuần có thể nằm trong một lớp `OrderStages`. Với ứng dụng lớn, có thể tách theo trách nhiệm:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Application service | Điều phối các bước use case | `buildOrderViews`, `placeOrder` |
| Domain policy/stage | Quy tắc nghiệp vụ thuần | `paidOrders`, `withinCreditLimit` |
| Client/repository adapter | I/O và chuyển đổi giao thức | `loadCustomer`, `saveOrder` |
| Mapper | Chuyển mô hình domain thành DTO/view | `toOrderView` |
| Recovery policy | Timeout, retry, fallback theo dependency | `loadCustomerWithCacheFallback` |

Không tạo một lớp tiện ích toàn cục chứa mọi `Function<Flux<T>, Flux<T>>`. Hãy đặt phép biến đổi gần domain sở hữu quy tắc đó. Ví dụ, điều kiện đủ hạn mức tín dụng thuộc policy thanh toán; cách gọi endpoint tồn kho thuộc adapter inventory. Tổ chức theo trách nhiệm giúp thay đổi dependency mà không làm thay đổi quy tắc nghiệp vụ.

## Kiểm thử từng giai đoạn và pipeline tổng

Khi giai đoạn có tên và có hợp đồng rõ, có thể kiểm thử nó riêng bằng `StepVerifier`:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(
        Flux.just(paidOrder, pendingOrder)
            .transform(OrderStages.paidOrders()))
    .expectNext(paidOrder)
    .verifyComplete();
```

Test này chỉ kiểm tra quy tắc chọn đơn hàng đã thanh toán. Không cần mock HTTP client hoặc repository nếu stage là phép biến đổi thuần.

Với giai đoạn gọi I/O, mock publisher trả về các trường hợp thành công, rỗng, lỗi và timeout. Kiểm tra cả số lần gọi, concurrency nếu quan trọng và hành vi cancellation. Với pipeline tổng, viết một số integration test xác nhận các stage được ghép đúng thứ tự và lỗi/fallback không bị đặt sai phạm vi.

Không nên kiểm thử chi tiết triển khai nội bộ của một stage nếu hợp đồng quan sát được mới là điều quan trọng. Ví dụ, test `paidOrders` cần xác nhận đơn không hợp lệ bị loại; không cần xác nhận chính xác lambda `filter` được gọi bao nhiêu lần. Điều này giúp có thể tái cấu trúc hoặc thay operator mà không phải sửa hàng loạt test.

## Những dấu hiệu tách giai đoạn chưa hợp lý

- **Tên chung chung:** `process`, `handle`, `step2` không cho biết kết quả nghiệp vụ.
- **Một helper chỉ bọc một toán tử vô nghĩa:** `applyMap` hoặc `filterData` làm tăng số lần nhảy mã nhưng không thêm ngữ nghĩa.
- **Một helper làm nhiều việc:** validate, gọi ba dependency, ghi database và chuyển DTO trong một phương thức khó kiểm thử.
- **Helper tự subscribe hoặc block:** tạo luồng thực thi tách rời, làm mất khả năng điều phối lỗi và cancellation từ caller.
- **Phạm vi lỗi quá rộng:** fallback ở cuối chuỗi che lỗi của dependency khác.
- **Kiểu dữ liệu trung gian không rõ:** dùng nhiều tuple lồng nhau khiến ý nghĩa từng phần tử khó hiểu; cân nhắc kiểu domain có tên.
- **Ranh giới scheduler không có lý do:** mỗi helper tự `publishOn` khiến pipeline đổi worker nhiều lần và khó theo dõi.
- **Capture state mutable:** hàm biến đổi dùng chung collection/counter ngoài subscription mà không có đồng bộ hoặc chủ đích chia sẻ.
- **Chia stage theo số dòng thay vì trách nhiệm:** một quy tắc nghiệp vụ bị tách thành nhiều hàm nhỏ không mang ý nghĩa riêng.

## Quy trình refactor một chuỗi dài

Trước tiên, đọc pipeline hiện tại và đánh dấu từng bước theo loại công việc: lọc nghiệp vụ, biến đổi thuần, gọi I/O, side effect, recovery, đổi scheduler hoặc quan sát. Xác định kiểu đầu vào/đầu ra và hành vi lỗi/rỗng/cancellation của từng đoạn.

Tiếp theo, gom các bước có cùng mục đích thành phép biến đổi có tên. Dùng phương thức trả `Mono`/`Flux` cho thao tác bất đồng bộ; dùng `Function` kết hợp `transform` cho stage tái sử dụng; dùng `transformDeferred` khi cần tạo state theo subscription. Đặt retry, timeout và fallback gần dependency mà chúng bảo vệ. Giữ side effect trong cùng pipeline và chỉ thêm scheduler boundary khi có yêu cầu thực thi cụ thể.

Cuối cùng, kiểm thử stage thuần độc lập, kiểm thử adapter I/O với các tín hiệu success/empty/error/cancel và kiểm thử một số đường đi end-to-end. Tên giai đoạn nên giúp người đọc hiểu mục đích mà không cần mở mọi helper; phần điều phối cấp cao nên đọc gần giống trình tự nghiệp vụ. Một pipeline được chia đúng cách vừa dễ bảo trì, vừa giữ được demand, cancellation và chính sách lỗi của Reactive Streams xuyên suốt ứng dụng.
