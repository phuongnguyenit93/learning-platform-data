# Lấy, bỏ qua và giới hạn phần tử theo số lượng hoặc điều kiện

Trong một pipeline reactive, không phải lúc nào ta cũng cần tiêu thụ toàn bộ dữ liệu từ nguồn. Một màn hình có thể chỉ hiển thị vài kết quả đầu tiên, một tác vụ chỉ cần bỏ phần tiêu đề rồi xử lý phần còn lại, hoặc một luồng cần dừng khi gặp một sự kiện đánh dấu ranh giới. Project Reactor cung cấp các toán tử như take, skip, takeWhile, takeUntil, skipWhile và skipUntil để diễn đạt những quy tắc này trực tiếp trong pipeline.

Bài học thuộc chương **Biến đổi dữ liệu** của module **REACTIVE_PROGRAMMING**. Module giúp người học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các toán tử trong bài được vận dụng cùng Mono, Flux, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các ví dụ sử dụng Project Reactor. Những tên như orderRepository, log hoặc Order đại diện cho thành phần của ứng dụng; hãy thay bằng kiểu và bean thực tế của dự án.

Các đoạn mã tập trung vào phần pipeline nên lược bỏ một số import và khai báo miền. Khi đưa vào dự án, cần bổ sung các kiểu như Flux, Mono, Duration, StepVerifier và những lớp nghiệp vụ tương ứng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giới hạn số phần tử đầu ra bằng take(n) và bỏ qua một số phần tử đầu vào bằng skip(n).
- Phân biệt takeWhile với takeUntil, cũng như skipWhile với skipUntil.
- Xác định phần tử tại ranh giới điều kiện có được phát ra hay bị loại bỏ.
- Giải thích ảnh hưởng của take và skip đến demand, cancellation và công việc của upstream.
- Dự đoán kết quả khi kết hợp các toán tử theo thứ tự khác nhau.
- Kiểm thử luồng dữ liệu, điều kiện dừng và hành vi hủy bằng StepVerifier.

## 1. Lấy và bỏ qua theo số lượng

### take(n): chỉ nhận tối đa n phần tử

take(n) giới hạn số phần tử mà Flux phát xuống downstream. Khi đã phát đủ n phần tử, toán tử hủy subscription upstream vì không cần thêm dữ liệu:

~~~java
Flux<Integer> firstThree =
    Flux.range(1, 10)
        .take(3);
~~~

Kết quả là 1, 2, 3, sau đó Flux hoàn tất. Nguồn ban đầu có mười phần tử, nhưng downstream chỉ nhận tối đa ba phần tử.

Một ví dụ thường gặp là chỉ hiển thị một số kết quả đầu tiên:

~~~java
Flux<Order> featuredOrders =
    orderRepository.findRecentOrders()
        .take(5);
~~~

Nếu repository phát nhiều đơn hàng, subscriber chỉ nhận tối đa năm đơn đầu tiên. Với nguồn hỗ trợ cancellation, take báo cho upstream rằng không cần tiếp tục truy vấn hoặc phát thêm dữ liệu cho subscription đó. Khả năng dừng công việc thực tế còn phụ thuộc vào cách nguồn và driver triển khai việc hủy.

Một số trường hợp biên:

- take(0) không phát phần tử nào.
- Nếu nguồn chỉ có hai phần tử và dùng take(5), cả hai phần tử được phát rồi nguồn hoàn tất tự nhiên.
- Nếu downstream chỉ request một phần tử, take không thể phát vượt quá demand đó dù giới hạn của nó là năm.
- Khi đã phát đủ số lượng giới hạn, take hủy upstream; subscriber cuối vẫn nhận tín hiệu hoàn tất bình thường từ toán tử take.

Không nên nhầm take với việc lấy một danh sách bằng chỉ số. take không cần chờ toàn bộ nguồn hoàn tất để biết kết quả; nó có thể phát từng phần tử ngay khi nhận được và dừng khi đủ số lượng.

### skip(n): bỏ qua n phần tử đầu tiên

skip(n) tiêu thụ và loại bỏ n phần tử đầu tiên, sau đó chuyển tiếp các phần tử còn lại:

~~~java
Flux<Integer> afterHeader =
    Flux.range(1, 8)
        .skip(3);
~~~

Kết quả là 4, 5, 6, 7, 8. Toán tử bỏ 1, 2, 3 rồi phát phần còn lại.

Một ứng dụng có thể bỏ qua một số bản ghi đầu để xử lý phần dữ liệu mới hơn:

~~~java
Flux<AuditEvent> events =
    auditRepository.readEvents()
        .skip(100);
~~~

skip không hủy nguồn sau khi bỏ đủ n phần tử. Nó tiếp tục chuyển tiếp dữ liệu cho đến khi nguồn hoàn tất, phát lỗi hoặc bị downstream hủy.

Nếu nguồn kết thúc trước khi có đủ n phần tử, skip sẽ không phát gì và chuyển tín hiệu hoàn tất xuống downstream. Ví dụ Flux.range(1, 2).skip(5) tạo một Flux rỗng.

### take và skip không giống filter

take và skip làm việc theo vị trí trong chuỗi phần tử. filter đánh giá từng phần tử theo một điều kiện và có thể loại bỏ nhiều phần tử ở bất kỳ vị trí nào.

~~~java
Flux<Integer> firstThree =
    Flux.range(1, 10)
        .take(3);

Flux<Integer> evenNumbers =
    Flux.range(1, 10)
        .filter(number -> number % 2 == 0);
~~~

firstThree phát 1, 2, 3 rồi dừng. evenNumbers phát 2, 4, 6, 8, 10 và tiếp tục cho đến khi nguồn hoàn tất. filter không tự dừng sau một số lần loại bỏ hay sau lần khớp đầu tiên.

## 2. Lấy phần tử theo điều kiện

Các toán tử điều kiện đánh giá từng phần tử bằng Predicate. Khác biệt quan trọng nằm ở thời điểm dừng và việc phần tử làm điều kiện đúng có được phát xuống downstream hay không.

### takeWhile(predicate): phát khi điều kiện còn đúng

takeWhile phát các phần tử liên tiếp từ đầu luồng miễn là predicate trả về true. Ngay khi gặp phần tử đầu tiên làm predicate trả về false, toán tử loại bỏ phần tử đó và dừng nhận dữ liệu từ upstream:

~~~java
Flux<Integer> belowFour =
    Flux.range(1, 8)
        .takeWhile(number -> number < 4);
~~~

Kết quả là 1, 2, 3. Phần tử 4 làm điều kiện sai nên không được phát. Các phần tử 5, 6, 7, 8 cũng không được xử lý tiếp vì takeWhile đã kết thúc subscription upstream.

Hãy dùng takeWhile khi dữ liệu được sắp theo một ranh giới liên tục, chẳng hạn đọc các bản ghi cho đến khi gặp bản ghi đầu tiên nằm ngoài khoảng thời gian:

~~~java
Flux<Reading> currentWindow =
    readings.takeWhile(reading ->
        reading.timestamp().isBefore(windowEnd)
    );
~~~

Ví dụ này chỉ phù hợp nếu các bản ghi đến theo thứ tự thời gian. Nếu một bản ghi không thỏa điều kiện xuất hiện rồi sau đó có bản ghi khác lại thỏa, takeWhile vẫn đã dừng tại phần tử sai đầu tiên.

### takeUntil(predicate): phát cả phần tử làm điều kiện đúng

takeUntil cũng dừng khi predicate trả về true, nhưng nó phát luôn phần tử làm điều kiện đúng rồi mới kết thúc:

~~~java
Flux<Integer> throughFour =
    Flux.range(1, 8)
        .takeUntil(number -> number == 4);
~~~

Kết quả là 1, 2, 3, 4. Phần tử 4 được giữ lại vì nó đánh dấu phần tử cuối cùng cần phát.

Toán tử này phù hợp khi phần tử đánh dấu ranh giới cũng cần được xử lý, ví dụ nhận các sự kiện cho đến và bao gồm sự kiện SESSION_CLOSED:

~~~java
Flux<SessionEvent> sessionEvents =
    eventSource.takeUntil(event ->
        event.type() == EventType.SESSION_CLOSED
    );
~~~

Nếu sự kiện đóng phiên cần được ghi nhận, takeUntil giữ lại nó. Dùng takeWhile với điều kiện ngược lại có thể làm mất chính phần tử ranh giới đó.

### So sánh ranh giới

| Toán tử | Khi predicate trả về true | Phần tử làm điều kiện đúng |
|---|---|---|
| takeWhile | Tiếp tục phát | Chỉ phát khi predicate còn true; phần tử false đầu tiên bị loại và luồng dừng |
| takeUntil | Dừng sau phần tử hiện tại | Được phát rồi luồng dừng |

Có thể nhớ bằng cách đặt câu hỏi: điều kiện mô tả các phần tử cần giữ (takeWhile) hay mô tả sự kiện kết thúc cần bao gồm (takeUntil)?

## 3. Bỏ qua phần tử theo điều kiện

### skipWhile(predicate): bỏ liên tiếp khi điều kiện còn đúng

skipWhile bỏ các phần tử từ đầu luồng trong khi predicate trả về true. Khi gặp phần tử đầu tiên làm predicate trả về false, toán tử phát phần tử đó và tất cả phần tử tiếp theo:

~~~java
Flux<Integer> fromFour =
    Flux.range(1, 8)
        .skipWhile(number -> number < 4);
~~~

Kết quả là 4, 5, 6, 7, 8. Sau khi gặp 4, skipWhile ngừng kiểm tra điều kiện để quyết định bỏ qua. Vì vậy, nếu 5 hoặc 6 sau đó thỏa lại điều kiện ban đầu thì chúng vẫn được phát.

Ví dụ dùng để bỏ các bản ghi chưa đến thời điểm bắt đầu của một cửa sổ:

~~~java
Flux<Reading> window =
    readings.skipWhile(reading ->
        reading.timestamp().isBefore(windowStart)
    );
~~~

Cách dùng này giả định nguồn đã được sắp theo thời gian. skipWhile không tìm kiếm mọi phần tử thỏa điều kiện để loại bỏ; nó chỉ bỏ một đoạn liên tục ở đầu luồng.

### skipUntil(predicate): bỏ cho đến khi gặp phần tử khớp

skipUntil bỏ các phần tử đầu cho đến khi predicate trả về true. Phần tử đầu tiên khớp điều kiện được phát, sau đó tất cả phần tử tiếp theo cũng được phát:

~~~java
Flux<Integer> fromMarker =
    Flux.range(1, 8)
        .skipUntil(number -> number == 4);
~~~

Kết quả là 4, 5, 6, 7, 8. Khác với skipWhile, điều kiện ở đây diễn đạt sự kiện đánh dấu điểm bắt đầu cần giữ.

Một ví dụ là bỏ các sự kiện trước khi nhận tín hiệu bắt đầu phiên:

~~~java
Flux<SessionEvent> activeEvents =
    eventSource.skipUntil(event ->
        event.type() == EventType.SESSION_STARTED
    );
~~~

Sự kiện SESSION_STARTED được phát xuống downstream. Nếu nguồn hoàn tất mà chưa gặp sự kiện này, skipUntil hoàn tất mà không phát phần tử nào.

### So sánh skipWhile và skipUntil

| Toán tử | Quy tắc bỏ qua | Phần tử đầu tiên được phát |
|---|---|---|
| skipWhile | Bỏ khi predicate còn true | Phần tử đầu tiên làm predicate false |
| skipUntil | Bỏ cho đến khi predicate true | Phần tử đầu tiên làm predicate true |

Cả hai chỉ áp dụng điều kiện ở đoạn đầu luồng. Chúng không quay lại bỏ phần tử ở giữa luồng sau khi đã bắt đầu phát dữ liệu.

## 4. Kết hợp các toán tử và ảnh hưởng của thứ tự

Các toán tử take, skip và filter có thể kết hợp để diễn đạt quy tắc lấy dữ liệu. Tuy nhiên, đổi thứ tự toán tử có thể làm thay đổi kết quả.

~~~java
Flux<Integer> firstThenSkip =
    Flux.range(1, 20)
        .take(10)
        .skip(5);

Flux<Integer> skipThenTake =
    Flux.range(1, 20)
        .skip(5)
        .take(10);
~~~

| Pipeline | Kết quả |
|---|---|
| take(10).skip(5) | 6, 7, 8, 9, 10 |
| skip(5).take(10) | 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 |

Ở pipeline thứ nhất, take giới hạn nguồn còn mười phần tử rồi skip bỏ năm phần tử trong số đó. Ở pipeline thứ hai, skip bỏ năm phần tử đầu rồi take lấy tối đa mười phần tử tiếp theo.

Thứ tự với filter cũng quan trọng:

~~~java
Flux<Integer> filterThenTake =
    Flux.range(1, 10)
        .filter(number -> number % 2 == 0)
        .take(3);

Flux<Integer> takeThenFilter =
    Flux.range(1, 10)
        .take(3)
        .filter(number -> number % 2 == 0);
~~~

filterThenTake phát 2, 4, 6: nó lọc số chẵn trước rồi lấy ba kết quả. takeThenFilter chỉ xem ba số đầu 1, 2, 3, sau đó lọc và chỉ phát 2. Khi thiết kế pipeline, hãy xác định giới hạn áp dụng lên phần tử nguồn hay lên phần tử đã biến đổi/lọc.

Một cách thực hành tốt là đọc pipeline từ trên xuống và ghi rõ mỗi bước thay đổi tập phần tử nào. Điều này đặc biệt hữu ích khi có nhiều bước filter, skip và take liên tiếp.

## 5. Lấy hoặc bỏ các phần tử ở cuối luồng

Ngoài các toán tử làm việc từ đầu nguồn, Reactor còn có takeLast và skipLast:

- takeLast(n) giữ lại tối đa n phần tử cuối và chỉ phát chúng khi nguồn hoàn tất.
- skipLast(n) giữ một vùng đệm gồm n phần tử gần nhất để chắc chắn phần tử nào thuộc cuối luồng; khi có phần tử mới đến, phần tử cũ hơn được phát xuống downstream.

~~~java
Flux<Integer> lastThree =
    Flux.range(1, 8)
        .takeLast(3);

Flux<Integer> withoutLastTwo =
    Flux.range(1, 8)
        .skipLast(2);
~~~

lastThree phát 6, 7, 8 sau khi nguồn hoàn tất. withoutLastTwo phát 1, 2, 3, 4, 5, 6, bỏ 7, 8.

Các toán tử này cần lưu dữ liệu ở cuối luồng. takeLast(n) phải giữ các phần tử cuối cùng cho đến khi biết nguồn đã hoàn tất; skipLast(n) phải giữ lại n phần tử gần nhất để biết chúng có thật sự là phần tử cuối hay không. Với nguồn vô hạn, takeLast không thể phát kết quả cuối vì nguồn chưa hoàn tất; skipLast vẫn có thể phát các phần tử cũ hơn vùng đệm khi có dữ liệu mới đến.

Vì có lưu đệm, hãy cân nhắc kích thước n và kích thước từng phần tử. Không nên dùng takeLast hoặc skipLast với vùng đệm lớn trên nguồn vô hạn nếu không có một điều kiện kết thúc hoặc giới hạn khác.

## 6. Demand, backpressure và cancellation

Các toán tử lấy/bỏ không chỉ ảnh hưởng đến giá trị đầu ra; chúng còn tác động đến cách pipeline tiêu thụ upstream.

### take giới hạn nhu cầu tổng thể

take(n) không phát quá n phần tử. Khi đã đạt giới hạn, nó hủy subscription upstream để ngừng nhận thêm dữ liệu. Điều này đặc biệt hữu ích với nguồn vô hạn:

~~~java
Flux<Long> sample =
    Flux.interval(Duration.ofMillis(100))
        .take(5);
~~~

Flux.interval có thể phát vô hạn, nhưng take(5) khiến pipeline chỉ phát năm giá trị rồi kết thúc. Subscriber cuối nhận onComplete. Toán tử take hủy nguồn interval để không tiếp tục tạo tick cho subscription này.

Với nguồn nóng được chia sẻ cho nhiều subscriber, cancellation của một subscriber không nhất thiết dừng nguồn cho các subscriber khác. Nó chỉ hủy subscription hiện tại; việc nguồn nóng có dừng hay không phụ thuộc cách nguồn được chia sẻ và quản lý.

### skip vẫn cần tiêu thụ phần tử bị bỏ

skip(n) không phát n phần tử đầu nhưng vẫn cần nhận chúng từ upstream để biết khi nào đã bỏ đủ số lượng. Vì vậy, skip không đồng nghĩa với việc nguồn không phải tạo hoặc đọc các phần tử bị bỏ.

Nếu nguồn có thể đáp ứng demand, toán tử sẽ phối hợp request để tiêu thụ cả phần bị bỏ và phần cần phát. Với nguồn đọc từ tệp hoặc cơ sở dữ liệu, việc bỏ các phần tử ở tầng reactive có thể vẫn cần đọc qua dữ liệu đó. Nếu mục tiêu là tối ưu truy vấn hoặc giảm I/O nguồn, hãy cân nhắc đẩy điều kiện phân trang/lọc xuống tầng database hoặc API khi phù hợp.

### Điều kiện dừng cũng hủy upstream

takeWhile dừng ở phần tử đầu tiên không thỏa điều kiện; takeUntil dừng sau phần tử đầu tiên thỏa điều kiện. Cả hai đều không cần chờ nguồn hoàn tất tự nhiên. Khi điều kiện dừng được xác định, toán tử hủy upstream để tránh tiêu thụ dữ liệu không cần thiết.

Ngược lại, skipWhile và skipUntil không dừng nguồn sau khi tìm được ranh giới. Chúng chuyển sang chế độ phát phần tử và tiếp tục cho đến khi nguồn hoàn tất, lỗi hoặc downstream hủy.

### Không phải nguồn nào cũng dừng tức thì

Cancellation là tín hiệu điều khiển bất đồng bộ. Nó không thể đảo ngược một thao tác đã hoàn tất và không bảo đảm mọi API bên ngoài dừng ngay lập tức. Với HTTP client, database driver hoặc callback adapter, hãy kiểm tra cách thư viện hỗ trợ hủy và đặt timeout phù hợp. Không nên dựa vào take như cơ chế thay thế mọi giới hạn thời gian của hệ thống phụ thuộc.

## 7. Xử lý nguồn rỗng, lỗi và điều kiện không bao giờ khớp

Các toán tử lấy/bỏ vẫn tuân theo vòng đời Reactive Streams:

- Nếu nguồn hoàn tất trước khi đủ số lượng, các phần tử đã có được phát theo quy tắc toán tử rồi pipeline hoàn tất.
- Nếu nguồn lỗi trước khi toán tử đạt điều kiện dừng, lỗi được truyền xuống downstream.
- Nếu takeWhile gặp phần tử đầu tiên không thỏa, phần tử đó bị loại và pipeline hoàn tất.
- Nếu takeUntil gặp phần tử đầu tiên thỏa, phần tử đó được phát rồi pipeline hoàn tất.
- Nếu skipUntil không bao giờ gặp điều kiện true và nguồn hoàn tất, downstream nhận một luồng rỗng hoàn tất bình thường.
- Nếu downstream hủy trước khi điều kiện dừng xảy ra, upstream nhận cancellation.

Predicate có thể được gọi nhiều lần, một lần cho mỗi phần tử đi qua toán tử cho đến khi có quyết định dừng. Predicate nên là hàm thuần, nhanh và không có tác dụng phụ. Nếu predicate ném exception, pipeline kết thúc bằng onError. Tránh dùng predicate để cập nhật trạng thái nghiệp vụ hoặc gọi I/O chặn.

Ví dụ, nên viết điều kiện xác định từ chính phần tử:

~~~java
Flux<Order> validPrefix =
    orders.takeWhile(order ->
        order.status() != OrderStatus.CANCELLED
    );
~~~

Nếu điều kiện cần truy vấn dịch vụ bên ngoài, hãy biến đổi thành Publisher và dùng toán tử kết hợp bất đồng bộ phù hợp. Predicate của takeWhile/takeUntil là hàm đồng bộ, không nhận Mono<Boolean> hoặc Flux<Boolean>.

## 8. Kiểm thử với StepVerifier

StepVerifier giúp xác nhận chính xác phần tử được phát, tín hiệu kết thúc và cancellation.

### Kiểm thử take và skip theo số lượng

~~~java
StepVerifier.create(Flux.range(1, 10).take(3))
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(Flux.range(1, 8).skip(3))
    .expectNext(4, 5, 6, 7, 8)
    .verifyComplete();
~~~

Hai kiểm thử xác nhận take giới hạn đầu ra còn skip loại bỏ đoạn đầu.

### Kiểm thử ranh giới của điều kiện

~~~java
StepVerifier.create(
        Flux.range(1, 8).takeWhile(number -> number < 4)
    )
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(
        Flux.range(1, 8).takeUntil(number -> number == 4)
    )
    .expectNext(1, 2, 3, 4)
    .verifyComplete();
~~~

Kiểm thử này làm rõ sự khác nhau ở phần tử ranh giới: takeWhile loại phần tử đầu tiên không thỏa, còn takeUntil phát phần tử đầu tiên thỏa.

### Kiểm thử skipWhile và skipUntil

~~~java
StepVerifier.create(
        Flux.range(1, 8).skipWhile(number -> number < 4)
    )
    .expectNext(4, 5, 6, 7, 8)
    .verifyComplete();

StepVerifier.create(
        Flux.range(1, 8).skipUntil(number -> number == 4)
    )
    .expectNext(4, 5, 6, 7, 8)
    .verifyComplete();
~~~

Trong ví dụ này hai toán tử có cùng kết quả, nhưng ý nghĩa khác nhau: một toán tử dừng bỏ khi điều kiện false đầu tiên xuất hiện, toán tử còn lại dừng bỏ khi điều kiện true đầu tiên xuất hiện.

### Kiểm thử take hủy nguồn sau khi đủ số lượng

~~~java
AtomicBoolean upstreamCancelled = new AtomicBoolean();

Flux<Integer> source =
    Flux.range(1, 100)
        .doOnCancel(() -> upstreamCancelled.set(true));

StepVerifier.create(source.take(3))
    .expectNext(1, 2, 3)
    .verifyComplete();

assertTrue(upstreamCancelled.get());
~~~

Khi take đã phát đủ ba phần tử, nó hủy subscription upstream. Hook doOnCancel giúp xác nhận hành vi đó. Với nguồn hữu hạn, take có thể hủy trước khi nguồn phát hết; với nguồn chỉ có đúng ba phần tử, việc hoàn tất tự nhiên có thể xảy ra cùng ranh giới, nên ví dụ dùng một nguồn dài hơn để kiểm tra rõ việc hủy.

Trong dự án, hãy đặt các đoạn kiểm thử trong test class phù hợp và thêm import cần thiết, chẳng hạn reactor.test.StepVerifier, reactor.core.publisher.Flux và java.util.concurrent.atomic.AtomicBoolean.

## 9. Chọn toán tử theo yêu cầu

| Nhu cầu | Toán tử |
|---|---|
| Chỉ lấy tối đa n phần tử đầu | take(n) |
| Bỏ n phần tử đầu, phát phần còn lại | skip(n) |
| Phát đoạn đầu khi điều kiện còn đúng | takeWhile(predicate) |
| Phát đến và bao gồm phần tử đầu tiên thỏa điều kiện | takeUntil(predicate) |
| Bỏ đoạn đầu khi điều kiện còn đúng | skipWhile(predicate) |
| Bỏ cho đến và bắt đầu phát từ phần tử đầu tiên thỏa điều kiện | skipUntil(predicate) |
| Chỉ phát n phần tử cuối sau khi nguồn hoàn tất | takeLast(n) |
| Bỏ n phần tử cuối | skipLast(n) |

Trước khi chọn toán tử, hãy tự hỏi:

1. Quy tắc áp dụng cho đoạn đầu, đoạn cuối hay toàn bộ luồng?
2. Phần tử làm điều kiện đúng có cần được phát không?
3. Khi đạt ranh giới, có cần dừng upstream ngay không?
4. Nguồn có hữu hạn hay có thể phát vô hạn?
5. Việc bỏ phần tử ở tầng reactive có đủ hiệu quả hay cần đẩy điều kiện xuống nguồn dữ liệu?
6. Phần tử bị bỏ có tác dụng phụ hoặc yêu cầu audit nào cần được xử lý không?

## 10. Bài tập vận dụng

Một luồng sự kiện của thiết bị gồm các phần tử CONNECTED, MEASUREMENT và DISCONNECTED. Dữ liệu có thể chứa nhiều sự kiện trước khi thiết bị kết nối và sau khi thiết bị ngắt kết nối. Yêu cầu của ứng dụng là bỏ mọi sự kiện trước CONNECTED, phát từ chính sự kiện CONNECTED, lấy các phép đo cho đến và bao gồm DISCONNECTED, rồi kết thúc subscription.

Hãy xây dựng pipeline bằng skipUntil và takeUntil:

~~~java
Flux<DeviceEvent> session =
    deviceEvents
        .skipUntil(event -> event.type() == EventType.CONNECTED)
        .takeUntil(event -> event.type() == EventType.DISCONNECTED);
~~~

Sau đó trả lời:

1. Vì sao skipUntil giữ lại sự kiện CONNECTED?
2. Vì sao takeUntil giữ lại sự kiện DISCONNECTED?
3. Nếu luồng không bao giờ có CONNECTED nhưng hoàn tất, subscriber nhận tín hiệu gì?
4. Nếu luồng có CONNECTED nhưng không có DISCONNECTED, pipeline sẽ tiếp tục như thế nào?
5. Nếu subscriber hủy khi đang nhận MEASUREMENT, upstream được thông báo ra sao?
6. Nếu cần bỏ cả hai sự kiện ranh giới, bạn sẽ đặt filter ở vị trí nào và điều đó thay đổi kết quả thế nào?

Hãy viết kiểm thử StepVerifier cho ít nhất ba trường hợp: phiên có đủ hai sự kiện ranh giới, nguồn hoàn tất trước CONNECTED và subscriber hủy giữa phiên. Mục tiêu là xác nhận cả dữ liệu đầu ra lẫn vòng đời subscription.

## Kết luận

take và skip giới hạn hoặc bỏ phần tử theo số lượng. takeWhile và takeUntil dừng luồng theo điều kiện nhưng khác nhau ở việc phần tử ranh giới có được phát hay không. skipWhile và skipUntil bỏ một đoạn liên tục ở đầu luồng rồi chuyển sang phát dữ liệu. Thứ tự kết hợp các toán tử quyết định tập kết quả, còn take và các toán tử điều kiện dừng có thể hủy upstream khi không cần thêm dữ liệu. Khi hiểu rõ ranh giới phần tử, demand và cancellation, bạn có thể xây dựng pipeline Flux dễ đọc và kiểm thử chính xác hơn.
