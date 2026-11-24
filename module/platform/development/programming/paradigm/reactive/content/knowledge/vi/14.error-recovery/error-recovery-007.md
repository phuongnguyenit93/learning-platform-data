# Giới hạn số lần thử, thời gian chờ tăng dần và độ lệch ngẫu nhiên

Trong chương **Lỗi và phục hồi**, bài học này trình bày cách cho một thao tác reactive thử lại khi gặp lỗi tạm thời, đồng thời kiểm soát số lần thử và khoảng chờ giữa các lần đăng ký lại. Khi nhiều client cùng gọi một dịch vụ đang gián đoạn, việc thử lại ngay lập tức có thể làm hệ thống quá tải hơn. Chính sách retry có giới hạn, backoff tăng dần và jitter giúp giảm áp lực đó.

Bài học thuộc module **REACTIVE_PROGRAMMING**. Module hướng dẫn: “Học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.” Trong Reactor, ta định nghĩa chính sách thử lại bằng `Retry` rồi gắn chính sách đó vào publisher với `retryWhen`.

## 1. Retry là đăng ký lại publisher upstream

Khi publisher upstream phát `onError`, tín hiệu lỗi thường kết thúc subscription hiện tại. Toán tử retry có thể đăng ký lại upstream để thực hiện thao tác lần nữa. Nếu lần đăng ký mới thành công, dữ liệu tiếp tục đi xuống downstream; nếu vẫn lỗi và chính sách còn cho phép, Reactor có thể tiếp tục thử.

```java
Mono<String> response =
    Mono.defer(() -> remoteClient.fetchProfile(userId))
        .retry(2);
```

Với `retry(2)`, Reactor cho phép tối đa hai lần đăng ký lại sau lần đầu. Nếu cả ba lần thực hiện đều lỗi, lỗi cuối cùng được chuyển xuống downstream. `retry(2)` thử lại ngay, không tự thêm khoảng chờ.

Cần phân biệt:

- **Lần thử ban đầu:** subscription đầu tiên vào publisher nguồn.
- **Retry:** mỗi lần đăng ký lại sau khi upstream phát lỗi.
- **Tổng số lần thực hiện tối đa:** lần ban đầu cộng số retry được cho phép.

Vì vậy, giới hạn retry bằng 3 thường có nghĩa là tối đa 4 lần thực hiện nếu tính cả lần ban đầu. Khi đọc API cấu hình retry, hãy xác định tham số đang đếm số lần retry hay tổng số lần thực hiện để tránh cấu hình sai ngân sách.

Retry không biến một thao tác thất bại thành thao tác thành công một cách tự động. Nó chỉ cho phép chạy lại publisher nguồn theo một chính sách cụ thể. Nếu lỗi là do dữ liệu đầu vào không hợp lệ hoặc người dùng không có quyền, việc thử lại thường không giúp ích.

## 2. Giới hạn số lần thử với Retry

Reactor cung cấp các chính sách dựng sẵn trong `reactor.util.retry.Retry`. Với thao tác chỉ cần giới hạn số lần retry và không cần chờ, có thể dùng `Retry.max`:

```java
Mono<Profile> profile =
    Mono.defer(() -> profileClient.fetch(userId))
        .retryWhen(Retry.max(2));
```

Chính sách này cho phép tối đa hai lần retry sau lần thử đầu. Nếu upstream vẫn lỗi sau khi hết lượt, retry kết thúc bằng lỗi báo rằng chính sách đã cạn lượt; có thể tùy chỉnh cách phát lỗi cuối bằng `onRetryExhaustedThrow`.

Nếu muốn có khoảng chờ cố định giữa các lần thử, dùng `Retry.fixedDelay`:

```java
Mono<Profile> profile =
    profileClient.fetch(userId)
        .retryWhen(
            Retry.fixedDelay(3, Duration.ofMillis(500))
        );
```

Mỗi lần retry chờ 500 mili giây. Số 3 là số lần retry tối đa; nếu tính cả lần thực hiện đầu tiên, tổng cộng có thể có bốn lần gọi upstream.

Chính sách giới hạn là cần thiết để tránh retry vô hạn. Mỗi lần retry có thể tiêu thụ kết nối, thread, quota hoặc tài nguyên ở dịch vụ đích. Nếu một thao tác không thể thành công trong một ngân sách hợp lý, hệ thống cần kết thúc và chuyển lỗi cho tầng xử lý cao hơn.

## 3. Exponential backoff: tăng thời gian chờ theo cấp số nhân

Nếu nhiều request cùng thất bại và cùng retry ngay hoặc chờ một khoảng cố định ngắn, chúng có thể tiếp tục dồn vào dịch vụ đang quá tải. Exponential backoff tăng dần thời gian chờ giữa các lần thử.

Dùng `Retry.backoff(maxAttempts, minBackoff)` để tạo chính sách này:

```java
Retry retryPolicy =
    Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0d);
```

Trong cấu hình trên:

- `3` là số lần retry tối đa sau lần thực hiện ban đầu.
- `200 ms` là khoảng backoff cơ sở cho lần retry đầu.
- Các khoảng chờ tiếp theo tăng theo cấp số nhân.
- `maxBackoff(2 giây)` đặt giới hạn trên cho khoảng chờ.

Nếu bỏ qua jitter để dễ hình dung, chuỗi khoảng chờ cơ sở có dạng 200 ms, 400 ms, 800 ms, 1.600 ms rồi được giới hạn ở mức tối đa đã cấu hình. Đây là khoảng chờ giữa các lần đăng ký lại, không phải thời gian chạy của từng request.

Có thể gắn chính sách vào publisher:

```java
Mono<Inventory> inventory =
    Mono.defer(() -> inventoryClient.findBySku(sku))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
        );
```

Với nguồn chỉ phát một kết quả, downstream nhận kết quả khi một lần thực hiện thành công. Nếu tất cả lần thử đều lỗi, lỗi được chuyển xuống theo chính sách retry. Exponential backoff cho dịch vụ đích thêm thời gian phục hồi giữa các lần gọi.

## 4. Jitter: tạo độ lệch ngẫu nhiên giữa các client

Backoff tăng dần vẫn có thể khiến nhiều client retry cùng thời điểm. Ví dụ, hàng nghìn request cùng thất bại ở một thời điểm và đều chờ 200 ms; chúng có thể tạo ra một đợt request mới gần như đồng loạt. Hiện tượng này thường được gọi là *thundering herd*.

Jitter thêm độ lệch ngẫu nhiên vào khoảng backoff để phân tán thời điểm retry. Trong Reactor, cấu hình bằng `jitter(factor)` trên chính sách backoff:

```java
Retry retryPolicy =
    Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5);
```

Hệ số jitter nằm trong khoảng từ 0 đến 1. Hệ số 0 tắt độ lệch ngẫu nhiên; hệ số lớn hơn tạo mức biến thiên lớn hơn quanh khoảng backoff được tính. Khoảng chờ thực tế vẫn chịu các giới hạn của chính sách.

Ví dụ minh họa dưới đây chỉ thể hiện ý tưởng, không phải lịch retry cố định:

| Lần retry | Backoff cơ sở (không jitter) | Khi có jitter |
|---|---:|---|
| 1 | 200 ms | Xê dịch quanh khoảng cơ sở |
| 2 | 400 ms | Xê dịch quanh khoảng cơ sở |
| 3 | 800 ms | Xê dịch quanh khoảng cơ sở |
| Các lần tiếp theo | Tăng đến giới hạn | Vẫn bị giới hạn bởi max backoff |

Không nên viết test dựa trên một giá trị thời gian chính xác khi jitter đang bật, vì khoảng chờ được ngẫu nhiên hóa. Khi cần kiểm thử thời gian có thể dự đoán, hãy đặt `jitter(0d)`.

## 5. Chỉ retry những lỗi có khả năng tạm thời

Không phải lỗi nào cũng nên thử lại. Một lỗi xác thực, lỗi dữ liệu hoặc lỗi nghiệp vụ thường không thể được khắc phục bằng cách gửi lại cùng request. Có thể lọc loại lỗi được phép retry bằng `filter`:

```java
Mono<PaymentReceipt> receipt =
    Mono.defer(() -> paymentGateway.authorize(command))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(3))
                .jitter(0.5)
                .filter(this::isTransientFailure)
        );
```

Hàm `isTransientFailure` có thể nhận diện các lỗi như mất kết nối tạm thời, timeout hoặc phản hồi máy chủ có thể phục hồi. Những lỗi không thỏa điều kiện lọc sẽ được chuyển xuống ngay, không tiêu tốn các lượt retry còn lại.

Ví dụ một bộ phân loại đơn giản:

```java
boolean isTransientFailure(Throwable error) {
    return error instanceof IOException
        || error instanceof TimeoutException
        || error instanceof ServiceUnavailableException;
}
```

Trong ứng dụng thực tế, hãy dùng các loại exception mà client và thư viện mạng thực sự phát ra. Không nên phân loại chỉ dựa trên chuỗi thông báo lỗi nếu có thể kiểm tra kiểu lỗi hoặc mã trạng thái có cấu trúc.

Nếu upstream phát lỗi không được phép retry, retry policy sẽ không tiếp tục thử. Điều này giúp lỗi không thể phục hồi được xử lý nhanh và giữ nguyên ý nghĩa của lỗi nghiệp vụ.

## 6. Theo dõi từng lần retry và xử lý khi hết lượt

Có thể gắn hành động quan sát vào chính sách bằng `doBeforeRetry` hoặc `doAfterRetry`. `RetrySignal` cung cấp thông tin về lỗi gây retry và số lần retry đã diễn ra.

```java
Mono<Profile> profile =
    Mono.defer(() -> profileClient.fetch(userId))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isTransientFailure)
                .doBeforeRetry(signal ->
                    log.warn(
                        "Retry #{} tiếp theo sau lỗi loại {}",
                        signal.totalRetries() + 1,
                        signal.failure().getClass().getSimpleName()
                    )
                )
        );
```

Đặt lời gọi client bên trong `Mono.defer` giúp mỗi lần subscribe upstream gọi lại hàm tạo publisher. Điều này hữu ích khi client method có công việc được khởi tạo ngay lúc gọi. Nếu client vốn đã lazy, `defer` vẫn làm rõ rằng việc tạo publisher thuộc mỗi lần thực hiện.

Khi hết lượt, Reactor mặc định phát một lỗi báo chính sách retry đã cạn lượt, kèm nguyên nhân cuối. Nếu muốn giữ nguyên lỗi cuối cùng, có thể cấu hình `onRetryExhaustedThrow`:

```java
Mono<Profile> profile =
    Mono.defer(() -> profileClient.fetch(userId))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isTransientFailure)
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()
                )
        );
```

Cấu hình này làm cho downstream nhận nguyên nhân lỗi cuối cùng khi chính sách đã hết lượt. Chọn cách phát lỗi cuối dựa trên hợp đồng API của ứng dụng: một số nơi cần biết retry đã cạn, nơi khác cần giữ kiểu lỗi gốc để xử lý theo loại lỗi.

Log retry nên chứa thông tin vận hành cần thiết như loại lỗi, số lần retry và định danh tương quan. Tránh ghi token, dữ liệu cá nhân hoặc nội dung nhạy cảm của request vào log.

## 7. Retry có thể chạy lại tác dụng phụ: thiết kế idempotency

Retry hoạt động bằng cách đăng ký lại publisher upstream. Vì vậy, toàn bộ thao tác nằm trong vùng upstream của `retryWhen` có thể được thực hiện lại. Điều này đặc biệt quan trọng với thao tác ghi dữ liệu, trừ tiền, gửi email hoặc tạo đơn hàng.

Ví dụ, nếu một request thanh toán đã được xử lý ở máy chủ nhưng phản hồi bị mất trên đường truyền, client có thể nhận timeout và gửi lại. Nếu server không nhận diện request trùng, khách hàng có thể bị trừ tiền hai lần.

Với thao tác có tác dụng phụ, hãy thiết kế tính idempotent. Một cách phổ biến là tạo idempotency key ổn định cho một yêu cầu nghiệp vụ và gửi lại cùng key ở mọi lần retry:

```java
Mono<PaymentReceipt> authorize(PaymentCommand command) {
    String idempotencyKey = command.idempotencyKey();

    return Mono.defer(() ->
            paymentGateway.authorize(command, idempotencyKey)
        )
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(500))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(this::isTransientFailure)
        );
}
```

Idempotency key phải đại diện cho cùng một thao tác nghiệp vụ qua mọi lần thử. Không tạo key mới bên trong hàm được gọi lại mỗi lần retry, vì khi đó server không thể nhận ra các request là cùng một yêu cầu.

Với `Flux`, cần đặc biệt chú ý dữ liệu đã phát trước lỗi. Khi retry đăng ký lại nguồn, các phần tử trước lỗi có thể được phát lại. Ví dụ, nguồn phát A và B rồi lỗi; lần đăng ký lại có thể phát A, B lần nữa trước khi tiếp tục. Downstream khi đó có thể quan sát A, B, A, B. Nếu mỗi phần tử kích hoạt ghi dữ liệu hoặc gửi thông báo, cần chống trùng hoặc đặt ranh giới retry quanh đúng thao tác cần thử lại.

Không đặt một thao tác phụ không idempotent vào upstream của retry nếu chưa xác định cách xử lý kết quả một phần và request trùng.

## 8. Kết hợp retry với timeout và ngân sách thời gian

Retry có giới hạn số lần nhưng tổng thời gian chờ vẫn có thể dài. Tổng thời gian thực hiện gồm thời gian chạy của từng lần gọi cộng các khoảng backoff giữa những lần gọi.

Có hai nhu cầu khác nhau:

- **Timeout cho từng lần gọi:** mỗi lần gọi không được chạy quá lâu. Đặt `timeout` bên trong phần publisher được retry.
- **Timeout cho toàn bộ quy trình:** tổng thời gian từ lúc subscriber bắt đầu đến khi có kết quả không được vượt ngân sách. Đặt `timeout` sau `retryWhen`.

Ví dụ giới hạn mỗi lần gọi:

```java
Mono<Response> perAttemptTimeout =
    Mono.defer(() -> remoteClient.call())
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
        );
```

Mỗi lần retry đăng ký lại publisher có timeout hai giây, nên bộ đếm thời gian của lần gọi mới bắt đầu lại.

Ví dụ giới hạn toàn bộ chuỗi retry:

```java
Mono<Response> totalBudget =
    Mono.defer(() -> remoteClient.call())
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
        )
        .timeout(Duration.ofSeconds(8));
```

Timeout đặt sau retry áp dụng cho toàn bộ chuỗi thử lại. Khi hết tám giây mà chưa có kết quả, pipeline kết thúc bằng lỗi timeout. Hãy chọn ngân sách đủ bao gồm thời gian thực hiện request và các khoảng chờ dự kiến.

Nếu subscriber hủy subscription trong lúc đang chờ backoff, retry được hủy và lần gọi tiếp theo không được khởi động. Cancellation cần được truyền đúng xuống client để giải phóng tài nguyên đang sử dụng.

## 9. Kiểm thử retry bằng thời gian ảo

Không nên dùng `Thread.sleep` để kiểm thử backoff. `StepVerifier.withVirtualTime` cho phép tiến đồng hồ ảo, giúp kiểm tra số lần thực hiện và thời điểm retry mà không phải chờ thật.

Ví dụ dưới đây giả lập hai lần lỗi tạm thời rồi lần thứ ba thành công:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
    Mono.defer(() -> {
        int attempt = attempts.incrementAndGet();

        if (attempt < 3) {
            return Mono.error(new IOException("temporary"));
        }

        return Mono.just("OK");
    }).retryWhen(
        Retry.backoff(3, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(4))
            .jitter(0d)
    )
)
.thenAwait(Duration.ofSeconds(3))
.expectNext("OK")
.verifyComplete();

assertEquals(3, attempts.get());
```

Vì jitter được tắt, hai lần retry xảy ra sau khoảng một giây và hai giây. Tổng thời gian ảo cần tiến là ba giây; lần thực hiện thứ ba thành công. Bộ đếm xác nhận tổng cộng có ba lần đăng ký vào nguồn.

Có thể kiểm thử trường hợp hết lượt bằng một publisher luôn phát lỗi:

```java
StepVerifier.withVirtualTime(() ->
    Mono.<String>error(new IOException("temporary"))
        .retryWhen(
            Retry.backoff(2, Duration.ofSeconds(1))
                .maxBackoff(Duration.ofSeconds(4))
                .jitter(0d)
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()
                )
        )
)
.thenAwait(Duration.ofSeconds(3))
.expectErrorMatches(error ->
    error instanceof IOException
        && "temporary".equals(error.getMessage())
)
.verify();
```

Với hai lần retry, chuỗi có ba lần thực hiện: lần đầu và hai lần đăng ký lại. Test tiến thời gian ảo qua hai khoảng chờ, sau đó xác nhận lỗi cuối được truyền xuống.

Hãy tạo publisher bên trong supplier truyền cho `withVirtualTime` để scheduler ảo được cài đặt trước khi pipeline được lắp ráp. Đặt jitter bằng 0 khi cần kiểm tra chính xác lịch backoff; các test khác có thể xác nhận rằng jitter đã được bật mà không phụ thuộc một giá trị ngẫu nhiên cố định.

## 10. Chọn chính sách và tránh lỗi thường gặp

| Nhu cầu | Cách chọn | Hành vi |
|---|---|---|
| Thử lại ngay, giới hạn số lần | `Retry.max(n)` | Không thêm backoff |
| Chờ cố định giữa các lần retry | `Retry.fixedDelay(n, duration)` | Khoảng chờ không tăng dần |
| Tăng thời gian chờ theo cấp số nhân | `Retry.backoff(n, minBackoff)` | Backoff tăng dần |
| Giới hạn khoảng chờ tối đa | `maxBackoff(duration)` | Chặn mức tăng của backoff |
| Phân tán thời điểm retry của nhiều client | `jitter(factor)` | Thêm độ lệch ngẫu nhiên |
| Chỉ retry lỗi tạm thời | `filter(predicate)` | Lỗi không phù hợp được chuyển xuống |
| Tùy chỉnh lỗi khi hết lượt | `onRetryExhaustedThrow(...)` | Quyết định lỗi cuối được phát |

Những lỗi thiết kế thường gặp:

- **Nhầm số lần retry với tổng số lần thực hiện.** `maxAttempts` là số lần đăng ký lại; cần cộng thêm lần đầu khi tính tổng.
- **Retry mọi loại lỗi.** Lỗi nghiệp vụ, xác thực hoặc dữ liệu sai thường không thể phục hồi bằng cách gửi lại. Hãy lọc lỗi có khả năng tạm thời.
- **Dùng backoff nhưng không có giới hạn.** Luôn cân nhắc `maxBackoff` và ngân sách thời gian tổng thể.
- **Bỏ jitter khi nhiều client cùng retry.** Các client có thể đồng bộ thời điểm gọi lại và tạo thêm đỉnh tải.
- **Không tính đến tác dụng phụ bị lặp.** Retry đăng ký lại upstream; cần idempotency key hoặc cơ chế chống trùng cho thao tác ghi.
- **Retry cả một Flux sau khi đã phát dữ liệu.** Các phần tử trước lỗi có thể xuất hiện lại; hãy xác định ranh giới retry và cách xử lý bản ghi trùng.
- **Dùng retry để thay thế fallback.** Retry chạy lại nguồn; `onErrorResume` chuyển sang publisher khác. Chọn theo mục tiêu phục hồi.
- **Không kiểm thử trường hợp hết lượt và cancellation.** Cần xác nhận cả số lần gọi, lỗi cuối và hành vi khi downstream hủy trong lúc chờ.

## 11. Bài tập vận dụng

Một dịch vụ đặt chỗ gọi hệ thống kho để giữ hàng. Hệ thống kho đôi khi trả lỗi timeout hoặc tạm thời không khả dụng. Các lỗi dữ liệu không hợp lệ và lỗi sản phẩm không tồn tại cần được trả về ngay.

Hãy xây dựng publisher đáp ứng các yêu cầu:

1. Thực hiện lần gọi ban đầu và cho phép tối đa ba lần retry.
2. Bắt đầu backoff ở 250 mili giây, tăng dần và không vượt quá ba giây.
3. Bật jitter để nhiều request không retry cùng một thời điểm.
4. Chỉ retry timeout và lỗi dịch vụ tạm thời.
5. Ghi nhận số lần retry cùng loại lỗi, nhưng không ghi dữ liệu nhạy cảm.
6. Khi hết lượt, giữ nguyên lỗi cuối để tầng API phân loại phản hồi.
7. Đảm bảo request giữ hàng có idempotency key ổn định qua mọi lần retry.
8. Đặt timeout cho mỗi lần gọi và một ngân sách thời gian cho toàn bộ chuỗi.

Dùng `StepVerifier.withVirtualTime` để kiểm thử trường hợp lần thứ ba thành công, trường hợp hết lượt và trường hợp lỗi không thuộc nhóm retryable. Giải thích vì sao cần tắt jitter trong test kiểm tra lịch thời gian chính xác, và vì sao một Flux đã phát dữ liệu trước lỗi có thể phát lại những phần tử đó sau retry.

Một chính sách retry tốt phải trả lời được lỗi nào được thử lại, tối đa bao nhiêu lần, chờ bao lâu, thời điểm retry được phân tán ra sao và tác dụng phụ được bảo vệ như thế nào.
