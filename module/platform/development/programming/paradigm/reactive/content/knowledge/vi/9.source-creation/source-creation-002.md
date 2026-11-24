# Tạo nguồn rỗng, nguồn lỗi và nguồn không kết thúc

Khi xây dựng pipeline reactive, không phải nguồn nào cũng phát ra dữ liệu. Có nguồn hoàn tất ngay mà không có phần tử, có nguồn kết thúc bằng lỗi, và có nguồn không phát bất kỳ tín hiệu nào. Ba trường hợp này có hành vi rất khác nhau đối với các toán tử phía sau. Hiểu rõ chúng giúp bạn chọn đúng cách tạo `Mono` hoặc `Flux`, thiết kế nhánh dự phòng và tránh để một pipeline chờ vô thời hạn.

Bài học thuộc chương **Tạo nguồn** của module `REACTIVE_PROGRAMMING`. Module giúp người học nắm tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là ba trạng thái nguồn cơ bản trong Reactor: empty, error và never.

Sau bài học, bạn có thể:

- Tạo `Mono` và `Flux` hoàn tất bình thường mà không phát phần tử.
- Tạo nguồn phát lỗi và phân biệt lỗi với kết quả rỗng.
- Nhận biết nguồn không phát tín hiệu, không hoàn tất và không báo lỗi.
- Chọn `switchIfEmpty`, `onErrorResume` hoặc `timeout` đúng với tình huống.
- Kiểm thử completion, error, no-signal và hành vi hủy subscription bằng `StepVerifier`.

## 1. Ba kết quả khác nhau của một Publisher

Một Publisher có thể kết thúc theo một trong hai tín hiệu đầu cuối: `onComplete` hoặc `onError`. Trước tín hiệu đầu cuối, nó có thể phát không, một hoặc nhiều `onNext` tùy loại Publisher. Nguồn `never` là trường hợp đặc biệt: nó không phát tín hiệu nào, kể cả tín hiệu đầu cuối.

| Loại nguồn | `onNext` | Tín hiệu đầu cuối | Ý nghĩa |
|---|---:|---|---|
| Empty | Không | `onComplete` | Hoàn tất thành công nhưng không có giá trị. |
| Error | Có thể không có phần tử trước lỗi | `onError` | Xử lý thất bại; lỗi là kết quả đầu cuối. |
| Never | Không | Không có | Subscription tiếp tục tồn tại cho đến khi bị hủy hoặc bị toán tử bên ngoài kết thúc. |

Với `Mono`, kết quả bình thường có tối đa một phần tử. Vì vậy `Mono.empty()` biểu thị hoàn tất mà không có giá trị. Với `Flux`, `Flux.empty()` biểu thị một luồng không có phần tử và hoàn tất bình thường. Cả hai đều khác `null`: Reactive Streams không dùng `null` làm phần tử `onNext`.

Có thể hình dung ba trường hợp như sau:

```text
EMPTY                         ERROR
subscribe                     subscribe
    |                             |
    v                             v
 onComplete()                 onError(error)

NEVER
subscribe
    |
    v
 (không có onNext,
  không onComplete,
  không onError)
    |
    +---- chờ cho đến khi bị cancel hoặc có timeout bên ngoài
```

Sự khác nhau này ảnh hưởng trực tiếp đến các toán tử kết hợp. `switchIfEmpty` chỉ phản ứng khi nguồn hoàn tất mà không có phần tử. `onErrorResume` chỉ phản ứng khi nguồn báo lỗi. Cả hai đều không thể tự chạy nếu nguồn never không phát tín hiệu nào.

## 2. Tạo nguồn rỗng với `Mono.empty()` và `Flux.empty()`

Khi một kết quả hợp lệ có thể không tồn tại, hãy biểu diễn trường hợp đó bằng nguồn empty.

```java
Mono<User> findUser(String id) {
    return repository.findById(id);
}

Mono<User> findOptionalUser(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.empty());
}
```

Ví dụ đầu tiên giả định repository đã trả về `Mono<User>` với semantics không tìm thấy là empty. Ví dụ thứ hai chỉ minh họa rằng có thể trả lại một nguồn empty; trong trường hợp này, `switchIfEmpty(Mono.empty())` không thêm hành vi hữu ích và có thể bỏ đi.

Tạo nguồn empty trực tiếp:

```java
Mono<String> noName = Mono.empty();
Flux<Order> noOrders = Flux.empty();
```

Khi subscribe, `noName` và `noOrders` hoàn tất bình thường. Không có callback `onNext` nào được gọi. Điều này phù hợp với các trường hợp như:

- Một truy vấn tùy chọn không tìm thấy bản ghi.
- Một thao tác `Mono<Void>` chỉ biểu thị hoàn tất của hành động, không trả về dữ liệu.
- Một danh sách đầu vào hợp lệ nhưng hiện tại không có phần tử.
- Một nhánh filter loại bỏ tất cả phần tử và sau đó hoàn tất.

### Empty không phải lỗi

Giả sử API tìm hồ sơ người dùng. Không tìm thấy hồ sơ có thể là kết quả bình thường của truy vấn; lỗi kết nối database lại là thất bại vận hành. Không nên biến mọi trường hợp không có dữ liệu thành exception hoặc biến mọi exception thành empty, vì điều đó làm mất thông tin cần thiết cho nghiệp vụ và quan sát hệ thống.

```java
Mono<User> loadUser(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.defer(() ->
            Mono.error(new UserNotFoundException(id))
        ));
}
```

Ở đây, chỉ trường hợp hoàn tất mà không có người dùng mới được chuyển thành lỗi `UserNotFoundException`. Nếu repository gặp lỗi database, lỗi đó vẫn truyền xuống downstream. `Mono.defer` tạo nhánh lỗi khi nhánh dự phòng thực sự được subscribe.

Nếu nghiệp vụ muốn dùng giá trị mặc định thay vì báo lỗi, có thể dùng `defaultIfEmpty`:

```java
Mono<String> displayName = findDisplayName(userId)
    .defaultIfEmpty("Khách");
```

`defaultIfEmpty` phát giá trị mặc định rồi hoàn tất nếu upstream empty. Nó không thay thế lỗi bằng giá trị mặc định.

### `switchIfEmpty` chỉ chạy sau khi biết nguồn empty

```java
Mono<Product> product = primaryCatalog.findById(id)
    .switchIfEmpty(backupCatalog.findById(id));
```

Nếu catalog chính phát một sản phẩm, catalog dự phòng không được dùng. Nếu catalog chính hoàn tất mà không phát sản phẩm, Reactor subscribe nguồn dự phòng. Nếu catalog chính báo lỗi, `switchIfEmpty` không kích hoạt; lỗi tiếp tục đi xuống.

Khi tạo nguồn dự phòng tốn tài nguyên hoặc cần tính toán tại thời điểm sử dụng, nên trì hoãn việc tạo nó:

```java
Mono<Product> product = primaryCatalog.findById(id)
    .switchIfEmpty(Mono.defer(() -> backupCatalog.findById(id)));
```

`defer` làm cho lời gọi tạo Publisher dự phòng diễn ra khi nhánh đó được subscribe. Điều này tránh thực hiện công việc chuẩn bị không cần thiết trong lúc lắp ráp pipeline.

## 3. Tạo nguồn lỗi với `Mono.error()` và `Flux.error()`

Khi một thao tác không thể tạo ra kết quả hợp lệ, hãy biểu diễn thất bại bằng `onError`.

```java
Mono<User> invalidUser = Mono.error(
    new IllegalArgumentException("userId không hợp lệ")
);

Flux<Order> failedOrders = Flux.error(
    new IllegalStateException("Không thể đọc danh sách đơn hàng")
);
```

Các Publisher trên không phát `onNext`; khi được subscribe, chúng kết thúc bằng `onError`. Một lỗi là tín hiệu đầu cuối: sau khi `onError` được phát, subscription không tiếp tục phát phần tử hoặc tín hiệu đầu cuối thứ hai.

Lỗi cũng có thể xuất hiện sau một số phần tử:

```java
Flux<Integer> valuesThenFailure = Flux.concat(
    Flux.just(10, 20, 30),
    Flux.error(new IllegalStateException("Nguồn phía sau bị lỗi"))
);
```

Subscriber nhận `10`, `20`, `30`, rồi nhận `onError`. Những phần tử đã phát trước đó không bị thu hồi. Các toán tử downstream cần xử lý đúng việc luồng kết thúc bằng lỗi sau một phần dữ liệu.

### Chuyển lỗi thành nhánh dự phòng

`onErrorResume` cho phép thay nguồn bị lỗi bằng một Publisher khác:

```java
Mono<Profile> profile = remoteClient.fetchProfile(userId)
    .onErrorResume(NetworkException.class,
        error -> localCache.findProfile(userId));
```

Nếu nguồn gặp `NetworkException`, pipeline chuyển sang đọc cache. Những lỗi thuộc loại khác tiếp tục truyền xuống. Cách này phù hợp khi cache là nguồn dự phòng có thể đáp ứng cùng hợp đồng nghiệp vụ.

`onErrorReturn` dùng một giá trị cố định khi có lỗi:

```java
Mono<Configuration> configuration = loadConfiguration()
    .onErrorReturn(Configuration.safeDefaults());
```

Hãy cẩn thận khi dùng giá trị mặc định cho lỗi. Một cấu hình mặc định có thể giúp ứng dụng khởi động, nhưng cũng có thể che giấu việc tải cấu hình thất bại. Nếu cần quan sát hoặc phân loại lỗi, hãy ghi nhận đúng loại lỗi và chỉ phục hồi các trường hợp đã được nghiệp vụ cho phép.

### Phân biệt quan sát lỗi và phục hồi lỗi

`doOnError` thêm hành động quan sát như log hoặc tăng metric, nhưng không xử lý lỗi. Lỗi vẫn tiếp tục truyền xuống:

```java
Mono<Receipt> receipt = submitPayment(command)
    .doOnError(error -> metrics.increment("payment.failed"));
```

`onErrorMap` chuyển lỗi hiện tại thành một loại lỗi khác:

```java
Mono<Receipt> receipt = submitPayment(command)
    .onErrorMap(DatabaseException.class,
        error -> new PaymentStorageException("Không lưu được giao dịch", error));
```

`onErrorResume` thay thế nhánh lỗi bằng một Publisher khác. Ba cách này có mục đích khác nhau: quan sát, chuyển đổi và phục hồi. Không nên xem `doOnError` như một cơ chế nuốt lỗi.

## 4. Tạo nguồn không phát tín hiệu với `Mono.never()` và `Flux.never()`

`Mono.never()` và `Flux.never()` tạo Publisher không phát `onNext`, không `onComplete` và không `onError`.

```java
Mono<String> waitForever = Mono.never();
Flux<Event> silentStream = Flux.never();
```

Chúng hữu ích trong một số tình huống kiểm thử hoặc khi mô hình hóa một nguồn chưa có sự kiện và không có điều kiện kết thúc trong phạm vi subscription. Trong ứng dụng thông thường, hãy cân nhắc kỹ vì pipeline có thể giữ tài nguyên và chờ mãi nếu không có timeout hoặc cơ chế hủy.

### Never khác với luồng phát vô hạn

Một nguồn never không phát gì cả. Một nguồn vô hạn có thể phát dữ liệu liên tục mà không tự hoàn tất. Ví dụ:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
```

`Flux.interval` phát các giá trị tăng dần theo chu kỳ cho đến khi bị hủy hoặc gặp lỗi. Nó là nguồn phát vô hạn theo thời gian, không phải nguồn never. Vì timer vẫn tạo tick theo lịch, nếu không có demand tại thời điểm cần phát, nguồn interval mặc định có thể báo lỗi overflow thay vì chờ consumer yêu cầu. Hãy chọn chính sách backpressure phù hợp nếu downstream có thể chậm. Sự phân biệt này rất quan trọng:

| Đặc điểm | `Flux.never()` | `Flux.interval(...)` |
|---|---|---|
| Có `onNext` | Không | Có, theo chu kỳ |
| Tự hoàn tất | Không | Thông thường không tự hoàn tất |
| Có thể tiêu thụ demand | Không có phần tử để tiêu thụ | Có; việc phát chịu cơ chế demand của Publisher |
| Mục đích thường gặp | Kiểm thử trạng thái chờ/no-signal | Tick, polling hoặc sự kiện định kỳ |

Một pipeline dùng `Flux.interval` vẫn cần quan tâm backpressure và tốc độ xử lý. Nếu downstream chậm, cần chọn cách lấy mẫu, buffer, drop hoặc xử lý tải phù hợp với yêu cầu nghiệp vụ.

### Kết thúc việc chờ bằng timeout

Một nguồn never có thể được đặt dưới `timeout` để pipeline có kết quả kết thúc:

```java
Mono<Response> response = Mono.<Response>never()
    .timeout(Duration.ofSeconds(3))
    .onErrorResume(TimeoutException.class,
        error -> Mono.just(Response.unavailable()));
```

Nếu không có tín hiệu trong thời hạn, `timeout` phát lỗi timeout. `onErrorResume` sau đó chuyển lỗi timeout thành phản hồi dự phòng. Nếu không muốn dùng giá trị dự phòng, có thể để timeout tiếp tục truyền lỗi cho caller.

Timeout là một chính sách của pipeline bên ngoài nguồn; nó không biến `Mono.never()` thành Publisher tự hoàn tất. Nếu Subscriber hủy subscription trước thời hạn, pipeline cũng dừng theo việc hủy đó.

## 5. Phối hợp empty, error và never trong pipeline

Khi kết hợp nhiều nguồn, hãy xác định rõ nhánh nào xử lý kết quả rỗng, nhánh nào xử lý lỗi và nhánh nào giới hạn thời gian chờ.

```java
Mono<Account> account = primaryStore.findAccount(accountId)
    .switchIfEmpty(Mono.defer(() -> archiveStore.findAccount(accountId)))
    .switchIfEmpty(Mono.error(new AccountNotFoundException(accountId)))
    .onErrorResume(ArchiveUnavailableException.class,
        error -> Mono.just(Account.unavailable(accountId)))
    .timeout(Duration.ofSeconds(2));
```

Pipeline minh họa các quyết định sau:

1. Nếu kho chính có tài khoản, dùng kết quả đó.
2. Nếu kho chính empty, truy vấn kho lưu trữ.
3. Nếu cả hai đều empty, phát lỗi `AccountNotFoundException`.
4. Nếu kho lưu trữ gặp lỗi thuộc loại được chọn, dùng trạng thái dự phòng.
5. Nếu pipeline không có tín hiệu trong hai giây, `timeout` phát lỗi timeout.

Thứ tự toán tử ảnh hưởng đến kết quả. Trong ví dụ, `timeout` nằm sau `onErrorResume`, nên timeout phát sinh ở phía trước nó không được nhánh `onErrorResume` đã đặt trước đó xử lý. Nếu muốn phục hồi cả timeout, hãy đặt `onErrorResume(TimeoutException.class, ...)` sau `timeout` hoặc điều chỉnh thứ tự toán tử theo ý định.

Một nguồn never không kích hoạt `switchIfEmpty`, vì nó không hoàn tất. Nó cũng không kích hoạt `onErrorResume`, vì không có lỗi. Đây là lý do timeout hoặc cancellation quan trọng khi làm việc với nguồn có thể không phát tín hiệu.

## 6. Tạo Publisher theo nhu cầu với `defer`

Reactor phân biệt thời điểm lắp ráp pipeline và thời điểm subscribe. `Mono.just(value)` nhận giá trị đã được tính trước khi tạo Publisher. Nếu biểu thức tạo giá trị có tác dụng phụ hoặc có thể ném exception, nó có thể chạy ngay tại thời điểm lắp ráp.

```java
Mono<Instant> assembledAt = Mono.just(Instant.now());

Mono<Instant> subscribedAt = Mono.defer(
    () -> Mono.just(Instant.now())
);
```

`assembledAt` giữ thời điểm được tính khi gọi `Mono.just`. `subscribedAt` tạo giá trị mới mỗi lần subscribe. `defer` cũng giúp tạo lỗi tại thời điểm subscribe thay vì thực thi logic tạo nguồn ngay khi lắp ráp:

```java
Mono<User> user = Mono.defer(() -> {
    if (userId == null || userId.isBlank()) {
        return Mono.error(new IllegalArgumentException("userId rỗng"));
    }
    return repository.findById(userId);
});
```

Supplier của `defer` phải trả về một Publisher. Mỗi subscription sẽ gọi supplier để lấy Publisher tương ứng. Điều này hữu ích khi mỗi lần subscribe cần tạo một thao tác, giá trị hoặc nguồn lỗi mới.

Một lựa chọn khác là `Mono.fromCallable` khi công việc tạo ra một giá trị đồng bộ:

```java
Mono<Report> report = Mono.fromCallable(() -> reportService.buildReport());
```

Callable được thực thi khi có subscription. Nếu callable trả về `null`, `Mono.fromCallable` hoàn tất empty; nếu callable ném exception, lỗi được chuyển thành `onError`. Nếu công việc có thể blocking, hãy điều phối nó trên scheduler phù hợp, chẳng hạn `subscribeOn(Schedulers.boundedElastic())`, thay vì chạy blocking trên thread event loop.

## 7. Kiểm thử ba loại nguồn bằng StepVerifier

Kiểm thử nên xác nhận tín hiệu giao thức thay vì chỉ kiểm tra giá trị trả về.

### Kiểm thử nguồn empty

```java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
```

`verifyComplete()` xác nhận Publisher hoàn tất bình thường. Có thể viết gọn bằng `StepVerifier.create(Mono.empty()).verifyComplete()` nếu không cần kiểm tra thêm.

### Kiểm thử nguồn error

```java
StepVerifier.create(
        Mono.error(new IllegalStateException("boom"))
    )
    .expectErrorMessage("boom")
    .verify();
```

Nếu cần xác minh loại exception, dùng `expectError(IllegalStateException.class)` hoặc `expectErrorMatches` để kiểm tra điều kiện cụ thể.

### Kiểm thử nguồn never và cancellation

```java
StepVerifier.create(Mono.<String>never())
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(200))
    .thenCancel()
    .verify();
```

`expectSubscription()` xác nhận subscription đã được thiết lập. `expectNoEvent` xác nhận trong khoảng thời gian đó không có tín hiệu tiếp theo; sau đó `thenCancel()` chủ động hủy để bài kiểm thử kết thúc. Không nên để kiểm thử chờ vô hạn.

### Kiểm thử timeout

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
```

Virtual time giúp kiểm thử thời gian mà không phải chờ năm giây thực. Với các scheduler hoặc toán tử thời gian phức tạp, hãy tạo pipeline bên trong supplier của `withVirtualTime` để Reactor có thể áp dụng scheduler ảo khi lắp ráp.

Các trường hợp nên có trong bộ kiểm thử:

| Trường hợp | Điều cần xác minh |
|---|---|
| `Mono.empty()` | Không có `onNext`, có `onComplete`. |
| `Flux.empty()` | Không có phần tử, có `onComplete`. |
| `Mono.error()` / `Flux.error()` | Có `onError` đúng loại hoặc thông điệp; không có tín hiệu sau lỗi. |
| `switchIfEmpty` | Nhánh dự phòng chỉ được subscribe khi upstream empty. |
| `onErrorResume` | Nhánh dự phòng chỉ chạy cho lỗi phù hợp. |
| `Mono.never()` | Không có tín hiệu trong khoảng quan sát; cancellation kết thúc kiểm thử. |
| `never().timeout(...)` | Timeout tạo lỗi sau thời hạn đã cấu hình. |
| `defer` | Supplier được gọi theo từng subscription, không phải một lần khi lắp ráp. |

## 8. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `null` để biểu diễn không tìm thấy dữ liệu | `null` không phải phần tử hợp lệ của Reactive Streams; dễ tạo lỗi không rõ ràng. | Trả `Mono.empty()` hoặc một kiểu kết quả biểu diễn rõ trạng thái. |
| Xem empty là error | Tạo exception cho một kết quả nghiệp vụ bình thường, làm tăng chi phí và nhiễu log. | Dùng `switchIfEmpty` hoặc `defaultIfEmpty` khi phù hợp. |
| Mong `switchIfEmpty` xử lý lỗi | Nhánh dự phòng không chạy khi upstream kết thúc bằng `onError`. | Dùng `onErrorResume` cho lỗi. |
| Mong `onErrorResume` xử lý never | Không có lỗi nên toán tử không được kích hoạt. | Dùng `timeout` hoặc cancellation để giới hạn thời gian chờ. |
| Nhầm `Flux.interval` với `Flux.never` | Bỏ qua việc interval phát phần tử liên tục. | Phân biệt nguồn không tín hiệu với nguồn vô hạn có tín hiệu. |
| Dùng buffer hoặc chờ vô hạn mà không có chính sách hủy | Giữ tài nguyên lâu dài và có thể gây cạn tài nguyên. | Đặt timeout, giới hạn hàng đợi và quản lý cancellation. |
| Tạo nguồn dự phòng ngay khi lắp ráp pipeline | Có thể chạy logic không cần thiết hoặc dùng trạng thái cũ. | Dùng `Mono.defer` / `Flux.defer` cho nguồn tạo theo subscription. |

## 9. Checklist lựa chọn nguồn

Trước khi tạo hoặc kết hợp một nguồn, hãy tự hỏi:

- Không có dữ liệu có phải là kết quả thành công hợp lệ không? Nếu có, dùng empty.
- Thao tác thất bại có cần truyền nguyên nhân cho caller không? Nếu có, phát error và chỉ phục hồi lỗi đã được xác định.
- Nguồn có thể không phát tín hiệu trong thời gian dài không? Nếu có, quy định timeout hoặc cancellation.
- Nguồn vô hạn có phát dữ liệu liên tục hay hoàn toàn im lặng? Chọn cách xử lý theo đúng semantics.
- Nguồn dự phòng có nên được tạo khi lắp ráp hay chỉ khi nhánh đó được subscribe? Dùng `defer` khi cần trì hoãn.
- Kiểm thử đã xác nhận cả `onNext`, `onComplete`, `onError` và cancellation chưa?

Khi mô hình hóa đúng empty, error và never, pipeline `Mono`/`Flux` thể hiện rõ kết quả nghiệp vụ, thất bại và trạng thái chờ. Điều đó giúp các toán tử fallback, timeout, xử lý lỗi và kiểm thử hoạt động đúng với hợp đồng Publisher–Subscriber và backpressure của Reactive Streams.
