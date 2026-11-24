# Phần tử bị bỏ, bộ đệm chưa tiêu thụ và tài nguyên cần giải phóng

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` quản lý luồng dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Một pipeline có thể lọc bỏ phần tử, bỏ dữ liệu khi downstream không theo kịp, giữ phần tử trong buffer hoặc bị hủy trước khi mọi phần tử được tiêu thụ. Nếu phần tử chỉ là giá trị bất biến trên heap, việc bỏ qua thường không cần xử lý đặc biệt. Nhưng nếu phần tử đang giữ tài nguyên như buffer có reference count, file handle, lease hoặc đối tượng native, việc bỏ phần tử mà không giải phóng có thể gây rò rỉ tài nguyên.

Quản lý tài nguyên trong Reactor cần xem xét hai vòng đời khác nhau: **vòng đời của từng phần tử** và **vòng đời của tài nguyên được cấp phát cho một subscription**. `doOnDiscard` hỗ trợ dọn dẹp phần tử bị loại bỏ bởi các toán tử có hỗ trợ discard; `using` và `usingWhen` quản lý tài nguyên gắn với subscription; còn `doFinally` giúp quan sát tín hiệu kết thúc để thực hiện tác vụ đồng bộ phù hợp.

## 1. Phần tử có thể không bao giờ đến được downstream

Một phần tử được phát từ upstream không nhất thiết sẽ được xử lý bởi Subscriber cuối cùng. Trong quá trình đi qua pipeline, phần tử có thể bị loại bỏ ở nhiều vị trí:

- `filter` loại bỏ phần tử không đạt điều kiện.
- `take`, `takeWhile` hoặc `takeUntil` dừng nhận dữ liệu khi đã đạt giới hạn hoặc điều kiện.
- `onBackpressureDrop` bỏ phần tử mới khi downstream chưa có demand.
- `onBackpressureLatest` giữ giá trị mới nhất và loại bỏ giá trị cũ bị thay thế khi downstream chậm.
- Buffer hữu hạn có thể loại bỏ phần tử theo chính sách overflow hoặc giải phóng phần tử còn chờ khi subscription bị hủy.
- Một toán tử có thể loại bỏ dữ liệu đã giữ trong hàng đợi khi upstream lỗi hoặc downstream cancel.

Ví dụ, một buffer có reference count được lọc trước khi giải mã:

```java
Flux<ByteBuf> frames = inboundFrames;

Flux<Message> messages = frames
    .filter(ByteBuf::isReadable)
    .map(this::decode);
```

Nếu `filter` loại bỏ một `ByteBuf` không đọc được, callback `map` không chạy với buffer đó. Nếu quyền sở hữu buffer yêu cầu gọi `release()`, chỉ giải phóng trong `map` là chưa đủ. Tương tự, phần tử còn trong queue có thể chưa từng đến `map` khi subscription bị hủy.

Đó là lý do phải xác định rõ ai chịu trách nhiệm giải phóng một phần tử ở từng nhánh: phần tử được tiêu thụ bình thường, phần tử bị lọc, phần tử bị drop, phần tử bị thay thế trong buffer và phần tử còn chờ lúc cancellation.

## 2. Phân biệt drop, discard và buffer chưa tiêu thụ

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Điều xảy ra | Ví dụ |
|---|---|---|
| Drop | Một phần tử bị loại bỏ theo chính sách khi downstream không có đủ demand | `onBackpressureDrop` |
| Discard | Một phần tử bị toán tử loại khỏi luồng và sẽ không được phát tiếp từ vị trí đó | `filter`, thay thế giá trị cũ trong `latest`, cleanup queue |
| Buffer chưa tiêu thụ | Phần tử đã được nhận và giữ lại để chờ downstream yêu cầu hoặc xử lý | `onBackpressureBuffer`, queue của toán tử ghép |
| Cancel | Downstream yêu cầu dừng subscription | `Subscription.cancel()`, `take(n)` sau khi đủ phần tử |

Buffer chưa tiêu thụ chưa phải là phần tử đã bị drop. Nó vẫn đang được giữ để có thể phát sau khi downstream có demand. Nhưng khi subscription kết thúc hoặc chính sách overflow loại bỏ nó, phần tử đó cần được xử lý theo vòng đời discard.

Cancellation cũng không đồng nghĩa mọi tài nguyên tự động được giải phóng. Reactor truyền yêu cầu hủy qua chuỗi subscription và các toán tử quản lý queue nội bộ của chúng. Tuy nhiên, nếu một phần tử đang giữ tài nguyên bên ngoài heap hoặc có reference count, ứng dụng cần dùng cơ chế cleanup phù hợp với toán tử và kiểu tài nguyên đó.

## 3. Dùng doOnDiscard cho phần tử bị loại bỏ

Reactor cung cấp `doOnDiscard(Class, Consumer)` để đăng ký callback dọn dẹp các phần tử bị loại bỏ bởi những toán tử upstream có hỗ trợ discard. Callback nhận chính phần tử bị loại bỏ, cho phép giải phóng tài nguyên hoặc ghi nhận metrics.

```java
Flux<Message> messages = inboundFrames
    .filter(ByteBuf::isReadable)
    .doOnDiscard(ByteBuf.class, buffer -> buffer.release())
    .map(buffer -> {
        try {
            return decoder.decodeCopy(buffer);
        } finally {
            buffer.release();
        }
    });
```

Trong ví dụ này:

- `filter` loại bỏ những buffer không có dữ liệu đọc được.
- `doOnDiscard` được đặt phía downstream của `filter`, nên hook có thể được truyền ngược qua context để nhận các `ByteBuf` mà toán tử upstream hỗ trợ discard loại bỏ.
- Với buffer được chuyển đến `map`, hàm giải mã tạo ra một `Message` độc lập; `finally` giải phóng buffer sau khi giải mã, kể cả khi giải mã ném lỗi.

`decodeCopy` trong ví dụ phải tạo dữ liệu đầu ra không còn phụ thuộc vào vùng nhớ của `ByteBuf`. Nếu kết quả giữ một view hoặc tham chiếu đến buffer gốc, không được release buffer ngay tại đây; cần chuyển quyền sở hữu hoặc retain theo quy tắc của thư viện buffer.

### Vị trí đặt doOnDiscard

`doOnDiscard` là hook được đưa vào context cho các toán tử upstream hỗ trợ discard. Vì vậy, hãy đặt nó sau những toán tử có thể loại bỏ phần tử và gần cuối pipeline để bao phủ nhiều toán tử upstream nhất có thể:

```java
source
    .filter(this::isUseful)
    .take(100)
    .doOnDiscard(PooledPayload.class, PooledPayload::release)
    .map(this::decode);
```

Hook chỉ hoạt động với những toán tử có triển khai discard support. Nó không phải callback tổng quát cho mọi phần tử không đến được `doOnNext`, cũng không thay thế cleanup của tài nguyên được cấp phát độc lập bên ngoài luồng. Hãy kiểm tra tài liệu của operator và phiên bản Reactor đang dùng trước khi dựa vào hook cho một đường đi cụ thể.

## 4. Chọn chính sách backpressure cũng là chọn cách xử lý phần tử

Khi nguồn có thể phát nhanh hơn downstream, ứng dụng phải quyết định giữ, bỏ hay từ chối dữ liệu. Với phần tử giữ tài nguyên, mỗi chính sách cần có cách xử lý vòng đời tương ứng.

### Bỏ phần tử mới khi downstream chưa sẵn sàng

`onBackpressureDrop` loại bỏ phần tử đến trong lúc downstream không có demand. Có thể cung cấp callback riêng cho phần tử bị drop:

```java
Flux<Event> events = hotEventSource()
    .onBackpressureDrop(event -> {
        droppedMetrics.increment();
        event.release();
    });
```

Callback này là nơi ứng dụng xử lý phần tử bị drop theo chính sách đã chọn, ví dụ tăng bộ đếm và giải phóng payload. Chiến lược này phù hợp với dữ liệu có thể mất như một số loại telemetry hoặc cập nhật không cần lưu mọi trạng thái trung gian.

### Chỉ giữ giá trị mới nhất

`onBackpressureLatest` giữ lại giá trị mới nhất khi downstream chậm; giá trị đang chờ có thể bị thay thế bởi giá trị mới hơn:

```java
Flux<State> states = hotStateSource()
    .onBackpressureLatest()
    .doOnDiscard(State.class, State::release);
```

Chính sách này phù hợp khi trạng thái hiện tại quan trọng hơn mọi thay đổi trung gian, chẳng hạn vị trí hiện tại hoặc snapshot mới nhất. Không phù hợp với giao dịch, sự kiện kiểm toán hoặc dữ liệu cần xử lý đủ từng phần tử.

### Buffer có giới hạn

`onBackpressureBuffer(maxSize)` giữ phần tử chưa được tiêu thụ trong queue có giới hạn. Khi vượt giới hạn, toán tử báo lỗi overflow thay vì cho buffer tăng không giới hạn:

```java
Flux<Payload> buffered = payloadSource
    .onBackpressureBuffer(256)
    .doOnDiscard(Payload.class, Payload::release);
```

Hook discard giúp dọn dẹp những payload bị các toán tử upstream hỗ trợ discard loại bỏ, chẳng hạn phần tử còn trong buffer khi queue được dọn lúc kết thúc hoặc hủy. Hãy xác minh discard support của operator trong phiên bản Reactor cụ thể và bảo đảm callback chỉ giải phóng một lần.

Buffer hấp thụ burst ngắn, không giải quyết tình trạng tốc độ đến trung bình luôn lớn hơn tốc độ xử lý. Với dữ liệu quan trọng, cần cân nhắc ghi bền vững vào broker hoặc log để consumer có thể đọc lại, thay vì dựa vào queue trong bộ nhớ.

## 5. Tránh giải phóng hai lần cùng một phần tử

Tài nguyên có reference count như Netty `ByteBuf` thường yêu cầu cân bằng số lần retain và release. Giải phóng thiếu gây rò rỉ; giải phóng lặp có thể gây lỗi truy cập bộ nhớ hoặc lỗi reference count.

Một phần tử chỉ nên có một chủ thể chịu trách nhiệm cleanup tại mỗi đường đi:

- Phần tử được xử lý: callback xử lý bình thường giải phóng sau khi hoàn thành hoặc chuyển quyền sở hữu rõ ràng.
- Phần tử bị drop: callback drop chịu trách nhiệm cleanup.
- Phần tử bị discard bởi toán tử: discard hook chịu trách nhiệm cleanup.
- Tài nguyên gắn với subscription: `using` hoặc `usingWhen` quản lý cleanup khi kết thúc.

Không gắn cùng một thao tác `release()` ở nhiều callback có thể được gọi cho cùng một lần discard. Ví dụ, nếu `onBackpressureDrop` đã nhận callback và giải phóng phần tử bị drop, không nên giả định có thể thêm một hook khác cũng giải phóng cùng phần tử mà không kiểm tra ngữ nghĩa cụ thể của operator. Hãy xác định đường cleanup nào thực sự được gọi và kiểm thử số lần release.

Với object mutable hoặc tài nguyên có ownership phức tạp, nên viết hàm cleanup idempotent nếu thư viện cho phép. Tuy nhiên, idempotency không thay thế việc hiểu đúng ownership và reference counting.

## 6. Quản lý tài nguyên theo vòng đời subscription với using

Một số tài nguyên được tạo riêng cho mỗi subscription, chẳng hạn stream đọc file, cursor hoặc session. `using` giúp liên kết việc tạo tài nguyên, sử dụng tài nguyên và cleanup với vòng đời Publisher.

```java
Flux<String> lines = Flux.using(
    () -> openLineReader(path),
    reader -> Flux.fromIterable(reader.readAllLines()),
    LineReader::close
);
```

Supplier tạo một `LineReader` khi subscribe. Hàm thứ hai tạo Publisher sử dụng reader. Hàm cleanup được gọi khi luồng kết thúc hoặc bị hủy theo quy tắc của `using`. Mỗi subscription có tài nguyên riêng thay vì chia sẻ một reader đã bị đóng với subscription khác.

`using` phù hợp với cleanup đồng bộ. Nếu việc đóng tài nguyên cũng là thao tác bất đồng bộ và cần được chờ hoàn tất, hãy dùng `usingWhen`.

## 7. Dùng usingWhen cho cleanup bất đồng bộ

`usingWhen` quản lý tài nguyên được lấy từ một Publisher và cho phép định nghĩa cleanup riêng cho ba đường kết thúc: hoàn tất, lỗi và cancellation.

```java
Mono<Result> result = Mono.usingWhen(
    connectionFactory.create(),
    connection -> query(connection),
    connection -> connection.close(),
    (connection, error) ->
        connection.rollback().then(connection.close()),
    connection ->
        connection.rollback().then(connection.close())
);
```

Trong ví dụ:

- `connectionFactory.create()` cấp một connection cho subscription.
- `query(connection)` thực hiện công việc và trả về Publisher kết quả.
- Khi hoàn tất bình thường, `connection.close()` được chạy.
- Khi lỗi, transaction được rollback rồi connection được đóng.
- Khi cancellation, transaction cũng được rollback rồi connection được đóng.

`usingWhen` chờ Publisher cleanup tương ứng hoàn tất trước khi phát tín hiệu kết thúc phù hợp xuống downstream. Lỗi trong quá trình cleanup cũng có thể ảnh hưởng đến tín hiệu cuối cùng; cần thiết kế và kiểm thử chính sách xử lý lỗi cleanup, đặc biệt khi nguồn chính đã lỗi.

Không nên thay cleanup bất đồng bộ bằng một lời gọi blocking trong `doFinally`. Callback `doFinally` phù hợp với thao tác đồng bộ ngắn như dừng timer hoặc ghi metrics; nó không cung cấp Publisher để Reactor chờ một thao tác đóng tài nguyên bất đồng bộ.

## 8. Phân biệt doFinally, doOnCancel và usingWhen

| Cơ chế | Khi nào chạy? | Vai trò chính |
|---|---|---|
| `doOnCancel` | Khi nhận yêu cầu cancellation | Quan sát hoặc phản ứng đồng bộ với cancel |
| `doFinally` | Sau complete, error hoặc cancel | Ghi nhận loại tín hiệu cuối, dừng timer hoặc cleanup đồng bộ |
| `using` | Khi resource scope kết thúc hoặc bị hủy | Tạo và cleanup tài nguyên đồng bộ theo subscription |
| `usingWhen` | Theo complete, error hoặc cancel | Cleanup tài nguyên bằng Publisher bất đồng bộ và chờ kết quả |
| `doOnDiscard` | Khi phần tử bị toán tử upstream hỗ trợ discard loại bỏ | Dọn dẹp tài nguyên gắn với phần tử bị bỏ |

Không dùng `doOnCancel` để thay cho cleanup khi complete hoặc error vì callback đó chỉ dành cho cancellation. Không dùng `doFinally` để giả định rằng một thao tác async đã hoàn tất; callback không có cơ chế trả Publisher cleanup cho Reactor chờ.

## 9. Kết hợp cleanup phần tử với cleanup tài nguyên subscription

Một pipeline có thể đồng thời sở hữu một tài nguyên ở cấp subscription và nhiều tài nguyên gắn với từng phần tử. Ví dụ, ứng dụng mở một session để đọc các frame, mỗi frame là buffer có reference count:

```java
Flux<Message> messages = Flux.usingWhen(
    sessionFactory.open(),
    session -> session.receiveFrames()
        .filter(ByteBuf::isReadable)
        .doOnDiscard(ByteBuf.class, ByteBuf::release)
        .map(frame -> {
            try {
                return decoder.decodeCopy(frame);
            } finally {
                frame.release();
            }
        }),
    session -> session.close(),
    (session, error) -> session.abort().then(session.close()),
    session -> session.abort().then(session.close())
);
```

Session được cleanup theo complete/error/cancel nhờ `usingWhen`. Frame được giải phóng khi bị filter loại bỏ nhờ `doOnDiscard`, hoặc sau khi được giải mã thành công/thất bại nhờ `finally`. Hai cơ chế quản lý hai loại ownership khác nhau.

Ví dụ giả định `decodeCopy` tạo một `Message` độc lập với vùng nhớ của frame. Nếu `Message` giữ tham chiếu đến buffer, cần chuyển ownership hoặc retain trước khi release. Cũng cần xác nhận `session.receiveFrames()` và các operator trung gian có hỗ trợ discard cho kiểu frame đang dùng.

## 10. Kiểm thử phần tử bị bỏ và cleanup

Kiểm thử nên xác nhận cả kết quả downstream lẫn số lần cleanup. Với phần tử bị `filter` loại bỏ, có thể dùng bộ đếm:

```java
AtomicInteger released = new AtomicInteger();

Flux<Integer> values = Flux.just(1, 2, 3, 4)
    .filter(value -> value % 2 == 0)
    .doOnDiscard(Integer.class, value -> released.incrementAndGet());

StepVerifier.create(values)
    .expectNext(2, 4)
    .verifyComplete();

assertEquals(2, released.get());
```

Trong ví dụ dùng `Integer`, bộ đếm chỉ minh họa discard hook. Với tài nguyên thật, callback sẽ giải phóng buffer hoặc đóng payload theo API tương ứng.

Có thể kiểm tra cleanup khi cancellation với một tài nguyên được quản lý bằng `usingWhen`:

```java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> source = Flux.usingWhen(
    Mono.fromSupplier(Resource::new),
    resource -> Flux.interval(Duration.ofMillis(100)).map(tick -> resource.read()),
    resource -> Mono.fromRunnable(() -> {
        resource.close();
        closed.incrementAndGet();
    }),
    (resource, error) -> Mono.fromRunnable(() -> {
        resource.close();
        closed.incrementAndGet();
    }),
    resource -> Mono.fromRunnable(() -> {
        resource.close();
        closed.incrementAndGet();
    })
);

StepVerifier.withVirtualTime(() -> source)
    .thenAwait(Duration.ofMillis(100))
    .expectNextCount(1)
    .thenCancel()
    .verify();

assertEquals(1, closed.get());
```

Test này xác nhận cleanup cancellation được chạy sau khi Subscriber hủy. `Resource` là kiểu tài nguyên minh họa có các phương thức `read()` và `close()`; trong ứng dụng, nên dùng loại tài nguyên và cleanup Publisher thực tế. Với cleanup bất đồng bộ, cần chờ hoặc xác minh Publisher cleanup hoàn tất trước khi kiểm tra trạng thái cuối.

Ngoài các test trên, hãy kiểm tra overflow, lỗi trong mapper, lỗi cleanup, nhiều subscription và trường hợp downstream chỉ nhận một phần dữ liệu rồi cancel. Với buffer có reference count, số lần retain/release phải cân bằng ở mọi đường kết thúc.

## 11. Những lỗi quản lý tài nguyên thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ release trong `doOnNext` | Phần tử bị filter hoặc nằm trong buffer lúc cancel không đi qua callback | Dùng discard hook cho operator hỗ trợ và cleanup rõ ràng cho phần tử được tiêu thụ |
| Cho rằng cancel tự đóng mọi tài nguyên | File, session hoặc native buffer có thể còn mở | Quản lý resource scope bằng `using` hoặc `usingWhen` |
| Dùng buffer không giới hạn | Backlog tăng có thể làm cạn heap | Dùng buffer hữu hạn và định nghĩa overflow policy |
| Dùng drop nhưng không xử lý phần tử bị drop | Tài nguyên gắn với phần tử bị rò rỉ | Cung cấp drop callback hoặc discard hook đúng đường đi |
| Đặt `doOnDiscard` trước operator loại bỏ | Hook không nằm ở downstream context phù hợp để bao phủ operator đó | Đặt hook sau các operator có thể discard |
| Giải phóng cùng phần tử ở nhiều callback | Double release hoặc lỗi reference count | Xác định một chủ thể cleanup cho mỗi đường đi |
| Đóng tài nguyên async trong `doFinally` bằng blocking | Chặn thread và không quản lý đúng thời gian cleanup | Dùng `usingWhen` với Publisher cleanup |
| Không kiểm tra cleanup khi error | Tài nguyên hoặc transaction có thể bị bỏ lại | Định nghĩa error cleanup và kiểm thử riêng |

## 12. Checklist trước khi đưa pipeline vào vận hành

1. Phần tử nào có tài nguyên cần release, close hoặc dispose?
2. Phần tử có thể bị filter, drop, latest, overflow hoặc nằm trong queue khi cancel không?
3. Những operator nào trong pipeline hỗ trợ discard và `doOnDiscard` đã được đặt đúng vị trí chưa?
4. Phần tử được tiêu thụ bình thường được giải phóng ở đâu?
5. Có nguy cơ cùng một phần tử bị cleanup hai lần không?
6. Tài nguyên được tạo theo subscription có được quản lý bằng `using` hoặc `usingWhen` không?
7. Cleanup có chính sách riêng cho complete, error và cancel không?
8. Buffer có giới hạn và overflow policy rõ ràng không?
9. Kiểm thử có xác nhận cleanup sau filter, drop, overflow, error và cancellation không?

Quản lý tài nguyên trong pipeline reactive đòi hỏi xử lý cả phần tử không đến được downstream lẫn tài nguyên sống theo subscription. Dùng `doOnDiscard` cho phần tử bị loại bởi operator hỗ trợ, callback drop cho chính sách drop cụ thể và `using`/`usingWhen` cho tài nguyên được cấp phát theo subscription. Khi xác định rõ ownership, giới hạn buffer và kiểm thử mọi đường complete/error/cancel, pipeline có thể dừng đúng lúc mà không để lại tài nguyên chưa được giải phóng.
