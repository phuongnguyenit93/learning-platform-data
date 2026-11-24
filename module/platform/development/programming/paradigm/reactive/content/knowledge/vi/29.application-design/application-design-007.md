# Thiết kế hủy, thời gian chờ và thử lại ngay từ đầu

Một pipeline reactive cần có câu trả lời rõ ràng cho ba tình huống: caller không còn cần kết quả, một bước xử lý chờ quá lâu, hoặc thao tác thất bại tạm thời và cần chạy lại. Cancellation giải phóng công việc khi subscription không còn được quan tâm; timeout đặt giới hạn thời gian chờ; retry tạo subscription mới để thử lại một phần pipeline. Ba cơ chế này liên quan chặt chẽ nhưng có semantics khác nhau. Đặt chúng sai vị trí có thể khiến request tiếp tục chạy sau khi client đã ngắt, tổng thời gian vượt deadline hoặc side effect bị thực hiện nhiều lần.

Bài học thuộc chương **Thiết kế ứng dụng** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là thiết kế vòng đời subscription, phân bổ deadline và xác định chính xác phần công việc được subscribe lại khi retry.

Sau bài học, bạn có thể:

- Giải thích cancellation lan truyền từ downstream về upstream và giới hạn của nó với side effect bên ngoài.
- Gắn cleanup với complete, error và cancel bằng `using` hoặc `usingWhen`.
- Dùng `timeout` để giới hạn thời gian chờ và phân biệt timeout mỗi lần thử với deadline tổng.
- Dùng `retry` hoặc `retryWhen` với số lần thử, backoff và bộ lọc lỗi có kiểm soát.
- Hiểu retry resubscribe phần Publisher nằm trước operator retry và có thể phát lại dữ liệu đã phát.
- Phân biệt nguồn cold và hot khi thử lại.
- Bảo vệ thao tác ghi bằng idempotency và thiết kế kiểm thử cancellation, timeout, retry bằng `StepVerifier`.

## 1. Ba cơ chế bảo vệ ba ranh giới khác nhau

| Cơ chế | Kích hoạt khi | Tác động chính | Câu hỏi thiết kế |
|---|---|---|---|
| Cancellation | Downstream không còn cần dữ liệu hoặc chủ động hủy | Yêu cầu upstream dừng phát và giải phóng tài nguyên | Công việc nào có thể dừng an toàn? |
| Timeout | Không có tín hiệu trong thời hạn quy định | Hủy nguồn upstream và phát lỗi timeout hoặc chuyển sang fallback | Deadline áp dụng cho một bước, một lần thử hay toàn request? |
| Retry | Upstream phát lỗi phù hợp với chính sách | Subscribe lại Publisher ở phía upstream của retry | Phần nào được chạy lại và có an toàn khi lặp không? |

Một request có thể đi qua cả ba cơ chế. Ví dụ, client gửi yêu cầu lấy đơn hàng; WebFlux gọi một dịch vụ upstream với timeout hai giây; nếu lỗi mạng tạm thời thì retry một lần; nếu client ngắt kết nối trong lúc backoff thì cancellation dừng lần thử tiếp theo. Nếu upstream đã nhận request ghi dữ liệu, cancellation phía client không tự động hoàn tác side effect ở server.

```text
Client / downstream
       |
       | subscribe + request(n)
       v
  retry policy
       |
       v
  timeout per attempt
       |
       v
  remote Publisher

cancel:  downstream ---------------------------> upstream
signal:  upstream   ---------------------------> downstream
```

Tín hiệu dữ liệu và terminal signal đi từ upstream xuống downstream. Cancellation đi ngược về upstream qua `Subscription.cancel()`. Retry tạo một subscription mới khi lỗi phù hợp được nhận; nó không phải là một tín hiệu đi ngược để khôi phục trạng thái đã phát.

## 2. Cancellation là một phần của hợp đồng Reactive Streams

Khi subscriber gọi `cancel()`, nó thông báo rằng không còn muốn nhận thêm tín hiệu từ subscription đó. Publisher nên ngừng phát dữ liệu cho subscriber và giải phóng tài nguyên có thể giải phóng. Cancellation không yêu cầu Publisher phát `onComplete` hoặc `onError` sau đó; subscriber đã hủy không còn chờ một terminal signal.

Cancellation có thể xuất phát từ nhiều nơi:

- Client đóng kết nối hoặc ngừng đọc response body.
- `timeout` hủy nguồn khi hết thời hạn.
- `take(n)` đã nhận đủ số phần tử cần thiết.
- `switchMap` chuyển sang Publisher con mới và hủy inner cũ.
- Một pipeline downstream bị dispose hoặc hủy bởi ứng dụng.

Ví dụ, `take(3)` chỉ cần ba phần tử nên hủy nguồn sau khi nhận đủ:

```java
Flux<Long> firstThree = Flux.interval(Duration.ofMillis(100))
    .take(3);
```

Nguồn `interval` không cần tiếp tục phát vô hạn sau khi downstream đã nhận ba giá trị. Cancellation giúp giới hạn công việc và tài nguyên.

### Cancellation là best effort, không phải rollback

Cancellation không bảo đảm một thao tác bên ngoài đã bắt đầu sẽ bị đảo ngược. Nếu HTTP request đã được gửi, database đã commit hoặc message đã được broker chấp nhận, việc hủy subscription chỉ có thể dừng phần công việc còn có thể dừng ở phía client/adapter. Nó không tự rollback hành động đã xảy ra ở hệ thống khác.

Với thao tác có side effect, hãy dùng transaction, idempotency key, trạng thái xử lý hoặc quy trình bù trừ phù hợp. Không xem cancellation như một cơ chế hoàn tác nghiệp vụ.

### Quan sát cancellation

`doOnCancel` chạy khi subscription bị hủy; `doFinally` nhận cả `SignalType.CANCEL`, `ON_COMPLETE` và `ON_ERROR`:

```java
Flux<Event> events = eventSource
    .doOnCancel(() -> metrics.increment("events.cancelled"))
    .doFinally(signal -> log.debug("Stream ended: {}", signal));
```

Các hook này phù hợp để ghi nhận metric hoặc log. Không dùng chúng làm cơ chế chính để chờ cleanup bất đồng bộ; `doFinally` là callback đồng bộ và không nhận Publisher cleanup.

## 3. Gắn cleanup với vòng đời subscription

Nếu pipeline mở cursor, file, connection hoặc lease, tài nguyên cần được đóng khi luồng complete, error hoặc cancel. Đặt cleanup chỉ trong `doOnComplete` sẽ bỏ sót đường error và cancellation.

### `using` cho cleanup đồng bộ

```java
Flux<Row> rows = Flux.using(
    cursorFactory::open,
    Cursor::rows,
    Cursor::close
);
```

Tài nguyên được tạo khi subscribe, dùng để tạo Publisher dữ liệu và được cleanup khi Publisher kết thúc hoặc bị hủy. Mỗi subscription có vòng đời tài nguyên riêng.

### `usingWhen` cho cleanup bất đồng bộ

```java
Flux<Row> rows = Flux.usingWhen(
    connectionFactory.create(),
    connection -> connection.createStatement(SQL).execute(),
    connection -> connection.close(),
    (connection, error) -> rollbackAndClose(connection, error),
    connection -> rollbackAndClose(connection, null)
);
```

`usingWhen` cho phép khai báo cleanup riêng khi complete, error và cancel. Các callback trả về Publisher để Reactor có thể subscribe và phối hợp với vòng đời kết thúc. Tên API transaction/connection cụ thể tùy driver; ví dụ trên minh họa cấu trúc quản lý.

Nếu client ngắt kết nối trong khi stream đang đọc, cancellation đi ngược về nguồn và callback cleanup dành cho cancel được thực hiện. Với transaction, chính sách thường là rollback rồi đóng connection; cần xử lý cả trường hợp rollback thất bại để connection vẫn được giải phóng.

## 4. `timeout`: giới hạn thời gian chờ

`timeout(Duration)` phát `TimeoutException` nếu Publisher không phát tín hiệu trong khoảng thời gian quy định. Với `Mono`, đây thường là deadline chờ một kết quả. Với `Flux`, timeout được áp dụng cho khoảng chờ tín hiệu tiếp theo: sau mỗi `onNext`, thời gian chờ cho phần tử kế tiếp được tính lại.

```java
Mono<Product> product = productClient.find(productId)
    .timeout(Duration.ofSeconds(2));

Flux<PriceUpdate> updates = priceFeed.stream()
    .timeout(Duration.ofSeconds(15));
```

- `product` timeout nếu không phát kết quả trong hai giây.
- `updates` timeout nếu không có tín hiệu kế tiếp trong 15 giây. Một stream vẫn có thể chạy lâu hơn 15 giây tổng cộng nếu nó tiếp tục phát đều đặn.

Khi timeout xảy ra, Reactor hủy subscription upstream rồi phát lỗi timeout xuống downstream. Việc hủy giúp ngừng công việc còn có thể dừng, nhưng không bảo đảm server bên ngoài đã ngừng xử lý request.

### Timeout với fallback Publisher

Overload có fallback chuyển sang một Publisher khác khi hết thời gian:

```java
Mono<Product> product = productClient.find(productId)
    .timeout(
        Duration.ofSeconds(2),
        productCache.find(productId)
    );
```

Khi nguồn chính timeout, nguồn cache được subscribe. Nếu cache cũng lỗi, lỗi từ cache được truyền xuống. Nếu fallback có thể chờ lâu, hãy đặt deadline phù hợp cho toàn bộ request; không để mỗi fallback tiêu thụ thêm thời gian vô hạn.

### Timeout không giống hoàn tất theo thời gian

`take(Duration)` dừng và hoàn tất luồng sau một khoảng thời gian; `timeout(Duration)` phát lỗi nếu không nhận tín hiệu đúng hạn. Hai hành vi khác nhau:

```java
// Hoàn tất bình thường sau 5 giây.
Flux<Event> sample = eventSource.take(Duration.ofSeconds(5));

// Phát TimeoutException nếu 5 giây không có tín hiệu kế tiếp.
Flux<Event> guarded = eventSource.timeout(Duration.ofSeconds(5));
```

Chọn theo hợp đồng: một cửa sổ quan sát kết thúc bình thường khác với một dependency không phản hồi.

## 5. Timeout ở nhiều tầng và deadline tổng

Trong ứng dụng web, một thao tác có thể chờ ở nhiều tầng:

| Loại giới hạn | Phạm vi | Ví dụ |
|---|---|---|
| Connect timeout | Thiết lập kết nối transport | Giới hạn thời gian mở kết nối tới upstream. |
| Response/read timeout | Chờ response hoặc dữ liệu trên kết nối | Phát hiện dependency ngừng phản hồi. |
| Publisher timeout | Chờ tín hiệu reactive | Giới hạn một `Mono` hoặc khoảng im lặng của `Flux`. |
| Request deadline | Toàn bộ xử lý của API | Giới hạn tổng thời gian từ lúc nhận đến lúc trả response. |

Giả sử API có deadline tổng ba giây. Nếu xác thực tiêu thụ 200 ms, gọi service A tối đa một giây, gọi service B tối đa một giây và serialize/ghi response cần phần thời gian còn lại, từng tầng phải có ngân sách nhỏ hơn deadline tổng. Đặt timeout ba giây cho từng dependency nối tiếp có thể khiến request vượt quá ba giây nhiều lần.

### Timeout mỗi lần thử và timeout toàn bộ retry

Vị trí của `timeout` so với `retryWhen` thay đổi ý nghĩa:

```java
// Mỗi lần thử có timeout riêng.
Mono<Response> perAttempt = client.call()
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.max(2));

// Deadline bao trọn cả chuỗi retry.
Mono<Response> overall = client.call()
    .retryWhen(Retry.max(2))
    .timeout(Duration.ofSeconds(3));
```

Ở pipeline thứ nhất, mỗi subscription lại vào nguồn sẽ có một timeout một giây. Tổng thời gian có thể vượt một giây vì có nhiều lần thử và có thể có backoff. Ở pipeline thứ hai, timeout nằm ngoài retry nên giới hạn cả các lần thử và khoảng chờ giữa chúng; khi hết ba giây, subscription của toàn bộ chuỗi bị hủy.

Trong production thường cần cả hai: timeout transport/attempt để phát hiện một lần gọi bị treo và deadline tổng để request không vượt SLO. Hãy đảm bảo deadline tổng lớn hơn ngân sách của một lần thử và backoff, nhưng vẫn nằm trong ngân sách request.

## 6. `retry`: subscribe lại Publisher sau lỗi

`retry` không tiếp tục từ đúng instruction hoặc phần tử đã lỗi. Nó subscribe lại Publisher nằm phía upstream của operator retry. Với nguồn cold, subscription mới thường chạy lại công việc nguồn từ đầu.

```java
Mono<User> user = Mono.fromCallable(() -> legacyClient.loadUser(userId))
    .retry(2);
```

Nếu lần gọi đầu và lần thứ hai lỗi, lần thứ ba có thể thành công. `retry(2)` cho phép tối đa hai lần retry sau subscription ban đầu, tức tối đa ba lần subscribe tổng cộng.

`retry()` không giới hạn số lần thử; không dùng retry vô hạn cho request web hoặc dependency không có chính sách dừng. Một nguồn lỗi liên tục có thể tạo tải và giữ request mãi.

### `retryWhen` với backoff và bộ lọc lỗi

`retryWhen` cho phép cấu hình số lần retry, delay và loại lỗi được phép thử lại:

```java
Mono<Response> response = client.call()
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(TransientNetworkException.class::isInstance));
```

Chính sách minh họa:

- Tối đa ba lần retry sau lần gọi đầu.
- Backoff bắt đầu từ 100 ms và tăng theo chính sách exponential backoff.
- Thời gian backoff tối đa hai giây.
- Jitter làm lệch thời điểm retry giữa các client, giảm nguy cơ nhiều client cùng retry đồng loạt.
- Chỉ lỗi `TransientNetworkException` được retry.

Không retry mọi exception. Lỗi validate, lỗi phân quyền, `404` nghiệp vụ hoặc lỗi do bulkhead/circuit breaker từ chối thường không tự hết khi gọi lại. Retry chỉ dành cho lỗi tạm thời và thao tác có thể lặp an toàn.

### Khi hết số lần retry

Khi retry exhaustion xảy ra, Reactor mặc định phát lỗi retry exhausted có nguyên nhân liên quan đến lỗi cuối cùng. Có thể tùy biến exception cuối cùng bằng `onRetryExhaustedThrow`:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
    .filter(TransientNetworkException.class::isInstance)
    .onRetryExhaustedThrow((spec, signal) -> signal.failure());

Mono<Response> response = client.call()
    .retryWhen(retryPolicy);
```

Ví dụ giữ lỗi cuối cùng làm lỗi được phát xuống. Hãy chọn cách biểu diễn exhaustion theo hợp đồng API; controller có thể ánh xạ lỗi cuối thành `503` hoặc `504` tùy nguyên nhân và vai trò của service.

## 7. Retry chỉ lặp phần nằm trước operator retry

Vị trí của `retryWhen` xác định ranh giới được subscribe lại:

```java
Mono<Result> result = source
    .doOnSubscribe(s -> log.info("source subscribed"))
    .map(this::transform)
    .retryWhen(retryPolicy)
    .doOnNext(this::publishMetric);
```

Khi lỗi xảy ra phía trước `retryWhen`, Reactor subscribe lại phần `source -> doOnSubscribe -> map`. Các side effect ở phía trước retry có thể chạy nhiều lần. `doOnNext` nằm sau retry chỉ nhận những phần tử được retry operator chuyển xuống; tuy nhiên, với `Flux`, các phần tử đã được phát ở lần thử lỗi trước vẫn đã đến downstream và không thể thu hồi.

Điều này đặc biệt quan trọng với `Flux`:

```java
Flux<String> events = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IOException("connection lost"))
    )
    .retry(1);
```

Vì nguồn cold được chạy lại từ đầu, downstream có thể nhận `A`, `B` từ lần đầu, sau đó `A`, `B` từ lần retry rồi mới nhận lỗi cuối cùng. Retry không xóa những phần tử đã phát trước lỗi. Nếu downstream đã ghi dữ liệu hoặc gửi message từ lần đầu, lần retry có thể tạo bản ghi trùng.

### `defer` và `fromCallable` để tạo công việc mới mỗi lần subscribe

Nếu cần tạo request hoặc Publisher mới cho mỗi lần thử, hãy trì hoãn việc tạo bằng `defer`:

```java
Mono<Response> response = Mono.defer(() ->
        webClient.get()
            .uri("/resource/{id}", resourceId)
            .retrieve()
            .bodyToMono(Response.class)
    )
    .retryWhen(retryPolicy);
```

`defer` gọi supplier cho mỗi subscription, bao gồm mỗi lần retry. Điều này giúp tạo Publisher mới theo attempt. Ngược lại, nếu gọi một API eager trước khi tạo `Mono.just(value)`, retry sẽ chỉ phát lại cùng giá trị đã tính chứ không thực hiện lại lời gọi ban đầu.

## 8. Nguồn cold và hot khi retry

Retry hoạt động bằng resubscription, nhưng kết quả phụ thuộc vào loại nguồn:

| Nguồn | Hành vi khi retry | Rủi ro |
|---|---|---|
| Cold Publisher | Mỗi subscription thường bắt đầu lại công việc từ đầu | Side effect hoặc phần tử đã phát có thể lặp. |
| Hot Publisher | Subscription mới chỉ nhận tín hiệu từ thời điểm nó tham gia | Có thể bỏ lỡ dữ liệu đã phát trong lúc hủy/chờ retry. |
| Cached/replayed Publisher | Có thể phát lại dữ liệu đã lưu thay vì gọi nguồn mới | Có thể dùng dữ liệu cũ hoặc không tạo request mới như mong đợi. |

Không giả định retry luôn “gọi lại server từ đầu” hoặc luôn phát lại mọi dữ liệu. Hãy xác định nguồn là cold, hot, shared hay replayed. Với stream sự kiện nóng, retry có thể chỉ khôi phục việc nghe từ thời điểm hiện tại; nếu cần không mất sự kiện, hãy dùng offset, cursor hoặc cơ chế replay của broker.

## 9. Bảo vệ side effect bằng idempotency

Retry một thao tác đọc thường dễ an toàn hơn retry thao tác ghi. Nhưng ngay cả thao tác đọc cũng có thể gây chi phí hoặc rate limit. Với lệnh ghi, tình huống nguy hiểm là server đã thực hiện hành động nhưng response bị mất trước khi client nhận được. Client thấy timeout và retry, dẫn đến hành động được thực hiện lần thứ hai.

Ví dụ tạo thanh toán:

```java
Mono<PaymentResult> createPayment(PaymentCommand command) {
    return paymentClient.create(
        command,
        command.idempotencyKey()
    );
}
```

Server hoặc payment provider cần lưu idempotency key và trả lại kết quả của cùng một yêu cầu logic khi nhận key trùng. Chỉ thêm `retryWhen` ở client mà không có idempotency không đủ để bảo đảm không tạo giao dịch trùng.

Với `Flux` đã phát một phần dữ liệu trước khi lỗi, hãy cân nhắc:

- Dùng event ID hoặc sequence number để downstream deduplicate.
- Commit offset/checkpoint sau khi xử lý thành công.
- Đặt transaction ở đúng ranh giới batch hoặc đơn vị nghiệp vụ.
- Không phát side effect không thể đảo ngược trước khi biết đơn vị xử lý đã hoàn tất, nếu nghiệp vụ yêu cầu tính nguyên tử.

## 10. Kết hợp timeout, retry và fallback

Một pipeline thường có ba lớp: timeout để giới hạn mỗi lần gọi, retry cho lỗi tạm thời và fallback khi chính sách retry đã cạn hoặc circuit breaker từ chối.

```java
Mono<Product> loadProduct(String id) {
    Mono<Product> primary = Mono.defer(() ->
            webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class)
        )
        .timeout(Duration.ofSeconds(1))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure));

    return primary
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(error -> productCache.find(id));
}
```

Pipeline minh họa có:

1. `defer` tạo Publisher request mới cho mỗi subscription.
2. Timeout một giây giới hạn mỗi attempt.
3. `retryWhen` thử lại tối đa hai lần với backoff cho lỗi tạm thời.
4. Timeout ba giây bên ngoài giới hạn toàn bộ chuỗi retry.
5. Nếu chuỗi chính thất bại hoặc vượt deadline tổng, fallback đọc cache.

Trong code production, không nên fallback cho mọi lỗi nếu có lỗi bảo mật hoặc lỗi nghiệp vụ. Hãy lọc loại lỗi phù hợp, đặt timeout riêng cho cache nếu cần và xác nhận cache tuân thủ cùng tenant/security policy. Cũng cần phân bổ deadline để fallback còn đủ thời gian chạy.

### Fallback và retry có thứ tự khác nhau

```java
source
    .retryWhen(retryPolicy)
    .onErrorResume(this::fallback);
```

Đây là cách thường dùng: thử lại nguồn chính trước, sau đó mới chuyển sang fallback nếu retry exhaustion vẫn lỗi.

Nếu đặt fallback trước retry:

```java
source
    .onErrorResume(this::fallback)
    .retryWhen(retryPolicy);
```

retry có thể áp dụng cho cả Publisher fallback nếu fallback cũng lỗi. Điều này có thể khiến nguồn dự phòng bị gọi lại theo cùng chính sách, dù mục tiêu ban đầu chỉ là thử lại dependency chính. Hãy đặt retry ở đúng vùng cần lặp.

## 11. Backoff, jitter và retry storm

Nếu nhiều client gặp cùng sự cố và đều retry sau đúng 100 ms, chúng có thể gửi lại request cùng lúc. Điều này tạo retry storm, làm dependency vừa phục hồi lại bị quá tải.

Backoff tăng dần và jitter giúp phân tán các lần thử:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(TransientNetworkException.class::isInstance);
```

Ngoài ra, hãy:

- Giới hạn số lần retry.
- Giới hạn deadline tổng.
- Tôn trọng `Retry-After` nếu API có quy định và client hỗ trợ.
- Không retry lỗi do circuit breaker đang OPEN hoặc bulkhead hết permit.
- Theo dõi retry count và tỷ lệ thành công sau retry.
- Có thể dùng circuit breaker/bulkhead để bảo vệ dependency trong lúc lỗi kéo dài.

Retry là tải bổ sung lên dependency. Khi hệ thống quá tải, giảm số lần thử hoặc trả lỗi sớm có thể tốt hơn tiếp tục retry.

## 12. Kiểm thử cancellation bằng StepVerifier

`StepVerifier` có thể chủ động hủy subscription. Dùng hook để xác nhận nguồn nhận cancellation:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
```

Kiểm thử không cần chờ nguồn tự hoàn tất. Sau khi nhận phần tử đầu tiên, verifier cancel và xác nhận hook upstream đã chạy.

### Kiểm thử timeout bằng virtual time

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
```

Virtual time giúp kiểm thử timeout mà không phải chờ năm giây thực. Tạo Publisher bên trong supplier của `withVirtualTime` để scheduler ảo được áp dụng đúng thời điểm.

## 13. Kiểm thử retry và số lần subscribe

Dùng `AtomicInteger` để xác nhận nguồn cold được gọi lại:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.fromCallable(() -> {
        int attempt = attempts.incrementAndGet();
        if (attempt < 3) {
            throw new IOException("temporary failure");
        }
        return "ok";
    })
    .retry(2);

StepVerifier.create(source)
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

Nguồn được subscribe ba lần: một lần ban đầu và hai lần retry. Đây là cách kiểm tra rõ ràng hơn việc chỉ xác nhận giá trị cuối.

### Kiểm thử `Flux` phát lại phần tử sau retry

```java
StepVerifier.create(
        Flux.concat(
                Flux.just("A", "B"),
                Flux.error(new IOException("failed"))
            )
            .retry(1)
    )
    .expectNext("A", "B", "A", "B")
    .expectError(IOException.class)
    .verify();
```

Test xác nhận phần tử `A`, `B` từ lần thử đầu không bị thu hồi. Khi nguồn cold được subscribe lại, chúng được phát lần nữa trước lỗi cuối. Đây là lý do side effect downstream phải idempotent hoặc có cơ chế deduplication.

### Kiểm thử retry chỉ với lỗi được chọn

```java
StepVerifier.create(
        Mono.<String>error(new IllegalArgumentException("invalid"))
            .retryWhen(Retry.max(3)
                .filter(TransientNetworkException.class::isInstance))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
```

Lỗi validate không khớp filter nên không retry. Kiểm thử chính sách lỗi quan trọng không kém kiểm thử số lần thử.

## 14. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Xem cancellation như rollback | Side effect bên ngoài có thể đã hoàn tất dù client đã hủy. | Dùng transaction, idempotency hoặc quy trình bù trừ. |
| Chỉ cleanup trong `doOnComplete` | Error hoặc cancel có thể làm rò rỉ tài nguyên. | Dùng `using` hoặc `usingWhen`. |
| Dùng `timeout` mà không phân biệt deadline tổng | Retry có thể làm tổng thời gian vượt ngân sách request. | Đặt timeout mỗi attempt và timeout tổng ở đúng vị trí. |
| Nghĩ `Flux.timeout` giới hạn tổng thời lượng | Stream phát đều vẫn có thể chạy vô hạn. | Hiểu timeout là khoảng chờ tín hiệu; dùng deadline tổng riêng. |
| Retry vô hạn | Request có thể giữ tài nguyên mãi và tạo tải liên tục. | Giới hạn retry, backoff và deadline tổng. |
| Retry mọi exception | Lặp lỗi validate, auth hoặc lỗi lập trình. | Dùng filter chỉ cho lỗi tạm thời. |
| Retry thao tác ghi không idempotent | Tạo giao dịch hoặc message trùng. | Dùng idempotency key và xác nhận trạng thái. |
| Nghĩ retry xóa các phần tử `Flux` đã phát | Downstream có thể nhận lại phần tử và side effect bị lặp. | Dùng sequence/deduplication hoặc xử lý theo checkpoint. |
| Đặt retry trước fallback nhưng không xét phạm vi | Publisher fallback cũng có thể bị retry ngoài ý muốn. | Đặt retry ngay quanh nguồn cần thử lại. |
| Dùng retry cho `CallNotPermittedException` hoặc `BulkheadFullException` | Tạo thêm tải khi hệ thống chủ động từ chối. | Fallback hoặc trả lỗi quá tải; không retry ngay. |
| Nghĩ cancellation luôn dừng server từ xa | Server có thể đã nhận và đang xử lý request. | Dùng deadline phía server và idempotency cho side effect. |

## 15. Checklist thiết kế cancellation, timeout và retry

Trước khi đưa pipeline vào production, hãy xác nhận:

- Ai có thể hủy subscription và cancellation có được truyền đến nguồn không?
- Tài nguyên có cleanup trên complete, error và cancel không?
- Side effect nào không thể hoàn tác sau cancellation?
- Timeout áp dụng cho kết nối, mỗi attempt, khoảng im lặng hay deadline tổng?
- Timeout của `Flux` có bị nhầm với giới hạn tổng thời lượng không?
- Retry chỉ áp dụng cho lỗi tạm thời và có số lần tối đa không?
- Backoff/jitter có phù hợp để tránh retry storm không?
- Publisher được retry là cold, hot hay shared; subscription mới có chạy lại từ đầu không?
- `Flux` có thể phát lại phần tử đã phát trước lỗi không?
- Side effect có idempotent hoặc có deduplication/checkpoint không?
- Retry và fallback có được đặt quanh đúng ranh giới Publisher không?
- Deadline tổng có đủ thời gian cho retry, backoff và fallback không?
- Kiểm thử đã xác nhận cancel, timeout, số lần subscribe, lỗi không được retry và duplicate emission chưa?

Cancellation dừng việc tiêu thụ khi downstream không còn cần dữ liệu; timeout biến việc chờ quá lâu thành một quyết định có giới hạn; retry tạo subscription mới cho phần pipeline được chọn. Thiết kế đúng cần xác định rõ ranh giới của từng cơ chế, quản lý tài nguyên theo vòng đời subscription và bảo vệ side effect khỏi việc chạy lặp. Khi deadline, backoff, idempotency và cancellation được kiểm thử cùng nhau, ứng dụng reactive có thể phục hồi lỗi mà vẫn giữ được giới hạn thời gian và tài nguyên.
