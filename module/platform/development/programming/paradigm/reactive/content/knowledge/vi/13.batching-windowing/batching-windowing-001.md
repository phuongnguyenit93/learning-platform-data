# `reduce`: tổng hợp kết quả sau khi nguồn hoàn thành

Trong **REACTIVE_PROGRAMMING**, `Flux` biểu diễn một luồng có thể phát nhiều phần tử theo thời gian, còn `Mono` biểu diễn một kết quả có tối đa một phần tử. Khi cần tính tổng, đếm số bản ghi, tìm giá trị lớn nhất hoặc tạo một bản tóm tắt từ toàn bộ luồng, ta có thể dùng toán tử `reduce` của Reactor.

`reduce` nhận từng phần tử từ upstream, cập nhật một giá trị tích lũy và chỉ phát kết quả cuối cùng khi nguồn hoàn tất bình thường. Vì vậy, kết quả của `Flux.reduce(...)` là một `Mono`: nó chứa một giá trị tổng hợp sau khi đã xử lý hết nguồn, hoặc có thể rỗng tùy overload và trạng thái nguồn.

## 1. Cách reduce tích lũy dữ liệu

Có thể hình dung `reduce` như một phép gấp (fold) trên các phần tử của luồng. Ở mỗi bước, toán tử nhận giá trị tích lũy hiện tại và phần tử tiếp theo, rồi tạo ra giá trị tích lũy mới.

```text
Nguồn:       2 ---- 4 ---- 6 ---- onComplete
              \      \      \
Giá trị:       0 ->  2 ->  6 -> 12
                              |
                              v
                         Mono(12)
```

Với seed bằng `0`, phép cộng được thực hiện lần lượt:

1. Bắt đầu với accumulator là `0`.
2. Nhận `2`: tính `0 + 2`, accumulator mới là `2`.
3. Nhận `4`: tính `2 + 4`, accumulator mới là `6`.
4. Nhận `6`: tính `6 + 6`, accumulator mới là `12`.
5. Khi nguồn phát `onComplete`, `reduce` phát `12` rồi hoàn tất `Mono` kết quả.

Trong Reactor:

```java
Mono<Integer> total = Flux.just(2, 4, 6)
    .reduce(0, Integer::sum);
```

`Integer::sum` là hàm tích lũy: nhận accumulator hiện tại và phần tử mới, trả về accumulator tiếp theo. `reduce` không phát `2`, `6`, `12` thành các phần tử trung gian cho downstream; downstream chỉ nhận kết quả cuối cùng `12`.

## 2. Hai cách dùng reduce: có seed và không có seed

Reactor cung cấp hai dạng phổ biến:

```java
// Có giá trị khởi tạo (seed).
Mono<Integer> withSeed = Flux.just(2, 4, 6)
    .reduce(0, Integer::sum);

// Không có seed; phần tử đầu tiên trở thành accumulator ban đầu.
Mono<Integer> withoutSeed = Flux.just(2, 4, 6)
    .reduce(Integer::sum);
```

Khác biệt quan trọng xuất hiện khi nguồn rỗng:

| Nguồn | `reduce(seed, accumulator)` | `reduce(accumulator)` |
|---|---|---|
| Có phần tử | Tích lũy từ seed rồi phát kết quả | Dùng phần tử đầu làm accumulator rồi tích lũy |
| Rỗng và hoàn tất | Phát seed rồi hoàn tất | Hoàn tất rỗng (`Mono.empty()`) |
| Phát lỗi | Kết thúc bằng lỗi | Kết thúc bằng lỗi |

Ví dụ:

```java
Mono<Integer> emptyWithSeed = Flux.<Integer>empty()
    .reduce(0, Integer::sum);       // phát 0

Mono<Integer> emptyWithoutSeed = Flux.<Integer>empty()
    .reduce(Integer::sum);          // Mono.empty()
```

Hãy chọn overload theo ý nghĩa nghiệp vụ. Nếu tổng của tập rỗng được định nghĩa là `0`, dùng seed `0`. Nếu không có phần tử đồng nghĩa với “không có kết quả”, overload không seed cho phép biểu diễn điều đó bằng `Mono.empty()`.

## 3. Tổng hợp một giá trị nghiệp vụ

Accumulator không nhất thiết là kiểu dữ liệu giống phần tử nguồn. Ví dụ, luồng đơn hàng có thể được rút gọn thành tổng tiền và số lượng đơn:

```java
record OrderSummary(BigDecimal total, long count) {}

Mono<OrderSummary> summary = orders.reduce(
    new OrderSummary(BigDecimal.ZERO, 0),
    (current, order) -> new OrderSummary(
        current.total().add(order.total()),
        current.count() + 1
    )
);
```

Mỗi phần tử `Order` cập nhật một `OrderSummary` mới. Sau khi nguồn hoàn tất, downstream nhận một bản tóm tắt duy nhất. Có thể tiếp tục biến đổi kết quả bằng các toán tử thông thường:

```java
Mono<BigDecimal> averageOrderValue = summary
    .filter(result -> result.count() > 0)
    .map(result -> result.total()
        .divide(BigDecimal.valueOf(result.count()), 2, RoundingMode.HALF_UP));
```

Ở đây, `filter` loại bỏ trường hợp không có đơn hàng trước khi tính trung bình. Vì `summary` dùng seed, nguồn rỗng sẽ tạo `OrderSummary(BigDecimal.ZERO, 0)`; điều kiện `filter` chuyển trường hợp đó thành `Mono.empty()`.

Nên ưu tiên accumulator bất biến như ví dụ trên: mỗi bước trả về một giá trị mới. Cách này giúp tránh việc nhiều subscription hoặc nhiều phần khác của ứng dụng vô tình chia sẻ và sửa cùng một object tích lũy.

## 4. Dùng reduceWith khi accumulator cần được tạo theo từng subscription

Nếu accumulator là object mutable, chẳng hạn một `ArrayList`, cần tạo một instance mới cho mỗi subscription. Reactor có `reduceWith` nhận một `Supplier` để tạo seed khi subscription bắt đầu:

```java
Mono<List<String>> collected = names.reduceWith(
    ArrayList::new,
    (items, name) -> {
        items.add(name);
        return items;
    }
);
```

Supplier `ArrayList::new` tạo accumulator riêng cho mỗi subscription. Điều này tránh dùng chung một seed mutable giữa nhiều lần subscribe. Tuy nhiên, nếu mục tiêu đơn giản chỉ là gom tất cả phần tử thành một danh sách, `collectList()` diễn đạt ý định rõ ràng hơn:

```java
Mono<List<String>> allNames = names.collectList();
```

`reduceWith` phù hợp khi bạn cần tự định nghĩa kiểu accumulator và quy tắc cập nhật. `collectList`, `collectMap` hoặc các toán tử collect chuyên biệt thường dễ đọc hơn khi cấu trúc kết quả đã có sẵn.

## 5. Reduce chỉ phát kết quả khi nguồn hoàn tất

Điểm quan trọng nhất của `reduce` là thời điểm phát kết quả. Nó phải biết không còn phần tử nào nữa trước khi phát giá trị cuối cùng. Vì vậy, `reduce` phù hợp với nguồn hữu hạn hoặc nguồn có điều kiện hoàn tất xác định.

```java
Flux<Integer> finite = Flux.range(1, 5);

Mono<Integer> sum = finite.reduce(0, Integer::sum);
```

Nguồn `Flux.range` phát năm phần tử rồi hoàn tất, do đó `sum` có thể phát `15`.

Với nguồn vô hạn như `Flux.interval`, nếu không có điều kiện dừng, `reduce` không thể phát kết quả cuối cùng:

```java
Mono<Long> neverFinalized = Flux.interval(Duration.ofSeconds(1))
    .reduce(0L, Long::sum);
```

Nguồn tiếp tục phát nên accumulator tiếp tục thay đổi, nhưng `Mono` kết quả vẫn chờ `onComplete`. Nếu muốn tổng hợp một đoạn hữu hạn của nguồn, hãy giới hạn trước khi reduce:

```java
Mono<Long> firstTenTicks = Flux.interval(Duration.ofSeconds(1))
    .take(10)
    .reduce(0L, Long::sum);
```

`take(10)` làm upstream kết thúc sau mười phần tử; sau đó `reduce` phát tổng. Nếu Subscriber hủy trước khi nguồn hoàn tất, phép tổng hợp không phát giá trị cuối cùng. Hủy đăng ký cũng truyền yêu cầu dừng về upstream theo khả năng của nguồn.

## 6. Phân biệt reduce với scan và collect

Các toán tử này đều có thể tích lũy dữ liệu, nhưng mục đích và đầu ra khác nhau:

| Toán tử | Đầu ra | Khi nào phát? | Trường hợp sử dụng |
|---|---|---|---|
| `reduce` | `Mono<A>` | Một kết quả sau khi nguồn hoàn tất | Tổng, min/max, thống kê cuối cùng |
| `scan` | `Flux<A>` | Phát accumulator sau mỗi phần tử | Theo dõi tổng lũy kế hoặc trạng thái tiến triển |
| `collectList` | `Mono<List<T>>` | Một danh sách sau khi nguồn hoàn tất | Cần giữ tất cả phần tử để xử lý cùng lúc |
| `collectMap` | `Mono<Map<K,V>>` | Một map sau khi nguồn hoàn tất | Gom phần tử theo khóa |

Ví dụ so sánh `reduce` và `scan`:

```java
Flux<Integer> source = Flux.just(1, 2, 3);

Mono<Integer> finalTotal = source.reduce(0, Integer::sum);
// Kết quả: 6

Flux<Integer> runningTotals = source.scan(0, Integer::sum);
// Kết quả: 0, 1, 3, 6
```

`scan` phát trạng thái tích lũy qua từng bước, còn `reduce` chỉ phát tổng cuối. Nếu cần cập nhật giao diện hoặc metrics theo tiến độ, `scan` có thể phù hợp hơn. Nếu chỉ cần kết quả cuối cùng, `reduce` tránh phát các giá trị trung gian.

`collectList` giữ mọi phần tử trong bộ nhớ cho đến khi nguồn hoàn tất. `reduce` có thể dùng bộ nhớ gần như hằng số nếu accumulator chỉ giữ một số liệu tổng hợp cố định, ví dụ một số đếm hoặc tổng. Mức dùng bộ nhớ thực tế phụ thuộc vào kiểu accumulator: nếu accumulator tự giữ toàn bộ phần tử, `reduce` cũng có thể tiêu thụ bộ nhớ tăng theo kích thước nguồn.

## 7. Hành vi khi nguồn phát lỗi hoặc không hoàn tất

`reduce` chỉ tạo kết quả cuối khi nhận `onComplete`. Các trường hợp khác có hành vi riêng:

- **Nguồn rỗng:** overload có seed phát seed; overload không seed hoàn tất rỗng.
- **Nguồn phát lỗi:** `Mono` kết quả kết thúc bằng `onError`; accumulator một phần không được phát như kết quả thành công.
- **Nguồn không hoàn tất:** accumulator tiếp tục được cập nhật nhưng không có giá trị cuối được phát.
- **Subscriber hủy:** pipeline dừng theo cơ chế cancellation; không có kết quả tổng hợp cuối cùng.

Nếu muốn phục hồi lỗi, cần quyết định rõ dữ liệu một phần có được chấp nhận hay không. Ví dụ, đặt `onErrorResume` trước `reduce` có thể thay lỗi nguồn bằng một Publisher dự phòng rồi tổng hợp Publisher đó. Đặt `onErrorResume` sau `reduce` sẽ xử lý lỗi của toàn phép tổng hợp. Hai vị trí thể hiện hai chính sách khác nhau.

Không nên mặc định xem accumulator hiện tại là kết quả hợp lệ khi nguồn lỗi. Nếu nghiệp vụ cần tổng hợp một phần, hãy biểu diễn điều đó tường minh bằng một cấu trúc dữ liệu có trạng thái hoàn tất/lỗi hoặc một chính sách phục hồi được kiểm thử.

## 8. Lưu ý về thứ tự, tính toán số và tác dụng phụ

`reduce` xử lý các phần tử theo thứ tự tín hiệu mà upstream phát. Với phép cộng số nguyên, thứ tự không làm thay đổi kết quả toán học nếu không xảy ra tràn số. Với phép toán không giao hoán hoặc không kết hợp như phép trừ, thứ tự ảnh hưởng trực tiếp đến kết quả.

```java
Mono<Integer> subtraction = Flux.just(10, 3, 2)
    .reduce((left, right) -> left - right);
// Tính theo thứ tự: (10 - 3) - 2 = 5
```

Với kiểu số nguyên có giới hạn, tổng có thể tràn. Hãy chọn kiểu dữ liệu đủ miền giá trị, kiểm tra overflow hoặc dùng `BigInteger`/`BigDecimal` khi nghiệp vụ yêu cầu. Với số thực dấu phẩy động, sai số làm tròn có thể xuất hiện khi cộng nhiều giá trị.

Accumulator nên tập trung vào việc tính giá trị mới. Tránh gửi email, ghi cơ sở dữ liệu hoặc thay đổi trạng thái bên ngoài trong hàm tích lũy. Tác dụng phụ có thể bị thực hiện lại khi Publisher được subscribe nhiều lần hoặc khi pipeline được retry. Nếu thao tác bất đồng bộ là một phần của nghiệp vụ, hãy đưa Publisher đó vào pipeline bằng toán tử ghép phù hợp trước hoặc sau bước tổng hợp theo yêu cầu.

## 9. Kiểm thử reduce bằng StepVerifier

`StepVerifier` giúp xác minh giá trị cuối cùng và tín hiệu kết thúc:

```java
StepVerifier.create(Flux.range(1, 5).reduce(0, Integer::sum))
    .expectNext(15)
    .verifyComplete();
```

Kiểm thử nguồn rỗng cho cả hai overload:

```java
StepVerifier.create(Flux.<Integer>empty().reduce(0, Integer::sum))
    .expectNext(0)
    .verifyComplete();

StepVerifier.create(Flux.<Integer>empty().reduce(Integer::sum))
    .verifyComplete();
```

Kiểm thử lỗi xác nhận accumulator một phần không được phát như kết quả thành công:

```java
StepVerifier.create(
        Flux.concat(
            Flux.just(1, 2),
            Flux.<Integer>error(new IllegalStateException("source failed"))
        )
            .reduce(0, Integer::sum)
    )
    .expectErrorMessage("source failed")
    .verify();
```

Với nguồn không kết thúc, cần giới hạn thời gian quan sát và hủy subscription để test tự kết thúc:

```java
StepVerifier.create(Flux.<Integer>never().reduce(0, Integer::sum))
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(100))
    .thenCancel()
    .verify();
```

Trong dự án, hãy kiểm thử thêm trường hợp nhiều subscription nếu accumulator mutable, overflow nếu miền giá trị có giới hạn và chính sách phục hồi nếu nguồn có thể phát lỗi.

## 10. Chọn reduce khi nào?

- Dùng `reduce(seed, accumulator)` khi cần một kết quả duy nhất và có giá trị mặc định rõ ràng cho nguồn rỗng.
- Dùng `reduce(accumulator)` khi cần kết quả từ phần tử đầu tiên và muốn biểu diễn nguồn rỗng bằng `Mono.empty()`.
- Dùng `reduceWith` khi cần tạo accumulator riêng theo từng subscription, đặc biệt với accumulator mutable.
- Dùng `scan` khi cần phát các trạng thái tích lũy trung gian.
- Dùng `collectList` hoặc toán tử collect khác khi cần giữ toàn bộ phần tử hay gom theo cấu trúc có sẵn.
- Giới hạn nguồn vô hạn bằng `take`, điều kiện dừng hoặc window trước khi dùng `reduce` nếu cần kết quả cuối.
- Giữ accumulator thuần, kiểm soát overflow và kiểm thử riêng hành vi nguồn rỗng, lỗi, cancellation.

`reduce` là phép tổng hợp cuối luồng: nó tiêu thụ các phần tử, cập nhật accumulator và chỉ phát một kết quả khi Publisher nguồn hoàn tất bình thường. Hiểu rõ seed, trạng thái rỗng, lỗi và sự khác biệt với `scan` giúp chọn đúng toán tử, kiểm soát bộ nhớ và tạo ra kết quả có ý nghĩa rõ ràng trong pipeline Reactor.
