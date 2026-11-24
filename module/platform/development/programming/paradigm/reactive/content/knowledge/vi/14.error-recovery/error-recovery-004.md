# Thay lỗi bằng giá trị mặc định hoặc một nguồn khác

Một Publisher có thể thất bại trong lúc truy vấn dịch vụ, đọc cache hoặc xử lý một sự kiện. Ở một số tình huống, ứng dụng vẫn có thể tiếp tục bằng giá trị mặc định hoặc bằng một nguồn dữ liệu dự phòng. Reactor cung cấp `onErrorReturn` để thay lỗi bằng một giá trị và `onErrorResume` để chuyển sang một Publisher khác. Chọn đúng toán tử giúp pipeline phục hồi có chủ đích mà vẫn giữ được thông tin về lỗi và hợp đồng dữ liệu.

Bài học thuộc chương **Lỗi và phục hồi** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là thay thế nhánh lỗi bằng kết quả có thể sử dụng tiếp, giới hạn loại lỗi được phục hồi và hiểu chính xác điều gì xảy ra sau khi một phần luồng đã được phát.

Sau bài học, bạn có thể:

- Dùng `onErrorReturn` để phát một giá trị mặc định khi nguồn lỗi.
- Dùng `onErrorResume` để chuyển sang nguồn dự phòng hoặc tạo kết quả theo nguyên nhân lỗi.
- Chỉ phục hồi các loại lỗi mà nghiệp vụ cho phép.
- Phân biệt lỗi với kết quả empty và với cancellation.
- Hiểu cách fallback hoạt động khi `Flux` đã phát một số phần tử trước khi lỗi.
- Sắp xếp `retryWhen`, logging và fallback theo đúng mục tiêu.
- Kiểm thử cả nhánh thành công, fallback và lỗi của chính nguồn dự phòng bằng `StepVerifier`.

## 1. Phục hồi lỗi có nghĩa là thay thế tín hiệu lỗi

Trong Reactive Streams, `onError` là tín hiệu đầu cuối. Sau khi Publisher phát `onError`, subscription đó không tiếp tục phát thêm `onNext` hoặc một tín hiệu đầu cuối khác. Reactor cho phép đặt toán tử phục hồi ở phía sau nguồn lỗi để thay nhánh kết thúc bằng lỗi bằng một nhánh khác.

```text
Nguồn chính
    |
    +---- onNext(value) ----> downstream
    |
    +---- onComplete -------> downstream hoàn tất
    |
    +---- onError(error)
              |
              v
       toán tử phục hồi
          /       \
         /         \
  giá trị mặc định  Publisher dự phòng
         \         /
          \       /
           downstream
```

Phục hồi không làm cho thao tác ban đầu thành công. Nó định nghĩa cách pipeline tiếp tục sau khi nhận lỗi. Vì vậy, cần phân biệt:

- **Thành công:** nguồn chính phát dữ liệu và hoàn tất bình thường.
- **Phục hồi:** nguồn chính lỗi, toán tử thay nhánh lỗi bằng giá trị hoặc Publisher khác.
- **Thất bại cuối cùng:** nguồn chính lỗi và không có chính sách phục hồi phù hợp, hoặc chính nhánh dự phòng cũng lỗi.

Một fallback chỉ nên được dùng khi kết quả thay thế đáp ứng yêu cầu nghiệp vụ. Ví dụ, dùng cache khi dịch vụ hồ sơ tạm thời không truy cập được có thể hợp lý; dùng một cấu hình mặc định khi hệ thống không đọc được chính sách bảo mật có thể tạo ra hành vi nguy hiểm.

## 2. `onErrorReturn`: thay lỗi bằng một giá trị cố định

`onErrorReturn` phát một giá trị được chỉ định khi upstream báo lỗi, rồi hoàn tất bình thường. Toán tử này phù hợp khi có một giá trị mặc định đơn giản, không cần truy vấn nguồn khác.

```java
Mono<Configuration> configuration = loadConfiguration()
    .onErrorReturn(Configuration.safeDefaults());
```

Nếu `loadConfiguration()` thành công, giá trị cấu hình thật được phát. Nếu nguồn báo lỗi, `Configuration.safeDefaults()` được phát thay thế, sau đó downstream nhận `onComplete`.

Có thể giới hạn fallback theo loại exception:

```java
Mono<String> displayName = loadDisplayName(userId)
    .onErrorReturn(TimeoutException.class, "Khách");
```

Chỉ `TimeoutException` được thay bằng chuỗi `"Khách"`. Các lỗi khác tiếp tục truyền xuống dưới dạng `onError`.

Overload theo predicate cũng cho phép chọn lỗi theo điều kiện:

```java
Mono<Profile> profile = loadProfile(userId)
    .onErrorReturn(
        error -> error instanceof TemporaryProfileException,
        Profile.unavailable(userId)
    );
```

Hãy nhớ `onErrorReturn` dùng một giá trị đã có. Nếu cần gọi dịch vụ khác, tính fallback dựa trên exception hoặc tạo một Publisher mới, hãy dùng `onErrorResume`.

### `onErrorReturn` với `Flux`

Với `Flux`, giá trị mặc định được phát như một phần tử thay thế cho tín hiệu lỗi. Các phần tử upstream đã phát trước lỗi vẫn được giữ lại:

```java
Flux<Integer> values = Flux.concat(
        Flux.just(10, 20),
        Flux.error(new IllegalStateException("Nguồn bị gián đoạn"))
    )
    .onErrorReturn(-1);
```

Downstream nhận `10`, `20`, `-1`, rồi hoàn tất. `-1` không thay thế toàn bộ luồng từ đầu; nó thay thế tín hiệu lỗi xảy ra sau hai phần tử đầu tiên.

Chỉ dùng sentinel như `-1` khi nó không thể bị nhầm với dữ liệu hợp lệ. Với dữ liệu nghiệp vụ, một kiểu kết quả rõ ràng như `Result`, `Optional` hoặc record trạng thái thường an toàn hơn một giá trị đặc biệt.

## 3. `onErrorResume`: chuyển sang một Publisher khác

Khi fallback cần truy vấn cache, gọi dịch vụ dự phòng hoặc tạo kết quả dựa trên exception, dùng `onErrorResume`.

```java
Mono<User> user = remoteUserClient.findById(userId)
    .onErrorResume(error -> localUserCache.findById(userId));
```

Nếu nguồn chính lỗi, function nhận exception và trả về một Publisher khác. Reactor subscribe Publisher dự phòng và chuyển các tín hiệu của nó xuống downstream. Publisher dự phòng phải phát cùng kiểu phần tử tương thích với kiểu đầu ra của pipeline.

Trong ví dụ thực tế, nên giới hạn loại lỗi được phục hồi:

```java
Mono<User> user = remoteUserClient.findById(userId)
    .onErrorResume(TimeoutException.class, error -> {
        log.warn("Dịch vụ hồ sơ timeout, chuyển sang cache", error);
        return localUserCache.findById(userId);
    });
```

Nếu remote service trả về lỗi xác thực, lỗi dữ liệu hoặc lỗi lập trình, các lỗi đó không khớp `TimeoutException` và tiếp tục truyền xuống. Việc phân loại giúp tránh biến mọi sự cố thành một kết quả tưởng như hợp lệ.

### Chọn nguồn dự phòng theo nguyên nhân lỗi

Function của `onErrorResume` có thể chọn các nguồn khác nhau:

```java
Mono<ExchangeRate> rate = primaryRateClient.getRate(currency)
    .onErrorResume(error -> {
        if (error instanceof RateLimitException) {
            return backupRateClient.getRate(currency);
        }

        if (error instanceof TimeoutException) {
            return cachedRates.find(currency);
        }

        return Mono.error(error);
    });
```

Ở đây:

- Bị giới hạn tốc độ ở nguồn chính thì gọi nhà cung cấp dự phòng.
- Timeout thì đọc tỷ giá cache.
- Lỗi không được nhận diện thì truyền tiếp lỗi ban đầu.

Trong ứng dụng lớn, có thể tách logic chọn fallback thành một hàm riêng để dễ kiểm thử. Tránh tạo một chuỗi `instanceof` dài nếu có thể dùng overload theo class hoặc một chính sách phục hồi có cấu trúc.

### Tạo nguồn dự phòng đúng thời điểm

Nguồn dự phòng chỉ nên được gọi khi nhánh lỗi xảy ra. Có thể dùng `Mono.defer` để trì hoãn việc tạo Publisher:

```java
Mono<Product> product = catalogClient.findProduct(productId)
    .onErrorResume(CatalogUnavailableException.class,
        error -> Mono.defer(() -> backupCatalog.findProduct(productId)));
```

`onErrorResume` chỉ gọi function fallback khi nhận lỗi phù hợp. `defer` hữu ích khi việc tạo Publisher dự phòng có logic hoặc tác dụng phụ cần chạy đúng lúc subscription fallback bắt đầu. Đừng gọi trước một phương thức blocking để tạo giá trị fallback trong lúc lắp ráp pipeline.

## 4. Phân biệt error, empty và cancellation

Fallback cho lỗi không được kích hoạt bởi mọi tình huống không có dữ liệu hoặc không có kết quả.

| Tình huống | Tín hiệu từ upstream | Toán tử thường dùng |
|---|---|---|
| Không tìm thấy dữ liệu và đây là kết quả hợp lệ | `onComplete` mà không có `onNext` | `switchIfEmpty`, `defaultIfEmpty` |
| Thao tác thất bại | `onError(error)` | `onErrorReturn`, `onErrorResume` |
| Subscriber không còn cần dữ liệu | `cancel` | Quản lý cancellation và giải phóng tài nguyên |
| Nguồn chưa phát tín hiệu | Chưa có tín hiệu | `timeout` nếu cần giới hạn thời gian chờ |

Ví dụ, nếu truy vấn cache trả về `Mono.empty()`, `onErrorResume` không chạy vì không có lỗi. Nếu muốn một giá trị mặc định cho trường hợp không tìm thấy, dùng `defaultIfEmpty` hoặc `switchIfEmpty`:

```java
Mono<User> user = cache.findById(userId)
    .switchIfEmpty(remoteUserClient.findById(userId));
```

Nếu muốn phục hồi cả lỗi cache lẫn trường hợp cache empty, hai chính sách cần được viết riêng và theo đúng thứ tự:

```java
Mono<User> user = cache.findById(userId)
    .onErrorResume(CacheUnavailableException.class,
        error -> remoteUserClient.findById(userId))
    .switchIfEmpty(remoteUserClient.findById(userId));
```

Trong ví dụ này, lỗi cache phù hợp được chuyển sang remote; nếu cache hoàn tất empty thì `switchIfEmpty` cũng gọi remote. Nếu remote có thể được gọi nhiều lần hoặc việc tạo Publisher có tác dụng phụ, hãy dùng `Mono.defer` cho nhánh dự phòng và kiểm thử số lần subscribe.

Cancellation không phải `onError`. Khi downstream hủy subscription, `onErrorResume` không được gọi để tạo fallback. Đây là điều mong muốn: khi caller đã ngừng quan tâm, hệ thống không nên tiếp tục công việc chỉ để tạo một kết quả thay thế.

## 5. Fallback trong `Flux` sau khi đã phát một phần dữ liệu

Với `Flux`, nguồn có thể phát nhiều phần tử trước khi lỗi. Khi `onErrorResume` chuyển sang nguồn dự phòng, các phần tử đã được phát không bị thu hồi. Publisher dự phòng tiếp tục từ thời điểm lỗi theo luồng tín hiệu hiện tại.

```java
Flux<String> events = Flux.concat(
        Flux.just("event-1", "event-2"),
        Flux.error(new FeedUnavailableException())
    )
    .onErrorResume(FeedUnavailableException.class,
        error -> Flux.just("backup-event-3", "backup-event-4"));
```

Downstream nhận:

```text
event-1
event-2
backup-event-3
backup-event-4
onComplete
```

Đây là **thay phần còn lại của luồng**, không phải phát lại toàn bộ từ đầu. Nếu nguồn dự phòng đọc lại lịch sử từ đầu, ứng dụng có thể nhận bản ghi trùng. Nếu nguồn chính đã phát đến sequence `2`, fallback nên có cách tiếp tục từ sequence tiếp theo hoặc có cơ chế loại trùng theo ID.

Ví dụ dùng sequence number để tiếp tục:

```java
Flux<OrderEvent> events = primaryFeed.events()
    .doOnNext(event -> lastSeenSequence.set(event.sequence()))
    .onErrorResume(FeedUnavailableException.class, error ->
        backupFeed.eventsAfter(lastSeenSequence.get())
    );
```

`lastSeenSequence` ở ví dụ là trạng thái dùng chung, nên trong ứng dụng thực tế cần bảo vệ nó nếu có nhiều thread truy cập và cần xác định chính sách khi có nhiều subscriber. Có thể mô hình hóa trạng thái trong một service riêng hoặc dùng một cơ chế state an toàn. Điều quan trọng là fallback phải tiếp tục từ vị trí nghiệp vụ phù hợp.

Nếu mục tiêu là chạy lại toàn bộ thao tác từ đầu, đó là bài toán retry. `onErrorResume` thay nhánh lỗi bằng Publisher khác; nó không tự động subscribe lại nguồn ban đầu.

## 6. Chọn giữa giá trị mặc định, nguồn dự phòng và retry

Ba cách tiếp cận có mục đích khác nhau:

| Cơ chế | Hành vi | Khi nào dùng |
|---|---|---|
| `onErrorReturn(value)` | Phát một giá trị thay thế rồi hoàn tất | Có giá trị mặc định an toàn, không cần nguồn khác. |
| `onErrorResume(error -> publisher)` | Chuyển sang Publisher dự phòng | Có cache, nhà cung cấp khác hoặc logic fallback dựa trên lỗi. |
| `retry` / `retryWhen` | Subscribe lại nguồn upstream theo chính sách | Lỗi có thể tạm thời và thao tác có thể được thử lại an toàn. |

Ví dụ retry trước rồi mới fallback:

```java
Mono<Quote> quote = primaryQuoteClient.get(symbol)
    .retryWhen(Retry.max(2)
        .filter(TransientNetworkException.class::isInstance))
    .onErrorResume(TransientNetworkException.class,
        error -> backupQuoteClient.get(symbol));
```

Nguồn chính được thử lại tối đa hai lần theo chính sách `Retry.max(2)`; nếu lỗi mạng tạm thời vẫn còn, pipeline chuyển sang nhà cung cấp dự phòng. Cần xác minh semantics retry của phiên bản Reactor và tính idempotent của thao tác trước khi áp dụng cho lệnh ghi.

Thứ tự ngược lại có ý nghĩa khác:

```java
Mono<Quote> quote = primaryQuoteClient.get(symbol)
    .onErrorResume(error -> backupQuoteClient.get(symbol))
    .retryWhen(Retry.max(2));
```

Ở đây retry đặt sau fallback nên có thể subscribe lại toàn bộ chuỗi đã phục hồi. Nó có thể gọi lại cả nguồn chính lẫn nguồn dự phòng tùy nơi lỗi phát sinh. Nếu fallback đã trả về kết quả thành công, không có lỗi để retry. Hãy đặt retry ở đúng ranh giới nguồn cần thử lại.

Retry không phải lúc nào cũng an toàn. Một lệnh thanh toán hoặc tạo đơn hàng có thể đã được hệ thống bên ngoài thực hiện trước khi kết nối bị ngắt. Thử lại mà không có idempotency key hoặc cơ chế xác nhận trạng thái có thể tạo giao dịch trùng.

## 7. Quan sát lỗi trước khi thay thế

Khi fallback thành công, downstream không còn nhận lỗi gốc. Nếu không ghi nhận lỗi trước khi phục hồi, hệ thống có thể mất dấu sự cố của nguồn chính.

```java
Mono<Profile> profile = remoteClient.fetchProfile(userId)
    .doOnError(error -> metrics.increment("profile.remote.failed"))
    .onErrorResume(TimeoutException.class, error -> {
        log.warn("Dùng cache vì nguồn chính timeout", error);
        return profileCache.find(userId);
    });
```

`doOnError` đứng trước `onErrorResume` quan sát lỗi của nguồn chính trước khi nó được thay thế. Nếu đặt `doOnError` sau `onErrorResume`, nó chỉ quan sát lỗi còn thoát ra từ nhánh fallback hoặc lỗi khác chưa được phục hồi; nó không nhìn thấy lỗi chính đã được thay thế thành công.

Không nên log mọi lỗi ở nhiều tầng nếu chúng tạo bản ghi trùng. Hãy chọn một ranh giới có trách nhiệm quan sát lỗi, đồng thời ghi metric cho số lần fallback, tỷ lệ fallback thành công, độ trễ nguồn dự phòng và lỗi của fallback.

### Lỗi từ chính Publisher dự phòng

Fallback cũng có thể thất bại. Ví dụ, remote service timeout và cache cũng không truy cập được. Khi Publisher trả về từ `onErrorResume` phát `onError`, lỗi fallback sẽ được truyền xuống downstream.

```java
Mono<User> user = remoteClient.findUser(userId)
    .onErrorResume(TimeoutException.class,
        primaryError -> cache.findUser(userId)
            .onErrorMap(cacheError ->
                new UserLookupFailedException(userId, primaryError, cacheError)));
```

Ví dụ đóng gói cả lỗi nguồn chính và lỗi cache vào một exception nghiệp vụ. Cách này giúp caller hiểu rằng cả hai nguồn đều thất bại. Thiết kế exception cần giữ nguyên nguyên nhân gốc để phục vụ chẩn đoán.

## 8. Giá trị fallback cần có cùng ý nghĩa nghiệp vụ

Fallback có cùng kiểu Java chưa chắc có cùng ý nghĩa nghiệp vụ. Ví dụ `User.empty()` và một người dùng thật đều có thể mang kiểu `User`, nhưng caller cần biết đâu là dữ liệu thật và đâu là trạng thái dự phòng.

Một cách biểu diễn rõ ràng là dùng record trạng thái:

```java
enum DataSource {
    PRIMARY,
    CACHE,
    DEFAULT
}

record UserResult(User user, DataSource source) {}

Mono<UserResult> loadUserResult(String userId) {
    return remoteClient.findUser(userId)
        .map(user -> new UserResult(user, DataSource.PRIMARY))
        .onErrorResume(TimeoutException.class, error ->
            cache.findUser(userId)
                .map(user -> new UserResult(user, DataSource.CACHE))
        )
        .defaultIfEmpty(new UserResult(User.guest(), DataSource.DEFAULT));
}
```

Kết quả cho biết dữ liệu đến từ nguồn chính, cache hay giá trị mặc định. Ví dụ này cũng thể hiện sự khác nhau giữa lỗi và empty: lỗi timeout mới kích hoạt `onErrorResume`; nếu cả nguồn được chọn hoàn tất empty, `defaultIfEmpty` mới phát kết quả mặc định.

Chỉ dùng giá trị mặc định khi caller có thể xử lý nó như một kết quả hợp lệ. Nếu giá trị mặc định làm sai lệch quyết định nghiệp vụ, hãy để lỗi truyền xuống hoặc biểu diễn rõ trạng thái không khả dụng.

## 9. Kiểm thử fallback bằng StepVerifier

Kiểm thử nên xác nhận cả dữ liệu thay thế lẫn việc lỗi không thuộc phạm vi vẫn được truyền xuống.

### Kiểm thử `onErrorReturn`

```java
StepVerifier.create(
        Mono.<String>error(new TimeoutException("slow"))
            .onErrorReturn("cached")
    )
    .expectNext("cached")
    .verifyComplete();
```

### Kiểm thử `onErrorResume`

```java
StepVerifier.create(
        Mono.<String>error(new TimeoutException("slow"))
            .onErrorResume(error -> Mono.just("backup"))
    )
    .expectNext("backup")
    .verifyComplete();
```

### Kiểm thử chỉ phục hồi loại lỗi đã chọn

```java
StepVerifier.create(
        Mono.<String>error(new IllegalArgumentException("bad input"))
            .onErrorResume(TimeoutException.class,
                error -> Mono.just("backup"))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
```

### Kiểm thử `Flux` giữ phần tử đã phát

```java
StepVerifier.create(
        Flux.concat(
                Flux.just("A", "B"),
                Flux.error(new IllegalStateException("broken"))
            )
            .onErrorResume(error -> Flux.just("C", "D"))
    )
    .expectNext("A", "B", "C", "D")
    .verifyComplete();
```

### Kiểm thử fallback cũng thất bại

```java
StepVerifier.create(
        Mono.<String>error(new TimeoutException("primary"))
            .onErrorResume(error ->
                Mono.error(new IllegalStateException("fallback")))
    )
    .expectErrorMessage("fallback")
    .verify();
```

Ngoài các ví dụ trên, hãy kiểm tra fallback không được subscribe khi nguồn chính thành công, cancellation không kích hoạt fallback, và fallback được gọi đúng số lần khi có retry hoặc nhiều subscriber.

## 10. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `onErrorReturn` khi cần gọi nguồn dự phòng | Chỉ có một giá trị cố định, không thực hiện truy vấn thay thế. | Dùng `onErrorResume` để trả về Publisher khác. |
| Phục hồi mọi loại exception | Lỗi lập trình, dữ liệu hoặc xác thực có thể bị che thành kết quả hợp lệ. | Chọn class hoặc predicate cho lỗi được phép phục hồi. |
| Nghĩ `onErrorResume` xử lý cả empty | Empty là `onComplete`, không phải `onError`. | Dùng `switchIfEmpty` hoặc `defaultIfEmpty`. |
| Nghĩ fallback chạy khi downstream cancel | Cancellation không phải tín hiệu lỗi. | Quản lý tài nguyên bằng cancellation hook hoặc `using` phù hợp. |
| Dùng `onErrorResume` để chạy lại nguồn chính | Fallback thay nhánh lỗi bằng Publisher khác. | Dùng `retry`/`retryWhen` nếu cần subscribe lại nguồn. |
| Cho fallback `Flux` đọc lại từ đầu sau khi đã phát một phần | Có thể tạo bản ghi trùng hoặc sai thứ tự. | Tiếp tục từ cursor/sequence đã xử lý hoặc loại trùng theo ID. |
| Không quan sát lỗi nguồn chính trước khi fallback | Sự cố được che giấu khi fallback thành công. | Ghi log/metric ở trước toán tử phục hồi. |
| Cho rằng fallback chắc chắn thành công | Nguồn dự phòng cũng có thể lỗi hoặc empty. | Kiểm thử lỗi fallback và định nghĩa kết quả cuối cùng. |

## 11. Checklist thiết kế chính sách fallback

Trước khi đưa fallback vào production, hãy xác định:

- Lỗi nào được phép phục hồi và lỗi nào phải truyền xuống?
- Dùng một giá trị mặc định hay cần một Publisher dự phòng?
- Giá trị thay thế có cùng ý nghĩa nghiệp vụ và cùng hợp đồng kiểu dữ liệu không?
- Nguồn chính đã phát một phần dữ liệu chưa; fallback cần tiếp tục từ vị trí nào?
- Có cần retry nguồn chính trước khi chuyển sang fallback không?
- Fallback có thể empty, lỗi hoặc chậm không; có timeout riêng không?
- Đã ghi nhận lỗi nguồn chính và đo tỷ lệ sử dụng fallback chưa?
- Cancellation có dừng được công việc nguồn chính và nguồn dự phòng không?
- Đã kiểm thử thành công, lỗi được chọn, lỗi không được chọn, fallback lỗi và partial emission chưa?

`onErrorReturn` phù hợp với một giá trị mặc định đã xác định; `onErrorResume` phù hợp khi cần thay nhánh lỗi bằng một Publisher khác. Phục hồi tốt cần chọn đúng loại lỗi, giữ đúng ý nghĩa dữ liệu, tính đến những phần tử đã phát và quan sát được sự cố của nguồn chính. Khi các điều kiện đó rõ ràng, pipeline `Mono`/`Flux` có thể tiếp tục một cách có kiểm soát mà vẫn giữ được tính minh bạch của hợp đồng Publisher–Subscriber.
