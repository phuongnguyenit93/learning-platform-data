# Scheduler, subscribeOn và observeOn trong RxJava

RxJava xử lý dữ liệu bằng các chuỗi sự kiện, nhưng việc một chuỗi phát tín hiệu không đồng nghĩa mọi thao tác đều chạy trên cùng một thread. Khi một ứng dụng đọc dữ liệu từ mạng, biến đổi dữ liệu và cập nhật giao diện, ta cần chọn nơi thực thi cho từng phần công việc. RxJava dùng **Scheduler** để biểu diễn môi trường thực thi, **subscribeOn** để điều phối quá trình đăng ký vào nguồn và **observeOn** để chuyển việc xử lý tín hiệu ở phía downstream.

Bài học thuộc chương **RxJava** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trong phần này, ta tập trung vào RxJava 3 và cách lựa chọn Scheduler, đặt ranh giới thread, quản lý vòng đời subscription và kiểm thử thời gian thực thi.

## Scheduler là gì?

Một **Scheduler** là abstraction mà RxJava dùng để lập lịch công việc. Nó quyết định tác vụ được thực thi trên thread hiện tại, một thread dùng chung, một pool thread hay một executor do ứng dụng cung cấp. Scheduler không thay đổi ý nghĩa của dữ liệu; nó thay đổi cách và thời điểm các tác vụ của pipeline được thực thi.

Một pipeline có thể gồm nhiều loại công việc:

- Đọc tệp hoặc gọi thư viện HTTP đồng bộ: có thể phải chờ I/O.
- Parse JSON, tính toán hoặc lọc dữ liệu lớn: chủ yếu dùng CPU.
- Cập nhật component giao diện: phải chạy trên thread giao diện của nền tảng.
- Chạy tác vụ tuần tự: có thể cần một worker để giữ thứ tự thực thi.

Đưa mọi công việc vào cùng một thread có thể làm giao diện bị treo hoặc khiến các tác vụ độc lập chờ nhau. Ngược lại, tạo quá nhiều thread cũng làm tăng chi phí chuyển ngữ cảnh và sử dụng bộ nhớ. Chọn Scheduler theo loại công việc giúp kiểm soát các đánh đổi đó.

## Các Scheduler thường dùng trong RxJava

RxJava 3 cung cấp các Scheduler tĩnh qua lớp **Schedulers**:

| Scheduler | Đặc điểm | Trường hợp sử dụng |
|---|---|---|
| `Schedulers.io()` | Tái sử dụng worker cho các tác vụ I/O; có thể tạo thêm thread khi nhu cầu tăng và thu hồi worker nhàn rỗi | Gọi API đồng bộ, JDBC, đọc tệp hoặc thư viện blocking |
| `Schedulers.computation()` | Pool worker có kích thước dựa trên số CPU khả dụng | Parse, tính toán và biến đổi CPU-bound |
| `Schedulers.single()` | Một thread dùng chung cho các tác vụ cần thực thi tuần tự | Tác vụ nhẹ cần thứ tự chung |
| `Schedulers.newThread()` | Tạo thread mới cho worker | Trường hợp đặc biệt cần worker riêng; tránh tạo liên tục cho tác vụ ngắn |
| `Schedulers.trampoline()` | Xếp tác vụ vào hàng đợi và chạy trên thread hiện tại | Điều phối tuần tự mà không chuyển sang thread khác |
| `Schedulers.from(executor)` | Dùng Executor do ứng dụng cung cấp | Cần kiểm soát pool, giới hạn tài nguyên hoặc tích hợp executor có sẵn |

Không nên dùng `Schedulers.computation()` cho I/O blocking. Các worker của Scheduler này được thiết kế cho công việc CPU-bound; nếu chúng bị giữ trong lúc chờ mạng hoặc đĩa, các phép tính khác có thể bị trì hoãn.

`Schedulers.io()` phù hợp với API đồng bộ có thời gian chờ, nhưng pool có thể tăng theo lượng công việc đồng thời. Nó không phải hàng đợi có giới hạn concurrency cho toàn bộ ứng dụng. Nếu cần giới hạn số thao tác blocking, có thể tạo một `ExecutorService` có kích thước và hàng đợi phù hợp rồi bọc bằng `Schedulers.from(executor)`. Ứng dụng cần quản lý vòng đời của executor do mình tạo.

`Schedulers.single()` dùng một thread chung cho các subscription sử dụng Scheduler đó. Nó hữu ích cho công việc tuần tự nhẹ, nhưng một tác vụ blocking dài có thể làm mọi tác vụ khác trên worker phải chờ. `Schedulers.newThread()` tạo worker mới thay vì tái sử dụng pool, nên thường không phù hợp khi có nhiều tác vụ ngắn.

Trên Android, ứng dụng thường cần cập nhật giao diện bằng Scheduler của RxAndroid:

~~~java
AndroidSchedulers.mainThread()
~~~

Đây là Scheduler bổ sung từ thư viện RxAndroid, không phải một phần của RxJava core. Với Java desktop hoặc framework giao diện khác, cần dùng Scheduler do nền tảng đó cung cấp.

## subscribeOn điều phối quá trình đăng ký vào nguồn

`subscribeOn(scheduler)` lập lịch thao tác subscribe vào nguồn upstream trên Scheduler được chọn. Với nguồn đồng bộ, phần công việc diễn ra bên trong quá trình subscribe thường cũng chạy trên worker đó.

Ví dụ, đọc tệp bằng API đồng bộ:

~~~java
Single<String> fileContent = Single.fromCallable(
        () -> Files.readString(path))
    .subscribeOn(Schedulers.io());
~~~

`Single.fromCallable` trì hoãn lời gọi `Files.readString` đến lúc subscribe và chuyển exception được ném thành `onError`. `subscribeOn(Schedulers.io())` đưa quá trình gọi này lên worker dành cho I/O. Thread gọi `subscribe()` không phải trực tiếp chờ việc đọc tệp hoàn tất.

Nếu viết như sau:

~~~java
Single<String> fileContent =
    Single.just(Files.readString(path))
        .subscribeOn(Schedulers.io());
~~~

thì `Files.readString(path)` đã được thực thi trước khi `Single.just` nhận đối số. `subscribeOn` không thể chuyển ngược một thao tác đã xảy ra. Với lời gọi đồng bộ có thể ném exception, hãy đặt lời gọi bên trong `fromCallable`, `fromSupplier` hoặc một nguồn trì hoãn thích hợp.

`subscribeOn` cũng không biến API blocking thành API non-blocking. Nó chỉ chuyển công việc sang Scheduler phù hợp để không chiếm thread gọi subscribe, ví dụ event loop hoặc thread giao diện. Nếu nguồn là API bất đồng bộ tự quản lý thread và callback, `subscribeOn` chủ yếu điều phối lúc đăng ký; nó không ép mọi callback của thư viện đó phát trên worker đã chọn.

Trong đa số pipeline, nên đặt một `subscribeOn` rõ ràng gần nguồn. Có thể xuất hiện nhiều `subscribeOn` trong chuỗi lồng nhau, nhưng chúng có thể tạo thêm các bước lập lịch và làm khó việc xác định nguồn chạy ở đâu. Dùng `observeOn` khi mục tiêu là chuyển phần xử lý tín hiệu phía sau một ranh giới cụ thể.

## observeOn chuyển việc xử lý tín hiệu downstream

`observeOn(scheduler)` tạo ranh giới bất đồng bộ: các tín hiệu từ vị trí toán tử này trở đi được xếp lịch để xử lý trên Scheduler đã chọn. Các toán tử đặt trước `observeOn` vẫn chạy theo thread của upstream; các toán tử đặt sau nó chạy trên Scheduler được chọn, trừ khi có một ranh giới khác được thêm vào sau đó.

~~~java
Observable<Result> results = source
    .subscribeOn(Schedulers.io())
    .map(this::decode)
    .observeOn(Schedulers.computation())
    .map(this::calculate);
~~~

Trong ví dụ:

- Nguồn được subscribe trên `Schedulers.io()`.
- `decode` nằm trước `observeOn`, nên chạy theo thread phát tín hiệu từ nguồn.
- `calculate` nằm sau `observeOn`, nên được xử lý trên `Schedulers.computation()`.

Nếu `decode` cũng là phép tính CPU nặng, có thể đặt `observeOn(Schedulers.computation())` trước `decode`. Vị trí ranh giới nên phản ánh phần công việc muốn chuyển, không chỉ dựa vào thói quen đặt toán tử.

Có thể chuyển lần nữa để cập nhật giao diện:

~~~java
source
    .subscribeOn(Schedulers.io())
    .observeOn(Schedulers.computation())
    .map(this::buildViewModel)
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(view::render, view::showError);
~~~

Ở đây, `buildViewModel` chạy trên Scheduler tính toán, còn `view.render` và `view.showError` chạy trên main thread Android. Nếu không dùng Android, thay Scheduler cuối bằng Scheduler giao diện tương ứng.

## So sánh subscribeOn và observeOn

Hai toán tử giải quyết hai nhu cầu khác nhau:

| Tiêu chí | `subscribeOn` | `observeOn` |
|---|---|---|
| Tác động chính | Lập lịch quá trình subscribe vào nguồn upstream | Lập lịch việc xử lý tín hiệu downstream |
| Vị trí thường đặt | Gần nguồn | Trước nhóm toán tử cần chạy trên Scheduler mới |
| Số lần dùng | Thường một lần để xác định nơi nguồn bắt đầu | Có thể nhiều lần để tạo các ranh giới thực thi |
| Ví dụ | Chuyển lời gọi JDBC đồng bộ sang I/O worker | Chuyển kết quả sang CPU worker rồi sang UI thread |

Một cách nhớ hữu ích: `subscribeOn` trả lời “đăng ký và khởi chạy nguồn ở đâu?”, còn `observeOn` trả lời “từ đây trở xuống, xử lý tín hiệu ở đâu?”.

Không nên đặt `observeOn(Schedulers.io())` sau một nguồn blocking và cho rằng thao tác blocking trước đó đã được chuyển đi. Nguồn đã chạy trong quá trình subscribe trước khi tín hiệu tới `observeOn`. Để cách ly lời gọi blocking, hãy dùng `subscribeOn` tại nguồn.

## observeOn, hàng đợi và backpressure

`observeOn` cần chuyển tín hiệu giữa hai môi trường thực thi, nên nó sử dụng hàng đợi để giữ phần tử chờ downstream xử lý. Điều này tạo ra ranh giới bất đồng bộ và có thể làm tăng bộ nhớ sử dụng nếu upstream phát nhanh hơn downstream tiêu thụ.

RxJava có hai họ API quan trọng:

- `Observable` không hỗ trợ giao thức backpressure. Nếu nguồn phát nhanh hơn downstream, hàng đợi của các toán tử như `observeOn` có thể tích lũy nhiều phần tử.
- `Flowable` hỗ trợ backpressure. `observeOn` phối hợp demand và prefetch để lấy phần tử từ upstream theo lô, đồng thời quản lý hàng đợi theo chính sách của toán tử.

Ví dụ với `Flowable`:

~~~java
Flowable<Integer> processed = Flowable.range(1, 1_000_000)
    .observeOn(Schedulers.computation(), false, 128)
    .map(this::cpuHeavyTransform);
~~~

Tham số `128` là kích thước prefetch được yêu cầu cho `observeOn` trong ví dụ. Nó không có nghĩa toàn bộ pipeline chỉ bao giờ dùng đúng 128 phần tử bộ nhớ: downstream có thể yêu cầu thêm theo cơ chế replenishment, và các toán tử khác cũng có thể có hàng đợi riêng. Hãy chọn prefetch dựa trên độ trễ, kích thước phần tử và tốc độ xử lý thực tế.

Nếu dữ liệu có thể được bỏ hoặc gộp, hãy chọn chính sách backpressure phù hợp như `onBackpressureDrop`, `onBackpressureLatest` hoặc `onBackpressureBuffer` trước ranh giới xử lý tương ứng. Nếu mọi phần tử đều quan trọng, cần kiểm soát tốc độ nguồn hoặc thiết kế lưu trữ và giới hạn hàng đợi. Đổi Scheduler không tự giải quyết quá tải.

## Một pipeline có nhiều loại công việc

Giả sử ứng dụng tải danh sách đơn hàng, tính tổng giá trị và cập nhật giao diện. Có thể chia pipeline theo trách nhiệm:

~~~java
Disposable subscription = Flowable.fromCallable(
        () -> legacyOrderClient.fetchOrders(customerId))
    .subscribeOn(Schedulers.io())
    .flatMapIterable(orders -> orders)
    .observeOn(Schedulers.computation())
    .map(this::calculateOrderSummary)
    .toList()
    .toFlowable()
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(
        view::renderSummaries,
        view::showError
    );
~~~

Đoạn mã minh họa các ranh giới:

1. `fromCallable` trì hoãn API đồng bộ cho đến subscribe.
2. `subscribeOn(io())` cách ly thời gian chờ của client.
3. `flatMapIterable` phát từng đơn hàng.
4. `observeOn(computation())` chuyển việc tính summary sang pool CPU.
5. `toList()` gom các summary thành một danh sách sau khi nguồn hoàn tất.
6. `observeOn(mainThread())` chuyển callback cuối về thread giao diện.

Nếu `fetchOrders` đã là API bất đồng bộ trả về Publisher, không cần bọc nó bằng `fromCallable` hoặc chuyển nó sang I/O chỉ vì nó thực hiện mạng. Hãy kiểm tra hợp đồng của client và đặt Scheduler theo hành vi thật của nguồn.

`toList()` giữ toàn bộ kết quả trong bộ nhớ cho đến khi upstream hoàn tất. Nếu danh sách có thể rất lớn hoặc cần hiển thị tăng dần, hãy cân nhắc giữ luồng phần tử và cập nhật giao diện theo lô phù hợp.

## Quản lý subscription và Scheduler

`subscribe()` thường trả về một `Disposable`. Khi màn hình hoặc thành phần sở hữu pipeline không còn cần kết quả, hãy hủy subscription:

~~~java
private final CompositeDisposable disposables =
    new CompositeDisposable();

void loadScreen() {
    Disposable disposable = repository.load()
        .subscribeOn(Schedulers.io())
        .observeOn(AndroidSchedulers.mainThread())
        .subscribe(view::render, view::showError);

    disposables.add(disposable);
}

void clearScreen() {
    disposables.clear();
}
~~~

`dispose()` yêu cầu chuỗi subscription ngừng nhận tín hiệu và hủy các tác vụ đã lập lịch nếu có thể. Một lời gọi blocking đã bắt đầu có thể không dừng ngay lập tức; khả năng ngắt phụ thuộc nguồn và API được gọi. Vì vậy, cancellation cần được kết hợp với timeout, giới hạn thời gian và API I/O có khả năng hủy khi nghiệp vụ yêu cầu.

Các Scheduler dùng chung như `Schedulers.io()` và `Schedulers.computation()` được RxJava quản lý. Thông thường, một subscription không nên tự shutdown Scheduler toàn cục sau khi hoàn tất. Nếu ứng dụng tạo Executor riêng và bọc bằng `Schedulers.from`, ứng dụng cần quản lý vòng đời Executor đó theo phạm vi sở hữu của mình.

Khi dùng `Scheduler.Worker` trực tiếp, Worker là tài nguyên lập lịch có thể dispose. Hãy dispose Worker khi công việc kết thúc để giải phóng hàng đợi và tác vụ đã lên lịch không còn cần thiết.

## Kiểm thử việc lập lịch bằng TestScheduler

Kiểm thử phụ thuộc thời gian hoặc Scheduler không nên dựa vào `Thread.sleep`, vì test sẽ chậm và dễ chập chờn. RxJava cung cấp **TestScheduler** để điều khiển thời gian và tác vụ một cách tường minh.

Kiểm tra `subscribeOn` trì hoãn việc chạy nguồn cho đến khi Scheduler được kích hoạt:

~~~java
TestScheduler scheduler = new TestScheduler();
AtomicInteger calls = new AtomicInteger();

Single<Integer> source = Single.fromCallable(calls::incrementAndGet)
    .subscribeOn(scheduler);

TestObserver<Integer> observer = source.test();

assertEquals(0, calls.get());
scheduler.triggerActions();

observer.assertResult(1);
assertEquals(1, calls.get());
~~~

Trước `triggerActions`, subscription đã được đăng ký nhưng tác vụ nguồn vẫn đang chờ trên TestScheduler. Khi kích hoạt các tác vụ đã lên lịch, nguồn chạy và phát kết quả.

Kiểm tra `observeOn` tạo ranh giới cho callback downstream:

~~~java
TestScheduler scheduler = new TestScheduler();

TestObserver<Integer> observer = Observable.just(1, 2, 3)
    .observeOn(scheduler)
    .test();

observer.assertNoValues();
scheduler.triggerActions();
observer.assertResult(1, 2, 3);
~~~

Nguồn `Observable.just` phát đồng bộ, nhưng các thông báo phía sau `observeOn` được xếp vào TestScheduler. Chỉ sau `triggerActions`, observer mới nhận các phần tử.

Có thể điều khiển thời gian của một nguồn định kỳ:

~~~java
TestScheduler clock = new TestScheduler();

TestObserver<Long> observer = Observable
    .interval(1, TimeUnit.SECONDS, clock)
    .take(2)
    .test();

observer.assertNoValues();
clock.advanceTimeBy(1, TimeUnit.SECONDS);
observer.assertValues(0L);
clock.advanceTimeBy(1, TimeUnit.SECONDS);
observer.assertResult(0L, 1L);
~~~

`advanceTimeBy` di chuyển đồng hồ ảo và chạy các tác vụ đến hạn. Cách kiểm thử này giúp xác minh hành vi theo thời gian mà không cần chờ thật.

Để test service dễ kiểm soát, nên truyền Scheduler vào constructor hoặc phương thức thay vì gọi trực tiếp `Schedulers.io()` ở nhiều nơi. Trong production có thể truyền Scheduler thật; trong test truyền `TestScheduler`. Điều này giúp kiểm thử cả vị trí chuyển thread lẫn thời điểm tác vụ chạy.

## Những lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng `Schedulers.computation()` cho I/O blocking | Giữ worker CPU trong lúc chờ I/O | Dùng `Schedulers.io()` hoặc Executor có giới hạn |
| Dùng `just(blockingCall())` rồi thêm `subscribeOn` | Lời gọi đã chạy trước khi subscribe | Dùng `fromCallable` |
| Dùng `observeOn` để chuyển nguồn blocking | `observeOn` chỉ tác động tới downstream | Đặt `subscribeOn` tại nguồn |
| Chuyển Scheduler ở mọi toán tử | Tạo nhiều ranh giới và hàng đợi không cần thiết | Chỉ chuyển ở ranh giới trách nhiệm |
| Cho rằng `Observable.observeOn` có backpressure | Observable không có demand protocol | Dùng Flowable hoặc chính sách giới hạn dữ liệu |
| Không dispose subscription khi màn hình đóng | Callback có thể tiếp tục giữ tham chiếu tới view | Quản lý bằng `CompositeDisposable` theo lifecycle |
| Gọi `Thread.sleep` trong kiểm thử | Test chậm và không ổn định | Dùng `TestScheduler` |

## Nguyên tắc lựa chọn Scheduler

Trước khi đặt Scheduler cho một pipeline RxJava, hãy xác định:

1. Nguồn là đồng bộ, blocking hay đã bất đồng bộ?
2. Công việc chủ yếu chờ I/O hay sử dụng CPU?
3. Nhóm toán tử nào cần chạy trên cùng môi trường thực thi?
4. Có cần chuyển sang thread giao diện ở cuối pipeline không?
5. Hàng đợi của `observeOn` có thể tích lũy nhiều phần tử không và nguồn có hỗ trợ backpressure không?
6. Ai sở hữu subscription, Executor hoặc Worker và chịu trách nhiệm dispose chúng?
7. Có thể inject Scheduler để kiểm thử bằng `TestScheduler` không?

Scheduler xác định nơi tác vụ được thực thi; `subscribeOn` điều phối việc đăng ký và khởi chạy nguồn; `observeOn` chuyển việc xử lý tín hiệu ở phía downstream. Khi đặt các ranh giới đúng theo loại công việc, kiểm soát hàng đợi và quản lý subscription theo vòng đời ứng dụng, pipeline RxJava sẽ dễ dự đoán và ít gây nghẽn hơn.
