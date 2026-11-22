# ConnectableFlux, connect, autoConnect và refCount

**Ngữ cảnh:** Spring Framework Reactive → **Nguồn nóng và lạnh**.

Mặc định, nhiều publisher trong Reactor là **cold**: mỗi subscriber tạo một subscription riêng, và nguồn có thể thực hiện lại công việc từ đầu cho subscriber đó. Điều này phù hợp khi mỗi người gọi cần một kết quả độc lập. Nhưng với một nguồn tốn kém hoặc một feed cập nhật liên tục, ta có thể muốn **nhiều subscriber cùng quan sát một lần chạy upstream**.

Project Reactor cung cấp `ConnectableFlux<T>` để tách hai hành động:

1. **Subscribe:** các subscriber đăng ký vào luồng chia sẻ và chờ dữ liệu.
2. **Connect:** chủ động cho phép nguồn upstream bắt đầu phát dữ liệu.

Từ đó có ba cách quản lý thời điểm kết nối phổ biến:

- `connect()` — ứng dụng quyết định chính xác lúc nào bắt đầu và có thể giữ `Disposable` để ngắt kết nối.
- `autoConnect(n)` — tự kết nối khi đủ `n` subscriber; sau khi kết nối thì không tự ngắt chỉ vì subscriber rời đi.
- `refCount(n)` — tự kết nối khi đủ `n` subscriber và ngắt upstream khi số subscriber giảm xuống dưới ngưỡng.

Các operator này giúp chia sẻ **một subscription nguồn** giữa nhiều consumer. Chúng không tự tạo dữ liệu, không tự lưu bền sự kiện, không bảo đảm replay cho subscriber đến muộn và không tạo thread mới.

## 1. Vì sao cần chia sẻ subscription?

Giả sử có một publisher cold:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

ticks.subscribe(value -> System.out.println("A=" + value));
ticks.subscribe(value -> System.out.println("B=" + value));
```

Đây là snippet trong project có Reactor và import `Duration`. Mỗi lần gọi `subscribe()` tạo một subscription riêng. Vì `Flux.interval` là nguồn cold, mỗi subscriber có lịch tick riêng, thường bắt đầu từ 0 sau khi subscribe.

Kết quả khái niệm:

```text
Nguồn cold
   ├── subscription A → 0, 1, 2, 3, ...
   └── subscription B → 0, 1, 2, 3, ...

Hai subscription có thể làm hai lần công việc upstream.
```

Điều này không phải lúc nào cũng xấu. Nếu mỗi subscriber cần dữ liệu độc lập, đây là hành vi đúng. Nhưng hãy xét các trường hợp:

- Nhiều client cùng xem một feed thị trường; mỗi client không nên mở thêm một kết nối nguồn bên ngoài.
- Nhiều thành phần trong ứng dụng cùng cần một lần polling trạng thái.
- Một luồng sự kiện tốn tài nguyên được tiêu thụ bởi dashboard, metric và thông báo.
- Nhiều request cần cùng quan sát một tiến trình phát dữ liệu đang chạy.

Nếu muốn các subscriber cùng nhận sự kiện từ **một lần thực thi nguồn**, hãy cân nhắc `publish()` hoặc `replay()` để tạo `ConnectableFlux`.

## 2. ConnectableFlux là gì?

`ConnectableFlux<T>` là một dạng `Flux<T>` có **điều khiển kết nối upstream tách biệt với việc subscriber đăng ký**.

Tạo nó bằng `publish()`:

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3)
        .publish();
```

Hoặc dùng `replay()` khi cần lưu lại dữ liệu cho subscriber đến sau:

```java
ConnectableFlux<Integer> replayed = Flux.range(1, 3)
        .replay(1);
```

Các đoạn trên là snippet cần import `Flux` và `ConnectableFlux`.

Với `publish()`:

- Subscriber có thể đăng ký trước khi nguồn bắt đầu.
- Nguồn upstream chỉ được kích hoạt khi có lệnh kết nối.
- Một kết nối upstream phát dữ liệu cho các subscriber hiện đang tham gia.
- Subscriber đến muộn **không tự nhận lại những item đã phát trước đó**.
- Khi nguồn complete/error hoặc connection bị dispose, vòng đời kết nối hiện tại kết thúc.

Với `replay(1)`, operator giữ lại tối đa một item gần nhất cho subscriber đến sau trong phạm vi vòng đời replay. `replay()` không giới hạn lịch sử có thể giữ nhiều dữ liệu; hãy chọn giới hạn số lượng hoặc thời gian khi dùng với nguồn dài hạn.

**ConnectableFlux không đồng nghĩa với Sinks.** `ConnectableFlux` chia sẻ subscription của một publisher có sẵn; `Sinks.Many` cho phép ứng dụng chủ động phát sự kiện vào một publisher hot. Hai công cụ giải các bài toán liên quan nhưng khác nhau về quyền sở hữu producer và cách đưa dữ liệu vào luồng.

## 3. connect(): tự quyết định thời điểm bắt đầu

`connect()` là cách điều khiển thủ công. Quy trình:

1. Tạo `ConnectableFlux` từ nguồn.
2. Đăng ký tất cả subscriber cần tham gia.
3. Gọi `connect()` để bắt đầu upstream.
4. Giữ `Disposable` được trả về nếu cần chủ động ngắt kết nối.

Ví dụ:

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3)
        .doOnSubscribe(s -> System.out.println("upstream subscribed"))
        .publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.subscribe(value -> System.out.println("B=" + value));

Disposable connection = shared.connect();
```

Snippet cần import `ConnectableFlux`, `Flux` và `Disposable`.

**Tại sao đăng ký subscriber trước khi connect?** Với nguồn đồng bộ hữu hạn như `Flux.range`, `connect()` có thể khiến toàn bộ item được phát ngay trong lời gọi đó. Nếu connect trước rồi mới subscribe, subscriber đến sau có thể bỏ lỡ toàn bộ dữ liệu đã phát. `publish()` không có lịch sử để phát lại.

### 3.1. Disposable của connection khác Disposable của subscriber

Có hai loại handle cần phân biệt:

| Handle | Đại diện cho | Dùng để |
|---|---|---|
| `Disposable` trả về từ `subscriber.subscribe(...)` | Một subscriber cụ thể | Hủy nhu cầu của subscriber đó |
| `Disposable` trả về từ `connectable.connect()` | Kết nối upstream được chia sẻ | Ngắt nguồn chung, ảnh hưởng tới mọi subscriber đang dùng kết nối |

Ví dụ:

```java
Disposable subscriberA = shared.subscribe(value -> useA(value));
Disposable subscriberB = shared.subscribe(value -> useB(value));

Disposable connection = shared.connect();

// Khi ứng dụng chủ động dừng nguồn chung:
connection.dispose();
```

Đây là snippet cần khai báo `shared` và các hàm xử lý. Nếu chỉ muốn một consumer rời đi, dispose subscription của consumer đó. Nếu dispose connection, bạn đang ngắt **nguồn chung**, không chỉ một subscriber.

### 3.2. connect(Consumer<Disposable>) để nắm quyền sở hữu kết nối

Có thể nhận handle connection qua callback:

```java
shared.connect(disposable -> {
    connectionRegistry.add(disposable);
});
```

Đây là snippet với `connectionRegistry` giả định là nơi ứng dụng quản lý các kết nối. Callback được gọi khi kết nối được thiết lập và cung cấp `Disposable` để ngắt kết nối sau này. Cần quản lý registry và cleanup theo lifecycle thực tế; không lưu handle vô thời hạn nếu nguồn đã hoàn tất.

**Không gọi connect tùy tiện từ nhiều nơi.** Nên có một component chịu trách nhiệm tạo nguồn, đăng ký consumer, kết nối và dừng nguồn. Nếu nhiều component cùng điều khiển kết nối, việc dispose từ một nơi có thể làm gián đoạn mọi nơi khác.

## 4. autoConnect(n): kết nối khi đủ subscriber

`autoConnect(n)` biến một `ConnectableFlux` thành `Flux` tự động kết nối khi có ít nhất `n` subscriber đăng ký.

```java
Flux<Integer> shared = Flux.range(1, 3)
        .doOnSubscribe(s -> System.out.println("upstream subscribed"))
        .publish()
        .autoConnect(2);
```

Đây là snippet. Hành vi:

- Subscriber thứ nhất đăng ký: upstream **chưa** bắt đầu.
- Subscriber thứ hai đăng ký: đạt ngưỡng 2, upstream kết nối.
- Cả hai subscriber hiện có cùng nhận các item.
- Sau khi kết nối đã được kích hoạt, subscriber rời đi **không làm autoConnect tự động ngắt upstream**.
- Nguồn tự complete/error thì kết nối kết thúc theo terminal signal.

### 4.1. Ngưỡng 1 và ngưỡng 0

```java
Flux<Event> startWithFirst =
        eventSource.publish().autoConnect(1);

Flux<Event> startImmediately =
        eventSource.publish().autoConnect(0);
```

- `autoConnect(1)`: kết nối khi subscriber đầu tiên xuất hiện.
- `autoConnect(0)`: kết nối ngay mà không cần subscriber nào.

Ngưỡng 0 hữu ích khi chủ đích muốn khởi chạy một nguồn dùng chung ngay khi publisher được kích hoạt, nhưng cũng có thể tạo công việc **không có người tiêu thụ**. Chỉ dùng khi component sở hữu nguồn và có chính sách dừng rõ ràng.

### 4.2. autoConnect không phải refCount

Giả sử nguồn là một `Flux.interval` vô hạn và ngưỡng là 1:

- Một client kết nối → upstream bắt đầu.
- Client đó đóng kết nối → subscriber rời đi.
- `autoConnect` **không tự dispose connection** chỉ vì không còn subscriber.
- Nguồn có thể tiếp tục tick và tiêu tốn tài nguyên mà không có consumer.

Muốn lấy được handle kết nối, có thể dùng overload `autoConnect(n, consumer)`. Nếu yêu cầu là “còn subscriber thì chạy, hết subscriber thì dừng”, `refCount` thường đúng mục đích hơn.

## 5. refCount(n): tự kết nối và tự ngắt theo số subscriber

`refCount(n)` theo dõi số subscriber đang tham gia một `ConnectableFlux`:

1. Khi số subscriber đạt ít nhất `n`, kết nối upstream.
2. Khi số subscriber giảm xuống dưới `n`, connection upstream bị hủy/ngắt.
3. Khi có đủ subscriber trở lại, operator có thể thiết lập một connection mới với nguồn phù hợp.

Ví dụ:

```java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
        .publish()
        .refCount(1);
```

Đây là snippet cần import `Duration`. Ý nghĩa:

- Khi chưa có ai subscribe, timer chưa cần chạy.
- Subscriber đầu tiên xuất hiện, timer bắt đầu.
- Nhiều subscriber cùng tham gia thì chia sẻ cùng timer.
- Subscriber cuối cùng rời đi, upstream bị cancel.
- Subscriber mới tới sau đó có thể kích hoạt một subscription nguồn mới; với `Flux.interval`, chuỗi tick mới bắt đầu lại từ đầu.

`refCount(1)` phù hợp với nguồn chia sẻ chỉ cần hoạt động khi có ít nhất một consumer. Với ngưỡng lớn hơn:

```java
Flux<Event> sharedForPair =
        eventSource.publish().refCount(2);
```

Nguồn chỉ kết nối khi có hai subscriber; nếu số lượng giảm còn một, kết nối chung bị ngắt. Vì vậy subscriber còn lại **không nên được giả định** sẽ tiếp tục nhận dữ liệu như một nguồn độc lập.

### 5.1. refCount với thời gian chờ trước khi ngắt

Trong hệ thống client thường xuyên kết nối lại, việc connect/disconnect liên tục có thể gây churn. Có thể dùng khoảng grace period:

```java
Flux<Event> shared = eventSource
        .publish()
        .refCount(1, Duration.ofSeconds(5));
```

Khi subscriber cuối rời đi, operator chờ khoảng thời gian cấu hình trước khi disconnect. Nếu có subscriber mới quay lại trong khoảng grace period, connection có thể tiếp tục được dùng. Đây là cách giảm kết nối lại liên tục; nó đồng nghĩa nguồn có thể tiếp tục chạy **một khoảng thời gian không có subscriber**.

Chọn thời gian chờ theo chi phí mở kết nối, độ trễ chấp nhận được và ngân sách tài nguyên. Grace period không phải cơ chế lưu bền hoặc bảo đảm client mới nhận lại dữ liệu đã phát trong thời gian vắng mặt.

## 6. So sánh connect, autoConnect và refCount

| Cơ chế | Ai quyết định bắt đầu? | Điều kiện ngắt upstream | Quyền kiểm soát |
|---|---|---|---|
| `connect()` | Code gọi thủ công | Nguồn terminal hoặc chủ sở hữu dispose connection | Cao; phù hợp lifecycle do component quản lý |
| `autoConnect(n)` | Tự động khi đủ `n` subscriber | Nguồn terminal hoặc chủ sở hữu dispose qua handle được giữ | Dễ dùng; không tự ngắt theo subscriber count |
| `refCount(n)` | Tự động khi đủ `n` subscriber | Subscriber count xuống dưới ngưỡng, hoặc nguồn terminal | Tự quản lý theo người tiêu thụ |
| `refCount(n, gracePeriod)` | Tự động khi đủ ngưỡng | Sau grace period nếu vẫn thiếu subscriber | Giảm churn nhưng có thể giữ nguồn chạy khi không ai xem |

Chọn nhanh:

- Cần chờ tất cả subscriber đã đăng ký rồi mới phát: `connect()`.
- Cần bắt đầu sau khi đủ số consumer và nguồn sống theo lifecycle ứng dụng: `autoConnect(n)`.
- Cần chỉ chạy khi có consumer và dừng khi không còn đủ consumer: `refCount(n)`.
- Cần giữ connection một thời gian ngắn khi client reconnect: `refCount(n, gracePeriod)`.

**Không có lựa chọn nào tự giải quyết replay, độ bền dữ liệu, overflow hoặc chính sách slow subscriber.** Những vấn đề đó phải được thiết kế riêng.

## 7. publish() và replay(): subscriber đến muộn nhận gì?

Đây là khác biệt quan trọng nhất khi chọn loại `ConnectableFlux`.

### 7.1. publish(): chỉ phân phối sự kiện trong lúc subscriber đang tham gia

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.connect();

// Subscriber B đến sau khi nguồn đã phát xong:
shared.subscribe(value -> System.out.println("B=" + value));
```

Với nguồn đồng bộ `range`, A nhận 1, 2, 3; B đến sau terminal signal và không nhận lại các item cũ. `publish` chia sẻ **sự kiện đang phát**, không lưu lịch sử.

Với nguồn vô hạn, B có thể nhận những item được phát sau thời điểm B subscribe, nhưng không nhận những item đã đi qua trước đó.

### 7.2. replay(): phát lại lịch sử đã lưu

```java
ConnectableFlux<Integer> latest = Flux.range(1, 5).replay(1);

latest.subscribe(value -> System.out.println("early=" + value));
latest.connect();

latest.subscribe(value -> System.out.println("late=" + value));
```

Với nguồn finite đồng bộ, subscriber sớm nhận 1..5; subscriber đến sau có thể nhận lại item gần nhất được replay (5), rồi nhận terminal signal. `replay(1)` giữ tối đa một item lịch sử.

Một số lựa chọn:

| Cách tạo | Lịch sử giữ lại |
|---|---|
| `publish()` | Không replay item đã phát |
| `replay(1)` | Tối đa item gần nhất |
| `replay(100)` | Tối đa 100 item gần nhất |
| `replay(Duration.ofMinutes(1))` | Item còn trong cửa sổ thời gian |
| `replay()` | Có thể giữ toàn bộ lịch sử của nguồn |

`replay()` không giới hạn trên một nguồn dài hạn có thể giữ bộ nhớ tăng liên tục. Chọn giới hạn theo số lượng/thời gian và kích thước payload; nếu cần lịch sử lâu dài, dùng kho lưu trữ hoặc message broker phù hợp.

**Replay trong bộ nhớ không phải event store.** Nó không bảo đảm dữ liệu sống qua restart, không thay thế offset/sequence bền vững và không tự xử lý reconnect của trình duyệt.

## 8. So sánh publish, replay, cache và Sinks

Các công cụ sau thường bị gọi chung là “hot”, nhưng hành vi không giống nhau:

| Cơ chế | Nguồn được chia sẻ? | Có replay? | Cách quản lý vòng đời |
|---|---|---|---|
| `publish().connect()` | Có, sau khi connect | Không | Chủ động giữ `Disposable` connection |
| `publish().autoConnect(n)` | Có, sau ngưỡng | Không | Kết nối tự động, không tự ngắt theo subscriber count |
| `publish().refCount(n)` | Có, khi đủ ngưỡng | Không | Kết nối/ngắt theo số subscriber |
| `replay(k)` | Có | Có, giới hạn k item | Kết nối thủ công hoặc kết hợp autoConnect/refCount |
| `cache()` | Có, publisher bắt đầu khi subscriber đầu tiên tới | Cache item và terminal signal theo cấu hình | Không có điều khiển connect/disconnect như ConnectableFlux |
| `Sinks.Many` | Là nguồn hot do ứng dụng phát | Tùy loại sink (multicast/replay) | Ứng dụng quản lý sink và producer |

### 8.1. cache() không phải refCount()

`cache()` hữu ích khi muốn một lần tính toán và lưu kết quả để subscriber sau nhận lại. Tuy nhiên, cache có thể giữ item/terminal signal và không tự ngắt upstream chỉ vì không còn subscriber theo cơ chế `refCount`.

```java
Mono<Product> cached = productService.loadProduct(id)
        .cache();
```

Đây là snippet. `cache()` phù hợp khi muốn chia sẻ và giữ kết quả; cần xem xét TTL, số lượng key, kích thước dữ liệu và thời điểm invalidation. Không dùng cache không giới hạn cho một luồng sự kiện vô hạn.

### 8.2. Sinks.Many là producer chủ động

```java
Sinks.Many<Event> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<Event> events = sink.asFlux();

// Nơi khác trong ứng dụng:
Sinks.EmitResult result = sink.tryEmitNext(event);
```

Đây là snippet; `Event` và `event` cần được khai báo. Sink cho phép ứng dụng chủ động phát dữ liệu, trong khi `ConnectableFlux` chia sẻ việc subscribe vào một publisher đã tồn tại. Sinks có chính sách multicast/replay/overflow riêng; cần xử lý `EmitResult`, concurrency và cleanup đúng cách.

## 9. Một nguồn, nhiều subscriber: side effect đặt trước hay sau publish?

Vị trí operator ảnh hưởng số lần side effect chạy.

### 9.1. Side effect trước publish: thuộc nguồn dùng chung

```java
Flux<Event> shared = source
        .doOnNext(event -> metrics.recordSourceEvent())
        .publish()
        .refCount(1);
```

Khi upstream phát một event trong một connection, `recordSourceEvent()` chạy một lần ở nhánh nguồn chung trước khi phân phối cho subscriber.

### 9.2. Side effect sau publish: mỗi subscriber có thể thực hiện riêng

```java
Flux<Event> shared = source
        .publish()
        .refCount(1)
        .doOnNext(event -> metrics.recordClientDelivery());
```

Hook nằm sau phần chia sẻ; mỗi subscriber nhận item có thể chạy callback của nhánh đó. Nếu có ba subscriber, một event upstream có thể dẫn đến ba lần callback downstream.

Điều này cũng quan trọng với `doOnError`, metric và tracing:

- Hook trước `publish` quan sát lỗi từ nguồn dùng chung một lần trên connection.
- Hook sau `publish` có thể được gọi cho từng subscriber đang nhận lỗi.
- Không đặt side effect nghiệp vụ không idempotent sau publish nếu không muốn nó chạy một lần cho mỗi consumer.

## 10. Backpressure và subscriber chậm trong luồng chia sẻ

Chia sẻ một nguồn đồng nghĩa nhiều subscriber cùng tác động tới cách nguồn được tiêu thụ. Với `publish()`, Reactor phối hợp demand của các subscriber; một subscriber không có demand có thể làm upstream tạm dừng phát để tránh gửi dữ liệu vượt nhu cầu của nhánh đó.

Điều này tạo ra một trade-off:

- Tất cả subscriber quan sát một luồng chung nhất quán theo thứ tự phát.
- Một subscriber chậm có thể làm giảm tốc cả nguồn chung.
- Nếu một nhánh cần chính sách khác (drop/latest/buffer), phải thiết kế rõ ở vị trí phù hợp.

Ví dụ dashboard chỉ cần trạng thái gần nhất:

```java
Flux<Metric> sharedLatest = metricsSource
        .onBackpressureLatest()
        .publish()
        .refCount(1);
```

Đây là snippet. Chính sách latest được áp dụng trước publish, nên dữ liệu được giữ/bỏ ở tầng nguồn chia sẻ. Các subscriber nhận cùng luồng đã được điều tiết.

Nếu cần chính sách riêng cho từng client, có thể đặt operator ở nhánh sau phần chia sẻ:

```java
Flux<Metric> shared = metricsSource
        .publish()
        .refCount(1);

Flux<Metric> clientView = shared.onBackpressureLatest();
```

Đây là snippet minh họa một nhánh consumer. Hãy đánh giá demand và buffer thực tế: operator ở sau publish có thể làm thay đổi request mà nhánh đó gửi tới phần chia sẻ. Nếu dùng buffer cho mỗi client, giới hạn số item/byte và overflow policy là bắt buộc; buffer vô hạn có thể làm cạn bộ nhớ.

**Không dùng latest/drop cho event bắt buộc đầy đủ** như thanh toán, đơn hàng hoặc audit. Chia sẻ subscription không thay thế durable queue, acknowledgment hoặc event log.

## 11. Lifecycle: subscribe, connect, complete, error và cancel

Một nguồn được chia sẻ có nhiều vòng đời cần phân biệt:

1. **Subscriber lifecycle:** một consumer subscribe, nhận item rồi có thể complete/error/cancel độc lập.
2. **Connection lifecycle:** nguồn upstream được connect, phát item và cuối cùng complete/error hoặc bị dispose/cancel.
3. **Application lifecycle:** bean/service được khởi tạo, bắt đầu và dừng cùng ứng dụng.

### 11.1. Nguồn complete

Khi upstream complete, các subscriber đang tham gia nhận `onComplete`. Không có dữ liệu mới từ connection đó. Hành vi subscriber đến sau phụ thuộc operator (ví dụ publish không replay, replay/cache có thể giữ lịch sử/terminal signal theo cấu hình).

### 11.2. Nguồn error

Một lỗi upstream được phân phối tới các subscriber đang tham gia connection. `doOnError` đặt trước publish quan sát lỗi nguồn; đặt sau publish có thể quan sát lỗi ở từng nhánh consumer. `ConnectableFlux` không tự retry hoặc phục hồi lỗi.

Nếu muốn retry nguồn dùng chung, đặt retry **trước khi chia sẻ** khi mục tiêu là một retry policy chung:

```java
Flux<Event> shared = eventSource
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1)))
        .publish()
        .refCount(1);
```

Đây là snippet cần `Retry` và `Duration`. Retry của upstream nằm trước publish, nên các subscriber cùng quan sát một lần kết nối/khởi động lại nguồn. Retry vẫn cần filter lỗi tạm thời, giới hạn số lần, jitter, timeout và idempotency cho side effect.

### 11.3. Một subscriber cancel

Với `refCount(1)`, nếu vẫn còn subscriber khác thì upstream tiếp tục. Khi subscriber cuối cùng rời đi, connection bị cancel. Với `refCount(2)`, số subscriber giảm từ hai xuống một đã thấp hơn ngưỡng nên connection bị ngắt.

Với `autoConnect(n)`, subscriber cancel **không tự hạ số lượng để ngắt nguồn** sau khi connection đã được kích hoạt. Với `connect()` thủ công, chỉ owner dispose connection hoặc nguồn tự terminal mới kết thúc connection chung.

### 11.4. Cancellation không rollback side effect

Nếu nguồn đã gửi request tới dịch vụ thanh toán hoặc đã ghi DB, cancel subscription không bảo đảm side effect ngoài hệ thống bị hoàn tác. Hãy dùng idempotency key, transaction phù hợp, outbox, trạng thái job và cơ chế reconciliation theo yêu cầu nghiệp vụ.

## 12. Chương trình Java 17+ chạy độc lập: quan sát ba cách kết nối

Ví dụ sau dùng Reactor Core và Maven, không cần Spring Boot, mạng hay database. Nó minh họa:

1. `connect()` chờ subscriber đăng ký rồi mới bắt đầu.
2. `autoConnect(2)` kết nối khi subscriber thứ hai xuất hiện.
3. `refCount(2)` kết nối ở ngưỡng hai và ngắt upstream khi số subscriber giảm xuống dưới ngưỡng.

Cấu trúc thư mục:

```text
connectable-flux-demo/
├── pom.xml
└── src/main/java/demo/ConnectableFluxDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>connectable-flux-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/ConnectableFluxDemo.java`:

```java
package demo;

import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class ConnectableFluxDemo {

    public static void main(String[] args) {
        manualConnect();
        autoConnect();
        refCount();
    }

    private static void manualConnect() {
        System.out.println("1) manual connect");

        ConnectableFlux<Integer> shared = Flux.concat(
                        Flux.range(1, 3),
                        Flux.<Integer>never())
                .doOnSubscribe(s ->
                        System.out.println("manual:source subscribed"))
                .doOnCancel(() ->
                        System.out.println("manual:source cancelled"))
                .publish();

        shared.subscribe(value ->
                System.out.println("manual A=" + value));
        shared.subscribe(value ->
                System.out.println("manual B=" + value));

        System.out.println("manual:calling connect");
        Disposable connection = shared.connect();

        System.out.println("manual:disposing connection");
        connection.dispose();
    }

    private static void autoConnect() {
        System.out.println("2) autoConnect(2)");

        Flux<Integer> shared = Flux.range(10, 2)
                .doOnSubscribe(s ->
                        System.out.println("auto:source subscribed"))
                .publish()
                .autoConnect(2);

        shared.subscribe(
                value -> System.out.println("auto A=" + value),
                error -> System.out.println("auto A error"),
                () -> System.out.println("auto A complete"));

        System.out.println("auto:first subscriber attached");

        shared.subscribe(
                value -> System.out.println("auto B=" + value),
                error -> System.out.println("auto B error"),
                () -> System.out.println("auto B complete"));

        System.out.println("auto:second subscriber attached");
    }

    private static void refCount() {
        System.out.println("3) refCount(2)");

        Flux<Integer> shared = Flux.<Integer>never()
                .doOnSubscribe(s ->
                        System.out.println("refCount:source connected"))
                .doOnCancel(() ->
                        System.out.println("refCount:source cancelled"))
                .publish()
                .refCount(2);

        Disposable first = shared.subscribe();
        System.out.println("refCount:first subscriber attached");

        Disposable second = shared.subscribe();
        System.out.println("refCount:second subscriber attached");

        first.dispose();
        System.out.println("refCount:first subscriber disposed");

        second.dispose();
        System.out.println("refCount:second subscriber disposed");
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConnectableFluxDemo
```

**Standard output dự kiến** (không tính thông báo riêng của Maven):

```text
1) manual connect
manual:calling connect
manual:source subscribed
manual A=1
manual B=1
manual A=2
manual B=2
manual A=3
manual B=3
manual:disposing connection
manual:source cancelled
2) autoConnect(2)
auto:first subscriber attached
auto:source subscribed
auto A=10
auto B=10
auto A=11
auto B=11
auto A complete
auto B complete
auto:second subscriber attached
3) refCount(2)
refCount:first subscriber attached
refCount:source connected
refCount:second subscriber attached
refCount:source cancelled
refCount:first subscriber disposed
refCount:second subscriber disposed
```

### Giải thích output

**Phần 1 — manual connect**

- Hai subscriber A và B đã đăng ký nhưng nguồn chưa chạy.
- Dòng `manual:calling connect` xuất hiện trước `manual:source subscribed`.
- `connect()` bắt đầu một subscription upstream; cả A và B nhận cùng ba item.
- Sau `Flux.range`, `Flux.never()` giữ nguồn mở. Dispose `connection` hủy upstream và kích hoạt `doOnCancel`.
- Đây là lý do cần giữ `Disposable` khi chủ động quản lý một nguồn vô hạn.

**Phần 2 — autoConnect(2)**

- Subscriber A đăng ký đầu tiên; chưa đủ ngưỡng nên chưa có upstream subscription.
- Dòng `auto:first subscriber attached` xuất hiện trước khi nguồn được subscribe.
- Khi B đăng ký, ngưỡng 2 đạt được và nguồn đồng bộ phát 10, 11 cho cả hai.
- Nguồn complete trước khi lệnh subscribe của B trả về, nên `auto:second subscriber attached` xuất hiện cuối cùng.

**Phần 3 — refCount(2)**

- Subscriber đầu tiên chưa đủ ngưỡng, nguồn chưa kết nối.
- Subscriber thứ hai đạt ngưỡng; `Flux.never` được subscribe.
- Dispose subscriber đầu tiên làm số subscriber giảm từ hai xuống một, thấp hơn ngưỡng 2; connection upstream bị cancel.
- Dòng `refCount:source cancelled` xuất hiện trước dòng xác nhận dispose subscriber đầu tiên.

Thứ tự output xác định vì các thao tác trong demo chạy đồng bộ, không dùng scheduler, timer hay network. Demo minh họa lifecycle của operator; nó không chứng minh mọi driver HTTP/DB có thể rollback side effect khi bị cancel.

## 13. Spring WebFlux: chia sẻ một SSE feed cho nhiều client

Một trường hợp thực tế là nhiều browser cùng xem một feed cập nhật. Nếu mỗi request tạo một `Flux.interval` riêng, mỗi browser có timer riêng. Nếu muốn tất cả client cùng quan sát một nguồn, có thể đặt publisher dùng chung trong một Spring singleton bean.

Ví dụ sau gồm hai class cho ứng dụng Spring Boot có dependency `spring-boot-starter-webflux`. Đây là **mã ứng dụng**, không phải project độc lập; vẫn cần main class Spring Boot và cấu hình server.

Tệp `SharedEventStream.java`:

```java
import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public class SharedEventStream {

    private final Flux<ServerSentEvent<Long>> events =
            Flux.interval(Duration.ofSeconds(1))
                    .map(tick -> ServerSentEvent.<Long>builder(tick)
                            .id(Long.toString(tick))
                            .build())
                    .publish()
                    .refCount(1);

    public Flux<ServerSentEvent<Long>> events() {
        return events;
    }
}
```

Tệp `EventController.java`:

```java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {

    private final SharedEventStream stream;

    public EventController(SharedEventStream stream) {
        this.stream = stream;
    }

    @GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Long>> events() {
        return stream.events();
    }
}
```

### Điều gì xảy ra khi client kết nối?

1. Client A gọi `GET /events`; WebFlux subscribe vào `events`. `refCount(1)` đạt ngưỡng và khởi động một timer upstream.
2. Client B kết nối trong khi A còn hoạt động; B tham gia cùng `ConnectableFlux` và nhận các tick tiếp theo từ cùng một timer.
3. B không nhận lại những tick đã phát trước khi B kết nối, vì nguồn dùng `publish()` chứ không phải `replay()`.
4. Nếu A đóng tab nhưng B vẫn còn, nguồn tiếp tục chạy cho B.
5. Khi B cũng rời đi, subscriber count về 0; `refCount(1)` cancel timer.
6. Client C kết nối sau đó sẽ tạo subscription nguồn mới. `Flux.interval` bắt đầu một chuỗi mới, trong demo này tick bắt đầu lại từ 0.

**Lưu ý production:** ID SSE trong ví dụ chỉ là tick trong bộ nhớ. Nếu cần reconnect và phát lại event qua `Last-Event-ID`, cần sequence bền vững, event store hoặc broker có offset và logic replay. `publish().refCount(1)` không tự cung cấp lịch sử hoặc bảo đảm không mất event.

### Khi nào dùng grace period?

Nếu browser thường reconnect trong vài giây, có thể cân nhắc:

```java
.publish()
.refCount(1, Duration.ofSeconds(5));
```

Nguồn được giữ thêm trong grace period sau khi subscriber cuối rời đi. Điều này giảm việc tạo/hủy upstream liên tục, nhưng nguồn vẫn có thể phát trong lúc không có client. Nếu dữ liệu trong khoảng đó cần được gửi lại cho client mới, cần replay hoặc lưu trữ riêng.

### Một feed dùng chung có thể bị client chậm ảnh hưởng

Nếu mọi client dùng cùng một `publish`, demand của các nhánh consumer có thể phối hợp và subscriber chậm có thể làm chậm nguồn chung. Với dashboard, có thể chấp nhận bỏ các trạng thái trung gian; với thông báo quan trọng, cần một cơ chế lưu trữ/replay đáng tin cậy. Không dùng cùng một chính sách cho cả hai loại dữ liệu.

## 14. Khi nào dùng autoConnect, refCount hay connect trong ứng dụng?

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Polling chỉ cần chạy khi có ít nhất một browser | `publish().refCount(1)` | Tự bắt đầu và dừng theo consumer |
| Nguồn phải chạy sau khi đủ hai worker đăng ký và sống theo lifecycle ứng dụng | `publish().autoConnect(2)` | Chỉ cần ngưỡng khởi động |
| Ứng dụng có một service quản lý start/stop rõ ràng | `publish()` + `connect()` | Component sở hữu connection Disposable |
| Chỉ cần giữ trạng thái mới nhất cho subscriber đến muộn | `replay(1)` kết hợp lifecycle phù hợp | Replay một item, không giữ cả lịch sử |
| Cần lưu mọi event qua restart | Broker/event store | ConnectableFlux chỉ chia sẻ trong bộ nhớ |
| Mỗi subscriber cần một lần gọi upstream riêng | Giữ nguồn cold, không chia sẻ | Không nên ép chia sẻ nếu ngữ nghĩa không phù hợp |

### Cẩn trọng với bean singleton

Nếu tạo `ConnectableFlux` trong một singleton bean, hãy quyết định ai sở hữu lifecycle:

- `refCount` phù hợp khi số client quyết định nguồn có cần chạy hay không.
- `autoConnect` phù hợp khi nguồn được khởi động một lần và sống đến khi hoàn tất hoặc ứng dụng dừng.
- `connect()` phù hợp khi component cần quản lý kết nối thủ công, chẳng hạn bắt đầu sau khi ứng dụng ready và dispose khi shutdown.

Đừng gọi `connect()` mỗi lần controller xử lý một request. Điều đó có thể làm lifecycle khó kiểm soát và tạo cạnh tranh giữa các request.

## 15. Những lỗi thường gặp

### Lỗi 1 — Nghĩ publish() tự kết nối

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();
shared.subscribe(System.out::println);
// Chưa connect nên nguồn chưa phát.
```

**Sửa:** gọi `shared.connect()`, hoặc dùng `autoConnect`/`refCount`.

### Lỗi 2 — Connect trước khi subscriber đăng ký

Với nguồn synchronous finite, `connect()` có thể phát và hoàn tất trước khi subscriber đến; `publish()` không replay dữ liệu cũ. **Sửa:** đăng ký các subscriber trước, rồi connect; hoặc chọn `replay` nếu subscriber muộn cần lịch sử.

### Lỗi 3 — Nghĩ autoConnect tự ngắt khi mọi subscriber rời đi

`autoConnect` chỉ quyết định thời điểm kết nối. Sau khi đạt ngưỡng, nó không tự disconnect theo số subscriber. **Sửa:** dùng `refCount` hoặc quản lý Disposable từ overload autoConnect.

### Lỗi 4 — Dùng refCount với ngưỡng quá cao

`refCount(3)` sẽ ngắt upstream khi số subscriber giảm còn hai. Một consumer còn lại không có nghĩa nguồn vẫn chạy. **Sửa:** chọn ngưỡng theo lifecycle thực tế; phần lớn feed theo browser dùng ngưỡng 1.

### Lỗi 5 — Nghĩ late subscriber được nhận lịch sử

`publish` không lưu item cũ. **Sửa:** `replay(k)` hoặc endpoint snapshot + stream delta, tùy hợp đồng dữ liệu.

### Lỗi 6 — Dùng replay() không giới hạn trên nguồn vô hạn

Mọi item có thể bị giữ lại, khiến bộ nhớ tăng. **Sửa:** chọn `replay(k)` hoặc giới hạn thời gian, hoặc lưu lịch sử ở hệ thống lưu trữ.

### Lỗi 7 — Nhầm ConnectableFlux với Sinks.Many

ConnectableFlux chia sẻ một nguồn đã tồn tại; Sinks cho phép ứng dụng phát sự kiện. **Sửa:** chọn theo quyền sở hữu producer và overflow/replay policy.

### Lỗi 8 — Không giữ Disposable của connect()

Với nguồn vô hạn, không có handle để chủ động dừng connection. **Sửa:** lưu `Disposable` trong component quản lý và dispose khi shutdown hoặc khi nguồn không còn cần thiết.

### Lỗi 9 — Dispose connection khi chỉ muốn một client rời đi

Connection Disposable ngắt nguồn chung cho mọi subscriber. **Sửa:** dispose subscription của đúng client; để `refCount` tự quyết định khi nào ngắt nguồn.

### Lỗi 10 — Nghĩ chia sẻ tạo thread mới

`publish`/`replay` không tự tạo scheduler hoặc parallel execution. Các subscriber có thể nhận callback trên thread phát tín hiệu. **Sửa:** nếu cần đổi execution context, dùng scheduler/operator phù hợp; không chặn event-loop.

### Lỗi 11 — Một subscriber chậm làm ảnh hưởng mọi client

Một luồng dùng chung phối hợp demand; slow subscriber có thể làm chậm upstream. **Sửa:** xác định có thể drop/latest/sample hay không; nếu cần buffer, giới hạn theo item/byte và định nghĩa overflow. Nếu mỗi client cần độc lập hoàn toàn, cân nhắc tách pipeline.

### Lỗi 12 — Đặt side effect sai phía publish

Side effect trước publish thường chạy một lần trên nguồn chung; sau publish có thể chạy một lần mỗi subscriber. **Sửa:** xác định rõ metric/log/side effect thuộc source hay từng consumer.

### Lỗi 13 — Nghĩ autoConnect/refCount cung cấp durable replay

Các operator này quản lý subscription trong bộ nhớ. **Sửa:** dùng Kafka, Redis Streams, database hoặc event store phù hợp nếu cần replay sau restart, consumer offset và độ bền.

### Lỗi 14 — Cho rằng cancel rollback được công việc ngoài hệ thống

Hủy connection có thể dừng việc phát thêm item, nhưng side effect đã gửi đi có thể vẫn hoàn tất. **Sửa:** idempotency, transaction, outbox và reconciliation.

### Lỗi 15 — Gọi connect nhiều nơi trong ứng dụng

Nhiều component cùng sở hữu connection tạo lifecycle khó hiểu. **Sửa:** chỉ định một owner; cung cấp Flux dùng chung cho consumer, không trao quyền connect/dispose tràn lan.

## 16. Checklist thiết kế nguồn chia sẻ

Trước khi dùng `ConnectableFlux`, trả lời:

1. Nguồn ban đầu là cold hay hot? Mỗi subscriber hiện đang tạo bao nhiêu upstream subscription?
2. Các consumer có thực sự cần cùng một lần chạy upstream không?
3. Nên dùng `publish` hay `replay`? Subscriber đến muộn có cần lịch sử không?
4. Ai quyết định kết nối: code owner, ngưỡng subscriber hay số consumer đang hoạt động?
5. Nếu dùng `autoConnect`, ai sẽ dispose nguồn vô hạn khi ứng dụng dừng?
6. Nếu dùng `refCount`, ngưỡng subscriber có phù hợp? Có cần grace period để tránh reconnect churn?
7. Subscriber chậm có được làm chậm tất cả? Có policy buffer/drop/latest và giới hạn cụ thể?
8. Side effect/log/metric đặt trước hay sau publish? Mong muốn chạy một lần hay mỗi consumer?
9. Nguồn complete/error thì subscriber mới nhận gì? Retry đặt trước hay sau operator chia sẻ?
10. Có cần replay bền vững qua restart? Nếu có, ConnectableFlux có đủ không?
11. Khi một client disconnect, subscription và tài nguyên có được giải phóng?
12. Có kiểm thử ngưỡng subscriber, late subscriber, cancellation, error và reconnect không?

## 17. Tự kiểm tra

**Câu 1:** `Flux.range(1, 3).publish()` đã phát dữ liệu ngay chưa?

→ Chưa. Nó tạo `ConnectableFlux`; cần `connect()` hoặc cơ chế auto/refCount.

**Câu 2:** A subscribe, B subscribe, rồi connect. Có bao nhiêu subscription nguồn?

→ Một connection upstream được chia sẻ cho A và B.

**Câu 3:** Dùng `autoConnect(2)`, chỉ có A subscribe. Nguồn đã chạy chưa?

→ Chưa. Cần subscriber thứ hai để đạt ngưỡng.

**Câu 4:** Hai subscriber đã kích hoạt `autoConnect(2)`, sau đó cả hai cancel. Nguồn vô hạn có tự dừng không?

→ Không tự dừng chỉ vì subscriber count về 0. Cần quản lý connection hoặc dùng `refCount`.

**Câu 5:** `refCount(2)` đang có hai subscriber, một người rời đi. Điều gì xảy ra?

→ Số lượng còn một, thấp hơn ngưỡng; connection upstream bị cancel/ngắt.

**Câu 6:** `publish()` có gửi lại item đã phát cho subscriber đến muộn không?

→ Không. Dùng `replay` nếu cần lịch sử trong bộ nhớ.

**Câu 7:** `replay()` không giới hạn có an toàn với feed vô hạn không?

→ Không. Lịch sử có thể tăng không giới hạn; chọn giới hạn số lượng/thời gian.

**Câu 8:** `connect()` trả về gì?

→ `Disposable` đại diện cho connection upstream; dispose nó sẽ ngắt nguồn chung.

**Câu 9:** `refCount(1)` có tạo thread mới cho mỗi client không?

→ Không. Nó chia sẻ subscription nguồn; scheduler và nguồn quyết định thread thực thi.

**Câu 10:** Muốn mỗi browser có nguồn riêng thì có nên publish/refCount không?

→ Thường không. Giữ publisher cold nếu mỗi browser cần một nguồn độc lập.

**Ghi nhớ:** `ConnectableFlux` tách việc **subscriber tham gia** khỏi việc **nguồn upstream bắt đầu**. `connect()` cho quyền điều khiển thủ công, `autoConnect(n)` tự bắt đầu khi đủ subscriber nhưng không tự ngắt theo số lượng, còn `refCount(n)` tự bắt đầu và ngắt khi subscriber count xuống dưới ngưỡng. `publish` chia sẻ item đang phát; `replay` giữ lịch sử trong bộ nhớ. Chọn đúng operator theo ownership, late subscriber, cancellation, backpressure và yêu cầu độ bền dữ liệu.

## Tài liệu tham khảo

- Project Reactor — [Hot Versus Cold: ConnectableFlux, publish, replay](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html).
- Project Reactor — [ConnectableFlux API: connect, autoConnect, refCount](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/ConnectableFlux.html).
- Project Reactor — [Flux API: publish, replay, cache, share](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Backpressure and request reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Sinks: multicast and replay](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [Server-Sent Events in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
