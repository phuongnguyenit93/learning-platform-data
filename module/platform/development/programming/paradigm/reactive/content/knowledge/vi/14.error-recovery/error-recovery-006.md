# Thử lại nguồn và phân biệt retry với repeat

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` mô tả các nguồn dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Một subscription có thể kết thúc bình thường bằng `onComplete` hoặc thất bại bằng `onError`. Reactor cung cấp hai nhóm toán tử có vẻ giống nhau vì đều có thể đăng ký lại nguồn: **`retry` đăng ký lại khi nguồn phát lỗi**, còn **`repeat` đăng ký lại khi nguồn hoàn tất bình thường**.

Chọn nhầm hai toán tử này có thể khiến một tác vụ chạy lặp vô hạn, một lỗi không được thử lại hoặc một thao tác nghiệp vụ bị thực hiện nhiều lần. Cần hiểu tín hiệu nào kích hoạt đăng ký lại, số lần chạy thực tế, cách nguồn được tạo lại và ảnh hưởng đến dữ liệu đã phát trước khi dùng chúng trong pipeline.

## 1. Vòng đời subscription quyết định khi nào đăng ký lại

Một Publisher có thể phát không hoặc nhiều phần tử `onNext`, sau đó kết thúc bằng một trong hai tín hiệu đầu cuối:

- `onComplete`: nguồn hoàn tất bình thường.
- `onError`: nguồn kết thúc do lỗi.

`retry` và `repeat` phản ứng với hai tín hiệu khác nhau:

```text
                         subscribe
                             |
                             v
                        Publisher
                             |
                    onNext (0..n lần)
                             |
                  +----------+----------+
                  |                     |
              onError               onComplete
                  |                     |
                retry                 repeat
                  |                     |
          subscribe lại          subscribe lại
```

`retry` chỉ đăng ký lại khi upstream phát `onError`. Nếu nguồn hoàn tất thành công, `retry` chuyển tín hiệu hoàn tất xuống downstream và dừng. `repeat` chỉ đăng ký lại khi upstream phát `onComplete`. Nếu nguồn phát lỗi, `repeat` chuyển lỗi xuống downstream và dừng; nó không tự biến lỗi thành một lần chạy mới.

## 2. Retry: đăng ký lại sau lỗi

`retry` phù hợp khi lỗi có khả năng tạm thời, chẳng hạn kết nối mạng chập chờn hoặc dịch vụ từ xa trả lỗi có thể phục hồi. Khi nhận lỗi, Reactor hủy subscription hiện tại và đăng ký lại upstream theo chính sách retry.

```java
Mono<String> response = Mono.fromCallable(() -> remoteClient.fetch())
    .retry(2);
```

`retry(2)` cho phép tối đa hai lần thử lại sau lần đăng ký ban đầu. Nếu lần đầu và lần thử lại thứ nhất thất bại, Reactor thử thêm lần thứ hai. Tổng số lần thực thi tối đa là ba. Nếu cả ba lần đều lỗi, lỗi cuối cùng được chuyển xuống downstream.

| Cấu hình | Số lần đăng ký tối đa |
|---|---:|
| `retry(0)` | 1 lần ban đầu, không thử lại |
| `retry(1)` | 1 lần ban đầu + 1 lần thử lại = 2 |
| `retry(2)` | 1 lần ban đầu + 2 lần thử lại = 3 |
| `retry(3)` | 1 lần ban đầu + 3 lần thử lại = 4 |

Không tham số, `retry()` tiếp tục đăng ký lại vô hạn khi nguồn liên tục lỗi. Cách này thường không phù hợp với request nghiệp vụ vì subscription có thể không bao giờ kết thúc và giữ tài nguyên lâu dài.

## 3. Nguồn cần được tạo lại ở mỗi lần retry

Retry hoạt động bằng cách subscribe lại Publisher upstream. Để mỗi lần đăng ký thực sự gọi lại thao tác, hãy dùng nguồn lazy như `Mono.defer` hoặc `Mono.fromCallable`:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> request = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IOException("Temporary network failure"));
    }
    return Mono.just("OK");
}).retry(2);
```

`Mono.defer` gọi factory mỗi lần có subscription. Trong ví dụ, hai lần đầu phát lỗi; lần thứ ba trả về `OK`. `retry(2)` đăng ký lại đủ hai lần và downstream nhận một kết quả thành công.

Nếu tính toán giá trị hoặc gọi hàm ngay khi lắp ráp bằng `Mono.just`, retry có thể chỉ phát lại giá trị đã tạo sẵn thay vì thực hiện lại công việc:

```java
// fetch() được gọi ngay khi lắp ráp; Mono giữ lại kết quả đó.
Mono<Response> eager = Mono.just(remoteClient.fetch())
    .retry(2);
```

Trong trường hợp này, `retry` vẫn subscribe lại Publisher, nhưng lời gọi `fetch()` đã xảy ra trước đó. Để trì hoãn lời gọi đến subscription, dùng `fromCallable` hoặc `defer`:

```java
Mono<Response> lazy = Mono.fromCallable(remoteClient::fetch)
    .retry(2);
```

Đăng ký lại cũng không có nghĩa mọi loại nguồn đều phát lại cùng dữ liệu. Với nguồn lạnh, mỗi subscription thường tạo một lần đọc hoặc tính toán mới. Với nguồn nóng, dữ liệu đã phát trước khi subscription mới bắt đầu có thể không được phát lại, trừ khi nguồn có cơ chế replay hoặc lưu trữ riêng.

## 4. Repeat: đăng ký lại sau khi hoàn tất

`repeat` dùng khi muốn thực hiện lại một Publisher sau mỗi lần hoàn tất bình thường. Ví dụ, một tác vụ kiểm tra trạng thái trả về kết quả rồi cần được chạy lại một số lần:

```java
AtomicInteger runs = new AtomicInteger();

Mono<Integer> pollOnce = Mono.fromSupplier(runs::incrementAndGet);

Flux<Integer> polls = pollOnce.repeat(2);
```

`repeat(2)` đăng ký lại sau hai lần hoàn tất, ngoài lần chạy đầu tiên. Vì vậy, `polls` phát `1`, `2`, `3` rồi hoàn tất. Số `2` là số lần lặp thêm, không phải tổng số lần chạy.

Với `Flux`, các phần tử từ mỗi lần đăng ký được nối tiếp theo thứ tự subscription:

```java
Flux<Integer> cycles = Flux.just(1, 2)
    .repeat(1);
```

Kết quả là `1, 2, 1, 2`. Nguồn hoàn tất sau hai phần tử, nên `repeat(1)` đăng ký lại một lần.

`repeat()` không giới hạn số lần lặp. Nếu nguồn hoàn tất rất nhanh hoặc rỗng, repeat vô hạn có thể tạo vòng lặp đồng bộ liên tục và tiêu thụ CPU. Với polling hoặc tác vụ định kỳ, nên có khoảng nghỉ hoặc điều kiện dừng rõ ràng.

## 5. So sánh retry và repeat

| Đặc điểm | `retry` | `repeat` |
|---|---|---|
| Tín hiệu kích hoạt | `onError` | `onComplete` |
| Mục tiêu | Thử lại sau thất bại | Chạy lại sau khi hoàn tất thành công |
| Nguồn phát lỗi | Đăng ký lại theo giới hạn retry | Chuyển lỗi xuống downstream |
| Nguồn hoàn tất | Hoàn tất downstream | Đăng ký lại theo giới hạn repeat |
| Tham số `n` | Số lần thử lại thêm | Số lần lặp thêm |
| Rủi ro khi không giới hạn | Lặp vô hạn khi liên tục lỗi | Lặp vô hạn khi liên tục hoàn tất |

Một cách kiểm tra nhanh là hỏi: “Tôi muốn chạy lại vì lần trước thất bại, hay vì lần trước đã hoàn tất và tôi muốn bắt đầu chu kỳ mới?” Nếu thất bại, dùng retry. Nếu hoàn tất và cần chu kỳ tiếp theo, dùng repeat.

## 6. Chọn lỗi nào được phép retry

Không phải lỗi nào cũng có thể phục hồi bằng cách thực hiện lại cùng một thao tác. Lỗi xác thực, dữ liệu đầu vào không hợp lệ hoặc lỗi nghiệp vụ thường không biến mất khi thử lại. Ngược lại, lỗi kết nối tạm thời, timeout hoặc một số lỗi dịch vụ có thể phục hồi sau một khoảng thời gian.

Với Reactor, `retryWhen` kết hợp `Retry` cho phép đặt chính sách cụ thể:

```java
Mono<Profile> profile = Mono.defer(() -> profileClient.load(userId))
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isTransient)
            .doBeforeRetry(signal ->
                log.warn(
                    "Retry attempt {} after failure",
                    signal.totalRetries() + 1,
                    signal.failure()
                )
            )
    );
```

Chính sách trên có tối đa ba lần thử lại, bắt đầu với khoảng chờ 200 ms, tăng dần theo backoff và giới hạn tối đa hai giây. `jitter` thêm độ ngẫu nhiên vào khoảng chờ để nhiều client không đồng loạt retry tại cùng một thời điểm. `filter` chỉ cho phép thử lại với loại lỗi mà `isTransient` xác định là tạm thời.

Backoff giúp tránh tạo một đợt request dồn dập khi dịch vụ đang gặp sự cố. Jitter giảm nguy cơ nhiều client đồng bộ hóa các lần thử lại (thundering herd). Cần đặt giới hạn retry và tổng thời gian chờ phù hợp với timeout của request cấp cao hơn.

Nếu lỗi không thỏa điều kiện `filter`, chính sách retry không tiếp tục thử lại lỗi đó; lỗi được chuyển xuống downstream. Khi hết số lần thử, Reactor cũng kết thúc bằng lỗi. Có thể tùy chỉnh cách phát lỗi khi cạn retry bằng API của `Retry`, nhưng cần giữ thông tin nguyên nhân để chẩn đoán.

## 7. Retry có thể phát lại các phần tử đã phát trước lỗi

Với `Mono`, thường chỉ có một giá trị nên vấn đề phát lại prefix ít rõ ràng. Với `Flux`, nguồn có thể phát nhiều phần tử rồi mới lỗi. Khi retry, Reactor subscribe lại upstream; các phần tử đầu luồng có thể được phát lại.

```java
Flux<Integer> retried = Flux.just(1, 2)
    .concatWith(Mono.<Integer>error(new IOException("connection lost")))
    .retry(1);
```

Mỗi lần đăng ký vào nguồn lạnh này phát `1`, `2`, rồi lỗi. `retry(1)` đăng ký lại một lần, nên downstream thấy chuỗi `1, 2, 1, 2` rồi nhận lỗi. Hai phần tử đầu đã được downstream xử lý ở lần đầu vẫn xuất hiện lần nữa.

Đây là hành vi quan trọng khi xử lý luồng sự kiện, ghi dữ liệu hoặc thực hiện tác dụng phụ. Nếu downstream đã ghi một bản ghi trước khi nguồn lỗi, retry toàn pipeline có thể khiến bản ghi đó được ghi lần thứ hai. Hãy xem xét:

- Đặt retry gần thao tác có thể thử lại an toàn thay vì bao trùm cả pipeline đã thực hiện nhiều tác dụng phụ.
- Dùng khóa idempotency hoặc cơ chế deduplication ở ranh giới nghiệp vụ khi một request có thể được gửi lại.
- Lưu checkpoint hoặc offset nếu đọc lại luồng sự kiện từ một vị trí xác định.
- Kiểm tra xem thao tác đã thành công ở phía server nhưng response bị mất hay chưa; timeout không chứng minh thao tác chưa được thực hiện.

Retry là cơ chế đăng ký lại, không tự bảo đảm exactly-once. Tính idempotent và khả năng khử trùng lặp phải được thiết kế ở tầng nghiệp vụ hoặc lưu trữ.

## 8. Thứ tự retry, repeat và phục hồi lỗi

Vị trí đặt toán tử quyết định phạm vi được đăng ký lại. Ví dụ:

```java
Mono<Result> result = callRemote()
    .retry(2)
    .onErrorResume(error -> loadFallback());
```

Pipeline thử lại `callRemote` tối đa hai lần. Nếu vẫn lỗi, `onErrorResume` chuyển sang Publisher dự phòng. Đây thường là ý định: thử phục hồi nguồn chính trước, sau đó mới fallback.

Nếu đổi thứ tự:

```java
Mono<Result> result = callRemote()
    .onErrorResume(error -> loadFallback())
    .retry(2);
```

Lỗi từ `callRemote` được chuyển thành kết quả từ `loadFallback` nếu fallback thành công. Khi đó, `retry` phía sau không thấy lỗi ban đầu để thử lại nguồn chính. Nó chỉ retry nếu Publisher fallback hoặc phần pipeline sau đó phát lỗi.

Có thể kết hợp retry và repeat, nhưng cần xác định tín hiệu nào được xử lý ở từng tầng. Ví dụ:

```java
Mono<Status> onePoll = Mono.defer(statusClient::readStatus)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));

Flux<Status> polling = onePoll.repeat(4);
```

Mỗi chu kỳ polling sẽ thử lại lỗi tạm thời tối đa hai lần. Khi một chu kỳ hoàn tất thành công, `repeat(4)` tạo thêm bốn chu kỳ. Nếu một chu kỳ vẫn lỗi sau retry, lỗi kết thúc toàn bộ pipeline và `repeat` không được kích hoạt cho lỗi đó.

## 9. Repeat có khoảng nghỉ và điều kiện dừng

Polling thường cần chờ giữa các lần chạy để tránh gọi dịch vụ liên tục. Có thể dùng `repeatWhen` để quyết định thời điểm lặp dựa trên tín hiệu hoàn tất:

```java
Flux<Status> polling = Mono.defer(statusClient::readStatus)
    .repeatWhen(completions ->
        completions
            .delayElements(Duration.ofSeconds(1))
            .take(4)
    );
```

Ví dụ này chờ một giây sau mỗi lần hoàn tất rồi phát tín hiệu cho phép lặp, tối đa bốn lần lặp thêm. Nguồn ban đầu chạy một lần, nên có tối đa năm chu kỳ nếu tất cả đều hoàn tất bình thường.

Nếu cần dừng khi đạt trạng thái nghiệp vụ, có thể dùng toán tử điều kiện như `takeUntil` hoặc kiểm tra trạng thái trong từng chu kỳ:

```java
Flux<Status> untilReady = Mono.defer(statusClient::readStatus)
    .repeatWhen(completions ->
        completions.delayElements(Duration.ofSeconds(1))
    )
    .takeUntil(Status::isReady);
```

Ở đây, luồng lặp cho đến khi downstream nhận trạng thái `isReady() == true`. Cần thêm timeout tổng thể nếu trạng thái có thể không bao giờ đạt, để subscription không tồn tại vô hạn.

## 10. Kiểm thử số lần đăng ký và tín hiệu kích hoạt

Không nên chỉ kiểm tra giá trị cuối. Hãy xác minh số lần nguồn được đăng ký để bảo đảm retry hoặc repeat chạy đúng số lần dự kiến.

### Kiểm thử retry

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> retried = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.<String>error(new IOException("temporary"));
    }
    return Mono.just("OK");
}).retry(2);

StepVerifier.create(retried)
    .expectNext("OK")
    .verifyComplete();

assertEquals(3, attempts.get());
```

Hai lần đăng ký đầu lỗi, lần thứ ba thành công. Assertion xác nhận tổng số lần chạy là ba, tương ứng một lần ban đầu và hai lần thử lại.

### Kiểm thử repeat

```java
AtomicInteger runs = new AtomicInteger();

Mono<Integer> repeated = Mono.fromSupplier(runs::incrementAndGet)
    .repeat(2);

StepVerifier.create(repeated)
    .expectNext(1, 2, 3)
    .verifyComplete();

assertEquals(3, runs.get());
```

Nguồn hoàn tất thành công sau mỗi giá trị, vì vậy `repeat(2)` tạo hai lần đăng ký thêm. Tổng số lần chạy là ba.

### Xác nhận repeat không xử lý lỗi

```java
AtomicInteger runs = new AtomicInteger();

Mono<Integer> failing = Mono.defer(() -> {
    runs.incrementAndGet();
    return Mono.<Integer>error(new IllegalStateException("failed"));
}).repeat(3);

StepVerifier.create(failing)
    .expectErrorMessage("failed")
    .verify();

assertEquals(1, runs.get());
```

Nguồn phát `onError` ngay lần đầu, nên `repeat(3)` không đăng ký lại. Đây là cách kiểm tra rõ sự khác biệt giữa tín hiệu lỗi và tín hiệu hoàn tất.

Với `Retry.backoff` hoặc `repeatWhen` có delay, hãy dùng `StepVerifier.withVirtualTime` để kiểm tra thời điểm thử lại mà không chờ đồng hồ thật. Tạo pipeline bên trong supplier truyền cho `withVirtualTime` để các toán tử delay sử dụng virtual scheduler.

## 11. Những lỗi thường gặp khi dùng retry và repeat

| Cách dùng sai | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `repeat` để xử lý lỗi | Nguồn lỗi không được đăng ký lại | Dùng `retry` hoặc `retryWhen` |
| Dùng `retry` cho polling sau khi hoàn tất | Nguồn hoàn tất bình thường nên không chạy lại | Dùng `repeat` hoặc `repeatWhen` |
| Dùng `retry()` không giới hạn cho request | Request có thể giữ subscription vô hạn | Đặt số lần thử, backoff và timeout |
| Retry mọi loại lỗi | Lặp lại cả lỗi nghiệp vụ không thể phục hồi | Lọc lỗi bằng `Retry.filter` |
| Retry một thao tác ghi không idempotent | Có thể tạo bản ghi hoặc giao dịch trùng | Dùng idempotency key, deduplication hoặc thiết kế lại ranh giới retry |
| Dùng `Mono.just(call())` rồi mong retry gọi lại `call()` | Lời gọi đã chạy ở assembly, giá trị chỉ được phát lại | Dùng `fromCallable` hoặc `defer` |
| Bỏ qua phần tử đã phát trước lỗi trong `Flux` | Downstream có thể nhận trùng prefix sau retry | Thiết kế checkpoint, deduplication hoặc đặt retry đúng phạm vi |
| Repeat nguồn hoàn tất tức thì vô hạn | Có thể tạo vòng lặp nóng và tiêu thụ CPU | Thêm delay, điều kiện dừng hoặc giới hạn số lần lặp |

## 12. Checklist trước khi đăng ký lại nguồn

Trước khi thêm `retry` hoặc `repeat`, hãy trả lời:

1. Nguồn được đăng ký lại vì `onError` hay `onComplete`?
2. Số lần chạy tối đa gồm lần đầu và bao nhiêu lần đăng ký thêm?
3. Publisher có lazy và tạo lại thao tác ở mỗi subscription không?
4. Loại lỗi nào có thể phục hồi, loại lỗi nào phải chuyển xuống downstream ngay?
5. Có cần backoff, jitter, timeout hoặc giới hạn thời gian tổng thể không?
6. Nguồn có phát dữ liệu trước lỗi khiến retry phát lại phần tử cũ không?
7. Tác dụng phụ có idempotent hoặc có khóa chống trùng không?
8. Nếu dùng repeat, điều kiện dừng và khoảng nghỉ giữa các chu kỳ là gì?
9. Kiểm thử có xác nhận số lần đăng ký, tín hiệu kết thúc và hành vi cancellation không?

`retry` phục hồi từ lỗi bằng cách đăng ký lại upstream; `repeat` bắt đầu chu kỳ mới sau khi upstream hoàn tất bình thường. Khi kết hợp với nguồn lazy, giới hạn số lần, lọc lỗi, backoff và kiểm thử số lần đăng ký, ta có thể xây dựng pipeline Reactor có hành vi phục hồi và lặp lại dễ dự đoán. Đặc biệt với `Flux`, cần tính đến các phần tử đã phát trước lỗi và bảo đảm tác dụng phụ có thể chịu được việc thực hiện lại.
