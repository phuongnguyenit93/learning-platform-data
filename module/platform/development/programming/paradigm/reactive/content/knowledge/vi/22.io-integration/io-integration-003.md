# Gọi nhiều dịch vụ độc lập bằng luồng con có giới hạn

Một request nghiệp vụ thường cần tổng hợp dữ liệu từ nhiều dịch vụ: hồ sơ khách hàng, hạn mức tín dụng, trạng thái giao hàng hoặc thông tin thanh toán. Những lời gọi này có thể độc lập với nhau, nhưng nếu gọi tuần tự thì thời gian phản hồi bị cộng dồn. Nếu khởi chạy tất cả lời gọi cho mọi phần tử cùng lúc mà không giới hạn, ứng dụng có thể làm cạn connection pool, vượt quota của dịch vụ ngoài hoặc tạo quá nhiều tác vụ chờ trong bộ nhớ.

Trong Reactor, có thể kết hợp `Mono.zip` để chạy các lời gọi độc lập trong cùng một nhóm và dùng `Flux.flatMap` với giới hạn concurrency để xử lý nhiều nhóm phần tử. Mỗi nhóm được biểu diễn bằng một publisher con (*inner publisher*). Giới hạn số inner đang hoạt động giúp kiểm soát lượng công việc đồng thời trong khi vẫn tận dụng được khả năng I/O bất đồng bộ.

## 1. Nhận diện các lời gọi thực sự độc lập

Giả sử một màn hình chi tiết đơn hàng cần lấy thông tin khách hàng và trạng thái thanh toán. Hai dịch vụ đều chỉ cần `orderId`, không cần kết quả của nhau:

```java
Mono<Customer> customer = customerClient.findForOrder(orderId);
Mono<PaymentStatus> payment = paymentClient.statusForOrder(orderId);
```

Hai publisher có thể được subscribe cùng lúc. Nếu gọi tuần tự bằng `flatMap`, lời gọi thanh toán chỉ bắt đầu sau khi customer hoàn tất:

```java
Mono<OrderDetails> sequential = customerClient.findForOrder(orderId)
    .flatMap(customer -> paymentClient.statusForOrder(orderId)
        .map(payment -> new OrderDetails(customer, payment)));
```

Nếu hai dịch vụ độc lập, `Mono.zip` thể hiện đúng quan hệ dữ liệu: chờ cả hai có kết quả rồi kết hợp thành một đối tượng:

```java
Mono<OrderDetails> details = Mono.zip(
        customerClient.findForOrder(orderId),
        paymentClient.statusForOrder(orderId)
    )
    .map(tuple -> new OrderDetails(tuple.getT1(), tuple.getT2()));
```

Khi `details` được subscribe, `Mono.zip` subscribe vào cả hai nguồn. Mỗi lời gọi tiến triển theo publisher riêng và kết quả chỉ được phát khi cả hai nguồn cung cấp một phần tử. Nếu một lời gọi phụ thuộc vào kết quả của lời gọi khác, hãy dùng `flatMap` tuần tự thay vì cố ép chúng thành `zip`.

## 2. Gộp nhiều lời gọi thành một inner publisher

Khi xử lý một `Flux` mã đơn hàng, mỗi mã có thể mở ra một nhóm các lời gọi dịch vụ độc lập. Có thể dùng `Mono.zip` bên trong `flatMap`:

```java
record OrderSummary(
    String orderId,
    Customer customer,
    PaymentStatus payment
) {}

Flux<OrderSummary> summaries = orderIds.flatMap(orderId ->
    Mono.zip(
        customerClient.findForOrder(orderId),
        paymentClient.statusForOrder(orderId)
    ).map(tuple -> new OrderSummary(
        orderId,
        tuple.getT1(),
        tuple.getT2()
    )),
    8
);
```

Mapper của `flatMap` tạo một `Mono<OrderSummary>` cho mỗi `orderId`. Publisher con đó gồm hai lời gọi độc lập được phối hợp bằng `Mono.zip`. `flatMap` đăng ký các inner publisher và hợp nhất kết quả thành một `Flux<OrderSummary>`.

Kết quả là một luồng phẳng, không phải `Flux<Mono<OrderSummary>>`. Caller chỉ cần subscribe một lần vào `summaries`; Reactor quản lý các subscription con theo vòng đời của subscription ngoài.

## 3. Giới hạn số inner publisher đang hoạt động

Tham số concurrency của `flatMap` đặt giới hạn số publisher con được subscribe đồng thời:

```java
Flux<Result> results = requests.flatMap(
    request -> remoteClient.execute(request),
    8
);
```

Với concurrency bằng 8, `flatMap` chỉ duy trì tối đa tám inner publisher đang hoạt động theo cơ chế điều phối của toán tử. Khi một inner hoàn tất, Reactor có thể yêu cầu phần tử nguồn tiếp theo và subscribe inner kế tiếp. Điều này giới hạn số nhóm công việc đang được xử lý cùng lúc.

Nếu mỗi inner chứa hai lời gọi độc lập được `Mono.zip` subscribe cùng lúc, concurrency 8 có thể tạo khoảng tối đa 16 lời gọi dịch vụ đang hoạt động khi tất cả nhóm đều đã khởi chạy và chưa hoàn tất. Vì vậy, concurrency của `flatMap` giới hạn số nhóm đầu vào, không nhất thiết bằng số request HTTP/database thực tế. Hãy tính cả số lời gọi bên trong mỗi nhóm khi chọn giá trị.

| Cấu hình | Ý nghĩa |
| --- | --- |
| `flatMap(mapper, 1)` | Chỉ một inner hoạt động tại một thời điểm; gần với xử lý tuần tự |
| `flatMap(mapper, 4)` | Tối đa bốn nhóm inner được subscribe đồng thời |
| `flatMap(mapper, 16)` | Tối đa mười sáu nhóm inner được subscribe đồng thời |

Concurrency càng cao không có nghĩa hệ thống càng nhanh. Nếu dịch vụ ngoài chỉ cho phép một số connection hoặc request đồng thời, đặt concurrency quá lớn chỉ chuyển hàng đợi sang HTTP client, connection pool hoặc dịch vụ đích. Giá trị phù hợp phải dựa trên năng lực thật của các dependency.

## 4. Chọn concurrency theo giới hạn của từng dịch vụ

Một nhóm có thể gọi nhiều dịch vụ với giới hạn khác nhau. Ví dụ, customer service có thể chịu 40 request đồng thời, nhưng payment service chỉ cho phép 10. Nếu mỗi nhóm luôn gọi cả hai dịch vụ và `flatMap` có concurrency 20, payment service có thể nhận tới khoảng 20 request cùng lúc, vượt mức mong muốn.

Hãy chọn concurrency tổng thể theo dependency có giới hạn chặt nhất, hoặc áp dụng giới hạn riêng cho từng loại lời gọi. Một cách đơn giản là giới hạn số nhóm sao cho số request tối đa của dependency nhạy cảm không vượt khả năng của nó. Với luồng phức tạp hơn, có thể dùng bulkhead/semaphore hoặc rate limiter ở client tương ứng để bảo vệ từng dependency.

Ví dụ, nếu mỗi nhóm tạo một request tới customer và một request tới payment, mà payment chỉ nên nhận tối đa 8 request đồng thời, đặt concurrency nhóm không quá 8 là điểm khởi đầu an toàn. Nếu một nhóm tạo ba request tới cùng payment service, cần tính giới hạn theo hệ số ba hoặc dùng bulkhead riêng.

Concurrency giới hạn số publisher con đang được xử lý; nó không phải giới hạn tốc độ theo giây. Nếu API có quota 100 request/phút, cần rate limiter hoặc cơ chế điều tiết theo thời gian ngoài giới hạn concurrency.

## 5. Kết hợp timeout cho từng dịch vụ

Mỗi dịch vụ có thể có độ trễ và SLA riêng. Đặt timeout tại publisher của từng dependency để một lời gọi chậm không giữ nhóm công việc vô thời hạn:

```java
Mono<OrderSummary> loadSummary(String orderId) {
    Mono<Customer> customer = customerClient.findForOrder(orderId)
        .timeout(Duration.ofSeconds(2));

    Mono<PaymentStatus> payment = paymentClient.statusForOrder(orderId)
        .timeout(Duration.ofSeconds(1));

    return Mono.zip(customer, payment)
        .map(tuple -> new OrderSummary(
            orderId,
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

Trong ví dụ, payment có deadline ngắn hơn customer. Nếu một publisher timeout, nhóm `zip` kết thúc bằng lỗi theo chính sách mặc định; subscription của nguồn còn lại được hủy theo cơ chế của `zip`. Việc hủy request mạng thực tế phụ thuộc HTTP client và khả năng cancellation của transport.

Có thể đặt thêm timeout tổng thể cho nhóm nếu nghiệp vụ có deadline đầu-cuối:

```java
return Mono.zip(customer, payment)
    .map(tuple -> toSummary(orderId, tuple))
    .timeout(Duration.ofSeconds(3));
```

Timeout từng dịch vụ bảo vệ từng dependency; timeout tổng thể giới hạn thời gian caller chờ cả nhóm. Không nên đặt các timeout tùy tiện mà không tính tổng ngân sách thời gian và thời gian dành cho retry.

## 6. Retry phải nằm ở đúng ranh giới

Nếu một dependency có lỗi tạm thời, có thể retry riêng publisher của dependency đó:

```java
Mono<PaymentStatus> payment = paymentClient.statusForOrder(orderId)
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientFailure));
```

Retry bên trong giúp chỉ gọi lại dependency bị lỗi. Nếu đặt retry sau `Mono.zip`, cả nhóm có thể được đăng ký lại và những dịch vụ đã trả kết quả thành công cũng bị gọi lại. Điều đó làm tăng tải và có thể lặp lại tác dụng phụ.

Chỉ retry các thao tác có thể thực hiện lại an toàn hoặc có idempotency key. Truy vấn đọc thường dễ retry hơn lệnh ghi hoặc thanh toán. Với thao tác ghi, cần xác định rõ server xử lý idempotency và cách đối soát kết quả không rõ ràng sau timeout.

Giới hạn số lần retry, dùng backoff và lọc loại lỗi có thể phục hồi. Retry không thay thế giới hạn concurrency; khi dependency quá tải, retry đồng loạt có thể khuếch đại sự cố.

## 7. Xử lý lỗi theo từng dịch vụ hoặc cho cả nhóm

Mặc định, nếu một nguồn trong `Mono.zip` phát lỗi, kết quả nhóm phát lỗi và các nguồn còn lại có thể bị hủy. Đây là lựa chọn phù hợp khi tất cả dữ liệu đều bắt buộc để tạo kết quả:

```java
Mono<OrderDetails> requiredDetails = Mono.zip(
    customerClient.findForOrder(orderId),
    paymentClient.statusForOrder(orderId)
).map(tuple -> new OrderDetails(tuple.getT1(), tuple.getT2()));
```

Nếu một dependency có thể thiếu mà vẫn cho phép hiển thị kết quả một phần, hãy phục hồi lỗi ngay tại publisher đó bằng fallback có kiểu dữ liệu rõ ràng:

```java
Mono<PaymentStatus> payment = paymentClient.statusForOrder(orderId)
    .onErrorResume(RecoverablePaymentException.class, error ->
        Mono.just(PaymentStatus.unavailable())
    );

Mono<OrderDetails> details = Mono.zip(
    customerClient.findForOrder(orderId),
    payment
).map(tuple -> new OrderDetails(tuple.getT1(), tuple.getT2()));
```

Trong ví dụ, lỗi phục hồi được chuyển thành một trạng thái miền nghiệp vụ `unavailable`; lỗi không phục hồi vẫn đi xuống. Cách này giúp caller phân biệt rõ dữ liệu không khả dụng với một giá trị thanh toán hợp lệ.

Không nên dùng `onErrorResume(error -> Mono.empty())` một cách tổng quát cho mọi dependency. Khi một nguồn zip hoàn tất rỗng, `Mono.zip` có thể hoàn tất rỗng mà không phát kết quả; caller sẽ không biết trường dữ liệu nào bị thiếu. Nếu absence là hợp lệ, dùng `defaultIfEmpty` với giá trị miền nghiệp vụ hoặc biểu diễn kết quả bằng `Optional`/kiểu trạng thái rõ ràng.

## 8. Giữ thứ tự đầu ra khi cần

`flatMap` ưu tiên cho phép các inner publisher tiến triển đồng thời. Kết quả được phát khi từng inner sẵn sàng, vì vậy thứ tự có thể khác thứ tự đầu vào:

```text
Đầu vào:           --A------B------C--|
Inner A:              -----------●a|
Inner B:                 --●b|
Inner C:                        ----●c|
flatMap:                --●b------●c----●a|
```

Nếu kết quả phải giữ thứ tự theo đầu vào, có hai lựa chọn:

- `concatMap`: chỉ subscribe inner tiếp theo sau khi inner trước hoàn tất. Thứ tự được giữ nhưng các lời gọi không chạy đồng thời.
- `flatMapSequential`: subscribe nhiều inner đồng thời nhưng phát kết quả theo thứ tự nguồn. Kết quả của inner hoàn tất sớm có thể phải nằm trong buffer để chờ inner trước.

```java
Flux<OrderSummary> ordered = orderIds.flatMapSequential(
    this::loadSummary,
    8
);
```

Chọn `flatMapSequential` khi cần concurrency nhưng thứ tự đầu ra quan trọng. Hãy lưu ý rằng một lời gọi đầu tiên chậm có thể giữ kết quả của các lời gọi sau trong bộ đệm, làm tăng độ trễ và bộ nhớ.

## 9. Gọi nhiều tác vụ chỉ cần hoàn tất bằng Mono.when

Không phải mọi lời gọi độc lập đều cần trả payload. Ví dụ ghi hai audit hoặc cập nhật hai chỉ số độc lập:

```java
Mono<Void> sideEffects = Mono.when(
    auditClient.recordOrderViewed(orderId),
    metricsClient.incrementOrderView(orderId)
);
```

`Mono.when` subscribe vào các publisher và hoàn tất khi các publisher hoàn tất. Nó phù hợp khi cần chờ tất cả tác vụ completion-only. Nếu cần kết hợp dữ liệu từ nhiều `Mono<T>`, dùng `Mono.zip`. Không dùng `zip` với `Mono<Void>` để mong nhận tuple vì `Mono<Void>` không phát phần tử `onNext`.

Nếu một tác vụ trong `when` lỗi, `Mono.when` mặc định kết thúc bằng lỗi và hủy các nguồn còn lại theo khả năng của chúng. Nếu nghiệp vụ cần trì hoãn lỗi cho tới khi tất cả tác vụ kết thúc, tìm hiểu `whenDelayError` và kiểm tra rõ cách tổng hợp lỗi phù hợp.

## 10. Backpressure và hàng đợi không thay thế concurrency limit

Reactive Streams cho phép downstream điều khiển số phần tử muốn nhận qua `request(n)`. Các toán tử như `flatMap` phối hợp demand với publisher nguồn và inner publisher. Tuy vậy, giới hạn concurrency và backpressure giải quyết hai khía cạnh khác nhau:

- Backpressure điều tiết số phần tử được yêu cầu qua subscription.
- Concurrency giới hạn số inner publisher đang hoạt động cùng lúc.
- Connection pool giới hạn số kết nối vật lý có thể dùng.
- Rate limiter giới hạn số lời gọi trong một khoảng thời gian.

Một pipeline có backpressure nhưng concurrency quá cao vẫn có thể tạo nhiều lời gọi đang chờ. Ngược lại, concurrency thấp không bảo đảm quota theo phút nếu mỗi lời gọi hoàn tất rất nhanh. Hãy thiết kế đồng thời các giới hạn phù hợp với từng tầng.

Với `Flux` inner publisher phát nhiều phần tử, overload `flatMap(mapper, concurrency, prefetch)` còn có tham số `prefetch` điều khiển số phần tử được yêu cầu trước từ mỗi inner. `prefetch` ảnh hưởng lượng dữ liệu được đệm, không phải số thread và không thay thế concurrency. Với ví dụ mỗi inner là `Mono.zip`, concurrency thường là tham số quan trọng nhất.

## 11. Không dùng scheduler để giả lập bất đồng bộ

Nếu HTTP client hoặc database driver đã reactive và non-blocking, publisher của nó tự quản lý I/O mà không cần chuyển mỗi lời gọi sang `boundedElastic`. Việc thêm `subscribeOn` cho mọi client reactive có thể làm pipeline phức tạp mà không tăng khả năng đồng thời.

Chỉ cô lập lời gọi khi dependency thực sự blocking:

```java
Mono<LegacyProfile> profile = Mono.fromCallable(
        () -> legacyProfileDao.find(profileId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Đặt `subscribeOn` sát nguồn blocking và giới hạn concurrency của `flatMap` để tránh đẩy quá nhiều tác vụ vào scheduler. `boundedElastic` có giới hạn thread và queue; nếu queue đầy hoặc scheduler bị dispose, tác vụ có thể bị từ chối và publisher phát lỗi. Không retry vô hạn khi scheduler quá tải.

## 12. Kiểm thử giới hạn concurrency

Có thể dùng bộ đếm trong publisher giả lập để xác minh số inner đang hoạt động không vượt concurrency đã đặt:

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

Flux<Integer> work = Flux.range(1, 20)
    .flatMap(id -> Mono.defer(() -> {
        int current = active.incrementAndGet();
        peak.accumulateAndGet(current, Math::max);

        return Mono.delay(Duration.ofMillis(20))
            .map(ignored -> id)
            .doFinally(signal -> active.decrementAndGet());
    }), 4);

StepVerifier.create(work)
    .expectNextCount(20)
    .verifyComplete();

assertTrue(peak.get() <= 4);
assertEquals(0, active.get());
```

`Mono.defer` tăng bộ đếm khi inner được subscribe. `doFinally` giảm bộ đếm khi inner complete, error hoặc cancel. Với concurrency bằng bốn, số inner đồng thời không được vượt bốn. Trong test thực tế, có thể dùng `Sinks.One`, `TestPublisher` hoặc latch để điều khiển thời điểm hoàn tất và xác minh rằng inner thứ năm chỉ được subscribe sau khi một trong bốn inner đầu tiên kết thúc.

Ngoài concurrency, cần kiểm thử các tình huống: một dịch vụ timeout, một dịch vụ trả empty, một dịch vụ phát lỗi, retry chỉ áp dụng cho dependency được chọn, cancellation khi caller rời đi và thứ tự đầu ra nếu dùng `flatMapSequential`. Dùng `StepVerifier.withVirtualTime` cho timeout/backoff dựa trên scheduler thời gian; tránh `Thread.sleep` dài khiến test phụ thuộc tốc độ máy.

## 13. Chọn cấu trúc theo quan hệ giữa các lời gọi

| Nhu cầu | Cấu trúc phù hợp |
| --- | --- |
| Một request cần kết quả từ nhiều dịch vụ độc lập | `Mono.zip(serviceA(), serviceB())` |
| Mỗi phần tử nguồn mở một nhóm lời gọi độc lập | `Flux.flatMap(item -> Mono.zip(...), concurrency)` |
| Các lời gọi không trả payload, chỉ cần chờ hoàn tất | `Mono.when(...)` |
| Cần giới hạn một nhóm chạy tại một thời điểm và giữ thứ tự | `concatMap` |
| Cần chạy đồng thời nhưng phát kết quả theo thứ tự nguồn | `flatMapSequential` |
| Một dependency có thể lỗi nhưng vẫn cho phép kết quả một phần | Fallback có kiểu dữ liệu ngay trên publisher dependency đó |

Trước khi chọn toán tử, hãy vẽ quan hệ phụ thuộc giữa các lời gọi. Các nhánh độc lập có thể chạy đồng thời; nhánh cần dữ liệu từ nhánh trước phải được nối bằng `flatMap` hoặc `then`. Sau đó xác định số request thực tế mà mỗi inner tạo ra, giới hạn concurrency theo dependency nhạy cảm nhất, đặt timeout và retry ở đúng ranh giới, rồi quyết định có cần giữ thứ tự hay cho phép kết quả xen kẽ.

Khi thiết kế theo cách này, mỗi inner publisher đại diện cho một nhóm công việc có vòng đời rõ ràng. `flatMap` điều phối số nhóm hoạt động, `Mono.zip` kết hợp các lời gọi độc lập trong nhóm, còn backpressure, timeout, bulkhead và rate limiter bảo vệ từng tầng tài nguyên. Nhờ đó, ứng dụng có thể tận dụng I/O bất đồng bộ mà vẫn kiểm soát được tải khi tích hợp nhiều dịch vụ trong Project Reactor.
