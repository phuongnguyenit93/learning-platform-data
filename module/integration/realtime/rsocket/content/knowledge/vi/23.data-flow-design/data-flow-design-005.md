# Dùng `map`, `flatMap` và `concatMap` theo yêu cầu đồng thời và thứ tự

Trong ứng dụng RSocket dùng Reactor, dữ liệu thường đi qua các pipeline `Mono<T>` hoặc `Flux<T>`. Ba operator `map`, `flatMap` và `concatMap` đều biến đổi dữ liệu, nhưng chúng có ngữ nghĩa khác nhau về kiểu kết quả, cách subscribe publisher con, mức độ đồng thời và thứ tự phát phần tử.

- Dùng **`map`** khi mỗi phần tử được chuyển đổi đồng bộ thành đúng một giá trị khác.
- Dùng **`flatMap`** khi mỗi phần tử tạo ra một publisher khác và các publisher con có thể được xử lý đồng thời.
- Dùng **`concatMap`** khi mỗi phần tử tạo ra một publisher khác nhưng cần xử lý tuần tự, giữ thứ tự nguồn.

Chọn đúng operator giúp thiết kế luồng dữ liệu rõ ràng, tận dụng concurrency khi phù hợp và tránh đảo thứ tự các thao tác nghiệp vụ trên cùng một tài nguyên.

## 1. Ba operator giải quyết ba nhu cầu khác nhau

Giả sử một RSocket requester nhận các báo giá từ server và cần chuyển đổi hoặc gọi thêm dịch vụ để làm giàu dữ liệu.

| Operator | Hàm biến đổi | Publisher con | Thứ tự kết quả | Mức đồng thời |
|---|---|---|---|---|
| `map` | `T -> R` | Không tạo publisher con | Giữ thứ tự nguồn | Xử lý từng phần tử theo pipeline; không tự tạo async concurrency |
| `flatMap` | `T -> Publisher<R>` | Có | Không đảm bảo giữ thứ tự nguồn | Có thể subscribe nhiều publisher con đồng thời |
| `concatMap` | `T -> Publisher<R>` | Có | Giữ thứ tự nguồn | Subscribe publisher con tuần tự, chờ publisher hiện tại kết thúc |

Sơ đồ tổng quát:

```text
Nguồn: A, B, C

map:
  A -> a'
  B -> b'       => a', b', c'
  C -> c'

flatMap:
  A -> publisher A --\
  B -> publisher B ----> kết quả có thể xen kẽ theo thời điểm hoàn tất
  C -> publisher C --/

concatMap:
  A -> publisher A -> hoàn tất
  B -> publisher B -> hoàn tất   => kết quả A rồi B rồi C
  C -> publisher C -> hoàn tất
```

Điểm quan trọng: `flatMap` và `concatMap` không chỉ khác nhau ở tốc độ. Chúng thể hiện hai hợp đồng xử lý khác nhau: cho phép các tác vụ độc lập chạy đồng thời, hoặc bắt buộc hoàn tất theo thứ tự.

## 2. `map`: chuyển đổi đồng bộ một phần tử thành một phần tử

`map` áp dụng một hàm đồng bộ cho từng giá trị được phát ra. Mỗi input tạo đúng một output nếu hàm chạy thành công. Operator không tự subscribe một publisher mới và không tự biến một lời gọi blocking thành bất đồng bộ.

```java
Flux<QuoteView> views = quoteService.streamQuotes("ACME")
    .map(quote -> new QuoteView(
        quote.symbol(),
        quote.price(),
        quote.updatedAt()));
```

Trong ví dụ, mỗi `Quote` được chuyển thành một `QuoteView`. Số phần tử và thứ tự vẫn tương ứng với nguồn. Đây là lựa chọn phù hợp cho các phép biến đổi như:

- Chuyển DTO sang view model.
- Chuẩn hóa chuỗi hoặc đơn vị đo.
- Trích xuất một trường từ object.
- Tính một giá trị thuần từ dữ liệu đầu vào.
- Chuyển `Payload` thành object đã giải mã, với việc quản lý ownership phù hợp.

### `map` không làm cho code trở thành bất đồng bộ

Đoạn sau vẫn gọi một phương thức đồng bộ trên luồng đang thực thi:

```java
Flux<QuoteView> views = quotes
    .map(quote -> blockingRiskClient.lookup(quote.symbol()));
```

Nếu `lookup(...)` chặn thread để chờ mạng hoặc I/O, `map` cũng bị chặn. `map` không tự chuyển công việc sang thread khác. Với I/O bất đồng bộ trả về `Mono`/`Flux`, dùng `flatMap` hoặc `concatMap` theo yêu cầu concurrency và thứ tự. Với API blocking, cần cô lập trên scheduler phù hợp hoặc thay bằng client non-blocking.

### Lỗi trong hàm map

Nếu hàm mapper ném exception, pipeline kết thúc bằng `onError` trừ khi có operator xử lý lỗi phía sau:

```java
Flux<Integer> parsed = Flux.just("10", "20", "invalid")
    .map(Integer::parseInt)
    .onErrorResume(NumberFormatException.class, error -> Flux.empty());
```

Trong ví dụ, lỗi parse phần tử thứ ba kết thúc nguồn `map`; `onErrorResume` chuyển lỗi thành một publisher rỗng. Những phần tử phía sau phần tử lỗi của nguồn không tiếp tục được xử lý trong pipeline đó.

## 3. `flatMap`: gọi publisher con và cho phép concurrency

`flatMap` dùng khi hàm biến đổi trả về một `Publisher`. Reactor subscribe các publisher con và hợp nhất phần tử chúng phát ra vào một luồng kết quả chung.

Ví dụ, mỗi báo giá cần gọi một RSocket route khác để lấy điểm rủi ro:

```java
Flux<EnrichedQuote> enriched = quoteService.streamQuotes("ACME")
    .flatMap(quote -> requester
        .route("risk.score")
        .data(new RiskRequest(quote.symbol()))
        .retrieveMono(RiskScore.class)
        .map(score -> new EnrichedQuote(quote, score)));
```

Mỗi `Quote` tạo ra một request-response RSocket độc lập. Các request có thể chạy chồng lấp; khi response nào về trước, kết quả tương ứng có thể được phát trước.

Giả sử nguồn phát `A`, `B`, `C`, nhưng các publisher con hoàn tất theo thứ tự `B`, `C`, `A`. `flatMap` có thể phát kết quả theo thứ tự hoàn tất đó. Vì vậy, không được giả định output giữ nguyên thứ tự input.

```text
Nguồn:          A -------- B -------- C
Inner request:  [------ A ------]
                    [-- B --]
                         [--- C ---]
Output:             B       C       A
```

Đây là ưu điểm khi các thao tác độc lập và độ trễ khác nhau: thay vì đợi A hoàn tất mới bắt đầu B, pipeline có thể xử lý nhiều request đồng thời.

## 4. Giới hạn concurrency và prefetch của flatMap

Không nên mở concurrency không giới hạn tới dịch vụ downstream. Reactor cung cấp overload để giới hạn số publisher con đang được subscribe:

```java
Flux<EnrichedQuote> enriched = quoteService.streamQuotes("ACME")
    .flatMap(quote -> loadRiskScore(quote)
        .map(score -> new EnrichedQuote(quote, score)),
        8, 1);
```

Trong overload `flatMap(mapper, concurrency, prefetch)`:

- `concurrency = 8` giới hạn tối đa số publisher con đang hoạt động đồng thời.
- `prefetch = 1` điều chỉnh số phần tử được yêu cầu trước từ mỗi publisher con trong ví dụ này.
- Giá trị phù hợp phụ thuộc độ trễ downstream, throughput, bộ nhớ và giới hạn tài nguyên của server.

`concurrency` không phải số thread. Nó là giới hạn số inner publisher đang được xử lý đồng thời. Một inner publisher có thể chạy trên cùng thread hoặc thread khác tùy scheduler và implementation của nguồn.

`flatMap` cũng không tự tạo một thread mới cho mỗi phần tử. Nó điều phối subscriptions và hợp nhất kết quả. Nếu cần chuyển execution context, hãy dùng scheduler và operator như `publishOn`/`subscribeOn` một cách có chủ đích.

Nếu không giới hạn concurrency, một nguồn phát nhanh có thể tạo nhiều request RSocket đang chờ, làm tăng số stream đang hoạt động, bộ nhớ và tải của server. Hãy chọn giới hạn phù hợp với capacity của dịch vụ được gọi.

## 5. `concatMap`: tuần tự hóa publisher con và giữ thứ tự

`concatMap` cũng nhận mapper trả về publisher, nhưng chỉ subscribe publisher con kế tiếp sau khi publisher hiện tại hoàn tất. Kết quả vì thế giữ thứ tự theo nguồn.

```java
Flux<CommandResult> results = commandStream
    .concatMap(command -> requester
        .route("devices.command")
        .data(command)
        .retrieveMono(CommandResult.class));
```

Nếu nguồn phát `A`, `B`, `C`, publisher con của A phải hoàn tất trước khi B được subscribe; B hoàn tất trước khi C được subscribe. Output được phát theo thứ tự A, B, C.

```text
Nguồn:          A -------- B -------- C
Inner request:  [------ A ------]
                              [-- B --]
                                      [--- C ---]
Output:                  A       B       C
```

`concatMap` phù hợp khi các thao tác có phụ thuộc thứ tự, ví dụ:

- Ghi các lệnh điều khiển thiết bị theo trình tự.
- Cập nhật trạng thái của cùng một aggregate.
- Gửi sự kiện theo thứ tự nghiệp vụ yêu cầu.
- Thực hiện thao tác tiếp theo dựa trên kết quả của thao tác trước.
- Gọi một API downstream có giới hạn concurrency bằng một request tại một thời điểm.

Đổi lại, một publisher con chậm sẽ làm các phần tử phía sau phải chờ. Đây là chi phí có chủ ý để giữ thứ tự và tránh cạnh tranh trên cùng tài nguyên.

## 6. So sánh bằng một ví dụ RSocket thực tế

Giả sử một client nhận lệnh cập nhật tồn kho từ RSocket stream. Mỗi lệnh cần gọi `inventory.apply` và nhận `CommandResult`.

### Chuyển đổi dữ liệu với map

```java
Flux<InventoryCommand> commands = requester
    .route("inventory.commands")
    .data(new CommandSubscription("warehouse-1"))
    .retrieveFlux(InventoryCommand.class)
    .map(this::normalizeCommand);
```

`normalizeCommand` là phép biến đổi đồng bộ. Không có request RSocket thứ hai được mở bởi operator này.

### Gọi các request độc lập với flatMap

```java
Flux<CommandResult> results = commands
    .flatMap(command -> requester
        .route("inventory.apply")
        .data(command)
        .retrieveMono(CommandResult.class),
        16);
```

Tối đa 16 request-response inner publisher có thể hoạt động đồng thời. Nếu lệnh độc lập và server xử lý chúng an toàn song song, cách này có thể tăng throughput. Output không đảm bảo theo thứ tự lệnh nguồn.

### Giữ thứ tự với concatMap

```java
Flux<CommandResult> results = commands
    .concatMap(command -> requester
        .route("inventory.apply")
        .data(command)
        .retrieveMono(CommandResult.class));
```

Mỗi lệnh được gửi sau khi request trước đó hoàn tất. Nếu lệnh cập nhật cùng một SKU hoặc cùng một aggregate và thứ tự là một phần của quy tắc nghiệp vụ, `concatMap` thể hiện rõ yêu cầu đó.

## 7. Dùng map, flatMap và concatMap với Mono

Các operator này cũng dùng được trên `Mono`:

```java
Mono<OrderView> view = requester
    .route("orders.read")
    .data(new OrderQuery(orderId))
    .retrieveMono(Order.class)
    .map(this::toView);
```

Với `Mono`, `map` biến một giá trị response thành một giá trị khác. `flatMap` dùng khi kết quả đầu tiên cần kích hoạt một thao tác bất đồng bộ khác:

```java
Mono<OrderDetails> details = requester
    .route("orders.read")
    .data(new OrderQuery(orderId))
    .retrieveMono(Order.class)
    .flatMap(order -> requester
        .route("customers.read")
        .data(new CustomerQuery(order.customerId()))
        .retrieveMono(Customer.class)
        .map(customer -> new OrderDetails(order, customer)));
```

Ở đây, request lấy customer chỉ bắt đầu sau khi order đã được nhận vì nó phụ thuộc `customerId`. `flatMap` trên `Mono` không tạo nhiều phần tử đồng thời từ một giá trị đơn, nhưng vẫn cần thiết để nối publisher bất đồng bộ mà không tạo `Mono<Mono<T>>`.

Nếu cần chạy hai request độc lập đồng thời rồi kết hợp kết quả, dùng `Mono.zip(...)` thường diễn đạt ý định rõ hơn:

```java
Mono<OrderDashboard> dashboard = Mono.zip(
        loadOpenOrders(customerId),
        loadCreditLimit(customerId))
    .map(tuple -> new OrderDashboard(tuple.getT1(), tuple.getT2()));
```

## 8. Khi nào nên chọn operator nào?

| Tình huống | Chọn | Lý do |
|---|---|---|
| Chuyển DTO, chuẩn hóa hoặc tính giá trị đồng bộ | `map` | Một input thành một output, không cần publisher con. |
| Mỗi phần tử gọi một RSocket request độc lập | `flatMap` | Có thể xử lý nhiều request đồng thời. |
| Mỗi phần tử gọi một publisher nhưng cần đúng thứ tự | `concatMap` | Chỉ chạy inner publisher tiếp theo sau khi inner hiện tại hoàn tất. |
| Kết hợp một kết quả với một request phụ thuộc kết quả đó | `flatMap` trên `Mono` | Nối hai bước bất đồng bộ. |
| Xử lý tuần tự command trên cùng thiết bị | `concatMap` | Tránh hai command cạnh tranh và giữ thứ tự. |
| Xử lý telemetry độc lập với giới hạn tải | `flatMap` có concurrency | Tận dụng song song nhưng giới hạn số request đồng thời. |

Không chọn `flatMap` chỉ vì nó có chữ “flat” hoặc nghĩ nó luôn nhanh hơn. Nếu các thao tác phải chạy tuần tự, concurrency có thể làm hỏng trạng thái nghiệp vụ dù throughput cao hơn.

## 9. Thứ tự nguồn và thứ tự hoàn tất

`flatMap` hợp nhất kết quả từ các inner publisher theo thời điểm chúng phát ra. Nếu mỗi inner publisher chỉ phát một giá trị, thứ tự thường phản ánh publisher nào hoàn tất trước. Nếu inner publisher phát nhiều giá trị, các phần tử từ nhiều inner publisher có thể xen kẽ.

Ví dụ:

```java
Flux<String> result = Flux.just("A", "B", "C")
    .flatMap(value -> delayedResult(value));
```

Không nên kiểm thử output bằng giả định `A, B, C` trừ khi các inner publisher được thiết kế hoàn tất theo đúng thứ tự đó. Nếu cần chạy đồng thời nhưng vẫn phát kết quả theo thứ tự nguồn, Reactor có operator `flatMapSequential`; operator này subscribe các inner publisher với concurrency nhưng giữ thứ tự phát kết quả theo nguồn bằng cách đệm kết quả đến lượt. Chủ đề chính của bài này là `flatMap` không giữ thứ tự và `concatMap` giữ thứ tự bằng xử lý tuần tự.

`concatMap` giữ thứ tự output theo nguồn vì inner publisher được xử lý lần lượt. Nếu inner publisher phát nhiều giá trị, tất cả giá trị của A được phát trước khi giá trị của B bắt đầu.

## 10. Backpressure và bộ đệm

Reactor truyền demand từ subscriber ngược về upstream. Các operator có thể yêu cầu trước một lượng phần tử để giữ pipeline hoạt động, nên backpressure không đồng nghĩa mọi phần tử chỉ được yêu cầu đúng lúc downstream gọi `request(1)`.

- `map` thường chuyển tiếp demand theo quan hệ một input/one output.
- `flatMap` quản lý demand của nguồn và các inner publisher; `concurrency` và `prefetch` ảnh hưởng số công việc/giá trị có thể được giữ đồng thời.
- `concatMap` xử lý inner publisher tuần tự nhưng có thể prefetch và đệm phần tử nguồn trong khi inner hiện tại đang chạy.

Không nên dùng các operator như thể chúng không có chi phí bộ nhớ. Khi downstream chậm hoặc inner publisher có độ trễ lớn, hàng đợi có thể tích lũy. Hãy:

1. Giới hạn concurrency của `flatMap` theo capacity của downstream.
2. Chọn prefetch hợp lý cho kích thước phần tử và độ trễ.
3. Giới hạn buffer ở những nguồn có thể phát nhanh hơn consumer.
4. Định nghĩa chính sách overflow nếu nguồn là hot và không thể backpressure.
5. Theo dõi số stream RSocket đang hoạt động, request pending, độ trễ và bộ nhớ.

Backpressure của Reactor gắn với demand của RSocket `request-stream`/`request-channel` ở runtime. Khi một pipeline mở thêm nhiều request-response bằng `flatMap`, mỗi inner request là một tương tác riêng; cần giới hạn concurrency để không tạo quá nhiều stream đồng thời trên connection.

## 11. Error handling và phạm vi lỗi

Khi mapper của `map` ném exception hoặc một inner publisher của `flatMap`/`concatMap` phát lỗi, pipeline thường kết thúc bằng `onError`. Các publisher đang hoạt động có thể bị cancel khi lỗi được truyền xuống.

Ví dụ xử lý lỗi từng request con bên trong `flatMap`:

```java
Flux<CommandResult> results = commands
    .flatMap(command -> applyCommand(command)
        .onErrorResume(error -> Mono.just(
            CommandResult.failed(command.id(), error.getMessage()))),
        8);
```

Ở đây lỗi của một command được chuyển thành một kết quả thất bại, nên các command khác vẫn có thể tiếp tục. Nếu đặt `onErrorResume` bên ngoài `flatMap`, một lỗi inner có thể kết thúc toàn bộ pipeline rồi chuyển sang fallback chung.

Với `concatMap`, nếu một inner publisher phát lỗi, chuỗi tuần tự mặc định kết thúc và các phần tử sau không được xử lý. Nếu nghiệp vụ yêu cầu tiếp tục sau lỗi của từng phần tử, đặt xử lý lỗi bên trong mapper:

```java
Flux<CommandResult> results = commands
    .concatMap(command -> applyCommand(command)
        .onErrorResume(error -> Mono.just(
            CommandResult.failed(command.id(), error.getMessage()))));
```

Hãy quyết định lỗi là lỗi của một phần tử hay lỗi toàn bộ stream. Không biến mọi lỗi transport/authentication thành kết quả nghiệp vụ bình thường nếu caller cần phân biệt.

## 12. Retry: đặt bên trong hay bên ngoài mapper?

Vị trí của `retryWhen` quyết định phạm vi retry:

```java
// Retry riêng request con cho từng command.
Flux<CommandResult> perCommandRetry = commands
    .flatMap(command -> applyCommand(command)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))),
        8);

// Retry toàn bộ pipeline nguồn nếu một lỗi thoát ra ngoài.
Flux<CommandResult> wholePipelineRetry = commands
    .flatMap(this::applyCommand, 8)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
```

Retry toàn pipeline có thể subscribe lại nguồn và phát lại những phần tử đã được xử lý trước lỗi, tùy nguồn có khả năng replay hay không. Điều này có thể lặp side effect. Retry riêng inner publisher giới hạn phạm vi hơn nhưng vẫn có thể lặp thao tác nếu server đã xử lý request trước khi kết nối lỗi.

Với lệnh ghi hoặc thao tác tài chính, hãy dùng idempotency key và thiết kế server có khả năng deduplicate. Retry không tự tạo ra exactly-once semantics.

## 13. Cancellation và tài nguyên

Khi downstream hủy subscription, Reactor truyền cancellation về upstream. Với `flatMap`, các inner publisher đang hoạt động có thể bị cancel; với `concatMap`, inner publisher hiện tại và các nguồn upstream liên quan được hủy. RSocket runtime có thể gửi frame `CANCEL` cho các stream đang chạy nếu tương tác đã được mở.

Cancellation không rollback side effect đã thực hiện. Nếu một request đã ghi dữ liệu hoặc gửi lệnh tới thiết bị, hủy publisher không tự động hoàn tác hành động đó.

Khi một pipeline xử lý `Payload`/`ByteBuf`, cancellation và discard cũng cần được tính đến trong cleanup. Nếu operator loại bỏ phần tử đã được cấp phát, hãy bảo đảm reference-counted resource được release theo ownership contract; không release payload outbound sau khi đã chuyển ownership cho RSocket runtime.

## 14. Dùng concatMap khi cần tuần tự hóa theo khóa

`concatMap` tuần tự hóa toàn bộ stream. Nếu cần xử lý tuần tự trong từng nhóm (ví dụ từng thiết bị) nhưng vẫn cho phép các thiết bị khác nhau chạy song song, có thể nhóm theo khóa rồi xử lý từng nhóm bằng `concatMap`:

```java
Flux<CommandResult> results = commandStream
    .groupBy(DeviceCommand::deviceId)
    .flatMap(group -> group.concatMap(command ->
        deviceService.apply(command)));
```

Trong ví dụ, các command của cùng một `deviceId` được xử lý theo thứ tự trong group; các group khác nhau có thể chạy đồng thời nhờ `flatMap` bên ngoài. Cần chú ý số lượng group và vòng đời của group; `groupBy` trên cardinality rất lớn hoặc key không giới hạn có thể giữ nhiều group và gây áp lực bộ nhớ.

Nếu thứ tự cần được giữ trên toàn bộ nguồn, chỉ dùng `concatMap` trực tiếp là cách đơn giản hơn. Nếu cần tuần tự theo aggregate, hãy xác định khóa và chính sách quản lý group rõ ràng.

## 15. Kiểm thử thứ tự và concurrency bằng StepVerifier

`StepVerifier` có thể kiểm tra thứ tự output, completion và lỗi. Với `concatMap`, dùng nguồn có kết quả xác định để khẳng định thứ tự:

```java
Flux<String> sequential = Flux.just("A", "B", "C")
    .concatMap(value -> delayedResult(value));

StepVerifier.create(sequential)
    .expectNext("A-result", "B-result", "C-result")
    .verifyComplete();
```

Với `flatMap`, không nên khẳng định thứ tự nếu inner publisher có thời gian hoàn tất khác nhau. Thay vào đó, kiểm tra tập kết quả hoặc kiểm soát scheduler/test publisher để kiểm tra concurrency một cách xác định.

Ví dụ kiểm tra số tác vụ đồng thời tối đa bằng bộ đếm trong test fixture:

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxActive = new AtomicInteger();

Flux<Integer> concurrent = Flux.range(1, 20)
    .flatMap(value -> Mono.defer(() -> {
        int current = active.incrementAndGet();
        maxActive.accumulateAndGet(current, Math::max);

        return Mono.delay(Duration.ofMillis(10))
            .map(ignored -> value)
            .doFinally(signal -> active.decrementAndGet());
    }), 4);

StepVerifier.create(concurrent)
    .expectNextCount(20)
    .verifyComplete();

assertThat(maxActive.get()).isLessThanOrEqualTo(4);
```

Test dùng concurrency `4`, nên số publisher con hoạt động đồng thời không vượt quá giới hạn đó. Với test chạy trên scheduler song song, hãy dùng bộ đếm thread-safe và tránh assertion phụ thuộc timing quá chặt.

Các tình huống nên kiểm thử:

1. `map` giữ số lượng và thứ tự phần tử khi mapper thành công.
2. `map` phát lỗi khi mapper ném exception.
3. `flatMap` cho phép inner publisher chạy đồng thời trong giới hạn đã cấu hình.
4. `flatMap` không được giả định giữ thứ tự nguồn.
5. `concatMap` subscribe inner publisher tuần tự và giữ thứ tự output.
6. Lỗi inner được xử lý ở đúng phạm vi phần tử hoặc toàn pipeline.
7. Cancellation dừng các inner publisher đang chạy và giải phóng tài nguyên.
8. Retry không gây lặp side effect ngoài ý muốn.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `map` nhưng mapper trả `Mono<T>` | Kết quả thành `Flux<Mono<T>>`; publisher con chưa được flatten. | Dùng `flatMap` hoặc `concatMap`. |
| Dùng `flatMap` nhưng kỳ vọng giữ thứ tự nguồn | Output có thể phát theo thứ tự hoàn tất inner publisher. | Dùng `concatMap` nếu cần tuần tự; cân nhắc `flatMapSequential` nếu muốn concurrency nhưng giữ thứ tự output. |
| Dùng `concatMap` cho tác vụ hoàn toàn độc lập và chậm | Throughput giảm vì mọi inner publisher phải chờ lần lượt. | Dùng `flatMap` với concurrency có giới hạn. |
| Cho `flatMap` concurrency quá lớn | Quá nhiều RSocket request/stream đồng thời, tăng tải và bộ nhớ. | Đặt concurrency/prefetch theo capacity downstream. |
| Nghĩ `flatMap` tự tạo thread | Hiểu sai execution model và có thể chặn event loop. | Dùng client non-blocking; chọn scheduler rõ ràng cho tác vụ blocking. |
| Dùng `concatMap` rồi mong các phần tử sau vượt qua inner publisher đang treo | Pipeline bị chặn đúng theo semantics tuần tự. | Đặt timeout/cancel phù hợp hoặc chọn concurrency nếu nghiệp vụ cho phép. |
| Đặt `onErrorResume` bên ngoài khi chỉ muốn bỏ qua lỗi một phần tử | Một lỗi inner có thể kết thúc toàn stream trước fallback. | Xử lý lỗi bên trong mapper của `flatMap`/`concatMap`. |
| Retry toàn pipeline có side effect | Nguồn có thể chạy lại và lặp các thao tác đã thành công. | Retry inner có kiểm soát và dùng idempotency key. |
| Không giới hạn buffer của nguồn hot | Dữ liệu chờ tăng và có thể làm cạn bộ nhớ. | Dùng backpressure, giới hạn buffer và chính sách overflow. |

## 17. Quy trình chọn operator

Trước khi viết pipeline, hãy trả lời ba câu hỏi:

1. **Hàm biến đổi có trả về publisher không?** Nếu không, thường dùng `map`. Nếu có, chọn `flatMap` hoặc `concatMap`.
2. **Các publisher con có được chạy đồng thời không?** Nếu được, dùng `flatMap` và giới hạn concurrency. Nếu không, dùng `concatMap`.
3. **Output có phải giữ thứ tự nguồn không?** Nếu có, `concatMap` là lựa chọn rõ ràng; nếu cần concurrency và vẫn giữ thứ tự phát output, xem xét `flatMapSequential`.

Ví dụ áp dụng:

```java
Flux<CommandResult> pipeline = requester
    .route("devices.{deviceId}.commands", deviceId)
    .data(new CommandSubscription())
    .retrieveFlux(DeviceCommand.class)
    .map(this::validateAndNormalize)       // chuyển đổi đồng bộ
    .concatMap(command -> deviceService.apply(command)); // giữ thứ tự thiết bị
```

Nếu mỗi command độc lập và server hỗ trợ xử lý đồng thời, thay `concatMap` bằng `flatMap(command -> deviceService.apply(command), concurrency)` để tăng throughput nhưng chấp nhận output không còn theo thứ tự nguồn.

## Kết luận

`map` dành cho phép biến đổi đồng bộ một phần tử thành một phần tử. `flatMap` nối các publisher con và cho phép xử lý đồng thời, phù hợp với các request độc lập nhưng không bảo đảm thứ tự output. `concatMap` xử lý publisher con tuần tự và giữ thứ tự nguồn, phù hợp với command hoặc side effect phụ thuộc thứ tự. Trong pipeline RSocket, hãy cân nhắc concurrency, prefetch, backpressure, lỗi, retry và cancellation cùng với semantics nghiệp vụ. Chọn operator theo yêu cầu đồng thời và thứ tự sẽ giúp luồng dữ liệu reactive vừa hiệu quả vừa có hành vi dự đoán được.
