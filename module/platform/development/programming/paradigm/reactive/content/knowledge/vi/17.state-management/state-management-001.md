# Hàm thuần, dữ liệu bất biến và khả năng suy luận chuỗi xử lý

Một pipeline reactive có thể xử lý nhiều sự kiện trên các thread khác nhau, nối các thao tác bất đồng bộ và tiếp tục chạy trong khi trạng thái ứng dụng thay đổi. Nếu mỗi bước tùy ý sửa dữ liệu dùng chung hoặc tạo tác dụng phụ khó quan sát, việc xác định kết quả của pipeline trở nên khó khăn: cùng một đầu vào có thể cho kết quả khác nhau tùy thời điểm, thứ tự thread hoặc lần subscribe.

Hàm thuần và dữ liệu bất biến giúp giảm sự phụ thuộc ẩn đó. Hàm thuần cho cùng một đầu vào luôn cho cùng một đầu ra và không thay đổi trạng thái bên ngoài. Dữ liệu bất biến không bị sửa sau khi tạo; muốn biểu diễn trạng thái mới, chương trình tạo một giá trị mới. Khi kết hợp hai nguyên tắc này với `map`, `filter`, `scan`, `flatMap` và các publisher của Reactor, mỗi bước trong chuỗi xử lý có đầu vào và đầu ra rõ ràng hơn, dễ kiểm thử và dễ suy luận hơn.

## 1. Hàm thuần có hai đặc tính cốt lõi

Một hàm được xem là thuần khi:

1. **Kết quả chỉ phụ thuộc vào đối số:** gọi hàm nhiều lần với cùng đầu vào sẽ nhận cùng kết quả.
2. **Không có tác dụng phụ quan sát được:** hàm không sửa biến toàn cục, không ghi file, không gửi request, không cập nhật database, không thay đổi đối tượng đầu vào hoặc trạng thái dùng chung.

Ví dụ một hàm thuần tính tổng tiền sau giảm giá:

```java
static BigDecimal discountedPrice(BigDecimal price, BigDecimal rate) {
    return price.multiply(BigDecimal.ONE.subtract(rate));
}
```

Với cùng `price` và `rate`, hàm luôn tính ra cùng kết quả. Hàm không cần biết database, thời gian hệ thống, cấu hình toàn cục hay trạng thái của thread hiện tại.

Ngược lại, hàm sau không thuần:

```java
private static BigDecimal lastPrice;

static BigDecimal calculateAndRemember(BigDecimal price) {
    lastPrice = price;
    return price.multiply(new BigDecimal("0.9"));
}
```

Hàm này sửa biến tĩnh `lastPrice`. Lời gọi có thể ảnh hưởng tới code khác và kết quả quan sát được phụ thuộc thứ tự gọi giữa các thread. Một hàm đọc thời gian hệ thống, sinh số ngẫu nhiên hoặc gọi dịch vụ ngoài cũng không thuần nếu kết quả không chỉ phụ thuộc đối số.

## 2. Tính bất biến làm rõ quyền sở hữu dữ liệu

Đối tượng mutable có thể bị sửa sau khi được truyền qua nhiều tầng. Nếu hai phần của pipeline cùng giữ một tham chiếu, một bên sửa đối tượng có thể làm bên kia nhìn thấy trạng thái mới mà không có tín hiệu nào thể hiện thay đổi đó.

```java
class MutableOrder {
    private String status;

    void setStatus(String status) {
        this.status = status;
    }
}
```

Giả sử một pipeline phát `MutableOrder` cho hai subscriber. Một subscriber gọi `setStatus("PAID")`; subscriber còn lại có thể quan sát trạng thái đã đổi dù nó không thực hiện thao tác đó. Nếu các subscriber xử lý trên nhiều thread, việc đọc và ghi đồng thời còn có thể tạo race condition.

Với dữ liệu bất biến, trạng thái mới được biểu diễn bằng một đối tượng mới:

```java
record Order(String id, String status, BigDecimal total) {
    Order withStatus(String newStatus) {
        return new Order(id, newStatus, total);
    }
}

Order pending = new Order("ORD-42", "PENDING", new BigDecimal("120.00"));
Order paid = pending.withStatus("PAID");
```

`pending` vẫn giữ trạng thái `PENDING`; `paid` là một giá trị khác mang trạng thái `PAID`. Không có bước nào âm thầm sửa dữ liệu mà subscriber khác đang giữ.

`record` tạo các field final và cung cấp accessor, `equals`, `hashCode` cùng `toString`, nhưng tính bất biến chỉ ở mức nông. Nếu một field tham chiếu tới `List`, `Map` hoặc đối tượng mutable khác, nội dung bên trong vẫn có thể bị thay đổi. Hãy sao chép dữ liệu mutable khi tạo đối tượng và chỉ công khai các cấu trúc không thể sửa:

```java
record OrderSnapshot(String id, List<String> itemIds) {
    OrderSnapshot {
        itemIds = List.copyOf(itemIds);
    }
}
```

`List.copyOf` tạo danh sách không thể sửa thông qua tham chiếu trả về. Nếu phần tử trong danh sách cũng mutable, cần bảo đảm chúng bất biến hoặc sao chép sâu theo yêu cầu của miền dữ liệu.

## 3. Referential transparency giúp suy luận bằng thay thế

Một biểu thức có tính *referential transparency* nếu có thể thay biểu thức đó bằng giá trị kết quả của nó mà không làm thay đổi hành vi chương trình. Hàm thuần trên dữ liệu bất biến thường có tính chất này.

Ví dụ:

```java
BigDecimal total = discountedPrice(new BigDecimal("100"), new BigDecimal("0.1"));
```

Vì đầu vào cố định và hàm thuần, có thể suy luận biểu thức tương đương với giá trị `90`. Việc đọc code không cần xét tới trạng thái ẩn hoặc thời điểm gọi.

Trong pipeline reactive, điều này làm cho từng phép biến đổi dễ hiểu hơn:

```java
Mono<OrderView> view = orderRepository.findById(orderId)
    .map(order -> order.withStatus("REVIEWED"))
    .map(orderMapper::toView);
```

Nếu `withStatus` và `toView` là các hàm thuần, mỗi bước chỉ biến đổi giá trị nhận được. Chúng không sửa đối tượng nguồn và không phụ thuộc vào trạng thái bên ngoài. Khi cần kiểm tra kết quả, có thể gọi trực tiếp các hàm đó trong unit test mà không cần khởi tạo Reactor hoặc mock database.

Tính thuần không đồng nghĩa với tính lười (lazy) hay bất đồng bộ. Một hàm thuần có thể chạy ngay và một publisher lazy vẫn có thể thực hiện tác dụng phụ khi subscribe. Đây là hai khía cạnh khác nhau: purity nói về quan hệ đầu vào/đầu ra và tác dụng phụ; laziness nói về thời điểm thực thi.

## 4. map và filter là nơi phù hợp cho phép biến đổi thuần

`map` biến đổi từng payload. `filter` quyết định giữ hay bỏ phần tử dựa trên predicate. Khi hàm truyền vào là hàm thuần, ý nghĩa của pipeline dễ đọc và kết quả không phụ thuộc thứ tự thực thi giữa các thread:

```java
Flux<OrderView> visibleOrders = orderRepository.findAll()
    .filter(Order::isVisible)
    .map(orderMapper::toView);
```

Ở đây, `isVisible` và `toView` nên chỉ đọc dữ liệu và trả kết quả. Nếu mapper sửa đối tượng gốc, subscriber khác có thể nhận dữ liệu đã bị thay đổi. Nếu predicate đọc một biến cấu hình mutable, cùng một phần tử có thể được giữ hoặc loại tùy thời điểm đánh giá.

Khi cần cấu hình thay đổi, hãy đưa giá trị cấu hình vào đầu vào một cách rõ ràng hoặc tạo một snapshot bất biến cho lần xử lý:

```java
record VisibilityPolicy(Set<String> allowedStatuses) {
    VisibilityPolicy {
        allowedStatuses = Set.copyOf(allowedStatuses);
    }

    boolean allows(Order order) {
        return allowedStatuses.contains(order.status());
    }
}

VisibilityPolicy policy = new VisibilityPolicy(Set.of("PAID", "SHIPPED"));

Flux<Order> visible = orders.filter(policy::allows);
```

Pipeline sử dụng một policy snapshot có thể được kiểm thử và suy luận độc lập. Nếu muốn cập nhật policy, tạo policy mới và xác định rõ subscription nào sử dụng phiên bản nào.

## 5. Tác dụng phụ nên nằm ở ranh giới có chủ đích

Ứng dụng thực tế vẫn cần đọc database, gửi thông báo, ghi log hoặc cập nhật hệ thống bên ngoài. Mục tiêu không phải loại bỏ mọi tác dụng phụ mà là đặt chúng ở ranh giới dễ nhận biết, để phần biến đổi dữ liệu ở giữa giữ được tính thuần.

Ví dụ, service có thể đọc dữ liệu, biến đổi thuần, rồi ghi kết quả:

```java
Mono<OrderView> updateOrder(String orderId) {
    return orderRepository.findById(orderId)
        .map(order -> order.withStatus("REVIEWED"))
        .flatMap(orderRepository::save)
        .map(orderMapper::toView);
}
```

`map` đầu tiên tạo một giá trị mới. `flatMap` nối thao tác lưu bất đồng bộ. Mapper cuối tạo view. Tác dụng phụ lưu database được thể hiện bằng một publisher riêng và lỗi của nó được truyền xuống caller.

Các hook như `doOnNext`, `doOnSuccess` và `doOnError` phù hợp cho quan sát như log hoặc metric:

```java
Mono<Order> order = orderRepository.findById(orderId)
    .doOnNext(value -> metrics.recordOrderRead(value.id()))
    .doOnError(error -> log.warn("Không tải được đơn hàng {}", orderId, error));
```

Hook `doOn...` vẫn là nơi thực hiện tác dụng phụ. Dùng nó cho quan sát nhỏ, không dùng để giấu một quy trình nghiệp vụ bất đồng bộ cần được chờ. Nếu cần gửi thông báo và chỉ hoàn tất khi gửi xong, hãy compose publisher bằng `flatMap` hoặc `then`, không gọi `subscribe()` bên trong hook.

## 6. Dữ liệu bất biến giúp xử lý đồng thời an toàn hơn

Reactive pipeline có thể chạy các nhánh trên nhiều thread, đặc biệt khi dùng `flatMap`, `publishOn` hoặc các nguồn bất đồng bộ. Nếu nhiều nhánh cùng sửa một đối tượng mutable, kết quả có thể phụ thuộc lịch chạy:

```java
// Rủi ro: nhiều nhánh cùng sửa một đối tượng dùng chung.
AtomicOrder shared = new AtomicOrder(orderId);

Flux<Update> updates = updateSources.flatMap(source ->
    source.load().doOnNext(shared::apply)
);
```

`AtomicOrder` có thể cần khóa hoặc cơ chế đồng bộ để bảo vệ state. Ngay cả khi không có data race, thứ tự áp dụng các update vẫn có thể không xác định.

Một hướng khác là mỗi nhánh tạo giá trị mới và kết hợp kết quả sau đó:

```java
Flux<OrderUpdate> updates = updateSources.flatMap(source ->
    source.load().map(OrderUpdate::from)
);
```

Mỗi nhánh chỉ tạo `OrderUpdate` bất biến. Tầng tổng hợp quyết định cách kết hợp chúng, ví dụ sắp xếp theo sequence number rồi áp dụng vào một snapshot mới. Việc hợp nhất state trở thành một phép biến đổi rõ ràng thay vì một loạt mutation cạnh tranh.

Lưu ý: bất biến làm giảm nhu cầu khóa khi chia sẻ dữ liệu đọc, nhưng không tự giải quyết xung đột nghiệp vụ. Hai cập nhật cùng thay đổi một trường vẫn cần quy tắc ưu tiên, versioning hoặc optimistic locking. Tính bất biến giúp nhìn thấy xung đột và xử lý nó tại một bước tổng hợp có chủ đích.

## 7. scan và reduce với accumulator bất biến

`scan` phát ra các trạng thái tích lũy sau từng phần tử; `reduce` chỉ phát trạng thái cuối khi nguồn hoàn tất. Khi accumulator tạo state mới thay vì sửa state cũ, chuỗi chuyển trạng thái có thể được kiểm tra từng bước:

```java
record CartState(List<CartItem> items, BigDecimal total) {
    CartState {
        items = List.copyOf(items);
    }

    CartState add(CartItem item) {
        List<CartItem> nextItems = new ArrayList<>(items);
        nextItems.add(item);
        return new CartState(
            nextItems,
            total.add(item.price().multiply(BigDecimal.valueOf(item.quantity())))
        );
    }
}

CartState initial = new CartState(List.of(), BigDecimal.ZERO);

Flux<CartState> states = cartEvents
    .scan(initial, CartState::add);
```

Mỗi `CartState` là một snapshot mới. Subscriber có thể giữ snapshot trước đó mà không lo nó bị thay đổi khi sự kiện tiếp theo đến. Với `reduce`, có thể tính trạng thái cuối:

```java
Mono<CartState> finalState = cartEvents
    .reduce(initial, CartState::add);
```

Accumulator nên thuần và không sửa `initial` hoặc accumulator trước đó. Nếu mutate một `ArrayList` dùng chung trong accumulator, các snapshot được phát từ `scan` có thể cùng tham chiếu tới một list đang thay đổi, làm mất ý nghĩa của việc phát trạng thái theo thời gian.

## 8. Không nhầm immutable state với state không bao giờ thay đổi

Một ứng dụng quản lý trạng thái vẫn cần cập nhật state. Tính bất biến chỉ yêu cầu mỗi phiên bản state không bị sửa sau khi được tạo. State mới được tạo từ state cũ và sự kiện mới:

```java
record AccountState(BigDecimal balance, long version) {
    AccountState apply(Deposit deposit) {
        return new AccountState(
            balance.add(deposit.amount()),
            version + 1
        );
    }
}
```

Chuỗi sự kiện có thể được fold qua state:

```java
Mono<AccountState> currentState = deposits
    .reduce(initialState, AccountState::apply);
```

Điều cần chú ý là thứ tự sự kiện. Nếu nguồn có thể phát đồng thời hoặc merge từ nhiều partition, thứ tự đến downstream có thể khác thứ tự nghiệp vụ. Khi thứ tự ảnh hưởng kết quả, cần sequence number, timestamp có quy tắc rõ hoặc partition key để đảm bảo các sự kiện của cùng aggregate được xử lý theo thứ tự.

Không nên lưu state mới vào một biến toàn cục từ bên trong `map` hoặc `scan`. Hãy trả state mới trong publisher và để một ranh giới sở hữu state quyết định cách công bố snapshot mới. Với nhiều subscriber, có thể dùng một store hoặc sink được thiết kế để quản lý cập nhật và đồng bộ; không biến mọi toán tử thành nơi tự sửa state dùng chung.

## 9. Clock, random và cấu hình cần được đưa thành đầu vào

Một hàm gắn timestamp bằng `Instant.now()` hoặc sinh mã ngẫu nhiên trực tiếp không còn thuần vì kết quả thay đổi theo môi trường và thời điểm. Để kiểm thử và suy luận, hãy đưa nguồn thời gian hoặc bộ sinh giá trị vào như dependency:

```java
static OrderSnapshot markReviewed(OrderSnapshot order, Instant reviewedAt) {
    return new OrderSnapshot(order.id(), order.items(), reviewedAt);
}

Mono<OrderSnapshot> review(OrderSnapshot order, Clock clock) {
    return Mono.fromSupplier(() -> markReviewed(order, clock.instant()));
}
```

Hàm `markReviewed` thuần vì `reviewedAt` là đầu vào tường minh. Việc đọc clock được đặt ở ranh giới và có thể thay bằng `Clock.fixed(...)` trong test. Cách tương tự áp dụng cho random generator, cấu hình và user context: lấy giá trị tại ranh giới rồi truyền snapshot cần thiết vào hàm biến đổi.

Đưa dependency vào đầu vào không làm mọi dependency trở thành dữ liệu bất biến. Nó làm rõ nơi lấy giá trị và cho phép test thay thế bằng implementation xác định. Nếu dependency có trạng thái nội bộ, cần quản lý thread safety và lifecycle riêng.

## 10. Kiểm thử hàm thuần và pipeline reactive

Hàm thuần có thể kiểm thử bằng unit test thông thường, không cần khởi chạy scheduler hoặc mock framework:

```java
@Test
void withStatusCreatesNewOrderWithoutChangingOriginal() {
    Order original = new Order("ORD-42", "PENDING", new BigDecimal("120.00"));

    Order updated = original.withStatus("PAID");

    assertEquals("PENDING", original.status());
    assertEquals("PAID", updated.status());
    assertNotSame(original, updated);
}
```

Với pipeline, `StepVerifier` xác minh chuỗi tín hiệu và giá trị được tạo:

```java
StepVerifier.create(
        Flux.just(
            new Order("A", "PENDING", BigDecimal.TEN),
            new Order("B", "PAID", BigDecimal.ONE)
        )
        .filter(order -> order.status().equals("PAID"))
        .map(order -> order.withStatus("REVIEWED"))
    )
    .assertNext(order -> {
        assertEquals("B", order.id());
        assertEquals("REVIEWED", order.status());
    })
    .verifyComplete();
```

Khi test state accumulation, kiểm tra cả snapshot trước và sau để bảo đảm accumulator không mutate state cũ. Khi test nhánh bất đồng bộ, dùng publisher giả lập hoặc `TestPublisher` để điều khiển thời điểm phát và lỗi. Tránh dựa vào thời gian hệ thống hoặc thread scheduling không xác định nếu không phải nội dung đang được kiểm thử.

## 11. Dấu hiệu pipeline khó suy luận

Một pipeline thường khó đọc hoặc dễ lỗi khi có các dấu hiệu sau:

- `map` hoặc `filter` sửa đối tượng đầu vào thay vì tạo giá trị mới.
- Callback thay đổi biến ngoài pipeline hoặc một collection được chia sẻ.
- Kết quả phụ thuộc `Instant.now()`, random hoặc cấu hình toàn cục được đọc ở nhiều vị trí.
- Nhiều nhánh `flatMap` cùng cập nhật một state mutable.
- `doOnNext` chứa logic nghiệp vụ hoặc gọi `subscribe()` cho một công việc khác.
- Accumulator của `scan`/`reduce` tái sử dụng một đối tượng mutable làm các snapshot cũ thay đổi theo.

Khi gặp những trường hợp đó, hãy xác định tác dụng phụ thuộc về thành phần nào, đưa dependency thành đầu vào rõ ràng, tạo snapshot bất biến và compose publisher của thao tác I/O ở ranh giới phù hợp. Nếu state thật sự cần cập nhật dùng chung, gom quyền sở hữu state vào một component có hợp đồng đồng bộ và thứ tự cập nhật rõ ràng.

## 12. Áp dụng vào thiết kế pipeline reactive

Trong một pipeline Java reactive, hãy cố gắng giữ phần lớn bước xử lý ở dạng hàm thuần trên dữ liệu bất biến: `map` để chuyển đổi, `filter` để chọn phần tử, `scan` hoặc `reduce` để tính state mới. Đặt I/O và tác dụng phụ tại các ranh giới có thể quan sát, trả publisher để caller quản lý subscription, lỗi và cancellation. Khi cần trạng thái dùng chung, phát các phiên bản bất biến và xác định rõ thành phần chịu trách nhiệm công bố phiên bản tiếp theo.

Hàm thuần giúp biết một bước sẽ trả gì từ đầu vào của nó. Dữ liệu bất biến giúp biết một giá trị đã phát sẽ không bị thay đổi âm thầm sau đó. Kết hợp hai đặc tính này làm giảm phụ thuộc vào thứ tự thread và trạng thái ẩn, từ đó giúp chuỗi xử lý bất đồng bộ dễ kiểm thử, dễ gỡ lỗi và dễ mở rộng hơn trong Project Reactor và hệ sinh thái Reactive Streams.
