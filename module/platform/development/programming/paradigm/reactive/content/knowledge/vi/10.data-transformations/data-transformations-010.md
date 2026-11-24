# Lựa chọn toán tử theo số đầu ra, trạng thái và tín hiệu kết thúc

Trong Reactor, một pipeline `Mono` hoặc `Flux` được tạo bằng cách nối các operator để biến đổi, lọc, kết hợp và điều khiển tín hiệu. Có nhiều operator cho kết quả trông giống nhau trong ví dụ đơn giản, nhưng khác nhau về số phần tử đầu ra, trạng thái nội bộ, thứ tự xử lý và cách xử lý khi nguồn hoàn tất hoặc phát lỗi. Chọn đúng operator giúp pipeline thể hiện rõ ý định nghiệp vụ và kiểm soát được chi phí bộ nhớ, concurrency cũng như vòng đời subscription.

Bài học thuộc module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là đọc yêu cầu biến đổi theo ba câu hỏi: mỗi phần tử đầu vào tạo ra bao nhiêu đầu ra, operator có cần giữ trạng thái giữa các phần tử không, và điều gì xảy ra với các tín hiệu `onComplete`, `onError` hoặc cancel.

## 1. Đọc yêu cầu biến đổi trước khi chọn operator

Khi thiết kế một bước trong pipeline, hãy xác định số đầu ra có thể sinh ra từ một đầu vào và số đầu ra của cả luồng.

| Dạng biến đổi | Số đầu ra trên mỗi đầu vào | Operator thường gặp | Ví dụ nghiệp vụ |
|---|---:|---|---|
| Một thành một | Chính xác một nếu mapper chạy thành công | `map` | Chuẩn hóa một bản ghi thành DTO. |
| Một thành không hoặc một | 0 hoặc 1 | `filter`, `handle` | Bỏ bản ghi không hợp lệ hoặc không đủ điều kiện. |
| Một thành nhiều | 0 đến nhiều | `flatMap`, `concatMap`, `flatMapSequential` | Mỗi đơn hàng mở rộng thành nhiều dòng chi tiết. |
| Nhiều thành một | Một kết quả tổng hợp sau khi nguồn hoàn tất | `reduce`, `collectList`, `count` | Tính tổng, gom danh sách hoặc đếm bản ghi. |
| Nhiều thành nhiều theo nhóm | Một kết quả cho mỗi nhóm hoặc cửa sổ | `buffer`, `window`, `groupBy` | Xử lý theo lô, theo khoảng thời gian hoặc theo khóa. |
| Chỉ quan sát | Không đổi số đầu ra | `doOnNext`, `doOnError`, `doFinally` | Ghi log, đo thời gian hoặc cập nhật metric. |
| Chỉ chờ kết thúc | Bỏ các phần tử, giữ ý nghĩa hoàn tất/lỗi | `then`, `thenReturn`, `thenMany` | Chờ thao tác lưu xong rồi mới chạy bước tiếp theo. |

Số đầu ra là một chiều phân loại hữu ích, nhưng chưa đủ để quyết định. Cần xem thêm operator có giữ dữ liệu giữa các lần gọi hay không, có chạy publisher con đồng thời không, và tín hiệu kết thúc có được truyền tiếp hay thay đổi.

## 2. Một thành một: dùng `map` cho biến đổi đồng bộ

`map` nhận một giá trị `T` và biến đổi thành một giá trị `R`. Với mỗi `onNext` đầu vào, mapper tạo một giá trị đầu ra tương ứng. Operator không cần giữ trạng thái giữa các phần tử.

```java
Flux<Order> orders = orderRepository.findAll();

Flux<OrderSummary> summaries = orders
    .map(order -> new OrderSummary(
        order.id(),
        order.total(),
        order.status()
    ));
```

Chọn `map` khi phép biến đổi hoàn tất ngay trong lời gọi mapper và không trả về một `Publisher` khác. Ví dụ gồm đổi kiểu dữ liệu, chuẩn hóa chuỗi, tính trường dẫn xuất hoặc tạo đối tượng đầu ra.

`map` không chấp nhận giá trị `null` làm phần tử reactive. Nếu dữ liệu có thể không tồn tại, hãy biểu diễn trường hợp đó bằng `Mono.empty()`, `filter` hoặc một kiểu kết quả tường minh như `Optional` rồi xử lý tiếp. Không dùng `map` để gọi một API bất đồng bộ trả về `Mono` hoặc `Flux`, vì khi đó kết quả sẽ là publisher lồng nhau như `Flux<Mono<R>>`.

Nếu mapper ném exception, lỗi được chuyển thành tín hiệu `onError` và pipeline kết thúc tại nhánh lỗi, trừ khi phía sau có operator phục hồi. `map` không tự bắt lỗi để tiếp tục với phần tử tiếp theo.

## 3. Một thành không hoặc một: `filter` và `handle`

### `filter`: giữ hoặc loại bỏ phần tử

`filter` nhận một predicate. Nếu predicate trả về `true`, phần tử được chuyển xuống; nếu trả về `false`, phần tử bị loại bỏ. Một phần tử đầu vào vì vậy tạo ra không hoặc một phần tử đầu ra.

```java
Flux<Order> payableOrders = orders
    .filter(order -> order.total().signum() > 0)
    .filter(order -> order.status() == OrderStatus.CONFIRMED);
```

`filter` phù hợp khi quyết định chỉ là giữ hay bỏ từng phần tử. Nó không giữ trạng thái nghiệp vụ giữa các phần tử. Nếu tất cả phần tử bị loại bỏ, downstream nhận `onComplete` mà không nhận `onNext` nào. Vì vậy, kết quả có thể là một `Flux` rỗng.

Đối với `Mono`, `filter` cũng có thể biến một `Mono` có giá trị thành `Mono.empty()` khi predicate không thỏa mãn. Hãy cân nhắc điều này nếu operator phía sau yêu cầu phải có dữ liệu.

### `handle`: lọc và biến đổi trong một bước

`handle` kết hợp quyết định phát hoặc bỏ phần tử với việc biến đổi giá trị. Callback nhận giá trị đầu vào và một `SynchronousSink`; callback có thể gọi `next` tối đa một lần cho mỗi phần tử đầu vào, hoặc không gọi để bỏ phần tử đó. Callback cũng có thể kết thúc luồng hoặc phát lỗi.

```java
Flux<ValidOrder> validOrders = orders.handle((order, sink) -> {
    if (order.id() == null) {
        return;
    }

    if (order.total().signum() < 0) {
        sink.error(new IllegalArgumentException("Negative order total"));
        return;
    }

    sink.next(new ValidOrder(order.id(), order.total()));
});
```

Chọn `handle` khi logic trên mỗi phần tử có nhiều nhánh và cần vừa kiểm tra điều kiện vừa tạo giá trị mới. Nếu chỉ lọc, `filter` dễ đọc hơn; nếu chỉ biến đổi, `map` rõ ràng hơn. `handle` không phải cách phát nhiều phần tử từ một đầu vào. Khi một đầu vào cần tạo ra nhiều kết quả, dùng một operator flattening như `flatMap`.

## 4. Một thành nhiều: chọn cách flatten publisher con

Khi phép biến đổi của một phần tử trả về `Publisher`, cần nối publisher con vào luồng chính. Đây là lúc dùng các operator như `flatMap`, `concatMap` hoặc `flatMapSequential`.

### `flatMap`: xử lý publisher con đồng thời

`flatMap` gọi mapper cho từng phần tử nguồn, đăng ký các publisher con và hợp nhất kết quả của chúng. Một phần tử nguồn có thể tạo ra không, một hoặc nhiều phần tử đầu ra. Các publisher con có thể hoạt động đồng thời, nên kết quả có thể xen kẽ theo thời điểm phát.

```java
Flux<OrderLine> lines = orders.flatMap(order ->
    orderLineRepository.findByOrderId(order.id())
);
```

Nếu mỗi đơn hàng có nhiều dòng chi tiết, mỗi phần tử `Order` có thể tạo ra nhiều `OrderLine`. Nếu publisher con rỗng, phần tử nguồn đó không tạo ra đầu ra nào.

Có thể giới hạn số publisher con chạy đồng thời và lượng prefetch:

```java
Flux<InventoryResult> checks = orders.flatMap(
    order -> inventoryClient.check(order),
    8,  // concurrency tối đa
    4   // prefetch từ mỗi publisher con
);
```

`concurrency` giới hạn số publisher con đang được subscribe đồng thời. `prefetch` kiểm soát lượng phần tử yêu cầu trước từ mỗi publisher con. Hai tham số này ảnh hưởng đến thông lượng và lượng dữ liệu đang chờ; chúng không tự đặt giới hạn cho mọi hàng đợi bên ngoài pipeline.

### `concatMap`: lần lượt xử lý và giữ thứ tự

`concatMap` cũng ánh xạ mỗi phần tử thành một publisher con, nhưng chỉ xử lý publisher con hiện tại cho đến khi hoàn tất rồi mới chuyển sang phần tử nguồn tiếp theo. Kết quả giữ thứ tự theo nguồn.

```java
Flux<Receipt> receipts = orders.concatMap(order ->
    receiptService.create(order)
);
```

Chọn `concatMap` khi các thao tác phụ thuộc thứ tự hoặc không nên chạy đồng thời, chẳng hạn ghi tuần tự các thay đổi của cùng một tài khoản. Đổi lại, một publisher con chậm sẽ trì hoãn việc xử lý các phần tử nguồn phía sau.

### `flatMapSequential`: đồng thời nhưng giữ thứ tự nguồn

`flatMapSequential` cho phép đăng ký và thực thi publisher con đồng thời, nhưng phát kết quả theo thứ tự của các phần tử nguồn. Nếu publisher con thứ hai hoàn tất trước publisher con thứ nhất, kết quả thứ hai có thể phải chờ trong bộ đệm.

```java
Flux<EnrichedOrder> enriched = orders.flatMapSequential(
    order -> enrichmentService.enrich(order),
    6,
    2
);
```

Chọn operator này khi cần tận dụng concurrency nhưng vẫn phải giữ thứ tự đầu ra. Hãy tính đến lượng dữ liệu có thể bị đệm khi một publisher con đầu tiên chậm hơn các publisher con phía sau.

### `switchMap`: chỉ giữ kết quả của yêu cầu mới nhất

`switchMap` chuyển mỗi phần tử nguồn thành publisher con và chuyển sang publisher con mới nhất khi có phần tử nguồn mới. Subscription đến publisher con trước bị hủy. Các kết quả đến muộn từ publisher con cũ không còn được chuyển xuống.

```java
Flux<SearchResult> results = searchQueries
    .debounce(Duration.ofMillis(250))
    .switchMap(query -> searchService.search(query));
```

Đây là lựa chọn phù hợp cho tìm kiếm gợi ý khi người dùng tiếp tục nhập từ khóa: kết quả của truy vấn cũ không còn hữu ích sau khi có truy vấn mới. Không dùng `switchMap` cho các thao tác bắt buộc hoàn tất, chẳng hạn ghi giao dịch hoặc xử lý sự kiện kiểm toán, vì publisher con trước có thể bị hủy khi nguồn phát phần tử mới.

### So sánh các operator flattening

| Operator | Publisher con | Thứ tự kết quả | Tác động khi có phần tử nguồn mới |
|---|---|---|---|
| `flatMap` | Có thể chạy đồng thời. | Theo thời điểm kết quả đến; có thể xen kẽ. | Tiếp tục đăng ký publisher con mới trong giới hạn concurrency. |
| `concatMap` | Xử lý lần lượt. | Theo thứ tự nguồn. | Đợi publisher con trước hoàn tất. |
| `flatMapSequential` | Có thể chạy đồng thời. | Theo thứ tự nguồn. | Có thể đệm kết quả đến sớm để chờ kết quả trước. |
| `switchMap` | Chỉ publisher con mới nhất còn được theo dõi. | Theo publisher con hiện tại. | Hủy publisher con trước khi chuyển sang publisher con mới. |

## 5. Nhiều thành một: tổng hợp bằng `reduce`, `scan` và `collectList`

Khi cần tổng hợp nhiều phần tử thành một kết quả, cần quyết định kết quả được phát liên tục hay chỉ sau khi nguồn hoàn tất.

### `reduce`: chỉ phát kết quả cuối cùng

`reduce` kết hợp các phần tử nguồn bằng một accumulator và chỉ phát giá trị tích lũy cuối cùng khi nguồn hoàn tất.

```java
Mono<BigDecimal> total = orderLines
    .map(OrderLine::subtotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Với overload có seed như trên, nguồn rỗng vẫn tạo ra một kết quả là seed (`BigDecimal.ZERO`). Nếu dùng `reduce(accumulator)` không có seed, nguồn rỗng tạo ra `Mono.empty()` vì không có phần tử nào để tích lũy.

`reduce` phù hợp khi downstream chỉ cần kết quả cuối cùng, ví dụ tổng tiền, giá trị lớn nhất hoặc một đối tượng thống kê cuối luồng. Vì phải chờ nguồn hoàn tất, nó không phát kết quả trung gian.

### `scan`: phát từng trạng thái tích lũy

`scan` cũng dùng accumulator nhưng phát mỗi trạng thái tích lũy ngay khi được tính. Với overload có seed, seed được phát đầu tiên, sau đó là các giá trị tích lũy sau mỗi phần tử nguồn.

```java
Flux<BigDecimal> runningTotals = orderLines
    .map(OrderLine::subtotal)
    .scan(BigDecimal.ZERO, BigDecimal::add);
```

Nếu các subtotal lần lượt là `10`, `15`, `5`, kết quả `scan` là `0`, `10`, `25`, `30`. Đây là lựa chọn phù hợp khi giao diện cần hiển thị tổng đang tăng hoặc pipeline cần quan sát trạng thái tích lũy theo thời gian.

### `collectList`: gom tất cả phần tử thành một danh sách

`collectList` thu thập mọi phần tử của `Flux` vào một `List` và phát danh sách đó dưới dạng `Mono<List<T>>` khi nguồn hoàn tất.

```java
Mono<List<OrderLine>> allLines = orderLines.collectList();
```

Với nguồn rỗng, `collectList` phát một danh sách rỗng rồi hoàn tất. Vì vậy, nó khác với `reduce` không seed, vốn có thể hoàn tất mà không phát giá trị.

`collectList` cần giữ tất cả phần tử trước khi phát kết quả. Không nên dùng trên luồng vô hạn hoặc luồng có kích thước không kiểm soát, vì danh sách sẽ tiếp tục tăng và tiêu thụ bộ nhớ. Với dữ liệu lớn, hãy xử lý theo batch bằng `buffer(n)` hoặc lưu/ghi theo từng phần.

### Chọn cách tổng hợp

| Operator | Giá trị phát ra | Thời điểm phát | Nguồn rỗng |
|---|---|---|---|
| `reduce(seed, accumulator)` | Một giá trị cuối | Khi nguồn hoàn tất | Phát seed. |
| `reduce(accumulator)` | Tối đa một giá trị cuối | Khi nguồn hoàn tất | `Mono.empty()`. |
| `scan(seed, accumulator)` | Seed và các trạng thái tích lũy | Sau từng bước tích lũy | Phát seed rồi hoàn tất. |
| `collectList()` | Một danh sách chứa mọi phần tử | Khi nguồn hoàn tất | Phát danh sách rỗng. |
| `count()` | Một số đếm | Khi nguồn hoàn tất | Phát `0`. |

## 6. Nhóm và chia lô: `buffer`, `window` và `groupBy`

Khi cần xử lý nhiều phần tử theo nhóm, hãy chọn operator dựa trên dạng nhóm đầu ra.

### `buffer`: gom phần tử thành collection

`buffer(n)` thu thập tối đa `n` phần tử thành một danh sách rồi phát danh sách đó. Mỗi đầu ra là một collection, vì vậy số đầu ra thường ít hơn số phần tử đầu vào.

```java
Flux<List<Event>> batches = events.buffer(100);

batches.concatMap(batch -> batchRepository.saveAll(batch));
```

Với overload theo thời gian, `buffer(Duration)` gom phần tử trong một khoảng thời gian. Có thể kết hợp giới hạn kích thước và thời gian khi cần flush theo điều kiện nào đến trước. Cần cân nhắc phần tử còn lại ở cuối luồng: khi nguồn hoàn tất, buffer chưa đầy nhưng có phần tử vẫn được phát như một batch cuối.

### `window`: chia thành các luồng con

`window(n)` chia nguồn thành các `Flux` con, mỗi cửa sổ chứa tối đa `n` phần tử. Khác với `buffer`, phần tử đầu ra là một publisher con, không phải collection đã thu thập xong.

```java
Flux<Flux<Event>> windows = events.window(100);

windows.concatMap(window ->
    window.collectList().flatMap(batchRepository::saveAll)
);
```

`window` phù hợp khi cần xử lý từng nhóm bằng operator reactive mà không nhất thiết gom tất cả phần tử vào một collection ngay tại bước chia nhóm. Tuy nhiên, các cửa sổ vẫn cần được tiêu thụ; nếu tạo quá nhiều cửa sổ hoặc xử lý chúng đồng thời không giới hạn, pipeline vẫn có thể tích lũy công việc.

### `groupBy`: phân nhóm theo khóa

`groupBy` tạo một `GroupedFlux` cho mỗi khóa khác nhau. Ví dụ:

```java
Flux<GroupedFlux<String, OrderEvent>> byCustomer =
    orderEvents.groupBy(OrderEvent::customerId);

byCustomer.flatMap(group ->
    group.concatMap(this::updateCustomerState)
);
```

Mỗi nhóm có luồng riêng, cho phép xử lý tuần tự trong từng khách hàng trong khi các khách hàng khác có thể được xử lý đồng thời. Số khóa khác nhau có thể tăng lớn, nên cần kiểm soát số nhóm và cách tiêu thụ chúng. Không nên giữ mọi `GroupedFlux` vô thời hạn hoặc để một nhóm không được subscribe trong khi nguồn tiếp tục phát dữ liệu.

## 7. Chuyển đổi tín hiệu khi nguồn rỗng hoặc kết thúc

Một số operator được chọn không phải vì số đầu ra thông thường mà vì cách chúng xử lý trường hợp không có phần tử.

### `defaultIfEmpty`: cung cấp giá trị mặc định

`defaultIfEmpty(value)` phát giá trị mặc định nếu nguồn hoàn tất mà không phát phần tử nào.

```java
Mono<User> user = userRepository.findById(userId)
    .defaultIfEmpty(User.anonymous());
```

Operator này chỉ xử lý trường hợp hoàn tất rỗng. Nếu repository phát `onError`, lỗi vẫn đi xuống downstream; `defaultIfEmpty` không phải cơ chế bắt lỗi.

### `switchIfEmpty`: chuyển sang nguồn thay thế

`switchIfEmpty` subscribe vào publisher thay thế nếu nguồn ban đầu hoàn tất mà không có phần tử.

```java
Mono<Product> product = productRepository.findById(id)
    .switchIfEmpty(productApi.fetchById(id));
```

Publisher thay thế chỉ được sử dụng khi nguồn đầu tiên rỗng. Nếu lời gọi API thay thế cần được tạo trễ, có thể bọc bằng `Mono.defer` để tránh thực thi sớm khi xây dựng pipeline.

### `take`: giới hạn số phần tử và kết thúc sớm

`take(n)` chỉ chuyển tối đa `n` phần tử đầu tiên rồi hoàn tất downstream. Khi đã nhận đủ số phần tử, operator hủy subscription upstream để ngừng yêu cầu thêm dữ liệu.

```java
Flux<Event> firstEvents = eventSource.take(10);
```

`take` hữu ích khi chỉ cần một mẫu hoặc một số lượng phần tử giới hạn. Hủy upstream là tín hiệu điều khiển từ downstream; nó không phải `onComplete` hay `onError` được gửi từ upstream. Cần bảo đảm nguồn có xử lý cancel để dừng tài nguyên và công việc nền.

## 8. Tín hiệu kết thúc: hoàn tất, lỗi và hủy

Reactive Streams định nghĩa một chuỗi tín hiệu gồm `onSubscribe`, không hoặc nhiều `onNext`, rồi tối đa một tín hiệu kết thúc là `onComplete` hoặc `onError`. Sau terminal signal, publisher không được gửi thêm tín hiệu dữ liệu cho subscription đó.

Cancel có vai trò khác: subscriber gọi `cancel()` trên subscription để yêu cầu dừng nhận dữ liệu. Cancel không phải terminal signal downstream; publisher cũng không gửi `onComplete` chỉ để xác nhận cancel. Trong Reactor, có thể quan sát các trường hợp kết thúc bằng các operator phù hợp.

| Operator | Quan sát điều gì? | Có phục hồi luồng không? |
|---|---|---|
| `doOnComplete` | Nguồn hoàn tất bình thường. | Không. |
| `doOnError` | Nguồn phát lỗi. | Không. |
| `doOnCancel` | Downstream hủy subscription. | Không. |
| `doFinally` | Kết thúc bằng complete, error hoặc cancel. | Không. |
| `onErrorMap` | Chuyển exception này thành exception khác. | Không, luồng vẫn lỗi. |
| `onErrorResume` | Chuyển sang publisher dự phòng khi có lỗi. | Có thể tiếp tục bằng publisher thay thế. |
| `onErrorReturn` | Thay lỗi bằng một giá trị dự phòng. | Có, nếu phát giá trị dự phòng thành công. |
| `retry` | Đăng ký lại nguồn khi có lỗi. | Thử lại bằng một subscription mới. |

Ví dụ quan sát vòng đời:

```java
Flux<Event> observed = eventSource
    .doOnComplete(() -> log.info("Source completed"))
    .doOnError(error -> log.error("Source failed", error))
    .doOnCancel(() -> log.info("Subscription cancelled"))
    .doFinally(signalType -> log.info("Finished with {}", signalType));
```

`doFinally` hữu ích khi cần giải phóng hoặc ghi nhận trạng thái sau bất kỳ kiểu kết thúc nào. Nếu cần tháo tài nguyên thuộc về nguồn callback, nên đăng ký cleanup ngay tại nơi tạo nguồn, chẳng hạn `Flux.create` với `sink.onDispose`.

### `then`, `thenReturn` và `thenMany`: chỉ quan tâm việc hoàn tất

`then()` bỏ qua các phần tử nguồn và trả về `Mono<Void>` hoàn tất khi nguồn hoàn tất. Nếu nguồn lỗi, lỗi được truyền tiếp.

```java
Mono<Void> saveAll = orderRepository.saveAll(events)
    .then();
```

`thenReturn(value)` cũng bỏ qua các phần tử nguồn nhưng phát một giá trị cố định sau khi nguồn hoàn tất bình thường:

```java
Mono<String> result = auditRepository.write(record)
    .thenReturn("AUDIT_RECORDED");
```

`thenMany(publisher)` chờ nguồn trước hoàn tất rồi mới subscribe vào publisher tiếp theo:

```java
Flux<Notification> notifications = auditRepository.write(record)
    .thenMany(notificationService.sendFor(record));
```

Nếu nguồn trước phát lỗi, publisher phía sau không được subscribe trừ khi lỗi đã được phục hồi. Các operator `then...` hữu ích khi thứ tự hoàn tất quan trọng nhưng giá trị của bước trước không cần chuyển sang bước sau.

## 9. Xử lý lỗi: phân biệt quan sát, thay lỗi và thử lại

Lỗi là terminal signal. Operator được chọn quyết định lỗi được quan sát, chuyển đổi, thay bằng kết quả khác hay làm nguồn được đăng ký lại.

### Quan sát lỗi không đồng nghĩa với phục hồi

`doOnError` dùng để ghi log hoặc cập nhật metric. Sau callback, lỗi vẫn đi xuống downstream:

```java
Mono<Profile> profile = profileRepository.findById(id)
    .doOnError(error -> metrics.increment("profile.lookup.failed"));
```

Nếu muốn thay loại exception nhưng vẫn giữ nhánh lỗi, dùng `onErrorMap`:

```java
Mono<Profile> profile = profileRepository.findById(id)
    .onErrorMap(DatabaseException.class,
        error -> new ProfileLookupException(id, error));
```

### Dùng publisher dự phòng khi có lỗi

`onErrorResume` thay nguồn lỗi bằng một publisher khác:

```java
Mono<Profile> profile = profileRepository.findById(id)
    .onErrorResume(RepositoryUnavailableException.class,
        error -> profileCache.findById(id));
```

Publisher dự phòng phải phù hợp với kiểu kết quả và chính sách nghiệp vụ. Không nên chuyển mọi lỗi thành dữ liệu mặc định nếu điều đó che giấu lỗi xác thực, lỗi dữ liệu hoặc lỗi lập trình.

### `retry`: đăng ký lại nguồn

`retry(n)` thử đăng ký lại upstream khi có lỗi, tối đa theo chính sách số lần được chỉ định. Đây là một lần thực thi mới của phần nguồn được retry. Vì vậy, tác dụng phụ trước khi lỗi có thể đã xảy ra và có thể lặp lại khi đăng ký lại.

```java
Mono<PaymentStatus> status = paymentClient.check(paymentId)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientFailure));
```

Chỉ retry những lỗi có khả năng tạm thời và cần cân nhắc tính idempotent của thao tác. Với thao tác ghi tiền hoặc tạo đơn hàng, hãy dùng idempotency key hoặc cơ chế đối soát để tránh thực hiện trùng khi không biết lần gọi trước đã được hệ thống ngoài xử lý đến đâu.

### Empty và Error là hai trạng thái khác nhau

Một publisher hoàn tất mà không phát dữ liệu (`onComplete` không có `onNext`) không phải là lỗi. `defaultIfEmpty` và `switchIfEmpty` xử lý trường hợp rỗng; `onErrorResume` xử lý terminal error. Nếu trộn hai trường hợp, pipeline có thể trả kết quả dự phòng sai hoặc che giấu lỗi thật.

## 10. Operator có trạng thái và operator không giữ trạng thái

Một tiêu chí khác là operator có phải lưu thông tin giữa các phần tử hay không.

| Nhóm | Ví dụ | Trạng thái được giữ | Điều cần chú ý |
|---|---|---|---|
| Không trạng thái theo phần tử | `map`, `filter`, `handle` | Không cần lịch sử phần tử trước để xử lý phần tử hiện tại. | Thường dễ song song hóa ở các ranh giới phù hợp; mapper vẫn cần an toàn luồng nếu dùng trạng thái ngoài. |
| Tích lũy | `scan`, `reduce`, `count` | Giá trị tích lũy hoặc bộ đếm. | `reduce` chờ nguồn hoàn tất; `scan` phát trạng thái từng bước. |
| Khử trùng lặp | `distinct`, `distinctUntilChanged` | Tập khóa đã thấy hoặc giá trị trước đó. | Bộ nhớ có thể tăng theo số khóa khác nhau. |
| Gom nhóm/buffer | `buffer`, `window`, `groupBy` | Phần tử đang chờ, nhóm hoặc cửa sổ đang mở. | Cần giới hạn kích thước, số nhóm và cách tiêu thụ. |
| Kết hợp bất đồng bộ | `flatMap`, `flatMapSequential`, `switchMap` | Subscription con, concurrency và có thể cả kết quả đang chờ. | Cần xác định thứ tự, prefetch và chính sách cancel. |

### `distinct` và `distinctUntilChanged`

`distinct()` chỉ chuyển xuống phần tử có khóa chưa xuất hiện trước đó trong phạm vi subscription. Nó cần theo dõi các khóa đã thấy, vì vậy bộ nhớ tăng theo số khóa khác nhau.

```java
Flux<String> uniqueCustomerIds = orderEvents
    .map(OrderEvent::customerId)
    .distinct();
```

`distinctUntilChanged()` chỉ loại bỏ phần tử lặp liên tiếp theo khóa hoặc phép so sánh. Nó chỉ cần nhớ giá trị/khóa trước đó:

```java
Flux<Status> statusChanges = orderEvents
    .map(OrderEvent::status)
    .distinctUntilChanged();
```

Với chuỗi trạng thái `NEW, NEW, PAID, PAID, SHIPPED`, `distinctUntilChanged` phát `NEW, PAID, SHIPPED`. `distinct` cũng chỉ phát mỗi giá trị khác nhau một lần trong toàn subscription, nên có thể bỏ một trạng thái hợp lệ nếu trạng thái đó xuất hiện lại sau một trạng thái khác. Chọn theo đúng định nghĩa trùng lặp của nghiệp vụ.

## 11. Kết hợp operator theo một ví dụ xuyên suốt

Giả sử một dịch vụ nhận sự kiện đơn hàng. Mỗi sự kiện cần được kiểm tra, tải thông tin khách hàng, tạo bản ghi kiểm toán và cuối cùng cập nhật trạng thái. Mỗi bước có cardinality và yêu cầu kết thúc khác nhau.

```java
Flux<OrderResult> results = orderEvents
    .filter(event -> event.orderId() != null)
    .distinct(OrderEvent::eventId)
    .flatMap(event -> customerService.find(event.customerId())
        .map(customer -> new EnrichedOrder(event, customer)),
        8,
        4
    )
    .concatMap(enriched -> auditService.write(enriched)
        .then(orderService.apply(enriched))
    )
    .onErrorResume(RecoverableOrderException.class,
        error -> recoveryService.record(error).then(Mono.<OrderResult>empty())
    );
```

Đọc pipeline theo từng bước:

1. `filter` loại bỏ sự kiện thiếu `orderId`; mỗi sự kiện còn lại tạo tối đa một đầu ra.
2. `distinct` loại bỏ `eventId` đã thấy trong subscription; operator giữ tập khóa để nhận biết trùng lặp.
3. `flatMap` tải khách hàng bất đồng bộ với concurrency giới hạn; một sự kiện có thể không tạo đầu ra nếu lookup rỗng.
4. `concatMap` thực hiện ghi kiểm toán rồi mới cập nhật đơn hàng cho từng phần tử theo thứ tự nguồn sau bước trước đó.
5. `onErrorResume` chỉ phục hồi `RecoverableOrderException` bằng cách ghi nhận lỗi rồi chuyển thành publisher rỗng; các lỗi khác vẫn kết thúc pipeline.

Ví dụ giả định các phương thức trả về đúng kiểu `Mono`/`Flux` tương ứng và các kiểu domain đã được định nghĩa. Trong hệ thống thật, cần quyết định rõ `distinct` giữ khóa trong bao lâu, liệu thứ tự theo toàn bộ luồng có bắt buộc hay chỉ theo từng đơn hàng, và thao tác kiểm toán có idempotent khi retry hay không.

## 12. Quy trình chọn operator

Trước khi viết pipeline, hãy đi theo trình tự sau:

1. **Xác định cardinality:** một đầu vào tạo một, không hoặc một, nhiều, hay góp phần vào một kết quả tổng hợp?
2. **Xác định trạng thái:** phép biến đổi chỉ nhìn phần tử hiện tại, hay cần nhớ giá trị trước, khóa đã thấy, bộ đếm hoặc nhóm đang mở?
3. **Xác định thực thi:** publisher con có thể chạy đồng thời không? Kết quả có phải giữ thứ tự nguồn không? Có thể hủy công việc cũ khi có yêu cầu mới không?
4. **Xác định empty:** nguồn rỗng là kết quả hợp lệ, cần giá trị mặc định, cần nguồn thay thế hay cần giữ `Mono.empty()`?
5. **Xác định error:** lỗi chỉ cần quan sát, cần đổi loại, cần publisher dự phòng hay có thể retry an toàn?
6. **Xác định terminal và cancel:** khi nguồn hoàn tất, lỗi hoặc subscriber hủy, tài nguyên nào cần đóng và publisher con nào cần dừng?
7. **Xác định tài nguyên:** operator có buffer, prefetch, tập khóa hoặc danh sách tích lũy không? Cần giới hạn kích thước hoặc concurrency ở đâu?

Một số quy tắc chọn nhanh:

- Biến đổi đồng bộ một giá trị thành một giá trị: `map`.
- Giữ hoặc bỏ từng phần tử: `filter`; cần logic phát có điều kiện và biến đổi cùng lúc: `handle`.
- Gọi publisher con bất đồng bộ: `flatMap`; cần tuần tự: `concatMap`; cần đồng thời nhưng giữ thứ tự: `flatMapSequential`; chỉ cần kết quả mới nhất: `switchMap`.
- Cần kết quả tích lũy cuối cùng: `reduce`; cần từng trạng thái tích lũy: `scan`; cần danh sách cuối: `collectList`.
- Cần xử lý theo batch, cửa sổ hoặc khóa: `buffer`, `window`, `groupBy`.
- Cần xử lý nguồn rỗng: `defaultIfEmpty` hoặc `switchIfEmpty`; cần xử lý lỗi: `onErrorResume`, `onErrorMap` hoặc `retry` theo ngữ nghĩa.
- Chỉ cần chạy bước sau khi nguồn hoàn tất: `then`, `thenReturn` hoặc `thenMany`.

## 13. Kiểm thử cardinality và terminal signal

`StepVerifier` giúp xác minh số phần tử đầu ra, thứ tự và tín hiệu kết thúc. Ví dụ kiểm tra `filter` có thể tạo luồng rỗng:

```java
StepVerifier.create(Flux.just(2, 4, 6).filter(value -> value % 2 != 0))
    .verifyComplete();
```

Kiểm tra `reduce` với seed trên nguồn rỗng:

```java
StepVerifier.create(Flux.<Integer>empty().reduce(0, Integer::sum))
    .expectNext(0)
    .verifyComplete();
```

Kiểm tra `collectList` trên nguồn rỗng:

```java
StepVerifier.create(Flux.<Integer>empty().collectList())
    .expectNext(List.of())
    .verifyComplete();
```

Kiểm tra lỗi được thay bằng publisher dự phòng:

```java
StepVerifier.create(
        Mono.<String>error(new IllegalStateException("temporary"))
            .onErrorResume(error -> Mono.just("fallback"))
    )
    .expectNext("fallback")
    .verifyComplete();
```

Kiểm thử một pipeline nên bao gồm các nhánh quan trọng, không chỉ trường hợp có dữ liệu bình thường:

- Có phần tử đầu vào và có đầu ra theo cardinality dự kiến.
- Nguồn rỗng và tất cả phần tử bị lọc bỏ.
- Mapper hoặc publisher con phát lỗi.
- Publisher con hoàn tất rỗng.
- Nhiều publisher con hoàn tất theo thứ tự khác nhau.
- Cancel xảy ra khi còn publisher con hoặc dữ liệu đang chờ.
- Buffer, nhóm hoặc danh sách tích lũy đạt giới hạn dự kiến.
- Retry không lặp tác dụng phụ ngoài ý muốn.

Khi kiểm tra operator có trạng thái, hãy xác minh trạng thái được khởi tạo lại cho mỗi subscription nếu đó là yêu cầu. Tránh đặt một mutable accumulator dùng chung bên ngoài pipeline rồi vô tình chia sẻ nó giữa nhiều subscriber.

## 14. Kết luận thực hành

Operator nên được chọn theo hợp đồng đầu ra mà bước nghiệp vụ cần cung cấp. Cardinality cho biết một phần tử có thể tạo ra bao nhiêu phần tử; trạng thái cho biết operator phải giữ dữ liệu nào giữa các lần phát; tín hiệu kết thúc cho biết pipeline tiếp tục, hoàn tất, phục hồi hay dừng khi nguồn rỗng, lỗi hoặc bị hủy.

Khi ba khía cạnh này được xác định trước, việc chọn `map`, `filter`, `flatMap`, `reduce`, `scan`, `buffer`, `then` hay nhóm operator xử lý lỗi trở nên có cơ sở. Pipeline vì thế dễ đọc, dễ kiểm thử và dễ điều chỉnh concurrency, backpressure cùng tài nguyên khi chạy trong môi trường bất đồng bộ.
