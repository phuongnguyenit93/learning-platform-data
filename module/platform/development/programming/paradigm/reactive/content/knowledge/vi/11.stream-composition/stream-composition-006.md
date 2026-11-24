# `concat` và `merge`: nối tiếp hoặc trộn nhiều nguồn

Một pipeline reactive thường cần lấy dữ liệu từ nhiều Publisher: hồ sơ khách hàng từ một dịch vụ, lịch sử giao dịch từ dịch vụ khác, hoặc sự kiện từ nhiều thiết bị. Khi kết hợp các nguồn, ta cần quyết định dữ liệu sẽ được phát theo từng nguồn nối tiếp hay được trộn theo thời điểm các nguồn phát tín hiệu. Trong Project Reactor, `concat` và `merge` giải quyết hai nhu cầu khác nhau này.

`concat` tiêu thụ từng nguồn theo thứ tự: nguồn hiện tại phải hoàn tất rồi nguồn kế tiếp mới được đăng ký. `merge` đăng ký nhiều nguồn và chuyển các phần tử xuống downstream khi chúng đến, vì vậy các phần tử từ các nguồn có thể xen kẽ. Chọn đúng toán tử ảnh hưởng đến thứ tự dữ liệu, thời điểm đăng ký, lỗi, tài nguyên và khả năng xử lý đồng thời.

Chủ đề này thuộc chương **Ghép luồng** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi ghép luồng, hãy xác định thứ tự nghiệp vụ có bắt buộc hay không, các nguồn có thể chạy đồng thời không và điều gì cần xảy ra nếu một nguồn thất bại.

## Hai cách kết hợp nhiều Publisher

Giả sử có hai nguồn A và B:

```text
Nguồn A:  A1 ───── A2 ───── A3 ──|
Nguồn B:  B1 ── B2 ──────────────|
```

Với `concat`, toàn bộ phần tử của A được phát trước, sau đó mới tới B:

```text
concat:   A1 ───── A2 ───── A3 ── B1 ── B2 ──|
```

Với `merge`, các phần tử được chuyển tiếp theo thời điểm chúng đến từ các nguồn:

```text
merge:    A1 ── B1 ── B2 ── A2 ───── A3 ──|
```

Sơ đồ `merge` chỉ minh họa một cách xen kẽ có thể xảy ra. Thứ tự tương đối giữa A và B phụ thuộc thời điểm mỗi nguồn phát, lịch thực thi và tốc độ xử lý. Nếu không có quy tắc đồng bộ riêng, không nên dựa vào một thứ tự xen kẽ cố định.

| Tiêu chí | `concat` | `merge` |
|---|---|---|
| Đăng ký nguồn | Đăng ký lần lượt; nguồn sau bắt đầu khi nguồn trước hoàn tất | Đăng ký các nguồn để chúng có thể phát đồng thời |
| Thứ tự giữa các nguồn | Giữ nguyên thứ tự nguồn | Xen kẽ theo thời điểm tín hiệu đến |
| Nguồn đang hoạt động | Thường chỉ một nguồn được tiêu thụ tại một thời điểm | Có thể có nhiều nguồn đang hoạt động cùng lúc |
| Khi nguồn đầu tiên chậm hoặc không kết thúc | Các nguồn sau phải chờ | Các nguồn khác vẫn có thể phát |
| Trường hợp phù hợp | Các bước phụ thuộc nhau hoặc cần thứ tự nguồn rõ ràng | Các nguồn độc lập và có thể tiêu thụ xen kẽ |

## Nối tiếp các nguồn bằng `Flux.concat`

`Flux.concat` nhận nhiều Publisher và tạo một Flux phát lần lượt các phần tử của từng nguồn. Nguồn thứ hai chỉ được đăng ký sau khi nguồn thứ nhất hoàn tất; nguồn thứ ba chỉ được đăng ký sau khi nguồn thứ hai hoàn tất, cứ tiếp tục như vậy.

```java
import reactor.core.publisher.Flux;

Flux<String> first = Flux.just("validate", "authorize");
Flux<String> second = Flux.just("charge", "send-receipt");

Flux<String> workflow = Flux.concat(first, second);

workflow.subscribe(System.out::println);
```

Kết quả:

```text
validate
authorize
charge
send-receipt
```

Thứ tự nguồn được giữ rõ ràng. Đây là cách phù hợp khi các bước nghiệp vụ phải chạy tuần tự, chẳng hạn chỉ bắt đầu thu tiền sau khi xác thực và cấp quyền hoàn tất. Trong ví dụ, `Flux.just` là nguồn đồng bộ và hữu hạn; với nguồn bất đồng bộ, quy tắc đăng ký tuần tự vẫn được áp dụng.

### Dùng `concatWith` để nối thêm một nguồn

Khi đã có một Flux và muốn nối thêm một Publisher ở cuối, có thể dùng `concatWith`:

```java
Flux<String> events = Flux.just("CREATED", "PAID")
    .concatWith(Flux.just("PACKED", "SHIPPED"));
```

`concatWith` thể hiện quan hệ nối tiếp ngay tại nơi khai báo pipeline. Nó hữu ích khi ghép một luồng chính với một nguồn bổ sung, chẳng hạn phát các bản ghi đã đọc từ cache trước rồi mới đọc tiếp từ nguồn dự phòng. Hãy đảm bảo việc chờ nguồn đầu tiên hoàn tất là đúng với yêu cầu nghiệp vụ.

### `concat` với `Mono` và `Flux`

`Mono<T>` cũng là Publisher, nên có thể nối với `Flux<T>` nếu kiểu phần tử tương thích:

```java
Mono<String> currentStatus = loadCurrentStatus();
Flux<String> statusHistory = loadStatusHistory();

Flux<String> allStatuses = Flux.concat(currentStatus, statusHistory);
```

Nếu `currentStatus` hoàn tất mà không phát phần tử, `concat` tiếp tục với `statusHistory`. Nếu Mono phát một giá trị, giá trị đó được phát trước lịch sử. Kiểu trả về là `Flux` vì tổng hợp có thể chứa nhiều phần tử.

## Điều gì xảy ra nếu một nguồn trong `concat` bị lỗi?

Theo mặc định, lỗi từ nguồn đang được tiêu thụ kết thúc toàn bộ chuỗi `concat`. Các nguồn phía sau chưa được đăng ký sẽ không được chạy:

```java
Flux<String> sequence = Flux.concat(
    Flux.just("step-1"),
    Flux.error(new IllegalStateException("step-2 failed")),
    Flux.just("step-3")
);
```

Subscriber nhận `step-1`, sau đó nhận `onError`. `step-3` không được đăng ký. Đây thường là hành vi phù hợp với workflow mà bước sau phụ thuộc vào kết quả thành công của bước trước.

Nếu muốn tiếp tục tiêu thụ các nguồn còn lại rồi mới chuyển lỗi xuống downstream, Reactor cung cấp biến thể `concatDelayError`:

```java
Flux<String> sequence = Flux.concatDelayError(
    Flux.just("step-1"),
    Flux.error(new IllegalStateException("step-2 failed")),
    Flux.just("step-3")
);
```

Với chính sách trì hoãn lỗi, các nguồn tiếp theo vẫn được tiêu thụ; lỗi được chuyển xuống sau khi các nguồn đã được xử lý. Chỉ dùng cách này nếu việc tiếp tục sau lỗi là an toàn. Ví dụ, nếu `step-2` là bước cấp quyền bắt buộc, chạy `step-3` sau khi bước đó thất bại có thể vi phạm nghiệp vụ.

## Trộn các nguồn bằng `Flux.merge`

`Flux.merge` kết hợp nhiều Publisher và chuyển tiếp phần tử khi chúng phát ra. Các nguồn được đăng ký để có thể hoạt động cùng lúc; phần tử từ nguồn nhanh có thể xuất hiện trước phần tử từ nguồn chậm:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<String> prices = Flux.interval(Duration.ofMillis(300))
    .map(tick -> "price-" + tick)
    .take(3);

Flux<String> alerts = Flux.interval(Duration.ofMillis(500))
    .map(tick -> "alert-" + tick)
    .take(3);

Flux<String> marketFeed = Flux.merge(prices, alerts);

marketFeed.subscribe(System.out::println);
```

Hai nguồn `interval` phát theo nhịp riêng. `merge` chuyển các tín hiệu đến từ cả hai nguồn vào một Flux. Kết quả có thể xen kẽ `price-0`, `alert-0`, `price-1` hoặc một thứ tự khác tùy thời điểm phát và lập lịch. Không nên kiểm thử ví dụ bất đồng bộ này bằng cách kỳ vọng một thứ tự xen kẽ cố định.

`merge` giữ thứ tự phát bên trong từng nguồn: nếu một Publisher phát `A1` rồi `A2`, downstream không nhận `A2` trước `A1` từ chính Publisher đó. Điều không được bảo đảm là thứ tự tương đối giữa các nguồn khác nhau.

### Dùng `mergeWith` để kết hợp thêm một Publisher

Tương tự `concatWith`, `mergeWith` kết hợp Flux hiện tại với một Publisher khác theo cách trộn:

```java
Flux<String> notifications = emailNotifications()
    .mergeWith(pushNotifications());
```

Nếu email và push notification phát độc lập, các phần tử được chuyển xuống khi đến. Nếu nghiệp vụ cần nhóm email trước rồi mới đến push notification, `mergeWith` không phù hợp; hãy dùng `concatWith` hoặc một quy tắc điều phối khác.

## `merge` không tự động tạo song song

`merge` cho phép nhiều Publisher đang hoạt động và trộn tín hiệu của chúng. Tuy nhiên, điều đó không đồng nghĩa mọi phép tính CPU trong các nguồn sẽ tự chạy trên nhiều thread. Nếu các nguồn đều đồng bộ và chạy trên thread gọi subscription, việc ghép chúng không tự tạo pool luồng hay tăng số lõi được sử dụng.

Muốn thực hiện công việc trên scheduler khác, hãy cấu hình nguồn hoặc ranh giới thực thi một cách tường minh:

```java
Flux<Result> combined = Flux.merge(
    loadCustomers().subscribeOn(Schedulers.boundedElastic()),
    loadInvoices().subscribeOn(Schedulers.boundedElastic())
);
```

Ví dụ giả định hai phương thức trả về Publisher có công việc blocking cần cô lập. `subscribeOn` chuyển việc bắt đầu subscription của từng nguồn sang scheduler phù hợp; `merge` kết hợp kết quả khi chúng đến. Với phép tính CPU-bound, cân nhắc `Schedulers.parallel()` và chia công việc thành các phần độc lập. Không nên chuyển scheduler một cách máy móc: mỗi ranh giới có chi phí và các nguồn bên ngoài vẫn có giới hạn kết nối hoặc concurrency riêng.

## Thứ tự đăng ký và tác động với nguồn nóng

Sự khác biệt giữa `concat` và `merge` đặc biệt quan trọng khi nguồn là hot Publisher hoặc đại diện cho callback đang phát liên tục.

Với `concat`, nguồn thứ hai chưa được đăng ký cho đến khi nguồn đầu tiên hoàn tất. Nếu nguồn thứ hai là hot và phát sự kiện trước thời điểm đăng ký, những sự kiện đó có thể bị bỏ lỡ. `concat` không tự lưu lại lịch sử của một hot source.

Với `merge`, các nguồn được đăng ký sớm để có thể phát xen kẽ. Điều này giảm khoảng thời gian chờ đăng ký đối với nguồn thứ hai, nhưng không bảo đảm nhận được sự kiện đã phát trước khi subscription thực sự được thiết lập. Nếu cần dữ liệu lịch sử, nguồn phải hỗ trợ replay hoặc lưu trữ sự kiện.

Ví dụ, nối một nguồn trạng thái liên tục sau một tác vụ tải dữ liệu ban đầu có thể bỏ lỡ thay đổi trạng thái xảy ra trong lúc tác vụ ban đầu chạy. Nếu không được phép mất sự kiện, hãy đăng ký nguồn sự kiện sớm, lưu tạm dữ liệu hoặc thiết kế một cơ chế đồng bộ giữa snapshot và event stream. Không thể giải quyết vấn đề này chỉ bằng cách đổi tên toán tử.

## Xử lý lỗi khi trộn nguồn

Theo mặc định, `merge` chuyển lỗi từ một nguồn xuống downstream và hủy các nguồn còn lại. Đây là hành vi fail-fast:

```java
Flux<String> combined = Flux.merge(
    Flux.just("A1", "A2"),
    Flux.error(new IllegalStateException("source B failed")),
    Flux.just("C1", "C2")
);
```

Khi nguồn lỗi được quan sát, Subscriber nhận `onError`; các subscription nguồn còn lại bị hủy. Một số phần tử từ nguồn khác có thể đã được phát trước khi lỗi được xử lý, vì các nguồn hoạt động cùng lúc. Không nên dựa vào thứ tự chính xác của những phần tử cạnh thời điểm lỗi.

Nếu muốn tiếp tục nhận dữ liệu từ các nguồn khác và trì hoãn lỗi đến khi chúng hoàn tất, có thể dùng `mergeDelayError`:

```java
Flux<String> combined = Flux.mergeDelayError(
    32,
    Flux.just("A1", "A2"),
    Flux.error(new IllegalStateException("source B failed")),
    Flux.just("C1", "C2")
);
```

Tham số đầu tiên là prefetch được dùng cho mỗi nguồn trong overload này. `mergeDelayError` tiếp tục tiêu thụ các nguồn còn lại rồi mới báo lỗi; nếu nhiều nguồn lỗi, Reactor có thể tổng hợp các lỗi. Chính sách trì hoãn hữu ích khi mỗi nguồn độc lập và kết quả từ các nguồn còn lại vẫn có giá trị. Với dữ liệu cần tính nhất quán toàn cục, hãy quyết định rõ liệu có thể trả một phần kết quả hay phải thất bại toàn bộ.

Có thể xử lý lỗi riêng cho từng nguồn trước khi ghép:

```java
Flux<String> combined = Flux.merge(
    loadPrimaryFeed()
        .onErrorResume(error -> fallbackPrimaryFeed()),
    loadSecondaryFeed()
        .onErrorResume(error -> Flux.empty())
);
```

Ở đây, lỗi của nguồn chính được chuyển sang nguồn dự phòng; lỗi của nguồn phụ được chuyển thành luồng rỗng. Khi xử lý lỗi trước `merge`, các chính sách được gắn với từng nguồn và không nhất thiết làm kết thúc toàn bộ luồng. Chỉ bỏ qua lỗi bằng `Flux.empty()` khi nghiệp vụ cho phép mất dữ liệu của nguồn đó.

## Backpressure khi kết hợp nhiều nguồn

`concat` và `merge` đều là toán tử Reactive Streams và phối hợp demand với upstream. Tuy nhiên, cách chúng tiêu thụ nguồn khác nhau:

- `concat` tập trung demand vào nguồn đang được tiêu thụ; nguồn sau chỉ tham gia khi nguồn trước hoàn tất.
- `merge` phải điều phối demand từ nhiều nguồn và có thể giữ phần tử đang chờ từ từng nguồn trong hàng đợi nội bộ. Prefetch và số nguồn đang hoạt động ảnh hưởng lượng dữ liệu có thể được giữ tạm thời.

Nếu có nhiều nguồn phát nhanh, `merge` có thể tạo áp lực lên downstream và sử dụng bộ nhớ cho các phần tử chờ. Hãy giới hạn số nguồn được ghép cùng lúc khi danh sách nguồn lớn, kiểm soát prefetch/concurrency ở các toán tử liên quan và chọn chính sách buffer phù hợp. Backpressure không thay thế việc giới hạn số kết nối hoặc giới hạn công việc đang chạy bên ngoài pipeline.

Với nguồn push-only không hỗ trợ demand, adapter cần buffer có giới hạn hoặc chính sách drop/latest/error rõ ràng. Nếu không, việc ghép nhiều nguồn chỉ chuyển chênh lệch tốc độ thành hàng đợi tăng dần.

## Khi ghép nhiều Publisher được tạo động

Trong ứng dụng, danh sách Publisher có thể được tạo từ một tập ID hoặc từ kết quả truy vấn. Khi cần nối tuần tự danh sách Publisher, có thể dùng `Flux.concat` trên một Publisher phát các Publisher con. Khi cần trộn các nguồn con, có thể dùng `Flux.merge`:

```java
Flux<Flux<Event>> feeds = accountIds()
    .map(this::eventsForAccount);

Flux<Event> sequential = Flux.concat(feeds);
Flux<Event> interleaved = Flux.merge(feeds);
```

`sequential` đăng ký từng feed sau khi feed trước hoàn tất. `interleaved` đăng ký các feed để chúng có thể phát xen kẽ. Với số lượng account lớn, không nên mặc định mở tất cả nguồn cùng lúc. Dùng overload có giới hạn concurrency hoặc `flatMap` với concurrency phù hợp khi cần giới hạn số Publisher con hoạt động đồng thời.

Nếu mỗi nguồn con phát vô hạn, `concat` sẽ không bao giờ chuyển sang nguồn tiếp theo. Đây có thể là hành vi đúng nếu nguồn đầu tiên là ưu tiên tuyệt đối, nhưng thường không phù hợp khi muốn theo dõi nhiều stream liên tục. `merge` phù hợp hơn cho nhiều nguồn dài hạn độc lập, với giới hạn tài nguyên được thiết kế rõ ràng.

## Kiểm thử `concat` và `merge` bằng `StepVerifier`

Với `concat`, thứ tự đầu ra là một phần của hợp đồng mong đợi, nên test có thể xác nhận chính xác chuỗi phần tử:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class CompositionTest {
    @Test
    void concatEmitsSourcesInSequence() {
        Flux<Integer> result = Flux.concat(
            Flux.just(1, 2),
            Flux.just(3, 4)
        );

        StepVerifier.create(result)
            .expectNext(1, 2, 3, 4)
            .verifyComplete();
    }
}
```

Với `merge` của các nguồn bất đồng bộ, không nên kỳ vọng một thứ tự xen kẽ cụ thể. Nếu chỉ quan tâm tất cả phần tử đều xuất hiện, hãy xác nhận số lượng và tập giá trị:

```java
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MergeCompositionTest {
    @Test
    void mergeEmitsValuesFromBothSources() {
        Flux<String> result = Flux.merge(
            Flux.just("A", "B"),
            Flux.just("C", "D")
        );

        StepVerifier.create(result)
            .recordWith(HashSet::new)
            .expectNextCount(4)
            .consumeRecordedWith(values ->
                assertEquals(Set.of("A", "B", "C", "D"), values)
            )
            .verifyComplete();
    }
}
```

Ví dụ dùng các nguồn đồng bộ để kiểm tra tập phần tử mà không phụ thuộc thứ tự xen kẽ. Với nguồn bất đồng bộ, có thể dùng `TestPublisher`, virtual time hoặc scheduler kiểm thử để điều khiển thời điểm phát. Hãy kiểm thử thêm các trường hợp một nguồn lỗi, một nguồn không bao giờ hoàn tất, downstream hủy và một nguồn phát nhanh hơn nguồn còn lại.

Nếu thứ tự nghiệp vụ giữa các nguồn thực sự quan trọng, hãy thể hiện thứ tự đó bằng `concat` hoặc bằng dữ liệu có sequence/timestamp và bước sắp xếp có chủ đích. Đừng viết test ép `merge` phải luôn cho ra một thứ tự mà hợp đồng không bảo đảm.

## Những lỗi thiết kế thường gặp

**Dùng `concat` cho nhiều nguồn không bao giờ hoàn tất.** Nguồn đầu tiên có thể chiếm luồng mãi mãi, khiến các nguồn sau không bao giờ được đăng ký. Với các nguồn sự kiện dài hạn độc lập, cân nhắc `merge`.

**Dùng `merge` khi cần thứ tự nghiệp vụ cố định.** Các nguồn có thể xen kẽ theo thời điểm phát. Nếu bước B chỉ được chạy sau khi bước A hoàn tất, hãy dùng `concat` hoặc một workflow tuần tự.

**Cho rằng `merge` tự tạo song song.** Nó kết hợp nhiều Publisher nhưng không tự chuyển mọi công việc sang thread riêng. Hãy điều khiển scheduler ở đúng nguồn hoặc ranh giới cần thiết.

**Cho rằng `merge` bảo đảm thứ tự giữa các nguồn.** Nó giữ thứ tự nội bộ của từng nguồn nhưng không quy định thứ tự xen kẽ giữa các nguồn độc lập.

**Quên nguồn hot khi dùng `concat`.** Nguồn phía sau chưa được đăng ký trong lúc nguồn trước đang chạy, nên sự kiện phát sớm có thể bị bỏ lỡ nếu không có replay hoặc lưu trữ.

**Trì hoãn lỗi mà không xem xét nghiệp vụ.** `concatDelayError` và `mergeDelayError` cho phép tiếp tục các nguồn khác, nhưng kết quả một phần có thể không hợp lệ nếu các bước phụ thuộc nhau.

**Ghép quá nhiều nguồn cùng lúc.** `merge` có thể tạo nhiều subscription hoạt động và nhiều hàng đợi nội bộ. Giới hạn concurrency, prefetch và tài nguyên nguồn theo tải thực tế.

## Tự kiểm tra

1. Với hai nguồn A và B, `concat(A, B)` đăng ký B vào thời điểm nào? Điều gì xảy ra nếu A không bao giờ hoàn tất?
2. Vì sao `merge(A, B)` có thể phát `B1` trước `A1` dù A được truyền vào trước?
3. `merge` giữ loại thứ tự nào và không bảo đảm loại thứ tự nào?
4. Nếu nguồn thứ hai là hot Publisher và chỉ được đăng ký sau khi nguồn thứ nhất hoàn tất, dữ liệu nào có thể bị bỏ lỡ?
5. So sánh hành vi lỗi mặc định của `concat` và `merge` với các biến thể trì hoãn lỗi.
6. Vì sao ghép nhiều Publisher không tự động làm phép tính CPU chạy song song?
7. Khi test `merge` với các nguồn bất đồng bộ, vì sao nên xác nhận tập giá trị hoặc số lượng thay vì một thứ tự xen kẽ cố định?

Khi phân biệt được nối tiếp với trộn, bạn có thể chọn `concat` để giữ thứ tự nguồn và điều kiện hoàn tất, hoặc chọn `merge` để tiêu thụ các nguồn độc lập theo thời điểm phát, đồng thời kiểm soát lỗi, demand và tài nguyên trong pipeline Reactor.
