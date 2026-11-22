# onErrorResume và chuyển sang nguồn dự phòng trong Reactor

## 1. Vấn đề cần giải quyết

Trong **Project Reactor**, một **Mono<T>** hoặc **Flux<T>** có thể gặp lỗi vì dịch vụ bên ngoài tạm thời không khả dụng, timeout, kết nối bị đóng hoặc phép biến đổi dữ liệu thất bại. Theo Reactive Streams, **onError** là tín hiệu kết thúc: Publisher đã lỗi không thể tiếp tục phát các phần tử còn lại.

Trong nhiều hệ thống Spring WebFlux, một lỗi kỹ thuật có thể được xử lý bằng nguồn thay thế. Ví dụ: gọi API chính lấy hồ sơ người dùng; khi API lỗi tạm thời, đọc hồ sơ đã được lưu trong cache. Toán tử **onErrorResume** có nhiệm vụ **chuyển sang Publisher dự phòng** khi upstream phát lỗi phù hợp:

~~~java
Mono<User> result = remoteClient.find(id)
    .onErrorResume(error -> localCache.find(id));
~~~

Đoạn trên minh họa các kiểu và phương thức ứng dụng giả định. Nó không tự chuyển việc đọc remote thành đọc cache khi remote trả về rỗng, và không gọi lại remote. Mục tiêu của bài là hiểu chính xác **khi nào fallback chạy, lỗi nào được phục hồi, dữ liệu nào được phát, điều gì xảy ra khi fallback cũng lỗi** và cách áp dụng an toàn trong WebFlux.

Sau bài này, bạn có thể:

- Giải thích chuỗi tín hiệu onSubscribe/onNext/onError/onComplete trước và sau onErrorResume.
- Phân biệt **error recovery**, **retry** và **empty fallback**.
- Sử dụng overload theo **Class** hoặc **Predicate** để chỉ bắt lỗi cho phép phục hồi.
- Đặt onErrorResume đúng vị trí trong pipeline Mono, Flux và trong mapper của flatMap/concatMap.
- Thiết kế fallback có giới hạn timeout, quan sát được lỗi gốc và không che giấu lỗi nghiệp vụ.
- Chạy và giải thích một chương trình Java 17 với Reactor Core minh họa các đường đi thành công, lỗi, nguồn rỗng và fallback nhiều tầng.

## 2. Cơ chế tín hiệu: nguồn lỗi kết thúc, nguồn dự phòng được đăng ký

Giao thức Reactive Streams ở một Subscription:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

**onError** và **onComplete** là hai tín hiệu kết thúc loại trừ nhau. onErrorResume không cho phép Publisher cũ tự phát thêm sau lỗi. Thay vào đó, nó xử lý tín hiệu lỗi và **subscribe một Publisher mới** mà hàm fallback trả về.

~~~text
Nguồn chính:
  onSubscribe → onNext(A) → onError(primaryError)
                                       │
                                       ▼
                                onErrorResume
                                       │
                                 chọn Publisher
                                       │
Nguồn dự phòng:            onSubscribe → onNext(B) → onComplete
                                       │
                                       ▼
Downstream nhìn thấy:
  onSubscribe → onNext(A) → onNext(B) → onComplete
~~~

Nếu fallback cũng phát **onError**, downstream sẽ nhận lỗi đó, trừ khi có một operator xử lý lỗi khác ở phía sau.

Các hệ quả:

1. Những **onNext** đã gửi trước lỗi của Flux vẫn được giữ nguyên ở downstream. onErrorResume không xóa hoặc rollback dữ liệu đã phát.
2. **Nguồn chính không được tiếp tục từ phần tử sau lỗi.** Việc phục hồi là thay phần còn lại bằng nguồn mới.
3. **Fallback function chỉ được gọi khi upstream phát onError phù hợp** trong quá trình subscribe, không chạy ngay chỉ vì tạo đối tượng Mono/Flux.
4. **Subscription downstream vẫn phải được tôn trọng demand/backpressure** khi chuyển sang nguồn dự phòng.
5. Khi Subscriber cuối **cancel**, đây là thao tác hủy, không phải lỗi; cancel không mặc nhiên kích hoạt onErrorResume.
6. onErrorResume chỉ bắt lỗi ở **phần pipeline upstream tại vị trí của nó**. Lỗi sinh ra từ operator đặt sau nó phải được xử lý ở một vị trí downstream khác.

Đối với **Mono<T>**, fallback có thể là một Mono thành công có giá trị, Mono.empty hoặc Mono.error. Với **Flux<T>**, fallback có thể phát nhiều phần tử. Không nên hiểu tên onErrorResume là “chạy lại cùng một lời gọi”.

## 3. Cú pháp và overload

Các dạng cơ bản:

~~~java
Mono<T> recoveredMono = sourceMono
    .onErrorResume(error -> alternativeMono(error));

Flux<T> recoveredFlux = sourceFlux
    .onErrorResume(error -> alternativePublisher(error));
~~~

Hàm xử lý **Throwable** và trả về một Publisher có kiểu dữ liệu tương thích với source. Reactor cung cấp biến thể lọc bằng class hoặc predicate:

~~~java
// Chỉ một loại exception và các lớp con.
source.onErrorResume(
    RemoteUnavailableException.class,
    error -> cacheLookup()
);

// Chỉ những exception khớp predicate.
source.onErrorResume(
    error -> isRecoverable(error),
    error -> cacheLookup()
);

// Tự phân loại nhiều trường hợp.
source.onErrorResume(error -> {
    if (error instanceof TimeoutException) {
        return cachedData();
    }
    if (error instanceof RateLimitedException) {
        return alternateRegion();
    }
    return Mono.error(error);
});
~~~

Các ví dụ là snippet, yêu cầu định nghĩa **RemoteUnavailableException**, **RateLimitedException**, các hàm truy cập dữ liệu và import **java.util.concurrent.TimeoutException**. Khi không muốn phục hồi một lỗi, có thể **trả Mono.error(error)** để giữ lỗi gốc. Nếu chỉ muốn biến Throwable thành lỗi nghiệp vụ khác, **onErrorMap** thường đúng mục đích hơn.

**Chọn phạm vi nhỏ nhất có thể.** Một onErrorResume không lọc có thể vô tình chuyển lỗi xác thực, validation hoặc lỗi lập trình thành kết quả dự phòng, gây khó điều tra và thậm chí vi phạm hợp đồng quyền truy cập.

## 4. Phân biệt kết quả có dữ liệu, rỗng và lỗi

Đây là khác biệt quan trọng nhất khi thiết kế fallback:

| Nguồn chính | Tín hiệu | onErrorResume có chạy? | Kết quả |
| --- | --- | --- | --- |
| **Mono.just("ok")** | onNext + onComplete | Không | Giá trị ok |
| **Mono.empty()** | onComplete, không onNext | Không | Kết quả rỗng |
| **Mono.error(e)** | onError | Có nếu lỗi phù hợp | Dữ liệu/complete/error của fallback |
| **Flux** phát A, B rồi lỗi | A, B, onError | Có | A, B rồi dữ liệu fallback |
| **Mono.never()** | Không có terminal | Không | Chờ, trừ khi hủy/timeout |
| **cancel()** từ downstream | Yêu cầu hủy | Không mặc nhiên | Dừng xử lý theo hợp đồng cancel |

Một kết quả rỗng **không phải lỗi**:

~~~java
Mono<String> value = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("backup"));

// Value vẫn hoàn thành rỗng, không trả "backup".
~~~

Muốn có fallback **khi rỗng**, dùng **switchIfEmpty**:

~~~java
Mono<String> value = source
    .switchIfEmpty(Mono.defer(() -> loadCache()));
~~~

Nếu muốn phân biệt cả hai tình huống:

~~~java
Mono<String> value = source
    .onErrorResume(RecoverableException.class, error -> loadCache())
    .switchIfEmpty(Mono.defer(() -> loadCache()));
~~~

Hãy xem xét kỹ việc gọi cache hai lần: nếu nguồn chính lỗi, fallback đầu tiên gọi cache nhưng cache hoàn thành rỗng, **switchIfEmpty đặt phía sau lại có thể gọi cache lần nữa**. Khi muốn chỉ một lần truy cập cache, thiết kế lại luồng theo hợp đồng rõ ràng hoặc đặt nhánh xử lý rỗng trước nhánh recovery.

**Mono.empty** được phép mang ý nghĩa “không có tài nguyên”. **Mono.error** mang ý nghĩa “không thực hiện được truy vấn”. Không nên tự biến mọi trường hợp empty thành lỗi kỹ thuật chỉ để dùng onErrorResume.

## 5. Ví dụ nghiệp vụ: remote lỗi, đọc cache

Giả sử một hệ thống đọc thông tin sản phẩm từ dịch vụ chính, có một cache cục bộ được phép trả dữ liệu cũ:

~~~java
public Mono<Product> findProduct(String id) {
    return remoteProductClient.get(id)
        .onErrorResume(
            RemoteUnavailableException.class,
            error -> productCache.findById(id)
        );
}
~~~

Giả định kiểu **Product** và các dependency đã được định nghĩa; cả hai phương thức truy cập trả Mono<Product>.

Dòng điều khiển:

~~~text
remoteProductClient.get(id)
     ├─ onNext(Product) + onComplete ──────────> Product từ remote
     ├─ onComplete (rỗng) ────────────────────> Rỗng, không fallback
     └─ onError(RemoteUnavailableException)
                          │
                          ▼
                  productCache.findById(id)
                        ├─ onNext(Product) → Product từ cache
                        ├─ onComplete rỗng → Không có dữ liệu dự phòng
                        └─ onError        → Lỗi của cache tới downstream
~~~

Đây là mô hình reactive của ý tưởng:

~~~java
try {
    return remoteBlockingCall(id);
} catch (RemoteUnavailableException e) {
    return cacheBlockingCall(id);
}
~~~

Ví dụ thứ hai là mô tả **imperative, blocking**, không phải một cách triển khai cho pipeline bất đồng bộ. Trong Reactor, nhiều lỗi chỉ xảy ra **khi subscribe**, sau thời điểm đối tượng Mono được tạo ra. Vì vậy một try/catch xung quanh lời gọi trả Mono không thay thế được onErrorResume.

## 6. Chỉ fallback cho lỗi được phép phục hồi

| Lỗi | Thường có nên chuyển nguồn? | Lý do |
| --- | --- | --- |
| Timeout đọc dữ liệu, kết nối tạm lỗi | Có thể, nếu cache/backup hợp lệ | Nguồn chính tạm không khả dụng |
| HTTP 503 từ dịch vụ đọc | Có thể, theo SLA và tuổi dữ liệu | Có thể phục vụ degraded mode |
| HTTP 401/403 | Thường không | Phải giữ chính sách xác thực và phân quyền |
| Validation đầu vào sai | Không | Fallback che lỗi của caller |
| Dữ liệu không tồn tại bình thường | Tùy hợp đồng, thường là empty/404 | Không tự nhầm thành sự cố remote |
| NullPointerException do bug | Không nên | Dễ che giấu lỗi lập trình |
| Lỗi ghi có side effect chưa rõ trạng thái commit | Cần thiết kế riêng | Có thể trùng ghi hoặc vi phạm tính nhất quán |

Đoạn minh họa dùng predicate:

~~~java
Mono<Order> result = remote.find(id)
    .onErrorResume(
        error -> error instanceof TimeoutException
              || error instanceof ConnectException,
        error -> cache.find(id)
    );
~~~

Đây là snippet giả định, cần import **java.util.concurrent.TimeoutException**, **java.net.ConnectException** và các kiểu ứng dụng. Exception thực tế có thể được client HTTP bọc trong loại exception khác. Khi viết predicate production, phải căn cứ đúng loại Throwable mà thư viện thực sự phát, kể cả cause nếu hợp đồng thư viện quy định.

Không dùng một câu lệnh chung **onErrorResume(error -> Mono.empty())** chỉ để làm hệ thống “không báo lỗi”. Nếu caller cần biết truy vấn đã thất bại, việc trả Mono.empty có thể bị diễn giải nhầm là dữ liệu không tồn tại.

## 7. Nguồn dự phòng là lazy và có vòng đời riêng

### 7.1. Khi nào backup được gọi?

~~~java
Mono<String> result = remote()
    .onErrorResume(error -> loadBackup());
~~~

Hàm **loadBackup** ở trong lambda chỉ được gọi sau khi upstream báo lỗi. Nó không chạy khi remote thành công.

Nếu việc **tạo** Publisher đã có side effect, có thể dùng **Mono.defer** để đảm bảo hành động diễn ra lúc đăng ký fallback:

~~~java
Mono<String> result = remote()
    .onErrorResume(error ->
        Mono.defer(() -> loadBackup())
    );
~~~

**Mono.just(expensiveCall())** thực hiện **expensiveCall** ngay khi câu lệnh tạo Mono được đánh giá; **Mono.fromCallable(this::expensiveCall)** mới trì hoãn phép tính đến subscribe. Với I/O blocking, chọn scheduler phù hợp (ví dụ boundedElastic cho blocking work) để không chặn thread event-loop của WebFlux.

### 7.2. Fallback có thể thất bại

~~~java
Mono<String> result = remote()
    .onErrorResume(error -> cache())
    .onErrorResume(error -> secondRegion());
~~~

Nếu remote lỗi, cache được subscribe. Nếu cache cũng lỗi, **onErrorResume thứ hai** được kích hoạt và chuyển sang secondRegion. **onErrorResume đầu tiên không tự bắt lại lỗi từ chính fallback của nó**, nên cần một operator xử lý khác ở downstream nếu muốn có thêm tầng phục hồi.

Nếu mọi đường đều thất bại, cuối cùng phải truyền lỗi có ý nghĩa cho caller; không nên tạo một chuỗi fallback vô hạn. Khi cần bảo toàn thông tin lỗi gốc và lỗi backup, ghi nhận chúng bằng logs/trace hoặc thiết kế exception chứa nguyên nhân và ngữ cảnh phù hợp.

### 7.3. Fallback có thể rỗng hoặc phát nhiều giá trị

~~~java
Mono<String> optional = remote()
    .onErrorResume(RecoverableException.class,
        error -> Mono.empty());

Flux<String> stream = primaryFlux()
    .onErrorResume(error -> Flux.just("backup-A", "backup-B"));
~~~

Trường hợp đầu có nghĩa ứng dụng **chủ động chấp nhận** mất dữ liệu khi lỗi được phân loại và trả thành công rỗng. Trường hợp thứ hai, nếu primaryFlux đã phát X, Y trước lỗi, downstream thấy **X, Y, backup-A, backup-B** theo demand; onErrorResume không xóa X và Y đã phát trước đó.

## 8. Phạm vi bắt lỗi trong Flux: ngoài chuỗi hay trong từng item

Đây là khác biệt dễ gây bug nghiêm trọng. Giả sử nhận danh sách các mã định danh và mỗi mã thực hiện một truy vấn.

**Đặt ngoài concatMap:**

~~~java
Flux.fromIterable(ids)
    .concatMap(id -> remote.find(id))
    .onErrorResume(error -> fallbackFeed());
~~~

Khi một request lỗi, **toàn bộ chuỗi trước onErrorResume** đã kết thúc lỗi. onErrorResume đăng ký fallbackFeed và **không quay lại thực hiện các id còn lại** ở Flux nguồn. Nó giữ những kết quả đã gửi trước lỗi.

**Đặt trong từng inner:**

~~~java
Flux.fromIterable(ids)
    .concatMap(id ->
        remote.find(id)
            .onErrorResume(
                RecoverableException.class,
                error -> cache.find(id)
            )
    );
~~~

Nếu một id lỗi có thể phục hồi, inner cho id đó chuyển sang cache, hoàn tất rồi concatMap tiếp tục id kế tiếp. Đây là cách thích hợp cho từng thao tác độc lập có fallback riêng. Nếu cache trả rỗng, số lượng kết quả đầu ra có thể ít hơn số id. Nếu cache cũng lỗi hoặc exception không khớp, pipeline vẫn có thể kết thúc lỗi.

Với **flatMap**, các inner có thể hoạt động đồng thời và không bảo đảm thứ tự kết quả. Với **concatMap**, từng inner hoàn thành rồi mới chuyển sang inner sau, nên thứ tự item được giữ. **Vị trí recovery quan trọng hơn việc chỉ biết tên toán tử.**

Không tự gọi subscribe trong mapper:

~~~java
// Sai về điều phối tác vụ: subscription bên trong bị tách rời.
return ids.concatMap(id -> {
    remote.find(id).subscribe(this::record);
    return Mono.just(id);
});
~~~

Ở đây concatMap chỉ chờ Mono.just(id), không chờ remote.find(id), và lỗi của remote có thể rời khỏi pipeline. Đúng hơn là **trả về Publisher chứa toàn bộ công việc**, rồi ghép onErrorResume vào chính inner đó.

## 9. So sánh với retry, switchIfEmpty và các operator xử lý lỗi

| Toán tử | Khi nào kích hoạt | Hành vi |
| --- | --- | --- |
| **onErrorResume** | Lỗi từ upstream | Subscribe Publisher dự phòng |
| **onErrorReturn** | Lỗi phù hợp | Trả một giá trị cố định |
| **onErrorComplete** | Lỗi phù hợp | Biến lỗi thành onComplete, không có dữ liệu mới |
| **onErrorMap** | Lỗi phù hợp | Đổi exception, tiếp tục đường lỗi |
| **doOnError** | Lỗi đi qua vị trí operator | Quan sát/log; không phục hồi |
| **retry / retryWhen** | Lỗi từ upstream | Đăng ký lại upstream; có thể lặp side effect |
| **switchIfEmpty** | Nguồn hoàn thành rỗng | Subscribe một Publisher khác |
| **defaultIfEmpty** | Nguồn hoàn thành rỗng | Phát một giá trị mặc định |
| **timeout** | Vượt điều kiện thời hạn | Phát lỗi timeout hoặc dùng overload có fallback |

Ví dụ:

~~~java
Mono<String> a = remote().onErrorReturn("default");

Mono<String> b = remote().onErrorResume(
    error -> cache()
);

Mono<String> c = remote().switchIfEmpty(
    Mono.defer(() -> cache())
);

Mono<String> d = remote().onErrorMap(
    error -> new DomainException("lookup failed", error)
);
~~~

Các phương thức và kiểu trong snippet là giả định. Nếu cần **thử lại remote** vì lỗi tạm thời, chọn retry có giới hạn; nếu muốn **chuyển nguồn**, chọn onErrorResume; nếu muốn **một kết quả mặc định tĩnh**, onErrorReturn là gọn hơn; nếu nguồn **rỗng**, switchIfEmpty mới là lựa chọn đúng.

## 10. Ghép timeout và retry trước fallback

Một chính sách phổ biến: đợi remote trong giới hạn, thử lại có kiểm soát, rồi mới chuyển cache.

~~~java
Mono<Data> result = remote.find(id)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    )
    .onErrorResume(
        error -> shouldUseCache(error),
        error -> cache.find(id)
    );
~~~

Đây là snippet trong service có **Data**, remote/cache, các hàm predicate giả định; import **java.time.Duration** và **reactor.util.retry.Retry**.

- **timeout** khiến một lần đăng ký upstream phát lỗi nếu quá hạn.
- **retryWhen** có thể đăng ký lại upstream khi lỗi phù hợp, tối đa **hai lần thử lại** sau lần thử đầu tiên. Phải đánh giá side effect và idempotency.
- Sau khi retry dừng bằng lỗi, **onErrorResume** quyết định có chuyển cache hay giữ đường lỗi.
- **Retry exhaustion** có thể bọc exception thành loại retry-exhausted. Predicate chỉ kiểm tra TimeoutException trực tiếp **có thể không còn khớp**. Cần kiểm chứng exception thực tế, dùng contract của Reactor như **Exceptions.isRetryExhausted** và nguyên nhân, hoặc cấu hình **onRetryExhaustedThrow** để định nghĩa lỗi cuối mong muốn.
- Nếu cache cũng lỗi, lỗi của cache tiếp tục xuống downstream trừ khi có handler khác.

**Thứ tự operator thay đổi kết quả.** Nếu onErrorResume đứng **trước** retry và biến lỗi thành dữ liệu cache thành công, retry sẽ không được kích hoạt. Nếu retry đứng **sau** fallback, nó có thể đăng ký lại pipeline khi fallback lỗi. Hãy viết thứ tự theo nghiệp vụ thay vì lắp các operator theo thói quen.

Timeout gửi yêu cầu hủy phần upstream đang hoạt động, nhưng không bảo đảm đã dừng hoặc rollback mọi thao tác ngoài hệ thống. Với giao dịch ghi, chỉ retry và fallback khi có chính sách idempotency rõ ràng.

## 11. Quan sát lỗi gốc và trạng thái giảm chất lượng

Một khi fallback thành công, downstream không còn nhận lỗi gốc. Vì vậy vị trí **doOnError** rất quan trọng:

~~~java
Mono<User> result = remote.find(id)
    .doOnError(error -> logPrimaryFailure(id, error))
    .onErrorResume(error -> {
        countFallbackAttempt(id, error);
        return cache.find(id);
    })
    .doOnError(error -> logUnrecoveredFailure(id, error))
    .doFinally(signal -> recordTerminalSignal(signal));
~~~

Các hàm log, metrics và service là thành phần minh họa.

- **doOnError trước onErrorResume** thấy lỗi gốc của remote.
- Callback **onErrorResume** báo lúc fallback được lựa chọn.
- **doOnError sau onErrorResume** thấy lỗi còn lại, chẳng hạn cache cũng lỗi; khi recovery thành công, nó **không** thấy lỗi remote.
- **doFinally** thấy lý do hoàn tất tại vị trí quan sát, bao gồm onComplete, onError hoặc cancel.
- **doOnSuccess** của Mono nhận đối số null khi Mono hoàn thành rỗng; đây không phải onNext(null).

Các metric cần cân nhắc: số request remote, số lỗi remote theo loại, số lần fallback, tỷ lệ fallback thành công, số lần fallback trả rỗng, lỗi fallback, độ trễ fallback, tỷ lệ response dùng dữ liệu cũ. Không coi onComplete của Mono.empty là đã lấy được dữ liệu hợp lệ.

Nếu caller cần biết kết quả từ nguồn nào, mô hình hóa minh bạch:

~~~java
record SourcedUser(User user, String source) {}

Mono<SourcedUser> found = remote.find(id)
    .map(user -> new SourcedUser(user, "PRIMARY"))
    .onErrorResume(
        RecoverableException.class,
        error -> cache.find(id)
            .map(user -> new SourcedUser(user, "CACHE"))
    );
~~~

Đây là snippet phụ thuộc User, remote/cache và exception ứng dụng. Kiểu kết quả có trường source giúp tránh tình trạng nội dung cache bị trình bày như dữ liệu mới nhất. Quyết định có gửi thông tin nguồn ra HTTP response hay chỉ ghi metrics tùy nghiệp vụ và bảo mật.

## 12. Ví dụ Java 17+ hoàn chỉnh, chạy được với Maven

Ví dụ minh họa sáu trường hợp: remote thành công; remote lỗi và chuyển cache; remote rỗng; lỗi không thuộc loại cho fallback; fallback theo từng item; và fallback thứ nhất lỗi phải chuyển nguồn thứ hai.

Cấu trúc:

~~~text
onerrorresume-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── OnErrorResumeDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>onerrorresume-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tệp **src/main/java/OnErrorResumeDemo.java**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class OnErrorResumeDemo {

    static Mono<String> primary(String key) {
        return Mono.defer(() -> {
            System.out.println("primary " + key);
            return switch (key) {
                case "ok" -> Mono.just("remote-ok");
                case "down" -> Mono.<String>error(
                    new IllegalStateException("service down")
                );
                case "missing" -> Mono.<String>empty();
                case "bad" -> Mono.<String>error(
                    new IllegalArgumentException("invalid input")
                );
                default -> Mono.<String>error(
                    new IllegalStateException("unknown")
                );
            };
        });
    }

    static Mono<String> cache(String key) {
        return Mono.defer(() -> {
            System.out.println("fallback " + key);
            return Mono.just("cache-" + key);
        });
    }

    public static void main(String[] args) {
        System.out.println("=== 1. Primary success ===");
        primary("ok")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("ok")
            )
            .doOnNext(System.out::println)
            .block();

        System.out.println("=== 2. Primary error ===");
        primary("down")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("down")
            )
            .doOnNext(System.out::println)
            .block();

        System.out.println("=== 3. Empty is not error ===");
        primary("missing")
            .onErrorResume(error -> cache("missing"))
            .doOnSuccess(value ->
                System.out.println("result=" + value)
            )
            .block();

        System.out.println("=== 4. Error type does not match ===");
        primary("bad")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("bad")
            )
            .onErrorResume(error -> {
                System.out.println(
                    "unhandled " + error.getClass().getSimpleName()
                );
                return Mono.empty();
            })
            .block();

        System.out.println("=== 5. Per-item recovery ===");
        Flux.just("ok", "down", "ok")
            .concatMap(key ->
                primary(key)
                    .onErrorResume(
                        IllegalStateException.class,
                        error -> cache(key)
                    )
            )
            .doOnNext(System.out::println)
            .blockLast();

        System.out.println("=== 6. Backup also fails ===");
        Mono.<String>error(
                new IllegalStateException("primary offline")
            )
            .onErrorResume(error ->
                Mono.error(
                    new UnsupportedOperationException("backup offline")
                )
            )
            .onErrorResume(
                UnsupportedOperationException.class,
                error -> Mono.just("secondary-backup")
            )
            .doOnNext(System.out::println)
            .block();
    }
}
~~~

Chạy tại thư mục chứa **pom.xml** với **JDK 17+** và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OnErrorResumeDemo
~~~

**Stdout mong đợi:**

~~~text
=== 1. Primary success ===
primary ok
remote-ok
=== 2. Primary error ===
primary down
fallback down
cache-down
=== 3. Empty is not error ===
primary missing
result=null
=== 4. Error type does not match ===
primary bad
unhandled IllegalArgumentException
=== 5. Per-item recovery ===
primary ok
remote-ok
primary down
fallback down
cache-down
primary ok
remote-ok
=== 6. Backup also fails ===
secondary-backup
~~~

Giải thích:

1. Với **ok**, lambda fallback không được gọi. Vì nguồn dùng **Mono.defer**, dòng primary xuất hiện khi subscription thực sự xảy ra.
2. Với **down**, IllegalStateException khớp overload lọc loại lỗi, nên cache được đăng ký và trả **cache-down**.
3. Với **missing**, Mono.empty hoàn thành thành công rỗng; fallback không chạy. **doOnSuccess** nhận **null**, nhưng không có onNext(null).
4. Với **bad**, IllegalArgumentException không khớp IllegalStateException; cache không chạy. Handler tiếp theo in tên exception và chuyển thành empty **chỉ để minh họa trong CLI**. Trong ứng dụng thực, lỗi validation cần được trả về caller theo chính sách.
5. Với chuỗi ba item, fallback nằm trong concatMap. Khi item thứ hai được phục hồi, item thứ ba vẫn được xử lý, giữ thứ tự input.
6. Fallback đầu tiên phát UnsupportedOperationException; chỉ operator onErrorResume thứ hai xử lý lỗi mới đó và trả **secondary-backup**.

Các nguồn trong chương trình đều đồng bộ và không dùng sleep, nên thứ tự stdout ổn định. **block()** và **blockLast()** chỉ dùng ở phương thức main của ứng dụng CLI để quan sát kết quả; chúng **không phù hợp trên event-loop Spring WebFlux**.

## 13. Áp dụng với WebClient trong Spring WebFlux

Giả sử endpoint đọc hồ sơ từ một dịch vụ bên ngoài. Chỉ khi remote trả **HTTP 5xx** mới được dùng cache:

~~~java
@GetMapping("/profiles/{id}")
public Mono<Profile> getProfile(@PathVariable String id) {
    return webClient.get()
        .uri("/profiles/{id}", id)
        .retrieve()
        .bodyToMono(Profile.class)
        .doOnError(error -> recordPrimaryFailure(id, error))
        .onErrorResume(
            error -> error instanceof WebClientResponseException response
                  && response.getStatusCode().is5xxServerError(),
            error -> profileCache.findById(id)
        );
}
~~~

Đây là **snippet controller**, với các dependency **webClient**, **profileCache**, kiểu **Profile** và phương thức **recordPrimaryFailure** giả định. Cần import **WebClientResponseException** của Spring WebFlux và các annotation MVC/WebFlux tương ứng.

Lưu ý:

- Với **retrieve()**, HTTP 4xx/5xx mặc định được chuyển thành lỗi WebClientResponseException nếu ứng dụng không thay cấu hình xử lý response.
- Predicate trên chỉ phục hồi cho phản hồi **5xx**. Một lỗi kết nối có thể là loại exception khác; nếu muốn bắt lỗi mạng, thêm điều kiện có chủ đích.
- HTTP **401/403** không tự được fallback, giúp giữ đường lỗi quyền truy cập.
- Nếu cache trả Mono.empty, downstream hoàn thành rỗng; cách ánh xạ ra HTTP status cần được xác định theo hợp đồng endpoint.
- Nếu cache lỗi, lỗi mới được framework xử lý qua pipeline.
- Controller **trả về Mono** cho Spring, không tự gọi subscribe. Framework giữ vòng đời subscription của HTTP request.

### Không gọi subscribe thủ công để xử lý fallback

~~~java
// Không nên: mất liên kết với response và cơ chế báo lỗi.
public Mono<Profile> bad(String id) {
    remote.find(id).subscribe(
        value -> updateCache(value)
    );
    return profileCache.findById(id);
}
~~~

Đoạn trên mang tính mô tả lỗi kiến trúc; **updateCache** và các dependency là giả định. Lời gọi subscribe khởi tạo một subscription tách rời, nên pipeline HTTP không chờ remote và không quản lý được lỗi/cancellation của tác vụ phụ.

Thay vào đó:

~~~java
public Mono<Profile> good(String id) {
    return remote.find(id)
        .onErrorResume(
            RecoverableException.class,
            error -> profileCache.findById(id)
        );
}
~~~

Khi cần đồng bộ cache sau khi đọc thành công, có thể ghép **flatMap** vào cùng pipeline và thể hiện rõ đường thành công cùng đường lỗi.

## 14. Ranh giới an toàn: ghi dữ liệu, cache stale và lỗi ngoài hệ thống

onErrorResume **không phải transaction hay rollback**. Nếu một thao tác POST đến remote timeout, remote có thể đã commit rồi mới mất kết nối. Khi đó chuyển sang hệ thống backup để thực hiện cùng thao tác ghi có nguy cơ ghi trùng.

Quy tắc triển khai:

1. Với **tác vụ đọc**, xác định mức độ cũ tối đa của cache, quyền truy cập và sự tương thích của dữ liệu backup.
2. Với **tác vụ ghi**, yêu cầu idempotency key, trạng thái commit rõ hoặc một quy trình bù trừ trước khi retry/fallback.
3. Không dùng **Mono.empty()** để che mọi lỗi của thao tác bắt buộc ghi thành công.
4. Xác định timeout riêng cho primary và backup; một backup bị treo vẫn có thể làm toàn bộ request không kết thúc.
5. Tính đến trường hợp **nhiều request đồng thời chuyển sang backup** khi nguồn chính gặp sự cố, gây quá tải cho hệ thống dự phòng.
6. Khi primary và backup dùng chung một dependency, fallback không nhất thiết cải thiện khả năng phục hồi.
7. Cancellation/timeout trong Reactor không chứng minh tác vụ ở mạng hoặc database bên ngoài đã được hoàn tác.
8. Nếu dùng cache chứa dữ liệu nhạy cảm, kiểm tra lại authorization đối với mỗi request; không coi cache là đường vượt qua chính sách quyền truy cập.

Để quan sát chế độ giảm chất lượng, báo cáo tỷ lệ fallback, tuổi dữ liệu và lỗi fallback. Một HTTP response thành công từ cache có thể hữu ích với người dùng nhưng vẫn là tín hiệu để hệ thống vận hành kiểm tra remote.

## 15. Backpressure và cancellation khi chuyển nguồn

Khi onErrorResume chuyển sang một Flux dự phòng, dữ liệu vẫn phải tuân thủ **request(n)** của Subscriber cuối. Những item đã được phát từ nguồn chính trước lỗi đã tiêu thụ một phần demand. Fallback không được bỏ qua phần demand còn lại để phát tự do.

Một số tình huống:

- Downstream không còn demand: fallback có thể chờ request tiếp theo trước khi phát onNext.
- Downstream cancel trước khi primary lỗi: không có onError nên fallback không được kích hoạt.
- Downstream cancel sau khi fallback bắt đầu: subscription của fallback được yêu cầu hủy; không nhất thiết dừng ngay side effect ngoài hệ thống.
- Fallback bị lỗi: onError của fallback đi tiếp trừ khi có thêm handler ở downstream.
- Fallback không bao giờ kết thúc: pipeline có thể chờ vô hạn nếu không timeout/hủy.

Ví dụ timeout cho từng nhánh:

~~~java
Mono<Result> result = primary()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(
        TimeoutException.class,
        error -> backup()
            .timeout(Duration.ofSeconds(1))
    );
~~~

Đây là snippet giả định kiểu Result và phương thức primary/backup. Nếu backup lại timeout, lỗi timeout thứ hai được báo xuống downstream. Nếu cần một deadline tổng cho cả operation, đặt cơ chế giới hạn thời gian ở ranh giới thích hợp của toàn pipeline, không mặc định cộng thời hạn từng bước bằng SLA.

## 16. Các lỗi thường gặp

| Nhầm lẫn hoặc triệu chứng | Cách hiểu đúng |
| --- | --- |
| onErrorResume làm upstream tiếp tục chạy sau item lỗi | Upstream đã kết thúc, được **thay bằng Publisher khác** |
| onErrorResume xử lý Mono.empty | Không, cần switchIfEmpty |
| onErrorResume giống retry | Không, retry **đăng ký lại upstream**, còn onErrorResume chuyển nguồn |
| onErrorResume bắt tất cả lỗi ở bất kỳ vị trí nào | Chỉ lỗi upstream của operator; vị trí quan trọng |
| onErrorResume ngoài concatMap giúp xử lý item kế tiếp | Không; nguồn concatMap cũ đã lỗi. Đặt recovery trong inner nếu cần xử lý item độc lập |
| Cache trả rỗng nhưng được báo là đã tải thành công | Rỗng là kết quả riêng; cần chính sách HTTP/nghiệp vụ rõ |
| onErrorResume tự bắt cả lỗi của chính fallback | Không; cần handler khác downstream |
| doOnError sau recovery thấy lỗi primary | Nếu recovery thành công, lỗi primary đã được xử lý trước vị trí này |
| Fallback cho 401/403 là vô hại | Có thể vi phạm quyền truy cập, phải phân loại lỗi |
| onErrorResume(error -> Mono.empty()) luôn an toàn | Dễ che giấu lỗi bắt buộc báo |
| Timeout chứng minh remote chưa ghi | Không; commit có thể đã xảy ra |
| Gọi subscribe trong controller rồi trả Mono khác | Subscription tách rời, framework không tự chờ tác vụ đó |
| Fallback bảo đảm nhanh hơn | Có thể chậm, treo hoặc quá tải; phải đo latency và giới hạn |
| retryWhen giữ nguyên loại exception khi hết retry | Không chắc; có thể là retry-exhausted wrapper |
| Hủy subscription kích hoạt fallback | Cancel không phải onError |

## 17. Tự kiểm tra và bài tập

**Câu 1.** Mono.just("OK").onErrorResume(e -> backup()) có gọi backup không?  
**Đáp án:** không, vì upstream thành công.

**Câu 2.** Mono.empty().onErrorResume(e -> backup()) có kết quả backup không?  
**Đáp án:** không, vì empty là thành công rỗng. Dùng switchIfEmpty nếu mục tiêu là backup khi rỗng.

**Câu 3.** Flux phát A, B rồi lỗi, fallback là Flux.just(C,D). Downstream nhận gì?  
**Đáp án:** A, B, C, D rồi hoàn thành, nếu fallback thành công và đủ demand.

**Câu 4.** Trong [1,2,3], truy vấn id 2 lỗi. Recovery đặt ngoài concatMap có chạy id 3 không?  
**Đáp án:** không. Nếu muốn xử lý tiếp, đặt recovery phù hợp trong Publisher cho từng id.

**Câu 5.** Backup cũng lỗi thì onErrorResume đầu tiên có tự thử lại không?  
**Đáp án:** không. Lỗi backup đi xuống downstream; muốn chuyển tiếp nguồn thứ ba cần handler khác.

**Câu 6.** Khi nào cần giữ lỗi gốc thay vì trả cache?  
**Đáp án:** khi lỗi không được phép phục hồi như validation, authentication/authorization hoặc khi dữ liệu cache không đủ điều kiện sử dụng.

**Bài tập A:** Sửa ví dụ ở phần 12, thêm **switchIfEmpty(Mono.defer(() -> cache("missing")))** cho case 3. Quan sát có dòng fallback missing và giá trị cache-missing.

**Bài tập B:** Chuyển onErrorResume trong case 5 ra ngoài concatMap. Thay fallback bằng Flux.just("global-backup") rồi kiểm tra có thực hiện item thứ ba từ primary hay không.

**Bài tập C:** Đặt doOnError trước và sau onErrorResume, làm remote lỗi nhưng cache thành công. Ghi lại vị trí nào nhận được primary error.

**Bài tập D:** Thêm timeout, retryWhen có giới hạn và fallback. Kiểm tra exception cuối cùng khi retry hết lượt và bảo đảm predicate fallback phù hợp với lớp lỗi thực tế.

## 18. Tài liệu tham khảo

- Reactor Reference Guide — Handling Errors / Fallback Method: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core — Mono API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core — Flux API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Reference Guide — Operator Choice: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams JVM Specification: https://github.com/reactive-streams/reactive-streams-jvm
