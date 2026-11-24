# Kiểm thử

## Yêu cầu từng phần dữ liệu để xác minh áp lực ngược

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Backpressure cho phép Subscriber điều tiết lượng dữ liệu mà Publisher được phép phát. Để xác minh một pipeline tôn trọng cơ chế này, bài kiểm thử cần điều khiển demand theo từng đợt, quan sát những phần tử được phát và xác nhận nguồn không vượt quá lượng yêu cầu tại ranh giới đang kiểm tra.

Trong Reactor Test, `StepVerifier` cung cấp một cách tự nhiên để làm việc đó. Thay vì yêu cầu toàn bộ dữ liệu ngay khi subscribe, ta khởi tạo verifier với demand ban đầu bằng 0, sau đó gọi `thenRequest(n)` để yêu cầu từng phần. Ta có thể kiểm tra phần tử chỉ xuất hiện sau khi có demand, yêu cầu thêm dữ liệu ở bước kế tiếp, quan sát tín hiệu hoàn tất và hủy subscription khi không còn cần dữ liệu.

Một bài kiểm thử demand tốt cũng cần phân biệt **demand ở downstream** với **request được chuyển tiếp tới upstream**. Các toán tử như `publishOn`, `flatMap` hoặc `limitRate` có thể prefetch, chia nhỏ hoặc điều chỉnh request. Vì vậy, số phần tử mà Subscriber cuối yêu cầu không nhất thiết bằng chính xác số phần tử mà nguồn gốc nhận trong một lần gọi `request`. Ta phải kiểm tra đúng ranh giới và hợp đồng mà ứng dụng muốn bảo vệ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích demand và cách `request(n)` điều khiển tín hiệu `onNext`.
- Dùng `StepVerifier.create(publisher, 0)` để bắt đầu với demand bằng 0.
- Dùng `thenRequest(n)` để yêu cầu dữ liệu theo từng đợt.
- Xác minh không có phần tử được phát trước khi Subscriber yêu cầu.
- Quan sát request upstream bằng `doOnRequest` tại một ranh giới xác định.
- Phân biệt demand của Subscriber với prefetch và buffer của toán tử.
- Kiểm tra hoàn tất, lỗi và cancellation trong điều kiện demand từng phần.
- Dùng thời gian ảo khi kiểm thử nguồn bất đồng bộ có timer mà không làm mất kiểm soát demand.
- Tránh các assertion phụ thuộc chi tiết nội bộ không thuộc hợp đồng của pipeline.

## 1. Demand là hợp đồng giữa Subscriber và Publisher

Trong Reactive Streams, Subscriber điều khiển lượng phần tử có thể nhận bằng cách gọi `Subscription.request(n)`. Giá trị `n` phải lớn hơn 0. Demand là số phần tử còn được phép phát; mỗi tín hiệu `onNext` tiêu thụ một đơn vị demand.

Ví dụ, Subscriber yêu cầu hai phần tử:

~~~text
request(2)
onNext(A)
onNext(B)
~~~

Sau hai phần tử, demand đã dùng hết. Publisher cần chờ request tiếp theo trước khi phát thêm phần tử. Nếu Subscriber yêu cầu thêm một phần tử, Publisher có thể phát phần tử kế tiếp:

~~~text
request(1)
onNext(C)
~~~

Demand được cộng dồn. Nếu Subscriber gọi `request(2)` rồi gọi `request(3)` trước khi nhận dữ liệu, tổng demand có thể là năm phần tử. Gọi `request(Long.MAX_VALUE)` biểu thị demand không giới hạn trong thực tế; nhiều Subscriber và công cụ kiểm thử mặc định sử dụng cách này để tiêu thụ toàn bộ luồng.

Các tín hiệu kết thúc có quy tắc riêng:

- `onComplete` và `onError` không cần demand để được phát.
- `onNext` phải tuân thủ demand.
- Sau `cancel()`, Subscriber không còn yêu cầu phần tử tiếp theo.
- Publisher không được phát `onNext` vượt quá demand đã nhận.

Vì thế, kiểm thử áp lực ngược cần tập trung vào số lượng và thời điểm của `onNext`, đồng thời xác minh đúng hành vi terminal và cancellation.

## 2. Vì sao StepVerifier mặc định có thể che giấu lỗi backpressure?

Cách viết phổ biến:

~~~java
StepVerifier.create(Flux.range(1, 5))
    .expectNext(1, 2, 3, 4, 5)
    .verifyComplete();
~~~

`StepVerifier.create(publisher)` mặc định yêu cầu demand ban đầu không giới hạn. Test tiêu thụ tất cả phần tử mà không mô phỏng một Subscriber yêu cầu dữ liệu chậm hoặc theo từng phần.

Cách viết này hữu ích để xác minh giá trị, thứ tự và tín hiệu kết thúc. Nhưng nó không đủ để chứng minh pipeline hoạt động đúng khi downstream chỉ yêu cầu một số phần tử giới hạn.

Muốn kiểm tra backpressure, đặt demand ban đầu bằng 0:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
~~~

Trình tự kiểm thử:

1. Subscribe với demand bằng 0.
2. Xác nhận subscription đã được thiết lập.
3. Yêu cầu hai phần tử.
4. Xác nhận chỉ nhận phần tử thứ nhất và thứ hai.
5. Yêu cầu thêm một phần tử.
6. Xác nhận nhận phần tử thứ ba.
7. Hủy subscription khi không cần đọc phần còn lại.

Điểm quan trọng là `thenRequest(n)` phát sinh request tại đúng vị trí trong kịch bản. Ta có thể kiểm tra luồng theo từng bước thay vì để verifier yêu cầu toàn bộ dữ liệu từ đầu.

## 3. Dùng initialRequest bằng 0

Overload `StepVerifier.create(Publisher, long initialRequest)` cho phép chỉ định demand ban đầu. Giá trị 0 đặc biệt hữu ích khi muốn tự điều khiển mọi lần request:

~~~java
Flux<Integer> source = Flux.range(1, 6);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .thenRequest(1)
    .expectNext(4)
    .thenCancel()
    .verify();
~~~

Test mô phỏng một Subscriber tiêu thụ theo các đợt 1, 2 và 1 phần tử. Các phần tử 5 và 6 không được yêu cầu; `thenCancel()` kết thúc subscription trước khi chúng được phát.

Nếu muốn mô tả cấu hình rõ ràng hơn, có thể dùng `StepVerifierOptions`:

~~~java
StepVerifierOptions options =
    StepVerifierOptions.create()
        .initialRequest(0);

StepVerifier.create(source, options)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
~~~

Cả hai cách đều phục vụ cùng mục đích. Dùng overload đơn giản khi chỉ cần điều chỉnh demand ban đầu; dùng options khi test còn cần cấu hình khác như scenario name hoặc context.

## 4. Xác minh không có dữ liệu trước khi request

Với nguồn đồng bộ có khả năng tôn trọng demand như `Flux.range`, ta có thể xác nhận Subscriber chưa nhận `onNext` khi demand bằng 0:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(50))
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify();
~~~

`expectNoEvent` xác nhận không có tín hiệu nào trong khoảng thời gian chỉ định. Nó cũng xem subscription là một tín hiệu; do đó, cần gọi `expectSubscription()` trước khi dùng `expectNoEvent`. Nếu đặt `expectNoEvent` ngay sau khi bắt đầu verifier, test có thể thất bại vì `onSubscribe` đã xảy ra.

Trong ví dụ, sau khi subscription được xác nhận, verifier đợi 50 ms mà không yêu cầu phần tử nào. Khi gọi `thenRequest(1)`, phần tử đầu tiên mới được phát.

Khoảng đợi ở đây chỉ nhằm kiểm tra rằng nguồn không tự phát dữ liệu trong lúc không có demand. Với nguồn đồng bộ như `Flux.range`, có thể dùng khoảng ngắn; với nguồn bất đồng bộ, cần kiểm soát scheduler và timer để test không phụ thuộc thời gian thực ngoài ý muốn.

### Terminal signal không bị chặn bởi demand

Không nên hiểu rằng demand bằng 0 thì Publisher không được phát bất kỳ tín hiệu nào. Một nguồn rỗng có thể hoàn tất ngay mà không cần Subscriber yêu cầu phần tử:

~~~java
StepVerifier.create(Flux.<Integer>empty(), 0)
    .expectSubscription()
    .verifyComplete();
~~~

Tương tự, nguồn lỗi có thể phát `onError` mà không cần demand:

~~~java
StepVerifier.create(
        Flux.<Integer>error(new IllegalStateException("source failed")),
        0
    )
    .expectSubscription()
    .expectError(IllegalStateException.class)
    .verify();
~~~

Điều cần kiểm tra là Publisher không phát `onNext` vượt demand. Các tín hiệu `onComplete` và `onError` không tiêu thụ demand.

## 5. Quan sát request tại nguồn bằng doOnRequest

Ngoài việc kiểm tra phần tử đầu ra, có thể quan sát các request mà một Publisher nhận được bằng `doOnRequest`. Điều này hữu ích để xác minh request được chuyển tới nguồn tại một ranh giới cụ thể.

~~~java
AtomicLong requested = new AtomicLong();

Flux<Integer> source =
    Flux.range(1, 5)
        .doOnRequest(n -> requested.addAndGet(n));

StepVerifier.create(source, 0)
    .expectSubscription()
    .then(() -> assertThat(requested.get()).isZero())
    .thenRequest(2)
    .expectNext(1, 2)
    .then(() -> assertThat(requested.get()).isEqualTo(2))
    .thenRequest(1)
    .expectNext(3)
    .then(() -> assertThat(requested.get()).isEqualTo(3))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Trong pipeline đơn giản này, `doOnRequest` đặt trực tiếp trên nguồn nên có thể quan sát lượng request được chuyển tới `Flux.range`. Test xác nhận:

- Trước request đầu tiên, nguồn chưa nhận demand.
- Sau `thenRequest(2)`, tổng demand nguồn nhận là 2.
- Sau `thenRequest(1)`, tổng demand nguồn nhận là 3.
- Subscription được hủy sau khi đã kiểm tra ba phần tử.

Dùng `AtomicLong` vì callback request có thể được gọi từ thread khác trong các pipeline bất đồng bộ. Với một nguồn đồng bộ chỉ chạy trên test thread, biến cục bộ có thể đủ, nhưng atomic giúp ví dụ an toàn hơn khi thay đổi pipeline.

### Đặt doOnRequest ở đâu rất quan trọng

`doOnRequest` quan sát request tại vị trí nó được đặt. Nếu có toán tử ở giữa, lượng request nhìn thấy tại nguồn có thể khác lượng request từ Subscriber cuối.

Ví dụ:

~~~java
Flux<Integer> pipeline =
    Flux.range(1, 100)
        .doOnRequest(n -> log.info("Source received request: {}", n))
        .limitRate(8)
        .map(this::transform);
~~~

Subscriber cuối yêu cầu một số phần tử từ pipeline. `limitRate` có thể điều chỉnh cách request được chuyển upstream và yêu cầu theo các đợt. Vì vậy, log ở nguồn phản ánh request mà nguồn nhận từ `limitRate`, không nhất thiết là từng lời gọi `request(n)` trực tiếp của Subscriber cuối.

Đây là điều cần thiết để hiểu đúng backpressure: demand được điều phối qua từng toán tử, và mỗi toán tử có thể có chính sách prefetch hoặc buffer riêng.

## 6. Demand và prefetch là hai khái niệm khác nhau

Demand là số phần tử downstream cho phép nhận. Prefetch là lượng dữ liệu một toán tử có thể yêu cầu trước từ upstream để duy trì hoạt động hoặc làm đầy buffer nội bộ.

Ví dụ, `publishOn` có thể prefetch một số phần tử vào hàng đợi trước khi downstream xử lý hết. `flatMap` có thể subscribe nhiều Publisher con và yêu cầu dữ liệu từ mỗi inner. Các hành vi đó không vi phạm backpressure nếu toán tử vẫn quản lý demand và buffer theo hợp đồng của nó.

Một pipeline có thể có dạng:

~~~text
Subscriber cuối
    request(2)
       |
       v
publishOn / buffer
    có thể prefetch upstream
       |
       v
Nguồn
~~~

Do có prefetch, không nên đặt một assertion tổng quát rằng "downstream request 2 thì nguồn gốc chỉ nhận đúng request 2" cho mọi pipeline. Điều đó chỉ đúng ở một số ranh giới đơn giản không có toán tử thay đổi demand.

Khi kiểm thử, hãy phân chia mục tiêu:

- **Hợp đồng đầu ra:** Subscriber không nhận nhiều hơn số phần tử đã yêu cầu.
- **Hành vi nguồn:** nguồn nhận request theo cách toán tử trung gian được thiết kế.
- **Giới hạn bộ đệm:** toán tử không giữ dữ liệu vô hạn trong điều kiện tải đã kiểm tra.
- **Hủy:** cancellation được truyền tới nguồn hoặc Publisher con theo khả năng của chúng.

Không nên phụ thuộc vào một con số prefetch mặc định nếu đó là chi tiết triển khai có thể thay đổi theo phiên bản Reactor. Chỉ assert chính xác request upstream khi con số đó là một phần hợp đồng mà ứng dụng tự cấu hình và muốn bảo vệ.

## 7. Kiểm thử demand qua một pipeline có limitRate

`limitRate(highTide)` điều chỉnh request upstream thành các đợt có kích thước giới hạn. Nó hữu ích để tránh yêu cầu một lượng dữ liệu lớn cùng lúc từ nguồn.

Ví dụ:

~~~java
Flux<Integer> source =
    Flux.range(1, 20);

Flux<Integer> limited =
    source.limitRate(4);

StepVerifier.create(limited, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(2)
    .expectNext(3, 4)
    .thenCancel()
    .verify();
~~~

Test này xác minh hợp đồng quan sát được ở downstream: chỉ hai phần tử được yêu cầu và nhận trong mỗi đợt. Nó không khẳng định rằng nguồn chỉ nhận request 2 ở mỗi bước. `limitRate` có thể prefetch theo cấu hình high tide và low tide của nó.

Nếu cần kiểm tra cách `limitRate` điều tiết upstream, đặt `doOnRequest` ở trước hoặc sau toán tử theo đúng ranh giới muốn quan sát:

~~~java
AtomicLong upstreamDemand = new AtomicLong();

Flux<Integer> limited =
    Flux.range(1, 20)
        .doOnRequest(n -> upstreamDemand.addAndGet(n))
        .limitRate(4);
~~~

Khi viết assertion cho `upstreamDemand`, cần hiểu cấu hình và ngữ nghĩa của overload `limitRate` đang dùng. Một số chi tiết replenishment phụ thuộc high tide, low tide và phiên bản Reactor. Nếu mục tiêu của test chỉ là chứng minh Subscriber cuối nhận đúng lượng dữ liệu theo demand, assertion ở đầu ra thường ổn định hơn.

## 8. Kiểm thử demand với flatMap

`flatMap` có thể xử lý nhiều Publisher con đồng thời. Nó cũng quản lý demand và prefetch cho các inner. Vì vậy, test nên xác minh hai thuộc tính riêng: số phần tử downstream nhận được và giới hạn số inner đang hoạt động.

Ví dụ:

~~~java
Flux<String> results =
    Flux.range(1, 5)
        .flatMap(
            value -> Mono.just("item-" + value),
            2
        );

StepVerifier.create(results, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("item-1")
    .thenRequest(1)
    .expectNext("item-2")
    .thenCancel()
    .verify();
~~~

Test xác minh downstream chỉ nhận hai phần tử sau hai lần request. Tham số concurrency bằng 2 giới hạn số Publisher con được subscribe đồng thời; nó không có nghĩa Subscriber cuối đã yêu cầu hai phần tử và cũng không phải số thread.

Nếu muốn kiểm tra concurrency thực tế, dùng một bộ đếm tăng khi inner bắt đầu và giảm khi inner kết thúc. Sau đó xác minh giá trị lớn nhất không vượt giới hạn đã cấu hình. Đó là một kiểm thử khác với kiểm thử demand, dù cả hai cùng liên quan tới việc điều tiết công việc.

Không nên assert thứ tự đầu ra của `flatMap` nếu các inner bất đồng bộ có thể hoàn tất theo thứ tự khác. Nếu yêu cầu bảo toàn thứ tự, hãy chọn `flatMapSequential` hoặc `concatMap` và kiểm thử đúng hợp đồng thứ tự đó.

## 9. Kiểm thử cancellation sau khi tiêu thụ một phần dữ liệu

Một Subscriber có thể yêu cầu một vài phần tử rồi hủy vì không còn cần dữ liệu. Test cần xác minh cancellation được truyền tới nguồn và cleanup được gọi.

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source =
    Flux.range(1, 10)
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
~~~

Nguồn `Flux.range` chỉ cần phát hai phần tử theo demand. Khi verifier hủy subscription, callback `doOnCancel` được gọi.

Trong pipeline thực tế, nguồn có thể là listener, cursor hoặc HTTP response body. Hãy kiểm tra rằng cancellation dẫn tới cleanup thích hợp: listener được gỡ, cursor được đóng, connection được trả về pool hoặc request phụ thuộc được hủy nếu adapter hỗ trợ.

Cancellation không bảo đảm một tác dụng phụ đã gửi tới hệ thống từ xa được rollback. Nếu thao tác ghi đã được commit, cần idempotency hoặc đối soát thay vì giả định `cancel()` đảo ngược nó.

## 10. Kiểm thử nguồn bất đồng bộ với demand từng phần

Nguồn có timer hoặc phát dữ liệu bất đồng bộ có thể kiểm thử bằng `StepVerifier.withVirtualTime`. Khi dùng thời gian ảo, hãy tạo Publisher bên trong supplier để scheduler ảo được cài trước khi pipeline được lắp ráp.

Ví dụ:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1))
            .onBackpressureBuffer(10),
        StepVerifierOptions.create().initialRequest(0)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .thenRequest(2)
    .expectNext(0L, 1L)
    .thenAwait(Duration.ofSeconds(1))
    .thenRequest(1)
    .expectNext(2L)
    .thenCancel()
    .verify();
~~~

Test tiến thời gian ảo ba giây trong khi demand vẫn bằng 0. `Flux.interval` là nguồn theo nhịp và không tự chờ demand; nếu không có buffer, nó có thể phát lỗi overflow khi tick đến mà Subscriber chưa yêu cầu. `onBackpressureBuffer(10)` làm rõ chính sách của ví dụ: giữ tối đa 10 tick đang chờ. Sau ba giây, test yêu cầu hai phần tử và nhận 0, 1; sau tick tiếp theo, yêu cầu thêm một phần tử và nhận 2. Nếu buffer vượt sức chứa, pipeline sẽ lỗi theo chính sách overflow của toán tử. Test này minh họa demand từng phần cùng một buffer có giới hạn, không phải cách cấu hình mặc định cho mọi luồng sự kiện.

Với nguồn bất đồng bộ, thời gian và demand là hai trục độc lập:

- `thenAwait` điều khiển thời gian test tiến lên.
- `thenRequest(n)` điều khiển lượng phần tử Subscriber cho phép nhận.
- `expectNext` xác minh các phần tử được phát.
- `thenCancel` kết thúc subscription.

Không dùng `Thread.sleep` trong test backpressure. Thời gian ảo giúp test chạy nhanh và tránh phụ thuộc tốc độ máy, nhưng nó không thay thế kiểm thử tích hợp cho transport hoặc driver thật.

## 11. Kiểm tra terminal signal khi demand bằng 0

Một số test cần xác minh nguồn hoàn tất hoặc lỗi mà không phát phần tử. Các terminal signal không cần demand, nên có thể kiểm tra với initial request bằng 0:

~~~java
StepVerifier.create(Mono.<String>empty(), 0)
    .expectSubscription()
    .verifyComplete();
~~~

Với lỗi:

~~~java
StepVerifier.create(
        Mono.<String>error(new IllegalArgumentException("invalid")),
        0
    )
    .expectSubscription()
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Đây là kiểm thử quan trọng khi một pipeline có thể hoàn tất rỗng hoặc thất bại trước khi phát dữ liệu. Nếu test chỉ chờ `onNext` mới kết thúc, nó có thể bị treo dù Publisher đã phát terminal signal hợp lệ.

Với một nguồn có cả dữ liệu và terminal signal, terminal chỉ có thể tới sau khi các phần tử đã được phát theo demand hoặc khi nguồn lỗi. Không được dùng initial request bằng 0 để suy luận rằng Publisher phải chờ request mới được phát lỗi.

## 12. Kiểm tra vi phạm demand và nguồn không tuân thủ

Các nguồn tuân thủ Reactive Streams không phát `onNext` vượt demand. Tuy nhiên, một adapter tự viết hoặc thư viện callback có thể phát nhanh hơn khả năng tiêu thụ.

Khi tích hợp nguồn ngoài, cần xác định:

- Nguồn có hỗ trợ pull/demand hay chỉ callback push?
- Adapter buffer ở đâu và có giới hạn không?
- Khi buffer đầy, nguồn có thể pause, drop, fail hoặc phải lưu bền vững?
- Callback có thể đến sau cancellation không?
- Có thể nhận hai callback đồng thời không?
- Tài nguyên của phần tử bị loại bỏ có cần cleanup không?

Với nguồn callback push, `Flux.create` cung cấp các overflow strategy như `BUFFER`, `DROP`, `LATEST` và `ERROR`. Chọn chiến lược theo ý nghĩa dữ liệu:

| Strategy | Hành vi khi nguồn phát nhanh hơn demand | Phù hợp khi |
|---|---|---|
| `BUFFER` | Giữ phần tử chờ demand | Dữ liệu cần giữ, nhưng phải kiểm soát dung lượng và nguy cơ bộ nhớ |
| `DROP` | Bỏ phần tử mới khi không thể chuyển tiếp | Một số cập nhật có thể bỏ qua |
| `LATEST` | Giữ giá trị mới nhất thay cho giá trị cũ đang chờ | Trạng thái mới nhất quan trọng hơn mọi mẫu trung gian |
| `ERROR` | Phát lỗi khi vượt khả năng tiêu thụ | Muốn phát hiện producer vượt hợp đồng |

Ví dụ nguồn trạng thái chỉ cần giá trị mới nhất:

~~~java
Flux<Reading> readings =
    Flux.create(sink -> {
        SensorListener listener = sink::next;
        sink.onDispose(() -> sensor.removeListener(listener));
        sensor.addListener(listener);
    }, FluxSink.OverflowStrategy.LATEST);
~~~

Test demand từng phần có thể xác minh downstream chỉ nhận dữ liệu khi request, nhưng cũng cần test riêng chính sách overflow. Không thể chỉ dựa vào `StepVerifier` để chứng minh buffer của adapter có giới hạn nếu test không tạo tải vượt khả năng tiêu thụ.

### Test nguồn không tuân thủ bằng công cụ chuyên dụng

Reactor Test có `TestPublisher` để tạo nguồn có thể điều khiển trong test. Nó hỗ trợ các chế độ tuân thủ và không tuân thủ Reactive Streams, giúp mô phỏng nguồn phát sai hợp đồng hoặc callback đến muộn. Chỉ nên dùng chế độ không tuân thủ khi mục tiêu test là xác minh adapter xử lý được một nguồn ngoài không đáng tin cậy; không dùng nó làm ví dụ cho cách xây dựng Publisher thông thường.

Khi test nguồn không tuân thủ, xác định rõ hành vi mong muốn của adapter: chuyển lỗi, drop, buffer có giới hạn, giải phóng tài nguyên hoặc ghi nhận callback đến muộn. Tránh tạo một test chỉ xác minh Reactor ném exception mà không kiểm tra chính sách của ứng dụng.

## 13. Giới hạn thời gian và tránh test bị treo

Một test backpressure có thể treo nếu verifier chờ một phần tử mà chưa phát request đủ, hoặc nguồn không bao giờ hoàn tất. Nên đặt timeout cho việc verify:

~~~java
StepVerifier.create(Flux.range(1, 10), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Timeout ở đây là giới hạn thời gian chạy test, không phải toán tử `timeout` của Publisher. Nếu verifier không nhận được tín hiệu mong đợi, test kết thúc thất bại thay vì giữ tiến trình vô thời hạn.

Với test dùng `withVirtualTime`, dùng `thenAwait` để tiến thời gian ảo thay vì đặt thời gian chờ thật quá dài. Tuy nhiên, timeout của `verify(Duration)` vẫn hữu ích như một giới hạn an toàn cho test runner.

Đừng đặt timeout quá ngắn đến mức máy CI tải cao làm test thất bại ngẫu nhiên. Chọn giới hạn đủ rộng cho overhead test, còn các mốc thời gian nghiệp vụ nên được điều khiển bằng virtual time.

## 14. Những nhầm lẫn thường gặp

- **StepVerifier mặc định kiểm tra backpressure:** demand mặc định thường không giới hạn; dùng initial request bằng 0 để điều khiển từng đợt.
- **request(2) nghĩa là Publisher phải phát đúng hai phần tử ngay lập tức:** Publisher có thể chưa có dữ liệu; request chỉ cho phép phát tối đa hai phần tử.
- **Demand bằng 0 chặn cả onComplete và onError:** terminal signal không cần demand; chỉ `onNext` bị giới hạn bởi demand.
- **Mỗi thenRequest tương ứng chính xác một request ở nguồn gốc:** toán tử trung gian có thể prefetch hoặc điều chỉnh request.
- **Concurrency là demand:** concurrency giới hạn số Publisher con hoạt động; demand giới hạn số phần tử downstream được phép nhận.
- **limitRate giới hạn mọi buffer của hệ thống:** nó điều chỉnh request upstream trong một ranh giới; các queue khác vẫn cần giới hạn riêng.
- **expectNoEvent có thể đặt trước expectSubscription:** subscription cũng là một tín hiệu; hãy xác nhận subscription trước khi kiểm tra khoảng không có sự kiện.
- **thenAwait tự tạo demand:** thời gian trôi qua không đồng nghĩa Subscriber đã yêu cầu dữ liệu; dùng `thenRequest` riêng.
- **Hủy sau vài phần tử làm rollback công việc:** cancellation yêu cầu dừng luồng; tác dụng phụ đã commit không tự được hoàn tác.
- **Một test demand chứng minh adapter callback có buffer hữu hạn:** cần tạo tải vượt tốc độ tiêu thụ và kiểm tra overflow policy, dung lượng buffer hoặc hành vi từ chối.
- **Có thể assert mọi con số prefetch mặc định:** chi tiết nội bộ có thể thay đổi theo toán tử và phiên bản; chỉ kiểm tra chính xác khi đó là cấu hình/hợp đồng của ứng dụng.

## 15. Bài tập vận dụng

Một API trả về `Flux<Reading>` gồm các mẫu cảm biến. Client chỉ xử lý được từng nhóm nhỏ và có thể hủy stream sau khi nhận đủ dữ liệu.

Hãy thiết kế bộ kiểm thử:

1. Tạo nguồn gồm 10 phần tử bằng `Flux.range` hoặc nguồn giả.
2. Khởi tạo `StepVerifier` với initial request bằng 0.
3. Xác minh không có `onNext` trước request đầu tiên.
4. Yêu cầu hai phần tử và xác minh chỉ nhận hai mẫu đầu.
5. Yêu cầu thêm ba phần tử và xác minh đúng nhóm tiếp theo.
6. Quan sát request ở nguồn bằng `doOnRequest`; giải thích vì sao vị trí đặt callback ảnh hưởng số liệu.
7. Hủy subscription sau năm phần tử và xác minh cleanup được gọi.
8. Thêm một toán tử có prefetch như `publishOn` hoặc `limitRate`; xác minh hợp đồng downstream mà không giả định request upstream phải bằng demand cuối.
9. Nếu nguồn cảm biến phát callback nhanh hơn Subscriber, chọn overflow strategy nào và vì sao?
10. Viết thêm test cho nguồn hoàn tất rỗng và nguồn phát lỗi khi demand bằng 0.

**Gợi ý:** dùng `StepVerifier.create(source, 0)`, `expectSubscription()`, `thenRequest(n)`, `expectNext(...)`, `thenCancel()` và `verify(Duration)`. Dùng `AtomicLong` trong `doOnRequest` để quan sát request ở một ranh giới đơn giản. Khi thêm toán tử prefetch, kiểm tra số phần tử downstream thực nhận và đo request upstream như một hành vi riêng. Với nguồn callback, chọn `LATEST` nếu chỉ cần trạng thái mới nhất; chọn buffer có giới hạn hoặc lưu bền vững nếu không được phép mất sự kiện.

## Kết luận

Để xác minh backpressure, hãy điều khiển demand thay vì để `StepVerifier` yêu cầu toàn bộ dữ liệu ngay khi subscribe. Khởi tạo với demand bằng 0, yêu cầu từng phần bằng `thenRequest(n)`, xác nhận các phần tử được phát đúng giới hạn rồi kiểm tra cancellation, complete hoặc error. Dùng `doOnRequest` để quan sát request tại một ranh giới cụ thể, nhưng nhớ rằng các toán tử có thể prefetch và điều chỉnh demand upstream. Kiểm thử cần tách hợp đồng đầu ra khỏi chi tiết buffer nội bộ, đồng thời xác minh chính sách overflow của nguồn callback khi producer nhanh hơn consumer. Những test này giúp phát hiện pipeline phát vượt demand, giữ dữ liệu không kiểm soát hoặc không dừng công việc khi Subscriber không còn cần dữ liệu.
