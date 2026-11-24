# Disposable và Subscription trong quản lý hủy nhận

Trong một ứng dụng reactive, đăng ký nhận dữ liệu cũng đồng nghĩa với việc bắt đầu một công việc có vòng đời riêng. Công việc đó có thể là lắng nghe sự kiện, gọi API, chạy timer, đọc dữ liệu từ socket hoặc xử lý một luồng dài hạn. Khi màn hình đóng, request không còn cần thiết hoặc service dừng, ứng dụng phải hủy đăng ký để ngừng nhận dữ liệu và giải phóng tài nguyên.

RxJava cung cấp `Disposable` để quản lý việc hủy đăng ký ở các kiểu nguồn như `Observable`, `Single`, `Maybe` và `Completable`. Với `Flowable`, RxJava tuân theo Reactive Streams và sử dụng `Subscription`, trong đó `request(n)` điều khiển demand còn `cancel()` dừng việc nhận dữ liệu. Hai cơ chế có quan hệ gần nhau nhưng có API và mục đích riêng.

Bài học thuộc chương **RxJava** của module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, cùng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách giữ handle của subscription, gom nhiều disposable theo chủ sở hữu, thay thế tác vụ đang chạy và bảo đảm việc hủy được kiểm thử rõ ràng.

## 1. Subscription có vòng đời từ lúc đăng ký đến khi kết thúc

Một nguồn reactive thường không thực thi cho đến khi có subscriber. Khi gọi `subscribe`, nguồn bắt đầu gửi tín hiệu theo hợp đồng của kiểu publisher đó. Subscription có thể kết thúc theo ba cách phổ biến:

- Nguồn hoàn tất bình thường bằng `onComplete`.
- Nguồn phát lỗi bằng `onError`.
- Consumer chủ động hủy vì không còn cần dữ liệu.

Hai trường hợp đầu là terminal signal từ nguồn. Trường hợp thứ ba là hành động điều khiển từ phía consumer. Hủy đăng ký không có nghĩa nguồn đã hoàn tất bình thường.

Với RxJava, các overload `subscribe` dạng lambda thường trả về một `Disposable`. Ứng dụng cần giữ đối tượng này nếu muốn chủ động hủy công việc sau đó.

```java
Disposable timer = Observable.interval(1, TimeUnit.SECONDS)
    .subscribe(value -> System.out.println("Tick: " + value));

// Khi không cần nhận tick nữa:
timer.dispose();
```

`dispose()` yêu cầu dừng subscription và truyền việc hủy về upstream. `isDisposed()` cho biết handle đã ở trạng thái disposed hay chưa:

```java
if (!timer.isDisposed()) {
    timer.dispose();
}
```

Thông thường không cần kiểm tra trước khi gọi `dispose()`, vì thao tác hủy được thiết kế để có thể gọi nhiều lần một cách an toàn. Kiểm tra `isDisposed()` hữu ích khi cần quan sát trạng thái hoặc tránh thực hiện thêm công việc ở tầng ứng dụng; nó không thay thế việc quản lý ownership.

## 2. `Disposable` và `Subscription` giải quyết hai việc khác nhau

`Disposable` là handle hủy đăng ký trong API RxJava. `Subscription` là hợp đồng của Reactive Streams, gồm cả demand và cancel.

| Đặc điểm | `Disposable` | `Subscription` |
|---|---|---|
| API chính | `dispose()`, `isDisposed()` | `request(long n)`, `cancel()` |
| Mục đích | Hủy đăng ký và ngừng nhận tín hiệu. | Điều khiển demand và hủy đăng ký. |
| Thường gặp ở | `Observable`, `Single`, `Maybe`, `Completable`; cả overload subscribe dạng lambda của `Flowable`. | `Flowable` khi làm việc trực tiếp với Reactive Streams `Subscriber`. |
| Backpressure | Không có API request trong chính handle. | `request(n)` cho biết subscriber có thể nhận thêm bao nhiêu phần tử. |
| Hủy | `dispose()` | `cancel()` |

`Observable` không hỗ trợ backpressure. `Flowable` hỗ trợ backpressure và triển khai `org.reactivestreams.Publisher`. Khi subscribe bằng một `Subscriber` tường minh, `Subscription` được trao qua `onSubscribe`:

```java
Flowable.range(1, 5).subscribe(new Subscriber<Integer>() {
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(Integer value) {
        System.out.println("Received: " + value);
        if (value == 3) {
            subscription.cancel();
        } else {
            subscription.request(1);
        }
    }

    @Override
    public void onError(Throwable error) {
        error.printStackTrace();
    }

    @Override
    public void onComplete() {
        System.out.println("Completed");
    }
});
```

Subscriber yêu cầu từng phần tử một. Sau khi nhận phần tử thứ ba, nó gọi `cancel()` nên không yêu cầu thêm dữ liệu. Đây là cách điều khiển trực tiếp demand và vòng đời của `Flowable`.

Nếu dùng overload lambda của `Flowable`, RxJava tạo subscriber nội bộ và trả về `Disposable` để consumer hủy đăng ký:

```java
Disposable handle = Flowable.range(1, 100)
    .subscribe(value -> process(value));

handle.dispose();
```

Trong trường hợp này, `Disposable` là handle tiện dụng do RxJava cung cấp; nó không làm `Flowable` mất hợp đồng backpressure. Khi cần điều khiển chính xác `request(n)`, hãy triển khai `Subscriber` và dùng `Subscription`.

## 3. Giữ `Disposable` thay vì bỏ quên subscription

Một lời gọi `subscribe()` không giữ handle khiến component khó hủy công việc khi vòng đời của nó kết thúc.

Không nên:

```java
void startWatching(String accountId) {
    accountRepository.observeBalance(accountId)
        .subscribe(this::renderBalance);
}
```

Nếu `observeBalance` phát vô hạn, subscription có thể tiếp tục giữ callback và tham chiếu đến component sau khi component không còn hiển thị. Điều này có thể gây rò rỉ bộ nhớ, cập nhật giao diện đã đóng hoặc tiếp tục tiêu thụ tài nguyên mạng.

Nên lưu handle:

```java
private Disposable balanceSubscription;

void startWatching(String accountId) {
    balanceSubscription = accountRepository
        .observeBalance(accountId)
        .subscribe(this::renderBalance, this::showError);
}

void stopWatching() {
    if (balanceSubscription != null) {
        balanceSubscription.dispose();
        balanceSubscription = null;
    }
}
```

Ví dụ này có một subscription. Nếu component tạo nhiều subscription, việc lưu từng handle riêng lẻ dễ dẫn đến quên hủy một nhánh. `CompositeDisposable` giúp quản lý một nhóm công việc cùng ownership.

## 4. Gom nhiều subscription bằng `CompositeDisposable`

`CompositeDisposable` là một container sở hữu nhiều `Disposable`. Khi gọi `dispose()` trên container, tất cả disposable đã thêm vào sẽ được hủy.

```java
private final CompositeDisposable disposables =
    new CompositeDisposable();

void start() {
    disposables.add(
        accountRepository.observeBalance()
            .subscribe(this::renderBalance, this::showError)
    );

    disposables.add(
        notificationRepository.observeNotifications()
            .subscribe(this::showNotification, this::showError)
    );

    disposables.add(
        Observable.interval(30, TimeUnit.SECONDS)
            .subscribe(ignored -> refreshStatus())
    );
}

void stop() {
    disposables.dispose();
}
```

Khi `stop()` được gọi, cả ba subscription đều được hủy. Cách này phù hợp với component hoặc service có nhiều nguồn dữ liệu nhưng cùng một thời điểm kết thúc.

### Phân biệt `clear()` và `dispose()`

Hai phương thức có ý nghĩa khác nhau:

- `clear()` hủy tất cả disposable hiện tại rồi làm rỗng container. Container vẫn có thể nhận thêm disposable mới.
- `dispose()` hủy tất cả disposable hiện tại và đánh dấu container đã kết thúc. Các disposable được thêm sau đó sẽ bị dispose ngay.

Ví dụ component có thể khởi động và dừng nhiều lần:

```java
private final CompositeDisposable screenTasks =
    new CompositeDisposable();

void onStart() {
    screenTasks.add(loadDashboard().subscribe(this::render));
}

void onStop() {
    screenTasks.clear();
}

void onDestroy() {
    screenTasks.dispose();
}
```

`clear()` phù hợp với một scope có thể được khởi động lại. `dispose()` phù hợp khi owner đã kết thúc vĩnh viễn, chẳng hạn component bị hủy hoặc service shutdown.

### `remove()` và `delete()`

Khi một tác vụ kết thúc sớm hơn owner, có thể bỏ nó khỏi container:

- `remove(disposable)` loại bỏ và dispose disposable đó.
- `delete(disposable)` loại bỏ khỏi container nhưng không dispose nó.

Chọn đúng phương thức theo ownership. Nếu container vẫn chịu trách nhiệm hủy tác vụ, dùng `remove`. Nếu quyền sở hữu được chuyển sang nơi khác và tác vụ cần tiếp tục, `delete` tránh hủy ngoài ý muốn.

`CompositeDisposable` hỗ trợ thao tác đồng thời trên container. Tuy vậy, điều đó không làm cho trạng thái mutable mà các callback truy cập trở nên thread-safe; dữ liệu dùng chung vẫn cần cơ chế đồng bộ hoặc thiết kế immutable phù hợp.

## 5. Thay thế tác vụ đang chạy bằng `SerialDisposable`

Một số component chỉ muốn giữ một tác vụ hiện tại. Khi có tác vụ mới, tác vụ cũ phải bị hủy. Ví dụ điển hình là tìm kiếm theo từ khóa: mỗi lần người dùng nhập, truy vấn trước không còn cần thiết.

`SerialDisposable` quản lý một disposable tại một thời điểm. Gọi `set(next)` thay disposable hiện tại và dispose disposable cũ.

```java
private final SerialDisposable activeSearch =
    new SerialDisposable();

void search(String query) {
    Disposable next = searchService.search(query)
        .subscribe(
            this::renderResults,
            this::showSearchError
        );

    activeSearch.set(next);
}

void closeSearch() {
    activeSearch.dispose();
}
```

Khi `search()` được gọi lần tiếp theo, subscription trước được dispose. Khi `closeSearch()` được gọi, subscription hiện tại cũng được hủy. Nếu `SerialDisposable` đã bị dispose, một disposable được đưa vào sau đó cũng sẽ bị dispose ngay.

### `set()` khác `replace()`

`SerialDisposable` cung cấp hai cách thay thế:

- `set(next)` thay disposable hiện tại và dispose disposable cũ.
- `replace(next)` thay disposable hiện tại nhưng không dispose disposable cũ.

Trong phần lớn tình huống thay request hoặc timer, `set()` là lựa chọn mong muốn vì tác vụ trước không còn được sử dụng. `replace()` chỉ phù hợp khi ứng dụng đã chuyển quyền sở hữu disposable cũ sang một nơi khác và có trách nhiệm quản lý nó.

Nếu cần kết hợp nhiều disposable thay thế theo chuỗi, `SequentialDisposable` cung cấp cơ chế tương tự để cập nhật tác vụ tuần tự. Hãy chọn một container phù hợp với vòng đời thực tế thay vì tự viết biến mutable và dispose thủ công trong nhiều nhánh.

### Dùng `switchMap` khi việc thay thế là một phần của luồng dữ liệu

Nếu yêu cầu mới đến từ một publisher, `switchMap` thường diễn đạt ý định tốt hơn việc tự quản lý `SerialDisposable`:

```java
Observable<SearchResult> results = searchQueries
    .debounce(250, TimeUnit.MILLISECONDS)
    .distinctUntilChanged()
    .switchMap(query -> searchService.search(query));
```

Khi có query mới, `switchMap` dispose subscription của publisher con trước và chuyển sang publisher con mới. Cơ chế thay thế được quản lý bên trong pipeline, giúp lỗi và vòng đời của các truy vấn nằm trong cùng chuỗi reactive.

## 6. Hủy subscription và giải phóng tài nguyên upstream

Dispose không chỉ ngăn consumer nhận dữ liệu. Nó còn yêu cầu upstream dừng công việc và giải phóng tài nguyên nếu nguồn hỗ trợ hủy.

Có thể quan sát lúc một `Observable` bị dispose bằng `doOnDispose`, và quan sát mọi kiểu kết thúc bằng `doFinally`:

```java
Observable<Event> events = eventSource
    .doOnDispose(() -> log.info("Observer disposed"))
    .doFinally(() -> log.info("Subscription finished"));
```

`doOnDispose` chỉ chạy khi subscription bị dispose. `doFinally` chạy sau complete, error hoặc dispose. Dùng `doFinally` khi cần metric hoặc cleanup đồng bộ luôn phải được thực hiện sau mọi kiểu kết thúc.

Ví dụ tích hợp listener bên ngoài:

```java
Observable<Event> observeEvents() {
    return Observable.create(emitter -> {
        Listener listener = event -> {
            if (!emitter.isDisposed()) {
                emitter.onNext(event);
            }
        };

        eventBus.register(listener);
        emitter.setCancellable(() -> eventBus.unregister(listener));
    });
}
```

Khi downstream dispose, cancellable được gọi để tháo listener. Nếu không tháo listener, event bus có thể tiếp tục giữ callback và component liên quan. Kiểm tra `emitter.isDisposed()` giúp tránh gửi thêm dữ liệu khi đã hủy, nhưng cleanup listener mới là phần giải phóng tài nguyên quan trọng.

Với nguồn có thao tác cleanup bất đồng bộ, cần kết nối việc cleanup với API nguồn hoặc một publisher quản lý tài nguyên. `doFinally` nhận callback đồng bộ; nó không chờ một publisher cleanup bất đồng bộ được trả về từ callback.

## 7. Cancellation là hợp tác, không phải rollback

Khi gọi `dispose()`, consumer thông báo không cần thêm tín hiệu. Upstream có thể dừng ngay nếu nguồn hỗ trợ hủy. Tuy nhiên, một callback đã bắt đầu chạy hoặc một thao tác I/O không hỗ trợ interrupt có thể vẫn tiếp tục.

Các điểm cần hiểu:

- Dispose không đảo ngược side effect đã xảy ra, chẳng hạn một giao dịch đã được gửi đến hệ thống thanh toán.
- Callback đang thực thi tại thời điểm dispose có thể đã bắt đầu và không thể bị thu hồi.
- Một API blocking có thể tiếp tục chạy nếu thư viện không hỗ trợ cancel/interrupt.
- Dispose không phát `onComplete` để báo hoàn tất bình thường.
- Nếu công việc cần rollback nghiệp vụ, phải gọi API rollback hoặc compensation riêng.

Ví dụ, hủy một request HTTP có thể đóng kết nối hoặc ngừng đọc response tùy client. Điều đó không bảo đảm server chưa xử lý request. Với thao tác ghi dữ liệu, cần idempotency key hoặc cơ chế đối soát nếu client không biết server đã nhận và thực hiện đến đâu.

## 8. Phân biệt `dispose`, `take`, `takeUntil` và `timeout`

Không phải lúc nào cũng cần giữ một handle và gọi dispose thủ công. Một số operator biểu diễn điều kiện kết thúc ngay trong pipeline.

| Cơ chế | Điều kiện | Tín hiệu phía downstream |
|---|---|---|
| `dispose()` | Owner chủ động hủy handle. | Ngừng nhận; không phát terminal signal chỉ để xác nhận hủy. |
| `take(n)` | Đã nhận đủ n phần tử. | Hoàn tất bình thường sau phần tử thứ n và hủy upstream. |
| `takeUntil(other)` | Publisher điều kiện phát tín hiệu. | Hoàn tất khi điều kiện kích hoạt và hủy upstream. |
| `timeout(duration)` | Không có tín hiệu trong thời hạn. | Phát lỗi timeout, đồng thời hủy upstream. |
| `switchMap` | Nguồn ngoài phát giá trị mới. | Dispose publisher con cũ và chuyển sang publisher con mới. |

Ví dụ giới hạn số phần tử:

```java
Observable<Event> firstTen = eventSource.take(10);
```

Sau mười phần tử, downstream hoàn tất và subscription upstream được dispose. Không cần giữ handle chỉ để hủy sau phần tử thứ mười.

Ví dụ kết thúc theo tín hiệu lifecycle:

```java
Observable<Event> screenEvents = eventSource
    .takeUntil(screenDestroyed);
```

Khi `screenDestroyed` phát tín hiệu, subscription đến `eventSource` bị hủy và luồng phía dưới hoàn tất. Cách này hữu ích khi vòng đời được biểu diễn bằng một publisher.

Ví dụ timeout:

```java
Single<Profile> profile = profileService.load(userId)
    .timeout(3, TimeUnit.SECONDS);
```

Nếu nguồn không phát tín hiệu trong ba giây, downstream nhận lỗi timeout. Timeout không bảo đảm thao tác phía server đã bị rollback; nó chỉ kết thúc subscription phía client và yêu cầu upstream dừng.

## 9. Hủy trong pipeline `Flowable` và backpressure

Với `Flowable`, `Subscription` quản lý cả demand và cancellation. Nếu subscriber không còn cần dữ liệu, gọi `cancel()` để ngừng nhận. Nếu dùng lambda `subscribe`, `Disposable` trả về từ RxJava là handle tiện dụng để hủy subscriber nội bộ.

```java
Disposable subscription = Flowable.range(1, 1_000_000)
    .onBackpressureBuffer(128)
    .observeOn(Schedulers.computation())
    .subscribe(this::process, this::handleError);

// Khi component kết thúc:
subscription.dispose();
```

Backpressure kiểm soát số phần tử được yêu cầu; cancellation kết thúc việc nhận dữ liệu khi consumer không còn cần subscription. Hai cơ chế phối hợp nhưng không thay thế nhau. Một subscriber có demand bằng 0 vẫn có thể giữ subscription hoạt động; nó chưa hủy chỉ vì chưa request thêm.

Khi hủy, `Flowable` truyền cancellation ngược về upstream. Các operator có thể giải phóng queue và hủy publisher con. Với một nguồn tùy chỉnh, hãy triển khai `Subscription.cancel()` để ngừng phát và đóng tài nguyên tương ứng.

Không nên giữ một queue không giới hạn rồi hy vọng dispose sẽ giải quyết mọi tình trạng quá tải. Hãy thiết kế backpressure, giới hạn buffer và vòng đời subscription cùng nhau.

## 10. Quản lý scope theo component hoặc service

Một quy tắc thực tế là container disposable nên có cùng vòng đời với thành phần sở hữu các subscription.

| Owner | Nơi lưu handle | Khi hủy |
|---|---|---|
| Một request | Biến cục bộ hoặc scope request | Khi response bị hủy hoặc request kết thúc. |
| Một màn hình/component | `CompositeDisposable` của component | `clear()` khi tạm dừng; `dispose()` khi hủy vĩnh viễn. |
| Một tác vụ thay thế | `SerialDisposable` | `set()` khi có tác vụ mới; `dispose()` khi owner kết thúc. |
| Một service dài hạn | `CompositeDisposable` của service | `dispose()` trong lifecycle shutdown. |
| Một subscriber `Flowable` điều khiển demand | `Subscription` | `cancel()` khi không còn cần dữ liệu. |

Không nên dùng một `CompositeDisposable` toàn cục cho các component có vòng đời khác nhau. Nếu một màn hình gọi `clear()` trên container dùng chung, nó có thể hủy subscription của màn hình khác. Mỗi owner nên quản lý đúng những công việc mà nó chịu trách nhiệm kết thúc.

### Không dùng `isDisposed()` làm cơ chế đồng bộ dữ liệu

`isDisposed()` là thông tin trạng thái của handle, không phải khóa đồng bộ. Một thread có thể kiểm tra `false`, rồi thread khác dispose trước khi thread thứ nhất thực hiện hành động tiếp theo. Nếu callback truy cập trạng thái mutable dùng chung, hãy dùng cơ chế thread-safe phù hợp như atomic, lock có phạm vi nhỏ hoặc tuần tự hóa trên scheduler.

## 11. Kiểm thử cancellation bằng `TestObserver` và `TestSubscriber`

RxJava cung cấp `TestObserver` và `TestSubscriber` để kiểm thử tín hiệu, demand và việc hủy mà không cần phụ thuộc thời gian thực.

### Kiểm thử `Disposable` của `Observable`

```java
TestScheduler scheduler = new TestScheduler();

TestObserver<Long> observer = Observable.interval(
        1, TimeUnit.SECONDS, scheduler
    )
    .test();

scheduler.advanceTimeBy(2, TimeUnit.SECONDS);
observer.assertValues(0L, 1L);

observer.dispose();
scheduler.advanceTimeBy(5, TimeUnit.SECONDS);

observer.assertValues(0L, 1L);
assertTrue(observer.isDisposed());
```

`TestScheduler` điều khiển thời gian ảo. Sau khi observer dispose, việc tiến thời gian thêm năm giây không tạo thêm phần tử cho observer. Bài kiểm thử không cần `Thread.sleep` và chạy nhanh, ổn định.

### Kiểm thử `Subscription` và demand của `Flowable`

```java
TestSubscriber<Integer> subscriber = Flowable.range(1, 5)
    .test(0);

subscriber.assertNoValues();
subscriber.request(2);
subscriber.assertValues(1, 2);

subscriber.cancel();
subscriber.request(3);
subscriber.assertValues(1, 2);
subscriber.assertNotComplete();
```

Subscriber bắt đầu với demand bằng 0 nên chưa nhận phần tử. Sau khi request hai, nó nhận đúng hai phần tử. Khi cancel, request tiếp theo không làm nguồn phát thêm dữ liệu. `TestSubscriber` giúp kiểm tra cả backpressure lẫn cancellation.

### Kiểm thử cleanup khi dispose

```java
AtomicBoolean cleaned = new AtomicBoolean();

TestObserver<Long> observer = Observable.interval(
        1, TimeUnit.SECONDS, scheduler
    )
    .doOnDispose(() -> cleaned.set(true))
    .test();

observer.dispose();

assertTrue(cleaned.get());
```

Bài kiểm thử xác minh cleanup callback được gọi khi observer dispose. Với cleanup bất đồng bộ hoặc tài nguyên ngoài tiến trình, cần kiểm thử thêm trạng thái cuối của tài nguyên thay vì chỉ xác minh callback đã được gọi.

## 12. Tình huống thực tế: quản lý nhiều request trong màn hình tài khoản

Một màn hình tài khoản theo dõi số dư, thông báo và trạng thái đồng bộ. Khi màn hình xuất hiện, ba nguồn được subscribe. Khi màn hình tạm dừng, tất cả subscription phải dừng để tránh cập nhật giao diện ẩn và tiêu thụ tài nguyên không cần thiết.

```java
final class AccountScreen {
    private final CompositeDisposable screenTasks =
        new CompositeDisposable();

    void onStart() {
        screenTasks.add(
            accountRepository.observeBalance()
                .subscribe(this::renderBalance, this::showError)
        );

        screenTasks.add(
            notificationRepository.observeUnreadCount()
                .subscribe(this::renderUnreadCount, this::showError)
        );

        screenTasks.add(
            syncService.observeSyncState()
                .subscribe(this::renderSyncState, this::showError)
        );
    }

    void onStop() {
        screenTasks.clear();
    }

    void onDestroy() {
        screenTasks.dispose();
    }

    private void renderBalance(BigDecimal balance) { /* UI update */ }
    private void renderUnreadCount(Integer count) { /* UI update */ }
    private void renderSyncState(SyncState state) { /* UI update */ }
    private void showError(Throwable error) { /* error handling */ }
}
```

`clear()` cho phép component subscribe lại trong lần `onStart()` tiếp theo. Khi component bị hủy hoàn toàn, `dispose()` đánh dấu container kết thúc. Nếu có lời gọi `onStart()` sau khi container đã dispose, disposable mới thêm vào sẽ bị dispose ngay; vì vậy lifecycle của component cần gọi đúng thứ tự.

Nếu một request tìm kiếm trong màn hình cần được thay thế mỗi khi người dùng nhập, dùng `SerialDisposable` hoặc `switchMap` cho riêng request đó. Không cần hủy toàn bộ subscription của màn hình mỗi lần query thay đổi.

## 13. Những lỗi quản lý cancellation thường gặp

### Không giữ handle

Subscribe mà không lưu `Disposable` khiến component không thể hủy subscription khi kết thúc. Hãy lưu handle hoặc thêm ngay vào container sở hữu.

### Dùng `dispose()` thay cho `clear()` ở scope có thể khởi động lại

Sau `dispose()`, container đã kết thúc và không nhận thêm công việc. Với component có thể start/stop nhiều lần, dùng `clear()` khi tạm dừng và chỉ `dispose()` khi owner bị hủy vĩnh viễn.

### Dùng `delete()` khi vẫn muốn container chịu trách nhiệm hủy

`delete()` chỉ bỏ disposable khỏi container, không hủy nó. Nếu không chuyển ownership sang nơi khác, subscription có thể tiếp tục chạy mà không còn handle được quản lý.

### Nghĩ rằng dispose đồng nghĩa callback đang chạy bị dừng tức thì

Cancellation là hợp tác. Callback đã bắt đầu hoặc API blocking không hỗ trợ hủy có thể tiếp tục. Hãy kiểm tra khả năng cancel của nguồn và cấu hình timeout ở client/driver.

### Dùng một container cho nhiều owner

Một component gọi `clear()` có thể vô tình hủy công việc của component khác. Container phải có phạm vi ownership rõ ràng.

### Nhầm cancel với complete

Dispose không phải `onComplete`. Nếu cần cleanup cho cả complete, error và cancel, dùng operator lifecycle phù hợp như `doFinally`, hoặc cơ chế quản lý tài nguyên của nguồn.

## 14. Checklist thiết kế vòng đời subscription

- Giữ `Disposable` từ các overload `subscribe` dạng lambda nếu cần hủy chủ động.
- Dùng `Subscription` trực tiếp khi cần điều khiển `request(n)` và `cancel()` của `Flowable`.
- Không nhầm `Observable` với `Flowable`: `Observable` không có backpressure.
- Gom công việc cùng owner bằng `CompositeDisposable`.
- Dùng `clear()` cho scope có thể tái sử dụng; dùng `dispose()` khi owner kết thúc vĩnh viễn.
- Dùng `SerialDisposable.set()` khi tác vụ mới thay thế tác vụ cũ.
- Dùng `switchMap` nếu việc thay publisher con có thể được biểu diễn ngay trong pipeline.
- Tháo listener, timer và tài nguyên ngoài trong cleanup khi upstream bị dispose.
- Hiểu rằng cancellation không rollback side effect đã xảy ra và không bảo đảm API blocking dừng ngay.
- Kết hợp backpressure, concurrency và buffer với vòng đời cancellation.
- Kiểm thử `Disposable`, `Subscription`, demand và cleanup bằng `TestObserver`, `TestSubscriber`, `TestScheduler`.
- Đảm bảo mỗi subscription có một owner rõ ràng và được kết thúc đúng lifecycle.

`Disposable` giúp ứng dụng quản lý vòng đời đăng ký trong các API RxJava; `Subscription` bổ sung điều khiển demand và cancel cho `Flowable` theo Reactive Streams. Khi giữ đúng handle, gom công việc theo owner và gắn cleanup với cancellation, pipeline có thể dừng đúng lúc, tránh giữ listener hoặc tài nguyên không còn cần thiết, đồng thời duy trì hành vi backpressure có thể kiểm soát.
