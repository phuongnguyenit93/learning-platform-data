# Giới hạn số luồng con thay vì khởi chạy không kiểm soát

Một pipeline reactive thường biến mỗi phần tử đầu vào thành một thao tác bất đồng bộ khác. Ví dụ, một luồng đơn hàng có thể gọi API khách hàng để làm giàu dữ liệu, ghi kết quả vào database hoặc gửi yêu cầu đến một dịch vụ tính giá. Nếu khởi chạy mọi thao tác cùng lúc, ứng dụng có thể vượt giới hạn connection pool, làm đầy hàng đợi, tăng bộ nhớ và khiến dịch vụ phụ thuộc bị quá tải.

Reactor cho phép giới hạn số publisher con đang hoạt động bằng các overload có tham số concurrency của `flatMap` và `flatMapSequential`. Đây là cách kiểm soát lượng công việc đang bay (*in-flight work*) ngay trong pipeline. Cần phân biệt giới hạn này với số thread, prefetch, tốc độ request mỗi giây và giới hạn tài nguyên của hệ thống bên ngoài.

Bài học thuộc chương **Hiệu năng** của module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.

## 1. Vấn đề khi khởi chạy mọi tác vụ cùng lúc

Giả sử một nguồn phát 50.000 đơn hàng. Với mỗi đơn, ứng dụng gọi dịch vụ khách hàng và chờ kết quả. Nếu mỗi phần tử tạo một tác vụ độc lập bằng `subscribe()` bên trong callback, các tác vụ con tách khỏi pipeline chính:

```java
// Không nên: subscription con bị tách khỏi lifecycle của pipeline.
Flux<Order> orders = orderRepository.findPending();

orders.doOnNext(order ->
    customerClient.findById(order.customerId())
        .subscribe(customer -> saveEnrichedOrder(order, customer))
).subscribe();
```

Pipeline ngoài không chờ các publisher con hoàn tất. Nó không kiểm soát được số request đang chạy, không tổng hợp lỗi của các tác vụ con và việc cancel pipeline ngoài không nhất thiết hủy những subscription đã tạo riêng. Nếu nguồn phát nhanh, số tác vụ có thể tăng đến mức làm cạn connection, thread hoặc bộ nhớ.

Cách đúng là trả publisher con về operator kết hợp:

```java
Flux<EnrichedOrder> enriched = orders.flatMap(order ->
    customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer))
);
```

`flatMap` giữ các publisher con trong cùng chuỗi xử lý. Nó phối hợp subscription, tín hiệu lỗi và cancellation giữa luồng ngoài với các luồng con. Tuy nhiên, khi cần bảo đảm một giới hạn cụ thể, hãy chọn overload có concurrency tường minh.

## 2. `flatMap` giới hạn số publisher con đang hoạt động

Overload quan trọng của Reactor có dạng:

```java
flatMap(mapper, concurrency, prefetch)
```

- `mapper` chuyển mỗi phần tử nguồn thành một `Publisher` con.
- `concurrency` là số publisher con tối đa được subscribe và xử lý đồng thời.
- `prefetch` điều chỉnh lượng phần tử được yêu cầu trước từ mỗi publisher con.

Ví dụ giới hạn 12 lời gọi API đang hoạt động:

```java
Flux<EnrichedOrder> enrichedOrders = orderRepository.findPending()
    .flatMap(
        order -> customerClient.findById(order.customerId())
            .map(customer -> new EnrichedOrder(order, customer)),
        12,
        1
    );
```

Tại một thời điểm, `flatMap` chỉ cho phép tối đa 12 publisher con đang hoạt động. Khi một publisher con hoàn tất, operator có thể subscribe vào publisher con tiếp theo. Vì mỗi lời gọi ở ví dụ trả về `Mono` chỉ phát tối đa một giá trị, `prefetch = 1` là lựa chọn dễ hiểu; với inner publisher phát nhiều phần tử, cần chọn prefetch phù hợp.

Sơ đồ minh họa:

```text
Flux<Order>
     |
     v
  flatMap(concurrency = 3)
     |
     +---- inner A: đang chạy -----+
     +---- inner B: đang chạy -----+----> kết quả được phát khi sẵn sàng
     +---- inner C: đang chạy -----+
     |
     | Chờ một inner hoàn tất
     v
  Subscribe inner D
```

Khi ba publisher con A, B, C đang hoạt động, phần tử tiếp theo chưa được mở thành publisher con thứ tư. Khi một trong ba hoàn tất, slot được giải phóng để xử lý phần tử tiếp theo.

### Concurrency không phải số thread

Đây là điểm rất quan trọng: `concurrency = 12` giới hạn số publisher con đang được subscribe, không có nghĩa Reactor tạo đúng 12 thread.

Một publisher con có thể là một lời gọi HTTP non-blocking. Nhiều lời gọi có thể đang chờ response mà không giữ một thread riêng cho từng lời gọi. Ngược lại, nếu mỗi publisher con tự khởi chạy một thread hoặc gọi `subscribe()` riêng, giới hạn của `flatMap` không kiểm soát được các công việc đã tách ra ngoài.

Vì vậy, hãy giữ toàn bộ công việc thuộc một phần tử bên trong publisher mà `flatMap` nhận được. Không tạo tác vụ fire-and-forget ở bên trong mapper.

## 3. Chọn `concurrency` dựa trên capacity thực tế

Không có một con số concurrency phù hợp cho mọi ứng dụng. Giới hạn cần dựa trên tài nguyên nhỏ nhất trong đường xử lý và phần capacity cần dành cho các luồng khác.

Ví dụ, một pipeline gọi database có thể bị giới hạn bởi:

- Số connection còn khả dụng trong pool.
- Số query database có thể xử lý đồng thời.
- Thời gian trung bình và p95 của query.
- Bộ nhớ cần giữ cho mỗi query đang hoạt động.
- Số request khác cũng dùng chung pool.

Nếu pool có 40 connection, không nên mặc định dành cả 40 connection cho một pipeline. Các request khác, transaction, health check và tác vụ nền cũng cần connection. Có thể dành tối đa 24 slot cho pipeline này rồi điều chỉnh theo metric thực tế.

Một cách ước lượng ban đầu là dùng định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số công việc trung bình đang ở trong hệ thống.
- `λ` là throughput mục tiêu, tính bằng công việc mỗi giây.
- `W` là thời gian xử lý trung bình, tính bằng giây.

Nếu muốn xử lý 120 request/giây và thời gian phản hồi trung bình là 150 ms, số request đang bay trung bình cần khoảng:

\[
L = 120 \times 0.15 = 18
\]

Đây là ước lượng để bắt đầu đo, không phải cấu hình tối ưu. Latency thay đổi theo tải, p95/p99 có thể cao hơn trung bình và dependency có thể có giới hạn riêng. Hãy thử nghiệm tải, quan sát queue và đặt giới hạn có khoảng dự phòng.

### Mô hình capacity theo dependency

| Dependency | Điều cần giới hạn | Nguồn số liệu |
|---|---|---|
| Database | Query đang chạy và connection đang mượn. | Connection pool, query latency, database capacity. |
| HTTP service | Request đang bay và connection đang mở. | Connection pool, quota, latency, 429/503. |
| Message broker | Record đang xử lý và chưa acknowledge. | Prefetch, consumer lag, partition assignment. |
| CPU transform | Công việc tính toán đồng thời. | Số core, CPU utilization, thời gian xử lý. |
| File hoặc API blocking | Worker blocking đang sử dụng. | `boundedElastic` active threads, queue và thời gian chờ. |

Nếu pipeline gọi nhiều dependency nối tiếp, hãy xem xét giới hạn tại từng ranh giới. Concurrency phù hợp với HTTP service có thể quá cao đối với connection pool database nhỏ hơn ở bước tiếp theo.

## 4. `prefetch` khác `concurrency`

Hai tham số này thường bị nhầm lẫn:

- `concurrency` giới hạn số publisher con đang hoạt động.
- `prefetch` điều chỉnh số phần tử được yêu cầu trước từ mỗi publisher con.

Với inner publisher là `Mono`, mỗi publisher chỉ có tối đa một giá trị nên prefetch thường ít ảnh hưởng. Với inner publisher là `Flux`, prefetch ảnh hưởng đến lượng phần tử mà operator có thể yêu cầu trước và giữ trong hàng đợi.

Ví dụ mỗi đơn hàng trả về một luồng nhiều dòng chi tiết:

```java
Flux<OrderLine> allLines = orders.flatMap(
    order -> orderService.streamLines(order.id()),
    8,   // tối đa 8 luồng đơn hàng hoạt động
    16   // yêu cầu trước tối đa 16 phần tử từ mỗi luồng con
);
```

Ở đây có tối đa tám publisher con hoạt động, mỗi publisher có thể được yêu cầu trước 16 phần tử theo chính sách prefetch. Đây không phải cam kết rằng luôn có chính xác 128 object nằm trong bộ nhớ; queue, fusion và cách nguồn thực thi có thể ảnh hưởng lượng thực tế. Tuy nhiên, concurrency và prefetch cùng quyết định mức độ dữ liệu có thể được đưa vào pipeline trước khi downstream tiêu thụ hết.

Nếu downstream xử lý chậm, giảm prefetch có thể giảm dữ liệu đệm. Nếu prefetch quá thấp, pipeline có thể tạo thêm round trip request giữa operator và inner publisher. Hãy đo throughput và memory thay vì chỉ chọn giá trị nhỏ nhất.

## 5. Chọn operator theo yêu cầu thứ tự

`flatMap` cho phép các publisher con chạy đồng thời và phát kết quả ngay khi sẵn sàng. Vì vậy, thứ tự đầu ra có thể khác thứ tự phần tử nguồn.

```java
Flux<String> result = Flux.just("A", "B", "C")
    .flatMap(value -> remoteLookup(value), 3);
```

Nếu lời gọi cho B hoàn tất trước A, kết quả của B có thể được phát trước A. Đây là hành vi phù hợp khi các phần tử độc lập và throughput quan trọng hơn thứ tự.

Ba lựa chọn thường gặp:

| Operator | Số inner publisher hoạt động | Thứ tự đầu ra | Khi phù hợp |
|---|---:|---|---|
| `concatMap(mapper)` | 1 | Giữ thứ tự nguồn. | Các thao tác phụ thuộc thứ tự hoặc cần xử lý tuần tự. |
| `flatMap(mapper, concurrency, prefetch)` | Tối đa `concurrency`. | Có thể xen kẽ theo thời điểm hoàn tất. | Các thao tác độc lập, cần concurrency có giới hạn. |
| `flatMapSequential(mapper, concurrency, prefetch)` | Tối đa `concurrency`. | Giữ thứ tự nguồn khi phát kết quả. | Muốn chạy đồng thời nhưng kết quả phải theo thứ tự đầu vào. |

### `concatMap`: đơn giản và tuần tự

```java
Flux<Receipt> receipts = orders.concatMap(order ->
    paymentService.charge(order)
        .map(payment -> new Receipt(order.id(), payment.id()))
);
```

Chỉ một publisher con được xử lý tại một thời điểm. Điều này giữ thứ tự và tránh nhiều thao tác ghi đồng thời. Đổi lại, một thao tác chậm sẽ làm các phần tử sau phải chờ.

### `flatMapSequential`: đồng thời nhưng phát theo thứ tự

```java
Flux<EnrichedOrder> ordered = orders.flatMapSequential(
    order -> customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer)),
    8,
    1
);
```

Tối đa tám publisher con có thể chạy cùng lúc. Nếu publisher con thứ hai hoàn tất trước publisher con thứ nhất, kết quả thứ hai có thể phải chờ trong buffer cho đến khi kết quả đầu tiên sẵn sàng. Cách này giữ thứ tự đầu ra nhưng có thể tăng bộ nhớ và độ trễ khi một publisher con đầu luồng bị chậm.

Đừng dùng `flatMapSequential` nếu thứ tự không có ý nghĩa nghiệp vụ. `flatMap` thường tận dụng kết quả sớm hơn và tránh phải giữ kết quả chỉ để chờ thứ tự.

## 6. Giới hạn công việc blocking bằng `boundedElastic`

Khi phải tích hợp thư viện đồng bộ, hãy đưa lời gọi vào `Mono.fromCallable` hoặc `Flux.defer` và dùng `boundedElastic`. Đồng thời, giới hạn số publisher con để không gửi quá nhiều tác vụ blocking vào scheduler.

```java
int maxBlockingCalls = 12;

Flux<LegacyResult> results = requests.flatMap(
    request -> Mono.fromCallable(() -> legacyClient.execute(request))
        .subscribeOn(Schedulers.boundedElastic()),
    maxBlockingCalls,
    1
);
```

`boundedElastic` dành cho tác vụ blocking có giới hạn; `flatMap` đảm bảo pipeline này chỉ có tối đa 12 publisher con đang hoạt động. Nếu mỗi tác vụ blocking chiếm một worker trong suốt thời gian chờ, concurrency hữu hạn giúp kiểm soát số worker mà pipeline này có thể sử dụng.

Không nên chuyển một lời gọi blocking lên `Schedulers.parallel()`. Scheduler đó dành cho công việc CPU-bound không blocking. Cũng không nên gọi `block()` trong mapper để chờ kết quả. Hãy trả publisher con để `flatMap` phối hợp vòng đời và cancellation.

Nếu thư viện blocking không hỗ trợ interrupt hoặc cancellation, hủy subscription có thể không dừng lời gọi đang chạy ngay lập tức. Hãy cấu hình timeout ở client/driver và theo dõi thời gian hoàn tất của các worker.

## 7. Giới hạn concurrency không phải rate limit

Concurrency giới hạn số thao tác đang hoạt động cùng lúc. Rate limit giới hạn số thao tác bắt đầu trong một đơn vị thời gian. Hai giới hạn này giải quyết hai vấn đề khác nhau.

Ví dụ, nếu mỗi request hoàn tất trong 5 ms và `flatMap` concurrency là 10, hệ thống có thể bắt đầu rất nhiều request mỗi giây vì các slot được giải phóng nhanh. Điều đó vẫn có thể vượt quota 100 request/giây của dịch vụ bên ngoài.

| Cơ chế | Giới hạn | Ví dụ mục tiêu |
|---|---|---|
| `flatMap(..., 10)` | Tối đa 10 publisher con đang hoạt động. | Không quá 10 request đồng thời. |
| Rate limiter/token bucket | Tối đa một số request trong một cửa sổ thời gian. | Không quá 100 request/giây. |
| `limitRate(32)` | Điều tiết các đợt request upstream theo demand. | Không request upstream một lượng quá lớn trong một đợt. |
| `delayElements(...)` | Trì hoãn tín hiệu giữa các phần tử downstream. | Tạo khoảng cách thời gian trong một luồng đơn giản. |

`limitRate` không phải rate limiter theo giây. Nó thay đổi cách operator yêu cầu dữ liệu từ upstream, không bảo đảm số request đến một API trong một giây. `delayElements` cũng không phải giải pháp tổng quát cho quota khi có nhiều subscription hoặc nhiều instance.

Nếu dependency quy định quota, hãy dùng rate limiter chuyên dụng hoặc cơ chế token bucket được chia sẻ phù hợp với phạm vi quota. Kết hợp rate limit với giới hạn concurrency để bảo vệ cả tốc độ lẫn số request đang bay.

## 8. Đặt giới hạn ở đúng ranh giới dependency

Một pipeline có thể gọi HTTP, database và một dịch vụ tính toán. Không nên dùng một concurrency lớn cho toàn bộ chuỗi nếu mỗi dependency có capacity khác nhau.

```java
Flux<EnrichedOrder> enriched = orders
    .flatMap(order ->
        customerClient.findById(order.customerId())
            .flatMap(customer ->
                inventoryRepository.findBySku(order.sku())
                    .map(inventory -> new EnrichedOrder(
                        order, customer, inventory
                    ))
                    .flatMap(result -> pricingClient.quote(result)
                        .map(result::withQuote)
                    )
            ),
        16,
        1
    );
```

Ví dụ trên giới hạn số đơn hàng đang đi qua chuỗi xử lý ở mức 16, nhưng các thao tác nối tiếp bên trong mỗi đơn hàng vẫn có capacity riêng. Nếu cần kiểm soát chính xác hơn, tách từng ranh giới thành adapter hoặc service có giới hạn riêng:

```java
Flux<Customer> customers = orders.flatMap(
    order -> customerClient.findById(order.customerId()),
    20,
    1
);

Flux<Inventory> inventories = skuRequests.flatMap(
    request -> inventoryRepository.findBySku(request.sku()),
    8,
    1
);
```

Ví dụ minh họa các giới hạn riêng, không phải khuyến nghị chạy hai pipeline độc lập nếu dữ liệu cần được ghép theo đơn hàng. Trong code thực tế, có thể xây dựng service adapter nhận một request và áp dụng semaphore/rate limiter hoặc giới hạn concurrency ở nơi sở hữu dependency.

Nếu một publisher con thực hiện nhiều request bên trong, giới hạn ở outer `flatMap` chỉ giới hạn số publisher con, không nhất thiết giới hạn số request nội bộ. Hãy đảm bảo adapter không tự tạo fan-out không kiểm soát.

## 9. Không tạo fan-out không giới hạn bên trong mapper

Giới hạn của `flatMap` chỉ có tác dụng khi công việc được trả về trong publisher con. Đoạn mã sau vi phạm nguyên tắc đó:

```java
// Không nên: mỗi phần tử tự subscribe một loạt request riêng.
Flux<Order> unsafe = orders.doOnNext(order -> {
    for (String sku : order.skus()) {
        inventoryClient.findBySku(sku)
            .subscribe(this::recordInventory);
    }
});
```

Outer publisher không biết số publisher con được tạo trong vòng lặp. Cancel outer subscription cũng không quản lý đầy đủ các subscription độc lập. Nếu một đơn hàng có hàng nghìn SKU, số request có thể tăng đột ngột.

Hãy biến danh sách SKU thành luồng con và giới hạn concurrency ở đó:

```java
Flux<Inventory> loadInventory(Order order) {
    return Flux.fromIterable(order.skus())
        .flatMap(inventoryClient::findBySku, 8, 1);
}

Flux<OrderInventory> enriched = orders.flatMap(order ->
    loadInventory(order)
        .collectList()
        .map(items -> new OrderInventory(order, items)),
    12,
    1
);
```

Ở ví dụ này, mỗi đơn hàng có tối đa tám truy vấn inventory đang hoạt động trong luồng con; outer pipeline có tối đa 12 đơn hàng đang được xử lý. Vì vậy, số truy vấn inventory đang bay có thể lên đến khoảng 12 × 8 nếu mọi đơn hàng đều dùng đủ slot. Hãy tính giới hạn lồng nhau theo tổng capacity của dependency, không chỉ nhìn một con số concurrency riêng lẻ.

`collectList()` gom kết quả SKU của một đơn hàng vào bộ nhớ. Nếu một đơn hàng có số SKU không giới hạn, cần giới hạn kích thước hoặc xử lý streaming thay vì thu thập toàn bộ.

## 10. Retry và lỗi trong luồng con

Retry nên đặt trong publisher con để một thao tác lỗi chỉ được thử lại trong phạm vi phần tử tương ứng. Nếu đặt retry quá rộng ở ngoài, toàn bộ nguồn có thể bị đăng ký lại và các phần tử trước đó có thể được xử lý lần nữa.

```java
Retry retryPolicy = Retry.backoff(
        2,
        Duration.ofMillis(100)
    )
    .maxBackoff(Duration.ofSeconds(1))
    .jitter(0.5)
    .filter(this::isTransient);

Flux<Result> results = requests.flatMap(request ->
    remoteService.execute(request)
        .retryWhen(retryPolicy)
        .onErrorResume(error -> {
            if (isPermanent(error)) {
                return deadLetterService.record(request, error)
                    .then(Mono.empty());
            }
            return Mono.error(error);
        }),
    10,
    1
);
```

Trong ví dụ, mỗi request có tối đa hai lần retry sau lần đầu. Slot concurrency của publisher con được giữ trong lúc retry/backoff và được giải phóng khi publisher con kết thúc. Điều này giúp không tạo thêm một đợt request vô hạn trong thời gian chờ.

Nếu `onErrorResume` phục hồi lỗi và trả publisher thay thế, outer `Flux` có thể tiếp tục xử lý phần tử khác. Nếu lỗi thoát khỏi publisher con, `flatMap` mặc định có thể phát lỗi ra downstream và hủy các publisher con còn lại. Hãy chọn rõ chính sách: lỗi một phần tử có làm dừng toàn bộ batch hay được ghi nhận và tiếp tục.

Với thao tác ghi, retry cần tính lũy đẳng hoặc idempotency key. Giới hạn concurrency không ngăn side effect bị lặp nếu một lần gọi đã thành công ở server nhưng response bị mất.

## 11. Cancellation giải phóng slot và dừng công việc không còn cần thiết

Khi downstream hủy subscription, Reactor truyền cancellation về upstream và các publisher con đang hoạt động. Khi một publisher con hoàn tất hoặc bị hủy, slot concurrency tương ứng được giải phóng theo vòng đời operator.

Ví dụ một client chỉ cần năm kết quả đầu tiên:

```java
Flux<SearchResult> topResults = searchRequests
    .flatMap(searchClient::execute, 6, 1)
    .take(5);
```

Sau khi nhận đủ năm kết quả, `take(5)` hoàn tất downstream và hủy upstream. Các request còn hoạt động được yêu cầu cancel. Khả năng dừng ngay phụ thuộc client và giao thức; một request đã gửi đến server có thể vẫn được xử lý ở phía server.

Không nên bỏ qua cancellation khi viết adapter. Nếu adapter mở socket, đăng ký listener hoặc tạo tác vụ nền, cần gắn cleanup với dispose/cancel để giải phóng tài nguyên. Với nguồn có cleanup bất đồng bộ, dùng cơ chế quản lý resource phù hợp như `usingWhen` trong Reactor.

## 12. Kết hợp `limitRate` với giới hạn inner concurrency

`limitRate` điều tiết demand mà operator downstream gửi lên publisher upstream. Nó hữu ích khi muốn chia request thành các đợt nhỏ, nhưng không thay thế giới hạn publisher con.

```java
Flux<Result> results = source
    .limitRate(128)
    .flatMap(this::callDependency, 12, 1);
```

Trong ví dụ:

- `limitRate(128)` điều chỉnh cách `flatMap` yêu cầu phần tử từ `source`.
- `flatMap(..., 12, 1)` giới hạn tối đa 12 publisher con đang hoạt động.
- `prefetch = 1` điều chỉnh request trước từ mỗi inner publisher.

Nếu nguồn là một adapter có buffer nội bộ hoặc broker đã fetch batch trước, `limitRate` không thể thu hồi dữ liệu đã được lấy vào bộ nhớ. Cần cấu hình prefetch/fetch của adapter và broker tương ứng.

Không nên thêm `onBackpressureBuffer()` với capacity lớn để che giấu downstream chậm. Buffer chỉ giữ dữ liệu chờ; nếu tốc độ đầu vào lâu dài cao hơn tốc độ xử lý, queue sẽ đầy hoặc bộ nhớ tăng đến giới hạn. Hãy giảm concurrency đầu vào, điều tiết nguồn, giới hạn buffer hoặc tăng capacity có kiểm soát.

## 13. Xử lý CPU-bound và blocking theo cách khác nhau

Giới hạn publisher con và chọn scheduler là hai quyết định riêng.

### Công việc CPU-bound

Với phép biến đổi tính toán nặng, số công việc đồng thời nên tương ứng với số core và mức độ cạnh tranh tài nguyên. Có thể dùng `parallel()` cùng `runOn()` cho các phép biến đổi độc lập:

```java
int cpuParallelism = Runtime.getRuntime().availableProcessors();

Flux<Score> scores = inputs
    .parallel(cpuParallelism)
    .runOn(Schedulers.parallel())
    .map(this::calculateScore)
    .sequential();
```

`parallel(cpuParallelism)` chia luồng thành các rail; `runOn` xác định scheduler thực thi từng rail; `sequential()` ghép kết quả thành `Flux` trở lại. Cách này phù hợp với phép tính CPU độc lập, không blocking. Nó không phải cách thay thế trực tiếp cho `flatMap` khi mỗi phần tử tạo một publisher bất đồng bộ.

### Công việc blocking

Với API blocking, dùng `boundedElastic` và giới hạn số publisher con:

```java
Flux<LegacyResult> results = inputs.flatMap(
    input -> Mono.fromCallable(() -> blockingClient.call(input))
        .subscribeOn(Schedulers.boundedElastic()),
    8,
    1
);
```

Concurrency 8 giới hạn số tác vụ blocking đang hoạt động từ pipeline này. `boundedElastic` có capacity hữu hạn; nếu nhiều pipeline khác cũng dùng chung scheduler, cần quan sát tổng tải và cân nhắc scheduler được cấu hình riêng cho workload.

Không dùng `parallel()` cho JDBC hoặc lời gọi mạng đồng bộ. Không dùng `boundedElastic` cho vòng lặp CPU nặng kéo dài nếu có thể xử lý trên scheduler CPU-bound.

## 14. Tính giới hạn lồng nhau và ngân sách tài nguyên

Một pipeline có thể có nhiều tầng fan-out. Ví dụ, mỗi đơn hàng gọi tối đa 4 API khách hàng và mỗi khách hàng gọi tối đa 3 dịch vụ thông tin khác. Trong trường hợp tất cả nhánh cùng hoạt động, số thao tác ở tầng sâu có thể lên đến 12 cho mỗi đơn hàng đang xử lý.

Nếu outer concurrency là 10, giới hạn lý thuyết ở tầng sâu có thể là 10 × 4 × 3 = 120 publisher con, trước khi tính các giới hạn riêng ở từng adapter. Vì vậy, hãy tính tổng fan-out khi lồng `flatMap`.

Một bảng ngân sách ví dụ:

| Tầng | Concurrency mỗi parent | Parent đồng thời | Giới hạn lý thuyết ở tầng |
|---|---:|---:|---:|
| Đơn hàng | — | 10 | 10 |
| API khách hàng | 4 | 10 | 40 |
| API hồ sơ phụ | 3 | 40 | 120 |

Nếu API hồ sơ phụ chỉ cho phép 50 request đồng thời, giới hạn 120 là quá cao. Hãy giảm concurrency ở tầng con, dùng rate limiter chung hoặc tách xử lý thành queue có kiểm soát.

Với nhiều instance service, concurrency trong một process không phải giới hạn toàn hệ thống. Nếu mỗi instance cho phép 20 request đồng thời và có 10 instance, dependency có thể nhận đến 200 request đồng thời. Cần phối hợp giới hạn per-instance với quota toàn cluster hoặc capacity của dependency.

## 15. Kiểm thử concurrency có giới hạn

Có thể dùng `AtomicInteger` để đo số publisher con đang hoạt động cao nhất trong một test. Dùng `Mono.delay` và scheduler ảo để mô phỏng tác vụ bất đồng bộ mà không cần `Thread.sleep`.

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maximum = new AtomicInteger();

StepVerifier.withVirtualTime(() -> Flux.range(1, 20)
    .flatMap(value -> Mono.defer(() -> {
            int now = active.incrementAndGet();
            maximum.accumulateAndGet(now, Math::max);

            return Mono.delay(Duration.ofSeconds(1))
                .map(ignored -> value)
                .doFinally(signal -> active.decrementAndGet());
        }),
        4,
        1
    ))
    .thenAwait(Duration.ofSeconds(10))
    .expectNextCount(20)
    .verifyComplete();

assertTrue(maximum.get() <= 4);
assertEquals(0, active.get());
```

Test xác minh số publisher con đang hoạt động không vượt quá bốn và mọi publisher đã kết thúc khi pipeline hoàn tất. `Mono.defer` đặt phép tăng bộ đếm tại thời điểm inner publisher được subscribe; `doFinally` giảm bộ đếm khi complete, error hoặc cancel.

Trong test dùng scheduler ảo, publisher thời gian phải được tạo bên trong supplier của `withVirtualTime` để scheduler ảo được cài đặt trước khi pipeline khởi tạo. Nếu một nguồn dùng scheduler tùy chỉnh không được thay thế, `thenAwait` không điều khiển được clock của nguồn đó.

### Kiểm thử thứ tự của `flatMapSequential`

Tạo inner publisher có thời gian hoàn tất khác nhau rồi xác minh kết quả vẫn theo thứ tự đầu vào. Với `flatMap`, không nên assert thứ tự nếu nghiệp vụ không yêu cầu; hãy kiểm tra tập kết quả hoặc dùng `expectNextMatches` phù hợp.

### Kiểm thử lỗi và cancellation

Ngoài concurrency tối đa, nên xác minh:

- Một inner publisher lỗi có làm dừng toàn bộ outer stream theo chính sách hay không.
- `onErrorResume` trong inner có giúp các phần tử khác tiếp tục không.
- Cancel downstream có hủy các inner publisher còn hoạt động không.
- Slot concurrency được giải phóng khi inner complete, error hoặc cancel.
- Retry nằm trong inner có giữ giới hạn tổng số publisher con đang hoạt động không.
- Nguồn upstream không bị yêu cầu quá mức khi downstream chậm.

## 16. Quan sát tải và điều chỉnh giới hạn trong production

Concurrency cần được xác nhận bằng metric. Một giá trị phù hợp trong môi trường local có thể quá cao khi nhiều instance chạy đồng thời hoặc dependency có tải nền.

Nên theo dõi:

- Số publisher con đang hoạt động và số slot concurrency đã sử dụng.
- Số phần tử đang chờ được xử lý và thời gian chờ trong queue.
- Throughput đầu vào/đầu ra theo giây.
- Latency trung bình, p95 và p99 của mỗi dependency.
- Tỷ lệ timeout, lỗi, retry và rate limit.
- Connection pool active/idle/pending và thời gian chờ lấy connection.
- Scheduler active threads, queue và thời gian chờ tác vụ.
- Bộ nhớ heap, garbage collection và kích thước buffer.
- Consumer lag nếu nguồn đến từ message broker.

### Dấu hiệu concurrency quá cao

- Latency của dependency tăng khi tăng concurrency nhưng throughput không tăng tương ứng.
- Connection pool có nhiều request chờ lấy connection.
- Tỷ lệ timeout, 429 hoặc 503 tăng.
- Queue và heap tăng theo tải.
- Số retry tăng khiến dependency càng quá tải.

### Dấu hiệu concurrency quá thấp

- Dependency còn capacity nhưng throughput của ứng dụng thấp.
- Connection pool thường xuyên nhàn rỗi.
- Queue upstream tăng dù downstream có khả năng xử lý thêm.
- Latency của từng thao tác thấp nhưng tổng thời gian hoàn thành batch cao do xử lý tuần tự không cần thiết.

Điều chỉnh từng bước, thay đổi một giới hạn tại một thời điểm và so sánh throughput, latency cùng tài nguyên. Không tăng concurrency chỉ vì CPU còn thấp; workload có thể đang bị giới hạn bởi database, network hoặc quota.

## 17. Tình huống thực tế: làm giàu dữ liệu đơn hàng với giới hạn API

Một batch xử lý 20.000 đơn hàng. Mỗi đơn hàng cần gọi API khách hàng và API tính giá. Dịch vụ khách hàng cho phép tối đa 30 request đồng thời; dịch vụ tính giá chỉ cho phép 12. Connection pool database có 40 connection nhưng cần giữ lại một phần cho request trực tuyến.

Có thể đặt giới hạn ở từng ranh giới:

```java
Flux<EnrichedOrder> enrich(Flux<Order> orders) {
    return orders.flatMap(order ->
        customerClient.findById(order.customerId())
            .flatMap(customer -> pricingClient.quote(order, customer)
                .map(quote -> new EnrichedOrder(order, customer, quote))
            ),
        12,
        1
    );
}
```

Outer concurrency 12 giới hạn số đơn hàng đang đi qua chuỗi. Vì mỗi đơn hàng chỉ gọi customer rồi mới gọi pricing, số request pricing đang hoạt động tối đa cũng không vượt quá 12 trong ví dụ này. Giới hạn đó nằm dưới capacity 12 của pricing service. Nếu bước customer có thể được chạy song song độc lập với pricing hoặc có fan-out riêng, cần đặt giới hạn adapter tương ứng và tính lại tổng số request.

Khi lưu kết quả:

```java
Mono<Void> processBatch(Flux<Order> orders) {
    return enrich(orders)
        .flatMap(
            enrichedOrder -> orderRepository.save(enrichedOrder),
            8,
            1
        )
        .then();
}
```

Ví dụ minh họa bước lưu có concurrency 8. Trong một pipeline production, có thể nối trực tiếp các bước để giữ giới hạn và lỗi trong cùng chuỗi, đồng thời bảo đảm transaction và idempotency phù hợp. Không nên subscribe riêng cho từng bước hoặc gom toàn bộ 20.000 kết quả vào một danh sách nếu không cần.

Nếu pricing service có quota 100 request/giây, concurrency 12 vẫn chưa đủ để bảo đảm quota. Cần thêm rate limiter theo đúng phạm vi quota. Nếu batch chạy trên nhiều instance, limiter phải phối hợp giữa các instance hoặc quota phải được chia rõ cho từng instance.

## 18. Checklist giới hạn luồng con an toàn

- Dùng `flatMap(mapper, concurrency, prefetch)` thay vì tạo subscription con fire-and-forget.
- Chọn concurrency theo capacity của dependency, connection pool, bộ nhớ và tổng tải của các instance.
- Hiểu concurrency giới hạn publisher con đang hoạt động, không phải số thread.
- Chọn prefetch riêng theo cardinality và tốc độ tiêu thụ của inner publisher.
- Dùng `concatMap` khi cần tuần tự; dùng `flatMapSequential` khi cần đồng thời nhưng giữ thứ tự phát.
- Tính fan-out lồng nhau và tổng request có thể đến dependency.
- Đặt giới hạn ở đúng ranh giới HTTP, database, broker và tác vụ blocking.
- Dùng rate limiter riêng khi dependency giới hạn request/giây; không nhầm với `limitRate`.
- Không gọi `subscribe()` bên trong mapper hoặc callback để tạo công việc ngoài pipeline.
- Đặt retry trong phạm vi inner publisher phù hợp, giới hạn số lần và bảo vệ side effect bằng idempotency.
- Đảm bảo cancellation truyền đến publisher con và cleanup tài nguyên được thực hiện.
- Kiểm thử concurrency tối đa, thứ tự, lỗi và cancel bằng `StepVerifier`.
- Theo dõi active work, queue, latency, throughput, retry, pool và scheduler metrics.
- Điều chỉnh dựa trên tải thực tế; tránh tăng concurrency khi dependency đã bão hòa.

Giới hạn publisher con giúp pipeline reactive duy trì lượng công việc đang hoạt động trong phạm vi mà dependency và ứng dụng có thể phục vụ. `flatMap` cung cấp concurrency tường minh; `concatMap` và `flatMapSequential` đáp ứng yêu cầu thứ tự khác nhau. Khi kết hợp các giới hạn đó với prefetch, rate limiter, scheduler, cancellation và metric, ứng dụng có thể tăng throughput mà không tạo fan-out vượt khả năng hệ thống.
