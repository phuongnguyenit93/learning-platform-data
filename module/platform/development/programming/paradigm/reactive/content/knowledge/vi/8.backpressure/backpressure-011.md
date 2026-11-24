# Kiểm tra áp lực ngược bằng bên tiêu thụ chậm có kiểm soát

Trong **REACTIVE_PROGRAMMING**, `Publisher` phát dữ liệu bất đồng bộ cho `Subscriber` theo hợp đồng Reactive Streams. Khi consumer xử lý chậm hơn nguồn phát, pipeline cần kiểm soát lượng phần tử được yêu cầu, số tác vụ đang chạy và lượng dữ liệu đang chờ. Backpressure giúp consumer báo nhu cầu qua `request(n)`, nhưng muốn biết pipeline có thực sự tuân thủ nhu cầu hay không, ta cần kiểm thử với một consumer chậm có chủ đích và quan sát được.

Một kiểm thử tốt phải trả lời được: consumer yêu cầu bao nhiêu phần tử, upstream nhận yêu cầu đó ra sao, có bao nhiêu công việc đồng thời, phần tử có bị tích tụ hoặc mất không, và pipeline kết thúc thế nào khi consumer tiếp tục yêu cầu hoặc hủy đăng ký. Bài này sử dụng Reactor và `StepVerifier` để tạo tải chậm một cách xác định, không phụ thuộc vào tốc độ máy hay thời gian chờ thực.

## 1. Vì sao cần một consumer chậm có kiểm soát?

Nếu producer phát 1.000 phần tử mỗi giây trong khi mỗi consumer chỉ xử lý 100 phần tử mỗi giây, backlog có xu hướng tăng khoảng 900 phần tử mỗi giây nếu không có cơ chế điều tiết hoặc loại bỏ dữ liệu. Một bài kiểm thử chỉ chạy với consumer nhanh có thể không bộc lộ lỗi này.

Ta cần làm chậm consumer theo cách có thể lặp lại. Có hai khía cạnh cần kiểm tra riêng:

- **Demand:** Subscriber yêu cầu một phần tử hay một lô phần tử; Publisher không được phát vượt số lượng còn được yêu cầu.
- **Thời gian xử lý:** mỗi phần tử mất một khoảng thời gian xác định để xử lý; pipeline cần tránh tạo quá nhiều tác vụ đang chờ hoặc đang chạy cùng lúc.

Hai khía cạnh có liên quan nhưng không đồng nhất. `request(1)` kiểm soát số phần tử được phép phát theo giao thức. Một tác vụ xử lý mất 100 ms phản ánh năng lực xử lý theo thời gian. Backpressure không phải bộ giới hạn tốc độ theo giây; một consumer có thể yêu cầu nhiều phần tử cùng lúc dù từng phần tử cần thời gian xử lý.

## 2. Không dùng `Thread.sleep` để giả lập consumer chậm

Một cách dễ nghĩ đến là đặt `Thread.sleep` bên trong `map` hoặc callback `onNext`. Cách này chặn thread đang thực thi pipeline. Trong ứng dụng Reactor, thread đó có thể là thread event loop hoặc scheduler dùng chung; việc chặn nó làm sai lệch kết quả và có thể gây ảnh hưởng đến các tác vụ khác.

```java
// Không nên dùng để mô phỏng xử lý chậm trong pipeline reactive.
Flux<Integer> blocked = Flux.range(1, 10)
    .map(value -> {
        try {
            Thread.sleep(100);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
        return value;
    });
```

Để mô phỏng một công việc bất đồng bộ mất thời gian, hãy dùng Publisher có độ trễ như `Mono.delay`. Khi đó, thread không phải nằm ngủ trong thời gian chờ; pipeline tiếp tục theo dõi tín hiệu hoàn tất của công việc. Kết hợp `concatMap` với `prefetch` nhỏ để điều khiển số công việc đồng thời và lượng phần tử được lấy trước.

## 3. Quan sát demand và dữ liệu được phát

Reactor cung cấp `doOnRequest` để quan sát số lượng phần tử được yêu cầu đi qua một vị trí trong pipeline. `doOnNext` quan sát các phần tử phát ra tại vị trí đặt toán tử.

```java
Flux<Integer> source = Flux.range(1, 5)
    .doOnRequest(n -> log.info("Upstream received request: {}", n))
    .doOnNext(value -> log.info("Upstream emitted: {}", value));
```

Vị trí đặt `doOnRequest` có ý nghĩa. Đặt nó gần nguồn để quan sát demand mà nguồn nhận được; đặt ở downstream của một toán tử điều tiết để quan sát demand tại ranh giới đó. Các toán tử như `limitRate`, `publishOn`, `flatMap` hoặc `concatMap` có thể thay đổi cách demand được chia nhỏ, prefetch hoặc truyền lên upstream. Vì vậy, số lượng được ghi nhận ở hai vị trí khác nhau có thể khác nhau mà không đồng nghĩa có vi phạm giao thức.

Trong môi trường kiểm thử, có thể ghi các yêu cầu vào một danh sách hoặc bộ đếm thay vì phụ thuộc vào log:

```java
List<Long> requests = new ArrayList<>();

Flux<Integer> source = Flux.range(1, 3)
    .doOnRequest(requests::add);
```

Sau khi chạy kiểm thử, ta có thể xác nhận nguồn đã nhận các yêu cầu như mong đợi. Nên quan sát cả demand và `onNext`; chỉ đo số phần tử cuối cùng không cho biết consumer đã điều tiết nguồn theo cách nào.

## 4. Kiểm tra demand từng phần tử với StepVerifier

`StepVerifier` cho phép khởi tạo subscription với demand ban đầu bằng 0 rồi yêu cầu thêm dữ liệu theo từng bước. Đây là cách kiểm tra trực tiếp hợp đồng backpressure mà không cần tạo độ trễ thời gian.

```java
List<Long> requests = new ArrayList<>();

Flux<Integer> source = Flux.range(1, 3)
    .doOnRequest(requests::add);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();

assertEquals(List.of(1L, 1L, 1L), requests);
```

Kiểm thử này xác nhận:

1. Subscriber đăng ký nhưng chưa yêu cầu dữ liệu, nên nguồn không được phát `onNext`.
2. Mỗi lần Subscriber yêu cầu thêm một phần tử, nguồn phát tối đa một phần tử theo demand mới.
3. Sau phần tử thứ ba, nguồn hữu hạn phát `onComplete`.
4. Các yêu cầu được quan sát ở vị trí `doOnRequest` đúng với ba lần yêu cầu riêng lẻ.

`StepVerifier.create(source, 0)` đặt demand ban đầu bằng 0. Nếu bỏ tham số này, StepVerifier mặc định yêu cầu một lượng lớn dữ liệu để kiểm tra thuận tiện; khi đó bài kiểm thử không còn thể hiện consumer yêu cầu từng phần tử.

## 5. Mô phỏng công việc xử lý chậm bằng concatMap

Để mô phỏng mỗi phần tử cần 100 ms xử lý bất đồng bộ, có thể chuyển mỗi phần tử thành một `Mono.delay` rồi trả lại phần tử sau khi tác vụ hoàn tất:

```java
Flux<Integer> slowConsumer = Flux.range(1, 3)
    .concatMap(value ->
        Mono.delay(Duration.ofMillis(100))
            .thenReturn(value),
        1
    );
```

`concatMap` subscribe vào inner Publisher theo thứ tự và chỉ xử lý một inner Publisher tại một thời điểm. Tham số `prefetch = 1` giới hạn số phần tử outer được lấy trước cho toán tử. Đây là mô hình hữu ích cho consumer tuần tự như ghi tuần tự vào một thiết bị hoặc xử lý một luồng bản ghi theo thứ tự.

Độ trễ ở đây là công việc bất đồng bộ mô phỏng, không phải `Thread.sleep`. Nó không chặn thread trong 100 ms. Khi một inner Publisher hoàn tất, `concatMap` mới tiếp tục xử lý phần tử kế tiếp theo quy tắc của nó.

`prefetch = 1` là cấu hình tại toán tử `concatMap`, không phải cam kết rằng toàn bộ hệ thống chỉ giữ đúng một phần tử. Các tầng khác có thể có buffer hoặc prefetch riêng. Khi kiểm thử hệ thống thật, cần quan sát cả các ranh giới có queue và các dependency phía sau.

## 6. Kiểm thử thời gian xử lý bằng virtual time

Không nên bắt một unit test phải chờ đồng hồ thật nhiều giây chỉ để kiểm tra độ trễ. `StepVerifier.withVirtualTime` cho phép tiến thời gian ảo để kiểm thử các toán tử dựa trên scheduler.

```java
StepVerifier.withVirtualTime(() ->
        Flux.range(1, 3)
            .concatMap(value ->
                Mono.delay(Duration.ofMillis(100))
                    .thenReturn(value),
                1
            )
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(99))
    .thenAwait(Duration.ofMillis(1))
    .expectNext(1)
    .thenAwait(Duration.ofMillis(100))
    .expectNext(2)
    .thenAwait(Duration.ofMillis(100))
    .expectNext(3)
    .verifyComplete();
```

Supplier truyền vào `withVirtualTime` tạo pipeline bên trong môi trường virtual scheduler. Ba phần tử lần lượt xuất hiện sau các khoảng 100 ms ảo. Kiểm thử này xác nhận consumer tuần tự không hoàn tất phần tử tiếp theo trước khi khoảng xử lý của phần tử hiện tại kết thúc.

Virtual time phù hợp với `Mono.delay`, `Flux.interval`, `delayElements`, `timeout` và các toán tử sử dụng scheduler được hỗ trợ. Nó không làm cho một lời gọi blocking tùy ý như JDBC đồng bộ hoặc `Thread.sleep` chạy nhanh hơn; những thao tác đó vẫn cần được thay bằng nguồn bất đồng bộ hoặc kiểm thử riêng.

## 7. Đo số công việc đang xử lý đồng thời

Khi kiểm tra consumer chậm, ngoài thời gian phát phần tử, ta thường cần biết có bao nhiêu tác vụ đang chạy cùng lúc. Có thể dùng bộ đếm trong kiểm thử để đo số inner Publisher đang hoạt động:

```java
AtomicInteger inFlight = new AtomicInteger();
AtomicInteger maxInFlight = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Flux.range(1, 3)
            .concatMap(value ->
                Mono.delay(Duration.ofMillis(100))
                    .doOnSubscribe(subscription -> {
                        int current = inFlight.incrementAndGet();
                        maxInFlight.accumulateAndGet(current, Math::max);
                    })
                    .doFinally(signal -> inFlight.decrementAndGet())
                    .thenReturn(value),
                1
            )
    )
    .thenAwait(Duration.ofMillis(300))
    .expectNext(1, 2, 3)
    .verifyComplete();

assertEquals(1, maxInFlight.get());
assertEquals(0, inFlight.get());
```

Trong ví dụ, mỗi inner Publisher tăng bộ đếm khi được subscribe và giảm bộ đếm khi kết thúc. Vì `concatMap` chạy từng inner Publisher một, giá trị lớn nhất của `inFlight` là 1. Sau khi luồng hoàn tất, không còn tác vụ nào đang hoạt động.

Trong một kiểm thử thực tế, cần bảo đảm pipeline được tạo bên trong supplier của `withVirtualTime` để các scheduler được thay bằng virtual scheduler đúng lúc. Nếu muốn dùng lại pipeline đã tạo trước đó, hãy kiểm tra kỹ scheduler mà nguồn đã giữ; pipeline có thể đã chụp scheduler thực từ trước.

## 8. Phân biệt demand, prefetch, concurrency và rate limit

Các khái niệm này thường bị gọi chung là “giới hạn tải”, nhưng chúng kiểm soát những khía cạnh khác nhau:

| Cơ chế | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Demand | Số phần tử Subscriber cho phép Publisher phát | `request(1)` |
| Prefetch | Số phần tử một toán tử lấy trước từ upstream | `concatMap(mapper, 1)` |
| Concurrency | Số inner Publisher/tác vụ có thể hoạt động đồng thời | `flatMap(mapper, 8)` |
| Rate limit | Số thao tác được phép trong một đơn vị thời gian | 100 request/giây |
| Buffer capacity | Số phần tử có thể chờ tại một ranh giới | Queue tối đa 500 phần tử |

Ví dụ, `flatMap(this::callRemote, 8)` giới hạn tối đa tám inner Publisher hoạt động đồng thời ở toán tử đó. Nó không có nghĩa dịch vụ ngoài chỉ nhận tám request mỗi giây. Nếu mỗi request hoàn tất rất nhanh, số request mỗi giây vẫn có thể cao. Ngược lại, một rate limiter không tự giới hạn số phần tử đang nằm trong các queue khác.

Khi kiểm thử, cần xác định rõ điều kiện đang kiểm tra. Nếu mục tiêu là chứng minh nguồn không phát vượt demand, hãy điều khiển `request(n)` bằng StepVerifier. Nếu mục tiêu là giới hạn tác vụ đồng thời, hãy đo `inFlight`. Nếu mục tiêu là quota theo thời gian, cần kiểm thử rate limiter với clock hoặc scheduler có thể kiểm soát.

## 9. Kiểm tra hành vi khi consumer hủy đăng ký

Một consumer chậm có thể quyết định dừng xử lý vì hết thời gian chờ, người dùng hủy yêu cầu hoặc ứng dụng đóng. Khi đó cần xác minh subscription được hủy và công việc upstream được dừng hoặc giải phóng theo hợp đồng của nguồn.

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .doOnCancel(() -> log.info("Upstream cancelled")),
        0
    )
    .expectSubscription()
    .thenRequest(1)
    .thenAwait(Duration.ofMillis(100))
    .expectNext(0L)
    .thenCancel()
    .verify();
```

Ví dụ yêu cầu một phần tử, nhận tick đầu tiên rồi hủy subscription. `doOnCancel` cho phép quan sát yêu cầu hủy đi qua vị trí đặt toán tử. Với tài nguyên như file, socket hoặc cursor, cần xác minh thêm callback giải phóng tài nguyên được gọi khi hủy.

Hủy đăng ký không phát `onComplete` đến Subscriber. Nó là tín hiệu điều khiển từ downstream lên upstream. Vì vậy, kiểm thử cancellation cần dùng `thenCancel()` hoặc một cơ chế hủy tương đương, không chờ `verifyComplete()`.

## 10. Các lỗi kiểm thử thường gặp

| Lỗi | Vì sao gây hiểu nhầm? | Cách làm tốt hơn |
|---|---|---|
| Dùng consumer không giới hạn demand | Test mặc định có thể yêu cầu gần như toàn bộ dữ liệu ngay | Dùng `StepVerifier.create(source, 0)` và `thenRequest(n)` |
| Dùng `Thread.sleep` | Chặn thread và làm test phụ thuộc tải máy | Dùng `Mono.delay` và `withVirtualTime` |
| Chỉ kiểm tra phần tử đầu ra | Không biết demand đã truyền lên nguồn ra sao | Gắn `doOnRequest` ở các ranh giới cần quan sát |
| Nhầm `prefetch` với concurrency | Một toán tử có thể giữ phần tử chờ trong khi tác vụ khác đang chạy | Đo riêng số phần tử chờ và `inFlight` |
| Nhầm demand với rate limit | `request(n)` không mang đơn vị thời gian | Kiểm thử rate limiter riêng theo clock |
| Bỏ qua cancellation | Tác vụ hoặc tài nguyên có thể tiếp tục tồn tại sau khi downstream dừng | Kiểm tra `doOnCancel`, `doFinally` và giải phóng tài nguyên |
| Dùng nguồn không hỗ trợ backpressure nhưng kỳ vọng nó tự chậm lại | Nguồn có thể tiếp tục phát độc lập với demand | Kiểm tra adapter và chính sách buffer/drop/error tại ranh giới |

## 11. Checklist cho một bài kiểm thử consumer chậm

Trước khi xem một bài kiểm thử là đủ, hãy xác nhận:

1. Nguồn kiểm thử có tuân thủ Reactive Streams hay là nguồn nóng không thể điều tiết?
2. Demand ban đầu là bao nhiêu và bài test yêu cầu thêm dữ liệu ở thời điểm nào?
3. `doOnRequest` được đặt ở đâu để quan sát đúng ranh giới cần kiểm tra?
4. Công việc chậm được mô phỏng bằng Publisher bất đồng bộ hay bằng thao tác blocking?
5. Prefetch và concurrency có được đặt theo mục tiêu kiểm thử không?
6. Test có đo số tác vụ đang chạy và số phần tử được phát không?
7. Khi hoàn tất, lỗi hoặc cancellation, subscription và tài nguyên có được giải phóng không?
8. Thời gian được kiểm soát bằng virtual time khi có thể, tránh phụ thuộc vào thời gian thực không cần thiết?

Một consumer chậm có kiểm soát giúp tái tạo chênh lệch tốc độ và kiểm chứng hành vi của pipeline một cách ổn định. Kết hợp demand từng phần tử, xử lý bất đồng bộ tuần tự, quan sát request, đo concurrency và kiểm thử cancellation giúp xác định rõ nơi backpressure đang có hiệu lực, nơi còn buffer hoặc prefetch, và liệu hệ thống có tiếp tục giữ tài nguyên sau khi downstream dừng hay không.
