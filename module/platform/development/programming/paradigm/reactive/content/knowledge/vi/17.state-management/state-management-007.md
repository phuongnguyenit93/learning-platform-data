# Tính xác định khi kết quả phụ thuộc thứ tự hoặc thời điểm

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` xử lý dữ liệu bất đồng bộ qua hợp đồng `Publisher–Subscriber`. Một pipeline có thể nhận nhiều sự kiện, gọi nhiều dịch vụ cùng lúc, chuyển dữ liệu qua scheduler và cập nhật trạng thái từ các kết quả đó. Khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các tín hiệu đến, cùng một đầu vào có thể tạo ra kết quả khác nhau giữa các lần chạy.

Tính xác định (determinism) là khả năng tạo cùng kết quả và cùng hành vi quan sát được khi đầu vào và điều kiện liên quan giống nhau. Muốn đạt được điều đó, cần làm rõ thứ tự nào có ý nghĩa nghiệp vụ, thời điểm nào được dùng để ra quyết định và trạng thái được sở hữu bởi subscription nào. Không phải pipeline bất đồng bộ nào cũng cần xử lý tuần tự; điều quan trọng là chọn rõ nơi cần giữ thứ tự và nơi có thể chạy song song.

## 1. Vì sao cùng đầu vào có thể cho kết quả khác nhau?

Trong chương **Trạng thái**, ta quan tâm đến việc kết quả thay đổi như thế nào theo các sự kiện và trạng thái trước đó. Một pipeline có thể mất tính xác định khi:

- Các Publisher con hoàn tất theo thứ tự khác với thứ tự đầu vào.
- Nhiều tác vụ cùng cập nhật một trạng thái mutable.
- Một quyết định phụ thuộc `Instant.now()`, timeout hoặc timer thực tế.
- Một nguồn nóng phát sự kiện tùy theo thời điểm Subscriber đăng ký.
- Retry hoặc nhiều subscription làm một tác dụng phụ được thực hiện lại.
- Một kết quả được tính từ thứ tự phát sự kiện nhưng thứ tự đó không được đặc tả bởi nghiệp vụ.

Ví dụ, một tài khoản nhận hai sự kiện: cộng 100 và trừ 30. Nếu chỉ tính số dư cuối bằng phép cộng/trừ, kết quả có thể giống nhau. Nhưng nếu sự kiện thứ nhất là “đóng tài khoản” và sự kiện thứ hai là “ghi nhận thanh toán”, thứ tự có thể quyết định thanh toán có được chấp nhận hay không. Các phép cập nhật trạng thái không giao hoán cần một thứ tự rõ ràng.

## 2. Phân biệt thứ tự đầu vào, thứ tự hoàn tất và thứ tự phát ra

Khi ghép Publisher bất đồng bộ, cần phân biệt ba thứ tự:

1. **Thứ tự đầu vào:** thứ tự phần tử mà outer Publisher phát đến toán tử ghép luồng.
2. **Thứ tự hoàn tất:** thứ tự các Publisher con hoàn tất công việc của chúng.
3. **Thứ tự phát ra:** thứ tự phần tử mà downstream thực sự nhận.

Với `flatMap`, các Publisher con có thể chạy đồng thời và kết quả thường được phát khi sẵn sàng. Do đó, thứ tự phát ra có thể khác thứ tự đầu vào:

```java
Flux<Integer> unordered = Flux.just(1, 2, 3)
    .flatMap(id -> {
        Duration delay = switch (id) {
            case 1 -> Duration.ofMillis(300);
            case 2 -> Duration.ofMillis(100);
            default -> Duration.ofMillis(200);
        };
        return Mono.delay(delay).thenReturn(id);
    }, 3);
```

Ba Publisher con được subscribe đồng thời. Phần tử `2` hoàn tất trước, tiếp theo là `3`, rồi `1`; downstream có thể nhận `2, 3, 1`. Đây là hành vi phù hợp khi kết quả độc lập và thứ tự hoàn tất được chấp nhận.

Nếu nghiệp vụ yêu cầu giữ thứ tự đầu vào, có thể chọn một trong hai cách sau:

| Toán tử | Cách xử lý | Đánh đổi |
|---|---|---|
| `flatMapSequential` | Subscribe nhiều Publisher con đồng thời nhưng phát kết quả theo thứ tự outer | Kết quả hoàn tất sớm có thể phải chờ trong buffer phía sau phần tử trước đó |
| `concatMap` | Chỉ subscribe Publisher con tiếp theo sau khi Publisher hiện tại kết thúc | Giữ thứ tự và tránh chạy inner đồng thời, nhưng một inner chậm làm các phần tử sau phải chờ |

Ví dụ giữ thứ tự trong khi vẫn cho phép công việc chạy đồng thời:

```java
Flux<Integer> ordered = Flux.just(1, 2, 3)
    .flatMapSequential(id -> {
        Duration delay = id == 1
            ? Duration.ofMillis(300)
            : Duration.ofMillis(100);
        return Mono.delay(delay).thenReturn(id);
    }, 3);
```

`flatMapSequential` giữ thứ tự phát kết quả, nhưng không tuần tự hóa các tác dụng phụ bên trong Publisher con. Nếu mỗi inner Publisher thực hiện ghi dữ liệu hoặc cập nhật trạng thái bên ngoài, các thao tác đó vẫn có thể chạy đồng thời. Khi bản thân tác dụng phụ phải diễn ra theo thứ tự, hãy dùng `concatMap` hoặc một cơ chế tuần tự hóa ở tầng lưu trữ.

## 3. Thứ tự tín hiệu không giống thứ tự xử lý nghiệp vụ

Reactive Streams yêu cầu tín hiệu của một subscription được gửi tuần tự; `onNext` không chồng lấn và thứ tự phát của một Publisher được giữ. Điều đó không tự bảo đảm thứ tự hoàn tất của các công việc được khởi chạy bên trong từng phần tử.

Ví dụ:

```java
Flux<Event> events = eventSource()
    .publishOn(Schedulers.parallel())
    .map(this::normalize);
```

`publishOn` chuyển việc xử lý phía downstream sang scheduler và dùng queue để chuyển tín hiệu. Bản thân nó không đảo thứ tự `onNext` của một subscription. Nhưng nếu sau đó dùng `flatMap` để gọi nhiều Publisher con, các kết quả bất đồng bộ có thể hoàn tất theo thứ tự khác.

Vì vậy, khi điều tra kết quả không ổn định, hãy tìm toán tử thực sự tạo concurrency. Không nên quy mọi khác biệt thứ tự cho scheduler. Scheduler quyết định nơi công việc chạy; toán tử ghép luồng quyết định cách các kết quả của nhiều công việc được hợp nhất.

## 4. Trạng thái tích lũy phải có quy tắc chuyển trạng thái rõ ràng

Một trạng thái thường được tính từ trạng thái trước đó và sự kiện hiện tại:

\[
S_{n+1} = f(S_n, E_n)
\]

Trong đó \(S_n\) là trạng thái hiện tại, \(E_n\) là sự kiện tiếp theo và \(f\) là hàm chuyển trạng thái. Nếu `f` phụ thuộc thứ tự sự kiện, thay đổi thứ tự đầu vào có thể làm thay đổi kết quả cuối.

Reactor có `scan` và `scanWith` để biểu diễn trạng thái tích lũy theo từng phần tử:

```java
record AccountEvent(long sequence, long delta) {}
record AccountState(long balance, long version) {}

Flux<AccountState> history = accountEvents
    .scanWith(
        () -> new AccountState(0, 0),
        (state, event) -> new AccountState(
            state.balance() + event.delta(),
            state.version() + 1
        )
    );
```

`scanWith` tạo trạng thái khởi đầu riêng cho mỗi subscription. Mỗi sự kiện tạo một trạng thái bất biến mới, nên các subscriber không sửa chung một object accumulator. Downstream nhận các trạng thái trung gian theo thứ tự tín hiệu của `accountEvents`.

Nếu `accountEvents` đã bị một bước `flatMap` làm thay đổi thứ tự phát, `scanWith` vẫn tính đúng theo thứ tự nó nhận được, nhưng kết quả có thể khác với thứ tự nghiệp vụ mong muốn. Hãy bảo đảm thứ tự trước bước tích lũy.

## 5. Sắp xếp sự kiện bằng sequence number khi thứ tự có ý nghĩa

Nếu nguồn có thể phát sự kiện không theo thứ tự nghiệp vụ, mỗi sự kiện nên mang một khóa thứ tự đáng tin cậy, chẳng hạn sequence number do nguồn tạo ra:

```java
Flux<AccountEvent> orderedEvents = finiteEvents
    .sort(Comparator.comparingLong(AccountEvent::sequence));

Flux<AccountState> states = orderedEvents
    .scanWith(
        () -> new AccountState(0, 0),
        (state, event) -> new AccountState(
            state.balance() + event.delta(),
            state.version() + 1
        )
    );
```

`sort` giữ toàn bộ phần tử trước khi phát kết quả đã sắp xếp. Vì vậy, cách này phù hợp với nguồn hữu hạn và có thể tiêu thụ bộ nhớ theo kích thước nguồn. Không dùng `sort` cho luồng vô hạn vì không có thời điểm toàn bộ nguồn hoàn tất để bắt đầu phát kết quả đã sắp xếp.

Với luồng liên tục, cần một quy tắc thứ tự theo từng partition hoặc một khoảng chờ có giới hạn. Ví dụ, hệ thống có thể giữ sự kiện trong một cửa sổ reorder nhỏ, chờ sequence còn thiếu đến trong thời gian cho phép rồi mới phát. Sau watermark hoặc deadline, sự kiện đến muộn phải được xử lý theo chính sách rõ ràng: bỏ, ghi nhận riêng, cập nhật bù hoặc yêu cầu phát lại.

Sequence number chỉ có ý nghĩa nếu nguồn định nghĩa cách cấp số và phạm vi duy nhất của nó. Nếu nhiều producer cấp số độc lập, cần partition key hoặc version theo aggregate để tránh so sánh các sequence không cùng miền.

## 6. Tránh chia sẻ trạng thái mutable giữa nhiều subscription

Một Publisher lạnh có thể được subscribe nhiều lần. Nếu accumulator mutable được tạo bên ngoài pipeline rồi dùng chung, các subscription có thể cùng sửa một object:

```java
// Không nên: cùng một list bị nhiều subscription sử dụng.
List<String> shared = new ArrayList<>();

Mono<List<String>> result = names
    .reduce(shared, (list, name) -> {
        list.add(name);
        return list;
    });
```

Vấn đề không chỉ là thread safety. Kết quả của subscription thứ hai có thể chứa dữ liệu do subscription thứ nhất thêm vào; thứ tự và nội dung phụ thuộc lịch sử subscribe.

Nếu cần accumulator mutable, tạo mới cho mỗi subscription bằng `reduceWith` hoặc `collect` với supplier phù hợp:

```java
Mono<List<String>> isolated = names.reduceWith(
    ArrayList::new,
    (list, name) -> {
        list.add(name);
        return list;
    }
);
```

Nếu mục tiêu là gom tất cả phần tử thành danh sách, `collectList()` thường diễn đạt ý định rõ hơn. Với trạng thái tích lũy từng bước, ưu tiên `scanWith` cùng trạng thái bất biến.

## 7. Atomic không tự tạo ra thứ tự nghiệp vụ

`AtomicLong`, `AtomicReference` hoặc cấu trúc concurrent giúp tránh một số race condition khi nhiều thread cập nhật cùng trạng thái. Nhưng atomic chỉ bảo đảm thao tác nguyên tử theo cơ chế của nó; nó không tự quyết định thứ tự nghiệp vụ mong muốn.

Ví dụ, hai tác vụ đồng thời gọi `incrementAndGet()`. Bộ đếm không mất lần tăng, nhưng số thứ tự được cấp cho từng tác vụ phụ thuộc tác vụ nào đến trước tại thời điểm atomic update. Nếu tác vụ A bắt buộc có version trước B, chỉ dùng atomic là chưa đủ.

Khi thứ tự cập nhật quan trọng, hãy chọn một cơ chế rõ ràng:

- Tuần tự hóa các cập nhật bằng `concatMap` trong một partition.
- Dùng actor hoặc single-writer cho từng aggregate.
- Dùng version và optimistic locking ở database để từ chối cập nhật dựa trên trạng thái cũ.
- Dùng sequence number từ nguồn và xử lý sự kiện theo thứ tự đó.

Nếu các cập nhật độc lập và phép gộp có tính giao hoán, kết hợp, có thể xử lý song song rồi tổng hợp. Ví dụ, đếm số sự kiện hoặc cộng các giá trị độc lập có thể phù hợp. Nhưng cần kiểm tra overflow, tính chính xác số học và việc sự kiện có bị xử lý lặp hay không.

## 8. Thời điểm cũng là một phần của trạng thái

Kết quả có thể khác nhau nếu logic đọc đồng hồ hệ thống ở nhiều vị trí. Ví dụ:

```java
Mono<AuditRecord> audit = Mono.fromSupplier(() ->
    new AuditRecord(requestId, Instant.now())
);
```

Mỗi subscription có thể tạo timestamp khác nhau. Nếu timestamp được dùng để quyết định hết hạn, phân loại sự kiện hoặc tính thời lượng, kết quả có thể thay đổi giữa các lần chạy.

Hãy phân biệt:

- **Event time:** thời điểm sự kiện thực sự xảy ra theo nguồn phát, thường nằm trong dữ liệu sự kiện.
- **Processing time:** thời điểm ứng dụng xử lý sự kiện.
- **Ingestion time:** thời điểm hệ thống tiếp nhận sự kiện vào một ranh giới cụ thể.

Không nên thay thế event time bằng `Instant.now()` nếu nghiệp vụ cần biết thời điểm sự kiện xảy ra. Một sự kiện có thể đến muộn nhưng vẫn mang event time cũ. Với xử lý cửa sổ, tổng hợp theo thời gian hoặc phát hiện sự kiện trễ, cần xác định loại thời gian được dùng.

## 9. Tiêm Clock để kiểm soát thời gian

Thay vì gọi trực tiếp `Instant.now()` rải rác, có thể truyền `Clock` vào thành phần nghiệp vụ:

```java
final class AuditService {
    private final Clock clock;

    AuditService(Clock clock) {
        this.clock = clock;
    }

    Mono<AuditRecord> record(String requestId) {
        return Mono.fromSupplier(() ->
            new AuditRecord(requestId, clock.instant())
        );
    }
}
```

Trong ứng dụng, có thể dùng `Clock.systemUTC()`. Trong kiểm thử, dùng `Clock.fixed(...)` để mọi lần đọc thời gian trả về cùng một instant:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);

AuditService service = new AuditService(fixedClock);
```

Với logic cần tiến thời gian, có thể dùng clock giả có thể điều khiển trong test. `StepVerifier.withVirtualTime` điều khiển scheduler thời gian của Reactor cho các toán tử như `delay`, `interval` và `timeout`; nó không tự thay thế `Instant.now()` hoặc clock hệ thống mà ứng dụng gọi trực tiếp. Vì vậy, hãy kiểm soát cả scheduler lẫn `Clock` khi kiểm thử hành vi phụ thuộc thời gian.

## 10. Nguồn nóng, subscription và thời điểm bắt đầu nhận dữ liệu

Với nguồn lạnh, mỗi subscription thường bắt đầu một lần thực thi nguồn riêng. Với nguồn nóng, sự kiện có thể phát độc lập với subscriber. Một subscriber đăng ký muộn có thể bỏ lỡ các sự kiện đã phát trước đó, trừ khi nguồn có replay hoặc buffer.

Ví dụ, một luồng sự kiện chia sẻ có thể phát dữ liệu trước khi một consumer bắt đầu subscribe. Nếu trạng thái khởi tạo của consumer giả định đã nhận đủ mọi sự kiện từ đầu, trạng thái đó sẽ không xác định.

Các cách giải quyết thường dùng:

- Khởi tạo consumer từ snapshot có version rồi chỉ nhận sự kiện sau version đó.
- Dùng nguồn có replay hoặc log bền vững khi cần phát lại lịch sử.
- Xác định rõ semantics của `share`, `replay` hoặc `cache` và thời điểm kết nối nguồn.
- Kết hợp snapshot và event stream bằng sequence number để không bỏ sót hoặc áp dụng trùng sự kiện tại ranh giới chuyển tiếp.

Không nên giả định `share()` lưu lại mọi phần tử đã phát. Chia sẻ subscription và replay lịch sử là hai yêu cầu khác nhau.

## 11. Retry và repeat có thể làm thay đổi trạng thái

Retry đăng ký lại nguồn khi lỗi. Nếu nguồn là cold và đã phát một số phần tử trước khi lỗi, các phần tử đó có thể xuất hiện lại sau retry. Nếu downstream đã cập nhật trạng thái hoặc ghi dữ liệu từ prefix trước lỗi, việc phát lại có thể tạo tác dụng phụ trùng.

```java
Flux<Event> applied = eventSource()
    .concatMap(event -> stateRepository.apply(event))
    .retry(1);
```

Nếu một số `apply` đã thành công trước khi nguồn lỗi, retry có thể khiến các sự kiện tương ứng được áp dụng lần nữa. Để kết quả ổn định, thao tác cập nhật cần idempotent, có event ID/sequence để deduplicate hoặc dùng transaction/checkpoint ở ranh giới phù hợp.

`repeat` đăng ký lại sau khi nguồn hoàn tất bình thường. Nếu nó được dùng cho polling, cần xác định trạng thái nào được giữ giữa các chu kỳ và trạng thái nào được tạo mới cho từng subscription. Tránh đặt accumulator mutable dùng chung bên ngoài factory của nguồn lặp.

## 12. Kiểm thử tính xác định bằng virtual time

Không nên dùng `Thread.sleep` để kiểm tra thứ tự hoàn tất. Dùng `StepVerifier.withVirtualTime` để mô phỏng thời gian và xác nhận kết quả theo từng toán tử.

Kiểm thử `flatMap` phát theo thời điểm hoàn tất:

```java
StepVerifier.withVirtualTime(() ->
        Flux.just(1, 2, 3)
            .flatMap(id -> {
                Duration delay = switch (id) {
                    case 1 -> Duration.ofMillis(300);
                    case 2 -> Duration.ofMillis(100);
                    default -> Duration.ofMillis(200);
                };
                return Mono.delay(delay).thenReturn(id);
            }, 3)
    )
    .thenAwait(Duration.ofMillis(300))
    .expectNext(2, 3, 1)
    .verifyComplete();
```

Kiểm thử `flatMapSequential` giữ thứ tự đầu vào:

```java
StepVerifier.withVirtualTime(() ->
        Flux.just(1, 2, 3)
            .flatMapSequential(id -> {
                Duration delay = switch (id) {
                    case 1 -> Duration.ofMillis(300);
                    case 2 -> Duration.ofMillis(100);
                    default -> Duration.ofMillis(200);
                };
                return Mono.delay(delay).thenReturn(id);
            }, 3)
    )
    .thenAwait(Duration.ofMillis(300))
    .expectNext(1, 2, 3)
    .verifyComplete();
```

Các kiểm thử này làm rõ semantics mà pipeline đang chọn. Khi thay đổi concurrency hoặc toán tử ghép luồng, hãy giữ các assertion thứ tự để phát hiện hành vi thay đổi ngoài ý muốn.

## 13. Kiểm thử trạng thái và thời gian độc lập với môi trường

Một bài test trạng thái nên kiểm tra:

1. Cùng một chuỗi sự kiện có sequence giống nhau luôn tạo cùng lịch sử trạng thái.
2. Nhiều subscription không chia sẻ accumulator mutable ngoài ý muốn.
3. Sự kiện đến sai thứ tự được sắp xếp, giữ lại hoặc xử lý theo chính sách đã định.
4. Cập nhật trùng do retry không làm thay đổi trạng thái hai lần nếu nghiệp vụ yêu cầu idempotency.
5. Timestamp được lấy từ event time hay processing time đúng với yêu cầu.
6. Clock cố định hoặc clock giả giúp test không phụ thuộc thời điểm chạy.
7. Virtual time kiểm soát các toán tử delay/timeout và test có cancellation rõ ràng.

Ví dụ, với `Clock.fixed`, có thể xác minh timestamp chính xác thay vì chỉ kiểm tra nó nằm trong một khoảng thời gian gần đúng:

```java
StepVerifier.create(service.record("req-42"))
    .expectNext(new AuditRecord(
        "req-42",
        Instant.parse("2026-01-15T10:00:00Z")
    ))
    .verifyComplete();
```

Nếu dùng `Clock.systemUTC()` trong test, kết quả sẽ phụ thuộc thời điểm test thực sự chạy. Tiêm clock giúp kiểm thử tập trung vào logic nghiệp vụ.

## 14. Chọn chiến lược theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược phù hợp | Điều cần kiểm soát |
|---|---|---|
| Kết quả độc lập, thứ tự không quan trọng | `flatMap` có concurrency hữu hạn | Giới hạn tải và xử lý lỗi từng inner |
| Cần phát kết quả theo thứ tự nhưng muốn chạy song song | `flatMapSequential` | Buffer và head-of-line blocking |
| Tác dụng phụ phải diễn ra tuần tự | `concatMap` hoặc single-writer | Độ trễ của phần tử chậm và cancellation |
| Tính trạng thái từ chuỗi sự kiện | `scanWith` với trạng thái bất biến | Thứ tự sự kiện và sequence number |
| Sự kiện có thể đến muộn hoặc sai thứ tự | Event time, watermark hoặc reorder window | Giới hạn chờ và chính sách late event |
| Kết quả phụ thuộc thời gian hiện tại | Tiêm `Clock` | Phân biệt event time và processing time |
| Nguồn có thể phát lại khi retry | Idempotency và deduplication | Event ID, version và checkpoint |

Không cần tuần tự hóa toàn bộ pipeline để đạt tính xác định. Hãy giới hạn tuần tự hóa ở aggregate hoặc partition nơi thứ tự có ý nghĩa; các công việc độc lập vẫn có thể chạy song song. Cách này vừa giữ được tính đúng đắn của trạng thái, vừa tận dụng khả năng xử lý bất đồng bộ.

## 15. Checklist chẩn đoán kết quả không ổn định

Khi cùng một đầu vào tạo kết quả khác nhau, hãy lần lượt kiểm tra:

1. Nguồn có phát cùng tập sự kiện và cùng sequence number không?
2. Có `flatMap` hoặc operator nào cho phép kết quả hoàn tất không theo thứ tự không?
3. Thứ tự cần giữ là thứ tự đầu vào, thứ tự event time hay thứ tự hoàn tất?
4. Có trạng thái mutable được chia sẻ giữa nhiều subscription hoặc thread không?
5. Có tác dụng phụ nào chạy đồng thời dù downstream phát kết quả theo thứ tự không?
6. Logic có đọc clock hệ thống hoặc phụ thuộc timeout thực không?
7. Retry/repeat có phát lại sự kiện hoặc thực hiện tác dụng phụ lần nữa không?
8. Nguồn nóng có thể phát trước khi subscriber đăng ký hoặc bỏ lỡ lịch sử không?
9. Kiểm thử có dùng virtual time, clock giả và dữ liệu đầu vào cố định không?

Tính xác định đến từ việc quy định rõ thứ tự, thời gian và quyền sở hữu trạng thái. Dùng `flatMap` khi thứ tự không quan trọng, `flatMapSequential` khi chỉ cần giữ thứ tự phát kết quả, `concatMap` khi tác dụng phụ phải tuần tự, và trạng thái bất biến theo từng subscription để tránh chia sẻ ngoài ý muốn. Kết hợp sequence number, event time, clock có thể kiểm soát và kiểm thử virtual time giúp pipeline reactive tạo ra kết quả có thể dự đoán và tái lập.
