# `scan`: phát trạng thái tích lũy sau từng phần tử

Trong nhiều luồng dữ liệu, mỗi phần tử mới cần được kết hợp với trạng thái đã tính từ các phần tử trước đó. Ví dụ, một dashboard muốn hiển thị tổng doanh thu tăng dần, một bộ theo dõi tồn kho cần biết số lượng còn lại sau mỗi giao dịch, hoặc một bộ xử lý log muốn phát số sự kiện đã đọc đến thời điểm hiện tại. Reactor có toán tử `scan` để tạo và phát trạng thái tích lũy sau từng phần tử, thay vì chỉ trả về kết quả cuối cùng.

Bài học thuộc chương **Gom và chia luồng** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là cách `scan` duy trì trạng thái qua từng tín hiệu, lựa chọn giá trị khởi tạo và phối hợp với batching/windowing.

Sau bài học, bạn có thể:

- Dùng `scan` để phát kết quả tích lũy sau từng phần tử của `Flux`.
- Phân biệt `scan` có seed, `scan` không seed và `scanWith`.
- Giải thích vì sao `scan` khác `reduce` và `collect`.
- Đặt `scan` trước hoặc sau các toán tử lọc để kiểm soát ý nghĩa trạng thái.
- Tạo lại trạng thái cho từng batch hoặc window.
- Kiểm thử giá trị seed, thứ tự tích lũy, lỗi và cancellation bằng `StepVerifier`.

## 1. Từ từng sự kiện đến trạng thái đang chạy

Giả sử một luồng ghi nhận số tiền của các giao dịch:

```java
Flux<Long> amounts = Flux.just(120_000L, 80_000L, 50_000L);
```

Nếu muốn biết tổng tiền sau mỗi giao dịch, ta cần cộng giá trị mới vào tổng đã có. Với `scan`, có thể viết:

```java
Flux<Long> runningTotals = amounts
    .scan(0L, Long::sum);
```

Kết quả phát ra là:

```text
0
120000
200000
250000
```

Giá trị `0` là seed, tức trạng thái ban đầu. Sau đó, mỗi phần tử upstream tạo ra một trạng thái mới bằng cách áp dụng accumulator với trạng thái hiện tại và phần tử vừa nhận.

Với `scan(seed, accumulator)`, có thể hình dung quá trình như sau:

```text
Seed = 0
       |
       v
  + 120000  ---> 120000
       |
       v
  +  80000  ---> 200000
       |
       v
  +  50000  ---> 250000
```

`scan` phát trạng thái seed trước, sau đó phát từng trạng thái được cập nhật. Vì vậy, nếu nghiệp vụ chỉ cần trạng thái sau mỗi phần tử đầu vào, có thể bỏ seed bằng `skip(1)`:

```java
Flux<Long> totalsAfterEachTransaction = amounts
    .scan(0L, Long::sum)
    .skip(1);
```

Khi đó kết quả là `120000`, `200000`, `250000`.

## 2. `scan` có seed

Seed là trạng thái ban đầu mà accumulator sử dụng trước khi nhận phần tử đầu tiên. Chọn seed theo ý nghĩa nghiệp vụ, không chỉ theo kiểu dữ liệu.

```java
Flux<Integer> inventoryChanges = Flux.just(5, -2, 4, -1);

Flux<Integer> stockLevels = inventoryChanges
    .scan(10, (currentStock, change) -> currentStock + change);
```

Kết quả:

| Thứ tự phát | Trạng thái | Ý nghĩa |
|---:|---:|---|
| 0 | 10 | Tồn kho ban đầu (seed). |
| 1 | 15 | Nhập thêm 5. |
| 2 | 13 | Xuất 2. |
| 3 | 17 | Nhập thêm 4. |
| 4 | 16 | Xuất 1. |

Accumulator có dạng `(state, element) -> newState`. Với ví dụ tồn kho, `currentStock` là trạng thái trước đó, còn `change` là sự kiện mới. Giá trị trả về trở thành trạng thái cho lần tính kế tiếp và cũng được phát xuống downstream.

### Dùng kiểu trạng thái có cấu trúc

Khi trạng thái gồm nhiều trường, hãy mô hình hóa bằng record hoặc class thay vì ghép nhiều giá trị rời rạc.

```java
record SalesState(long transactionCount, long totalAmount) {
    static SalesState initial() {
        return new SalesState(0, 0);
    }

    SalesState add(long amount) {
        return new SalesState(
            transactionCount + 1,
            totalAmount + amount
        );
    }
}

Flux<SalesState> states = amounts
    .scan(SalesState.initial(),
        (state, amount) -> state.add(amount));
```

Record bất biến giúp mỗi bước tạo ra một trạng thái mới. Các subscriber có thể quan sát trạng thái đã phát mà không lo accumulator tiếp tục sửa chính object đó sau khi phát.

Nếu muốn chỉ phát trạng thái sau giao dịch, bỏ seed:

```java
Flux<SalesState> statesAfterTransactions = amounts
    .scan(SalesState.initial(), SalesState::add)
    .skip(1);
```

Lưu ý: `skip(1)` loại bỏ phần tử đầu tiên mà `scan` phát ra, tức seed. Nếu upstream empty, scan có seed vẫn phát seed rồi hoàn tất; sau `skip(1)`, kết quả sẽ empty.

## 3. `scan` không seed

Overload `scan(BiFunction)` không nhận trạng thái khởi tạo riêng. Phần tử đầu tiên của nguồn trở thành trạng thái ban đầu và được phát ra nguyên trạng. Các phần tử tiếp theo được kết hợp với trạng thái hiện tại.

```java
Flux<Integer> values = Flux.just(3, 5, 2);

Flux<Integer> cumulative = values
    .scan(Integer::sum);
```

Kết quả:

```text
3
8
10
```

Ở đây không có `0` ở đầu. `3` vừa là phần tử đầu tiên của nguồn, vừa là trạng thái tích lũy đầu tiên. Overload không seed phù hợp khi giá trị đầu vào đầu tiên đã là trạng thái hợp lệ để bắt đầu tính toán.

So sánh hai cách:

| Nguồn | Cách dùng | Kết quả |
|---|---|---|
| `Flux.just(3, 5, 2)` | `scan(Integer::sum)` | `3, 8, 10` |
| `Flux.just(3, 5, 2)` | `scan(0, Integer::sum)` | `0, 3, 8, 10` |
| `Flux.empty()` | `scan(Integer::sum)` | Empty, không có seed để phát. |
| `Flux.empty()` | `scan(0, Integer::sum)` | `0`, sau đó hoàn tất. |

Khi dùng overload có seed, hãy nhớ seed cũng là một phần tử đầu ra. Điều này ảnh hưởng đến số lượng phần tử downstream nhận được và cần được tính đến trong `StepVerifier`, `skip`, `take` hoặc các toán tử ghép luồng khác.

## 4. `scanWith`: tạo seed mới cho mỗi subscription

`scan(seed, accumulator)` nhận một object seed cụ thể khi lắp ráp pipeline. Nếu seed là mutable và được tái sử dụng giữa nhiều subscription, các lần subscribe có nguy cơ chia sẻ cùng một object trạng thái ban đầu.

`scanWith` nhận một supplier để tạo seed khi subscription bắt đầu:

```java
Flux<SalesState> states = amounts
    .scanWith(SalesState::initial, SalesState::add);
```

Supplier được gọi cho mỗi subscription, nhờ đó mỗi subscriber có trạng thái khởi tạo riêng. Đây là lựa chọn phù hợp khi seed cần được tạo động hoặc là một object mutable có vòng đời riêng cho từng subscription.

Ví dụ với một accumulator mutable để minh họa vòng đời seed:

```java
final class MutableCounter {
    private long count;

    void increment() {
        count++;
    }

    long value() {
        return count;
    }
}

Flux<Long> counts = Flux.just("A", "B", "C")
    .scanWith(MutableCounter::new, (state, ignored) -> {
        state.increment();
        return state;
    })
    .map(MutableCounter::value);
```

Trong thực tế, nên ưu tiên trạng thái bất biến như record ở phần trước. Ví dụ mutable chỉ để cho thấy vì sao cần supplier tạo seed riêng; không nên phát cùng một object mutable rồi tiếp tục thay đổi nó, vì subscriber có thể giữ tham chiếu đến object và nhìn thấy giá trị đã bị sửa sau đó.

## 5. `scan` khác `reduce` và `collect` thế nào?

Ba toán tử đều có thể duy trì trạng thái trong quá trình tiêu thụ nguồn, nhưng chúng phát ra kết quả khác nhau.

```java
Flux<Integer> source = Flux.just(1, 2, 3, 4);

Flux<Integer> eachState = source.scan(0, Integer::sum);
Mono<Integer> finalState = source.reduce(0, Integer::sum);
Mono<List<Integer>> allValues = source.collectList();
```

| Toán tử | Đầu ra | Thời điểm phát |
|---|---|---|
| `scan` | `Flux` các trạng thái trung gian | Sau seed và sau từng phần tử. |
| `reduce` | `Mono` một kết quả cuối | Khi nguồn hoàn tất bình thường. |
| `collectList` | `Mono<List<T>>` chứa các phần tử | Khi nguồn hoàn tất bình thường. |

Với `source` ở trên:

- `eachState`: `0, 1, 3, 6, 10`.
- `finalState`: `10`.
- `allValues`: `[1, 2, 3, 4]`.

Nếu cần cập nhật dashboard sau mỗi giao dịch, `scan` phù hợp vì downstream nhận được trạng thái tiến triển. Nếu chỉ cần tổng cuối cùng để lưu báo cáo, `reduce` thường gọn hơn. Nếu cần gom toàn bộ phần tử thành danh sách, dùng `collectList`; lưu ý nó giữ toàn bộ phần tử trong bộ nhớ cho đến khi nguồn hoàn tất.

## 6. Đặt `scan` trước hay sau `filter`?

Giống các phép biến đổi khác, vị trí của `scan` trong pipeline thay đổi ý nghĩa trạng thái.

```java
Flux<Integer> changes = Flux.just(10, -3, 7, -2);

// Tính trạng thái từ mọi sự kiện, rồi chỉ phát các trạng thái dương.
Flux<Integer> positiveStates = changes
    .scan(0, Integer::sum)
    .filter(state -> state > 0);

// Loại sự kiện âm trước, sau đó mới tích lũy.
Flux<Integer> positiveChangesOnly = changes
    .filter(change -> change > 0)
    .scan(0, Integer::sum);
```

Kết quả khác nhau:

| Cách đặt toán tử | Kết quả | Ý nghĩa |
|---|---|---|
| `scan` rồi `filter` | `10, 14, 12` | Trạng thái vẫn tính cả thay đổi âm; chỉ ẩn trạng thái không dương khỏi đầu ra. |
| `filter` rồi `scan` | `0, 10, 17` | Sự kiện âm bị loại khỏi phép tính, nên trạng thái không phản ánh đầy đủ giao dịch. |

Trong ví dụ thứ hai, seed `0` vẫn được phát bởi `scan` trước khi nhận phần tử dương. Nếu muốn chỉ phát trạng thái sau mỗi thay đổi được giữ lại, có thể thêm `skip(1)`.

Hãy xác định bạn muốn loại sự kiện khỏi phép tính hay chỉ muốn ẩn một số trạng thái khỏi downstream. Đây là hai yêu cầu khác nhau.

## 7. Dùng `scan` trong batching và windowing

`scan` duy trì trạng thái xuyên suốt subscription. Nếu cần trạng thái được reset cho từng batch hoặc từng time window, hãy đặt một `scan` bên trong từng Publisher con do `window` tạo ra.

Ví dụ, chia các sự kiện thành batch 3 phần tử và tính tổng riêng cho từng batch:

```java
Flux<Integer> values = Flux.just(2, 4, 1, 5, 3, 2, 7);

Flux<Integer> batchTotalsProgress = values
    .window(3)
    .concatMap(batch -> batch
        .scan(0, Integer::sum)
        .skip(1));
```

Kết quả:

```text
2
6
7
5
8
10
7
```

Trạng thái bắt đầu lại từ `0` ở mỗi window. Với batch đầu `[2, 4, 1]`, trạng thái lần lượt là `2, 6, 7`; batch tiếp theo `[5, 3, 2]` tạo `5, 8, 10`; phần tử cuối `7` tạo trạng thái `7` trong window cuối.

Nếu muốn chỉ phát tổng cuối của từng batch, có thể dùng `reduce` bên trong từng window:

```java
Flux<Integer> batchTotals = values
    .window(3)
    .concatMap(batch -> batch.reduce(0, Integer::sum));
```

Khác biệt là `scan` phát tiến trình trong từng batch, còn `reduce` chỉ phát kết quả cuối sau khi batch hoàn tất. `concatMap` xử lý các window theo thứ tự; nếu dùng cách kết hợp khác, hãy xác định rõ có cho phép các window được xử lý đồng thời hay không.

## 8. Thứ tự, concurrency và backpressure

Accumulator của `scan` phụ thuộc vào thứ tự phần tử mà toán tử nhận được. Nếu upstream là một nguồn có thứ tự xác định, trạng thái được tính theo thứ tự đó. Nếu upstream kết hợp nhiều nguồn bằng `merge`, các phần tử có thể xen kẽ theo thời điểm đến; kết quả tích lũy phản ánh thứ tự quan sát thực tế.

Ví dụ:

```java
Flux<Event> merged = Flux.merge(sourceA, sourceB);

Flux<State> states = merged
    .scan(State.empty(), State::apply);
```

Nếu thứ tự nghiệp vụ quan trọng, hãy đưa sequence number hoặc khóa sắp xếp vào sự kiện và tổ chức lại thứ tự ở ranh giới phù hợp trước khi tính trạng thái. Không nên giả định `scan` tự tạo ra thứ tự toàn cục cho các nguồn đồng thời.

`scan` là phép biến đổi trạng thái theo từng phần tử và phát các kết quả tiến triển; nó không phải bộ đệm toàn bộ luồng. Demand downstream vẫn tham gia điều tiết subscription theo hợp đồng Reactive Streams. Tuy nhiên, accumulator được gọi cho mỗi phần tử upstream được xử lý, nên cần giữ phép tính ngắn gọn và tránh I/O blocking bên trong accumulator.

Không dùng accumulator để thực hiện side effect không thể lặp lại hoặc không thể kiểm soát. Retry hoặc nhiều subscription có thể chạy lại phép tính. Hãy giữ accumulator thuần khiết khi có thể, còn side effect nên được đặt ở vị trí rõ ràng như `doOnNext` hoặc trong một bước xử lý riêng có chính sách retry/idempotency.

### Lỗi trong accumulator

Nếu accumulator ném exception, pipeline kết thúc bằng `onError`. Các trạng thái đã được phát trước thời điểm lỗi vẫn đã được downstream quan sát; không có trạng thái tiếp theo sau lỗi.

```java
Flux<Integer> safeDivision = Flux.just(100, 2, 0, 5)
    .scan(1, (state, divisor) -> state / divisor);
```

Ví dụ trên có thể lỗi khi gặp phép chia cho `0`. Nếu đây là tình huống nghiệp vụ có thể phục hồi, hãy kiểm tra dữ liệu trong accumulator hoặc chuyển việc xác thực thành một bước rõ ràng trước khi cập nhật trạng thái. Không nên nuốt exception tổng quát vì có thể làm trạng thái tích lũy trở nên sai lệch.

## 9. Kiểm thử `scan` bằng StepVerifier

`StepVerifier` xác nhận cả seed lẫn từng trạng thái trung gian.

### Kiểm thử scan có seed

```java
StepVerifier.create(
        Flux.just(1, 2, 3).scan(0, Integer::sum)
    )
    .expectNext(0, 1, 3, 6)
    .verifyComplete();
```

### Kiểm thử scan không seed

```java
StepVerifier.create(
        Flux.just(1, 2, 3).scan(Integer::sum)
    )
    .expectNext(1, 3, 6)
    .verifyComplete();
```

### Kiểm thử nguồn empty

```java
StepVerifier.create(
        Flux.<Integer>empty().scan(10, Integer::sum)
    )
    .expectNext(10)
    .verifyComplete();

StepVerifier.create(
        Flux.<Integer>empty().scan(Integer::sum)
    )
    .verifyComplete();
```

Kiểm thử này làm rõ khác biệt giữa overload có seed và không seed. Với overload có seed, trạng thái ban đầu được phát ngay cả khi upstream empty; overload không seed không có phần tử để khởi tạo trạng thái.

### Kiểm thử reset theo từng window

```java
StepVerifier.create(
        Flux.just(1, 2, 3, 4)
            .window(2)
            .concatMap(window -> window.scan(0, Integer::sum).skip(1))
    )
    .expectNext(1, 3, 3, 7)
    .verifyComplete();
```

Hai window lần lượt tạo tổng tiến triển `1, 3` và `3, 7`. Kiểm thử xác nhận seed được reset khi chuyển sang window mới.

### Kiểm thử lỗi và cancellation

```java
StepVerifier.create(
        Flux.just(1, 2, 0, 4)
            .scan(100, (state, value) -> state / value)
    )
    .expectNext(100, 100, 50)
    .expectError(ArithmeticException.class)
    .verify();
```

Khi cần xác minh cancellation dừng nguồn, có thể gắn `doOnCancel` vào upstream hoặc dùng `TestPublisher` để điều khiển việc phát dữ liệu trong kiểm thử.

## 10. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Quên rằng seed được phát ra | Downstream nhận thêm một phần tử trạng thái ban đầu. | Dùng `skip(1)` nếu chỉ cần trạng thái sau phần tử đầu vào. |
| Dùng `scan` khi chỉ cần tổng cuối | Phát nhiều trạng thái trung gian không cần thiết. | Dùng `reduce` cho một kết quả cuối. |
| Dùng `scan` không seed khi cần trạng thái ban đầu độc lập | Không có trạng thái để phát khi nguồn empty. | Dùng overload có seed. |
| Dùng chung seed mutable cho nhiều subscriber | Trạng thái có thể bị chia sẻ ngoài ý muốn. | Ưu tiên immutable state hoặc dùng `scanWith` tạo seed riêng. |
| Đặt `filter` sai phía của `scan` | Loại sự kiện khỏi phép tính hoặc chỉ ẩn trạng thái ngoài ý muốn. | Quyết định rõ filter tác động lên đầu vào hay trạng thái đầu ra. |
| Giả định `scan` sắp xếp các nguồn đã merge | Trạng thái phụ thuộc thứ tự đến thực tế, có thể khác lần chạy. | Dùng sequence number và quy tắc sắp xếp rõ ràng nếu cần. |
| Thực hiện I/O blocking trong accumulator | Chặn thread xử lý tín hiệu và làm chậm pipeline. | Chỉ tính trạng thái trong accumulator; tách I/O sang bước có scheduler phù hợp. |

## 11. Checklist trước khi dùng `scan`

- Trạng thái ban đầu là gì và có cần phát seed xuống downstream không?
- Có nên dùng `scanWith` để tạo seed riêng cho mỗi subscription không?
- Accumulator có tạo trạng thái mới hay sửa object đã phát?
- Cần phát mọi trạng thái trung gian hay chỉ cần kết quả cuối cùng?
- `filter`, `flatMap`, `merge` hoặc `window` được đặt ở đâu so với `scan`?
- Thứ tự phần tử upstream có ổn định và phù hợp với ý nghĩa nghiệp vụ không?
- Trạng thái cần reset theo subscription, batch hay window?
- Kiểm thử đã bao gồm seed, empty source, lỗi, cancellation và thứ tự chưa?

`scan` phù hợp khi downstream cần nhìn thấy trạng thái tiến triển sau từng sự kiện. Việc chọn seed, đặt toán tử đúng vị trí và kiểm soát thứ tự đầu vào giúp trạng thái tích lũy có ý nghĩa rõ ràng. Khi chỉ cần kết quả cuối, hãy chọn `reduce`; khi cần reset trạng thái theo từng batch hoặc window, đặt phép `scan` bên trong từng luồng con để mỗi nhóm có vòng đời trạng thái riêng.
