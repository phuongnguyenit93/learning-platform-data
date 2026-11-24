# Quan hệ và khác biệt giữa FRP cổ điển với thư viện luồng sự kiện

Trong chương **Phản ứng hàm** của module `REACTIVE_PROGRAMMING`, ta học cách mô hình hóa các luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Các thư viện như Reactor và RxJava giúp xây dựng ứng dụng phản ứng bằng những chuỗi dữ liệu bất đồng bộ. Tuy nhiên, chúng không đồng nghĩa với mọi mô hình **Functional Reactive Programming (FRP)** cổ điển.

FRP cổ điển tập trung vào cách biểu diễn giá trị thay đổi theo thời gian và các sự kiện xảy ra tại những thời điểm cụ thể. Các thư viện luồng sự kiện hiện đại tập trung nhiều hơn vào việc vận chuyển, biến đổi và tiêu thụ các phần tử bất đồng bộ qua một pipeline. Hai hướng tiếp cận có chung tư tưởng khai báo phép biến đổi và kết hợp các luồng, nhưng khác nhau về mô hình thời gian, ngữ nghĩa trạng thái, đồng bộ hóa, điều phối và kiểm soát tốc độ tiêu thụ.

Hiểu ranh giới này giúp chọn đúng công cụ: dùng stream khi cần xử lý chuỗi sự kiện, dùng mô hình trạng thái khi cần giá trị hiện tại nhất quán, và kết hợp cả hai khi ứng dụng cần vừa phản ứng với sự kiện vừa duy trì trạng thái dẫn xuất.

## 1. FRP cổ điển mô hình hóa giá trị theo thời gian

Trong các cách trình bày FRP cổ điển, hai khái niệm trung tâm thường là **Behavior** và **Event**:

- **Behavior** biểu diễn một giá trị thay đổi theo thời gian. Có thể mô hình hóa khái niệm này như một hàm từ thời gian đến giá trị: `B(t)`. Ví dụ: nhiệt độ hiện tại, vị trí con trỏ hoặc âm lượng hiện tại.
- **Event** biểu diễn những lần xảy ra rời rạc tại các thời điểm cụ thể. Ví dụ: nhấn nút, nhận một thông điệp hoặc cảm biến báo một thay đổi.

Giả sử nhiệt độ phòng thay đổi theo thời gian. Behavior `temperature` cho biết nhiệt độ tại một thời điểm bất kỳ. Event `temperatureAlert` chỉ xuất hiện khi nhiệt độ vượt một ngưỡng. Behavior có thể tồn tại và được lấy mẫu ngay cả khi không có sự kiện mới; Event chỉ có giá trị tại những lần xảy ra.

```text
Thời gian:       t0       t1       t2       t3       t4
Event:                    báo 27             báo 31
Behavior:       25       27       27       31       31
```

Sơ đồ này minh họa một Behavior dạng giữ giá trị gần nhất: giữa hai lần cập nhật, giá trị vẫn được xem là hiện hành. Nó không có nghĩa mọi implementation FRP đều lưu dữ liệu theo cách này. Một số hệ thống biểu diễn Behavior bằng hàm lấy mẫu; một số hệ thống dùng graph phụ thuộc và cơ chế cập nhật theo thời gian.

Trong FRP, phép kết hợp có thể được mô tả trên chính giá trị theo thời gian. Nếu `temperature` và `humidity` là hai Behavior, một Behavior dẫn xuất `comfort` có thể được định nghĩa từ hai giá trị tại cùng thời điểm:

\[
comfort(t) = f(temperature(t), humidity(t))
\]

Ý tưởng quan trọng là biểu thức mô tả quan hệ giữa các giá trị, còn hệ thống FRP chịu trách nhiệm duy trì quan hệ đó khi đầu vào thay đổi.

## 2. Thư viện luồng sự kiện hiện đại mô hình hóa chuỗi tín hiệu

Trong Reactor và RxJava, dữ liệu thường được biểu diễn bằng Publisher như `Flux<T>` hoặc `Mono<T>`. Publisher phát các tín hiệu `onNext`, rồi kết thúc bằng `onComplete` hoặc `onError`. Một `Flux<T>` có thể phát không, một hoặc nhiều phần tử; `Mono<T>` phát tối đa một phần tử.

```java
Flux<TemperatureReading> readings = sensor.readings();

Flux<TemperatureReading> alerts = readings
    .filter(reading -> reading.celsius() >= 30);
```

`readings` là một chuỗi phần tử. `filter` tạo một Publisher khác chỉ phát những phần tử thỏa điều kiện. Pipeline mô tả cách biến đổi sự kiện được phát, không mặc nhiên tạo một Behavior có thể được lấy mẫu tại mọi thời điểm.

Một thư viện stream có thể cung cấp các toán tử như `map`, `filter`, `scan`, `combineLatest`, `sample`, `window` hoặc `buffer`. Những toán tử này hỗ trợ nhiều cách xây dựng trạng thái và xử lý theo thời gian, nhưng ngữ nghĩa cụ thể vẫn dựa trên tín hiệu, subscription, scheduler và chính sách của thư viện.

| Khía cạnh | FRP cổ điển | Thư viện luồng sự kiện hiện đại |
|---|---|---|
| Đối tượng mô hình hóa | Behavior và Event | Publisher/Observable, phần tử và tín hiệu |
| Thời gian | Giá trị được hiểu theo thời gian; Event xảy ra tại thời điểm | Chuỗi tín hiệu được phát theo thứ tự và lịch thực thi |
| Trạng thái hiện tại | Behavior là khái niệm cốt lõi trong nhiều mô hình | Thường được xây dựng từ `scan`, replay, cache hoặc state holder |
| Kết hợp dữ liệu | Quan hệ giữa các giá trị theo thời gian | Toán tử kết hợp các chuỗi tín hiệu theo quy tắc phát |
| Đồng bộ hóa | Một số hệ thống có ngữ nghĩa cập nhật nhất quán, tránh trạng thái trung gian | Phụ thuộc operator, scheduler, queue và subscription |
| Điều tiết tốc độ | Tùy mô hình và implementation | Reactive Streams có demand/backpressure; Observable không có demand |
| Kết thúc | Behavior có thể được xem là tồn tại theo miền thời gian của ứng dụng | Subscription có thể hoàn tất hoặc lỗi rõ ràng |

Không nên xem bảng này là ranh giới tuyệt đối. FRP có nhiều dòng nghiên cứu và implementation; thư viện stream cũng có thể cung cấp abstraction trạng thái. Bảng nêu khác biệt thường gặp giữa mô hình Behavior/Event và pipeline Publisher/Subscriber.

## 3. Tư tưởng chung: khai báo quan hệ thay vì điều khiển từng bước

FRP và thư viện stream đều khuyến khích mô tả phép biến đổi bằng hàm và toán tử. Thay vì viết vòng lặp, biến tạm và callback lồng nhau, ta mô tả dữ liệu đầu vào được biến đổi như thế nào.

Ví dụ với stream:

```java
Flux<OrderTotal> totals = orders
    .filter(Order::isPaid)
    .map(order -> new OrderTotal(order.id(), order.amount()));
```

Ví dụ với trạng thái tích lũy:

```java
record CartState(List<CartItem> items, BigDecimal total) {
    CartState add(CartItem item) {
        List<CartItem> nextItems = new ArrayList<>(items);
        nextItems.add(item);
        return new CartState(
            List.copyOf(nextItems),
            total.add(item.price())
        );
    }
}

Flux<CartState> cartStates = cartEvents
    .scan(initialCartState, (state, event) ->
        event instanceof ItemAdded added
            ? state.add(added.item())
            : state
    );
```

Trong ví dụ thứ hai, `scan` biến chuỗi event thành chuỗi snapshot trạng thái. Mỗi event tạo một phiên bản trạng thái mới. Đây là cách dùng stream để mô phỏng một phần ý tưởng Behavior, nhưng `Flux<CartState>` vẫn là chuỗi snapshot phát theo subscription; nó không tự trở thành một kiểu Behavior cổ điển có ngữ nghĩa thời gian độc lập.

Hàm cập nhật trạng thái nên thuần khi có thể: cùng trạng thái và cùng event tạo cùng trạng thái mới. Side effect như ghi database, gửi thông báo hoặc gọi API nên được đặt ở bước có chủ đích để có thể kiểm soát retry, lỗi và tính lũy đẳng.

## 4. Khác biệt về thời gian: liên tục, rời rạc và thời điểm xử lý

Một Behavior trong mô hình FRP thường được hiểu là giá trị theo thời gian, không chỉ là danh sách các giá trị được phát khi có cập nhật. Trong một pipeline Reactor, phần tử có thời điểm được phát và được xử lý trên scheduler. Hai thời điểm đó có thể khác với thời điểm sự kiện thực sự xảy ra ở nguồn.

Khi xử lý event từ mạng hoặc message broker, nên phân biệt:

- **Event time**: thời điểm sự kiện xảy ra ở nguồn và được ghi trong payload.
- **Processing time**: thời điểm ứng dụng nhận hoặc xử lý sự kiện.
- **Emission time**: thời điểm Publisher phát tín hiệu downstream; thời điểm này có thể bị ảnh hưởng bởi queue và scheduler.

Ví dụ, cảm biến ghi nhận nhiệt độ lúc 10:00:00 nhưng mạng chỉ chuyển bản tin đến ứng dụng lúc 10:00:03. Nếu pipeline cập nhật trạng thái theo thứ tự nhận, một bản tin cũ có thể ghi đè trạng thái mới hơn. Nếu nghiệp vụ cần trạng thái theo event time, cần kiểm tra timestamp hoặc sequence number, xử lý sự kiện đến muộn và xác định giới hạn trễ chấp nhận được.

Các toán tử `window(Duration)` hoặc `buffer(Duration)` nhóm theo thời gian xử lý của scheduler mà operator sử dụng, trừ khi thư viện hoặc API được cấu hình rõ ràng để dựa trên event time. Không nên mặc định một cửa sổ thời gian trong Reactor tương đương với cửa sổ event-time trong hệ thống xử lý stream phân tán.

## 5. Glitch và tính nhất quán khi kết hợp nhiều giá trị

Một vấn đề được quan tâm trong nhiều mô hình FRP là **glitch**: thành phần quan sát trạng thái kết hợp có thể tạm thời nhìn thấy một tổ hợp giá trị trung gian không nhất quán trong lúc nhiều nguồn phụ thuộc đang cập nhật.

Giả sử `total` được tính từ `price` và `quantity`:

\[
total = price \times quantity
\]

Khi cả `price` và `quantity` cùng thay đổi trong một thao tác nghiệp vụ, hệ thống có thể cần bảo đảm observer chỉ thấy cặp giá trị mới hoàn chỉnh. Nếu observer nhận cập nhật `price` mới trước nhưng `quantity` vẫn cũ, nó có thể tạm tính ra một `total` không thuộc trạng thái nghiệp vụ nào.

Một số implementation FRP dùng graph phụ thuộc và cơ chế cập nhật theo transaction/tick để tránh phát trạng thái trung gian như vậy. Không phải mọi thư viện được gọi là FRP đều có cùng bảo đảm; cần đọc ngữ nghĩa cập nhật của implementation.

Trong Reactor, `combineLatest` kết hợp giá trị mới nhất đã nhận từ mỗi Publisher:

```java
Flux<Price> prices = priceUpdates;
Flux<Quantity> quantities = quantityUpdates;

Flux<Total> totals = Flux.combineLatest(
    prices,
    quantities,
    (price, quantity) -> new Total(
        price.value().multiply(BigDecimal.valueOf(quantity.value()))
    )
);
```

`combineLatest` phát sau khi mỗi nguồn đã phát ít nhất một giá trị, rồi phát kết quả mỗi khi một nguồn cập nhật. Nếu `price` và `quantity` được phát riêng biệt, downstream có thể nhận kết quả trung gian giữa hai lần phát. `combineLatest` không tự hiểu rằng hai tín hiệu thuộc cùng một giao dịch logic.

Nếu hai giá trị phải được quan sát như một đơn vị nhất quán, hãy phát chúng trong cùng một object snapshot hoặc dùng một event tổng hợp:

```java
record PriceQuantity(BigDecimal price, int quantity) {}

Flux<Total> totals = priceQuantityUpdates
    .map(snapshot -> new Total(
        snapshot.price().multiply(BigDecimal.valueOf(snapshot.quantity()))
    ));
```

Trong cách này, mỗi phần tử đầu vào đã chứa một cặp giá trị nhất quán. Việc thiết kế ranh giới cập nhật thường quan trọng hơn việc chỉ chọn một toán tử kết hợp.

## 6. State switching và thay đổi nguồn theo thời gian

FRP thường cần mô tả quan hệ động: một Behavior có thể chuyển sang phụ thuộc vào nguồn khác khi một sự kiện xảy ra. Các thư viện stream hỗ trợ một phần hành vi này bằng các toán tử như `switchMap` hoặc `switchOnNext`.

Ví dụ giao diện tìm kiếm: mỗi truy vấn mới tạo một request; kết quả của truy vấn cũ không còn cần thiết sau khi người dùng nhập nội dung mới.

```java
Flux<SearchResult> results = searchTerms
    .debounce(Duration.ofMillis(250))
    .distinctUntilChanged()
    .switchMap(term -> searchClient.search(term));
```

`switchMap` chuyển sang Publisher con mới khi có truy vấn mới và hủy subscription của Publisher con trước đó. Đây là một cách biểu diễn việc thay đổi nguồn hoạt động theo sự kiện. Nó không đồng nghĩa với mọi phép chuyển đổi Behavior trong FRP cổ điển; cancellation của request cũ cũng chỉ có hiệu lực đến mức API bên dưới hỗ trợ hủy.

Nếu mỗi request cũ vẫn cần hoàn tất và xử lý kết quả, `switchMap` không phù hợp. Khi đó có thể cân nhắc `flatMap` hoặc `concatMap` tùy yêu cầu concurrency và thứ tự.

## 7. Backpressure là điểm mạnh riêng của Reactive Streams

Một khác biệt quan trọng của Reactive Streams là demand được biểu diễn tường minh qua `Subscription.request(n)`. Subscriber có thể yêu cầu số phần tử muốn nhận, và Publisher tuân thủ hợp đồng không phát `onNext` vượt quá demand đã cấp.

Reactor `Flux` và RxJava `Flowable` triển khai mô hình này. Khi downstream xử lý chậm, demand có thể truyền ngược về upstream; các operator có thể dùng prefetch, buffer hoặc chính sách overflow để phối hợp tốc độ.

```java
Flux<Integer> values = Flux.range(1, 5)
    .limitRate(2);
```

`limitRate` điều tiết các request được gửi ngược upstream thành những đợt nhỏ hơn. Nó hữu ích khi nguồn tuân thủ backpressure. Một nguồn nóng không tuân thủ demand cần chính sách buffer/drop hoặc adapter riêng.

Không nên kết luận rằng FRP cổ điển không có điều tiết tốc độ. Các implementation FRP có thể dùng pull, sampling, transaction hoặc cơ chế riêng để kiểm soát tính toán. Điểm khác là backpressure của Reactive Streams có một giao thức demand chuẩn hóa giữa Publisher và Subscriber, còn đây không phải thuộc tính bắt buộc của mọi mô hình FRP.

## 8. Scheduler và thời điểm tính toán

Trong thư viện stream, scheduler là một phần rõ ràng của mô hình thực thi. Reactor dùng `subscribeOn` để điều khiển nơi subscription vào upstream bắt đầu và `publishOn` để chuyển tín hiệu downstream sang scheduler khác.

```java
Mono<Report> report = Mono.fromCallable(
        () -> blockingRepository.loadReport(reportId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::calculateSummary);
```

Tác vụ repository blocking chạy trên `boundedElastic`; phép tính sau `publishOn` chạy trên worker của `parallel`. Các ranh giới này ảnh hưởng thời điểm callback được thực thi và thứ tự quan sát tín hiệu. Chúng không thay đổi bản chất dữ liệu thành Behavior hay bảo đảm đồng bộ cập nhật nhiều nguồn.

Một số hệ thống FRP cổ điển cung cấp ngữ nghĩa cập nhật theo thời điểm logic hoặc transaction. Vì vậy, khi chuyển một mô hình từ FRP sang Reactor, cần chủ động quyết định nơi đặt ranh giới scheduler, cách ghép snapshot và cách xử lý cập nhật đồng thời.

## 9. Dùng Reactor để xây dựng một projection trạng thái

Một cách thực tế để kết hợp hai tư tưởng là lưu event dưới dạng `Flux<DomainEvent>` rồi tạo projection trạng thái bằng `scan`. Ví dụ trạng thái đơn hàng:

```java
sealed interface OrderEvent permits OrderCreated, OrderPaid, OrderCancelled {}

record OrderCreated(String orderId) implements OrderEvent {}
record OrderPaid(String orderId) implements OrderEvent {}
record OrderCancelled(String orderId) implements OrderEvent {}

enum OrderStatus { NEW, PAID, CANCELLED }

record OrderState(String orderId, OrderStatus status) {
    OrderState apply(OrderEvent event) {
        if (event instanceof OrderCreated created) {
            return new OrderState(created.orderId(), OrderStatus.NEW);
        }
        if (event instanceof OrderPaid paid) {
            return new OrderState(paid.orderId(), OrderStatus.PAID);
        }
        if (event instanceof OrderCancelled cancelled) {
            return new OrderState(cancelled.orderId(), OrderStatus.CANCELLED);
        }
        throw new IllegalArgumentException("Loại event không được hỗ trợ: " + event);
    }
}
```

Có thể tạo chuỗi trạng thái:

```java
Flux<OrderState> states = orderEvents
    .scan(initialState, OrderState::apply);
```

`scan` phát trạng thái ban đầu và từng trạng thái sau khi áp dụng event. Nếu nhiều subscriber cần cùng trạng thái mới nhất, có thể chia sẻ projection và phát lại phần tử gần nhất:

```java
Flux<OrderState> sharedCurrentState = states
    .replay(1)
    .refCount(1);
```

`replay(1)` giữ lại một trạng thái gần nhất; `refCount(1)` tự kết nối khi có subscriber và ngắt khi subscriber cuối cùng rời đi. Với nguồn lạnh, subscription mới sau khi ngắt có thể chạy lại nguồn và reducer. Nếu trạng thái cần tồn tại lâu dài, cần chọn lifecycle hoặc state store rõ ràng thay vì dựa vào `refCount` một cách mặc định.

Đây là một projection trạng thái dựa trên event stream. Nó có nét tương đồng với Behavior vì cung cấp giá trị hiện tại và các cập nhật, nhưng vẫn giữ ngữ nghĩa Publisher/Subscriber của Reactor: mỗi subscriber có subscription, demand và cancellation riêng.

## 10. Khi nào nên dùng FRP, khi nào nên dùng thư viện stream?

| Bài toán | Hướng tiếp cận phù hợp | Lý do |
|---|---|---|
| Tính giá trị giao diện từ nhiều giá trị hiện tại | Mô hình Behavior hoặc state holder reactive | Quan tâm trạng thái hiện tại và quan hệ giữa các giá trị |
| Xử lý message từ broker theo từng phần tử | `Flux`/`Flowable` | Cần pipeline, lỗi, concurrency và backpressure |
| Xây dựng trạng thái từ event log | Stream + reducer (`scan`) + state store | Cần lịch sử sự kiện và projection hiện tại |
| Cập nhật UI theo giá trị mới nhất | State holder/replay latest kết hợp stream | Subscriber mới cần snapshot hiện tại |
| Tính toán tín hiệu âm thanh hoặc dữ liệu theo thời gian | FRP hoặc thư viện signal chuyên dụng | Có thể cần mô hình thời gian và sampling chính xác hơn |
| Gọi dịch vụ bất đồng bộ và kết hợp kết quả | `Mono`/`Flux` | Cần composition, cancellation, timeout và xử lý lỗi |

Không cần ép toàn bộ ứng dụng vào một mô hình duy nhất. Một hệ thống có thể dùng Reactor để nhận và xử lý sự kiện, lưu event bền vững, rồi cập nhật state holder cho UI hoặc các thành phần cần snapshot hiện tại.

## 11. Kiểm thử khác biệt giữa chuỗi sự kiện và trạng thái

`StepVerifier` có thể xác nhận cách `scan` chuyển các event thành snapshot trạng thái:

```java
OrderState initial = new OrderState("order-1", OrderStatus.NEW);

Flux<OrderEvent> events = Flux.just(
    new OrderPaid("order-1"),
    new OrderCancelled("order-1")
);

Flux<OrderState> states = events
    .scan(initial, OrderState::apply);

StepVerifier.create(states)
    .expectNext(initial)
    .expectNext(new OrderState("order-1", OrderStatus.PAID))
    .expectNext(new OrderState("order-1", OrderStatus.CANCELLED))
    .verifyComplete();
```

Bài kiểm thử xác nhận mỗi event tạo một snapshot trạng thái tiếp theo. Nên bổ sung các trường hợp event đến sai thứ tự, event trùng, nguồn lỗi và subscriber hủy. Nếu trạng thái dẫn xuất phụ thuộc nhiều nguồn, hãy kiểm thử trường hợp các nguồn cập nhật riêng biệt để xác định liệu có phát snapshot trung gian hay không.

Với Behavior hoặc state holder được chia sẻ, kiểm thử subscriber đến muộn để xác nhận nó nhận snapshot gần nhất trước các cập nhật tiếp theo. Với event stream cần bảo toàn lịch sử, kiểm thử rằng không có event nào bị bỏ do buffer, drop hoặc cancellation ngoài chính sách.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao không chính xác | Cách hiểu đúng |
|---|---|---|
| Mọi `Flux` đều là Behavior | `Flux` là Publisher phát chuỗi tín hiệu, không nhất thiết giữ trạng thái hiện tại | Dùng reducer/state holder nếu cần trạng thái |
| `combineLatest` luôn tránh glitch | Nó kết hợp giá trị mới nhất theo từng lần phát | Phát snapshot tổng hợp nếu nhiều giá trị phải cập nhật nguyên tử |
| `scan` tạo Behavior cổ điển | `scan` phát chuỗi trạng thái theo subscription | Nó là cách xây dựng projection trạng thái từ event stream |
| FRP cổ điển và Reactive Streams là cùng một chuẩn | Hai khái niệm có mục tiêu và hợp đồng khác nhau | FRP là họ mô hình phản ứng theo thời gian; Reactive Streams là giao thức Publisher–Subscriber có demand |
| Scheduler quyết định ngữ nghĩa thời gian nghiệp vụ | Scheduler quyết định nơi callback chạy | Dùng event time/sequence number cho thứ tự nghiệp vụ |
| Backpressure có trong mọi Observable | Observable không có giao thức request | Dùng `Flux`/`Flowable` khi cần backpressure |
| Replay latest giữ toàn bộ lịch sử | Replay giới hạn chỉ giữ số phần tử đã cấu hình | Dùng event store riêng nếu cần lịch sử đầy đủ |

## 13. Quy trình thiết kế hệ thống kết hợp

Khi ứng dụng vừa xử lý sự kiện vừa duy trì trạng thái, hãy xác định:

1. **Điều gì là event?** Định nghĩa signal miền nghiệp vụ có ID, timestamp và payload rõ ràng.
2. **Điều gì là trạng thái hiện tại?** Xác định snapshot hoặc Behavior cần cung cấp cho consumer.
3. **Reducer có thuần không?** Cùng state và event nên tạo cùng state tiếp theo; side effect đặt ở bước riêng.
4. **Thứ tự sự kiện dựa trên mốc nào?** Phân biệt event time với processing time và xử lý event đến muộn.
5. **Nhiều nguồn có cần cập nhật nguyên tử không?** Nếu có, phát snapshot tổng hợp hoặc dùng cơ chế transaction thay vì giả định `combineLatest` tự gom các lần phát thành một giao dịch.
6. **Downstream có cần backpressure không?** Dùng Publisher tuân thủ Reactive Streams và đặt chính sách buffer/overflow phù hợp.
7. **Trạng thái được chia sẻ trong bao lâu?** Chọn replay, cache hoặc state store theo vòng đời và số subscriber.
8. **Cần kiểm thử điều gì?** Kiểm tra chuỗi event, snapshot, subscriber đến muộn, event trùng, lỗi, cancellation và cập nhật đồng thời.

FRP cổ điển cung cấp cách tư duy về Behavior và Event như các giá trị và lần xảy ra gắn với thời gian. Reactor và RxJava cung cấp công cụ thực thi pipeline sự kiện bất đồng bộ với các hợp đồng rõ ràng về subscription, tín hiệu, demand, cancellation và scheduler. Hai hướng tiếp cận có thể bổ trợ nhau: dùng stream để tiếp nhận và biến đổi sự kiện, reducer để tạo trạng thái, rồi công bố snapshot hiện tại cho những thành phần cần quan sát Behavior. Điều quan trọng là không đồng nhất chuỗi tín hiệu với giá trị hiện tại, cũng không giả định một toán tử stream tự cung cấp mọi ngữ nghĩa thời gian và nhất quán của FRP cổ điển.
