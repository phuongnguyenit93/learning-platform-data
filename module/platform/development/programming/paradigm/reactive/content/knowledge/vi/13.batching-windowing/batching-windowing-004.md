# Đếm, kiểm tra tồn tại và kiểm tra điều kiện toàn luồng

Trong chương **Gom và chia luồng**, bài học này trình bày cách tổng hợp thông tin từ một luồng reactive mà không cần thu thập tất cả phần tử thành một danh sách. Các câu hỏi thường gặp gồm: có bao nhiêu phần tử, luồng có phần tử nào không, có chứa một giá trị cụ thể không, có ít nhất một phần tử thỏa điều kiện không, và tất cả phần tử có thỏa điều kiện không.

Bài học thuộc module **REACTIVE_PROGRAMMING**. Module hướng dẫn: “Học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.” Các phép tổng hợp của Reactor giúp trả lời những câu hỏi trên bằng một publisher kết quả, đồng thời giữ nguyên khả năng truyền lỗi và hủy subscription của pipeline.

## 1. Từ Flux nhiều phần tử đến Mono kết quả

Một `Flux<T>` có thể phát không, một hoặc nhiều phần tử. Khi cần đếm hoặc kiểm tra điều kiện trên toàn luồng, Reactor thường trả về một `Mono` chứa kết quả tổng hợp:

| Câu hỏi | Toán tử | Kiểu kết quả |
|---|---|---|
| Có bao nhiêu phần tử? | `count()` | `Mono<Long>` |
| Luồng có ít nhất một phần tử? | `hasElements()` | `Mono<Boolean>` |
| Luồng có chứa giá trị này? | `hasElement(value)` | `Mono<Boolean>` |
| Có phần tử nào thỏa điều kiện? | `any(predicate)` | `Mono<Boolean>` |
| Tất cả phần tử có thỏa điều kiện? | `all(predicate)` | `Mono<Boolean>` |

Các toán tử này không trả về kết quả ngay tại lúc lắp ráp pipeline. Chúng trả về publisher kết quả; giá trị của `Mono` chỉ được phát khi quá trình xử lý upstream cung cấp đủ thông tin để kết luận.

Ví dụ:

```java
Mono<Long> numberOfOrders =
    orderRepository.findAll()
        .count();

Mono<Boolean> hasOrders =
    orderRepository.findAll()
        .hasElements();
```

Cả hai đều là pipeline reactive. Không cần gọi `block()` để lấy kết quả ở giữa một pipeline khác; hãy nối tiếp bằng `map`, `flatMap`, `filter` hoặc trả về `Mono` cho tầng gọi.

## 2. Đếm phần tử bằng count

`count()` đếm số phần tử mà upstream phát ra và trả về một `Mono<Long>`. Kết quả được phát sau khi nguồn hoàn tất bình thường.

```java
Mono<Long> count =
    Flux.range(1, 5)
        .count();
```

Khi subscribe, `count` phát `5L` rồi hoàn tất. Kiểu kết quả là `Long`, không phải `Integer`.

Có thể đếm sau khi lọc để trả lời một câu hỏi nghiệp vụ cụ thể:

```java
Mono<Long> paidOrderCount =
    orderRepository.findAll()
        .filter(Order::isPaid)
        .count();
```

Pipeline chỉ đếm các đơn hàng đã thanh toán. Mỗi phần tử được kiểm tra bởi `filter`; những phần tử không thỏa điều kiện không được tính.

Một ví dụ khác là đếm các bản ghi trong một khoảng trạng thái:

```java
Mono<Long> activeUserCount =
    userRepository.findAll()
        .filter(User::isActive)
        .count();
```

### count cần nguồn hoàn tất

Để biết tổng số phần tử, `count()` phải đi đến cuối nguồn. Với một luồng hữu hạn, điều đó xảy ra sau phần tử cuối cùng. Với nguồn không bao giờ hoàn tất như `Flux.interval(...)`, `count()` cũng không phát ra tổng số cuối cùng nếu không có toán tử giới hạn hoặc hủy nguồn.

```java
Mono<Long> firstTenTicks =
    Flux.interval(Duration.ofSeconds(1))
        .take(10)
        .count();
```

Ở đây `take(10)` giới hạn nguồn còn mười phần tử, vì vậy `count()` có thể phát kết quả sau khi mười tick được nhận và nguồn kết thúc.

Không dùng `count()` chỉ để kiểm tra xem luồng có phần tử hay không. Nếu chỉ cần biết có ít nhất một phần tử, `hasElements()` có thể kết luận sớm sau phần tử đầu tiên.

### Đếm không đồng nghĩa với thu thập

`count()` chỉ giữ thông tin đếm, còn `collectList()` giữ các phần tử trong một danh sách. Khi dữ liệu lớn, đếm thường tiết kiệm bộ nhớ hơn:

```java
Mono<Long> total = events.count();

// Chỉ dùng khi thực sự cần giữ tất cả phần tử:
Mono<List<Event>> allEvents = events.collectList();
```

Cả hai đều phải chờ nguồn hoàn tất để phát kết quả cuối. Tuy nhiên, `collectList()` lưu toàn bộ phần tử, trong khi `count()` chỉ cần bộ đếm.

## 3. Kiểm tra luồng có phần tử với hasElements

`hasElements()` trả về `Mono<Boolean>` cho biết upstream có phát ít nhất một phần tử hay không.

```java
Mono<Boolean> hasAnyEvent =
    eventRepository.findRecentEvents()
        .hasElements();
```

- Nếu upstream phát ít nhất một `onNext`, kết quả là `true`.
- Nếu upstream hoàn tất mà không phát phần tử nào, kết quả là `false`.
- Nếu upstream phát lỗi trước khi có thể kết luận, lỗi được truyền xuống thay vì biến thành `false`.

Ví dụ với nguồn hữu hạn:

```java
Mono<Boolean> nonEmpty = Flux.just("A", "B").hasElements();
Mono<Boolean> empty = Flux.<String>empty().hasElements();
```

`nonEmpty` phát `true`; `empty` phát `false`.

Toán tử này có thể dừng upstream sớm. Khi nhận phần tử đầu tiên, Reactor đã biết câu trả lời là `true`, nên không cần đọc các phần tử còn lại. Subscription upstream được hủy sau khi đã đủ thông tin để đưa ra kết luận.

Điều đó rất hữu ích với nguồn tốn chi phí hoặc luồng dài. Tuy nhiên, nếu upstream có tác dụng phụ gắn với việc duyệt hết mọi phần tử, `hasElements()` không đảm bảo những tác dụng phụ ở phần còn lại sẽ chạy. Chỉ dùng nó khi câu hỏi thực sự là “có tồn tại phần tử nào không?”.

## 4. Kiểm tra một giá trị cụ thể với hasElement

`hasElement(value)` kiểm tra xem upstream có phát một phần tử bằng giá trị được truyền vào hay không. Việc so sánh sử dụng quy tắc `equals` của kiểu dữ liệu.

```java
Mono<Boolean> containsAdmin =
    Flux.just("USER", "EDITOR", "ADMIN")
        .hasElement("ADMIN");
```

Kết quả là `true`. Nếu không có phần tử bằng `"ADMIN"`, publisher trả về `false` sau khi nguồn hoàn tất.

Có thể kiểm tra một mã sản phẩm:

```java
Mono<Boolean> productExists =
    productRepository.findAll()
        .map(Product::sku)
        .hasElement(requestedSku);
```

Nếu tìm thấy SKU trùng khớp, Reactor có thể kết luận ngay và hủy subscription upstream. Nếu không tìm thấy, nó cần tiếp tục cho đến khi nguồn hoàn tất mới kết luận `false`.

Cần phân biệt:

- `hasElements()` hỏi luồng có bất kỳ phần tử nào không.
- `hasElement(value)` hỏi luồng có phần tử bằng đúng giá trị đó không.

Với đối tượng tùy chỉnh, hãy bảo đảm `equals` được định nghĩa đúng nếu dùng `hasElement` để so sánh theo nội dung. Nếu cần kiểm tra một thuộc tính hoặc quy tắc phức tạp, `any(predicate)` thường phù hợp hơn.

## 5. Kiểm tra có ít nhất một phần tử thỏa điều kiện với any

`any(predicate)` phát `true` nếu tìm thấy ít nhất một phần tử làm predicate trả về `true`. Nếu nguồn hoàn tất mà không có phần tử nào thỏa điều kiện, nó phát `false`.

```java
Mono<Boolean> hasOverdueOrder =
    orderRepository.findAll()
        .any(Order::isOverdue);
```

Nếu tìm thấy một đơn quá hạn, Reactor có thể kết luận ngay. Các phần tử sau đó không cần được đọc để trả lời câu hỏi này.

Ví dụ kiểm tra xem có đơn hàng nào vượt ngưỡng giá trị:

```java
Mono<Boolean> hasLargeOrder =
    orderRepository.findAll()
        .any(order ->
            order.total().compareTo(new BigDecimal("10000000")) > 0
        );
```

Predicate trong `any` là hàm đồng bộ nhận một phần tử và trả về Boolean. Nếu điều kiện cần gọi dịch vụ bất đồng bộ, không gọi `block()` bên trong predicate; hãy chuyển sang một pipeline bất đồng bộ khác và kết hợp kết quả theo yêu cầu.

Với luồng rỗng, `any` trả `false`, vì không tồn tại phần tử nào thỏa điều kiện:

```java
Mono<Boolean> anyOnEmpty =
    Flux.<Integer>empty()
        .any(value -> value > 0);
```

Kết quả là `false`.

## 6. Kiểm tra tất cả phần tử thỏa điều kiện với all

`all(predicate)` kiểm tra mọi phần tử của upstream. Kết quả là `true` nếu tất cả phần tử đều làm predicate trả về `true`; nếu gặp một phần tử không thỏa điều kiện, kết quả là `false`.

```java
Mono<Boolean> allOrdersPaid =
    orderRepository.findAll()
        .all(Order::isPaid);
```

Nếu có một đơn chưa thanh toán, kết quả là `false`. Nếu mọi đơn đều đã thanh toán và nguồn hoàn tất, kết quả là `true`.

Ví dụ kiểm tra mọi điểm số có nằm trong khoảng hợp lệ:

```java
Mono<Boolean> allScoresValid =
    scoreRepository.findAll()
        .all(score -> score >= 0 && score <= 100);
```

### Nguồn rỗng và quy tắc đúng hiển nhiên

Một điểm quan trọng: `all(predicate)` trả về `true` nếu nguồn rỗng. Không có phần tử nào vi phạm điều kiện, vì vậy mệnh đề “tất cả phần tử đều thỏa điều kiện” được xem là đúng.

Trong khi đó, `any(predicate)` trên nguồn rỗng trả về `false`, vì không có phần tử nào thỏa điều kiện.

| Toán tử | Nguồn rỗng | Ý nghĩa |
|---|---:|---|
| `count()` | `0L` | Không có phần tử để đếm |
| `hasElements()` | `false` | Không tồn tại phần tử |
| `hasElement(value)` | `false` | Không tìm thấy giá trị |
| `any(predicate)` | `false` | Không có phần tử thỏa điều kiện |
| `all(predicate)` | `true` | Không có phần tử vi phạm điều kiện |

Nếu nghiệp vụ yêu cầu “phải có ít nhất một bản ghi và tất cả bản ghi đều hợp lệ”, chỉ dùng `all` là chưa đủ. Hãy kết hợp kiểm tra tồn tại:

```java
Mono<Boolean> nonEmptyAndAllValid =
    records.hasElements()
        .flatMap(hasRecords -> {
            if (!hasRecords) {
                return Mono.just(false);
            }

            return records.all(this::isValid);
        });
```

Ví dụ này giả định `records` là publisher lạnh có thể subscribe lại để thực hiện hai lượt. Nếu nguồn chỉ dùng được một lần hoặc việc subscribe lại gây tác dụng phụ, hãy chia sẻ hoặc thiết kế lại nguồn để không vô tình đọc dữ liệu hai lần. Một cách khác là tổng hợp cả hai thông tin trong một lượt duyệt bằng `reduce` hoặc `collect` với trạng thái tích lũy phù hợp.

### all cũng có thể kết luận sớm

Khi gặp phần tử đầu tiên không thỏa predicate, kết quả chắc chắn là `false`; Reactor không cần đọc tiếp để trả lời. Vì vậy `all` có thể hủy upstream sớm giống `any`, nhưng điều kiện dừng ngược lại:

- `any` dừng khi tìm thấy phần tử thỏa điều kiện.
- `all` dừng khi tìm thấy phần tử không thỏa điều kiện.

Nếu không có phần tử quyết định, cả hai phải chờ nguồn hoàn tất.

## 7. So sánh các phép kiểm tra và chọn đúng toán tử

Có thể diễn đạt một số câu hỏi theo nhiều cách, nhưng lựa chọn toán tử ảnh hưởng đến lượng dữ liệu phải duyệt và ý nghĩa của pipeline.

| Mục tiêu | Cách viết phù hợp | Hành vi |
|---|---|---|
| Đếm tất cả phần tử | `flux.count()` | Duyệt đến khi nguồn hoàn tất |
| Chỉ biết có phần tử hay không | `flux.hasElements()` | Có thể dừng ở phần tử đầu tiên |
| Tìm giá trị bằng một đối tượng | `flux.hasElement(value)` | Có thể dừng khi tìm thấy giá trị |
| Kiểm tra có phần tử thỏa predicate | `flux.any(predicate)` | Có thể dừng ở kết quả true đầu tiên |
| Kiểm tra mọi phần tử thỏa predicate | `flux.all(predicate)` | Có thể dừng ở kết quả false đầu tiên |

Tránh viết `count().map(count -> count > 0)` chỉ để kiểm tra nguồn có phần tử hay không. Cách này phải chờ đếm hết luồng, trong khi `hasElements()` có thể trả lời ngay khi nhận phần tử đầu tiên.

Tương tự, nếu cần kiểm tra một điều kiện tồn tại, `any(predicate)` diễn đạt trực tiếp ý định hơn việc lọc rồi thu thập tất cả phần tử:

```java
// Trả lời trực tiếp câu hỏi có tồn tại phần tử thỏa điều kiện
Mono<Boolean> hasInvalidRecord =
    records.any(record -> !record.isValid());

// Không cần giữ danh sách chỉ để kiểm tra danh sách có rỗng hay không
Mono<Boolean> hasRecords =
    records.hasElements();
```

Nếu cần danh sách các phần tử phù hợp để xử lý tiếp, khi đó `filter` kết hợp `collectList()` mới đúng mục tiêu. Nếu chỉ cần một Boolean hoặc một con số, hãy dùng phép tổng hợp tương ứng.

## 8. Lỗi, hủy và nguồn có tác dụng phụ

Các phép tổng hợp trên vẫn tuân theo hợp đồng Reactive Streams:

- Nếu upstream phát `onError` trước khi phép tổng hợp kết luận, `Mono` kết quả phát lỗi.
- Khi đã có đủ thông tin để kết luận sớm, `hasElements`, `hasElement`, `any` và `all` có thể hủy subscription upstream.
- `count()` cần nguồn hoàn tất để phát tổng số; nếu nguồn lỗi, tổng số không được phát như một kết quả hoàn chỉnh.
- Nếu downstream hủy `Mono` kết quả trước khi có kết luận, việc hủy được truyền ngược lên upstream theo khả năng của publisher.

Ví dụ, nếu luồng sự kiện thực hiện ghi log hoặc cập nhật bộ đếm trong từng phần tử, một phép kiểm tra tồn tại có thể dừng luồng trước khi các phần tử sau được xử lý. Không đặt tác dụng phụ bắt buộc phải chạy cho mọi phần tử vào một pipeline mà sau đó dùng toán tử có thể short-circuit.

Với nguồn có tác dụng phụ hoặc chỉ tiêu thụ được một lần, hãy cân nhắc kỹ trước khi tạo nhiều phép tổng hợp trên cùng biến publisher. Mỗi subscription có thể kích hoạt một lượt đọc mới đối với publisher lạnh. Nếu cần nhiều thống kê từ cùng một lần đọc, hãy thiết kế một phép tổng hợp trạng thái trong một lượt duyệt thay vì subscribe riêng cho từng câu hỏi.

## 9. Kết hợp nhiều điều kiện trong một lượt duyệt

Khi cần nhiều thông tin từ cùng một luồng, có thể tích lũy một đối tượng thống kê bằng `reduce`. Ví dụ, cần biết tổng số đơn hàng và có đơn quá hạn hay không:

```java
record OrderSummary(long count, boolean hasOverdue) {}

Mono<OrderSummary> summary =
    orderRepository.findAll()
        .reduce(
            new OrderSummary(0L, false),
            (current, order) -> new OrderSummary(
                current.count() + 1,
                current.hasOverdue() || order.isOverdue()
            )
        );
```

Mỗi phần tử cập nhật trạng thái tích lũy. Khi nguồn hoàn tất, `reduce` phát một `OrderSummary`. Với nguồn rỗng, giá trị khởi tạo được phát: `count = 0` và `hasOverdue = false`.

Cách này phù hợp khi nhiều chỉ số cần được tính từ cùng một lượt đọc. Đổi lại, logic tích lũy phải được thiết kế cẩn thận để trạng thái cập nhật đúng và không chứa tác dụng phụ ngoài ý muốn.

Nếu chỉ cần một kết quả đơn giản, đừng tạo một bộ tích lũy phức tạp. Dùng `count`, `hasElements`, `any` hoặc `all` sẽ dễ đọc hơn.

## 10. Kiểm thử bằng StepVerifier

`StepVerifier` giúp kiểm tra giá trị Boolean, số lượng và tín hiệu kết thúc. Các trường hợp nguồn rỗng đặc biệt quan trọng vì `all` có quy tắc khác với `any`.

```java
StepVerifier.create(Flux.range(1, 5).count())
    .expectNext(5L)
    .verifyComplete();

StepVerifier.create(Flux.<Integer>empty().count())
    .expectNext(0L)
    .verifyComplete();

StepVerifier.create(Flux.just("A", "B").hasElements())
    .expectNext(true)
    .verifyComplete();

StepVerifier.create(Flux.<String>empty().hasElements())
    .expectNext(false)
    .verifyComplete();

StepVerifier.create(Flux.just("A", "B", "C").hasElement("B"))
    .expectNext(true)
    .verifyComplete();

StepVerifier.create(Flux.range(1, 5).any(value -> value > 4))
    .expectNext(true)
    .verifyComplete();

StepVerifier.create(Flux.range(1, 5).all(value -> value > 0))
    .expectNext(true)
    .verifyComplete();

StepVerifier.create(Flux.range(1, 5).all(value -> value < 5))
    .expectNext(false)
    .verifyComplete();

StepVerifier.create(Flux.<Integer>empty().any(value -> value > 0))
    .expectNext(false)
    .verifyComplete();

StepVerifier.create(Flux.<Integer>empty().all(value -> value > 0))
    .expectNext(true)
    .verifyComplete();
```

Có thể kiểm tra lỗi upstream:

```java
StepVerifier.create(
        Flux.<Integer>error(new IllegalStateException("source failed"))
            .count()
    )
    .expectErrorMessage("source failed")
    .verify();
```

Không có phép tổng hợp nào ở đây tự biến lỗi nguồn thành giá trị mặc định. Nếu muốn có chính sách phục hồi, hãy nối `onErrorResume` hoặc `onErrorReturn` sau phép tổng hợp và chỉ áp dụng cho loại lỗi phù hợp.

## 11. Những lỗi thường gặp

- **Dùng `count()` để kiểm tra tồn tại.** Đếm phải duyệt đến khi nguồn hoàn tất; dùng `hasElements()` nếu chỉ cần biết có phần tử hay không.
- **Nhầm `hasElements()` với `hasElement(value)`.** Một toán tử kiểm tra luồng không rỗng, toán tử kia tìm một giá trị cụ thể.
- **Nhầm `any` với `all`.** `any` cần ít nhất một phần tử đúng; `all` yêu cầu không có phần tử nào sai.
- **Quên ngữ nghĩa nguồn rỗng.** `any` trả false nhưng `all` trả true khi không có phần tử.
- **Cho rằng phép kiểm tra luôn duyệt hết nguồn.** `hasElements`, `hasElement`, `any` và `all` có thể hủy upstream ngay khi kết quả được xác định.
- **Subscribe nhiều lần vào nguồn chỉ dùng một lần.** Mỗi phép tổng hợp có thể tạo một subscription mới; hãy kiểm tra đặc tính của nguồn trước khi tái sử dụng.
- **Bỏ qua lỗi upstream.** Các phép tổng hợp không tự coi lỗi là false, zero hoặc empty; lỗi tiếp tục được truyền xuống.
- **Dùng phép tổng hợp để thay cho việc thu thập dữ liệu.** Nếu cần xử lý từng phần tử sau khi lọc, hãy dùng `filter` và toán tử phù hợp thay vì chỉ lấy một Boolean.

## 12. Bài tập vận dụng

Một hệ thống quản lý đơn hàng cần thống kê luồng `Order` từ repository. Hãy viết các publisher để trả lời các câu hỏi sau:

1. Có bao nhiêu đơn hàng trong luồng?
2. Có đơn hàng nào tồn tại không?
3. Có đơn hàng nào đang ở trạng thái `CANCELLED` không?
4. Có đơn hàng nào có tổng tiền lớn hơn 10 triệu đồng không?
5. Tất cả đơn hàng có ở trạng thái `PAID` không?
6. Nếu nguồn rỗng, kết quả của câu 3 và câu 5 là gì? Vì sao?
7. Nếu nguồn phát lỗi sau một số phần tử, mỗi phép tổng hợp sẽ phản hồi thế nào?
8. Nếu cần cả tổng số đơn và cờ cho biết có đơn quá hạn trong cùng một lần duyệt, hãy thiết kế một trạng thái tích lũy bằng `reduce`.

Dùng `StepVerifier` để kiểm tra nguồn có dữ liệu, nguồn rỗng, trường hợp điều kiện đúng, trường hợp điều kiện sai và lỗi upstream. Với các phép kiểm tra có thể kết luận sớm, giải thích khi nào subscription upstream được hủy và tác động của điều đó đến các công việc gắn với từng phần tử.

Chọn toán tử theo đúng câu hỏi cần trả lời: `count` để đếm toàn bộ, `hasElements` để kiểm tra luồng không rỗng, `hasElement` để tìm một giá trị, `any` để tìm ít nhất một phần tử thỏa điều kiện và `all` để xác nhận không có phần tử nào vi phạm điều kiện.
