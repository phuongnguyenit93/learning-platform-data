# Phân biệt biến đổi dữ liệu với quan sát tác dụng phụ

Trong **REACTIVE_PROGRAMMING**, pipeline `Mono` và `Flux` mô tả cách dữ liệu đi qua các bước xử lý bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Một pipeline thường vừa cần biến đổi dữ liệu để tạo kết quả nghiệp vụ, vừa cần ghi log, đo metrics hoặc theo dõi vòng đời subscription. Hai nhóm công việc này có mục đích khác nhau: **toán tử biến đổi tạo ra luồng dữ liệu đầu ra mới**, còn **toán tử quan sát tác dụng phụ theo dõi tín hiệu mà không chủ đích thay đổi phần tử đang đi qua**.

Phân biệt rõ hai nhóm giúp pipeline dễ đọc, dễ kiểm thử và dễ dự đoán. Nó cũng tránh những lỗi như ghi log rồi vô tình làm thay đổi dữ liệu, gọi dịch vụ bên ngoài bằng một subscription tách rời hoặc xử lý lỗi quan sát như thể đã phục hồi lỗi.

## 1. Hai mục đích khác nhau trong một pipeline

Hãy xem một luồng đơn hàng. Ứng dụng cần loại bỏ đơn không hợp lệ, chuẩn hóa mã đơn và ghi nhận số lượng đơn đi qua pipeline. Các thao tác này có vai trò khác nhau:

- `filter` quyết định phần tử nào được tiếp tục đi xuống.
- `map` tạo giá trị đã chuẩn hóa từ phần tử đầu vào.
- `doOnNext` quan sát phần tử đi qua một vị trí, chẳng hạn để ghi log hoặc tăng bộ đếm metrics.

```java
Flux<Order> acceptedOrders = orderSource()
    .filter(Order::isValid)
    .map(Order::normalize)
    .doOnNext(order -> metrics.increment("orders.accepted"));
```

`filter` và `map` quyết định dữ liệu mà downstream nhận được. `doOnNext` thực hiện một hành động quan sát khi có phần tử đi qua; nó không trả về một `Order` mới và không thay thế phần tử trong luồng.

Có thể hình dung pipeline như sau:

```text
Publisher<Order>
      |
      v
   filter       -- quyết định giữ hay bỏ phần tử
      |
      v
    map         -- tạo giá trị đầu ra đã biến đổi
      |
      v
  doOnNext      -- quan sát, ghi log hoặc đo metrics
      |
      v
  Subscriber
```

Một quy tắc dễ nhớ là: nếu câu hỏi là “downstream sẽ nhận dữ liệu gì?”, hãy tìm các toán tử biến đổi. Nếu câu hỏi là “tôi muốn biết điều gì vừa xảy ra?”, hãy cân nhắc toán tử quan sát.

## 2. Toán tử biến đổi thay đổi luồng dữ liệu

Toán tử biến đổi nhận tín hiệu từ upstream và định nghĩa dữ liệu hoặc luồng tín hiệu mà downstream sẽ quan sát. Một số toán tử thường dùng:

| Toán tử | Vai trò | Ảnh hưởng đến dữ liệu |
|---|---|---|
| `map` | Ánh xạ từng phần tử sang một giá trị khác | Thay kiểu hoặc nội dung phần tử |
| `filter` | Kiểm tra điều kiện cho từng phần tử | Loại bỏ phần tử không đạt điều kiện |
| `flatMap` | Ánh xạ mỗi phần tử thành một Publisher rồi hợp nhất kết quả | Một đầu vào có thể tạo không, một hoặc nhiều đầu ra; các kết quả có thể xen kẽ |
| `concatMap` | Ánh xạ mỗi phần tử thành Publisher và nối kết quả theo thứ tự | Giữ thứ tự giữa các inner Publisher |
| `switchMap` | Chuyển sang Publisher mới nhất, hủy Publisher trước đó | Kết quả cũ có thể bị hủy khi có đầu vào mới |
| `distinct` | Loại bỏ phần tử trùng theo quy tắc so sánh | Downstream không nhận các phần tử trùng |
| `scan` | Tích lũy trạng thái qua từng phần tử | Phát trạng thái tích lũy sau mỗi bước |

Ví dụ với `map` và `filter`:

```java
Flux<String> normalizedIds = Flux.just(" ord-01 ", "", " ord-02 ")
    .map(String::trim)
    .filter(id -> !id.isEmpty())
    .map(String::toUpperCase);
```

Downstream nhận `ORD-01` và `ORD-02`. Các toán tử đã định nghĩa rõ cách dữ liệu được chuyển từ đầu vào sang đầu ra. Nếu đổi thứ tự `filter` và `map`, kết quả có thể khác khi phép biến đổi ảnh hưởng đến điều kiện lọc.

Với `flatMap`, công việc bất đồng bộ trở thành một phần của luồng:

```java
Flux<OrderView> views = orderSource()
    .flatMap(order -> customerClient.findById(order.customerId())
        .map(customer -> OrderView.from(order, customer)));
```

Mỗi đơn hàng được ánh xạ thành một `Mono<Customer>`, rồi tạo `OrderView` khi dữ liệu khách hàng sẵn sàng. Kết quả của thao tác bất đồng bộ tham gia vào cùng pipeline, vì vậy downstream có thể nhận lỗi, hủy đăng ký và điều tiết nhu cầu trên luồng đó. Thứ tự kết quả của `flatMap` không nhất thiết giống thứ tự đơn hàng đầu vào; nếu cần tuần tự, cân nhắc `concatMap`.

## 3. Toán tử quan sát ghi nhận điều xảy ra

Các toán tử `doOn...` trong Reactor cho phép gắn callback vào vòng đời và tín hiệu của pipeline. Chúng thường được dùng cho log, metrics, tracing, debug hoặc cập nhật trạng thái quan sát.

| Toán tử | Thời điểm callback | Dữ liệu downstream |
|---|---|---|
| `doOnSubscribe` | Khi nhận Subscription từ upstream | Không thay đổi phần tử |
| `doOnRequest` | Khi downstream yêu cầu demand | Không thay đổi phần tử |
| `doOnNext` | Khi một phần tử đi qua vị trí đặt toán tử | Vẫn là phần tử đó |
| `doOnComplete` | Khi upstream hoàn tất bình thường | Không thay đổi tín hiệu hoàn tất |
| `doOnError` | Khi upstream phát lỗi | Không tự phục hồi lỗi |
| `doOnCancel` | Khi subscription bị hủy | Không biến hủy thành hoàn tất |
| `doFinally` | Khi luồng kết thúc bằng complete, error hoặc cancel | Quan sát loại tín hiệu cuối |
| `doOnEach` | Khi một tín hiệu đi qua vị trí đặt toán tử | Không thay đổi tín hiệu |

Ví dụ:

```java
Flux<Order> orders = orderSource()
    .doOnSubscribe(subscription -> log.info("Order stream subscribed"))
    .doOnRequest(n -> log.debug("Order demand: {}", n))
    .doOnNext(order -> log.info("Received order {}", order.id()))
    .doOnError(error -> log.error("Order stream failed", error))
    .doFinally(signal -> log.info("Order stream ended: {}", signal));
```

Các callback trên không tạo `Order` mới, không lọc phần tử và không thay thế tín hiệu lỗi bằng kết quả khác. Chúng quan sát những sự kiện xảy ra tại vị trí của chúng trong pipeline.

### `doOnNext` không phải `map`

Hai biểu thức sau có mục đích khác nhau:

```java
Flux<Order> transformed = orderSource()
    .map(order -> order.withStatus("RECEIVED"));

Flux<Order> observed = orderSource()
    .doOnNext(order -> log.info("Received {}", order.id()));
```

Trong `transformed`, hàm mapper trả về một `Order` để downstream nhận. Trong `observed`, callback trả về `void`; downstream tiếp tục nhận chính phần tử được phát từ upstream.

Không nên dùng `map` chỉ để ghi log rồi trả lại nguyên phần tử:

```java
// Có thể chạy, nhưng diễn đạt sai mục đích của bước xử lý.
Flux<Order> awkward = orderSource()
    .map(order -> {
        log.info("Received {}", order.id());
        return order;
    });
```

Nên dùng `doOnNext` cho hành động quan sát. Khi đọc code, người khác sẽ biết bước đó không chủ định biến đổi dữ liệu.

## 4. Vị trí toán tử quyết định điều gì được quan sát

Callback quan sát nhìn thấy tín hiệu tại vị trí đặt nó. Vì thế, cùng một `doOnNext` nhưng đặt trước hoặc sau `map` sẽ quan sát giá trị khác nhau:

```java
Flux<Integer> values = Flux.just("10", "20")
    .doOnNext(raw -> log.info("Raw value: {}", raw))
    .map(Integer::parseInt)
    .doOnNext(parsed -> log.info("Parsed value: {}", parsed));
```

Callback đầu tiên nhận chuỗi (`"10"`, `"20"`); callback thứ hai nhận số nguyên (`10`, `20`). Cả hai đều quan sát luồng tại hai giai đoạn khác nhau.

Với lỗi cũng vậy. `doOnError` đặt trước `onErrorResume` quan sát lỗi gốc. Nếu đặt sau `onErrorResume`, nó chỉ quan sát lỗi còn tiếp tục đi xuống sau bước phục hồi (nếu có):

```java
Mono<Profile> profile = loadProfile(userId)
    .doOnError(error -> log.warn("Original lookup failed", error))
    .onErrorResume(error -> loadGuestProfile())
    .doOnError(error -> log.error("Fallback also failed", error));
```

Nếu `loadProfile` lỗi nhưng `loadGuestProfile` thành công, callback đầu tiên chạy còn callback thứ hai không chạy. Nếu fallback cũng lỗi, callback thứ hai quan sát lỗi fallback. Đặt toán tử quan sát ở đâu là một phần của ý nghĩa pipeline.

## 5. Quan sát lỗi khác với xử lý hoặc phục hồi lỗi

`doOnError` là callback quan sát. Nó thích hợp để ghi log, tăng bộ đếm lỗi hoặc gửi thông tin chẩn đoán. Nó không biến một luồng lỗi thành luồng thành công.

```java
Mono<Profile> observed = loadProfile(userId)
    .doOnError(error -> metrics.increment("profile.lookup.errors"));
```

Nếu `loadProfile` phát `onError`, `observed` vẫn kết thúc bằng lỗi đó. Muốn chọn kết quả thay thế, dùng toán tử xử lý lỗi:

```java
Mono<Profile> recovered = loadProfile(userId)
    .doOnError(error -> log.warn("Lookup failed", error))
    .onErrorResume(error -> loadGuestProfile());
```

`onErrorResume` nhận lỗi và trả về một Publisher khác để tiếp tục pipeline. Đây là hành vi thay đổi luồng tín hiệu, khác với quan sát. Tương tự, `onErrorReturn` có thể phát một giá trị dự phòng, còn `retry` có thể đăng ký lại nguồn theo chính sách retry.

Không nên nuốt lỗi chỉ để log nếu nghiệp vụ cần biết thao tác đã thất bại. Nếu quyết định phục hồi, hãy thể hiện quyết định đó bằng toán tử chuyên dụng và kiểm thử kết quả khi cả nguồn chính lẫn nguồn dự phòng lỗi.

## 6. Tác vụ bất đồng bộ có tác dụng phụ phải tham gia pipeline

Một lỗi thường gặp là gọi một API bất đồng bộ bên trong `doOnNext` rồi tự subscribe:

```java
// Không nên: tạo một subscription tách rời khỏi pipeline chính.
Flux<Order> detached = orderSource()
    .doOnNext(order -> auditClient.record(order).subscribe());
```

Subscription bên trong không được quản lý bởi subscription chính. Pipeline ngoài có thể hoàn tất trong khi thao tác audit vẫn đang chạy; lỗi audit có thể không được truyền về downstream; cancellation của pipeline ngoài cũng không nhất thiết hủy được công việc audit.

Nếu thao tác bất đồng bộ là một phần của nghiệp vụ, hãy kết hợp Publisher đó bằng `flatMap`, `concatMap` hoặc toán tử phù hợp:

```java
Flux<Order> audited = orderSource()
    .concatMap(order ->
        auditClient.record(order)
            .thenReturn(order)
    );
```

Ở đây, mỗi thao tác audit tham gia vào pipeline. `concatMap` giữ thứ tự xử lý; nếu audit lỗi, luồng sẽ lỗi theo mặc định. Nếu audit là best-effort và lỗi không được phép làm hỏng luồng đơn hàng, hãy thể hiện chính sách đó một cách tường minh:

```java
Flux<Order> auditedBestEffort = orderSource()
    .concatMap(order ->
        auditClient.record(order)
            .doOnError(error -> log.warn("Audit failed for {}", order.id(), error))
            .onErrorResume(error -> Mono.empty())
            .thenReturn(order)
    );
```

Trong ví dụ này, lỗi audit được quan sát rồi bỏ qua để tiếp tục với đơn hàng. Đây là một quyết định nghiệp vụ có chủ đích: pipeline vẫn phát đơn hàng dù audit thất bại. Cần cân nhắc liệu có được phép mất bản ghi audit hay cần retry, lưu vào hàng đợi khác hoặc báo lỗi.

## 7. Callback quan sát cũng có thể ảnh hưởng đến pipeline nếu ném lỗi

Mặc dù các toán tử `doOn...` không nhằm biến đổi phần tử, callback vẫn là mã ứng dụng và có thể ném exception. Reactor có thể chuyển exception từ callback thành tín hiệu lỗi theo hợp đồng của toán tử. Vì vậy, không nên đặt một thao tác dễ thất bại hoặc có logic nghiệp vụ phức tạp trong callback quan sát.

Ví dụ, nếu logger tùy biến hoặc bộ ghi metrics có thể ném lỗi, việc ghi nhận quan sát có nguy cơ làm luồng nghiệp vụ kết thúc. Các callback nên ngắn, ít lỗi và không thực hiện I/O blocking. Với thao tác phụ có khả năng thất bại, cần xác định rõ lỗi của nó có nên ảnh hưởng đến luồng chính hay không rồi biểu diễn bằng một Publisher và toán tử xử lý thích hợp.

Một callback quan sát cũng không nên sửa trực tiếp object mutable đang được phát. Nếu `doOnNext` thay đổi trạng thái của phần tử, downstream vẫn nhận cùng object nhưng nhìn thấy trạng thái đã bị thay đổi. Điều này tạo ra side effect ẩn, đặc biệt khó kiểm soát khi object được chia sẻ giữa nhiều subscriber. Ưu tiên dữ liệu bất biến và dùng `map` để tạo giá trị mới khi cần thay đổi.

## 8. `doOnSuccess`, `doOnComplete` và `doFinally`

Các callback kết thúc có ngữ nghĩa khác nhau, đặc biệt khi làm việc với `Mono`:

| Toán tử | Áp dụng | Khi nào chạy? | Giá trị callback |
|---|---|---|---|
| `doOnSuccess` | `Mono` | Khi Mono hoàn tất thành công, có hoặc không có phần tử | Giá trị phát ra; `null` nếu rỗng |
| `doOnComplete` | `Flux` | Khi Flux hoàn tất bình thường | Không có giá trị phần tử |
| `doOnError` | `Mono` và `Flux` | Khi luồng kết thúc bằng lỗi | `Throwable` |
| `doFinally` | `Mono` và `Flux` | Sau complete, error hoặc cancel | `SignalType` |

Ví dụ:

```java
Mono<Customer> customer = findCustomer(id)
    .doOnSuccess(value -> {
        if (value == null) {
            log.info("Customer not found");
        } else {
            log.info("Customer found: {}", value.id());
        }
    })
    .doFinally(signal -> log.info("Lookup ended: {}", signal));
```

Với `Mono.empty()`, `doOnSuccess` vẫn chạy và nhận `null`. Điều đó không có nghĩa Publisher phát một phần tử `null`; Reactive Streams không cho phép `null` làm phần tử `onNext`. `doFinally` chạy cả khi subscriber hủy, vì vậy thích hợp để ghi nhận vòng đời hoặc dọn dẹp tài nguyên có quy tắc phù hợp.

## 9. Kiểm thử biến đổi và quan sát riêng biệt

Một bài kiểm thử nên xác minh đầu ra dữ liệu và số lần callback quan sát được gọi. Không nên chỉ kiểm tra rằng log đã xuất hiện rồi suy ra phép biến đổi là đúng.

Ví dụ kiểm thử `map` và `doOnNext`:

```java
AtomicInteger observed = new AtomicInteger();

Flux<Integer> pipeline = Flux.just("2", "4", "6")
    .map(Integer::parseInt)
    .doOnNext(value -> observed.incrementAndGet());

StepVerifier.create(pipeline)
    .expectNext(2, 4, 6)
    .verifyComplete();

assertEquals(3, observed.get());
```

`StepVerifier` xác minh dữ liệu downstream nhận là các số nguyên `2`, `4`, `6`. Bộ đếm xác minh callback đã được gọi ba lần. Hai khẳng định kiểm tra hai trách nhiệm riêng biệt.

Có thể kiểm tra rằng `doOnError` quan sát lỗi nhưng không phục hồi nó:

```java
AtomicInteger errorSignals = new AtomicInteger();

Mono<String> pipeline = Mono.<String>error(new IllegalStateException("failed"))
    .doOnError(error -> errorSignals.incrementAndGet());

StepVerifier.create(pipeline)
    .expectErrorMessage("failed")
    .verify();

assertEquals(1, errorSignals.get());
```

Nếu muốn kiểm thử phục hồi, hãy xác minh kết quả dự phòng ở downstream:

```java
Mono<String> recovered = Mono.<String>error(new IllegalStateException("failed"))
    .doOnError(error -> log.warn("Observed failure", error))
    .onErrorReturn("fallback");

StepVerifier.create(recovered)
    .expectNext("fallback")
    .verifyComplete();
```

## 10. Hướng dẫn chọn toán tử

| Nhu cầu | Nên dùng | Tránh dùng |
|---|---|---|
| Chuyển đổi một giá trị thành giá trị khác | `map` | `doOnNext` rồi sửa object tại chỗ |
| Loại bỏ phần tử không đạt điều kiện | `filter` | Callback quan sát có biến trạng thái để bỏ qua phần tử |
| Gọi Publisher bất đồng bộ cho từng phần tử | `flatMap`, `concatMap`, `switchMap` tùy ngữ nghĩa | Gọi `.subscribe()` bên trong `doOnNext` |
| Ghi log một phần tử | `doOnNext` | `map` chỉ để log rồi trả lại nguyên phần tử |
| Đếm tín hiệu hoặc ghi metrics | `doOnNext`, `doOnRequest`, `doOnError`, `doFinally` | Thay đổi dữ liệu chỉ để tạo điểm đo |
| Phục hồi khi có lỗi | `onErrorResume`, `onErrorReturn`, `retry` | Chỉ dùng `doOnError` rồi kỳ vọng lỗi biến mất |
| Dọn dẹp khi complete, error hoặc cancel | `doFinally` hoặc API quản lý tài nguyên phù hợp | Chỉ dùng `doOnComplete` |

Khi thiết kế pipeline, hãy để các toán tử biến đổi mô tả rõ dữ liệu nghiệp vụ đi qua hệ thống. Đặt callback quan sát gần tín hiệu cần theo dõi và giữ chúng ngắn gọn. Nếu một tác vụ bất đồng bộ có kết quả hoặc lỗi cần được quản lý, hãy đưa Publisher của tác vụ đó vào pipeline. Cách tổ chức này làm rõ dữ liệu nào được tạo ra, sự kiện nào chỉ được ghi nhận và lỗi nào có thể ảnh hưởng đến kết quả cuối cùng.
