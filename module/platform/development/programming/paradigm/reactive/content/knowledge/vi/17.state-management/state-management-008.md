# Ảnh chụp trạng thái, phát lại sự kiện và tái tạo kết quả

Trong một hệ thống reactive, trạng thái hiện tại thường được hình thành từ nhiều sự kiện đến theo thời gian. Ví dụ, trạng thái đơn hàng có thể thay đổi qua các sự kiện tạo đơn, xác nhận thanh toán, đóng gói, giao hàng và hủy đơn. Khi dịch vụ khởi động lại hoặc cần dựng lại một bản chiếu dữ liệu, ứng dụng phải đọc lại lịch sử sự kiện và áp dụng chúng theo đúng thứ tự.

Nếu lịch sử rất dài, việc phát lại từ sự kiện đầu tiên mỗi lần khởi động có thể tốn nhiều thời gian. **Ảnh chụp trạng thái** (*snapshot*) lưu lại kết quả đã tính đến một vị trí xác định trong lịch sử. Khi khôi phục, ứng dụng nạp snapshot gần nhất rồi chỉ phát lại các sự kiện xuất hiện sau vị trí đó. Snapshot giúp tăng tốc quá trình khôi phục; nhật ký sự kiện vẫn là nguồn dữ liệu gốc để kiểm chứng và tái tạo trạng thái.

Bài học thuộc module `REACTIVE_PROGRAMMING`, tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung trình bày cách xây dựng reducer xác định, tạo và lưu snapshot, phát lại sự kiện bằng Reactor, xử lý sự kiện trùng hoặc sai thứ tự, và kiểm tra tính nhất quán khi khôi phục.

## 1. Trạng thái được tái tạo từ lịch sử sự kiện

Một hệ thống theo hướng sự kiện lưu lại những gì đã xảy ra thay vì chỉ lưu trạng thái cuối cùng. Một sự kiện thường bất biến sau khi được ghi nhận và có định danh, khóa aggregate, số thứ tự hoặc phiên bản cùng dữ liệu cần thiết để diễn giải thay đổi.

Ví dụ lịch sử của một đơn hàng:

```text
OrderCreated       sequence 1
PaymentCaptured    sequence 2
ItemsPacked        sequence 3
OrderShipped       sequence 4
```

Reducer nhận trạng thái trước đó và một sự kiện, sau đó tạo ra trạng thái tiếp theo:

```text
State ban đầu
    |
    | apply(OrderCreated)
    v
State version 1
    |
    | apply(PaymentCaptured)
    v
State version 2
    |
    | apply(ItemsPacked)
    v
State version 3
    |
    | apply(OrderShipped)
    v
State version 4
```

Về mặt khái niệm:

\[
S_n = reduce(S_0, E_1, E_2, \ldots, E_n)
\]

Trong đó `S0` là trạng thái ban đầu, `E1...En` là các sự kiện theo thứ tự và `Sn` là trạng thái sau khi áp dụng toàn bộ lịch sử. Nếu reducer xác định và các sự kiện được giữ nguyên, cùng một trạng thái ban đầu cùng một chuỗi sự kiện sẽ tạo ra cùng một kết quả.

### Reducer nên có tính xác định

Reducer nên là một phép biến đổi thuần: đầu ra chỉ phụ thuộc trạng thái đầu vào và sự kiện hiện tại. Không nên gọi dịch vụ mạng, đọc đồng hồ hệ thống, tạo số ngẫu nhiên hoặc ghi cơ sở dữ liệu ngay trong reducer. Những yếu tố đó khiến cùng một lịch sử có thể tạo ra kết quả khác nhau khi replay.

Không nên:

```java
OrderState apply(OrderState state, OrderEvent event) {
    if (event.type() == PAYMENT_CAPTURED) {
        // Giá trị thay đổi theo thời điểm chạy lại.
        return state.withPaidAt(Instant.now());
    }
    return state;
}
```

Thay vào đó, dữ liệu thời gian cần thiết phải được ghi trong sự kiện:

```java
OrderState apply(OrderState state, OrderEvent event) {
    if (event.type() == PAYMENT_CAPTURED) {
        return state.withPaidAt(event.occurredAt());
    }
    return state;
}
```

Nếu trạng thái cần một giá trị được tạo từ bên ngoài, hãy tạo giá trị đó trước khi ghi sự kiện hoặc đưa nó vào dữ liệu sự kiện. Khi replay, reducer chỉ sử dụng dữ liệu đã được lưu.

## 2. Snapshot lưu trạng thái tại một vị trí cụ thể

Snapshot không chỉ là một bản sao trạng thái. Nó phải ghi rõ trạng thái đó tương ứng với phần nào của lịch sử. Một snapshot thường chứa:

- `aggregateId`: đối tượng hoặc luồng nghiệp vụ mà snapshot đại diện.
- `version` hoặc `sequence`: số thứ tự của sự kiện cuối cùng đã được áp dụng.
- `state`: dữ liệu trạng thái tại phiên bản đó.
- `createdAt`: thời điểm tạo snapshot để quan sát và quản trị.
- `schemaVersion`: phiên bản cấu trúc snapshot nếu cần hỗ trợ nâng cấp định dạng.

Ví dụ:

```java
record OrderSnapshot(
    String orderId,
    long version,
    OrderState state,
    Instant createdAt,
    int schemaVersion
) {}
```

Nếu snapshot có `version = 500`, trạng thái trong snapshot phải phản ánh chính xác các sự kiện từ đầu đến sự kiện số 500. Khi khôi phục, chỉ phát lại các sự kiện có sequence lớn hơn 500.

```text
Event log:
  1  2  3  ...  498  499  500 | 501  502  503 ...
                            |
                         Snapshot
                         version 500

Recovery:
  load snapshot at 500
          |
          +---- replay 501, 502, 503, ...
                         |
                         v
                 Current state
```

Nếu snapshot lưu trạng thái đến version 500 nhưng metadata lại ghi 499, sự kiện 500 sẽ bị áp dụng lần nữa. Nếu metadata ghi 501, sự kiện 501 có thể bị bỏ qua. Vì vậy, trạng thái và checkpoint phải được lưu như một đơn vị nhất quán.

### Snapshot là điểm khởi đầu tăng tốc, không phải lịch sử thay thế

Trong mô hình event sourcing, event log vẫn là nguồn dữ liệu có thẩm quyền. Snapshot là dữ liệu dẫn xuất có thể tạo lại từ log. Nếu snapshot bị hỏng hoặc sai phiên bản, hệ thống có thể bỏ snapshot đó và phát lại từ một snapshot cũ hơn hoặc từ trạng thái ban đầu.

Không nên xóa lịch sử sự kiện chỉ vì đã tạo snapshot, trừ khi hệ thống có một chính sách lưu trữ và khả năng phục hồi được thiết kế riêng. Snapshot không thay thế yêu cầu lưu trữ, kiểm toán và đối soát của event log.

## 3. Phát lại sự kiện bằng `Flux.reduce`

Khi event store cung cấp một `Flux<OrderEvent>` đã được sắp xếp theo sequence, `reduce` là cách trực tiếp để tái tạo trạng thái cuối cùng. Nó giữ một accumulator và chỉ phát kết quả khi nguồn hoàn tất.

```java
Mono<OrderState> rebuildFromBeginning(String orderId) {
    return eventStore.readAll(orderId)
        .reduce(OrderState.initial(orderId), orderReducer::apply);
}
```

`readAll` trả về các sự kiện theo thứ tự. `reduce` áp dụng từng sự kiện vào trạng thái hiện tại và phát một `Mono<OrderState>` khi lịch sử đã được đọc hết. Nếu không có sự kiện, overload có seed phát trạng thái ban đầu.

Nếu cần quan sát trạng thái sau từng sự kiện, dùng `scan`:

```java
Flux<OrderState> stateHistory = eventStore.readAll(orderId)
    .scan(OrderState.initial(orderId), orderReducer::apply);
```

`scan` phát cả trạng thái ban đầu rồi phát trạng thái sau mỗi sự kiện. Đây là cách hữu ích để hiển thị tiến trình replay, cập nhật projection hoặc kiểm tra kết quả trung gian. `reduce` phù hợp khi chỉ cần trạng thái cuối; `scan` phù hợp khi cần chuỗi trạng thái.

### `reduce` và `scan` khác nhau ở thời điểm phát

| Operator | Đầu ra | Thời điểm phát | Bộ nhớ tích lũy |
|---|---|---|---|
| `reduce(seed, reducer)` | Một trạng thái cuối. | Khi nguồn hoàn tất. | Giữ accumulator hiện tại. |
| `scan(seed, reducer)` | Trạng thái ban đầu và từng trạng thái tiếp theo. | Sau mỗi sự kiện. | Giữ accumulator hiện tại; downstream nhận thêm các trạng thái. |
| `collectList()` | Danh sách toàn bộ sự kiện. | Khi nguồn hoàn tất. | Giữ mọi phần tử; không phù hợp với lịch sử lớn nếu không giới hạn. |

Để tái tạo trạng thái, thường không cần `collectList()` rồi mới lặp qua danh sách. `reduce` áp dụng từng sự kiện khi nó đến và chỉ giữ trạng thái hiện tại, nên bộ nhớ không tăng theo tổng số sự kiện nếu reducer không tự giữ lịch sử.

## 4. Khôi phục từ snapshot gần nhất

Quy trình khôi phục phổ biến gồm ba bước:

1. Tải snapshot mới nhất hợp lệ của aggregate.
2. Đọc các sự kiện có sequence lớn hơn version trong snapshot.
3. Áp dụng các sự kiện đó lên trạng thái snapshot bằng reducer.

Ví dụ:

```java
Mono<OrderState> rebuild(String orderId) {
    return snapshotStore.loadLatest(orderId)
        .defaultIfEmpty(OrderSnapshot.initial(orderId))
        .flatMap(snapshot -> {
            if (snapshot.version() != snapshot.state().version()) {
                return Mono.error(new IllegalStateException(
                    "Snapshot version does not match state version"
                ));
            }

            return eventStore.readAfter(orderId, snapshot.version())
                .reduce(snapshot.state(), orderReducer::apply);
        });
}
```

Đoạn mã giả định:

- `loadLatest` trả về `Mono<OrderSnapshot>` rỗng nếu chưa có snapshot.
- `OrderSnapshot.initial` chứa trạng thái ban đầu với version 0.
- `readAfter(orderId, version)` chỉ phát sự kiện có sequence lớn hơn version, theo thứ tự tăng dần.
- `OrderState.version()` là sequence cuối cùng đã được áp dụng.

Điểm quan trọng là điều kiện đọc `sequence > snapshot.version`. Không được đọc lại sự kiện đã được phản ánh trong snapshot. Đồng thời, không được bỏ qua sự kiện tiếp theo chỉ vì nó chưa có trong trang dữ liệu hiện tại; việc phân trang phải tiếp tục cho đến checkpoint hoặc điểm cuối đã xác định.

## 5. Kiểm tra sequence và xử lý sự kiện trùng lặp

Event store có thể cung cấp dữ liệu theo cơ chế at-least-once, hoặc một luồng replay có thể gặp lại sự kiện do retry. Reducer cần có quy tắc rõ ràng cho sequence.

```java
OrderState apply(OrderState current, OrderEvent event) {
    if (event.sequence() <= current.version()) {
        // Sự kiện đã được phản ánh trong trạng thái hiện tại.
        return current;
    }

    if (event.sequence() != current.version() + 1) {
        throw new IllegalStateException(
            "Missing event: expected " + (current.version() + 1)
                + " but received " + event.sequence()
        );
    }

    return switch (event.type()) {
        case PAYMENT_CAPTURED -> current.withPayment(
            event.sequence(), event.amount()
        );
        case SHIPPED -> current.withStatus(
            event.sequence(), OrderStatus.SHIPPED
        );
        case CANCELLED -> current.withStatus(
            event.sequence(), OrderStatus.CANCELLED
        );
    };
}
```

Quy tắc này bỏ qua sự kiện có sequence đã được áp dụng và từ chối khoảng trống sequence. Cách xử lý cụ thể phụ thuộc nguồn dữ liệu: một hệ thống có thể cần phát lại từ checkpoint trước, truy vấn lại event store hoặc đưa aggregate vào trạng thái cần đối soát.

Không nên âm thầm bỏ qua mọi sự kiện sai thứ tự. Nếu trạng thái version là 10 mà event 12 đến trước event 11, việc áp dụng event 12 có thể tạo trạng thái không hợp lệ. Với một aggregate, cách đơn giản nhất là đọc theo sequence và áp dụng tuần tự. Nếu nguồn phân phối song song, cần sắp xếp hoặc phân vùng theo aggregate trước khi reducer nhận dữ liệu.

Sequence giúp phát hiện sự kiện lặp hoặc thiếu, nhưng không tự giải quyết mọi trường hợp trùng lặp. Event store nên có ràng buộc duy nhất trên cặp `(aggregateId, sequence)` và định danh `eventId`. Nếu cùng sequence xuất hiện với payload khác nhau, đó là lỗi dữ liệu cần được phát hiện, không nên coi như một bản lặp hợp lệ.

## 6. Tạo snapshot định kỳ bằng `scan`

Sau khi tái tạo trạng thái, dịch vụ có thể lưu snapshot theo chu kỳ, chẳng hạn sau mỗi 500 sự kiện. `scan` tạo trạng thái sau mỗi sự kiện; `filter` chọn những version đến ngưỡng; `concatMap` lưu tuần tự để không ghi snapshot vượt thứ tự.

```java
Mono<Void> createSnapshots(String orderId) {
    return snapshotStore.loadLatest(orderId)
        .defaultIfEmpty(OrderSnapshot.initial(orderId))
        .flatMapMany(snapshot -> eventStore.readAfter(
                orderId, snapshot.version()
            )
            .scan(snapshot.state(), orderReducer::apply)
            .skip(1)
            .filter(state -> state.version() % 500 == 0)
            .concatMap(state -> snapshotStore.save(
                new OrderSnapshot(
                    orderId,
                    state.version(),
                    state,
                    Instant.now(),
                    1
                )
            ))
        )
        .then();
}
```

`scan` phát seed đầu tiên, nên `skip(1)` bỏ trạng thái snapshot ban đầu và chỉ xét trạng thái sau các sự kiện mới. `concatMap` đợi mỗi lần lưu snapshot hoàn tất rồi mới lưu lần tiếp theo. Điều này giữ thứ tự ghi và tránh tạo nhiều thao tác lưu đồng thời cho cùng aggregate.

Ví dụ dùng `Instant.now()` ở bước tạo snapshot là phù hợp cho metadata `createdAt`, vì đây là thời điểm tạo bản snapshot chứ không phải logic reducer dùng để tái tạo trạng thái. Trạng thái nghiệp vụ vẫn phải được tính hoàn toàn từ snapshot trước đó và chuỗi sự kiện.

### Snapshot cần ghi có điều kiện

Trong hệ thống có nhiều consumer hoặc nhiều tiến trình cùng có thể tạo snapshot, việc ghi snapshot cần bảo vệ khỏi ghi lùi version. Một cách là dùng optimistic concurrency:

```text
Save snapshot only if storedVersion < candidateVersion
```

Hoặc dùng khóa/transaction theo aggregate. Snapshot version 600 không được bị ghi đè bởi một tiến trình đang replay chậm hơn và chỉ có version 550. Nếu cùng version được ghi lại, nội dung phải tương đương theo schema và reducer tương ứng.

## 7. Tính nhất quán giữa snapshot và event log

Một snapshot chỉ hữu ích nếu trạng thái và checkpoint được lưu nhất quán. Hãy xem xét tình huống:

1. Consumer đã áp dụng đến event 500.
2. Nó ghi snapshot state version 500.
3. Ứng dụng crash trước khi lưu metadata checkpoint 500.
4. Khi khởi động lại, consumer đọc snapshot version 500 nhưng checkpoint bên ngoài vẫn là 480.

Nếu hai giá trị được quản lý độc lập, hệ thống có thể phát lại event 481–500 lần nữa. Nếu reducer bỏ duplicate theo version thì có thể tránh thay đổi trạng thái lần hai, nhưng hệ thống vẫn tốn công đọc lại và có nguy cơ sai nếu side effect nằm trong reducer.

Hãy lưu snapshot và version trong cùng một bản ghi hoặc transaction nếu cùng một cơ sở dữ liệu. Nếu snapshot và offset nằm ở hai hệ thống khác nhau, cần một giao thức checkpoint có thể phục hồi sau crash, chẳng hạn ghi snapshot trước rồi cập nhật offset theo điều kiện version, hoặc lưu một bản ghi snapshot chứa luôn offset nguồn.

**Không ghi checkpoint vượt quá trạng thái đã lưu bền vững.** Nếu offset đã tiến đến 700 nhưng snapshot chỉ lưu trạng thái đến 650 và các thay đổi 651–700 chưa được lưu ở nơi khác, khi khởi động lại hệ thống có thể bỏ mất dữ liệu.

### Replay theo một high-water mark

Khi nguồn tiếp tục nhận sự kiện trong lúc khôi phục, cần xác định ranh giới lịch sử mà lần replay đang xử lý. Có thể lấy một high-water mark `H` và phát lại từ `snapshot.version + 1` đến `H`. Sau khi hoàn tất, hệ thống chuyển sang theo dõi sự kiện mới hơn H.

Để không bỏ lỡ sự kiện phát sinh trong lúc replay, nguồn cần hỗ trợ cursor bền vững hoặc một cơ chế nối lịch sử với luồng live một cách nguyên tử. Ví dụ, broker có thể cho phép subscribe từ offset H rồi tiếp tục đọc sự kiện mới; event store có thể cung cấp một cursor ổn định để đọc đến H và sau đó tail từ vị trí kế tiếp. Nếu chỉ subscribe một hot publisher sau khi replay xong, sự kiện phát ra trong khoảng replay có thể bị bỏ lỡ.

## 8. Phân biệt replay bền vững với replay trong bộ nhớ của Reactor

Reactor có các sink và operator giúp nhiều subscriber nhận lại dữ liệu đã phát, nhưng phạm vi của chúng là bộ nhớ của tiến trình.

```java
Sinks.Many<OrderEvent> recentEvents = Sinks.many()
    .replay()
    .limit(500);

Flux<OrderEvent> liveAndRecent = recentEvents.asFlux();
```

Sink replay giữ tối đa 500 sự kiện gần nhất trong bộ nhớ và phát chúng cho subscriber mới theo chính sách replay. Nó hữu ích khi một thành phần mới tham gia cần một đoạn lịch sử ngắn cùng luồng live.

Tuy nhiên, sink này không phải event store bền vững:

- Dữ liệu mất khi tiến trình dừng hoặc khởi động lại.
- Lịch sử chỉ tồn tại trong giới hạn cấu hình và thời gian sống của sink.
- Nó không cung cấp transaction, lưu trữ lâu dài hoặc checkpoint qua nhiều tiến trình.
- Subscriber đến muộn chỉ nhận phần lịch sử mà sink còn giữ.

Các lựa chọn cần phân biệt:

| Cơ chế | Phạm vi lịch sử | Có bền vững qua restart? | Mục đích |
|---|---|---|---|
| `Sinks.many().replay().limit(n)` | n phần tử gần nhất trong bộ nhớ. | Không. | Phát lại ngắn hạn cho subscriber mới. |
| `Flux.cache(n)` | Tín hiệu được cache trong vòng đời publisher. | Không. | Dùng lại kết quả đã phát trong cùng tiến trình. |
| Event store/database/log | Lịch sử được lưu theo chính sách lưu trữ. | Có, tùy độ bền của hệ thống lưu trữ. | Tái tạo trạng thái và phục hồi sau restart. |
| Snapshot store | Trạng thái tại một version/checkpoint. | Có, nếu lưu bền vững. | Rút ngắn thời gian replay. |

Trong hệ thống cần phục hồi, snapshot và event log nên được lưu trong hạ tầng bền vững. Sink replay có thể bổ sung trải nghiệm live cho các subscriber trong tiến trình, nhưng không thay thế cơ chế lưu trữ và replay của event store.

## 9. Không dùng `flatMap` để áp dụng song song các sự kiện phụ thuộc thứ tự

Một aggregate thường yêu cầu sự kiện được áp dụng theo sequence. Nếu mỗi sự kiện thay đổi trạng thái phụ thuộc kết quả sự kiện trước, không thể áp dụng chúng song song tùy ý.

Không nên:

```java
Flux<OrderState> unsafe = events
    .flatMap(event -> Mono.fromCallable(() -> reducer.apply(sharedState, event)));
```

Đoạn mã này còn có vấn đề chia sẻ mutable state và thứ tự hoàn tất không được bảo đảm. Các sự kiện có thể cạnh tranh cập nhật trạng thái.

Với một aggregate, dùng phép tích lũy tuần tự:

```java
Mono<OrderState> rebuilt = events
    .reduce(snapshot.state(), orderReducer::apply);
```

`reduce` áp dụng từng phần tử theo thứ tự mà publisher phát ra. Nếu cần xử lý nhiều aggregate song song, có thể phân vùng theo `aggregateId`, sau đó xử lý tuần tự bên trong từng phân vùng và giới hạn concurrency giữa các aggregate.

```java
Flux<OrderState> rebuiltAggregates = events
    .groupBy(OrderEvent::aggregateId)
    .flatMap(group -> group
        .concatMap(event -> stateService.apply(group.key(), event))
        .last()
    , 16);
```

Ví dụ minh họa xử lý tuần tự trong từng aggregate và tối đa 16 nhóm đồng thời. `groupBy` cần được dùng với cardinality có thể kiểm soát và mọi nhóm phải được tiêu thụ. Nếu số aggregate không giới hạn hoặc luồng dài hạn có nhiều khóa, hãy dùng partition hữu hạn hoặc một cơ chế phân vùng bền vững thay vì tạo publisher con không giới hạn.

## 10. Schema evolution của snapshot và sự kiện

Theo thời gian, cấu trúc trạng thái hoặc sự kiện có thể thay đổi. Một snapshot được ghi bằng phiên bản ứng dụng cũ có thể không đọc được trực tiếp bằng phiên bản mới. Cần lưu `schemaVersion` và có chiến lược nâng cấp.

Các cách tiếp cận thường gặp:

- **Snapshot migration:** chuyển snapshot cũ sang cấu trúc mới trước khi sử dụng.
- **Snapshot invalidation:** bỏ qua snapshot cũ và replay từ một snapshot mới hơn hoặc từ event log nếu khối lượng cho phép.
- **Event upcasting:** chuyển sự kiện phiên bản cũ thành dạng domain hiện tại khi đọc.
- **Backward-compatible fields:** thêm trường có giá trị mặc định và tránh thay đổi ý nghĩa của trường cũ.

Không nên thay đổi cách diễn giải một event cũ mà không có version hoặc migration rõ ràng. Nếu reducer mới tính event cũ theo quy tắc mới, trạng thái replay có thể khác trạng thái đã được tạo ở quá khứ. Với thay đổi nghiệp vụ có ảnh hưởng lớn, hãy định nghĩa rõ liệu cần tái tạo theo quy tắc hiện tại hay giữ nguyên kết quả lịch sử.

## 11. Backpressure khi replay lịch sử lớn

Event log có thể chứa hàng triệu sự kiện. Replay cần đọc theo luồng và tôn trọng demand thay vì nạp toàn bộ lịch sử vào `List`.

```java
Mono<OrderState> rebuildFromSnapshot(String orderId) {
    return snapshotStore.loadLatest(orderId)
        .defaultIfEmpty(OrderSnapshot.initial(orderId))
        .flatMap(snapshot -> eventStore.readAfter(
                orderId, snapshot.version()
            )
            .limitRate(256)
            .reduce(snapshot.state(), orderReducer::apply)
        );
}
```

`limitRate(256)` chia request upstream thành các đợt nhỏ hơn tại ranh giới đó. Nó không giới hạn kích thước dữ liệu mà event store tự nạp trước bên trong; repository cũng cần đọc theo cursor hoặc page có giới hạn để tránh giữ toàn bộ log trong bộ nhớ.

Nếu replay có bước I/O blocking, hãy chuyển phần blocking đó lên `boundedElastic` tại adapter nguồn. Nếu event store trả về publisher non-blocking, không cần thêm scheduler chỉ để chuyển thread. Trạng thái reducer nên được cập nhật tuần tự cho từng aggregate, trong khi các aggregate độc lập có thể được xử lý đồng thời với concurrency giới hạn.

Snapshot có thể được tạo theo số sự kiện hoặc theo thời gian. Chu kỳ quá ngắn làm tăng chi phí ghi snapshot; chu kỳ quá dài khiến thời gian replay sau restart tăng. Hãy chọn chu kỳ dựa trên tốc độ sự kiện, chi phí lưu snapshot, thời gian khôi phục mục tiêu và khả năng chịu tải của event store.

## 12. Xử lý lỗi trong quá trình tái tạo

Replay có thể thất bại vì event store không truy cập được, snapshot không hợp lệ, thiếu sequence, payload không tương thích hoặc reducer phát hiện vi phạm bất biến nghiệp vụ.

Không nên lưu snapshot mới nếu replay chưa hoàn tất thành công đến checkpoint đã chọn. Nếu một sự kiện giữa chừng bị lỗi, trạng thái accumulator mới chỉ là kết quả một phần. Hãy giữ snapshot trước đó và checkpoint cũ để có thể thử lại.

```java
Mono<OrderState> rebuildSafely(String orderId) {
    return rebuild(orderId)
        .doOnError(error -> log.error(
            "Cannot rebuild order {}", orderId, error
        ));
}
```

`doOnError` chỉ quan sát lỗi; nó không biến replay lỗi thành trạng thái hợp lệ. Nếu snapshot hiện tại không đọc được, có thể thử snapshot cũ hơn hoặc replay từ đầu theo chính sách rõ ràng. Không nên trả về một trạng thái mặc định rồi tiếp tục xử lý đơn hàng như thể dữ liệu đã được khôi phục đầy đủ.

Nếu một event có payload không tương thích, hãy ghi nhận event ID, aggregate ID và sequence để điều tra. Việc bỏ qua event có thể làm trạng thái sai; chỉ được quarantine hoặc skip khi nghiệp vụ có quy tắc bù trừ được xác định.

## 13. Kiểm thử reducer, snapshot và replay

Reducer thuần có thể được kiểm thử độc lập bằng unit test: cùng trạng thái và sự kiện phải tạo cùng kết quả; sequence trùng phải được xử lý theo chính sách; sequence bị thiếu phải phát hiện lỗi.

Ví dụ kiểm thử replay bằng `StepVerifier`:

```java
OrderState snapshotState = new OrderState(
    "order-42",
    10,
    OrderStatus.PAID,
    new BigDecimal("125.00")
);

Flux<OrderEvent> tail = Flux.just(
    new OrderEvent("order-42", 11, EventType.SHIPPED, null),
    new OrderEvent("order-42", 12, EventType.DELIVERED, null)
);

Mono<OrderState> rebuilt = tail
    .reduce(snapshotState, orderReducer::apply);

StepVerifier.create(rebuilt)
    .assertNext(state -> {
        assertEquals(12, state.version());
        assertEquals(OrderStatus.DELIVERED, state.status());
        assertEquals(new BigDecimal("125.00"), state.paidAmount());
    })
    .verifyComplete();
```

Các kiểu `OrderState`, `OrderEvent`, `EventType` và `orderReducer` trong ví dụ đại diện cho domain model đã được định nghĩa trong ứng dụng. Bài kiểm thử xác minh snapshot version 10 được dùng làm điểm bắt đầu và chỉ hai sự kiện 11, 12 được áp dụng.

Với kiểm thử đầy đủ hơn, hãy bao gồm:

- Không có snapshot: replay từ trạng thái ban đầu.
- Snapshot version N: chỉ đọc sự kiện có sequence lớn hơn N.
- Sự kiện trùng: không làm thay đổi trạng thái lần thứ hai.
- Thiếu sequence hoặc sai thứ tự: replay thất bại hoặc kích hoạt quy trình đối soát.
- Snapshot state và version không khớp: không sử dụng snapshot đó.
- Replay lỗi giữa chừng: không ghi snapshot/checkpoint mới.
- Snapshot lưu thất bại: event log vẫn giữ nguyên và lần khôi phục sau có thể replay lại.
- Sự kiện mới xuất hiện trong lúc replay: không bị bỏ lỡ khi chuyển từ lịch sử sang live stream.
- Schema cũ: migration hoặc upcasting cho kết quả đã định nghĩa.

Khi kiểm thử luồng thời gian hoặc nguồn bất đồng bộ, dùng scheduler ảo và tín hiệu đồng bộ hóa thay cho `Thread.sleep`. Khi kiểm thử repository, nên xác minh thứ tự sequence và ranh giới cursor bằng dữ liệu có nhiều trang.

## 14. Tình huống thực tế: khôi phục trạng thái đơn hàng sau khi service khởi động lại

Một dịch vụ quản lý đơn hàng lưu mọi thay đổi vào event store. Mỗi 500 sự kiện của một đơn hàng, dịch vụ tạo snapshot. Khi service khởi động lại, nó cần dựng lại trạng thái để tiếp tục nhận cập nhật.

Quy trình có thể thực hiện như sau:

1. Tải snapshot có version cao nhất đã được lưu hoàn chỉnh.
2. Kiểm tra schema version, aggregate ID và sự nhất quán giữa metadata với state.
3. Lấy cursor hoặc high-water mark của event store.
4. Đọc sự kiện từ `snapshot.version + 1` đến high-water mark theo thứ tự sequence.
5. Dùng `reduce` để tái tạo trạng thái; kiểm tra duplicate, sequence gap và bất biến nghiệp vụ.
6. Nếu replay thành công, đưa aggregate vào trạng thái phục vụ và tiếp tục nhận sự kiện mới từ cursor kế tiếp.
7. Tạo snapshot mới theo chu kỳ, lưu state cùng version bằng thao tác có điều kiện để không ghi lùi.

Nếu snapshot hỏng, service có thể chọn snapshot cũ hơn hoặc replay từ đầu. Nếu event log có một sequence bị thiếu, service cần dừng khôi phục aggregate đó và kích hoạt đối soát; tiếp tục với trạng thái thiếu dữ liệu có thể làm sai các quyết định nghiệp vụ phía sau.

Đối với hệ thống có nhiều aggregate, có thể khôi phục nhiều aggregate độc lập đồng thời, nhưng mỗi aggregate vẫn phải áp dụng sự kiện theo thứ tự của nó. Concurrency cần được giới hạn theo năng lực event store, CPU, bộ nhớ và các dịch vụ downstream.

## 15. Checklist thiết kế snapshot và replay

- Reducer xác định, không thực hiện I/O hoặc tạo dữ liệu ngẫu nhiên trong lúc replay.
- Event có định danh, aggregate ID và sequence/version rõ ràng.
- Snapshot lưu trạng thái cùng version/checkpoint tương ứng.
- Event store đọc sự kiện sau snapshot theo thứ tự và có cursor/high-water mark xác định.
- Replay dùng `reduce` khi chỉ cần trạng thái cuối; dùng `scan` khi cần trạng thái trung gian.
- Không nạp toàn bộ lịch sử vào collection nếu có thể xử lý theo luồng.
- Phát hiện duplicate, sequence gap và event sai thứ tự.
- Chỉ lưu snapshot sau khi replay đến checkpoint đã chọn hoàn tất thành công.
- Ghi snapshot có điều kiện để tránh version bị lùi khi nhiều consumer hoạt động.
- Có giao thức chuyển từ replay sang live stream để không bỏ lỡ sự kiện mới.
- Phân biệt replay bền vững từ event store với replay ngắn hạn trong `Sinks.replay` hoặc `cache`.
- Có chiến lược schema migration hoặc event upcasting.
- Kiểm thử complete, error, duplicate, gap, crash boundary và cancel.
- Giới hạn page, prefetch, concurrency và dung lượng snapshot theo tài nguyên thực tế.

Snapshot rút ngắn thời gian khôi phục bằng cách lưu trạng thái tại một version đã biết; replay áp dụng phần lịch sử còn lại để tái tạo trạng thái hiện tại. Khi reducer xác định, checkpoint nhất quán và luồng sự kiện được đọc theo thứ tự, hệ thống có thể khởi động lại hoặc dựng lại projection mà vẫn giữ được tính đúng đắn của dữ liệu. Reactor cung cấp `Flux`, `reduce`, `scan`, `concatMap` và backpressure để tổ chức quá trình này thành một pipeline có thể kiểm soát và kiểm thử.
